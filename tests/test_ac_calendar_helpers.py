"""Saved-only exact-session timing; no provider/pipeline imports or wall-clock estimates."""
from copy import deepcopy
from datetime import date
import pytest
from domain.trade_timing import after_sessions, day, remaining_hold, sessions_between, timing_for_row


@pytest.mark.parametrize('hold',[1,2,3,4,5,7,21,61,252,666])
def test_any_positive_session_hold_is_preserved(hold):
    result=timing_for_row(dict(planned_hold_sessions=hold,expiry='2030-01-18'),
                          planned_at='2026-11-11',as_of='2026-11-12T15:00:00Z')
    assert result['planned_hold_sessions']==hold
    assert result['remaining_hold_sessions']==hold  # current session not complete
    assert result['minimum_required_sessions']==hold+8
    assert result['planned_short_1_5'] is (1<=hold<=5)


def test_holidays_and_early_close_are_sessions_not_calendar_days():
    assert sessions_between(day('2026-09-04'),day('2026-09-08'))==1  # Labor Day
    assert sessions_between(day('2026-11-25'),day('2026-11-27'))==1  # Thanksgiving, early close
    assert after_sessions(day('2026-11-25'),1)==date(2026,11,27)
    assert sessions_between(day('2026-12-24'),day('2027-01-04'))==5


def test_remaining_hold_ages_only_completed_sessions_not_partial_day_or_weekend():
    assert remaining_hold(3,'2026-11-25','2026-11-27T17:59:00Z')['remaining_hold_sessions']==3
    assert remaining_hold(3,'2026-11-25','2026-11-27T18:01:00Z')['remaining_hold_sessions']==2
    assert remaining_hold(3,'2026-11-25','2026-11-29')['remaining_hold_sessions']==2
    assert remaining_hold(1,'2026-11-25','2026-11-27T18:01:00Z')['hold_clock_state']=='EXHAUSTED'
    assert day('2026-11-13T00:30:00Z')==date(2026,11,12)


def test_four_clocks_never_substitute_for_each_other():
    row=dict(planned_hold_sessions=52,anticipated_sessions_q50=22,anticipated_sessions_q80=52,
             scenario_exit_sessions=22,ev3_planned_hold_sessions=20,dte=99)
    original=deepcopy(row)
    result=timing_for_row(row,planned_at='2026-11-11',as_of='2026-11-12T21:01:00Z')
    assert [result[k] for k in ('arrival_median_sessions','planned_hold_sessions','remaining_hold_sessions','valuation_horizon_sessions')]==[22,52,51,22]
    assert result['empirical_horizon_state']=='DIFFERS_FROM_PLANNED_HOLD'
    assert row==original


def test_missing_dates_and_holds_stay_explicit_not_five_or_twenty():
    result=timing_for_row(dict(dte=99,contract_dte=67))
    assert result['planned_hold_sessions'] is None
    assert result['remaining_hold_sessions'] is None
    assert result['valuation_horizon_sessions'] is None
    assert result['expiry_session_check_state']=='UNASSESSED_MISSING_DATES'
