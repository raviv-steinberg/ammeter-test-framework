"""
Entry point that starts the ammeter emulators, tests each of them, saves the results and can build an HTML report.

Usage:
    python main.py                  run the tests
    python main.py --report         run the tests and write an HTML report
    python main.py --show-report    run the tests, write the report and open it in the browser
    python main.py --debug          also show debug messages on the console
    python main.py --simulate-errors   make the emulators fail on purpose, as set in config.yaml
"""

import argparse

from Ammeters.runner import start_emulators
from src.reporting.html_report import generate_report, open_report
from src.testing.result_store import ResultStore
from src.testing.test_framework import DEFAULT_CONFIG_PATH, PROJECT_ROOT, AmmeterTestFramework
from src.utils.config import load_config
from src.utils.logger import setup_logging

# Used when config.yaml has no report section.
DEFAULT_REPORT_DIR = 'results/reports'
DEFAULT_HISTORY_RUNS = 8


def parse_args() -> argparse.Namespace:
    """
    Read the command line options.

    :return: The parsed options.
    """
    parser = argparse.ArgumentParser(description='Run the ammeter test framework.')
    parser.add_argument('--debug', action='store_true', help='Show debug messages on the console too.')
    parser.add_argument('--report', action='store_true', help='Write an HTML report when the tests finish.')
    parser.add_argument('--show-report', action='store_true',
                        help='Write the HTML report and open it in the browser. Implies --report.')
    parser.add_argument('--simulate-errors', action='store_true',
                        help='Make the emulators fail on purpose, as set in the error_simulation section of config.yaml.')
    return parser.parse_args()


if __name__ == '__main__':
    args = parse_args()

    # Read the logging settings first, so logging is ready before anything else runs.
    config = load_config(str(DEFAULT_CONFIG_PATH))
    logging_config = config['logging']
    # The --debug option overrides the console level from the config.
    console_level = 'DEBUG' if args.debug else logging_config['console_level']
    log_file = setup_logging(PROJECT_ROOT / logging_config['log_dir'], console_level, logging_config['file_level'])
    print(f'Log file: {log_file}')

    framework = AmmeterTestFramework()
    store = ResultStore(framework.config['result_management']['results_dir'])

    # --simulate-errors switches the simulation on without editing config.yaml.
    simulation = framework.config.get('error_simulation') or {}
    if args.simulate_errors:
        simulation['enabled'] = True
        framework.config['error_simulation'] = simulation
    if simulation.get('enabled'):
        print('Error simulation is ON: the emulators fail on purpose, as set in config.yaml.')
    start_emulators(framework.ammeters, simulation_config=simulation)

    session_results = []
    # Run one ammeter at a time so each summary is printed as soon as it is ready.
    for ammeter_type in framework.ammeters:
        result = framework.run_test(ammeter_type)
        saved_path = store.save(result)
        session_results.append(result)

        print()
        print(result.format_summary())
        print(f'saved:    {saved_path}')

    # Show this session's ammeters side by side.
    print('\nThis session:')
    print(ResultStore.compare(session_results))

    if args.report or args.show_report:
        report_config = framework.config.get('report') or {}
        report_dir = PROJECT_ROOT / report_config.get('output_dir', DEFAULT_REPORT_DIR)
        history = store.load_history(session_results, report_config.get('history_runs', DEFAULT_HISTORY_RUNS))

        report_path = generate_report(session_results, report_dir, history)
        print(f'\nReport:   {report_path}')

        if args.show_report:
            open_report(report_path)
