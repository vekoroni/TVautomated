from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import sqlite3
import tempfile
import unittest

from canonical_data.contracts import (
    CompletenessStatus,
    DataScope,
    DatasetRecord,
    DatasetType,
)
from canonical_data.errors import DatasetValidationError
from canonical_data.option_liquidity_lifecycle import (
    ContractLiquidityState,
    MonitorState,
    OptionLifecycleConcurrencyError,
    OptionLifecycleConflict,
    OptionLiquidityLifecycleStore,
    ThesisState,
)
from canonical_data.registry import CanonicalRegistry
from domain.dynamic_options_intelligence import (
    ContractAssessment,
    ContractEntryState,
    ContractFamily,
    ModelApplicabilityState,
    PreferredContractDecision,
    UnderlyingThesisRef,
)


RUN_ID = "20260910_180000"
SESSION = date(2026, 9, 10)
CUTOFF = datetime(2026, 9, 10, 20, 0, tzinfo=timezone.utc)


class DynamicOptionsDomainPersistenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.registry = CanonicalRegistry(self.root / "control_plane.sqlite")
        self.registry.initialise()
        self.registry.register_run(RUN_ID, "EVENING", SESSION)
        self.store = OptionLiquidityLifecycleStore(self.registry)
        self.store.initialise()
        self.dataset_id = self._dataset()
        self.store.record_thesis_event(
            thesis_id="BP-PUT-DOI-1",
            event_key="EOD-CREATED",
            run_id=RUN_ID,
            ticker="BP",
            direction="PUT",
            thesis_state=ThesisState.ACTIVE,
            monitor_state=MonitorState.ACTIVE,
            reason_code="DOI_MONITOR",
            structural_target=38.0,
            invalidation_spot=43.0,
            horizon_end_date=date(2026, 9, 30),
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _dataset(self) -> str:
        dataset_id = "chain-bp-marketdata-doi"
        payload = self.root / "chain.parquet"
        payload.write_bytes(b"PAR1-doi-test-PAR1")
        self.registry.register_dataset(
            DatasetRecord(
                dataset_id=dataset_id,
                dataset_type=DatasetType.OPTION_CHAIN,
                instrument_id="BP",
                session_date=SESSION,
                scope=DataScope(
                    start_date=SESSION,
                    end_date=SESSION,
                    dte_min=1,
                    dte_max=90,
                    sides=("CALL", "PUT"),
                ),
                provider="MARKETDATA",
                content_hash="d" * 64,
                completeness_status=CompletenessStatus.COMPLETE,
                storage_uri=str(payload),
                observed_at=CUTOFF,
                as_of=CUTOFF,
                adjustment_convention="RAW_OPTION_CONTRACT",
                schema_version="option_chain_v2",
                source_run_id=RUN_ID,
            )
        )
        return dataset_id

    def _thesis_ref(self) -> UnderlyingThesisRef:
        return UnderlyingThesisRef(
            thesis_id="BP-PUT-DOI-1",
            thesis_version=1,
            ticker="BP",
            governed_direction="PUT",
            origin_spot=41.0,
            origin_timestamp_utc=CUTOFF - timedelta(hours=1),
            target_spot=38.0,
            invalidation_spot=43.0,
            planned_hold_sessions=10,
            planned_hold_source="HORIZON_ROUTER",
            evidence_cutoff_utc=CUTOFF,
        )

    def _observation(
        self,
        contract_symbol: str = "BP261016P00040000",
        quote_time: datetime = CUTOFF,
        bid: float = 1.00,
        ask: float = 1.20,
    ):
        return self.store.record_contract_observation(
            thesis_id="BP-PUT-DOI-1",
            run_id=RUN_ID,
            ticker="BP",
            contract_symbol=contract_symbol,
            option_side="PUT",
            quote_as_of=quote_time,
            source_dataset_id=self.dataset_id,
            spot=41.0,
            strike=40.0 if "40000" in contract_symbol else 39.0,
            expiration=date(2026, 10, 16),
            dte=36,
            delta=-0.40,
            bid=bid,
            ask=ask,
            bid_size=5,
            ask_size=7,
            spread_pct=(ask - bid) / ((ask + bid) / 2),
            volume=3,
            open_interest=12,
            iv=0.40,
            liquidity_state=ContractLiquidityState.REVIEWABLE_SPREAD,
            maturation_score_1d=45.0,
            maturation_score_2d=55.0,
            maturation_score_3d=65.0,
            maturation_score_is_probability=False,
            atm_distance_sigma=0.5,
            remaining_runway_pct=80.0,
        ).record

    def _family(
        self,
        *,
        cutoff: datetime = CUTOFF,
        symbols: tuple[str, ...] = (
            "BP261016P00040000",
            "BP261016P00039000",
        ),
    ) -> ContractFamily:
        return ContractFamily.create(
            thesis=self._thesis_ref(),
            run_id=RUN_ID,
            family_policy_version="doi-family-policy-v1",
            evidence_cutoff_utc=cutoff,
            candidate_symbols=symbols,
            source_dataset_ids=(self.dataset_id,),
            family_state=ModelApplicabilityState.DETERMINISTIC_ONLY,
            created_at=cutoff,
        )

    def _assessment(
        self,
        family: ContractFamily,
        observation_id: str,
        symbol: str = "BP261016P00040000",
        cutoff: datetime = CUTOFF,
    ) -> ContractAssessment:
        return ContractAssessment.create(
            family_id=family.family_id,
            thesis_id=family.thesis.thesis_id,
            run_id=RUN_ID,
            contract_symbol=symbol,
            observation_id=observation_id,
            entry_state=ContractEntryState.CONTRACT_LIMIT_PRICE_REQUIRED,
            applicability_state=ModelApplicabilityState.DETERMINISTIC_ONLY,
            evidence_cutoff_utc=cutoff,
            input_dataset_ids=(self.dataset_id,),
            calculation_version="doi-assessment-v1",
            feature_version="doi-features-v1",
            ranking_score_uncalibrated=61.25,
            model_uncertainty=0.40,
        )

    def test_schema_is_additive_and_uses_existing_control_plane(self) -> None:
        with self.registry.connection() as connection:
            tables = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
        self.assertTrue(
            {
                "doi_contract_families",
                "doi_contract_assessments",
                "doi_preferred_contract_decisions",
            }.issubset(tables)
        )
        self.assertEqual(list(self.root.glob("*.sqlite")), [self.root / "control_plane.sqlite"])

    def test_domain_contract_has_no_provider_or_persistence_dependency(self) -> None:
        source = (
            Path(__file__).resolve().parents[1]
            / "domain"
            / "dynamic_options_intelligence.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn("canonical_data", source)
        self.assertNotIn("sqlite", source.lower())
        self.assertNotIn("MarketData", source)

    def test_domain_contracts_preserve_authority_and_incomplete_geometry(self) -> None:
        thesis = UnderlyingThesisRef(
            thesis_id="ABC-CALL-1",
            thesis_version=1,
            ticker="ABC",
            governed_direction="CALL",
            origin_spot=100.0,
            origin_timestamp_utc=CUTOFF,
            target_spot=None,
            invalidation_spot=None,
            planned_hold_sessions=5,
            planned_hold_source="HORIZON_ROUTER",
            evidence_cutoff_utc=CUTOFF,
        )
        family = ContractFamily.create(
            thesis=thesis,
            run_id=RUN_ID,
            family_policy_version="doi-family-policy-v1",
            evidence_cutoff_utc=CUTOFF,
            family_state=ModelApplicabilityState.DATA_INSUFFICIENT,
        )
        self.assertFalse(thesis.geometry_complete)
        self.assertEqual(family.decision_authority, "NONE")
        self.assertFalse(family.can_change_direction)
        self.assertFalse(family.can_invalidate_thesis)
        self.assertFalse(family.can_grant_capital)

    def test_call_put_geometry_validation_is_symmetric(self) -> None:
        for direction, target, invalidation in (
            ("CALL", 110.0, 95.0),
            ("PUT", 90.0, 105.0),
        ):
            thesis = UnderlyingThesisRef(
                thesis_id=f"ABC-{direction}-1",
                thesis_version=1,
                ticker="ABC",
                governed_direction=direction,
                origin_spot=100.0,
                origin_timestamp_utc=CUTOFF,
                target_spot=target,
                invalidation_spot=invalidation,
                planned_hold_sessions=10,
                planned_hold_source="HORIZON_ROUTER",
                evidence_cutoff_utc=CUTOFF,
            )
            self.assertTrue(thesis.geometry_complete)
            with self.assertRaisesRegex(ValueError, "target_spot is wrong-sided"):
                UnderlyingThesisRef(
                    thesis_id=f"ABC-{direction}-BAD",
                    thesis_version=1,
                    ticker="ABC",
                    governed_direction=direction,
                    origin_spot=100.0,
                    origin_timestamp_utc=CUTOFF,
                    target_spot=invalidation,
                    invalidation_spot=target,
                    planned_hold_sessions=10,
                    planned_hold_source="HORIZON_ROUTER",
                    evidence_cutoff_utc=CUTOFF,
                )

    def test_data_insufficient_empty_family_is_persisted_not_discarded(self) -> None:
        family = ContractFamily.create(
            thesis=self._thesis_ref(),
            run_id=RUN_ID,
            family_policy_version="doi-family-no-chain-v1",
            evidence_cutoff_utc=CUTOFF,
            candidate_symbols=(),
            source_dataset_ids=(),
            family_state=ModelApplicabilityState.DATA_INSUFFICIENT,
            created_at=CUTOFF,
            metadata={"reason": "CHAIN_UNAVAILABLE"},
        )
        persisted = self.store.record_contract_family(family)
        self.assertFalse(persisted.reused_existing)
        self.assertEqual(persisted.record.candidate_symbols, ())
        self.assertEqual(
            persisted.record.family_state,
            ModelApplicabilityState.DATA_INSUFFICIENT,
        )

    def test_probability_outputs_cannot_be_published_as_uncalibrated(self) -> None:
        observation = self._observation()
        family = self._family()
        with self.assertRaisesRegex(ValueError, "probabilities_calibrated"):
            ContractAssessment.create(
                family_id=family.family_id,
                thesis_id=family.thesis.thesis_id,
                run_id=RUN_ID,
                contract_symbol=observation.contract_symbol,
                observation_id=observation.observation_id,
                entry_state=ContractEntryState.CONTRACT_MONITOR,
                applicability_state=ModelApplicabilityState.DETERMINISTIC_ONLY,
                evidence_cutoff_utc=CUTOFF,
                input_dataset_ids=(self.dataset_id,),
                calculation_version="doi-assessment-v1",
                feature_version="doi-features-v1",
                p_liquidity_1d=0.60,
            )
        calibrated = ContractAssessment.create(
            family_id=family.family_id,
            thesis_id=family.thesis.thesis_id,
            run_id=RUN_ID,
            contract_symbol=observation.contract_symbol,
            observation_id=observation.observation_id,
            entry_state=ContractEntryState.CONTRACT_MONITOR,
            applicability_state=ModelApplicabilityState.APPLICABLE,
            evidence_cutoff_utc=CUTOFF,
            input_dataset_ids=(self.dataset_id,),
            calculation_version="doi-assessment-v1",
            feature_version="doi-features-v1",
            model_version="liquidity-logit-calibrated-v1",
            p_liquidity_1d=0.60,
            probabilities_calibrated=True,
        )
        self.assertEqual(calibrated.p_liquidity_1d, 0.60)

    def test_family_assessment_and_preferred_decision_round_trip_idempotently(self) -> None:
        observation = self._observation()
        family = self._family()
        first_family = self.store.record_contract_family(family)
        replay_family = self.store.record_contract_family(
            self._family()
        )
        self.assertFalse(first_family.reused_existing)
        self.assertTrue(replay_family.reused_existing)

        assessment = self._assessment(family, observation.observation_id)
        first_assessment = self.store.record_contract_assessment(assessment)
        replay_assessment = self.store.record_contract_assessment(assessment)
        self.assertFalse(first_assessment.reused_existing)
        self.assertTrue(replay_assessment.reused_existing)

        alternative_observation = self._observation(
            contract_symbol="BP261016P00039000",
            bid=1.30,
            ask=1.50,
        )
        alternative = self._assessment(
            family,
            alternative_observation.observation_id,
            symbol=alternative_observation.contract_symbol,
        )
        self.store.record_contract_assessment(alternative)

        preferred = PreferredContractDecision.create(
            event_key="EOD-PREFERRED-1",
            family_id=family.family_id,
            thesis_id=family.thesis.thesis_id,
            run_id=RUN_ID,
            selected_contract_symbol=assessment.contract_symbol,
            selected_assessment_id=assessment.assessment_id,
            selection_reason="HIGHEST_DETERMINISTIC_UTILITY",
            selected_at=CUTOFF,
            alternative_contract_symbols=(alternative.contract_symbol,),
        )
        first_preferred = self.store.record_preferred_contract_decision(preferred)
        replay_preferred = self.store.record_preferred_contract_decision(preferred)
        self.assertEqual(first_preferred.record.decision_version, 1)
        self.assertTrue(replay_preferred.reused_existing)
        self.assertEqual(
            self.store.latest_preferred_contract(family.thesis.thesis_id).decision_id,
            preferred.decision_id,
        )
        self.assertEqual(
            self.store.latest_preferred_contract(
                family.thesis.thesis_id
            ).alternative_contract_symbols,
            (alternative.contract_symbol,),
        )

        restarted = OptionLiquidityLifecycleStore(self.registry)
        restarted.initialise()
        self.assertEqual(restarted.contract_family(family.family_id), family)
        self.assertEqual(
            restarted.contract_assessment(assessment.assessment_id), assessment
        )

    def test_family_identity_conflict_fails_closed(self) -> None:
        family = self._family()
        self.store.record_contract_family(family)
        changed = ContractFamily(
            family_id=family.family_id,
            thesis=family.thesis,
            run_id=family.run_id,
            family_policy_version=family.family_policy_version,
            evidence_cutoff_utc=family.evidence_cutoff_utc,
            candidate_symbols=("BP261016P00040000",),
            source_dataset_ids=family.source_dataset_ids,
            family_state=family.family_state,
            created_at=family.created_at,
            metadata=family.metadata,
        )
        with self.assertRaises(OptionLifecycleConflict):
            self.store.record_contract_family(changed)

    def test_assessment_requires_exact_contract_and_dataset_lineage(self) -> None:
        observation = self._observation()
        family = self._family()
        self.store.record_contract_family(family)
        wrong = self._assessment(
            family,
            observation.observation_id,
            symbol="BP261016P00039000",
        )
        with self.assertRaisesRegex(DatasetValidationError, "exact contract"):
            self.store.record_contract_assessment(wrong)

    def test_preferred_supersession_is_append_only_and_version_checked(self) -> None:
        first_observation = self._observation()
        family1 = self._family()
        self.store.record_contract_family(family1)
        assessment1 = self._assessment(family1, first_observation.observation_id)
        self.store.record_contract_assessment(assessment1)
        decision1 = PreferredContractDecision.create(
            event_key="PREFERRED-1",
            family_id=family1.family_id,
            thesis_id=family1.thesis.thesis_id,
            run_id=RUN_ID,
            selected_contract_symbol=assessment1.contract_symbol,
            selected_assessment_id=assessment1.assessment_id,
            selection_reason="INITIAL_SELECTION",
            selected_at=CUTOFF,
        )
        persisted1 = self.store.record_preferred_contract_decision(decision1).record

        later = CUTOFF + timedelta(minutes=5)
        second_observation = self._observation(
            contract_symbol="BP261016P00039000",
            quote_time=later,
            bid=1.30,
            ask=1.45,
        )
        family2 = self._family(cutoff=later)
        self.store.record_contract_family(family2)
        assessment2 = self._assessment(
            family2,
            second_observation.observation_id,
            symbol=second_observation.contract_symbol,
            cutoff=later,
        )
        self.store.record_contract_assessment(assessment2)
        decision2 = PreferredContractDecision.create(
            event_key="PREFERRED-2",
            family_id=family2.family_id,
            thesis_id=family2.thesis.thesis_id,
            run_id=RUN_ID,
            selected_contract_symbol=assessment2.contract_symbol,
            selected_assessment_id=assessment2.assessment_id,
            selection_reason="UTILITY_MARGIN_EXCEEDED",
            selected_at=later,
            previous_contract_symbol=persisted1.selected_contract_symbol,
            prior_decision_id=persisted1.decision_id,
            utility_margin=12.5,
            economics_recomputed=True,
        )
        with self.assertRaises(OptionLifecycleConcurrencyError):
            self.store.record_preferred_contract_decision(
                decision2, expected_version=0
            )
        persisted2 = self.store.record_preferred_contract_decision(
            decision2, expected_version=1
        ).record
        self.assertEqual(persisted2.decision_version, 2)
        self.assertEqual(persisted2.prior_decision_id, persisted1.decision_id)

    def test_new_doi_tables_reject_update_and_delete(self) -> None:
        family = self._family()
        self.store.record_contract_family(family)
        with self.assertRaises(sqlite3.DatabaseError):
            with self.registry.connection() as connection:
                connection.execute(
                    "UPDATE doi_contract_families SET family_state = ? "
                    "WHERE family_id = ?",
                    (ModelApplicabilityState.APPLICABLE.value, family.family_id),
                )
        with self.assertRaises(sqlite3.DatabaseError):
            with self.registry.connection() as connection:
                connection.execute(
                    "DELETE FROM doi_contract_families WHERE family_id = ?",
                    (family.family_id,),
                )


if __name__ == "__main__":
    unittest.main()
