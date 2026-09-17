"""Item 4 step 2 (ACK 17 Sep 2026): point-in-time replay of discovery inputs across 2022-2026 (read-only).

Runs the production discovery scan `avshunter_discovery_ULTIMATE.scan_ticker_ultimate` on each ticker's price
history truncated at the evaluation session (no future bars), for a random sample of tickers and every 5th
session, and records its numeric outputs and direction labels together with forward log returns (1, 5, 10, 20
sessions) from the same price series. Macro-derived outputs are dropped (they read today's macro file: look-ahead).
Trivial baselines are added: past 1 / 5 / 20 / 60-session returns. DQ-12: windows containing a one-bar move of
10x or more, or sub-cent closes, are skipped.

Output: direction_replay_rows.parquet (one row per ticker-session).

  venv\\Scripts\\python.exe Enhancements\\direction_evidence\\discovery_replay_2022_2026.py
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
OUT = Path(__file__).resolve().parent / "direction_replay_rows.parquet"
SAMPLE_TICKERS, SEED, STEP, START, END_BUFFER, WORKERS = 600, 20260917, 5, "2022-03-01", 20, 6
HORIZONS = (1, 5, 10, 20)
LABEL_FIELDS = ("direction", "discovery_direction_preliminary", "repricing_direction", "precor_intent",
                "dominant_trend", "vwap_bias", "fusion_direction", "wyckoff_phase_bucket", "phase")
DROP_TOKENS = ("macro", "risk_on_off", "sector_tilt", "ticker_sector_alignment", "credit_risk", "bar_data_days_old",
               "stock_price", "entry_price", "stop_loss", "structural_stop", "EMA", "VWAP", "ATR_14", "dte", "tier",
               "invalidation_level", "prior_adjustment")


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
    if len(df) < 320:
        return []
    df["date"] = pd.to_datetime(df["date"])
    close = df["close"].to_numpy()
    logs = np.log(np.where(close > 0, close, np.nan))
    rows = []
    start_idx = int(np.searchsorted(df["date"].to_numpy(), np.datetime64(START)))
    for end in range(max(start_idx, 260), len(df) - END_BUFFER, STEP):
        window = slice(end - 260, end + 1 + max(HORIZONS))
        seg = close[window]
        if np.any(seg < 0.01) or np.any(np.abs(np.diff(np.log(seg))) >= math.log(10)):
            continue
        try:
            result = discovery.scan_ticker_ultimate(ticker, df.iloc[:end + 1].copy().reset_index(drop=True), cfg, engine)
        except Exception:
            continue
        if not result:
            continue
        row = {"ticker": ticker, "session": df.loc[end, "date"].date().isoformat()}
        for key, value in result.items():
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                continue
            if any(tok.lower() in key.lower() for tok in DROP_TOKENS):
                continue
            if value is not None and math.isfinite(float(value)):
                row[f"x__{key}"] = float(value)
        for key in LABEL_FIELDS:
            if isinstance(result.get(key), str):
                row[f"l__{key}"] = result[key]
        for lag in (1, 5, 20, 60):
            row[f"x__baseline_past_return_{lag}"] = float(logs[end] - logs[end - lag])
        for h in HORIZONS:
            row[f"fwd_{h}"] = float(logs[end + h] - logs[end])
        rows.append(row)
    return rows


def main():
    con = sqlite3.connect(f"file:{PRICES.as_posix()}?mode=ro", uri=True)
    tickers = [r[0] for r in con.execute("SELECT ticker FROM ohlcv_daily WHERE bar_status = 'COMPLETE' GROUP BY ticker "
                                         "HAVING COUNT(*) >= 320")]
    con.close()
    sample = sorted(np.random.default_rng(SEED).choice(tickers, size=min(SAMPLE_TICKERS, len(tickers)), replace=False))
    print(f"tickers eligible {len(tickers)}, sampled {len(sample)}", flush=True)
    started, rows = time.time(), []
    with Pool(WORKERS) as pool:
        for i, part in enumerate(pool.imap_unordered(_worker, sample, chunksize=4), 1):
            rows.extend(part)
            if i % 50 == 0:
                print(f"{i}/{len(sample)} tickers, {len(rows)} rows, {time.time() - started:.0f}s", flush=True)
    frame = pd.DataFrame(rows)
    frame.to_parquet(OUT, index=False)
    print(f"done: {len(frame)} rows, {frame['session'].nunique()} sessions, {frame['ticker'].nunique()} tickers, "
          f"{time.time() - started:.0f}s", flush=True)


if __name__ == "__main__":
    main()
