"""Provider-session finality domain model for AVS-FIX-002.

Clock time and a single late quote cannot prove that a completed option-chain
session is usable. This module combines governed session identity, request
mode, settlement, official-close lineage and chain-wide coverage evidence.
It is pure domain logic: no provider calls, database access or orchestration.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from enum import Enum
from typing import Iterable, Mapping


PROVIDER_COMPLETENESS_VERSION = "provider_completeness_v1"
DEFAULT_MINIMUM_SESSION_COVERAGE = 0.80
DEFAULT_MINIMUM_TIMESTAMP_COVERAGE = 0.80
DEFAULT_MINIMUM_LATE_WATERMARK_COVERAGE = 0.10
DEFAULT_NORMAL_CHAIN_FRACTION = 0.95
DEFAULT_OFFICIAL_CLOSE_FRACTION = 0.99


class ProviderFinalityState(str, Enum):
    COMPLETE = "PROVIDER_SESSION_COMPLETE"
    PARTIAL = "PROVIDER_SESSION_PARTIAL"
    NOT_SETTLED = "PROVIDER_SESSION_NOT_SETTLED"
    DATE_MISMATCH = "PROVIDER_SESSION_DATE_MISMATCH"
    EVIDENCE_INSUFFICIENT = "PROVIDER_SESSION_EVIDENCE_INSUFFICIENT"


class ProviderRequestMode(str, Enum):
    HISTORICAL_COMPLETED = "HISTORICAL_COMPLETED"
    LIVE_LATEST = "LIVE_LATEST"


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("provider finality timestamps must be timezone-aware")
    return value.astimezone(timezone.utc)


@dataclass(frozen=True)
class QuoteTimestampDistribution:
    observed_count: int
    expected_count: int
    minimum_utc: datetime | None
    median_utc: datetime | None
    p95_utc: datetime | None
    maximum_utc: datetime | None
    late_watermark_coverage: float

    @property
    def timestamp_coverage(self) -> float:
        if self.expected_count <= 0:
            return 0.0
        return min(1.0, self.observed_count / self.expected_count)

    def to_dict(self) -> dict[str, object]:
        def text(value: datetime | None) -> str | None:
            return value.isoformat() if value else None

        return {
            "observed_count": self.observed_count,
            "expected_count": self.expected_count,
            "timestamp_coverage": self.timestamp_coverage,
            "minimum_utc": text(self.minimum_utc),
            "median_utc": text(self.median_utc),
            "p95_utc": text(self.p95_utc),
            "maximum_utc": text(self.maximum_utc),
            "late_watermark_coverage": self.late_watermark_coverage,
        }


def timestamp_distribution(
    timestamps: Iterable[datetime | None],
    *,
    expected_count: int,
    late_watermark_utc: datetime,
) -> QuoteTimestampDistribution:
    if expected_count < 0:
        raise ValueError("expected_count cannot be negative")
    watermark = _utc(late_watermark_utc)
    values = sorted(_utc(value) for value in timestamps if value is not None)
    if not values:
        return QuoteTimestampDistribution(0, expected_count, None, None, None, None, 0.0)

    def percentile_index(fraction: float) -> int:
        return min(len(values) - 1, max(0, int((len(values) - 1) * fraction + 0.999999)))

    late_count = sum(value >= watermark for value in values)
    return QuoteTimestampDistribution(
        observed_count=len(values),
        expected_count=expected_count,
        minimum_utc=values[0],
        median_utc=values[percentile_index(0.50)],
        p95_utc=values[percentile_index(0.95)],
        maximum_utc=values[-1],
        late_watermark_coverage=(late_count / expected_count if expected_count else 0.0),
    )


@dataclass(frozen=True)
class ProviderFinalityAssessment:
    state: ProviderFinalityState
    requested_session: date
    last_completed_session: date
    request_mode: ProviderRequestMode
    assessed_at_utc: datetime
    session_close_utc: datetime
    provider_settlement_delay_seconds: int
    underlying_close_dataset_id: str | None
    session_date_coverage: float
    timestamp_distribution: QuoteTimestampDistribution
    completion_basis: tuple[str, ...]
    reasons: tuple[str, ...]
    ticker: str = ""

    @property
    def normal_completed_session_eligible(self) -> bool:
        return self.state is ProviderFinalityState.COMPLETE

    def to_dict(self) -> dict[str, object]:
        return {
            "ticker": self.ticker,
            "finality_state": self.state.value,
            "normal_completed_session_eligible": self.normal_completed_session_eligible,
            "requested_session": self.requested_session.isoformat(),
            "last_completed_session": self.last_completed_session.isoformat(),
            "request_mode": self.request_mode.value,
            "assessed_at_utc": self.assessed_at_utc.isoformat(),
            "session_close_utc": self.session_close_utc.isoformat(),
            "provider_settlement_delay_seconds": self.provider_settlement_delay_seconds,
            "underlying_close_dataset_id": self.underlying_close_dataset_id,
            "session_date_coverage": self.session_date_coverage,
            "timestamp_distribution": self.timestamp_distribution.to_dict(),
            "completion_basis": list(self.completion_basis),
            "reasons": list(self.reasons),
        }


def assess_provider_session_finality(
    *,
    requested_session: date,
    last_completed_session: date,
    request_mode: ProviderRequestMode,
    assessed_at_utc: datetime,
    session_close_utc: datetime,
    provider_settlement_delay: timedelta,
    underlying_close_dataset_id: str | None,
    session_date_coverage: float,
    timestamps: QuoteTimestampDistribution,
    minimum_session_coverage: float = DEFAULT_MINIMUM_SESSION_COVERAGE,
    minimum_timestamp_coverage: float = DEFAULT_MINIMUM_TIMESTAMP_COVERAGE,
    minimum_late_watermark_coverage: float = DEFAULT_MINIMUM_LATE_WATERMARK_COVERAGE,
    ticker: str = "",
) -> ProviderFinalityAssessment:
    assessed = _utc(assessed_at_utc)
    close = _utc(session_close_utc)
    if provider_settlement_delay.total_seconds() < 0:
        raise ValueError("provider settlement delay cannot be negative")
    for label, value in (
        ("session_date_coverage", session_date_coverage),
        ("minimum_session_coverage", minimum_session_coverage),
        ("minimum_timestamp_coverage", minimum_timestamp_coverage),
        ("minimum_late_watermark_coverage", minimum_late_watermark_coverage),
    ):
        if not 0.0 <= value <= 1.0:
            raise ValueError(f"{label} must be within [0, 1]")

    basis: list[str] = []
    reasons: list[str] = []
    state: ProviderFinalityState
    if requested_session != last_completed_session:
        state = ProviderFinalityState.DATE_MISMATCH
        reasons.append("REQUESTED_SESSION_IS_NOT_LAST_COMPLETED_XNYS_SESSION")
    elif request_mode is not ProviderRequestMode.HISTORICAL_COMPLETED:
        state = ProviderFinalityState.EVIDENCE_INSUFFICIENT
        reasons.append("REQUEST_MODE_IS_NOT_HISTORICAL_COMPLETED")
    elif assessed < close + provider_settlement_delay:
        state = ProviderFinalityState.NOT_SETTLED
        reasons.append("PROVIDER_SETTLEMENT_DELAY_NOT_ELAPSED")
    elif not (underlying_close_dataset_id or "").strip():
        state = ProviderFinalityState.EVIDENCE_INSUFFICIENT
        reasons.append("OFFICIAL_UNDERLYING_CLOSE_MISSING")
    elif timestamps.expected_count <= 0 or timestamps.observed_count <= 0:
        state = ProviderFinalityState.EVIDENCE_INSUFFICIENT
        reasons.append("CHAIN_TIMESTAMP_DISTRIBUTION_MISSING")
    elif (
        session_date_coverage < minimum_session_coverage
        or timestamps.timestamp_coverage < minimum_timestamp_coverage
        or timestamps.late_watermark_coverage < minimum_late_watermark_coverage
    ):
        state = ProviderFinalityState.PARTIAL
        if session_date_coverage < minimum_session_coverage:
            reasons.append("SESSION_DATE_COVERAGE_BELOW_THRESHOLD")
        if timestamps.timestamp_coverage < minimum_timestamp_coverage:
            reasons.append("PROVIDER_TIMESTAMP_COVERAGE_BELOW_THRESHOLD")
        if timestamps.late_watermark_coverage < minimum_late_watermark_coverage:
            reasons.append("LATE_SESSION_WATERMARK_COVERAGE_BELOW_THRESHOLD")
    else:
        state = ProviderFinalityState.COMPLETE
        basis.extend(
            (
                "LAST_COMPLETED_XNYS_SESSION_MATCH",
                "HISTORICAL_COMPLETED_REQUEST",
                "PROVIDER_SETTLEMENT_DELAY_ELAPSED",
                "OFFICIAL_UNDERLYING_CLOSE_PRESENT",
                "SESSION_DATE_COVERAGE_PASSED",
                "PROVIDER_TIMESTAMP_COVERAGE_PASSED",
                "LATE_SESSION_WATERMARK_COVERAGE_PASSED",
                "CHAIN_TIMESTAMP_DISTRIBUTION_RECORDED",
            )
        )

    return ProviderFinalityAssessment(
        state=state,
        requested_session=requested_session,
        last_completed_session=last_completed_session,
        request_mode=request_mode,
        assessed_at_utc=assessed,
        session_close_utc=close,
        provider_settlement_delay_seconds=int(provider_settlement_delay.total_seconds()),
        underlying_close_dataset_id=underlying_close_dataset_id,
        session_date_coverage=session_date_coverage,
        timestamp_distribution=timestamps,
        completion_basis=tuple(basis),
        reasons=tuple(reasons),
        ticker=str(ticker or "").strip().upper(),
    )


@dataclass(frozen=True)
class RunProviderCompletenessEvidence:
    """Run-level decision derived from ticker-level finality assessments."""

    chains_expected: int
    complete_chains: int
    underlying_tickers_expected: int
    closes_present: int
    normal_chain_fraction: float
    official_close_fraction: float
    minimum_normal_chain_fraction: float
    minimum_official_close_fraction: float
    state_counts: Mapping[str, int]
    ticker_exceptions: tuple[Mapping[str, object], ...]
    checked_at_utc: datetime
    normal_completed_session_eligible: bool
    governed_constants_sha256: str = "UNCONFIGURED"
    threshold_version: str = PROVIDER_COMPLETENESS_VERSION

    def to_dict(self) -> dict[str, object]:
        return {
            "threshold_version": self.threshold_version,
            "governed_constants_sha256": self.governed_constants_sha256,
            "checked_at_utc": self.checked_at_utc.isoformat(),
            "chains_expected": self.chains_expected,
            "complete_chains": self.complete_chains,
            "normal_chain_fraction": self.normal_chain_fraction,
            "minimum_normal_chain_fraction": self.minimum_normal_chain_fraction,
            "underlying_tickers_expected": self.underlying_tickers_expected,
            "closes_present": self.closes_present,
            "official_close_fraction": self.official_close_fraction,
            "minimum_official_close_fraction": self.minimum_official_close_fraction,
            "state_counts": dict(self.state_counts),
            "ticker_exceptions": [dict(value) for value in self.ticker_exceptions],
            "normal_completed_session_eligible": self.normal_completed_session_eligible,
        }


def assess_run_provider_completeness(
    assessments: Iterable[ProviderFinalityAssessment],
    *,
    chains_expected: int,
    underlying_tickers_expected: int,
    checked_at_utc: datetime,
    minimum_normal_chain_fraction: float = DEFAULT_NORMAL_CHAIN_FRACTION,
    minimum_official_close_fraction: float = DEFAULT_OFFICIAL_CLOSE_FRACTION,
    governed_constants_sha256: str = "UNCONFIGURED",
) -> RunProviderCompletenessEvidence:
    """Aggregate without allowing residual ticker failures to abort the run."""

    checked = _utc(checked_at_utc)
    if chains_expected < 0 or underlying_tickers_expected < 0:
        raise ValueError("provider completeness denominators cannot be negative")
    for label, value in (
        ("minimum_normal_chain_fraction", minimum_normal_chain_fraction),
        ("minimum_official_close_fraction", minimum_official_close_fraction),
    ):
        if not 0.0 <= value <= 1.0:
            raise ValueError(f"{label} must be within [0, 1]")
    values = tuple(assessments)
    if len(values) != chains_expected:
        raise ValueError(
            "ticker-level finality population does not match chains_expected: "
            f"assessments={len(values)} expected={chains_expected}"
        )
    complete = sum(item.state is ProviderFinalityState.COMPLETE for item in values)
    closes = sum(bool((item.underlying_close_dataset_id or "").strip()) for item in values)
    chain_fraction = complete / chains_expected if chains_expected else 0.0
    close_fraction = (
        closes / underlying_tickers_expected if underlying_tickers_expected else 0.0
    )
    counts = Counter(item.state.value for item in values)
    exceptions = tuple(
        {
            "ticker": item.ticker,
            "state": item.state.value,
            "reasons": list(item.reasons),
            "underlying_close_dataset_id": item.underlying_close_dataset_id,
        }
        for item in values
        if item.state is not ProviderFinalityState.COMPLETE
    )
    eligible = (
        chains_expected > 0
        and underlying_tickers_expected > 0
        and chain_fraction >= minimum_normal_chain_fraction
        and close_fraction >= minimum_official_close_fraction
    )
    return RunProviderCompletenessEvidence(
        chains_expected=chains_expected,
        complete_chains=complete,
        underlying_tickers_expected=underlying_tickers_expected,
        closes_present=closes,
        normal_chain_fraction=chain_fraction,
        official_close_fraction=close_fraction,
        minimum_normal_chain_fraction=minimum_normal_chain_fraction,
        minimum_official_close_fraction=minimum_official_close_fraction,
        state_counts=dict(sorted(counts.items())),
        ticker_exceptions=exceptions,
        checked_at_utc=checked,
        normal_completed_session_eligible=eligible,
        governed_constants_sha256=str(governed_constants_sha256 or "UNCONFIGURED"),
    )


__all__ = [
    "DEFAULT_MINIMUM_LATE_WATERMARK_COVERAGE",
    "DEFAULT_MINIMUM_SESSION_COVERAGE",
    "DEFAULT_MINIMUM_TIMESTAMP_COVERAGE",
    "DEFAULT_NORMAL_CHAIN_FRACTION",
    "DEFAULT_OFFICIAL_CLOSE_FRACTION",
    "PROVIDER_COMPLETENESS_VERSION",
    "ProviderFinalityAssessment",
    "ProviderFinalityState",
    "ProviderRequestMode",
    "QuoteTimestampDistribution",
    "RunProviderCompletenessEvidence",
    "assess_run_provider_completeness",
    "assess_provider_session_finality",
    "timestamp_distribution",
]
