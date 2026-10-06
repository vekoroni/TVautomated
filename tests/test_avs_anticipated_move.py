"""Anticipated move (design AVS_ANTICIPATED_MOVE_DESIGN_20261003 §3-§5, §9 step 2; ACK 3 Oct 2026).

Business rules (display only in this step; no gate, score or rank reads these fields):
- Magnitude: the trade-side candidate's structural Outcome_Level, capped at the volatility-reachable level
  over the evidence time (D-D); no structural level -> volatility only; nothing is invented from a stop.
- Time: the candidate's duration evidence (q50 / q80, own-timeframe bars converted to sessions). Thin evidence:
  hold UNESTIMATED, the reach uses the governed window, labelled (D-A a).
- Payoff: coverage = anticipated move / breakeven move; value multiple at q50 (and q80 stress) from the
  repository's Black-Scholes valuer with the contract IV held; IV x governed iv_stress low when earnings fall
  inside q80 (disclosed stress, not scored).
- The invalidation is the thesis exit on the card; it is not an input here.
"""
import inspect

import pytest

from domain.anticipated_move import ANTICIPATED_MOVE_FIELDS, anticipated_move_fields

CONTRACT = {"strike": 16.0, "ask": 1.51, "iv": 0.5245, "expiry": "2026-12-18", "as_of": "2026-10-02"}
DUR = {"test": "OUTCOME", "status": "IN_SAMPLE_REPLAY_NOT_VALIDATED", "n": 412, "q50_bars": 6, "q80_bars": 14,
       "p_event": 0.41, "p_invalidation": 0.37}


def _am(**kw):
    base = dict(direction="PUT", spot=15.92, outcome_level=14.20, outcome_definition="PRIOR_SWING_LOW",
                timeframe="1d", duration=DUR, vol_annual=0.53, contract=CONTRACT, governed_window_sessions=20,
                earnings={"earnings_state": "SCHEDULED", "earnings_sessions_to_event": 17})
    base.update(kw)
    return anticipated_move_fields(**base)


def test_fields_and_authority():
    out = _am()
    assert set(ANTICIPATED_MOVE_FIELDS) <= set(out)
    assert out["anticipated_authority"] == "DISPLAY_ONLY"
    assert "invalidation" not in inspect.signature(anticipated_move_fields).parameters


def test_structural_level_within_reach_is_used():
    out = _am()
    assert out["anticipated_level_basis"] == "STRUCTURAL"
    assert out["anticipated_level"] == pytest.approx(14.20)
    assert out["anticipated_move_pct"] == pytest.approx((15.92 - 14.20) / 15.92 * 100, abs=0.01)
    assert out["anticipated_sessions_q50"] == 6 and out["anticipated_sessions_q80"] == 14
    assert out["anticipated_hold_sessions"] == 6
    assert out["anticipated_time_basis"].startswith("DURATION_EVIDENCE")


def test_structural_level_beyond_reach_is_capped():
    out = _am(outcome_level=4.87)                       # the old invented 3R level, far beyond reach
    assert out["anticipated_level_basis"] == "VOLATILITY_CAPPED"
    assert out["anticipated_level"] == pytest.approx(out["anticipated_reachable_level"])
    assert out["anticipated_structural_level"] == pytest.approx(4.87)


def test_no_structural_level_uses_volatility_only():
    out = _am(outcome_level=None)
    assert out["anticipated_level_basis"] == "VOLATILITY_ONLY"


def test_thin_evidence_leaves_hold_unestimated_and_labels_the_window():
    out = _am(duration={"status": "INSUFFICIENT_SAMPLE", "n": 40})
    assert out["anticipated_hold_sessions"] is None
    assert out["anticipated_time_basis"] == "GOVERNED_WINDOW_NO_DURATION_EVIDENCE"
    assert out["anticipated_reachable_level"] is not None


def test_weekly_bars_convert_to_sessions():
    out = _am(timeframe="1w", duration={**DUR, "q50_bars": 2, "q80_bars": 4})
    assert out["anticipated_sessions_q50"] == 10 and out["anticipated_sessions_q80"] == 20


def test_payoff_against_breakeven_and_premium():
    out = _am()
    assert out["anticipated_breakeven_move_pct"] == pytest.approx((15.92 - 14.49) / 15.92 * 100, abs=0.01)
    assert out["anticipated_move_coverage"] == pytest.approx(out["anticipated_move_pct"] / out["anticipated_breakeven_move_pct"], abs=1e-3)
    assert out["anticipated_value_multiple_q50"] > out["anticipated_value_multiple_q80"] > 0


def test_earnings_stress_only_when_earnings_fall_inside_q80():
    after = _am()                                          # earnings 17 sessions away, q80 = 14
    assert after["anticipated_value_multiple_earnings_stress"] is None
    inside = _am(earnings={"earnings_state": "SCHEDULED", "earnings_sessions_to_event": 10})
    assert 0 < inside["anticipated_value_multiple_earnings_stress"] < inside["anticipated_value_multiple_q80"]
    assert "IV x 0.8" in inside["anticipated_stress_basis"]


def test_missing_volatility_invents_nothing():
    out = _am(vol_annual=None, outcome_level=None)
    assert out["anticipated_move_state"].startswith("UNESTIMATED")
    assert out["anticipated_level"] is None and out["anticipated_move_coverage"] is None


def test_non_directional_is_not_applicable():
    assert _am(direction="NONE")["anticipated_move_state"] == "NOT_APPLICABLE_NON_DIRECTIONAL"


def test_fields_travel_from_discovery_through_eod_to_the_book():
    import inspect
    import eod_candidate_engine
    from contracts.lab_control import FINAL_BOOK_FIELDS, opportunity_book_row
    from domain.structure_behaviour.thesis_category import EVIDENCE_FIELDS, thesis_category
    src = inspect.getsource(eod_candidate_engine)
    assert "anticipated_move_fields(" in src and "THESIS_EVIDENCE_FIELDS" in src
    assert "target_reachable_vol_annual" in src
    for f in (*EVIDENCE_FIELDS, *ANTICIPATED_MOVE_FIELDS):
        assert f in FINAL_BOOK_FIELDS, f
    row = opportunity_book_row({"ticker": "SOFI", "anticipated_level": 14.2, "anticipated_move_coverage": 1.2,
                                "thesis_outcome_level": 14.2}, "RUN", 1)
    assert row["anticipated_level"] == 14.2 and row["thesis_outcome_level"] == 14.2
    cand = {"Candidate_ID": "SOFI|1d|C", "Direction": "BEAR", "Signal_State": "ACTIVATED", "Timeframe": "1d",
            "Signal_Type": "SOW -> LPSY continuation", "Structure_Scope": "CAMPAIGN", "Outcome_Level": 14.2,
            "Outcome_Definition": "PRIOR_SWING_LOW", "Duration_Level_Status": "IN_SAMPLE_REPLAY_NOT_VALIDATED",  # step 4a: level timing
            "Duration_Level_Q50_Bars": 6, "Duration_Level_Q80_Bars": 14, "Duration_Level_N": 412}
    out = thesis_category({"1d": {"Status": "EVALUATED", "candidates": [cand], "Wyckoff_Phase": "D"}}, "PUT")
    assert out["thesis_outcome_level"] == 14.2 and out["thesis_duration_q80_bars"] == 14
    opposing = thesis_category({"1d": {"Status": "EVALUATED", "candidates": [cand], "Wyckoff_Phase": "D"}}, "CALL")
    assert opposing["thesis_outcome_level"] is None          # an opposing event's level is never a target


def test_no_trade_side_event_has_no_anticipated_move():
    """Real-data finding (3 Oct 2026): INTC/NET/TWLO carried no event on the trade side (opposing only), yet the
    symmetric volatility reach produced 25-31% 'anticipated' moves. Volatility alone is not a directional
    expectation; without a trade-side event the state says so and nothing is computed."""
    out = _am(trade_side_event=False, outcome_level=None, duration=None)
    assert out["anticipated_move_state"] == "NO_TRADE_SIDE_EVENT"
    assert out["anticipated_level"] is None and out["anticipated_move_coverage"] is None
    assert _am(trade_side_event=True, outcome_level=None)["anticipated_level_basis"] == "VOLATILITY_ONLY"


def test_contract_expiring_before_the_anticipated_time_is_stated():
    """Real-data finding (3 Oct 2026): weekly/monthly events (TW q50/q80 = 115/180 sessions) outlived the contract,
    and the value multiple silently assumed the move arrived before expiry. Time fit is stated; no value is
    computed at a time the contract does not live to."""
    short = dict(CONTRACT, expiry="2026-10-23")             # ~15 sessions of contract life
    out = _am(contract=short, duration={**DUR, "q50_bars": 30, "q80_bars": 60})
    assert out["anticipated_time_fit"] == "CONTRACT_EXPIRES_BEFORE_MEDIAN_TIME"
    assert out["anticipated_value_multiple_q50"] is None and out["anticipated_value_multiple_q80"] is None
    mid = _am(contract=short, duration={**DUR, "q50_bars": 6, "q80_bars": 30})
    assert mid["anticipated_time_fit"] == "CONTRACT_EXPIRES_BEFORE_Q80"
    assert mid["anticipated_value_multiple_q50"] is not None and mid["anticipated_value_multiple_q80"] is None
    assert _am()["anticipated_time_fit"] == "CONTRACT_OUTLASTS_Q80"


# --- Fix B (ACK 5 Oct 2026): each valuation uses the level reachable by its own time. -----------------------------
# Run 20261005_072245, SMH: a volatility-only level was the 1.5-sigma reach over q80 (42 sessions, +19.2%) but
# valued as if reached at q50 (10 sessions): 3.04x, roughly a 2-sigma move in 10 sessions (external review).

def test_q50_value_uses_the_reach_at_q50_not_q80():
    from domain.anticipated_move import anticipated_move_fields as amf
    out = _am(outcome_level=4.87)                        # far beyond reach: capped at every horizon
    k, vol, s0 = 1.5, 0.53, 15.92
    reach50 = s0 * (1 - k * vol * (6 / 252) ** 0.5)
    assert out["anticipated_level_q50"] == pytest.approx(reach50, rel=1e-3)
    assert out["anticipated_level"] == pytest.approx(out["anticipated_reachable_level"])     # q80 level, displayed
    assert abs(out["anticipated_level_q50"] - s0) < abs(out["anticipated_level"] - s0)


def test_structural_level_inside_the_q50_reach_is_used_at_both_times():
    out = _am()
    assert out["anticipated_level_q50"] == pytest.approx(14.20)


def test_volatility_only_has_no_pays_verdict():
    out = _am(outcome_level=None)
    assert out["anticipated_level_basis"] == "VOLATILITY_ONLY"
    assert out["anticipated_pays_state"] == "NOT_ASSESSED_VOLATILITY_ONLY"
    assert out["anticipated_value_multiple_q50"] is not None          # still shown, labelled, never a verdict
