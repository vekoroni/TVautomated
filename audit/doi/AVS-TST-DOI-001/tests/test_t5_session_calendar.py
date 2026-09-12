"""T5-CAL-* : session-vs-calendar conversion (SS9.4, invariant 9).

Spec SS9.4: "Planned hold is governed in trading sessions. Option expiry is
calendar time. All valuation must convert through the exchange calendar and
exact timestamps. Direct subtraction of session count from calendar DTE is
prohibited."
Invariant 9: "Trading sessions are never treated as calendar days."

Code under test:
  canonical_data/session_clock.py            :: is_xnys_session, session_bounds,
                                                xnys_holidays, xnys_sessions_between
  canonical_data/dynamic_options_valuation.py:: build_xnys_scenario_points
  domain/deterministic_option_valuation.py   :: evaluate_deterministic_scenarios
                                                (SS318-319 time_to_expiry_years)

Pure calendar + domain arithmetic. No provider, no database, no pipeline.

Run:
  venv\\Scripts\\python.exe -m pytest audit/doi/AVS-TST-DOI-001/tests/test_t5_session_calendar.py -q
"""
from __future__ import annotations

import os
import sys
from datetime import date, datetime, timedelta, timezone

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.abspath(os.path.join(_HERE, "..", "..", "..", ".."))
sys.path.insert(0, _HERE)
sys.path.insert(0, _REPO)

from canonical_data.session_clock import (  # noqa: E402
    is_xnys_session, session_bounds, xnys_holidays, xnys_sessions_between,
)
from canonical_data.dynamic_options_valuation import (  # noqa: E402
    build_xnys_scenario_points,
)
from domain.deterministic_option_valuation import (  # noqa: E402
    ScenarioTiming, evaluate_deterministic_scenarios,
)

# ---------------------------------------------------------------------------
# T5-CAL-0x .. the calendar is a REAL exchange calendar, not an approximation
# ---------------------------------------------------------------------------

def test_cal01_xnys_2026_holiday_set_is_complete():
    """A real NYSE calendar, including the two that an approximation always
    gets wrong: Good Friday (moves with Easter) and a Saturday holiday
    observed on the preceding Friday."""
    hols = xnys_holidays(2026)
    expected = {
        date(2026, 1, 1),    # New Year's Day
        date(2026, 1, 19),   # MLK (3rd Mon Jan)
        date(2026, 2, 16),   # Washington's Birthday (3rd Mon Feb)
        date(2026, 4, 3),    # GOOD FRIDAY -- Easter-derived, not a fixed date
        date(2026, 5, 25),   # Memorial Day (last Mon May)
        date(2026, 6, 19),   # Juneteenth
        date(2026, 7, 3),    # Independence Day OBSERVED (Jul 4 is a Saturday)
        date(2026, 9, 7),    # Labor Day (1st Mon Sep)
        date(2026, 11, 26),  # Thanksgiving (4th Thu Nov)
        date(2026, 12, 25),  # Christmas
    }
    assert hols == expected, sorted(hols ^ expected)


def test_cal02_thanksgiving_and_christmas_are_not_sessions():
    assert is_xnys_session(date(2026, 11, 25)) is True   # Wed before
    assert is_xnys_session(date(2026, 11, 26)) is False  # THANKSGIVING
    assert is_xnys_session(date(2026, 11, 27)) is True   # Fri after
    assert is_xnys_session(date(2026, 12, 24)) is True
    assert is_xnys_session(date(2026, 12, 25)) is False  # CHRISTMAS
    assert is_xnys_session(date(2026, 12, 26)) is False  # Saturday
    assert is_xnys_session(date(2026, 12, 28)) is True


def test_cal03_no_approximation_constant_in_session_clock():
    """Guards against a 7/5, 5/7, 1.4 or 252/365 fudge factor appearing in
    the conversion path."""
    src = open(os.path.join(_REPO, "canonical_data", "session_clock.py"),
               encoding="utf-8").read()
    for fudge in ("1.4", "0.714", "1.4286", "7/5", "5/7", "252/365", "365/252"):
        assert fudge not in src, f"approximation constant {fudge!r} present"


# ---------------------------------------------------------------------------
# T5-CAL-1x .. THE HOLIDAY FIXTURE the brief asks for:
#              10 trading sessions spanning US Thanksgiving 2026
# ---------------------------------------------------------------------------

# Start Friday 2026-11-20. The next 10 XNYS sessions are:
#   1 Mon Nov 23   2 Tue Nov 24   3 Wed Nov 25
#     (Thu Nov 26 THANKSGIVING -- skipped)
#   4 Fri Nov 27   5 Mon Nov 30   6 Tue Dec 01   7 Wed Dec 02
#   8 Thu Dec 03   9 Fri Dec 04  10 Mon Dec 07
# => 10 sessions span 17 CALENDAR days (Nov 20 -> Dec 07).
START = date(2026, 11, 20)
HOLD_SESSIONS = 10


def test_cal10_ten_sessions_over_thanksgiving_span_more_calendar_days():
    pts = build_xnys_scenario_points(
        start_session=START, planned_hold_sessions=HOLD_SESSIONS)
    late = next(p for p in pts if p.timing is ScenarioTiming.LATE)
    assert late.sessions_elapsed == HOLD_SESSIONS

    late_date = late.as_of_utc.astimezone(
        session_bounds(START)[1].tzinfo or timezone.utc).date()
    calendar_span = (late_date - START).days

    # THE INVARIANT-9 ASSERTION: sessions != calendar days
    assert calendar_span != HOLD_SESSIONS, (
        "10 trading sessions were treated as 10 calendar days")
    assert calendar_span == 17, (late_date, calendar_span)

    # and the exchange calendar agrees the span really is 10 sessions
    assert xnys_sessions_between(START, late_date) == HOLD_SESSIONS


def test_cal11_thanksgiving_is_never_a_scenario_instant():
    pts = build_xnys_scenario_points(
        start_session=START, planned_hold_sessions=HOLD_SESSIONS)
    for p in pts:
        d = p.as_of_utc.date()
        assert is_xnys_session(d), f"{p.timing} landed on non-session {d}"
        assert d != date(2026, 11, 26), "scenario instant fell on Thanksgiving"


def test_cal12_christmas_fixture_also_walks_the_calendar():
    """Second holiday fixture: 10 sessions from 2026-12-18 crosses both
    Christmas (Fri Dec 25) and New Year's Day (Fri Jan 1 2027)."""
    start = date(2026, 12, 18)
    pts = build_xnys_scenario_points(start_session=start, planned_hold_sessions=10)
    late = next(p for p in pts if p.timing is ScenarioTiming.LATE)
    late_date = late.as_of_utc.date()
    span = (late_date - start).days
    assert span != 10
    assert xnys_sessions_between(start, late_date) == 10
    for p in pts:
        assert is_xnys_session(p.as_of_utc.date())
        assert p.as_of_utc.date() not in {date(2026, 12, 25), date(2027, 1, 1)}


def test_cal13_scenario_points_are_session_close_instants():
    """SS9.4 'exact timestamps': each point must be an actual session close,
    not midnight or a naive date."""
    pts = build_xnys_scenario_points(
        start_session=START, planned_hold_sessions=HOLD_SESSIONS)
    for p in pts:
        assert p.as_of_utc.tzinfo is not None
        expected_close = session_bounds(p.as_of_utc.date())[1]
        assert p.as_of_utc == expected_close, (p.timing, p.as_of_utc, expected_close)


# ---------------------------------------------------------------------------
# T5-CAL-2x .. the PROHIBITED arithmetic must not be what the engine does
# ---------------------------------------------------------------------------

def test_cal20_engine_does_not_subtract_sessions_from_calendar_dte():
    """The load-bearing assertion of SS9.4.

    Build the Thanksgiving fixture, run the real scenario engine, and show
    that the LATE cell's time_to_expiry_years equals the EXACT-TIMESTAMP
    calendar remainder and NOT the prohibited `dte - planned_hold_sessions`.
    """
    expiry_date = date(2027, 1, 15)
    expiry_close = session_bounds(expiry_date)[1]
    pts = build_xnys_scenario_points(
        start_session=START, planned_hold_sessions=HOLD_SESSIONS)

    val = evaluate_deterministic_scenarios(
        option_side="CALL", strike=100.0, expiration_utc=expiry_close,
        target_spot=115.0, invalidation_spot=94.0, base_iv=0.30,
        scenario_points=pts, entry_ask=5.0,
        risk_free_rate=0.045, dividend_yield=0.0,
    )
    late = next(s for s in val.scenarios if s.timing is ScenarioTiming.LATE)

    # (a) what the engine actually produced: exact calendar seconds / 365d
    late_point = next(p for p in pts if p.timing is ScenarioTiming.LATE)
    exact_years = (expiry_close - late_point.as_of_utc).total_seconds() / (
        365.0 * 24 * 3600)
    assert late.time_to_expiry_years == pytest.approx(exact_years, rel=1e-12)

    # (b) the PROHIBITED computation, for contrast
    start_close = session_bounds(START)[1]
    dte_calendar_days = (expiry_close - start_close).total_seconds() / 86400.0
    prohibited_years = (dte_calendar_days - HOLD_SESSIONS) / 365.0

    # they must differ, and by the holiday+weekend gap (7 calendar days)
    assert late.time_to_expiry_years != pytest.approx(prohibited_years, rel=1e-9)
    gap_days = (prohibited_years - late.time_to_expiry_years) * 365.0
    print(f"exact={late.time_to_expiry_years:.8f}y "
          f"prohibited={prohibited_years:.8f}y gap={gap_days:.4f} calendar days")
    assert gap_days == pytest.approx(7.0, abs=1e-6), gap_days


def test_cal21_source_contains_no_session_minus_dte_arithmetic():
    """Static guard on the two DOI-5 valuation files."""
    import re
    banned = [
        r"dte\s*-\s*\w*hold", r"dte\s*-\s*\w*session",
        r"days_to_expiry\s*-\s*\w*session", r"days_to_expiry\s*-\s*\w*hold",
        r"planned_hold_sessions\s*-\s*dte", r"sessions_elapsed\s*-\s*dte",
        r"dte\s*-\s*sessions_elapsed",
    ]
    for rel in ("domain/deterministic_option_valuation.py",
                "canonical_data/dynamic_options_valuation.py",
                "canonical_data/session_clock.py"):
        src = open(os.path.join(_REPO, rel), encoding="utf-8").read()
        for pat in banned:
            assert not re.search(pat, src), f"{rel}: prohibited pattern {pat}"


def test_cal22_sessions_elapsed_is_carried_but_never_used_as_time():
    """sessions_elapsed appears in the persisted row as metadata only; the
    valuation clock is time_to_expiry_years, derived from timestamps."""
    pts = build_xnys_scenario_points(
        start_session=START, planned_hold_sessions=HOLD_SESSIONS)
    val = evaluate_deterministic_scenarios(
        option_side="CALL", strike=100.0,
        expiration_utc=session_bounds(date(2027, 1, 15))[1],
        target_spot=115.0, invalidation_spot=94.0, base_iv=0.30,
        scenario_points=pts, entry_ask=5.0,
        risk_free_rate=0.045, dividend_yield=0.0,
    )
    for row in val.to_dict()["scenarios"]:
        assert isinstance(row["sessions_elapsed"], int)
        assert isinstance(row["time_to_expiry_years"], float)
        # the two are not proportional -- proof they are separate clocks
    early = next(s for s in val.scenarios if s.timing is ScenarioTiming.EARLY)
    late = next(s for s in val.scenarios if s.timing is ScenarioTiming.LATE)
    session_ratio = late.sessions_elapsed / early.sessions_elapsed
    day_gap = (early.time_to_expiry_years - late.time_to_expiry_years) * 365.0
    print(f"early sessions={early.sessions_elapsed} late={late.sessions_elapsed} "
          f"session_ratio={session_ratio:.3f} calendar_days_between={day_gap:.2f}")
    # 4 -> 10 sessions is 6 sessions but 8 calendar days (weekend crossed)
    assert day_gap != pytest.approx(
        late.sessions_elapsed - early.sessions_elapsed, abs=1e-6)


# ---------------------------------------------------------------------------
# T5-CAL-3x .. boundary behaviour of the hold window
# ---------------------------------------------------------------------------

def test_cal30_planned_hold_bounds_enforced():
    with pytest.raises(ValueError):
        build_xnys_scenario_points(start_session=START, planned_hold_sessions=0)
    with pytest.raises(ValueError):
        build_xnys_scenario_points(start_session=START, planned_hold_sessions=21)


def test_cal31_non_session_start_is_refused():
    with pytest.raises(ValueError):
        build_xnys_scenario_points(
            start_session=date(2026, 11, 26), planned_hold_sessions=5)  # Thanksgiving


@pytest.mark.parametrize("hold", list(range(1, 21)))
def test_cal32_early_mid_late_are_monotonic_and_within_hold(hold):
    pts = build_xnys_scenario_points(start_session=START, planned_hold_sessions=hold)
    by = {p.timing: p for p in pts}
    e, m, l = (by[ScenarioTiming.EARLY], by[ScenarioTiming.MID],
               by[ScenarioTiming.LATE])
    assert 1 <= e.sessions_elapsed <= m.sessions_elapsed <= l.sessions_elapsed == hold
    assert e.as_of_utc <= m.as_of_utc <= l.as_of_utc
