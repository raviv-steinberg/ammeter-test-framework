"""
Base class for all ammeter emulators.
"""

import logging
import os
import random
import socket
import time
from abc import ABC, abstractmethod
from typing import Optional

from Ammeters.fault_injection import INVALID_REPLY, FaultInjector

logger = logging.getLogger(__name__)

NotImplementedErrorMsg = 'Subclasses must implement this property.'


class AmmeterEmulatorBase(ABC):
    """
    TCP server that answers a measurement command with a simulated current value.
    """

    def __init__(self, port: int, fault_injector: Optional[FaultInjector] = None):
        """
        Store the port and seed the random number generator.

        :param port: TCP port the emulator listens on.
        :param fault_injector: Makes the emulator misbehave on purpose, None for a healthy emulator.
        """
        self.port = port
        self.fault_injector = fault_injector
        # Seed the random number generator for each instance.
        random.seed(time.time())

    def start_server(self):
        """
        Starts the server to listen for client requests.
        The server will run indefinitely, handling one client request at a time.
        """
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            # On Linux and macOS a closed server keeps its port busy for about a minute (TIME_WAIT),
            # so a second run right after the first one would fail. SO_REUSEADDR lets it start again.
            # Windows is left out on purpose: there the option would let two servers share one port.
            if os.name != 'nt':
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(('localhost', self.port))
            s.listen()
            logger.info('%s is running on port %s', self.__class__.__name__, self.port)
            while True:
                conn, addr = s.accept()
                with conn:
                    logger.debug('Connected by %s', addr)
                    try:
                        self.handle_request(conn)
                    except OSError as error:
                        # The client may have gone already, for example after its timeout.
                        # One broken connection must not stop the server for every later request.
                        logger.warning('%s lost the connection on port %s: %s', self.__class__.__name__, self.port, error)

    def handle_request(self, conn: socket.socket) -> None:
        """
        Read one command and answer it, misbehaving on purpose when a fault is simulated.

        :param conn: The connection of one client.
        """
        data = conn.recv(1024)
        if data != self.get_current_command:
            # Report unknown commands instead of ignoring them silently.
            logger.warning('%s received unknown command %r on port %s', self.__class__.__name__, data, self.port)
            return

        fault = self.fault_injector.choose() if self.fault_injector else None
        if fault:
            logger.warning('%s simulates fault %r on port %s', self.__class__.__name__, fault, self.port)

        if fault == 'no_reply':
            # Close without answering, like a device that drops the request.
            return
        if fault == 'invalid_reply':
            conn.sendall(INVALID_REPLY)
            return
        if fault == 'delay':
            time.sleep(self.fault_injector.profile.delay_seconds)

        # Call the specific measure_current() method defined in subclasses.
        current = self.measure_current()
        if fault == 'spike':
            # A wrong reading that still looks like a valid number.
            current *= self.fault_injector.profile.spike_factor
        conn.sendall(str(current).encode('utf-8'))

    @property
    @abstractmethod
    def get_current_command(self) -> bytes:
        """
        This property must be implemented by each subclass to provide the specific
        command to get the current measurement.
        """
        raise NotImplementedError(NotImplementedErrorMsg)

    @abstractmethod
    def measure_current(self) -> float:
        """
        This method must be implemented by each subclass to provide the specific
        logic for current measurement.
        """
        raise NotImplementedError(NotImplementedErrorMsg)
    