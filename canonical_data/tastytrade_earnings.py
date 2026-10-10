"""Tastytrade earnings dates (output-trust item 9, D7-1), read from the shared market-metrics fetch.

Second earnings source beside MarketData (ACK 9 Oct 2026). The same call carries the dividend fields used for option
valuation (ACK 10 Oct 2026), so canonical_data.tastytrade_metrics fetches once and caches per session.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, Optional

from canonical_data.tastytrade_metrics import fetch_tastytrade_metrics
from domain.earnings_confirmation import TASTYTRADE_SOURCE, parse_tastytrade_earnings


def fetch_tastytrade_earnings(tickers: Iterable[str], *, as_of: date, cache_dir: Path | str | None = None,
                              broker_factory: Optional[Callable[[], Any]] = None, batch: int = 100) -> Dict[str, Dict[str, Any]]:
    metrics = fetch_tastytrade_metrics(tickers, as_of=as_of, cache_dir=cache_dir, broker_factory=broker_factory,
                                       batch=batch)
    out: Dict[str, Dict[str, Any]] = {}
    for symbol, entry in metrics.items():
        if entry.get("status") == "OK":
            out[symbol] = parse_tastytrade_earnings({"earnings": entry.get("earnings") or {}}, as_of=as_of)
        else:
            out[symbol] = {"state": "UNKNOWN", "reason": entry.get("reason") or "TASTYTRADE_UNAVAILABLE",
                           "source": TASTYTRADE_SOURCE}
    return out
