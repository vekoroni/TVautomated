"""Step 4c (ACK 3 Oct 2026): theta decay is charged over the evidence hold, in the right units.

Defect: ctx['hold_days'] was Vanguard's actuarial recommended hold, else the DTE window midpoint (28 calendar
days) or 5 - invented holds (inventory C3) - and it was used both as sessions (ATR x sqrt(hold)) and as calendar
days (theta per calendar day x hold). Business rules:
- The hold for decay and range checks is the anticipated move time (evidence q50, sessions); without evidence,
  the governed window, labelled. Never the DTE-window midpoint or a constant.
- Theta (per calendar day) is charged over hold sessions x governed calendar days per session (365/252).
"""
import inspect

import pytest

import scripts.avshunter_options_intelligence as oi


def test_hold_comes_from_evidence_else_the_governed_window():
    assert oi.decay_hold_sessions(evidence_move_sessions=8, governed_window=20) == (8, "DURATION_EVIDENCE_Q50")
    assert oi.decay_hold_sessions(evidence_move_sessions=None, governed_window=20) == (20, "GOVERNED_WINDOW_NO_EVIDENCE")


def test_theta_drag_is_charged_in_calendar_days():
    # 0.0089/calendar day over 8 sessions (11.6 calendar days) on a 1.51 premium
    assert oi.theta_drag_pct(theta_per_calendar_day=-0.0089, hold_sessions=8, mark=1.51) == pytest.approx(0.0089 * 8 * 1.4484 / 1.51 * 100, abs=0.01)
    assert oi.theta_drag_pct(theta_per_calendar_day=-0.0089, hold_sessions=8, mark=0) is None


def test_context_no_longer_uses_the_dte_window_or_actuarial_hold():
    src = inspect.getsource(oi.parse_structural_context)
    assert "hold_days = l2_hold_days if l2_hold_days > 0 else dte_window[1]" not in src
    assert "decay_hold_sessions(" in src
    econ = inspect.getsource(oi)
    assert "theta_total  = abs(theta) * hold" not in econ
