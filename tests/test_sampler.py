"""
Tests for the sampling plan and the sampling loop.
"""

import time
import pytest
from src.exceptions.ammeter_exceptions import AmmeterResponseError
from src.testing.sampler import Sampler, resolve_sampling

# Interval used in the timing tests, long enough to measure but short enough to keep the tests fast.
INTERVAL = 0.1
# Allowed timing error. On Windows time.sleep can wake up about 15 ms late.
TOLERANCE = 0.03


class FakeClient:
    """
    Stand-in for AmmeterClient that returns prepared replies without any network.
    """

    def __init__(self, replies: list, delay: float = 0.0):
        """
        Prepare the replies.
        :param replies: Each item is a current to return, or an exception to raise.
        :param delay: Seconds every request takes, to simulate a slow ammeter.
        """
        self.replies = list(replies)
        self.delay = delay
        # Sampler logs the port, so the fake needs one too.
        self.port = 0
        # Counts how many times the sampler asked for a measurement.
        self.calls = 0

    def request_current(self) -> float:
        """
        Return the next prepared reply, or raise it if it is an exception.
        :return: The next current in amperes.
        """
        self.calls += 1
        if self.delay:
            time.sleep(self.delay)
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


@pytest.mark.sampler
@pytest.mark.unit
class TestResolveSampling:
    """
    Turning the three config parameters into a sampling plan.
    """

    @pytest.mark.parametrize('count, duration, frequency, expected_count, expected_interval', [
        (10, None, 2, 10, 0.5),    # Count and frequency.
        (None, 5, 2, 10, 0.5),     # Duration and frequency.
        (10, 5, None, 10, 0.5),    # Count and duration.
        (10, 5, 2, 10, 0.5),       # All three and consistent.
    ])
    def test_valid_settings(self, count, duration, frequency, expected_count, expected_interval):
        """
        Any two of the three parameters give the right plan.
        """
        result_count, result_interval = resolve_sampling(count, duration, frequency)

        assert result_count == expected_count
        assert result_interval == pytest.approx(expected_interval)

    @pytest.mark.parametrize('count, duration, frequency, message', [
        (10, None, None, 'at least two'),       # Only one parameter.
        (None, None, None, 'at least two'),     # No parameters at all.
        (0, None, 2, 'must be positive'),       # Zero count.
        (10, None, -1, 'must be positive'),     # Negative frequency.
        (10, 3, 2, 'Inconsistent'),             # 10 samples at 2 Hz take 5 s, not 3 s.
        (None, 0.4, 2, 'less than one'),        # 0.4 s at 2 Hz is less than one sample.
    ])
    def test_invalid_settings(self, count, duration, frequency, message):
        """
        Invalid sampling settings raise a clear ValueError.
        """
        with pytest.raises(ValueError, match=message):
            resolve_sampling(count, duration, frequency)

    def test_from_config_reads_the_config_keys(self):
        """
        The sampler is built from a dictionary shaped like the config section.
        """
        sampling_config = {'measurements_count': 4, 'total_duration_seconds': None, 'sampling_frequency_hz': 10}

        sampler = Sampler.from_config(sampling_config)

        assert sampler.measurements_count == 4
        assert sampler.interval_seconds == pytest.approx(0.1)


@pytest.mark.sampler
@pytest.mark.unit
class TestSamplerRun:
    """
    The sampling loop: collecting samples and handling failures.
    """

    def test_returns_all_samples_in_order(self):
        """
        Every reply becomes a sample, in the order it was received.
        """
        client = FakeClient([1.0, 2.0, 3.0])

        samples = Sampler(3, 0.01).run(client)

        assert [sample.index for sample in samples] == [0, 1, 2]
        assert [sample.current for sample in samples] == [1.0, 2.0, 3.0]
        assert all(sample.error is None for sample in samples)

    def test_records_failure_and_continues(self):
        """
        A failed measurement is recorded and the sampling goes on.
        """
        client = FakeClient([1.0, AmmeterResponseError('no data'), 3.0])

        samples = Sampler(3, 0.01).run(client)

        # The sampler did not stop after the failure.
        assert client.calls == 3
        assert samples[1].current is None
        assert samples[1].error == 'no data'
        assert samples[2].current == 3.0

    def test_does_not_hide_unexpected_errors(self):
        """
        Only ammeter errors are caught, a real bug in the code must still stop the run.
        """
        client = FakeClient([RuntimeError('bug')])

        with pytest.raises(RuntimeError):
            Sampler(1, 0.01).run(client)


@pytest.mark.sampler
@pytest.mark.timing
class TestSamplerTiming:
    """
    Timing precision of the sampling loop, measured with real time.
    """

    def test_follows_the_schedule(self):
        """
        Each sample starts at its planned time.
        """
        samples = Sampler(5, INTERVAL).run(FakeClient([1.0] * 5))

        for sample in samples:
            assert sample.timestamp == pytest.approx(sample.index * INTERVAL, abs=TOLERANCE)

    def test_slow_measurements_do_not_cause_drift(self):
        """
        Time spent measuring is absorbed by the wait, so the delay does not add up.
        """
        # Each measurement takes 40% of the interval.
        # A simple sleep loop would end 4 * 0.04 = 0.16 s late, far outside the tolerance.
        samples = Sampler(5, INTERVAL).run(FakeClient([1.0] * 5, delay=0.04))

        assert samples[-1].timestamp == pytest.approx(4 * INTERVAL, abs=TOLERANCE)
