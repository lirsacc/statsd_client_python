import errno
import logging
import socket
import time
from typing import Any, Generator
from unittest import mock

import pytest

from statsd import StatsdClient


@pytest.fixture
def receiver_socket() -> Generator[socket.socket, None, None]:
    sock = socket.socket(type=socket.SOCK_DGRAM)
    sock.bind(("", 0))
    sock.settimeout(0)
    try:
        yield sock
    finally:
        try:
            sock.shutdown(socket.SHUT_RDWR)
            sock.close()
        except OSError:
            pass


def _read_from_socket(sock: socket.socket) -> str:
    # TODO: Fix this. There's a case where the test code races the sockets and
    # by the time we call this, the socket has not received the packets.
    # Sleeping solves it for now, but it's not ideal.
    time.sleep(0.001)

    try:
        data = sock.recv(4096)
    except OSError as err:
        if err.errno == errno.EAGAIN:
            return ""
        raise
    else:
        return data.decode("ascii")


def test_no_buffering_sends_immediately(receiver_socket: socket.socket) -> None:
    host, port = receiver_socket.getsockname()
    client = StatsdClient(host=host, port=port, max_buffer_size=0)

    client.increment("foo", 1)
    assert _read_from_socket(receiver_socket) == "foo:1|c"
    assert _read_from_socket(receiver_socket) == ""

    client.increment("foo", 2)
    assert _read_from_socket(receiver_socket) == "foo:2|c"


def test_buffering(receiver_socket: socket.socket) -> None:
    host, port = receiver_socket.getsockname()
    client = StatsdClient(host=host, port=port, max_buffer_size=36)

    # None of these should lead to a send.
    client.increment("foo", 1)
    client.increment("foo", 2)
    client.increment("foo", 3)
    client.increment("foo", 4)

    assert _read_from_socket(receiver_socket) == ""

    # At this point we've gone over the buffer size, we should see a flush and
    # start a new buffer.
    client.increment("foo", 5)

    assert (
        _read_from_socket(receiver_socket)
        == "foo:1|c\nfoo:2|c\nfoo:3|c\nfoo:4|c"
    )
    assert _read_from_socket(receiver_socket) == ""

    # This should flush the remaining entry.
    client._close()

    assert _read_from_socket(receiver_socket) == "foo:5|c"


def test_broken_pipe(receiver_socket: socket.socket, caplog: Any) -> None:
    host, port = receiver_socket.getsockname()
    client = StatsdClient(host=host, port=port, max_buffer_size=0)

    with mock.patch("socket.socket.send", side_effect=[2]), caplog.at_level(
        logging.WARNING
    ):
        # Should not raise.
        client.increment("foo", 1)

    assert len(caplog.records) == 1
    assert "Broken pipe" in caplog.text


def test_socket_errors_are_logged_not_raised(
    receiver_socket: socket.socket, caplog: Any
) -> None:
    host, port = receiver_socket.getsockname()
    client = StatsdClient(host=host, port=port, max_buffer_size=0)

    with mock.patch(
        "socket.socket.send", side_effect=[socket.error("Broken socket")]
    ), caplog.at_level(logging.WARNING):
        # Should not raise.
        client.increment("foo", 1)

    assert len(caplog.records) == 1
    assert "Error sending packet" in caplog.text


def test_unexpected_exceptions_are_logged_not_raised(
    receiver_socket: socket.socket, caplog: Any
) -> None:
    host, port = receiver_socket.getsockname()
    client = StatsdClient(host=host, port=port, max_buffer_size=0)

    with mock.patch(
        "socket.socket.send", side_effect=[ValueError("Random error")]
    ), caplog.at_level(logging.ERROR):
        # Should not raise.
        client.increment("foo", 1)

    assert len(caplog.records) == 1
    assert "Traceback (most recent call last)" in caplog.text
    assert "ValueError: Random error" in caplog.text


def test_close_before_anything_happened(receiver_socket: socket.socket) -> None:
    host, port = receiver_socket.getsockname()
    client = StatsdClient(host=host, port=port, max_buffer_size=0)
    client._close()


def test_call_after_close_raises(
    receiver_socket: socket.socket, caplog: Any
) -> None:
    host, port = receiver_socket.getsockname()
    client = StatsdClient(host=host, port=port, max_buffer_size=0)
    client._close()

    with pytest.raises(RuntimeError):
        client.increment("foo", 1)
