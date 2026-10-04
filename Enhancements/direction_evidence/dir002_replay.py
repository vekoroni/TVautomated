"""DIR-002 offline replay harness (R-1, R-2, R-3, R-4, R-5 support).

Offline only: reads the canonical completed-bar database read-only and the
stored run artefacts; never calls a provider, never writes pipeline data.

Functions
- ``replay_stored_run``: re-run ``scan_ticker_ultimate`` on bars cut at a stored
  run's last completed session and diff against the stored Discovery CSV (R-1/R-3).
- ``build_panel``: point-in-time historical panel of Discovery rows at dated
  cuts with forward 1-20 session outcomes (R-4/R-5 and policy calibration).
- ``reflect_bars``: log-space reflection used by the population mirror (R-2).

Point-in-time caveat (stated in every receipt): the canonical store keeps the
current revision of each bar; bar revisions made after a cut are not
reconstructed. Universe membership is today's universe (survivorship).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import math
import os
import sqlite3
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DB_PATH = ROOT / "data" / "canonical" / "historical_prices.sqlite"
ADJUSTMENT = "POLYGON_SPLIT_ADJUSTED"

KEEP_COLUMNS = [
    "ticker", "tier", "stock_price", "direction", "discovery_direction_preliminary",
    "discovery_direction_status", "discovery_direction_basis", "direction_authority",
    "stop_loss", "structural_stop_source", "structural_target", "structural_target_source",
    "governed_invalidation_spot", "governed_invalidation_source", "rr_underlying",
    "current_phase", "dominant_event", "control_state", "precor_intent", "precor_intent_raw",
    "precor_phase", "wyckoff_mode", "fusion_direction", "composite_score", "lift_proxy_score",
    "wyckoff_phase_bucket",
]
KEEP_PREFIXES = ("sym_", "thesis__", "shadow_", "bull_", "bear_", "legacy_", "side_")
KEEP_EXACT = {"geometry_status", "target_state"}


def read_bars(ticker: str, end_date: str | None = None) -> pd.DataFrame:
    """Read completed daily bars directly, read-only (no WAL writes)."""
    uri = f"file:{DB_PATH.as_posix()}?mode=ro"
    with sqlite3.connect(uri, uri=True) as conn:
        sql = (
            "SELECT trading_date AS date, open, high, low, close, volume FROM ohlcv_daily "
            "WHERE ticker=? AND adjustment_convention=? AND bar_status='COMPLETE'"
        )
        params: list = [ticker.upper(), ADJUSTMENT]
        if end_date:
            sql += " AND trading_date<=?"
            params.append(end_date)
        frame = pd.read_sql_query(sql + " ORDER BY trading_date", conn, params=params)
    frame["date"] = pd.to_datetime(frame["date"])
    return frame


def _attrs(frame: pd.DataFrame) -> pd.DataFrame:
    frame.attrs["data_source"] = "CANONICAL_HISTORICAL_PRICE_DB"
    frame.attrs["data_as_of"] = str(frame["date"].iloc[-1].date()) if len(frame) else ""
    return frame


def reflect_bars(frame: pd.DataFrame, reference: float | None = None) -> pd.DataFrame:
    """Reflect OHLC in log space about K (default: last close); volume unchanged."""
    k = float(frame["close"].iloc[-1]) if reference is None else float(reference)
    out = frame.copy()
    out["open"] = k * k / frame["open"]
    out["close"] = k * k / frame["close"]
    out["high"] = k * k / frame["low"]
    out["low"] = k * k / frame["high"]
    out.attrs.update(frame.attrs)
    return out


def _compact(row: dict | None) -> dict | None:
    if row is None:
        return None
    keep = {}
    for key, value in row.items():
        if key in KEEP_COLUMNS or key in KEEP_EXACT or key.startswith(KEEP_PREFIXES):
            if isinstance(value, (list, dict)):
                value = json.dumps(value, sort_keys=True, default=str)
            keep[key] = value
    return keep


_ENGINE = None
_CFG = None


def _scanner():
    global _ENGINE, _CFG
    if _ENGINE is None:
        logging.disable(logging.CRITICAL)
        import avshunter_discovery_ULTIMATE as discovery

        _CFG = discovery.UltimateConfig()
        _ENGINE = discovery.WyckoffEngine(min_bars=20)
    import avshunter_discovery_ULTIMATE as discovery

    return discovery, _CFG, _ENGINE


def scan(ticker: str, frame: pd.DataFrame) -> tuple[dict | None, str]:
    discovery, cfg, engine = _scanner()
    diagnostic: dict = {}
    try:
        row = discovery.scan_ticker_ultimate(
            ticker, _attrs(frame.copy()), cfg, engine, eligibility_diagnostic=diagnostic
        )
    except Exception as exc:  # recorded, never hidden
        return None, f"ERROR:{type(exc).__name__}:{exc}"[:200]
    return _compact(row), diagnostic.get("reason_code", "SURVIVE" if row else "NO_SIGNAL")


def forward_outcomes(frame: pd.DataFrame, index: int, horizons=(1, 5, 10, 20)) -> dict:
    """Forward path from the close of bar ``index`` (log units, σ = prior 20d)."""
    close = frame["close"].to_numpy(float)
    high = frame["high"].to_numpy(float)
    low = frame["low"].to_numpy(float)
    out: dict = {"cut_close": close[index]}
    logret = np.diff(np.log(close[max(0, index - 20): index + 1]))
    sigma = float(np.std(logret, ddof=1)) if len(logret) >= 15 else float("nan")
    out["sigma_d"] = sigma
    available = len(close) - 1 - index
    out["forward_sessions_available"] = int(available)
    for h in horizons:
        if available >= h:
            out[f"ret_{h}"] = math.log(close[index + h] / close[index])
        else:
            out[f"ret_{h}"] = float("nan")
    if available >= 20:
        path_hi = np.log(high[index + 1: index + 21] / close[index])
        path_lo = np.log(low[index + 1: index + 21] / close[index])
        out["mfe_up_20"] = float(path_hi.max())
        out["mfe_dn_20"] = float(path_lo.min())
        # First passage of ±1σ√20 barriers; same-bar double touch = AMBIGUOUS.
        barrier = sigma * math.sqrt(20) if sigma == sigma else float("nan")
        first = "NEITHER"
        for day in range(20):
            up = path_hi[day] >= barrier
            dn = path_lo[day] <= -barrier
            if up and dn:
                first = "AMBIGUOUS"
                break
            if up:
                first = "UP"
                break
            if dn:
                first = "DOWN"
                break
        out["first_passage_1sig"] = first
    else:
        out["mfe_up_20"] = out["mfe_dn_20"] = float("nan")
        out["first_passage_1sig"] = "CENSORED"
    return out


def _panel_worker(args: tuple) -> list[dict]:
    ticker, cut_dates, mirror = args
    frame = read_bars(ticker)
    if frame.empty:
        return []
    dates = frame["date"].dt.strftime("%Y-%m-%d").tolist()
    position = {d: i for i, d in enumerate(dates)}
    rows: list[dict] = []
    for cut in cut_dates:
        index = position.get(cut)
        if index is None or index < 260:
            continue
        sub = frame.iloc[: index + 1].reset_index(drop=True)
        record = {"ticker": ticker, "cut_date": cut, "bars": index + 1}
        row, reason = scan(ticker, sub)
        record["outcome"] = reason
        if row:
            record.update({f"o__{k}": v for k, v in row.items() if k != "ticker"})
        if mirror:
            mrow, mreason = scan(ticker, reflect_bars(sub))
            record["m__outcome"] = mreason
            if mrow:
                record.update({f"m__{k}": v for k, v in mrow.items() if k != "ticker"})
        record.update(forward_outcomes(frame, index))
        rows.append(record)
    return rows


def trading_calendar(reference: str = "SPY") -> list[str]:
    return read_bars(reference)["date"].dt.strftime("%Y-%m-%d").tolist()


def select_tickers(n: int, seed: str = "dir002-panel-v1") -> list[str]:
    universe = pd.read_csv(ROOT / "config" / "tickers.csv")
    column = "ticker" if "ticker" in universe.columns else universe.columns[0]
    tickers = sorted({str(t).strip().upper() for t in universe[column].dropna()})
    ranked = sorted(tickers, key=lambda t: hashlib.sha256(f"{seed}:{t}".encode()).hexdigest())
    return ranked[:n]


def build_panel(tickers: Iterable[str], cuts: list[str], out: Path, mirror: bool, workers: int) -> None:
    jobs = [(t, cuts, mirror) for t in tickers]
    done = 0
    with ProcessPoolExecutor(max_workers=workers) as pool, out.open("a", encoding="utf-8") as handle:
        for rows in pool.map(_panel_worker, jobs, chunksize=1):
            for row in rows:
                handle.write(json.dumps(row, default=str) + "\n")
            done += 1
            if done % 25 == 0:
                print(f"panel tickers done {done}/{len(jobs)}", flush=True)
                handle.flush()


def replay_stored_run(run_id: str, workers: int, out: Path, limit: int | None = None) -> None:
    run_dir = ROOT / "data" / "output" / "runs" / run_id
    meta = json.loads((run_dir / "run_meta.json").read_text(encoding="utf-8"))
    session = meta["dynamic_plan"]["last_completed_session"]
    lifecycle = pd.read_csv(run_dir / "discovery" / f"discovery_lifecycle_{run_id}.csv")
    tickers = sorted(lifecycle["ticker"].astype(str).str.upper().unique())
    if limit:
        tickers = tickers[:limit]
    with ProcessPoolExecutor(max_workers=workers) as pool, out.open("w", encoding="utf-8") as handle:
        for rows in pool.map(_replay_one, [(t, session) for t in tickers], chunksize=4):
            handle.write(json.dumps(rows, default=str) + "\n")


def _replay_one(args: tuple) -> dict:
    ticker, session = args
    frame = read_bars(ticker, end_date=session)
    record = {"ticker": ticker, "cut_date": session, "bars": len(frame)}
    if frame.empty or frame["date"].iloc[-1].strftime("%Y-%m-%d") != session:
        record["outcome"] = "NO_BAR_AT_SESSION"
        return record
    row, reason = scan(ticker, frame)
    record["outcome"] = reason
    if row:
        record.update({f"o__{k}": v for k, v in row.items() if k != "ticker"})
    return record


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("panel")
    p.add_argument("--tickers", type=int, default=500)
    p.add_argument("--start", default="2022-09-01")
    p.add_argument("--end", default="2026-08-28")
    p.add_argument("--step", type=int, default=10)
    p.add_argument("--mirror", action="store_true")
    p.add_argument("--workers", type=int, default=5)
    p.add_argument("--out", required=True)
    r = sub.add_parser("replay")
    r.add_argument("--run-id", required=True)
    r.add_argument("--workers", type=int, default=5)
    r.add_argument("--limit", type=int)
    r.add_argument("--out", required=True)
    args = parser.parse_args()
    if args.cmd == "panel":
        calendar = [d for d in trading_calendar() if args.start <= d <= args.end]
        cuts = calendar[:: args.step]
        build_panel(select_tickers(args.tickers), cuts, Path(args.out), args.mirror, args.workers)
    else:
        replay_stored_run(args.run_id, args.workers, Path(args.out), args.limit)


if __name__ == "__main__":
    main()
