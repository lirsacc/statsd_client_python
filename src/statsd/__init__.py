r"""
Statsd client implementation for Python.

Version: v\ |version|.
"""

from .client import (
    BaseStatsdClient,
    DebugStatsdClient,
    StatsdClient,
    UDPStatsdClient,
)
from .version import __version__


__all__ = (
    "BaseStatsdClient",
    "DebugStatsdClient",
    "StatsdClient",
    "UDPStatsdClient",
    "__version__",
)
