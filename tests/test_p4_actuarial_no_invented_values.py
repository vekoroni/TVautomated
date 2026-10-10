"""Phase 4 / RC05: Vanguard's actuarial outcomes never invent values, and say what each statistic is.

Business rules (R1 missing is never neutral; R6 labels say what was measured):
- A cohort with no winners publishes NOT_MEASURED (NaN) for the winner statistics - never +5% / 5%; no losers ->
  never -3% / 3%; an undefined Kelly is NaN, never 0.1; an undefined win/loss ratio is NaN, never 1.0.
- Horizons with no labels in the database (5d / 10d) are NaN, never a measured 0.0.
- The arithmetic mean return is published beside the median-weighted "expected value", which is labelled as a
  heuristic (Codex B17: EV 1% vs arithmetic mean 25.25% on the same cohort).
- Missing median days never crash the hold recommendation.
"""
import math

import pandas as pd

from vanguard.layer2_statistical.actuarial_query import ActuarialQueryEngine


def _engine():
    e = ActuarialQueryEngine.__new__(ActuarialQueryEngine)
    e._has_5d_cols = False
    e._has_10d_cols = False
    return e


def _frame(returns, days=5):
    n = len(returns)
    return pd.DataFrame({"outcome_20d_return": returns, "outcome_hit_10pct_up": [r >= .1 for r in returns],
                         "outcome_hit_5pct_down_before_10up": [False] * n, "outcome_max_drawdown_20d": [-.02] * n,
                         "outcome_days_to_10pct": [days] * n, "outcome_category": ["MEASURED"] * n})


def test_no_losers_is_not_measured_not_minus_three_percent():
    o = _engine()._calculate_outcomes(_frame([.01, .02, .05] * 20))
    assert math.isnan(o.median_loss_if_down)
    assert math.isnan(o.avg_win_loss_ratio)


def test_no_winners_is_not_measured_not_plus_five_percent():
    o = _engine()._calculate_outcomes(_frame([-.01, -.02, -.05] * 20))
    assert math.isnan(o.median_gain_if_up)
    assert math.isnan(o.kelly_fraction)


def test_missing_horizons_are_nan_not_measured_zero():
    o = _engine()._calculate_outcomes(_frame([.01, -.02] * 30))
    assert math.isnan(o.win_rate_5d) and math.isnan(o.expected_value_5d)
    assert math.isnan(o.win_rate_10d) and math.isnan(o.expected_value_10d)


def test_arithmetic_mean_is_published_beside_the_median_heuristic():
    returns = [.01, .02, 1.0, -.02] * 25
    o = _engine()._calculate_outcomes(_frame(returns))
    assert abs(o.mean_return_20d - sum(returns) / len(returns)) < 1e-12
    assert o.expected_value_basis == "MEDIAN_WEIGHTED_HEURISTIC_NOT_ARITHMETIC_MEAN"


def test_missing_median_days_do_not_crash_the_hold():
    returns = [.2, .15, .12, .3] * 20
    f = _frame(returns)
    f["outcome_days_to_10pct"] = float("nan")
    o = _engine()._calculate_outcomes(f)
    assert o.recommended_hold_days == 20
