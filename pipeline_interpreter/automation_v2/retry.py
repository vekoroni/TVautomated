"""Retry policy for transient analysis-provider failures."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable

from .models import AnalysisPayload, TickerRunRequest
from .schemas import SchemaValidationError


Sleep = Callable[[float], None]


def is_retryable_provider_error(exc: Exception) -> bool:
    if isinstance(exc, SchemaValidationError):
        return False
    if isinstance(exc, (TimeoutError, ConnectionError)):
        return True
    status = getattr(exc, "status_code", None)
    if status is None:
        response = getattr(exc, "response", None)
        status = getattr(response, "status_code", None)
    try:
        status_code = int(status)
    except (TypeError, ValueError):
        return False
    return status_code == 429 or 500 <= status_code <= 599


@dataclass(slots=True)
class RetryPolicy:
    max_attempts: int = 3
    initial_backoff_seconds: float = 0.25
    multiplier: float = 2.0
    max_backoff_seconds: float = 2.0

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be at least one")


@dataclass(slots=True)
class RetryingProvider:
    provider: object
    policy: RetryPolicy = field(default_factory=RetryPolicy)
    sleep: Sleep = time.sleep
    attempts: int = 0
    errors: list[str] = field(default_factory=list)

    def analyze(self, request: TickerRunRequest) -> AnalysisPayload:
        delay = self.policy.initial_backoff_seconds
        for attempt in range(1, self.policy.max_attempts + 1):
            self.attempts = attempt
            try:
                return self.provider.analyze(request)
            except Exception as exc:
                self.errors.append(f"{type(exc).__name__}:{exc}")
                if (
                    attempt >= self.policy.max_attempts
                    or not is_retryable_provider_error(exc)
                ):
                    raise
                self.sleep(min(delay, self.policy.max_backoff_seconds))
                delay *= self.policy.multiplier
        raise AssertionError("retry loop exited unexpectedly")
