"""
Builds a self-contained HTML report from test results and opens it in the browser.

The report needs no internet and no extra library: charts are drawn as SVG by a small script
that is copied into the HTML file together with the data.
"""

import json
import logging
import platform
import webbrowser
from datetime import datetime
from pathlib import Path
from typing import Optional

from src.reporting.ammeter_info import get_ammeter_info
from src.testing.test_framework import AmmeterTestResult

logger = logging.getLogger(__name__)

ASSETS_DIR = Path(__file__).parent / 'assets'


def _summarize_history(runs: list[AmmeterTestResult]) -> list[dict]:
    """
    Keep only the numbers the history charts need from earlier runs.

    :param runs: Earlier results of one ammeter, oldest first.
    :return: One small dictionary per run.
    """
    return [
        {
            'run_id': run.run_id,
            'started_at': run.started_at,
            'mean': run.statistics.mean,
            'median': run.statistics.median,
            'cv_percent': run.statistics.cv_percent,
            'failed_count': run.statistics.failed_count,
        }
        for run in runs
        # A run where every sample failed has no numbers to draw.
        if run.statistics.mean is not None
    ]


def build_report_data(results: list[AmmeterTestResult],
                      history: Optional[dict[str, list[AmmeterTestResult]]] = None,
                      tests: Optional[dict] = None,
                      measurement_error: Optional[str] = None) -> dict:
    """
    Turn test results into the data structure the report page reads.

    :param results: Ammeter results of this session, one per ammeter.
    :param history: Earlier results per ammeter name, oldest first.
    :param tests: pytest session results, shown as extra tiles in the same page.
    :param measurement_error: Why there are no ammeter results, shown instead of the charts.
    :return: Data ready to be written as JSON into the page.
    :raises ValueError: If there is nothing to report at all.
    """
    if not results and tests is None:
        raise ValueError('A report needs at least one test result.')

    history = history or {}
    first = results[0] if results else None
    ammeters = []
    for position, result in enumerate(results):
        info = get_ammeter_info(result.ammeter_type, position)
        ammeters.append({
            'name': result.ammeter_type,
            **info,
            'port': result.metadata.get('port'),
            # Fault probabilities when the run simulated errors on purpose, otherwise None.
            'faults': result.metadata.get('error_simulation'),
            'command': result.metadata.get('command'),
            'run_id': result.run_id,
            'started_at': result.started_at,
            'duration_seconds': result.duration_seconds,
            # Short keys keep the file small, a run can have thousands of samples.
            'samples': [{'i': s.index, 't': s.timestamp, 'v': s.current, 'err': s.error} for s in result.samples],
            'stats': {
                'count': result.statistics.count,
                'failed_count': result.statistics.failed_count,
                'mean': result.statistics.mean,
                'median': result.statistics.median,
                'std': result.statistics.std,
                'min_value': result.statistics.min_value,
                'max_value': result.statistics.max_value,
                'cv_percent': result.statistics.cv_percent,
            },
        })

    metadata = first.metadata if first else {}
    data = {
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'sampling': {
            'measurements_count': first.measurements_count,
            'interval_seconds': first.interval_seconds,
            'frequency_hz': round(1 / first.interval_seconds, 3) if first.interval_seconds else None,
        } if first else None,
        'environment': {
            'python_version': metadata.get('python_version', platform.python_version()),
            'platform': metadata.get('platform', platform.platform()),
            'host': metadata.get('host', 'localhost'),
        },
        'ammeters': ammeters,
        'history': {name: _summarize_history(runs) for name, runs in history.items()},
        'measurement_error': measurement_error,
    }
    if tests is not None:
        data['tests'] = tests
    return data


def render_html(data: dict, template_name: str = 'report_template.html') -> str:
    """
    Put the data, the chart script and the styles into a page template.

    :param data: Data for the page, for example from build_report_data.
    :param template_name: File name of the template in the assets folder.
    :return: The complete HTML page.
    """
    template = (ASSETS_DIR / template_name).read_text(encoding='utf-8')
    charts = (ASSETS_DIR / 'charts.js').read_text(encoding='utf-8')
    base_css = (ASSETS_DIR / 'base.css').read_text(encoding='utf-8')

    # A '</' inside the JSON, for example in an error message, would end the script tag early.
    data_json = json.dumps(data).replace('</', '<\\/')

    return (template
            .replace('/*BASE_CSS*/', base_css)
            .replace('/*CHARTS_JS*/', charts)
            .replace('/*DATA*/', data_json))


def generate_report(results: list[AmmeterTestResult], output_dir: str | Path,
                    history: Optional[dict[str, list[AmmeterTestResult]]] = None,
                    tests: Optional[dict] = None, measurement_error: Optional[str] = None,
                    file_prefix: str = 'report') -> Path:
    """
    Write the HTML report of a session to a file.

    :param results: Ammeter results of this session, one per ammeter.
    :param output_dir: Folder for the report, created if it does not exist.
    :param history: Earlier results per ammeter name, oldest first.
    :param tests: pytest session results, shown as extra tiles in the same page.
    :param measurement_error: Why there are no ammeter results.
    :param file_prefix: Start of the file name, 'report' for main.py and 'tests' for pytest.
    :return: Path of the written report.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    data = build_report_data(results, history, tests, measurement_error)
    # The timestamp of the first run names the report, so it is easy to match with the saved runs.
    stamp = results[0].run_id[:15] if results else datetime.now().strftime('%Y%m%d_%H%M%S')
    file_path = output_dir / f'{file_prefix}_{stamp}.html'
    file_path.write_text(render_html(data), encoding='utf-8')

    logger.info('Report written to %s', file_path)
    return file_path


def open_report(file_path: str | Path) -> None:
    """
    Open a report in the default web browser.

    :param file_path: Path of the HTML report.
    """
    uri = Path(file_path).resolve().as_uri()
    logger.debug('Opening %s', uri)
    webbrowser.open(uri)
