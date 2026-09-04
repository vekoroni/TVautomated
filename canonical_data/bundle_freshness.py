"""Canonical semantic freshness for MSI evidence bundles.

Freshness is derived from timestamps and market sessions.  Upstream labels are
never treated as authority because they can survive a contract or run change.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Mapping

from .session_clock import evaluate_freshness


def _first(row: Mapping[str, Any], *names: str) -> Any:
    for name in names:
        value = row.get(name)
        if value is not None and str(value).strip().upper() not in {"", "NAN", "NONE", "NULL"}:
            return value
    return None


def _timestamp(value: Any) -> datetime | None:
    if value is None:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.astimezone(timezone.utc) if parsed.tzinfo else None


def _date(value: Any) -> date | None:
    if value is None:
        return None
    try:
        return date.fromisoformat(str(value).strip()[:10])
    except ValueError:
        return None


def _state(
    row: Mapping[str, Any],
    *,
    timestamp_fields: tuple[str, ...],
    domain: str,
    now: datetime,
    ttl_seconds: int,
) -> str:
    return evaluate_freshness(
        as_of=_timestamp(_first(row, *timestamp_fields)),
        dataset_session=_date(_first(row, "session_date", "market_session_date", "as_of_date")),
        domain=domain,
        now=now,
        live_ttl_seconds=ttl_seconds,
    ).value


def derive_bundle_freshness(
    row: Mapping[str, Any], *, now: datetime | None = None
) -> dict[str, str]:
    instant = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    return {
        "exact_option_quote": _state(
            row,
            timestamp_fields=(
                "current_quote_timestamp_utc", "quote_timestamp_utc",
                "selected_quote_timestamp_utc", "live_contract_quote_timestamp",
                "live_contract_provider_updated", "live_options_fetched_at",
            ),
            domain="LIVE_OPTION", now=instant, ttl_seconds=60,
        ),
        "underlying_quote": _state(
            row,
            timestamp_fields=(
                "underlying_nbbo_timestamp_utc", "underlying_quote_updated",
                "underlying_timestamp_utc", "price_timestamp_utc",
            ),
            domain="LIVE_UNDERLYING", now=instant, ttl_seconds=30,
        ),
        "market_structure": _state(
            row,
            timestamp_fields=("ms_as_of_utc", "last_completed_bar_utc", "market_structure_as_of_utc"),
            domain="LIVE_STRUCTURE", now=instant, ttl_seconds=120,
        ),
        "macro_quant_packet": str(
            _first(row, "macro_freshness_status", "macro_freshness") or "UNKNOWN"
        ).strip().upper(),
    }


__all__ = ["derive_bundle_freshness"]
