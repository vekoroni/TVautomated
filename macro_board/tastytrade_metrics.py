"""Tastytrade market metrics (IV index/rank/percentile, HV, beta, per-expiry IV) for the board.

Fetched read-only through the repo's broker bridge (``bridge.tastytrade_readonly_mcp``),
which needs the broker OAuth environment. The board itself only reads the dated snapshot
file, so a missing broker session shows as MISSING/STALE, never as neutral values.

Units: the API mixes 0-1 decimals (IV index, ranks, per-expiry IV) with percentages (HV,
IV-HV difference). ``normalise`` converts everything to percent exactly once.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

_DECIMAL_TO_PCT = {
    "implied-volatility-index": "iv_index_pct",
    "implied-volatility-index-rank": "iv_rank_pct",
    "implied-volatility-percentile": "iv_percentile_pct",
    "implied-volatility-index-5-day-change": "iv_index_5d_change_pct",
    "liquidity-rank": "liquidity_rank_pct",
}
_ALREADY_PCT = {
    "historical-volatility-30-day": "hv30_pct",
    "historical-volatility-60-day": "hv60_pct",
    "historical-volatility-90-day": "hv90_pct",
    "iv-hv-30-day-difference": "iv_hv_diff_pct",
    "implied-volatility-30-day": "iv30_pct",
}
_PLAIN = {"beta": "beta", "corr-spy-3month": "corr_spy_3m", "liquidity-rating": "liquidity_rating"}


def _num(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def normalise(raw: Mapping) -> dict:
    out: dict[str, Any] = {"symbol": raw.get("symbol"),
                           "updated_at": raw.get("implied-volatility-updated-at") or raw.get("updated-at")}
    for key, name in _DECIMAL_TO_PCT.items():
        value = _num(raw.get(key))
        out[name] = None if value is None else round(value * 100.0, 4)
    for key, name in {**_ALREADY_PCT, **_PLAIN}.items():
        value = _num(raw.get(key))
        out[name] = None if value is None else round(value, 4)
    term = []
    for item in raw.get("option-expiration-implied-volatilities") or []:
        if item.get("option-chain-type") not in (None, "Standard"):
            continue                                   # adjusted (post-split) chains: non-standard deliverable
        iv = _num(item.get("implied-volatility"))
        if item.get("expiration-date") and iv is not None:
            term.append({"expiry": item["expiration-date"], "iv_pct": round(iv * 100.0, 4)})
    out["term"] = term
    return out


def fetch(symbols: Sequence[str], out_dir: Path, *, batch: int = 20, broker_factory=None) -> dict:
    """Fetch through the read-only bridge and write ``tastytrade_metrics_<date>.json``.

    A batch the server rejects (e.g. a leveraged ETF whose non-standard chain fails the MCP
    server's own output schema) is retried one symbol at a time, so one bad symbol never
    loses the rest; rejected symbols are listed as skipped. Missing credentials fail fast."""
    from bridge.tastytrade_readonly_mcp import BrokerCredentialUnavailable, BrokerMcpError, ReadOnlyTastytradeMcp

    factory = broker_factory or ReadOnlyTastytradeMcp
    items: list[dict] = []
    skipped: list[str] = []

    def unwrap(payload):
        return list(payload.get("items", [])) if isinstance(payload, Mapping) else list(payload)

    try:
        with factory() as broker:
            for start in range(0, len(symbols), batch):
                chunk = list(symbols[start:start + batch])
                try:
                    items.extend(unwrap(broker.market_metrics(chunk)))
                except BrokerCredentialUnavailable:
                    raise
                except BrokerMcpError:
                    for symbol in chunk:
                        try:
                            items.extend(unwrap(broker.market_metrics([symbol])))
                        except BrokerCredentialUnavailable:
                            raise
                        except BrokerMcpError:
                            skipped.append(symbol)
    except (BrokerMcpError, ValueError, OSError) as exc:
        return {"status": "FAILED", "error": f"{type(exc).__name__}: {str(exc)[:160]}"}
    if not items:
        return {"status": "FAILED", "error": "no metrics returned", "skipped": skipped}
    report = write_snapshot(items, out_dir, source="bridge.tastytrade_readonly_mcp", skipped=skipped)
    return {**report, "skipped": skipped}


def write_snapshot(items: Sequence[Mapping], out_dir: Path, *, source: str, skipped: Sequence[str] = ()) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    record = {"fetched_utc": now.isoformat(timespec="seconds"), "source": source, "skipped": list(skipped),
              "items": list(items)}
    path = out_dir / f"tastytrade_metrics_{now.date().isoformat()}.json"
    path.write_text(json.dumps(record), encoding="utf-8")
    return {"status": "OK", "count": len(items), "file": path.name}


def load_latest(out_dir: Path, now: datetime, max_age_hours: float) -> dict:
    files = sorted(out_dir.glob("tastytrade_metrics_*.json")) if out_dir.exists() else []
    if not files:
        return {"status": "MISSING", "metrics": {}}
    record = json.loads(files[-1].read_text(encoding="utf-8"))
    fetched = datetime.fromisoformat(record["fetched_utc"])
    age = (now - fetched).total_seconds() / 3600.0
    metrics = {item.get("symbol"): normalise(item) for item in record.get("items", []) if item.get("symbol")}
    return {"status": "FRESH" if age <= max_age_hours else "STALE", "fetched_utc": record["fetched_utc"],
            "skipped": record.get("skipped", []),
            "age_hours": round(age, 1), "source": record.get("source"), "file": files[-1].name, "metrics": metrics}
