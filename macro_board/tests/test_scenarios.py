"""Scenario watch (ACK 6 Oct 2026: "based on certain conditions QQQ cannot sustain a high of the year
for 3 sessions so I would position puts"). Business rules, written before the engine."""

from __future__ import annotations

import datetime as dt
import json

import numpy as np
import pandas as pd
import pytest

from macro_board import scenarios as scn

SESSIONS = pd.bdate_range("2024-01-01", periods=40)


def _closes(values):
    return pd.Series(values, index=SESSIONS[: len(values)], dtype=float)


FAILED_HIGH = {"type": "failed_extreme", "extreme": "high", "lookback": 5, "hold_sessions": 3, "min_depth_daily_moves": 0}


# --- the trigger is exactly the trader's rule ------------------------------------------------

def test_a_yearly_high_with_no_higher_close_in_three_sessions_triggers_on_the_third_close():
    c = _closes([10, 11, 12, 13, 14, 15, 14.8, 14.9, 14.7, 14.5])     # high 15 at i=5, then 3 lower closes
    events = scn.detect(FAILED_HIGH, c, daily_move_pct=pd.Series(1.0, index=c.index))
    assert list(events) == [8]                                         # trigger on the 3rd close after the high


def test_a_high_that_is_bettered_within_three_sessions_is_not_a_failure():
    c = _closes([10, 11, 12, 13, 14, 15, 14.8, 15.2, 15.1, 15.0, 14.9, 14.8, 14.7])
    events = scn.detect(FAILED_HIGH, c, daily_move_pct=pd.Series(1.0, index=c.index))
    assert 8 not in list(events) and list(events) == [10]             # only the later high (15.2 at i=7) fails


def test_the_failed_low_is_the_mirror_image():
    rule = {**FAILED_HIGH, "extreme": "low"}
    c = _closes([20, 19, 18, 17, 16, 15, 15.2, 15.1, 15.3, 15.4])
    assert list(scn.detect(rule, c, daily_move_pct=pd.Series(1.0, index=c.index))) == [8]


def test_macro_conditions_must_all_hold_on_the_trigger_day_and_missing_never_matches():
    rule = {"type": "big_day", "direction": "down", "min_daily_moves": 2.0}
    c = _closes([100, 100, 100, 96, 100, 96])
    dm = pd.Series(1.0, index=c.index)
    states = pd.DataFrame({"market_breadth": ["LOW", "LOW", "LOW", "LOW", "LOW", "MISSING"]}, index=c.index)
    assert list(scn.detect(rule, c, daily_move_pct=dm)) == [3, 5]
    assert list(scn.detect(rule, c, daily_move_pct=dm, states=states, conditions={"market_breadth": "LOW"})) == [3]


# --- forward-looking status -----------------------------------------------------------------

def test_status_watches_a_fresh_high_with_its_level_and_deadline_session():
    c = _closes([10, 11, 12, 13, 14, 15, 14.8])                        # high 15 one session ago
    future = [SESSIONS[7].date(), SESSIONS[8].date(), SESSIONS[9].date()]
    st = scn.status(FAILED_HIGH, c, daily_move_pct=pd.Series(1.0, index=c.index), future_sessions=future)
    assert st["state"] == "WATCHING" and st["level"] == 15.0
    assert st["deadline"] == str(SESSIONS[8].date())                   # 3 sessions after the high
    assert st["closes_left"] == 2


def test_status_reports_the_trigger_on_the_day_it_fires():
    c = _closes([10, 11, 12, 13, 14, 15, 14.8, 14.9, 14.7])
    st = scn.status(FAILED_HIGH, c, daily_move_pct=pd.Series(1.0, index=c.index), future_sessions=[])
    assert st["state"] == "TRIGGERED"


def test_status_is_not_active_without_a_recent_high():
    c = _closes([15, 14, 13, 12, 11, 10, 9])
    st = scn.status(FAILED_HIGH, c, daily_move_pct=pd.Series(1.0, index=c.index), future_sessions=[])
    assert st["state"] == "NOT_ACTIVE"


def test_price_met_but_macro_condition_not_yet_is_partial():
    rule = {"type": "near_extreme", "extreme": "high", "lookback": 5, "within_daily_moves": 1.0}
    c = _closes([10, 11, 12, 13, 14, 14.9])
    states = pd.DataFrame({"market_breadth": ["MID"] * 6}, index=c.index)
    st = scn.status(rule, c, daily_move_pct=pd.Series(1.0, index=c.index), future_sessions=[],
                    states=states, conditions={"market_breadth": "LOW"})
    assert st["state"] == "PARTIAL" and "market_breadth" in st["text"]


# --- judged on what a long option would have paid, not on hit rate ----------------------------

OPT = {"runway_multiple": 2, "iv_over_rv": 1.0, "spread_pct_of_premium": 4.0}


def test_an_unchanged_price_loses_time_value_and_costs_on_a_long_option():
    m = scn.option_multiple(side="PUT", entry=100.0, exit=100.0, horizon=5, sigma_annual_pct=20.0, cfg=OPT)
    assert m < 0


def test_a_large_move_in_the_options_favour_pays_and_costs_are_charged_on_both_legs():
    put_win = scn.option_multiple(side="PUT", entry=100.0, exit=95.0, horizon=5, sigma_annual_pct=20.0, cfg=OPT)
    call_loss = scn.option_multiple(side="CALL", entry=100.0, exit=95.0, horizon=5, sigma_annual_pct=20.0, cfg=OPT)
    free = scn.option_multiple(side="PUT", entry=100.0, exit=95.0, horizon=5, sigma_annual_pct=20.0,
                               cfg={**OPT, "spread_pct_of_premium": 0.0})
    assert put_win > 0 > call_loss and free > put_win


def test_outcomes_start_at_the_next_open_and_are_signed_for_the_hypothesis():
    opens = pd.Series([100, 100, 100, 100, 100], index=SESSIONS[:5], dtype=float)
    closes = pd.Series([100, 100, 98, 97, 96], index=SESSIONS[:5], dtype=float)
    out = scn.outcome(event=0, side="PUT", horizon=2, opens=opens, closes=closes,
                      daily_move_pct=pd.Series(1.0, index=SESSIONS[:5]), rv_annual_pct=pd.Series(16.0, index=SESSIONS[:5]),
                      cfg=OPT)
    assert out["entry_session"] == str(SESSIONS[1].date())
    # board convention (evidence.forward_returns): next open -> close h sessions after the trigger day
    assert out["exit_session"] == str(SESSIONS[2].date())
    assert out["side_move_pct"] == pytest.approx(2.0)                  # open 100 (i=1) -> close 98 (i=2), put view
    assert out["first"] == "FAVOURABLE"


# --- verdicts ---------------------------------------------------------------------------------

EV = {"min_effective_n": 8, "min_effective_n_holdout": 3, "lean_t_min": 1.5, "holdout_fraction": 0.25}


def _rows(n, side_moves, multiples, spacing=20):
    return [{"event": i * spacing, "side_move_pct": side_moves[i % len(side_moves)],
             "option_multiple": multiples[i % len(multiples)]} for i in range(n)]


def test_too_few_independent_windows_is_thin_whatever_the_average():
    v = scn.verdict(_rows(5, [3.0, 2.5], [1.0, 0.8]), baseline_multiple=-0.2, horizon=5, settings=EV)
    assert v["verdict"] == "THIN"


def test_a_consistent_payoff_above_buying_every_session_is_an_edge():
    v = scn.verdict(_rows(30, [2.0, 1.5, 2.5, 1.0], [0.6, 0.4, 0.9, 0.2]), baseline_multiple=-0.2, horizon=5, settings=EV)
    assert v["verdict"] == "EDGE"


def test_when_the_other_side_paid_the_verdict_says_so():
    v = scn.verdict(_rows(30, [-2.0, -1.5, -2.5, -1.0], [-0.6, -0.5, -0.7, -0.4]), baseline_multiple=-0.2,
                    horizon=5, settings=EV)
    assert v["verdict"] == "OPPOSITE"


def test_no_difference_from_buying_every_session_is_no_edge():
    v = scn.verdict(_rows(30, [0.5, -0.5, 0.4, -0.4], [-0.1, -0.3, -0.2, -0.2]), baseline_multiple=-0.2,
                    horizon=5, settings=EV)
    assert v["verdict"] == "NO_EDGE"


# --- the live record is written once and scored out of sample ----------------------------------

def test_a_live_trigger_is_recorded_once_per_session(tmp_path):
    path = tmp_path / "scenario_ledger.jsonl"
    rec = {"scenario": "failed_yearly_high", "ticker": "QQQ", "trigger_session": "2026-10-08", "side": "PUT"}
    scn.record_triggers(path, [rec])
    scn.record_triggers(path, [rec])
    assert len(path.read_text(encoding="utf-8").strip().splitlines()) == 1


def test_the_every_session_baseline_matches_the_trade_by_trade_proxy():
    idx = pd.bdate_range("2023-01-02", periods=60)
    rng = np.random.default_rng(3)
    closes = pd.Series(100 * np.exp(np.cumsum(rng.normal(0, 0.01, 60))), index=idx)
    opens = closes.shift(1).fillna(closes.iloc[0]) * (1 + rng.normal(0, 0.002, 60))
    dm = scn.daily_move_pct(closes, 10)
    rv = dm * np.sqrt(252)
    one_by_one = [scn.outcome(event=e, side="PUT", horizon=3, opens=opens, closes=closes, daily_move_pct=dm,
                              rv_annual_pct=rv, cfg=OPT) for e in range(len(idx))]
    expected = np.mean([r["option_multiple"] for r in one_by_one if r and r["option_multiple"] is not None])
    assert scn.baseline_multiple(opens, closes, rv, side="PUT", horizon=3, cfg=OPT) == pytest.approx(expected, abs=1e-5)


def test_the_vectorised_outcomes_equal_the_trade_by_trade_outcomes():
    idx = pd.bdate_range("2023-01-02", periods=80)
    rng = np.random.default_rng(11)
    closes = pd.Series(100 * np.exp(np.cumsum(rng.normal(0, 0.012, 80))), index=idx)
    opens = closes.shift(1).fillna(closes.iloc[0]) * (1 + rng.normal(0, 0.003, 80))
    dm = scn.daily_move_pct(closes, 10)
    rv = dm * np.sqrt(252)
    events = np.arange(10, 75, 3)
    arrays = [x.to_numpy(dtype=float) for x in (opens, closes, dm, rv)]
    dates = [str(d.date()) for d in idx]
    for side in ("PUT", "CALL"):
        fast = {r["event"]: r for r in scn.outcomes_vec(events, side, 4, *arrays, dates, OPT)}
        for e in events:
            slow = scn.outcome(event=int(e), side=side, horizon=4, opens=opens, closes=closes, daily_move_pct=dm,
                               rv_annual_pct=rv, cfg=OPT)
            if slow is None:
                assert int(e) not in fast
                continue
            f = fast[int(e)]
            assert f["first"] == slow["first"] and f["side_move_pct"] == pytest.approx(slow["side_move_pct"])
            if slow["option_multiple"] is None:
                assert f["option_multiple"] is None
            else:
                assert f["option_multiple"] == pytest.approx(slow["option_multiple"], rel=1e-9)


# --- many tests: an edge must survive the false-discovery check ---------------------------------

def test_benjamini_hochberg_keeps_only_results_that_beat_the_number_of_tries():
    p = [0.001, 0.008, 0.039, 0.041, 0.042, 0.06, 0.074, 0.205, 0.212, 0.216]
    assert scn.fdr_flags(p, q=0.05) == [True, True] + [False] * 8
    assert scn.fdr_flags([0.5] * 100 + [0.0001], q=0.1)[-1] is True


def test_library_wide_check_marks_edges_and_reports_the_trial_count():
    rows = [{"by_horizon": {"5": {"verdict": "EDGE", "t_edge": 4.0, "t_side": 3.0}}},
            {"by_horizon": {"5": {"verdict": "EDGE", "t_edge": 1.6, "t_side": 1.0}}}] + \
           [{"by_horizon": {"5": {"verdict": "NO_EDGE", "t_edge": 0.1, "t_side": 0.0}}} for _ in range(60)]
    summary = scn.apply_fdr(rows, q=0.10)
    assert rows[0]["by_horizon"]["5"]["survives_fdr"] is True
    assert rows[1]["by_horizon"]["5"]["survives_fdr"] is False
    assert summary["tests"] == 62 and summary["edges"] == 2 and summary["edges_surviving"] == 1
