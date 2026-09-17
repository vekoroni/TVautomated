"""The only place in the rebuild package allowed to read the wall clock."""

from __future__ import annotations

from datetime import datetime, timezone


def wall_clock_utc() -> datetime:
    return datetime.now(timezone.utc)


def parse_as_of(value: str) -> datetime:
    instant = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    if instant.tzinfo is None:
        raise ValueError("--as-of-utc must include a timezone")
    return instant.astimezone(timezone.utc)
