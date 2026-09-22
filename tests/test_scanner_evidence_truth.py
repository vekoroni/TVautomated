"""Scanner evidence must not acquire trading authority from missing or proxy data."""

import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import pandas as pd

from scripts import avshunter_universe_scanner as scanner


def test_standalone_scanner_entry_point_imports_domain_contract():
    repo = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, str(repo / "scripts" / "avshunter_universe_scanner.py"), "--help"],
        cwd=repo,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr


def _lead(**overrides):
    inputs = dict(
        vms={"score": 80, "decision": "GO", "iv_rank": 0.5},
        vol_anomaly={"options_vol_ratio": None, "sweep_flag": "NO_TRADE_PRINT_DATA"},
        short_data={"short_data_available": False},
        sector_rs={"sector_rs_flag": "NO_MAP"},
        dark_pool={"dark_pool_proxy_score": 0},
        price_data={},
    )
    inputs.update(overrides)
    return scanner.compute_lead_signal_score(**inputs)


def test_chain_volume_concentration_is_not_a_sweep():
    chain = pd.DataFrame(
        {"contract_type": ["call", "put"], "volume": [300, 50]}
    )
    with sqlite3.connect(":memory:") as conn:
        evidence = scanner._compute_options_volume_anomaly(chain, "TEST", conn)
    assert evidence["call_put_vol_ratio"] == 6.0
    assert evidence["volume_concentration_side"] == "CALL"
    assert evidence["sweep_flag"] == "NO_TRADE_PRINT_DATA"
    assert evidence["options_vol_ratio"] is None  # no historical baseline


def test_call_put_ratio_preserves_zero_calls_and_undefined_zero_puts():
    with sqlite3.connect(":memory:") as conn:
        only_puts = scanner._compute_options_volume_anomaly(
            pd.DataFrame({"contract_type": ["put"], "volume": [10]}), "PUTS", conn
        )
        only_calls = scanner._compute_options_volume_anomaly(
            pd.DataFrame({"contract_type": ["call"], "volume": [10]}), "CALLS", conn
        )
    assert only_puts["call_put_vol_ratio"] == 0.0
    assert only_calls["call_put_vol_ratio"] is None


def test_missing_activity_and_short_data_do_not_exclude_vms_go():
    result = _lead()
    assert result["lss_decision"] == "LEAD_INCOMPLETE"
    assert result["lss_route"] == "WATCHLIST_ONLY"
    assert result["lss_comp4_short"] is None
    assert "OPTIONS_VOLUME_BASELINE" in result["lss_missing_evidence"]
    assert "SHORT_DATA" in result["lss_missing_evidence"]
    assert "SWEEP" not in result["lss_reasons"]


def test_aggregate_volume_ratio_does_not_gain_sweep_bonus():
    base = _lead(vol_anomaly={"options_vol_ratio": 1.0, "sweep_flag": "NO_TRADE_PRINT_DATA"})
    legacy = _lead(vol_anomaly={"options_vol_ratio": 1.0, "sweep_flag": "CALL_SWEEP"})
    assert base["lss_comp1_opts_vol"] == legacy["lss_comp1_opts_vol"]
    assert "sweep=" not in legacy["lss_reasons"]


def test_option_activity_proxy_never_claims_dark_pool_evidence():
    chain = pd.DataFrame({"volume": [1000], "bid": [1.0], "ask": [1.01]})
    result = scanner.compute_dark_pool_proxy(chain, {"spot": 100, "live_prev_close": 95})
    assert result["dark_pool_proxy_score"] > 0
    assert result["dark_pool_proxy_flag"] == "OPTION_ACTIVITY_PROXY"
    assert result["dark_pool_data_source"] == "PROXY_ONLY"


def test_manifest_retains_low_score_ticker_and_reports_actual_route_source(tmp_path, monkeypatch):
    monkeypatch.setattr(scanner, "OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(scanner, "SIGNAL_HISTORY_PATH", tmp_path / "history.json")
    rows = pd.DataFrame([{
        "ticker": "TEST", "score": 80, "decision": "GO", "pipeline_tag": "NEW",
        "iv_rank_source": "REAL", "lss_score": 12, "lss_decision": "LEAD_INCOMPLETE",
        "lss_route": "WATCHLIST_ONLY",
    }])
    manifest = scanner.write_outputs(pd.DataFrame(), rows, "test", ["TEST"], False)
    scoreboard = pd.read_csv(tmp_path / "vms_scoreboard_latest.csv")
    assert scoreboard.loc[0, "scanner_primary_route"] == "WATCHLIST_ONLY"
    assert scoreboard.loc[0, "route_source"] == "SCANNER_LSS"
    assert manifest["tickers"]["TEST"]["lss_decision"] == "LEAD_INCOMPLETE"
    assert manifest["go_new"] == ["TEST"]  # VMS finding remains discoverable
    assert json.loads((tmp_path / "scanner_manifest.json").read_text())["tickers"]["TEST"]


def test_pipeline_context_preserves_missing_evidence_without_upgrading_route(tmp_path, monkeypatch):
    import intelligent_orchestrator as orchestrator

    monkeypatch.setattr(orchestrator.cfg, "RUNS_DIR", tmp_path)
    row = pd.DataFrame([{
        "ticker": "TEST", "score": 80, "decision": "GO", "lss_route": "WATCHLIST_ONLY",
        "lss_score": 12, "lss_decision": "LEAD_INCOMPLETE",
        "lss_missing_evidence": "OPTIONS_VOLUME_BASELINE|SHORT_DATA",
        "volume_concentration_side": "CALL", "call_put_vol_ratio": 6.0,
        "sweep_flag": "NO_TRADE_PRINT_DATA", "pipeline_tag": "NEW",
    }])
    scanner_input = {
        "available": True, "vms_df": row, "run_id": "scanner-run",
        "manifest_tickers": {"TEST": {"signal_detected_at": "2026-09-21T00:00:00Z"}},
    }
    orchestrator.write_scanner_context(scanner_input, "pipeline-run")
    context = json.loads((tmp_path / "pipeline-run" / "scanner_context_pipeline-run.json").read_text())
    ticker = context["tickers"]["TEST"]
    assert ticker["scanner_primary_route"] == "WATCHLIST_ONLY"
    assert ticker["lss_missing_evidence"] == "OPTIONS_VOLUME_BASELINE|SHORT_DATA"
    assert ticker["volume_concentration_side"] == "CALL"
    assert ticker["sweep_flag"] == "NO_TRADE_PRINT_DATA"
