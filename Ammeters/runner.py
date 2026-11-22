"""
Starts the ammeter emulators in background threads.
"""

import logging
import threading
import time
from typing import Optional

from Ammeters.Circutor_Ammeter import CircutorAmmeter
from Ammeters.Entes_Ammeter import EntesAmmeter
from Ammeters.Greenlee_Ammeter import GreenleeAmmeter
from Ammeters.fault_injection import build_injectors

logger = logging.getLogger(__name__)

# Maps each ammeter name in config.yaml to its emulator class.
EMULATOR_CLASSES = {
    'greenlee': GreenleeAmmeter,
    'entes': EntesAmmeter,
    'circutor': CircutorAmmeter,
}


def start_emulators(ammeters_config: dict, startup_delay: float = 1.0,
                    simulation_config: Optional[dict] = None) -> None:
    """
    Start every ammeter defined in the config, each in its own background thread.

    :param ammeters_config: The ammeters section of config.yaml.
    :param startup_delay: Seconds to wait so the servers are listening before the function returns.
    :param simulation_config: The error_simulation section of config.yaml, None for healthy emulators.
    :raises ValueError: If the config contains an ammeter name that has no emulator class.
    """
    injectors = build_injectors(simulation_config, list(ammeters_config))
    for name, settings in ammeters_config.items():
        # Fail early with a clear message instead of a KeyError.
        if name not in EMULATOR_CLASSES:
            raise ValueError(f'No emulator for ammeter {name!r}. Known ammeters: {list(EMULATOR_CLASSES)}.')

        emulator_class = EMULATOR_CLASSES[name]
        logger.debug('Starting %s emulator (%s) on port %s', name, emulator_class.__name__, settings['port'])
        emulator = emulator_class(settings['port'], injectors.get(name))
        if name in injectors:
            logger.info('Error simulation on %s: %s', name, injectors[name].profile.to_dict())
        # Daemon thread so the server stops when the main program ends.
        threading.Thread(target=emulator.start_server, daemon=True, name=f'{name}-emulator').start()

    # Give the servers time to bind and start listening.
    logger.debug('Waiting %.1f s for the emulators to start listening', startup_delay)
    time.sleep(startup_delay)
