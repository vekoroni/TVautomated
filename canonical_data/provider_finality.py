"""Canonical adapter for the AVS-FIX-002 provider-finality domain.

The adapter joins immutable option-chain payloads to the canonical daily-close
store.  It performs no acquisition: missing chains and closes are named
ticker-level exceptions and are then aggregated independently at run level.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Mapping, Sequence

import pandas as pd

from domain.provider_finality import (
    DEFAULT_MINIMUM_LATE_WATERMARK_COVERAGE,
    DEFAULT_MINIMUM_SESSION_COVERAGE,
    DEFAULT_MINIMUM_TIMESTAMP_COVERAGE,
    DEFAULT_NORMAL_CHAIN_FRACTION,
    DEFAULT_OFFICIAL_CLOSE_FRACTION,
    ProviderFinalityAssessment,
    ProviderRequestMode,
    RunProviderCompletenessEvidence,
    assess_provider_session_finality,
    assess_run_provider_completeness,
    timestamp_distribution,
)

from .contracts import DatasetRecord
from .registry import CanonicalRegistry
from .session_clock import session_bounds


GOVERNED_CONSTANTS_PATH = (
    Path(__file__).resolve().parents[1] / "config" / "governed_constants_v1.json"
)


@dataclass(frozen=True, slots=True)
class ProviderFinalityPolicy:
    provider_settlement_delay: timedelta = timedelta(minutes=15)
    late_session_window: timedelta = timedelta(minutes=15)
    minimum_session_coverage: float = DEFAULT_MINIMUM_SESSION_COVERAGE
    minimum_timestamp_coverage: float = DEFAULT_MINIMUM_TIMESTAMP_COVERAGE
    minimum_late_watermark_coverage: float = DEFAULT_MINIMUM_LATE_WATERMARK_COVERAGE
    minimum_normal_chain_fraction: float = DEFAULT_NORMAL_CHAIN_FRACTION
    minimum_official_close_fraction: float = DEFAULT_OFFICIAL_CLOSE_FRACTION
    governed_constants_sha256: str = "UNCONFIGURED"


def load_provider_finality_policy(
    path: Path | str = GOVERNED_CONSTANTS_PATH,
) -> ProviderFinalityPolicy:
    """Load and validate the governed ALG-15 thresholds fail-closed."""

    source = Path(path)
    encoded = source.read_bytes()
    payload = json.loads(encoded.decode("utf-8-sig"))
    if payload.get("schema_version") != "governed_constants_v1":
        raise ValueError("unsupported governed constants schema")
    values = payload.get("provider_completeness")
    if not isinstance(values, Mapping):
        raise ValueError("governed constants omit provider_completeness")
    if values.get("threshold_version") != "provider_completeness_v1":
        raise ValueError("unsupported provider completeness threshold version")

    def fraction(name: str) -> float:
        value = float(values[name])
        if not 0.0 <= value <= 1.0:
            raise ValueError(f"provider completeness {name} must be within [0, 1]")
        return value

    settlement = int(values["provider_settlement_delay_minutes"])
    late_window = int(values["late_session_window_minutes"])
    if settlement < 0 or late_window <= 0:
        raise ValueError("provider completeness timing constants are invalid")
    return ProviderFinalityPolicy(
        provider_settlement_delay=timedelta(minutes=settlement),
        late_session_window=timedelta(minutes=late_window),
        minimum_session_coverage=fraction("minimum_session_date_coverage"),
        minimum_timestamp_coverage=fraction("minimum_provider_timestamp_coverage"),
        minimum_late_watermark_coverage=fraction(
            "minimum_late_watermark_coverage"
        ),
        minimum_normal_chain_fraction=fraction("normal_chain_fraction"),
        minimum_official_close_fraction=fraction("official_close_fraction"),
        governed_constants_sha256=hashlib.sha256(encoded).hexdigest(),
    )


@dataclass(frozen=True, slots=True)
class ProviderFinalityRunResult:
    assessments: tuple[ProviderFinalityAssessment, ...]
    aggregate: RunProviderCompletenessEvidence

    def to_dict(self) -> dict[str, object]:
        return {
            "provider_completeness_evidence": self.aggregate.to_dict(),
            "ticker_assessments": [item.to_dict() for item in self.assessments],
        }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_chain(record: DatasetRecord) -> pd.DataFrame:
    path = Path(record.storage_uri)
    if not path.is_file() or _sha256(path) != record.content_hash:
        raise ValueError("canonical option-chain payload failed integrity")
    suffix = path.suffix.lower()
    if suffix == ".parquet":
        frame = pd.read_parquet(path)
    elif suffix == ".csv":
        frame = pd.read_csv(path, low_memory=False)
    else:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
        if isinstance(payload, list):
            frame = pd.DataFrame(payload)
        elif isinstance(payload, Mapping):
            frame = pd.DataFrame([payload])
        else:
            raise ValueError("canonical option-chain payload is not tabular")
    if frame.empty:
        raise ValueError("canonical option-chain payload is empty")
    return frame


def official_close_dataset_id(
    database_path: Path | str,
    *,
    ticker: str,
    session_date: date,
) -> str | None:
    """Resolve a deterministic identity for one COMPLETE canonical close row."""

    path = Path(database_path)
    if not path.is_file():
        return None
    uri = f"file:{path.resolve().as_posix()}?mode=ro"
    with sqlite3.connect(uri, uri=True) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            """
            SELECT ticker, trading_date, adjustment_convention, close,
                   bar_status, provider, source_kind, source_run_id,
                   row_hash, current_batch_id
            FROM ohlcv_daily
            WHERE ticker = ? AND trading_date = ? AND bar_status = 'COMPLETE'
            ORDER BY CASE adjustment_convention
                       WHEN 'SPLIT_DIVIDEND_ADJUSTED' THEN 0 ELSE 1 END,
                     adjustment_convention
            LIMIT 1
            """,
            (str(ticker).strip().upper(), session_date.isoformat()),
        ).fetchone()
    if row is None:
        return None
    normalized = json.dumps(dict(row), sort_keys=True, separators=(",", ":"))
    return "historical_close_v1:" + hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def assess_canonical_option_chain(
    *,
    ticker: str,
    requested_session: date,
    last_completed_session: date,
    request_mode: ProviderRequestMode,
    assessed_at_utc: datetime,
    chain_record: DatasetRecord | None,
    historical_price_database_path: Path | str,
    policy: ProviderFinalityPolicy | None = None,
) -> ProviderFinalityAssessment:
    """Assess one chain using provider timestamps, never fetch/current time."""

    policy = policy or load_provider_finality_policy()
    _, close_utc = session_bounds(requested_session)
    close_id = official_close_dataset_id(
        historical_price_database_path,
        ticker=ticker,
        session_date=requested_session,
    )
    frame = pd.DataFrame()
    if chain_record is not None:
        try:
            frame = _read_chain(chain_record)
        except (OSError, ValueError, json.JSONDecodeError):
            frame = pd.DataFrame()
    expected_count = len(frame)
    raw_timestamps = (
        pd.to_datetime(frame["quote_timestamp_utc"], errors="coerce", utc=True)
        if "quote_timestamp_utc" in frame.columns
        else pd.Series([], dtype="datetime64[ns, UTC]")
    )
    observed = [
        value.to_pydatetime()
        for value in raw_timestamps.dropna()
    ]
    distribution = timestamp_distribution(
        observed,
        expected_count=expected_count,
        late_watermark_utc=close_utc - policy.late_session_window,
    )
    session_coverage = (
        float((raw_timestamps.dt.date == requested_session).sum() / expected_count)
        if expected_count else 0.0
    )
    return assess_provider_session_finality(
        ticker=ticker,
        requested_session=requested_session,
        last_completed_session=last_completed_session,
        request_mode=request_mode,
        assessed_at_utc=assessed_at_utc,
        session_close_utc=close_utc,
        provider_settlement_delay=policy.provider_settlement_delay,
        underlying_close_dataset_id=close_id,
        session_date_coverage=session_coverage,
        timestamps=distribution,
        minimum_session_coverage=policy.minimum_session_coverage,
        minimum_timestamp_coverage=policy.minimum_timestamp_coverage,
        minimum_late_watermark_coverage=policy.minimum_late_watermark_coverage,
    )


def assess_completed_option_worklist(
    *,
    registry: CanonicalRegistry,
    expected_tickers: Sequence[str],
    chain_dataset_ids: Mapping[str, str | None],
    requested_session: date,
    last_completed_session: date,
    assessed_at_utc: datetime | None,
    historical_price_database_path: Path | str,
    request_mode: ProviderRequestMode = ProviderRequestMode.HISTORICAL_COMPLETED,
    policy: ProviderFinalityPolicy | None = None,
) -> ProviderFinalityRunResult:
    """Assess and reconcile every authorised ticker without short-circuiting."""

    policy = policy or load_provider_finality_policy()
    checked = assessed_at_utc or datetime.now(timezone.utc)
    tickers = tuple(sorted({str(value).strip().upper() for value in expected_tickers if str(value).strip()}))
    assessments: list[ProviderFinalityAssessment] = []
    for ticker in tickers:
        dataset_id = str(chain_dataset_ids.get(ticker) or "").strip()
        record = registry.get_dataset(dataset_id) if dataset_id else None
        if record is not None and (
            record.instrument_id != ticker or record.session_date != requested_session
        ):
            record = None
        assessments.append(
            assess_canonical_option_chain(
                ticker=ticker,
                requested_session=requested_session,
                last_completed_session=last_completed_session,
                request_mode=request_mode,
                assessed_at_utc=checked,
                chain_record=record,
                historical_price_database_path=historical_price_database_path,
                policy=policy,
            )
        )
    aggregate = assess_run_provider_completeness(
        assessments,
        chains_expected=len(tickers),
        underlying_tickers_expected=len(tickers),
        checked_at_utc=checked,
        minimum_normal_chain_fraction=policy.minimum_normal_chain_fraction,
        minimum_official_close_fraction=policy.minimum_official_close_fraction,
        governed_constants_sha256=policy.governed_constants_sha256,
    )
    return ProviderFinalityRunResult(tuple(assessments), aggregate)


__all__ = [
    "ProviderFinalityPolicy",
    "ProviderFinalityRunResult",
    "GOVERNED_CONSTANTS_PATH",
    "assess_canonical_option_chain",
    "assess_completed_option_worklist",
    "official_close_dataset_id",
    "load_provider_finality_policy",
]
