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
CASE_EMPTY_VALUE: SerializeInput = (
    "my_metric",
    "ms",
    "123456",
    1,
    {"foo": "1", "bar": "", "baz": "some_value"},
)
CASE_INVALID_CHARS = SerializeInput = (
    "my_metric",
    "ms",
    "123456",
    1,
    {"foo": "*.:=1foo"},
)
CASE_EMPTY_KEY = SerializeInput = (
    "my_metric",
    "ms",
    "123456",
    1,
    {"foo": "1", "": "some_value"},
)


@pytest.mark.parametrize(
    "params,expected",
    [
        (CASE_SIMPLE, "my_metric:1|c"),
        (CASE_TAG_AND_RATE, "my_metric:123456|ms|@0.4|#foo:1,bar:some_value"),
        (CASE_TAG_NO_RATE, "my_metric:123456|ms|#foo:1,bar:some_value"),
        (CASE_EMPTY_VALUE, "my_metric:123456|ms|#foo:1,bar,baz:some_value"),
        (CASE_INVALID_CHARS, "my_metric:123456|ms|#foo:-.--1foo"),
        (CASE_EMPTY_KEY, "my_metric:123456|ms|#foo:1"),
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
        (CASE_INVALID_CHARS, "my_metric,foo=-.--1foo:123456|ms"),
        (CASE_EMPTY_KEY, "my_metric,foo=1:123456|ms"),
    ],
)
def test_telegraf_format_ok(params: SerializeInput, expected: str) -> None:
    assert TelegrafSerializer().serialize(*params) == expected


@pytest.mark.parametrize("params", [CASE_EMPTY_VALUE])
def test_telegraf_format_invalid(params: SerializeInput) -> None:
    with pytest.raises(ValueError):
        TelegrafSerializer().serialize(*params)


@pytest.mark.parametrize(
    "params,expected",
    [
        (CASE_SIMPLE, "my_metric:1|c"),
        (CASE_TAG_AND_RATE, "my_metric;foo=1;bar=some_value:123456|ms|@0.4"),
        (CASE_TAG_NO_RATE, "my_metric;foo=1;bar=some_value:123456|ms"),
        (CASE_INVALID_CHARS, "my_metric;foo=-.--1foo:123456|ms"),
        (CASE_EMPTY_KEY, "my_metric;foo=1:123456|ms"),
    ],
)
def test_graphite_format_ok(params: SerializeInput, expected: str) -> None:
    assert GraphiteSerializer().serialize(*params) == expected


@pytest.mark.parametrize("params", [CASE_EMPTY_VALUE])
def test_graphite_format_invalid(params: SerializeInput) -> None:
    with pytest.raises(ValueError):
        GraphiteSerializer().serialize(*params)
