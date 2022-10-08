r"""
Statsd client implementation for Python.

Version: v\ |version|.
"""  # noqa: W605
from .client import (  # noqa: F401
    BaseStatsdClient,
    DebugStatsdClient,
    StatsdClient,
    UDPStatsdClient,
)
from .version import __version__  # noqa: F401


__all__ = (
    "BaseStatsdClient",
    "StatsdClient",
    "UDPStatsdClient",
    "DebugStatsdClient",
)
