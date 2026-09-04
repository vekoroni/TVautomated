"""Logical and physical request accounting for CDS observability."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
import sqlite3
from uuid import uuid4

from .contracts import DatasetRequest, DatasetType, iso_utc, parse_utc, utc_now
from .registry import CanonicalRegistry


class RequestResolution(str, Enum):
    PENDING = "PENDING"
    CACHE_HIT = "CACHE_HIT"
    SUPERSET_HIT = "SUPERSET_HIT"
    PARTIAL_HIT = "PARTIAL_HIT"
    CACHE_MISS = "CACHE_MISS"
    PARTIAL_FETCH = "PARTIAL_FETCH"
    PROVIDER_FETCH = "PROVIDER_FETCH"
    BLOCKED_NOT_AUTHORISED = "BLOCKED_NOT_AUTHORISED"
    PROVIDER_ERROR = "PROVIDER_ERROR"


class RequestLedger:
    def __init__(self, registry: CanonicalRegistry):
        self.registry = registry

    def start(
        self,
        request: DatasetRequest,
        *,
        provider: str | None = None,
        request_id: str | None = None,
    ) -> str:
        identifier = request_id or str(uuid4())
        with self.registry.connection() as connection:
            connection.execute(
                """
                INSERT INTO api_request_ledger(
                    request_id, run_id, stage, ticker, dataset_type,
                    scope_fingerprint, provider, resolution, started_at,
                    invocation_id, evidence_cutoff_utc, exchange_calendar,
                    evidence_state, request_fingerprint
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    identifier,
                    request.run_id,
                    request.requesting_stage,
                    request.instrument_id,
                    request.dataset_type.value,
                    request.scope.fingerprint,
                    provider.upper() if provider else None,
                    RequestResolution.PENDING.value,
                    iso_utc(utc_now()),
                    request.invocation_id,
                    iso_utc(request.evidence_cutoff_utc),
                    request.exchange_calendar,
                    request.evidence_state,
                    request.request_fingerprint,
                ),
            )
        return identifier

    def finish(
        self,
        request_id: str,
        resolution: RequestResolution,
        *,
        dataset_id: str | None = None,
        physical_request_count: int = 0,
        retry_count: int = 0,
        reason: str = "",
        completed_at: datetime | None = None,
    ) -> None:
        if physical_request_count < 0 or retry_count < 0:
            raise ValueError("request and retry counts cannot be negative")
        with self.registry.connection() as connection:
            cursor = connection.execute(
                """
                UPDATE api_request_ledger SET
                    resolution = ?, dataset_id = ?, physical_request_count = ?,
                    retry_count = ?, reason = ?, completed_at = ?
                WHERE request_id = ?
                """,
                (
                    resolution.value,
                    dataset_id,
                    physical_request_count,
                    retry_count,
                    reason,
                    iso_utc(completed_at or utc_now()),
                    request_id,
                ),
            )
            if cursor.rowcount != 1:
                raise KeyError(f"unknown request_id {request_id}")

    def record_blocked(self, request: DatasetRequest, reason: str) -> str:
        request_id = self.start(request)
        self.finish(
            request_id,
            RequestResolution.BLOCKED_NOT_AUTHORISED,
            physical_request_count=0,
            reason=reason,
        )
        return request_id

    def entries(self, run_id: str) -> tuple[dict[str, object], ...]:
        with self.registry.connection() as connection:
            rows = connection.execute(
                "SELECT * FROM api_request_ledger WHERE run_id = ? ORDER BY started_at",
                (run_id,),
            ).fetchall()
        return tuple(dict(row) for row in rows)

    def physical_request_count(self, run_id: str) -> int:
        with self.registry.connection() as connection:
            value = connection.execute(
                """
                SELECT COALESCE(SUM(physical_request_count), 0)
                FROM api_request_ledger WHERE run_id = ?
                """,
                (run_id,),
            ).fetchone()[0]
        return int(value)
