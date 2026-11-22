# Sample Test Results

Real results of the framework, kept in the repository so they can be read without running anything.
The normal working folder `results/` is ignored by git, because every run creates it again.

All files come from one session with the default `config/config.yaml`:
100 samples per ammeter, every 0.5 s (2 Hz), timeout 2 s.
They were created on Linux with Python 3.13, so the paths and the platform in them are of that machine.

## Contents

| File | Created by | What it shows |
|---|---|---|
| `reports/measurement_report.html` | `python main.py --report` | HTML report of a normal run of the 3 ammeters |
| `reports/measurement_report_simulated_errors.html` | `python main.py --report --simulate-errors` | HTML report of a run with simulated faults |
| `reports/pytest_report.html` | `python -m pytest -v --report` | The test results together with a report measurement of the ammeters |
| `runs/normal/*.json` | `python main.py` | One saved run per ammeter: samples, statistics and metadata |
| `runs/simulated_errors/*.json` | `python main.py --simulate-errors` | The same, with the fault profile in the metadata |
| `main_output.txt` | `python main.py --report` | Console output of the normal run |
| `main_simulate_errors_output.txt` | `python main.py --report --simulate-errors` | Console output of the run with simulated faults |
| `pytest_output.txt` | `python -m pytest -v --report` | Output of the test suite: 118 passed |

The HTML reports are self-contained: open them in any browser, no server or internet connection is needed.

## Summary

### Normal run

| Ammeter | Samples | Failed | Mean (A) | Median (A) | CV |
|---|---|---|---|---|---|
| Greenlee | 100 | 0 | 0.3778 | 0.1217 | 365.0% |
| ENTES | 100 | 0 | 59.97 | 52.94 | 65.4% |
| CIRCUTOR | 100 | 0 | 0.0322 | 0.0317 | 46.5% |

CIRCUTOR was the most reliable ammeter (the lowest coefficient of variation).

### Run with simulated faults

| Ammeter | Simulated faults | Failed | Out of range | Mean (A) | Median (A) | CV |
|---|---|---|---|---|---|---|
| Greenlee | no reply 5% | 2 | 0 | 0.3112 | 0.1289 | 249.7% |
| ENTES | invalid reply 5%, spike 5% | 5 | 4 | 239.29 | 61.63 | 386.0% |
| CIRCUTOR | delay 3% | 4 | 0 | 0.0292 | 0.0290 | 53.7% |

Every failed sample was recorded with its reason and the run went on.
The spikes of ENTES returned values outside the possible range of 5 - 200 A, which pulled the mean up to
about 4 times the median: the median stayed close to the normal run, which is why the report shows both.

### Test suite

118 tests passed. The report measurement of `pytest --report` uses healthy emulators,
so `reports/pytest_report.html` shows no simulated faults.
