"""Historical replay study (ACK approval 28 Sep 2026; pre-registration
Enhancements/assessment/AVS_HISTORICAL_REPLAY_STUDY_PREREGISTRATION_20260929.md). Read-only.

Extends Enhancements/direction_evidence/discovery_replay_2022_2026.py (17 Sep; left unchanged because its output is
cited) for the ticker-edge study:
- runs the CURRENT production Discovery scan `avshunter_discovery_ULTIMATE.scan_ticker_ultimate` (after the 27 Sep
  SOR-001 Wyckoff/Crabel changes) on each ticker's bars truncated at the evaluation session (no future bars);
- the whole eligible universe (every ticker with >= 320 complete bars), not a sample;
- one GLOBAL calendar of evaluation sessions (every 5th trading session), so every signal has a same-session
  universe baseline;
- keeps every scalar output (numbers AND text labels) so the trigger and physics layers can be applied to the rows
  afterwards, plus the Discovery horizon (`assign_discovery_horizon`, pure);
- outcome: entry = next session's open; close/high/low relative to entry for hold days 1..40 (NaN where not yet
  observed). The data-quality skip uses PAST bars only (the 17 Sep script looked at the forward window: selection on
  future data); an extreme forward overnight gap (> 1.8x or < 0.55x) is flagged, not skipped.
Known hazards neutralised (subagent audit 29 Sep): df.attrs left empty (no date.today() composite decay); a copy
of the truncated frame is passed (the scan adds EMA columns). `is_stale`/`candidate_lane` are cosmetic under replay.

  venv\\Scripts\\python.exe Enhancements\\direction_evidence\\ticker_edge_replay_20260929.py OUT_DIR [WORKERS]
"""

from __future__ import annotations

import logging
import math
from multiprocessing import Pool
from pathlib import Path
import sqlite3
import sys
import time

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
PRICES = ROOT / "data" / "canonical" / "historical_prices.sqlite"
STEP, WARMUP, MAXH, MIN_BARS = 5, 260, 40, 320
_SESSIONS: set[str] = set()


def _init(sessions):
    global _SESSIONS
    _SESSIONS = set(sessions)


def _worker(ticker: str):
    sys.path.insert(0, str(ROOT))
    logging.disable(logging.CRITICAL)
    import avshunter_discovery_ULTIMATE as discovery
    cfg = discovery.UltimateConfig()
    engine = discovery.WyckoffEngine(min_bars=20)
    con = sqlite3.connect(f"file:{PRICES.as_posix()}?mode=ro", uri=True)
    df = pd.read_sql_query("SELECT trading_date AS date, open, high, low, close, volume FROM ohlcv_daily WHERE ticker = ? "
                           "AND bar_status = 'COMPLETE' ORDER BY trading_date", con, params=(ticker,))
    con.close()
    if len(df) < MIN_BARS:
        return [], []
    dates = df["date"].to_numpy()
    df["date"] = pd.to_datetime(df["date"])
    o, h, l, c = (df[k].to_numpy(dtype=float) for k in ("open", "high", "low", "close"))
    gap = o / np.r_[np.nan, c[:-1]]
    extreme = (gap > 1.8) | (gap < 0.55)
    rows, paths = [], []
    for end in range(WARMUP, len(df) - 1):
        if dates[end] not in _SESSIONS:
            continue
        past = c[end - WARMUP:end + 1]
        if np.any(past < 0.01) or np.any(np.abs(np.diff(np.log(past))) >= math.log(10)):
            continue                                   # data error in the PAST window only
        entry = o[end + 1]
        if not entry > 0:
            continue
        try:
            result = discovery.scan_ticker_ultimate(ticker, df.iloc[:end + 1].copy().reset_index(drop=True), cfg, engine)
        except Exception:
            continue
        if not result:
            continue
        row = {"ticker": ticker, "session": dates[end], "entry": float(entry)}
        for key, value in result.items():
            if isinstance(value, bool):
                row[f"x__{key}"] = float(value)
            elif isinstance(value, (int, float)) and value is not None and math.isfinite(float(value)):
                row[f"x__{key}"] = float(value)
            elif isinstance(value, str) and len(value) <= 80:
                row[f"l__{key}"] = value
        try:
            row["l__horizon_bucket_discovery"] = discovery.assign_discovery_horizon(dict(result)) or ""
        except Exception:
            row["l__horizon_bucket_discovery"] = "ERROR"
        j = slice(end + 1, min(end + 1 + MAXH, len(df)))
        n = j.stop - j.start
        pc = np.full(MAXH, np.nan, np.float32); ph = pc.copy(); pl = pc.copy()
        pc[:n], ph[:n], pl[:n] = c[j] / entry - 1, h[j] / entry - 1, l[j] / entry - 1
        row["extreme_forward_gap"] = bool(extreme[j].any())
        rows.append(row)
        paths.append(np.stack([pc, ph, pl]))
    return rows, paths


def main():
    out = Path(sys.argv[1])
    workers = int(sys.argv[2]) if len(sys.argv) > 2 else 6
    con = sqlite3.connect(f"file:{PRICES.as_posix()}?mode=ro", uri=True)
    tickers = [r[0] for r in con.execute("SELECT ticker FROM ohlcv_daily WHERE bar_status = 'COMPLETE' GROUP BY ticker "
                                         f"HAVING COUNT(*) >= {MIN_BARS} ORDER BY ticker")]
    sessions = [r[0] for r in con.execute("SELECT DISTINCT trading_date FROM ohlcv_daily ORDER BY trading_date")]
    con.close()
    sample_sessions = sessions[WARMUP::STEP]
    print(f"tickers eligible {len(tickers)}, evaluation sessions {len(sample_sessions)} "
          f"({sample_sessions[0]}..{sample_sessions[-1]}), workers {workers}", flush=True)
    started, rows, paths = time.time(), [], []
    with Pool(workers, initializer=_init, initargs=(sample_sessions,)) as pool:
        for i, (r, p) in enumerate(pool.imap_unordered(_worker, tickers, chunksize=4), 1):
            rows.extend(r); paths.extend(p)
            if i % 100 == 0:
                print(f"{i}/{len(tickers)} tickers, {len(rows)} rows, {time.time() - started:.0f}s", flush=True)
    out.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame(rows)
    frame.to_parquet(out / "replay_rows.parquet", index=False)
    np.save(out / "replay_paths.npy", np.stack(paths).astype(np.float32))
    print(f"done: {len(frame)} rows, {frame['session'].nunique()} sessions, {frame['ticker'].nunique()} tickers, "
          f"{time.time() - started:.0f}s", flush=True)


if __name__ == "__main__":
    main()
