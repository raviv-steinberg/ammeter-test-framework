"""
Tests for the statistical analysis of sampling results.
"""

import pytest
from src.testing.analysis import analyze_samples
from src.testing.sampler import Sample


def make_samples(values: list) -> list[Sample]:
    """
    Build samples from a list of currents, where None means a failed measurement.

    :param values: Currents in amperes, or None for a failure.
    :return: One Sample per value.
    """
    return [Sample(index, 0.0, value, None if value is not None else 'failed')
            for index, value in enumerate(values)]


@pytest.mark.analysis
@pytest.mark.unit
class TestAnalyzeSamples:
    """
    Statistics calculated from a list of samples.
    """

    def test_basic_statistics(self):
        """
        Known input gives the statistics we calculated by hand.
        """
        stats = analyze_samples(make_samples([1, 3, 5, 7, 9]))

        assert stats.count == 5
        assert stats.failed_count == 0
        assert stats.mean == 5
        assert stats.median == 5
        # sqrt(10), compared with a tolerance because it is a float.
        assert stats.std == pytest.approx(3.1623, abs=1e-4)
        assert stats.min_value == 1
        assert stats.max_value == 9
        assert stats.cv_percent == pytest.approx(63.25, abs=0.01)

    def test_failed_samples_are_excluded(self):
        """
        Failed samples are counted but not used in the calculation.
        """
        stats = analyze_samples(make_samples([1, 3, 5, 7, None]))

        assert stats.count == 4
        assert stats.failed_count == 1
        assert stats.mean == 4
        # The failed sample must not be treated as a value.
        assert stats.max_value == 7

    def test_even_count_median_is_average_of_middle_values(self):
        """
        With an even number of values the median is the mean of the two middle ones.
        """
        stats = analyze_samples(make_samples([1, 3, 5, 7]))

        assert stats.median == 4.0

    def test_single_value_has_zero_std(self):
        """
        One value has no spread, so std is zero instead of raising an error.
        """
        stats = analyze_samples(make_samples([2.5]))

        assert stats.count == 1
        assert stats.std == 0.0
        assert stats.cv_percent == 0.0

    def test_all_failed_returns_empty_statistics(self):
        """
        When every sample failed there are no numbers, only the failure count.
        """
        stats = analyze_samples(make_samples([None, None, None]))

        assert stats.count == 0
        assert stats.failed_count == 3
        assert stats.mean is None
        assert stats.std is None
        assert stats.cv_percent is None

    def test_empty_list(self):
        """
        An empty list is handled like a run with no successful samples.
        """
        stats = analyze_samples([])

        assert stats.count == 0
        assert stats.failed_count == 0
        assert stats.mean is None
