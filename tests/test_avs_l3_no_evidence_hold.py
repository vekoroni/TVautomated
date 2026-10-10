"""L3 (ACK 7 Oct 2026, "5 = B"): with no evidence hold there is no minimum DTE; the row says NO_EVIDENCE_HOLD.

The Morning gate resolved a hold through a fallback chain - planned_hold_sessions, remaining_hold_sessions,
ev3_horizon_sessions, hold_days, l2_hold_days, then the largest number parsed from hold_label / hold_period /
time_horizon - and calculate_dte_requirement refused any non-evidence hold outside the retired {5, 10, 20}, which
became CONTRACT_REPRICE_REQUIRED -> FLAG CONTRACT_REPAIR.
Business rules:
- Morning: the hold is the evidence hold (planned_hold_sessions with a DURATION_EVIDENCE source) or nothing.
- No hold: no hold-based minimum DTE; the contract must still be holdable past issue (exit buffer); the reason
  NO_EVIDENCE_HOLD is stated. The lifecycle runs - it is not DATA_INCOMPLETE for a missing hold.
- The {5, 10, 20} restriction is retired: a caller-stated hold (e.g. contract selection's governed window) is used
  as stated, with its basis.
"""
from __future__ import annotations

import morning_gate
from domain.option_contract_liquidity import (LifecycleInputs, calculate_dte_requirement,
                                              evaluate_options_liquidity_lifecycle)


def test_no_hold_means_no_minimum_and_says_so():
    out = calculate_dte_requirement(None)
    assert out["minimum_required_dte"] is None and out["dte_requirement_basis"] == "NO_EVIDENCE_HOLD"
    assert out["minimum_holdable_dte"] > 0                       # still holdable past issue


def test_the_retired_5_10_20_restriction_is_gone():
    stated = calculate_dte_requirement(27)
    assert stated["minimum_required_dte"] > 0 and stated["dte_requirement_basis"] == "STATED_HOLD"
    assert calculate_dte_requirement(27, evidence_hold=True)["dte_requirement_basis"] == "EVIDENCE_HOLD"


def test_the_lifecycle_runs_without_a_hold():
    out = evaluate_options_liquidity_lifecycle(LifecycleInputs(
        side="CALL", spot=100.0, strike=100.0, delta=0.5, bid=2.0, ask=2.1, dte=40.0, remaining_hold_sessions=None,
        forecast_vol_annual=0.30, thesis_spot=100.0, current_spot=100.0, structural_target=110.0,
        invalidation_spot=95.0, quote_age_seconds=60.0))
    assert out["dte_requirement_basis"] == "NO_EVIDENCE_HOLD" and out["minimum_required_dte"] is None
    assert "NO_EVIDENCE_HOLD" in out.get("liquidity_reasons", [])
    assert out["liquidity_state"] != "INVALID_QUOTE"


def test_morning_takes_only_the_evidence_hold():
    assert morning_gate._morning_hold_sessions({"planned_hold_sessions": 27,
                                                "planned_hold_source": "DURATION_EVIDENCE:1d"}) == 27
    legacy = {"planned_hold_sessions": None, "ev3_horizon_sessions": 20, "hold_days": 10, "l2_hold_days": 5,
              "hold_label": "1-5 sessions", "time_horizon": "1_5d"}
    assert morning_gate._morning_hold_sessions(legacy) is None
    assert morning_gate._morning_hold_sessions({"planned_hold_sessions": 20, "planned_hold_source": "FIXED_20"}) is None
