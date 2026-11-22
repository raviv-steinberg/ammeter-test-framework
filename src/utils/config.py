"""
Loads the YAML configuration file.
"""

import logging

import yaml

logger = logging.getLogger(__name__)


def load_config(config_path: str) -> dict:
    """
    Load the configuration file.

    :param config_path: Path to the YAML file.
    :return: The configuration as a dictionary.
    """
    logger.debug('Loading config from %s', config_path)
    with open(config_path, 'r', encoding='utf-8') as file:
        config = yaml.safe_load(file)
    logger.debug('Loaded config: %s', config)
    return config
