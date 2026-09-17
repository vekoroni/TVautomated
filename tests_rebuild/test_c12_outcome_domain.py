"""P0-8 domain: geometry classification, first passage with censoring, estimators, base rate."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from avshunter.c12_outcome.base_rate import average_true_range, matched_outcomes
from avshunter.c12_outcome.estimators import (
    CENSOR, STOP, TARGET, EventRecord, aalen_johansen, block_bootstrap, to_event,
)
from avshunter.c12_outcome.geometry import classify
from avshunter.c12_outcome.model import (
    Bar, ContractState, Direction, InvalidationState, OutcomeState, TargetState,
)
from avshunter.c12_outcome.passage import evaluate_passage
from avshunter.shared.xnys_calendar import is_xnys_session

WINDOW = 20


def sessions_after(start: date, count: int) -> list[date]:
    out, day = [], start
    while len(out) < count:
        day += timedelta(days=1)
        if is_xnys_session(day):
            out.append(day)
    return out


def bars_for(sessions, rows):
    return {s: Bar(s, *row) for s, row in zip(sessions, rows)}


EVIDENCE = date(2026, 9, 2)


# --- geometry ----------------------------------------------------------------

def test_valid_bull_geometry():
    g = classify("CALL", 100, 95, 110, "FORM261016C00105000")
    assert (g.direction, g.invalidation_state, g.target_state, g.contract_state) == (
        Direction.BULL, InvalidationState.VALID, TargetState.LEVEL, ContractState.VALID)


@pytest.mark.parametrize("target", [0, -8.67, 95])
def test_legacy_invalid_targets(target):
    g = classify("CALL", 100, 95, target, None)
    assert g.target_state is TargetState.INVALID_LEGACY
    assert g.scorable


def test_negative_put_target_is_invalid_legacy():
    g = classify("PUT", 9.54, 15.61, -8.67, "LPTH261016P00010000")
    assert g.target_state is TargetState.INVALID_LEGACY
    assert g.invalidation_state is InvalidationState.VALID


def test_call_thesis_with_put_contract():
    g = classify("CALL", 245.10, 234.75, 0, "ABBV260821P00245000")
    assert g.contract_state is ContractState.SIDE_MISMATCH


@pytest.mark.parametrize("direction, inv, state", [
    ("CALL", None, InvalidationState.MISSING),
    ("CALL", 0, InvalidationState.NON_POSITIVE),
    ("CALL", 105, InvalidationState.WRONG_SIDE),
    ("PUT", 95, InvalidationState.WRONG_SIDE),
])
def test_invalidation_classes(direction, inv, state):
    g = classify(direction, 100, inv, None, None)
    assert g.invalidation_state is state and not g.scorable


def test_missing_target_is_none_and_unknown_direction_not_scorable():
    assert classify("CALL", 100, 95, None, None).target_state is TargetState.NONE
    assert not classify("STRADDLE", 100, 95, 110, None).scorable


# --- first passage -------------------------------------------------------------

def test_target_first_on_session_three():
    s = sessions_after(EVIDENCE, WINDOW)
    rows = [(100, 101, 99, 100), (100, 104, 97, 103), (103, 111, 102, 110)] + [(110, 111, 109, 110)] * 17
    out = evaluate_passage(classify("CALL", 100, 95, 110, None), s, bars_for(s, rows), WINDOW)
    assert (out.state, out.resolution_session, out.exit_price) == (OutcomeState.TARGET_FIRST, 3, 110)
    assert out.r_multiple == pytest.approx(2.0)


def test_stop_gap_fills_at_open():
    s = sessions_after(EVIDENCE, WINDOW)
    rows = [(100, 101, 99, 100), (92, 93, 90, 91)]
    out = evaluate_passage(classify("CALL", 100, 95, 110, None), s[:2], bars_for(s, rows), WINDOW)
    assert (out.state, out.exit_price) == (OutcomeState.STOP_FIRST, 92)
    assert out.return_to_exit_pct == pytest.approx(-0.08)


def test_same_session_touch_is_ambiguous():
    s = sessions_after(EVIDENCE, WINDOW)
    out = evaluate_passage(classify("CALL", 100, 95, 110, None), s[:1], bars_for(s, [(100, 112, 94, 100)]), WINDOW)
    assert out.state is OutcomeState.AMBIGUOUS


def test_bear_is_mirrored():
    s = sessions_after(EVIDENCE, WINDOW)
    rows = [(100, 101, 95, 96), (96, 97, 89, 90)]
    out = evaluate_passage(classify("PUT", 100, 105, 90, None), s[:2], bars_for(s, rows), WINDOW)
    assert (out.state, out.resolution_session, out.exit_price) == (OutcomeState.TARGET_FIRST, 2, 90)


def test_open_censored_then_resolved_later():
    s = sessions_after(EVIDENCE, WINDOW)
    rows = [(100, 102, 98, 101)] * 4 + [(101, 111, 100, 110)] + [(110, 110, 110, 110)] * 15
    bars = bars_for(s, rows)
    early = evaluate_passage(classify("CALL", 100, 95, 110, None), s[:3], {d: bars[d] for d in s[:3]}, WINDOW)
    assert (early.state, early.sessions_observed, early.resolution_session) == (OutcomeState.OPEN_CENSORED, 3, None)
    late = evaluate_passage(classify("CALL", 100, 95, 110, None), s, bars, WINDOW)
    assert (late.state, late.resolution_session) == (OutcomeState.TARGET_FIRST, 5)


def test_timeout_after_full_window():
    s = sessions_after(EVIDENCE, WINDOW)
    rows = [(100, 102, 98, 101)] * WINDOW
    out = evaluate_passage(classify("CALL", 100, 95, 110, None), s, bars_for(s, rows), WINDOW)
    assert (out.state, out.sessions_observed, out.exit_price) == (OutcomeState.TIMEOUT, WINDOW, 101)
    assert out.mfe_pct == pytest.approx(0.02) and out.mae_pct == pytest.approx(-0.02)


def test_no_target_resolves_only_by_stop_or_timeout():
    s = sessions_after(EVIDENCE, WINDOW)
    rows = [(100, 150, 99, 140)] + [(140, 141, 139, 140)] * 19
    out = evaluate_passage(classify("CALL", 100, 95, 0, None), s, bars_for(s, rows), WINDOW)
    assert out.state is OutcomeState.TIMEOUT


def test_data_gap_censors_before_missing_bar():
    s = sessions_after(EVIDENCE, WINDOW)
    bars = bars_for(s, [(100, 101, 99, 100)] * 3)
    del bars[s[1]]
    out = evaluate_passage(classify("CALL", 100, 95, 110, None), s[:3], bars, WINDOW)
    assert (out.state, out.sessions_observed) == (OutcomeState.DATA_GAP, 1)


def test_holiday_skipped_in_session_count():
    s = sessions_after(date(2026, 9, 4), 1)   # Friday before Labor Day
    assert s == [date(2026, 9, 8)]


def test_not_scorable_reason():
    out = evaluate_passage(classify("CALL", 100, 105, 110, None), [], {}, WINDOW)
    assert out.state is OutcomeState.NOT_SCORABLE and "WRONG_SIDE" in out.reason


# --- estimators ----------------------------------------------------------------

def test_aalen_johansen_hand_computed_with_censoring():
    events = [EventRecord(1, TARGET, "a"), EventRecord(2, STOP, "a"), EventRecord(2, CENSOR, "b"),
              EventRecord(3, TARGET, "b")]
    curve = aalen_johansen(events, 3)
    # t1: n=4 dT=1 -> CIF_T=0.25, S=0.75; t2: n=3 dS=1 -> CIF_S=0.75*1/3=0.25, S=0.5; t3: n=1 dT=1 -> CIF_T=0.25+0.5=0.75
    assert curve.target == pytest.approx((0.25, 0.25, 0.75))
    assert curve.stop == pytest.approx((0.0, 0.25, 0.25))
    assert curve.survival[-1] == pytest.approx(0.0)


def test_ambiguous_counts_as_stop_and_timeout_is_censored():
    s = sessions_after(EVIDENCE, WINDOW)
    amb = evaluate_passage(classify("CALL", 100, 95, 110, None), s[:1], bars_for(s, [(100, 112, 94, 100)]), WINDOW)
    assert to_event(amb, "x").cause == STOP
    timeout = evaluate_passage(classify("CALL", 100, 95, 110, None), s, bars_for(s, [(100, 101, 99, 100)] * WINDOW), WINDOW)
    assert (to_event(timeout, "x").cause, to_event(timeout, "x").time) == (CENSOR, WINDOW)


def test_block_bootstrap_uses_session_blocks_and_is_seeded():
    events = [EventRecord(1, TARGET, "s1"), EventRecord(1, STOP, "s1"), EventRecord(2, TARGET, "s2"), EventRecord(3, CENSOR, "s3")]
    first = block_bootstrap(events, 3, resamples=200, seed=7, lower_quantile=0.05, upper_quantile=0.95)
    again = block_bootstrap(events, 3, resamples=200, seed=7, lower_quantile=0.05, upper_quantile=0.95)
    assert first == again and first.blocks == 3
    low, point, high = first.target_by_final_session
    assert low <= point <= high


# --- base rate -----------------------------------------------------------------

def test_average_true_range():
    start = date(2026, 8, 3)
    history = [Bar(start + timedelta(days=i), 100, 102, 98, 100) for i in range(15)]
    assert average_true_range(history, 14) == pytest.approx(4.0)
    assert average_true_range(history[:14], 14) is None


def test_matched_base_rate_on_synthetic_universe():
    s = sessions_after(EVIDENCE, WINDOW)
    start = date(2026, 8, 3)
    history = [Bar(start + timedelta(days=i), 100, 102, 98, 100) for i in range(15)]   # ATR 4
    up = bars_for(s, [(100, 109, 99, 108)] + [(108, 108, 108, 108)] * 19)   # +2 ATR target hit session 1
    down = bars_for(s, [(100, 101, 91, 92)] + [(92, 92, 92, 92)] * 19)     # -2 ATR stop hit session 1
    flat = bars_for(s, [(100, 101, 99, 100)] * WINDOW)
    universe = {"UP": (history, up), "DOWN": (history, down), "FLAT": (history, flat)}
    results = dict(matched_outcomes(Direction.BULL, 2.0, 2.0, universe, s, WINDOW, 14))
    assert results["UP"].state is OutcomeState.TARGET_FIRST
    assert results["DOWN"].state is OutcomeState.STOP_FIRST
    assert results["FLAT"].state is OutcomeState.TIMEOUT
