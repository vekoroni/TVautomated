"""Tastytrade market metrics through the read-only broker bridge, cached per session (ACK 9-10 Oct 2026).

One call per run serves two readers: the earnings confirmation tiers (item 9) and the dividend yield for option
valuation (item 4; ACK 10 Oct: "use tastytrade for dividends instead of polygon"). Uses bridge.tastytrade_readonly_mcp
(read-only; broker OAuth environment) in batches of up to 100 symbols, retrying a rejected batch one symbol at a time.
Each entry keeps only the earnings and dividend blocks. Missing credentials or a failure leave every ticker
UNAVAILABLE with the reason - never "no earnings" or "no dividend". Credentials are never logged or returned.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, Optional, Tuple

DIVIDEND_KEYS = ("dividend-yield", "annual-dividend-per-share", "dividend-rate-per-share", "dividend-ex-date",
                 "dividend-pay-date", "dividend-updated-at")
DEFAULT_CACHE_DIR = Path(__file__).resolve().parents[1] / "data" / "cache" / "tastytrade_metrics"


def _unwrap(payload: Any) -> list:
    return list(payload.get("items", [])) if isinstance(payload, dict) else list(payload or [])


def _compact(item: Dict[str, Any]) -> Dict[str, Any]:
    return {"status": "OK", "earnings": dict(item.get("earnings") or {}),
            "dividend": {k: item.get(k) for k in DIVIDEND_KEYS if item.get(k) is not None},
            "updated_at": item.get("updated-at")}


def fetch_tastytrade_metrics(tickers: Iterable[str], *, as_of: date, cache_dir: Path | str | None = None,
                             broker_factory: Optional[Callable[[], Any]] = None,
                             batch: int = 100) -> Dict[str, Dict[str, Any]]:
    symbols = sorted({str(t).strip().upper() for t in tickers if str(t).strip()})
    cache_path = Path(cache_dir) / f"{as_of.isoformat()}.json" if cache_dir else None
    cached: Dict[str, Dict[str, Any]] = {}
    if cache_path and cache_path.exists():
        try:
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            cached = {}
    results = {s: cached[s] for s in symbols if s in cached}
    wanted = [s for s in symbols if s not in cached]
    if wanted:
        try:
            from bridge.tastytrade_readonly_mcp import (BrokerCredentialUnavailable, BrokerMcpError,
                                                        ReadOnlyTastytradeMcp)
        except Exception as exc:                                   # noqa: BLE001 - stated per ticker
            return {**results, **{s: {"status": "UNAVAILABLE", "reason": f"BRIDGE_UNAVAILABLE:{type(exc).__name__}"}
                                  for s in wanted}}
        items: Dict[str, Any] = {}
        reason = None
        try:
            with (broker_factory or ReadOnlyTastytradeMcp)() as broker:
                for start in range(0, len(wanted), batch):
                    chunk = wanted[start:start + batch]
                    try:
                        found = _unwrap(broker.market_metrics(chunk))
                    except BrokerCredentialUnavailable:
                        raise
                    except BrokerMcpError:
                        found = []
                        for symbol in chunk:
                            try:
                                found.extend(_unwrap(broker.market_metrics([symbol])))
                            except BrokerCredentialUnavailable:
                                raise
                            except BrokerMcpError:
                                continue
                    for item in found:
                        items[str(item.get("symbol") or "").upper()] = item
        except BrokerCredentialUnavailable:
            reason = "TASTYTRADE_CREDENTIALS_UNAVAILABLE"
        except Exception as exc:                                   # noqa: BLE001 - stated per ticker
            reason = f"TASTYTRADE_FETCH_FAILED:{type(exc).__name__}"
        for symbol in wanted:
            results[symbol] = (_compact(items[symbol]) if symbol in items else
                               {"status": "UNAVAILABLE", "reason": reason or "TASTYTRADE_NO_METRICS_FOR_SYMBOL"})
    if cache_path:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        keep = {**cached, **{s: r for s, r in results.items() if r.get("status") == "OK"}}
        cache_path.write_text(json.dumps(keep, sort_keys=True), encoding="utf-8")
    return results


def latest_cached_metrics(cache_dir: Path | str | None, *, as_of: date, max_age_days: int = 7
                          ) -> Tuple[Dict[str, Dict[str, Any]], Optional[str]]:
    """The newest session cache on or before ``as_of`` within ``max_age_days`` (the Morning reads the Evening's)."""
    folder = Path(cache_dir) if cache_dir else DEFAULT_CACHE_DIR
    if not folder.is_dir():
        return {}, None
    best = None
    for path in folder.glob("*.json"):
        try:
            day = datetime.fromisoformat(path.stem).date()
        except ValueError:
            continue
        if as_of - timedelta(days=max_age_days) <= day <= as_of and (best is None or day > best[0]):
            best = (day, path)
    if best is None:
        return {}, None
    try:
        return json.loads(best[1].read_text(encoding="utf-8")), best[0].isoformat()
    except (OSError, ValueError):
        return {}, None
