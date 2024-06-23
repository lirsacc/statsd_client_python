from __future__ import annotations

import abc
import datetime
import logging
import random
from typing import Generic, Literal, Mapping, NamedTuple, TypeVar
from typing_extensions import ParamSpec

from statsd.exceptions import InvalidMetricType, InvalidSampleRate
from statsd.formats import DefaultSerializer, Serializer


P = ParamSpec("P")
T = TypeVar("T")


logger = logging.getLogger("statsd")


class Sample(NamedTuple):
    """
    Container for a metric sample.

    :param metric_name: Metric name. This will be namespaced if the client
        is namespace.

    :param metric_type: One of the supported Statsd metric types, counter
        ("c"), gauge ("g"), timing ("ms") and set ("s"), histogram ("h") or
        distribution ("d").

    :param value: Metric value formatted according to the rules for the type.

    :param tags: A mapping of tag name to their value. This will be merged
        with the client's tags if relevant, overriding any tag already set.
    """

    metric_name: str
    metric_type: Literal["c", "g", "s", "ms", "h", "d"]
    value: str
    tags: Mapping[str, str] | None = None


class AbstractStatsdClient(abc.ABC, Generic[T]):
    """
    Abstract Statsd client interface.

    This class exists to share implementation details between the async and sync
    base classes. For most use cases you should not be subclassing this
    directly; prefer ``BaseStatsdClient`` and ``BaseAsyncStatsdClient`` drop the
    generic type parameter.
    """

    KNOWN_METRIC_TYPES = ("c", "g", "s", "ms", "h", "d")

    def __init__(
        self,
        *,
        namespace: str | None = None,
        tags: Mapping[str, str] | None = None,
        sample_rate: float = 1,
        serializer: Serializer | None = None,
    ) -> None:
        """
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
        if not (0 <= sample_rate <= 1):
            raise InvalidSampleRate(sample_rate)

        self.namespace = namespace
        self.default_tags = tags or {}
        self.default_sample_rate = sample_rate
        self.serializer = (
            DefaultSerializer() if serializer is None else serializer
        )

    def _serialize(
        self,
        sample: Sample,
        sample_rate: float,
    ) -> str:
        if sample.metric_type not in self.KNOWN_METRIC_TYPES:
            raise InvalidMetricType(sample.metric_type)

        return self.serializer.serialize(
            (
                # TODO: Is defaulting to ``.`` separator the right call here?
                # Alternative 1: Use a prefix that simply prepended
                # Alternative 2: Make the separator configurable
                # Alternative 3: Make this configurable through an override of
                #                some sort (`serialize_name` or similar.)
                f"{self.namespace}.{sample.metric_name}"
                if self.namespace
                else sample.metric_name
            ),
            sample.metric_type,
            sample.value,
            sample_rate=sample_rate,
            tags={**self.default_tags, **(sample.tags or {})},
        )

    # Shared interface

    def emit(self, *samples: Sample, sample_rate: float | None = None) -> T:
        """
        Send samples to the underlying implementation.

        This method takes care of making any sampling decision and building the
        actual packets that will be sent to the server through :meth:`_emit`.
        which is purely responsible for sending the packet.

        This may modify the samples in various ways:

        - The metric name will be namespaced if the client is namespaced.
        - The tags will be merged with the client's tags if relevant but the
          sample tags have precedence.

        .. note::
            Calling this method with multiple samples will result in the sampling
            decision being applied to all of them as a whole.

        :param samples: List of samples to send.

        :param sample_rate: Sampling rate applied to this particular call.
            Should be between 0 and 1 inclusive, 1 meaning that all metrics
            will be forwarded and 0 that none will be forwarded. If left
            unspecified this will use the client's sample rate.
        """
        sample_rate = (
            sample_rate if sample_rate is not None else self.default_sample_rate
        )
        if not (0 <= sample_rate <= 1):
            raise InvalidSampleRate(sample_rate)

        filtered_out = sample_rate < 1 and random.random() > sample_rate

        if not filtered_out:
            return self._emit([
                self._serialize(x, sample_rate=sample_rate) for x in samples
            ])
        else:
            # WARN: This is weird.
            return self._emit([])

    def increment(
        self,
        name: str,
        value: int = 1,
        *,
        tags: Mapping[str, str] | None = None,
        sample_rate: float | None = None,
    ) -> T:
        """
        Increment a counter by the specified value (defaults to 1).

        :param metric_name: Metric name.

        :param value: Increment step.

        :param tags: A mapping of tag name to their value.
        """
        return self.emit(
            Sample(name, "c", str(value), tags=tags),
            sample_rate=sample_rate,
        )

    def decrement(
        self,
        name: str,
        value: int = 1,
        *,
        tags: Mapping[str, str] | None = None,
        sample_rate: float | None = None,
    ) -> T:
        """
        Decrement a counter by the specified value (defaults to 1).

        :param metric_name: Metric name.

        :param value: Decrement step.

        :param tags: A mapping of tag name to their value.
        """
        return self.emit(
            Sample(name, "c", str(-1 * value), tags=tags),
            sample_rate=sample_rate,
        )

    def gauge(
        self,
        name: str,
        value: int | float,
        *,
        is_update: bool = False,
        tags: Mapping[str, str] | None = None,
        sample_rate: float | None = None,
    ) -> T:
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

        :param metric_name: Metric name.

        :param value: The updated gauge value.

        :param tags: A mapping of tag name to their value.
        """
        if is_update:
            _value = f"{'+' if value >= 0 else ''}{value}"
        else:
            _value = str(value)

        samples = []
        if value < 0 and not is_update:
            samples.append(Sample(name, "g", "0", tags=tags))
        samples.append(Sample(name, "g", _value, tags=tags))

        return self.emit(*samples, sample_rate=sample_rate)

    def timing(
        self,
        name: str,
        value: int | datetime.timedelta,
        *,
        tags: Mapping[str, str] | None = None,
        sample_rate: float | None = None,
    ) -> T:
        """
        Send a timing value.

        Timing usually are aggregated by the StatsD server receiving them.

        :param metric_name: Metric name.

        :param value: Timing value. Expected to be in milliseconds.

        :param tags: A mapping of tag name to their value.
        """
        # TODO: Some server implementation support higher resolution timers
        # using floats. We could support this with a flag.
        if isinstance(value, datetime.timedelta):
            value = int(1000 * value.total_seconds())

        return self.emit(
            Sample(name, "ms", str(value), tags=tags),
            sample_rate=sample_rate,
        )

    def set(
        self,
        name: str,
        value: int,
        *,
        tags: Mapping[str, str] | None = None,
        sample_rate: float | None = None,
    ) -> T:
        """
        Update a set counter.

        :param metric_name: Metric name.

        :param value: The number of occurences.

        :param tags: A mapping of tag name to their value.
        """
        return self.emit(
            Sample(name, "s", str(value), tags=tags),
            sample_rate=sample_rate,
        )

    def histogram(
        self,
        name: str,
        value: float,
        *,
        tags: Mapping[str, str] | None = None,
        sample_rate: float | None = None,
    ) -> T:
        """
        Send an histogram sample.

        Histograms, like timings are usually aggregated locally but the StatsD
        server receiving them.

        .. warning::
            This is not a standard metric type and is not supported by all
            StatsD backends.

        :param metric_name: Metric name.

        :param value: The recorded value.

        :param tags: A mapping of tag name to their value.
        """
        return self.emit(
            Sample(name, "h", str(value), tags=tags),
            sample_rate=sample_rate,
        )

    def distribution(
        self,
        name: str,
        value: float,
        *,
        tags: Mapping[str, str] | None = None,
        sample_rate: float | None = None,
    ) -> T:
        """
        Send a distribution sample.

        Distributions are usually aggregated globally by a centralised service
        (e.g. Veneur, Datadog) and not locally by any intermediary StatsD
        server.

        .. warning::
            This is not a standard metric type and is not supported by all
            StatsD backends.

        :param metric_name: Metric name.

        :param value: The recorded value.

        :param tags: A mapping of tag name to their value.
        """
        return self.emit(
            Sample(name, "d", str(value), tags=tags),
            sample_rate=sample_rate,
        )

    # Implementation specific methods.

    @abc.abstractmethod
    def _emit(self, packets: list[str]) -> T:
        """
        Send implementation.

        This method is responsible for actually sending the formatted packets
        and should be implemented by all subclasses.

        It may batch or buffer packets but should not modify them in any way. It
        should be agnostic to the Statsd format.
        """
        raise NotImplementedError()
