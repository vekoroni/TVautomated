"""Business rules for the Layer 3 volatility leftovers (V5-V7 and the macro display default, 17 Sep 2026).

Defects characterised on commit 8d1e04c (each rule below failed before the change):
  V5 `layer3_forward_variance.py` clipped every forecast to 5%-250% annualised in three places (HAR-RV
     literal, `_annualise`, final clip) with no trace; a clipped value was reported as FORECAST_OK.
     Evidence (Enhancements/expression_forensics/VOL_FLOOR_CAP_EVIDENCE.md, vol_floor_cap_study.py; production
     path, regime '', all tickers, every 20th session since 2022, 252 bars, 20-session delivered vol;
     85,253 forecasts, 1,937 tickers, all HAR-RV):
       below floor 48 (0.056%, 12 tickers, stale/near-cash): delivered median 2.9%, 83% below 5%;
         abs log error raw 0.520 -> clipped 0.679, QLIKE mean 0.864 -> 0.761; clipped closer in 27%.
       above cap 148 (0.17%, 57 tickers): raw median 336%, delivered median 95%, 12.8% above 250%;
         abs log error 1.358 -> 0.984, QLIKE mean 2.22 -> 5.18; clipped closer in 93%.
       all: QLIKE 0.3542 -> 0.3593, abs log error 0.3131 -> 0.3125.
     Decision: neither bound improves accuracy; kept as a governed range guard
     (config/governed_constants_v1.json layer3_forecast_bounds), labelled CLIPPED_AT_FLOOR / CLIPPED_AT_CAP,
     raw model output in l3_forward_realised_vol_raw.
  V6 `garch_runner._process_one_ticker` returned no row for a ticker without price data or on an error, so
     the forecast CSV omitted it and downstream merges showed NaN with no reason.
  V7 no forecast (and < 20 returns or flat prices) gave `l3_jump_risk_flag = False` - "no jump risk" that
     was never measured. Consumers: EOD manifest said review not required (C5), the bridge ordered the
     candidate (C6), the Lab summary could not show not-assessed rows (C7).
  M1 `garch_runner._load_regime` invented 'TRANSITIONAL' when no macro regime was found (display only).
"""

from __future__ import annotations

import importlib.util
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import layer3_forward_variance as l3

ROOT = Path(__file__).resolve().parents[1]


def _ohlcv(n=260, seed=7, daily=0.02):
    rng = np.random.default_rng(seed)
    close = 100 * np.exp(np.cumsum(rng.normal(0.0, daily, n)))
    return pd.DataFrame({"close": close, "high": close * 1.01, "low": close * 0.99})


def _is_missing(value):
    return value is None or (isinstance(value, float) and math.isnan(value))


# ── V5 a bounded forecast is labelled as bounded; the raw model output is kept ──


def _governed_bounds():
    constants = json.loads((ROOT / "config" / "governed_constants_v1.json").read_text(encoding="utf-8-sig"))
    return constants["layer3_forecast_bounds"]


def test_v5_bounds_are_governed_configuration_with_evidence():
    bounds = _governed_bounds()
    assert bounds["floor_annual_vol_fraction"] == 0.05 and bounds["cap_annual_vol_fraction"] == 2.50
    assert bounds["evidence"].endswith("VOL_FLOOR_CAP_EVIDENCE.md")
    assert bounds["validation_state"] == "RANGE_GUARD_NOT_ACCURACY_IMPROVEMENT"
    assert l3.VOL_FLOOR == bounds["floor_annual_vol_fraction"] and l3.VOL_CAP == bounds["cap_annual_vol_fraction"]


def test_v5_forecast_inside_bounds_is_the_model_output():
    row = l3.compute_forward_variance("AAA", _ohlcv(), implied_vol=0.3).to_dict()
    assert row["l3_forecast_state"] == "FORECAST_OK"
    assert 0.05 < row["l3_forward_realised_vol_raw"] < 2.5
    assert row["l3_forward_realised_vol"] == row["l3_forward_realised_vol_raw"]


def test_v5_har_rv_below_floor_is_clipped_at_floor_with_raw_kept():
    result = l3.compute_forward_variance("AAA", _ohlcv(daily=0.001), implied_vol=0.3)
    assert result.method == "HAR_RV"
    row = result.to_dict()
    assert row["l3_forecast_state"] == "CLIPPED_AT_FLOOR"
    assert row["l3_forward_realised_vol"] == 0.05
    assert row["l3_forward_realised_vol_raw"] < 0.05


def test_v5_har_rv_above_cap_is_clipped_at_cap_with_raw_kept():
    frame = _ohlcv(daily=0.25)
    # DQ-12 (17 Sep 2026): keep the synthetic 25%-a-day walk at a realistic price level; a walk that
    # drifts below $0.01 is (correctly) treated as a defunct history and gets no forecast.
    frame[["close", "high", "low"]] = frame[["close", "high", "low"]] * (50.0 / frame["low"].min())
    result = l3.compute_forward_variance("AAA", frame, implied_vol=0.3)
    assert result.method == "HAR_RV"
    row = result.to_dict()
    assert row["l3_forecast_state"] == "CLIPPED_AT_CAP"
    assert row["l3_forward_realised_vol"] == 2.5
    assert row["l3_forward_realised_vol_raw"] > 2.5
    assert "VOL_HARDCAP" in row["l3_model_risk_flags"]


def test_v5_fallback_models_are_labelled_when_clipped():
    """EWMA (20-59 returns) previously clipped inside _annualise with no trace."""
    result = l3.compute_forward_variance("AAA", _ohlcv(n=40, daily=0.001), implied_vol=None)
    assert result.method == "EWMA_FALLBACK"
    assert result.forecast_state == "CLIPPED_AT_FLOOR"
    assert result.forward_realised_vol_raw < 0.05


def test_v5_clipping_follows_the_configured_bounds(monkeypatch):
    monkeypatch.setattr(l3, "VOL_FLOOR", 1.0)
    result = l3.compute_forward_variance("AAA", _ohlcv(), implied_vol=0.3)
    assert result.forecast_state == "CLIPPED_AT_FLOOR"
    assert result.forward_realised_vol == 1.0 and result.forward_realised_vol_raw < 1.0


def test_v5_no_forecast_has_no_raw_forecast():
    row = l3.compute_forward_variance("AAA", pd.DataFrame(), implied_vol=0.3).to_dict()
    assert row["l3_forward_realised_vol_raw"] is None


# ── V6 every requested ticker appears in the forecast CSV with an explicit state ──

def _runner():
    import garch_runner
    return garch_runner


def test_v6_ticker_without_price_data_returns_an_explicit_missing_row(monkeypatch):
    runner = _runner()
    monkeypatch.setattr(runner, "RATE_SLEEP", 0)
    monkeypatch.setattr(runner, "_fetch_ohlcv", lambda *_a, **_k: None)
    row, status = runner._process_one_ticker(("AAA", 0.3, "RISK_OFF"))
    assert status == "FAIL"
    assert row is not None and row["ticker"] == "AAA"
    assert row["l3_forecast_state"] == "MISSING_PRICE_HISTORY"
    assert row["l3_error"]
    for name in ("l3_forward_realised_vol", "l3_expected_move_1_5d", "l3_iv_tailwind_score", "l3_vol_forecast_conf"):
        assert row[name] is None, name


def test_v6_unexpected_error_returns_a_failed_row_with_reason(monkeypatch):
    runner = _runner()
    monkeypatch.setattr(runner, "RATE_SLEEP", 0)
    monkeypatch.setattr(runner, "_fetch_ohlcv", lambda *_a, **_k: _ohlcv())

    def boom(*_a, **_k):
        raise ValueError("model exploded")

    monkeypatch.setattr(runner, "compute_forward_variance", boom)
    row, status = runner._process_one_ticker(("AAA", None, ""))
    assert status == "FAIL"
    assert row is not None and row["ticker"] == "AAA"
    assert row["l3_forecast_state"] == "FORECAST_FAILED"
    assert "model exploded" in row["l3_error"] and "ValueError" in row["l3_error"]
    assert row["l3_forward_realised_vol"] is None and row["l3_jump_risk_flag"] is None


def _batch(monkeypatch, tmp_path, tickers, priced):
    runner = _runner()
    sb = tmp_path / "sb.csv"
    pd.DataFrame({"ticker": tickers}).to_csv(sb, index=False)
    monkeypatch.setattr(runner, "RATE_SLEEP", 0)
    monkeypatch.setattr(runner, "_load_regime", lambda _b: "RISK_OFF")
    monkeypatch.setattr(runner, "_build_iv_map", lambda *_a: {})
    monkeypatch.setattr(runner, "_fetch_ohlcv", lambda t, *_a: _ohlcv() if t in priced else None)
    out_dir = tmp_path / "out"
    try:
        runner.run_garch_batch("RID", superbrain_csv=sb, output_dir=out_dir)
    except RuntimeError:
        pass
    return pd.read_csv(out_dir / "garch_forecasts_RID.csv")


def test_v6_batch_csv_lists_every_requested_ticker(monkeypatch, tmp_path):
    out = _batch(monkeypatch, tmp_path, ["A", "B", "C"], priced={"A"})
    assert sorted(out["ticker"]) == ["A", "B", "C"]
    states = dict(zip(out["ticker"], out["l3_forecast_state"]))
    assert states == {"A": "FORECAST_OK", "B": "MISSING_PRICE_HISTORY", "C": "MISSING_PRICE_HISTORY"}
    missing = out[out["ticker"] != "A"]
    assert missing["l3_forward_realised_vol"].isna().all()
    assert missing["l3_jump_risk_flag"].isna().all()


def test_v6_batch_with_no_price_data_still_writes_explicit_rows(monkeypatch, tmp_path):
    out = _batch(monkeypatch, tmp_path, ["A", "B"], priced=set())
    assert sorted(out["ticker"]) == ["A", "B"]
    assert set(out["l3_forecast_state"]) == {"MISSING_PRICE_HISTORY"}


def test_v6_orchestrator_merge_carries_missing_state_rows(monkeypatch, tmp_path):
    import intelligent_orchestrator as orchestrator

    rows = [l3.compute_forward_variance("A", _ohlcv(), implied_vol=0.3).to_dict(),
            l3.compute_forward_variance("B", pd.DataFrame(), implied_vol=0.3).to_dict()]
    runs = tmp_path / "runs"
    (runs / "RID" / "qomega").mkdir(parents=True)
    (runs / "RID" / "superbrain").mkdir(parents=True)
    pd.DataFrame(rows).to_csv(runs / "RID" / "qomega" / "garch_forecasts_RID.csv", index=False)
    pd.DataFrame({"ticker": ["A", "B", "C"], "score": [1, 2, 3]}).to_csv(
        runs / "RID" / "superbrain" / "superbrain_enriched_RID.csv", index=False)
    monkeypatch.setattr(orchestrator.cfg, "RUNS_DIR", runs)
    assert orchestrator.merge_garch_into_enriched("RID") is True
    merged = pd.read_csv(runs / "RID" / "superbrain" / "superbrain_enriched_RID.csv").set_index("ticker")
    assert merged.loc["A", "l3_forecast_state"] == "FORECAST_OK"
    assert merged.loc["B", "l3_forecast_state"] == "MISSING_PRICE_HISTORY"
    assert pd.isna(merged.loc["B", "l3_forward_realised_vol"])
    assert pd.isna(merged.loc["B", "l3_jump_risk_flag"])
    assert pd.isna(merged.loc["C", "l3_forecast_state"])     # not requested from the runner: absent, not invented


# ── V7 no forecast / no assessable history: jump risk is missing, never False ───

@pytest.mark.parametrize("ohlcv", [pd.DataFrame(), pd.DataFrame({"close": [100.0]})], ids=["empty", "single_close"])
def test_v7_no_forecast_has_missing_jump_flag_with_state(ohlcv):
    result = l3.compute_forward_variance("AAA", ohlcv, implied_vol=0.3)
    assert result.jump_risk_flag is None
    row = result.to_dict()
    assert row["l3_jump_risk_flag"] is None
    assert row["l3_jump_risk_state"] == "NOT_ASSESSED_NO_FORECAST"
    assert row["l3_forecast_state"] == "MISSING_PRICE_HISTORY"


def test_v7_short_history_forecast_does_not_claim_no_jump_risk():
    """ATR proxy with < 20 returns: a forecast exists but jump risk cannot be measured."""
    close = 100 * np.exp(np.cumsum(np.random.default_rng(1).normal(0, 0.02, 12)))
    ohlcv = pd.DataFrame({"close": close, "high": close * 1.01, "low": close * 0.99})
    result = l3.compute_forward_variance("AAA", ohlcv, implied_vol=0.3)
    assert result.method == "ATR_PROXY" and result.forward_realised_vol is not None
    assert result.jump_risk_flag is None
    assert result.to_dict()["l3_jump_risk_state"] == "NOT_ASSESSED_SHORT_HISTORY"


def test_v7_flat_prices_do_not_claim_no_jump_risk():
    close = np.full(80, 50.0)
    result = l3.compute_forward_variance("AAA", pd.DataFrame({"close": close}), implied_vol=None)
    assert result.jump_risk_flag is None
    assert result.to_dict()["l3_jump_risk_state"] == "NOT_ASSESSED_NO_PRICE_VARIATION"


def test_v7_assessed_jump_flag_is_a_real_boolean_with_state():
    calm = l3.compute_forward_variance("AAA", _ohlcv(), implied_vol=0.3)
    assert calm.jump_risk_flag in (True, False)
    assert calm.to_dict()["l3_jump_risk_state"] == "ASSESSED"
    close = list(100 * np.exp(np.cumsum(np.random.default_rng(3).normal(0, 0.005, 255))))
    for move in (0.12, -0.15, 0.10, -0.12, 0.14):
        close.append(close[-1] * (1 + move))
    jumpy = l3.compute_forward_variance("AAA", pd.DataFrame({"close": close}), implied_vol=0.3)
    assert jumpy.jump_risk_flag is True


# ── Consumers read a missing jump flag as not assessed, never as "no jump risk" ─

def _load_eod():
    import eod_candidate_engine
    return eod_candidate_engine


@pytest.mark.parametrize("row", [{}, {"l3_jump_risk_flag": ""}, {"l3_jump_risk_flag": "nan"}, {"l3_jump_risk_flag": None}])
def test_c5_eod_manifest_missing_jump_flag_is_not_assessed(row):
    fields = _load_eod()._jump_risk_review_fields(row)
    assert fields["jump_risk_review_required"] == "NOT_ASSESSED"
    assert fields["jump_risk_note"] == "GARCH_JUMP_RISK_NOT_ASSESSED"
    assert fields["l3_jump_risk_flag"] == ""


def test_c5_eod_manifest_measured_jump_flags_keep_their_meaning():
    eod = _load_eod()
    assert eod._jump_risk_review_fields({"l3_jump_risk_flag": "True"}) == {
        "l3_jump_risk_flag": "True", "jump_risk_review_required": "TRUE", "jump_risk_note": "GARCH_JUMP_RISK_REVIEW"}
    assert eod._jump_risk_review_fields({"jump_risk_flag": "False"}) == {
        "l3_jump_risk_flag": "False", "jump_risk_review_required": "FALSE", "jump_risk_note": ""}


def _write_csv(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(path, index=False)


def test_c6_bridge_does_not_order_a_candidate_whose_jump_risk_was_not_assessed(tmp_path):
    from bridge.avshunter_reader import load_trade_candidates
    run = tmp_path / "RID"
    base = {"eod_candidate_authorized": "TRUE", "execution_permission": "GO", "contract_spread_pct": 5.0}
    _write_csv(run / "execution" / "execution_v3_5_RID.csv", [
        {**base, "ticker": "SAFE", "l3_jump_risk_flag": "False"},
        {**base, "ticker": "JUMP", "l3_jump_risk_flag": "True"},
        {**base, "ticker": "UNKNOWN", "l3_jump_risk_flag": ""},
    ])
    tickers = [row["ticker"] for row in load_trade_candidates(run)]
    assert tickers == ["SAFE"]


def _load_lab():
    path = ROOT / "intelligence-lab" / "intelligence_lab.py"
    spec = importlib.util.spec_from_file_location("intelligence_lab_l3_leftovers", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_c7_lab_stats_count_jump_risk_not_assessed():
    stats = _load_lab()._garch_stats([
        {"l3_jump_risk_flag": "True"}, {"l3_jump_risk_flag": "False"},
        {"l3_jump_risk_flag": ""}, {"l3_jump_risk_flag": "nan"}, {},
    ])
    assert stats["jump_risk"] == 1
    assert stats["jump_risk_not_assessed"] == 3


# ── Macro regime display: missing is said, never invented as TRANSITIONAL ───────

def test_m1_no_macro_file_displays_missing_regime(tmp_path):
    assert _runner()._load_regime(tmp_path) == "MACRO_REGIME_MISSING"


def test_m1_macro_file_without_regime_field_displays_missing(tmp_path):
    path = tmp_path / "dropbox" / "macro" / "macro_intelligence_latest.json"
    path.parent.mkdir(parents=True)
    path.write_text('{"other": 1}', encoding="utf-8")
    assert _runner()._load_regime(tmp_path) == "MACRO_REGIME_MISSING"


def test_m1_unreadable_macro_file_displays_missing(tmp_path):
    path = tmp_path / "dropbox" / "macro" / "macro_intelligence_latest.json"
    path.parent.mkdir(parents=True)
    path.write_text("{not json", encoding="utf-8")
    assert _runner()._load_regime(tmp_path) == "MACRO_REGIME_MISSING"
