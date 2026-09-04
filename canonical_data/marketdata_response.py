"""Recorded-response normalisation for MarketData option observations."""

from __future__ import annotations

from datetime import datetime, timezone
import math
from typing import Any, Mapping

import pandas as pd

from contracts.long_option_policy import quote_spread_fraction

from .option_identity import normalise_occ_symbol, parse_occ_symbol


CHAIN_V2_COLUMNS = (
    "underlying", "symbol", "right", "strike", "expiration_date", "dte",
    "bid", "ask", "mid", "bid_size", "ask_size", "last", "spread_pct",
    "open_interest", "volume", "implied_vol", "delta", "gamma", "theta",
    "vega", "underlying_price", "contract_multiplier", "quote_timestamp_utc",
    "quote_source", "quote_freshness", "quote_quality", "bid_size_quality",
    "ask_size_quality", "quality_flags",
)


def _values(payload: Mapping[str, Any], key: str, count: int) -> list[Any]:
    raw = payload.get(key)
    if isinstance(raw, (list, tuple)):
        values = list(raw)
        if len(values) in {0, count}:
            return values or [None] * count
        if len(values) == 1:
            return values * count
        raise ValueError(f"incompatible MarketData parallel-array length for {key}: {len(values)} != {count}")
    return [raw] * count


def _number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _size(value: Any) -> tuple[int | None, str]:
    if value is None or str(value).strip().upper() in {"", "NAN", "NONE", "NULL"}:
        return None, "MISSING"
    number = _number(value)
    if number is None or number < 0 or not float(number).is_integer():
        raise ValueError(f"invalid displayed size: {value!r}")
    integer = int(number)
    return integer, "OBSERVED_ZERO" if integer == 0 else "OBSERVED_POSITIVE"


def _timestamp(value: Any) -> str | None:
    if value is None:
        return None
    try:
        number = _number(value)
        if number is not None and str(value).strip().replace(".", "", 1).isdigit():
            unit = "ns" if abs(number) >= 1e17 else "ms" if abs(number) >= 1e11 else "s"
            parsed = pd.to_datetime(number, unit=unit, utc=True)
        else:
            parsed = pd.Timestamp(value)
            if parsed.tzinfo is None:
                return None
            parsed = parsed.tz_convert("UTC")
        return parsed.to_pydatetime().astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    except Exception:
        return None


def _quote(bid_raw: Any, ask_raw: Any, mid_raw: Any) -> tuple[float | None, float | None, float | None, float | None, str, tuple[str, ...]]:
    bid, ask, mid = _number(bid_raw), _number(ask_raw), _number(mid_raw)
    flags: list[str] = []
    if bid is not None and bid < 0 or ask is not None and ask < 0:
        raise ValueError(f"negative quote: bid={bid} ask={ask}")
    if bid is not None and ask is not None and bid > ask:
        flags.append("CROSSED_QUOTE")
        quality = "INVALID"
    elif bid == 0 and ask is not None and ask > 0:
        mid = ask / 2.0
        quality = "ONE_SIDED"
        flags.append("ZERO_BID")
    elif bid is not None and ask is not None and bid > 0 and ask > 0:
        mid = (bid + ask) / 2.0
        quality = "TWO_SIDED"
    else:
        quality = "INCOMPLETE"
    # A crossed quote is retained for audit evidence, but it must never be
    # represented as a negative spread.  Downstream rankers historically
    # interpreted that negative number as a liquidity bonus.  ``None`` keeps
    # the invalid observation visible while preventing it from masquerading as
    # executable economics.
    spread_pct = (
        quote_spread_fraction(bid, ask)
        if quality != "INVALID"
        else None
    )
    return bid, ask, mid, spread_pct, quality, tuple(flags)


def parse_marketdata_option_response(
    payload: Mapping[str, Any], *, ticker: str, quote_source: str = "MARKETDATA"
) -> pd.DataFrame:
    """Normalise scalar or parallel-array option responses into option_chain_v2."""
    if str(payload.get("s", "")).lower() != "ok":
        if str(payload.get("s", "")).lower() in {"no_data", "nodata"}:
            return pd.DataFrame(columns=CHAIN_V2_COLUMNS)
        raise ValueError(f"MarketData response status is not ok: {payload.get('s')!r}")
    symbols_raw = payload.get("optionSymbol")
    symbols = list(symbols_raw) if isinstance(symbols_raw, (list, tuple)) else [symbols_raw]
    symbols = [value for value in symbols if value not in {None, ""}]
    if not symbols:
        return pd.DataFrame(columns=CHAIN_V2_COLUMNS)
    count = len(symbols)
    arrays = {key: _values(payload, key, count) for key in (
        "side", "strike", "expiration", "dte", "bid", "ask", "mid", "bidSize",
        "askSize", "last", "openInterest", "volume", "iv", "delta", "gamma",
        "theta", "vega", "underlyingPrice", "contractMultiplier", "multiplier", "updated",
    )}
    rows: list[dict[str, Any]] = []
    for index, raw_symbol in enumerate(symbols):
        symbol = normalise_occ_symbol(raw_symbol)
        identity = parse_occ_symbol(symbol)
        bid_size, bid_size_quality = _size(arrays["bidSize"][index])
        ask_size, ask_size_quality = _size(arrays["askSize"][index])
        bid, ask, mid, spread_pct, quote_quality, flags = _quote(
            arrays["bid"][index], arrays["ask"][index], arrays["mid"][index]
        )
        expiry = identity.expiry.isoformat()
        raw_expiry = arrays["expiration"][index]
        if raw_expiry:
            try:
                expiry = pd.to_datetime(raw_expiry, unit="s", utc=True).date().isoformat() if _number(raw_expiry) is not None else pd.Timestamp(raw_expiry).date().isoformat()
            except Exception:
                pass
        multiplier = _number(arrays["contractMultiplier"][index]) or _number(arrays["multiplier"][index])
        rows.append({
            "underlying": ticker.strip().upper(), "symbol": symbol,
            "right": "C" if identity.side == "CALL" else "P", "strike": identity.strike,
            "expiration_date": expiry, "dte": _number(arrays["dte"][index]),
            "bid": bid, "ask": ask, "mid": mid, "bid_size": bid_size,
            "ask_size": ask_size, "last": _number(arrays["last"][index]),
            "spread_pct": spread_pct, "open_interest": _number(arrays["openInterest"][index]),
            "volume": _number(arrays["volume"][index]), "implied_vol": _number(arrays["iv"][index]),
            "delta": _number(arrays["delta"][index]), "gamma": _number(arrays["gamma"][index]),
            "theta": _number(arrays["theta"][index]), "vega": _number(arrays["vega"][index]),
            "underlying_price": _number(arrays["underlyingPrice"][index]),
            "contract_multiplier": multiplier, "quote_timestamp_utc": _timestamp(arrays["updated"][index]),
            "quote_source": quote_source, "quote_freshness": "UNASSESSED",
            "quote_quality": quote_quality, "bid_size_quality": bid_size_quality,
            "ask_size_quality": ask_size_quality, "quality_flags": "|".join(flags),
        })
    return pd.DataFrame(rows, columns=CHAIN_V2_COLUMNS)


def parse_exact_option_quote(payload: Mapping[str, Any], *, ticker: str, symbol: str) -> dict[str, Any]:
    frame = parse_marketdata_option_response(payload, ticker=ticker)
    canonical = normalise_occ_symbol(symbol)
    match = frame.loc[frame["symbol"] == canonical]
    if len(match) != 1:
        raise ValueError(f"exact quote response did not contain exactly one {canonical} row")
    record = match.iloc[0].to_dict()
    if record["quote_quality"] == "INVALID":
        raise ValueError("crossed exact option quote is invalid")
    record["executable_now"] = record["quote_quality"] == "TWO_SIDED"
    return record
