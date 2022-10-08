import datetime
import logging
from typing import Any, Dict, List, Tuple, Union
from unittest import mock

import pytest

from statsd import BaseStatsdClient, DebugStatsdClient


class MockClient(BaseStatsdClient):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.mock = mock.Mock()

    def _emit_packet(self, packet: str) -> None:
        self.mock(packet)


def _assert_calls(fn, expected):
    if isinstance(expected, list):
        assert len(fn.call_args_list) == len(expected)
        assert fn.call_args_list == [mock.call(x) for x in expected]
    else:
        fn.assert_called_once_with(expected)


def assert_emits(
    client: MockClient,
    method: str,
    args: Tuple[Any, ...],
    kwargs: Dict[str, Any],
    expected: Union[List[str], str],
) -> None:
    client.mock.reset_mock()
    getattr(client, method)(*args, **kwargs)
    _assert_calls(client.mock, expected)


def assert_does_not_emit(
    client: MockClient,
    method: str,
    args: Tuple[Any, ...],
    kwargs: Dict[str, Any],
) -> None:
    client.mock.reset_mock()
    getattr(client, method)(*args, **kwargs)
    client.mock.assert_not_called()


SIMPLE_TEST_CASES: List[
    Tuple[str, Tuple[Any, ...], Dict[str, Any], Union[List[str], str]]
] = [
    ("increment", ("foo",), {}, "foo:1|c"),
    ("increment", ("foo", 10), {}, "foo:10|c"),
    ("increment", ("foo", -2), {}, "foo:-2|c"),
    ("decrement", ("foo",), {}, "foo:-1|c"),
    ("decrement", ("foo", 10), {}, "foo:-10|c"),
    ("decrement", ("foo", -2), {}, "foo:2|c"),
    ("gauge", ("foo", 42), {}, "foo:42|g"),
    ("gauge", ("foo", 1.5), {}, "foo:1.5|g"),
    ("gauge", ("foo", 256_128), {}, "foo:256128|g"),
    ("gauge", ("foo", -512), {}, ["foo:0|g", "foo:-512|g"]),
    ("gauge", ("foo", -1.5), {}, ["foo:0|g", "foo:-1.5|g"]),
    ("gauge", ("foo", 10), {"is_update": True}, "foo:+10|g"),
    ("gauge", ("foo", -10), {"is_update": True}, "foo:-10|g"),
    ("gauge", ("foo", 1.5), {"is_update": True}, "foo:+1.5|g"),
    ("gauge", ("foo", -1.5), {"is_update": True}, "foo:-1.5|g"),
    ("set", ("foo", 42), {}, "foo:42|s"),
    ("timing", ("foo", 1234), {}, "foo:1234|ms"),
    ("timing", ("foo", datetime.timedelta(minutes=17)), {}, "foo:1020000|ms"),
    ("histogram", ("foo", 256.128), {}, "foo:256.128|h"),
    ("distribution", ("foo", 256.128), {}, "foo:256.128|d"),
]


@pytest.mark.parametrize("method,args,kwargs,expected", SIMPLE_TEST_CASES)
def test_basic_metrics(
    method: str, args: Tuple[Any, ...], kwargs: Dict[str, Any], expected: str
) -> None:
    assert_emits(MockClient(), method, args, kwargs, expected)


@pytest.mark.parametrize("value", [-1, 100, 1.1])
def test_invalid_sample_rate(value):
    client = MockClient()

    with pytest.raises(ValueError):
        client.increment("foo", sample_rate=value)

    with pytest.raises(ValueError):
        MockClient(sample_rate=value)


def test_sample_rate_out():
    client = MockClient()
    with mock.patch("random.random", side_effect=lambda: 0.75):
        assert_does_not_emit(
            client, "increment", ("foo", 5), {"sample_rate": 0.5}
        )


def test_sample_rate_in():
    client = MockClient()
    with mock.patch("random.random", side_effect=lambda: 0.25):
        assert_emits(
            client,
            "increment",
            ("foo", 5),
            {"sample_rate": 0.5},
            "foo:5|c|@0.5",
        )


def test_validates_invalid_metric_type():
    client = MockClient()
    with pytest.raises(ValueError):
        client.emit("foo", "p", 54)


def test_default_sample_rate_out():
    client = MockClient(sample_rate=0.5)
    with mock.patch("random.random", side_effect=lambda: 0.75):
        assert_does_not_emit(client, "increment", ("foo", 5), {})


def test_default_sample_rate_in():
    client = MockClient(sample_rate=0.5)
    with mock.patch("random.random", side_effect=lambda: 0.25):
        assert_emits(
            client,
            "increment",
            ("foo", 5),
            {},
            "foo:5|c|@0.5",
        )


def test_batched_messages_are_sampled_as_one_in():
    client = MockClient(sample_rate=0.5)
    with mock.patch("random.random", side_effect=lambda: 0.25):
        assert_emits(
            client,
            "gauge",
            ("foo", -5),
            {},
            [
                "foo:0|g|@0.5",
                "foo:-5|g|@0.5",
            ],
        )


def test_batched_messages_are_sampled_as_one_out():
    client = MockClient(sample_rate=0.5)
    with mock.patch("random.random", side_effect=lambda: 0.75):
        assert_does_not_emit(
            client,
            "gauge",
            ("foo", -5),
            {},
        )


@pytest.mark.parametrize(
    "method,args,kwargs,expected",
    [
        ("increment", ("foo",), {}, "foo:1|c|#foo:1,bar:value"),
        (
            "gauge",
            ("foo", -10),
            {},
            ["foo:0|g|#foo:1,bar:value", "foo:-10|g|#foo:1,bar:value"],
        ),
    ],
)
def test_basic_with_tags(
    method: str, args: Tuple[Any, ...], kwargs: Dict[str, Any], expected: str
) -> None:
    tags = {"foo": "1", "bar": "value"}
    assert_emits(MockClient(), method, args, {**kwargs, "tags": tags}, expected)


@pytest.mark.parametrize(
    "method,args,kwargs,expected",
    [
        ("increment", ("foo",), {}, "foo:1|c|#foo:1,bar:value"),
        (
            "gauge",
            ("foo", -10),
            {},
            ["foo:0|g|#foo:1,bar:value", "foo:-10|g|#foo:1,bar:value"],
        ),
    ],
)
def test_default_tags(
    method: str, args: Tuple[Any, ...], kwargs: Dict[str, Any], expected: str
) -> None:
    tags = {"foo": "1", "bar": "value"}
    assert_emits(MockClient(tags=tags), method, args, {**kwargs}, expected)


def test_metric_tag_overrides_default_tags():
    client = MockClient(tags={"foo": "1", "bar": "value"})
    assert_emits(
        client,
        "increment",
        ("foo",),
        {"tags": {"foo": "2", "baz": "other_value"}},
        "foo:1|c|#foo:2,bar:value,baz:other_value",
    )


def test_timed_decorator():
    client = MockClient()

    @client.timed("foo", tags={"foo": "1"})
    def fn():
        pass

    with mock.patch(
        "time.perf_counter", side_effect=[7.886838544, 20.181117592]
    ):
        fn()

    client.mock.assert_called_once_with("foo:12294|ms|#foo:1")


def test_timed_decorator_use_distribution():
    client = MockClient()

    @client.timed("foo", tags={"foo": "1"}, use_distribution=True)
    def fn():
        pass

    with mock.patch(
        "time.perf_counter", side_effect=[7.886838544, 20.181117592]
    ):
        fn()

    client.mock.assert_called_once_with("foo:12294|d|#foo:1")


@pytest.mark.parametrize("method,args,kwargs,expected", SIMPLE_TEST_CASES)
def test_debug_client_no_inner(
    method: str,
    args: Tuple[Any, ...],
    kwargs: Dict[str, Any],
    expected: Union[List[str], str],
    caplog: Any,
) -> None:
    client = DebugStatsdClient()
    with caplog.at_level(logging.INFO, logger="statsd"):
        getattr(client, method)(*args, **kwargs)

    if isinstance(expected, list):
        assert len(caplog.records) == len(expected)
        for x in expected:
            assert x in caplog.text
    else:
        assert len(caplog.records) == 1
        assert expected in caplog.text


@pytest.mark.parametrize("method,args,kwargs,expected", SIMPLE_TEST_CASES)
def test_debug_client(
    method: str,
    args: Tuple[Any, ...],
    kwargs: Dict[str, Any],
    expected: str,
) -> None:
    mock_inner = mock.Mock()
    client = DebugStatsdClient(inner=mock_inner)
    getattr(client, method)(*args, **kwargs)
    _assert_calls(mock_inner._emit_packet, expected)


@pytest.mark.parametrize("method,args,kwargs,expected", SIMPLE_TEST_CASES)
def test_debug_client_custom_logger_and_level(
    method: str,
    args: Tuple[Any, ...],
    kwargs: Dict[str, Any],
    expected: Union[List[str], str],
    caplog: Any,
) -> None:
    client = DebugStatsdClient(
        logger=logging.getLogger("foo"), level=logging.DEBUG
    )
    with caplog.at_level(logging.DEBUG, logger="foo"):
        getattr(client, method)(*args, **kwargs)

    if isinstance(expected, list):
        assert len(caplog.records) == len(expected)
        for x in expected:
            assert x in caplog.text
    else:
        assert len(caplog.records) == 1
        assert expected in caplog.text
