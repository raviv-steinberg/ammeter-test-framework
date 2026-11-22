"""
Client for requesting current measurements from the ammeter emulators.
"""

import logging
from socket import socket, AF_INET, SOCK_STREAM

from src.exceptions.ammeter_exceptions import (
    AmmeterConnectionError,
    AmmeterInvalidReplyError,
    AmmeterResponseError,
)

logger = logging.getLogger(__name__)


class AmmeterClient:
    """
    Client that talks to a single ammeter emulator.
    """

    def __init__(self, port: int, command: bytes, host: str = 'localhost', timeout: float = 5.0):
        """
        Store the connection details of one ammeter.

        :param port: TCP port the ammeter listens on.
        :param command: Exact command bytes the ammeter expects.
        :param host: Host name of the ammeter.
        :param timeout: Seconds to wait for connect and receive.
        """
        # Port and command always belong together, so keep them on the object.
        self.port = port
        self.command = command
        self.host = host
        self.timeout = timeout
        logger.debug('Created client for %s:%s, command %r, timeout %s s', host, port, command, timeout)

    def request_current(self) -> float:
        """
        Request one measurement from the ammeter.

        :return: The measured current in amperes.
        :raises AmmeterConnectionError: If the ammeter cannot be reached or does not answer in time.
        :raises AmmeterResponseError: If the ammeter returns no data.
        :raises AmmeterInvalidReplyError: If the reply is not a number.
        """
        logger.debug('Connecting to %s:%s', self.host, self.port)
        try:
            with socket(AF_INET, SOCK_STREAM) as s:
                # Avoid hanging forever if the server does not answer.
                s.settimeout(self.timeout)
                s.connect((self.host, self.port))
                s.sendall(self.command)
                logger.debug('Sent command %r to port %s', self.command, self.port)
                data = s.recv(1024)
        except OSError as error:
            # OSError covers connection refused, timeout and other socket failures.
            raise AmmeterConnectionError(f'Cannot communicate with ammeter on port {self.port}: {error}.') from error

        # Show the exact bytes, which helps when the reply is empty or unexpected.
        logger.debug('Received raw reply %r from port %s', data, self.port)

        # An empty reply means the server did not recognise the command.
        if not data:
            raise AmmeterResponseError(f'No data received from port {self.port} for command {self.command!r}.')

        text = data.decode('utf-8')
        try:
            # The server sends the number as text, so convert it to float.
            current = float(text)
        except ValueError as error:
            raise AmmeterInvalidReplyError(f'Invalid reply from port {self.port}: {text!r}.') from error

        logger.debug('Parsed current %s A from port %s', current, self.port)
        return current
