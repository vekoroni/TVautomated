from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import sqlite3
import tempfile
import unittest

from canonical_data.dynamic_options_probability import (
    DynamicOptionsProbabilityRepository,
    DynamicOptionsProbabilityService,
    build_probability_feature_vector,
    chronological_model_cohorts,
    infer_probability,
    outcome_target_value,
    train_probability_model,
)
from canonical_data.contracts import CompletenessStatus, DataScope, DatasetRecord, DatasetType
from canonical_data.option_liquidity_lifecycle import (
    ContractLiquidityState, MonitorState, OptionLiquidityLifecycleStore, ThesisState,
)
from canonical_data.registry import CanonicalRegistry
from domain.dynamic_options_intelligence import (
    ContractAssessment, ContractEntryState, ContractFamily,
    ModelApplicabilityState, UnderlyingThesisRef,
)
from domain.dynamic_options_outcomes import OutcomeDataStatus
from domain.dynamic_options_probability import (
    ProbabilityAcceptancePolicy,
    ProbabilityFeatureVector,
    ProbabilityInference,
    ProbabilityModelStatus,
    ProbabilityTarget,
    ProbabilityTrainingExample,
)


UTC = timezone.utc
START = datetime(2024, 1, 2, 20, tzinfo=UTC)


def _feature(index: int, *, direction: str = "CALL", x: float | None = None) -> ProbabilityFeatureVector:
    value = float((index % 20) - 10) / 10.0 if x is None else x
    return ProbabilityFeatureVector(
        assessment_id=f"ASSESS-{direction}-{index}", family_id=f"FAMILY-{direction}-{index}",
        thesis_id=f"THESIS-{direction}-{index}", run_id=f"RUN-{index}", ticker="ABC",
        contract_symbol=f"ABC261218{direction[0]}00100000", direction=direction,
        evidence_cutoff_utc=START + timedelta(days=index), input_dataset_ids=(f"DATA-{index}",),
        values={
            "dte": 35.0 + (index % 5), "directed_moneyness": value,
            "spread_fraction": 0.12 + (index % 3) * 0.01,
            "log_volume": 2.0 + value, "log_open_interest": 3.0,
            "implied_volatility": 0.30 + 0.02 * value,
            "deterministic_score": value, "planned_hold_sessions": 5.0,
        },
    )


def _examples(count: int = 600, *, reverse_holdout: bool = False, direction: str = "CALL"):
    items = []
    for index in range(count):
        feature = _feature(index, direction=direction)
        signal = float(feature.values["deterministic_score"])
        value = int(signal >= 0)
        if reverse_holdout and index >= int(count * 0.8):
            value = 1 - value
        items.append(ProbabilityTrainingExample(
            label_id=f"LABEL-{direction}-{index}", target=ProbabilityTarget.POSITIVE_RETURN,
            feature=feature, outcome_cutoff_utc=feature.evidence_cutoff_utc + timedelta(hours=12),
            value=value,
        ))
    return tuple(items)


class ProbabilityDomainTests(unittest.TestCase):
    def test_outcome_or_future_features_are_forbidden(self) -> None:
        with self.assertRaisesRegex(ValueError, "feature name"):
            replace(_feature(1), values={"future_return": 1.0})

    def test_training_example_enforces_point_in_time_order(self) -> None:
        feature = _feature(1)
        with self.assertRaisesRegex(ValueError, "after"):
            ProbabilityTrainingExample(
                label_id="LEAK", target=ProbabilityTarget.POSITIVE_RETURN,
                feature=feature, outcome_cutoff_utc=feature.evidence_cutoff_utc,
                value=1,
            )

    def test_chronological_split_purges_cross_boundary_labels(self) -> None:
        items = list(_examples(30))
        boundary = int(len(items) * 0.6)
        items[boundary - 1] = replace(
            items[boundary - 1],
            outcome_cutoff_utc=items[boundary].feature.evidence_cutoff_utc + timedelta(hours=1),
        )
        cohorts = chronological_model_cohorts(items)
        self.assertNotIn(items[boundary - 1], cohorts.training)
        self.assertIn(items[boundary - 1], cohorts.purged_overlap)
        self.assertLess(
            max(item.outcome_cutoff_utc for item in cohorts.training),
            min(item.feature.evidence_cutoff_utc for item in cohorts.calibration),
        )

    def test_insufficient_support_never_publishes_a_probability(self) -> None:
        model = train_probability_model(
            _examples(30), target=ProbabilityTarget.POSITIVE_RETURN, direction="CALL",
            horizon_sessions=5, created_at_utc=START + timedelta(days=900),
        )
        self.assertIs(model.status, ProbabilityModelStatus.INSUFFICIENT_SUPPORT)
        inference = infer_probability(model, _feature(1000))
        self.assertIs(inference.applicability_state, ModelApplicabilityState.MODEL_UNAVAILABLE)
        self.assertIsNone(inference.probability)
        self.assertEqual(model.decision_authority, "NONE")

    def test_interpretable_model_must_pass_later_holdout(self) -> None:
        policy = ProbabilityAcceptancePolicy(
            min_training=100, min_calibration=30, min_holdout=30,
            min_class_per_split=10, maximum_ece=0.20,
        )
        model = train_probability_model(
            _examples(), target=ProbabilityTarget.POSITIVE_RETURN, direction="CALL",
            horizon_sessions=5, created_at_utc=START + timedelta(days=900), policy=policy,
        )
        self.assertIs(model.status, ProbabilityModelStatus.ACCEPTED)
        self.assertLess(model.holdout_metrics.brier_score, model.holdout_metrics.baseline_brier_score)
        self.assertLess(model.holdout_metrics.log_loss, model.holdout_metrics.baseline_log_loss)
        self.assertEqual(len(model.coefficients), len(model.feature_names))

    def test_temporally_reversed_edge_is_rejected(self) -> None:
        policy = ProbabilityAcceptancePolicy(
            min_training=100, min_calibration=30, min_holdout=30,
            min_class_per_split=10, maximum_ece=0.20,
        )
        model = train_probability_model(
            _examples(reverse_holdout=True), target=ProbabilityTarget.POSITIVE_RETURN,
            direction="CALL", horizon_sessions=5,
            created_at_utc=START + timedelta(days=900), policy=policy,
        )
        self.assertIsNot(model.status, ProbabilityModelStatus.ACCEPTED)

    def test_accepted_model_withholds_probability_out_of_distribution(self) -> None:
        policy = ProbabilityAcceptancePolicy(
            min_training=100, min_calibration=30, min_holdout=30,
            min_class_per_split=10, maximum_ece=0.20,
        )
        model = train_probability_model(
            _examples(), target=ProbabilityTarget.POSITIVE_RETURN, direction="CALL",
            horizon_sessions=5, created_at_utc=START + timedelta(days=900), policy=policy,
        )
        in_range = infer_probability(model, _feature(1001, x=0.5))
        self.assertIs(in_range.applicability_state, ModelApplicabilityState.APPLICABLE)
        self.assertIsNotNone(in_range.probability)
        out_of_range = infer_probability(model, _feature(1002, x=9.0))
        self.assertIs(out_of_range.applicability_state, ModelApplicabilityState.OUT_OF_DISTRIBUTION)
        self.assertIsNone(out_of_range.probability)
        self.assertEqual(out_of_range.uncertainty, 1.0)

    def test_call_and_put_are_separate_symmetric_cohorts(self) -> None:
        policy = ProbabilityAcceptancePolicy(
            min_training=100, min_calibration=30, min_holdout=30,
            min_class_per_split=10, maximum_ece=0.20,
        )
        call = train_probability_model(
            _examples(direction="CALL"), target=ProbabilityTarget.POSITIVE_RETURN,
            direction="CALL", horizon_sessions=5, created_at_utc=START + timedelta(days=900), policy=policy,
        )
        put = train_probability_model(
            _examples(direction="PUT"), target=ProbabilityTarget.POSITIVE_RETURN,
            direction="PUT", horizon_sessions=5, created_at_utc=START + timedelta(days=900), policy=policy,
        )
        self.assertEqual(call.status, put.status)
        self.assertEqual(call.training_count, put.training_count)
        self.assertNotEqual(call.model_id, put.model_id)

    def test_label_target_mapping_does_not_confuse_liquidity_and_profit(self) -> None:
        label = SimpleNamespace(
            data_status=OutcomeDataStatus.COMPLETE, horizon_sessions=5,
            first_spread_35_session=2, terminal_executable_return=-0.20,
            reference_entry_ask=2.0, first_return_hurdle_session=None,
            first_passage_state="TARGET_FIRST",
        )
        self.assertEqual(outcome_target_value(label, ProbabilityTarget.LIQUIDITY_1D), 0)
        self.assertEqual(outcome_target_value(label, ProbabilityTarget.LIQUIDITY_3D), 1)
        self.assertEqual(outcome_target_value(label, ProbabilityTarget.POSITIVE_RETURN), 0)
        self.assertEqual(outcome_target_value(label, ProbabilityTarget.TARGET_BEFORE_INVALIDATION), 1)


class ProbabilityPersistenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "control.sqlite"
        self.registry = CanonicalRegistry(self.path)
        self.registry.initialise()
        self.store = OptionLiquidityLifecycleStore(self.registry)
        self.store.initialise()

    def _assessment(self):
        run_id = "RUN-PERSIST"
        self.registry.register_run(run_id, "REHEARSAL", START.date())
        dataset_id = hashlib.sha256(b"DOI8-PERSIST").hexdigest()
        path = Path(self.temp.name) / "dataset.json"
        path.write_text(json.dumps({"ticker": "ABC"}), encoding="utf-8")
        self.registry.register_dataset(DatasetRecord(
            dataset_id=dataset_id, dataset_type=DatasetType.OPTION_CHAIN,
            instrument_id="ABC", session_date=START.date(),
            scope=DataScope(start_date=START.date(), end_date=START.date(), sides=("CALL", "PUT")),
            provider="MARKETDATA", content_hash=dataset_id,
            completeness_status=CompletenessStatus.COMPLETE, storage_uri=str(path),
            observed_at=START, as_of=START, adjustment_convention="RAW_OPTION_CONTRACT",
            schema_version="option_chain_v2", source_run_id=run_id,
        ))
        thesis = UnderlyingThesisRef(
            thesis_id="THESIS-PERSIST", thesis_version=1, ticker="ABC",
            governed_direction="CALL", origin_spot=100,
            origin_timestamp_utc=START - timedelta(minutes=1),
            target_spot=105, invalidation_spot=95, planned_hold_sessions=5,
            planned_hold_source="HORIZON_ROUTER", evidence_cutoff_utc=START,
        )
        self.store.record_thesis_event(
            thesis_id=thesis.thesis_id, event_key="ORIGIN", run_id=run_id,
            ticker="ABC", direction="CALL", thesis_state=ThesisState.ACTIVE,
            monitor_state=MonitorState.ACTIVE, reason_code="GOVERNED_THESIS",
            structural_target=105, invalidation_spot=95, recorded_at=START,
        )
        observation = self.store.record_contract_observation(
            thesis_id=thesis.thesis_id, run_id=run_id, ticker="ABC",
            contract_symbol="ABC261218C00100000", option_side="CALL",
            quote_as_of=START, observed_at=START, source_dataset_id=dataset_id,
            spot=100, strike=100, expiration=date(2026, 12, 18), dte=99,
            liquidity_state=ContractLiquidityState.REVIEWABLE_SPREAD,
            bid=1.0, ask=1.2, volume=10, open_interest=20,
        ).record
        family = self.store.record_contract_family(ContractFamily.create(
            thesis=thesis, run_id=run_id, family_policy_version="FAMILY-V1",
            evidence_cutoff_utc=START, candidate_symbols=(observation.contract_symbol,),
            source_dataset_ids=(dataset_id,),
            family_state=ModelApplicabilityState.DETERMINISTIC_ONLY,
            created_at=START,
        )).record
        assessment = self.store.record_contract_assessment(ContractAssessment.create(
            family_id=family.family_id, thesis_id=thesis.thesis_id, run_id=run_id,
            contract_symbol=observation.contract_symbol, observation_id=observation.observation_id,
            entry_state=ContractEntryState.CONTRACT_MONITOR,
            applicability_state=ModelApplicabilityState.DETERMINISTIC_ONLY,
            evidence_cutoff_utc=START, input_dataset_ids=(dataset_id,),
            calculation_version="ASSESS-V1", feature_version="FEATURE-V1",
            model_version="NOT_EVALUATED", ranking_score_uncalibrated=0.5,
        )).record
        return assessment, family, observation, dataset_id

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_empty_production_cohort_records_insufficient_model_idempotently(self) -> None:
        service = DynamicOptionsProbabilityService(self.store)
        first = service.train_and_record(
            target=ProbabilityTarget.POSITIVE_RETURN, direction="CALL",
            horizon_sessions=5, created_at_utc=START,
        )
        second = service.train_and_record(
            target=ProbabilityTarget.POSITIVE_RETURN, direction="CALL",
            horizon_sessions=5, created_at_utc=START,
        )
        self.assertEqual(first.model_id, second.model_id)
        self.assertIs(first.status, ProbabilityModelStatus.INSUFFICIENT_SUPPORT)
        self.assertEqual(service.repository.model(first.model_id).to_dict(), first.to_dict())
        with self.registry.connection() as connection:
            count = connection.execute("SELECT COUNT(*) FROM doi_probability_models").fetchone()[0]
            self.assertEqual(count, 1)
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute("UPDATE doi_probability_models SET direction='PUT'")

    def test_non_applicable_inference_cannot_claim_probability(self) -> None:
        with self.assertRaisesRegex(ValueError, "non-applicable"):
            ProbabilityInference.create(
                model_id="MODEL", assessment_id="ASSESS", target=ProbabilityTarget.LIQUIDITY_1D,
                direction="CALL", evidence_cutoff_utc=START,
                applicability_state=ModelApplicabilityState.MODEL_UNAVAILABLE,
                probability=0.8, raw_probability=None, uncertainty=None, ood_features=(),
                input_dataset_ids=("DATA",), reason_codes=("NO_MODEL",),
            )

    def test_inference_round_trip_is_idempotent_and_lineage_bound(self) -> None:
        assessment, _, _, dataset_id = self._assessment()
        service = DynamicOptionsProbabilityService(self.store)
        model = service.train_and_record(
            target=ProbabilityTarget.POSITIVE_RETURN, direction="CALL",
            horizon_sessions=5, created_at_utc=START,
        )
        inference = ProbabilityInference.create(
            model_id=model.model_id, assessment_id=assessment.assessment_id,
            target=ProbabilityTarget.POSITIVE_RETURN, direction="CALL",
            evidence_cutoff_utc=assessment.evidence_cutoff_utc,
            applicability_state=ModelApplicabilityState.MODEL_UNAVAILABLE,
            probability=None, raw_probability=None, uncertainty=None, ood_features=(),
            input_dataset_ids=(dataset_id,), reason_codes=("INSUFFICIENT_SUPPORT",),
        )
        first, first_reused = service.repository.record_inference(inference)
        second, second_reused = service.repository.record_inference(inference)
        self.assertFalse(first_reused)
        self.assertTrue(second_reused)
        self.assertEqual(first.to_dict(), second.to_dict())
        with self.assertRaisesRegex(Exception, "direction"):
            service.repository.record_inference(replace(
                inference,
                inference_id=ProbabilityInference.create(
                    model_id=model.model_id, assessment_id=assessment.assessment_id,
                    target=ProbabilityTarget.POSITIVE_RETURN, direction="PUT",
                    evidence_cutoff_utc=assessment.evidence_cutoff_utc,
                    applicability_state=ModelApplicabilityState.MODEL_UNAVAILABLE,
                    probability=None, raw_probability=None, uncertainty=None, ood_features=(),
                    input_dataset_ids=(dataset_id,), reason_codes=("INSUFFICIENT_SUPPORT",),
                ).inference_id,
                direction="PUT",
            ))
        with self.registry.connection() as connection:
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute("DELETE FROM doi_probability_inferences")


class ProbabilityFeatureAdapterTests(unittest.TestCase):
    def test_feature_adapter_uses_only_assessment_time_evidence(self) -> None:
        assessment = SimpleNamespace(
            assessment_id="ASSESS", family_id="FAMILY", thesis_id="THESIS", run_id="RUN",
            contract_symbol="ABC261218C00100000", observation_id="OBS",
            evidence_cutoff_utc=START, input_dataset_ids=("DATA",), ranking_score_uncalibrated=0.7,
        )
        family = SimpleNamespace(
            family_id="FAMILY",
            thesis=SimpleNamespace(governed_direction="CALL", ticker="ABC", planned_hold_sessions=5),
        )
        observation = SimpleNamespace(
            observation_id="OBS", quote_as_of=START, source_dataset_id="DATA",
            spot=100.0, strike=105.0, dte=35.0, delta=0.35,
            bid=1.0, ask=1.2, spread_pct=None, volume=5.0, open_interest=0.0,
            bid_size=2.0, ask_size=3.0, iv=0.4, atm_distance_sigma=0.5,
            remaining_runway_pct=0.8,
        )
        feature = build_probability_feature_vector(
            assessment=assessment, family=family, observation=observation,
        )
        self.assertAlmostEqual(feature.values["directed_moneyness"], 0.05)
        self.assertIsNone(feature.values["volume_open_interest_ratio"])
        self.assertNotIn("outcome", " ".join(feature.values))


if __name__ == "__main__":
    unittest.main()
