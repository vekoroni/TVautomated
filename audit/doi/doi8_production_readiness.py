"""Read-only DOI-8 cohort support assessment for the live control plane."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATABASE = ROOT / "data/canonical/control_plane.sqlite"
TARGETS = (
    "LIQUIDITY_1D", "LIQUIDITY_2D", "LIQUIDITY_3D",
    "POSITIVE_RETURN", "RETURN_HURDLE", "TARGET_BEFORE_INVALIDATION",
)
DIRECTIONS = ("CALL", "PUT")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def assess(database: Path) -> dict:
    before_hash = _sha256(database)
    uri = f"file:{database.resolve().as_posix()}?mode=ro"
    with sqlite3.connect(uri, uri=True) as connection:
        tables = {
            row[0] for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        labels = connection.execute("SELECT COUNT(*) FROM doi_outcome_labels").fetchone()[0] if "doi_outcome_labels" in tables else 0
        assessments = connection.execute("SELECT COUNT(*) FROM doi_contract_assessments").fetchone()[0] if "doi_contract_assessments" in tables else 0
        direction_counts = {direction: 0 for direction in DIRECTIONS}
        complete_counts = {direction: 0 for direction in DIRECTIONS}
        if "doi_outcome_labels" in tables:
            for direction, count in connection.execute(
                "SELECT direction, COUNT(*) FROM doi_outcome_labels GROUP BY direction"
            ):
                direction_counts[direction] = count
            for direction, count in connection.execute(
                """SELECT direction, COUNT(*) FROM doi_outcome_labels
                   WHERE data_status IN ('COMPLETE','COMPLETE_OPTION_PATH_PARTIAL',
                                         'COMPLETE_OPTION_RETURN_UNAVAILABLE')
                   GROUP BY direction"""
            ):
                complete_counts[direction] = count
    after_hash = _sha256(database)
    cohorts = {
        f"{target}:{direction}": {
            "available_complete_labels_upper_bound": complete_counts[direction],
            "status": "INSUFFICIENT_SUPPORT",
            "probability_publishable": False,
        }
        for target in TARGETS for direction in DIRECTIONS
    }
    return {
        "schema": "doi8-production-readiness-v1",
        "assessed_at_utc": datetime.now(timezone.utc).isoformat(),
        "database": str(database.resolve()),
        "database_hash_before": before_hash,
        "database_hash_after": after_hash,
        "database_modified": before_hash != after_hash,
        "doi_outcome_table_present": "doi_outcome_labels" in tables,
        "doi_assessment_table_present": "doi_contract_assessments" in tables,
        "production_assessments": assessments,
        "production_outcome_labels": labels,
        "labels_by_direction": direction_counts,
        "complete_labels_by_direction": complete_counts,
        "cohorts": cohorts,
        "production_probability_status": "NOT_TRAINED_INSUFFICIENT_MATURE_COHORT",
        "active_fallback": "DOI5_DETERMINISTIC_ASSESSMENT",
        "synthetic_or_rehearsal_data_used_for_production_model": False,
        "provider_calls": 0,
        "decision_authority": "NONE",
        "can_grant_capital": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = assess(args.database)
    rendered = json.dumps(result, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if not result["database_modified"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
