from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import math
from pathlib import Path
import tempfile
import unittest

import pandas as pd

from canonical_data.contracts import (
    CompletenessStatus, DataScope, DatasetRecord, DatasetType,
)
from canonical_data.dynamic_options_bridge import GovernedOptionObservation
from canonical_data.dynamic_options_family import ThesisConditionedContractFamilyGenerator
from canonical_data.dynamic_options_valuation import (
    DeterministicContractValuationService,
    build_xnys_scenario_points,
)
from canonical_data.option_liquidity_lifecycle import (
    MonitorState, OptionLiquidityLifecycleStore, ThesisState,
)
from canonical_data.registry import CanonicalRegistry
from domain.deterministic_option_valuation import (
    IVStress, ScenarioPath, ScenarioPoint, ScenarioTiming,
    assess_american_exercise_materiality, dividend_adjusted_black_scholes,
    evaluate_deterministic_scenarios,
)
from domain.dynamic_options_intelligence import (
    ModelApplicabilityState, ObservationAcquisitionDecision,
    OptionObservationKind, UnderlyingThesisRef,
)


UTC = timezone.utc
RUN_ID = "20260910_200000"
SESSION = date(2026, 9, 10)
CUTOFF = datetime(2026, 9, 10, 20, 0, tzinfo=UTC)


def _symbol(side: str, strike: float, expiry: str = "261016") -> str:
    return f"ABC{expiry}{'C' if side == 'CALL' else 'P'}{int(strike * 1000):08d}"


def _points(at: datetime) -> tuple[ScenarioPoint, ...]:
    return tuple(
        ScenarioPoint(timing=timing, sessions_elapsed=index, as_of_utc=at)
        for index, timing in enumerate(ScenarioTiming, 1)
    )


class DeterministicFormulaTests(unittest.TestCase):
    def test_dividend_adjusted_put_call_parity(self) -> None:
        values = dict(
            spot=103.0, strike=100.0, time_to_expiry_years=0.7,
            risk_free_rate=0.042, dividend_yield=0.017, volatility=0.31,
        )
        call = dividend_adjusted_black_scholes(option_side="CALL", **values)
        put = dividend_adjusted_black_scholes(option_side="PUT", **values)
        parity = 103.0 * math.exp(-0.017 * 0.7) - 100.0 * math.exp(-0.042 * 0.7)
        self.assertAlmostEqual(call - put, parity, places=11)

    def test_expiry_intrinsic_and_friction_fixture_are_exact(self) -> None:
        at = datetime(2026, 10, 16, 20, 0, tzinfo=UTC)
        valuation = evaluate_deterministic_scenarios(
            option_side="CALL", strike=100.0, expiration_utc=at,
            target_spot=110.0, invalidation_spot=90.0, base_iv=0.40,
            scenario_points=_points(at), entry_ask=5.0,
            risk_free_rate=0.0, dividend_yield=0.0,
            entry_friction_bps=100.0, exit_friction_bps=100.0,
        )
        target = next(
            item for item in valuation.scenarios
            if item.path is ScenarioPath.FAVOURABLE_TARGET
            and item.timing is ScenarioTiming.EARLY
            and item.iv_stress is IVStress.BASE
        )
        self.assertEqual(target.theoretical_value, 10.0)
        self.assertEqual(target.entry_cost_after_friction, 5.05)
        self.assertEqual(target.exit_value_after_friction, 9.9)
        self.assertAlmostEqual(target.net_return_fraction, (9.9 - 5.05) / 5.05)

    def test_grid_is_18_and_timing_exposes_theta(self) -> None:
        start = datetime(2026, 9, 11, 20, 0, tzinfo=UTC)
        points = (
            ScenarioPoint(ScenarioTiming.EARLY, 1, start),
            ScenarioPoint(ScenarioTiming.MID, 5, start + timedelta(days=7)),
            ScenarioPoint(ScenarioTiming.LATE, 10, start + timedelta(days=14)),
        )
        result = evaluate_deterministic_scenarios(
            option_side="CALL", strike=100, expiration_utc=datetime(2026, 10, 16, 20, tzinfo=UTC),
            target_spot=110, invalidation_spot=95, base_iv=0.35,
            scenario_points=points, entry_ask=4, risk_free_rate=0.04,
            dividend_yield=0.01,
        )
        self.assertEqual(len(result.scenarios), 18)
        target_base = {
            item.timing: item.theoretical_value for item in result.scenarios
            if item.path is ScenarioPath.FAVOURABLE_TARGET and item.iv_stress is IVStress.BASE
        }
        self.assertGreater(target_base[ScenarioTiming.EARLY], target_base[ScenarioTiming.LATE])

    def test_iv_stress_ordering_for_call_and_put(self) -> None:
        for side, target, invalidation in (("CALL", 110, 95), ("PUT", 90, 105)):
            result = evaluate_deterministic_scenarios(
                option_side=side, strike=100,
                expiration_utc=datetime(2026, 10, 16, 20, tzinfo=UTC),
                target_spot=target, invalidation_spot=invalidation, base_iv=0.4,
                scenario_points=_points(datetime(2026, 9, 15, 20, tzinfo=UTC)),
                entry_ask=4, risk_free_rate=0.04, dividend_yield=0.01,
            )
            early = {
                item.iv_stress: item.theoretical_value for item in result.scenarios
                if item.path is ScenarioPath.FAVOURABLE_TARGET and item.timing is ScenarioTiming.EARLY
            }
            self.assertLess(early[IVStress.CONTRACTED], early[IVStress.BASE])
            self.assertLess(early[IVStress.BASE], early[IVStress.EXPANDED])

    def test_missing_inputs_never_become_probability_or_fabricated_utility(self) -> None:
        result = evaluate_deterministic_scenarios(
            option_side="PUT", strike=100,
            expiration_utc=datetime(2026, 10, 16, 20, tzinfo=UTC),
            target_spot=90, invalidation_spot=105, base_iv=None,
            scenario_points=_points(datetime(2026, 9, 15, 20, tzinfo=UTC)),
            entry_ask=4, risk_free_rate=0.04, dividend_yield=0.01,
        )
        self.assertEqual(result.applicability_state, ModelApplicabilityState.DATA_INSUFFICIENT)
        self.assertIsNone(result.ranking_score_uncalibrated)
        self.assertFalse(result.probabilities_calibrated)
        self.assertEqual(result.scenarios, ())

    def test_dividends_lower_calls_and_raise_puts(self) -> None:
        kwargs = dict(spot=100, strike=100, time_to_expiry_years=1,
                      risk_free_rate=0.04, volatility=0.3)
        call_zero = dividend_adjusted_black_scholes(option_side="CALL", dividend_yield=0, **kwargs)
        call_div = dividend_adjusted_black_scholes(option_side="CALL", dividend_yield=0.03, **kwargs)
        put_zero = dividend_adjusted_black_scholes(option_side="PUT", dividend_yield=0, **kwargs)
        put_div = dividend_adjusted_black_scholes(option_side="PUT", dividend_yield=0.03, **kwargs)
        self.assertLess(call_div, call_zero)
        self.assertGreater(put_div, put_zero)

    def test_american_long_option_value_never_falls_below_intrinsic(self) -> None:
        put = dividend_adjusted_black_scholes(
            option_side="PUT", spot=85, strike=100,
            time_to_expiry_years=1.0, risk_free_rate=0.08,
            dividend_yield=0.0, volatility=0.05,
        )
        call = dividend_adjusted_black_scholes(
            option_side="CALL", spot=120, strike=100,
            time_to_expiry_years=1.0, risk_free_rate=-0.02,
            dividend_yield=0.08, volatility=0.05,
        )
        self.assertGreaterEqual(put, 15.0)
        self.assertGreaterEqual(call, 20.0)

    def test_american_put_materiality_uses_rate_horizon_and_volatility(self) -> None:
        material, reason = assess_american_exercise_materiality(
            option_side="PUT", spot=100, strike=100, dividend_yield=0.0,
            ex_dividend_within_horizon=False, risk_free_rate=0.08,
            time_to_expiry_years=1.0, volatility=0.20,
        )
        self.assertTrue(material)
        self.assertEqual(reason, "RATE_AND_HORIZON_PUT_EARLY_EXERCISE_NOT_MODELLED")

        short_material, _ = assess_american_exercise_materiality(
            option_side="PUT", spot=75, strike=100, dividend_yield=0.0,
            ex_dividend_within_horizon=False, risk_free_rate=0.04,
            time_to_expiry_years=14 / 365.0, volatility=0.20,
        )
        self.assertFalse(short_material)

    def test_sufficiently_itm_put_discloses_american_model_limit(self) -> None:
        result = evaluate_deterministic_scenarios(
            option_side="PUT", strike=150,
            expiration_utc=datetime(2026, 10, 16, 20, tzinfo=UTC),
            target_spot=80, invalidation_spot=105, base_iv=0.4,
            scenario_points=_points(datetime(2026, 9, 15, 20, tzinfo=UTC)),
            entry_ask=50, risk_free_rate=0.04, dividend_yield=0,
        )
        self.assertEqual(result.applicability_state, ModelApplicabilityState.OUT_OF_DISTRIBUTION)
        self.assertTrue(result.american_exercise_material)
        self.assertIn("SUFFICIENTLY_ITM_PUT_EARLY_EXERCISE_NOT_MODELLED", result.disclosures)

    def test_calendar_points_skip_weekend_and_are_session_closes(self) -> None:
        points = build_xnys_scenario_points(start_session=date(2026, 9, 11), planned_hold_sessions=3)
        self.assertEqual([item.sessions_elapsed for item in points], [1, 2, 3])
        self.assertEqual([item.as_of_utc.date() for item in points], [
            date(2026, 9, 14), date(2026, 9, 15), date(2026, 9, 16)
        ])
        self.assertTrue(all(item.as_of_utc.hour == 20 for item in points))

    def test_scenario_timing_must_be_monotonic(self) -> None:
        at = datetime(2026, 9, 15, 20, tzinfo=UTC)
        points = (
            ScenarioPoint(ScenarioTiming.EARLY, 10, at),
            ScenarioPoint(ScenarioTiming.MID, 5, at + timedelta(days=1)),
            ScenarioPoint(ScenarioTiming.LATE, 1, at + timedelta(days=2)),
        )
        with self.assertRaisesRegex(ValueError, "sessions must increase"):
            evaluate_deterministic_scenarios(
                option_side="CALL", strike=100,
                expiration_utc=datetime(2026, 10, 16, 20, tzinfo=UTC),
                target_spot=110, invalidation_spot=95, base_iv=0.35,
                scenario_points=points, entry_ask=4, risk_free_rate=0.04,
                dividend_yield=0.01,
            )


class DeterministicValuationPersistenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.registry = CanonicalRegistry(self.root / "control_plane.sqlite")
        self.registry.initialise()
        self.registry.register_run(RUN_ID, "EVENING", SESSION)
        self.store = OptionLiquidityLifecycleStore(self.registry)
        self.store.initialise()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _thesis(self, direction: str = "CALL") -> UnderlyingThesisRef:
        target, invalidation = ((110.0, 95.0) if direction == "CALL" else (90.0, 105.0))
        thesis_id = f"ABC-{direction}-DOI5"
        self.store.record_thesis_event(
            thesis_id=thesis_id, event_key="DOI5-ORIGIN", run_id=RUN_ID,
            ticker="ABC", direction=direction, thesis_state=ThesisState.ACTIVE,
            monitor_state=MonitorState.ACTIVE, reason_code="GOVERNED_THESIS",
            structural_target=target, invalidation_spot=invalidation,
            horizon_end_date=date(2026, 10, 1),
        )
        return UnderlyingThesisRef(
            thesis_id=thesis_id, thesis_version=1, ticker="ABC",
            governed_direction=direction, origin_spot=100,
            origin_timestamp_utc=CUTOFF - timedelta(hours=1),
            target_spot=target, invalidation_spot=invalidation,
            planned_hold_sessions=10, planned_hold_source="HORIZON_ROUTER",
            evidence_cutoff_utc=CUTOFF,
        )

    @staticmethod
    def _row(side: str, strike: float, **overrides: object) -> dict[str, object]:
        row: dict[str, object] = {
            "symbol": _symbol(side, strike), "right": side[0], "strike": strike,
            "expiration_date": "2026-10-16", "underlying_price": 100.0,
            "bid": 2.0, "ask": 2.2, "bid_size": 3, "ask_size": 4,
            "volume": 10, "open_interest": 100, "iv": 0.40, "delta": 0.45,
            "quote_timestamp_utc": "2026-09-10T20:00:00Z",
        }
        row.update(overrides)
        return row

    def _observation(self, rows: list[dict[str, object]]) -> GovernedOptionObservation:
        encoded = json.dumps(rows, sort_keys=True, separators=(",", ":")).encode()
        path = self.root / "chain.json"
        path.write_bytes(encoded)
        dataset_id = hashlib.sha256(encoded).hexdigest()
        self.registry.register_dataset(DatasetRecord(
            dataset_id=dataset_id, dataset_type=DatasetType.OPTION_CHAIN,
            instrument_id="ABC", session_date=SESSION,
            scope=DataScope(start_date=SESSION, end_date=SESSION, dte_min=1,
                            dte_max=90, sides=("CALL", "PUT")),
            provider="MARKETDATA", content_hash=hashlib.sha256(encoded).hexdigest(),
            completeness_status=CompletenessStatus.COMPLETE, storage_uri=str(path),
            observed_at=CUTOFF, as_of=CUTOFF,
            adjustment_convention="RAW_OPTION_CONTRACT",
            schema_version="option_chain_v2", source_run_id=RUN_ID,
        ))
        return GovernedOptionObservation(
            ticker="ABC", observation_kind=OptionObservationKind.COMPLETED_SESSION,
            dataset_id=dataset_id, provider="MARKETDATA", as_of_utc=CUTOFF,
            frame=pd.DataFrame(rows), resolution="CANONICAL_REUSE",
            acquisition=ObservationAcquisitionDecision(False, "REUSE_CANONICAL_EVIDENCE"),
            physical_fetch_count=0,
        )

    def _evaluate(self, direction: str, rows: list[dict[str, object]]):
        observation = self._observation(rows)
        family = ThesisConditionedContractFamilyGenerator(self.store).generate(
            thesis=self._thesis(direction), observation=observation, run_id=RUN_ID
        )
        service = DeterministicContractValuationService(
            self.store, risk_free_rate=0.04, dividend_yield=0.01
        )
        return service, observation, family, service.evaluate_family(
            generated_family=family, observation=observation
        )

    def test_every_admitted_quote_state_is_persisted_not_discarded(self) -> None:
        rows = [
            self._row("CALL", 100),
            self._row("CALL", 105, bid=0, ask=1, open_interest=0, volume=0),
            self._row("CALL", 110, bid=None, ask=None, bid_size=None, ask_size=None),
        ]
        _, _, family, result = self._evaluate("CALL", rows)
        self.assertEqual(result.summary.family_candidates, 3)
        self.assertEqual(result.summary.assessed_contracts, 3)
        self.assertEqual((result.summary.two_sided, result.summary.one_sided, result.summary.no_quote), (1, 1, 1))
        self.assertEqual(result.summary.scenario_values, 54)
        self.assertEqual(result.summary.utility_available, 2)
        self.assertEqual(len(self.store.assessments_for_family(family.family.family_id)), 3)

    def test_canonical_implied_vol_alias_is_consumed(self) -> None:
        row = self._row("CALL", 100)
        row["implied_vol"] = row.pop("iv")
        _, _, _, result = self._evaluate("CALL", [row])
        self.assertEqual(result.summary.scenario_values, 18)
        self.assertEqual(result.summary.utility_available, 1)

    def test_freshly_acquired_upstream_observation_is_accepted_without_service_fetch(self) -> None:
        observation = replace(
            self._observation([self._row("CALL", 100)]),
            physical_fetch_count=1,
        )
        family = ThesisConditionedContractFamilyGenerator(self.store).generate(
            thesis=self._thesis("CALL"), observation=observation, run_id=RUN_ID
        )
        result = DeterministicContractValuationService(
            self.store, risk_free_rate=0.04, dividend_yield=0.01
        ).evaluate_family(generated_family=family, observation=observation)
        self.assertEqual(
            result.results[0].assessment.metadata["upstream_physical_fetch_count"], 1
        )
        self.assertEqual(
            result.results[0].assessment.metadata["valuation_service_physical_fetch_count"], 0
        )

    def test_persisted_assessments_have_exact_lineage_and_no_authority_or_probability(self) -> None:
        _, observation, family, result = self._evaluate("PUT", [self._row("PUT", 100)])
        item = result.results[0]
        assessment = item.assessment
        self.assertEqual(assessment.contract_symbol, _symbol("PUT", 100))
        self.assertEqual(assessment.input_dataset_ids, (observation.dataset_id,))
        self.assertFalse(assessment.probabilities_calibrated)
        self.assertIsNone(assessment.p_liquidity_1d)
        self.assertIsNone(assessment.p_positive_return_before_horizon)
        self.assertIsNone(assessment.expected_net_return)
        self.assertFalse(assessment.can_change_direction)
        self.assertFalse(assessment.can_invalidate_thesis)
        self.assertFalse(assessment.can_grant_capital)
        self.assertFalse(assessment.metadata["utility_is_probability"])
        self.assertEqual(assessment.metadata["valuation_service_physical_fetch_count"], 0)
        self.assertEqual(assessment.metadata["upstream_physical_fetch_count"], 0)
        self.assertEqual(assessment.family_id, family.family.family_id)

    def test_replay_is_idempotent(self) -> None:
        service, observation, family, first = self._evaluate("CALL", [self._row("CALL", 100)])
        second = service.evaluate_family(generated_family=family, observation=observation)
        self.assertEqual(first.results[0].assessment.assessment_id, second.results[0].assessment.assessment_id)
        self.assertTrue(second.results[0].observation_reused)
        self.assertTrue(second.results[0].assessment_reused)

    def test_corporate_action_reduces_applicability_without_removing_contract(self) -> None:
        service, observation, family, _ = self._evaluate("CALL", [self._row("CALL", 100)])
        result = service.evaluate_family(
            generated_family=family, observation=observation,
            corporate_action_flag=True,
        )
        self.assertEqual(result.summary.assessed_contracts, 1)
        self.assertEqual(result.summary.out_of_distribution, 1)
        self.assertEqual(
            result.results[0].assessment.applicability_state,
            ModelApplicabilityState.OUT_OF_DISTRIBUTION,
        )
        self.assertIn(
            "CORPORATE_ACTION_MODEL_APPLICABILITY_REDUCED",
            result.results[0].valuation.disclosures,
        )
        self.assertFalse(result.results[0].assessment.can_invalidate_thesis)


if __name__ == "__main__":
    unittest.main()
