"""SQLite control-plane registry for canonical datasets and run metadata."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import replace
from datetime import date, datetime
import json
from pathlib import Path
import sqlite3
from typing import Iterator

from .contracts import (
    CompletenessStatus,
    DataScope,
    DatasetRecord,
    DatasetRequest,
    DatasetResolution,
    DatasetType,
    ResolutionKind,
    iso_utc,
    parse_utc,
    utc_now,
)
from .errors import DatasetValidationError
from domain.market_evidence import EvidenceCandidate, decide_evidence_reuse


SCHEMA_VERSION = "cds_control_plane_v2"
LEDGER_V2_COLUMNS = {
    "invocation_id": "TEXT NOT NULL DEFAULT ''",
    "evidence_cutoff_utc": "TEXT",
    "exchange_calendar": "TEXT NOT NULL DEFAULT 'XNYS'",
    "evidence_state": "TEXT NOT NULL DEFAULT 'COMPLETED_SESSION'",
    "request_fingerprint": "TEXT NOT NULL DEFAULT ''",
}
REQUIRED_TABLES = frozenset(
    {
        "schema_metadata",
        "run_registry",
        "ticker_lifecycle",
        "stage_worklist",
        "dataset_registry",
        "api_request_ledger",
        "schema_migration_log",
    }
)


class CanonicalRegistry:
    """Metadata registry. Large payloads remain in the atomic payload store."""

    def __init__(self, database_path: str | Path):
        self.database_path = Path(database_path)

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database_path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 30000")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _pending_ledger_migration(self) -> tuple[str, ...]:
        """Inspect an existing database without changing it."""
        if not self.database_path.is_file() or self.database_path.stat().st_size == 0:
            return ()
        uri = f"file:{self.database_path.as_posix()}?mode=ro"
        connection = sqlite3.connect(uri, uri=True)
        try:
            exists = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' "
                "AND name='api_request_ledger'"
            ).fetchone()
            if not exists:
                return ()
            columns = {
                row[1]
                for row in connection.execute("PRAGMA table_info(api_request_ledger)")
            }
            return tuple(sorted(set(LEDGER_V2_COLUMNS) - columns))
        finally:
            connection.close()

    def migration_status(self) -> dict[str, object]:
        pending_columns = self._pending_ledger_migration()
        if not self.database_path.is_file() or self.database_path.stat().st_size == 0:
            return {
                "required": False,
                "pending_columns": pending_columns,
                "installed_versions": (),
                "legacy_rows_pending_backfill": 0,
            }
        uri = f"file:{self.database_path.as_posix()}?mode=ro"
        connection = sqlite3.connect(uri, uri=True)
        try:
            tables = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
            versions = tuple(
                row[0]
                for row in connection.execute(
                    "SELECT schema_version FROM schema_metadata"
                )
            ) if "schema_metadata" in tables else ()
            columns = {
                row[1]
                for row in connection.execute("PRAGMA table_info(api_request_ledger)")
            } if "api_request_ledger" in tables else set()
            backfill = 0
            if set(LEDGER_V2_COLUMNS) <= columns:
                backfill = int(connection.execute(
                    "SELECT COUNT(*) FROM api_request_ledger "
                    "WHERE invocation_id = '' OR request_fingerprint = ''"
                ).fetchone()[0])
        finally:
            connection.close()
        existing_control_plane = "api_request_ledger" in tables
        required = bool(
            existing_control_plane
            and (pending_columns or SCHEMA_VERSION not in versions or backfill)
        )
        return {
            "required": required,
            "pending_columns": pending_columns,
            "installed_versions": versions,
            "legacy_rows_pending_backfill": backfill,
        }

    def initialise(self, *, allow_migration: bool = False) -> None:
        migration_before = self.migration_status()
        if migration_before["required"] and not allow_migration:
            raise RuntimeError(
                "control-plane schema migration required before pipeline startup: "
                + json.dumps(migration_before, sort_keys=True)
            )
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as connection:
            # Schema backfills must not depend on a writable operating-system
            # temp directory.  This also makes the explicit migrator reliable
            # in restricted service accounts and sandboxed deployments.
            connection.execute("PRAGMA temp_store = MEMORY")
            connection.execute("PRAGMA journal_mode = WAL")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS schema_metadata (
                    schema_version TEXT PRIMARY KEY,
                    installed_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS run_registry (
                    run_id TEXT PRIMARY KEY,
                    run_type TEXT NOT NULL,
                    session_date TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}'
                );

                CREATE TABLE IF NOT EXISTS ticker_lifecycle (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    ticker TEXT NOT NULL,
                    state TEXT NOT NULL,
                    drop_class TEXT NOT NULL,
                    stage TEXT NOT NULL,
                    reason_code TEXT NOT NULL DEFAULT '',
                    allowed_capabilities_json TEXT NOT NULL DEFAULT '[]',
                    version INTEGER NOT NULL,
                    recorded_at TEXT NOT NULL,
                    FOREIGN KEY(run_id) REFERENCES run_registry(run_id),
                    UNIQUE(run_id, ticker, version)
                );

                CREATE INDEX IF NOT EXISTS idx_lifecycle_latest
                    ON ticker_lifecycle(run_id, ticker, version DESC);

                CREATE TABLE IF NOT EXISTS stage_worklist (
                    run_id TEXT NOT NULL,
                    stage TEXT NOT NULL,
                    ticker TEXT NOT NULL,
                    dataset_type TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY(run_id, stage, ticker, dataset_type),
                    FOREIGN KEY(run_id) REFERENCES run_registry(run_id)
                );

                CREATE TABLE IF NOT EXISTS dataset_registry (
                    dataset_id TEXT PRIMARY KEY,
                    dataset_type TEXT NOT NULL,
                    instrument_id TEXT NOT NULL,
                    session_date TEXT NOT NULL,
                    scope_fingerprint TEXT NOT NULL,
                    scope_json TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    adjustment_convention TEXT NOT NULL,
                    schema_version TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    completeness_status TEXT NOT NULL,
                    storage_uri TEXT NOT NULL,
                    observed_at TEXT NOT NULL,
                    as_of TEXT NOT NULL,
                    expires_at TEXT,
                    quality_flags_json TEXT NOT NULL DEFAULT '[]',
                    parent_dataset_ids_json TEXT NOT NULL DEFAULT '[]',
                    source_run_id TEXT,
                    registered_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_dataset_lookup
                    ON dataset_registry(
                        dataset_type, instrument_id, session_date,
                        adjustment_convention, schema_version
                    );

                CREATE TABLE IF NOT EXISTS api_request_ledger (
                    request_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    stage TEXT NOT NULL,
                    ticker TEXT NOT NULL,
                    dataset_type TEXT NOT NULL,
                    scope_fingerprint TEXT NOT NULL,
                    provider TEXT,
                    resolution TEXT NOT NULL,
                    dataset_id TEXT,
                    physical_request_count INTEGER NOT NULL DEFAULT 0,
                    retry_count INTEGER NOT NULL DEFAULT 0,
                    reason TEXT NOT NULL DEFAULT '',
                    started_at TEXT NOT NULL,
                    completed_at TEXT,
                    invocation_id TEXT NOT NULL DEFAULT '',
                    evidence_cutoff_utc TEXT,
                    exchange_calendar TEXT NOT NULL DEFAULT 'XNYS',
                    evidence_state TEXT NOT NULL DEFAULT 'COMPLETED_SESSION',
                    request_fingerprint TEXT NOT NULL DEFAULT '',
                    FOREIGN KEY(run_id) REFERENCES run_registry(run_id),
                    FOREIGN KEY(dataset_id) REFERENCES dataset_registry(dataset_id)
                );

                CREATE TABLE IF NOT EXISTS schema_migration_log (
                    migration_id TEXT PRIMARY KEY,
                    from_version TEXT NOT NULL,
                    to_version TEXT NOT NULL,
                    applied_at TEXT NOT NULL,
                    detail_json TEXT NOT NULL DEFAULT '{}'
                );

                CREATE INDEX IF NOT EXISTS idx_request_ledger_run
                    ON api_request_ledger(run_id, stage, ticker);
                """
            )
            existing_columns = {
                row[1]
                for row in connection.execute("PRAGMA table_info(api_request_ledger)")
            }
            added_columns: list[str] = []
            for column, definition in LEDGER_V2_COLUMNS.items():
                if column not in existing_columns:
                    connection.execute(
                        f"ALTER TABLE api_request_ledger ADD COLUMN {column} {definition}"
                    )
                    added_columns.append(column)
            if migration_before["required"]:
                connection.execute(
                    "UPDATE api_request_ledger SET invocation_id = run_id "
                    "WHERE invocation_id = ''"
                )
                connection.execute(
                    "UPDATE api_request_ledger SET request_fingerprint = "
                    "'LEGACY:' || request_id WHERE request_fingerprint = ''"
                )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_request_ledger_invocation "
                "ON api_request_ledger(invocation_id, stage, ticker)"
            )
            if not migration_before["required"] or allow_migration:
                connection.execute(
                    "INSERT OR IGNORE INTO schema_metadata(schema_version, installed_at) "
                    "VALUES (?, ?)",
                    (SCHEMA_VERSION, iso_utc(utc_now())),
                )
            if migration_before["required"]:
                connection.execute(
                    "INSERT OR REPLACE INTO schema_migration_log(" 
                    "migration_id, from_version, to_version, applied_at, detail_json" 
                    ") VALUES (?, ?, ?, ?, ?)",
                    (
                        "cds_control_plane_v1_to_v2",
                        "cds_control_plane_v1",
                        SCHEMA_VERSION,
                        iso_utc(utc_now()),
                        json.dumps(
                            {
                                "added_columns": added_columns,
                                "resumed_partial_migration": not bool(added_columns),
                                "legacy_rows_backfilled": migration_before[
                                    "legacy_rows_pending_backfill"
                                ],
                            },
                            sort_keys=True,
                        ),
                    ),
                )

    def register_run(
        self,
        run_id: str,
        run_type: str,
        session_date: date,
        *,
        metadata: dict | None = None,
        started_at: datetime | None = None,
    ) -> None:
        with self.connection() as connection:
            connection.execute(
                """
                INSERT INTO run_registry(
                    run_id, run_type, session_date, started_at, metadata_json
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(run_id) DO UPDATE SET
                    run_type=excluded.run_type,
                    session_date=excluded.session_date,
                    metadata_json=excluded.metadata_json
                """,
                (
                    run_id,
                    run_type.upper(),
                    session_date.isoformat(),
                    iso_utc(started_at or utc_now()),
                    json.dumps(metadata or {}, sort_keys=True),
                ),
            )

    def validate_schema(self) -> dict[str, object]:
        """Return a non-mutating schema health report for startup checks."""
        with self.connection() as connection:
            tables = {
                row["name"]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                ).fetchall()
            }
            versions = tuple(
                row["schema_version"]
                for row in connection.execute(
                    "SELECT schema_version FROM schema_metadata ORDER BY installed_at"
                ).fetchall()
            )
            foreign_key_violations = tuple(
                tuple(row) for row in connection.execute("PRAGMA foreign_key_check")
            )
        missing = tuple(sorted(REQUIRED_TABLES - tables))
        return {
            "valid": not missing
            and SCHEMA_VERSION in versions
            and not foreign_key_violations,
            "schema_version": SCHEMA_VERSION,
            "installed_versions": versions,
            "missing_tables": missing,
            "foreign_key_violations": foreign_key_violations,
        }

    def register_dataset(self, record: DatasetRecord) -> None:
        with self.connection() as connection:
            existing_row = connection.execute(
                "SELECT * FROM dataset_registry WHERE dataset_id = ?",
                (record.dataset_id,),
            ).fetchone()
            if existing_row is not None:
                existing = self._record_from_row(existing_row)
                if existing == record:
                    return
                # Dataset IDs are content identities, while ``source_run_id``
                # records the run that first registered that immutable object.
                # A later run may legitimately observe and reuse the identical
                # dataset.  Preserve the original provenance and make that
                # repeat registration idempotent; every other field remains
                # part of the immutability comparison below.
                if replace(
                    record,
                    source_run_id=existing.source_run_id,
                    # A content-derived dataset may be observed again after its
                    # freshness window.  Keep the first-observed provenance;
                    # the later physical request is recorded in the ledger.
                    observed_at=existing.observed_at,
                ) == existing:
                    return
                raise DatasetValidationError(
                    f"dataset_id {record.dataset_id} is immutable and already registered"
                )
            connection.execute(
                """
                INSERT INTO dataset_registry(
                    dataset_id, dataset_type, instrument_id, session_date,
                    scope_fingerprint, scope_json, provider,
                    adjustment_convention, schema_version, content_hash,
                    completeness_status, storage_uri, observed_at, as_of,
                    expires_at, quality_flags_json, parent_dataset_ids_json,
                    source_run_id, registered_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.dataset_id,
                    record.dataset_type.value,
                    record.instrument_id,
                    record.session_date.isoformat(),
                    record.scope.fingerprint,
                    json.dumps(record.scope.to_dict(), sort_keys=True),
                    record.provider,
                    record.adjustment_convention,
                    record.schema_version,
                    record.content_hash,
                    record.completeness_status.value,
                    record.storage_uri,
                    iso_utc(record.observed_at),
                    iso_utc(record.as_of),
                    iso_utc(record.expires_at),
                    json.dumps(record.quality_flags),
                    json.dumps(record.parent_dataset_ids),
                    record.source_run_id,
                    iso_utc(utc_now()),
                ),
            )

    @staticmethod
    def _record_from_row(row: sqlite3.Row) -> DatasetRecord:
        return DatasetRecord(
            dataset_id=row["dataset_id"],
            dataset_type=DatasetType(row["dataset_type"]),
            instrument_id=row["instrument_id"],
            session_date=date.fromisoformat(row["session_date"]),
            scope=DataScope.from_dict(json.loads(row["scope_json"])),
            provider=row["provider"],
            adjustment_convention=row["adjustment_convention"],
            schema_version=row["schema_version"],
            content_hash=row["content_hash"],
            completeness_status=CompletenessStatus(row["completeness_status"]),
            storage_uri=row["storage_uri"],
            observed_at=parse_utc(row["observed_at"]),
            as_of=parse_utc(row["as_of"]),
            expires_at=parse_utc(row["expires_at"]),
            quality_flags=tuple(json.loads(row["quality_flags_json"])),
            parent_dataset_ids=tuple(json.loads(row["parent_dataset_ids_json"])),
            source_run_id=row["source_run_id"],
        )

    def get_dataset(self, dataset_id: str) -> DatasetRecord | None:
        with self.connection() as connection:
            row = connection.execute(
                "SELECT * FROM dataset_registry WHERE dataset_id = ?", (dataset_id,)
            ).fetchone()
        return self._record_from_row(row) if row else None

    def latest_dataset(
        self,
        dataset_type: DatasetType,
        instrument_id: str,
        *,
        adjustment_convention: str | None = None,
        schema_version: str | None = None,
        complete_only: bool = False,
    ) -> DatasetRecord | None:
        """Return the newest registered dataset across market sessions."""
        sql = """
            SELECT * FROM dataset_registry
            WHERE dataset_type = ? AND instrument_id = ?
        """
        parameters: list[object] = [dataset_type.value, instrument_id.strip().upper()]
        if adjustment_convention is not None:
            sql += " AND adjustment_convention = ?"
            parameters.append(adjustment_convention)
        if schema_version is not None:
            sql += " AND schema_version = ?"
            parameters.append(schema_version)
        if complete_only:
            sql += " AND completeness_status = ?"
            parameters.append(CompletenessStatus.COMPLETE.value)
        sql += " ORDER BY session_date DESC, as_of DESC, registered_at DESC LIMIT 1"
        with self.connection() as connection:
            row = connection.execute(sql, parameters).fetchone()
        return self._record_from_row(row) if row else None

    def list_dataset_records(
        self,
        dataset_type: DatasetType,
        *,
        instrument_id: str | None = None,
    ) -> tuple[DatasetRecord, ...]:
        sql = "SELECT * FROM dataset_registry WHERE dataset_type = ?"
        parameters: list[object] = [dataset_type.value]
        if instrument_id is not None:
            sql += " AND instrument_id = ?"
            parameters.append(instrument_id.strip().upper())
        sql += " ORDER BY instrument_id, session_date, as_of"
        with self.connection() as connection:
            rows = connection.execute(sql, parameters).fetchall()
        return tuple(self._record_from_row(row) for row in rows)

    def resolve(
        self, request: DatasetRequest, *, now: datetime | None = None
    ) -> DatasetResolution:
        sql = """
            SELECT * FROM dataset_registry
            WHERE dataset_type = ? AND instrument_id = ? AND session_date = ?
              AND adjustment_convention = ? AND schema_version = ?
              AND completeness_status IN (?, ?)
        """
        parameters: list[object] = [
            request.dataset_type.value,
            request.instrument_id,
            request.session_date.isoformat(),
            request.adjustment_convention,
            request.schema_version,
            CompletenessStatus.COMPLETE.value,
            CompletenessStatus.PARTIAL.value,
        ]
        if request.accepted_providers:
            placeholders = ",".join("?" for _ in request.accepted_providers)
            sql += f" AND provider IN ({placeholders})"
            parameters.extend(request.accepted_providers)
        sql += " ORDER BY as_of DESC"

        with self.connection() as connection:
            rows = connection.execute(sql, parameters).fetchall()
        records = tuple(
            record
            for record in map(self._record_from_row, rows)
            if record.is_fresh(request.freshness_seconds, now=now)
        )

        decision = decide_evidence_reuse(
            EvidenceCandidate(
                dataset_id=record.dataset_id,
                complete=record.completeness_status is CompletenessStatus.COMPLETE,
                exact_scope=record.scope == request.scope,
                covers_scope=record.scope.covers(request.scope),
                overlaps_scope=record.scope.overlaps(request.scope),
            )
            for record in records
        )
        by_id = {record.dataset_id: record for record in records}
        selected = tuple(by_id[dataset_id] for dataset_id in decision.dataset_ids)
        return DatasetResolution(
            ResolutionKind(decision.kind.value),
            request,
            selected,
            missing_scope=(
                request.scope if decision.requires_provider_fetch else None
            ),
            reason=decision.reason,
        )

    def dataset_count(self) -> int:
        with self.connection() as connection:
            return int(
                connection.execute("SELECT COUNT(*) FROM dataset_registry").fetchone()[0]
            )
