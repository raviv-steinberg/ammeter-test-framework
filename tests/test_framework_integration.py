"""
End to end tests: the framework against the real emulators running on localhost.
"""

import copy
import re

import pytest

from src.testing.test_framework import AmmeterTestFramework
from tests.expected import CURRENT_RANGES

AMMETERS = ['greenlee', 'entes', 'circutor']


@pytest.fixture
def framework(emulators_config, write_config) -> AmmeterTestFramework:
    """
    A framework whose config points to the emulators started for this session.
    """
    return AmmeterTestFramework(write_config(emulators_config))


@pytest.mark.framework
@pytest.mark.integration
@pytest.mark.network
class TestRunTest:
    """
    Running a full test on one ammeter.
    """

    @pytest.mark.parametrize('ammeter_type', AMMETERS)
    def test_every_sample_succeeds(self, framework, ammeter_type):
        """
        All planned samples are taken and none of them fails.
        """
        result = framework.run_test(ammeter_type)

        assert result.ammeter_type == ammeter_type
        assert len(result.samples) == framework.sampler.measurements_count
        assert result.statistics.count == framework.sampler.measurements_count
        assert result.statistics.failed_count == 0

    @pytest.mark.parametrize('ammeter_type', AMMETERS)
    def test_values_stay_in_range(self, framework, ammeter_type):
        """
        Values that went through the network are still inside the range of the ammeter.
        """
        low, high = CURRENT_RANGES[ammeter_type]

        stats = framework.run_test(ammeter_type).statistics

        assert low <= stats.min_value <= stats.max_value <= high

    def test_result_contains_id_and_metadata(self, framework, emulators_config):
        """
        The result carries a run id and the details needed to understand the run later.
        """
        result = framework.run_test('greenlee')

        assert re.fullmatch(r'\d{8}_\d{6}_[0-9a-f]{8}', result.run_id)
        assert result.metadata['port'] == emulators_config['ammeters']['greenlee']['port']
        assert result.metadata['command'] == emulators_config['ammeters']['greenlee']['command']
        assert 'python_version' in result.metadata

    def test_two_runs_get_different_ids(self, framework):
        """
        Each run is identified on its own, even for the same ammeter.
        """
        first = framework.run_test('entes')
        second = framework.run_test('entes')

        assert first.run_id != second.run_id

    def test_unknown_ammeter_raises(self, framework):
        """
        A name that is not in the config gives a clear error that lists the known names.
        """
        with pytest.raises(ValueError, match='Unknown ammeter .fluke.'):
            framework.run_test('fluke')

    def test_run_all_tests_every_ammeter(self, framework):
        """
        run_all returns one result for each ammeter in the config.
        """
        results = framework.run_all()

        assert list(results) == AMMETERS
        assert all(result.statistics.failed_count == 0 for result in results.values())


@pytest.mark.framework
@pytest.mark.integration
@pytest.mark.network
class TestRunTestFailures:
    """
    Problems in the setup are reported in the result instead of crashing the run.
    """

    def test_wrong_command_fails_every_sample(self, emulators_config, write_config):
        """
        A wrong command in the config makes every sample fail, and the result says so.
        """
        config = copy.deepcopy(emulators_config)
        config['ammeters']['entes']['command'] = 'MEASURE_ENTES'
        framework = AmmeterTestFramework(write_config(config))

        result = framework.run_test('entes')

        assert result.statistics.count == 0
        assert result.statistics.failed_count == framework.sampler.measurements_count
        assert all('No data received' in sample.error for sample in result.samples)

    def test_no_emulator_on_port_fails_every_sample(self, emulators_config, write_config, closed_port):
        """
        A port with no emulator makes every sample fail with a connection error.
        """
        config = copy.deepcopy(emulators_config)
        config['ammeters']['greenlee']['port'] = closed_port
        # Windows takes about 2 seconds to refuse each connection on localhost, one sample keeps the test fast.
        config['testing']['sampling']['measurements_count'] = 1
        framework = AmmeterTestFramework(write_config(config))

        result = framework.run_test('greenlee')

        assert result.statistics.failed_count == framework.sampler.measurements_count
        assert all('Cannot communicate' in sample.error for sample in result.samples)


@pytest.mark.framework
@pytest.mark.integration
@pytest.mark.timing
class TestRunTestTiming:
    """
    The duration of a full run matches the sampling plan.
    """

    def test_duration_matches_the_plan(self, framework):
        """
        N samples have N - 1 gaps between them, so the run takes (N - 1) * interval.
        """
        sampler = framework.sampler
        expected = (sampler.measurements_count - 1) * sampler.interval_seconds

        result = framework.run_test('circutor')

        assert result.duration_seconds == pytest.approx(expected, abs=0.05)
