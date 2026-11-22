"""
Saves test results as JSON files and loads them back for retrieval and comparison.
"""

import json
import logging
from pathlib import Path
from typing import Optional

from src.testing.test_framework import PROJECT_ROOT, AmmeterTestResult

logger = logging.getLogger(__name__)


def _format_number(value: Optional[float], digits: int = 4) -> str:
    """
    Format a number for the comparison table.

    :param value: The number, or None when there is no value.
    :param digits: Digits after the decimal point.
    :return: The formatted number, or a dash for None.
    """
    return '-' if value is None else f'{value:.{digits}f}'


class ResultStore:
    """
    Archive of test results, one JSON file per run.
    """

    def __init__(self, results_dir: str | Path):
        """
        Prepare the results folder.

        :param results_dir: Folder for the JSON files, absolute or relative to the project root.
        """
        path = Path(results_dir)
        # Relative paths from the config are relative to the project root, not the current folder.
        self.results_dir = path if path.is_absolute() else PROJECT_ROOT / path
        self.results_dir.mkdir(parents=True, exist_ok=True)
        logger.debug('Results folder: %s', self.results_dir)

    def save(self, result: AmmeterTestResult) -> Path:
        """
        Save one result as a JSON file named after its run id.

        :param result: The result to save.
        :return: Path of the saved file.
        """
        file_path = self.results_dir / f'{result.run_id}.json'
        with open(file_path, 'w', encoding='utf-8') as file:
            json.dump(result.to_dict(), file, indent=2)
        logger.debug('Saved run %s (%s) to %s', result.run_id, result.ammeter_type, file_path)
        return file_path

    def load(self, run_id: str) -> AmmeterTestResult:
        """
        Load one saved result by its run id.

        :param run_id: Id of the run to load.
        :return: The loaded result.
        :raises FileNotFoundError: If no run with this id was saved.
        """
        file_path = self.results_dir / f'{run_id}.json'
        logger.debug('Loading run %s from %s', run_id, file_path)
        if not file_path.exists():
            raise FileNotFoundError(f'No saved run with id {run_id!r} in {self.results_dir}.')

        with open(file_path, encoding='utf-8') as file:
            return AmmeterTestResult.from_dict(json.load(file))

    def list_runs(self, ammeter_type: Optional[str] = None) -> list[AmmeterTestResult]:
        """
        Load all saved runs, oldest first.

        :param ammeter_type: If given, return only runs of this ammeter.
        :return: The saved results.
        """
        # File names start with a timestamp, so sorting by name sorts by time.
        results = [self.load(path.stem) for path in sorted(self.results_dir.glob('*.json'))]
        if ammeter_type is not None:
            results = [result for result in results if result.ammeter_type == ammeter_type]
        logger.debug('Listed %d saved runs (filter: %s)', len(results), ammeter_type)
        return results

    def load_history(self, results: list[AmmeterTestResult], limit: int) -> dict[str, list[AmmeterTestResult]]:
        """
        Load the earlier saved runs of every ammeter in the given results.

        :param results: Results of the current session, they are left out of the history.
        :param limit: Maximum number of earlier runs per ammeter, the most recent ones are kept.
        :return: Earlier results per ammeter name, oldest first.
        """
        session_ids = {result.run_id for result in results}
        history = {}
        for result in results:
            earlier = [run for run in self.list_runs(result.ammeter_type) if run.run_id not in session_ids]
            history[result.ammeter_type] = earlier[-limit:] if limit > 0 else []
        return history

    @staticmethod
    def compare(results: list[AmmeterTestResult]) -> str:
        """
        Build a side by side table of several results.

        :param results: The results to compare.
        :return: The table as text.
        """
        columns = ['run id', 'ammeter', 'samples', 'failed', 'mean', 'median', 'std', 'cv %']
        # The run id is 24 characters, the extra space keeps it apart from the next column.
        widths = [26, 10, 9, 8, 12, 12, 12, 8]

        # Pad every cell to its column width so the columns line up.
        header = ''.join(name.ljust(width) for name, width in zip(columns, widths))
        lines = [header, '-' * len(header)]

        for result in results:
            stats = result.statistics
            values = [
                result.run_id,
                result.ammeter_type,
                str(stats.count),
                str(stats.failed_count),
                _format_number(stats.mean),
                _format_number(stats.median),
                _format_number(stats.std),
                _format_number(stats.cv_percent, 1),
            ]
            lines.append(''.join(value.ljust(width) for value, width in zip(values, widths)))

        return '\n'.join(lines)
