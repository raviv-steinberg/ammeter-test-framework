"""
Example: use the test framework from your own code instead of main.py.

Tests the Greenlee ammeter, saves the result and compares it with the earlier Greenlee runs.
Run it from the project root as a module:

    python -m examples.run_tests
"""

from Ammeters.runner import start_emulators
from src.testing.result_store import ResultStore
from src.testing.test_framework import AmmeterTestFramework

# The ammeter this example tests.
AMMETER = 'greenlee'


def main() -> None:
    """
    Run one test and show it next to the earlier runs of the same ammeter.
    """
    framework = AmmeterTestFramework()
    store = ResultStore(framework.config['result_management']['results_dir'])

    # Start only the ammeter this example needs.
    start_emulators({AMMETER: framework.ammeters[AMMETER]})

    result = framework.run_test(AMMETER)
    store.save(result)
    print(result.format_summary())

    # Every saved run of this ammeter, oldest first, including the one just made.
    print(f'\nAll saved {AMMETER} runs:')
    print(ResultStore.compare(store.list_runs(AMMETER)))


if __name__ == '__main__':
    main()
