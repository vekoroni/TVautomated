#!/usr/bin/env python3
"""
avshunter_db_update.py
======================
AVSHUNTER Actuarial Database Gap-Fill Script
Schema: 2.2.0 | Bucket schema: 1.1.0

WHAT THIS SCRIPT DOES
---------------------
1.  Patches the existing DB in-place (structure_quality fix, schema normalisation)
2.  Fetches missing date ranges from Polygon to add new rows
3.  Re-tags all SIDEWAYS N/A rows to SIDEWAYS_BUILDING / SIDEWAYS_RANGING
4.  Recomputes state_hash for every row using the correct underscore separator
5.  Deduplicates, cleans, and saves the final merged parquet

GAPS CLOSED
-----------
  CRITICAL  Temporal coverage:  0.8yr → 4yr  (adds RISK_ON, EXPANSION, DISTRIBUTION, 2025 YTD)
  CRITICAL  RISK_ON regime:     absent → populated  (2023 bull, 2024 rate-cut rally)
  HIGH      DISTRIBUTION wyckoff: absent → populated  (2022 bear market tops)
  HIGH      BIG_WIN outcomes:   absent → populated  (20d returns >10%)
  MEDIUM    EXPANSION vol:      absent → populated  (2022 vol spikes, 2024 breakouts)
  MEDIUM    STRONG ADX:         absent → populated  (trending markets)
  MEDIUM    LATE maturity:      absent → populated  (extended trend setups)
  FIX       Hash separator:     pipe|  → underscore_  (rebuild_v2_2 bug corrected)
  2026-04   Universe:           clean_universe__with_sector.csv → polygon_liquid_universe.csv
  2026-04   Rate limit:         5/min (free tier) → 500/min (Starter unlimited plan)
  2026-04   New fetch window:   2024-11-01 → 2025-04-24 (2025 YTD TRANSITIONAL regime)
  2026-04   63 new tickers added to universe (leveraged ETFs, international, crypto proxies)

DATE RANGES FETCHED (additive to existing DB)
---------------------------------------------
  2022-01-01 → 2022-12-31  RISK_OFF peak, DISTRIBUTION wyckoff, bear EXPANSION
  2023-01-01 → 2023-12-31  RISK_ON recovery, MARKUP D/E setups
  2024-01-01 → 2024-11-30  RISK_ON continuation, rate-cut rally, LATE maturity
  2024-11-01 → 2025-04-24  2025 YTD: TRANSITIONAL, tariff volatility, new universe tickers
  (rows already in DB are skipped via ticker+date dedup — safe to re-run)

UNIVERSE
--------
  polygon_liquid_universe.csv  — 1,999 tickers (updated 2026-04-24)
  Location: C:\\Users\\ACKVerissimo\\AVSHUNTER-Intelligence\\data\\polygon_liquid_universe.csv
  This is the authoritative universe file. Do NOT use clean_universe__with_sector.csv
  as the universe source — that file has sector metadata but may be stale on ticker list.

USAGE (Windows + venv)
-----------------------
  # Quick test — 10 tickers only:
  python avshunter_db_update.py --test

  # Full run (~16 minutes at 500 calls/min unlimited plan):
  python avshunter_db_update.py

  # Custom paths:
  python avshunter_db_update.py ^
    --existing  C:\\path\\to\\actuarial_database_v6.parquet ^
    --universe  C:\\path\\to\\polygon_liquid_universe.csv ^
    --output    C:\\path\\to\\actuarial_database_v6_updated.parquet

  # Patch existing DB only (no Polygon fetch — fast):
  python avshunter_db_update.py --patch-only

GOOGLE COLAB
------------
  !pip install pyarrow pandas numpy requests
  from google.colab import files
  files.upload()   # upload actuarial_database_v6.parquet + polygon_liquid_universe.csv
  !python avshunter_db_update.py
  files.download('actuarial_database_v6_updated.parquet')

POST-RUN STEPS
--------------
  1. Verify output:    python vanguard\\validate_enrichment.py
  2. Promote after review: copy actuarial_database_v6_updated.parquet → actuarial_database_v6.parquet
  3. Rebuild cache:    python C:\\Users\\ACKVerissimo\\vanguard\\actuarial_cache_builder.py
     (use full rebuild — not incremental — new tickers add new state combinations)

OUTPUT
------
  actuarial_database_v6_updated.parquet   — reviewed staging replacement for v6 DB
  actuarial_db_update_log.csv          — per-ticker status (rows added, errors)
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import shutil
import sys
import time
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import requests

# ── CONFIG ────────────────────────────────────────────────────────────────────

POLYGON_API_KEY     = os.environ.get("POLYGON_API_KEY", "***REDACTED_POLYGON_API_KEY***").strip()

DEFAULT_EXISTING_DB = r"C:\Users\ACKVerissimo\vanguard\data\actuarial_database_v6.parquet"
DEFAULT_UNIVERSE    = r"C:\Users\ACKVerissimo\AVSHUNTER-Intelligence\data\universe\polygon_liquid_universe.csv"
DEFAULT_OUTPUT      = r"C:\Users\ACKVerissimo\vanguard\data\actuarial_database_v6_updated.parquet"
DEFAULT_LOG         = "actuarial_db_update_log.csv"

# Date ranges to fetch (inclusive). Historical windows remain additive for new
# tickers; the final rolling window keeps the v6 database fresh for current prep.
def _default_fetch_windows(today: date | None = None) -> list[tuple[str, str]]:
    today = today or date.today()
    return [
        ("2021-11-01", "2022-12-31"),   # 2022 bear: RISK_OFF, DISTRIBUTION, EXPANSION
        ("2022-11-01", "2023-12-31"),   # 2023 bull: RISK_ON recovery, MARKUP D/E setups
        ("2023-11-01", "2024-11-30"),   # 2024 bull: RISK_ON continuation, rate-cut rally
        ("2024-11-01", "2025-04-24"),   # 2025 YTD: TRANSITIONAL regime, tariff volatility
        ("2025-11-01", today.isoformat()),  # rolling current refresh with indicator lookback
    ]

FETCH_WINDOWS = _default_fetch_windows()

# Schema constants — must match state_calculator.py exactly
SCHEMA_VERSION        = "2.2.0"
BUCKET_SCHEMA_VERSION = "1.1.0"

# Hash dimensions — order must match state_calculator._generate_state_hash
HASH_DIMS = [
    "vol_regime",
    "trend_direction",
    "trend_maturity",
    "structure_quality",
    "catalyst_proximity",
    "adx_bucket",
    "atr_pct_bucket",
    "wyckoff_phase_bucket",
    "macro_regime",
]

# Polygon rate limits
# UNLIMITED plan (Stock Screener Standard) — 500 calls/min is safe and fast
# At 500/min: 1,999 tickers × 4 windows ≈ 8,000 API calls → ~16 minutes
# Do NOT change this back to 5 — that is the free tier setting
CALLS_PER_MINUTE  = 500
RATE_SLEEP        = 60.0 / CALLS_PER_MINUTE
MAX_RETRIES       = 3
MIN_BARS_REQUIRED = 60    # minimum bars needed for reliable state vector
CHECKPOINT_EVERY  = 200   # save checkpoint every N tickers


# ═══════════════════════════════════════════════════════════════════════════════
# PHASE 1 — PATCH EXISTING DB
# ═══════════════════════════════════════════════════════════════════════════════

def patch_existing_db(df: pd.DataFrame) -> pd.DataFrame:
    """
    Apply all in-place fixes to the existing DB rows:
      1. Rename FLAT → BREAKEVEN in outcome_category (schema normalisation)
      2. Retag SIDEWAYS N/A → SIDEWAYS_BUILDING / SIDEWAYS_RANGING (v2.2.0)
      3. Recompute state_hash with correct underscore separator
    """
    print("\n[PHASE 1] Patching existing DB rows...")
    original_len = len(df)

    # ── Fix 1: Rename FLAT → BREAKEVEN ────────────────────────────────────────
    if "outcome_category" in df.columns:
        flat_count = (df["outcome_category"] == "FLAT").sum()
        if flat_count > 0:
            df["outcome_category"] = df["outcome_category"].replace("FLAT", "BREAKEVEN")
            print(f"  outcome_category: renamed {flat_count:,} FLAT → BREAKEVEN")

    # ── Fix 2: Retag SIDEWAYS N/A → SIDEWAYS_BUILDING / SIDEWAYS_RANGING ─────
    sideways_na = (df["trend_direction"] == "SIDEWAYS") & (
        df["trend_maturity"].isin(["N/A", "UNKNOWN", ""])
        | df["trend_maturity"].isna()
    )
    n_sideways_na = sideways_na.sum()
    if n_sideways_na > 0:
        df.loc[sideways_na, "trend_maturity"] = df.loc[sideways_na].apply(
            lambda r: _sideways_maturity(
                r.get("vol_regime", "NORMAL"),
                r.get("wyckoff_phase_bucket", "UNKNOWN")
            ), axis=1
        )
        print(f"  trend_maturity:   retagged {n_sideways_na:,} SIDEWAYS N/A rows")

    # ── Fix 3: Recompute state_hash with underscore separator ─────────────────
    print(f"  state_hash:       recomputing {len(df):,} rows (underscore separator)...")
    df["state_hash"] = df.apply(_state_hash, axis=1)

    # ── Fix 4: Ensure schema version columns are present ──────────────────────
    df["schema_version"]        = SCHEMA_VERSION
    df["bucket_schema_version"] = BUCKET_SCHEMA_VERSION

    print(f"  Done. {len(df):,} rows patched ({original_len:,} original).")
    return df


# ═══════════════════════════════════════════════════════════════════════════════
# PHASE 2 — FETCH NEW ROWS
# ═══════════════════════════════════════════════════════════════════════════════

def fetch_new_rows(
    tickers: List[str],
    existing_keys: set,
    test_mode: bool = False,
    fetch_windows: Optional[List[Tuple[str, str]]] = None,
) -> Tuple[List[Dict], List[Dict]]:
    """
    Fetch new rows from Polygon for all gap windows.
    Returns (new_rows, log_rows).
    """
    fetch_windows = fetch_windows or FETCH_WINDOWS
    if test_mode:
        tickers = tickers[:10]
        print(f"\n[PHASE 2] TEST MODE - processing {len(tickers)} tickers")
    else:
        print(f"\n[PHASE 2] Fetching {len(tickers):,} tickers across {len(fetch_windows)} date windows")
    new_rows: List[Dict] = []
    log_rows: List[Dict] = []
    total = len(tickers)
    checkpoint_base = "actuarial_checkpoint"

    for t_idx, ticker in enumerate(tickers, 1):
        ticker_rows = 0
        ticker_errors = 0

        for win_start, win_end in fetch_windows:
            df_raw = _polygon_fetch(ticker, win_start, win_end)
            if df_raw is None or df_raw.empty or len(df_raw) < MIN_BARS_REQUIRED:
                ticker_errors += 1
                continue

            # Compute all technicals once for the full window
            df = _compute_technicals(df_raw)

            # Build observations — start at bar 60 (enough lookback), stop 20 before end
            start_idx = MIN_BARS_REQUIRED
            end_idx   = len(df) - 21

            for idx in range(start_idx, end_idx):
                row_date = str(df["date"].iloc[idx])
                if (ticker, row_date) in existing_keys:
                    continue

                state = _compute_state(df, idx)
                if state is None:
                    continue

                outcomes = _compute_outcomes(df, idx)
                if outcomes is None:
                    continue

                state["ticker"] = ticker
                new_rows.append({**state, **outcomes})
                existing_keys.add((ticker, row_date))
                ticker_rows += 1

        log_rows.append({
            "ticker":     ticker,
            "rows_added": ticker_rows,
            "errors":     ticker_errors,
            "status":     "OK" if ticker_rows > 0 else ("NO_DATA" if ticker_errors else "SKIP"),
        })

        if t_idx % 25 == 0 or t_idx == total:
            print(f"  [{t_idx:4d}/{total}] {ticker:<8} +{ticker_rows:4d} rows | "
                  f"Total new: {len(new_rows):,}")

        # Checkpoint
        if len(new_rows) > 0 and t_idx % CHECKPOINT_EVERY == 0:
            _save_checkpoint(new_rows, f"{checkpoint_base}_{t_idx}.parquet")

    return new_rows, log_rows


# ═══════════════════════════════════════════════════════════════════════════════
# PHASE 3 — MERGE, CLEAN, SAVE
# ═══════════════════════════════════════════════════════════════════════════════

def merge_and_save(
    existing_df: pd.DataFrame,
    new_rows: List[Dict],
    output_path: str,
    log_rows: List[Dict],
) -> pd.DataFrame:
    """Merge new rows with patched existing DB, clean, and save."""
    print(f"\n[PHASE 3] Merging and saving...")

    if new_rows:
        new_df = pd.DataFrame(new_rows)
        # Ensure schema columns
        new_df["schema_version"]        = SCHEMA_VERSION
        new_df["bucket_schema_version"] = BUCKET_SCHEMA_VERSION
        combined = pd.concat([existing_df, new_df], ignore_index=True)
    else:
        combined = existing_df
        print("  No new rows — saving patched existing DB only.")

    # Deduplicate
    before = len(combined)
    combined = combined.drop_duplicates(subset=["ticker", "date"])
    removed = before - len(combined)
    print(f"  Dedup: removed {removed:,} duplicate rows")

    # Clean outliers — penny stocks and >100% 20d returns cause EV noise
    ret_col = "outcome_20d_return"
    if ret_col in combined.columns:
        bad = (combined[ret_col].abs() > 1.0) | (combined["price"] < 0.50)
        if bad.sum() > 0:
            combined = combined[~bad].copy()
            print(f"  Cleaned: removed {bad.sum():,} outlier rows (price<$0.50 or |ret|>100%)")

    # Ensure bool columns
    for col in ["outcome_hit_10pct_up", "outcome_hit_5pct_down_before_10up",
                "outcome_hit_5pct_up_5d", "outcome_hit_7pct_up_10d"]:
        if col in combined.columns:
            combined[col] = combined[col].fillna(False).astype(bool)

    # Ensure date is string for consistent dedup
    if "date" in combined.columns:
        combined["date"] = combined["date"].astype(str)

    # Rebuild the full v6 scenario-mapping layer after merge/clean. New rows
    # arrive as base state rows; this pass gives them the same v6 contract as
    # the live database before the staging parquet is written.
    combined = _enrich_v6_contract(combined, reference_df=existing_df)

    # Save
    out_path = Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    combined.to_parquet(str(out_path), index=False, compression="snappy")
    size_mb = out_path.stat().st_size / 1024 / 1024
    print(f"\n  Saved: {out_path}")
    print(f"  Size:  {size_mb:.1f} MB")
    print(f"  Rows:  {len(combined):,}")
    print(f"  Cols:  {len(combined.columns)}")

    # Stats
    print("\n  === FINAL DB STATS ===")
    for col, label in [
        ("macro_regime",          "Macro regime"),
        ("wyckoff_phase_bucket",  "Wyckoff bucket"),
        ("outcome_category",      "Outcome category"),
        ("vol_regime",            "Vol regime"),
        ("trend_maturity",        "Trend maturity"),
        ("structure_quality",     "Structure quality"),
        ("adx_bucket",            "ADX bucket"),
    ]:
        if col in combined.columns:
            counts = combined[col].value_counts()
            parts = "  |  ".join(f"{k}: {v:,}" for k, v in counts.items())
            print(f"  {label:<22} {parts}")

    # EV by bucket/regime cross-tab
    if all(c in combined.columns for c in ["wyckoff_phase_bucket", "macro_regime", ret_col]):
        print("\n  === WIN RATE BY BUCKET × REGIME (target: 55%+) ===")
        for bucket in ["ACCUMULATION", "MARKUP", "DISTRIBUTION"]:
            for regime in ["RISK_ON", "TRANSITIONAL", "RISK_OFF"]:
                sub = combined[
                    (combined["wyckoff_phase_bucket"] == bucket) &
                    (combined["macro_regime"] == regime)
                ]
                if len(sub) >= 100:
                    wr  = (sub[ret_col] > 0).mean()
                    ev  = sub[ret_col].mean()
                    h10 = sub["outcome_hit_10pct_up"].mean()
                    print(f"  {bucket:<15} × {regime:<14}: "
                          f"WR={wr:.1%}  EV={ev:+.2%}  Hit10={h10:.1%}  n={len(sub):,}")

    # Save log
    pd.DataFrame(log_rows).to_csv(DEFAULT_LOG, index=False)
    print(f"\n  Log: {DEFAULT_LOG}")

    return combined


# ═══════════════════════════════════════════════════════════════════════════════
# STATE VECTOR COMPUTATION
# ═══════════════════════════════════════════════════════════════════════════════

def _compute_technicals(df: pd.DataFrame) -> pd.DataFrame:
    """Compute all technical indicators needed for state vector computation."""
    df = df.copy()
    close  = df["close"]
    high   = df["high"]
    low    = df["low"]
    volume = df["volume"]

    # EMAs
    df["ema21"]  = close.ewm(span=21,  adjust=False).mean()
    df["ema50"]  = close.ewm(span=50,  adjust=False).mean()
    df["ema200"] = close.ewm(span=200, adjust=False).mean()

    # ATR (EWM true range)
    tr          = pd.concat([
        high - low,
        (high - close.shift(1)).abs(),
        (low  - close.shift(1)).abs()
    ], axis=1).max(axis=1)
    df["atr14"] = tr.ewm(span=14, adjust=False).mean()
    df["atr_pct"] = (df["atr14"] / close.replace(0, np.nan)) * 100

    # ADX
    dm_plus  = high.diff().clip(lower=0)
    dm_minus = (-low.diff()).clip(lower=0)
    mask     = dm_plus >= dm_minus
    dm_plus  = dm_plus.where(mask, 0)
    dm_minus = dm_minus.where(~mask, 0)
    atr_ewm  = tr.ewm(span=14, adjust=False).mean().replace(0, np.nan)
    di_plus  = 100 * dm_plus.ewm(span=14, adjust=False).mean() / atr_ewm
    di_minus = 100 * dm_minus.ewm(span=14, adjust=False).mean() / atr_ewm
    dx       = 100 * (di_plus - di_minus).abs() / (di_plus + di_minus).replace(0, np.nan)
    df["adx"] = dx.ewm(span=14, adjust=False).mean().fillna(0.0)

    # RSI
    delta    = close.diff()
    gain     = delta.clip(lower=0).ewm(span=14, adjust=False).mean()
    loss     = (-delta.clip(upper=0)).ewm(span=14, adjust=False).mean()
    rs       = gain / loss.replace(0, np.nan)
    df["rsi"] = (100 - 100 / (1 + rs)).fillna(50.0)

    # Bollinger Band width
    bb_mid   = close.rolling(20).mean()
    bb_std   = close.rolling(20).std()
    df["bb_width"] = (4 * bb_std / bb_mid.replace(0, np.nan)) * 100

    # 52-week high/low
    df["high_252"]      = high.rolling(252, min_periods=50).max()
    df["low_252"]       = low.rolling(252, min_periods=50).min()
    df["dist_from_high"] = (df["high_252"] - close) / df["high_252"].replace(0, np.nan)
    df["dist_from_low"]  = (close - df["low_252"]) / df["low_252"].replace(0, np.nan)

    return df


def _compute_state(df: pd.DataFrame, idx: int) -> Optional[Dict]:
    """Compute 9-dimensional state vector for row at idx."""
    if idx < MIN_BARS_REQUIRED:
        return None

    row   = df.iloc[idx]
    close = float(row["close"])

    if close <= 0:
        return None

    # ── Percentile helpers ────────────────────────────────────────────────────
    def pct_rank(series: pd.Series, val: float) -> float:
        s = series.iloc[max(0, idx-252):idx+1].dropna()
        return float((s < val).sum() / len(s) * 100) if len(s) > 0 else 50.0

    atr_pct     = float(row.get("atr_pct", 0))
    bb_width    = float(row.get("bb_width", 0)) if not pd.isna(row.get("bb_width", np.nan)) else 0
    atr_percentile = pct_rank(df["atr_pct"], atr_pct)
    bb_percentile  = pct_rank(df["bb_width"], bb_width)

    # ── Vol regime ────────────────────────────────────────────────────────────
    if atr_percentile < 30 and bb_percentile < 30:
        vol_regime = "COMPRESSION"
    elif atr_percentile > 70 or bb_percentile > 70:
        vol_regime = "EXPANSION"
    else:
        vol_regime = "NORMAL"

    # ── Trend direction ───────────────────────────────────────────────────────
    ema21  = float(row.get("ema21",  close))
    ema50  = float(row.get("ema50",  close))
    ema200 = float(row.get("ema200", close))

    if (not any(pd.isna([ema21, ema50, ema200]))
            and close > ema21 and ema21 > ema50 and ema50 > ema200):
        trend_direction = "UP"
    elif (not any(pd.isna([ema21, ema50, ema200]))
            and close < ema21 and ema21 < ema50 and ema50 < ema200):
        trend_direction = "DOWN"
    else:
        trend_direction = "SIDEWAYS"

    # ── Trend maturity ────────────────────────────────────────────────────────
    dist_high = float(row.get("dist_from_high", 0.5)) if not pd.isna(row.get("dist_from_high", np.nan)) else 0.5
    dist_low  = float(row.get("dist_from_low",  0.5)) if not pd.isna(row.get("dist_from_low",  np.nan)) else 0.5

    if trend_direction == "UP":
        if dist_high < 0.05:
            trend_maturity = "LATE"
        elif dist_high < 0.15:
            trend_maturity = "MIDDLE"
        else:
            trend_maturity = "EARLY"
    elif trend_direction == "DOWN":
        if dist_low < 0.05:
            trend_maturity = "LATE"
        elif dist_low < 0.15:
            trend_maturity = "MIDDLE"
        else:
            trend_maturity = "EARLY"
    else:
        trend_maturity = None  # filled by _sideways_maturity below

    # ── Wyckoff phase bucket ──────────────────────────────────────────────────
    adx = float(row.get("adx", 0))
    rsi = float(row.get("rsi", 50))

    vol_recent = df["volume"].iloc[max(0, idx-5):idx+1].mean()
    vol_avg    = df["volume"].iloc[max(0, idx-20):idx+1].mean()
    vol_ratio  = float(vol_recent / vol_avg) if vol_avg > 0 else 1.0

    atr_pct_rank_60 = pct_rank(df["atr_pct"], atr_pct)

    ema_bullish = (not any(pd.isna([ema21, ema50, ema200]))
                   and close > ema21 and ema21 > ema50 and ema50 > ema200)
    ema_bearish = (not any(pd.isna([ema21, ema50, ema200]))
                   and close < ema21 and ema21 < ema50 and ema50 < ema200)

    # Distribution: near 52w high, vol declining or RSI overbought
    if dist_high < 0.08 and rsi > 60 and (ema_bullish or ema21 > ema50) and (vol_ratio < 0.85 or rsi > 75):
        wyckoff_phase        = "DISTRIBUTION"
        wyckoff_phase_bucket = "DISTRIBUTION"
    # Phase E: full markup, extended, strong ADX
    elif ema_bullish and dist_high < 0.15 and adx > 25 and rsi > 55:
        wyckoff_phase        = "E"
        wyckoff_phase_bucket = "MARKUP"
    # Phase D: SOS, uptrend just established
    elif ema_bullish and dist_high >= 0.15 and adx > 18 and rsi > 48:
        wyckoff_phase        = "D"
        wyckoff_phase_bucket = "MARKUP"
    # Phase C: spring / test — compressed, near low, RSI recovering
    elif dist_low < 0.10 and atr_pct_rank_60 < 35 and rsi > 38 and not ema_bearish:
        wyckoff_phase        = "C"
        wyckoff_phase_bucket = "ACCUMULATION"
    # Phase A: stopping action — near low, vol spike
    elif dist_low < 0.15 and vol_ratio > 1.4 and atr_pct_rank_60 > 55:
        wyckoff_phase        = "A"
        wyckoff_phase_bucket = "ACCUMULATION"
    # Phase B: range-bound cause building
    else:
        wyckoff_phase        = "B"
        wyckoff_phase_bucket = "ACCUMULATION"

    # ── Sideways maturity (now that wyckoff_phase_bucket is known) ─────────
    if trend_maturity is None:
        trend_maturity = _sideways_maturity(vol_regime, wyckoff_phase_bucket)

    # ── Structure quality (mirrors state_calculator) ──────────────────────────
    if rsi > 55:
        structure_quality = "STRONG"
    elif rsi < 40:
        structure_quality = "WEAK"
    else:
        structure_quality = "NEUTRAL"

    # ── ADX bucket ────────────────────────────────────────────────────────────
    if adx < 20:
        adx_bucket = "WEAK"
    elif adx > 35:
        adx_bucket = "STRONG"
    else:
        adx_bucket = "MODERATE"

    # ── ATR percentile bucket ─────────────────────────────────────────────────
    if atr_percentile < 33:
        atr_pct_bucket = "LOW"
    elif atr_percentile > 66:
        atr_pct_bucket = "HIGH"
    else:
        atr_pct_bucket = "MID"

    # ── Macro regime (ATR rank + EMA trend proxy — mirrors state_calculator) ──
    if ema_bullish and atr_percentile < 50:
        macro_regime = "RISK_ON"
    elif ema_bearish or atr_percentile > 70:
        macro_regime = "RISK_OFF"
    else:
        macro_regime = "TRANSITIONAL"

    # ── State hash (underscore separator — matches state_calculator exactly) ──
    state_row = {
        "vol_regime":            vol_regime,
        "trend_direction":       trend_direction,
        "trend_maturity":        trend_maturity,
        "structure_quality":     structure_quality,
        "catalyst_proximity":    "NONE",
        "adx_bucket":            adx_bucket,
        "atr_pct_bucket":        atr_pct_bucket,
        "wyckoff_phase_bucket":  wyckoff_phase_bucket,
        "macro_regime":          macro_regime,
    }
    state_hash = _state_hash(state_row)

    return {
        **state_row,
        "state_hash":            state_hash,
        "schema_version":        SCHEMA_VERSION,
        "bucket_schema_version": BUCKET_SCHEMA_VERSION,
        "date":                  str(row["date"]),
        "price":                 round(close, 4),
        "wyckoff_phase":         wyckoff_phase,
        "atr_percentile":        round(atr_percentile, 2),
        "bb_percentile":         round(bb_percentile, 2),
        "adx":                   round(adx, 2),
        "rsi":                   round(rsi, 2),
        "dist_from_high":        round(dist_high, 4),
        "dist_from_low":         round(dist_low, 4),
    }


def _compute_outcomes(df: pd.DataFrame, idx: int) -> Optional[Dict]:
    """Compute 5d / 10d / 20d forward outcomes."""
    entry = float(df["close"].iloc[idx])
    if entry <= 0:
        return None

    fwd = df.iloc[idx+1:].reset_index(drop=True)
    if len(fwd) < 20:
        return None

    def forward(bars, horizon):
        if len(bars) < horizon:
            return None
        b = bars.iloc[:horizon]
        ret    = float((b["close"].iloc[-1] - entry) / entry)
        max_g  = float((b["high"].max() - entry) / entry)
        max_d  = float((b["low"].min() - entry) / entry)
        return ret, max_g, max_d

    s20 = forward(fwd, 20)
    if s20 is None:
        return None
    ret_20, max_g_20, max_d_20 = s20

    # Hit flags
    hit_10   = bool(max_g_20 >= 0.10)
    hit_5dn  = bool(max_d_20 <= -0.05)
    hit_5_before_10 = False
    if hit_10:
        idx_10 = next((i for i, r in enumerate(
            (fwd["close"].iloc[:20] - entry) / entry) if r >= 0.10), 20)
        if any((fwd["low"].iloc[:idx_10] - entry) / entry <= -0.05):
            hit_5_before_10 = True

    # Days to 10%
    days_to_10 = next(
        (i+1 for i, h in enumerate(fwd["high"].iloc[:20])
         if (h - entry) / entry >= 0.10), 20
    )
    days_to_5 = next(
        (i+1 for i, h in enumerate(fwd["high"].iloc[:20])
         if (h - entry) / entry >= 0.05), 20
    )

    # Outcome category
    if ret_20 >= 0.10:
        cat = "BIG_WIN"
    elif ret_20 >= 0.02:
        cat = "SMALL_WIN"
    elif ret_20 >= -0.02:
        cat = "BREAKEVEN"
    elif ret_20 >= -0.08:
        cat = "SMALL_LOSS"
    else:
        cat = "BIG_LOSS"

    result = {
        "outcome_20d_return":              round(ret_20, 6),
        "outcome_max_gain_20d":            round(max_g_20, 6),
        "outcome_max_drawdown_20d":        round(max_d_20, 6),
        "outcome_hit_10pct_up":            hit_10,
        "outcome_hit_5pct_down_before_10up": hit_5_before_10,
        "outcome_days_to_10pct":           days_to_10,
        "outcome_days_to_5pct":            days_to_5,
        "outcome_category":                cat,
    }

    s5 = forward(fwd, 5)
    if s5:
        ret_5, max_g_5, max_d_5 = s5
        result.update({
            "outcome_5d_return":       round(ret_5, 6),
            "outcome_max_gain_5d":     round(max_g_5, 6),
            "outcome_max_drawdown_5d": round(max_d_5, 6),
            "outcome_hit_5pct_up_5d":  bool(max_g_5 >= 0.05),
        })
    else:
        result.update({"outcome_5d_return": np.nan,
                        "outcome_max_gain_5d": np.nan,
                        "outcome_max_drawdown_5d": np.nan,
                        "outcome_hit_5pct_up_5d": False})

    s10 = forward(fwd, 10)
    if s10:
        ret_10, max_g_10, max_d_10 = s10
        result.update({
            "outcome_10d_return":        round(ret_10, 6),
            "outcome_max_gain_10d":      round(max_g_10, 6),
            "outcome_max_drawdown_10d":  round(max_d_10, 6),
            "outcome_hit_7pct_up_10d":   bool(max_g_10 >= 0.07),
        })
    else:
        result.update({"outcome_10d_return": np.nan,
                        "outcome_max_gain_10d": np.nan,
                        "outcome_max_drawdown_10d": np.nan,
                        "outcome_hit_7pct_up_10d": False})

    return result


def _momentum_bucket_from_score(score) -> object:
    if pd.isna(score):
        return pd.NA
    score = float(score)
    if score < 15:
        return "LOW"
    if score < 30:
        return "MID"
    if score < 45:
        return "HIGH"
    return "EXTREME"


def _enrich_v6_contract(df: pd.DataFrame, reference_df: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """Compute the v6 scenario-mapping fields expected by actuarial_query.

    The database updater creates base v2.2 state rows from Polygon. The live v6
    parquet also carries scenario-mapping and transition columns that are
    derived from those base fields. This function rebuilds that derived layer
    for the merged frame so newly fetched rows do not enter the DB as partial
    records.
    """
    out = df.copy()

    for col in [
        "ticker", "date", "vol_regime", "trend_direction", "structure_quality",
        "phase_v2", "momentum_bucket", "location_bucket", "state_v2",
        "future_momentum_bucket",
    ]:
        if col in out.columns:
            out[col] = out[col].astype("string")

    for col in [
        "atr_percentile", "bb_percentile", "adx", "rsi",
        "dist_from_high", "dist_from_low", "momentum_score",
    ]:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce")

    atr = out["atr_percentile"]
    adx = out["adx"]
    bb = out["bb_percentile"]
    rsi = out["rsi"]
    dist_high = pd.to_numeric(out["dist_from_high"], errors="coerce")
    dist_low = pd.to_numeric(out["dist_from_low"], errors="coerce")
    valid_base = (
        atr.notna() & adx.notna() & bb.notna() & rsi.notna()
        & dist_high.notna() & dist_low.notna()
        & out["vol_regime"].notna()
        & out["trend_direction"].notna()
        & out["structure_quality"].notna()
    )

    out["phase_v2"] = np.select(
        [
            (atr < 45) & (adx < 22) & (bb < 55),
            (atr >= 45) & (adx >= 22) & (rsi < 72) & (bb < 95),
        ],
        ["EARLY_TRANSITION", "CONTINUATION"],
        default="EXHAUSTION",
    )
    out["phase_v2"] = pd.Series(out["phase_v2"], index=out.index, dtype="string")

    out["momentum_score"] = (adx * atr) / 100
    out["momentum_bucket"] = out["momentum_score"].map(_momentum_bucket_from_score).astype("string")

    out["location_bucket"] = np.select(
        [
            dist_high < 0.10,
            dist_low < 0.10,
            (dist_high > 0.30) & (dist_low > 0.30),
        ],
        ["NEAR_HIGH", "NEAR_LOW", "MID_RANGE"],
        default="TRANSITION_ZONE",
    )
    out["location_bucket"] = pd.Series(out["location_bucket"], index=out.index, dtype="string")
    out.loc[~valid_base, ["phase_v2", "momentum_bucket", "location_bucket"]] = pd.NA

    out["state_v2"] = (
        out["vol_regime"].astype("string").fillna("UNKNOWN") + "|" +
        out["trend_direction"].astype("string").fillna("UNKNOWN") + "|" +
        out["structure_quality"].astype("string").fillna("UNKNOWN") + "|" +
        out["phase_v2"].astype("string").fillna("UNKNOWN") + "|" +
        out["momentum_bucket"].astype("string").fillna("UNKNOWN") + "|" +
        out["location_bucket"].astype("string").fillna("UNKNOWN")
    ).astype("string")
    out.loc[~valid_base, "state_v2"] = pd.NA

    out["ticker"] = out["ticker"].astype("string").str.upper().str.strip()
    out["date"] = out["date"].astype(str)
    out = out.sort_values(["ticker", "date"]).reset_index(drop=True)

    g = out.groupby("ticker", sort=False)
    out["momentum_next"] = g["momentum_score"].shift(-1)
    out["momentum_delta"] = out["momentum_next"] - out["momentum_score"]
    out["atr_next"] = g["atr_percentile"].shift(-1)
    out["atr_delta"] = out["atr_next"] - out["atr_percentile"]
    out["adx_next"] = g["adx"].shift(-1)
    out["adx_delta"] = out["adx_next"] - out["adx"]

    out["transition_flag_v2"] = (
        (out["momentum_score"] > 10) & (out["momentum_score"] < 30) &
        (out["momentum_delta"] > 0) &
        (out["atr_percentile"] < 60) &
        (out["adx"] < 30)
    ).astype("int64")

    out["future_momentum_bucket"] = (
        out["momentum_next"].map(_momentum_bucket_from_score).astype("string")
    )

    for col in ["outcome_days_to_5pct", "outcome_days_to_10pct"]:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce").fillna(20).round().astype("int64")

    if "__index_level_0__" in out.columns:
        out["__index_level_0__"] = np.arange(len(out), dtype="int64")

    if reference_df is not None:
        for col in reference_df.columns:
            if col not in out.columns:
                out[col] = pd.NA
        out = out[list(reference_df.columns)]

        for col in ["outcome_days_to_5pct", "outcome_days_to_10pct", "transition_flag_v2", "__index_level_0__"]:
            if col in out.columns:
                out[col] = pd.to_numeric(out[col], errors="coerce").fillna(0).round().astype("int64")

        for col in ["schema_version", "bucket_schema_version"]:
            if col in out.columns:
                out[col] = out[col].astype("string")

    return out


# ═══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def _state_hash(row) -> str:
    """Compute state hash with underscore separator — matches state_calculator exactly."""
    if isinstance(row, dict):
        parts = [str(row.get(d, "UNKNOWN") or "UNKNOWN").strip() for d in HASH_DIMS]
    else:
        parts = [str(row.get(d, "UNKNOWN") or "UNKNOWN").strip() for d in HASH_DIMS]
    return hashlib.md5("_".join(parts).encode()).hexdigest()[:16]


def _sideways_maturity(vol_regime: str, wyckoff_phase_bucket: str) -> str:
    """Mirror of state_calculator._sideways_maturity."""
    v = str(vol_regime or "").strip().upper()
    w = str(wyckoff_phase_bucket or "").strip().upper()
    is_comp  = (v == "COMPRESSION")
    is_accum = (w in ("ACCUMULATION", "A", "B", "C"))
    return "SIDEWAYS_BUILDING" if (is_comp or is_accum) else "SIDEWAYS_RANGING"


_last_call = 0.0

def _polygon_fetch(ticker: str, start: str, end: str) -> Optional[pd.DataFrame]:
    """Fetch adjusted daily bars from Polygon with retry and rate limiting."""
    global _last_call
    url = (f"https://api.polygon.io/v2/aggs/ticker/{ticker}/range/1/day/"
           f"{start}/{end}?adjusted=true&sort=asc&limit=5000"
           f"&apiKey={POLYGON_API_KEY}")

    for attempt in range(MAX_RETRIES):
        # Rate limit
        elapsed = time.time() - _last_call
        if elapsed < RATE_SLEEP:
            time.sleep(RATE_SLEEP - elapsed)
        _last_call = time.time()

        try:
            r = requests.get(url, timeout=30)
            if r.status_code == 200:
                data = r.json()
                results = data.get("results", [])
                if not results:
                    return pd.DataFrame()
                df = pd.DataFrame(results)
                df["date"] = pd.to_datetime(df["t"], unit="ms").dt.date.astype(str)
                df = df.rename(columns={"o":"open","h":"high","l":"low","c":"close","v":"volume"})
                return df[["date","open","high","low","close","volume"]].sort_values("date").reset_index(drop=True)
            elif r.status_code == 429:
                time.sleep(65)
            else:
                break
        except Exception:
            if attempt < MAX_RETRIES - 1:
                time.sleep(10)

    return None


def _load_universe(path: str, *, allow_sample: bool = False) -> List[str]:
    """Load ticker list from CSV.

    Full refreshes must use a real ticker source. The historical built-in sample
    is still available only when explicitly requested for local smoke tests.
    """
    p = Path(path)
    if not p.exists():
        print(f"WARNING: Universe file not found: {path}")
        if allow_sample:
            print("         Explicit sample mode enabled; using built-in 50-ticker sample.")
            return [
                "AAPL","MSFT","NVDA","GOOGL","AMZN","META","TSLA","AVGO","ORCL","AMD",
                "SPY","QQQ","IWM","GLD","TLT","XLK","XLF","XLI","XLE","XLV",
                "MTUM","CDE","MAR","AMAT","JPM","BAC","WFC","GS","C","MS",
                "COST","WMT","TGT","HD","LOW","UNH","CVS","MRK","ABBV","LLY",
                "CAT","DE","HON","MMM","GE","NEE","DUK","SO","AEP","EXC",
            ]
        raise FileNotFoundError(
            "Universe file missing. Provide --universe or --ticker-source with a real "
            "CSV from the latest EIL/gap manifest, or pass --allow-sample-universe "
            "for an explicit smoke test."
        )
    df = pd.read_csv(p)
    for col in ["ticker","Ticker","symbol","Symbol"]:
        if col in df.columns:
            return df[col].dropna().str.strip().str.upper().unique().tolist()
    return df.iloc[:,0].dropna().str.strip().str.upper().unique().tolist()


def _save_checkpoint(new_rows: List[Dict], path: str):
    try:
        pd.DataFrame(new_rows).to_parquet(path, index=False)
        print(f"  [CHECKPOINT] {path} ({len(new_rows):,} new rows)")
    except Exception as e:
        print(f"  [CHECKPOINT] Failed: {e}")


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="AVSHUNTER Actuarial Database Gap-Fill",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--existing",  default=DEFAULT_EXISTING_DB,
                        help="Path to existing actuarial_database_v6.parquet")
    parser.add_argument("--universe",  default=DEFAULT_UNIVERSE,
                        help="Path to polygon_liquid_universe.csv (1,999 tickers)")
    parser.add_argument("--ticker-source", default=None,
                        help="Explicit CSV ticker source, such as latest EIL or DB gap manifest")
    parser.add_argument("--output",    default=DEFAULT_OUTPUT,
                        help="Output path for updated database")
    parser.add_argument("--api-key",   default=None,
                        help="Polygon API key (default: env POLYGON_API_KEY)")
    parser.add_argument("--rate",      type=int, default=None,
                        help="Polygon API calls/min (default: 500 Starter unlimited plan)")
    parser.add_argument("--test",      action="store_true",
                        help="Test mode: process only 10 tickers")
    parser.add_argument("--patch-only",action="store_true",
                        help="Only patch existing DB (no new Polygon fetches)")
    parser.add_argument("--refresh-start", default=None,
                        help="Optional single refresh window start date YYYY-MM-DD")
    parser.add_argument("--refresh-end", default=None,
                        help="Optional single refresh window end date YYYY-MM-DD, default today")
    parser.add_argument("--allow-sample-universe", action="store_true",
                        help="Allow built-in 50-ticker sample when ticker source is missing")
    args = parser.parse_args()

    global POLYGON_API_KEY, RATE_SLEEP, CALLS_PER_MINUTE
    if args.api_key:
        POLYGON_API_KEY = args.api_key
    if args.rate:
        CALLS_PER_MINUTE = args.rate
        RATE_SLEEP = 60.0 / CALLS_PER_MINUTE

    print("=" * 70)
    print("  AVSHUNTER Actuarial Database Gap-Fill")
    print(f"  Schema: {SCHEMA_VERSION} | Bucket: {BUCKET_SCHEMA_VERSION}")
    print(f"  API rate: {CALLS_PER_MINUTE} calls/min ({RATE_SLEEP:.1f}s between calls)")
    print("=" * 70)

    # ── Load existing DB ───────────────────────────────────────────────────────
    existing_path = Path(args.existing)
    if not existing_path.exists():
        print(f"ERROR: Existing DB not found: {existing_path}")
        sys.exit(1)

    print(f"\nLoading existing DB: {existing_path.name}")
    existing_df = pd.read_parquet(str(existing_path))
    print(f"  Loaded {len(existing_df):,} rows, {len(existing_df.columns)} columns")

    # Build dedup key set
    existing_keys = set(zip(
        existing_df["ticker"].astype(str),
        existing_df["date"].astype(str)
    ))
    print(f"  Unique ticker/date pairs: {len(existing_keys):,}")

    # ── Phase 1: Patch existing DB ─────────────────────────────────────────────
    existing_df = patch_existing_db(existing_df)

    if args.patch_only:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        existing_df.to_parquet(str(out_path), index=False)
        print(f"\nPatch-only mode: saved {out_path}")
        return

    # ── Phase 2: Fetch new rows ────────────────────────────────────────────────
    ticker_source = args.ticker_source or args.universe
    tickers = _load_universe(ticker_source, allow_sample=args.allow_sample_universe)
    print(f"\nUniverse: {len(tickers):,} tickers")
    print(f"Ticker source: {ticker_source}")
    fetch_windows = [(args.refresh_start, args.refresh_end or date.today().isoformat())] if args.refresh_start else FETCH_WINDOWS
    print(f"Fetch windows: {fetch_windows}")
    print(f"Test mode: {'YES - 10 tickers only' if args.test else 'NO'}")

    new_rows, log_rows = fetch_new_rows(
        tickers, existing_keys, test_mode=args.test, fetch_windows=fetch_windows
    )
    print(f"\n  Total new rows fetched: {len(new_rows):,}")

    # ── Phase 3: Merge and save ────────────────────────────────────────────────
    merge_and_save(existing_df, new_rows, args.output, log_rows)

    print("\n" + "=" * 70)
    print("  DONE")
    print(f"  Promote after review: copy {Path(args.output).name} → {existing_path}")
    print(r"  Then rebuild cache: python C:\Users\ACKVerissimo\vanguard\actuarial_cache_builder.py")
    print("=" * 70)


if __name__ == "__main__":
    main()


