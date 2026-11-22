"""
Sampling mechanism that collects a series of measurements from one ammeter.
"""

import logging
import math
import time
from dataclasses import dataclass
from typing import Optional

from Ammeters.client import AmmeterClient
from src.exceptions.ammeter_exceptions import AmmeterError

logger = logging.getLogger(__name__)


@dataclass
class Sample:
    """
    One measurement taken during a sampling run.
    """

    # Position of the sample in the run, starting from 0.
    index: int
    # Seconds since the start of the sampling run.
    timestamp: float
    # Measured current in amperes, or None if the measurement failed.
    current: Optional[float]
    # Error message if the measurement failed, otherwise None.
    error: Optional[str] = None


def resolve_sampling(measurements_count: Optional[int] = None,
                     total_duration_seconds: Optional[float] = None,
                     sampling_frequency_hz: Optional[float] = None) -> tuple[int, float]:
    """
    Work out the number of samples and the interval between them from any two of the three parameters.

    :param measurements_count: Number of samples to take.
    :param total_duration_seconds: Total length of the run in seconds.
    :param sampling_frequency_hz: Samples per second.
    :return: A tuple of (measurements_count, interval_seconds).
    :raises ValueError: If fewer than two parameters are given, a value is not positive, or the three values disagree.
    """
    logger.debug('Resolving sampling from count=%s, duration=%s, frequency=%s',
                 measurements_count, total_duration_seconds, sampling_frequency_hz)

    given = [value for value in (measurements_count, total_duration_seconds, sampling_frequency_hz)
             if value is not None]

    # Two parameters are needed to calculate the third.
    if len(given) < 2:
        raise ValueError('Sampling needs at least two of: measurements_count, total_duration_seconds, '
                         'sampling_frequency_hz.')

    # Zero or negative values make no sense for any of the parameters.
    if any(value <= 0 for value in given):
        raise ValueError(f'Sampling parameters must be positive, got {given}.')

    if sampling_frequency_hz is not None:
        interval = 1.0 / sampling_frequency_hz
        if measurements_count is None:
            # Duration and frequency are given, so calculate the count.
            count = int(total_duration_seconds * sampling_frequency_hz)
        else:
            count = int(measurements_count)
            # If all three are given, make sure they agree with each other.
            if total_duration_seconds is not None and not math.isclose(
                    count, total_duration_seconds * sampling_frequency_hz):
                raise ValueError(f'Inconsistent sampling: {count} samples at {sampling_frequency_hz} Hz '
                                 f'do not take {total_duration_seconds} seconds.')
    else:
        # Count and duration are given, so spread the samples evenly over the duration.
        count = int(measurements_count)
        interval = total_duration_seconds / count

    if count < 1:
        raise ValueError('Sampling settings result in less than one measurement.')

    logger.debug('Resolved sampling plan: %d samples, interval %.4f s', count, interval)
    return count, interval


class Sampler:
    """
    Collects measurements from an ammeter at a fixed rate.
    """

    def __init__(self, measurements_count: int, interval_seconds: float):
        """
        Store the sampling plan.

        :param measurements_count: Number of samples to take.
        :param interval_seconds: Time between the start of two consecutive samples.
        """
        self.measurements_count = measurements_count
        self.interval_seconds = interval_seconds

    @classmethod
    def from_config(cls, sampling_config: dict) -> 'Sampler':
        """
        Build a sampler from the testing.sampling section of config.yaml.

        :param sampling_config: Dictionary with the three sampling parameters.
        :return: A configured Sampler.
        """
        # The config keys match the parameter names of resolve_sampling.
        count, interval = resolve_sampling(**sampling_config)
        return cls(count, interval)

    def run(self, client: AmmeterClient) -> list[Sample]:
        """
        Take all the samples from one ammeter.

        :param client: Client of the ammeter to sample.
        :return: List of samples, including failed ones.
        """
        logger.debug('Starting sampling on port %s: %d samples every %.4f s',
                     client.port, self.measurements_count, self.interval_seconds)
        samples = []
        start = time.perf_counter()

        for index in range(self.measurements_count):
            # Schedule each sample relative to the start time so delays do not add up.
            scheduled_offset = index * self.interval_seconds
            delay = start + scheduled_offset - time.perf_counter()
            if delay > 0:
                time.sleep(delay)

            timestamp = time.perf_counter() - start
            # Shows how precise the timing is: scheduled time versus actual start time.
            logger.debug('Sample %d: scheduled at %.3f s, waited %.3f s, started at %.3f s',
                         index, scheduled_offset, max(delay, 0.0), timestamp)

            try:
                current = client.request_current()
                samples.append(Sample(index, timestamp, current))
                logger.debug('Sample %d: %s A', index, current)
            except AmmeterError as error:
                # Record the failure and keep sampling instead of stopping the whole run.
                samples.append(Sample(index, timestamp, None, str(error)))
                logger.warning('Sample %d failed: %s', index, error)

        failed_count = sum(1 for sample in samples if sample.current is None)
        logger.debug('Sampling on port %s finished: %d samples, %d failed', client.port, len(samples), failed_count)
        return samples
