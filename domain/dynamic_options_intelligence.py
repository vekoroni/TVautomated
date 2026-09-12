"""Domain contracts for Dynamic Options Intelligence (DOI).

The objects in this module describe thesis-bound option families, immutable
contract assessments and preferred-contract decisions.  They are deliberately
provider, database and UI agnostic.  None of the objects has thesis, execution
or capital authority.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
import math
from typing import Any, Mapping, Sequence


DOI_DOMAIN_VERSION = "dynamic-options-intelligence-v1"
DOI_DECISION_AUTHORITY = "NONE"
DOI_EXECUTION_AUTHORITY = "HUMAN_ONLY"


class _ValueEnum(str, Enum):
    def __str__(self) -> str:
        return self.value


class ContractEntryState(_ValueEnum):
    CONTRACT_MONITOR = "CONTRACT_MONITOR"
    CONTRACT_LIQUIDITY_DEVELOPING = "CONTRACT_LIQUIDITY_DEVELOPING"
    CONTRACT_ENTRY_ACCEPTABLE = "CONTRACT_ENTRY_ACCEPTABLE"
    CONTRACT_LIMIT_PRICE_REQUIRED = "CONTRACT_LIMIT_PRICE_REQUIRED"
    CONTRACT_REPAIR_REQUIRED = "CONTRACT_REPAIR_REQUIRED"
    CONTRACT_DATA_INSUFFICIENT = "CONTRACT_DATA_INSUFFICIENT"
    CONTRACT_DEGRADED = "CONTRACT_DEGRADED"
    CONTRACT_SUPERSEDED = "CONTRACT_SUPERSEDED"
    CONTRACT_EXPIRED = "CONTRACT_EXPIRED"


class ModelApplicabilityState(_ValueEnum):
    APPLICABLE = "APPLICABLE"
    DETERMINISTIC_ONLY = "DETERMINISTIC_ONLY"
    DATA_INSUFFICIENT = "DATA_INSUFFICIENT"
    MODEL_UNAVAILABLE = "MODEL_UNAVAILABLE"
    OUT_OF_DISTRIBUTION = "OUT_OF_DISTRIBUTION"
    NOT_EVALUATED = "NOT_EVALUATED"


class OptionObservationKind(_ValueEnum):
    COMPLETED_SESSION = "COMPLETED_SESSION"
    MORNING = "MORNING"


class OpportunityAcquisitionState(_ValueEnum):
    """Acquisition state only; it never removes or invalidates a thesis."""

    ACTIVE = "ACTIVE"
    DORMANT = "DORMANT"
    CONDITION_BREACHED = "CONDITION_BREACHED"
    HORIZON_ELAPSED = "HORIZON_ELAPSED"
    EXPIRED = "EXPIRED"


@dataclass(frozen=True, slots=True)
class ObservationAcquisitionDecision:
    should_fetch: bool
    reason: str
    retain_opportunity: bool = True
    decision_authority: str = DOI_DECISION_AUTHORITY

    def __post_init__(self) -> None:
        object.__setattr__(self, "reason", _token(self.reason, "reason"))
        if not self.retain_opportunity:
            raise ValueError("observation acquisition cannot remove an opportunity")
        if self.decision_authority != DOI_DECISION_AUTHORITY:
            raise ValueError("observation acquisition has no decision authority")


def decide_observation_acquisition(
    *,
    opportunity_state: OpportunityAcquisitionState | str,
    canonical_evidence_available: bool,
    underlying_reactivated: bool = False,
    manual_refresh: bool = False,
) -> ObservationAcquisitionDecision:
    """Govern provider acquisition without turning timing into trade authority.

    Canonical evidence is always reused unless the operator explicitly asks for
    a newer observation. Dormant, breached and elapsed opportunities stay in
    the opportunity book but do not repeatedly consume provider calls until an
    underlying-price reactivation or manual refresh occurs.
    """

    if isinstance(opportunity_state, OpportunityAcquisitionState):
        state = opportunity_state
    else:
        token = _token(opportunity_state, "opportunity_state")
        aliases = {
            "THESIS_DEVELOPING": OpportunityAcquisitionState.ACTIVE,
            "THESIS_ACTIVE": OpportunityAcquisitionState.ACTIVE,
            "THESIS_VALIDATED": OpportunityAcquisitionState.ACTIVE,
            "THESIS_RECOVERING": OpportunityAcquisitionState.ACTIVE,
            "THESIS_DATA_INSUFFICIENT": OpportunityAcquisitionState.ACTIVE,
            "INVALIDATED": OpportunityAcquisitionState.CONDITION_BREACHED,
            "THESIS_CONDITION_BREACHED": OpportunityAcquisitionState.CONDITION_BREACHED,
            "TARGET_REALIZED": OpportunityAcquisitionState.DORMANT,
            "TARGET_TOUCHED": OpportunityAcquisitionState.DORMANT,
            "COMPLETED": OpportunityAcquisitionState.DORMANT,
            "HORIZON_EXPIRED": OpportunityAcquisitionState.HORIZON_ELAPSED,
            "HORIZON_ELAPSED_REASSESS": OpportunityAcquisitionState.HORIZON_ELAPSED,
        }
        state = aliases.get(token) or OpportunityAcquisitionState(token)
    if state is OpportunityAcquisitionState.EXPIRED:
        return ObservationAcquisitionDecision(False, "CONTRACT_EXPIRED_NO_FETCH")
    if manual_refresh:
        return ObservationAcquisitionDecision(True, "MANUAL_NEWER_OBSERVATION_REQUESTED")
    if canonical_evidence_available:
        return ObservationAcquisitionDecision(False, "REUSE_CANONICAL_EVIDENCE")
    if state is OpportunityAcquisitionState.ACTIVE:
        return ObservationAcquisitionDecision(True, "CANONICAL_EVIDENCE_MISSING")
    if underlying_reactivated:
        return ObservationAcquisitionDecision(True, "UNDERLYING_PRICE_REACTIVATED")
    return ObservationAcquisitionDecision(
        False, f"{state.value}_ACQUISITION_SUPPRESSED"
    )


def _required_text(value: Any, field_name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{field_name} is required")
    return text


def _token(value: Any, field_name: str) -> str:
    return _required_text(value, field_name).upper()


def _direction(value: Any) -> str:
    direction = _token(value, "governed_direction")
    if direction not in {"CALL", "PUT"}:
        raise ValueError("governed_direction must be CALL or PUT")
    return direction


def _utc(value: datetime, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise ValueError(f"{field_name} must be a datetime")
    if value.tzinfo is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _finite_optional(value: Any, field_name: str) -> float | None:
    if value is None:
        return None
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{field_name} must be finite")
    return number


def _probability(value: Any, field_name: str) -> float | None:
    number = _finite_optional(value, field_name)
    if number is not None and not 0.0 <= number <= 1.0:
        raise ValueError(f"{field_name} must be between zero and one")
    return number


def _tokens(values: Sequence[Any], field_name: str) -> tuple[str, ...]:
    normalised = tuple(_token(value, field_name) for value in values)
    if len(set(normalised)) != len(normalised):
        raise ValueError(f"{field_name} contains duplicates")
    return normalised


def _unique_texts(values: Sequence[Any], field_name: str) -> tuple[str, ...]:
    normalised = tuple(_required_text(value, field_name) for value in values)
    if len(set(normalised)) != len(normalised):
        raise ValueError(f"{field_name} contains duplicates")
    return normalised


def _canonical_json(value: Mapping[str, Any]) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _identity(namespace: str, value: Mapping[str, Any]) -> str:
    payload = _canonical_json(value)
    return hashlib.sha256(f"{namespace}|{payload}".encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class UnderlyingThesisRef:
    thesis_id: str
    thesis_version: int
    ticker: str
    governed_direction: str
    origin_spot: float
    origin_timestamp_utc: datetime
    target_spot: float | None
    invalidation_spot: float | None
    planned_hold_sessions: int
    planned_hold_source: str
    evidence_cutoff_utc: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "thesis_id", _token(self.thesis_id, "thesis_id"))
        object.__setattr__(self, "ticker", _token(self.ticker, "ticker"))
        object.__setattr__(
            self, "governed_direction", _direction(self.governed_direction)
        )
        if int(self.thesis_version) < 1:
            raise ValueError("thesis_version must be at least one")
        object.__setattr__(self, "thesis_version", int(self.thesis_version))
        origin = _finite_optional(self.origin_spot, "origin_spot")
        if origin is None or origin <= 0:
            raise ValueError("origin_spot must be positive")
        object.__setattr__(self, "origin_spot", origin)
        target = _finite_optional(self.target_spot, "target_spot")
        invalidation = _finite_optional(self.invalidation_spot, "invalidation_spot")
        if target is not None and target <= 0:
            raise ValueError("target_spot must be positive when supplied")
        if invalidation is not None and invalidation <= 0:
            raise ValueError("invalidation_spot must be positive when supplied")
        if target is not None:
            direction = 1.0 if self.governed_direction == "CALL" else -1.0
            if direction * (target - origin) <= 0:
                raise ValueError("target_spot is wrong-sided for governed_direction")
        if invalidation is not None:
            direction = 1.0 if self.governed_direction == "CALL" else -1.0
            if direction * (origin - invalidation) <= 0:
                raise ValueError("invalidation_spot is wrong-sided for governed_direction")
        object.__setattr__(self, "target_spot", target)
        object.__setattr__(self, "invalidation_spot", invalidation)
        hold = int(self.planned_hold_sessions)
        if not 1 <= hold <= 20:
            raise ValueError("planned_hold_sessions must be between 1 and 20")
        object.__setattr__(self, "planned_hold_sessions", hold)
        object.__setattr__(
            self,
            "planned_hold_source",
            _token(self.planned_hold_source, "planned_hold_source"),
        )
        origin_time = _utc(self.origin_timestamp_utc, "origin_timestamp_utc")
        cutoff = _utc(self.evidence_cutoff_utc, "evidence_cutoff_utc")
        if origin_time > cutoff:
            raise ValueError("origin_timestamp_utc cannot exceed evidence_cutoff_utc")
        object.__setattr__(self, "origin_timestamp_utc", origin_time)
        object.__setattr__(self, "evidence_cutoff_utc", cutoff)

    @property
    def geometry_complete(self) -> bool:
        return self.target_spot is not None and self.invalidation_spot is not None

    def to_dict(self) -> dict[str, Any]:
        return {
            "thesis_id": self.thesis_id,
            "thesis_version": self.thesis_version,
            "ticker": self.ticker,
            "governed_direction": self.governed_direction,
            "origin_spot": self.origin_spot,
            "origin_timestamp_utc": _iso(self.origin_timestamp_utc),
            "target_spot": self.target_spot,
            "invalidation_spot": self.invalidation_spot,
            "planned_hold_sessions": self.planned_hold_sessions,
            "planned_hold_source": self.planned_hold_source,
            "evidence_cutoff_utc": _iso(self.evidence_cutoff_utc),
            "geometry_complete": self.geometry_complete,
        }


@dataclass(frozen=True, slots=True)
class ContractFamily:
    family_id: str
    thesis: UnderlyingThesisRef
    run_id: str
    family_policy_version: str
    evidence_cutoff_utc: datetime
    candidate_symbols: tuple[str, ...]
    source_dataset_ids: tuple[str, ...]
    family_state: ModelApplicabilityState
    created_at: datetime
    metadata: Mapping[str, Any]
    decision_authority: str = DOI_DECISION_AUTHORITY
    can_change_direction: bool = False
    can_invalidate_thesis: bool = False
    can_grant_capital: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "family_id", _required_text(self.family_id, "family_id"))
        object.__setattr__(self, "run_id", _token(self.run_id, "run_id"))
        object.__setattr__(
            self,
            "family_policy_version",
            _required_text(self.family_policy_version, "family_policy_version"),
        )
        object.__setattr__(
            self, "candidate_symbols", _tokens(self.candidate_symbols, "candidate_symbols")
        )
        object.__setattr__(
            self,
            "source_dataset_ids",
            _unique_texts(self.source_dataset_ids, "source_dataset_ids"),
        )
        state = (
            self.family_state
            if isinstance(self.family_state, ModelApplicabilityState)
            else ModelApplicabilityState(_token(self.family_state, "family_state"))
        )
        object.__setattr__(self, "family_state", state)
        cutoff = _utc(self.evidence_cutoff_utc, "evidence_cutoff_utc")
        created = _utc(self.created_at, "created_at")
        if self.thesis.evidence_cutoff_utc > cutoff:
            raise ValueError("family evidence cutoff predates its thesis evidence")
        object.__setattr__(self, "evidence_cutoff_utc", cutoff)
        object.__setattr__(self, "created_at", created)
        object.__setattr__(self, "metadata", dict(self.metadata or {}))
        if self.decision_authority != DOI_DECISION_AUTHORITY:
            raise ValueError("ContractFamily decision_authority must be NONE")
        if self.can_change_direction or self.can_invalidate_thesis or self.can_grant_capital:
            raise ValueError("ContractFamily cannot possess trading authority")

    @classmethod
    def create(
        cls,
        *,
        thesis: UnderlyingThesisRef,
        run_id: str,
        family_policy_version: str,
        evidence_cutoff_utc: datetime,
        candidate_symbols: Sequence[str] = (),
        source_dataset_ids: Sequence[str] = (),
        family_state: ModelApplicabilityState = ModelApplicabilityState.NOT_EVALUATED,
        created_at: datetime | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> "ContractFamily":
        cutoff = _utc(evidence_cutoff_utc, "evidence_cutoff_utc")
        identity = {
            "thesis_id": _token(thesis.thesis_id, "thesis_id"),
            "thesis_version": thesis.thesis_version,
            "run_id": _token(run_id, "run_id"),
            "family_policy_version": _required_text(
                family_policy_version, "family_policy_version"
            ),
            "evidence_cutoff_utc": _iso(cutoff),
        }
        return cls(
            family_id=_identity("DOI_CONTRACT_FAMILY_V1", identity),
            thesis=thesis,
            run_id=run_id,
            family_policy_version=family_policy_version,
            evidence_cutoff_utc=cutoff,
            candidate_symbols=tuple(candidate_symbols),
            source_dataset_ids=tuple(source_dataset_ids),
            family_state=family_state,
            created_at=created_at or datetime.now(timezone.utc),
            metadata=dict(metadata or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "family_id": self.family_id,
            "thesis": self.thesis.to_dict(),
            "run_id": self.run_id,
            "family_policy_version": self.family_policy_version,
            "evidence_cutoff_utc": _iso(self.evidence_cutoff_utc),
            "candidate_symbols": list(self.candidate_symbols),
            "source_dataset_ids": list(self.source_dataset_ids),
            "family_state": self.family_state.value,
            "created_at": _iso(self.created_at),
            "metadata": dict(self.metadata),
            "decision_authority": self.decision_authority,
            "can_change_direction": self.can_change_direction,
            "can_invalidate_thesis": self.can_invalidate_thesis,
            "can_grant_capital": self.can_grant_capital,
            "domain_version": DOI_DOMAIN_VERSION,
        }


@dataclass(frozen=True, slots=True)
class ContractAssessment:
    assessment_id: str
    family_id: str
    thesis_id: str
    run_id: str
    contract_symbol: str
    observation_id: str
    entry_state: ContractEntryState
    applicability_state: ModelApplicabilityState
    evidence_cutoff_utc: datetime
    input_dataset_ids: tuple[str, ...]
    calculation_version: str
    feature_version: str
    model_version: str
    ranking_score_uncalibrated: float | None = None
    p_liquidity_1d: float | None = None
    p_liquidity_2d: float | None = None
    p_liquidity_3d: float | None = None
    p_positive_return_before_horizon: float | None = None
    p_return_hurdle_before_horizon: float | None = None
    p_target_before_invalidation: float | None = None
    expected_net_return: float | None = None
    expected_downside: float | None = None
    expected_time_to_monetisation: float | None = None
    model_uncertainty: float | None = None
    probabilities_calibrated: bool = False
    metadata: Mapping[str, Any] = None  # type: ignore[assignment]
    decision_authority: str = DOI_DECISION_AUTHORITY
    can_change_direction: bool = False
    can_invalidate_thesis: bool = False
    can_grant_capital: bool = False

    def __post_init__(self) -> None:
        for name in ("assessment_id", "family_id", "observation_id"):
            object.__setattr__(self, name, _required_text(getattr(self, name), name))
        for name in ("thesis_id", "run_id", "contract_symbol"):
            object.__setattr__(self, name, _token(getattr(self, name), name))
        entry = self.entry_state if isinstance(self.entry_state, ContractEntryState) else ContractEntryState(_token(self.entry_state, "entry_state"))
        applicability = self.applicability_state if isinstance(self.applicability_state, ModelApplicabilityState) else ModelApplicabilityState(_token(self.applicability_state, "applicability_state"))
        object.__setattr__(self, "entry_state", entry)
        object.__setattr__(self, "applicability_state", applicability)
        object.__setattr__(self, "evidence_cutoff_utc", _utc(self.evidence_cutoff_utc, "evidence_cutoff_utc"))
        object.__setattr__(
            self,
            "input_dataset_ids",
            _unique_texts(self.input_dataset_ids, "input_dataset_ids"),
        )
        if not self.input_dataset_ids:
            raise ValueError("input_dataset_ids must not be empty")
        for name in ("calculation_version", "feature_version", "model_version"):
            object.__setattr__(self, name, _required_text(getattr(self, name), name))
        object.__setattr__(self, "ranking_score_uncalibrated", _finite_optional(self.ranking_score_uncalibrated, "ranking_score_uncalibrated"))
        probability_fields = (
            "p_liquidity_1d", "p_liquidity_2d", "p_liquidity_3d",
            "p_positive_return_before_horizon", "p_return_hurdle_before_horizon",
            "p_target_before_invalidation",
        )
        for name in probability_fields:
            object.__setattr__(self, name, _probability(getattr(self, name), name))
        for name in ("expected_net_return", "expected_downside", "expected_time_to_monetisation"):
            object.__setattr__(self, name, _finite_optional(getattr(self, name), name))
        object.__setattr__(self, "model_uncertainty", _probability(self.model_uncertainty, "model_uncertainty"))
        probabilities_present = any(
            getattr(self, name) is not None for name in probability_fields
        )
        if not self.probabilities_calibrated and probabilities_present:
            raise ValueError("probability outputs require probabilities_calibrated=True")
        if self.probabilities_calibrated and not probabilities_present:
            raise ValueError("probabilities_calibrated requires a probability output")
        if self.probabilities_calibrated and self.model_version == "NOT_EVALUATED":
            raise ValueError("calibrated probabilities require a fitted model_version")
        object.__setattr__(self, "metadata", dict(self.metadata or {}))
        if self.decision_authority != DOI_DECISION_AUTHORITY:
            raise ValueError("ContractAssessment decision_authority must be NONE")
        if self.can_change_direction or self.can_invalidate_thesis or self.can_grant_capital:
            raise ValueError("ContractAssessment cannot possess trading authority")

    @classmethod
    def create(cls, *, family_id: str, thesis_id: str, run_id: str,
               contract_symbol: str, observation_id: str,
               entry_state: ContractEntryState,
               applicability_state: ModelApplicabilityState,
               evidence_cutoff_utc: datetime, input_dataset_ids: Sequence[str],
               calculation_version: str, feature_version: str,
               model_version: str = "NOT_EVALUATED", **values: Any) -> "ContractAssessment":
        identity = {
            "family_id": _required_text(family_id, "family_id"),
            "contract_symbol": _token(contract_symbol, "contract_symbol"),
            "observation_id": _required_text(observation_id, "observation_id"),
            "calculation_version": _required_text(calculation_version, "calculation_version"),
            "evidence_cutoff_utc": _iso(_utc(evidence_cutoff_utc, "evidence_cutoff_utc")),
        }
        return cls(
            assessment_id=_identity("DOI_CONTRACT_ASSESSMENT_V1", identity),
            family_id=family_id, thesis_id=thesis_id, run_id=run_id,
            contract_symbol=contract_symbol, observation_id=observation_id,
            entry_state=entry_state, applicability_state=applicability_state,
            evidence_cutoff_utc=evidence_cutoff_utc,
            input_dataset_ids=tuple(input_dataset_ids),
            calculation_version=calculation_version, feature_version=feature_version,
            model_version=model_version, **values,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "assessment_id": self.assessment_id, "family_id": self.family_id,
            "thesis_id": self.thesis_id, "run_id": self.run_id,
            "contract_symbol": self.contract_symbol, "observation_id": self.observation_id,
            "entry_state": self.entry_state.value,
            "applicability_state": self.applicability_state.value,
            "evidence_cutoff_utc": _iso(self.evidence_cutoff_utc),
            "input_dataset_ids": list(self.input_dataset_ids),
            "calculation_version": self.calculation_version,
            "feature_version": self.feature_version, "model_version": self.model_version,
            "ranking_score_uncalibrated": self.ranking_score_uncalibrated,
            "p_liquidity_1d": self.p_liquidity_1d, "p_liquidity_2d": self.p_liquidity_2d,
            "p_liquidity_3d": self.p_liquidity_3d,
            "p_positive_return_before_horizon": self.p_positive_return_before_horizon,
            "p_return_hurdle_before_horizon": self.p_return_hurdle_before_horizon,
            "p_target_before_invalidation": self.p_target_before_invalidation,
            "expected_net_return": self.expected_net_return,
            "expected_downside": self.expected_downside,
            "expected_time_to_monetisation": self.expected_time_to_monetisation,
            "model_uncertainty": self.model_uncertainty,
            "probabilities_calibrated": self.probabilities_calibrated,
            "metadata": dict(self.metadata), "decision_authority": self.decision_authority,
            "can_change_direction": self.can_change_direction,
            "can_invalidate_thesis": self.can_invalidate_thesis,
            "can_grant_capital": self.can_grant_capital,
            "domain_version": DOI_DOMAIN_VERSION,
        }


@dataclass(frozen=True, slots=True)
class PreferredContractDecision:
    decision_id: str
    event_key: str
    family_id: str
    thesis_id: str
    run_id: str
    selected_contract_symbol: str
    selected_assessment_id: str
    selection_reason: str
    selected_at: datetime
    alternative_contract_symbols: tuple[str, ...] = ()
    previous_contract_symbol: str | None = None
    prior_decision_id: str | None = None
    utility_margin: float | None = None
    hysteresis_applied: bool = False
    economics_recomputed: bool = False
    decision_version: int | None = None
    metadata: Mapping[str, Any] = None  # type: ignore[assignment]
    decision_authority: str = DOI_DECISION_AUTHORITY
    execution_authority: str = DOI_EXECUTION_AUTHORITY

    def __post_init__(self) -> None:
        for name in ("decision_id", "family_id", "selected_assessment_id"):
            object.__setattr__(self, name, _required_text(getattr(self, name), name))
        for name in ("event_key", "thesis_id", "run_id", "selected_contract_symbol"):
            object.__setattr__(self, name, _token(getattr(self, name), name))
        object.__setattr__(self, "selection_reason", _token(self.selection_reason, "selection_reason"))
        alternatives = _tokens(self.alternative_contract_symbols, "alternative_contract_symbols")
        if self.selected_contract_symbol in alternatives:
            raise ValueError("selected contract cannot also be an alternative")
        object.__setattr__(self, "alternative_contract_symbols", alternatives)
        if self.previous_contract_symbol:
            object.__setattr__(self, "previous_contract_symbol", _token(self.previous_contract_symbol, "previous_contract_symbol"))
        if self.prior_decision_id:
            object.__setattr__(self, "prior_decision_id", _required_text(self.prior_decision_id, "prior_decision_id"))
        object.__setattr__(self, "utility_margin", _finite_optional(self.utility_margin, "utility_margin"))
        object.__setattr__(self, "selected_at", _utc(self.selected_at, "selected_at"))
        if self.decision_version is not None and int(self.decision_version) < 1:
            raise ValueError("decision_version must be at least one")
        if self.previous_contract_symbol and self.previous_contract_symbol != self.selected_contract_symbol and not self.economics_recomputed:
            raise ValueError("replacement contract requires exact economics recomputation")
        object.__setattr__(self, "metadata", dict(self.metadata or {}))
        if self.decision_authority != DOI_DECISION_AUTHORITY or self.execution_authority != DOI_EXECUTION_AUTHORITY:
            raise ValueError("PreferredContractDecision authority is fixed")

    @classmethod
    def create(cls, *, event_key: str, family_id: str, thesis_id: str,
               run_id: str, selected_contract_symbol: str,
               selected_assessment_id: str, selection_reason: str,
               selected_at: datetime | None = None, **values: Any) -> "PreferredContractDecision":
        identity = {
            "event_key": _token(event_key, "event_key"),
            "family_id": _required_text(family_id, "family_id"),
            "thesis_id": _token(thesis_id, "thesis_id"),
        }
        return cls(
            decision_id=_identity("DOI_PREFERRED_CONTRACT_DECISION_V1", identity),
            event_key=event_key, family_id=family_id, thesis_id=thesis_id,
            run_id=run_id, selected_contract_symbol=selected_contract_symbol,
            selected_assessment_id=selected_assessment_id,
            selection_reason=selection_reason,
            selected_at=selected_at or datetime.now(timezone.utc), **values,
        )

    def with_version(self, version: int) -> "PreferredContractDecision":
        return replace(self, decision_version=version)

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision_id": self.decision_id, "event_key": self.event_key,
            "family_id": self.family_id, "thesis_id": self.thesis_id,
            "run_id": self.run_id,
            "selected_contract_symbol": self.selected_contract_symbol,
            "selected_assessment_id": self.selected_assessment_id,
            "selection_reason": self.selection_reason,
            "selected_at": _iso(self.selected_at),
            "alternative_contract_symbols": list(self.alternative_contract_symbols),
            "previous_contract_symbol": self.previous_contract_symbol,
            "prior_decision_id": self.prior_decision_id,
            "utility_margin": self.utility_margin,
            "hysteresis_applied": self.hysteresis_applied,
            "economics_recomputed": self.economics_recomputed,
            "decision_version": self.decision_version,
            "metadata": dict(self.metadata),
            "decision_authority": self.decision_authority,
            "execution_authority": self.execution_authority,
            "domain_version": DOI_DOMAIN_VERSION,
        }


__all__ = [
    "DOI_DOMAIN_VERSION", "DOI_DECISION_AUTHORITY", "DOI_EXECUTION_AUTHORITY",
    "ContractEntryState", "ModelApplicabilityState", "OptionObservationKind",
    "OpportunityAcquisitionState", "ObservationAcquisitionDecision",
    "decide_observation_acquisition", "UnderlyingThesisRef",
    "ContractFamily", "ContractAssessment", "PreferredContractDecision",
]
