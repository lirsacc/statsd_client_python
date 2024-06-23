# ruff: noqa: D101
from __future__ import annotations


class InvalidSampleRate(ValueError):
    def __init__(self, value: int | float) -> None:
        super().__init__(f"Sample rate must be between 0 and 1. Git `{value}`")


class InvalidMetricType(ValueError):
    def __init__(self, value: str) -> None:
        super().__init__(f"Invalid metric type `{value}`.")


class InvalidTags(ValueError):
    pass
