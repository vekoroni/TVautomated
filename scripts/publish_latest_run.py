#!/usr/bin/env python3
"""
publish_latest_run.py

AVSHUNTER Stability Publisher (v1.1)
====================================

Deterministic publish stage for discovery runs.

Fix v1.1:
- Robust run_id detection using strict regex: YYYYMMDD_HHMMSS
  Only considers files matching:
    discovery_summary_ultimate_<RUNID>.json
  where RUNID matches \d{8}_\d{6}.

Responsibilities:
- Detect run_id from discovery artefacts (or accept --run-id)
- Validate required artefacts exist
- Ensure runs/<run_id>/packages/ exists (scaffold)
- Ensure packages/index.json exists (empty scaffold index)
- Atomically update data/output/latest.json (temp + replace)

Fail-Closed Behaviour:
If any validation fails → script exits non-zero and DOES NOT update latest.json.
"""

from __future__ import annotations

from pathlib import Path
import json
import argparse
import re
from datetime import datetime, timezone


# Strict run_id format: 20260211_213317
RUNID_RE = re.compile(r"^(?P<prefix>discovery_summary_ultimate_)"
                      r"(?P<run_id>\d{8}_\d{6})"
                      r"$")


REQUIRED_FILES = [
    "discovery_summary_ultimate_{run_id}.json",
    "discovery_candidates_ultimate_{run_id}.csv",
    "final_watchlist_ultimate_{run_id}.csv",
    "early_positions_ultimate_{run_id}.csv",
]


def detect_latest_run_id(output_dir: Path) -> str:
    """Detect newest run_id by scanning strictly-matching summary files."""
    candidates = []
    for p in output_dir.glob("discovery_summary_ultimate_*.json"):
        stem = p.stem  # filename without .json
        m = RUNID_RE.match(stem)
        if not m:
            # Ignore legacy/other naming to prevent false IDs like '220924'
            continue
        run_id = m.group("run_id")
        candidates.append((p.stat().st_mtime, run_id, p))
    if not candidates:
        raise RuntimeError(
            "No strictly-matching discovery summary files found. "
            "Expected: discovery_summary_ultimate_<YYYYMMDD_HHMMSS>.json"
        )
    candidates.sort(key=lambda x: x[0])
    return candidates[-1][1]


def validate_run(output_dir: Path, run_id: str) -> None:
    missing = []
    for pattern in REQUIRED_FILES:
        file_path = output_dir / pattern.format(run_id=run_id)
        if not file_path.exists():
            missing.append(str(file_path))
    if missing:
        raise RuntimeError(
            f"Missing required artefacts for run {run_id}:\n" + "\n".join(missing)
        )


def ensure_run_scaffold(root: Path, run_id: str) -> Path:
    run_dir = root / "data" / "output" / "runs" / run_id
    packages_dir = run_dir / "packages"
    packages_dir.mkdir(parents=True, exist_ok=True)

    index_path = packages_dir / "index.json"
    if not index_path.exists():
        index_data = {
            "run_id": run_id,
            "packages": []
        }
        index_path.write_text(json.dumps(index_data, indent=4), encoding="utf-8")

    return run_dir


def atomic_update_latest(output_dir: Path, run_id: str) -> None:
    latest_path = output_dir / "latest.json"
    temp_path = output_dir / "latest.tmp.json"

    latest_data = {
        "schema_version": "1.0",
        "run_id": run_id,
        "outputs": {
            "output_dir": str(output_dir.resolve()),
            "summary_json": str((output_dir / f"discovery_summary_ultimate_{run_id}.json").resolve()),
            "early_positions_csv": str((output_dir / f"early_positions_ultimate_{run_id}.csv").resolve()),
            "watchlist_csv": str((output_dir / f"final_watchlist_ultimate_{run_id}.csv").resolve()),
            "candidates_csv": str((output_dir / f"discovery_candidates_ultimate_{run_id}.csv").resolve()),
        },
        "mode": "discovery",
        "created_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    }

    temp_path.write_text(json.dumps(latest_data, indent=4), encoding="utf-8")
    temp_path.replace(latest_path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", default=None, help="Specify run_id explicitly (YYYYMMDD_HHMMSS)")
    parser.add_argument("--root", default=".", help="Project root directory")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    output_dir = root / "data" / "output"

    if not output_dir.exists():
        raise RuntimeError("data/output directory not found.")

    run_id = args.run_id or detect_latest_run_id(output_dir)

    # Enforce strict run_id format even when provided manually
    if not re.fullmatch(r"\d{8}_\d{6}", run_id):
        raise RuntimeError(
            f"Invalid run_id format: {run_id}. Expected YYYYMMDD_HHMMSS (e.g., 20260211_213317)."
        )

    print(f"Detected run_id: {run_id}")

    validate_run(output_dir, run_id)
    print("Artefact validation PASSED.")

    run_dir = ensure_run_scaffold(root, run_id)
    print(f"Run scaffold ensured: {run_dir}")

    atomic_update_latest(output_dir, run_id)
    print("latest.json updated atomically.")

    print("PUBLISH COMPLETE (fail-closed safe).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
