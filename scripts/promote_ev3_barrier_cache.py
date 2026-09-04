"""Validate and atomically promote an EV3 barrier sidecar to its governed path."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import sys
from typing import Any, Sequence
import uuid

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from vanguard.ev3_stage0 import (
    DEFAULT_HORIZONS,
    DEFAULT_STOP_GRID,
    DEFAULT_TARGET_GRID,
    EV3_BARRIER_SCHEMA_VERSION,
    sha256_file,
)


GOVERNED_FINAL = Path(r"C:\Users\ACKVerissimo\vanguard\data\ev3_barrier_outcome_cache.parquet")


def validate_candidate(
    frame: pd.DataFrame,
    *,
    targets: Sequence[float] = DEFAULT_TARGET_GRID,
    stops: Sequence[float] = DEFAULT_STOP_GRID,
    horizons: Sequence[int] = DEFAULT_HORIZONS,
) -> dict[str, Any]:
    key = [
        "state_key", "direction", "horizon_sessions",
        "target_distance_fraction", "stop_distance_fraction",
    ]
    required = set(key) | {
        "p_target_first", "p_stop_first", "p_timeout", "n_effective",
        "schema_version", "calculation_version",
    }
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"candidate missing required columns: {missing}")
    if frame.empty:
        raise ValueError("candidate is empty")
    duplicates = int(frame.duplicated(key).sum())
    if duplicates:
        raise ValueError(f"candidate contains {duplicates} duplicate lookup keys")
    probability_error = (
        frame[["p_target_first", "p_stop_first", "p_timeout"]].sum(axis=1) - 1.0
    ).abs()
    if not np.isfinite(probability_error).all() or float(probability_error.max()) > 1e-9:
        raise ValueError("candidate probabilities are not finite and exhaustive")
    if (pd.to_numeric(frame["n_effective"], errors="coerce") <= 0).any():
        raise ValueError("candidate contains non-positive n_effective")
    if set(frame["schema_version"].astype(str)) != {EV3_BARRIER_SCHEMA_VERSION}:
        raise ValueError(
            f"candidate schema is not {EV3_BARRIER_SCHEMA_VERSION}: "
            f"{sorted(frame['schema_version'].astype(str).unique())}"
        )
    actual_targets = sorted(float(value) for value in frame["target_distance_fraction"].unique())
    actual_stops = sorted(float(value) for value in frame["stop_distance_fraction"].unique())
    actual_horizons = sorted(int(value) for value in frame["horizon_sessions"].unique())
    if not np.allclose(actual_targets, sorted(targets), atol=1e-12):
        raise ValueError(f"target grid mismatch: {actual_targets}")
    if not np.allclose(actual_stops, sorted(stops), atol=1e-12):
        raise ValueError(f"stop grid mismatch: {actual_stops}")
    if actual_horizons != sorted(horizons):
        raise ValueError(f"horizon grid mismatch: {actual_horizons}")
    expected_cells = len(targets) * len(stops)
    group_sizes = frame.groupby(["state_key", "direction", "horizon_sessions"], dropna=False).size()
    if not (group_sizes == expected_cells).all():
        raise ValueError("one or more state/direction/horizon groups lack the complete grid")
    return {
        "rows": int(len(frame)),
        "states": int(frame["state_key"].nunique()),
        "directions": sorted(frame["direction"].astype(str).unique()),
        "horizons": actual_horizons,
        "target_grid": actual_targets,
        "stop_grid": actual_stops,
        "duplicates": duplicates,
        "maximum_probability_sum_error": float(probability_error.max()),
        "minimum_n_effective": float(frame["n_effective"].min()),
        "status": "PASS",
    }


def promote(source: Path, output: Path = GOVERNED_FINAL) -> dict[str, Any]:
    source = source.resolve()
    output = output.resolve()
    if not source.exists():
        raise FileNotFoundError(source)
    audit_path = source.with_suffix(".audit.json")
    if not audit_path.exists():
        raise FileNotFoundError(f"candidate audit missing: {audit_path}")
    source_audit = json.loads(audit_path.read_text(encoding="utf-8"))
    if source_audit.get("status") != "PASS":
        raise ValueError("candidate builder audit did not pass")
    source_hash = sha256_file(source)
    if str(source_audit.get("output_sha256")) != source_hash:
        raise ValueError("candidate hash does not match builder audit")
    validation = validate_candidate(pd.read_parquet(source))

    output.parent.mkdir(parents=True, exist_ok=True)
    backup_path: Path | None = None
    if output.exists():
        backup_dir = output.parent / "backups" / "ev3_barrier_cache"
        backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup_path = backup_dir / f"{output.stem}_{stamp}{output.suffix}"
        shutil.copy2(output, backup_path)
    temporary = output.with_name(f".{output.name}.{uuid.uuid4().hex}.tmp")
    try:
        shutil.copy2(source, temporary)
        if sha256_file(temporary) != source_hash:
            raise ValueError("temporary promotion copy failed hash verification")
        os.replace(temporary, output)
    finally:
        if temporary.exists():
            temporary.unlink()

    promoted_utc = datetime.now(timezone.utc).isoformat()
    final_audit = dict(source_audit)
    final_audit.update(
        non_authoritative=False,
        production_consumer_enabled=True,
        governed_final=True,
        promoted_utc=promoted_utc,
        promoted_from=str(source),
        output=str(output),
        output_sha256=sha256_file(output),
        promotion_validation=validation,
    )
    output.with_suffix(".audit.json").write_text(
        json.dumps(final_audit, indent=2, sort_keys=True), encoding="utf-8",
    )
    manifest = {
        "schema_version": "ev3-cache-promotion-v1",
        "status": "PROMOTED",
        "promoted_utc": promoted_utc,
        "source": str(source),
        "source_sha256": source_hash,
        "output": str(output),
        "output_sha256": sha256_file(output),
        "backup": str(backup_path) if backup_path else None,
        "validation": validation,
    }
    output.with_suffix(".promotion.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8",
    )
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", type=Path, default=GOVERNED_FINAL)
    args = parser.parse_args()
    print(json.dumps(promote(args.source, args.output), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
