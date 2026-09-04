"""CDS-4 canonical EOD option-chain persistence and provider orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
import hashlib
import logging
import os
from pathlib import Path
from typing import Any, Callable, Iterable
from uuid import uuid4

import pandas as pd

from .contracts import (
    CompletenessStatus,
    DataScope,
    DatasetRecord,
    DatasetRequest,
    DatasetType,
    ResolutionKind,
)
from .feature_flags import CanonicalFeatureFlags
from .gateway import CanonicalDataGateway
from .lifecycle import LifecycleManager
from .registry import CanonicalRegistry
from .request_ledger import RequestLedger, RequestResolution
from .session_clock import session_bounds


CHAIN_SCHEMA_VERSION = "option_chain_v1"
CHAIN_ADJUSTMENT = "RAW_OPTION_CONTRACT"
MIN_SESSION_TIMESTAMP_COVERAGE = 0.80

log = logging.getLogger("canonical_option_chain")


@dataclass(frozen=True, slots=True)
class OptionChainResult:
    frame: pd.DataFrame
    resolution: str
    provider: str
    dataset_id: str | None


def resolve_completed_session_date(values: Iterable[Any]) -> date:
    """Resolve one governed completed-session date from upstream bar metadata."""
    resolved: set[date] = set()
    for value in values:
        if value is None or str(value).strip().lower() in {"", "nan", "none", "null"}:
            continue
        try:
            parsed = pd.Timestamp(value)
        except (TypeError, ValueError):
            continue
        if not pd.isna(parsed):
            resolved.add(parsed.date())
    if not resolved:
        raise ValueError("completed option session unavailable: bar_data_asof/data_as_of missing")
    if len(resolved) != 1:
        raise ValueError(
            "completed option session is ambiguous: "
            + ",".join(sorted(value.isoformat() for value in resolved))
        )
    return next(iter(resolved))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


class CanonicalOptionChainService:
    """Resolve one governed chain per ticker/session and write through on miss."""

    def __init__(
        self,
        *,
        registry_path: Path,
        payload_root: Path,
        run_id: str,
        session_date: date,
        dte_max: int,
        min_open_interest: int,
        invocation_id: str | None = None,
        evidence_cutoff_utc: datetime | None = None,
        exchange_calendar: str = "XNYS",
        flags: CanonicalFeatureFlags | None = None,
    ) -> None:
        self.registry = CanonicalRegistry(registry_path)
        self.registry.initialise()
        self.lifecycle = LifecycleManager(self.registry)
        self.ledger = RequestLedger(self.registry)
        self.flags = flags or CanonicalFeatureFlags.from_environment()
        self.gateway = CanonicalDataGateway(
            self.registry, self.lifecycle, self.ledger, flags=self.flags
        )
        self.payload_root = Path(payload_root)
        self.run_id = run_id
        self.invocation_id = invocation_id or run_id
        self.evidence_cutoff_utc = evidence_cutoff_utc or session_bounds(session_date)[1]
        self.exchange_calendar = exchange_calendar
        self.session_date = session_date
        self.scope = DataScope(
            start_date=session_date,
            end_date=session_date,
            dte_min=1,
            dte_max=int(dte_max),
            sides=("CALL", "PUT"),
            extra=(("min_open_interest", str(int(min_open_interest))), ("mode", "CACHED")),
        )

    def _request(self, ticker: str) -> DatasetRequest:
        return DatasetRequest(
            run_id=self.run_id,
            requesting_stage="OPTIONS",
            dataset_type=DatasetType.OPTION_CHAIN,
            instrument_id=ticker,
            session_date=self.session_date,
            scope=self.scope,
            accepted_providers=("MARKETDATA",),
            adjustment_convention=CHAIN_ADJUSTMENT,
            schema_version=CHAIN_SCHEMA_VERSION,
            invocation_id=self.invocation_id,
            evidence_cutoff_utc=self.evidence_cutoff_utc,
            exchange_calendar=self.exchange_calendar,
            evidence_state="COMPLETED_SESSION",
        )

    def _quote_as_of(self, frame: pd.DataFrame) -> datetime:
        """Validate payload timestamps and return the governed quote as-of time."""
        if "quote_timestamp_utc" not in frame.columns:
            raise ValueError("canonical option-chain payload has no quote_timestamp_utc")
        timestamps = pd.to_datetime(frame["quote_timestamp_utc"], errors="coerce", utc=True).dropna()
        if timestamps.empty:
            raise ValueError("canonical option-chain payload has no valid quote timestamps")
        timestamp_coverage = float(len(timestamps) / len(frame)) if len(frame) else 0.0
        if timestamp_coverage < MIN_SESSION_TIMESTAMP_COVERAGE:
            raise ValueError(
                "canonical option-chain quote timestamp coverage is insufficient: "
                f"coverage={timestamp_coverage:.1%} required={MIN_SESSION_TIMESTAMP_COVERAGE:.1%}"
            )
        session_coverage = float((timestamps.dt.date == self.session_date).mean())
        if session_coverage < MIN_SESSION_TIMESTAMP_COVERAGE:
            raise ValueError(
                "canonical option-chain quote/session mismatch: "
                f"expected={self.session_date.isoformat()} coverage={session_coverage:.1%} "
                f"latest={timestamps.max().date().isoformat()}"
            )
        return timestamps.max().to_pydatetime()

    def _read(self, record: DatasetRecord) -> pd.DataFrame:
        path = Path(record.storage_uri)
        if not path.exists() or _sha256(path) != record.content_hash:
            raise ValueError(f"canonical option-chain payload failed integrity: {path}")
        frame = pd.read_parquet(path)
        if frame.empty:
            raise ValueError(f"canonical option-chain payload is empty: {path}")
        self._quote_as_of(frame)
        return frame

    def _persist(
        self,
        ticker: str,
        frame: pd.DataFrame,
        *,
        provider: str,
    ) -> DatasetRecord:
        target_dir = self.payload_root / self.session_date.isoformat() / ticker.upper()
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / f"{self.scope.fingerprint}.parquet"
        temporary = target.with_suffix(f".tmp-{uuid4().hex}.parquet")
        frame.to_parquet(temporary, index=False)
        content_hash = _sha256(temporary)
        os.replace(temporary, target)
        observed_at = datetime.now(timezone.utc)
        quote_as_of = self._quote_as_of(frame)
        dataset_id = hashlib.sha256(
            (
                f"{DatasetType.OPTION_CHAIN.value}|{ticker.upper()}|"
                f"{self.session_date.isoformat()}|{self.scope.fingerprint}|{content_hash}"
            ).encode("utf-8")
        ).hexdigest()
        record = DatasetRecord(
            dataset_id=dataset_id,
            dataset_type=DatasetType.OPTION_CHAIN,
            instrument_id=ticker,
            session_date=self.session_date,
            scope=self.scope,
            provider=provider,
            content_hash=content_hash,
            completeness_status=CompletenessStatus.COMPLETE,
            storage_uri=str(target.resolve()),
            observed_at=observed_at,
            as_of=quote_as_of,
            adjustment_convention=CHAIN_ADJUSTMENT,
            schema_version=CHAIN_SCHEMA_VERSION,
            source_run_id=self.run_id,
        )
        self.registry.register_dataset(record)
        return record

    def get(
        self,
        ticker: str,
        *,
        marketdata_fetch: Callable[[str], pd.DataFrame],
    ) -> OptionChainResult:
        request = self._request(ticker)
        resolution = self.gateway.resolve(request)
        if resolution.kind in {ResolutionKind.EXACT_HIT, ResolutionKind.SUPERSET_HIT}:
            record = resolution.records[0]
            try:
                return OptionChainResult(
                    self._read(record), resolution.kind.value, record.provider, record.dataset_id
                )
            except ValueError as error:
                # Legacy CDS-4 records used the run date and fetch time.  Reject
                # any cache hit whose payload does not prove the requested
                # completed market session, then refresh from MarketData.
                log.warning("Ignoring invalid option-chain cache hit for %s: %s", ticker, error)

        # A controlled replay must be deterministic and must never turn a
        # missing/invalid cache entry into an external provider request.  The
        # gateway has already recorded the cache resolution above, so return an
        # explicit empty result and let Options Intelligence fail closed for the
        # affected ticker.
        if self.flags.offline_replay:
            log.warning(
                "Offline option-chain replay has no valid canonical payload for %s/%s",
                ticker,
                self.session_date.isoformat(),
            )
            return OptionChainResult(
                pd.DataFrame(), "OFFLINE_CACHE_MISS", "CANONICAL", None
            )

        provider = "MARKETDATA"
        ledger_id = self.ledger.start(request, provider=provider)
        try:
            frame = marketdata_fetch(ticker)
            if not frame.empty:
                record = self._persist(ticker, frame, provider=provider)
                self.ledger.finish(
                    ledger_id,
                    RequestResolution.PROVIDER_FETCH,
                    dataset_id=record.dataset_id,
                    physical_request_count=1,
                    reason="MARKETDATA_PRIMARY",
                )
                return OptionChainResult(frame, "PROVIDER_FETCH", provider, record.dataset_id)

            self.ledger.finish(
                ledger_id,
                RequestResolution.PROVIDER_ERROR,
                physical_request_count=1,
                reason="MARKETDATA_PRIMARY_EMPTY",
            )
            return OptionChainResult(frame, "PROVIDER_EMPTY", provider, None)
        except Exception as error:
            self.ledger.finish(
                ledger_id,
                RequestResolution.PROVIDER_ERROR,
                physical_request_count=1,
                reason=f"{type(error).__name__}:{error}",
            )
            raise
