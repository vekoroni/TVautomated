"""Station inspections: integrity defects stop the line (output-trust item 10, part 10.3; C-2).

Design: Enhancements/phase7/ITEM10_CALIBRATION_AND_STATIONS_DESIGN_20261010.md. ACK's assembly line: each stage's part
is inspected right after the stage and an integrity defect is repaired there, not discovered in the Lab.

STOP checks (integrity invariants; each was zero on the healthy 8 Oct run before it was made STOP): unique and
non-blank tickers ("NAN" is a ticker), no ticker invented by a later stage, every lost ticker accounted for by the
drop-off audit, positive prices, sane quotes, a directed side equal to its governed direction, target and invalidation
on the correct sides, no timestamp in the future. REPORT checks (fill rates) never stop. Integrity only: a row-level
trade judgement is never a station defect. Enforcement is governed config (`station_inspection.enforce`).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional

import pandas as pd

PRICE_COLUMNS = ("signal_price", "underlying_price", "entry_price")
SIDE_COLUMNS = ("direction", "options_direction", "final_direction")
FILL_RATE_COLUMNS = ("direction", "signal_price", "contract_symbol", "contract_bid", "contract_ask", "target_price",
                     "invalidation_price", "thesis__readiness", "trade_lane")


class StationDefect(RuntimeError):
    """An integrity defect at a station: the line stops here with the station, check and rows."""


def station_policy() -> Dict[str, Any]:
    path = Path(__file__).resolve().parents[1] / "config" / "governed_constants_v1.json"
    return dict(json.loads(path.read_text(encoding="utf-8-sig"))["station_inspection"])


def _text(series: pd.Series) -> pd.Series:
    return series.astype(object).where(series.notna(), "").astype(str).str.strip()


def _num(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def inspect_station(station: str, frame: pd.DataFrame, *, run_id: str, previous_tickers: Optional[Iterable[str]],
                    accounted_tickers: Optional[Iterable[str]], now_utc: Any = None,
                    policy: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    pol = dict(station_policy() if policy is None else policy)
    d = frame.loc[:, ~frame.columns.duplicated()].reset_index(drop=True)
    tickers = _text(d["ticker"]).str.upper() if "ticker" in d else pd.Series([""] * len(d))
    defects: List[Dict[str, Any]] = []

    def stop(check: str, mask: pd.Series, note: str) -> None:
        if bool(mask.any()):
            defects.append({"check": check, "count": int(mask.sum()), "note": note,
                            "tickers": sorted(set(tickers[mask].tolist()))[:50]})

    stop("unique_tickers", tickers.duplicated(keep=False) & tickers.ne(""), "the same ticker appears more than once")
    stop("nonblank_tickers", tickers.eq(""), "a row without a ticker")
    if previous_tickers is not None:
        prev = {str(t).strip().upper() for t in previous_tickers}
        stop("no_invented_tickers", ~tickers.isin(prev) & tickers.ne(""), "a ticker the previous station never had")
        if accounted_tickers is not None:
            lost = sorted(prev - set(tickers) - {str(t).strip().upper() for t in accounted_tickers})
            if lost:
                defects.append({"check": "losses_accounted", "count": len(lost), "tickers": lost[:50],
                                "note": "tickers lost since the previous station with no drop-off record"})
    price_col = next((c for c in PRICE_COLUMNS if c in d), None)
    if price_col:
        px = _num(d[price_col])
        stop("positive_prices", px.notna() & (px <= 0), f"{price_col} not positive")
    if "contract_bid" in d and "contract_ask" in d:
        bid, ask = _num(d["contract_bid"]), _num(d["contract_ask"])
        stop("sane_quotes", (bid < 0) | (ask < 0) | (bid.notna() & ask.notna() & (bid > ask)), "negative or crossed quote")
    side_col = next((c for c in SIDE_COLUMNS if c in d), None)
    if side_col:
        side = _text(d[side_col]).str.upper()
        if "governed_direction" in d:
            gov = _text(d["governed_direction"]).str.upper()
            stop("side_matches_governed_direction", side.isin(["CALL", "PUT"]) & gov.isin(["CALL", "PUT"]) & side.ne(gov),
                 f"{side_col} differs from the governed direction record")
        if price_col and "target_price" in d and "invalidation_price" in d:
            px, tg, iv = _num(d[price_col]), _num(d["target_price"]), _num(d["invalidation_price"])
            both = px.notna() & tg.notna() & iv.notna()
            bad = (side.eq("CALL") & both & ~((iv < px) & (px < tg))) | (side.eq("PUT") & both & ~((tg < px) & (px < iv)))
            stop("levels_on_correct_sides", bad, "target or invalidation on the wrong side of the reference price")
    now = pd.Timestamp(now_utc) if now_utc is not None else pd.Timestamp.now(tz="UTC")
    now = now.tz_localize("UTC") if now.tzinfo is None else now
    horizon = now + pd.Timedelta(minutes=float(pol.get("future_tolerance_minutes", 15)))
    for col in [c for c in d.columns if str(c).endswith(("_timestamp_utc", "_at_utc"))]:
        ts = pd.to_datetime(d[col], errors="coerce", utc=True)
        stop("no_future_timestamps", ts > horizon, f"{col} later than the inspection time")
    stop_checks = set(pol.get("stop_checks") or [])
    stop_defects = [x for x in defects if x["check"] in stop_checks]
    return {"station": station, "run_id": run_id, "rows": int(len(d)), "inspected_at_utc": now.isoformat(),
            "stop_defects": stop_defects, "other_defects": [x for x in defects if x["check"] not in stop_checks],
            "report": {"fill_rates": {c: round(float(_text(d[c]).ne("").mean()), 4) if len(d) else None
                                      for c in FILL_RATE_COLUMNS if c in d}},
            "enforce": bool(pol.get("enforce", True))}


def enforce(report: Mapping[str, Any], policy: Optional[Mapping[str, Any]] = None) -> None:
    pol = dict(station_policy() if policy is None else policy)
    if not pol.get("enforce", True) or not report.get("stop_defects"):
        return
    detail = "; ".join(f"{d['check']} x{d['count']} ({', '.join(d['tickers'][:5])})" for d in report["stop_defects"])
    raise StationDefect(f"STATION_INTEGRITY_DEFECT at {report['station']} (run {report['run_id']}): {detail}")


def write_station_report(report: Mapping[str, Any], run_dir: Path | str) -> Path:
    path = Path(run_dir) / "diagnostics" / f"station_{report['station']}_{report['run_id']}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    return path
