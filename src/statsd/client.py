from __future__ import annotations

import abc
import contextlib
import errno
import functools
import logging
import socket
import threading
import time
from typing import Any, Callable, Iterator, Mapping, TypeVar
from typing_extensions import ParamSpec

from statsd.base import AbstractStatsdClient


P = ParamSpec("P")
T = TypeVar("T")

logger = logging.getLogger("statsd")


class BaseStatsdClient(AbstractStatsdClient[None]):
    """
    Base client.

    This class exposes the public interface and takes care of packet formatting
    as well as sampling. It does not actually send packets anywhere, which is
    left to concrete subclasses implementing :meth:`_emit`.

    .. warning::
        This class makes no assumption around the underlying implementation
        behaviour. Delivery guarantees, thread safety, robustness to error are
        all left to specific implementations.
    """

    @abc.abstractmethod
    def _emit(self, packets: list[str]) -> None:
        """
        Send implementation.

        This method is responsible for actually sending the formatted packets
        and should be implemented by all subclasses.

        It may batch or buffer packets but should not modify them in any way. It
        should be agnostic to the Statsd format.
        """
        raise NotImplementedError()

    def timed(
        self,
        name: str | None = None,
        *,
        tags: Mapping[str, str] | None = None,
        sample_rate: float | None = None,
        use_distribution: bool = False,
    ) -> Callable[[Callable[P, T]], Callable[P, T]]:
        """
        Wrap a function to record its execution time.

        This just wraps the function call with a :meth:`timer` context manager.

        If a name is not provided, the function name will be used.

        Passing ``use_distribution=True`` will report the value as a globally
        aggregated :meth:`distribution` metric instead of a :meth:`timing`
        metric.

        >>> client = StatsdClient()
        >>> @client.timed()
        ... def do_something():
        ...     pass
        """

        def decorator(fn: Callable[P, T]) -> Callable[P, T]:
            # TODO: Should the fallback include the module? Class (for methods)?
            # or func.__name__
            metric_name = name or fn.__name__

            @functools.wraps(fn)
            def wrapped(*args: P.args, **kwargs: P.kwargs) -> T:
                with self.timer(
                    metric_name,
                    tags=tags,
                    use_distribution=use_distribution,
                    sample_rate=sample_rate,
                ):
                    return fn(*args, **kwargs)

            return wrapped

        return decorator

    @contextlib.contextmanager
    def timer(
        self,
        name: str,
        *,
        tags: Mapping[str, str] | None = None,
        sample_rate: float | None = None,
        use_distribution: bool = False,
    ) -> Iterator[None]:
        """
        Context manager to measure the execution time of a block.

        Passing ``use_distribution=True`` will report the value as a globally
        aggregated :meth:`distribution` metric instead of a :meth:`timing`
        metric.

        >>> client = StatsdClient()
        >>> with client.timer("download_duration"):
        ...     pass
        """
        start = time.perf_counter()
        try:
            yield
        finally:
            duration_ms = int(1000 * (time.perf_counter() - start))
            if use_distribution:
                self.distribution(
                    name,
                    duration_ms,
                    tags=tags,
                    sample_rate=sample_rate,
                )
            else:
                self.timing(
                    name,
                    duration_ms,
                    tags=tags,
                    sample_rate=sample_rate,
                )


class DebugStatsdClient(BaseStatsdClient):
    """
    Verbose client for development or debugging purposes.

    All Statsd packets will be logged and optionally forwarded to a wrapped
    client.
    """

    def __init__(
        self,
        level: int = logging.INFO,
        logger: logging.Logger = logger,
        inner: BaseStatsdClient | None = None,
        **kwargs: Any,
    ) -> None:
        r"""
        Initialize DebugStatsdClient.

        :param level: Log level to use, defaults to ``INFO``.

        :param logger: Logger instance to use, defaults to ``statsd``.

        :param inner: Wrapped client.

        :param \**kwargs: Extra arguments forwarded to :class:`BaseStatsdClient`.
        """
        super().__init__(**kwargs)
        self.level = level
        self.logger = logger
        self.inner = inner

    def _emit(self, packets: list[str]) -> None:
        for packet in packets:
            self.logger.log(self.level, "> %s", packet)
        if self.inner:
            self.inner._emit(packets)


class UDPStatsdClient(BaseStatsdClient):
    r"""
    UDP Client implementation.

    This client should be thread safe.

    :param host: Hostname for the Statsd server, defaults to localhost.

    :param port: Port for the statsd server, defaults to 8125.

    :param max_buffer_size: The maximum amount of data to buffer before sending
        to the Statsd server.

        This is an optimisation parameter; to avoid
        sending too many individual packets over the network. You should keep
        this in a range that your network MTU can handle.

        Set this to `0` to disable buffering.

    :param \**kwargs: Extra arguments forwarded to :class:`BaseStatsdClient`.
    """

    # Standard default for Statsd.
    DEFAULT_HOST = "localhost"
    DEFAULT_PORT = 8125

    # Default taken from Statsd documentation as a good value for most intranets
    # setups. Should be lower if the remote is going to be accessed over the
    # internet.
    DEFAULT_MAX_BUFFER_SIZE = 1432

    def __init__(
        self,
        *,
        host: str = DEFAULT_HOST,
        port: int = DEFAULT_PORT,
        max_buffer_size: int = DEFAULT_MAX_BUFFER_SIZE,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)

        self.lock = threading.RLock()
        self.max_buffer_size = max(max_buffer_size, 0)
        self.buffer: list[bytes] = []
        self.buffer_size = 0

        self.closed = False

        self.host = host
        self.port = port
        self.sock: socket.socket | None = None

    def _emit(self, packets: list[str]) -> None:
        with self.lock:
            for x in packets:
                self._emit_packet(x)

    def _socket(self) -> socket.socket:
        """Lazily instantiate the socket, this should only happen once."""
        if self.sock is None:
            with self.lock:
                family, _, _, _, addr = socket.getaddrinfo(
                    self.host,
                    self.port,
                    socket.AF_INET,
                    socket.SOCK_DGRAM,
                )[0]

                self.sock = socket.socket(family, socket.SOCK_DGRAM)
                self.sock.settimeout(0)
                self.sock.connect(addr)
                return self.sock
        else:
            return self.sock

    def _flush_buffer(self) -> None:
        """If there is data in the buffer, send it and reset the buffer."""
        with self.lock:
            if not self.buffer:
                return

            self._send(b"\n".join(self.buffer))
            self.buffer[:] = []
            self.buffer_size = 0

    def _emit_packet(self, packet: str) -> None:
        """Handle metric packets, buffering and flusing the buffer accordingly."""
        msg = packet.encode("ascii")

        # Buffering disabled, send immediately.
        if not self.max_buffer_size:
            return self._send(msg)

        msg_size = len(msg)

        would_overflow = (
            self.buffer_size + len(self.buffer) + msg_size
            > self.max_buffer_size
        )

        if would_overflow:
            self._flush_buffer()

        self.buffer.append(msg)
        self.buffer_size += msg_size

    def _send(self, data: bytes) -> None:
        """Actually send data."""
        # No lock this is only called from locked region. No guarantees if this
        # is called manually.
        if self.closed:
            raise RuntimeError("Can't emit metric after closing socket.")
        try:
            sent = self._socket().send(data)
            if sent < len(data):
                raise OSError(errno.EPIPE, "Broken pipe")
        # We should not break callsites when metrics fail to send so log instead.
        # TODO: Can we handle error conditions better?
        # TODO: Should this be configurable?
        except OSError as err:
            logger.warning("Error sending packet: %s", err)
        except Exception as err:
            logger.exception("Unexpected error: %s", err)

    def _close(self) -> None:
        """
        Close the underlying socket and refuse any new attempt to send packets.

        This will first flush the current buffer if there is data left to send.
        """
        with self.lock:
            self._flush_buffer()
            try:
                if self.sock:
                    self.sock.shutdown(socket.SHUT_RDWR)
                    self.sock.close()
            except OSError:
                pass
            finally:
                self.closed = True

    def __del__(self) -> None:
        self._close()


#: Default client. This should work with most statsd servers implementations.
StatsdClient = UDPStatsdClient
