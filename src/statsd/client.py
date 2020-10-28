import abc
import contextlib
import errno
import functools
import logging
import random
import socket
import threading
import time
from typing import (
    Any,
    Callable,
    Iterator,
    List,
    Mapping,
    Optional,
    Type,
    TypeVar,
)

from statsd.formats import DefaultSerializer, Serializer


TCallable = TypeVar("TCallable", bound=Callable[..., Any])
TSerializer = TypeVar("TSerializer", bound=Type[Serializer])

logger = logging.getLogger("statsd")


class BaseStatsdClient(abc.ABC):
    """
    Generic Statsd client interface.
    """

    def __init__(
        self,
        *,
        namespace: Optional[str] = None,
        tags: Optional[Mapping[str, str]] = None,
        sample_rate: int = 1,
        serializer_cls: Optional[TSerializer] = None,
    ) -> None:
        """
        Initialize a Statsd client.
        """
        if not (0 <= sample_rate <= 1):
            raise ValueError("sample_rate must be between 0 and 1.")

        self.prefix = "%s." % namespace if namespace else ""
        self.default_tags = tags or {}
        self.default_sample_rate = sample_rate
        self.serializer = (
            DefaultSerializer() if serializer_cls is None else serializer_cls()
        )

    # Shared interface

    def emit(
        self,
        metric_name: str,
        metric_type: str,
        value: str,
        *,
        tags: Optional[Mapping[str, str]] = None,
        sample_rate: Optional[float] = None,
    ) -> None:
        sample_rate = (
            sample_rate if sample_rate is not None else self.default_sample_rate
        )

        if not (0 <= sample_rate <= 1):
            raise ValueError("sample_rate must be between 0 and 1.")

        if sample_rate < 1 and random.random() > sample_rate:
            return

        packet = self.serializer.serialize(
            "%s%s" % (self.prefix, metric_name),
            metric_type,
            value,
            sample_rate=sample_rate,
            tags={**self.default_tags, **(tags or {})},
        )

        self._emit_packet(packet)

    def increment(
        self,
        name: str,
        value: int = 1,
        *,
        tags: Optional[Mapping[str, str]] = None,
        sample_rate: Optional[float] = None,
    ) -> None:
        self.emit(name, "c", str(value), tags=tags, sample_rate=sample_rate)

    def decrement(
        self,
        name: str,
        value: int = 1,
        *,
        tags: Optional[Mapping[str, str]] = None,
        sample_rate: Optional[float] = None,
    ) -> None:
        self.emit(
            name,
            "c",
            str(-1 * value),
            tags=tags,
            sample_rate=sample_rate,
        )

    def gauge(
        self,
        name: str,
        value: int,
        *,
        is_update: bool = False,
        tags: Optional[Mapping[str, str]] = None,
        sample_rate: Optional[float] = None,
    ) -> None:
        if is_update:
            _value = "%s%s" % ("+" if value >= 0 else "", value)
        else:
            _value = str(value)
        self.emit(name, "g", _value, tags=tags, sample_rate=sample_rate)

    def timing(
        self,
        name: str,
        value: int,
        *,
        tags: Optional[Mapping[str, str]] = None,
        sample_rate: Optional[float] = None,
    ) -> None:
        self.emit(name, "ms", str(value), tags=tags, sample_rate=sample_rate)

    def timed(
        self,
        name: str,
        *,
        tags: Optional[Mapping[str, str]] = None,
        sample_rate: Optional[float] = None,
    ) -> Callable[[TCallable], TCallable]:
        def decorator(fn: TCallable) -> TCallable:
            @functools.wraps(fn)
            def wrapped(*args, **kwargs):
                with self.timer(name, tags=tags):
                    return fn(*args, **kwargs)

            return wrapped  # type: ignore

        return decorator

    @contextlib.contextmanager
    def timer(
        self,
        name: str,
        *,
        tags: Optional[Mapping[str, str]] = None,
        sample_rate: Optional[float] = None,
    ) -> Iterator[None]:
        start = time.perf_counter()
        try:
            yield
        finally:
            duration_ms = int(1000 * (time.perf_counter() - start))
            self.timing(name, duration_ms, tags=tags)

    def set(
        self,
        name: str,
        value: int,
        *,
        tags: Optional[Mapping[str, str]] = None,
        sample_rate: Optional[float] = None,
    ) -> None:
        self.emit(name, "s", str(value), tags=tags, sample_rate=sample_rate)

    # Implementation specific methods.

    @abc.abstractmethod
    def _emit_packet(self, packet: str) -> None:
        raise NotImplementedError()


class DebugStatsdClient(BaseStatsdClient):
    """
    Verbose client for development or debugging purposes.
    """

    def __init__(
        self,
        level: int = logging.INFO,
        logger: logging.Logger = logger,
        inner: Optional[BaseStatsdClient] = None,
    ) -> None:
        super().__init__()
        self.level = level
        self.logger = logger
        self.inner = inner

    def _emit_packet(self, packet: str) -> None:
        self.logger.log(self.level, "> %s", packet)
        if self.inner:
            self.inner._emit_packet(packet)


class UDPStatsdClient(BaseStatsdClient):
    """
    UDP Cliemt which should work against most Statsd server implementations.
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
        max_buffer_size: Optional[int] = DEFAULT_MAX_BUFFER_SIZE,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)

        self.lock = threading.RLock()
        self.max_buffer_size = max_buffer_size
        self.buffer: List[bytes] = []
        self.buffer_size = 0

        self.closed = False

        self.host = host
        self.port = port
        self.sock: Optional[socket.socket] = None

    # Lazy initialisation of the socket.
    def _socket(self) -> socket.socket:
        if self.sock is None:
            with self.lock:
                family, _, _, _, addr = socket.getaddrinfo(
                    self.host, self.port, socket.AF_INET, socket.SOCK_DGRAM
                )[0]

                self.sock = socket.socket(family, socket.SOCK_DGRAM)
                self.sock.settimeout(0)
                self.sock.connect(addr)
                return self.sock
        else:
            return self.sock

    def _flush_buffer(self) -> None:
        if not self.buffer:
            return

        self._send(b"\n".join(self.buffer))
        self.buffer[:] = []
        self.buffer_size = 0

    def _emit_packet(self, packet: str) -> None:
        with self.lock:
            if self.closed:
                raise RuntimeError("Can't emit metric after closing socket.")

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
        try:
            sent = self._socket().send(data)
            if sent < len(data):
                raise socket.error(errno.EPIPE, "Broken pipe")
        # TODO: Can we handle error conditions better?
        # We should not break callsites when metrics fail to send so log instead.
        except socket.error as err:
            logger.warning("Error sending packet: %s", err)
        except Exception as err:
            logger.error("Unexpected error: %s", err, exc_info=True)

    def close(self) -> None:
        with self.lock:
            self._flush_buffer()
            try:
                if self.sock:
                    self.sock.shutdown(socket.SHUT_RDWR)
                    self.sock.close()
            except socket.error:
                pass
            finally:
                self.closed = True

    def __del__(self) -> None:
        self.close()


# Default is the standard UDP implementation.
StatsdClient = UDPStatsdClient
