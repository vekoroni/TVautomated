"""Point-in-time, advisory ticker/sector/option evidence for Interpreter reports.

This module observes the canonical completed-price store read-only. A missing or
later-revised bar is UNKNOWN; the current database value is never backdated.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import sqlite3
from typing import Any, Mapping


CHAIN_KEYS = ("sector", "ticker", "thesis", "contract", "morning")
ADJUSTMENT = "POLYGON_SPLIT_ADJUSTED"


def _instant(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.astimezone(timezone.utc) if parsed.tzinfo else None


def _positive(value: object) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and number > 0 else None


def _nonnegative(value: object) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and number >= 0 else None


def _direction(row: Mapping[str, Any]) -> str | None:
    raw = str(row.get("canonical_direction") or row.get("direction") or "").upper()
    return "CALL" if raw in {"CALL", "BULL", "LONG_CALL"} else (
        "PUT" if raw in {"PUT", "BEAR", "LONG_PUT"} else None)


def _bar(row: tuple, cutoff: datetime) -> dict[str, Any] | None:
    trading_date, close, fetched_at, row_hash = row
    fetched = _instant(fetched_at)
    price = _positive(close)
    if not fetched or fetched > cutoff or price is None or not row_hash:
        return None
    return {"session": trading_date, "close": price,
            "fetched_at_utc": fetched.isoformat(), "row_hash": str(row_hash)}


def _price_path(database: Path, *, ticker: str, sector_etf: str,
                session_date: str, cutoff: datetime) -> dict[str, Any]:
    try:
        date.fromisoformat(session_date)
    except (TypeError, ValueError):
        return {"state": "UNKNOWN", "reason": "NO_FROZEN_COMPLETED_SESSION"}
    if not database.is_file():
        return {"state": "UNKNOWN", "reason": "CANONICAL_PRICE_STORE_UNAVAILABLE"}
    symbols = {ticker, sector_etf, "SPY"}
    if not ticker or not sector_etf or any(not symbol for symbol in symbols):
        return {"state": "UNKNOWN", "reason": "TICKER_OR_SECTOR_ETF_MISSING"}
    try:
        connection = sqlite3.connect(f"file:{database.as_posix()}?mode=ro", uri=True, timeout=3)
        try:
            connection.execute("PRAGMA query_only=ON")
            query = ("SELECT trading_date,close,fetched_at,row_hash FROM ohlcv_daily "
                     "WHERE ticker=? AND adjustment_convention=? AND bar_status='COMPLETE' "
                     "AND trading_date<=? ORDER BY trading_date DESC LIMIT 30")
            histories = {}
            for symbol in symbols:
                histories[symbol] = {
                    bar["session"]: bar
                    for raw in connection.execute(query, (symbol, ADJUSTMENT, session_date))
                    if (bar := _bar(raw, cutoff)) is not None
                }
        finally:
            connection.close()
    except (OSError, sqlite3.Error):
        return {"state": "UNKNOWN", "reason": "CANONICAL_PRICE_READ_FAILED"}
    calendar = sorted(histories["SPY"])
    if len(calendar) < 6 or calendar[-1] != session_date:
        return {"state": "UNKNOWN", "reason": "NO_SIX_SESSION_PIT_MARKET_CALENDAR"}
    sessions = calendar[-6:]
    if any(any(session not in histories[symbol] for session in sessions) for symbol in symbols):
        return {"state": "UNKNOWN", "reason": "GAPPED_OR_LATER_REVISED_PRICE_PATH"}
    returns = {
        symbol: histories[symbol][sessions[-1]]["close"] / histories[symbol][sessions[0]]["close"] - 1
        for symbol in symbols
    }
    observed = [histories[symbol][session] for symbol in sorted(symbols) for session in sessions]
    fingerprint = hashlib.sha256(json.dumps(
        [(bar["session"], bar["row_hash"]) for bar in observed],
        separators=(",", ":"), sort_keys=True).encode("utf-8")).hexdigest()
    return {
        "state": "OBSERVED", "sessions": sessions,
        "ticker_return_5": round(returns[ticker], 8),
        "sector_return_5": round(returns[sector_etf], 8),
        "spy_return_5": round(returns["SPY"], 8),
        "sector_minus_spy_5": round(returns[sector_etf] - returns["SPY"], 8),
        "ticker_minus_sector_5": round(returns[ticker] - returns[sector_etf], 8),
        "latest_source_fetch_utc": max(bar["fetched_at_utc"] for bar in observed),
        "bar_hashes_sha256": fingerprint,
    }


def _ticker_link(ticker: str, sector_etf: str, ticker_minus_sector: float | None,
                 side: str | None) -> tuple[str, float | None]:
    """XLU-D12: a ticker that is its own sector ETF has no ticker-versus-sector link; an exact
    zero is FLAT, never "opposes"."""
    if ticker and sector_etf and ticker == sector_etf:
        return "NOT_APPLICABLE_TICKER_IS_SECTOR_ETF", None
    if ticker_minus_sector is None or side not in {"CALL", "PUT"}:
        return "UNKNOWN", None
    signed = (1 if side == "CALL" else -1) * ticker_minus_sector
    return ("SUPPORTS" if signed > 0 else "OPPOSES" if signed < 0 else "FLAT"), signed


def _days_to_expiry(symbol: object, as_of: str | None) -> int | None:
    """Calendar days from the evidence date to the OCC expiry in the contract symbol."""
    import re
    match = re.search(r"(\d{6})[CP]\d{8}$", str(symbol or "").replace("O:", ""))
    instant = _instant(as_of) if as_of else None
    if not match or instant is None:
        return None
    try:
        expiry = datetime.strptime(match.group(1), "%y%m%d").date()
    except ValueError:
        return None
    return (expiry - instant.date()).days


def build_confluence_evidence(
    row: Mapping[str, Any], *, session_date: str | None,
    evidence_cutoff_utc: str, historical_prices_path: Path,
    morning: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build observed facts and unknowns; never decide trade permission."""

    cutoff = _instant(evidence_cutoff_utc)
    side = _direction(row)
    ticker = str(row.get("ticker") or "").upper()
    sector_etf = str(row.get("sector_etf") or "").upper()
    prices = (_price_path(historical_prices_path, ticker=ticker, sector_etf=sector_etf,
                          session_date=session_date or "", cutoff=cutoff)
              if cutoff else {"state": "UNKNOWN", "reason": "INVALID_EOD_CUTOFF"})
    if prices["state"] == "OBSERVED" and side:
        signed = 1 if side == "CALL" else -1
        sector_signed = signed * prices["sector_minus_spy_5"]
        ticker_signed = signed * prices["ticker_minus_sector_5"]
        sector_state = "SUPPORTS" if sector_signed > 0 else "OPPOSES" if sector_signed < 0 else "FLAT"
        ticker_state, ticker_signed = _ticker_link(ticker, sector_etf, prices["ticker_minus_sector_5"], side)
    else:
        sector_state = "UNKNOWN"
        sector_signed = None
        ticker_state, ticker_signed = _ticker_link(ticker, sector_etf, None, side)
    trigger = str(row.get("trigger_quality") or "").upper()
    # Governed book columns: target_price and invalidation_price. invalidation_spot
    # is an upstream producer alias that never reaches the frozen book.
    levels_present = (_positive(row.get("target_price")) is not None and
                      _positive(row.get("invalidation_price")) is not None)
    thesis_state = ("GOVERNED_LEVELS_MISSING" if not levels_present else
                    "STRONG_TRIGGER" if trigger == "STRONG" else
                    "OTHER_TRIGGER" if trigger else "UNKNOWN")
    bid = _nonnegative(row.get("contract_bid"))
    ask = _positive(row.get("contract_ask"))
    spread = round((ask - bid) / ask * 100, 4) if bid is not None and ask and bid <= ask else None
    volume = _nonnegative(row.get("contract_volume"))
    quote_at = _instant(row.get("selected_quote_timestamp_utc"))
    if not quote_at or not cutoff or quote_at > cutoff:
        contract_state = "QUOTE_TIMESTAMP_UNVERIFIED"
    else:
        contract_state = ("EOD_ACTIVE_QUOTE_TRAIT" if spread is not None and spread < 20 and
                          volume is not None and volume > 0 else
                          "EOD_OTHER_QUOTE_TRAIT" if spread is not None and volume is not None else "UNKNOWN")
    morning_fields = morning.get("fields") if morning else None
    eod_symbol = str(row.get("selected_contract_symbol") or row.get("contract_symbol") or "").replace("O:", "")
    live = morning_fields or {}
    live_symbol = str(live.get("live_contract_symbol") or live.get("morning_selected_contract_symbol") or "").replace("O:", "")
    live_bid, live_ask = _nonnegative(live.get("live_contract_bid")), _positive(live.get("live_contract_ask"))
    use_morning_quote = bool(live_symbol and live_symbol == eod_symbol and live_bid is not None and live_ask
                             and live_bid <= live_ask)
    eod_spread, eod_delta, eod_quote_at = spread, row.get("contract_delta"), row.get("selected_quote_timestamp_utc")
    if use_morning_quote:
        # XLU-D06 (ACK 2 Oct 2026): Morning refreshed the exact contract; that quote is the evidence.
        spread = round((live_ask - live_bid) / live_ask * 100, 4)
        contract_quote = {"delta": live.get("live_contract_delta"),
                          "quote_timestamp_utc": live.get("live_contract_quote_timestamp"),
                          "quote_freshness": live.get("quote_freshness"),
                          "quote_is_live_executable": str(live.get("quote_freshness") or "").upper() == "FRESH",
                          "evidence_ref": "MORNING_QUOTE"}
        contract_state = "MORNING_QUOTE_" + (str(live.get("quote_freshness") or "UNKNOWN").upper())
    else:
        contract_quote = {"delta": eod_delta, "quote_timestamp_utc": eod_quote_at, "quote_freshness": None,
                          "quote_is_live_executable": False, "evidence_ref": "EOD_BOOK"}
    # The governed Morning validation event publishes validation_transition
    # (THESIS_CONFIRMED, PENDING_TRIGGER, THESIS_INVALIDATED, DATA_DEFERRED, ...).
    morning_result = (morning_fields or {}).get("validation_transition")
    morning_state = str(morning_result).upper() if morning_result else "NOT_RUN_OR_NOT_ACCEPTED"
    return {
        "version": "interpreter_confluence_v1", "authority": "ADVISORY_ONLY",
        "side": side, "session_date": session_date,
        "sector": {"status": sector_state, "sector_etf": sector_etf or None,
                   "signed_sector_minus_spy_5": round(sector_signed, 8) if sector_signed is not None else None,
                   "macro_alignment_advisory": row.get("macro_sector_alignment") or None,
                   "evidence_ref": "PIT_PRICE_BARS" if prices["state"] == "OBSERVED" else "EOD_BOOK"},
        "ticker": {"status": ticker_state,
                   "signed_ticker_minus_sector_5": round(ticker_signed, 8) if ticker_signed is not None else None,
                   "catalyst_type": row.get("catalyst_type"),
                   "catalyst_date": row.get("catalyst_date"),
                   "catalyst_event_status": row.get("catalyst_event_status"),
                   "evidence_ref": "PIT_PRICE_BARS" if prices["state"] == "OBSERVED" else "EOD_BOOK"},
        "thesis": {"status": thesis_state, "trigger_quality": trigger or None,
                   "trigger_evidence": row.get("trigger_evidence"),
                   "target_price": row.get("target_price"),
                   "invalidation_price": row.get("invalidation_price"),
                   "evidence_ref": "EOD_BOOK"},
        "contract": {"status": contract_state, "contract_symbol": row.get("selected_contract_symbol") or row.get("contract_symbol"),
                     "spread_pct_ask": spread, "volume": volume,
                     "bid_size": _nonnegative(row.get("contract_bid_size")),
                     "ask_size": _nonnegative(row.get("contract_ask_size")),
                     **contract_quote,
                     "days_to_expiry": _days_to_expiry(eod_symbol, contract_quote["quote_timestamp_utc"]),
                     "eod_spread_pct_ask": eod_spread, "eod_delta": eod_delta,
                     "eod_quote_timestamp_utc": eod_quote_at},
        "morning": {"status": morning_state,
                    "current_price": (morning_fields or {}).get("validation_current_price"),
                    "validation_event_id": (morning_fields or {}).get("validation_event_id"),
                    "validation_reason": (morning_fields or {}).get("validation_reason"),
                    "refresh_required": morning.get("refresh_required") if morning else None,
                    "evidence_ref": "MORNING_HANDOFF" if morning else "EOD_BOOK"},
        "price_path": prices,
    }
