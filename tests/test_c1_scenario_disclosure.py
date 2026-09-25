"""C1 — scenario values on every row, with conspicuous assumptions (ACK, 25 Sep 2026).

Design: Enhancements/research/rca/C1_SCENARIO_DISCLOSURE_RCA_AND_DESIGN_20260925.md

Business rules (ACK, reviewer amendments C1-C2):
- The six ALG-04 headline payoffs (LATE timing, BASE IV) are flat columns on the row, for the selected contract only.
- Every row says what was assumed: friction model and cap, vol-budget validation state, pricing model version.
- The break-even probability is review information and a stated lower bound, never a gate.
- The legacy rr_predicted is relabelled as intrinsic-at-structural-target; nothing here is an expected return.
"""

from __future__ import annotations

import json

from contracts.lab_control import FINAL_BOOK_FIELDS, scenario_disclosure_from_row

SYMBOL = "NVS261120P00145000"


def _grid(contract=SYMBOL, values=None):
    """A 54-scenario DOI grid; LATE/BASE net returns from `values`, other cells filled with sentinels."""
    values = values or {"FLAT": -0.40, "FAVOURABLE_1SIGMA": 0.35, "FAVOURABLE_2SIGMA": 1.20,
                        "REACHABLE": 0.80, "STRUCTURAL_DISCLOSURE": 2.10, "ADVERSE_INVALIDATION": -0.70}
    out = []
    for path, v in values.items():
        for timing in ("EARLY", "MID", "LATE"):
            for stress in ("CONTRACTED", "BASE", "EXPANDED"):
                net = v if (timing == "LATE" and stress == "BASE") else (
                    v - 0.10 if stress == "CONTRACTED" else v + 0.10 if stress == "EXPANDED" else v + 0.01)
                out.append({"scenario_id": f"{path}:{timing}:{stress}", "path": path, "timing": timing,
                            "iv_stress": stress, "net_return_fraction": net, "spot": 143.57})
    return json.dumps(out)


def _row(**over):
    base = {"ticker": "NVS", "selected_contract_symbol": SYMBOL, "doi_governed_contract_symbol": SYMBOL,
            "doi_scenarios_json": _grid(), "doi_assessment_calculation_version": "doi-deterministic-scenario-v1:4431",
            "doi_projection_state": "EVALUATED", "doi_projection_reason": "", "rr_premium_expected": 1.94}
    base.update(over)
    return base


def test_the_six_late_base_payoffs_are_flat_columns_with_their_assumptions():
    d = scenario_disclosure_from_row(_row())
    assert d["scenario_state"] == "AVAILABLE" and d["scenario_contract_symbol"] == SYMBOL
    assert d["payoff_flat_net_return_fraction"] == -0.40
    assert d["payoff_1sigma_net_return_fraction"] == 0.35
    assert d["payoff_2sigma_net_return_fraction"] == 1.20
    assert d["payoff_reachable_net_return_fraction"] == 0.80
    assert d["payoff_structural_net_return_fraction"] == 2.10
    assert d["payoff_invalidation_net_return_fraction"] == -0.70
    assert d["payoff_reachable_iv_stress_range"] == [0.70, 0.90]
    assert d["scenario_basis"] == "LATE_TIMING_BASE_IV_AT_GOVERNED_TIME_STOP"
    assert d["scenario_pricing_model_version"] == "doi-deterministic-scenario-v1:4431"
    assert d["friction_assumption"] == "CURRENT_SPREAD_PROXY_CAPPED" and d["friction_spread_cap"] == 0.15
    assert d["scenario_valuation_version"] == "scenario_valuation_v2"
    assert d["volatility_budget_validation_state"] == "UNVALIDATED" and d["volatility_budget_bias_multiplier"] == 1.0
    assert d["scenario_is_expected_return"] is False


def test_the_breakeven_is_a_stated_two_outcome_lower_bound():
    d = scenario_disclosure_from_row(_row())
    assert abs(d["breakeven_p_target_two_outcome"] - (0.70 / (0.80 + 0.70))) < 1e-9
    assert d["breakeven_basis"] == "TWO_OUTCOME_LOWER_BOUND_REACHABLE_VS_INVALIDATION"


def test_a_reachable_payoff_below_the_invalidation_payoff_has_no_breakeven():
    d = scenario_disclosure_from_row(_row(doi_scenarios_json=_grid(values={
        "FLAT": -0.4, "FAVOURABLE_1SIGMA": -0.5, "FAVOURABLE_2SIGMA": -0.3, "REACHABLE": -0.9,
        "STRUCTURAL_DISCLOSURE": 0.1, "ADVERSE_INVALIDATION": -0.7})))
    assert d["breakeven_p_target_two_outcome"] is None


def test_no_scenarios_is_not_assessed_with_the_doi_reason():
    d = scenario_disclosure_from_row(_row(doi_scenarios_json="", doi_projection_state="NOT_EVALUATED",
                                          doi_projection_reason="DOI_FAMILY_NOT_RANKED"))
    assert d["scenario_state"] == "NOT_ASSESSED" and d["scenario_reason"] == "DOI_FAMILY_NOT_RANKED"
    assert d["payoff_flat_net_return_fraction"] is None and d["breakeven_p_target_two_outcome"] is None
    assert d["friction_assumption"] == "CURRENT_SPREAD_PROXY_CAPPED"      # the assumption labels are always stated


def test_scenarios_for_another_contract_are_a_mismatch_not_a_value():
    d = scenario_disclosure_from_row(_row(doi_governed_contract_symbol="NVS261120P00140000"))
    assert d["scenario_state"] == "CONTRACT_MISMATCH"
    assert d["payoff_reachable_net_return_fraction"] is None


def test_no_contract_is_not_applicable():
    d = scenario_disclosure_from_row(_row(selected_contract_symbol="", doi_governed_contract_symbol="", doi_scenarios_json=""))
    assert d["scenario_state"] == "NOT_APPLICABLE"


def test_the_legacy_r_is_relabelled_not_changed():
    d = scenario_disclosure_from_row(_row())
    assert d["legacy_rr_basis"] == "INTRINSIC_AT_STRUCTURAL_TARGET_NO_TIME_VALUE_NO_FRICTION"
    assert d["legacy_rr_is_expected_return"] is False


def test_the_fields_are_in_the_book():
    for field in ("scenario_state", "scenario_reason", "scenario_contract_symbol", "scenario_basis",
                  "payoff_flat_net_return_fraction", "payoff_reachable_net_return_fraction",
                  "payoff_invalidation_net_return_fraction", "friction_assumption", "friction_spread_cap",
                  "volatility_budget_validation_state", "breakeven_p_target_two_outcome", "breakeven_basis",
                  "scenario_is_expected_return", "legacy_rr_basis", "legacy_rr_is_expected_return"):
        assert field in FINAL_BOOK_FIELDS, field
