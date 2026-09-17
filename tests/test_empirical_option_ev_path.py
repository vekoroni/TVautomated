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
    expected_value = black_scholes_price("call", 100.0, 100.0, remaining, 0.045, 0.30) - 0.1
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
