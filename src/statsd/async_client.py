from __future__ import annotations

import abc
import contextlib
import functools
import logging
import time
from typing import Any, AsyncIterator, Awaitable, Callable, Mapping, TypeVar
from typing_extensions import ParamSpec

from statsd.base import AbstractStatsdClient


P = ParamSpec("P")
T = TypeVar("T")
U = TypeVar("U")

logger = logging.getLogger("statsd")


class BaseAsyncStatsdClient(AbstractStatsdClient[Awaitable[None]]):
    """
    Base async client.

    This class exposes the public interface and takes care of packet formatting
    as well as sampling. It does not actually send packets anywhere, which is
    left to concrete subclasses implementing :meth:`_emit`.
    """

    @abc.abstractmethod
    async def _emit(self, packets: list[str]) -> None:
        """
        Async send implementation.

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
    ) -> Callable[[Callable[P, Awaitable[U]]], Callable[P, Awaitable[U]]]:
        """
        Wrap a function to record its execution time.

        This just wraps the function call with a :meth:`timer` context manager.

        If a name is not provided, the function name will be used.

        Passing ``use_distribution=True`` will report the value as a globally
        aggregated :meth:`distribution` metric instead of a :meth:`timing`
        metric.

        >>> client = AsyncStatsdClient()
        >>> @client.timed()
        ... async def do_something():
        ...     pass
        """

        def decorator(
            fn: Callable[P, Awaitable[U]],
        ) -> Callable[P, Awaitable[U]]:
            # TODO: Should the fallback include the module? Class (for methods)?
            # or func.__name__
            metric_name = name or fn.__name__

            @functools.wraps(fn)
            async def wrapped(*args: P.args, **kwargs: P.kwargs) -> U:
                async with self.timer(
                    metric_name,
                    tags=tags,
                    use_distribution=use_distribution,
                    sample_rate=sample_rate,
                ):
                    return await fn(*args, **kwargs)

            return wrapped

        return decorator

    @contextlib.asynccontextmanager
    async def timer(
        self,
        name: str,
        *,
        tags: Mapping[str, str] | None = None,
        sample_rate: float | None = None,
        use_distribution: bool = False,
    ) -> AsyncIterator[None]:
        """
        Context manager to measure the execution time of an async block.

        Passing ``use_distribution=True`` will report the value as a globally
        aggregated :meth:`distribution` metric instead of a :meth:`timing`
        metric.

        >>> client = AsyncStatsdClient()
        >>> async def operation():
        ...     async with client.timer("download_duration"):
        ...         pass
        """
        start = time.perf_counter()
        try:
            yield
        finally:
            duration_ms = int(1000 * (time.perf_counter() - start))
            if use_distribution:
                await self.distribution(
                    name,
                    duration_ms,
                    tags=tags,
                    sample_rate=sample_rate,
                )
            else:
                await self.timing(
                    name,
                    duration_ms,
                    tags=tags,
                    sample_rate=sample_rate,
                )


class DebugAsyncStatsdClient(BaseAsyncStatsdClient):
    """
    Verbose client for development or debugging purposes.

    All Statsd packets will be logged and optionally forwarded to a wrapped
    client.
    """

    def __init__(
        self,
        level: int = logging.INFO,
        logger: logging.Logger = logger,
        inner: BaseAsyncStatsdClient | None = None,
        **kwargs: Any,
    ) -> None:
        r"""
        Initialize DebugStatsdClient.

        :param level: Log level to use, defaults to ``INFO``.

        :param logger: Logger instance to use, defaults to ``statsd``.

        :param inner: Wrapped client.

        :param \**kwargs: Extra arguments forwarded to :class:`BaseAsyncStatsdClient`.
        """
        super().__init__(**kwargs)
        self.level = level
        self.logger = logger
        self.inner = inner

    async def _emit(self, packets: list[str]) -> None:
        for packet in packets:
            self.logger.log(self.level, "> %s", packet)
        if self.inner:
            await self.inner._emit(packets)


AsyncStatsdClient = DebugAsyncStatsdClient
