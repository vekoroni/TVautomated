from __future__ import annotations
from datetime import datetime, timezone
import json, math
from pathlib import Path

import pytest

from canonical_data.market_rate_observation import load_market_rate, resolve_market_rate
from canonical_data.decision_outcome_ledger import (
    DecisionOutcomeLedger, decision_record_v2, fill_record_v1,
)
from domain.contract_economics_v2 import evaluate_contract_economics_v2
from domain.deterministic_option_valuation import ScenarioPoint, ScenarioTiming
from domain.lab_signal_book_v4 import project_lab_signal_v4
from domain.macro_advisory_context import project_usmi_context
from domain.presentation import derive_opportunity_presentation_v1
from domain.preferred_contract_hysteresis import decide_preferred_contract
from domain.quote_units import resolve_spread
from domain.reachability import assess_reachability
from domain.structure_evidence import derive_structure_evidence
from domain.volatility_budget import calculate_volatility_budget, checkpoint_fields
from tools.validate_forecast_vol import build_report

ROOT = Path(__file__).resolve().parents[1]


class TestStage2UnitAndProperty:
    def test_cumulative_expected_move_contract(self):
        fields = checkpoint_fields(.40)
        assert fields["expected_move_10d_fraction"] / fields["expected_move_5d_fraction"] == pytest.approx(math.sqrt(2))
        assert fields["expected_move_20d_fraction"] / fields["expected_move_5d_fraction"] == pytest.approx(2)
        assert fields["vol_validation_state"] == "UNVALIDATED"

    @pytest.mark.parametrize("hold", range(1, 21))
    @pytest.mark.parametrize("vol", [.1, .4, 1.2])
    def test_arbitrary_hold_property(self, hold, vol):
        value = calculate_volatility_budget(vol, hold)
        assert value.expected_move_fraction == pytest.approx(vol * math.sqrt(hold / 252))
        assert value.bias_multiplier_applied is False

    def test_missing_and_defective_vol_never_become_zero(self):
        assert calculate_volatility_budget(None, 5).expected_move_fraction is None
        assert calculate_volatility_budget(0, 5).quality_state == "DATA_DEFECT"

    def test_spread_units_are_explicit(self):
        assert resolve_spread({"spread_fraction_mid": .12}).spread_pct_of_mid == 12
        assert resolve_spread({"spread_pct_of_mid": 12}).spread_fraction_mid == .12
        assert resolve_spread({"spread_pct": 12}).quality_state == "NOT_EVALUATED_UNIT_AMBIGUOUS"
        assert resolve_spread({"bid": 1, "ask": 1.2}).spread_fraction_mid == pytest.approx(.2/1.1)

    def test_forecast_validation_cannot_self_activate(self):
        import pandas as pd
        report = build_report(pd.DataFrame({
            "forecast_vol_annual_fraction":[.4,.5],
            "realised_vol_annual_fraction":[.3,.6],
            "hidden_state_label":["A","A"],
        }), minimum_n=2)
        assert report["overall"]["eligible_to_validate"] is True
        assert report["validation_state"] == "UNVALIDATED"
        assert report["bias_multiplier_applied"] is False

    def test_bias_requires_report_holdout_and_owner_approval(self):
        incomplete = calculate_volatility_budget(
            .40, 5, bias_multiplier=.8, validation_state="VALIDATED",
            multiplier_approved=True,
        )
        assert incomplete.bias_multiplier_applied is False
        assert incomplete.bias_multiplier == 1.0
        accepted = calculate_volatility_budget(
            .40, 5, bias_multiplier=.8, validation_state="VALIDATED",
            multiplier_approved=True, validation_report_id="AVS-VAL-001-R1",
            held_out_validation_passed=True,
        )
        assert accepted.bias_multiplier_applied is True
        assert accepted.bias_multiplier == .8


def _points():
    return tuple(ScenarioPoint(t, n, datetime(2026, 9, d, 20, tzinfo=timezone.utc))
                 for t, n, d in ((ScenarioTiming.EARLY,2,14),(ScenarioTiming.MID,4,16),(ScenarioTiming.LATE,5,17)))


class TestStage3Economics:
    def test_governed_profit_floor_is_approved_and_lineaged(self):
        constants = json.loads(
            (ROOT / "config" / "governed_constants_v1.json").read_text(
                encoding="utf-8"
            )
        )
        policy = constants["contract_economics"]
        assert policy["profit_floor"] == .25
        assert policy["profit_floor_approved"] is True
        assert policy["profit_floor_approval_id"]
        result = evaluate_contract_economics_v2(
            option_side="CALL", origin_spot=100, strike=100,
            expiration_utc=datetime(2026,10,16,20,tzinfo=timezone.utc),
            base_iv=.3, entry_bid=2, entry_ask=2.2, risk_free_rate=.04,
            dividend_yield=0, scenario_points=_points(),
            favourable_1sigma=106, favourable_2sigma=112,
            reachable_spot=109, structural_target=109, invalidation_spot=95,
            profit_floor=policy["profit_floor"],
            profit_floor_approved=policy["profit_floor_approved"],
            profit_floor_approval_id=policy["profit_floor_approval_id"],
        )
        assert result.monetisability_state != "INDETERMINATE"
        assert result.profit_floor_applied == .25
        assert result.profit_floor_approved is True
        assert result.profit_floor_approval_id == "ACK-20260912-AVS-FIX-002"
    @pytest.mark.parametrize("side,one,two,target,stop", [
        ("CALL",106,112,109,95), ("PUT",94,88,91,105),
    ])
    def test_call_put_scenario_grid_and_no_probability(self, side, one, two, target, stop):
        result = evaluate_contract_economics_v2(
            option_side=side, origin_spot=100, strike=100,
            expiration_utc=datetime(2026,10,16,20,tzinfo=timezone.utc), base_iv=.3,
            entry_bid=2, entry_ask=2.2, risk_free_rate=.04, dividend_yield=0,
            scenario_points=_points(), favourable_1sigma=one, favourable_2sigma=two,
            reachable_spot=target, structural_target=target, invalidation_spot=stop,
        )
        assert len(result.scenarios) == 54
        assert result.ranking_score_kind == "DETERMINISTIC_UTILITY"
        assert result.deterministic_utility is not None
        assert result.monetisability_state == "INDETERMINATE"
        assert result.monetisability_reason == "PROFIT_FLOOR_NOT_APPROVED"

    def test_horizon_limited_is_retained_indeterminate(self):
        result = evaluate_contract_economics_v2(
            option_side="CALL", origin_spot=100, strike=100,
            expiration_utc=datetime(2026,9,16,20,tzinfo=timezone.utc), base_iv=.3,
            entry_bid=2, entry_ask=2.2, risk_free_rate=.04, dividend_yield=0,
            scenario_points=_points(), favourable_1sigma=103, favourable_2sigma=106,
            reachable_spot=104, structural_target=110, invalidation_spot=95,
        )
        assert result.applicability == "HORIZON_LIMITED"
        assert result.monetisability_state == "INDETERMINATE"


class TestStage4And5Integration:
    def test_preferred_contract_policy_is_approved_and_versioned(self):
        constants = json.loads(
            (ROOT / "config" / "governed_constants_v1.json").read_text(
                encoding="utf-8"
            )
        )
        policy = constants["preferred_contract"]
        assert policy == {
            "margin_abs": .05,
            "margin_relative": .10,
            "approved": True,
            "approval_id": "ACK-20260912-AVS-FIX-002",
            "configuration_owner": "ACK",
            "utility_unit": "NET_RETURN_FRACTION",
            "version": "hysteresis_v1",
        }

    def test_hysteresis_uses_greater_absolute_or_relative_margin(self):
        assert decide_preferred_contract(incumbent_utility=1.0,challenger_utility=1.09,
                                         challenger_quality="PASS").switch is False
        assert decide_preferred_contract(incumbent_utility=1.0,challenger_utility=1.11,
                                         challenger_quality="PASS").switch is True
        assert decide_preferred_contract(incumbent_utility=1.0,challenger_utility=.5,
                                         challenger_quality="FAIL",incumbent_state="EXPIRED").switch is True

    def test_decision_and_fill_are_separate_append_only_events(self, tmp_path):
        ledger = DecisionOutcomeLedger(tmp_path / "ledger.sqlite")
        decision = decision_record_v2(run_id="R1",ticker="ABC",thesis_id="T1",
            occurred_at_utc="2026-09-12T10:00:00Z",preferred_assessment_id="A1",
            presentation_summary="Monitor exact contract",human_response="TAKEN")
        assert ledger.append(decision)
        fill = fill_record_v1(run_id="R1",ticker="ABC",thesis_id="T1",
            occurred_at_utc="2026-09-12T10:01:00Z",occ_symbol="ABC261016C00100000",
            price=2.1,quantity=2,side="BUY",source="MANUAL_CONFIRMATION",previous_event_id=decision.event_id)
        assert ledger.append(fill)
        assert ledger.event_counts("R1") == {"FILL_RECORDED":1,"PRESENTATION_DECISION":1}

    def test_pipeline_is_capital_agnostic(self):
        constants = json.loads(
            (ROOT / "config" / "governed_constants_v1.json").read_text(
                encoding="utf-8"
            )
        )
        assert "capacity" not in constants
        projected = project_lab_signal_v4({
            "thesis_state": "ACTIVE",
            "doi_monetisability_state": "SCENARIO_MONETISABLE",
            "execution_state": "EXECUTION_REVIEWABLE",
            "capacity_size_state": "AFFORDABLE",
            "capacity_contracts_at_budget": 7,
        })
        assert not any("capacity" in field for field in projected)
        source = (ROOT / "contracts" / "lab_control.py").read_text(
            encoding="utf-8"
        )
        assert "suggest_capacity" not in source
        assert "capacity_" not in source
        assert 'row["position_size_display"] = "HUMAN DETERMINED"' in source
        ui_source = (ROOT / "intelligence-lab" / "intelligence_lab.py").read_text(
            encoding="utf-8"
        )
        assert 'out["position_size_display"] = "HUMAN DETERMINED"' in ui_source
        assert 'out["sb_position_size_pct"] = None' in ui_source

    def test_presentation_cannot_claim_execution(self):
        value = derive_opportunity_presentation_v1(thesis_state="ACTIVE",contract_state="SCENARIO_MONETISABLE",
                                                   execution_state="EXECUTION_QUOTE_STALE_MONITOR",macro_context="SUPPORTIVE")
        assert value.summary_state == "MONITOR"
        assert "EXECUTION_REVIEW" not in value.summary_state
        row = project_lab_signal_v4({"thesis_state":"ACTIVE","doi_monetisability_state":"SCENARIO_MONETISABLE",
                                     "execution_state":"EXECUTION_QUOTE_STALE_MONITOR"})
        assert row["lab_schema_version"] == "lab_signal_book_v4"

    def test_v4_contract_has_no_risk_reward_field(self):
        source = (ROOT / "contracts" / "lab_control.py").read_text(encoding="utf-8")
        assert 'if field.startswith("rr_")' in source
        assert "risk_reward" not in project_lab_signal_v4({})

    def test_structure_and_macro_are_advisory(self):
        assert derive_structure_evidence(hidden_state_label="LOW_ENERGY",phase="C",trigger_primary="X")["structure_evidence_state"] == "NO_EDGE"
        result = project_usmi_context(packet={
                                      "contract_version": "us_money_index_v1_0",
                                      "sector_routing": {
                                          "CALL": {"FINANCIALS": {
                                              "alignment": "ALIGNED", "priority": 1,
                                              "reason": "TEST_ROUTE",
                                          }},
                                          "PUT": {},
                                      },
                                      "scenarios": {}, "metrics": {},
                                      },
                                      sector="Financials",industry="Banks",direction="CALL")
        assert result["usmi_sector_alignment"] == "ALIGNED"
        assert result["usmi_alignment_priority"] == 1
        assert result["usmi_routing_key"] == "FINANCIALS_CALL"
        assert result["usmi_authority"] == "ADVISORY_ONLY"


class TestStoredRunReplay:
    @pytest.mark.parametrize("run_id", ["20260910_150045", "20260911_115904"])
    def test_stored_macro_rate_and_options_population_replay(self, run_id):
        run = ROOT / "data" / "output" / "runs" / run_id
        macro = load_market_rate(run / "macro_snapshot.json")
        assert macro.quality_state == "PASS"
        assert 0 < macro.rate_annual_fraction < .25
        source = run / "options" / f"options_intelligence_{run_id}.csv"
        assert source.is_file()
        import pandas as pd
        sample = pd.read_csv(source, usecols=["ticker","governed_direction","planned_hold_sessions"], low_memory=False)
        assert len(sample) > 100
        directed = sample[sample.governed_direction.isin(["CALL","PUT"])]
        assert not directed.empty
        assert directed.planned_hold_sessions.between(1,20).all()
        qomega = pd.read_csv(
            run / "qomega" / f"garch_forecasts_{run_id}.csv",
            usecols=["ticker", "l3_forward_realised_vol"], low_memory=False,
        ).drop_duplicates("ticker")
        replay = directed.drop_duplicates("ticker").merge(qomega, on="ticker", how="left")
        assert replay.l3_forward_realised_vol.notna().mean() == 1.0
        assert replay.l3_forward_realised_vol.gt(0).all()

    def test_orchestrator_wires_macro_and_governed_constants_into_doi(self):
        source = (ROOT / "intelligent_orchestrator.py").read_text(encoding="utf-8")
        section = source[source.index("def run_dynamic_options_intelligence"):source.index("def run_options_intelligence")]
        assert "macro_path=" in section
        assert "governed_constants_path=" in section
