"""
Tests for the three ammeter emulators: formula, value range and command.

These tests call measure_current directly, without starting a server.
"""

import pytest

import Ammeters.Circutor_Ammeter as circutor_module
import Ammeters.Entes_Ammeter as entes_module
import Ammeters.Greenlee_Ammeter as greenlee_module
from Ammeters.Circutor_Ammeter import CircutorAmmeter
from Ammeters.Entes_Ammeter import EntesAmmeter
from Ammeters.Greenlee_Ammeter import GreenleeAmmeter
from tests.expected import COMMANDS, CURRENT_RANGES

# Ammeter name to emulator class, in the same order as in the README.
EMULATORS = {
    'greenlee': GreenleeAmmeter,
    'entes': EntesAmmeter,
    'circutor': CircutorAmmeter,
}

# How many random measurements to take when checking the range.
RANGE_SAMPLES = 500


class ScriptedRandom:
    """
    Replacement for generate_random_float that returns prepared values instead of random ones.

    It also records every range it was asked for, so tests can check the ranges against the README.
    """

    def __init__(self, values: list[float]):
        """
        Prepare the values to return, in order.

        :param values: Values returned by the next calls, one per call.
        """
        self.values = list(values)
        # Every (min_value, max_value) pair the emulator asked for.
        self.requested_ranges = []

    def __call__(self, min_value: float, max_value: float) -> float:
        """
        Return the next prepared value and record the requested range.

        :param min_value: Lowest value the emulator asked for.
        :param max_value: Highest value the emulator asked for.
        :return: The next prepared value.
        """
        self.requested_ranges.append((min_value, max_value))
        return self.values.pop(0)


@pytest.mark.emulators
@pytest.mark.unit
class TestEmulatorFormulas:
    """
    With fixed inputs each emulator must return exactly the value of its formula.
    """

    def test_greenlee_uses_ohms_law(self, monkeypatch):
        """
        I = V / R with V = 5 V and R = 2 ohm gives 2.5 A.
        """
        scripted = ScriptedRandom([5.0, 2.0])
        # Replace the random function only inside the Greenlee module, only for this test.
        monkeypatch.setattr(greenlee_module, 'generate_random_float', scripted)

        current = GreenleeAmmeter(0).measure_current()

        assert current == pytest.approx(2.5)
        assert scripted.requested_ranges == [(1.0, 10.0), (0.1, 100.0)]

    def test_entes_uses_hall_effect(self, monkeypatch):
        """
        I = B * K with B = 0.05 T and K = 1000 gives 50 A.
        """
        scripted = ScriptedRandom([0.05, 1000.0])
        monkeypatch.setattr(entes_module, 'generate_random_float', scripted)

        current = EntesAmmeter(0).measure_current()

        assert current == pytest.approx(50.0)
        assert scripted.requested_ranges == [(0.01, 0.1), (500, 2000)]

    def test_circutor_integrates_voltage_over_time(self, monkeypatch):
        """
        I = sum(V * dt) with dt = 0.005 s and ten samples of 0.5 V gives 10 * 0.5 * 0.005 = 0.025 A.
        """
        # The time step is drawn first, then the ten voltages.
        scripted = ScriptedRandom([0.005] + [0.5] * 10)
        monkeypatch.setattr(circutor_module, 'generate_random_float', scripted)

        current = CircutorAmmeter(0).measure_current()

        assert current == pytest.approx(0.025)
        assert scripted.requested_ranges == [(0.001, 0.01)] + [(0.1, 1.0)] * 10


@pytest.mark.emulators
@pytest.mark.unit
class TestEmulatorRanges:
    """
    With real random inputs every value must stay inside the range the formula allows.
    """

    @pytest.mark.parametrize('name', EMULATORS)
    def test_values_stay_in_range(self, name):
        """
        Many random measurements, none of them outside the possible range.
        """
        emulator = EMULATORS[name](0)
        low, high = CURRENT_RANGES[name]

        values = [emulator.measure_current() for _ in range(RANGE_SAMPLES)]

        assert all(low <= value <= high for value in values)

    @pytest.mark.parametrize('name', EMULATORS)
    def test_values_are_random(self, name):
        """
        The emulator does not return the same value every time.
        """
        emulator = EMULATORS[name](0)

        values = {emulator.measure_current() for _ in range(20)}

        assert len(values) > 1


@pytest.mark.emulators
@pytest.mark.unit
class TestEmulatorCommands:
    """
    Every emulator answers to the command written in the README.
    """

    @pytest.mark.parametrize('name', EMULATORS)
    def test_command_matches_readme(self, name):
        """
        The command in the code is byte for byte the command in the README.
        """
        assert EMULATORS[name](0).get_current_command == COMMANDS[name].encode('utf-8')
