"""Exact-contract Morning-to-current quote comparison evidence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from enum import Enum
import math
from typing import Any, Mapping

from canonical_data.option_identity import normalise_occ_symbol
from canonical_data.session_clock import FreshnessState, evaluate_freshness
from contracts.long_option_policy import quote_spread_fraction


class ComparisonStatus(str, Enum):
    SAME_CONTRACT = "SAME_CONTRACT"
    CONTRACT_CHANGED = "CONTRACT_CHANGED"
    BASELINE_MISSING = "BASELINE_MISSING"
    BASELINE_ZERO = "BASELINE_ZERO"
    CURRENT_MISSING = "CURRENT_MISSING"
    STALE = "STALE"


@dataclass(frozen=True, slots=True)
class QuoteSnapshot:
    contract_symbol: str
    dataset_id: str
    timestamp_utc: datetime | None
    session_date: date | None
    bid: float | None
    ask: float | None
    mid: float | None
    spread_pct: float | None
    bid_size: int | None
    ask_size: int | None
    source: str


def _first(row: Mapping[str, Any], *names: str) -> Any:
    for name in names:
        value = row.get(name)
        if value is not None and str(value).strip().upper() not in {
            "", "NONE", "NULL", "NAN", "N/A",
        }:
            return value
    return None


def _number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _size(value: Any) -> int | None:
    number = _number(value)
    if number is None or number < 0 or not number.is_integer():
        return None
    return int(number)


def _timestamp(value: Any) -> datetime | None:
    if value is None:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def _date(value: Any) -> date | None:
    if value is None:
        return None
    try:
        return date.fromisoformat(str(value).strip()[:10])
    except ValueError:
        return None


def _contract(value: Any) -> str:
    try:
        return normalise_occ_symbol(value)
    except (TypeError, ValueError):
        return ""


def quote_snapshot_from_row(row: Mapping[str, Any], *, role: str) -> QuoteSnapshot:
    current = role.strip().upper() == "CURRENT"
    if current:
        symbol = _first(row, "current_contract_symbol", "live_selected_contract_symbol",
                        "selected_contract_symbol", "morning_selected_contract_symbol", "contract_symbol")
        dataset_id = _first(row, "current_quote_snapshot_id", "current_quote_dataset_id",
                            "msi_exact_quote_dataset_id", "selected_quote_snapshot_id")
        timestamp = _first(row, "current_quote_timestamp_utc", "quote_timestamp_utc",
                           "contract_quote_timestamp", "live_contract_provider_updated",
                           "live_options_fetched_at")
        bid = _first(row, "current_contract_bid", "live_contract_bid", "contract_bid")
        ask = _first(row, "current_contract_ask", "live_contract_ask", "contract_ask")
        mid = _first(row, "current_contract_mid", "live_contract_mid", "contract_mid")
        spread = _first(row, "current_contract_spread_pct", "live_contract_spread_fraction",
                        "contract_spread_pct")
        bid_size = _first(row, "current_contract_bid_size", "live_contract_bid_size", "contract_bid_size")
        ask_size = _first(row, "current_contract_ask_size", "live_contract_ask_size", "contract_ask_size")
        source = _first(row, "current_quote_source", "quote_source", "live_options_source")
    else:
        symbol = _first(row, "morning_contract_symbol", "morning_selected_contract_symbol",
                        "selected_contract_symbol", "contract_symbol")
        dataset_id = _first(row, "morning_quote_dataset_id", "morning_contract_quote_dataset_id",
                            "selected_quote_snapshot_id")
        timestamp = _first(row, "morning_quote_timestamp_utc", "morning_contract_quote_timestamp_utc",
                           "selected_quote_timestamp_utc", "quote_timestamp_utc",
                           "contract_quote_timestamp", "live_options_fetched_at")
        bid = _first(row, "morning_contract_bid", "contract_bid", "live_contract_bid")
        ask = _first(row, "morning_contract_ask", "contract_ask", "live_contract_ask")
        mid = _first(row, "morning_contract_mid", "contract_mid", "live_contract_mid")
        spread = _first(row, "morning_contract_spread_pct", "contract_spread_pct",
                        "live_contract_spread_fraction")
        bid_size = _first(row, "morning_contract_bid_size", "contract_bid_size", "live_contract_bid_size")
        ask_size = _first(row, "morning_contract_ask_size", "contract_ask_size", "live_contract_ask_size")
        source = _first(row, "morning_quote_source", "quote_source", "live_options_source")
    bid_number, ask_number, mid_number = _number(bid), _number(ask), _number(mid)
    if mid_number is None and bid_number is not None and ask_number is not None:
        mid_number = (bid_number + ask_number) / 2.0
    spread_number = _number(spread)
    if spread_number is None:
        spread_number = quote_spread_fraction(bid_number, ask_number)
    return QuoteSnapshot(
        contract_symbol=_contract(symbol),
        dataset_id=str(dataset_id or "").strip(),
        timestamp_utc=_timestamp(timestamp),
        session_date=_date(_first(row, "session_date", "market_session_date", "as_of_date")),
        bid=bid_number,
        ask=ask_number,
        mid=mid_number,
        spread_pct=spread_number,
        bid_size=_size(bid_size),
        ask_size=_size(ask_size),
        source=str(source or "").strip().upper(),
    )


def _complete(snapshot: QuoteSnapshot) -> bool:
    return bool(
        snapshot.contract_symbol
        and snapshot.dataset_id
        and snapshot.timestamp_utc
        and snapshot.bid is not None
        and snapshot.ask is not None
        and snapshot.mid is not None
    )


def compare_exact_option_quotes(
    *,
    ticker: str,
    thesis_id: str,
    trade_idea_id: str,
    selected_structure_id: str,
    morning: QuoteSnapshot,
    current: QuoteSnapshot,
    now: datetime | None = None,
    live_ttl_seconds: int = 60,
) -> dict[str, Any]:
    instant = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    if not _complete(morning):
        status = ComparisonStatus.BASELINE_MISSING
    elif not _complete(current):
        status = ComparisonStatus.CURRENT_MISSING
    elif morning.contract_symbol != current.contract_symbol:
        status = ComparisonStatus.CONTRACT_CHANGED
    else:
        freshness = evaluate_freshness(
            as_of=current.timestamp_utc,
            dataset_session=current.session_date,
            domain="LIVE_OPTION",
            now=instant,
            live_ttl_seconds=live_ttl_seconds,
        )
        if freshness is not FreshnessState.FRESH:
            status = ComparisonStatus.STALE
        elif any(value == 0 for value in (morning.bid, morning.ask, morning.mid)):
            status = ComparisonStatus.BASELINE_ZERO
        else:
            status = ComparisonStatus.SAME_CONTRACT
    freshness = evaluate_freshness(
        as_of=current.timestamp_utc,
        dataset_session=current.session_date,
        domain="LIVE_OPTION",
        now=instant,
        live_ttl_seconds=live_ttl_seconds,
    )
    comparable = status in {ComparisonStatus.SAME_CONTRACT, ComparisonStatus.BASELINE_ZERO}

    def changes(base: float | None, value: float | None) -> tuple[float | None, float | None]:
        if not comparable or base is None or value is None:
            return None, None
        absolute = value - base
        return absolute, None if base == 0 else absolute / abs(base)

    bid_change, bid_change_pct = changes(morning.bid, current.bid)
    ask_change, ask_change_pct = changes(morning.ask, current.ask)
    mid_change, mid_change_pct = changes(morning.mid, current.mid)
    bid_size_change = (
        current.bid_size - morning.bid_size
        if comparable and current.bid_size is not None and morning.bid_size is not None
        else None
    )
    ask_size_change = (
        current.ask_size - morning.ask_size
        if comparable and current.ask_size is not None and morning.ask_size is not None
        else None
    )
    spread_change = (
        (current.spread_pct - morning.spread_pct) * 100.0
        if comparable and current.spread_pct is not None and morning.spread_pct is not None
        else None
    )
    return {
        "ticker": ticker.strip().upper(),
        "thesis_id": thesis_id,
        "trade_idea_id": trade_idea_id,
        "selected_structure_id": selected_structure_id,
        "comparison_status": status.value,
        "change_status": status.value,
        "morning_contract_symbol": morning.contract_symbol,
        "current_contract_symbol": current.contract_symbol,
        "morning_quote_dataset_id": morning.dataset_id,
        "current_quote_dataset_id": current.dataset_id,
        "morning_quote_timestamp_utc": morning.timestamp_utc.isoformat() if morning.timestamp_utc else None,
        "current_quote_timestamp_utc": current.timestamp_utc.isoformat() if current.timestamp_utc else None,
        "morning_bid": morning.bid, "morning_ask": morning.ask, "morning_mid": morning.mid,
        "morning_spread_pct": morning.spread_pct,
        "current_bid": current.bid, "current_ask": current.ask, "current_mid": current.mid,
        "current_spread_pct": current.spread_pct,
        "bid_change": bid_change, "bid_change_pct": bid_change_pct,
        "ask_change": ask_change, "ask_change_pct": ask_change_pct,
        "mid_change": mid_change, "mid_change_pct": mid_change_pct,
        "spread_change_pp": spread_change,
        "morning_bid_size": morning.bid_size, "morning_ask_size": morning.ask_size,
        "current_bid_size": current.bid_size, "current_ask_size": current.ask_size,
        "bid_size_change": bid_size_change, "ask_size_change": ask_size_change,
        "quote_age_seconds": (
            max(0.0, (instant - current.timestamp_utc).total_seconds())
            if current.timestamp_utc else None
        ),
        "quote_freshness": freshness.value,
        "quote_source": current.source,
    }


def quote_change_overlay_fields(evidence: Mapping[str, Any]) -> dict[str, Any]:
    mapping = {
        "current_contract_bid": "current_bid", "current_contract_ask": "current_ask",
        "current_contract_mid": "current_mid", "current_contract_spread_pct": "current_spread_pct",
        "contract_bid_change": "bid_change", "contract_bid_change_pct": "bid_change_pct",
        "contract_ask_change": "ask_change", "contract_ask_change_pct": "ask_change_pct",
        "contract_mid_change": "mid_change", "contract_mid_change_pct": "mid_change_pct",
        "contract_spread_change_pp": "spread_change_pp", "contract_bid_size": "current_bid_size",
        "contract_ask_size": "current_ask_size", "contract_bid_size_change": "bid_size_change",
        "contract_ask_size_change": "ask_size_change", "current_quote_snapshot_id": "current_quote_dataset_id",
        "quote_timestamp_utc": "current_quote_timestamp_utc", "quote_age_seconds": "quote_age_seconds",
        "quote_freshness": "quote_freshness", "quote_source": "quote_source",
        "comparison_status": "comparison_status", "change_status": "change_status",
    }
    return {target: evidence.get(source) for target, source in mapping.items()}


__all__ = ["ComparisonStatus", "QuoteSnapshot", "compare_exact_option_quotes",
           "quote_change_overlay_fields", "quote_snapshot_from_row"]
