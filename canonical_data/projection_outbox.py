"""Durable SQLite outbox for canonical dataset projections."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from enum import Enum
import json
from pathlib import Path
import sqlite3
from typing import Iterable

from domain.data_projection import CanonicalDatasetCommitted


PROJECTION_OUTBOX_SCHEMA_VERSION = "canonical-projection-outbox-v1"


class ProjectionDeliveryState(str, Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED_RETRYABLE = "FAILED_RETRYABLE"


def ensure_projection_outbox_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS projection_outbox (
            event_id TEXT PRIMARY KEY,
            event_type TEXT NOT NULL,
            event_version TEXT NOT NULL,
            projection_name TEXT NOT NULL,
            dataset_id TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            delivery_state TEXT NOT NULL,
            attempt_count INTEGER NOT NULL DEFAULT 0,
            created_at_utc TEXT NOT NULL,
            started_at_utc TEXT,
            completed_at_utc TEXT,
            last_error TEXT NOT NULL DEFAULT '',
            FOREIGN KEY(dataset_id) REFERENCES dataset_registry(dataset_id)
        );

        CREATE UNIQUE INDEX IF NOT EXISTS idx_projection_dataset_name
            ON projection_outbox(dataset_id, projection_name, event_version);

        CREATE INDEX IF NOT EXISTS idx_projection_delivery
            ON projection_outbox(projection_name, delivery_state, created_at_utc);

        CREATE TABLE IF NOT EXISTS projection_schema_metadata (
            schema_version TEXT PRIMARY KEY,
            installed_at_utc TEXT NOT NULL
        );
        """
    )
    connection.execute(
        "INSERT OR IGNORE INTO projection_schema_metadata"
        "(schema_version, installed_at_utc) VALUES (?, ?)",
        (PROJECTION_OUTBOX_SCHEMA_VERSION, datetime.now(timezone.utc).isoformat()),
    )


def enqueue_projection_event(
    connection: sqlite3.Connection, event: CanonicalDatasetCommitted
) -> bool:
    """Insert one event in the caller's dataset-registration transaction."""

    ensure_projection_outbox_schema(connection)
    cursor = connection.execute(
        """
        INSERT OR IGNORE INTO projection_outbox(
            event_id, event_type, event_version, projection_name, dataset_id,
            payload_json, delivery_state, created_at_utc
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            event.event_id,
            event.event_type.value,
            event.event_version,
            event.projection_name,
            event.dataset_id,
            json.dumps(event.to_dict(), sort_keys=True, separators=(",", ":")),
            ProjectionDeliveryState.PENDING.value,
            event.created_at_utc.isoformat(),
        ),
    )
    return cursor.rowcount == 1


class ProjectionOutbox:
    """Operational view over the durable projection delivery queue."""

    def __init__(self, database_path: Path | str) -> None:
        self.database_path = Path(database_path)

    def initialise(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.database_path, timeout=30) as connection:
            connection.execute("PRAGMA foreign_keys = ON")
            ensure_projection_outbox_schema(connection)

    def events(
        self,
        *,
        projection_name: str | None = None,
        states: Iterable[ProjectionDeliveryState | str] | None = None,
        limit: int = 100,
    ) -> tuple[CanonicalDatasetCommitted, ...]:
        if limit <= 0:
            raise ValueError("limit must be positive")
        where: list[str] = []
        params: list[object] = []
        if projection_name:
            where.append("projection_name = ?")
            params.append(str(projection_name).strip().upper())
        resolved_states = tuple(
            state.value if isinstance(state, ProjectionDeliveryState) else str(state)
            for state in (states or ())
        )
        if resolved_states:
            where.append("delivery_state IN (" + ",".join("?" for _ in resolved_states) + ")")
            params.extend(resolved_states)
        sql = "SELECT payload_json FROM projection_outbox"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY created_at_utc, event_id LIMIT ?"
        params.append(int(limit))
        uri = self.database_path.resolve().as_uri() + "?mode=ro"
        with sqlite3.connect(uri, uri=True) as connection:
            rows = connection.execute(sql, tuple(params)).fetchall()
        return tuple(CanonicalDatasetCommitted.from_dict(json.loads(row[0])) for row in rows)

    def requeue_stale_processing(self, *, older_than_seconds: int = 900) -> int:
        """Recover deliveries abandoned by an interrupted projector process."""

        threshold = int(older_than_seconds)
        if threshold < 1:
            raise ValueError("older_than_seconds must be positive")
        cutoff = (
            datetime.now(timezone.utc) - timedelta(seconds=threshold)
        ).isoformat()
        now = datetime.now(timezone.utc).isoformat()
        with sqlite3.connect(self.database_path, timeout=30) as connection:
            cursor = connection.execute(
                """
                UPDATE projection_outbox
                SET delivery_state=?, completed_at_utc=?,
                    last_error='INTERRUPTED_DELIVERY_REQUEUED'
                WHERE delivery_state=?
                  AND (started_at_utc IS NULL OR started_at_utc < ?)
                """,
                (
                    ProjectionDeliveryState.FAILED_RETRYABLE.value,
                    now,
                    ProjectionDeliveryState.PROCESSING.value,
                    cutoff,
                ),
            )
            return int(cursor.rowcount)

    def health_summary(self) -> dict[str, object]:
        """Return operational counts without exposing market-data payloads."""

        uri = self.database_path.resolve().as_uri() + "?mode=ro"
        with sqlite3.connect(uri, uri=True) as connection:
            present = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' "
                "AND name='projection_outbox'"
            ).fetchone()
            if not present:
                return {
                    "schema_version": PROJECTION_OUTBOX_SCHEMA_VERSION,
                    "schema_state": "NOT_INSTALLED",
                    "counts": {state.value: 0 for state in ProjectionDeliveryState},
                    "oldest_created_at_utc": {
                        state.value: None for state in ProjectionDeliveryState
                    },
                    "retryable_failures": [],
                    "execution_authority": "NONE",
                    "capital_authority": "NONE",
                }
            rows = connection.execute(
                "SELECT delivery_state,COUNT(*),MIN(created_at_utc) "
                "FROM projection_outbox GROUP BY delivery_state"
            ).fetchall()
            failures = connection.execute(
                "SELECT event_id,projection_name,dataset_id,attempt_count,last_error "
                "FROM projection_outbox WHERE delivery_state=? "
                "ORDER BY completed_at_utc DESC,event_id LIMIT 20",
                (ProjectionDeliveryState.FAILED_RETRYABLE.value,),
            ).fetchall()
        counts = {state.value: 0 for state in ProjectionDeliveryState}
        oldest: dict[str, str | None] = {state.value: None for state in ProjectionDeliveryState}
        for state, count, created_at in rows:
            counts[str(state)] = int(count)
            oldest[str(state)] = str(created_at) if created_at else None
        return {
            "schema_version": PROJECTION_OUTBOX_SCHEMA_VERSION,
            "schema_state": "READY",
            "counts": counts,
            "oldest_created_at_utc": oldest,
            "retryable_failures": [
                {
                    "event_id": str(event_id),
                    "projection_name": str(projection_name),
                    "dataset_id": str(dataset_id),
                    "attempt_count": int(attempt_count),
                    "last_error": str(last_error),
                }
                for event_id, projection_name, dataset_id, attempt_count, last_error
                in failures
            ],
            "execution_authority": "NONE",
            "capital_authority": "NONE",
        }

    def _transition(
        self,
        event_id: str,
        *,
        state: ProjectionDeliveryState,
        error: str = "",
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with sqlite3.connect(self.database_path, timeout=30) as connection:
            if state is ProjectionDeliveryState.PROCESSING:
                cursor = connection.execute(
                    """
                    UPDATE projection_outbox
                    SET delivery_state=?, attempt_count=attempt_count+1,
                        started_at_utc=?, completed_at_utc=NULL, last_error=''
                    WHERE event_id=? AND delivery_state IN (?, ?)
                    """,
                    (
                        state.value, now, event_id,
                        ProjectionDeliveryState.PENDING.value,
                        ProjectionDeliveryState.FAILED_RETRYABLE.value,
                    ),
                )
            else:
                cursor = connection.execute(
                    """
                    UPDATE projection_outbox
                    SET delivery_state=?, completed_at_utc=?, last_error=?
                    WHERE event_id=? AND delivery_state=?
                    """,
                    (
                        state.value, now, str(error), event_id,
                        ProjectionDeliveryState.PROCESSING.value,
                    ),
                )
            if cursor.rowcount != 1:
                raise ValueError(f"invalid projection transition for {event_id} -> {state.value}")

    def mark_processing(self, event_id: str) -> None:
        self._transition(event_id, state=ProjectionDeliveryState.PROCESSING)

    def mark_completed(self, event_id: str) -> None:
        self._transition(event_id, state=ProjectionDeliveryState.COMPLETED)

    def mark_failed(self, event_id: str, error: str) -> None:
        if not str(error).strip():
            raise ValueError("projection failure requires an error")
        self._transition(
            event_id, state=ProjectionDeliveryState.FAILED_RETRYABLE, error=error
        )


__all__ = [
    "PROJECTION_OUTBOX_SCHEMA_VERSION",
    "ProjectionDeliveryState",
    "ProjectionOutbox",
    "enqueue_projection_event",
    "ensure_projection_outbox_schema",
]
