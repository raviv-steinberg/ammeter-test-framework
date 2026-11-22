"""
Shared fixtures for the test suite. pytest loads this file automatically.
"""

import socket
import threading
import time
from pathlib import Path
from typing import Optional

import pytest
import yaml

from Ammeters.runner import start_emulators
from tests.expected import COMMANDS


def get_free_port() -> int:
    """
    Find a port on localhost where nothing is listening.

    :return: The port number.
    """
    # Ask the operating system for a free port, then close it again right away.
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('localhost', 0))
        return s.getsockname()[1]


class FakeAmmeterServer:
    """
    Small TCP server that answers every connection with a prepared reply.

    It lets the tests create situations the real emulators never produce,
    such as a reply that is not a number or an answer that comes too late.
    """

    def __init__(self, reply: Optional[bytes], delay: float = 0.0):
        """
        Start the server on a free port.

        :param reply: Bytes to send back, or None to close the connection without answering.
        :param delay: Seconds to wait before answering, to simulate a slow ammeter.
        """
        self.reply = reply
        self.delay = delay
        # Every command the server received, so tests can check what the client sent.
        self.received = []

        self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        # Port 0 lets the operating system pick a free port, so tests never clash.
        self._socket.bind(('localhost', 0))
        self._socket.listen()
        # Wake up regularly to check whether the server was asked to stop.
        self._socket.settimeout(0.1)
        self.port = self._socket.getsockname()[1]

        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._serve, daemon=True, name='fake-ammeter')
        self._thread.start()

    def _serve(self) -> None:
        """
        Accept connections until stop() is called.
        """
        while not self._stop_event.is_set():
            try:
                conn, _ = self._socket.accept()
            except TimeoutError:
                # No client yet, check the stop flag again.
                continue
            except OSError:
                # The socket was closed by stop().
                break

            with conn:
                self.received.append(conn.recv(1024))
                if self.delay:
                    time.sleep(self.delay)
                if self.reply is not None:
                    try:
                        conn.sendall(self.reply)
                    except OSError:
                        # The client may have given up already, for example after a timeout.
                        pass

    def stop(self) -> None:
        """
        Stop the server and release the port.
        """
        self._stop_event.set()
        self._thread.join(timeout=2)
        self._socket.close()


@pytest.fixture
def fake_server():
    """
    Factory that starts fake ammeter servers and stops all of them after the test.

    Usage inside a test: server = fake_server(b'1.5')
    """
    servers = []

    def start(reply: Optional[bytes], delay: float = 0.0) -> FakeAmmeterServer:
        """
        Start one fake server.

        :param reply: Bytes to send back, or None for no answer.
        :param delay: Seconds to wait before answering.
        :return: The running server.
        """
        server = FakeAmmeterServer(reply, delay)
        servers.append(server)
        return server

    # Everything before yield runs before the test, everything after it runs after the test.
    yield start

    for server in servers:
        server.stop()


@pytest.fixture
def closed_port() -> int:
    """
    A port on localhost where nothing is listening.

    :return: The port number.
    """
    return get_free_port()


@pytest.fixture(scope='session')
def emulators_config() -> dict:
    """
    Start the three real emulators once for the whole test session, on free ports.

    Free ports keep the tests from clashing with a main.py that may be running at the same time.

    :return: A config dictionary shaped like config.yaml that points to the running emulators.
    """
    ammeters = {name: {'port': get_free_port(), 'command': command} for name, command in COMMANDS.items()}
    # Emulator threads are daemon threads, so they stop by themselves when pytest exits.
    start_emulators(ammeters, startup_delay=0.5)

    return {
        'testing': {
            # Few and fast samples, so the integration tests take well under a second each.
            'sampling': {'measurements_count': 5, 'total_duration_seconds': None, 'sampling_frequency_hz': 50},
        },
        'ammeters': ammeters,
    }


@pytest.fixture
def write_config(tmp_path):
    """
    Factory that writes a config dictionary to a YAML file in a temporary folder.

    Usage inside a test: path = write_config(config_dict)
    """

    def write(config: dict) -> Path:
        """
        Save the config as YAML.

        :param config: The config dictionary.
        :return: Path of the written file.
        """
        path = tmp_path / 'config.yaml'
        # Keep the key order, safe_dump sorts the keys alphabetically by default.
        path.write_text(yaml.safe_dump(config, sort_keys=False), encoding='utf-8')
        return path

    return write
