#!/usr/bin/env python3
"""Create a hash-verified, non-secret CDS implementation baseline.

The utility copies only the production scripts and small manifests named in
``BASELINE_PATHS``.  Provider keys, environment files, databases and market
data payloads are deliberately excluded.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]

BASELINE_PATHS = (
    "intelligent_orchestrator.py",
    "run_evening.bat",
    "run_premarket.bat",
    "avshunter_discovery_ULTIMATE.py",
    "garch_runner.py",
    "morning_gate.py",
    "polygon_data_fetcher.py",
    "scripts/avshunter_universe_scanner.py",
    "scripts/avshunter_options_intelligence.py",
    "scripts/backfill_timeseries_into_packages.py",
    "docs/AVSHUNTER_CANONICAL_DATA_SYSTEM_SOLUTION_DESIGN_v1.md",
    "data/output/runs/20260821_090928/final_run_manifest.json",
    "data/output/runs/20260821_090928/packages/index.json",
    "data/output/runs/20260821_090928/options/options_intelligence_summary_20260821_090928.json",
    "data/output/runs/20260821_090928/morning_validation/morning_gate_summary_20260821_090928.json",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git_status() -> str:
    try:
        completed = subprocess.run(
            ["git", "status", "--short", "--untracked-files=all"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        return completed.stdout
    except OSError as exc:
        return f"UNAVAILABLE: {exc}"


def create_baseline(destination: Path) -> dict[str, Any]:
    destination = destination.resolve()
    if destination.exists():
        raise FileExistsError(f"Refusing to overwrite existing baseline: {destination}")
    destination.mkdir(parents=True)

    records: list[dict[str, Any]] = []
    for relative_text in BASELINE_PATHS:
        source = REPO_ROOT / relative_text
        record: dict[str, Any] = {
            "relative_path": relative_text.replace("\\", "/"),
            "exists": source.is_file(),
        }
        if source.is_file():
            target = destination / "files" / relative_text
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            source_hash = _sha256(source)
            copied_hash = _sha256(target)
            if copied_hash != source_hash:
                raise RuntimeError(f"Backup verification failed: {relative_text}")
            record.update(
                {
                    "size_bytes": source.stat().st_size,
                    "sha256": source_hash,
                    "backup_relative_path": str(target.relative_to(destination)).replace("\\", "/"),
                    "backup_sha256": copied_hash,
                }
            )
        records.append(record)

    created_at = datetime.now(timezone.utc).isoformat()
    manifest = {
        "contract_version": "cds_baseline_v1",
        "created_at_utc": created_at,
        "repository_root": str(REPO_ROOT),
        "purpose": "CDS-0 pre-change baseline for CDS-1 control-plane implementation",
        "secret_files_included": False,
        "database_payloads_included": False,
        "reference_run_id": "20260821_090928",
        "files": records,
        "all_present_backups_verified": all(
            not row["exists"] or row.get("sha256") == row.get("backup_sha256")
            for row in records
        ),
        "git_status_at_capture": _git_status().splitlines(),
    }

    manifest_path = destination / "baseline_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    readme = destination / "README.md"
    readme.write_text(
        "# CDS-0 pre-change baseline\n\n"
        f"Created: `{created_at}`\n\n"
        "This directory contains hash-verified copies of the active scripts and "
        "small reference-run manifests in scope for the canonical data project. "
        "It intentionally contains no `.env` files, API keys, databases, Parquet "
        "payloads or bulk market data.\n\n"
        "## Restore\n\n"
        "1. Disable all `AVSHUNTER_CANONICAL_*` feature flags.\n"
        "2. Compare the target file against `baseline_manifest.json`.\n"
        "3. Restore only the explicitly approved file from `files/`; never copy "
        "the whole directory over the repository.\n"
        "4. Re-run the focused regression suite before restarting production.\n",
        encoding="utf-8",
    )
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--destination", required=True, type=Path)
    args = parser.parse_args()
    manifest = create_baseline(args.destination)
    existing = sum(1 for row in manifest["files"] if row["exists"])
    print(
        json.dumps(
            {
                "destination": str(args.destination.resolve()),
                "files_backed_up": existing,
                "verified": manifest["all_present_backups_verified"],
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
