"""Infrastructure persistence adapter for immutable Run Plans."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3

from domain.run_planning import RunPlan


def _iso_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


class RunPlanStore:
    """Append-only SQLite repository for immutable plan identities."""

    def __init__(self, database_path: Path | str):
        self.database_path = Path(database_path)

    def initialise(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.database_path)
        try:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS run_plans(
                    plan_hash TEXT PRIMARY KEY,
                    pipeline_run_id TEXT NOT NULL,
                    invocation_id TEXT NOT NULL UNIQUE,
                    evidence_cutoff_utc TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    persisted_at_utc TEXT NOT NULL
                )
                """
            )
            connection.commit()
        finally:
            connection.close()

    def persist(self, plan: RunPlan) -> bool:
        self.initialise()
        payload = json.dumps(plan.to_dict(), sort_keys=True, separators=(",", ":"))
        connection = sqlite3.connect(self.database_path)
        try:
            existing = connection.execute(
                "SELECT plan_hash, payload_json FROM run_plans WHERE invocation_id = ?",
                (plan.invocation_id,),
            ).fetchone()
            if existing:
                if existing[0] != plan.plan_hash or existing[1] != payload:
                    raise ValueError("invocation identity already has different immutable plan content")
                return False
            connection.execute(
                "INSERT INTO run_plans VALUES (?, ?, ?, ?, ?, ?)",
                (
                    plan.plan_hash,
                    plan.pipeline_run_id,
                    plan.invocation_id,
                    plan.evidence_cutoff_utc,
                    payload,
                    _iso_utc(datetime.now(timezone.utc)),
                ),
            )
            connection.commit()
        finally:
            connection.close()
        return True

    def load(self, invocation_id: str) -> dict | None:
        self.initialise()
        connection = sqlite3.connect(self.database_path)
        try:
            row = connection.execute(
                "SELECT payload_json FROM run_plans WHERE invocation_id = ?",
                (invocation_id,),
            ).fetchone()
        finally:
            connection.close()
        return json.loads(row[0]) if row else None


def write_plan_atomic(plan: RunPlan, destination: Path | str) -> Path:
    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(plan.to_dict(), indent=2), encoding="utf-8")
    os.replace(temporary, path)
    return path
