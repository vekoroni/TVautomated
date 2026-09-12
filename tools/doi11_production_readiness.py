"""Read-only DOI-11 production acceptance assessor.

This command never initialises or migrates the control plane.  It validates the
artefacts produced by a completed-session run and, optionally, its Morning Gate
continuation.  A missing live cycle is reported as AWAITING_LIVE_CYCLE rather
than being concealed by offline test success.
"""

from __future__ import annotations

import argparse
from contextlib import closing
from dataclasses import dataclass
import json
from pathlib import Path
import sqlite3
from typing import Any


REQUIRED_TABLES = (
    "doi_contract_families",
    "doi_contract_assessments",
    "doi_preferred_contract_decisions",
    "doi_lifecycle_events",
    "doi_family_rankings",
)


@dataclass(frozen=True, slots=True)
class AcceptanceCheck:
    name: str
    status: str
    detail: str

    def to_dict(self) -> dict[str, str]:
        return {"name": self.name, "status": self.status, "detail": self.detail}


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _tables(connection: sqlite3.Connection) -> set[str]:
    return {
        str(row[0])
        for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }


def assess_doi11(
    *, run_id: str, project_root: Path | str, require_morning: bool = False,
) -> dict[str, Any]:
    root = Path(project_root)
    run_root = root / "data" / "output" / "runs" / run_id
    options_dir = run_root / "options"
    report_path = options_dir / f"dynamic_options_intelligence_{run_id}.json"
    book_path = run_root / "intelligence_lab" / f"final_opportunity_book_{run_id}.json"
    morning_path = run_root / "morning_validation" / f"morning_validated_trades_{run_id}.csv"
    runtime_path = root / "config" / "doi_runtime.json"
    database_path = root / "data" / "canonical" / "control_plane.sqlite"

    checks: list[AcceptanceCheck] = []
    runtime = _read_json(runtime_path)
    runtime_ok = bool(
        runtime
        and runtime.get("enabled") is True
        and runtime.get("canonical_reuse_only") is True
        and runtime.get("provider_fetch_allowed") is False
        and runtime.get("decision_authority") == "NONE"
        and runtime.get("execution_authority") == "HUMAN_ONLY"
    )
    checks.append(AcceptanceCheck(
        "governed_runtime", "PASS" if runtime_ok else "FAIL",
        "active, reuse-only, provider-free and advisory" if runtime_ok else "runtime contract is absent or unsafe",
    ))

    report = _read_json(report_path)
    if report is None:
        checks.append(AcceptanceCheck(
            "completed_session_report", "AWAITING",
            f"no DOI-11 report for run {run_id}",
        ))
    else:
        retained = int(report.get("retained_opportunities") or 0)
        unique = int(report.get("unique_tickers") or 0)
        deleted = int(report.get("deleted_opportunities") or 0)
        fetches = int(report.get("physical_fetch_count") or 0)
        invariant = retained == unique and deleted == 0 and fetches == 0
        checks.append(AcceptanceCheck(
            "completed_session_report", "PASS" if invariant else "FAIL",
            f"unique={unique} retained={retained} deleted={deleted} provider_fetches={fetches}",
        ))

    counts: dict[str, int] = {}
    authority_violations = 0
    missing_tables: list[str] = []
    try:
        uri = f"file:{database_path.as_posix()}?mode=ro"
        with closing(sqlite3.connect(uri, uri=True)) as connection:
            existing = _tables(connection)
            missing_tables = sorted(set(REQUIRED_TABLES) - existing)
            if not missing_tables:
                counts["families"] = int(connection.execute(
                    "SELECT COUNT(*) FROM doi_contract_families WHERE run_id=?", (run_id,),
                ).fetchone()[0])
                counts["assessments"] = int(connection.execute(
                    "SELECT COUNT(*) FROM doi_contract_assessments WHERE run_id=?", (run_id,),
                ).fetchone()[0])
                counts["preferred_decisions"] = int(connection.execute(
                    "SELECT COUNT(*) FROM doi_preferred_contract_decisions WHERE run_id=?", (run_id,),
                ).fetchone()[0])
                counts["lifecycle_events"] = int(connection.execute(
                    "SELECT COUNT(*) FROM doi_lifecycle_events WHERE run_id=?", (run_id,),
                ).fetchone()[0])
                counts["rankings"] = int(connection.execute(
                    "SELECT COUNT(*) FROM doi_family_rankings r JOIN doi_contract_families f "
                    "ON f.family_id=r.family_id WHERE f.run_id=?", (run_id,),
                ).fetchone()[0])
                authority_violations += int(connection.execute(
                    "SELECT COUNT(*) FROM doi_contract_families WHERE run_id=? AND "
                    "(decision_authority<>'NONE' OR can_change_direction<>0 OR "
                    "can_invalidate_thesis<>0 OR can_grant_capital<>0)", (run_id,),
                ).fetchone()[0])
                authority_violations += int(connection.execute(
                    "SELECT COUNT(*) FROM doi_contract_assessments WHERE run_id=? AND "
                    "(decision_authority<>'NONE' OR can_change_direction<>0 OR "
                    "can_invalidate_thesis<>0 OR can_grant_capital<>0)", (run_id,),
                ).fetchone()[0])
    except sqlite3.Error as error:
        missing_tables = [f"DATABASE_ERROR:{error}"]

    tables_ok = not missing_tables
    checks.append(AcceptanceCheck(
        "canonical_persistence", "PASS" if tables_ok else "AWAITING",
        json.dumps(counts, sort_keys=True) if tables_ok else ",".join(missing_tables),
    ))
    checks.append(AcceptanceCheck(
        "authority_separation", "PASS" if tables_ok and authority_violations == 0 else ("AWAITING" if not tables_ok else "FAIL"),
        f"violations={authority_violations}",
    ))

    book = _read_json(book_path)
    if book is None:
        checks.append(AcceptanceCheck("lab_projection", "AWAITING", "final opportunity book not produced"))
    else:
        rows = book.get("rows") if isinstance(book.get("rows"), list) else []
        expected = int(book.get("candidate_count") or len(rows))
        schema = str(book.get("lab_schema_version") or "")
        doi_rows = sum(
            1 for row in rows
            if row.get("doi_projection_state")
            and row.get("doi_decision_authority") == "NONE"
            and row.get("doi_execution_authority") == "HUMAN_ONLY"
        )
        # The durable population book remains the governed v2 source. The Lab
        # composes its v4 view at read time by overlaying the accepted atomic
        # handoff. DOI-10 fields must nevertheless be materialised for every
        # base-book row before that overlay is permitted.
        reconciled = (
            expected == len(rows)
            and schema == "lab_signal_book_v2"
            and doi_rows == len(rows)
        )
        checks.append(AcceptanceCheck(
            "lab_projection", "PASS" if reconciled else "FAIL",
            f"base_schema={schema or 'MISSING'} candidate_count={expected} "
            f"rows={len(rows)} doi_advisory_rows={doi_rows}",
        ))

    morning_exists = morning_path.is_file()
    checks.append(AcceptanceCheck(
        "morning_cycle", "PASS" if morning_exists else "AWAITING",
        str(morning_path) if morning_exists else "next valid Morning Gate has not completed",
    ))

    failed = [item for item in checks if item.status == "FAIL"]
    awaiting = [item for item in checks if item.status == "AWAITING"]
    if failed:
        status = "NOT_READY"
    elif awaiting and (require_morning or any(item.name != "morning_cycle" for item in awaiting)):
        status = "AWAITING_LIVE_CYCLE"
    elif awaiting:
        status = "EVENING_ACCEPTED_AWAITING_MORNING"
    else:
        status = "PRODUCTION_ACCEPTED"
    return {
        "schema_version": "doi11_production_acceptance_v1",
        "run_id": run_id,
        "status": status,
        "decision_authority": "NONE",
        "execution_authority": "HUMAN_ONLY",
        "require_morning": require_morning,
        "checks": [item.to_dict() for item in checks],
        "database_counts": counts,
        "report_path": str(report_path),
        "book_path": str(book_path),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--require-morning", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = assess_doi11(
        run_id=args.run_id, project_root=args.project_root,
        require_morning=args.require_morning,
    )
    rendered = json.dumps(result, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        temporary = args.output.with_suffix(args.output.suffix + ".tmp")
        temporary.write_text(rendered, encoding="utf-8")
        temporary.replace(args.output)
    print(rendered)
    return 0 if result["status"] in {"PRODUCTION_ACCEPTED", "EVENING_ACCEPTED_AWAITING_MORNING"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
