from __future__ import annotations

import logging
from typing import Any
from unittest import mock

import pytest

from statsd import BaseAsyncStatsdClient, DebugAsyncStatsdClient


class MockClient(BaseAsyncStatsdClient):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.mock = mock.Mock()

    async def _emit(self, packets: list[str]) -> None:
        if packets:
            self.mock(packets)

    def assert_emitted(self, expected: list[str] | str) -> None:
        self.mock.assert_called_once_with(
            expected if isinstance(expected, list) else [expected],
        )

    def assert_did_not_emit(self) -> None:
        self.mock.assert_not_called()


@pytest.mark.asyncio()
async def test_timed_decorator() -> None:
    client = MockClient()

    @client.timed("foo", tags={"foo": "1"})
    async def fn() -> None:
        pass

    with mock.patch(
        "time.perf_counter",
        side_effect=[7.886838544, 20.181117592],
    ):
        await fn()

    client.mock.assert_called_once_with(["foo:12294|ms|#foo:1"])


@pytest.mark.asyncio()
async def test_timed_decorator_use_distribution() -> None:
    client = MockClient()

    @client.timed("foo", tags={"foo": "1"}, use_distribution=True)
    async def fn() -> None:
        pass

    with mock.patch(
        "time.perf_counter",
        side_effect=[7.886838544, 20.181117592],
    ):
        await fn()

    client.mock.assert_called_once_with(["foo:12294|d|#foo:1"])


SIMPLE_TEST_CASES: list[
    tuple[str, tuple[Any, ...], dict[str, Any], list[str] | str]
] = [
    ("increment", ("foo",), {}, "foo:1|c"),
    ("increment", ("foo", 10), {}, "foo:10|c"),
]


@pytest.mark.parametrize(
    ("method", "args", "kwargs", "expected"),
    SIMPLE_TEST_CASES,
)
@pytest.mark.asyncio()
async def test_debug_client_no_inner(
    method: str,
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    expected: list[str] | str,
    caplog: Any,
) -> None:
    client = DebugAsyncStatsdClient()
    with caplog.at_level(logging.INFO, logger="statsd"):
        await getattr(client, method)(*args, **kwargs)

    if isinstance(expected, list):
        assert len(caplog.records) == len(expected)
        for x in expected:
            assert x in caplog.text
    else:
        assert len(caplog.records) == 1
        assert expected in caplog.text


@pytest.mark.parametrize(
    ("method", "args", "kwargs", "expected"),
    SIMPLE_TEST_CASES,
)
@pytest.mark.asyncio()
async def test_debug_client(
    method: str,
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    expected: str | list[str],
) -> None:
    inner = MockClient()
    client = DebugAsyncStatsdClient(inner=inner)
    await getattr(client, method)(*args, **kwargs)
    inner.assert_emitted(expected)


@pytest.mark.parametrize(
    ("method", "args", "kwargs", "expected"),
    SIMPLE_TEST_CASES,
)
@pytest.mark.asyncio()
async def test_debug_client_custom_logger_and_level(
    method: str,
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    expected: list[str] | str,
    caplog: Any,
) -> None:
    client = DebugAsyncStatsdClient(
        logger=logging.getLogger("foo"),
        level=logging.DEBUG,
    )
    with caplog.at_level(logging.DEBUG, logger="foo"):
        await getattr(client, method)(*args, **kwargs)

    if isinstance(expected, list):
        assert len(caplog.records) == len(expected)
        for x in expected:
            assert x in caplog.text
    else:
        assert len(caplog.records) == 1
        assert expected in caplog.text
