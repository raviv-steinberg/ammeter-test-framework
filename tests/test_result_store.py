"""
Tests for saving, loading and comparing test results.

The results are built by hand, so these tests need no emulator and no network.
"""

import json
import re

import pytest

from src.testing.analysis import analyze_samples
from src.testing.result_store import ResultStore
from src.testing.sampler import Sample
from src.testing.test_framework import AmmeterTestResult, generate_run_id

# Expected shape of a run id: YYYYMMDD_HHMMSS_ followed by eight hex characters.
RUN_ID_PATTERN = r'\d{8}_\d{6}_[0-9a-f]{8}'


def make_result(run_id: str, ammeter_type: str = 'greenlee', values: tuple = (1.0, 2.0, None)) -> AmmeterTestResult:
    """
    Build a result by hand, without running a real test.

    :param run_id: Run id of the result.
    :param ammeter_type: Ammeter name.
    :param values: Currents of the samples, None means a failed sample.
    :return: The result.
    """
    samples = [Sample(index, index * 0.5, value, None if value is not None else 'failed')
               for index, value in enumerate(values)]
    return AmmeterTestResult(
        run_id=run_id,
        ammeter_type=ammeter_type,
        started_at='2026-11-22T10:00:00',
        duration_seconds=1.0,
        measurements_count=len(values),
        interval_seconds=0.5,
        metadata={'port': 5000, 'command': 'TEST'},
        samples=samples,
        statistics=analyze_samples(samples),
    )


@pytest.fixture
def store(tmp_path):
    """
    A result store that writes into a temporary folder, deleted by pytest after the test.
    """
    return ResultStore(tmp_path / 'runs')


@pytest.mark.results
@pytest.mark.unit
class TestRunId:
    """
    Unique identification of every test run.
    """

    def test_run_id_format(self):
        """
        The id starts with the date and time, so sorting by id sorts by time.
        """
        assert re.fullmatch(RUN_ID_PATTERN, generate_run_id())

    def test_run_ids_are_unique(self):
        """
        Many ids created in the same second do not clash.

        With 32 random bits the chance of a clash among 100 ids is about one in a million,
        with the old 24 bits it was about 3% for 1000 ids, which made this test fail now and then.
        """
        run_ids = {generate_run_id() for _ in range(100)}

        assert len(run_ids) == 100


@pytest.mark.results
@pytest.mark.unit
class TestResultStore:
    """
    Saving results to JSON files and reading them back.
    """

    def test_save_creates_json_file_named_after_run_id(self, store):
        """
        One file per run, named after the run id, containing valid JSON.
        """
        path = store.save(make_result('20261122_100000_aaaaaa'))

        assert path.name == '20261122_100000_aaaaaa.json'
        data = json.loads(path.read_text(encoding='utf-8'))
        assert data['run_id'] == '20261122_100000_aaaaaa'
        assert data['metadata']['port'] == 5000

    def test_load_returns_exactly_what_was_saved(self, store):
        """
        Save and load lose nothing: the loaded result equals the original, failed samples included.
        """
        original = make_result('20261122_100000_aaaaaa')

        store.save(original)
        loaded = store.load(original.run_id)

        assert loaded == original
        # Nested objects come back as objects, not as dictionaries.
        assert isinstance(loaded.samples[0], Sample)
        assert loaded.samples[2].current is None

    def test_load_unknown_run_raises(self, store):
        """
        Loading a run that was never saved gives a clear error with the run id.
        """
        with pytest.raises(FileNotFoundError, match='no_such_run'):
            store.load('no_such_run')

    def test_list_runs_is_sorted_by_time(self, store):
        """
        Runs come back oldest first, whatever order they were saved in.
        """
        for run_id in ['20261122_120000_cccccc', '20261122_100000_aaaaaa', '20261122_110000_bbbbbb']:
            store.save(make_result(run_id))

        run_ids = [result.run_id for result in store.list_runs()]

        assert run_ids == ['20261122_100000_aaaaaa', '20261122_110000_bbbbbb', '20261122_120000_cccccc']

    def test_list_runs_filters_by_ammeter(self, store):
        """
        Only the runs of the requested ammeter are returned.
        """
        store.save(make_result('20261122_100000_aaaaaa', 'greenlee'))
        store.save(make_result('20261122_110000_bbbbbb', 'entes'))
        store.save(make_result('20261122_120000_cccccc', 'greenlee'))

        results = store.list_runs('greenlee')

        assert [result.run_id for result in results] == ['20261122_100000_aaaaaa', '20261122_120000_cccccc']

    def test_load_history_leaves_out_the_current_runs(self, store):
        """
        The history of an ammeter is its earlier runs, newest last, without the runs of this session.
        """
        for run_id in ['20261122_100000_aaaaaa', '20261122_110000_bbbbbb', '20261122_120000_cccccc']:
            store.save(make_result(run_id))
        current = store.load('20261122_120000_cccccc')

        history = store.load_history([current], limit=1)

        assert [run.run_id for run in history['greenlee']] == ['20261122_110000_bbbbbb']

    def test_list_runs_on_empty_store(self, store):
        """
        A store with no saved runs returns an empty list instead of failing.
        """
        assert store.list_runs() == []


@pytest.mark.results
@pytest.mark.unit
class TestCompare:
    """
    The side by side comparison table.
    """

    def test_table_has_header_and_one_row_per_run(self):
        """
        A header, a separator line and one line for each result.
        """
        results = [make_result('20261122_100000_aaaaaa', 'greenlee'), make_result('20261122_110000_bbbbbb', 'entes')]

        lines = ResultStore.compare(results).splitlines()

        assert len(lines) == 4
        assert lines[0].startswith('run id')
        assert '20261122_100000_aaaaaa' in lines[2] and 'greenlee' in lines[2]
        assert '20261122_110000_bbbbbb' in lines[3] and 'entes' in lines[3]

    def test_failed_run_shows_dashes(self):
        """
        A run where every sample failed has no numbers, so the table shows dashes instead of crashing.
        """
        result = make_result('20261122_100000_aaaaaa', values=(None, None))

        row = ResultStore.compare([result]).splitlines()[2]

        assert '-' in row.split()
