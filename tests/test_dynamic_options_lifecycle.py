from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

import pandas as pd

from canonical_data.contracts import CompletenessStatus, DataScope, DatasetRecord, DatasetType
from canonical_data.dynamic_options_bridge import GovernedOptionObservation
from canonical_data.dynamic_options_family import ThesisConditionedContractFamilyGenerator
from canonical_data.dynamic_options_lifecycle import DynamicOptionsLifecycleService
from canonical_data.dynamic_options_valuation import DeterministicContractValuationService
from canonical_data.option_liquidity_lifecycle import MonitorState, OptionLiquidityLifecycleStore, ThesisState
from canonical_data.registry import CanonicalRegistry
from domain.dynamic_options_intelligence import (
    ContractAssessment, ContractEntryState, ModelApplicabilityState,
    ObservationAcquisitionDecision, OptionObservationKind, UnderlyingThesisRef,
)
from domain.dynamic_options_lifecycle import (
    ContractEvidenceSnapshot, ContractTransitionState, DOIEvaluationPoint,
    DOIThesisConditionState, DynamicLifecyclePolicy, choose_preferred_contract,
    classify_contract_transition, detect_material_change, evaluate_thesis_condition,
)


UTC = timezone.utc
RUN_ID = "20260910_210000"
CUTOFF = datetime(2026, 9, 10, 20, 0, tzinfo=UTC)
SESSION = date(2026, 9, 10)


def _assessment(
    symbol: str,
    utility: float | None,
    adverse: float | None,
    *,
    entry_state: ContractEntryState = ContractEntryState.CONTRACT_LIMIT_PRICE_REQUIRED,
    applicability: ModelApplicabilityState = ModelApplicabilityState.DETERMINISTIC_ONLY,
) -> ContractAssessment:
    return ContractAssessment.create(
        family_id="family", thesis_id="thesis", run_id=RUN_ID,
        contract_symbol=symbol, observation_id=f"obs-{symbol}",
        entry_state=entry_state, applicability_state=applicability,
        evidence_cutoff_utc=CUTOFF, input_dataset_ids=("dataset",),
        calculation_version="calc-v1", feature_version="features-v1",
        model_version="model-v1", ranking_score_uncalibrated=utility,
        metadata={
            "contract_symbol_exact": symbol,
            "valuation": {"adverse_worst_return": adverse},
        },
    )


def _snapshot(**overrides) -> ContractEvidenceSnapshot:
    values = dict(
        contract_symbol="ABC261016C00100000", assessment_id="assessment",
        observation_id="observation", evidence_cutoff_utc=CUTOFF,
        spot=100.0, strike=100.0, dte=36.0, bid=2.0, ask=2.2,
        spread_fraction=0.095, volume=10.0, implied_volatility=0.40,
        entry_state=ContractEntryState.CONTRACT_LIMIT_PRICE_REQUIRED,
        applicability_state=ModelApplicabilityState.DETERMINISTIC_ONLY,
        ranking_score_uncalibrated=0.4, adverse_worst_return=-0.5,
        target_spot=110.0, invalidation_spot=95.0, thesis_version=1,
    )
    values.update(overrides)
    return ContractEvidenceSnapshot(**values)


class DynamicLifecycleDomainTests(unittest.TestCase):
    def test_initial_and_manual_refresh_are_material(self) -> None:
        initial = detect_material_change(
            previous=None, current=_snapshot(),
            evaluation_point=DOIEvaluationPoint.COMPLETED_SESSION,
        )
        manual = detect_material_change(
            previous=_snapshot(), current=_snapshot(),
            evaluation_point=DOIEvaluationPoint.MANUAL_REFRESH,
        )
        self.assertEqual(initial.reasons, ("INITIAL_OBSERVATION",))
        self.assertEqual(manual.reasons, ("MANUAL_REFRESH",))
        self.assertTrue(initial.retain_opportunity and manual.retain_opportunity)

    def test_material_market_changes_are_detected_without_authority(self) -> None:
        previous = _snapshot(dte=36, volume=10, spread_fraction=0.25, implied_volatility=0.30)
        current = _snapshot(
            spot=103, dte=34, volume=30, spread_fraction=0.08,
            implied_volatility=0.38, thesis_version=2,
        )
        result = detect_material_change(
            previous=previous, current=current,
            evaluation_point=DOIEvaluationPoint.MORNING_GATE,
        )
        self.assertTrue(result.should_revalue)
        for reason in (
            "SPOT_MOVED", "SPREAD_CHANGED", "VOLUME_DEVELOPED", "IV_CHANGED",
            "DTE_BOUNDARY_CROSSED", "THESIS_VERSION_CHANGED",
        ):
            self.assertIn(reason, result.reasons)
        self.assertEqual(result.decision_authority, "NONE")

    def test_non_material_observation_does_not_force_revaluation(self) -> None:
        result = detect_material_change(
            previous=_snapshot(), current=_snapshot(evidence_cutoff_utc=CUTOFF + timedelta(minutes=5)),
            evaluation_point=DOIEvaluationPoint.MORNING_GATE,
        )
        self.assertFalse(result.should_revalue)
        self.assertEqual(result.reasons, ())

    def test_call_and_put_breach_recovery_are_symmetric(self) -> None:
        cases = (("CALL", 94.0, 96.0, 110.0, 95.0), ("PUT", 106.0, 104.0, 90.0, 105.0))
        for side, breach_spot, recover_spot, target, invalidation in cases:
            breached = evaluate_thesis_condition(
                direction=side, current_spot=breach_spot, target_spot=target,
                invalidation_spot=invalidation, horizon_end_date=date(2026, 9, 30),
                evaluation_session=SESSION,
                evaluation_point=DOIEvaluationPoint.MORNING_GATE,
            )
            recovered = evaluate_thesis_condition(
                direction=side, current_spot=recover_spot, target_spot=target,
                invalidation_spot=invalidation, horizon_end_date=date(2026, 9, 30),
                evaluation_session=SESSION,
                evaluation_point=DOIEvaluationPoint.MORNING_GATE,
                previous_state=breached,
            )
            self.assertIs(breached, DOIThesisConditionState.THESIS_CONDITION_BREACHED)
            self.assertIs(recovered, DOIThesisConditionState.THESIS_RECOVERING)

    def test_elapsed_and_target_are_visible_not_terminal_deletions(self) -> None:
        elapsed = evaluate_thesis_condition(
            direction="CALL", current_spot=101, target_spot=110,
            invalidation_spot=95, horizon_end_date=date(2026, 9, 9),
            evaluation_session=SESSION,
            evaluation_point=DOIEvaluationPoint.MORNING_GATE,
        )
        target = evaluate_thesis_condition(
            direction="PUT", current_spot=89, target_spot=90,
            invalidation_spot=105, horizon_end_date=date(2026, 9, 30),
            evaluation_session=SESSION,
            evaluation_point=DOIEvaluationPoint.MORNING_GATE,
        )
        self.assertIs(elapsed, DOIThesisConditionState.HORIZON_ELAPSED_REASSESS)
        self.assertIs(target, DOIThesisConditionState.TARGET_TOUCHED)

    def test_contract_maturation_degradation_and_expiry(self) -> None:
        developing = _snapshot(entry_state=ContractEntryState.CONTRACT_LIQUIDITY_DEVELOPING)
        acceptable = _snapshot(entry_state=ContractEntryState.CONTRACT_LIMIT_PRICE_REQUIRED)
        matured = classify_contract_transition(developing, acceptable)
        degraded = classify_contract_transition(acceptable, developing)
        expired = classify_contract_transition(acceptable, _snapshot(dte=0))
        self.assertIs(matured.transition_state, ContractTransitionState.MATURED)
        self.assertIs(degraded.transition_state, ContractTransitionState.DEGRADED)
        self.assertIs(expired.transition_state, ContractTransitionState.EXPIRED)
        self.assertTrue(matured.retain_opportunity and degraded.retain_opportunity)
        with self.assertRaisesRegex(ValueError, "cannot remove"):
            replace(matured, retain_opportunity=False)

    def test_hysteresis_suppresses_small_improvement(self) -> None:
        current = _assessment("ABC261016C00100000", 0.50, -0.40)
        alternative = _assessment("ABC261016C00105000", 0.55, -0.35)
        result = choose_preferred_contract(
            assessments=(current, alternative),
            previous_contract_symbol=current.contract_symbol,
            policy=DynamicLifecyclePolicy(minimum_utility_margin=0.10),
        )
        self.assertEqual(result.selected_assessment.contract_symbol, current.contract_symbol)
        self.assertTrue(result.hysteresis_suppressed_switch)
        self.assertFalse(result.switched_contract)

    def test_hysteresis_switch_requires_margin_quality_and_stress(self) -> None:
        current = _assessment("ABC261016C00100000", 0.50, -0.40)
        alternative = _assessment("ABC261016C00105000", 0.75, -0.30)
        result = choose_preferred_contract(
            assessments=(current, alternative),
            previous_contract_symbol=current.contract_symbol,
        )
        self.assertEqual(result.selected_assessment.contract_symbol, alternative.contract_symbol)
        self.assertTrue(result.switched_contract)
        self.assertTrue(result.economics_recomputed)
        self.assertEqual(result.execution_authority, "HUMAN_ONLY")

    def test_hysteresis_uses_greater_absolute_or_relative_margin(self) -> None:
        current = _assessment("ABC261016C00100000", 2.00, -0.40)
        close = _assessment("ABC261016C00105000", 2.15, -0.35)
        better = _assessment("ABC261016C00110000", 2.21, -0.30)
        retained = choose_preferred_contract(
            assessments=(current, close),
            previous_contract_symbol=current.contract_symbol,
        )
        switched = choose_preferred_contract(
            assessments=(current, better),
            previous_contract_symbol=current.contract_symbol,
        )
        self.assertEqual(retained.selected_assessment.contract_symbol, current.contract_symbol)
        self.assertTrue(retained.hysteresis_suppressed_switch)
        self.assertEqual(switched.selected_assessment.contract_symbol, better.contract_symbol)
        self.assertTrue(switched.switched_contract)

    def test_better_utility_with_worse_stress_is_retained_for_human_review(self) -> None:
        current = _assessment("ABC261016P00100000", 0.40, -0.30)
        alternative = _assessment("ABC261016P00095000", 0.80, -0.60)
        result = choose_preferred_contract(
            assessments=(current, alternative),
            previous_contract_symbol=current.contract_symbol,
        )
        self.assertEqual(result.selected_assessment.contract_symbol, current.contract_symbol)
        self.assertTrue(result.hysteresis_suppressed_switch)

    def test_no_utility_keeps_every_contract_visible(self) -> None:
        items = (
            _assessment("ABC261016C00100000", None, None, entry_state=ContractEntryState.CONTRACT_DATA_INSUFFICIENT, applicability=ModelApplicabilityState.DATA_INSUFFICIENT),
            _assessment("ABC261016C00105000", None, None, entry_state=ContractEntryState.CONTRACT_DATA_INSUFFICIENT, applicability=ModelApplicabilityState.DATA_INSUFFICIENT),
        )
        result = choose_preferred_contract(assessments=items)
        self.assertIsNone(result.selected_assessment)
        self.assertEqual(set(result.alternative_contract_symbols), {item.contract_symbol for item in items})
        self.assertTrue(result.retain_opportunity)


class DynamicLifecyclePersistenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.registry = CanonicalRegistry(self.root / "control.sqlite")
        self.registry.initialise()
        self.registry.register_run(RUN_ID, "EVENING", SESSION)
        self.store = OptionLiquidityLifecycleStore(self.registry)
        self.store.initialise()
        self.thesis = UnderlyingThesisRef(
            thesis_id="ABC-CALL-DOI6", thesis_version=1, ticker="ABC",
            governed_direction="CALL", origin_spot=100,
            origin_timestamp_utc=CUTOFF - timedelta(hours=1),
            target_spot=110, invalidation_spot=95, planned_hold_sessions=10,
            planned_hold_source="HORIZON_ROUTER", evidence_cutoff_utc=CUTOFF,
        )
        self.store.record_thesis_event(
            thesis_id=self.thesis.thesis_id, event_key="ORIGIN", run_id=RUN_ID,
            ticker="ABC", direction="CALL", thesis_state=ThesisState.ACTIVE,
            monitor_state=MonitorState.ACTIVE, reason_code="GOVERNED_THESIS",
            structural_target=110, invalidation_spot=95,
            horizon_end_date=date(2026, 9, 30),
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    @staticmethod
    def _symbol(strike: float) -> str:
        return f"ABC261016C{int(strike * 1000):08d}"

    def _build(self, cutoff: datetime = CUTOFF):
        quote_text = cutoff.isoformat().replace("+00:00", "Z")
        rows = [
            {
                "symbol": self._symbol(100), "right": "C", "strike": 100,
                "expiration_date": "2026-10-16", "underlying_price": 100,
                "bid": 4.8, "ask": 5.0, "bid_size": 5, "ask_size": 5,
                "volume": 100, "open_interest": 100, "iv": 0.35, "delta": 0.5,
                "quote_timestamp_utc": quote_text,
            },
            {
                "symbol": self._symbol(105), "right": "C", "strike": 105,
                "expiration_date": "2026-10-16", "underlying_price": 100,
                "bid": 2.0, "ask": 2.2, "bid_size": 5, "ask_size": 5,
                "volume": 30, "open_interest": 10, "iv": 0.38, "delta": 0.35,
                "quote_timestamp_utc": quote_text,
            },
        ]
        encoded = json.dumps(rows, sort_keys=True, separators=(",", ":")).encode()
        path = self.root / f"chain-{cutoff.strftime('%Y%m%d%H%M%S')}.json"
        path.write_bytes(encoded)
        dataset_id = hashlib.sha256(encoded).hexdigest()
        self.registry.register_dataset(DatasetRecord(
            dataset_id=dataset_id, dataset_type=DatasetType.OPTION_CHAIN,
            instrument_id="ABC", session_date=cutoff.date(),
            scope=DataScope(start_date=cutoff.date(), end_date=cutoff.date(), dte_min=1, dte_max=90, sides=("CALL", "PUT")),
            provider="MARKETDATA", content_hash=dataset_id,
            completeness_status=CompletenessStatus.COMPLETE, storage_uri=str(path),
            observed_at=cutoff, as_of=cutoff,
            adjustment_convention="RAW_OPTION_CONTRACT", schema_version="option_chain_v2",
            source_run_id=RUN_ID,
        ))
        observation = GovernedOptionObservation(
            ticker="ABC", observation_kind=OptionObservationKind.COMPLETED_SESSION,
            dataset_id=dataset_id, provider="MARKETDATA", as_of_utc=cutoff,
            frame=pd.DataFrame(rows), resolution="CANONICAL_REUSE",
            acquisition=ObservationAcquisitionDecision(False, "REUSE_CANONICAL_EVIDENCE"),
            physical_fetch_count=0,
        )
        family = ThesisConditionedContractFamilyGenerator(self.store).generate(
            thesis=self.thesis, observation=observation, run_id=RUN_ID,
        )
        valuation = DeterministicContractValuationService(
            self.store, risk_free_rate=0.04, dividend_yield=0.01,
        ).evaluate_family(generated_family=family, observation=observation)
        return family, valuation

    def test_completed_session_persists_event_and_exact_preferred_decision(self) -> None:
        family, valuation = self._build()
        result = DynamicOptionsLifecycleService(self.store).evaluate_completed_session(
            generated_family=family, valuation_result=valuation,
            evaluation_session=SESSION, horizon_end_date=date(2026, 9, 30),
            event_key="EOD-1", current_spot=100,
        )
        self.assertEqual(result.summary.assessed_contracts, 2)
        self.assertEqual(result.summary.initial_contracts, 2)
        self.assertIs(result.lifecycle_event.condition_state, DOIThesisConditionState.THESIS_DEVELOPING)
        self.assertIsNotNone(result.preferred_decision)
        selected = self.store.contract_assessment(result.preferred_decision.selected_assessment_id)
        self.assertEqual(selected.contract_symbol, result.preferred_decision.selected_contract_symbol)
        self.assertEqual(result.summary.deleted_opportunities, 0)

    def test_restart_is_idempotent_and_history_is_append_only(self) -> None:
        family, valuation = self._build()
        service = DynamicOptionsLifecycleService(self.store)
        kwargs = dict(
            generated_family=family, valuation_result=valuation,
            evaluation_session=SESSION, horizon_end_date=date(2026, 9, 30),
            event_key="EOD-REPLAY", current_spot=100,
        )
        first = service.evaluate_completed_session(**kwargs)
        second = service.evaluate_completed_session(**kwargs)
        self.assertEqual(first.lifecycle_event.event_id, second.lifecycle_event.event_id)
        self.assertEqual(first.preferred_decision.decision_id, second.preferred_decision.decision_id)
        self.assertTrue(second.event_reused)
        self.assertTrue(second.preferred_decision_reused)
        with self.registry.connection() as connection:
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    "UPDATE doi_lifecycle_events SET condition_state='DATA_INSUFFICIENT' WHERE event_id=?",
                    (first.lifecycle_event.event_id,),
                )

    def test_morning_breach_and_recovery_need_no_new_option_quote(self) -> None:
        family, valuation = self._build()
        service = DynamicOptionsLifecycleService(self.store)
        service.evaluate_completed_session(
            generated_family=family, valuation_result=valuation,
            evaluation_session=SESSION, horizon_end_date=date(2026, 9, 30),
            event_key="EOD-BASE", current_spot=100,
        )
        breach = service.evaluate_morning_gate(
            generated_family=family, valuation_result=valuation,
            evaluation_session=date(2026, 9, 11), horizon_end_date=date(2026, 9, 30),
            event_key="MORNING-BREACH", current_spot=94,
            options_observation_refreshed=False,
        )
        recovery = service.evaluate_morning_gate(
            generated_family=family, valuation_result=valuation,
            evaluation_session=date(2026, 9, 14), horizon_end_date=date(2026, 9, 30),
            event_key="MORNING-RECOVERY", current_spot=96,
            options_observation_refreshed=False,
        )
        self.assertIs(breach.lifecycle_event.condition_state, DOIThesisConditionState.THESIS_CONDITION_BREACHED)
        self.assertIs(recovery.lifecycle_event.condition_state, DOIThesisConditionState.THESIS_RECOVERING)
        self.assertIsNone(breach.preferred_decision)
        self.assertTrue(breach.lifecycle_event.retain_opportunity)
        self.assertFalse(breach.summary.options_observation_refreshed)

    def test_schema_round_trip_and_authority_are_fixed(self) -> None:
        family, valuation = self._build()
        result = DynamicOptionsLifecycleService(self.store).evaluate_completed_session(
            generated_family=family, valuation_result=valuation,
            evaluation_session=SESSION, horizon_end_date=date(2026, 9, 30),
            event_key="ROUNDTRIP", current_spot=100,
        )
        loaded = self.store.latest_doi_lifecycle_event(self.thesis.thesis_id)
        self.assertEqual(loaded.event_id, result.lifecycle_event.event_id)
        self.assertEqual(loaded.decision_authority, "NONE")
        self.assertFalse(loaded.can_change_direction)
        self.assertFalse(loaded.can_grant_capital)
        self.assertEqual(len(self.store.doi_lifecycle_events(self.thesis.thesis_id)), 1)

    def test_better_exact_contract_is_superseded_append_only(self) -> None:
        family, valuation = self._build()
        service = DynamicOptionsLifecycleService(self.store)
        first = service.evaluate_completed_session(
            generated_family=family, valuation_result=valuation,
            evaluation_session=SESSION, horizon_end_date=date(2026, 9, 30),
            event_key="EOD-FIRST", current_spot=100,
        )
        prior_symbol = first.preferred_decision.selected_contract_symbol

        later_family, later_valuation = self._build(CUTOFF + timedelta(days=1))
        replacement_symbol = next(
            item.assessment.contract_symbol for item in later_valuation.results
            if item.assessment.contract_symbol != prior_symbol
        )
        revised_results = []
        for item in later_valuation.results:
            is_replacement = item.assessment.contract_symbol == replacement_symbol
            revised = ContractAssessment.create(
                family_id=item.assessment.family_id,
                thesis_id=item.assessment.thesis_id,
                run_id=item.assessment.run_id,
                contract_symbol=item.assessment.contract_symbol,
                observation_id=item.assessment.observation_id,
                entry_state=item.assessment.entry_state,
                applicability_state=ModelApplicabilityState.DETERMINISTIC_ONLY,
                evidence_cutoff_utc=item.assessment.evidence_cutoff_utc,
                input_dataset_ids=item.assessment.input_dataset_ids,
                calculation_version="doi6-supersession-fixture-v1",
                feature_version=item.assessment.feature_version,
                model_version=item.assessment.model_version,
                ranking_score_uncalibrated=1.0 if is_replacement else 0.0,
                metadata={
                    **item.assessment.metadata,
                    "valuation": {
                        **item.assessment.metadata["valuation"],
                        "adverse_worst_return": -0.1 if is_replacement else -0.8,
                    },
                },
            )
            revised = self.store.record_contract_assessment(revised).record
            revised_results.append(replace(item, assessment=revised))
        later_valuation = replace(later_valuation, results=tuple(revised_results))
        second = service.evaluate_completed_session(
            generated_family=later_family, valuation_result=later_valuation,
            evaluation_session=date(2026, 9, 11),
            horizon_end_date=date(2026, 9, 30), event_key="EOD-SECOND",
            current_spot=101,
        )
        self.assertTrue(second.summary.contract_switched)
        self.assertEqual(second.preferred_decision.previous_contract_symbol, prior_symbol)
        self.assertEqual(second.preferred_decision.selected_contract_symbol, replacement_symbol)
        self.assertEqual(second.preferred_decision.prior_decision_id, first.preferred_decision.decision_id)
        self.assertEqual(second.preferred_decision.decision_version, 2)
        self.assertTrue(second.preferred_decision.economics_recomputed)
        replay_first = service.evaluate_completed_session(
            generated_family=family, valuation_result=valuation,
            evaluation_session=SESSION, horizon_end_date=date(2026, 9, 30),
            event_key="EOD-FIRST", current_spot=100,
        )
        self.assertTrue(replay_first.event_reused)
        self.assertTrue(replay_first.preferred_decision_reused)
        self.assertEqual(
            replay_first.preferred_decision.decision_id,
            first.preferred_decision.decision_id,
        )

    def test_preferred_selection_rejects_non_exact_contract_economics(self) -> None:
        family, valuation = self._build()
        malformed_results = tuple(
            replace(
                item,
                assessment=replace(
                    item.assessment,
                    metadata={
                        key: value for key, value in item.assessment.metadata.items()
                        if key != "contract_symbol_exact"
                    },
                ),
            )
            for item in valuation.results
        )
        malformed = replace(valuation, results=malformed_results)
        with self.assertRaisesRegex(ValueError, "exact-contract bound"):
            DynamicOptionsLifecycleService(self.store).evaluate_completed_session(
                generated_family=family, valuation_result=malformed,
                evaluation_session=SESSION,
                horizon_end_date=date(2026, 9, 30),
                event_key="MALFORMED-ECONOMICS", current_spot=100,
            )


if __name__ == "__main__":
    unittest.main()
