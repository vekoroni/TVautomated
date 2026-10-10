"""Business rules for the local, measured US Money Index (ACK 10 Oct 2026).

The ChatGPT Money Index carries a risk-off transmission score on nine components. Seven of them are
measurable from data AVSHUNTER holds (oil, 10Y, credit, VIX, breadth, small caps, AI/semis); the board
scores those itself, each against its own trailing year (percentile, oriented to risk-off) so no
threshold goes stale, keeps the published ladder's weights so the two compare component by
component, and measures what followed for every ETF together with each ETF's beta and correlation
to SPY and QQQ (ACK: the plan works per ETF with its correlation). Display only. No network.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from macro_board import money_index as mi

COMPONENTS = [
    {"key": "oil", "label": "Oil (USO 20d)", "weight": 12, "risk_off": "HIGH", "published_key": "oil_breakout", "unit": "%"},
    {"key": "rates", "label": "10Y yield 20d change", "weight": 10, "risk_off": "HIGH", "published_key": "rates_confirmation", "unit": "bp"},
    {"key": "credit", "label": "HYG vs LQD 20d", "weight": 14, "risk_off": "LOW", "published_key": "credit_confirmation", "unit": "%"},
]
CFG = {
    "components": COMPONENTS,
    "published_only": [{"key": "geopolitical_escalation", "label": "Geopolitical escalation", "weight": 12},
                       {"key": "hormuz_impairment", "label": "Hormuz impairment", "weight": 12}],
    "window_sessions": 20, "min_sessions": 10, "score_floor_pct": 0.5, "score_full_pct": 0.95,
    "bands": {"calm_below": 35.0, "risk_off_from": 60.0},
    "horizons": [1, 5], "ic_horizon": 5, "corr_window_sessions": 30,
}
EVIDENCE = {"min_history_sessions": 50, "min_effective_n": 5, "min_effective_n_holdout": 3, "lean_t_min": 2.0,
            "lean_min_abs_mean_pct": {"1": 0.05, "5": 0.1, "20": 0.2}, "holdout_fraction": 0.25, "interval_level": 0.8}


def _raw(n=60, seed=1):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2026-06-01", periods=n)
    return pd.DataFrame({"oil": rng.normal(0, 1, n), "rates": rng.normal(0, 1, n), "credit": rng.normal(0, 1, n)}, index=idx)


def test_each_component_is_scored_against_its_own_trailing_window_in_the_risk_off_direction():
    raw = _raw()
    raw.iloc[-1] = [raw["oil"].iloc[-21:-1].max() + 5, raw["rates"].iloc[-21:-1].median(), raw["credit"].iloc[-21:-1].min() - 5]
    scores = mi.component_scores(raw, COMPONENTS, CFG)
    last = scores.iloc[-1]
    assert last["oil"] == 12.0                       # highest oil in the window: full risk-off weight
    assert last["credit"] == 14.0                    # credit appetite at its low: risk-off for a LOW component
    assert 0.0 <= last["rates"] <= 1.5               # at the median: (close to) nothing


def test_a_later_spike_never_changes_an_earlier_score():
    raw = _raw()
    before = mi.component_scores(raw, COMPONENTS, CFG).iloc[40].copy()
    raw.iloc[50:, 0] = 1000.0
    after = mi.component_scores(raw, COMPONENTS, CFG).iloc[40]
    pd.testing.assert_series_equal(before, after)


def test_the_total_uses_the_measured_weights_and_a_missing_component_is_missing_not_zero():
    raw = _raw()
    scores = mi.component_scores(raw, COMPONENTS, CFG)
    total = mi.total_score(scores, COMPONENTS)
    assert abs(total.iloc[-1] - scores.iloc[-1].sum() / 36.0 * 100.0) < 1e-9
    raw.iloc[-1, 1] = np.nan
    gap = mi.total_score(mi.component_scores(raw, COMPONENTS, CFG), COMPONENTS)
    assert np.isnan(gap.iloc[-1])
    reading = mi.current_reading(raw, mi.component_scores(raw, COMPONENTS, CFG), COMPONENTS, CFG)
    assert reading["score"] is None and reading["missing"] == ["rates"]


def test_bands_come_from_config():
    assert mi.band(20.0, CFG["bands"]) == "CALM"
    assert mi.band(35.0, CFG["bands"]) == "TRANSITION"
    assert mi.band(60.0, CFG["bands"]) == "RISK_OFF"
    assert mi.band(None, CFG["bands"]) == "MISSING"


def test_the_current_reading_states_value_percentile_and_points_per_component():
    raw = _raw()
    reading = mi.current_reading(raw, mi.component_scores(raw, COMPONENTS, CFG), COMPONENTS, CFG)
    row = {r["key"]: r for r in reading["components"]}["oil"]
    assert {"value", "percentile", "points", "weight", "label", "unit"} <= set(row)
    assert reading["band"] in ("CALM", "TRANSITION", "RISK_OFF") and reading["measured_weight"] == 36


def test_beta_and_correlation_are_measured_on_daily_returns():
    idx = pd.bdate_range("2026-01-01", periods=80)
    rng = np.random.default_rng(3)
    spy = pd.Series(100 * np.exp(np.cumsum(rng.normal(0, 0.01, 80))), index=idx)
    lev = pd.Series(100 * np.exp(2 * np.log(spy / 100)), index=idx)          # 2x SPY's log returns
    out = mi.beta_corr(lev, spy, window=30)
    assert abs(out["beta"] - 2.0) < 1e-6 and abs(out["corr"] - 1.0) < 1e-9 and out["n"] == 30


def test_an_etf_that_falls_after_high_scores_has_a_negative_information_coefficient():
    idx = pd.bdate_range("2025-01-01", periods=200)
    score = pd.Series(np.tile(np.linspace(0, 100, 20), 10), index=idx)
    fwd = -score / 1000.0
    ic = mi.information_coefficient(score, fwd, step=5)
    assert ic["ic"] < -0.9 and ic["n"] == 40


def test_what_followed_today_s_band_is_measured_with_the_board_s_evidence_rules():
    idx = pd.bdate_range("2025-01-01", periods=120)
    bands = pd.Series(np.where(np.arange(120) % 2 == 0, "RISK_OFF", "CALM"), index=idx)
    fwd = pd.Series(np.where(bands == "RISK_OFF", -0.01, 0.01), index=idx)
    out = mi.band_evidence(fwd, bands, "RISK_OFF", 1, EVIDENCE)
    assert out["analog"]["n"] == 60 and out["analog"]["mean_pct"] < 0


def test_local_and_published_compare_component_by_component_and_llm_only_parts_are_labelled():
    raw = _raw()
    reading = mi.current_reading(raw, mi.component_scores(raw, COMPONENTS, CFG), COMPONENTS, CFG)
    published = {"score": 83, "components": {"oil_breakout": {"weight": 12, "score": 6, "status": "ACTIVE"},
                                             "credit_confirmation": {"weight": 14, "score": 14, "status": "ELEVATED"},
                                             "geopolitical_escalation": {"weight": 12, "score": 12, "status": "CONFIRMED"}}}
    cmp = mi.compare(reading, published, CFG)
    rows = {r["key"]: r for r in cmp["rows"]}
    assert rows["oil"]["published_points"] == 6 and rows["oil"]["basis"] == "MEASURED"
    assert rows["rates"]["published_points"] is None                       # not in the published packet
    assert rows["geopolitical_escalation"]["basis"] == "LLM_ONLY" and rows["geopolitical_escalation"]["local_points"] is None
    assert cmp["published_score"] == 83
    assert cmp["comparable_total"] is None                                  # Hormuz missing: no total, never zero
    published["components"]["hormuz_impairment"] = {"weight": 12, "score": 12}
    full = mi.compare(reading, published, CFG)
    measured_points = sum(r["points"] for r in reading["components"])
    assert abs(full["comparable_total"] - (measured_points + 24) / (36 + 24) * 100.0) < 1e-3
