"""
Emulator for the ENTES ammeter, which uses the Hall effect.
"""

import logging
from Ammeters.base_ammeter import AmmeterEmulatorBase
from src.utils.Utils import generate_random_float

logger = logging.getLogger(__name__)


class EntesAmmeter(AmmeterEmulatorBase):
    """
    Calculates current as magnetic field multiplied by a calibration factor.
    """

    @property
    def get_current_command(self) -> bytes:
        """
        Command that requests a measurement from ENTES.
        """
        return b'MEASURE_ENTES -get_data'

    def measure_current(self) -> float:
        """
        Simulate one measurement with the Hall effect: I = B * K.
        :return: Current in amperes.
        """
        magnetic_field = generate_random_float(0.01, 0.1)  # Magnetic field strength (0.01T - 0.1T).
        calibration_factor = generate_random_float(500, 2000)  # Calibration factor (500 - 2000).
        current = magnetic_field * calibration_factor
        logger.debug('ENTES - Magnetic Field: %sT, Calibration Factor: %s, Current: %sA',
                     magnetic_field, calibration_factor, current)
        return current