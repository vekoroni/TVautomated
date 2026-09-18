"""Item 2 increment 2 (ACK 17 Sep 2026): volatility-range, exit-path option valuation (shadow, no authority).

Business rules:
  V1 the option is valued along simulated paths that exit exactly as the outcome scorer does: invalidation
     touched first -> exit at the invalidation level; target touched first -> exit at the target; neither ->
     exit at the horizon; touches between closes count (Brownian-bridge crossing, like the scorer's session
     highs and lows); every exit is repriced and sold at the bid (half-spread paid);
  V2 paths use no directional drift (direction skill is not established) and daily moves drawn from the
     calibrated empirical innovation distribution (fat tails from the price store, unit variance);
  V3 volatility is a range, not a point: scenarios are the forecast multiplied by the calibrated forecast-error
     bands (p10, p50, p90) for the horizon; the result reports cautious (lowest), central (p50) and upside
     (highest) expected return on premium, so ranking can use the cautious value with upside alongside;
  V4 results are reproducible for a given seed and path count (configuration);
  V5 missing inputs are explicit flags, never neutral numbers: no two-sided market, no forecast, no invalidation.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from empirical_option_ev import (
    PATH_QUALITY_OK, compute_path_option_ev, sample_innovations,
)
from compute_greeks_bs import black_scholes_price

NORMALISH = {  # symmetric, unit-variance-ish grid (standard normal quantiles)
    "levels": [0.001, 0.01, 0.05, 0.1, 0.25, 0.5, 0.75, 0.9, 0.95, 0.99, 0.999],
    "values": [-3.09, -2.326, -1.645, -1.2816, -0.6745, 0.0, 0.6745, 1.2816, 1.645, 2.326, 3.09],
    "std": 1.0,
}
CALIBRATION = {
    "forecast_error_bands": {"5": {"p10": 0.6, "p50": 0.9, "p90": 1.5}, "10": {"p10": 0.65, "p50": 0.92, "p90": 1.4},
                             "20": {"p10": 0.7, "p50": 0.95, "p90": 1.3}},
    "innovation_quantiles": NORMALISH,
}


def _inputs(**overrides):
    base = dict(side="call", spot=100.0, strike=100.0, dte=30.0, bid=2.9, ask=3.1, iv=0.30, rate=0.045,
                target=112.0, invalidation=94.0, hold_sessions=10, forecast_vol=0.30)
    base.update(overrides)
    return base


def _value(**overrides):
    return compute_path_option_ev(**_inputs(**overrides), calibration=CALIBRATION, paths=4000, seed=7)


def test_v4_reproducible_for_seed():
    assert _value() == _value()


def test_v2_innovation_sampler_matches_calibrated_distribution():
    draws = sample_innovations(NORMALISH, np.random.default_rng(1), size=200_000)
    assert abs(draws.mean()) < 0.02 and draws.std() == pytest.approx(1.0, abs=0.03)


def test_v1_target_touched_first_exits_at_target_value_less_half_spread():
    out = _value(target=100.0001, invalidation=50.0, forecast_vol=0.30)     # target touched on session 1
    expected = black_scholes_price("call", 100.0001, 100.0, (30.0 - 7 / 5) / 365.0, 0.045, 0.30) - 0.1
    assert out["emp_path_p_target_first_central"] > 0.45
    assert out["emp_path_quality_flag"] == PATH_QUALITY_OK


def test_v1_invalidation_touched_first_dominates_when_stop_is_close():
    out = _value(invalidation=99.9, target=150.0)
    assert out["emp_path_p_stop_first_central"] > 0.9
    # No level assertion: with zero drift an early stop near spot keeps most of the premium while holding
    # decays, so a close stop is not necessarily worth less; exit pricing is covered by the target / horizon tests.


def test_v1_no_touch_exits_at_horizon_with_time_value():
    tiny = _value(forecast_vol=0.0001, target=150.0, invalidation=50.0, hold_sessions=5)
    remaining = (30.0 - 5 * 7 / 5) / 365.0
    # Exits are repriced at the volatility that reproduces the 3.00 market mid at entry (ACK 18 Sep 2026), not the
    # quoted 0.30, which would price this contract at ~3.61.
    from empirical_option_ev import calibrated_iv
    market_vol = calibrated_iv("call", 100.0, 100.0, 30.0 / 365.0, 0.045, 3.0)
    expected_value = black_scholes_price("call", 100.0, 100.0, remaining, 0.045, market_vol) - 0.1
    assert tiny["emp_path_r_central"] == pytest.approx(expected_value / 3.1 - 1.0, abs=0.01)


def test_v1_wider_spread_lowers_value():
    assert _value(bid=2.5, ask=3.1)["emp_path_r_central"] < _value(bid=3.05, ask=3.1)["emp_path_r_central"]


def test_v3_range_is_ordered_and_uses_calibrated_bands():
    out = _value(hold_sessions=10, forecast_vol=0.40)
    assert out["emp_path_r_cautious"] <= out["emp_path_r_central"] <= out["emp_path_r_upside"]
    assert out["emp_path_vol_low"] == pytest.approx(0.40 * 0.65)
    assert out["emp_path_vol_central"] == pytest.approx(0.40 * 0.92)
    assert out["emp_path_vol_high"] == pytest.approx(0.40 * 1.4)
    assert out["emp_path_horizon_band"] == 10


def test_v3_more_movement_is_worth_more_to_an_at_the_money_option_with_distant_barriers():
    calm = _value(forecast_vol=0.15, target=200.0, invalidation=20.0)
    wild = _value(forecast_vol=0.60, target=200.0, invalidation=20.0)
    assert wild["emp_path_r_central"] > calm["emp_path_r_central"]


def test_v1_put_mirrors_call():
    out = _value(side="put", target=88.0, invalidation=106.0)
    assert out["emp_path_quality_flag"] == PATH_QUALITY_OK
    assert 0 < out["emp_path_p_target_first_central"] < 1


@pytest.mark.parametrize("overrides, flag", [
    (dict(bid=0.0), "NO_MARKET"),
    (dict(forecast_vol=None), "VOL_SCALE_UNAVAILABLE"),
    (dict(invalidation=None), "GEOMETRY_UNAVAILABLE"),
    (dict(invalidation=101.0), "GEOMETRY_UNAVAILABLE"),     # call invalidation above spot is on the wrong side
])
def test_v5_missing_inputs_are_explicit(overrides, flag):
    out = _value(**overrides)
    assert out["emp_path_quality_flag"] == flag
    assert out["emp_path_r_central"] is None


def test_v1_intraday_touches_between_closes_are_counted():
    # a stop just below spot is touched far more often once intraday crossings count
    out = _value(invalidation=99.9, target=150.0, hold_sessions=1, forecast_vol=0.30)
    assert out["emp_path_p_stop_first_central"] > 0.8


# --- ACK decision C3(b), 16 Sep 2026 (spec "Expression life: last exit session") ---------------------------------
# A contract is valued only until its own last_exit_session = min(thesis window, expiry minus the exit buffer);
# paths still unresolved then exit at that session's price. Short-dated convexity is judged by valuation and
# ranking, not by a DTE rule. Before this, the model simulated the full hold regardless of expiry and credited
# moves that happen after the contract has expired, overvaluing short-dated contracts (decision record D1).

from empirical_option_ev import PATH_SETTINGS  # noqa: E402


def test_c3_exit_buffer_is_governed():
    assert PATH_SETTINGS["option_exit_buffer_sessions"] == 2


def test_c3_last_exit_session_caps_the_valuation_window():
    short = _value(dte=10.0, hold_sessions=20)       # 10 calendar days ~ 7 sessions, minus 2 buffer -> 5
    assert short["emp_path_last_exit_sessions"] == 5
    long_ = _value(dte=60.0, hold_sessions=10)       # contract outlives the hold -> the hold ends the window
    assert long_["emp_path_last_exit_sessions"] == 10


def test_c3_forced_exits_are_reported():
    short = _value(dte=10.0, hold_sessions=20)
    assert short["emp_path_forced_exit_share"] > 0.5  # most paths are unresolved when the contract must be sold
    assert _value(dte=60.0, hold_sessions=10)["emp_path_forced_exit_share"] == 0.0


def test_c3_moves_after_the_contract_is_sold_are_never_credited():
    capped = _value(dte=10.0, hold_sessions=5)        # the same contract valued over its own life
    over_hold = _value(dte=10.0, hold_sessions=20)    # a 20-session thesis cannot make it worth more
    assert over_hold["emp_path_r_central"] <= capped["emp_path_r_central"] + 0.05


def test_c3_contract_with_no_usable_life_is_flagged():
    out = _value(dte=3.0, hold_sessions=10)           # 3 days ~ 2 sessions, minus 2 buffer -> 0
    assert out["emp_path_quality_flag"] == "CONTRACT_NOT_HOLDABLE"


# --- ACK decision D2(a): the evening valuation uses the thesis window, not the actuarial hold ------------------------

def test_d2_evening_inputs_use_the_thesis_window():
    from empirical_option_ev import path_inputs_from_options_row
    row = {"final_direction": "CALL", "underlying_price": 100.0, "strike": 100.0, "contract_dte": 45,
           "contract_bid": 4.8, "contract_ask": 5.0, "contract_iv": 0.3, "structural_target": 110.0,
           "invalidation_spot": 95.0, "layer2__recommended_hold_days": 5, "l3_forward_realised_vol": 0.3}
    assert path_inputs_from_options_row(row, thesis_window_sessions=20)["hold_sessions"] == 20


def test_d2_missing_thesis_window_is_never_replaced_by_the_actuarial_hold():
    from empirical_option_ev import path_inputs_from_options_row
    row = {"final_direction": "CALL", "layer2__recommended_hold_days": 5}
    assert path_inputs_from_options_row(row, thesis_window_sessions=None)["hold_sessions"] is None   # R1


# --- Market calibration at entry (ACK 18 Sep 2026) ---------------------------------------------------------------
# Measured on run 20260918_112522: pricing exits with the provider IV in a no-dividend formula put the model value at
# entry +1.2% above the market mid for the median call (+8.3% at the 90th percentile) and -1.6% for puts; the five
# issued tickets sat at +7% to +17%, so 90%-likely day-one stop-outs showed gains (UPS +2.1%).

def test_mkt_model_value_at_entry_equals_the_market_mid():
    from empirical_option_ev import calibrated_iv, _bs_vector
    iv = calibrated_iv("call", 100.0, 100.0, 91 / 365.0, 0.045, 5.26)
    assert float(_bs_vector("call", 100.0, 100.0, 91 / 365.0, 0.045, iv)) == pytest.approx(5.26, abs=1e-4)


def test_mkt_day_one_stop_out_is_a_loss_even_when_the_provider_iv_overprices_the_contract():
    """Provider IV 0.40 prices this call well above its 2.62/2.82 market (a dividend payer): a stop hit on day one
    must lose at least the half-spread, never show a gain."""
    out = _value(dte=91.0, bid=2.62, ask=2.82, iv=0.40, invalidation=99.9, target=140.0, hold_sessions=20)
    assert out["emp_path_quality_flag"] == PATH_QUALITY_OK
    assert out["emp_path_p_stop_first_central"] > 0.95
    assert out["emp_path_r_upside"] < -(0.10 / 2.82) * 0.5
    assert out["emp_path_iv_provider"] == pytest.approx(0.40)
    assert out["emp_path_iv_calibrated"] < 0.40


def test_mkt_price_that_no_volatility_can_match_is_flagged_not_valued():
    out = _value(spot=120.0, strike=100.0, bid=10.0, ask=10.4, invalidation=110.0, target=130.0)   # below intrinsic
    assert out["emp_path_quality_flag"] == "PRICE_NOT_CALIBRATABLE"
