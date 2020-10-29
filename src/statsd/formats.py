import abc
import re
from typing import Mapping


# Global exclusion based on a mix of what Graphite and Datadog support. Some
# implementation support unicode but I feel that's a rare enough case that its
# fair to drop them for now. Can always make it os it's controlled through a
# flag if required.
# This is applied to both key and value for simplicity.
INVALID_TAG_CHARACTERS_RE = re.compile(r"[^\w\-/\.]", flags=re.ASCII)


class Serializer(abc.ABC):
    """
    Metric line serializer.

    This class is used when sending packet to accomodate differing statsd
    immplementations. This is mostly used to handle the different ways tags are
    supported across implementations.

    Serializer implementations should also validate the metric and tags being
    sent against the formats they supports.

    This library provides 3 different formats which should cover most of the
    implementations I've come across so far:

    - :class:`~statsd.formats.DogstatsdSerializer` (default)
    - :class:`~statsd.formats.TelegrafSerializer`
    - :class:`~statsd.formats.GraphiteSerializer`

    .. note::
        This mechanism is primarily used to supported tags, but it technically
        covers the entire line protocol serialisation (except batching) and can
        be used to support different server implementations.
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

    Format:

    - The start of the packet follows the default statsd format.
    - Tags:

        - Are appended to the line, starting with ``|#``.
        - Individual tags are separated by a comma.
        - Name and value are separated by a colon.
        - Tags without value are supported.

    Example: ``my_metric:123456|ms|@0.4|#foo:1,bar,baz:some_value``

    This is the default format given it is fairly common, for example:

    - `Splunk <https://docs.splunk.com/Documentation/Splunk/8.1.0/Metrics/\
GetMetricsInStatsd>`_.
    - Etsy's Statsd supports it alongside the Graphite format.
    - It's the format used by `Vector <https://vector.dev/>`_.
    """

    def format_tags(self, tags: Mapping[str, str]) -> str:
        return "|#%s" % ",".join(
            # Dogstatsd supports tag without value.
            "%s:%s"
            % (
                re.sub(INVALID_TAG_CHARACTERS_RE, "-", key),
                re.sub(INVALID_TAG_CHARACTERS_RE, "-", value),
            )
            if value
            else key
            for key, value in tags.items()
            if key
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
                    *(
                        "%s=%s"
                        % (
                            re.sub(INVALID_TAG_CHARACTERS_RE, "-", key),
                            re.sub(INVALID_TAG_CHARACTERS_RE, "-", value),
                        )
                        for key, value in tags.items()
                        if key
                    ),
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

    Format:

    - Tags are added to the name section of the packet; trest of the packet
      follows the default statsd format.
    - Tags:

        - Are appended to the name, separated from the name by a comma.
        - Individual tags are separated by a comma.
        - Name and value are separated by an equal sign.
        - Tags without value are not supported.

    Example: ``my_metric,foo=1,bar=some_value:123456|ms|@0.4``
    """

    separator = ","


class GraphiteSerializer(_AppendToNameSerializer):
    """
    Graphite statsd format.

    Add support for serializing metrics following `Graphites's format
    <https://graphite.readthedocs.io/en/latest/tags.html>`_.

    Format:

    - Tags are added to the name section of the packet; trest of the packet
      follows the default statsd format.
    - Tags:

        - Are appended to the name, separated from the name by a semi-colon.
        - Individual tags are separated by a semi-colon.
        - Name and value are separated by an equal sign.
        - Tags without value are not supported.

    Example: ``my_metric;foo=1;bar=some_value:123456|ms|@0.4``
    """

    separator = ";"


#: Default serializer
DefaultSerializer = DogstatsdSerializer
