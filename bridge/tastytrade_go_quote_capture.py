"""Advisory broker quote capture for a frozen Morning GO cohort.

A near-close ask-to-bid comparison is a *paper mark*, never an executed trade,
and never the mature 1–20-session expression outcome. A missing or old broker
quote remains unknown. Nothing here writes to the governed opportunity book.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from canonical_data.option_identity import normalise_occ_symbol
from domain.broker_quote_observation import observe_tastytrade_quote
from bridge.tastytrade_readonly_mcp import BrokerMcpError


def _utc(value: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("UTC timestamp is required")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp requires a timezone")
    return parsed.astimezone(timezone.utc)


def _positive_decimal(value: Any) -> Decimal | None:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return result if result.is_finite() and result > 0 else None


def _multiplier(value: Any) -> int | None:
    decimal = _positive_decimal(value)
    return int(decimal) if decimal is not None and decimal == int(decimal) else None


def _broker_multiplier(payload: Mapping[str, Any] | list[Any], symbol: str) -> int | None:
    items = payload.get("items") if isinstance(payload, Mapping) else payload
    if not isinstance(items, list):
        return None
    for item in items:
        if not isinstance(item, Mapping):
            continue
        try:
            if normalise_occ_symbol(item.get("symbol")) != symbol:
                continue
        except ValueError:
            continue
        instrument = item.get("instrument")
        if isinstance(instrument, Mapping):
            return _multiplier(instrument.get("shares-per-contract"))
    return None


def build_go_quote_report(
    rows: Sequence[Mapping[str, Any]], broker: Any, *, run_id: str,
    fetched_at_utc: str | None = None, close_window_start_utc: str | None = None,
    close_window_end_utc: str | None = None,
) -> dict[str, Any]:
    """Capture exact symbols in <=100-symbol calls and preserve failures.

    A user-supplied close window is required before any quote is called a
    close-window mark. The window is a provenance rule, not a profit target.
    """
    fetched = _utc(fetched_at_utc) if fetched_at_utc else datetime.now(timezone.utc)
    if bool(close_window_start_utc) != bool(close_window_end_utc):
        raise ValueError("both close-window bounds are required")
    start = _utc(close_window_start_utc) if close_window_start_utc else None
    end = _utc(close_window_end_utc) if close_window_end_utc else None
    if start and (end is None or start >= end or end > fetched):
        raise ValueError("close-window bounds are invalid")
    selected: list[tuple[Mapping[str, Any], str]] = []
    seen: set[str] = set()
    for row in rows:
        if row.get("morning_gate_verdict") != "GO":
            continue
        symbol = normalise_occ_symbol(row.get("morning_selected_contract_symbol"))
        if symbol in seen:
            raise ValueError("duplicate exact OCC symbol in GO cohort")
        seen.add(symbol)
        selected.append((row, symbol))

    results: list[dict[str, Any]] = []
    for offset in range(0, len(selected), 100):
        batch = selected[offset:offset + 100]
        symbols = [symbol for _, symbol in batch]
        try:
            payload = broker.quote(symbols, "Equity Option")
            batch_error = None
        except BrokerMcpError as exc:
            payload = {"items": []}
            batch_error = type(exc).__name__
        batch_fetched_at = (
            fetched_at_utc or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        )
        fetched = _utc(batch_fetched_at)
        for row, symbol in batch:
            try:
                observation = observe_tastytrade_quote(
                    payload, requested_symbol=symbol, instrument_type="Equity Option",
                    fetched_at_utc=batch_fetched_at,
                    selected_contract_multiplier=_multiplier(row.get("contract_multiplier")),
                    broker_contract_multiplier=_broker_multiplier(payload, symbol),
                )
                detail = observation.to_dict()
                provider_time = (
                    _utc(observation.provider_updated_at_utc)
                    if observation.provider_updated_at_utc else None
                )
                morning_ask = _positive_decimal(row.get("morning_contract_ask"))
                broker_bid = _positive_decimal(observation.bid)
                inside_close = bool(start and end and provider_time and start <= provider_time <= end)
                paper_return = None
                if (inside_close and observation.identity_state == "EXACT_SYMBOL"
                        and observation.quote_state == "TWO_SIDED_OBSERVED"
                        and observation.time_state == "PROVIDER_TIME_PRESENT"
                        and morning_ask is not None and broker_bid is not None):
                    paper_return = str((broker_bid / morning_ask - Decimal(1)) * Decimal(100))
                mark_state = (
                    "CLOSE_WINDOW_PAPER_MARK" if paper_return is not None else
                    "NO_CLOSE_WINDOW_MARK" if start else "SNAPSHOT_ONLY"
                )
            except (ValueError, TypeError):
                detail = {"identity_state": "INVALID_BROKER_PAYLOAD", "quote_state": "INVALID_QUOTE_DATA",
                          "time_state": "NO_PROVIDER_TIME", "provider_updated_at_utc": None,
                          "fetched_at_utc": batch_fetched_at, "bid": None, "ask": None,
                          "bid_size": None, "ask_size": None, "multiplier_state": "UNVERIFIED",
                          "observation_hash": None}
                paper_return, mark_state = None, "NO_CLOSE_WINDOW_MARK" if start else "SNAPSHOT_ONLY"
            results.append({
                "run_id": run_id,
                "ticker": row.get("ticker"),
                "exact_occ_symbol": symbol,
                "morning_provider": "MARKETDATA",
                "morning_provider_updated_at_utc": row.get("quote_provider_timestamp_utc"),
                "morning_option_ask": row.get("morning_contract_ask"),
                "broker_provider": "TASTYTRADE",
                "broker_provider_updated_at_utc": detail["provider_updated_at_utc"],
                "broker_fetched_at_utc": detail["fetched_at_utc"],
                "broker_bid": detail["bid"],
                "broker_ask": detail["ask"],
                "broker_bid_size": detail["bid_size"],
                "broker_ask_size": detail["ask_size"],
                "broker_identity_state": detail["identity_state"],
                "broker_quote_state": detail["quote_state"],
                "broker_time_state": detail["time_state"],
                "broker_multiplier_state": detail["multiplier_state"],
                "broker_observation_hash": detail["observation_hash"],
                "broker_batch_error": batch_error,
                "mark_state": mark_state,
                "day_zero_paper_return_pct": paper_return,
                "realised_trade_return_pct": None,
                "authority": "ADVISORY_ONLY",
                "signal_quality_review": "UNDER_REVIEW_PIPELINE_FLAWS",
            })
    return {
        "contract_version": "tastytrade_go_quote_observation_v1",
        "run_id": run_id,
        "broker_fetched_at_utc": fetched.isoformat().replace("+00:00", "Z"),
        "close_window_start_utc": close_window_start_utc,
        "close_window_end_utc": close_window_end_utc,
        "requested_contract_count": len(selected),
        "close_window_paper_mark_count": sum(
            x["mark_state"] == "CLOSE_WINDOW_PAPER_MARK" for x in results
        ),
        "authority": "ADVISORY_ONLY",
        "observations": results,
    }
