"""Pure DOI-6 lifecycle, material-change and hysteresis rules.

The lifecycle is an advisory observation model.  It never removes a ticker,
changes the governed thesis, grants capital or executes an option.  Entry,
breach, elapsed-horizon and quote states remain visible for human judgement.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from enum import Enum
import hashlib
import json
import math
from typing import Any, Mapping, Sequence

from .dynamic_options_intelligence import (
    DOI_DECISION_AUTHORITY,
    DOI_EXECUTION_AUTHORITY,
    ContractAssessment,
    ContractEntryState,
    ModelApplicabilityState,
)


DOI_LIFECYCLE_DOMAIN_VERSION = "doi-dynamic-lifecycle-v1"
DOI_MATERIAL_CHANGE_POLICY_VERSION = "doi-material-change-policy-v1"
DOI_HYSTERESIS_POLICY_VERSION = "hysteresis_v1"


class _ValueEnum(str, Enum):
    def __str__(self) -> str:
        return self.value


class DOIEvaluationPoint(_ValueEnum):
    COMPLETED_SESSION = "COMPLETED_SESSION"
    MORNING_GATE = "MORNING_GATE"
    INTRADAY_MATERIAL = "INTRADAY_MATERIAL"
    MANUAL_REFRESH = "MANUAL_REFRESH"


class DOIThesisConditionState(_ValueEnum):
    THESIS_DEVELOPING = "THESIS_DEVELOPING"
    THESIS_CONFIRMED = "THESIS_CONFIRMED"
    THESIS_CONDITION_BREACHED = "THESIS_CONDITION_BREACHED"
    THESIS_RECOVERING = "THESIS_RECOVERING"
    TARGET_TOUCHED = "TARGET_TOUCHED"
    HORIZON_ELAPSED_REASSESS = "HORIZON_ELAPSED_REASSESS"
    DATA_INSUFFICIENT = "DATA_INSUFFICIENT"


class ContractTransitionState(_ValueEnum):
    INITIAL = "INITIAL"
    STABLE = "STABLE"
    MATURED = "MATURED"
    DEGRADED = "DEGRADED"
    SUPERSEDED = "SUPERSEDED"
    EXPIRED = "EXPIRED"


@dataclass(frozen=True, slots=True)
class DynamicLifecyclePolicy:
    """Versioned operational triggers; values are not fitted model claims."""

    spot_move_fraction: float = 0.02
    proximity_change_fraction: float = 0.02
    spread_change_fraction_points: float = 0.10
    volume_growth_multiple: float = 1.50
    volume_growth_minimum: float = 10.0
    iv_change_points: float = 0.05
    minimum_utility_margin: float = 0.05
    relative_utility_margin: float = 0.10
    dte_boundaries: tuple[int, ...] = (8, 13, 21, 35, 60)
    material_policy_version: str = DOI_MATERIAL_CHANGE_POLICY_VERSION
    hysteresis_policy_version: str = DOI_HYSTERESIS_POLICY_VERSION
    hysteresis_approval_id: str | None = None

    def __post_init__(self) -> None:
        for name in (
            "spot_move_fraction", "proximity_change_fraction",
            "spread_change_fraction_points", "volume_growth_minimum",
            "iv_change_points", "minimum_utility_margin",
            "relative_utility_margin",
        ):
            value = float(getattr(self, name))
            if not math.isfinite(value) or value < 0:
                raise ValueError(f"{name} must be finite and non-negative")
        if not math.isfinite(float(self.volume_growth_multiple)) or self.volume_growth_multiple < 1:
            raise ValueError("volume_growth_multiple must be at least one")
        boundaries = tuple(sorted({int(item) for item in self.dte_boundaries}))
        if any(item < 0 for item in boundaries):
            raise ValueError("dte_boundaries cannot contain negative values")
        object.__setattr__(self, "dte_boundaries", boundaries)


@dataclass(frozen=True, slots=True)
class ContractEvidenceSnapshot:
    contract_symbol: str
    assessment_id: str
    observation_id: str
    evidence_cutoff_utc: datetime
    spot: float
    strike: float
    dte: float
    bid: float | None
    ask: float | None
    spread_fraction: float | None
    volume: float | None
    implied_volatility: float | None
    entry_state: ContractEntryState
    applicability_state: ModelApplicabilityState
    ranking_score_uncalibrated: float | None
    adverse_worst_return: float | None
    target_spot: float | None = None
    invalidation_spot: float | None = None
    thesis_version: int = 1

    def __post_init__(self) -> None:
        for name in ("contract_symbol", "assessment_id", "observation_id"):
            if not str(getattr(self, name)).strip():
                raise ValueError(f"{name} is required")
        instant = self.evidence_cutoff_utc
        if instant.tzinfo is None:
            raise ValueError("evidence_cutoff_utc must be timezone-aware")
        object.__setattr__(self, "evidence_cutoff_utc", instant.astimezone(timezone.utc))
        for name in ("spot", "strike"):
            value = float(getattr(self, name))
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be positive and finite")
        if not math.isfinite(float(self.dte)) or self.dte < 0:
            raise ValueError("dte must be finite and non-negative")
        for name in (
            "bid", "ask", "spread_fraction", "volume", "implied_volatility",
            "ranking_score_uncalibrated", "adverse_worst_return", "target_spot",
            "invalidation_spot",
        ):
            value = getattr(self, name)
            if value is not None and not math.isfinite(float(value)):
                raise ValueError(f"{name} must be finite when supplied")
        if int(self.thesis_version) < 1:
            raise ValueError("thesis_version must be at least one")


@dataclass(frozen=True, slots=True)
class MaterialChangeDecision:
    should_revalue: bool
    reasons: tuple[str, ...]
    evaluation_point: DOIEvaluationPoint
    retain_opportunity: bool = True
    decision_authority: str = DOI_DECISION_AUTHORITY

    def __post_init__(self) -> None:
        if self.should_revalue != bool(self.reasons):
            raise ValueError("material decision and reason population disagree")
        if not self.retain_opportunity:
            raise ValueError("material-change policy cannot remove an opportunity")
        if self.decision_authority != DOI_DECISION_AUTHORITY:
            raise ValueError("material-change policy has no decision authority")


@dataclass(frozen=True, slots=True)
class ContractLifecycleTransition:
    contract_symbol: str
    previous_entry_state: ContractEntryState | None
    current_entry_state: ContractEntryState
    transition_state: ContractTransitionState
    reason: str
    retain_opportunity: bool = True
    decision_authority: str = DOI_DECISION_AUTHORITY

    def __post_init__(self) -> None:
        if not self.retain_opportunity:
            raise ValueError("contract lifecycle cannot remove an opportunity")
        if self.decision_authority != DOI_DECISION_AUTHORITY:
            raise ValueError("contract lifecycle has no decision authority")


@dataclass(frozen=True, slots=True)
class ContractRankingDecision:
    selected_assessment: ContractAssessment | None
    previous_contract_symbol: str | None
    alternative_contract_symbols: tuple[str, ...]
    selection_reason: str
    switched_contract: bool
    hysteresis_applied: bool
    hysteresis_suppressed_switch: bool
    utility_margin: float | None
    economics_recomputed: bool
    retain_opportunity: bool = True
    decision_authority: str = DOI_DECISION_AUTHORITY
    execution_authority: str = DOI_EXECUTION_AUTHORITY

    def __post_init__(self) -> None:
        if not self.retain_opportunity:
            raise ValueError("contract ranking cannot remove an opportunity")
        if self.decision_authority != DOI_DECISION_AUTHORITY:
            raise ValueError("contract ranking has no decision authority")
        if self.execution_authority != DOI_EXECUTION_AUTHORITY:
            raise ValueError("execution authority must remain human-only")
        if self.switched_contract and not self.economics_recomputed:
            raise ValueError("contract supersession requires recomputed economics")


@dataclass(frozen=True, slots=True)
class DOILifecycleEvent:
    event_id: str
    event_key: str
    thesis_id: str
    thesis_version: int
    family_id: str
    run_id: str
    evaluation_point: DOIEvaluationPoint
    condition_state: DOIThesisConditionState
    previous_condition_state: DOIThesisConditionState | None
    evidence_cutoff_utc: datetime
    current_spot: float | None
    target_spot: float | None
    invalidation_spot: float | None
    horizon_end_date: date | None
    material_change: bool
    material_reasons: tuple[str, ...]
    recorded_at: datetime
    metadata: Mapping[str, Any]
    retain_opportunity: bool = True
    decision_authority: str = DOI_DECISION_AUTHORITY
    can_change_direction: bool = False
    can_grant_capital: bool = False

    def __post_init__(self) -> None:
        for name in ("event_id", "event_key", "thesis_id", "family_id", "run_id"):
            if not str(getattr(self, name)).strip():
                raise ValueError(f"{name} is required")
        if int(self.thesis_version) < 1:
            raise ValueError("thesis_version must be at least one")
        for name in ("evidence_cutoff_utc", "recorded_at"):
            value = getattr(self, name)
            if value.tzinfo is None:
                raise ValueError(f"{name} must be timezone-aware")
            object.__setattr__(self, name, value.astimezone(timezone.utc))
        for name in ("current_spot", "target_spot", "invalidation_spot"):
            value = getattr(self, name)
            if value is not None and not math.isfinite(float(value)):
                raise ValueError(f"{name} must be finite when supplied")
        if self.current_spot is not None and self.current_spot <= 0:
            raise ValueError("current_spot must be positive when supplied")
        object.__setattr__(self, "material_reasons", tuple(self.material_reasons))
        object.__setattr__(self, "metadata", dict(self.metadata or {}))
        if not self.retain_opportunity:
            raise ValueError("DOI lifecycle cannot remove an opportunity")
        if self.decision_authority != DOI_DECISION_AUTHORITY:
            raise ValueError("DOI lifecycle has no decision authority")
        if self.can_change_direction or self.can_grant_capital:
            raise ValueError("DOI lifecycle cannot change direction or grant capital")
        if self.material_change != bool(self.material_reasons):
            raise ValueError("material-change flag and reasons disagree")

    @classmethod
    def create(
        cls,
        *,
        event_key: str,
        thesis_id: str,
        thesis_version: int,
        family_id: str,
        run_id: str,
        evaluation_point: DOIEvaluationPoint,
        condition_state: DOIThesisConditionState,
        previous_condition_state: DOIThesisConditionState | None,
        evidence_cutoff_utc: datetime,
        current_spot: float | None,
        target_spot: float | None,
        invalidation_spot: float | None,
        horizon_end_date: date | None,
        material_change: bool,
        material_reasons: Sequence[str],
        recorded_at: datetime | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> "DOILifecycleEvent":
        identity = {
            "event_key": str(event_key).strip().upper(),
            "thesis_id": str(thesis_id).strip().upper(),
            "family_id": str(family_id).strip(),
        }
        encoded = json.dumps(identity, sort_keys=True, separators=(",", ":"))
        event_id = hashlib.sha256(f"DOI_LIFECYCLE_EVENT_V1|{encoded}".encode()).hexdigest()
        return cls(
            event_id=event_id,
            event_key=identity["event_key"],
            thesis_id=identity["thesis_id"],
            thesis_version=int(thesis_version),
            family_id=identity["family_id"],
            run_id=str(run_id).strip().upper(),
            evaluation_point=evaluation_point,
            condition_state=condition_state,
            previous_condition_state=previous_condition_state,
            evidence_cutoff_utc=evidence_cutoff_utc.astimezone(timezone.utc),
            current_spot=current_spot,
            target_spot=target_spot,
            invalidation_spot=invalidation_spot,
            horizon_end_date=horizon_end_date,
            material_change=bool(material_change),
            material_reasons=tuple(sorted({str(item).strip().upper() for item in material_reasons if str(item).strip()})),
            recorded_at=(recorded_at or datetime.now(timezone.utc)).astimezone(timezone.utc),
            metadata=dict(metadata or {}),
        )


def _relative_change(previous: float, current: float) -> float:
    return abs(current - previous) / max(abs(previous), 1e-12)


def _proximity(spot: float, level: float | None) -> float | None:
    if level is None:
        return None
    return abs(spot - level) / spot


def _dte_bucket(value: float, boundaries: Sequence[int]) -> int:
    return sum(value > boundary for boundary in boundaries)


def detect_material_change(
    *,
    previous: ContractEvidenceSnapshot | None,
    current: ContractEvidenceSnapshot,
    evaluation_point: DOIEvaluationPoint,
    policy: DynamicLifecyclePolicy = DynamicLifecyclePolicy(),
) -> MaterialChangeDecision:
    reasons: set[str] = set()
    if previous is None:
        reasons.add("INITIAL_OBSERVATION")
    else:
        if previous.contract_symbol != current.contract_symbol:
            reasons.add("CONTRACT_CHANGED")
        if previous.thesis_version != current.thesis_version:
            reasons.add("THESIS_VERSION_CHANGED")
        if _relative_change(previous.spot, current.spot) >= policy.spot_move_fraction:
            reasons.add("SPOT_MOVED")
        for name, old_level, new_level in (
            ("STRIKE_PROXIMITY_CHANGED", previous.strike, current.strike),
            ("TARGET_PROXIMITY_CHANGED", previous.target_spot, current.target_spot),
            ("INVALIDATION_PROXIMITY_CHANGED", previous.invalidation_spot, current.invalidation_spot),
        ):
            old = _proximity(previous.spot, old_level)
            new = _proximity(current.spot, new_level)
            if old is not None and new is not None and abs(new - old) >= policy.proximity_change_fraction:
                reasons.add(name)
        if previous.spread_fraction is None and current.spread_fraction is not None:
            reasons.add("TWO_SIDED_QUOTE_DEVELOPED")
        elif previous.spread_fraction is not None and current.spread_fraction is None:
            reasons.add("TWO_SIDED_QUOTE_LOST")
        elif previous.spread_fraction is not None and current.spread_fraction is not None:
            if abs(current.spread_fraction - previous.spread_fraction) >= policy.spread_change_fraction_points:
                reasons.add("SPREAD_CHANGED")
        old_volume = previous.volume or 0.0
        new_volume = current.volume or 0.0
        if (
            new_volume - old_volume >= policy.volume_growth_minimum
            and (old_volume == 0 or new_volume >= old_volume * policy.volume_growth_multiple)
        ):
            reasons.add("VOLUME_DEVELOPED")
        if previous.implied_volatility is None and current.implied_volatility is not None:
            reasons.add("IV_BECAME_AVAILABLE")
        elif previous.implied_volatility is not None and current.implied_volatility is not None:
            if abs(current.implied_volatility - previous.implied_volatility) >= policy.iv_change_points:
                reasons.add("IV_CHANGED")
        if _dte_bucket(previous.dte, policy.dte_boundaries) != _dte_bucket(current.dte, policy.dte_boundaries):
            reasons.add("DTE_BOUNDARY_CROSSED")
        if previous.entry_state is not current.entry_state:
            reasons.add("CONTRACT_ENTRY_STATE_CHANGED")
    if evaluation_point is DOIEvaluationPoint.MANUAL_REFRESH:
        reasons.add("MANUAL_REFRESH")
    return MaterialChangeDecision(
        should_revalue=bool(reasons),
        reasons=tuple(sorted(reasons)),
        evaluation_point=evaluation_point,
    )


def evaluate_thesis_condition(
    *,
    direction: str,
    current_spot: float | None,
    target_spot: float | None,
    invalidation_spot: float | None,
    horizon_end_date: date | None,
    evaluation_session: date,
    evaluation_point: DOIEvaluationPoint,
    previous_state: DOIThesisConditionState | None = None,
) -> DOIThesisConditionState:
    """Observe the thesis condition without invalidating or removing it."""

    side = str(direction).strip().upper()
    if side not in {"CALL", "PUT"}:
        raise ValueError("direction must be CALL or PUT")
    if current_spot is None or not math.isfinite(float(current_spot)) or current_spot <= 0:
        return DOIThesisConditionState.DATA_INSUFFICIENT
    spot = float(current_spot)
    target_touched = target_spot is not None and (
        spot >= target_spot if side == "CALL" else spot <= target_spot
    )
    breached = invalidation_spot is not None and (
        spot <= invalidation_spot if side == "CALL" else spot >= invalidation_spot
    )
    if target_touched:
        return DOIThesisConditionState.TARGET_TOUCHED
    if breached:
        return DOIThesisConditionState.THESIS_CONDITION_BREACHED
    if previous_state is DOIThesisConditionState.THESIS_CONDITION_BREACHED:
        return DOIThesisConditionState.THESIS_RECOVERING
    if horizon_end_date is not None and evaluation_session > horizon_end_date:
        return DOIThesisConditionState.HORIZON_ELAPSED_REASSESS
    if evaluation_point is DOIEvaluationPoint.COMPLETED_SESSION:
        return DOIThesisConditionState.THESIS_DEVELOPING
    return DOIThesisConditionState.THESIS_CONFIRMED


def classify_contract_transition(
    previous: ContractEvidenceSnapshot | None,
    current: ContractEvidenceSnapshot,
) -> ContractLifecycleTransition:
    if current.dte <= 0 or current.entry_state is ContractEntryState.CONTRACT_EXPIRED:
        state, reason = ContractTransitionState.EXPIRED, "CONTRACT_EXPIRED_RETAIN_HISTORY"
    elif previous is None:
        state, reason = ContractTransitionState.INITIAL, "FIRST_CONTRACT_OBSERVATION"
    else:
        weak = {
            ContractEntryState.CONTRACT_LIQUIDITY_DEVELOPING,
            ContractEntryState.CONTRACT_DATA_INSUFFICIENT,
            ContractEntryState.CONTRACT_REPAIR_REQUIRED,
            ContractEntryState.CONTRACT_DEGRADED,
        }
        usable = {
            ContractEntryState.CONTRACT_ENTRY_ACCEPTABLE,
            ContractEntryState.CONTRACT_LIMIT_PRICE_REQUIRED,
        }
        if previous.entry_state in weak and current.entry_state in usable:
            state, reason = ContractTransitionState.MATURED, "CONTRACT_EVIDENCE_MATURED"
        elif previous.entry_state in usable and current.entry_state in weak:
            state, reason = ContractTransitionState.DEGRADED, "CONTRACT_EVIDENCE_DEGRADED"
        else:
            state, reason = ContractTransitionState.STABLE, "CONTRACT_STATE_STABLE"
    return ContractLifecycleTransition(
        contract_symbol=current.contract_symbol,
        previous_entry_state=previous.entry_state if previous else None,
        current_entry_state=current.entry_state,
        transition_state=state,
        reason=reason,
    )


def _adverse(assessment: ContractAssessment) -> float | None:
    valuation = assessment.metadata.get("valuation", {})
    value = valuation.get("adverse_worst_return") if isinstance(valuation, Mapping) else None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _adequate_for_switch(assessment: ContractAssessment) -> bool:
    return (
        assessment.ranking_score_uncalibrated is not None
        and assessment.entry_state in {
            ContractEntryState.CONTRACT_ENTRY_ACCEPTABLE,
            ContractEntryState.CONTRACT_LIMIT_PRICE_REQUIRED,
        }
        and assessment.applicability_state in {
            ModelApplicabilityState.APPLICABLE,
            ModelApplicabilityState.DETERMINISTIC_ONLY,
        }
        and _adverse(assessment) is not None
    )


def choose_preferred_contract(
    *,
    assessments: Sequence[ContractAssessment],
    previous_contract_symbol: str | None = None,
    policy: DynamicLifecyclePolicy = DynamicLifecyclePolicy(),
) -> ContractRankingDecision:
    """Rank current exact assessments and apply deterministic hysteresis."""

    unique: dict[str, ContractAssessment] = {}
    for assessment in assessments:
        if assessment.contract_symbol in unique:
            raise ValueError("one current assessment per contract is required")
        unique[assessment.contract_symbol] = assessment
    ranked = sorted(
        (item for item in unique.values() if item.ranking_score_uncalibrated is not None),
        key=lambda item: (-float(item.ranking_score_uncalibrated), item.contract_symbol),
    )
    if not ranked:
        return ContractRankingDecision(
            selected_assessment=None,
            previous_contract_symbol=previous_contract_symbol,
            alternative_contract_symbols=tuple(sorted(unique)),
            selection_reason="NO_COMPARABLE_CONTRACT_UTILITY",
            switched_contract=False,
            hysteresis_applied=previous_contract_symbol is not None,
            hysteresis_suppressed_switch=False,
            utility_margin=None,
            economics_recomputed=False,
        )

    best = ranked[0]
    current = unique.get(previous_contract_symbol) if previous_contract_symbol else None
    selected = best
    reason = "INITIAL_UNCALIBRATED_UTILITY_RANK"
    switched = False
    applied = current is not None
    suppressed = False
    margin: float | None = None

    if previous_contract_symbol:
        if current is None:
            reason = "SUPERSEDE_CONTRACT_OUTSIDE_CURRENT_FAMILY"
            switched = best.contract_symbol != previous_contract_symbol
        elif best.contract_symbol == current.contract_symbol:
            selected = current
            reason = "RETAIN_CURRENT_TOP_RANK"
        elif current.ranking_score_uncalibrated is None:
            if _adequate_for_switch(best):
                reason = "SUPERSEDE_CURRENT_NOT_COMPARABLE"
                switched = True
            else:
                selected = current
                reason = "RETAIN_CURRENT_ALTERNATIVE_QUALITY_INSUFFICIENT"
                suppressed = True
        else:
            margin = float(best.ranking_score_uncalibrated) - float(current.ranking_score_uncalibrated)
            stress_preferable = (
                _adverse(best) is not None
                and _adverse(current) is not None
                and float(_adverse(best)) >= float(_adverse(current))
            )
            threshold = max(
                policy.minimum_utility_margin,
                policy.relative_utility_margin
                * abs(float(current.ranking_score_uncalibrated)),
            )
            if margin >= threshold and _adequate_for_switch(best) and stress_preferable:
                reason = "SUPERSEDE_UTILITY_MARGIN_AND_STRESS"
                switched = True
            else:
                selected = current
                reason = "RETAIN_CURRENT_HYSTERESIS"
                suppressed = True

    alternatives = tuple(item.contract_symbol for item in ranked if item.contract_symbol != selected.contract_symbol)
    alternatives += tuple(
        symbol for symbol in sorted(unique)
        if symbol != selected.contract_symbol and symbol not in alternatives
    )
    return ContractRankingDecision(
        selected_assessment=selected,
        previous_contract_symbol=previous_contract_symbol,
        alternative_contract_symbols=alternatives,
        selection_reason=reason,
        switched_contract=switched,
        hysteresis_applied=applied,
        hysteresis_suppressed_switch=suppressed,
        utility_margin=margin,
        economics_recomputed=True,
    )


__all__ = [
    "DOI_LIFECYCLE_DOMAIN_VERSION", "DOI_MATERIAL_CHANGE_POLICY_VERSION",
    "DOI_HYSTERESIS_POLICY_VERSION", "DOIEvaluationPoint",
    "DOIThesisConditionState", "ContractTransitionState",
    "DynamicLifecyclePolicy", "ContractEvidenceSnapshot",
    "MaterialChangeDecision", "ContractLifecycleTransition",
    "ContractRankingDecision", "DOILifecycleEvent", "detect_material_change",
    "evaluate_thesis_condition", "classify_contract_transition",
    "choose_preferred_contract",
]
