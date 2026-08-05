#!/usr/bin/env python3
"""
AVSHUNTER — Upgrade Actuarial Database: Add Multi-Horizon Outcome Columns

Adds 5d and 10d outcome columns to the existing parquet database.
SAFE: purely additive — no rows deleted, no hashes changed, no Polygon calls.

New columns added:
  outcome_5d_return          float  — forward return at day 5
  outcome_10d_return         float  — forward return at day 10
  outcome_hit_5pct_up_5d     bool   — hit +5% within 5 days
  outcome_hit_7pct_up_10d    bool   — hit +7% within 10 days
  outcome_max_drawdown_5d    float  — max drawdown in 5d window
  outcome_max_drawdown_10d   float  — max drawdown in 10d window

Usage:
  python upgrade_actuarial_database.py

Backup:
  A .backup copy is written before any changes.
"""

from __future__ import annotations

import shutil
import time
from pathlib import Path

import pandas as pd

# ─── CONFIG ────────────────────────────────────────────────────────────────────
DB_PATH    = Path(r"C:\Users\ACKVerissimo\vanguard\data\actuarial_database.parquet")
BACKUP_PATH = DB_PATH.with_suffix(".parquet.backup")

# Thresholds for new boolean columns
HIT_5PCT_UP_5D_THRESHOLD  = 0.05   # +5% within 5 days
HIT_7PCT_UP_10D_THRESHOLD = 0.07   # +7% within 10 days

# ───────────────────────────────────────────────────────────────────────────────

def main() -> None:
    print("=" * 70)
    print("  AVSHUNTER — ACTUARIAL DATABASE MULTI-HORIZON UPGRADE")
    print("=" * 70)

    # ── 1. Load ────────────────────────────────────────────────────────────────
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Database not found: {DB_PATH}")

    print(f"\n[1] Loading database: {DB_PATH}")
    t0 = time.time()
    df = pd.read_parquet(DB_PATH)
    print(f"    Loaded {len(df):,} rows × {len(df.columns)} cols in {time.time()-t0:.1f}s")

    # ── 2. Check for existing new columns ─────────────────────────────────────
    NEW_COLS = [
        "outcome_5d_return",
        "outcome_10d_return",
        "outcome_hit_5pct_up_5d",
        "outcome_hit_7pct_up_10d",
        "outcome_max_drawdown_5d",
        "outcome_max_drawdown_10d",
    ]
    already = [c for c in NEW_COLS if c in df.columns]
    if already:
        print(f"\n    Columns already present: {already}")
        print("    Re-computing to ensure correctness...")

    # ── 3. Backup ──────────────────────────────────────────────────────────────
    print(f"\n[2] Backing up to: {BACKUP_PATH}")
    shutil.copy2(DB_PATH, BACKUP_PATH)
    print(f"    Backup written ({BACKUP_PATH.stat().st_size / 1e6:.1f} MB)")

    # ── 4. Sort by ticker + date ───────────────────────────────────────────────
    print(f"\n[3] Sorting by ticker + date...")
    t1 = time.time()
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values(["ticker", "date"]).reset_index(drop=True)
    print(f"    Sorted in {time.time()-t1:.1f}s")

    # ── 5. Compute forward prices per ticker ───────────────────────────────────
    print(f"\n[4] Computing forward prices at 5d and 10d per ticker...")
    t2 = time.time()

    # Group by ticker and compute forward-shifted prices
    # shift(-N) within group gives the price N rows ahead for same ticker
    def compute_forward(group: pd.DataFrame) -> pd.DataFrame:
        close = group["price"]

        # Forward close prices
        fwd_5d  = close.shift(-5)
        fwd_10d = close.shift(-10)

        # Forward returns
        group["outcome_5d_return"]  = (fwd_5d  / close) - 1.0
        group["outcome_10d_return"] = (fwd_10d / close) - 1.0

        # Boolean gates
        group["outcome_hit_5pct_up_5d"]  = group["outcome_5d_return"]  >= HIT_5PCT_UP_5D_THRESHOLD
        group["outcome_hit_7pct_up_10d"] = group["outcome_10d_return"] >= HIT_7PCT_UP_10D_THRESHOLD

        # Max drawdown in 5d and 10d windows
        # For each row, look at the next N closing prices and find the worst drop
        # Using rolling min on the forward window (approximation via shift)
        # More precise: compare price to min of next N prices
        # We build it as: min_5d / close - 1, min_10d / close - 1
        # Rolling min on reversed series is expensive — use a vectorised approximation:
        # min of close[t+1..t+N] relative to close[t]
        # We compute this by shifting individual days and taking the min
        fwd_prices_5d  = pd.concat([close.shift(-i) for i in range(1, 6)],  axis=1)
        fwd_prices_10d = pd.concat([close.shift(-i) for i in range(1, 11)], axis=1)

        min_5d  = fwd_prices_5d.min(axis=1)
        min_10d = fwd_prices_10d.min(axis=1)

        group["outcome_max_drawdown_5d"]  = (min_5d  / close) - 1.0
        group["outcome_max_drawdown_10d"] = (min_10d / close) - 1.0

        return group

    # Process in chunks by ticker for memory efficiency
    tickers = df["ticker"].unique()
    print(f"    Processing {len(tickers):,} tickers...")

    chunks = []
    for i, ticker in enumerate(tickers, 1):
        chunk = df[df["ticker"] == ticker].copy()
        chunk = compute_forward(chunk)
        chunks.append(chunk)
        if i % 500 == 0:
            print(f"    [{i:,}/{len(tickers):,}] tickers processed...")

    df = pd.concat(chunks, ignore_index=True)
    print(f"    Forward prices computed in {time.time()-t2:.1f}s")

    # ── 6. Fill NaN at tail rows (no forward data available) ──────────────────
    print(f"\n[5] Filling NaN values at tail rows (last 10 rows per ticker)...")
    df["outcome_5d_return"]         = df["outcome_5d_return"].fillna(0.0)
    df["outcome_10d_return"]        = df["outcome_10d_return"].fillna(0.0)
    df["outcome_hit_5pct_up_5d"]    = df["outcome_hit_5pct_up_5d"].fillna(False)
    df["outcome_hit_7pct_up_10d"]   = df["outcome_hit_7pct_up_10d"].fillna(False)
    df["outcome_max_drawdown_5d"]   = df["outcome_max_drawdown_5d"].fillna(0.0)
    df["outcome_max_drawdown_10d"]  = df["outcome_max_drawdown_10d"].fillna(0.0)

    # ── 7. Validate ────────────────────────────────────────────────────────────
    print(f"\n[6] Validation:")
    print(f"    Total rows:         {len(df):,}")
    print(f"    Total columns:      {len(df.columns)}")
    print(f"    New columns added:  {NEW_COLS}")
    print(f"\n    Sample statistics:")
    for col in NEW_COLS:
        if col.startswith("outcome_hit"):
            rate = df[col].mean()
            print(f"      {col}: {rate:.1%} hit rate")
        else:
            mean = df[col].mean()
            print(f"      {col}: mean={mean:.4f}")

    # Cross-check: 5d win rate should be lower than 20d (shorter window = harder)
    wr_5d  = (df["outcome_5d_return"]  > 0).mean()
    wr_10d = (df["outcome_10d_return"] > 0).mean()
    wr_20d = (df["outcome_20d_return"] > 0).mean()
    print(f"\n    Win rate sanity check (should increase with horizon):")
    print(f"      5d:  {wr_5d:.1%}")
    print(f"      10d: {wr_10d:.1%}")
    print(f"      20d: {wr_20d:.1%}")

    if not (wr_5d <= wr_10d <= wr_20d + 0.05):
        print("    ⚠️  WARNING: Win rates not monotonically increasing — check data")
    else:
        print("    ✅ Win rate ordering looks correct")

    # ── 8. Save ────────────────────────────────────────────────────────────────
    print(f"\n[7] Saving upgraded database...")
    t3 = time.time()
    df.to_parquet(DB_PATH, index=False, compression="snappy")
    size_mb = DB_PATH.stat().st_size / 1e6
    print(f"    Saved in {time.time()-t3:.1f}s  ({size_mb:.1f} MB)")

    print(f"\n{'='*70}")
    print(f"  ✅ UPGRADE COMPLETE")
    print(f"  Database: {DB_PATH}")
    print(f"  Backup:   {BACKUP_PATH}")
    print(f"  New cols: {', '.join(NEW_COLS)}")
    print(f"{'='*70}\n")


if __name__ == "__main__":
    main()
