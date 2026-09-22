from __future__ import annotations

import csv
import hashlib
import io
import json
from datetime import datetime, timezone
from pathlib import Path

import build_macro_json as builder
import intelligent_orchestrator as orchestrator
from scripts.macro_quant_packet import build_macro_quant_packet


ROOT = Path(__file__).resolve().parents[1]


def _use_complete_gex(tmp_path: Path, monkeypatch) -> None:
    """Pin a complete GEX publication instead of depending on today's drop."""
    proxy = tmp_path / builder.GEX_PROXY_FILENAME
    proxy.write_text(
        "Ticker,Date,As_Of,Data_Mode,Net_GEX_Bn,Regime,Data_Status,Run_Id\n"
        "SPY,2026-09-18,2026-09-18T20:00:00Z,HISTORICAL,-5.2,NEGATIVE,OK,FIXTURE\n"
        "QQQ,2026-09-18,2026-09-18T20:00:00Z,HISTORICAL,0.4,POSITIVE,OK,FIXTURE\n",
        encoding="utf-8",
    )
    strike = tmp_path / builder.GEX_BY_STRIKE_FILENAME
    strike.write_text(
        "Ticker,Date,strike,net_gex_usd_1pct\n"
        "SPY,2026-09-18,760,500\nQQQ,2026-09-18,720,300\n",
        encoding="utf-8",
    )
    manifest = tmp_path / builder.GEX_MANIFEST_FILENAME
    manifest.write_text(json.dumps({
        "status": "COMPLETE", "run_id": "FIXTURE", "session_date": "2026-09-18",
        "proxy_sha256": hashlib.sha256(proxy.read_bytes()).hexdigest(),
        "by_strike_sha256": hashlib.sha256(strike.read_bytes()).hexdigest(),
    }), encoding="utf-8")
    selected = {path.name: path for path in (proxy, strike, manifest)}
    original = builder.find_latest_file
    monkeypatch.setattr(
        builder, "find_latest_file",
        lambda directory, pattern: selected.get(pattern) or original(directory, pattern),
    )


def _model_macro() -> dict:
    return {
        "contract_version": "macro_contract_v1_0",
        "regime_state": "TRANSITIONAL",
        "dir_bias": "NEUTRAL",
        "trend_energy": "MIXED",
        "usd_state": "STABLE",
        "rates_impulse": "NEUTRAL",
        "liquidity_pulse": "STABLE",
        "regime_drift_status": "STABLE",
        "macro_conviction": 0.55,
        "vol_mode": "SHALLOW_CONTANGO",
        "risk_on_off_switch": "SELECTIVE",
        "notes": "Advisory context only.",
        "as_of_utc": "2026-09-18T20:00:00Z",
        "report_date": "2026-09-18",
        "net_liquidity_score": 0.5,
        "vix_regime_score": 0.5,
        "macro_momentum_score": 0.5,
        "regime_label": "TRANSITIONAL",
        "vix_spot": 15.0,
        "size_multiplier": 1.0,
        "horizon_routing": {},
        "gex_available": False,
        "conflict_flags": "GEX required session unavailable",
        "extras": {
            "conviction_score": 0.55,
            "vix_contango": 0.0,
            "volatility_mode": "SHALLOW_CONTANGO",
            "liquidity_status": "STABLE",
            "predictability_score": 0.5,
            "futures_bias": {
                "ES_SPY": {"note": "old GEX -2.8bn"},
                "NQ_QQQ": {"note": "old GEX -2.4bn"},
            },
        },
    }


def test_current_market_data_builds_complete_governed_prompt() -> None:
    payload = builder.load_data_payload(ROOT / "dropbox" / "market_data")
    prompt = builder.format_data_for_prompt(payload)
    context_text = prompt.split("=== GOVERNED MACRO INPUT CONTEXT ===", 1)[1]

    assert payload["input_manifest"]["gex_validation"]["status"] in {
        "VALIDATED", "SOURCE_UNAVAILABLE",
    }
    context = builder.build_macro_prompt_context(payload)
    assert context["input_consumption_status"] == "COMPLETE"
    assert len(context["input_consumption_ledger"]) == len(payload["input_manifest"]["entries"])
    assert '"breadth_csv"' in context_text
    assert '"threshold_flags_csv"' in context_text
    assert '"XLC"' in context_text
    assert '"VVIX"' in context_text
    assert '"DXY"' in context_text
    if payload["input_manifest"]["gex_validation"]["status"] == "VALIDATED":
        assert '"top_absolute_strikes"' in context_text
    else:
        assert '"SOURCE_UNAVAILABLE"' in context_text
        assert "gex_proxy_csv" not in payload["data"]
        macro = builder.apply_market_data_overrides(_model_macro(), payload)
        macro = builder.apply_macro_input_governance(macro, payload)
        builder.validate_macro_output_coherence(macro, payload)
        assert macro["gex_available"] is False
        assert macro["gex_regime_score"] is None
        assert macro["extras"]["gex"]["state"] == "MISSING"
        assert macro["extras"]["futures_bias"]["ES_SPY"]["gex_state"] == "SOURCE_UNAVAILABLE"
        assert "old GEX" not in json.dumps(macro["extras"]["futures_bias"])


def test_reconciled_macro_consumes_complete_gex_and_stays_advisory(tmp_path, monkeypatch) -> None:
    _use_complete_gex(tmp_path, monkeypatch)
    payload = builder.load_data_payload(ROOT / "dropbox" / "market_data")
    macro = builder.apply_market_data_overrides(_model_macro(), payload)
    macro = builder.apply_macro_input_governance(macro, payload)
    builder.validate_macro_output_coherence(macro, payload)
    packet = build_macro_quant_packet(macro)

    assert macro["macro_authority"] == "ADVISORY_ONLY"
    assert macro["macro_candidate_authority"] == "NONE"
    assert macro["macro_direction_authority"] == "NONE"
    assert macro["macro_contract_authority"] == "NONE"
    assert macro["macro_capital_authority"] == "NONE"
    assert macro["gex_available"] is True
    expected_run = payload["input_manifest"]["gex_validation"]["run_id"]
    expected_rows = {
        row["Ticker"]: float(row["Net_GEX_Bn"])
        for row in csv.DictReader(io.StringIO(payload["data"]["gex_proxy_csv"]))
    }
    assert macro["extras"]["gex"]["run_id"] == expected_run
    assert macro["extras"]["futures_bias"]["ES_SPY"]["net_gex_bn"] == expected_rows["SPY"]
    assert macro["extras"]["futures_bias"]["NQ_QQQ"]["net_gex_bn"] == expected_rows["QQQ"]
    assert packet["macro_authority"] == "ADVISORY_ONLY"
    assert packet["macro_input_manifest_id"] == macro["macro_input_manifest_id"]
    assert not any(
        "required session unavailable" in str(flag).lower()
        for flag in macro["conflict_flags"]
    )


def test_orchestrator_accepts_verified_advisory_and_rejects_changed_source(
    tmp_path: Path, monkeypatch,
) -> None:
    payload = builder.load_data_payload(ROOT / "dropbox" / "market_data")
    macro = builder.apply_market_data_overrides(_model_macro(), payload)
    macro = builder.apply_macro_input_governance(macro, payload)
    macro["extras"].update({
        "conviction_score": 0.55,
        "liquidity_status": "STABLE",
        "volatility_mode": "SHALLOW_CONTANGO",
        "vix_contango": 3.0,
    })
    macro["_builder_metadata"] = {"input_manifest": payload["input_manifest"]}
    path = tmp_path / "macro_intelligence_latest.json"
    path.write_text(json.dumps(macro), encoding="utf-8")
    monkeypatch.setattr(orchestrator.cfg, "MACRO_DIR", tmp_path)
    monkeypatch.setattr(orchestrator.cfg, "MACRO_FILE", path)
    monkeypatch.setattr(orchestrator.cfg, "MACRO_STALE_HOURS", 10**9)

    ready, message, selected = orchestrator.check_macro_json()
    assert ready is True
    assert selected == path
    assert macro["macro_authority"] == "ADVISORY_ONLY"

    tampered = json.loads(path.read_text())
    tampered["_builder_metadata"]["input_manifest"]["manifest_sha256"] = "0" * 64
    path.write_text(json.dumps(tampered), encoding="utf-8")
    ready, message, selected = orchestrator.check_macro_json()
    assert ready is False
    assert selected is None
    assert "lineage" in message.lower() or "manifest" in message.lower()


def test_required_macro_glob_does_not_select_threshold_flags(tmp_path: Path) -> None:
    threshold = tmp_path / "macro_series_threshold_flags.csv"
    capture = tmp_path / "macro_20260918_104311.csv"
    threshold.write_text("series,flag\nVIX,GREEN\n", encoding="utf-8")
    capture.write_text("Date,value\n2026-09-18,1\n", encoding="utf-8")
    assert builder.find_latest_file(tmp_path, "macro_????????_??????.csv") == capture


def test_macro_freshness_uses_completed_session_across_weekend() -> None:
    macro = _model_macro()
    flat = orchestrator._flatten_macro(macro)
    warning = orchestrator._macro_freshness_warning(
        macro,
        flat,
        now_utc=datetime(2026, 9, 20, 15, 0, tzinfo=timezone.utc),
    )
    assert warning is None


def test_macro_freshness_uses_market_session_not_weekend_build_date() -> None:
    """A Sunday build date must not masquerade as a future market session."""

    macro = _model_macro()
    macro["report_date"] = "2026-09-20"
    macro.setdefault("extras", {})["macro_input_lineage"] = {
        "gex_validation": {"session_date": "2026-09-18"},
    }
    flat = orchestrator._flatten_macro(macro)
    warning = orchestrator._macro_freshness_warning(
        macro,
        flat,
        now_utc=datetime(2026, 9, 20, 15, 0, tzinfo=timezone.utc),
    )
    assert warning is None


def test_macro_freshness_warns_when_a_completed_session_is_missing() -> None:
    macro = _model_macro()
    macro["report_date"] = "2026-09-17"
    macro["as_of_utc"] = "2026-09-17T20:00:00Z"
    flat = orchestrator._flatten_macro(macro)
    warning = orchestrator._macro_freshness_warning(
        macro,
        flat,
        now_utc=datetime(2026, 9, 20, 15, 0, tzinfo=timezone.utc),
    )
    assert warning is not None
    assert "2026-09-17" in warning
    assert "2026-09-18" in warning
