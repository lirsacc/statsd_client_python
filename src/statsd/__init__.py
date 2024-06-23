r"""
Statsd client implementation for Python.

Version: v\ |version|.
"""

from .base import Sample
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
    "Sample",
    "StatsdClient",
    "UDPStatsdClient",
    "__version__",
)
