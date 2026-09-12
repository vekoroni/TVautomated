"""Read-only DOI-9 production ranking readiness assessment."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATABASE = ROOT / "data/canonical/control_plane.sqlite"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _count(connection: sqlite3.Connection, tables: set[str], table: str) -> int:
    if table not in tables:
        return 0
    return int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])


def assess(database: Path) -> dict:
    """Inspect readiness without installing schema or mutating the database."""

    before_hash = _sha256(database)
    uri = f"file:{database.resolve().as_posix()}?mode=ro"
    with sqlite3.connect(uri, uri=True) as connection:
        tables = {
            row[0] for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        counts = {
            name: _count(connection, tables, name)
            for name in (
                "doi_contract_assessments",
                "doi_outcome_labels",
                "doi_probability_models",
                "doi_probability_inferences",
                "doi_ranking_policies",
                "doi_family_rankings",
            )
        }
        accepted_models = 0
        if "doi_probability_models" in tables:
            accepted_models = int(connection.execute(
                "SELECT COUNT(*) FROM doi_probability_models WHERE status='ACCEPTED'"
            ).fetchone()[0])
        accepted_policies = 0
        if "doi_ranking_policies" in tables:
            accepted_policies = int(connection.execute(
                "SELECT COUNT(*) FROM doi_ranking_policies WHERE status='ACCEPTED'"
            ).fetchone()[0])
    after_hash = _sha256(database)
    calibrated_ready = (
        counts["doi_contract_assessments"] > 0
        and counts["doi_outcome_labels"] > 0
        and accepted_models >= 3
        and accepted_policies > 0
    )
    return {
        "schema": "doi9-production-readiness-v1",
        "assessed_at_utc": datetime.now(timezone.utc).isoformat(),
        "database": str(database.resolve()),
        "database_hash_before": before_hash,
        "database_hash_after": after_hash,
        "database_modified": before_hash != after_hash,
        "table_presence": {
            name: name in tables for name in counts
        },
        "row_counts": counts,
        "accepted_probability_models": accepted_models,
        "accepted_ranking_policies": accepted_policies,
        "calibrated_ranking_ready": calibrated_ready,
        "active_mode_if_invoked": (
            "CALIBRATED_POLICY" if calibrated_ready
            else "DOI5_DETERMINISTIC_FALLBACK"
        ),
        "candidate_deletion_allowed": False,
        "provider_calls": 0,
        "decision_authority": "NONE",
        "execution_authority": "HUMAN_ONLY",
        "production_integration_deferred_to": "DOI10",
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
