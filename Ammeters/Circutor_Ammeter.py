"""
Emulator for the CIRCUTOR ammeter, which uses Rogowski coil integration.
"""

import logging
from Ammeters.base_ammeter import AmmeterEmulatorBase
from src.utils.Utils import generate_random_float

logger = logging.getLogger(__name__)


class CircutorAmmeter(AmmeterEmulatorBase):
    """
    Calculates current by integrating voltage samples over time.
    """

    @property
    def get_current_command(self) -> bytes:
        """
        Command that requests a measurement from CIRCUTOR.
        """
        return b'MEASURE_CIRCUTOR -get_measurement'

    def measure_current(self) -> float:
        """
        Simulate one measurement with Rogowski coil integration: I = sum(V * dt).
        :return: Current in amperes.
        """
        num_samples = 10
        time_step = generate_random_float(0.001, 0.01)  # Time step (0.001s - 0.01s).
        voltages = [generate_random_float(0.1, 1.0) for _ in range(num_samples)]  # Voltage values.
        current = sum(v * time_step for v in voltages)
        logger.debug('CIRCUTOR - Voltages: %s, Time Step: %ss, Current: %sA', voltages, time_step, current)
        return current