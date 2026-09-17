"""Business rules for Layer 3 volatility integrity (WP1 design 5b.1-5b.3, 17 Sep 2026).

Defects characterised on commit 202836b (each rule below failed before the fix):
  V1 `layer3_forward_variance.compute_forward_variance` multiplied the forecast by 1.10 when the macro
     regime contained RISK_OFF/BEAR and 1.05 for TRANSITIONAL, and cut confidence by 10 in RISK_OFF
     (AAPL 20260916: 0.3143 = 0.2857 x 1.10). A macro label changed a model value (CLAUDE.md rule 6).
  V2 empty or unusable price history returned forward_realised_vol = 0.25 (a plausible number) labelled
     ATR_PROXY; missing must be explicit (R1).
  V3 missing implied vol gave iv_tailwind_score = 0.0 described as "neutral" (R1).
  V4 `garch_runner` counted HAR_RV as a GARCH success and logged `GARCH=1476` while every row was
     HAR_RV (R6: labels say what was measured).
Consumers that must read a missing forecast / tailwind as missing (C1-C4) are covered at the end.
"""

from __future__ import annotations

import importlib.util
import logging
import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import layer3_forward_variance as l3

ROOT = Path(__file__).resolve().parents[1]
MODEL_METHODS = {"HAR_RV", "GARCH", "EWMA_FALLBACK", "ATR_PROXY"}


def _ohlcv(n=260, seed=7):
    rng = np.random.default_rng(seed)
    close = 100 * np.exp(np.cumsum(rng.normal(0.0, 0.02, n)))
    return pd.DataFrame({"close": close, "high": close * 1.01, "low": close * 0.99})


def _is_missing(value):
    return value is None or (isinstance(value, float) and math.isnan(value))


# ── V1 macro regime never changes a model value ────────────────────────────────

MODEL_VALUE_FIELDS = (
    "forward_realised_vol", "vol_forecast_confidence", "expected_move_1_5d",
    "expected_move_6_10d", "expected_move_11_20d", "iv_tailwind_score",
)


@pytest.mark.parametrize("regime", ["RISK_OFF", "TRANSITIONAL_BEARISH", "TRANSITIONAL", "BEAR", "RISK_ON"])
def test_v1_forecast_is_identical_whatever_the_macro_regime(regime):
    ohlcv = _ohlcv()
    base = l3.compute_forward_variance("AAA", ohlcv, implied_vol=0.30, regime="")
    other = l3.compute_forward_variance("AAA", ohlcv, implied_vol=0.30, regime=regime)
    for name in MODEL_VALUE_FIELDS:
        assert getattr(other, name) == getattr(base, name), name
    assert other.method == base.method


def test_v1_macro_regime_is_kept_only_as_a_display_field():
    row = l3.compute_forward_variance("AAA", _ohlcv(), implied_vol=0.30, regime="RISK_OFF").to_dict()
    assert row["l3_macro_regime_display"] == "RISK_OFF"
    base = l3.compute_forward_variance("AAA", _ohlcv(), implied_vol=0.30, regime="").to_dict()
    assert base["l3_macro_regime_display"] == ""
    differing = {k for k in row if row[k] != base[k]}
    assert differing == {"l3_macro_regime_display"}


# ── V2 missing price history is missing, never 25% ─────────────────────────────

@pytest.mark.parametrize("ohlcv", [
    pd.DataFrame(),
    pd.DataFrame({"open": [1.0, 2.0]}),                         # no close column
    pd.DataFrame({"close": [np.nan, np.nan, np.nan]}),          # no usable close
    pd.DataFrame({"close": [100.0]}),                            # one price, no return
], ids=["empty", "no_close_column", "all_nan_close", "single_close"])
def test_v2_missing_price_history_yields_no_numeric_forecast(ohlcv):
    result = l3.compute_forward_variance("AAA", ohlcv, implied_vol=0.30)
    assert result.forward_realised_vol is None
    assert result.expected_move_1_5d is None and result.expected_move_6_10d is None
    assert result.expected_move_11_20d is None
    assert result.iv_tailwind_score is None
    assert result.forecast_state == "MISSING_PRICE_HISTORY"
    assert result.error
    assert result.method not in MODEL_METHODS

    row = result.to_dict()
    assert row["l3_forward_realised_vol"] is None
    assert row["l3_forecast_state"] == "MISSING_PRICE_HISTORY"
    assert row["l3_expected_move_1_5d"] is None
    assert row["expected_move_10d_fraction"] is None
    assert row["l3_iv_tailwind_score"] is None


def test_v2_short_history_without_high_low_is_missing_not_default():
    """< 20 returns and no high/low: the ATR proxy cannot run; previously 0.25 was returned."""
    ohlcv = pd.DataFrame({"close": 100 + np.arange(10, dtype=float)})
    result = l3.compute_forward_variance("AAA", ohlcv, implied_vol=0.30)
    assert result.forward_realised_vol is None
    assert result.forecast_state == "FORECAST_UNAVAILABLE"
    assert result.method not in MODEL_METHODS
    assert result.to_dict()["l3_forward_realised_vol"] is None


def test_v2_valid_history_reports_forecast_ok():
    result = l3.compute_forward_variance("AAA", _ohlcv(), implied_vol=0.30)
    assert result.forecast_state == "FORECAST_OK"
    assert result.forward_realised_vol is not None and result.forward_realised_vol > 0
    assert result.error is None


# ── V3 missing implied vol is a missing tailwind, not neutral 0 ────────────────

@pytest.mark.parametrize("iv", [0.0, None, float("nan"), -0.1])
def test_v3_missing_implied_vol_yields_missing_tailwind(iv):
    result = l3.compute_forward_variance("AAA", _ohlcv(), implied_vol=iv)
    assert result.iv_tailwind_score is None
    assert result.iv_tailwind_state == "IV_MISSING"
    assert result.forward_realised_vol is not None      # forecast itself is unaffected
    row = result.to_dict()
    assert row["l3_iv_tailwind_score"] is None
    assert row["l3_iv_tailwind_score_capped"] is None
    assert row["l3_iv_tailwind_state"] == "IV_MISSING"
    assert "IV_TAILWIND_EXTREME" not in row["l3_model_risk_flags"]


def test_v3_present_implied_vol_gives_signed_tailwind():
    result = l3.compute_forward_variance("AAA", _ohlcv(), implied_vol=0.30)
    assert result.iv_tailwind_state == "IV_TAILWIND_OK"
    assert result.iv_tailwind_score == pytest.approx(0.30 - result.forward_realised_vol)


# ── V4 runner labels report the model actually used ────────────────────────────

def _load_runner():
    import garch_runner
    return garch_runner


def _result(ticker, method):
    return l3.ForwardVarianceResult(
        ticker=ticker, forward_realised_vol=0.3, vol_forecast_confidence=80.0,
        expected_move_1_5d=1.0, expected_move_6_10d=1.0, expected_move_11_20d=1.0,
        iv_tailwind_score=None, jump_risk_flag=False, method=method, n_bars_used=252,
    )


@pytest.mark.parametrize("method", ["HAR_RV", "GARCH", "EWMA_FALLBACK", "ATR_PROXY"])
def test_v4_ticker_status_is_the_model_that_ran(monkeypatch, method):
    runner = _load_runner()
    monkeypatch.setattr(runner, "RATE_SLEEP", 0)
    monkeypatch.setattr(runner, "_fetch_ohlcv", lambda *_a, **_k: _ohlcv())
    monkeypatch.setattr(runner, "compute_forward_variance", lambda t, *_a, **_k: _result(t, method))
    row, status = runner._process_one_ticker(("AAA", None, "RISK_OFF"))
    assert status == method
    assert row["l3_method"] == method


def test_v4_no_forecast_and_no_price_data_are_counted_as_fail(monkeypatch):
    runner = _load_runner()
    monkeypatch.setattr(runner, "RATE_SLEEP", 0)
    monkeypatch.setattr(runner, "_fetch_ohlcv", lambda *_a, **_k: None)
    assert runner._process_one_ticker(("AAA", None, ""))[1] == "FAIL"
    monkeypatch.setattr(runner, "_fetch_ohlcv", lambda *_a, **_k: pd.DataFrame({"close": [100.0]}))
    row, status = runner._process_one_ticker(("AAA", None, ""))
    assert status == "FAIL"
    assert row["l3_forecast_state"] == "MISSING_PRICE_HISTORY"


def test_v4_batch_log_counts_each_method_and_never_reports_har_rv_as_garch(monkeypatch, tmp_path, caplog):
    runner = _load_runner()
    sb = tmp_path / "sb.csv"
    pd.DataFrame({"ticker": ["A", "B", "C", "D", "E"]}).to_csv(sb, index=False)
    methods = {"A": "HAR_RV", "B": "HAR_RV", "C": "GARCH", "D": "EWMA_FALLBACK"}
    monkeypatch.setattr(runner, "RATE_SLEEP", 0)
    monkeypatch.setattr(runner, "_load_regime", lambda _b: "RISK_OFF")
    monkeypatch.setattr(runner, "_build_iv_map", lambda *_a: {})
    monkeypatch.setattr(runner, "_fetch_ohlcv", lambda t, *_a: _ohlcv() if t in methods else None)
    monkeypatch.setattr(runner, "compute_forward_variance", lambda t, *_a, **_k: _result(t, methods[t]))
    with caplog.at_level(logging.INFO, logger="garch_runner"):
        out = runner.run_garch_batch("RID", superbrain_csv=sb, output_dir=tmp_path / "out")
    assert out.exists()
    complete = [r.getMessage() for r in caplog.records if "Complete" in r.getMessage()]
    assert complete, caplog.text
    line = complete[-1]
    assert "HAR_RV=2" in line and "GARCH=1" in line and "EWMA_FALLBACK=1" in line
    assert "ATR_PROXY=0" in line and "FAIL=1" in line


# ── C1-C4 consumers read a missing forecast / tailwind as missing ──────────────

def test_c1_layer4_mispricing_missing_forward_vol_is_not_evaluated_not_fair():
    import layer4_mispricing as l4
    for vol in (None, float("nan")):
        res = l4.compute_mispricing(
            ticker="AAA", forward_realised_vol=vol, expected_move_pct=3.0, iv_tailwind_score=None,
            implied_vol=0.30, breakeven_pct=2.0, premium=2.0, theta_per_day=-0.05,
            spread_pct=0.05, hold_days=5, win_prob=0.5,
        )
        assert res.mispricing_state == "NOT_EVALUATED_DATA_MISSING"
        assert res.error == "missing_vol_inputs"
        assert res.vol_mispricing_score is None and res.rieg is None
        row = res.to_dict()
        assert row["l4_vol_mispricing_score"] is None and row["l4_rieg"] is None


def test_c2_empirical_option_ev_nan_forecast_vol_is_treated_as_absent():
    from empirical_option_ev import _finite_or_none
    assert _finite_or_none(float("nan")) is None
    assert _finite_or_none(None) is None
    assert _finite_or_none("") is None
    assert _finite_or_none("0.25") == 0.25


def _load_superbrain():
    path = ROOT / "scripts" / "avshunter_superbrain_layer.py"
    spec = importlib.util.spec_from_file_location("superbrain_layer_l3_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_c3_superbrain_tailwind_reader_keeps_missing_as_none():
    sb = _load_superbrain()
    assert sb._l3_iv_tailwind(({})) is None
    assert sb._l3_iv_tailwind({"l3_iv_tailwind_score": ""}) is None
    assert sb._l3_iv_tailwind({"l3_iv_tailwind_score": float("nan")}) is None
    assert sb._l3_iv_tailwind({"l3_iv_tailwind_score": "0.0"}) == 0.0
    assert sb._l3_iv_tailwind({"garch__l3_iv_tailwind_score": "0.2", "l3_iv_tailwind_score": "0.1"}) == 0.2


def _load_lab():
    path = ROOT / "intelligence-lab" / "intelligence_lab.py"
    spec = importlib.util.spec_from_file_location("intelligence_lab_l3_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_c4_lab_garch_stats_do_not_count_missing_tailwind_as_fair_and_label_methods():
    lab = _load_lab()
    rows = [
        {"l3_iv_tailwind_score": "", "l3_method": "HAR_RV"},
        {"l3_iv_tailwind_score": "-0.10", "l3_method": "HAR_RV"},
        {"l3_iv_tailwind_score": "0.01", "l3_method": "GARCH"},
        {"l3_iv_tailwind_score": "nan", "l3_method": "NO_FORECAST"},
    ]
    stats = lab._garch_stats(rows)
    assert stats["cheap_vol"] == 1 and stats["fair_vol"] == 1 and stats["expensive_vol"] == 0
    assert stats["iv_tailwind_missing"] == 2
    assert stats["har_rv_count"] == 2 and stats["garch_count"] == 1


def test_c4_lab_priority_score_gives_missing_tailwind_no_neutral_credit():
    lab = _load_lab()
    fair = lab._compute_priority_score({"garch__l3_iv_tailwind_score": "0.0"})
    missing = lab._compute_priority_score({})
    # A measured fair tailwind earns 0.5 x 0.05 x 100 = 2.5 points; missing earns nothing, never the neutral half.
    assert fair - missing == pytest.approx(2.5)
