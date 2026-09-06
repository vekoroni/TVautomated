"""Pure canonical market-evidence and acquisition policies.

This bounded context decides evidence identity, freshness, reuse and whether a
ticker may acquire a dataset.  It has no filesystem, database, provider,
dataframe or UI dependency.  Infrastructure adapters supply observed facts and
perform any authorised side effects.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from enum import Enum
import hashlib
import json
from typing import Any, Iterable


class _ValueEnum(str, Enum):
    def __str__(self) -> str:
        return self.value


class TickerLifecycleState(_ValueEnum):
    ACTIVE_DISCOVERY = "ACTIVE_DISCOVERY"
    ACTIVE_CORE = "ACTIVE_CORE"
    ACTIVE_OPTIONS = "ACTIVE_OPTIONS"
    ACTIVE_EQUITY_ONLY = "ACTIVE_EQUITY_ONLY"
    ACTIVE_MORNING = "ACTIVE_MORNING"
    DEFERRED_CURRENT_RUN = "DEFERRED_CURRENT_RUN"
    DROPPED_STAGE = "DROPPED_STAGE"
    DROPPED_TERMINAL_DATA = "DROPPED_TERMINAL_DATA"
    DROPPED_TERMINAL_LOGIC = "DROPPED_TERMINAL_LOGIC"
    COMPLETED = "COMPLETED"


class DropClass(_ValueEnum):
    NONE = "NONE"
    STAGE = "STAGE"
    TERMINAL_DATA = "TERMINAL_DATA"
    TERMINAL_LOGIC = "TERMINAL_LOGIC"
    DEFERRED = "DEFERRED"


class EvidenceFreshnessState(_ValueEnum):
    FRESH = "FRESH"
    STALE = "STALE"
    EXPIRED = "EXPIRED"
    FUTURE_DATED = "FUTURE_DATED"


class EvidenceResolutionKind(_ValueEnum):
    EXACT_HIT = "EXACT_HIT"
    SUPERSET_HIT = "SUPERSET_HIT"
    PARTIAL_HIT = "PARTIAL_HIT"
    MISS = "MISS"


ACTIVE_LIFECYCLE_STATES = frozenset(
    {
        TickerLifecycleState.ACTIVE_DISCOVERY,
        TickerLifecycleState.ACTIVE_CORE,
        TickerLifecycleState.ACTIVE_OPTIONS,
        TickerLifecycleState.ACTIVE_EQUITY_ONLY,
        TickerLifecycleState.ACTIVE_MORNING,
    }
)
TERMINAL_LIFECYCLE_STATES = frozenset(
    {
        TickerLifecycleState.DROPPED_TERMINAL_DATA,
        TickerLifecycleState.DROPPED_TERMINAL_LOGIC,
        TickerLifecycleState.COMPLETED,
    }
)
LEGAL_LIFECYCLE_TRANSITIONS: dict[
    TickerLifecycleState, frozenset[TickerLifecycleState]
] = {
    TickerLifecycleState.ACTIVE_DISCOVERY: frozenset({
        TickerLifecycleState.ACTIVE_DISCOVERY, TickerLifecycleState.ACTIVE_CORE,
        TickerLifecycleState.DROPPED_STAGE, TickerLifecycleState.DROPPED_TERMINAL_DATA,
        TickerLifecycleState.DROPPED_TERMINAL_LOGIC, TickerLifecycleState.DEFERRED_CURRENT_RUN,
        TickerLifecycleState.COMPLETED,
    }),
    TickerLifecycleState.ACTIVE_CORE: frozenset({
        TickerLifecycleState.ACTIVE_CORE, TickerLifecycleState.ACTIVE_OPTIONS,
        TickerLifecycleState.ACTIVE_EQUITY_ONLY, TickerLifecycleState.ACTIVE_MORNING,
        TickerLifecycleState.DROPPED_STAGE, TickerLifecycleState.DROPPED_TERMINAL_DATA,
        TickerLifecycleState.DROPPED_TERMINAL_LOGIC, TickerLifecycleState.DEFERRED_CURRENT_RUN,
        TickerLifecycleState.COMPLETED,
    }),
    TickerLifecycleState.ACTIVE_OPTIONS: frozenset({
        TickerLifecycleState.ACTIVE_OPTIONS, TickerLifecycleState.ACTIVE_MORNING,
        TickerLifecycleState.DROPPED_STAGE, TickerLifecycleState.DROPPED_TERMINAL_DATA,
        TickerLifecycleState.DROPPED_TERMINAL_LOGIC, TickerLifecycleState.DEFERRED_CURRENT_RUN,
        TickerLifecycleState.COMPLETED,
    }),
    TickerLifecycleState.ACTIVE_EQUITY_ONLY: frozenset({
        TickerLifecycleState.ACTIVE_EQUITY_ONLY, TickerLifecycleState.ACTIVE_MORNING,
        TickerLifecycleState.DROPPED_STAGE, TickerLifecycleState.DROPPED_TERMINAL_DATA,
        TickerLifecycleState.DROPPED_TERMINAL_LOGIC, TickerLifecycleState.DEFERRED_CURRENT_RUN,
        TickerLifecycleState.COMPLETED,
    }),
    TickerLifecycleState.ACTIVE_MORNING: frozenset({
        TickerLifecycleState.ACTIVE_MORNING, TickerLifecycleState.DROPPED_STAGE,
        TickerLifecycleState.DROPPED_TERMINAL_DATA, TickerLifecycleState.DROPPED_TERMINAL_LOGIC,
        TickerLifecycleState.COMPLETED,
    }),
    TickerLifecycleState.DROPPED_STAGE: frozenset({
        TickerLifecycleState.ACTIVE_CORE, TickerLifecycleState.ACTIVE_OPTIONS,
        TickerLifecycleState.ACTIVE_EQUITY_ONLY, TickerLifecycleState.ACTIVE_MORNING,
        TickerLifecycleState.DROPPED_TERMINAL_DATA, TickerLifecycleState.DROPPED_TERMINAL_LOGIC,
        TickerLifecycleState.COMPLETED,
    }),
    TickerLifecycleState.DEFERRED_CURRENT_RUN: frozenset(),
    TickerLifecycleState.DROPPED_TERMINAL_DATA: frozenset(),
    TickerLifecycleState.DROPPED_TERMINAL_LOGIC: frozenset(),
    TickerLifecycleState.COMPLETED: frozenset(),
}


class MarketEvidenceInvariantError(ValueError):
    """Raised when evidence or lifecycle facts violate domain invariants."""


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _token(value: Any) -> str:
    if isinstance(value, Enum):
        value = value.value
    return str(value or "").strip().upper()


def evidence_request_identity(
    *,
    run_id: str,
    invocation_id: str,
    requesting_stage: str,
    dataset_type: str,
    instrument_id: str,
    session_date: date,
    scope_fingerprint: str,
    evidence_cutoff_utc: str | None,
    exchange_calendar: str,
    evidence_state: str,
) -> str:
    """Create the stable identity for one logical evidence request."""

    payload = {
        "run_id": str(run_id),
        "invocation_id": str(invocation_id),
        "requesting_stage": _token(requesting_stage),
        "dataset_type": _token(dataset_type),
        "instrument_id": _token(instrument_id),
        "session_date": session_date.isoformat(),
        "scope_fingerprint": str(scope_fingerprint),
        "evidence_cutoff_utc": evidence_cutoff_utc,
        "exchange_calendar": _token(exchange_calendar),
        "evidence_state": _token(evidence_state),
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


@dataclass(frozen=True, slots=True)
class EvidenceFreshnessDecision:
    state: EvidenceFreshnessState
    age_seconds: float
    fresh: bool
    reason: str


def evaluate_evidence_freshness(
    *,
    as_of: datetime,
    now: datetime,
    freshness_seconds: int | None,
    expires_at: datetime | None = None,
) -> EvidenceFreshnessDecision:
    """Evaluate evidence age without treating missing limits as timestamp-free."""

    instant = _utc(now)
    observed = _utc(as_of)
    expiry = _utc(expires_at) if expires_at is not None else None
    if freshness_seconds is not None and freshness_seconds < 0:
        raise MarketEvidenceInvariantError("freshness_seconds cannot be negative")
    age = (instant - observed).total_seconds()
    if age < 0:
        return EvidenceFreshnessDecision(
            EvidenceFreshnessState.FUTURE_DATED, age, False, "AS_OF_AFTER_EVALUATION_TIME"
        )
    if expiry is not None and instant > expiry:
        return EvidenceFreshnessDecision(
            EvidenceFreshnessState.EXPIRED, age, False, "EXPIRES_AT_ELAPSED"
        )
    if freshness_seconds is not None and age > freshness_seconds:
        return EvidenceFreshnessDecision(
            EvidenceFreshnessState.STALE, age, False, "FRESHNESS_WINDOW_ELAPSED"
        )
    return EvidenceFreshnessDecision(
        EvidenceFreshnessState.FRESH, age, True, "WITHIN_FRESHNESS_POLICY"
    )


@dataclass(frozen=True, slots=True)
class AcquisitionAuthorityDecision:
    authorised: bool
    reason: str


def decide_ticker_acquisition_authority(
    *,
    lifecycle_state: Any,
    lifecycle_stage: str,
    allowed_capabilities: Iterable[Any],
    requested_stage: str,
    requested_dataset_type: Any,
    registered: bool = True,
    require_worklist: bool = False,
    worklisted: bool = False,
) -> AcquisitionAuthorityDecision:
    """Decide acquisition authority before any provider callback can run."""

    if not registered:
        return AcquisitionAuthorityDecision(False, "TICKER_NOT_REGISTERED")
    state_token = _token(lifecycle_state)
    try:
        state = TickerLifecycleState(state_token)
    except ValueError:
        return AcquisitionAuthorityDecision(False, f"STATE_{state_token or 'MISSING'}_BLOCKS_FETCH")
    if state not in ACTIVE_LIFECYCLE_STATES:
        return AcquisitionAuthorityDecision(False, f"STATE_{state.value}_BLOCKS_FETCH")
    current_stage = _token(lifecycle_stage)
    wanted_stage = _token(requested_stage)
    if current_stage != wanted_stage:
        return AcquisitionAuthorityDecision(False, f"STAGE_MISMATCH_CURRENT_{current_stage}")
    capabilities = {_token(item) for item in allowed_capabilities}
    requested_type = _token(requested_dataset_type)
    if capabilities and requested_type not in capabilities:
        return AcquisitionAuthorityDecision(False, "CAPABILITY_NOT_AUTHORISED")
    if require_worklist and not worklisted:
        return AcquisitionAuthorityDecision(False, "TICKER_NOT_IN_STAGE_WORKLIST")
    return AcquisitionAuthorityDecision(True, "AUTHORISED")


def validate_lifecycle_transition(
    *,
    previous_state: Any,
    new_state: Any,
    explicit_reactivation: bool,
    reason_code: str,
) -> DropClass:
    """Validate a lifecycle transition and return its governed drop class."""

    previous = TickerLifecycleState(_token(previous_state))
    target = TickerLifecycleState(_token(new_state))
    reason = str(reason_code or "").strip()
    if target is TickerLifecycleState.ACTIVE_DISCOVERY and previous in (
        TERMINAL_LIFECYCLE_STATES | {TickerLifecycleState.DEFERRED_CURRENT_RUN}
    ):
        if not explicit_reactivation or not reason:
            raise MarketEvidenceInvariantError(
                "terminal/deferred ticker requires explicit, reasoned reactivation"
            )
    elif target not in LEGAL_LIFECYCLE_TRANSITIONS[previous]:
        raise MarketEvidenceInvariantError(
            f"illegal transition {previous.value} -> {target.value}"
        )
    drop_class = {
        TickerLifecycleState.DROPPED_STAGE: DropClass.STAGE,
        TickerLifecycleState.DROPPED_TERMINAL_DATA: DropClass.TERMINAL_DATA,
        TickerLifecycleState.DROPPED_TERMINAL_LOGIC: DropClass.TERMINAL_LOGIC,
        TickerLifecycleState.DEFERRED_CURRENT_RUN: DropClass.DEFERRED,
    }.get(target, DropClass.NONE)
    if drop_class is not DropClass.NONE and not reason:
        raise MarketEvidenceInvariantError("drop/defer transition requires reason_code")
    return drop_class


@dataclass(frozen=True, slots=True)
class EvidenceCandidate:
    dataset_id: str
    complete: bool
    exact_scope: bool
    covers_scope: bool
    overlaps_scope: bool


@dataclass(frozen=True, slots=True)
class EvidenceReuseDecision:
    kind: EvidenceResolutionKind
    dataset_ids: tuple[str, ...]
    requires_provider_fetch: bool
    reason: str


def decide_evidence_reuse(
    candidates: Iterable[EvidenceCandidate],
) -> EvidenceReuseDecision:
    """Choose exact, superset, partial or miss from fresh ordered candidates."""

    values = tuple(candidates)
    exact = next((item for item in values if item.complete and item.exact_scope), None)
    if exact:
        return EvidenceReuseDecision(
            EvidenceResolutionKind.EXACT_HIT, (exact.dataset_id,), False,
            "exact fresh dataset",
        )
    superset = next((item for item in values if item.complete and item.covers_scope), None)
    if superset:
        return EvidenceReuseDecision(
            EvidenceResolutionKind.SUPERSET_HIT, (superset.dataset_id,), False,
            "fresh canonical superset",
        )
    overlaps = tuple(item.dataset_id for item in values if item.overlaps_scope)
    if overlaps:
        return EvidenceReuseDecision(
            EvidenceResolutionKind.PARTIAL_HIT, overlaps, True,
            "partial coverage requires gap fetch",
        )
    return EvidenceReuseDecision(
        EvidenceResolutionKind.MISS, (), True, "no fresh canonical coverage"
    )

