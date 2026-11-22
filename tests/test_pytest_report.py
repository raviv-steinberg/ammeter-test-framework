"""
Tests for the pytest report plugin, by running a small pytest session inside the test.
"""

import json
import re

import pytest

from src.reporting.pytest_report import run_report_measurement
from tests.expected import COMMANDS

# A tiny test file with every kind of result the report shows.
SAMPLE_TESTS = '''
import pytest


@pytest.mark.unit
class TestSample:
    """Sample tests."""

    def test_passes(self):
        """A test that passes."""
        assert True

    def test_fails(self):
        """A test that fails."""
        assert 1 == 2

    @pytest.mark.skip(reason='not ready')
    def test_skipped(self):
        """A test that is skipped."""
'''


def read_data(path) -> dict:
    """
    Read back the JSON data written into a report page.

    :param path: Path of the report.
    :return: The data.
    """
    html = path.read_text(encoding='utf-8')
    match = re.search(r'const DATA = (.*?);\n', html)
    return json.loads(match.group(1).replace('<\\/', '</'))


def run_inner_pytest(pytester, *options):
    """
    Run pytest on the sample tests with the report plugin switched on.

    :param pytester: The pytester fixture.
    :param options: Extra command line options.
    :return: The run result.
    """
    pytester.makeini('[pytest]\nmarkers =\n    unit: sample marker\n')
    pytester.makepyfile(test_sample=SAMPLE_TESTS)
    # Three samples per ammeter keep the report measurement short.
    return pytester.runpytest('-p', 'src.reporting.pytest_report', '--report-samples', '3', *options)


@pytest.mark.report
class TestPytestReport:
    """
    The --report and --show-report options of pytest.
    """

    def test_no_report_without_the_option(self, pytester, tmp_path):
        """
        Without --report nothing is written, normal test runs stay as they were.
        """
        report_dir = tmp_path / 'reports'

        result = run_inner_pytest(pytester, '--report-dir', str(report_dir))

        result.assert_outcomes(passed=1, failed=1, skipped=1)
        assert not report_dir.exists()

    def test_report_holds_every_outcome(self, pytester, tmp_path):
        """
        --report writes one file with the outcome, docstring and markers of every test.
        """
        report_dir = tmp_path / 'reports'

        result = run_inner_pytest(pytester, '--report', '--report-dir', str(report_dir))

        reports = list(report_dir.glob('tests_*.html'))
        assert len(reports) == 1
        tests = read_data(reports[0])['tests']
        assert tests['totals']['passed'] == 1
        assert tests['totals']['failed'] == 1
        assert tests['totals']['skipped'] == 1
        passed = next(t for t in tests['tests'] if t['name'] == 'test_passes')
        assert passed['doc'] == 'A test that passes.'
        assert passed['markers'] == ['unit']
        result.stdout.fnmatch_lines(['*HTML report:*tests_*.html*'])

    def test_failure_message_is_kept(self, pytester, tmp_path):
        """
        The report shows why a test failed.
        """
        report_dir = tmp_path / 'reports'

        run_inner_pytest(pytester, '--report', '--report-dir', str(report_dir))

        tests = read_data(next(report_dir.glob('tests_*.html')))['tests']
        failed = next(t for t in tests['tests'] if t['name'] == 'test_fails')
        assert 'assert 1 == 2' in failed['message']

    def test_report_has_the_ammeter_charts(self, pytester, tmp_path):
        """
        The same page as main.py: a real measurement of every ammeter is part of the pytest report.
        """
        report_dir = tmp_path / 'reports'

        run_inner_pytest(pytester, '--report', '--report-dir', str(report_dir))

        data = read_data(next(report_dir.glob('tests_*.html')))
        assert [a['name'] for a in data['ammeters']] == ['greenlee', 'entes', 'circutor']
        assert all(a['stats']['count'] == 3 and a['stats']['failed_count'] == 0 for a in data['ammeters'])
        assert data['measurement_error'] is None

    def test_show_report_opens_the_browser(self, pytester, tmp_path, monkeypatch):
        """
        --show-report also opens the report, the browser call is replaced so nothing really opens.
        """
        opened = []
        monkeypatch.setattr('webbrowser.open', opened.append)
        report_dir = tmp_path / 'reports'

        run_inner_pytest(pytester, '--show-report', '--report-dir', str(report_dir))

        assert len(opened) == 1
        assert opened[0].endswith('.html')


@pytest.mark.report
@pytest.mark.network
class TestReportMeasurement:
    """
    The real measurement the pytest report makes for its ammeter charts.
    """

    def test_sample_count_comes_from_the_main_sampling_settings(self):
        """
        Changing testing.sampling in config.yaml changes the pytest report too, only the rate is faster.
        """
        project_config = {
            'testing': {'sampling': {'measurements_count': 7, 'total_duration_seconds': None, 'sampling_frequency_hz': 2}},
            'ammeters': {name: {'port': 0, 'command': command} for name, command in COMMANDS.items()},
            'report': {'pytest_frequency_hz': 100},
        }

        results, _ = run_report_measurement(project_config)

        assert [len(result.samples) for result in results] == [7, 7, 7]
        assert all(result.interval_seconds == pytest.approx(0.01) for result in results)

    def test_report_samples_option_overrides_the_config(self):
        """
        --report-samples wins over the config.
        """
        project_config = {
            'testing': {'sampling': {'measurements_count': 50, 'total_duration_seconds': None, 'sampling_frequency_hz': 2}},
            'ammeters': {name: {'port': 0, 'command': command} for name, command in COMMANDS.items()},
            'report': {'pytest_frequency_hz': 100},
        }

        results, _ = run_report_measurement(project_config, samples=4)

        assert [len(result.samples) for result in results] == [4, 4, 4]

    def test_simulate_errors_reaches_the_report_measurement(self):
        """
        With simulate_errors the report measurement uses the error simulation, and the results say so.
        """
        project_config = {
            'testing': {'sampling': {'measurements_count': 5, 'total_duration_seconds': None, 'sampling_frequency_hz': 2}},
            'ammeters': {name: {'port': 0, 'command': command} for name, command in COMMANDS.items()},
            'report': {'pytest_frequency_hz': 100},
            # enabled is false on purpose: the option switches it on.
            'error_simulation': {'enabled': False, 'seed': 1, 'ammeters': {'entes': {'no_reply': 1.0}}},
        }

        results, _ = run_report_measurement(project_config, simulate_errors=True)

        entes = next(result for result in results if result.ammeter_type == 'entes')
        assert entes.statistics.failed_count == 5
        assert entes.metadata['error_simulation']['no_reply'] == 1.0
        # Ammeters without a profile stay healthy.
        assert all(r.statistics.failed_count == 0 for r in results if r.ammeter_type != 'entes')

    def test_without_the_option_the_report_measurement_is_healthy(self):
        """
        A normal pytest report never uses the simulation, even when config.yaml has it switched on.
        """
        project_config = {
            'testing': {'sampling': {'measurements_count': 5, 'total_duration_seconds': None, 'sampling_frequency_hz': 2}},
            'ammeters': {name: {'port': 0, 'command': command} for name, command in COMMANDS.items()},
            'report': {'pytest_frequency_hz': 100},
            'error_simulation': {'enabled': True, 'ammeters': {'entes': {'no_reply': 1.0}}},
        }

        results, _ = run_report_measurement(project_config)

        assert all(r.statistics.failed_count == 0 and r.metadata['error_simulation'] is None for r in results)
