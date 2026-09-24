"""Validated acquisition limits, scoped to one queue worker."""
from contextvars import ContextVar
from dataclasses import dataclass

MAX_DURATION_SECONDS = 6 * 60 * 60
MAX_SOURCE_BYTES = 5 * 1024 ** 3

@dataclass(frozen=True)
class Limits:
    duration: int = 3600
    size: int = 500 * 1024 ** 2

    def __post_init__(self):
        for value, ceiling in ((self.duration, MAX_DURATION_SECONDS), (self.size, MAX_SOURCE_BYTES)):
            if type(value) is not int or not 1 <= value <= ceiling:
                raise ValueError("Source limits are outside the supported range")

    @classmethod
    def from_settings(cls, settings):
        return cls(settings.get("max_duration_seconds", 3600),
                   settings.get("max_source_bytes", 500 * 1024 ** 2))

acquisition_limits = ContextVar("acquisition_limits", default=Limits())
