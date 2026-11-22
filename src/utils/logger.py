"""
Logging setup: a detailed log file for every run and a short output on the console.
"""

import logging
from datetime import datetime
from pathlib import Path

# Format: [timestamp] LEVEL file:function: message. Used for both the file and the console.
LOG_FORMAT = '[%(asctime)s] [%(levelname)s] %(filename)s:%(funcName)s: %(message)s'


def setup_logging(log_dir: str | Path, console_level: str = 'INFO', file_level: str = 'DEBUG') -> Path:
    """
    Configure logging for the whole program.
    :param log_dir: Folder for the log files.
    :param console_level: Lowest level shown on the console.
    :param file_level: Lowest level written to the log file.
    :return: Path of the new log file.
    """
    log_dir = Path(log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    log_file = log_dir / f'{timestamp}.log'

    root_logger = logging.getLogger()
    # Let every message reach the handlers, each handler filters by its own level.
    root_logger.setLevel(logging.DEBUG)

    # Remove handlers from an earlier call so messages are not written twice.
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
        handler.close()

    formatter = logging.Formatter(LOG_FORMAT)

    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setLevel(file_level)
    file_handler.setFormatter(formatter)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(console_level)
    console_handler.setFormatter(formatter)

    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)
    return log_file