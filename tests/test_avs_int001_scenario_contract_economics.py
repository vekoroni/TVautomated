"""INT-001 scenario suite 7: exact-contract economics from the pricing model to the Lab row.

One realistic long call and its mirror put on the same underlying (spot 48.20, 42% IV), 55 days
to expiry, ask entry 2.25 against bid 2.10, ten-session hold. The suite checks the model
arithmetic (parity, monotonicity, bounds), the DOI-5 scenario grid (early/mid/late, contracted/
base/expanded IV, flat/1-sigma/2-sigma/reachable/structural/invalidation paths), the typed
applicability states, and that what the Lab shows as the six headline payoffs is exactly what
the engine produced, labelled as scenarios and never as an expected return.
"""
from __future__ import annotations

import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from statistics import median

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from contracts.lab_control import scenario_disclosure_from_row  # noqa: E402
from domain.contract_economics_v2 import evaluate_contract_economics_v2  # noqa: E402
from domain.deterministic_option_valuation import (  # noqa: E402
    IVStress, ScenarioPath, ScenarioPoint, ScenarioTiming,
    dividend_adjusted_black_scholes, evaluate_deterministic_scenarios,
)
from domain.volatility_budget import checkpoint_fields  # noqa: E402

UTC = timezone.utc
SPOT, STRIKE, IV, R, Q = 48.20, 48.0, 0.42, 0.04, 0.0
EXPIRY = datetime(2026, 11, 20, 21, 0, tzinfo=UTC)
ENTRY = datetime(2026, 9, 25, 20, 0, tzinfo=UTC)
POINTS = (
    ScenarioPoint(ScenarioTiming.EARLY, 2, datetime(2026, 9, 29, 20, 0, tzinfo=UTC)),
    ScenarioPoint(ScenarioTiming.MID, 5, datetime(2026, 10, 2, 20, 0, tzinfo=UTC)),
    ScenarioPoint(ScenarioTiming.LATE, 10, datetime(2026, 10, 9, 20, 0, tzinfo=UTC)),
)
MOVE10 = checkpoint_fields(IV)["expected_move_10d_fraction"]


def _model_entry(side: str) -> float:
    t = (EXPIRY - ENTRY).total_seconds() / (365 * 86400)
    return dividend_adjusted_black_scholes(option_side=side, spot=SPOT, strike=STRIKE, time_to_expiry_years=t,
                                           risk_free_rate=R, dividend_yield=Q, volatility=IV)


# A completed-session quote consistent with the 42% base IV: ask one percent over model, 15c wide.
QUOTE = {side: (round(_model_entry(side) * 1.01, 2) - 0.15, round(_model_entry(side) * 1.01, 2))
         for side in ("CALL", "PUT")}


def _paths(side: str) -> dict:
    sign = 1 if side == "CALL" else -1
    return dict(
        favourable_1sigma=SPOT * (1 + sign * MOVE10),
        favourable_2sigma=SPOT * (1 + sign * 2 * MOVE10),
        reachable_spot=SPOT * (1 + sign * MOVE10),
        structural_target=SPOT * (1 + sign * 0.06),
        invalidation_spot=SPOT * (1 - sign * 0.045),
    )


def _economics(side: str = "CALL", **overrides):
    bid, ask = QUOTE[side]
    kwargs = dict(option_side=side, origin_spot=SPOT, strike=STRIKE, expiration_utc=EXPIRY,
                  base_iv=IV, entry_bid=bid, entry_ask=ask, risk_free_rate=R, dividend_yield=Q,
                  scenario_points=POINTS, **_paths(side))
    kwargs.update(overrides)
    return evaluate_contract_economics_v2(**kwargs)


# ---------------------------------------------------------------------------- model arithmetic
def test_pricing_model_respects_parity_bounds_and_monotonicity():
    t = (EXPIRY - POINTS[0].as_of_utc).total_seconds() / (365 * 86400)
    call = dividend_adjusted_black_scholes(option_side="CALL", spot=SPOT, strike=STRIKE, time_to_expiry_years=t,
                                           risk_free_rate=R, dividend_yield=Q, volatility=IV)
    put = dividend_adjusted_black_scholes(option_side="PUT", spot=SPOT, strike=STRIKE, time_to_expiry_years=t,
                                          risk_free_rate=R, dividend_yield=Q, volatility=IV)
    assert call - put == pytest.approx(SPOT - STRIKE * math.exp(-R * t), abs=1e-9)
    assert max(0.0, SPOT - STRIKE) < call < SPOT
    # A 52-day ATM 42%-vol call on a 48 dollar stock is worth roughly three dollars.
    assert 2.5 < call < 4.2
    assert QUOTE["CALL"][1] == pytest.approx(round(_model_entry("CALL") * 1.01, 2))
    spots = [40.0, 44.0, 48.2, 52.0, 56.0]
    calls = [dividend_adjusted_black_scholes(option_side="CALL", spot=s, strike=STRIKE, time_to_expiry_years=t,
                                             risk_free_rate=R, dividend_yield=Q, volatility=IV) for s in spots]
    assert calls == sorted(calls)
    vols = [dividend_adjusted_black_scholes(option_side="CALL", spot=SPOT, strike=STRIKE, time_to_expiry_years=t,
                                            risk_free_rate=R, dividend_yield=Q, volatility=v) for v in (0.2, 0.42, 0.8)]
    assert vols == sorted(vols)
    assert dividend_adjusted_black_scholes(option_side="CALL", spot=SPOT, strike=STRIKE, time_to_expiry_years=0.0,
                                           risk_free_rate=R, dividend_yield=Q, volatility=IV) == pytest.approx(0.20)


# ---------------------------------------------------------------------------- DOI-5 grid
@pytest.mark.parametrize("side", ["CALL", "PUT"])
def test_doi5_grid_orders_paths_timing_and_iv_stress_as_a_long_option_must(side):
    sign = 1 if side == "CALL" else -1
    paths = _paths(side)
    valuation = evaluate_deterministic_scenarios(
        option_side=side, strike=STRIKE, expiration_utc=EXPIRY,
        target_spot=paths["structural_target"], invalidation_spot=paths["invalidation_spot"],
        base_iv=IV, scenario_points=POINTS, entry_ask=QUOTE[side][1], risk_free_rate=R, dividend_yield=Q,
    )
    # The grid is deterministic-only; a put deep enough in the money at positive rates is flagged
    # OUT_OF_DISTRIBUTION because European pricing understates American early exercise.
    assert valuation.applicability_state.value in {"DETERMINISTIC_ONLY", "OUT_OF_DISTRIBUTION"}
    assert valuation.american_exercise_material is (valuation.applicability_state.value == "OUT_OF_DISTRIBUTION")
    if side == "CALL":
        assert not valuation.american_exercise_material  # no dividend, no early-exercise premium
    assert "DETERMINISTIC_SCENARIOS_NOT_FORECASTS" in valuation.disclosures
    assert "RANKING_SCORE_UNCALIBRATED_NOT_PROBABILITY" in valuation.disclosures
    assert len(valuation.scenarios) == 18
    assert valuation.probabilities_calibrated is False
    assert valuation.decision_authority == "NONE"
    grid = {(s.path, s.timing, s.iv_stress): s for s in valuation.scenarios}
    for timing in ScenarioTiming:
        target = grid[(ScenarioPath.FAVOURABLE_TARGET, timing, IVStress.BASE)]
        adverse = grid[(ScenarioPath.ADVERSE_INVALIDATION, timing, IVStress.BASE)]
        assert sign * (target.scenario_spot - SPOT) > 0 > sign * (adverse.scenario_spot - SPOT)
        assert target.net_return_fraction > adverse.net_return_fraction
        assert adverse.net_return_fraction < 0
        contracted = grid[(ScenarioPath.FAVOURABLE_TARGET, timing, IVStress.CONTRACTED)]
        expanded = grid[(ScenarioPath.FAVOURABLE_TARGET, timing, IVStress.EXPANDED)]
        assert contracted.theoretical_value < target.theoretical_value < expanded.theoretical_value
        assert contracted.scenario_iv == pytest.approx(IV * 0.8) and expanded.scenario_iv == pytest.approx(IV * 1.2)
    # Later arrival at the same adverse level is worth less (theta plus less time value).
    adverse_by_time = [grid[(ScenarioPath.ADVERSE_INVALIDATION, t, IVStress.BASE)].theoretical_value
                       for t in ScenarioTiming]
    assert adverse_by_time == sorted(adverse_by_time, reverse=True)
    assert valuation.adverse_worst_return == pytest.approx(min(
        s.net_return_fraction for s in valuation.scenarios if s.path is ScenarioPath.ADVERSE_INVALIDATION))
    assert valuation.adverse_worst_return > -1.0  # a long option cannot lose more than its premium


def test_doi5_grid_refuses_wrong_sided_or_missing_geometry_without_a_number():
    missing = evaluate_deterministic_scenarios(
        option_side="CALL", strike=STRIKE, expiration_utc=EXPIRY, target_spot=None,
        invalidation_spot=46.0, base_iv=IV, scenario_points=POINTS, entry_ask=QUOTE["CALL"][1],
        risk_free_rate=R, dividend_yield=Q)
    assert missing.applicability_state.value == "DATA_INSUFFICIENT"
    assert missing.scenarios == () and missing.ranking_score_uncalibrated is None
    assert "NO_PROBABILITY_OUTPUT" in missing.disclosures
    with pytest.raises(ValueError, match="target must exceed invalidation"):
        evaluate_deterministic_scenarios(
            option_side="CALL", strike=STRIKE, expiration_utc=EXPIRY, target_spot=46.0,
            invalidation_spot=51.0, base_iv=IV, scenario_points=POINTS, entry_ask=QUOTE["CALL"][1],
            risk_free_rate=R, dividend_yield=Q)


# ---------------------------------------------------------------------------- economics v2
@pytest.mark.parametrize("side", ["CALL", "PUT"])
def test_economics_v2_headline_payoffs_are_scenario_values_net_of_stated_friction(side):
    econ = _economics(side)
    bid, ask = QUOTE[side]
    assert econ.applicability == "APPLICABLE"
    assert len(econ.scenarios) == 6 * 3 * 3
    assert econ.decision_authority == "NONE" and econ.calibration_state == "NOT_AVAILABLE"
    assert econ.monetisability_state == "INDETERMINATE" and econ.monetisability_reason == "PROFIT_FLOOR_NOT_APPROVED"
    assert econ.spread_fraction_mid == pytest.approx((ask - bid) / ((ask + bid) / 2))
    late_base = {s.path: s for s in econ.scenarios if s.timing == "LATE" and s.iv_stress == "BASE"}
    assert set(late_base) == {"FLAT", "FAVOURABLE_1SIGMA", "FAVOURABLE_2SIGMA", "REACHABLE",
                              "STRUCTURAL_DISCLOSURE", "ADVERSE_INVALIDATION"}
    # Every exit is theoretical value less the friction proxy, expressed against the ask paid.
    for s in econ.scenarios:
        assert s.exit_value_after_friction_per_share == pytest.approx(
            s.theoretical_value_per_share * (1 - min(econ.spread_fraction_mid / 2, 0.15)))
        assert s.net_return_fraction == pytest.approx((s.exit_value_after_friction_per_share - ask) / ask)
        assert s.net_return_fraction >= -1.0
    assert late_base["FLAT"].net_return_fraction < 0                      # theta bleed at rest
    assert late_base["ADVERSE_INVALIDATION"].net_return_fraction < late_base["FLAT"].net_return_fraction
    assert late_base["FAVOURABLE_2SIGMA"].net_return_fraction > late_base["FAVOURABLE_1SIGMA"].net_return_fraction > late_base["FLAT"].net_return_fraction
    assert late_base["REACHABLE"].net_return_fraction == late_base["FAVOURABLE_1SIGMA"].net_return_fraction
    # Utility and convexity are the documented formulas, not a hidden model.
    reach = [s.net_return_fraction for s in econ.scenarios if s.path == "REACHABLE"]
    adverse = [s.net_return_fraction for s in econ.scenarios if s.path == "ADVERSE_INVALIDATION"]
    assert econ.deterministic_utility == pytest.approx(median(reach) + min(adverse) + 0.5 * late_base["FLAT"].net_return_fraction)
    convexity = late_base["FAVOURABLE_2SIGMA"].net_return_fraction - 2 * late_base["FAVOURABLE_1SIGMA"].net_return_fraction + late_base["FLAT"].net_return_fraction
    assert econ.convexity_score == pytest.approx(convexity)
    assert econ.convexity_label == ("CONVEX" if convexity > 0.01 else "LINEAR" if convexity >= -0.01 else "CONCAVE")


def test_economics_v2_typed_states_for_bad_quotes_wide_spreads_and_short_expiries():
    bid, ask = QUOTE["CALL"]
    assert _economics(entry_bid=None).applicability == "NOT_EVALUATED_DATA_MISSING"
    crossed = _economics(entry_bid=ask + 0.05)
    assert crossed.applicability == "DATA_DEFECT" and crossed.monetisability_reason == "INVALID_BID_ASK"
    wide = _economics(entry_bid=ask - 1.20, entry_ask=ask)
    assert wide.applicability == "FRICTION_OUT_OF_RANGE" and wide.monetisability_state == "INDETERMINATE"
    assert wide.spread_fraction_mid == pytest.approx(1.20 / (ask - 0.60))
    short = _economics(expiration_utc=datetime(2026, 10, 9, 20, 0, tzinfo=UTC))
    assert short.applicability == "HORIZON_LIMITED" and short.monetisability_reason == "HORIZON_LIMITED"
    with pytest.raises(ValueError, match="wrong-sided"):
        _economics(reachable_spot=SPOT * 0.97)


def test_profit_floor_changes_only_the_label_and_only_when_approved():
    floor_unapproved = _economics(profit_floor=0.20)
    assert floor_unapproved.monetisability_state == "INDETERMINATE"
    assert floor_unapproved.profit_floor_applied is None
    approved = _economics(profit_floor=0.20, profit_floor_approved=True, profit_floor_approval_id="ACK-TEST")
    headline = next(s.net_return_fraction for s in approved.scenarios
                    if s.path == "REACHABLE" and s.timing == "LATE" and s.iv_stress == "BASE")
    expected = ("SCENARIO_MONETISABLE" if headline >= 0.20 else
                "SCENARIO_LIMITED" if headline > 0 else "NOT_CURRENTLY_MONETISABLE")
    assert approved.monetisability_state == expected
    assert approved.profit_floor_applied == 0.20 and approved.profit_floor_approval_id == "ACK-TEST"
    assert approved.deterministic_utility == pytest.approx(floor_unapproved.deterministic_utility)


# ---------------------------------------------------------------------------- DOI -> Lab handoff
def test_lab_row_shows_exactly_the_engines_late_base_payoffs_as_scenarios_not_expectancy():
    econ = _economics("CALL")
    symbol = "ACME261120C00048000"
    row = {
        "ticker": "ACME", "selected_contract_symbol": symbol, "doi_governed_contract_symbol": symbol,
        "doi_scenarios_json": json.dumps([s.to_dict() for s in econ.scenarios]),
        "doi_assessment_calculation_version": econ.calculation_version, "rr_premium_expected": 1.7,
    }
    disclosure = scenario_disclosure_from_row(row)
    late_base = {s.path: s.net_return_fraction for s in econ.scenarios if s.timing == "LATE" and s.iv_stress == "BASE"}
    assert disclosure["scenario_state"] == "AVAILABLE"
    assert disclosure["payoff_flat_net_return_fraction"] == pytest.approx(late_base["FLAT"], abs=1e-6)
    assert disclosure["payoff_reachable_net_return_fraction"] == pytest.approx(late_base["REACHABLE"], abs=1e-6)
    assert disclosure["payoff_structural_net_return_fraction"] == pytest.approx(late_base["STRUCTURAL_DISCLOSURE"], abs=1e-6)
    assert disclosure["payoff_invalidation_net_return_fraction"] == pytest.approx(late_base["ADVERSE_INVALIDATION"], abs=1e-6)
    lo, hi = disclosure["payoff_reachable_iv_stress_range"]
    assert lo < late_base["REACHABLE"] < hi
    reach, inval = late_base["REACHABLE"], late_base["ADVERSE_INVALIDATION"]
    assert disclosure["breakeven_p_target_two_outcome"] == pytest.approx(-inval / (reach - inval), abs=1e-5)
    assert 0 < disclosure["breakeven_p_target_two_outcome"] < 1
    assert disclosure["scenario_is_expected_return"] is False
    assert disclosure["legacy_rr_is_expected_return"] is False
    assert disclosure["scenario_pricing_model_version"] == econ.calculation_version

    # A grid produced for a different governed contract is never shown against the selected one.
    mismatched = scenario_disclosure_from_row(dict(row, doi_governed_contract_symbol="ACME261120C00050000"))
    assert mismatched["scenario_state"] == "CONTRACT_MISMATCH"
    assert mismatched["payoff_reachable_net_return_fraction"] is None
    absent = scenario_disclosure_from_row(dict(row, doi_scenarios_json="", doi_projection_reason="NO_CHAIN_FOR_SESSION"))
    assert absent["scenario_state"] == "NOT_ASSESSED" and absent["scenario_reason"] == "NO_CHAIN_FOR_SESSION"
