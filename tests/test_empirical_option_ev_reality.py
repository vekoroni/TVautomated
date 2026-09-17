"""Item 2 (ACK 17 Sep 2026): reality calibration of empirical_option_ev (shadow, no authority).

Evidence (Enhancements/expression_forensics/empirical_option_ev_evaluation.json, 2,504 realised option marks):
the module ranks usefully (realised return rises by predicted quintile, -54% -> -29%) but is badly optimistic
(predicted mean +3.7% vs realised -40%). Two causes measured:
  - the actuarial percentiles are pooled by state (148 distinct distributions for 1,333 contracts on 16 Sep):
    relative to each ticker's own volatility forecast they are 1.48x too wide for the lowest-volatility
    quartile and 0.56x for the highest;
  - exits were valued at a model price, but the bid-ask spread persists (execution-cost probe: exit
    half-spread ~ entry half-spread), so every exit pays roughly the entry half-spread again.

Rules:
  R1 the percentile distribution keeps its empirical shape but is re-scaled around its median so its
     p10-p90 width equals the ticker's own forecast width for the horizon;
  R2 a missing or non-positive volatility forecast yields no value with quality VOL_SCALE_UNAVAILABLE —
     never an unscaled (pooled) result;
  R3 each scenario's exit is valued at model value minus the entry half-spread in dollars (floored at 0);
     a zero-spread quote is unchanged;
  R4 the scale and exit cost used are reported (emp_vol_scale, emp_exit_half_spread).
"""

from __future__ import annotations

import math

import pytest

from empirical_option_ev import (
    QUALITY_OK, QUALITY_VOL_SCALE_UNAVAILABLE, compute_empirical_option_ev, scaled_percentile_returns,
)
from tests.test_empirical_option_ev import _base_candidate

Z90 = 1.2815515655446004


def _width(returns):
    labels = ("p01", "p05", "p10", "p20", "p30", "p40", "p50", "p60", "p70", "p80", "p90", "p95", "p99")
    by = dict(zip(labels, returns))
    return by["p90"] - by["p10"]


def test_r1_distribution_rescaled_to_ticker_forecast_width():
    raw = [-0.15, -0.09, -0.06, -0.03, -0.01, 0.005, 0.015, 0.03, 0.05, 0.08, 0.13, 0.19, 0.32]
    forecast_vol, sessions = 0.20, 10
    scaled, scale = scaled_percentile_returns(raw, forecast_vol, sessions)
    target_log_width = 2 * Z90 * forecast_vol * math.sqrt(sessions / 252)
    log_scaled = [math.log1p(x) for x in scaled]
    assert log_scaled[10] - log_scaled[2] == pytest.approx(target_log_width)      # p90 - p10 in log returns
    assert scale == pytest.approx(target_log_width / (math.log1p(0.13) - math.log1p(-0.06)))
    assert scaled[6] == pytest.approx(raw[6])                                     # median unchanged
    assert all(a < b for a, b in zip(scaled, scaled[1:]))                         # ordering preserved


def test_r5_rescaled_scenarios_never_imply_a_non_positive_price():
    raw = [-0.60, -0.40, -0.25, -0.12, -0.05, 0.0, 0.01, 0.04, 0.10, 0.20, 0.35, 0.60, 1.20]
    scaled, _ = scaled_percentile_returns(raw, forecast_vol=2.5, sessions=20)
    assert all(x > -1.0 for x in scaled)


def test_r1_low_vol_ticker_gets_lower_value_than_high_vol_ticker_same_quote():
    calm = compute_empirical_option_ev(_base_candidate(forecast_vol=0.15, live_iv=0.55))
    wild = compute_empirical_option_ev(_base_candidate(forecast_vol=0.54, live_iv=0.55))
    assert calm["emp_quality_flag"] == QUALITY_OK and wild["emp_quality_flag"] == QUALITY_OK
    assert calm["emp_expected_r"] < wild["emp_expected_r"]


@pytest.mark.parametrize("forecast", [None, "", float("nan"), 0.0, -0.1])
def test_r2_missing_forecast_is_not_neutral(forecast):
    out = compute_empirical_option_ev(_base_candidate(forecast_vol=forecast))
    assert out["emp_quality_flag"] == QUALITY_VOL_SCALE_UNAVAILABLE
    assert out["emp_expected_r"] is None


def test_r3_exit_pays_the_half_spread():
    tight = compute_empirical_option_ev(_base_candidate(bid=2.00, ask=2.00))
    wide = compute_empirical_option_ev(_base_candidate(bid=1.60, ask=2.00))
    assert tight["emp_exit_half_spread"] == pytest.approx(0.0)
    assert wide["emp_exit_half_spread"] == pytest.approx(0.20)
    assert wide["emp_expected_r"] < tight["emp_expected_r"]


def test_r4_scale_and_exit_cost_reported():
    out = compute_empirical_option_ev(_base_candidate())
    assert out["emp_vol_scale"] is not None and out["emp_vol_scale"] > 0
    assert out["emp_exit_half_spread"] == pytest.approx((2.10 - 1.90) / 2)


def test_r1_zero_width_distribution_is_used_as_given_with_scale_missing():
    c = _base_candidate()
    for label in ("p01", "p05", "p10", "p20", "p30", "p40", "p50", "p60", "p70", "p80", "p90", "p95", "p99"):
        c[f"ret_pctl_10d_{label}"] = 0.02
    out = compute_empirical_option_ev(c)
    assert out["emp_quality_flag"] == QUALITY_OK and out["emp_vol_scale"] is None
