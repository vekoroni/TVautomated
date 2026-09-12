"""DOI-6 application service for lifecycle observation and re-ranking.

The service consumes DOI-5 assessments, records append-only lifecycle facts
and applies deterministic hysteresis.  It performs no provider calls and has
no thesis, capital or execution authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any

from domain.contract_family_generation import GeneratedContractFamily
from domain.dynamic_options_intelligence import (
    PreferredContractDecision,
)
from domain.dynamic_options_lifecycle import (
    DOI_LIFECYCLE_DOMAIN_VERSION,
    ContractEvidenceSnapshot,
    ContractLifecycleTransition,
    ContractRankingDecision,
    ContractTransitionState,
    DOIEvaluationPoint,
    DOILifecycleEvent,
    DOIThesisConditionState,
    DynamicLifecyclePolicy,
    choose_preferred_contract,
    classify_contract_transition,
    detect_material_change,
    evaluate_thesis_condition,
)

from .dynamic_options_valuation import ContractFamilyValuationResult
from .option_liquidity_lifecycle import (
    ContractObservation,
    OptionLiquidityLifecycleStore,
)


DOI_DYNAMIC_LIFECYCLE_SERVICE_VERSION = "doi-dynamic-lifecycle-service-v1"


@dataclass(frozen=True, slots=True)
class DynamicLifecycleSummary:
    assessed_contracts: int
    material_contracts: int
    matured_contracts: int
    degraded_contracts: int
    superseded_contracts: int
    expired_contracts: int
    stable_contracts: int
    initial_contracts: int
    preferred_decision_recorded: bool
    contract_switched: bool
    hysteresis_suppressed_switch: bool
    options_observation_refreshed: bool
    retained_opportunities: int = 1
    deleted_opportunities: int = 0
    physical_fetch_count: int = 0

    def __post_init__(self) -> None:
        transitions = (
            self.matured_contracts + self.degraded_contracts
            + self.superseded_contracts + self.expired_contracts + self.stable_contracts
            + self.initial_contracts
        )
        if transitions != self.assessed_contracts:
            raise ValueError("contract lifecycle population does not reconcile")
        if self.retained_opportunities != 1 or self.deleted_opportunities != 0:
            raise ValueError("DOI-6 cannot remove an opportunity")
        if self.physical_fetch_count != 0:
            raise ValueError("DOI-6 cannot acquire provider data")

    def to_dict(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class DynamicLifecycleEvaluationResult:
    lifecycle_event: DOILifecycleEvent
    event_reused: bool
    transitions: tuple[ContractLifecycleTransition, ...]
    ranking: ContractRankingDecision | None
    preferred_decision: PreferredContractDecision | None
    preferred_decision_reused: bool
    summary: DynamicLifecycleSummary
    service_version: str = DOI_DYNAMIC_LIFECYCLE_SERVICE_VERSION


def _snapshot(
    *,
    assessment,
    observation: ContractObservation,
    generated_family: GeneratedContractFamily,
) -> ContractEvidenceSnapshot:
    valuation = assessment.metadata.get("valuation", {})
    adverse = valuation.get("adverse_worst_return") if isinstance(valuation, dict) else None
    thesis = generated_family.family.thesis
    return ContractEvidenceSnapshot(
        contract_symbol=assessment.contract_symbol,
        assessment_id=assessment.assessment_id,
        observation_id=assessment.observation_id,
        evidence_cutoff_utc=assessment.evidence_cutoff_utc,
        spot=observation.spot,
        strike=observation.strike,
        dte=observation.dte,
        bid=observation.bid,
        ask=observation.ask,
        spread_fraction=observation.spread_pct,
        volume=observation.volume,
        implied_volatility=observation.iv,
        entry_state=assessment.entry_state,
        applicability_state=assessment.applicability_state,
        ranking_score_uncalibrated=assessment.ranking_score_uncalibrated,
        adverse_worst_return=adverse,
        target_spot=thesis.target_spot,
        invalidation_spot=thesis.invalidation_spot,
        thesis_version=thesis.thesis_version,
    )


class DynamicOptionsLifecycleService:
    def __init__(
        self,
        store: OptionLiquidityLifecycleStore,
        *,
        policy: DynamicLifecyclePolicy | None = None,
    ) -> None:
        self.store = store
        self.policy = policy or DynamicLifecyclePolicy()

    def evaluate_completed_session(
        self,
        *,
        generated_family: GeneratedContractFamily,
        valuation_result: ContractFamilyValuationResult,
        evaluation_session: date,
        horizon_end_date: date | None,
        event_key: str,
        current_spot: float | None = None,
    ) -> DynamicLifecycleEvaluationResult:
        return self.evaluate(
            generated_family=generated_family,
            valuation_result=valuation_result,
            evaluation_session=evaluation_session,
            horizon_end_date=horizon_end_date,
            event_key=event_key,
            evaluation_point=DOIEvaluationPoint.COMPLETED_SESSION,
            current_spot=current_spot,
            options_observation_refreshed=True,
        )

    def evaluate_morning_gate(
        self,
        *,
        generated_family: GeneratedContractFamily,
        valuation_result: ContractFamilyValuationResult,
        evaluation_session: date,
        horizon_end_date: date | None,
        event_key: str,
        current_spot: float | None,
        options_observation_refreshed: bool,
    ) -> DynamicLifecycleEvaluationResult:
        return self.evaluate(
            generated_family=generated_family,
            valuation_result=valuation_result,
            evaluation_session=evaluation_session,
            horizon_end_date=horizon_end_date,
            event_key=event_key,
            evaluation_point=DOIEvaluationPoint.MORNING_GATE,
            current_spot=current_spot,
            options_observation_refreshed=options_observation_refreshed,
        )

    def evaluate(
        self,
        *,
        generated_family: GeneratedContractFamily,
        valuation_result: ContractFamilyValuationResult,
        evaluation_session: date,
        horizon_end_date: date | None,
        event_key: str,
        evaluation_point: DOIEvaluationPoint,
        current_spot: float | None,
        options_observation_refreshed: bool,
    ) -> DynamicLifecycleEvaluationResult:
        family = generated_family.family
        thesis = family.thesis
        if valuation_result.family_id != family.family_id:
            raise ValueError("valuation result conflicts with generated family")
        existing_event = self.store.doi_lifecycle_event(
            thesis_id=thesis.thesis_id, event_key=event_key
        )
        current_assessments = tuple(item.assessment for item in valuation_result.results)
        if any(item.family_id != family.family_id for item in current_assessments):
            raise ValueError("all assessments must belong to the current family")
        if options_observation_refreshed:
            for assessment in current_assessments:
                if assessment.metadata.get("contract_symbol_exact") != assessment.contract_symbol:
                    raise ValueError("preferred contract economics are not exact-contract bound")
                if not isinstance(assessment.metadata.get("valuation"), dict):
                    raise ValueError("current exact-contract valuation metadata is missing")

        previous_event = self.store.latest_doi_lifecycle_event(thesis.thesis_id)
        replaying_event = existing_event is not None
        current_snapshots: list[ContractEvidenceSnapshot] = []
        transitions: list[ContractLifecycleTransition] = []
        material_reasons: set[str] = set()
        material_contracts = 0
        observed_spots: list[float] = []

        for item in valuation_result.results:
            observation = self.store.contract_observation(item.assessment.observation_id)
            if observation is None:
                raise ValueError("current assessment observation is missing")
            observed_spots.append(observation.spot)
            current = _snapshot(
                assessment=item.assessment,
                observation=observation,
                generated_family=generated_family,
            )
            prior_assessment = self.store.previous_contract_assessment(
                thesis_id=thesis.thesis_id,
                contract_symbol=item.assessment.contract_symbol,
                exclude_assessment_id=item.assessment.assessment_id,
            )
            previous = None
            if prior_assessment is not None:
                prior_observation = self.store.contract_observation(
                    prior_assessment.observation_id
                )
                if prior_observation is None:
                    raise ValueError("prior assessment observation is missing")
                previous = _snapshot(
                    assessment=prior_assessment,
                    observation=prior_observation,
                    generated_family=generated_family,
                )
            material = detect_material_change(
                previous=previous,
                current=current,
                evaluation_point=evaluation_point,
                policy=self.policy,
            )
            if material.should_revalue:
                material_contracts += 1
                material_reasons.update(material.reasons)
            transitions.append(classify_contract_transition(previous, current))
            current_snapshots.append(current)

        resolved_spot = current_spot
        if resolved_spot is None and observed_spots:
            resolved_spot = observed_spots[0]
        if (
            previous_event is not None
            and previous_event.current_spot is not None
            and resolved_spot is not None
            and abs(resolved_spot - previous_event.current_spot)
            / max(abs(previous_event.current_spot), 1e-12)
            >= self.policy.spot_move_fraction
        ):
            material_reasons.add("UNDERLYING_SPOT_MOVED")
        if evaluation_point is DOIEvaluationPoint.MANUAL_REFRESH:
            material_reasons.add("MANUAL_REFRESH")
        if replaying_event:
            material_reasons = set(existing_event.material_reasons)

        condition = evaluate_thesis_condition(
            direction=thesis.governed_direction,
            current_spot=resolved_spot,
            target_spot=thesis.target_spot,
            invalidation_spot=thesis.invalidation_spot,
            horizon_end_date=horizon_end_date,
            evaluation_session=evaluation_session,
            evaluation_point=evaluation_point,
            previous_state=(
                previous_event.previous_condition_state
                if replaying_event else (
                    previous_event.condition_state if previous_event else None
                )
            ),
        )
        if replaying_event:
            condition = existing_event.condition_state
        evidence_cutoff = max(
            [family.evidence_cutoff_utc]
            + [item.evidence_cutoff_utc for item in current_assessments]
        )
        event = DOILifecycleEvent.create(
            event_key=event_key,
            thesis_id=thesis.thesis_id,
            thesis_version=thesis.thesis_version,
            family_id=family.family_id,
            run_id=family.run_id,
            evaluation_point=evaluation_point,
            condition_state=condition,
            previous_condition_state=(
                existing_event.previous_condition_state
                if replaying_event else (
                    previous_event.condition_state if previous_event else None
                )
            ),
            evidence_cutoff_utc=evidence_cutoff,
            current_spot=resolved_spot,
            target_spot=thesis.target_spot,
            invalidation_spot=thesis.invalidation_spot,
            horizon_end_date=horizon_end_date,
            material_change=bool(material_reasons),
            material_reasons=tuple(material_reasons),
            metadata={
                "lifecycle_domain_version": DOI_LIFECYCLE_DOMAIN_VERSION,
                "material_policy_version": self.policy.material_policy_version,
                "hysteresis_policy_version": self.policy.hysteresis_policy_version,
                "hysteresis_approval_id": self.policy.hysteresis_approval_id,
                "options_observation_refreshed": bool(options_observation_refreshed),
                "assessed_contracts": len(current_assessments),
                "direction_immutable": thesis.governed_direction,
                "human_execution_only": True,
            },
        )
        if existing_event is not None:
            if (
                existing_event.family_id != family.family_id
                or existing_event.run_id != family.run_id
                or existing_event.evaluation_point is not evaluation_point
            ):
                raise ValueError("existing lifecycle event conflicts with replay scope")
            event_record = existing_event
            event_reused = True
        else:
            persisted_event = self.store.record_doi_lifecycle_event(event)
            event_record = persisted_event.record
            event_reused = persisted_event.reused_existing

        previous_preferred = self.store.latest_preferred_contract(thesis.thesis_id)
        event_preferred = self.store.preferred_contract_decision(
            thesis_id=thesis.thesis_id, event_key=event_key
        )
        ranking: ContractRankingDecision | None = None
        preferred: PreferredContractDecision | None = None
        preferred_reused = False
        if (
            options_observation_refreshed
            and event_preferred is not None
        ):
            preferred = event_preferred
            preferred_reused = True
            ranking = choose_preferred_contract(
                assessments=current_assessments,
                previous_contract_symbol=event_preferred.previous_contract_symbol,
                policy=self.policy,
            )
        elif (
            options_observation_refreshed
            and not (
                existing_event is not None
                and previous_preferred is not None
                and previous_preferred.event_key != event.event_key
            )
        ):
            ranking = choose_preferred_contract(
                assessments=current_assessments,
                previous_contract_symbol=(
                    previous_preferred.selected_contract_symbol
                    if previous_preferred else None
                ),
                policy=self.policy,
            )
            if ranking.selected_assessment is not None:
                selected = ranking.selected_assessment
                if selected.assessment_id not in {
                    item.assessment.assessment_id for item in valuation_result.results
                }:
                    raise ValueError("preferred contract lacks current exact economics")
                if selected.metadata.get("contract_symbol_exact") != selected.contract_symbol:
                    raise ValueError("preferred contract economics are not exact-contract bound")
                preferred_input = PreferredContractDecision.create(
                    event_key=event.event_key,
                    family_id=family.family_id,
                    thesis_id=thesis.thesis_id,
                    run_id=family.run_id,
                    selected_contract_symbol=selected.contract_symbol,
                    selected_assessment_id=selected.assessment_id,
                    selection_reason=ranking.selection_reason,
                    selected_at=event.recorded_at,
                    alternative_contract_symbols=ranking.alternative_contract_symbols,
                    previous_contract_symbol=(
                        previous_preferred.selected_contract_symbol
                        if previous_preferred else None
                    ),
                    prior_decision_id=(
                        previous_preferred.decision_id if previous_preferred else None
                    ),
                    utility_margin=ranking.utility_margin,
                    hysteresis_applied=ranking.hysteresis_applied,
                    economics_recomputed=ranking.economics_recomputed,
                    metadata={
                        "lifecycle_event_id": event.event_id,
                        "hysteresis_suppressed_switch": (
                            ranking.hysteresis_suppressed_switch
                        ),
                        "options_observation_refreshed": True,
                        "selected_observation_id": selected.observation_id,
                        "selected_calculation_version": selected.calculation_version,
                        "utility_is_probability": False,
                        "human_execution_only": True,
                    },
                )
                persisted_preferred = self.store.record_preferred_contract_decision(
                    preferred_input,
                    expected_version=(
                        previous_preferred.decision_version
                        if previous_preferred else None
                    ),
                )
                preferred = persisted_preferred.record
                preferred_reused = persisted_preferred.reused_existing

        counts = {
            state: sum(item.transition_state is state for item in transitions)
            for state in ContractTransitionState
        }
        summary = DynamicLifecycleSummary(
            assessed_contracts=len(current_assessments),
            material_contracts=material_contracts,
            matured_contracts=counts[ContractTransitionState.MATURED],
            degraded_contracts=counts[ContractTransitionState.DEGRADED],
            superseded_contracts=counts[ContractTransitionState.SUPERSEDED],
            expired_contracts=counts[ContractTransitionState.EXPIRED],
            stable_contracts=counts[ContractTransitionState.STABLE],
            initial_contracts=counts[ContractTransitionState.INITIAL],
            preferred_decision_recorded=preferred is not None,
            contract_switched=bool(ranking and ranking.switched_contract),
            hysteresis_suppressed_switch=bool(
                ranking and ranking.hysteresis_suppressed_switch
            ),
            options_observation_refreshed=bool(options_observation_refreshed),
        )
        return DynamicLifecycleEvaluationResult(
            lifecycle_event=event_record,
            event_reused=event_reused,
            transitions=tuple(transitions),
            ranking=ranking,
            preferred_decision=preferred,
            preferred_decision_reused=preferred_reused,
            summary=summary,
        )


__all__ = [
    "DOI_DYNAMIC_LIFECYCLE_SERVICE_VERSION", "DynamicLifecycleSummary",
    "DynamicLifecycleEvaluationResult", "DynamicOptionsLifecycleService",
]
