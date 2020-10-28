import abc
from typing import Mapping


class Serializer(abc.ABC):
    """
    Metric line serializer.

    This class is used when sending packet to accomodate differing statsd
    immplementations. This is mostly used to handle the different ways tags are
    handled.

    Serializer implementations should also validate the validity of the metric
    being sent against the formats they supports.

    This library provides 3 different formats which cover most of the
    implementations I've come across so far:

    - :class:`~statsd.formats.DogstatsdSerializer` (default)
    - :class:`~statsd.formats.TelegrafSerializer`
    - :class:`~statsd.formats.GraphiteSerializer`
    """

    def serialize(
        self,
        metric_name: str,
        metric_type: str,
        value: str,
        sample_rate: float,
        tags: Mapping[str, str] = {},
    ) -> str:
        """
        Return a serialized packet to be sent to the Statsd server.
        """
        raise NotImplementedError()


class DogstatsdSerializer(Serializer):
    """
    Dogstatsd statsd format.

    Add support for serializing metrics following Datadog's `Dogstatsd format
    <https://docs.datadoghq.com/developers/dogstatsd/datagram_shell/>`_.

    This is the default format given it is fairly common, for example:

    - `Splunk <https://docs.splunk.com/Documentation/Splunk/8.1.0/Metrics/\
GetMetricsInStatsd>`_.
    - Etsy's Statsd supports it alongside the Graphite format.
    - It's the format used by `Vector <https://vector.dev/>`_.

    """

    def format_tags(self, tags: Mapping[str, str]) -> str:
        return "#%s" % ",".join(
            # Dogstatsd supports tag without value.
            "%s:%s" % (key, value) if value else key
            for key, value in tags.items()
        )

    def serialize(
        self,
        metric_name: str,
        metric_type: str,
        value: str,
        sample_rate: float,
        tags: Mapping[str, str] = {},
    ) -> str:
        return "%s:%s|%s%s%s" % (
            metric_name,
            value,
            metric_type,
            "|@%s" % sample_rate if sample_rate < 1 else "",
            self.format_tags(tags) if tags else "",
        )


class _AppendToNameSerializer(Serializer):
    separator: str = NotImplemented

    def serialize(
        self,
        metric_name: str,
        metric_type: str,
        value: str,
        sample_rate: float,
        tags: Mapping[str, str] = {},
    ) -> str:
        # Graphite and InfluxDB will refuse the metric if a tag has no value.
        missing_tag_values = [k for k, v in tags.items() if not v]
        if missing_tag_values:
            raise ValueError("Missing tag values: %r" % missing_tag_values)

        return "%s:%s|%s%s" % (
            self.separator.join(
                [
                    metric_name,
                    *("%s=%s" % (key, value) for key, value in tags.items()),
                ]
            ),
            value,
            metric_type,
            "|@%s" % sample_rate if sample_rate < 1 else "",
        )


class TelegrafSerializer(_AppendToNameSerializer):
    """
    Telegraf statsd format.

    Add support for serializing metrics following `Telegraf's format
    <https://github.com/influxdata/telegraf/blob/master/plugins/inputs/statsd/>`_.
    """

    separator = ","


class GraphiteSerializer(_AppendToNameSerializer):
    """
    Graphite statsd format.

    Add support for serializing metrics following `Graphites's format
    <https://graphite.readthedocs.io/en/latest/tags.html>`_.
    """

    separator = ";"


DefaultSerializer = DogstatsdSerializer
