"""
Emulator for the Greenlee ammeter, which uses Ohm's law.
"""

import logging
from Ammeters.base_ammeter import AmmeterEmulatorBase
from src.utils.Utils import generate_random_float

logger = logging.getLogger(__name__)


class GreenleeAmmeter(AmmeterEmulatorBase):
    """
    Calculates current as voltage divided by resistance.
    """

    @property
    def get_current_command(self) -> bytes:
        """
        Command that requests a measurement from Greenlee.
        """
        return b'MEASURE_GREENLEE -get_measurement'

    def measure_current(self) -> float:
        """
        Simulate one measurement with Ohm's law: I = V / R.
        :return: Current in amperes.
        """
        voltage = generate_random_float(1.0, 10.0)  # Random voltage (1V - 10V).
        resistance = generate_random_float(0.1, 100.0)  # Random resistance (0.1Ω - 100Ω).
        current = voltage / resistance
        logger.debug('Greenlee - Voltage: %sV, Resistance: %sΩ, Current: %sA', voltage, resistance, current)
        return current