"""
Tests for the HTML report: the data it contains, the written file and opening it in the browser.

The results are built by hand, so these tests need no emulator, no network and no browser.
"""

import json
import re

import pytest

from src.reporting import html_report
from src.reporting.ammeter_info import AMMETER_INFO, get_ammeter_info
from src.reporting.html_report import build_report_data, generate_report, open_report, render_html
from src.testing.analysis import analyze_samples
from src.testing.sampler import Sample
from src.testing.test_framework import AmmeterTestResult
from tests.expected import CURRENT_RANGES


def make_result(run_id: str, ammeter_type: str = 'greenlee', values: tuple = (1.0, 2.0, 3.0),
                error: str = 'failed') -> AmmeterTestResult:
    """
    Build a result by hand, without running a real test.

    :param run_id: Run id of the result.
    :param ammeter_type: Ammeter name.
    :param values: Currents of the samples, None means a failed sample.
    :param error: Error message of the failed samples.
    :return: The result.
    """
    samples = [Sample(index, index * 0.5, value, None if value is not None else error)
               for index, value in enumerate(values)]
    return AmmeterTestResult(
        run_id=run_id,
        ammeter_type=ammeter_type,
        started_at='2026-11-22T10:00:00',
        duration_seconds=1.0,
        measurements_count=len(values),
        interval_seconds=0.5,
        metadata={'port': 5000, 'command': 'TEST', 'python_version': '3.13.0', 'platform': 'TestOS', 'host': 'localhost'},
        samples=samples,
        statistics=analyze_samples(samples),
    )


def embedded_data(html: str) -> dict:
    """
    Read back the JSON data that was written into the page.

    :param html: The report page.
    :return: The data as a dictionary.
    """
    match = re.search(r'const DATA = (.*?);\n', html)
    return json.loads(match.group(1).replace('<\\/', '</'))


@pytest.mark.report
@pytest.mark.unit
class TestAmmeterInfo:
    """
    Display details and theoretical values of the ammeters.
    """

    @pytest.mark.parametrize('name', AMMETER_INFO)
    def test_expected_mean_is_inside_the_range(self, name):
        """
        The theoretical mean must lie between the lowest and highest possible current.
        """
        info = AMMETER_INFO[name]

        assert info['range'][0] < info['expected_mean'] < info['range'][1]

    @pytest.mark.parametrize('name', AMMETER_INFO)
    def test_range_matches_the_tests(self, name):
        """
        The report uses the same ranges as the emulator tests, both come from the README.
        """
        assert AMMETER_INFO[name]['range'] == pytest.approx(list(CURRENT_RANGES[name]))

    def test_unknown_ammeter_gets_defaults(self):
        """
        An ammeter that is not listed still gets a label and a color, and no theory.
        """
        info = get_ammeter_info('fluke', 0)

        assert info['label'] == 'Fluke'
        assert info['color'].startswith('#')
        assert info['expected_mean'] is None


@pytest.mark.report
@pytest.mark.unit
class TestBuildReportData:
    """
    The data structure the report page reads.
    """

    def test_contains_every_ammeter_with_its_details(self):
        """
        Each result becomes one ammeter entry with label, theory, samples and statistics.
        """
        results = [make_result('20261122_100000_aaaaaa', 'greenlee'), make_result('20261122_100010_bbbbbb', 'entes')]

        data = build_report_data(results)

        assert [a['name'] for a in data['ammeters']] == ['greenlee', 'entes']
        greenlee = data['ammeters'][0]
        assert greenlee['label'] == 'Greenlee'
        assert greenlee['run_id'] == '20261122_100000_aaaaaa'
        assert greenlee['expected_mean'] == AMMETER_INFO['greenlee']['expected_mean']
        assert greenlee['stats']['mean'] == 2.0
        assert len(greenlee['samples']) == 3

    def test_samples_keep_failures(self):
        """
        A failed sample stays in the data with no value and its error message.
        """
        data = build_report_data([make_result('20261122_100000_aaaaaa', values=(1.0, None), error='No data received')])

        failed = data['ammeters'][0]['samples'][1]
        assert failed['v'] is None
        assert failed['err'] == 'No data received'

    def test_sampling_plan_and_environment(self):
        """
        The sampling plan and the environment come from the results.
        """
        data = build_report_data([make_result('20261122_100000_aaaaaa')])

        assert data['sampling'] == {'measurements_count': 3, 'interval_seconds': 0.5, 'frequency_hz': 2.0}
        assert data['environment']['python_version'] == '3.13.0'

    def test_history_leaves_out_runs_without_values(self):
        """
        Earlier runs where every sample failed have no numbers, so they are not in the history.
        """
        history = {'greenlee': [make_result('20261121_100000_cccccc'), make_result('20261121_110000_dddddd', values=(None,))]}

        data = build_report_data([make_result('20261122_100000_aaaaaa')], history)

        assert [h['run_id'] for h in data['history']['greenlee']] == ['20261121_100000_cccccc']

    def test_no_results_raises(self):
        """
        A report without any ammeter result and without test results makes no sense.
        """
        with pytest.raises(ValueError, match='at least one'):
            build_report_data([])

    def test_test_results_are_added(self):
        """
        pytest results go into the same data, next to the ammeters.
        """
        tests = {'totals': {'passed': 2, 'total': 2}, 'tests': []}

        data = build_report_data([make_result('20261122_100000_aaaaaa')], tests=tests)

        assert data['tests'] == tests
        assert len(data['ammeters']) == 1

    def test_tests_without_measurement(self):
        """
        If the measurement could not run, the report still shows the test results and why.
        """
        data = build_report_data([], tests={'totals': {}, 'tests': []}, measurement_error='port busy')

        assert data['ammeters'] == []
        assert data['sampling'] is None
        assert data['measurement_error'] == 'port busy'


@pytest.mark.report
@pytest.mark.unit
class TestGenerateReport:
    """
    Writing the report file.
    """

    def test_writes_a_complete_html_file(self, tmp_path):
        """
        The file is created, named after the run, and every placeholder was filled in.
        """
        path = generate_report([make_result('20261122_100000_aaaaaa')], tmp_path / 'reports')

        assert path.name == 'report_20261122_100000.html'
        html = path.read_text(encoding='utf-8')
        assert html.startswith('<!DOCTYPE html>')
        for placeholder in ['/*DATA*/', '/*CHARTS_JS*/', '/*BASE_CSS*/']:
            assert placeholder not in html

    def test_data_in_the_page_matches_the_results(self, tmp_path):
        """
        The data written into the page can be read back and holds the run.
        """
        path = generate_report([make_result('20261122_100000_aaaaaa')], tmp_path)

        data = embedded_data(path.read_text(encoding='utf-8'))

        assert data['ammeters'][0]['run_id'] == '20261122_100000_aaaaaa'

    def test_pytest_report_file_name(self, tmp_path):
        """
        The pytest report gets its own prefix, so it is not mixed up with the reports of main.py.
        """
        path = generate_report([make_result('20261122_100000_aaaaaa')], tmp_path, tests={'totals': {}, 'tests': []},
                               file_prefix='tests')

        assert path.name == 'tests_20261122_100000.html'

    def test_report_without_any_successful_sample(self, tmp_path):
        """
        A run where everything failed still produces a report, it is the most important one to read.
        """
        path = generate_report([make_result('20261122_100000_aaaaaa', values=(None, None))], tmp_path)

        data = embedded_data(path.read_text(encoding='utf-8'))

        assert data['ammeters'][0]['stats']['count'] == 0

    def test_error_text_cannot_break_the_page(self):
        """
        An error message containing </script> must not end the script tag of the page.
        """
        result = make_result('20261122_100000_aaaaaa', values=(None,), error='bad reply </script><b>')

        html = render_html(build_report_data([result]))

        # Only the real closing tag of the single script block is left.
        assert html.count('</script>') == 1
        assert embedded_data(html)['ammeters'][0]['samples'][0]['err'] == 'bad reply </script><b>'


@pytest.mark.report
@pytest.mark.unit
class TestOpenReport:
    """
    Opening the report in the browser.
    """

    def test_opens_the_file_in_the_browser(self, tmp_path, monkeypatch):
        """
        The default browser is asked to open the report as a file URI, no real browser is started.
        """
        opened = []
        monkeypatch.setattr(html_report.webbrowser, 'open', opened.append)
        path = tmp_path / 'report.html'
        path.write_text('<html></html>', encoding='utf-8')

        open_report(path)

        assert opened == [path.resolve().as_uri()]
