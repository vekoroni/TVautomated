from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
from types import SimpleNamespace
import unittest

from canonical_data.contracts import CompletenessStatus, DataScope, DatasetRecord, DatasetType
from canonical_data.dynamic_options_ranking import DynamicOptionsContractRankingService
from canonical_data.errors import DatasetValidationError
from canonical_data.option_liquidity_lifecycle import (
    ContractLiquidityState, MonitorState, OptionLiquidityLifecycleStore, ThesisState,
)
from canonical_data.registry import CanonicalRegistry
from domain.dynamic_options_intelligence import (
    ContractAssessment, ContractEntryState, ContractFamily,
    ModelApplicabilityState, UnderlyingThesisRef,
)
from domain.dynamic_options_ranking import (
    ContractRankingPolicy, RankingCandidateEvidence, RankingMode,
    RankingPolicyMetrics, RankingPolicyStatus, RankingReplayCase,
    RankingReplayPolicy, RankingWeights, rank_contract_family,
    tune_ranking_policy,
)
from domain.dynamic_options_probability import ProbabilityTarget


UTC = timezone.utc
START = datetime(2024, 1, 2, 20, tzinfo=UTC)


def _candidate(
    name: str, score: float | None, *, direction: str = "CALL",
    positive: float | None = None, liquidity: float | None = None,
    target: float | None = None, uncertainty: float | None = None,
) -> RankingCandidateEvidence:
    models = ("M-LIQ", "M-POS", "M-TARGET") if None not in (positive, liquidity, target, uncertainty) else ()
    return RankingCandidateEvidence(
        assessment_id=f"ASSESS-{name}", contract_symbol=f"ABC261218{direction[0]}00{name}",
        direction=direction, evidence_cutoff_utc=START,
        input_dataset_ids=(f"DATA-{name}",), deterministic_score=score,
        p_liquidity_3d=liquidity, p_positive_return=positive,
        p_target_before_invalidation=target, model_uncertainty=uncertainty,
        adverse_worst_return=-0.4, observation_quality="CONTRACT_MONITOR",
        probability_model_ids=models,
    )


def _accepted_policy(*, margin: float = 0.10) -> ContractRankingPolicy:
    metrics = RankingPolicyMetrics(
        cases=40, selected_cases=40, mean_reward=0.6, positive_reward_rate=0.8,
        baseline_mean_reward=0.2, baseline_positive_reward_rate=0.6,
        reward_lift=0.4, coverage=1.0, baseline_coverage=1.0,
        temporal_windows=(
            {"window": 1, "cases": 20, "reward_lift": 0.3, "coverage": 1.0, "baseline_coverage": 1.0, "baseline_not_worse": True},
            {"window": 2, "cases": 20, "reward_lift": 0.5, "coverage": 1.0, "baseline_coverage": 1.0, "baseline_not_worse": True},
        ),
    )
    return ContractRankingPolicy.create(
        policy_version="RANK-V1", status=RankingPolicyStatus.ACCEPTED,
        status_reasons=("TEST_ACCEPTED",),
        weights=RankingWeights(0.0, 0.0, 1.0, 0.0, 0.0),
        minimum_switch_margin=margin, created_at_utc=START,
        training_cutoff_utc=START, validation_cutoff_utc=START,
        holdout_cutoff_utc=START, training_cases=100,
        validation_cases=40, holdout_cases=40,
        source_replay_ids=("REPLAY",), validation_metrics=metrics,
        holdout_metrics=metrics,
    )


def _replays(count: int = 100, *, reverse_holdout: bool = False):
    cases = []
    for index in range(count):
        winner_a = index % 2 == 0
        if reverse_holdout and index >= int(count * 0.8):
            probability_a = 0.1 if winner_a else 0.9
        else:
            probability_a = 0.9 if winner_a else 0.1
        a = replace(
            _candidate(f"A{index}", 0.2, positive=probability_a, liquidity=0.5, target=0.5, uncertainty=0.1),
            evidence_cutoff_utc=START + timedelta(days=index),
        )
        b = replace(
            _candidate(f"B{index}", 0.8, positive=1.0 - probability_a, liquidity=0.5, target=0.5, uncertainty=0.1),
            evidence_cutoff_utc=START + timedelta(days=index),
        )
        cases.append(RankingReplayCase(
            replay_id=f"REPLAY-{index}", feature_cutoff_utc=a.evidence_cutoff_utc,
            outcome_cutoff_utc=a.evidence_cutoff_utc + timedelta(hours=12),
            candidates=(a, b), future_reward_by_assessment={
                a.assessment_id: 1.0 if winner_a else -1.0,
                b.assessment_id: -1.0 if winner_a else 1.0,
            },
        ))
    return tuple(cases)


class RankingDomainTests(unittest.TestCase):
    def test_deterministic_fallback_keeps_every_candidate(self) -> None:
        candidates = (_candidate("A", 0.4), _candidate("B", 0.8), _candidate("C", None))
        result = rank_contract_family(family_id="FAMILY", direction="CALL", candidates=candidates)
        self.assertIs(result.mode, RankingMode.DETERMINISTIC_FALLBACK)
        self.assertEqual(result.selected_assessment_id, "ASSESS-B")
        self.assertEqual(len(result.ranked_contracts), 3)
        self.assertEqual(result.ranked_contracts[-1].score_kind, "NO_COMPARABLE_SCORE")
        self.assertTrue(result.retain_opportunity)

    def test_calibrated_policy_changes_rank_without_claiming_probability(self) -> None:
        candidates = (
            _candidate("A", 0.8, positive=0.2, liquidity=0.5, target=0.5, uncertainty=0.1),
            _candidate("B", 0.2, positive=0.9, liquidity=0.5, target=0.5, uncertainty=0.1),
        )
        result = rank_contract_family(
            family_id="FAMILY", direction="CALL", candidates=candidates,
            policy=_accepted_policy(),
        )
        self.assertIs(result.mode, RankingMode.CALIBRATED_POLICY)
        self.assertEqual(result.selected_assessment_id, "ASSESS-B")
        self.assertEqual(result.decision_authority, "NONE")
        self.assertEqual(result.execution_authority, "HUMAN_ONLY")

    def test_partial_probability_coverage_falls_back_for_whole_family(self) -> None:
        candidates = (
            _candidate("A", 0.8, positive=0.2, liquidity=0.5, target=0.5, uncertainty=0.1),
            _candidate("B", 0.2),
        )
        result = rank_contract_family(
            family_id="FAMILY", direction="CALL", candidates=candidates,
            policy=_accepted_policy(),
        )
        self.assertIs(result.mode, RankingMode.DETERMINISTIC_FALLBACK)
        self.assertEqual(result.selected_assessment_id, "ASSESS-A")

    def test_hysteresis_uses_policy_margin_but_never_discards(self) -> None:
        candidates = (
            _candidate("A", 0.5, positive=0.70, liquidity=0.5, target=0.5, uncertainty=0.1),
            _candidate("B", 0.5, positive=0.75, liquidity=0.5, target=0.5, uncertainty=0.1),
        )
        retained = rank_contract_family(
            family_id="FAMILY", direction="CALL", candidates=candidates,
            previous_contract_symbol=candidates[0].contract_symbol,
            policy=_accepted_policy(margin=0.10),
        )
        self.assertEqual(retained.selected_assessment_id, "ASSESS-A")
        self.assertTrue(retained.hysteresis_suppressed_switch)
        switched = rank_contract_family(
            family_id="FAMILY", direction="CALL",
            candidates=(candidates[0], replace(candidates[1], p_positive_return=0.95)),
            previous_contract_symbol=candidates[0].contract_symbol,
            policy=_accepted_policy(margin=0.10),
        )
        self.assertEqual(switched.selected_assessment_id, "ASSESS-B")
        self.assertTrue(switched.switched_contract)
        self.assertEqual(len(switched.ranked_contracts), 2)

    def test_deterministic_hysteresis_uses_relative_margin(self) -> None:
        current = _candidate("A", 2.00)
        close = _candidate("B", 2.15)
        better = _candidate("C", 2.21)
        retained = rank_contract_family(
            family_id="FAMILY", direction="CALL",
            candidates=(current, close),
            previous_contract_symbol=current.contract_symbol,
            deterministic_fallback_margin=.05,
            deterministic_fallback_relative_margin=.10,
        )
        switched = rank_contract_family(
            family_id="FAMILY", direction="CALL",
            candidates=(current, better),
            previous_contract_symbol=current.contract_symbol,
            deterministic_fallback_margin=.05,
            deterministic_fallback_relative_margin=.10,
        )
        self.assertEqual(retained.selected_assessment_id, current.assessment_id)
        self.assertTrue(retained.hysteresis_suppressed_switch)
        self.assertEqual(switched.selected_assessment_id, better.assessment_id)
        self.assertTrue(switched.switched_contract)

    def test_call_put_ranking_is_symmetric(self) -> None:
        call = rank_contract_family(
            family_id="CALL-FAMILY", direction="CALL",
            candidates=(_candidate("A", 0.2), _candidate("B", 0.8)),
        )
        put = rank_contract_family(
            family_id="PUT-FAMILY", direction="PUT",
            candidates=(_candidate("A", 0.2, direction="PUT"), _candidate("B", 0.8, direction="PUT")),
        )
        self.assertEqual(call.ranked_contracts[0].assessment_id, put.ranked_contracts[0].assessment_id)

    def test_replay_tunes_only_with_chronological_out_of_sample_lift(self) -> None:
        replay_policy = RankingReplayPolicy(
            min_training_cases=30, min_validation_cases=10,
            min_holdout_cases=10, minimum_temporal_window=5,
        )
        accepted = tune_ranking_policy(
            _replays(), created_at_utc=START + timedelta(days=200), policy=replay_policy,
        )
        self.assertIs(accepted.status, RankingPolicyStatus.ACCEPTED)
        self.assertGreater(accepted.holdout_metrics.reward_lift, 0)
        rejected = tune_ranking_policy(
            _replays(reverse_holdout=True), created_at_utc=START + timedelta(days=201),
            policy=replay_policy,
        )
        self.assertIsNot(rejected.status, RankingPolicyStatus.ACCEPTED)

    def test_small_replay_never_creates_weights_or_margin(self) -> None:
        result = tune_ranking_policy(_replays(20), created_at_utc=START + timedelta(days=200))
        self.assertIs(result.status, RankingPolicyStatus.INSUFFICIENT_REPLAY_SUPPORT)
        self.assertIsNone(result.weights)
        self.assertIsNone(result.minimum_switch_margin)

    def test_replay_requires_every_candidate_reward(self) -> None:
        candidate = _candidate("A", 0.5)
        with self.assertRaisesRegex(ValueError, "every ranking candidate"):
            RankingReplayCase(
                replay_id="BAD", feature_cutoff_utc=START,
                outcome_cutoff_utc=START + timedelta(days=1), candidates=(candidate,),
                future_reward_by_assessment={},
            )

    def test_accepted_policy_requires_temporal_stability_evidence(self) -> None:
        with self.assertRaises(ValueError):
            ContractRankingPolicy.create(
                policy_version="POLICY-V1", status=RankingPolicyStatus.ACCEPTED,
                status_reasons=("TEST",),
                weights=RankingWeights(0.2, 0.2, 0.2, 0.2, 0.2),
                minimum_switch_margin=0.10, created_at_utc=START,
                training_cutoff_utc=START, validation_cutoff_utc=START,
                holdout_cutoff_utc=START, training_cases=20,
                validation_cases=10, holdout_cases=10,
                source_replay_ids=("REPLAY-1",), validation_metrics=None,
                holdout_metrics=RankingPolicyMetrics(
                    cases=10, selected_cases=10, mean_reward=1.0,
                    positive_reward_rate=1.0, baseline_mean_reward=0.0,
                    baseline_positive_reward_rate=0.0, reward_lift=1.0,
                    coverage=1.0, baseline_coverage=1.0,
                    temporal_windows=(),
                ),
            )


class RankingPersistenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.registry = CanonicalRegistry(self.root / "control.sqlite")
        self.registry.initialise()
        self.store = OptionLiquidityLifecycleStore(self.registry)
        self.store.initialise()
        self.run_id = "RUN-RANK"
        self.registry.register_run(self.run_id, "REHEARSAL", START.date())
        dataset_id = hashlib.sha256(b"RANK-DATA").hexdigest()
        path = self.root / "chain.json"
        path.write_text(json.dumps({"ticker": "ABC"}), encoding="utf-8")
        self.registry.register_dataset(DatasetRecord(
            dataset_id=dataset_id, dataset_type=DatasetType.OPTION_CHAIN,
            instrument_id="ABC", session_date=START.date(),
            scope=DataScope(start_date=START.date(), end_date=START.date(), sides=("CALL", "PUT")),
            provider="MARKETDATA", content_hash=dataset_id,
            completeness_status=CompletenessStatus.COMPLETE, storage_uri=str(path),
            observed_at=START, as_of=START, adjustment_convention="RAW_OPTION_CONTRACT",
            schema_version="option_chain_v2", source_run_id=self.run_id,
        ))
        thesis = UnderlyingThesisRef(
            thesis_id="THESIS-RANK", thesis_version=1, ticker="ABC", governed_direction="CALL",
            origin_spot=100, origin_timestamp_utc=START - timedelta(minutes=1),
            target_spot=105, invalidation_spot=95, planned_hold_sessions=5,
            planned_hold_source="HORIZON_ROUTER", evidence_cutoff_utc=START,
        )
        self.store.record_thesis_event(
            thesis_id=thesis.thesis_id, event_key="ORIGIN", run_id=self.run_id,
            ticker="ABC", direction="CALL", thesis_state=ThesisState.ACTIVE,
            monitor_state=MonitorState.ACTIVE, reason_code="GOVERNED_THESIS",
            structural_target=105, invalidation_spot=95, recorded_at=START,
        )
        symbols = ("ABC261218C00100000", "ABC261218C00105000", "ABC261218C00110000")
        self.family = self.store.record_contract_family(ContractFamily.create(
            thesis=thesis, run_id=self.run_id, family_policy_version="FAMILY-V1",
            evidence_cutoff_utc=START, candidate_symbols=symbols,
            source_dataset_ids=(dataset_id,), family_state=ModelApplicabilityState.DETERMINISTIC_ONLY,
            created_at=START,
        )).record
        for index, symbol in enumerate(symbols):
            observation = self.store.record_contract_observation(
                thesis_id=thesis.thesis_id, run_id=self.run_id, ticker="ABC",
                contract_symbol=symbol, option_side="CALL", quote_as_of=START,
                observed_at=START, source_dataset_id=dataset_id, spot=100,
                strike=100 + 5 * index, expiration=date(2026, 12, 18), dte=99,
                liquidity_state=ContractLiquidityState.REVIEWABLE_SPREAD,
                bid=1.0, ask=1.2, volume=0 if index == 2 else 10,
                open_interest=0 if index == 2 else 20,
            ).record
            self.store.record_contract_assessment(ContractAssessment.create(
                family_id=self.family.family_id, thesis_id=thesis.thesis_id,
                run_id=self.run_id, contract_symbol=symbol,
                observation_id=observation.observation_id,
                entry_state=(ContractEntryState.CONTRACT_LIQUIDITY_DEVELOPING if index == 2 else ContractEntryState.CONTRACT_MONITOR),
                applicability_state=ModelApplicabilityState.DETERMINISTIC_ONLY,
                evidence_cutoff_utc=START, input_dataset_ids=(dataset_id,),
                calculation_version="ASSESS-V1", feature_version="FEATURE-V1",
                model_version="NOT_EVALUATED", ranking_score_uncalibrated=0.2 + index * 0.2,
                metadata={"valuation": {"adverse_worst_return": -0.5}},
            ))

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_service_falls_back_retains_low_activity_and_persists_idempotently(self) -> None:
        service = DynamicOptionsContractRankingService(self.store)
        first = service.rank_family(family_id=self.family.family_id)
        second = service.rank_family(family_id=self.family.family_id)
        self.assertIs(first.ranking.mode, RankingMode.DETERMINISTIC_FALLBACK)
        self.assertEqual(first.candidate_count, 3)
        self.assertEqual(first.deleted_candidate_count, 0)
        self.assertEqual(first.provider_calls, 0)
        self.assertFalse(first.ranking_reused)
        self.assertTrue(second.ranking_reused)
        self.assertEqual(
            service.repository.ranking(first.ranking.ranking_id).to_dict(),
            first.ranking.to_dict(),
        )
        with self.registry.connection() as connection:
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute("DELETE FROM doi_family_rankings")

    def test_persistence_rejects_forged_ranking_identity(self) -> None:
        service = DynamicOptionsContractRankingService(self.store)
        result = service.rank_family(family_id=self.family.family_id)
        with self.assertRaises(DatasetValidationError):
            service.repository.record_ranking(replace(result.ranking, ranking_id="FORGED"))

    def test_persistence_rejects_forged_policy_identity(self) -> None:
        service = DynamicOptionsContractRankingService(self.store)
        service.repository.initialise()
        with self.assertRaises(DatasetValidationError):
            service.repository.record_policy(replace(_accepted_policy(), policy_id="FORGED"))

    def test_duplicate_applicable_target_inference_forces_family_fallback(self) -> None:
        class FakeProbabilityRepository:
            def initialise(self) -> None:
                return None

            def inferences_for_assessment(self, assessment_id: str):
                def item(target, model_id, probability):
                    return SimpleNamespace(
                        target=target, model_id=model_id, probability=probability,
                        uncertainty=0.0,
                        applicability_state=ModelApplicabilityState.APPLICABLE,
                    )

                return (
                    item(ProbabilityTarget.LIQUIDITY_3D, "L-A", 0.7),
                    item(ProbabilityTarget.LIQUIDITY_3D, "L-B", 0.8),
                    item(ProbabilityTarget.POSITIVE_RETURN, "P", 0.7),
                    item(ProbabilityTarget.TARGET_BEFORE_INVALIDATION, "T", 0.7),
                )

        service = DynamicOptionsContractRankingService(self.store)
        service.probabilities = FakeProbabilityRepository()
        result = service.rank_family(
            family_id=self.family.family_id, policy=_accepted_policy()
        )
        self.assertIs(result.ranking.mode, RankingMode.DETERMINISTIC_FALLBACK)
        self.assertEqual(result.deleted_candidate_count, 0)


if __name__ == "__main__":
    unittest.main()
