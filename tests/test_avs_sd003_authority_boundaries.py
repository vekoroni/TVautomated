from __future__ import annotations

from contracts.lab_control import opportunity_book_row
from contracts.direction_governance import resolve_governed_direction
from pathlib import Path
import json


def _base_signal() -> dict:
    direction = resolve_governed_direction(
        ticker="AAPL",
        run_id="RUN-1",
        discovery_direction="CALL",
        governed_direction="CALL",
        governed_basis="test=CALL",
        row={},
        decided_at_utc="2026-09-04T08:00:00+00:00",
    )
    return {
        "ticker": "AAPL",
        "canonical_direction": "CALL",
        "final_direction": "CALL",
        "instrument": "LONG_CALL",
        "contract_symbol": "AAPL260918C00100000",
        "final_action": "BUY_NOW",
        "lab_tradeable": True,
        "lab_verdict": "GO",
        "capital_permission": "YES",
        "contract_quote_timestamp_utc": "2026-09-04T08:30:00Z",
        "execution_viability_policy_version": "long-option-v1",
        "execution_viability_state": "ELIGIBLE",
        "execution_viability_reason": "OK",
        "execution_viability_eligible": True,
        "execution_viability_bid": 1.0,
        "execution_viability_ask": 1.1,
        "invalidation_spot": 95.0,
        "invalidation_state": "AVAILABLE",
        "invalidation_source": "GOVERNED_THESIS",
        **direction,
    }


def test_lab_preserves_quote_viability_and_governed_invalidation_lineage() -> None:
    row = opportunity_book_row(_base_signal(), "RUN-1", 1)
    assert row["selected_quote_timestamp_utc"] == "2026-09-04T08:30:00Z"
    assert row["execution_viability_state"] == "ELIGIBLE"
    assert row["execution_viability_bid"] == 1.0
    assert row["invalidation_price"] == 95.0
    assert row["invalidation_state"] == "AVAILABLE"
    assert row["invalidation_source"] == "GOVERNED_THESIS"


def test_lab_blocks_directional_execution_without_governed_invalidation() -> None:
    signal = _base_signal()
    signal.pop("invalidation_spot")
    signal.pop("invalidation_state")
    signal["stop_loss"] = 95.0
    row = opportunity_book_row(signal, "RUN-2", 1)
    assert row["lab_tradeable"] is False
    assert row["final_action"] == "BLOCK"
    assert row["lab_execution_status"] == "INVALIDATION_MISSING"
    assert "INVALIDATION_MISSING" in row["execution_lock_reason"]


def test_run_meta_records_every_resolved_feature_flag(tmp_path, monkeypatch) -> None:
    import intelligent_orchestrator as orchestrator

    monkeypatch.setattr(orchestrator.cfg, "RUNS_DIR", Path(tmp_path))
    monkeypatch.setenv("AVSHUNTER_COMPLETED_PROFILE_STAGE_ENABLED", "1")
    orchestrator._update_run_meta_status("RUN-3", "IN_PROGRESS", pipeline_mode="EOD")
    payload = json.loads((tmp_path / "RUN-3" / "run_meta.json").read_text())
    flags = payload["resolved_feature_flags"]
    assert len(flags) == 9
    assert flags["AVSHUNTER_COMPLETED_PROFILE_STAGE_ENABLED"] is True
    assert flags["AVSHUNTER_DYNAMIC_THESIS_ENABLED"] is True
    assert flags["AVSHUNTER_DYNAMIC_AUTO_ENABLED"] is False
    assert payload["ddd_runtime_profile"]["status"] == "CONTROLLED_LIVE_CYCLE"


def test_directional_options_economics_missing_target_is_governed_not_exception() -> None:
    from scripts.avshunter_options_intelligence import compute_trade_economics

    result = compute_trade_economics(
        {"mark": 1.25, "strike": 100.0, "theta": -0.02, "vega": 0.05, "delta": 0.4, "dte": 20},
        {
            "spot": 100.0,
            "entry": 100.0,
            "structural_target": None,
            "hold_days": 10,
            "direction": "CALL",
            "win_prob": 60.0,
        },
        {"ivp_label": "FAIR"},
    )
    assert result["economics_state"] == "NOT_EVALUATED"
    assert result["economics_reason"] == "STRUCTURAL_TARGET_UNRESOLVED"
    assert result["rr_premium_expected"] is None


def test_eod_permission_fails_closed_without_governed_invalidation() -> None:
    from eod_candidate_engine import _candidate_permission_fields

    result = _candidate_permission_fields(
        {
            "direction": "PUT",
            "signal_price": 100.0,
            "capital_permission": "EOD_CANDIDATE_ONLY",
            "eod_candidate_authorized": True,
            "execution_authorized": True,
        },
        "EOD_TRIGGER_READY",
    )
    assert result["capital_permission"] == "NO"
    assert result["eod_candidate_authorized"] is False
    assert result["execution_authorized"] is False
    assert result["invalidation_permission_reason"] == "INVALIDATION_MISSING"


def test_eod_numeric_invalidation_without_available_state_fails_closed() -> None:
    from eod_candidate_engine import _candidate_permission_fields

    result = _candidate_permission_fields(
        {
            "direction": "CALL",
            "signal_price": 100.0,
            "invalidation_spot": 95.0,
            "capital_permission": "YES",
            "execution_authorized": True,
        },
        "EOD_TRIGGER_READY",
    )
    assert result["capital_permission"] == "NO"
    assert result["execution_authorized"] is False
    assert result["invalidation_permission_reason"] == "INVALIDATION_MISSING"
