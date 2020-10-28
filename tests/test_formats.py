from typing import Mapping, Optional, Tuple

import pytest

from statsd.formats import (
    DogstatsdSerializer,
    GraphiteSerializer,
    TelegrafSerializer,
)


SerializeInput = Tuple[str, str, str, float, Optional[Mapping[str, str]]]


CASE_SIMPLE: SerializeInput = ("my_metric", "c", "1", 1, {})
CASE_TAG_AND_RATE: SerializeInput = (
    "my_metric",
    "ms",
    "123456",
    0.4,
    {"foo": "1", "bar": "some_value"},
)
CASE_TAG_NO_RATE: SerializeInput = (
    "my_metric",
    "ms",
    "123456",
    1,
    {"foo": "1", "bar": "some_value"},
)
CASE_EMPTY_TAG: SerializeInput = (
    "my_metric",
    "ms",
    "123456",
    1,
    {"foo": "1", "bar": "", "baz": "some_value"},
)


@pytest.mark.parametrize(
    "params,expected",
    [
        (CASE_SIMPLE, "my_metric:1|c"),
        (CASE_TAG_AND_RATE, "my_metric:123456|ms|@0.4#foo:1,bar:some_value"),
        (CASE_TAG_NO_RATE, "my_metric:123456|ms#foo:1,bar:some_value"),
        (CASE_EMPTY_TAG, "my_metric:123456|ms#foo:1,bar,baz:some_value"),
    ],
)
def test_dogstatsd_format_ok(params: SerializeInput, expected: str) -> None:
    assert DogstatsdSerializer().serialize(*params) == expected


@pytest.mark.parametrize(
    "params,expected",
    [
        (CASE_SIMPLE, "my_metric:1|c"),
        (CASE_TAG_AND_RATE, "my_metric,foo=1,bar=some_value:123456|ms|@0.4"),
        (CASE_TAG_NO_RATE, "my_metric,foo=1,bar=some_value:123456|ms"),
    ],
)
def test_telegraf_format_ok(params: SerializeInput, expected: str) -> None:
    assert TelegrafSerializer().serialize(*params) == expected


@pytest.mark.parametrize("params", [CASE_EMPTY_TAG])
def test_telegraf_format_invalid(params: SerializeInput) -> None:
    with pytest.raises(ValueError):
        TelegrafSerializer().serialize(*params)


@pytest.mark.parametrize(
    "params,expected",
    [
        (CASE_SIMPLE, "my_metric:1|c"),
        (CASE_TAG_AND_RATE, "my_metric;foo=1;bar=some_value:123456|ms|@0.4"),
        (CASE_TAG_NO_RATE, "my_metric;foo=1;bar=some_value:123456|ms"),
    ],
)
def test_graphite_format_ok(params: SerializeInput, expected: str) -> None:
    assert GraphiteSerializer().serialize(*params) == expected


@pytest.mark.parametrize("params", [CASE_EMPTY_TAG])
def test_graphite_format_invalid(params: SerializeInput) -> None:
    with pytest.raises(ValueError):
        GraphiteSerializer().serialize(*params)
