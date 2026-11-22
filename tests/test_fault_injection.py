"""
Tests for the error simulation: the fault settings, the emulator that misbehaves on purpose,
and the framework that has to cope with it.
"""

import copy
import socket
import struct
import threading
import time
from collections import Counter

import pytest

from Ammeters.base_ammeter import AmmeterEmulatorBase
from Ammeters.client import AmmeterClient
from Ammeters.fault_injection import FAULT_TYPES, INVALID_REPLY, FaultInjector, FaultProfile, build_injectors
from src.exceptions.ammeter_exceptions import AmmeterConnectionError, AmmeterInvalidReplyError, AmmeterResponseError
from src.testing.test_framework import AmmeterTestFramework
from tests.conftest import get_free_port

COMMAND = b'MEASURE_FIXED'
# The value the fixed emulator always measures.
FIXED_CURRENT = 2.0


class FixedAmmeter(AmmeterEmulatorBase):
    """
    Emulator that always measures the same value, so the effect of a fault is easy to see.
    """

    @property
    def get_current_command(self) -> bytes:
        """
        Command of the fixed emulator.
        """
        return COMMAND

    def measure_current(self) -> float:
        """
        Always the same current.

        :return: FIXED_CURRENT.
        """
        return FIXED_CURRENT


def start_fixed_ammeter(profile: FaultProfile) -> tuple[FixedAmmeter, int]:
    """
    Start a fixed emulator with a fault profile on a free port.

    :param profile: The faults to simulate.
    :return: The emulator and its port.
    """
    port = get_free_port()
    emulator = FixedAmmeter(port, FaultInjector(profile, seed=1))
    threading.Thread(target=emulator.start_server, daemon=True).start()
    # Wait until the server listens.
    for _ in range(50):
        try:
            socket.create_connection(('localhost', port), timeout=0.1).close()
            break
        except OSError:
            time.sleep(0.02)
    return emulator, port


@pytest.mark.faults
@pytest.mark.unit
class TestFaultProfile:
    """
    The fault settings from config.yaml.
    """

    @pytest.mark.parametrize('settings, message', [
        ({'no_reply': 1.5}, 'between 0 and 1'),
        ({'spike': -0.1}, 'between 0 and 1'),
        ({'no_reply': 0.6, 'delay': 0.6}, 'add up to 1.20'),
        ({'delay_seconds': 0}, 'must be positive'),
        ({'no_replies': 0.1}, 'Unknown error simulation settings'),
    ])
    def test_invalid_settings_are_rejected(self, settings, message):
        """
        A setting that cannot be right stops the run with a clear error.
        """
        with pytest.raises(ValueError, match=message):
            FaultProfile.from_dict(settings)

    def test_shared_defaults_and_own_settings(self):
        """
        delay_seconds and spike_factor are shared, but one ammeter can override them.
        """
        profile = FaultProfile.from_dict({'spike': 0.1, 'spike_factor': 10}, {'spike_factor': 50, 'delay_seconds': 4})

        assert profile.spike == 0.1
        assert profile.spike_factor == 10
        assert profile.delay_seconds == 4


@pytest.mark.faults
@pytest.mark.unit
class TestFaultInjector:
    """
    Choosing the fault of each request.
    """

    def test_no_faults_by_default(self):
        """
        A profile without probabilities never misbehaves.
        """
        injector = FaultInjector(FaultProfile(), seed=1)

        assert all(injector.choose() is None for _ in range(1000))

    def test_frequencies_follow_the_probabilities(self):
        """
        Over many requests every fault happens about as often as configured.
        """
        injector = FaultInjector(FaultProfile(no_reply=0.1, invalid_reply=0.2, delay=0.05, spike=0.15), seed=7)

        counts = Counter(injector.choose() for _ in range(20000))

        assert counts['no_reply'] / 20000 == pytest.approx(0.1, abs=0.01)
        assert counts['invalid_reply'] / 20000 == pytest.approx(0.2, abs=0.01)
        assert counts['delay'] / 20000 == pytest.approx(0.05, abs=0.01)
        assert counts['spike'] / 20000 == pytest.approx(0.15, abs=0.01)
        assert counts[None] / 20000 == pytest.approx(0.5, abs=0.015)

    def test_same_seed_same_faults(self):
        """
        A fixed seed repeats exactly the same faults, so a failing run can be reproduced.
        """
        profile = FaultProfile(no_reply=0.3, spike=0.3)

        runs = [[injector.choose() for _ in range(100)] for injector in (FaultInjector(profile, 42), FaultInjector(profile, 42))]

        assert runs[0] == runs[1]
        # Not a trivial sequence: some faults and some normal answers.
        assert {'no_reply', 'spike', None} <= set(runs[0])


@pytest.mark.faults
@pytest.mark.unit
class TestBuildInjectors:
    """
    Turning the error_simulation section of config.yaml into injectors.
    """

    def test_disabled_simulation_builds_nothing(self):
        """
        enabled: false keeps every emulator healthy, whatever the profiles say.
        """
        assert build_injectors({'enabled': False, 'ammeters': {'entes': {'no_reply': 1}}}, ['entes']) == {}
        assert build_injectors(None, ['entes']) == {}

    def test_only_listed_ammeters_get_faults(self):
        """
        An ammeter left out of the section stays healthy.
        """
        injectors = build_injectors({'enabled': True, 'ammeters': {'entes': {'no_reply': 0.5}}}, ['greenlee', 'entes'])

        assert list(injectors) == ['entes']
        assert injectors['entes'].profile.no_reply == 0.5

    def test_unknown_ammeter_is_rejected(self):
        """
        A typo in an ammeter name is reported instead of silently simulating nothing.
        """
        with pytest.raises(ValueError, match='unknown ammeters'):
            build_injectors({'enabled': True, 'ammeters': {'fluke': {'no_reply': 0.5}}}, ['greenlee'])


@pytest.mark.faults
@pytest.mark.network
class TestFaultyEmulator:
    """
    A real emulator that misbehaves, seen through the real client.
    """

    def test_no_reply(self):
        """
        The emulator closes without answering, the client reports it as a missing reply.
        """
        _, port = start_fixed_ammeter(FaultProfile(no_reply=1.0))

        with pytest.raises(AmmeterResponseError):
            AmmeterClient(port, COMMAND).request_current()

    def test_invalid_reply(self):
        """
        The emulator answers text, the client reports the text it got.
        """
        _, port = start_fixed_ammeter(FaultProfile(invalid_reply=1.0))

        with pytest.raises(AmmeterInvalidReplyError, match=INVALID_REPLY.decode()):
            AmmeterClient(port, COMMAND).request_current()

    def test_spike(self):
        """
        The emulator answers the real value times the spike factor, a number that looks valid.
        """
        _, port = start_fixed_ammeter(FaultProfile(spike=1.0, spike_factor=50))

        assert AmmeterClient(port, COMMAND).request_current() == FIXED_CURRENT * 50

    def test_delay_longer_than_timeout_fails_and_server_survives(self):
        """
        A late answer makes the client give up, and the emulator keeps serving the next requests.
        """
        emulator, port = start_fixed_ammeter(FaultProfile(delay=1.0, delay_seconds=0.5))

        with pytest.raises(AmmeterConnectionError):
            AmmeterClient(port, COMMAND, timeout=0.2).request_current()

        # Let the late answer hit the closed connection, then switch the faults off.
        time.sleep(0.6)
        emulator.fault_injector = None
        assert AmmeterClient(port, COMMAND).request_current() == FIXED_CURRENT


    def test_server_survives_a_connection_reset(self):
        """
        A client that resets the connection before the answer used to stop the emulator thread for good.
        """
        emulator, port = start_fixed_ammeter(FaultProfile(delay=1.0, delay_seconds=0.3))

        client = socket.create_connection(('localhost', port))
        client.sendall(COMMAND)
        # SO_LINGER with 0 seconds closes with a reset, so the late answer hits a reset connection.
        client.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack('ii', 1, 0))
        client.close()

        time.sleep(0.5)
        emulator.fault_injector = None
        assert AmmeterClient(port, COMMAND).request_current() == FIXED_CURRENT


@pytest.mark.faults
@pytest.mark.integration
@pytest.mark.network
class TestFrameworkWithFaults:
    """
    The whole framework running against emulators that fail on purpose.
    """

    def test_failures_are_recorded_and_the_run_goes_on(self, write_config):
        """
        Half of the samples fail, every sample is still taken, and the run says the failures were simulated.
        """
        from Ammeters.runner import start_emulators

        ammeters = {'entes': {'port': get_free_port(), 'command': 'MEASURE_ENTES -get_data'}}
        simulation = {'enabled': True, 'seed': 3, 'ammeters': {'entes': {'no_reply': 0.25, 'invalid_reply': 0.25}}}
        start_emulators(ammeters, startup_delay=0.3, simulation_config=simulation)
        config = {'testing': {'sampling': {'measurements_count': 40, 'total_duration_seconds': None, 'sampling_frequency_hz': 200}},
                  'ammeters': ammeters, 'error_simulation': copy.deepcopy(simulation)}

        result = AmmeterTestFramework(write_config(config)).run_test('entes')

        assert len(result.samples) == 40
        assert 0 < result.statistics.failed_count < 40
        assert result.statistics.count + result.statistics.failed_count == 40
        errors = {sample.error.split(' ')[0] for sample in result.samples if sample.error}
        assert errors <= {'No', 'Invalid'}
        assert result.metadata['error_simulation']['no_reply'] == 0.25

    def test_healthy_run_has_no_simulation_in_metadata(self, emulators_config, write_config):
        """
        Without the simulation the metadata says so, so a reader knows the failures were real.
        """
        result = AmmeterTestFramework(write_config(emulators_config)).run_test('greenlee')

        assert result.metadata['error_simulation'] is None


@pytest.mark.faults
@pytest.mark.unit
def test_every_fault_type_is_documented():
    """
    The four fault types in the code are the four documented in config.yaml and the README.
    """
    assert FAULT_TYPES == ('no_reply', 'invalid_reply', 'delay', 'spike')
