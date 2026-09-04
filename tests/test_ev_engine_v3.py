from __future__ import annotations

import math

import pandas as pd

from vanguard.ev_engine_v3 import (
    EV3BarrierCache,
    EV3Policy,
    american_option_price,
    evaluate_contract,
    select_contract,
)
from vanguard.ev3_stage0 import DEFAULT_STOP_GRID, DEFAULT_TARGET_GRID


NOW = "2026-08-10T12:05:00Z"


def _cache(p_target: float = 0.55, p_stop: float = 0.30) -> EV3BarrierCache:
    p_timeout = 1.0 - p_target - p_stop
    rows = []
    for direction in ("CALL", "PUT"):
        rows.append(
            {
                "state_key": "NORMAL|UP|STRONG|MODERATE|MARKUP|EARLY|MID",
                "direction": direction,
                "horizon_sessions": 10,
                "target_distance_fraction": 0.10,
                "stop_distance_fraction": 0.05,
                "p_target_first": p_target,
                "p_stop_first": p_stop,
                "p_timeout": p_timeout,
                "n_effective": 250,
                "target_exit_session_mean": 4.0,
                "stop_exit_session_mean_conservative": 3.0,
                "timeout_exit_session": 10.0,
                "calculation_version": "fixture-v1",
                "schema_version": "fixture-v1",
            }
        )
    return EV3BarrierCache(pd.DataFrame(rows))


def _row(direction: str = "CALL", symbol: str = "TEST260918C00100000") -> dict:
    call = direction == "CALL"
    return {
        "ticker": "TEST",
        "canonical_direction": direction,
        "direction_status": "RESOLVED",
        "entry_spot": 100.0,
        "target_spot": 110.0 if call else 90.0,
        "invalidation_spot": 95.0 if call else 105.0,
        "horizon_bucket": "6_10D",
        "planned_hold_sessions": 10,
        "state_key": "NORMAL|UP|STRONG|MODERATE|MARKUP|EARLY|MID",
        "contract_symbol": symbol,
        "contract_strike": 100.0,
        "contract_expiry": "2026-09-18",
        "quote_timestamp_utc": "2026-08-10T12:00:00Z",
        "contract_bid": 3.8,
        "contract_ask": 4.2,
        "contract_dte": 39,
        "contract_delta": 0.52 if call else -0.48,
        "contract_gamma": 0.03,
        "contract_theta": -0.04,
        "contract_vega": 0.10,
        "contract_iv": 0.40,
        "contract_oi": 500,
        "contract_volume": 100,
        "contract_multiplier": 100,
        "risk_free_rate": 0.04,
        "dividend_yield": 0.01,
    }


def _vertical_row(direction: str = "CALL") -> dict:
    row = _row(direction)
    is_call = direction == "CALL"
    row["contract_symbol"] = f"{'BULL_CALL' if is_call else 'BEAR_PUT'}:LONG/SHORT"
    row["contract_structure"] = "BULL_CALL_DEBIT" if is_call else "BEAR_PUT_DEBIT"

    def leg(symbol: str, strike: float, bid: float, ask: float, delta: float) -> dict:
        return {
            "symbol": symbol, "strike": strike, "expiry": "2026-09-18", "dte": 39,
            "bid": bid, "ask": ask, "delta": delta, "gamma": 0.03,
            "theta": -0.04, "vega": 0.10, "iv": 0.40,
            "oi": 500, "volume": 100, "quote_timestamp_utc": "2026-08-10T12:00:00Z",
            "contract_multiplier": 100,
        }

    if is_call:
        row["long_leg"] = leg("LONG_CALL", 100.0, 3.8, 4.2, 0.52)
        row["short_leg"] = leg("SHORT_CALL", 105.0, 1.8, 2.2, 0.32)
    else:
        row["long_leg"] = leg("LONG_PUT", 100.0, 3.8, 4.2, -0.52)
        row["short_leg"] = leg("SHORT_PUT", 95.0, 1.8, 2.2, -0.32)
    return row


def test_american_option_pricer_is_direction_correct() -> None:
    call = american_option_price(110, 100, 30 / 365, 0.04, 0.0, 0.3, "CALL")
    put = american_option_price(90, 100, 30 / 365, 0.04, 0.0, 0.3, "PUT")
    assert call > 10
    assert put >= 10


def test_three_outcomes_are_exhaustive_and_timeout_is_priced() -> None:
    result = evaluate_contract(_row(), _cache(), now_utc=NOW)
    assert result["ev3_status"] == "EVALUATED_PRODUCTION_EVIDENCE"
    assert result["ev3_shadow_only"] is False
    assert math.isclose(result["ev3_p_target"] + result["ev3_p_stop"] + result["ev3_p_timeout"], 1.0)
    assert "ev3_return_timeout_base" in result
    assert result["ev3_exit_mid_timeout_stress"] <= result["ev3_exit_mid_timeout_base"]
    assert result["ev3_structure"] == "LONG_SINGLE"
    assert result["ev3_strike"] == 100.0
    assert result["ev3_expiry"] == "2026-09-18"
    assert math.isclose(
        result["ev3_risk_unit_premium"],
        result["ev3_entry_debit_per_share"] * result["ev3_contract_multiplier"],
    )


def test_negative_contract_ev_remains_negative() -> None:
    result = evaluate_contract(_row(), _cache(p_target=0.05, p_stop=0.90), now_utc=NOW)
    assert result["ev3_ev_conservative_return"] < 0
    assert result["ev3_absolute_state"] == "NEGATIVE_EV"
    assert result["ev3_capital_eligible"] is False


def test_call_and_put_use_direction_specific_barrier_cells() -> None:
    call = evaluate_contract(_row("CALL"), _cache(), now_utc=NOW)
    put = evaluate_contract(_row("PUT", "TEST260918P00100000"), _cache(), now_utc=NOW)
    assert call["ev3_direction"] == "CALL"
    assert put["ev3_direction"] == "PUT"
    assert call["ev3_return_target_base"] > call["ev3_return_stop_base"]
    assert put["ev3_return_target_base"] > put["ev3_return_stop_base"]


def test_dte_does_not_select_barrier_horizon() -> None:
    row = _row()
    row["contract_dte"] = 90
    result = evaluate_contract(row, _cache(), now_utc=NOW)
    assert result["ev3_horizon_sessions"] == 10


def test_unsupported_hold_fails_closed_instead_of_nearest_mapping() -> None:
    row = _row()
    row["planned_hold_sessions"] = 8
    result = evaluate_contract(row, _cache(), now_utc=NOW)
    assert result["ev3_reason_code"] == "REJECT_HORIZON"


def test_unseen_state_uses_governed_core_aligned_five_of_seven_fallback() -> None:
    row = _row()
    row["state_key"] = "NORMAL|UP|STRONG|MODERATE|DISTRIBUTION|LATE|MID"
    result = evaluate_contract(row, _cache(), now_utc=NOW)
    assert result["ev3_status"] == "EVALUATED_PRODUCTION_EVIDENCE"
    assert result["ev3_state_match_type"] == "FALLBACK_5_OF_7"
    assert math.isclose(result["ev3_state_similarity"], 5 / 7)
    assert result["ev3_state_fallback_uncertainty_return"] == 0.02


def test_missing_exit_timing_is_conservatively_defaulted_and_penalised() -> None:
    frame = _cache().frame
    frame.loc[frame["direction"] == "CALL", "target_exit_session_mean"] = math.nan
    result = evaluate_contract(_row(), EV3BarrierCache(frame), now_utc=NOW)
    assert result["ev3_status"] == "EVALUATED_PRODUCTION_EVIDENCE"
    assert "target_exit_session_mean" in result["ev3_exit_session_defaulted_fields_json"]
    assert result["ev3_exit_session_default_uncertainty_return"] == 0.01


def test_state_fallback_refuses_weak_or_cross_regime_matches() -> None:
    weak = _row()
    weak["state_key"] = "NORMAL|UP|WEAK|HIGH|DISTRIBUTION|LATE|HIGH"
    assert evaluate_contract(weak, _cache(), now_utc=NOW)["ev3_reason_code"] == "REJECT_BARRIER_STATE_UNAVAILABLE"

    cross_regime = _row()
    cross_regime["state_key"] = "HIGH_VOL|UP|STRONG|MODERATE|MARKUP|EARLY|MID"
    assert evaluate_contract(cross_regime, _cache(), now_utc=NOW)["ev3_reason_code"] == "REJECT_BARRIER_STATE_UNAVAILABLE"


def test_barrier_policy_grid_covers_wider_valid_trade_geometry() -> None:
    assert 0.40 in DEFAULT_TARGET_GRID
    assert 0.20 in DEFAULT_STOP_GRID


def test_wider_spread_cannot_improve_robust_ev() -> None:
    tight = _row()
    wide = _row()
    wide["contract_bid"] = 3.4
    wide["contract_ask"] = 4.6
    tight_result = evaluate_contract(tight, _cache(), now_utc=NOW)
    wide_result = evaluate_contract(wide, _cache(), now_utc=NOW)
    assert wide_result["ev3_ev_lower_bound_return"] < tight_result["ev3_ev_lower_bound_return"]


def test_stale_quote_rejects_and_shadow_never_grants_capital() -> None:
    stale = evaluate_contract(_row(), _cache(), now_utc="2026-08-12T12:00:00Z")
    assert stale["ev3_reason_code"] == "REJECT_QUOTE_STALE"
    live = evaluate_contract(_row(), _cache(), now_utc=NOW)
    assert live["ev3_capital_eligible"] is False


def test_selected_contract_cannot_bypass_liquidity_policy() -> None:
    low_oi = _row()
    low_oi["contract_oi"] = 49
    assert evaluate_contract(low_oi, _cache(), now_utc=NOW)["ev3_reason_code"] == "REJECT_LIQUIDITY"

    zero_volume = _row()
    zero_volume["contract_volume"] = 0
    assert evaluate_contract(zero_volume, _cache(), now_utc=NOW)["ev3_reason_code"] == "REJECT_LIQUIDITY"

    wide = _row()
    wide["contract_bid"] = 3.2
    wide["contract_ask"] = 4.8
    assert evaluate_contract(wide, _cache(), now_utc=NOW)["ev3_reason_code"] == "REJECT_LIQUIDITY_SPREAD"

    extreme_but_valid = _row()
    extreme_but_valid["contract_bid"] = 0.1
    extreme_but_valid["contract_ask"] = 1.0
    assert evaluate_contract(extreme_but_valid, _cache(), now_utc=NOW)["ev3_reason_code"] == "REJECT_LIQUIDITY_SPREAD"

    zero_bid = _row()
    zero_bid["contract_bid"] = 0.0
    assert evaluate_contract(zero_bid, _cache(), now_utc=NOW)["ev3_reason_code"] == "REJECT_LIQUIDITY_ZERO_BID"


def test_selector_uses_lower_bound_and_is_bounded() -> None:
    tight = _row(symbol="TIGHT")
    wide = _row(symbol="WIDE")
    wide["contract_bid"] = 3.4
    wide["contract_ask"] = 4.6
    selected, evaluations = select_contract([wide, tight], _cache(), now_utc=NOW)
    assert selected["ev3_contract_symbol"] == "TIGHT"
    assert selected["ev3_candidates_evaluated"] == 2
    assert selected["ev3_argmax_margin"] > 0
    assert selected["ev3_runner_up_lower_bound_return"] is not None
    assert len(evaluations) == 2


def test_selector_enforces_twelve_contract_scope_cap() -> None:
    candidates = []
    for index in range(15):
        candidate = _row(symbol=f"TEST{index:02d}")
        candidates.append(candidate)
    selected, evaluations = select_contract(candidates, _cache(), now_utc=NOW)
    assert selected["ev3_candidates_received"] == 15
    assert selected["ev3_candidates_evaluated"] == 12
    assert len(evaluations) == 12


def test_selector_reports_child_rejection_counts_when_no_contract_is_evaluable() -> None:
    stale = _row(symbol="STALE")
    illiquid = _row(symbol="ILLIQUID")
    illiquid["contract_volume"] = 0
    selected, evaluations = select_contract(
        [stale, illiquid],
        _cache(),
        now_utc="2026-08-12T12:00:00Z",
    )
    assert selected["ev3_reason_code"] == "REJECT_NO_EVALUABLE_CONTRACT"
    assert "child_rejections=" in selected["ev3_reason_detail"]
    assert "REJECT_QUOTE_STALE:2" in selected["ev3_reason_detail"]
    assert selected["ev3_child_rejection_counts_json"] == '{"REJECT_QUOTE_STALE": 2}'
    assert len(evaluations) == 2


def test_qualitative_conviction_cannot_multiply_ev() -> None:
    low = _row()
    high = _row()
    low["conviction"] = 1
    high["conviction"] = 100
    a = evaluate_contract(low, _cache(), now_utc=NOW)
    b = evaluate_contract(high, _cache(), now_utc=NOW)
    assert a["ev3_ev_lower_bound_return"] == b["ev3_ev_lower_bound_return"]


def test_vertical_debit_engine_prices_bull_call_and_bear_put() -> None:
    for direction in ("CALL", "PUT"):
        result = evaluate_contract(_vertical_row(direction), _cache(), now_utc=NOW)
        assert result["ev3_status"] == "EVALUATED_PRODUCTION_EVIDENCE"
        assert result["ev3_structure"] == (
            "BULL_CALL_DEBIT" if direction == "CALL" else "BEAR_PUT_DEBIT"
        )
        assert result["ev3_max_loss_per_contract"] == result["ev3_risk_unit_premium"]
        assert result["ev3_max_profit_per_contract"] > 0
        assert result["ev3_return_target_base"] > result["ev3_return_stop_base"]
        assert result["ev3_short_assignment_risk_modelled"] is False
        assert result["ev3_capital_eligible"] is False


def test_vertical_debit_rejects_bad_geometry_and_multiplier_mismatch() -> None:
    bad_geometry = _vertical_row("CALL")
    bad_geometry["long_leg"], bad_geometry["short_leg"] = (
        bad_geometry["short_leg"], bad_geometry["long_leg"]
    )
    assert evaluate_contract(bad_geometry, _cache(), now_utc=NOW)["ev3_reason_code"] == "REJECT_VERTICAL_GEOMETRY"

    mismatch = _vertical_row("PUT")
    mismatch["short_leg"]["contract_multiplier"] = 10
    assert evaluate_contract(mismatch, _cache(), now_utc=NOW)["ev3_reason_code"] == "REJECT_VERTICAL_MULTIPLIER"


def test_selector_compares_long_single_and_vertical_on_same_lower_bound_objective() -> None:
    selected, evaluations = select_contract([_row(), _vertical_row()], _cache(), now_utc=NOW)
    assert selected["ev3_structure"] in {"LONG_SINGLE", "BULL_CALL_DEBIT"}
    assert selected["ev3_candidates_evaluated"] == 2
    assert len(evaluations) == 2
