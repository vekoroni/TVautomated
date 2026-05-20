"""
enrich_actuarial_9dim.py
========================
Adds the three missing 9-dimension match columns that CAN be derived from
existing DB columns (no Polygon re-fetch required):

    iv_regime       — volatility regime proxy from vol_regime + atr_percentile
                      LOW_IV | NORMAL_IV | ELEVATED_IV | HIGH_IV
    horizon_bucket  — best-fit outcome horizon from forward outcome columns
                      SHORT | MEDIUM | LONG
    crabel_state    — intraday compression proxy from vol/adx bucket columns
                      CRABEL_READY | COILING | NONE

Status of remaining missing dimensions:
    volume_bucket  — BLOCKED: requires raw volume data not stored in DB.
                     Fix: polygon_actuarial_builder.py now outputs this for
                     future builds (added in same sprint).
    sector_bucket  — BLOCKED: requires external ticker→sector reference file.
                     No sector mapping exists in the current pipeline.

Usage:
    python vanguard/scripts/enrich_actuarial_9dim.py
    python vanguard/scripts/enrich_actuarial_9dim.py --db path/to/db.parquet
"""

from __future__ import annotations

import argparse
import shutil
import time
from pathlib import Path

import pandas as pd

DEFAULT_DB = r"C:\Users\ACKVerissimo\vanguard\data\actuarial_database_v6.parquet"


# ─────────────────────────────────────────────────────────────────────────────
# iv_regime
# ─────────────────────────────────────────────────────────────────────────────

def classify_iv_regime(df: pd.DataFrame) -> pd.Series:
    """
    Derive iv_regime from vol_regime + atr_percentile.

    True implied-volatility requires options chain data not available in the
    OHLCV-only pipeline. ATR percentile is the closest available realized-vol
    proxy. Classification mirrors what the live state_calculator infers:

        COMPRESSION + any         → LOW_IV   (range compressed, vol suppressed)
        NORMAL + atr_pct < 50     → NORMAL_IV
        NORMAL + atr_pct >= 50    → ELEVATED_IV
        EXPANSION                 → HIGH_IV  (vol expanding, volatility event)
    """
    vol     = df["vol_regime"].fillna("NORMAL").str.upper()
    atr_pct = pd.to_numeric(df["atr_percentile"], errors="coerce").fillna(50.0)

    regime = pd.Series("NORMAL_IV", index=df.index)
    regime = regime.where(~(vol == "EXPANSION"), "HIGH_IV")
    regime = regime.where(~((vol == "NORMAL") & (atr_pct >= 50)), "ELEVATED_IV")
    regime = regime.where(~((vol == "NORMAL") & (atr_pct < 50)), "NORMAL_IV")
    regime = regime.where(~(vol == "COMPRESSION"), "LOW_IV")
    return regime


# ─────────────────────────────────────────────────────────────────────────────
# horizon_bucket
# ─────────────────────────────────────────────────────────────────────────────

def classify_horizon_bucket(df: pd.DataFrame) -> pd.Series:
    """
    Label each historical row with the best-fit outcome horizon.

    Uses outcome_days_to_10pct (days until 10% gain was achieved) as the
    primary signal. Rows that never hit 10% are labelled by which absolute
    return horizon showed the strongest directional move.

        hit 10% within 5 days   → SHORT
        hit 10% within 10 days  → MEDIUM
        hit 10% in 11-20 days   → LONG
        never hit 10%:
          abs(5d) >= abs(10d) and abs(5d) >= abs(20d) → SHORT
          abs(10d) >= abs(20d)                        → MEDIUM
          else                                        → LONG
    """
    hit      = pd.to_numeric(df["outcome_hit_10pct_up"], errors="coerce").fillna(0) > 0
    days     = pd.to_numeric(df["outcome_days_to_10pct"], errors="coerce").fillna(20)
    ret5     = pd.to_numeric(df["outcome_5d_return"],  errors="coerce").fillna(0).abs()
    ret10    = pd.to_numeric(df["outcome_10d_return"], errors="coerce").fillna(0).abs()
    ret20    = pd.to_numeric(df["outcome_20d_return"], errors="coerce").fillna(0).abs()

    bucket = pd.Series("LONG", index=df.index)

    # Rows that hit 10% — assign by speed
    bucket = bucket.where(~(hit & (days <= 10)), "MEDIUM")
    bucket = bucket.where(~(hit & (days <= 5)),  "SHORT")

    # Rows that never hit 10% — assign by best absolute return horizon
    no_hit = ~hit
    bucket = bucket.where(~(no_hit & (ret5 >= ret10) & (ret5 >= ret20)), "SHORT")
    bucket = bucket.where(~(no_hit & (ret10 >= ret5)  & (ret10 >= ret20) & (bucket != "SHORT")), "MEDIUM")

    return bucket


# ─────────────────────────────────────────────────────────────────────────────
# crabel_state
# ─────────────────────────────────────────────────────────────────────────────

def classify_crabel_state(df: pd.DataFrame) -> pd.Series:
    """
    Proxy for Crabel inside-bar compression state using daily OHLCV-derived columns.

    The live wyckoff_crabel_precor_logic_v2.py computes this from intraday
    candlestick sequences (inside bars + ATR compression). For historical DB rows
    only daily aggregates are available, so we derive from:
        vol_regime     — COMPRESSION = ATR + BB both tight (best proxy)
        atr_pct_bucket — LOW = bottom 33rd percentile ATR
        adx_bucket     — WEAK = ADX < 20 (no trend = range-bound)

    Classification:
        CRABEL_READY — COMPRESSION vol_regime AND WEAK adx (tight range, flat)
        COILING      — LOW atr_pct_bucket AND (WEAK or MODERATE) adx
        NONE         — everything else (trending or vol-expanding)

    Priority: CRABEL_READY > COILING > NONE
    """
    vol  = df["vol_regime"].fillna("NORMAL").str.upper()
    atr  = df["atr_pct_bucket"].fillna("MID").str.upper()
    adx  = df["adx_bucket"].fillna("MODERATE").str.upper()

    state = pd.Series("NONE", index=df.index)

    coiling = (atr == "LOW") & (adx.isin(["WEAK", "MODERATE"]))
    state = state.where(~coiling, "COILING")

    crabel_ready = (vol == "COMPRESSION") & (adx == "WEAK")
    state = state.where(~crabel_ready, "CRABEL_READY")

    return state


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def enrich(db_path: Path) -> None:
    print("=" * 70)
    print("VANGUARD ACTUARIAL DB — 9-DIM ENRICHMENT (v1.0)")
    print("=" * 70)
    print(f"DB : {db_path}")
    print(f"Size: {db_path.stat().st_size / 1024 / 1024:.1f} MB")

    t0 = time.time()
    print("\nLoading parquet...", end=" ", flush=True)
    df = pd.read_parquet(db_path)
    print(f"done ({time.time()-t0:.1f}s)  |  {len(df):,} rows  |  {len(df.columns)} cols")

    already = [c for c in ("iv_regime", "horizon_bucket", "crabel_state") if c in df.columns]
    if len(already) == 3:
        print("\n✓ All 3 new dimension columns already present.")
        for col in already:
            print(f"  {col}: {df[col].value_counts().to_dict()}")
        return

    # Required columns guard
    required = ["vol_regime", "atr_percentile", "atr_pct_bucket", "adx_bucket",
                "outcome_hit_10pct_up", "outcome_days_to_10pct",
                "outcome_5d_return", "outcome_10d_return", "outcome_20d_return"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        print(f"\nERROR: Missing required columns: {missing}")
        return

    # Backup
    backup = db_path.parent / (db_path.stem + "_pre_9dim.parquet")
    print(f"\nBacking up -> {backup.name}...", end=" ", flush=True)
    shutil.copy2(db_path, backup)
    print("done")

    # iv_regime
    if "iv_regime" not in df.columns:
        print("\nClassifying iv_regime...", end=" ", flush=True)
        t1 = time.time()
        df["iv_regime"] = classify_iv_regime(df)
        print(f"done ({time.time()-t1:.1f}s)")
        print("  Distribution:", df["iv_regime"].value_counts().to_dict())

    # horizon_bucket
    if "horizon_bucket" not in df.columns:
        print("\nClassifying horizon_bucket...", end=" ", flush=True)
        t2 = time.time()
        df["horizon_bucket"] = classify_horizon_bucket(df)
        print(f"done ({time.time()-t2:.1f}s)")
        print("  Distribution:", df["horizon_bucket"].value_counts().to_dict())

    # crabel_state
    if "crabel_state" not in df.columns:
        print("\nClassifying crabel_state...", end=" ", flush=True)
        t3 = time.time()
        df["crabel_state"] = classify_crabel_state(df)
        print(f"done ({time.time()-t3:.1f}s)")
        print("  Distribution:", df["crabel_state"].value_counts().to_dict())

    # Null check
    print("\n--- Null audit (new columns) ---")
    for col in ("iv_regime", "horizon_bucket", "crabel_state"):
        null_pct = df[col].isna().mean() * 100
        print(f"  {col}: {null_pct:.2f}% null")

    # Cross-tabs for sanity
    print("\nCross-tab iv_regime × vol_regime:")
    print(pd.crosstab(df["iv_regime"], df["vol_regime"]).to_string())

    print("\nCross-tab crabel_state × vol_regime:")
    print(pd.crosstab(df["crabel_state"], df["vol_regime"]).to_string())

    # Save
    print(f"\nSaving enriched DB ({len(df.columns)} cols)...", end=" ", flush=True)
    t4 = time.time()
    df.to_parquet(db_path, index=False)
    print(f"done ({time.time()-t4:.1f}s)")
    print(f"\n✓ Saved: {db_path}")
    print(f"  New size : {db_path.stat().st_size / 1024 / 1024:.1f} MB")
    print(f"  Columns  : {len(df.columns)}")
    print(f"  Rows     : {len(df):,}")
    print(f"  Runtime  : {time.time()-t0:.1f}s total")
    print()
    print("MISSING DIMENSIONS (require external data — not added):")
    print("  volume_bucket  — raw volume not stored in DB; builder now outputs")
    print("                   this for future builds (polygon_actuarial_builder.py)")
    print("  sector_bucket  — needs ticker→sector reference file")
    print("=" * 70)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Enrich actuarial DB v6 with iv_regime, horizon_bucket, crabel_state"
    )
    parser.add_argument("--db", type=str, default=DEFAULT_DB)
    args = parser.parse_args()
    db_path = Path(args.db)
    if not db_path.exists():
        print(f"ERROR: DB not found: {db_path}")
        return
    enrich(db_path)


if __name__ == "__main__":
    main()
