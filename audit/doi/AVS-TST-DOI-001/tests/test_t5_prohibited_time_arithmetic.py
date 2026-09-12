"""T5-TIME-* : the SS9.4 prohibited arithmetic, outside the DOI-5 path.

SS9.4: "Planned hold is governed in trading sessions. Option expiry is
calendar time. ... Direct subtraction of session count from calendar DTE is
prohibited."
Invariant 9: "Trading sessions are never treated as calendar days."

The DOI-5 engine (domain/deterministic_option_valuation.py +
canonical_data/dynamic_options_valuation.py) is COMPLIANT -- see
test_t5_session_calendar.py. This file documents a SECOND option-valuation
path in the same repo that performs the prohibited computation verbatim and
ships the result to the desk.

  contracts/selected_contract_economics.py:657
      years = max(dte - hold_days, 0.0) / 365.0
  where  :648  dte       resolves "contract_dte" FIRST
         :651  hold_days resolves "planned_hold_sessions" FIRST
  and    eod_candidate_engine.py:887
      return float(xnys_sessions_between(session, expiry)), "AVAILABLE"
  i.e. contract_dte is a TRADING SESSION COUNT.

These tests are static + arithmetic only. Nothing is imported from the
offending module and no pipeline is executed.

Run:
  venv\\Scripts\\python.exe -m pytest audit/doi/AVS-TST-DOI-001/tests/test_t5_prohibited_time_arithmetic.py -q
"""
from __future__ import annotations

import math
import os
import re
import sys
from datetime import date

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.abspath(os.path.join(_HERE, "..", "..", "..", ".."))
sys.path.insert(0, _HERE)
sys.path.insert(0, _REPO)

from t5_reference_bs import bs_merton  # noqa: E402
from canonical_data.session_clock import (  # noqa: E402
    is_xnys_session, xnys_sessions_between,
)

SCE = os.path.join(_REPO, "contracts", "selected_contract_economics.py")
EOE = os.path.join(_REPO, "empirical_option_ev.py")
EOD = os.path.join(_REPO, "eod_candidate_engine.py")


def _src(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


# ---------------------------------------------------------------------------
# T5-TIME-0x .. the prohibited expression is present, verbatim
# ---------------------------------------------------------------------------

def test_time01_selected_contract_economics_subtracts_sessions_from_dte():
    """DEFECT T5-D3 (P0). Static proof the prohibited line exists."""
    lines = _src(SCE).splitlines()
    assert lines[656].strip() == "years = max(dte - hold_days, 0.0) / 365.0", \
        lines[656]
    # and that both operands resolve session-typed fields FIRST.
    # (the hold_days call is wrapped across :651-:653, so join the block)
    assert '(row, "contract_dte"), (row, "dte")' in lines[647]
    hold_block = " ".join(x.strip() for x in lines[650:653])
    assert hold_block.startswith("hold_days = _first_present("), hold_block
    assert '(row, "planned_hold_sessions")' in hold_block, hold_block


def test_time02_contract_dte_is_a_session_count():
    """The unit of the left operand: xnys_sessions_between, not calendar."""
    src = _src(EOD)
    assert 'return float(xnys_sessions_between(session, expiry)), "AVAILABLE"' in src
    # sanity: the function really counts sessions, not days
    start, end = date(2026, 11, 20), date(2026, 12, 7)
    assert (end - start).days == 17
    assert xnys_sessions_between(start, end) == 10


def test_time03_empirical_option_ev_repeats_the_pattern():
    """DEFECT T5-D4 (P1)."""
    src = _src(EOE)
    assert "remaining_days = max(dte - hold_days, 0.0)" in src
    assert "time_years = remaining_days / 365.0" in src
    assert 'dte = g("dte", "contract_dte")' in src


def test_time04_doi5_path_is_clean_by_contrast():
    """The compliant path, for the report's CALL/PUT/OTHER split."""
    for rel in ("domain/deterministic_option_valuation.py",
                "canonical_data/dynamic_options_valuation.py"):
        src = _src(os.path.join(_REPO, rel))
        assert not re.search(r"dte\s*-\s*\w*(hold|session)", src), rel
        assert "max(dte - hold" not in src, rel


# ---------------------------------------------------------------------------
# T5-TIME-1x .. how wrong is it? (audit's own arithmetic)
# ---------------------------------------------------------------------------

def _true_calendar_years(start: date, sessions_to_expiry: int,
                         hold_sessions: int) -> float:
    """Walk the real XNYS calendar: advance `hold_sessions` sessions, then
    measure the CALENDAR span to the expiry session."""
    from datetime import timedelta

    def advance(d, n):
        cur = d
        for _ in range(n):
            cur += timedelta(days=1)
            while not is_xnys_session(cur):
                cur += timedelta(days=1)
        return cur

    expiry = advance(start, sessions_to_expiry)
    exit_day = advance(start, hold_sessions)
    return (expiry - exit_day).days / 365.0


# (label, start session, sessions to expiry, planned hold sessions)
_TIME_CASES = [
    ("Thanksgiving window", date(2026, 11, 20), 30, 10),
    ("Christmas/New Year window", date(2026, 12, 11), 30, 10),
    ("quiet window", date(2026, 3, 6), 30, 10),
    ("short hold", date(2026, 11, 20), 20, 5),
]


@pytest.mark.parametrize("label,start,dte_sessions,hold", _TIME_CASES,
                         ids=[c[0] for c in _TIME_CASES])
def test_time10_year_fraction_is_understated(label, start, dte_sessions, hold):
    """DEFECT T5-D3 magnitude, part 1: the year fraction."""
    engine_years = max(dte_sessions - hold, 0.0) / 365.0     # the shipped line
    true_years = _true_calendar_years(start, dte_sessions, hold)
    ratio = engine_years / true_years
    print(f"{label}: engine_T={engine_years:.6f}y true_T={true_years:.6f}y "
          f"ratio={ratio:.4f} understated_by={100*(1-ratio):.2f}%")
    assert engine_years < true_years
    assert ratio < 0.75          # at least a 25% understatement of T


@pytest.mark.parametrize("label,start,dte_sessions,hold", _TIME_CASES,
                         ids=[c[0] for c in _TIME_CASES])
def test_time11_option_value_at_target_is_understated(label, start, dte_sessions, hold):
    """DEFECT T5-D3 magnitude, part 2: the money.

    The mispriced T feeds _black_scholes_value, whose output gates
    `monetisability_state_timevalue`. Understating T understates the value at
    target, biasing the desk toward NOT_MONETISABLE.
    """
    S, K, r, sigma, q = 100.0, 100.0, 0.045, 0.30, 0.0
    engine_T = max(dte_sessions - hold, 0.0) / 365.0
    true_T = _true_calendar_years(start, dte_sessions, hold)

    eng_call = bs_merton(S, K, engine_T, r, sigma, q, "call").price
    true_call = bs_merton(S, K, true_T, r, sigma, q, "call").price
    eng_put = bs_merton(S, K, engine_T, r, sigma, q, "put").price
    true_put = bs_merton(S, K, true_T, r, sigma, q, "put").price

    c_err = (eng_call - true_call) / true_call
    p_err = (eng_put - true_put) / true_put
    print(f"{label}: CALL engine={eng_call:.4f} true={true_call:.4f} "
          f"err={100*c_err:+.2f}%  |  PUT engine={eng_put:.4f} "
          f"true={true_put:.4f} err={100*p_err:+.2f}%")

    # both sides understated -- invariant 8: the defect is side-symmetric
    assert c_err < -0.10, c_err
    assert p_err < -0.10, p_err


def test_time12_headline_understatement_atm():
    """Single quotable number for the report."""
    S, K, r, sigma, q = 100.0, 100.0, 0.045, 0.30, 0.0
    start, dte_sessions, hold = date(2026, 11, 20), 30, 10
    engine_T = (dte_sessions - hold) / 365.0
    true_T = _true_calendar_years(start, dte_sessions, hold)
    eng = bs_merton(S, K, engine_T, r, sigma, q, "call").price
    true = bs_merton(S, K, true_T, r, sigma, q, "call").price
    print(f"ATM CALL, 30 sessions to expiry, 10-session hold over Thanksgiving:"
          f"\n  engine T = (30-10)/365 = {engine_T:.6f}y -> value {eng:.4f}"
          f"\n  true   T = calendar span = {true_T:.6f}y -> value {true:.4f}"
          f"\n  understatement = {100*(1-eng/true):.2f}% of contract value")
    assert eng < true


def test_time13_dimensional_analysis_of_the_denominator():
    """Even ignoring the calendar walk, a SESSION remainder divided by 365
    is dimensionally wrong: sessions/year is 252, not 365. That alone
    understates T by a factor 252/365."""
    remainder_sessions = 20
    engine = remainder_sessions / 365.0
    session_correct = remainder_sessions / 252.0
    assert engine / session_correct == pytest.approx(252.0 / 365.0, rel=1e-12)
    print(f"sessions/365 = {engine:.6f} vs sessions/252 = {session_correct:.6f} "
          f"ratio = {252/365:.4f}")
    # and price impact scales roughly as sqrt(T)
    assert math.sqrt(252.0 / 365.0) == pytest.approx(0.83091, abs=1e-4)


# ---------------------------------------------------------------------------
# T5-TIME-2x .. the flat 1:1 session->calendar identity in the DTE floor
# ---------------------------------------------------------------------------

def test_time20_calculate_dte_requirement_maps_sessions_to_calendar_1to1():
    """DEFECT T5-D5 (P2): the docstring states the invariant violation and
    defers the fix to an 'integration layer' that does not exist."""
    from domain.option_contract_liquidity import calculate_dte_requirement
    out = calculate_dte_requirement(10)
    minimum = out["minimum_required_dte"]
    # a pure session sum: hold + monitor + exit buffer, no calendar conversion
    assert isinstance(minimum, (int, float))
    print(f"calculate_dte_requirement(10) -> minimum_required_dte={minimum} "
          f"(sessions, compared downstream against a CALENDAR dte)")
    # 10 sessions of hold really span more than `minimum` calendar days
    from datetime import timedelta
    cur, n = date(2026, 11, 20), 0
    for _ in range(int(minimum)):
        cur += timedelta(days=1)
        while not is_xnys_session(cur):
            cur += timedelta(days=1)
        n += 1
    calendar_span = (cur - date(2026, 11, 20)).days
    assert calendar_span > minimum, (calendar_span, minimum)
    print(f"  {int(minimum)} sessions == {calendar_span} calendar days "
          f"-> floor is short by {calendar_span - int(minimum)} days")


def test_time21_layer3_expected_move_uses_a_5_over_7_constant():
    """DEFECT T5-D6 (P2): an explicit weekday-ratio approximation constant,
    holiday-blind, pre-blessed by its own docstring."""
    src = _src(os.path.join(_REPO, "layer3_forward_variance.py"))
    assert "trading_frac = days * (5 / 7)" in src
    assert "not drift" in src   # the docstring that blesses it
    # a 5/7 ratio ignores holidays entirely
    start, end = date(2026, 11, 20), date(2026, 12, 7)
    calendar_days = (end - start).days
    approx_sessions = calendar_days * 5 / 7
    real_sessions = xnys_sessions_between(start, end)
    print(f"{calendar_days} calendar days: 5/7 approx = {approx_sessions:.3f} "
          f"sessions, real XNYS = {real_sessions} sessions")
    assert abs(approx_sessions - real_sessions) > 1.0
