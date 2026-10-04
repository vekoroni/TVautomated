"""XLU-D01 / XLU-D13 (ACK 2 Oct 2026: "No invented target").

Business rules:
- When no structural target exists, no target is invented. The 3R value
  (entry +/- 3 x stop distance) is kept only as a labelled disclosure, never as a target.
- Every directed row carries a volatility-reachable target:
  spot x (1 +/- k x sigma x sqrt(hold/252)), with k = contract_economics.sigma_multiple and the
  governed volatility budget, over the planned hold (governed thesis window).
- R:R at the structural target is disclosure only (rr_options). Scoring reads the R:R at the
  reachable target (rr_options_reachable). Economics that do not depend on a target
  (breakeven, theta) are still evaluated when no structural target exists.
- Scoring never falls through to a structural R:R when the reachable one is missing.
Evidence (run 20260930_083504): XLU PUT entry 39.71, stop 44.6501 -> invented 3R 24.8897 (9 sigma);
reachable about 37.2; R:R 8.27 on the invented target vs about 0.7 on the reachable one.
"""
import math

import pytest

import scripts.avshunter_options_intelligence as oi
from scripts.avshunter_options_intelligence import (
    _governed_structural_target, compute_trade_economics, reachable_target_fields, three_r_scenario,
)

SIGMA_DAILY = 0.0115          # XLU-like daily log sigma (about 18% annualised)


def test_no_structural_target_means_no_invented_target():
    assert _governed_structural_target("PUT", 39.71, None, None, 4.9401) == (None, "NO_STRUCTURAL_TARGET")
    assert _governed_structural_target("CALL", 100.0, None, None, 4.0) == (None, "NO_STRUCTURAL_TARGET")
    assert _governed_structural_target("PUT", 10.0, None, None, 4.0) == (None, "NO_STRUCTURAL_TARGET")


def test_structural_sources_are_unchanged():
    assert _governed_structural_target("PUT", 100.0, 80.0, None, 4.0) == (80.0, "DISCOVERY_TARGET")
    assert _governed_structural_target("CALL", 100.0, None, 115.0, 4.0) == (115.0, "L1_FAR")


def test_three_r_is_a_labelled_disclosure_only():
    value, state = three_r_scenario("PUT", 39.71, 4.9401)
    assert value == pytest.approx(24.8897, abs=1e-4) and state == "SCENARIO_3R_DISCLOSURE_ONLY"
    assert three_r_scenario("PUT", 10.0, 4.0) == (None, "SCENARIO_3R_NON_POSITIVE")
    assert three_r_scenario("CALL", 100.0, None) == (None, "SCENARIO_3R_NO_STOP")


def test_reachable_target_uses_the_governed_budget_and_multiple():
    fields = reachable_target_fields("PUT", 39.51, 24.8897, SIGMA_DAILY, hold_sessions=20)
    annual = SIGMA_DAILY * math.sqrt(252)
    move = annual * math.sqrt(20 / 252)
    assert fields["target_reachable"] == pytest.approx(39.51 * (1 - 1.5 * move), rel=1e-6)
    assert fields["target_reachable_sigma_multiple"] == 1.5
    assert fields["target_reach_ratio"] > 3          # the invented target is far beyond reach
    missing = reachable_target_fields("PUT", 39.51, None, None, hold_sessions=20)
    assert missing["target_reachable"] is None
    assert missing["target_reachable_state"] == "NOT_EVALUATED_DATA_MISSING"


def _contract(mark=1.63, strike=40.0):
    return {"mark": mark, "bid": mark - 0.08, "ask": mark + 0.08, "strike": strike, "theta": -0.01,
            "vega": 0.085, "delta": -0.457, "dte": 107}


def _ctx(target, reachable):
    return {"spot": 39.51, "entry": 39.71, "structural_target": target, "target_reachable": reachable,
            "hold_days": 20, "direction": "PUT", "win_prob": 50}


def test_economics_without_structural_target_are_evaluated_on_the_reachable_target():
    econ = compute_trade_economics(_contract(), _ctx(None, 37.20), {"ivp_label": "FAIR"})
    assert econ["economics_state"] == "EVALUATED"
    assert econ["rr_options"] is None and econ["rr_options_state"] == "NO_STRUCTURAL_TARGET"
    assert econ["rr_options_reachable"] == pytest.approx((40.0 - 37.20 - 1.63) / 1.63, abs=1e-3)
    assert econ["breakeven_price"] == pytest.approx(40.0 - 1.63, abs=0.01)


def test_structural_rr_is_disclosure_and_reachable_rr_is_reported_beside_it():
    econ = compute_trade_economics(_contract(), _ctx(24.8897, 37.20), {"ivp_label": "FAIR"})
    assert econ["rr_options"] == pytest.approx(8.27, abs=0.01)
    assert econ["rr_options_reachable"] == pytest.approx(0.718, abs=0.01)
    assert econ["rr_basis"] == "STRUCTURAL_DISCLOSURE|REACHABLE_SCORED"


def test_no_target_at_all_is_still_not_evaluated():
    econ = compute_trade_economics(_contract(), _ctx(None, None), {"ivp_label": "FAIR"})
    assert econ["economics_state"] == "NOT_EVALUATED"


def test_eod_monetisation_gives_no_rr_points():
    # ACK 3 Oct 2026 (step 6/D-C): R:R retired from every score - no ranking information on the holdout replay.
    from eod_candidate_engine import _monetisation_fit
    base = {"options_score": 0, "trigger_quality": "", "catalyst_truth_score": 0,
            "rr_underlying": 0, "rr_options": 8.27}
    info = {"direction_call_score": 0.0, "direction_put_score": 0.0}
    xlu = _monetisation_fit({**base, "rr_options_reachable": 0.72}, "B", {"contract_quality_score": 0}, info)
    invented = _monetisation_fit({**base}, "B", {"contract_quality_score": 0}, info)
    assert xlu["monetisation_fit_score"] == 0.0
    assert invented["monetisation_fit_score"] == 0.0


def test_lab_composite_reads_the_reachable_rr():
    import importlib.util
    from pathlib import Path
    source = Path("intelligence-lab/intelligence_lab.py").read_text(encoding="utf-8")
    assert '_f("rr_options_reachable")' in source
    assert 'rr     = _f("rr_options") or _f("opt__rr_options")' not in source
