from __future__ import annotations

from datetime import datetime, timedelta, timezone
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from contracts.core_authority_policy import assert_frozen_thesis_fields
from contracts.long_option_policy import (
    evaluate_execution_viability,
    quote_age_seconds,
    quote_spread_fraction,
    quote_spread_percent,
)
from macro_horizon_router import route_signals_by_horizon
from regime_threshold_injector import apply_regime_to_config
from vanguard.layer2_statistical.state_calculator import StateVectorCalculator


class Phase2AuthorityTests(unittest.TestCase):
    def test_macro_snapshot_cannot_change_discovery_thresholds(self) -> None:
        baseline = SimpleNamespace(
            tier1_min=50.0,
            tier2_min=35.0,
            tier3_min=25.0,
            compression_max=0.85,
            extreme_compression=0.60,
            min_avg_vol20=500_000,
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "macro.json"
            path.write_text(
                json.dumps({
                    "regime_state": "RISK_OFF",
                    "risk_on_off_switch": "RISK_OFF",
                    "vol_mode": "FEAR_SPIKE",
                }),
                encoding="utf-8",
            )
            result = apply_regime_to_config(baseline, path)
        self.assertEqual((result.tier1_min, result.tier2_min, result.tier3_min), (50.0, 35.0, 25.0))
        self.assertEqual(result.compression_max, 0.85)
        self.assertEqual(result.min_avg_vol20, 500_000)
        self.assertEqual(result.macro_authority, "ADVISORY_ONLY")
        self.assertEqual(result.macro_core_effective_delta, 0.0)

    def test_discovery_tier_and_prior_are_macro_invariant(self) -> None:
        from avshunter_discovery_ULTIMATE import (
            UltimateConfig,
            apply_state_prior_adjustment,
            assign_tier,
        )

        cfg = UltimateConfig()
        # The tier function has no macro parameter by contract.
        self.assertEqual(assign_tier(50.0, 50.0, 60.0, cfg), 1)
        risk_on = apply_state_prior_adjustment(70.0, "C", "RISK_ON", "MID")
        risk_off = apply_state_prior_adjustment(70.0, "C", "RISK_OFF", "MID")
        self.assertEqual(risk_on, risk_off)

    def test_vanguard_quant_regime_is_independent_of_macro_payload(self) -> None:
        calculator = StateVectorCalculator()
        bullish = SimpleNamespace(vix=10.0, vix_history=[30, 20, 10], spy_trend="UP")
        bearish = SimpleNamespace(vix=40.0, vix_history=[10, 20, 40], spy_trend="DOWN")
        self.assertEqual(calculator._calculate_macro_regime(bullish), calculator._calculate_macro_regime(bearish))
        self.assertEqual(calculator._calculate_macro_regime(bullish)["regime"], "TRANSITIONAL")

    def test_horizon_routes_without_macro_and_macro_cannot_change_result(self) -> None:
        signal = {
            "ticker": "AAPL",
            "instrument": "LONG_CALL",
            "dte": 30,
            "expected_holding_days": 7,
        }
        without_macro = route_signals_by_horizon(None, [signal])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "macro.json"
            path.write_text(json.dumps({"regime_state": "CRISIS"}), encoding="utf-8")
            with_macro = route_signals_by_horizon(path, [signal])
        first = without_macro["6_10d"][0]
        second = with_macro["6_10d"][0]
        self.assertEqual((first.horizon, first.action, first.size_multiplier),
                         (second.horizon, second.action, second.size_multiplier))
        self.assertEqual(without_macro["blocked"], [])

    def test_options_verdict_is_invariant_to_legacy_rr(self) -> None:
        from scripts.avshunter_options_intelligence import derive_verdict

        context = {
            "intent": "BUY",
            "direction": "CALL",
            "near_event": False,
            "structural_target": 110.0,
        }
        iv_context = {"iv_regime": "NORMAL"}
        contract = {
            "dte": 30,
            "expiry": "2026-10-01",
            "bid": 2.0,
            "ask": 2.1,
            "mark": 2.05,
            "spread_pct": quote_spread_fraction(2.0, 2.1),
            "mark_synthetic": False,
        }
        low = derive_verdict(
            90, context, iv_context,
            {"theta_drag_pct": 10, "option_value_at_target": 5, "rr_options": -5},
            [], contract=contract,
        )
        high = derive_verdict(
            90, context, iv_context,
            {"theta_drag_pct": 10, "option_value_at_target": 5, "rr_options": 5},
            [], contract=contract,
        )
        self.assertEqual(low, high)
        self.assertEqual(low[0], "EXECUTE")

    def test_eod_tier_is_invariant_to_legacy_rr(self) -> None:
        from eod_candidate_engine import classify_tier

        base = {
            "options_score": 50,
            "composite": 65,
            "eil_v3_verdict": "EXECUTE",
            "trigger_quality": "STRONG",
            "trigger_go_eligible": "TRUE",
            "catalyst_trade_class": "DATED_CATALYST_CONFIRMED",
            "catalyst_data_quality": "CONFIRMED",
            "sb_conv_score": 3,
            "direction_conflict_status": "RESOLVED",
        }
        negative = classify_tier({**base, "rr": -100, "rr_underlying": -100})
        positive = classify_tier({**base, "rr": 100, "rr_underlying": 100})
        self.assertEqual(negative, positive)
        self.assertEqual(negative, "A")
        tier_b = {**base, "options_score": 30, "composite": 52, "eil_v3_verdict": "WATCHLIST"}
        self.assertEqual(
            classify_tier({**tier_b, "rr_underlying": -100}),
            classify_tier({**tier_b, "rr_underlying": 100}),
        )
        self.assertEqual(classify_tier(tier_b), "B")

    def test_quote_spread_has_one_mid_denominator(self) -> None:
        self.assertAlmostEqual(quote_spread_fraction(1.0, 1.2), 0.2 / 1.1)
        self.assertAlmostEqual(quote_spread_percent(1.0, 1.2), (0.2 / 1.1) * 100.0)
        self.assertIsNone(quote_spread_fraction(1.2, 1.0))

    def test_quote_age_is_measured_not_fabricated(self) -> None:
        now = datetime(2026, 9, 3, 12, 0, tzinfo=timezone.utc)
        observed = now - timedelta(seconds=75)
        self.assertAlmostEqual(quote_age_seconds(observed.isoformat(), as_of_utc=now), 75.0)
        self.assertIsNone(quote_age_seconds(None, as_of_utc=now))

    def test_execution_viability_excludes_scenario_economics(self) -> None:
        hydrated = {
            "selected_structure_hydration_status": "COMPLETE",
            "selected_structure": "LONG_SINGLE",
            "selected_contract_symbol": "AAPL261016C00200000",
            "selected_long_leg": {"bid": 2.0, "ask": 2.1},
        }
        result = evaluate_execution_viability({}, hydrated)
        self.assertEqual(result["execution_viability_state"], "EXECUTABLE_QUOTE")
        self.assertTrue(result["execution_viability_eligible"])
        forbidden_prefixes = ("rr_", "ev_", "monetisability_", "scenario_")
        self.assertFalse(any(key.lower().startswith(forbidden_prefixes) for key in result))

    def test_non_directional_signal_is_reconciled_as_blocked(self) -> None:
        routed = route_signals_by_horizon(
            None,
            [{
                "ticker": "AAPL", "instrument": "STRANGLE", "dte": 30,
                "expected_holding_days": 7,
            }],
        )
        self.assertEqual(sum(len(rows) for rows in routed.values()), 1)
        blocked = routed["blocked"][0]
        self.assertEqual(blocked.instrument, "STRANGLE")
        self.assertEqual(
            blocked.block_reason,
            "NON_DIRECTIONAL_NOT_ROUTABLE:STRANGLE",
        )

    def test_frozen_thesis_guard_allows_annotation_and_rejects_mutation(self) -> None:
        thesis = {
            "governed_direction": "PUT",
            "planned_hold_sessions": 10,
            "target_spot": 90.0,
            "invalidation_spot": 105.0,
        }
        assert_frozen_thesis_fields(thesis, {**thesis, "current_underlying_price": 98.0})
        with self.assertRaisesRegex(ValueError, "FROZEN_THESIS_MUTATION"):
            assert_frozen_thesis_fields(thesis, {**thesis, "governed_direction": "CALL"})

    def test_lab_fallback_is_fail_closed(self) -> None:
        lab_path = REPO / "intelligence-lab" / "intelligence_lab.py"
        spec = importlib.util.spec_from_file_location(
            "intelligence_lab_phase2_fail_closed", lab_path
        )
        lab = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(lab)
        with tempfile.TemporaryDirectory() as directory:
            run_id = "20990101_235959"
            lab.RUNS_DIR = Path(directory) / "runs"
            lab._run_cache.clear()
            eil = (
                lab.RUNS_DIR / run_id / "superbrain"
                / f"eil_enriched_{run_id}.csv"
            )
            eil.parent.mkdir(parents=True)
            eil.write_text(
                "ticker,direction,lab_verdict\nAAA,CALL,GO\n",
                encoding="utf-8",
            )

            result = lab._load_run(run_id, force_reload=True)

        self.assertEqual(result["signals"], [])
        self.assertEqual(
            result["lab_signal_source"],
            "GOVERNED_BOOK_UNAVAILABLE_FAIL_CLOSED",
        )
        self.assertTrue(result["lab_fail_closed"])
        self.assertFalse(result["run_health"]["ok"])

    def test_interpreter_production_path_is_manifest_only(self) -> None:
        source = (REPO / "pipeline_interpreter" / "pipeline_interpreter_commands.py").read_text(encoding="utf-8")
        self.assertIn("resolve_interpreter_run()", source)
        self.assertIn("resolve_interpreter_evidence(ticker", source)
        self.assertIn("[RETIRED] /live cannot call a market-data provider", source)
        self.assertNotIn("from live_market_reader import", source)
        self.assertNotIn("from alternative_contract_selector import", source)

    def test_morning_does_not_fabricate_zero_quote_age(self) -> None:
        source = (REPO / "morning_gate.py").read_text(encoding="utf-8")
        self.assertNotIn("quote_age_seconds=0.0", source)
        self.assertIn("quote_age_seconds(", source)

    def test_execution_gate_no_longer_uses_scenario_monetisability(self) -> None:
        source = (REPO / "execution_gate.py").read_text(encoding="utf-8")
        body = source[source.index("def execution_gate("):]
        self.assertNotIn("monetisability_state", body)
        self.assertIn("execution_viability_state", body)


if __name__ == "__main__":
    unittest.main()
