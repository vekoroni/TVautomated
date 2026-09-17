"""Item 2 increment 3 (ACK 17 Sep 2026): shares valued on the same paths, and the expression preference (shadow).

Business rules:
  S1 the share spread is measured, not assumed: the Abdi-Ranaldo (2017) estimator from daily high, low and close
     recovers a known bid-ask bounce and gives ~0 with no bounce; too little history is missing, never a default;
  S2 shares are valued on exactly the same simulated paths and exits as the option (stop first -> stop level,
     target first -> target, otherwise horizon close), bought at the ask and sold at the bid (half-spread each way);
  S3 both expressions are expressed per unit of capital at risk: the option in premium (return on premium), the
     shares in R = distance from share entry to the stop exit; with no directional drift the expected share R is
     about minus costs;
  S4 the preference uses the cautious values: NEITHER when neither is positive; otherwise the higher of OPTION and
     SHARES; PREFERENCE_UNAVAILABLE when the share spread is missing (option values are still reported);
  S5 the option result is unchanged by adding the share valuation (common random numbers, same paths).
"""

from __future__ import annotations

import numpy as np
import pytest

from empirical_option_ev import (
    abdi_ranaldo_spread, compute_path_expression_ev, compute_path_option_ev, expression_preference,
)
from tests.test_empirical_option_ev_path import CALIBRATION, _inputs


def _expression(**overrides):
    share_spread = overrides.pop("share_spread", 0.001)
    return compute_path_expression_ev(**_inputs(**overrides), share_spread=share_spread, calibration=CALIBRATION,
                                      paths=4000, seed=7)


def test_s1_estimator_recovers_a_known_bounce():
    rng = np.random.default_rng(3)
    n, spread = 400, 0.02
    mid = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, n)))
    close = mid * (1 + rng.choice([-1, 1], n) * spread / 2)                 # closes at bid or ask
    high = np.maximum(mid * (1 + spread / 2) * np.exp(np.abs(rng.normal(0, 0.004, n))), close)
    low = np.minimum(mid * (1 - spread / 2) * np.exp(-np.abs(rng.normal(0, 0.004, n))), close)
    estimate = abdi_ranaldo_spread(high, low, close)
    assert estimate == pytest.approx(spread, rel=0.35)


def test_s1_no_bounce_gives_near_zero_and_short_history_is_missing():
    rng = np.random.default_rng(4)
    mid = 50 * np.exp(np.cumsum(rng.normal(0, 0.01, 300)))
    assert abdi_ranaldo_spread(mid * 1.003, mid * 0.997, mid) < 0.004
    assert abdi_ranaldo_spread(mid[:5] * 1.01, mid[:5] * 0.99, mid[:5]) is None


def test_s5_option_values_unchanged_by_share_valuation():
    option_only = compute_path_option_ev(**_inputs(), calibration=CALIBRATION, paths=4000, seed=7)
    both = _expression()
    for key, value in option_only.items():
        assert both[key] == value


def test_s3_zero_drift_shares_cost_about_the_spread():
    out = _expression(share_spread=0.002, target=112.0, invalidation=94.0)
    risk_fraction = (100 * 1.001 - 94 * 0.999) / (100 * 1.001)
    expected_cost_in_r = -0.002 / risk_fraction
    assert out["emp_share_r_central"] == pytest.approx(expected_cost_in_r, abs=0.08)


def test_s2_stop_exit_is_about_minus_one_r_less_costs():
    out = _expression(invalidation=99.9, target=150.0, share_spread=0.0, hold_sessions=1)
    assert out["emp_path_p_stop_first_central"] > 0.8
    assert out["emp_share_r_cautious"] < 0


@pytest.mark.parametrize("option_r, share_r, expected", [
    (-0.2, -0.05, "NEITHER"),
    (0.3, 0.1, "OPTION"),
    (0.05, 0.2, "SHARES"),
    (0.0, 0.0, "NEITHER"),
    (0.1, None, "PREFERENCE_UNAVAILABLE"),
    (None, 0.1, "PREFERENCE_UNAVAILABLE"),
])
def test_s4_preference_from_cautious_values(option_r, share_r, expected):
    assert expression_preference(option_r, share_r) == expected


def test_s4_missing_share_spread_keeps_option_values():
    out = _expression(share_spread=None)
    assert out["emp_path_r_central"] is not None
    assert out["emp_share_r_central"] is None
    assert out["emp_expression_preference"] == "PREFERENCE_UNAVAILABLE"
    assert out["emp_share_quality_flag"] == "SHARE_SPREAD_UNAVAILABLE"
