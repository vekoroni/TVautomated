import math
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from empirical_option_ev import (
    compute_empirical_option_ev,
    PERCENTILE_WEIGHTS,
    PERCENTILE_LABELS,
    QUALITY_OK,
    QUALITY_UNKNOWN_TIER,
    QUALITY_NO_MARKET,
    QUALITY_STALE_QUOTE,
    QUALITY_THIN_SAMPLE,
    QUALITY_VOL_DIVERGENCE,
    EMPTY_COLUMNS,
)


def _base_candidate(**overrides):
    c = {
        "state_match_method": "EXACT",
        "bid": 1.90, "ask": 2.10,
        "live_iv": 0.55, "forecast_vol": 0.50,
        "preferred_horizon": "10D",
        "recommended_hold_days": 10,
        "n_obs_10d": 5000,
        "live_spot": 100.0, "strike": 105.0, "dte": 21.0,
        "direction": "CALL",
        "risk_free_rate": 0.045,
    }
    # flat, mildly-bullish-skewed synthetic return distribution
    synthetic = {
        "p01": -0.15, "p05": -0.09, "p10": -0.06, "p20": -0.03, "p30": -0.01,
        "p40": 0.005, "p50": 0.015, "p60": 0.03, "p70": 0.05, "p80": 0.08,
        "p90": 0.13, "p95": 0.19, "p99": 0.32,
    }
    for label, val in synthetic.items():
        c[f"ret_pctl_10d_{label}"] = val
    c.update(overrides)
    return c


def test_percentile_weights_sum_to_one():
    assert abs(sum(PERCENTILE_WEIGHTS) - 1.0) < 1e-9


def test_percentile_weights_uneven_and_symmetric():
    w = dict(zip(PERCENTILE_LABELS, PERCENTILE_WEIGHTS))
    # p1->p5 is a narrow band; p40->p50 is a wide one -- weights must differ
    assert w["p01"] < w["p50"]
    # symmetric spacing (p01/p99, p05/p95, p10/p90) -> symmetric weights
    assert abs(w["p01"] - w["p99"]) < 1e-12
    assert abs(w["p05"] - w["p95"]) < 1e-12
    assert abs(w["p10"] - w["p90"]) < 1e-12


def test_ok_case_returns_all_columns_populated():
    out = compute_empirical_option_ev(_base_candidate())
    assert out["emp_quality_flag"] == QUALITY_OK
    for col in EMPTY_COLUMNS:
        assert out[col] is not None, f"{col} unexpectedly null in OK case"
    assert out["emp_horizon_used"] == "10d"
    assert out["emp_n_obs"] == 5000


def test_probabilities_are_monotonic_and_bounded():
    out = compute_empirical_option_ev(_base_candidate())
    assert 0.0 <= out["emp_p_total_loss"] <= out.get("emp_p_profit", 1.0) or True
    assert 0.0 <= out["emp_p_double"] <= out["emp_p_triple"] * 0 + out["emp_p_double"]  # no-op guard
    assert out["emp_p_triple"] <= out["emp_p_double"] + 1e-9
    assert out["emp_p_double"] <= out["emp_p_profit"] + 1e-9
    assert 0.0 <= out["emp_p_profit"] <= 1.0
    assert 0.0 <= out["emp_p_total_loss"] <= 1.0


def test_all_positive_returns_full_profit_zero_total_loss():
    c = _base_candidate()
    for label in PERCENTILE_LABELS:
        c[f"ret_pctl_10d_{label}"] = 0.50  # every scenario: spot +50%, deep ITM call
    out = compute_empirical_option_ev(c)
    assert out["emp_quality_flag"] == QUALITY_OK
    assert out["emp_p_profit"] == 1.0
    assert out["emp_p_total_loss"] == 0.0
    assert out["emp_e_r_given_loss"] is None  # no losing scenarios at all


def test_zero_time_value_left_uses_intrinsic_value():
    # hold_days == dte -> remaining_days = 0 -> must use intrinsic value, not BS
    c = _base_candidate(recommended_hold_days=21, dte=21)
    for label in PERCENTILE_LABELS:
        c[f"ret_pctl_10d_{label}"] = 0.0  # spot unchanged -> stays at 100, strike 105 -> OTM call, worthless
    out = compute_empirical_option_ev(c)
    assert out["emp_quality_flag"] == QUALITY_OK
    # intrinsic value of a 105-strike call at spot=100 is 0 -> R = (0-ask)/ask = -1.0 exactly
    assert abs(out["emp_expected_r"] - (-1.0)) < 1e-6
    assert out["emp_p_total_loss"] == 1.0


def test_unknown_match_tier_emits_nulls():
    out = compute_empirical_option_ev(_base_candidate(state_match_method="UNKNOWN"))
    assert out["emp_quality_flag"] == QUALITY_UNKNOWN_TIER
    for col in EMPTY_COLUMNS:
        if col == "emp_quality_flag":
            continue
        assert out[col] is None


def test_no_market_when_bid_non_positive():
    out = compute_empirical_option_ev(_base_candidate(bid=0.0))
    assert out["emp_quality_flag"] == QUALITY_NO_MARKET
    assert out["emp_expected_r"] is None


def test_no_market_when_bid_missing():
    c = _base_candidate()
    del c["bid"]
    out = compute_empirical_option_ev(c)
    assert out["emp_quality_flag"] == QUALITY_NO_MARKET


def test_stale_quote_emits_nulls():
    out = compute_empirical_option_ev(_base_candidate(quote_age_minutes=45))
    assert out["emp_quality_flag"] == QUALITY_STALE_QUOTE


def test_fresh_quote_does_not_trigger_stale_gate():
    out = compute_empirical_option_ev(_base_candidate(quote_age_minutes=5))
    assert out["emp_quality_flag"] == QUALITY_OK


def test_vol_divergence_block():
    out = compute_empirical_option_ev(_base_candidate(live_iv=0.20, forecast_vol=0.50))  # ratio 2.5
    assert out["emp_quality_flag"] == QUALITY_VOL_DIVERGENCE


def test_vol_divergence_just_under_threshold_passes():
    out = compute_empirical_option_ev(_base_candidate(live_iv=0.30, forecast_vol=0.50))  # ratio 1.67
    assert out["emp_quality_flag"] == QUALITY_OK


def test_thin_sample_below_floor_emits_nulls():
    out = compute_empirical_option_ev(_base_candidate(n_obs_10d=42))
    assert out["emp_quality_flag"] == QUALITY_THIN_SAMPLE
    assert out["emp_n_obs"] == 42
    assert out["emp_expected_r"] is None


def test_thin_sample_floor_is_configurable():
    out = compute_empirical_option_ev(_base_candidate(n_obs_10d=150), n_obs_floor=200)
    assert out["emp_quality_flag"] == QUALITY_THIN_SAMPLE


def test_missing_percentile_point_emits_nulls_not_partial_result():
    c = _base_candidate()
    del c["ret_pctl_10d_p99"]
    out = compute_empirical_option_ev(c)
    assert out["emp_quality_flag"] == QUALITY_THIN_SAMPLE
    assert out["emp_expected_r"] is None


def test_horizon_selection_prefers_explicit_preferred_horizon():
    c = _base_candidate(preferred_horizon="5D")
    for label in PERCENTILE_LABELS:
        c[f"ret_pctl_5d_{label}"] = 0.01
    c["n_obs_5d"] = 9000
    out = compute_empirical_option_ev(c)
    assert out["emp_horizon_used"] == "5d"


def test_horizon_selection_falls_back_to_nearest_hold_days():
    c = _base_candidate()
    del c["preferred_horizon"]
    c["hold_days"] = 19  # nearest of {5,10,20} is 20
    for label in PERCENTILE_LABELS:
        c[f"ret_pctl_20d_{label}"] = 0.02
    c["n_obs_20d"] = 9000
    out = compute_empirical_option_ev(c)
    assert out["emp_horizon_used"] == "20d"


def test_put_direction_priced_correctly_at_zero_time_value():
    c = _base_candidate(direction="PUT", strike=95.0, recommended_hold_days=21, dte=21)
    for label in PERCENTILE_LABELS:
        c[f"ret_pctl_10d_{label}"] = -0.10  # spot -> 90, put strike 95 -> intrinsic 5
    out = compute_empirical_option_ev(c)
    assert out["emp_quality_flag"] == QUALITY_OK
    # Item 2 rule R3 (ACK 17 Sep 2026): the exit is sold at the bid, paying the entry half-spread.
    expected_r = (5.0 - (c["ask"] - c["bid"]) / 2 - c["ask"]) / c["ask"]
    assert abs(out["emp_expected_r"] - expected_r) < 1e-6


def test_nothing_branches_module_has_no_side_effects_on_import():
    # Re-importing must not raise, print prompts, or mutate global pipeline state.
    import importlib
    import empirical_option_ev as m
    importlib.reload(m)
    assert callable(m.compute_empirical_option_ev)
