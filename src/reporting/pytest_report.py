"""
pytest plugin that writes one HTML report of the test session.

    python -m pytest --report          write the report when the tests finish
    python -m pytest --show-report     write the report and open it in the browser
    python -m pytest --report --simulate-errors   the report measurement uses the error simulation of config.yaml

The report is the same page main.py creates, with every ammeter chart, plus tiles with the test results.
For the ammeter charts the plugin runs a short real measurement at the end of the session,
on free ports so it never clashes with a running main.py. It is switched on by the conftest.py in the project root.
"""

import logging
import platform
import socket
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import pytest
import yaml

from src.reporting.html_report import generate_report, open_report

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = PROJECT_ROOT / 'config' / 'config.yaml'
DEFAULT_REPORT_DIR = PROJECT_ROOT / 'results' / 'reports'
# Used when config.yaml has no testing.sampling or report.pytest_frequency_hz.
DEFAULT_SAMPLES = 30
DEFAULT_FREQUENCY_HZ = 50
DEFAULT_HISTORY_RUNS = 8
# Markers that come with pytest itself, left out of the marker chart.
BUILTIN_MARKERS = {'parametrize', 'skip', 'skipif', 'xfail', 'usefixtures', 'filterwarnings'}
# Long tracebacks are cut so the report stays readable and small.
MAX_MESSAGE_LENGTH = 6000


def pytest_addoption(parser) -> None:
    """
    Add the report options to the pytest command line.

    :param parser: The pytest option parser.
    """
    group = parser.getgroup('ammeter report', 'HTML report of the test session')
    group.addoption('--report', action='store_true', help='Write an HTML report with the ammeter charts and the test results.')
    group.addoption('--show-report', action='store_true', help='Write the HTML report and open it in the browser.')
    group.addoption('--report-dir', default=None, help='Folder for the report, default results/reports.')
    group.addoption('--report-samples', type=int, default=None,
                    help='Samples per ammeter for the report measurement, default from config.yaml.')
    group.addoption('--simulate-errors', action='store_true',
                    help='The report measurement uses the error simulation of config.yaml. The tests themselves are not affected.')


def pytest_configure(config) -> None:
    """
    Start collecting results only when a report was asked for.

    :param config: The pytest configuration.
    """
    if config.getoption('report') or config.getoption('show_report'):
        config.pluginmanager.register(TestReportCollector(config), 'ammeter-test-report')


def _load_project_config() -> dict:
    """
    Read config.yaml, or return an empty config when it is missing or broken.

    :return: The config dictionary.
    """
    try:
        from src.utils.config import load_config
        return load_config(str(CONFIG_PATH)) or {}
    except (OSError, ValueError, yaml.YAMLError):
        # A missing or broken config must not break the test run.
        return {}


def _free_port() -> int:
    """
    Find a port on localhost where nothing is listening.

    :return: The port number.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('localhost', 0))
        return s.getsockname()[1]


def run_report_measurement(project_config: dict, samples: Optional[int] = None,
                           simulate_errors: bool = False) -> tuple[list, dict]:
    """
    Measure every ammeter in the config once, on free ports, for the charts of the report.

    The number of samples is the same as for main.py (testing.sampling in config.yaml), only the rate is
    faster (report.pytest_frequency_hz), so the test run does not take minutes.

    :param project_config: The content of config.yaml.
    :param samples: Samples per ammeter, overrides the config.
    :param simulate_errors: Make the emulators fail on purpose, as set in the error_simulation section.
    :return: The results and the earlier saved runs of every ammeter.
    """
    from Ammeters.runner import start_emulators
    from src.testing.result_store import ResultStore
    from src.testing.sampler import resolve_sampling
    from src.testing.test_framework import AmmeterTestFramework

    report_config = project_config.get('report') or {}
    if samples is None:
        main_sampling = (project_config.get('testing') or {}).get('sampling')
        # Any two of the three main settings give the count, exactly as main.py works it out.
        samples = resolve_sampling(**main_sampling)[0] if main_sampling else DEFAULT_SAMPLES
    sampling = {'measurements_count': samples, 'total_duration_seconds': None,
                'sampling_frequency_hz': report_config.get('pytest_frequency_hz') or DEFAULT_FREQUENCY_HZ}

    # Same ammeters and commands as config.yaml, but on free ports.
    ammeters = {name: {'port': _free_port(), 'command': settings['command']}
                for name, settings in project_config['ammeters'].items()}
    # The simulation is used only when asked for, so a normal report always shows healthy ammeters.
    simulation = dict(project_config.get('error_simulation') or {}, enabled=True) if simulate_errors else None
    start_emulators(ammeters, startup_delay=0.3, simulation_config=simulation)

    testing = {'sampling': sampling}
    timeout = (project_config.get('testing') or {}).get('timeout_seconds')
    if timeout:
        # The same timeout as main.py, so a simulated 'delay' fails the same way.
        testing['timeout_seconds'] = timeout
    framework_config = {'testing': testing, 'ammeters': ammeters}
    if simulation:
        framework_config['error_simulation'] = simulation

    with tempfile.TemporaryDirectory() as folder:
        config_file = Path(folder) / 'config.yaml'
        config_file.write_text(yaml.safe_dump(framework_config, sort_keys=False), encoding='utf-8')
        framework = AmmeterTestFramework(config_file)
        results = [framework.run_test(name) for name in ammeters]

    # History comes from the runs main.py saved, the report measurement itself is not saved.
    results_dir = (project_config.get('result_management') or {}).get('results_dir', 'results/runs')
    history = ResultStore(results_dir).load_history(results, report_config.get('history_runs', DEFAULT_HISTORY_RUNS))
    return results, history


class TestReportCollector:
    """
    Collects the outcome of every test and writes the report at the end of the session.
    """

    # Tells pytest this helper is not a test class, even though its name starts with Test.
    __test__ = False

    def __init__(self, config):
        """
        Prepare an empty collection.

        :param config: The pytest configuration.
        """
        self.config = config
        self.tests: dict[str, dict] = {}
        self.started = time.perf_counter()
        self.started_at = datetime.now()
        self.report_path: Optional[Path] = None

    def pytest_collection_finish(self, session) -> None:
        """
        Remember the file, class, docstring and markers of every collected test.

        :param session: The pytest session.
        """
        for item in session.items:
            function = getattr(item, 'function', None)
            doc = (function.__doc__ or '').strip().splitlines()[0] if function and function.__doc__ else ''
            cls = getattr(item, 'cls', None)
            self.tests[item.nodeid] = {
                'nodeid': item.nodeid,
                'file': item.nodeid.split('::')[0],
                'cls': cls.__name__ if cls else '',
                'name': item.name,
                'doc': doc,
                # Built in markers like parametrize or skip are not what anybody selects tests by.
                'markers': sorted({mark.name for mark in item.iter_markers() if mark.name not in BUILTIN_MARKERS}),
                'outcome': 'not run',
                'duration': 0.0,
                'message': '',
            }

    def pytest_runtest_logreport(self, report) -> None:
        """
        Record the outcome of one phase (setup, call or teardown) of a test.

        :param report: The pytest report of the phase.
        """
        entry = self.tests.setdefault(report.nodeid, {
            'nodeid': report.nodeid, 'file': report.nodeid.split('::')[0], 'cls': '', 'name': report.nodeid.split('::')[-1],
            'doc': '', 'markers': [], 'outcome': 'not run', 'duration': 0.0, 'message': '',
        })
        entry['duration'] += report.duration

        if report.when == 'call':
            if hasattr(report, 'wasxfail'):
                entry['outcome'] = 'xfailed' if report.skipped else 'xpassed'
            else:
                entry['outcome'] = report.outcome
        elif report.failed:
            # A failure in setup or teardown is an error of the test, not a failed assert.
            entry['outcome'] = 'error'
        elif report.skipped and report.when == 'setup':
            entry['outcome'] = 'skipped'

        if report.failed or (report.skipped and report.when == 'setup'):
            text = report.longreprtext or ''
            entry['message'] = text[-MAX_MESSAGE_LENGTH:]

    def build_tests_data(self, exit_status: int) -> dict:
        """
        Turn the collected outcomes into the test part of the report data.

        :param exit_status: Exit code of the pytest session.
        :return: The test results.
        """
        tests = list(self.tests.values())
        totals = {outcome: sum(1 for t in tests if t['outcome'] == outcome)
                  for outcome in ['passed', 'failed', 'error', 'skipped', 'xfailed', 'xpassed', 'not run']}
        totals['total'] = len(tests)
        return {
            'started_at': self.started_at.isoformat(timespec='seconds'),
            'duration_seconds': time.perf_counter() - self.started,
            'exit_status': int(exit_status),
            'command': 'pytest ' + ' '.join(self.config.invocation_params.args),
            'python_version': platform.python_version(),
            'pytest_version': pytest.__version__,
            'totals': totals,
            'tests': tests,
        }

    def _report_dir(self, project_config: dict) -> Path:
        """
        Folder for the report: the --report-dir option, the report section of config.yaml, or the default.

        :param project_config: The content of config.yaml.
        :return: The folder.
        """
        if self.config.getoption('report_dir'):
            return Path(self.config.getoption('report_dir'))
        output_dir = (project_config.get('report') or {}).get('output_dir')
        return PROJECT_ROOT / output_dir if output_dir else DEFAULT_REPORT_DIR

    def pytest_sessionfinish(self, session, exitstatus) -> None:
        """
        Measure the ammeters, write the report, and open it when --show-report was given.

        :param session: The pytest session.
        :param exitstatus: Exit code of the session.
        """
        tests = self.build_tests_data(exitstatus)
        project_config = _load_project_config()

        results, history, error = [], {}, None
        try:
            results, history = run_report_measurement(project_config, self.config.getoption('report_samples'),
                                                      self.config.getoption('simulate_errors'))
        except Exception as exc:  # noqa: BLE001 - the test results must be reported even if the measurement fails.
            error = f'{type(exc).__name__}: {exc}'
            logger.warning('Report measurement failed: %s', error)

        self.report_path = generate_report(results, self._report_dir(project_config), history, tests=tests,
                                           measurement_error=error, file_prefix='tests')
        if self.config.getoption('show_report'):
            open_report(self.report_path)

    def pytest_terminal_summary(self, terminalreporter) -> None:
        """
        Print where the report was written, at the end of the pytest output.

        :param terminalreporter: The pytest terminal reporter.
        """
        if self.report_path:
            terminalreporter.write_sep('-', f'HTML report: {self.report_path}')
