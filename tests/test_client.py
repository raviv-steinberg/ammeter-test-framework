"""
Tests for the TCP client that requests measurements from an ammeter.
"""

import time

import pytest

from Ammeters.client import AmmeterClient
from src.exceptions.ammeter_exceptions import (
    AmmeterConnectionError,
    AmmeterError,
    AmmeterInvalidReplyError,
    AmmeterResponseError,
)

COMMAND = b'MEASURE_TEST -get_measurement'


@pytest.mark.client
@pytest.mark.network
class TestAmmeterClientSuccess:
    """
    The client against a server that answers correctly.
    """

    def test_returns_the_reply_as_float(self, fake_server):
        """
        The number sent by the server comes back as a float.
        """
        server = fake_server(b'1.25')

        current = AmmeterClient(server.port, COMMAND).request_current()

        assert isinstance(current, float)
        assert current == 1.25

    def test_sends_the_exact_command(self, fake_server):
        """
        The server receives exactly the command the client was created with.
        """
        server = fake_server(b'1.0')

        AmmeterClient(server.port, COMMAND).request_current()

        assert server.received == [COMMAND]

    def test_every_request_is_a_new_connection(self, fake_server):
        """
        The same client can be used many times, each request opens its own connection.
        """
        server = fake_server(b'2.0')
        client = AmmeterClient(server.port, COMMAND)

        results = [client.request_current() for _ in range(3)]

        assert results == [2.0, 2.0, 2.0]
        assert len(server.received) == 3


@pytest.mark.client
@pytest.mark.network
class TestAmmeterClientErrors:
    """
    Every failure type raises its own clear exception.
    """

    def test_no_server_raises_connection_error(self, closed_port):
        """
        Nothing listens on the port, so the connection is refused.
        """
        client = AmmeterClient(closed_port, COMMAND)

        with pytest.raises(AmmeterConnectionError, match='Cannot communicate'):
            client.request_current()

    def test_original_error_is_kept_as_cause(self, closed_port):
        """
        The socket error is kept as the cause, so the traceback still shows what really happened.
        """
        client = AmmeterClient(closed_port, COMMAND)

        with pytest.raises(AmmeterConnectionError) as error_info:
            client.request_current()

        assert isinstance(error_info.value.__cause__, ConnectionRefusedError)

    def test_slow_server_raises_connection_error_after_timeout(self, fake_server):
        """
        A server that answers too late does not make the client wait forever.
        """
        server = fake_server(b'1.0', delay=1.0)
        client = AmmeterClient(server.port, COMMAND, timeout=0.2)

        start = time.perf_counter()
        with pytest.raises(AmmeterConnectionError):
            client.request_current()
        elapsed = time.perf_counter() - start

        # The client gave up after its timeout, long before the server would have answered.
        assert elapsed < 0.8

    def test_no_reply_raises_response_error(self, fake_server):
        """
        The server closes the connection without data, like an emulator that got a wrong command.
        """
        server = fake_server(None)

        with pytest.raises(AmmeterResponseError, match='No data received'):
            AmmeterClient(server.port, COMMAND).request_current()

    def test_text_reply_raises_invalid_reply_error(self, fake_server):
        """
        A reply that is not a number of raises an error that shows the reply.
        """
        server = fake_server(b'hello')

        with pytest.raises(AmmeterInvalidReplyError, match='hello'):
            AmmeterClient(server.port, COMMAND).request_current()

    @pytest.mark.parametrize('error_class', [
        AmmeterConnectionError,
        AmmeterResponseError,
        AmmeterInvalidReplyError,
    ])
    def test_all_errors_share_the_base_class(self, error_class):
        """
        Catching AmmeterError catches every ammeter failure, which the sampler relies on.
        """
        assert issubclass(error_class, AmmeterError)
