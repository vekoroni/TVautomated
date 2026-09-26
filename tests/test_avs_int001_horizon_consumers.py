"""Horizon and unit contracts at live Evening consumers."""

import pytest
from datetime import datetime, timezone

from eod_candidate_engine import _exit_intelligence_plan
from trigger_layer import _compute_ev
from execution_decision_engine import _build_signal_pkg
from execution_intelligence import build_execution_context_from_row
from vanguard.execution.strategies.liquidity_gate import run as liquidity_run
from morning_validation import compute_exit_plan


def test_eod_exit_fallback_uses_cumulative_ten_session_move():
    row = {
        "signal_price": 100.0,
        "time_horizon": "6_10d",
        "l3_expected_move_1_5d": 5.0,
        "l3_expected_move_6_10d": 2.0,
    }
    plan = _exit_intelligence_plan(row, "CALL", 90.0, 0.0, 0.0)
    assert plan["exit_t2"] == pytest.approx(107.0)


def test_eod_exit_fallback_uses_cumulative_twenty_session_move():
    row = {
        "signal_price": 100.0,
        "time_horizon": "11_20d",
        "l3_expected_move_1_5d": 5.0,
        "l3_expected_move_6_10d": 2.0,
        "l3_expected_move_11_20d": 2.0,
    }
    plan = _exit_intelligence_plan(row, "PUT", 110.0, 0.0, 0.0)
    assert plan["exit_t2"] == pytest.approx(91.0)


def test_trigger_ev_ten_session_legacy_path_sums_increments():
    assert _compute_ev({
        "win_rate_10d": 0.6,
        "l3_expected_move_1_5d": 5.0,
        "l3_expected_move_6_10d": 2.0,
    }) == pytest.approx(0.042)


def test_execution_package_ten_session_legacy_path_sums_increments():
    pkg = _build_signal_pkg({
        "ticker": "TEST", "win_rate_10d": 0.6,
        "l3_expected_move_1_5d": 5.0,
        "l3_expected_move_6_10d": 2.0,
    })
    assert pkg["actuarial"]["expected_move_10d"] == pytest.approx(0.07)


def test_execution_package_does_not_treat_display_percent_as_fraction():
    pkg = _build_signal_pkg({
        "ticker": "TEST", "expected_move_10d": 7.0,
        "l3_expected_move_1_5d": 5.0,
        "l3_expected_move_6_10d": 2.0,
    })
    assert pkg["actuarial"]["expected_move_10d"] == pytest.approx(0.07)


def test_unqualified_move_without_unit_is_not_used_for_execution_ev():
    pkg = _build_signal_pkg({"ticker": "TEST", "expected_move_10d": 0.5})
    assert pkg["actuarial"]["expected_move_10d"] is None


def test_stock_move_never_activates_option_return_spread_gate():
    ctx = build_execution_context_from_row({
        "ticker": "TEST", "signal_price": 100.0,
        "l3_expected_move_1_5d": 25.0,
        "premium": 5.0, "contract_oi": 600,
        "contract_spread_pct": 0.19,
    }, datetime(2026, 9, 25, 13, 0, tzinfo=timezone.utc),
       datetime(2026, 9, 25, 19, 0, tzinfo=timezone.utc))
    assert ctx.expected_move_basis == "UNDERLYING_FRACTION"
    result = liquidity_run(ctx)
    assert "EV BLOCK" not in result.detail
    assert "BORDERLINE" in result.detail

    ctx.expected_move_basis = "OPTION_RETURN_FRACTION"
    ctx.expected_move_pct = 0.05
    assert "EV BLOCK" in liquidity_run(ctx).detail


def test_incomplete_ten_session_path_is_unknown_not_five_day_substitute():
    row = {"win_rate_10d": 0.6, "l3_expected_move_6_10d": 2.0}
    assert _compute_ev(row) == 0.0
    assert _build_signal_pkg(row)["actuarial"]["expected_move_10d"] is None


def test_morning_exit_converts_percent_to_dollars_at_current_spot():
    plan = compute_exit_plan({
        "direction": "CALL", "underlying_price": 200.0,
        "wbs_wall_price": 220.0, "wbs_grade": "POSSIBLE",
        "l3_expected_move_1_5d": 5.0,
        "l3_expected_move_6_10d": 2.0,
    })
    assert plan["exit_garch_covers_pct"] == pytest.approx(50.0)
    assert plan["exit_mode"] == "SCALE_AT_WALL"
