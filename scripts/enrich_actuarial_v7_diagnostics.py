"""Atomically add deterministic v6-compatible diagnostics to v7 ticker shards."""

from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import json
import os
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq


DIAGNOSTIC_VERSION = "actuarial_diagnostics_v7.0.0"
REQUIRED = {
    "momentum_score", "state_v2", "momentum_next", "momentum_delta",
    "atr_next", "atr_delta", "adx_next", "adx_delta",
    "transition_flag_v2", "future_momentum_bucket", "early_candidate",
}


def _bucket(score: float) -> object:
    if pd.isna(score):
        return pd.NA
    return "LOW" if score < 15 else "MID" if score < 30 else "HIGH" if score < 45 else "EXTREME"


def _enrich(path: Path) -> tuple[str, int]:
    existing = set(pq.read_schema(path).names)
    if REQUIRED.issubset(existing):
        return "REUSED", pq.ParquetFile(path).metadata.num_rows
    frame = pd.read_parquet(path)
    frame["momentum_score"] = frame["adx"] * frame["atr_percentile"] / 100
    frame["state_v2"] = (
        frame["vol_regime"].astype("string").fillna("UNKNOWN") + "|" +
        frame["trend_direction"].astype("string").fillna("UNKNOWN") + "|" +
        frame["structure_quality"].astype("string").fillna("UNKNOWN") + "|" +
        frame["phase_v2"].astype("string").fillna("UNKNOWN") + "|" +
        frame["momentum_bucket"].astype("string").fillna("UNKNOWN") + "|" +
        frame["location_bucket"].astype("string").fillna("UNKNOWN")
    )
    frame["momentum_next"] = frame["momentum_score"].shift(-1)
    frame["momentum_delta"] = frame["momentum_next"] - frame["momentum_score"]
    frame["atr_next"] = frame["atr_percentile"].shift(-1)
    frame["atr_delta"] = frame["atr_next"] - frame["atr_percentile"]
    frame["adx_next"] = frame["adx"].shift(-1)
    frame["adx_delta"] = frame["adx_next"] - frame["adx"]
    frame["transition_flag_v2"] = (
        (frame["momentum_score"] > 10) & (frame["momentum_score"] < 30) &
        (frame["momentum_delta"] > 0) &
        (frame["atr_percentile"] < 60) & (frame["adx"] < 30)
    ).astype("int64")
    frame["future_momentum_bucket"] = frame["momentum_next"].map(_bucket).astype("string")
    frame["early_candidate"] = (
        frame["momentum_bucket"].eq("MID") &
        frame["location_bucket"].isin(["MID_RANGE", "NEAR_LOW"]) &
        frame["phase_v2"].eq("EARLY_TRANSITION")
    ).astype("int64")
    frame["diagnostics_contract_version"] = DIAGNOSTIC_VERSION
    temporary = path.with_suffix(".parquet.enriching")
    frame.to_parquet(temporary, index=False, compression="snappy")
    os.replace(temporary, path)
    return "ENRICHED", len(frame)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--parts-dir", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()
    manifest_path = args.parts_dir / "_parts_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    parts = sorted(args.parts_dir.glob("*.parquet"))
    with ProcessPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(_enrich, path): path for path in parts}
        counts = {"ENRICHED": 0, "REUSED": 0}
        rows = 0
        for index, future in enumerate(as_completed(futures), 1):
            status, part_rows = future.result()
            counts[status] += 1
            rows += part_rows
            if index % 100 == 0 or index == len(parts):
                print(f"[{index}/{len(parts)}] enriched={counts['ENRICHED']} reused={counts['REUSED']}", flush=True)
    manifest["diagnostics_contract_version"] = DIAGNOSTIC_VERSION
    manifest["diagnostics_status"] = "COMPLETE"
    temporary = manifest_path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    os.replace(temporary, manifest_path)
    print(json.dumps({"status": "COMPLETE", "parts": len(parts), "rows": rows, **counts}, indent=2))


if __name__ == "__main__":
    main()
