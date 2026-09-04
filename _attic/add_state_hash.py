"""
add_state_hash.py
=================
Adds the state_hash column to the existing actuarial database
using the EXACT same logic as StateVectorCalculator._generate_state_hash()

Hash formula (from state_calculator.py line 453-462):
  signature = f"{ticker}_{vol_regime}_{trend_direction}_{trend_maturity}_{structure_quality}_{catalyst_proximity}"
  state_hash = md5(signature.encode()).hexdigest()[:16]

Run:
    python add_state_hash.py

Output: overwrites actuarial_database.parquet with state_hash column added
"""

import pandas as pd
import hashlib

DB_PATH = r"C:\Users\ACKVerissimo\vanguard\data\actuarial_database.parquet"

print("Loading database...")
db = pd.read_parquet(DB_PATH)
print(f"  Rows: {len(db):,}")
print(f"  Columns: {db.columns.tolist()}")

# ── STEP 1: Check which hash fields exist ────────────────────────────────────
required = ['ticker', 'vol_regime', 'trend_direction', 'trend_maturity', 'structure_quality']
optional = ['catalyst_proximity']

print("\nChecking required columns for hash:")
missing = []
for c in required:
    present = c in db.columns
    sample = str(db[c].iloc[0]) if present else "MISSING"
    print(f"  {'OK' if present else 'MISSING':<8} {c:<25} sample: {sample}")
    if not present:
        missing.append(c)

print("\nChecking optional columns:")
for c in optional:
    present = c in db.columns
    sample = str(db[c].iloc[0]) if present else "MISSING - will default to 'NONE'"
    print(f"  {'OK' if present else 'ABSENT':<8} {c:<25} sample: {sample}")

if missing:
    print(f"\nERROR: Missing required columns: {missing}")
    print("Cannot reconstruct hash without these fields. The builder must be rerun.")
    raise SystemExit(1)

# ── STEP 2: Fill catalyst_proximity if absent ─────────────────────────────────
if 'catalyst_proximity' not in db.columns:
    print("\nAdding catalyst_proximity column defaulting to 'NONE'")
    print("NOTE: If the live pipeline produces non-NONE values for this field,")
    print("      hashes will still not match for those rows. Verify against live signals.")
    db['catalyst_proximity'] = 'NONE'

# ── STEP 3: Reconstruct the hash ─────────────────────────────────────────────
print("\nBuilding state_hash column...")

def compute_hash(row):
    # ticker intentionally excluded — matches updated state_calculator.py
    # observations pool across all stocks in the same market state
    parts = [
        str(row['vol_regime']),
        str(row['trend_direction']),
        str(row['trend_maturity']),
        str(row['structure_quality']),
        str(row['catalyst_proximity']),
    ]
    signature = "_".join(parts)
    return hashlib.md5(signature.encode()).hexdigest()[:16]

db['state_hash'] = db.apply(compute_hash, axis=1)

print(f"  Done. Sample hashes:")
for h in db['state_hash'].sample(5, random_state=42).tolist():
    print(f"    {h}")

# ── STEP 4: Stats ─────────────────────────────────────────────────────────────
print(f"\nUnique state hashes: {db['state_hash'].nunique():,}")
obs_per_hash = db.groupby('state_hash').size()
print(f"Observations per hash — min: {obs_per_hash.min()}, median: {obs_per_hash.median():.0f}, max: {obs_per_hash.max()}")
print(f"Hashes with >= 50 obs: {(obs_per_hash >= 50).sum():,}")
print(f"Hashes with >= 10 obs: {(obs_per_hash >= 10).sum():,}")
print(f"Hashes with < 10 obs:  {(obs_per_hash < 10).sum():,}")

# ── STEP 5: Save ──────────────────────────────────────────────────────────────
print(f"\nSaving to: {DB_PATH}")
db.to_parquet(DB_PATH, index=False)
import os
size_mb = os.path.getsize(DB_PATH) / (1024*1024)
print(f"Done. File size: {size_mb:.1f} MB")

# ── STEP 6: Cross-check against latest vanguard signals ───────────────────────
import glob
import os

runs_dir = r"C:\Users\ACKVerissimo\AVSHUNTER-Intelligence\data\output\runs"
runs = sorted(glob.glob(os.path.join(runs_dir, "2*")), reverse=True)
if runs:
    latest_signals = os.path.join(runs[0], "vanguard", "vanguard_signals.csv")
    if os.path.exists(latest_signals):
        print(f"\nCross-checking against: {latest_signals}")
        signals = pd.read_csv(latest_signals)
        if 'state_hash' in signals.columns:
            overlap = set(db['state_hash']) & set(signals['state_hash'])
            print(f"Signal hashes:     {signals['state_hash'].nunique():,} unique")
            print(f"DB hashes:         {db['state_hash'].nunique():,} unique")
            print(f"OVERLAP:           {len(overlap):,}")
            if len(overlap) > 0:
                print("\nSUCCESS - Layer 2 will now return real observations for matched hashes")
                # Show sample match
                sample_hash = list(overlap)[0]
                ticker = signals[signals['state_hash']==sample_hash]['ticker'].iloc[0]
                n_obs = len(db[db['state_hash']==sample_hash])
                print(f"Example: {ticker} -> {n_obs} historical observations in DB")
            else:
                print("\nWARNING: Zero overlap after hash reconstruction.")
                print("The catalyst_proximity field is likely the culprit.")
                print("\nCheck live signal hash format vs DB hash format:")
                print(f"  DB sample:     {db['state_hash'].iloc[0]}")
                print(f"  Signal sample: {signals['state_hash'].iloc[0]}")
                # Decode a signal hash to see what string produced it
                print("\nCheck catalyst_proximity values in live signals:")
                for col in signals.columns:
                    if 'catalyst' in col.lower() or 'proximity' in col.lower():
                        print(f"  {col}: {signals[col].value_counts().head(5).to_dict()}")
        else:
            print("vanguard_signals.csv has no state_hash column - check pipeline version")
    else:
        print(f"Could not find signals at: {latest_signals}")
else:
    print("No runs found for cross-check")
