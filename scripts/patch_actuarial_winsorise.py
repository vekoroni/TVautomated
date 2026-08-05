#!/usr/bin/env python3
"""
AVSHUNTER — Patch: Winsorise Extreme Returns in Actuarial Database

Caps outcome_5d_return and outcome_10d_return at ±100% to prevent
penny stock outliers from distorting EV calculations on normal signals.
Also fixes outcome_max_drawdown_5d/10d sign (should be negative or zero).

Safe: backup already exists from upgrade script.
"""
from pathlib import Path
import pandas as pd

DB_PATH = Path(r"C:\Users\ACKVerissimo\vanguard\data\actuarial_database.parquet")

print("Loading...")
df = pd.read_parquet(DB_PATH)
print(f"Loaded {len(df):,} rows")

# ── Winsorise returns at ±100% ─────────────────────────────────────────────
for col in ['outcome_5d_return', 'outcome_10d_return']:
    before_mean = df[col].mean()
    df[col] = df[col].clip(lower=-1.0, upper=1.0)
    print(f"{col}: mean before={before_mean:.4f} → after={df[col].mean():.4f}")

# ── Fix drawdown sign — should be ≤ 0 ────────────────────────────────────
# Max drawdown represents a drop so should be negative
# If positive values exist it means abs() was accidentally applied
for col in ['outcome_max_drawdown_5d', 'outcome_max_drawdown_10d']:
    pct_positive = (df[col] > 0).mean()
    if pct_positive > 0.4:
        # Majority positive — negate to make them losses
        df[col] = -df[col].abs()
        print(f"{col}: flipped to negative (was {pct_positive:.1%} positive)")
    else:
        df[col] = -df[col].abs()
        print(f"{col}: ensured negative (max drawdown is a loss)")

# ── Validation ─────────────────────────────────────────────────────────────
print("\nPost-patch stats:")
wr_5d  = (df['outcome_5d_return']  > 0).mean()
wr_10d = (df['outcome_10d_return'] > 0).mean()
wr_20d = (df['outcome_20d_return'] > 0).mean()
print(f"  Win rate 5d:  {wr_5d:.1%}")
print(f"  Win rate 10d: {wr_10d:.1%}")
print(f"  Win rate 20d: {wr_20d:.1%}")
print(f"  Mean 5d return:  {df['outcome_5d_return'].mean():.4f}")
print(f"  Mean 10d return: {df['outcome_10d_return'].mean():.4f}")
print(f"  Mean dd 5d:  {df['outcome_max_drawdown_5d'].mean():.4f}")
print(f"  Mean dd 10d: {df['outcome_max_drawdown_10d'].mean():.4f}")

print("\nSaving...")
df.to_parquet(DB_PATH, index=False, compression="snappy")
print(f"Done. {DB_PATH.stat().st_size/1e6:.1f} MB")
