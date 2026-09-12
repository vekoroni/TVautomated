from __future__ import annotations

import json
import math
import sys
import tempfile
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from contracts.handoff_contract import (  # noqa: E402
    HandoffTruthPacket,
    PRIORITY_DISCOVERY,
    PRIORITY_EIL_PSE,
    PRIORITY_INFERRED,
    PRIORITY_MACRO_QUANT,
    PRIORITY_VANGUARD_ACTUARIAL,
    build_truth_packet_from_row,
    enrich_dataframe_with_truth_packets,
    is_missing_value,
)


def test_unknown_cannot_overwrite_confirmed_value() -> None:
    pkt = HandoffTruthPacket(run_id="R1", ticker="AAPL", run_mode="EVENING")
    pkt.add_field("macro_regime_label", "RISK_ON", "MACRO", priority=PRIORITY_MACRO_QUANT)
    pkt.add_field("macro_regime_label", "UNKNOWN", "FALLBACK", status="INFERRED", priority=PRIORITY_INFERRED)
    assert pkt.get("macro_regime_label") == "RISK_ON"


def test_nan_cannot_overwrite_confirmed_value() -> None:
    pkt = HandoffTruthPacket(run_id="R1", ticker="AAPL")
    pkt.add_field("state_v2", "STATE_A", "VANGUARD", priority=PRIORITY_VANGUARD_ACTUARIAL)
    pkt.add_field("state_v2", math.nan, "CSV", status="MISSING", priority=PRIORITY_EIL_PSE)
    assert pkt.get("state_v2") == "STATE_A"


def test_higher_priority_confirmed_overwrites_lower_inferred() -> None:
    pkt = HandoffTruthPacket(run_id="R1", ticker="AAPL")
    pkt.add_field("ticker_sector_alignment", "NEUTRAL", "DERIVED", status="INFERRED", priority=PRIORITY_INFERRED)
    pkt.add_field("ticker_sector_alignment", "ALIGNED", "MACRO", priority=PRIORITY_MACRO_QUANT)
    assert pkt.get("ticker_sector_alignment") == "ALIGNED"
    assert pkt.conflicts[0]["reason"] == "higher_priority_override"


def test_conflicting_confirmed_fields_create_conflict_record() -> None:
    pkt = HandoffTruthPacket(run_id="R1", ticker="AAPL")
    pkt.add_field("direction", "CALL", "DISCOVERY", priority=PRIORITY_DISCOVERY)
    pkt.add_field("direction", "PUT", "EIL", priority=PRIORITY_EIL_PSE)
    assert pkt.get("direction") == "CALL"
    assert pkt.conflicts
    assert pkt.finalise().packet_status == "CONFLICTED"


def test_numeric_zero_is_not_missing() -> None:
    assert is_missing_value(0) is False
    assert is_missing_value(0.0) is False


def test_to_flat_dict_returns_csv_safe_values() -> None:
    pkt = HandoffTruthPacket(run_id="R1", ticker="AAPL")
    pkt.add_field("preferred_sectors", ["TECH", "XLK"], "MACRO", priority=PRIORITY_MACRO_QUANT)
    pkt.add_field("bucket_clarity_scores", {"equities": 80}, "MACRO", priority=PRIORITY_MACRO_QUANT)
    flat = pkt.to_flat_dict()
    assert json.loads(flat["preferred_sectors"]) == ["TECH", "XLK"]
    assert json.loads(flat["bucket_clarity_scores"]) == {"equities": 80}


def test_to_json_dict_returns_json_safe_values() -> None:
    pkt = HandoffTruthPacket(run_id="R1", ticker="AAPL")
    pkt.add_field("macro_age_hours", math.nan, "MACRO", status="MISSING", priority=PRIORITY_MACRO_QUANT)
    payload = pkt.to_json_dict()
    assert payload["fields"]["macro_age_hours"]["value"] is None


def test_merge_preserves_stronger_packet_fields() -> None:
    weak = HandoffTruthPacket(run_id="R1", ticker="AAPL")
    weak.add_field("state_v2", "UNKNOWN", "FALLBACK", status="INFERRED", priority=PRIORITY_INFERRED)
    strong = HandoffTruthPacket(run_id="R1", ticker="AAPL")
    strong.add_field("state_v2", "STATE_A", "VANGUARD", priority=PRIORITY_VANGUARD_ACTUARIAL)
    weak.merge(strong)
    assert weak.get("state_v2") == "STATE_A"


def test_eil_blocked_gate_is_advisory() -> None:
    pkt = HandoffTruthPacket(run_id="R1", ticker="AAPL")
    pkt.apply_sovereign_gate("EIL_BLOCKED", "BLOCKED", "test block", "EIL")
    assert pkt.finalise().packet_status == "PARTIAL"
    assert not pkt.errors
    assert "EIL_BLOCKED" in " ".join(pkt.warnings)


def test_validate_required_returns_missing_fields() -> None:
    pkt = HandoffTruthPacket(run_id="R1", ticker="AAPL")
    pkt.add_field("ticker", "AAPL", "DISCOVERY", priority=PRIORITY_DISCOVERY)
    result = pkt.validate_required(["ticker", "state_v2"])
    assert result["missing"] == ["state_v2"]


def test_build_packet_from_sample_candidate_row() -> None:
    row = {
        "run_id": "R1",
        "ticker": "AAPL",
        "direction": "CALL",
        "macro_regime_label": "RISK_ON",
        "sector_rotation_state": "TECH_LED_RISK_ON",
        "state_v2": "STATE_A",
        "layer2__state_match_method": "EXACT",
        "eil_v3_verdict": "PASS",
        "pse_execution_mode": "WATCH",
    }
    pkt = build_truth_packet_from_row(row, "SAMPLE", PRIORITY_EIL_PSE, run_id="R1", run_mode="EVENING")
    flat = pkt.to_flat_dict()
    assert flat["macro_regime_label"] == "RISK_ON"
    assert flat["layer2__state_match_method"] == "EXACT"
    assert flat["eil_v3_verdict"] == "PASS"


def test_eil_blocked_plus_go_is_retained_as_advisory() -> None:
    row = {
        "run_id": "R1",
        "ticker": "AAPL",
        "eil_v3_verdict": "BLOCKED",
        "thesis_decision": "GO",
    }
    pkt = build_truth_packet_from_row(row, "EIL", PRIORITY_EIL_PSE, run_id="R1", run_mode="EVENING")
    assert pkt.packet_status == "PARTIAL"
    assert not pkt.errors
    assert "EIL_ADVISORY_BLOCKED" in " ".join(pkt.warnings)


def test_final_csv_writer_includes_truth_packet_status_fields() -> None:
    df = pd.DataFrame([
        {
            "run_id": "R1",
            "ticker": "AAPL",
            "macro_regime_label": "RISK_ON",
            "state_v2": "STATE_A",
            "eil_v3_verdict": "PASS",
        }
    ])
    enriched = enrich_dataframe_with_truth_packets(df, "TEST", PRIORITY_EIL_PSE, run_id="R1", run_mode="EVENING")
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "out.csv"
        enriched.to_csv(path, index=False)
        loaded = pd.read_csv(path)
    assert "truth_packet_status" in loaded.columns
    assert "handoff_integrity_status" in loaded.columns
    assert loaded.loc[0, "truth_packet_status"] == "VALID"


def test_scanner_fields_are_preserved_but_do_not_create_execution_permission() -> None:
    row = {
        "run_id": "R1",
        "ticker": "AAPL",
        "scanner_source": "UNIVERSE_SCANNER",
        "scanner_run_id": "SCAN1",
        "scanner_signal_type": "GO",
        "scanner_score": 92,
        "scanner_confidence": 0.92,
        "scanner_data_quality": "CONFIRMED",
    }
    pkt = build_truth_packet_from_row(row, "SCANNER_CONTEXT", PRIORITY_DISCOVERY, run_id="R1", run_mode="EVENING")
    flat = pkt.to_flat_dict()
    assert flat["scanner_source"] == "UNIVERSE_SCANNER"
    assert flat["scanner_score"] == 92
    assert "execution_mode" not in flat
    assert "thesis_decision" not in flat


def test_catalyst_and_eod_receipts_are_preserved() -> None:
    row = {
        "run_id": "R1",
        "ticker": "AAPL",
        "catalyst_type": "EARNINGS",
        "catalyst_date": "2026-05-15",
        "catalyst_truth_score": 0.82,
        "catalyst_event_status": "SCHEDULED",
        "catalyst_source_tier": "TIER_1",
        "eod_candidate_status": "EOD_EXECUTE_CANDIDATE",
        "eod_dropoff_reason": "SURVIVED_TO_EOD_EXECUTE",
        "monetisation_fit_score": 88,
        "direction_reroute_status": "SELECTED_FROM_EVIDENCE",
        "selected_contract_side": "CALL",
        "contract_repair_status": "CONTRACT_OK",
        "contract_repair_required": "FALSE",
    }
    pkt = build_truth_packet_from_row(row, "EOD", PRIORITY_EIL_PSE, run_id="R1", run_mode="EVENING")
    flat = pkt.to_flat_dict()
    assert flat["catalyst_truth_score"] == 0.82
    assert flat["catalyst_event_status"] == "SCHEDULED"
    assert flat["eod_candidate_status"] == "EOD_EXECUTE_CANDIDATE"
    assert flat["monetisation_fit_score"] == 88
    assert flat["selected_contract_side"] == "CALL"
    assert flat["contract_repair_status"] == "CONTRACT_OK"


def _run_direct() -> None:
    tests = [
        obj for name, obj in globals().items()
        if name.startswith("test_") and callable(obj)
    ]
    for test in tests:
        test()
    print(f"handoff_contract tests passed: {len(tests)}")


if __name__ == "__main__":
    _run_direct()
