"""Derive the governed v7 rebuild universe without losing historical-only names."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import pandas as pd


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--current", type=Path, required=True)
    parser.add_argument("--live-database", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    current_frame = pd.read_csv(args.current)
    current_column = next(name for name in current_frame if name.lower() in {"ticker", "symbol"})
    current = set(current_frame[current_column].dropna().astype(str).str.upper().str.strip())
    live_frame = pd.read_parquet(args.live_database, columns=["ticker"])
    historical = set(live_frame["ticker"].dropna().astype(str).str.upper().str.strip())
    tickers = sorted(current | historical)
    output = pd.DataFrame(
        {
            "ticker": tickers,
            "in_current_universe": [ticker in current for ticker in tickers],
            "in_live_v6": [ticker in historical for ticker in tickers],
        }
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(".csv.tmp")
    output.to_csv(temporary, index=False)
    os.replace(temporary, args.output)
    manifest = {
        "current_universe": str(args.current.resolve()),
        "live_database": str(args.live_database.resolve()),
        "current_unique": len(current),
        "live_v6_unique": len(historical),
        "union_unique": len(tickers),
        "current_only": len(current - historical),
        "historical_only": len(historical - current),
    }
    args.output.with_suffix(".json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
