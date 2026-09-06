"""Build and persist immutable completed/developing Market Profile evidence."""

from __future__ import annotations

from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Iterable

import pandas as pd

from canonical_data.contracts import CompletenessStatus, DataScope, DatasetRecord, DatasetType
from canonical_data.registry import CanonicalRegistry
from canonical_data.storage import AtomicPayloadStore
from canonical_data.run_plan import evidence_identity
from domain.market_structure_evidence import (
    MarketProfileEvidence,
    PROFILE_EVIDENCE_VERSION,
    profile_levels_are_usable,
    profile_reason_code,
)
from .profile import build_market_profile, detect_double_distribution


PROFILE_ALGORITHM_VERSION = "completed_market_profile_v1"


def build_profile_evidence(
    *,
    ticker: str,
    session_date: date,
    evidence_state: str,
    bars: pd.DataFrame,
    exchange_tick: float,
    atr14: float,
    regular_open_utc: datetime,
    input_dataset_ids: Iterable[str],
    input_hashes: Iterable[str],
    completeness_status: str,
    calculated_at_utc: datetime | None = None,
) -> MarketProfileEvidence:
    profile = build_market_profile(
        bars, exchange_tick=exchange_tick, atr14=atr14,
        regular_open_utc=regular_open_utc,
    )
    structure = detect_double_distribution(profile, atr14=atr14)
    interval = profile.interval_minutes
    if interval is None and len(bars) and "interval_minutes" in bars:
        interval_values = pd.to_numeric(
            bars["interval_minutes"], errors="coerce"
        ).dropna()
        interval = int(interval_values.iloc[0]) if len(interval_values) else None
    # The contract requires a positive interval even for unusable evidence.
    # Zero is never substituted for a missing price level, but cadence can be
    # represented by the explicit UNKNOWN sentinel value of one minute only
    # when the source frame itself has no governed interval.
    interval = int(interval or 1)
    quality_penalty = {
        "ONE_MINUTE_ESTIMATED": 0.05,
        "FIVE_MINUTE_ESTIMATED": 0.10,
        "COARSE_15_MINUTE": 0.25,
        "COARSE_30_MINUTE": 0.40,
    }.get(profile.data_quality, 1.0)
    completeness = str(completeness_status or "UNAVAILABLE").upper()
    if completeness != "COMPLETE":
        quality_penalty = max(quality_penalty, 0.65)
    content = {
        "ticker": ticker.strip().upper(),
        "session_date": session_date.isoformat(),
        "evidence_state": str(evidence_state).upper(),
        "interval_minutes": interval,
        "poc": profile.poc,
        "value_area_low": profile.value_area_low,
        "value_area_high": profile.value_area_high,
        "profile_type": "DOUBLE_DISTRIBUTION" if structure.get("detected") else "SINGLE_DISTRIBUTION",
        "quality": profile.data_quality,
        "completeness_status": completeness,
        "input_dataset_ids": sorted(set(input_dataset_ids)),
        "input_hashes": sorted(set(input_hashes)),
        "algorithm_version": PROFILE_ALGORITHM_VERSION,
    }
    content_hash = hashlib.sha256(json.dumps(content, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    evidence_id = evidence_identity(
        evidence_type="MARKET_PROFILE", input_dataset_ids=content["input_dataset_ids"],
        calculation_version=PROFILE_ALGORITHM_VERSION, content_hash=content_hash,
    )
    calculated = calculated_at_utc
    if calculated is None:
        calculated = regular_open_utc
    if calculated.tzinfo is None:
        raise ValueError("calculated_at_utc must be timezone-aware")
    calculated_iso = calculated.astimezone(timezone.utc).replace(
        microsecond=0
    ).isoformat().replace("+00:00", "Z")
    reason = profile_reason_code(
        evidence_state=evidence_state,
        completeness_status=completeness,
        levels_available=profile_levels_are_usable(
            poc=profile.poc,
            value_area_low=profile.value_area_low,
            value_area_high=profile.value_area_high,
        ),
    )
    observed = pd.to_datetime(bars.get("observed_at", bars.get("timestamp_utc")), utc=True, errors="coerce").max()
    observed_at = calculated_iso if pd.isna(observed) else observed.isoformat().replace("+00:00", "Z")
    return MarketProfileEvidence(
        evidence_id=evidence_id, ticker=ticker, session_date=session_date.isoformat(),
        evidence_state=evidence_state, interval_minutes=interval,
        poc=profile.poc, value_area_low=profile.value_area_low,
        value_area_high=profile.value_area_high, profile_type=content["profile_type"],
        quality=profile.data_quality, completeness_status=completeness,
        input_dataset_ids=tuple(content["input_dataset_ids"]), input_hashes=tuple(content["input_hashes"]),
        observed_at_utc=observed_at, calculated_at_utc=calculated_iso,
        algorithm_version=PROFILE_ALGORITHM_VERSION,
        uncertainty_score=min(1.0, quality_penalty), reason_code=reason,
    )


class CanonicalProfileEvidenceStore:
    def __init__(self, *, registry_path: Path, payload_root: Path) -> None:
        self.registry = CanonicalRegistry(registry_path); self.registry.initialise()
        self.store = AtomicPayloadStore(payload_root)

    def persist(self, evidence: MarketProfileEvidence, *, source_run_id: str) -> DatasetRecord:
        payload = json.dumps(evidence.to_dict(), sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
        content_hash = hashlib.sha256(payload).hexdigest()
        session = date.fromisoformat(evidence.session_date)
        stored = self.store.write_bytes(
            Path("market_profile") / session.isoformat() / evidence.ticker / f"{content_hash}.json",
            payload,
        )
        scope = DataScope(extra=(("evidence_id", evidence.evidence_id), ("evidence_state", evidence.evidence_state),
                                 ("interval", f"{evidence.interval_minutes}min")))
        dataset_id = hashlib.sha256(f"MARKET_PROFILE|{evidence.ticker}|{session}|{content_hash}".encode()).hexdigest()
        observed = pd.Timestamp(evidence.observed_at_utc).to_pydatetime()
        calculated = pd.Timestamp(evidence.calculated_at_utc).to_pydatetime()
        record = DatasetRecord(
            dataset_id=dataset_id,
            dataset_type=DatasetType.MARKET_STRUCTURE,
            instrument_id=evidence.ticker,
            session_date=session,
            scope=scope,
            provider="DERIVED",
            content_hash=content_hash,
            completeness_status=(
                CompletenessStatus.COMPLETE
                if evidence.usable
                else CompletenessStatus.PARTIAL
            ),
            storage_uri=str(stored.path),
            observed_at=observed,
            as_of=calculated,
            adjustment_convention="SPLIT_ADJUSTED",
            schema_version=PROFILE_EVIDENCE_VERSION, quality_flags=(() if evidence.usable else (evidence.reason_code,)),
            parent_dataset_ids=evidence.input_dataset_ids, source_run_id=source_run_id,
        )
        self.registry.register_dataset(record)
        return record
