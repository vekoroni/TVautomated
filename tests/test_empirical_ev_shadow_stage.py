"""Item 2 wiring (ACK 17 Sep 2026): empirical option EV runs in shadow on every evening options output.

The enhanced `empirical_option_ev` (ticker-volatility scaling, exit at bid) has no production caller.
It is wired as a NON-CRITICAL, NO-AUTHORITY evening stage right after the Layer 3 merge, so forward sessions
accumulate evidence the outcome scorer can test. Nothing may branch on the emp_* columns.

  M1 an options-output row maps to the module's candidate fields (actuarial outcomes, quote, IV, spot, DTE,
     direction, hold, Layer 3 forecast);
  M2 the stage writes emp_* columns into the options output for rows with a selected contract; rows without
     one carry emp_quality_flag NO_SELECTED_CONTRACT and no numbers;
  M3 re-running replaces emp_* columns (no duplicates) and leaves every other column unchanged;
  M4 an unreadable options output is a named FAILED status, never an exception;
  M5 a summary artefact records flag counts and NO_AUTHORITY;
  M6 evening_workflow calls the stage after merge_garch_into_enriched.
"""

from __future__ import annotations

import inspect
import json
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

import intelligent_orchestrator as orchestrator
from empirical_option_ev import EMPTY_COLUMNS, candidate_from_options_row

RUN = "20260917_223000"
LABELS = ("p01", "p05", "p10", "p20", "p30", "p40", "p50", "p60", "p70", "p80", "p90", "p95", "p99")
DIST = (-0.15, -0.09, -0.06, -0.03, -0.01, 0.005, 0.015, 0.03, 0.05, 0.08, 0.13, 0.19, 0.32)


def _options_row(ticker="AAPL", symbol="AAPL261016C00105000", **overrides):
    row = {
        "ticker": ticker, "contract_occ_symbol": symbol, "final_direction": "CALL",
        "contract_bid": 1.90, "contract_ask": 2.10, "contract_iv": 0.45, "underlying_price": 100.0,
        "strike": 105.0, "contract_dte": 30.0, "layer2__recommended_hold_days": 10,
        "layer2__preferred_horizon": "10D", "layer2__n_obs_10d": 5000,
        "layer2__outcomes__state_match_method": "EXACT", "l3_forward_realised_vol": 0.40,
        "unrelated_column": "keep-me",
    }
    for label, value in zip(LABELS, DIST):
        row[f"layer2__outcomes__ret_pctl_10d_{label}"] = value
    row.update(overrides)
    return row


def _write_options(tmp_path: Path, rows):
    path = tmp_path / "runs" / RUN / "options" / f"options_intelligence_{RUN}.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(path, index=False)
    return path


def _stage(tmp_path):
    with patch.object(orchestrator.cfg, "RUNS_DIR", tmp_path / "runs"):
        return orchestrator.run_empirical_option_ev_shadow_stage(RUN)


def test_m1_options_row_maps_to_candidate():
    c = candidate_from_options_row(_options_row())
    assert c["state_match_method"] == "EXACT"
    assert (c["bid"], c["ask"], c["live_iv"], c["live_spot"], c["strike"], c["dte"]) == (1.90, 2.10, 0.45, 100.0, 105.0, 30.0)
    assert (c["direction"], c["hold_days"], c["preferred_horizon"], c["n_obs_10d"]) == ("CALL", 10, "10D", 5000)
    assert c["forecast_vol"] == 0.40 and c["ret_pctl_10d_p50"] == 0.015


def test_m2_emp_columns_written_for_contract_rows_only(tmp_path):
    path = _write_options(tmp_path, [_options_row(), _options_row(ticker="NOPE", symbol=None)])
    summary = _stage(tmp_path)
    out = pd.read_csv(path)
    assert set(EMPTY_COLUMNS) <= set(out.columns)
    aapl, nope = out.iloc[0], out.iloc[1]
    assert aapl["emp_quality_flag"] == "OK" and pd.notna(aapl["emp_expected_r"])
    assert nope["emp_quality_flag"] == "NO_SELECTED_CONTRACT" and pd.isna(nope["emp_expected_r"])
    assert summary["status"] == "COMPLETED"


def test_m3_rerun_replaces_emp_columns_and_keeps_others(tmp_path):
    path = _write_options(tmp_path, [_options_row()])
    _stage(tmp_path)
    first = pd.read_csv(path)
    _stage(tmp_path)
    second = pd.read_csv(path)
    assert list(first.columns) == list(second.columns)
    assert second["unrelated_column"].iloc[0] == "keep-me"
    assert len([c for c in second.columns if c == "emp_expected_r"]) == 1


def test_m4_unreadable_output_is_named_failure(tmp_path):
    path = tmp_path / "runs" / RUN / "options" / f"options_intelligence_{RUN}.csv"
    path.mkdir(parents=True)          # a directory where the CSV should be: unreadable
    summary = _stage(tmp_path)
    assert summary["status"] == "FAILED" and summary["reason"]
    missing = _stage(tmp_path / "elsewhere")
    assert missing["status"] == "SKIPPED" and missing["reason"] == "OPTIONS_OUTPUT_NOT_FOUND"


def test_m5_summary_artefact_records_flags_and_no_authority(tmp_path):
    _write_options(tmp_path, [_options_row(), _options_row(ticker="NOPE", symbol=None)])
    _stage(tmp_path)
    artefact = tmp_path / "runs" / RUN / "diagnostics" / f"empirical_option_ev_{RUN}.json"
    data = json.loads(artefact.read_text(encoding="utf-8"))
    assert data["authority"] == "NO_AUTHORITY" and data["can_grant_capital"] is False
    assert data["quality_flags"] == {"OK": 1, "NO_SELECTED_CONTRACT": 1}


def test_m6_evening_workflow_runs_stage_after_layer3_merge():
    source = inspect.getsource(orchestrator.evening_workflow)
    merged = source.index("merge_garch_into_enriched(canonical_run_id)")
    shadow = source.index("run_empirical_option_ev_shadow_stage(canonical_run_id)")
    assert merged < shadow


# ── Increment 2: path valuation in the shadow stage ─────────────────────────────────────────────

import empirical_option_ev as emp_module
from empirical_option_ev import PATH_COLUMNS

_CALIBRATION = {
    "version": "volatility_range_calibration_v1",
    "forecast_error_bands": {"5": {"p10": 0.6, "p50": 0.9, "p90": 1.5}, "10": {"p10": 0.65, "p50": 0.92, "p90": 1.4},
                             "20": {"p10": 0.7, "p50": 0.95, "p90": 1.3}},
    "innovation_quantiles": {"levels": [0.001, 0.5, 0.999], "values": [-3.09, 0.0, 3.09], "std": 1.0},
}


def _path_row(**overrides):
    return _options_row(structural_target=112.0, invalidation_spot=94.0, contract_dte=30.0, strike=100.0,
                        underlying_price=100.0, contract_iv=0.30, **overrides)


def _stage_with_calibration(tmp_path, calibration):
    path = tmp_path / "calibration.json"
    if calibration is not None:
        path.write_text(json.dumps(calibration), encoding="utf-8")
    with patch.object(orchestrator.cfg, "RUNS_DIR", tmp_path / "runs"), \
         patch.object(orchestrator, "EMPIRICAL_PATH_CALIBRATION_PATH", path):
        return orchestrator.run_empirical_option_ev_shadow_stage(RUN)


def test_m7_path_columns_written_with_governed_settings(tmp_path):
    out_path = _write_options(tmp_path, [_path_row()])
    summary = _stage_with_calibration(tmp_path, _CALIBRATION)
    out = pd.read_csv(out_path)
    assert set(PATH_COLUMNS) <= set(out.columns)
    row = out.iloc[0]
    assert row["emp_path_quality_flag"] == "OK"
    assert row["emp_path_r_cautious"] <= row["emp_path_r_central"] <= row["emp_path_r_upside"]
    assert summary["path_settings"]["paths"] == emp_module.PATH_SETTINGS["paths"]
    assert summary["path_quality_flags"] == {"OK": 1}


def test_m7_clipped_forecast_is_never_used_for_value(tmp_path):
    out_path = _write_options(tmp_path, [_path_row(l3_forward_realised_vol=2.5, l3_forward_realised_vol_raw=3.4,
                                                   l3_forecast_state="CLIPPED_AT_CAP")])
    _stage_with_calibration(tmp_path, _CALIBRATION)
    row = pd.read_csv(out_path).iloc[0]
    assert row["emp_path_vol_central"] == pytest.approx(3.4 * 0.92)          # hold 10 sessions -> band 10, p50 0.92
    assert row["emp_path_forecast_source"] == "RAW_UNCLIPPED"


def test_m8_missing_calibration_is_explicit(tmp_path):
    out_path = _write_options(tmp_path, [_path_row()])
    summary = _stage_with_calibration(tmp_path, None)
    row = pd.read_csv(out_path).iloc[0]
    assert row["emp_path_quality_flag"] == "CALIBRATION_UNAVAILABLE" and pd.isna(row["emp_path_r_central"])
    assert summary["status"] == "COMPLETED"


def test_m9_path_settings_are_governed():
    assert emp_module.PATH_SETTINGS["version"] == "empirical_path_valuation_v1"
    assert emp_module.PATH_SETTINGS["paths"] > 0 and isinstance(emp_module.PATH_SETTINGS["seed"], int)


# ── Increment 3: shares and expression preference in the shadow stage ───────────────────────────

import sqlite3

import numpy as np

from empirical_option_ev import SHARE_COLUMNS


def _price_db(tmp_path, ticker="AAPL", sessions=80, last_date="2026-09-17", spread=0.004):
    path = tmp_path / "prices.sqlite"
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE ohlcv_daily (ticker TEXT, trading_date TEXT, open REAL, high REAL, low REAL, close REAL, "
                "volume REAL, bar_status TEXT)")
    rng = np.random.default_rng(5)
    dates = pd.bdate_range(end=last_date, periods=sessions)
    mid = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, sessions)))
    close = mid * (1 + rng.choice([-1, 1], sessions) * spread / 2)
    rows = [(ticker, d.date().isoformat(), m, max(m * 1.01, c), min(m * 0.99, c), c, 1e6, "COMPLETE")
            for d, m, c in zip(dates, mid, close)]
    rows.append((ticker, "2026-09-30", 500.0, 900.0, 100.0, 800.0, 1e6, "COMPLETE"))   # after the run: must not be used
    con.executemany("INSERT INTO ohlcv_daily VALUES (?,?,?,?,?,?,?,?)", rows)
    con.commit()
    con.close()
    return path


def _stage_full(tmp_path, price_db):
    calibration = tmp_path / "calibration.json"
    calibration.write_text(json.dumps(_CALIBRATION), encoding="utf-8")
    with patch.object(orchestrator.cfg, "RUNS_DIR", tmp_path / "runs"), \
         patch.object(orchestrator, "EMPIRICAL_PATH_CALIBRATION_PATH", calibration), \
         patch.object(orchestrator, "EMPIRICAL_SHARE_PRICE_DB", price_db):
        return orchestrator.run_empirical_option_ev_shadow_stage(RUN)


def test_m10_share_valuation_and_preference_written(tmp_path):
    out_path = _write_options(tmp_path, [_path_row()])
    summary = _stage_full(tmp_path, _price_db(tmp_path))
    row = pd.read_csv(out_path).iloc[0]
    assert set(SHARE_COLUMNS) <= set(pd.read_csv(out_path).columns)
    assert row["emp_share_quality_flag"] == "OK" and 0 <= row["emp_share_spread_estimate"] < 0.05
    assert row["emp_expression_preference"] in {"OPTION", "SHARES", "NEITHER"}
    assert summary["preference_counts"] == {row["emp_expression_preference"]: 1}


def test_m11_missing_price_history_keeps_option_value(tmp_path):
    out_path = _write_options(tmp_path, [_path_row(ticker="NOHIST")])
    _stage_full(tmp_path, _price_db(tmp_path, ticker="AAPL"))
    row = pd.read_csv(out_path).iloc[0]
    assert row["emp_path_quality_flag"] == "OK" and pd.notna(row["emp_path_r_central"])
    assert row["emp_share_quality_flag"] == "SHARE_SPREAD_UNAVAILABLE"
    assert row["emp_expression_preference"] == "PREFERENCE_UNAVAILABLE"


def test_m12_share_spread_uses_only_bars_up_to_the_run_date(tmp_path):
    db = _price_db(tmp_path)
    assert orchestrator._share_spread_for(db, "AAPL", "2026-09-17") == \
        orchestrator._share_spread_for(db, "AAPL", "2026-09-17")
    with sqlite3.connect(db) as con:
        rows = con.execute("SELECT high, low, close FROM ohlcv_daily WHERE ticker='AAPL' AND trading_date <= '2026-09-17' "
                           "ORDER BY trading_date").fetchall()
    import empirical_option_ev as emp
    tail = rows[-emp.PATH_SETTINGS["share_spread_window_sessions"]:]
    expected = emp.abdi_ranaldo_spread([r[0] for r in tail], [r[1] for r in tail], [r[2] for r in tail])
    assert orchestrator._share_spread_for(db, "AAPL", "2026-09-17") == pytest.approx(expected)
