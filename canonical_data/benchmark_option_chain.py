"""Canonical reference-chain store for market-wide completed-session measures."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
from typing import Any, Callable, Mapping

import pandas as pd

from domain.data_projection import PHANTOM_OPTION_CHAIN_PROJECTION

from .contracts import (
    CompletenessStatus,
    DataScope,
    DatasetRecord,
    DatasetRequest,
    DatasetType,
    ResolutionKind,
    iso_utc,
    utc_now,
)
from .marketdata_response import parse_marketdata_option_response
from .registry import CanonicalRegistry
from .request_ledger import RequestLedger, RequestResolution
from .session_clock import session_bounds
from .storage import AtomicPayloadStore


BENCHMARK_CHAIN_SCHEMA_VERSION = "benchmark_option_chain_v1"
MARKET_REFERENCE_GEX, OPEN_RECORD_MARK = "MARKET_REFERENCE_GEX", "OPEN_RECORD_MARK"
_PURPOSE_STAGE = {MARKET_REFERENCE_GEX: ("MACRO_GEX", "macro-gex", "COMPLETED_GEX_REFERENCE"),
                  OPEN_RECORD_MARK: ("OPEN_RECORD_CAPTURE", "open-record-mark", "OPEN_RECORD_MARK_REFERENCE")}


@dataclass(frozen=True, slots=True)
class BenchmarkChainResult:
    rows: tuple[dict[str, Any], ...]
    dataset_id: str
    resolution: str


class CanonicalBenchmarkOptionChainStore:
    """Resolve completed-session reference chains outside candidate lifecycle authority.

    ``purpose``: MARKET_REFERENCE_GEX (SPY/QQQ for GEX) or OPEN_RECORD_MARK (daily marks for open tickets, P0-4).
    Both are data only: they never create or change a candidate.
    """

    def __init__(
        self,
        *,
        registry_path: Path | str,
        payload_root: Path | str,
        run_id: str,
        purpose: str = MARKET_REFERENCE_GEX,
    ) -> None:
        if purpose not in _PURPOSE_STAGE:
            raise ValueError(f"unknown reference-chain purpose: {purpose}")
        self.purpose = purpose
        self.registry = CanonicalRegistry(registry_path)
        self.registry.initialise()
        self.ledger = RequestLedger(self.registry)
        self.storage = AtomicPayloadStore(payload_root)
        self.run_id = run_id

    @staticmethod
    def _safe(value: Any) -> Any:
        if isinstance(value, Mapping):
            return {str(key): CanonicalBenchmarkOptionChainStore._safe(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [CanonicalBenchmarkOptionChainStore._safe(item) for item in value]
        if isinstance(value, (datetime, date)):
            return value.isoformat()
        if pd.isna(value):
            return None
        if hasattr(value, "item"):
            return value.item()
        return value

    def _request(self, ticker: str, session_date: date, dte_max: int) -> DatasetRequest:
        return DatasetRequest(
            run_id=self.run_id,
            requesting_stage=_PURPOSE_STAGE[self.purpose][0],
            dataset_type=DatasetType.OPTION_CHAIN,
            instrument_id=ticker,
            session_date=session_date,
            scope=DataScope(
                start_date=session_date,
                end_date=session_date,
                dte_min=1,
                dte_max=dte_max,
                sides=("CALL", "PUT"),
                extra=(("purpose", self.purpose), ("min_open_interest", "0")),
            ),
            accepted_providers=("MARKETDATA",),
            adjustment_convention="RAW_OPTION_CONTRACT",
            schema_version=BENCHMARK_CHAIN_SCHEMA_VERSION,
            invocation_id=f"{self.run_id}:{_PURPOSE_STAGE[self.purpose][1]}",
            evidence_cutoff_utc=session_bounds(session_date)[1],
            exchange_calendar="XNYS",
            evidence_state="COMPLETED_SESSION",
        )

    def _ensure_run_reference(self, session_date: date) -> None:
        """Create only a missing reference run; never overwrite pipeline metadata."""

        with self.registry.connection() as connection:
            existing = connection.execute(
                "SELECT session_date FROM run_registry WHERE run_id=?",
                (self.run_id,),
            ).fetchone()
            if existing is not None:
                if str(existing[0]) != session_date.isoformat():
                    raise ValueError(
                        "benchmark acquisition session conflicts with registered run"
                    )
                return
            connection.execute(
                """
                INSERT INTO run_registry(
                    run_id, run_type, session_date, started_at, metadata_json
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    self.run_id,
                    _PURPOSE_STAGE[self.purpose][2],
                    session_date.isoformat(),
                    iso_utc(utc_now()),
                    json.dumps({"authority": "DATA_REFERENCE_ONLY"}, sort_keys=True),
                ),
            )

    @staticmethod
    def _validate(rows: list[dict[str, Any]], session_date: date) -> datetime:
        if not rows:
            raise ValueError("completed benchmark option chain is empty")
        frame = pd.DataFrame(rows)
        timestamps = pd.to_datetime(
            frame.get("quote_timestamp_utc"), errors="coerce", utc=True
        ).dropna()
        if len(timestamps) / len(frame) < 0.80:
            raise ValueError("benchmark chain timestamp coverage is below 80%")
        if float((timestamps.dt.date == session_date).mean()) < 0.80:
            raise ValueError("benchmark chain does not represent the required session")
        _, close_utc = session_bounds(session_date)
        late_cutoff = close_utc - timedelta(minutes=30)
        if float((timestamps >= late_cutoff).mean()) < 0.80:
            raise ValueError("benchmark chain lacks completed-session late quotes")
        sides = set(frame.get("right", pd.Series(dtype=str)).astype(str).str.upper())
        if not {"C", "P"} <= sides:
            raise ValueError("benchmark chain must contain calls and puts")
        return timestamps.max().to_pydatetime()

    @staticmethod
    def _read(record: DatasetRecord) -> list[dict[str, Any]]:
        path = Path(record.storage_uri)
        payload = path.read_bytes()
        if hashlib.sha256(payload).hexdigest() != record.content_hash:
            raise ValueError("canonical benchmark chain failed hash verification")
        value = json.loads(payload)
        if not isinstance(value, list):
            raise ValueError("canonical benchmark chain payload is not a row list")
        return [dict(row) for row in value]

    def get(
        self,
        *,
        ticker: str,
        session_date: date,
        dte_max: int,
        fetch: Callable[[str], Mapping[str, Any]],
    ) -> BenchmarkChainResult:
        self._ensure_run_reference(session_date)
        request = self._request(ticker.strip().upper(), session_date, dte_max)
        request_id = self.ledger.start(request)
        resolution = self.registry.resolve(request)
        if resolution.kind in {ResolutionKind.EXACT_HIT, ResolutionKind.SUPERSET_HIT}:
            record = resolution.records[0]
            try:
                rows = self._read(record)
                self._validate(rows, session_date)
                self.ledger.finish(
                    request_id,
                    RequestResolution.CACHE_HIT if resolution.kind is ResolutionKind.EXACT_HIT else RequestResolution.SUPERSET_HIT,
                    dataset_id=record.dataset_id,
                )
                return BenchmarkChainResult(tuple(rows), record.dataset_id, resolution.kind.value)
            except ValueError:
                pass
        try:
            raw = fetch(ticker.strip().upper())
            frame = parse_marketdata_option_response(
                raw, ticker=ticker, quote_source="MARKETDATA"
            )
            rows = frame.to_dict("records")
            as_of = self._validate(rows, session_date)
            safe = self._safe(rows)
            encoded = json.dumps(
                safe, sort_keys=True, separators=(",", ":"), allow_nan=False
            ).encode("utf-8")
            content_hash = hashlib.sha256(encoded).hexdigest()
            stored = self.storage.write_bytes(
                Path("option_chain") / session_date.isoformat() /
                ticker.strip().upper() / f"{content_hash}.json",
                encoded,
            )
            dataset_id = hashlib.sha256(
                f"{DatasetType.OPTION_CHAIN.value}|{ticker.strip().upper()}|{session_date}|{request.scope.fingerprint}|{content_hash}".encode()
            ).hexdigest()
            record = DatasetRecord(
                dataset_id=dataset_id,
                dataset_type=DatasetType.OPTION_CHAIN,
                instrument_id=ticker,
                session_date=session_date,
                scope=request.scope,
                provider="MARKETDATA",
                content_hash=content_hash,
                completeness_status=CompletenessStatus.COMPLETE,
                storage_uri=str(stored.path),
                observed_at=datetime.now(timezone.utc),
                as_of=as_of,
                adjustment_convention=request.adjustment_convention,
                schema_version=BENCHMARK_CHAIN_SCHEMA_VERSION,
                quality_flags=(self.purpose,),
                source_run_id=self.run_id,
            )
            self.registry.register_dataset(
                record,
                projection_names=(PHANTOM_OPTION_CHAIN_PROJECTION,),
            )
            self.ledger.finish(
                request_id,
                RequestResolution.PROVIDER_FETCH,
                dataset_id=dataset_id,
                physical_request_count=1,
            )
            return BenchmarkChainResult(tuple(safe), dataset_id, "PROVIDER_FETCH")
        except Exception as error:
            self.ledger.finish(
                request_id,
                RequestResolution.PROVIDER_ERROR,
                physical_request_count=1,
                reason=f"{type(error).__name__}: {error}",
            )
            raise


__all__ = [
    "BENCHMARK_CHAIN_SCHEMA_VERSION",
    "MARKET_REFERENCE_GEX",
    "OPEN_RECORD_MARK",
    "BenchmarkChainResult",
    "CanonicalBenchmarkOptionChainStore",
]
