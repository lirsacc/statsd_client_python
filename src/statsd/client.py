import abc
import contextlib
import datetime
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
    TypeVar,
    Union,
)

from statsd.formats import DefaultSerializer, Serializer


TCallable = TypeVar("TCallable", bound=Callable[..., Any])

logger = logging.getLogger("statsd")


class BaseStatsdClient(abc.ABC):
    """
    Generic Statsd client interface.

    This class exposes the public interface and takes care of packet formatting
    as well as sampling. It does not actually send packets anywhere, which is
    left to concrete subclasses.

    .. warning::
        This class makes no assumption around the underlying implementation
        behaviour. Delivery guarantees, thread safety, robustness to error are
        all left to specific implementations.

    :param namespace: Optional prefix to add all metrics.

        If this is set to ``foo``, then all metrics will be prefixed with
        ``foo.``; so for instance sending out ``bar`` would actually be sent
        as ``foo.bar``.

    :param tags: Default tags applied to all metrics.

    :param sample_rate: Default sampling rate applied to all metrics.
        This should be between 0 and 1 inclusive, 1 meaning that all metrics
        will be forwarded and 0 that none will be forwarded.
        Defaults to 1.

    :param serializer: A serializer defining the wire format of the metrics.
        This allows supporting diverging server implementation such as how
        Telegraf and Dogstatsd handle tags. See :mod:`statsd.formats` for
        more details.
    """

    KNOWN_METRIC_TYPES = ("c", "g", "s", "ms", "h", "d")

    def __init__(
        self,
        *,
        namespace: Optional[str] = None,
        tags: Optional[Mapping[str, str]] = None,
        sample_rate: float = 1,
        serializer: Optional[Serializer] = None,
    ) -> None:
        if not (0 <= sample_rate <= 1):
            raise ValueError("sample_rate must be between 0 and 1.")

        self.namespace = namespace
        self.default_tags = tags or {}
        self.default_sample_rate = sample_rate
        self.serializer = (
            DefaultSerializer() if serializer is None else serializer
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
        """
        Send a metric to the underlying implementation.

        This method takes care sampling metrics and builds the actual packet
        that will be sent to the server; implementations are purely responsible
        for sending the packet and have nothing to do with the Statsd format.

        :param metric_name: Metric name. This will be namespaced if the client
            is namespace.

        :param metric_type: One of the supported Statsd metric types, counter
            ("c"), gauge ("g"), timing ("ms") and set ("s").

        :param value: etric value formatted according to the rules for the type.

        :param tags: A mapping of tag name to their value. This will be merged
            with the client's tags if relevant, overriding any tag already set.

        :param sample_rate: Sampling rate applied to this particular call.
            Should be between 0 and 1 inclusive, 1 meaning that all metrics
            will be forwarded and 0 that none will be forwarded. If left
            unspecified this will use the client's sample rate.
        """
        sample_rate = (
            sample_rate if sample_rate is not None else self.default_sample_rate
        )
        if not (0 <= sample_rate <= 1):
            raise ValueError("sample_rate must be between 0 and 1.")

        if sample_rate < 1 and random.random() > sample_rate:
            return

        self._emit_packet(
            self.serialize_metric(
                metric_name,
                metric_type,
                value,
                sample_rate=sample_rate,
                tags=tags,
            )
        )

    def serialize_metric(
        self,
        metric_name: str,
        metric_type: str,
        value: str,
        sample_rate: float,
        tags: Optional[Mapping[str, str]],
    ) -> str:
        if metric_type not in self.KNOWN_METRIC_TYPES:
            raise ValueError(f"Invalid metric type {metric_type}")

        return self.serializer.serialize(
            (
                # TODO: Is defaulting to ``.`` separator the right call here?
                # Alternative 1: Use a prefix that simply prepended
                # Alternative 2: Make the separator configurable
                # Alternative 3: Make this configurable through an override of
                #                some sort (`serialize_name` or similar.)
                f"{self.namespace}.{metric_name}"
                if self.namespace
                else metric_name
            ),
            metric_type,
            value,
            sample_rate=sample_rate,
            tags={**self.default_tags, **(tags or {})},
        )

    def increment(
        self,
        name: str,
        value: int = 1,
        *,
        tags: Optional[Mapping[str, str]] = None,
        sample_rate: Optional[float] = None,
    ) -> None:
        """
        Increment a counter by the specified value (defaults to 1).

        See :meth:`emit` for details on optional parameters.
        """
        self.emit(name, "c", str(value), tags=tags, sample_rate=sample_rate)

    def decrement(
        self,
        name: str,
        value: int = 1,
        *,
        tags: Optional[Mapping[str, str]] = None,
        sample_rate: Optional[float] = None,
    ) -> None:
        """
        Decrement a counter by the specified value (defaults to 1).

        See :meth:`emit` for details on optional parameters.
        """
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
        value: Union[int, float],
        *,
        is_update: bool = False,
        tags: Optional[Mapping[str, str]] = None,
        sample_rate: Optional[float] = None,
    ) -> None:
        """
        Update a gauge value.

        The ``is_update`` parameter can be used to control whether this sets the
        value of the gauge or sends a gauge delta packet (prepended with ``+``
        or ``-``).

        .. warning::
            Not all Statsd server implementations support Gauge deltas. Notably
            Datadog protocol does not (see:
            https://github.com/DataDog/dd-agent/issues/573 for more info).

        .. warning::
            Gauges can be integers or floats although floats may not be
            supported by all servers.

        See :meth:`emit` for details on other parameters.
        """
        if is_update:
            _value = f"{'+' if value >= 0 else ''}{value}"
        else:
            _value = str(value)

        with _Batcher(self, sample_rate=sample_rate) as batch:
            if value < 0 and not is_update:
                # WARN: This could be subject to race condition depending on the
                # underlying transport and buffering settings.
                batch.queue(name, "g", "0", tags=tags)
            batch.queue(name, "g", _value, tags=tags)

    def timing(
        self,
        name: str,
        value: Union[int, datetime.timedelta],
        *,
        tags: Optional[Mapping[str, str]] = None,
        sample_rate: Optional[float] = None,
    ) -> None:
        """
        Send a timing value.

        Timing usually are aggregated by the StatsD server receiving them.

        The ``value`` is expected to be in milliseconds.

        See :meth:`emit` for details on optional parameters.
        """
        # TODO: Some server implementation support higher resolution timers
        # using floats. We could support this with a flag.
        if isinstance(value, datetime.timedelta):
            value = int(1000 * value.total_seconds())

        self.emit(name, "ms", str(value), tags=tags, sample_rate=sample_rate)

    def timed(
        self,
        name: Optional[str] = None,
        *,
        tags: Optional[Mapping[str, str]] = None,
        sample_rate: Optional[float] = None,
        use_distribution: bool = False,
    ) -> Callable[[TCallable], TCallable]:
        """
        Decorator to record a function's execution time.

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

        def decorator(fn: TCallable) -> TCallable:
            # TODO: Should the fallback include the module? Class (for methods)?
            # or func.__name__
            metric_name = name or fn.__name__

            @functools.wraps(fn)
            def wrapped(*args, **kwargs):
                with self.timer(
                    metric_name,
                    tags=tags,
                    use_distribution=use_distribution,
                ):
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
        use_distribution: bool = False,
    ) -> Iterator[None]:
        """
        Context manager to measure the execution time of a block in milliseconds.

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
                self.distribution(name, duration_ms, tags=tags)
            else:
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

    def histogram(
        self,
        name: str,
        value: float,
        *,
        tags: Optional[Mapping[str, str]] = None,
        sample_rate: Optional[float] = None,
    ) -> None:
        """
        Send an histogram sample.

        Histograms, like timings are usually aggregated locally but the StatsD
        server receiving them.

        .. warning::
            This is not a standard metric type and is not supported by all
            StatsD backends.
        """
        self.emit(name, "h", str(value), tags=tags, sample_rate=sample_rate)

    def distribution(
        self,
        name: str,
        value: float,
        *,
        tags: Optional[Mapping[str, str]] = None,
        sample_rate: Optional[float] = None,
    ) -> None:
        """
        Send a distribution sample.

        Distributions are usually aggregated globally by a centralised service
        (e.g. Veneur, Datadog) and not locally by any intermediary StatsD
        server.

        .. warning::
            This is not a standard metric type and is not supported by all
            StatsD backends.
        """
        self.emit(name, "d", str(value), tags=tags, sample_rate=sample_rate)

    # Implementation specific methods.

    @abc.abstractmethod
    def _emit_packet(self, packet: str) -> None:
        """
        Send implementation.

        This method is responsible for actually sending the formatted packets
        and should be implemented by all subclasses.
        """
        raise NotImplementedError()


class _Batcher:
    def __init__(
        self,
        inner: BaseStatsdClient,
        sample_rate: Optional[float] = None,
    ) -> None:
        sample_rate = (
            sample_rate
            if sample_rate is not None
            else inner.default_sample_rate
        )
        if not (0 <= sample_rate <= 1):
            raise ValueError("sample_rate must be between 0 and 1.")

        self.sample_rate = sample_rate
        self.batch: List[str] = []
        self.inner = inner

    def flush(self):
        if self.sample_rate < 1 and random.random() > self.sample_rate:
            return

        for x in self.batch:
            self.inner._emit_packet(x)

        self.batch[:] = []

    def queue(
        self,
        metric_name: str,
        metric_type: str,
        value: str,
        *,
        tags: Optional[Mapping[str, str]] = None,
    ) -> None:
        self.batch.append(
            self.inner.serialize_metric(
                metric_name,
                metric_type,
                value,
                sample_rate=self.sample_rate,
                tags=tags,
            )
        )

    def __enter__(self) -> "_Batcher":
        return self

    def __exit__(self, *args: Any) -> None:
        self.flush()


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
        inner: Optional[BaseStatsdClient] = None,
        **kwargs: Any,
    ) -> None:
        r"""
        Initialize DebugStatsdClient.

        :param level: Log level to use, defaults to ``INFO``.

        :param logger: Logger instance to use, defaults to ``statsd``.

        :param inner: Wrapped client.

        :param \**kwargs: Extra arguments forwarded to :class:`BaseStatsdClient`.
        """  # noqa: W605
        super().__init__(**kwargs)
        self.level = level
        self.logger = logger
        self.inner = inner

    def _emit_packet(self, packet: str) -> None:
        self.logger.log(self.level, "> %s", packet)
        if self.inner:
            self.inner._emit_packet(packet)


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
    """  # noqa: W605

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
        self.buffer: List[bytes] = []
        self.buffer_size = 0

        self.closed = False

        self.host = host
        self.port = port
        self.sock: Optional[socket.socket] = None

    def _socket(self) -> socket.socket:
        """
        Lazily instantiate the socket, this should only happen once.
        """
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
        """
        If there is data in the buffer, send it and reset the buffer.
        """
        with self.lock:
            if not self.buffer:
                return

            self._send(b"\n".join(self.buffer))
            self.buffer[:] = []
            self.buffer_size = 0

    def _emit_packet(self, packet: str) -> None:
        """
        Handle metric packets, buffering and flusing the buffer accordingly.
        """
        with self.lock:
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
        """
        Actually send data.
        """
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
            logger.error("Unexpected error: %s", err, exc_info=True)

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
