"""Shared fail-closed validation for safety-critical numeric inputs."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any


def finite_decimal(value: Any) -> Decimal | None:
    """Return a finite Decimal, or None for missing/malformed/non-finite input."""
    if value is None or isinstance(value, bool):
        return None
    cleaned = str(value).strip()
    if not cleaned:
        return None
    try:
        parsed = Decimal(cleaned)
    except (InvalidOperation, ValueError, TypeError):
        return None
    return parsed if parsed.is_finite() else None


def invalid_or_negative(value: Any) -> bool:
    """Fail closed: invalid numeric input is treated like a negative value."""
    parsed = finite_decimal(value)
    return parsed is None or parsed < 0


def positive_finite(value: Any) -> bool:
    """Return True only for a finite numeric value strictly greater than zero."""
    parsed = finite_decimal(value)
    return parsed is not None and parsed > 0
