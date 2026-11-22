"""
Statistical analysis of sampling results.
"""

import logging
import statistics
from dataclasses import dataclass
from typing import Optional

from src.testing.sampler import Sample

logger = logging.getLogger(__name__)


@dataclass
class MeasurementStatistics:
    """
    Summary statistics of one sampling run.
    """

    # Number of successful measurements used in the calculation.
    count: int
    # Number of measurements that failed and were left out.
    failed_count: int
    # Average current in amperes.
    mean: Optional[float]
    # Middle value of the sorted currents in amperes.
    median: Optional[float]
    # Sample standard deviation in amperes.
    std: Optional[float]
    # Smallest current in amperes.
    min_value: Optional[float]
    # Largest current in amperes.
    max_value: Optional[float]
    # Coefficient of variation, std relative to mean, in percent.
    cv_percent: Optional[float]


def analyze_samples(samples: list[Sample]) -> MeasurementStatistics:
    """
    Calculate summary statistics for a list of samples.

    :param samples: Samples returned by Sampler.run.
    :return: The statistics of the successful samples.
    """
    # Failed samples have no current, so they cannot be part of the calculation.
    values = [sample.current for sample in samples if sample.current is not None]
    failed_count = len(samples) - len(values)
    logger.debug('Analyzing %d samples: %d successful, %d failed', len(samples), len(values), failed_count)
    logger.debug('Values used: %s', values)

    # If every measurement failed there is nothing to calculate.
    if not values:
        logger.warning('No successful samples to analyze')
        return MeasurementStatistics(count=0, failed_count=failed_count, mean=None, median=None,
                                     std=None, min_value=None, max_value=None, cv_percent=None)

    mean = statistics.mean(values)
    # Standard deviation needs at least two values, a single value has no spread.
    std = statistics.stdev(values) if len(values) > 1 else 0.0
    # Avoid division by zero when the mean is zero.
    cv_percent = std / mean * 100 if mean != 0 else None

    result = MeasurementStatistics(
        count=len(values),
        failed_count=failed_count,
        mean=mean,
        median=statistics.median(values),
        std=std,
        min_value=min(values),
        max_value=max(values),
        cv_percent=cv_percent,
    )
    logger.debug('Statistics: %s', result)
    return result
