"""Dividend yield for option valuation, from tastytrade (output-trust item 4; ACK 10 Oct 2026: "use tastytrade for
dividends instead of polygon").

The Evening's tastytrade market-metrics call (made for the earnings tiers, canonical_data.tastytrade_metrics) carries
dividend-yield, annual-dividend-per-share, dividend-rate-per-share and the next ex-dividend date. Precedence:
the provider's yield; else annual dividend per share / spot; an explicit zero rate is a measured none; a per-payment
rate alone is not annualised by guessing the frequency (ASSUMED_ZERO, stated). Missing data is ASSUMED_ZERO with the
reason - never a silent zero. The next ex-date is carried in the basis for the discrete-dividend step.
"""
from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Any, Mapping, Optional, Tuple

from canonical_data.tastytrade_metrics import latest_cached_metrics


def _num(value: Any) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number else None


def _day(value: Any) -> Optional[date]:
    try:
        return datetime.fromisoformat(str(value)[:10]).date()
    except (TypeError, ValueError):
        return None


def dividend_from_metrics(dividend: Mapping[str, Any], *, spot: Any, as_of: date | str) -> Tuple[Optional[float], str]:
    """(continuous yield, basis) from one tastytrade dividend block."""
    as_of_day = as_of if isinstance(as_of, date) else _day(as_of)
    block = dict(dividend or {})
    if not block:
        return None, "ASSUMED_ZERO:TASTYTRADE_NO_DIVIDEND_FIELDS"
    ex = _day(block.get("dividend-ex-date"))
    next_ex = f":next_ex {ex.isoformat()}" if ex and as_of_day and ex > as_of_day else ""
    stamp = str(block.get("dividend-updated-at") or "")[:10]
    yield_ = _num(block.get("dividend-yield"))
    if yield_ is not None and yield_ >= 0:
        return yield_, f"DIVIDEND_YIELD_TASTYTRADE:{stamp or 'time not recorded'}{next_ex}"
    annual, px = _num(block.get("annual-dividend-per-share")), _num(spot)
    if annual is not None and annual > 0 and px and px > 0:
        return annual / px, f"DIVIDEND_ANNUAL_PER_SHARE_TASTYTRADE:{annual:g}/{px:g}{next_ex}"
    rate = _num(block.get("dividend-rate-per-share"))
    if (rate == 0.0 or annual == 0.0) and not next_ex:
        return 0.0, "DIVIDEND_NONE_TASTYTRADE"
    return None, "ASSUMED_ZERO:TASTYTRADE_YIELD_NOT_PROVIDED"


def dividend_inputs(ticker: Any, *, as_of: Any, spot: Any, cache_dir: Path | str | None = None) -> dict:
    """The valuation engine's dividend arguments for one ticker, from the newest tastytrade metrics cache within
    7 days (the Morning reads the Evening's). Never raises; the basis states what was missing."""
    day = _day(as_of) or date.today()
    try:
        metrics, cache_day = latest_cached_metrics(cache_dir, as_of=day)
    except Exception as exc:                                      # noqa: BLE001 - stated, never silent
        return {"dividend_yield": None, "dividend_basis": f"ASSUMED_ZERO:METRICS_CACHE_ERROR:{type(exc).__name__}"}
    if cache_day is None:
        return {"dividend_yield": None, "dividend_basis": "ASSUMED_ZERO:NO_TASTYTRADE_METRICS_CACHE"}
    entry = metrics.get(str(ticker or "").strip().upper())
    if not entry or entry.get("status") != "OK":
        return {"dividend_yield": None, "dividend_basis": f"ASSUMED_ZERO:NOT_FETCHED (metrics {cache_day})"}
    value, basis = dividend_from_metrics(entry.get("dividend") or {}, spot=spot, as_of=day)
    return {"dividend_yield": value, "dividend_basis": f"{basis} (metrics {cache_day})"}
