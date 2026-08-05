#!/usr/bin/env python3
"""Validate AVSHUNTER behaviour-state split against a Vanguard CSV."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from behaviour_state_builder import enrich_dataframe


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("vanguard_csv", type=Path)
    parser.add_argument("--target-hash", default="df39b8cf5f786f07")
    args = parser.parse_args()

    df = pd.read_csv(args.vanguard_csv, low_memory=False)
    enriched = enrich_dataframe(df)

    print(f"Rows: {len(enriched)}")
    print(f"Unique broad hashes:     {enriched['state_hash'].nunique() if 'state_hash' in enriched else 0}")
    print(f"Unique behaviour hashes: {enriched['behaviour_state_hash'].nunique()}")
    if "state_hash" in enriched:
        print(f"Avg tickers/broad hash:  {len(enriched)/max(enriched['state_hash'].nunique(), 1):.1f}")
    print(f"Avg tickers/behav hash:  {len(enriched)/max(enriched['behaviour_state_hash'].nunique(), 1):.1f}")

    parts = enriched["behaviour_state_key"].str.split("|", expand=True)
    parts.columns = ["phase", "momentum", "location", "trigger", "horizon", "direction", "catalyst"]
    print("\nUNK audit:")
    for col in parts.columns:
        print(f"  {col}: {(parts[col] == 'UNK').mean() * 100:.1f}%")

    if "state_hash" in enriched:
        bucket = enriched[enriched["state_hash"].astype(str) == args.target_hash]
        print(f"\nTarget broad bucket {args.target_hash}: {len(bucket)} rows")
        print(bucket["behaviour_state_key"].value_counts().head(20).to_string())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
