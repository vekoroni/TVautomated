"""The descriptive C5 packet is frozen before option interpretation."""

import csv
import json

from domain.descriptive_forecast_handoff import build_descriptive_packet
from contracts.descriptive_forecast_packet import (
    load_or_publish_descriptive_packet, project_lab_descriptive_rows,
)
from contracts.lab_control import FINAL_BOOK_FIELDS, _output_files, write_final_opportunity_book
from test_ila_release_coverage_gate import RUN_ID, _base_signal
from pipeline_interpreter.automation_v2.lab_structured import build_structured_lab_manifest


def _row(ticker="XYZ", **changes):
    row = {
        "ticker": ticker, "direction": "CALL",
        "direction_authority": "DISCOVERY_GOVERNED", "is_stale": "False",
        "bar_data_asof": "2026-09-25", "stock_price": "100",
        "structural_target": "110", "structural_target_source": "WYCKOFF",
        "governed_invalidation_spot": "95",
        "governed_invalidation_source": "WYCKOFF_VALIDATION",
        "sector": "Industrials", "selected_contract": "XYZ261016C00100000",
    }
    row.update(changes)
    return row


def test_descriptive_packet_keeps_ticker_forecast_separate_from_option():
    packet = build_descriptive_packet(
        "R", "2026-09-25", "2026-09-26T17:37:30Z", [_row()],
        discovery_sha256="a" * 64,
    )
    item = packet["rows"][0]
    assert item["forecast_direction"] == "BULL"
    assert item["forecast_state"] == "DESCRIPTIVE_ONLY"
    assert item["forecast_target_spot"] == 110.0
    assert item["forecast_invalidation_spot"] == 95.0
    assert item["c4_reliability_state"] == "NOT_ESTIMABLE"
    assert item["c8_valuation_state"] == "NOT_VALUED_STATISTICAL_SUPPORT"
    assert item["forecast_authority"] == "ADVISORY_ONLY"
    assert "selected_contract" not in item
    assert "option_symbol" not in item
    assert "ev" not in item


def test_missing_or_option_stage_target_is_visible_not_filled():
    packet = build_descriptive_packet(
        "R", "2026-09-25", "2026-09-26T17:37:30Z",
        [_row("XYZ", structural_target="", structural_target_source="PENDING_OI"),
         _row("ABC", direction_authority="DISCOVERY_PRELIMINARY_ONLY")],
        discovery_sha256="b" * 64,
    )
    first, second = packet["rows"]
    assert first["forecast_state"] == "DESCRIPTIVE_ONLY"
    assert first["forecast_target_spot"] is None
    assert first["forecast_reason"] == "TARGET_NOT_SOURCED_PREOPTION"
    assert second["forecast_state"] == "DATA_INSUFFICIENT"
    assert second["forecast_reason"] == "DIRECTION_NOT_GOVERNED"
    assert second["forecast_direction"] is None


def test_duplicate_ticker_or_missing_cutoff_fails_closed():
    import pytest
    with pytest.raises(ValueError, match="duplicate ticker"):
        build_descriptive_packet(
            "R", "2026-09-25", "2026-09-26T17:37:30Z",
            [_row(), _row()], discovery_sha256="c" * 64,
        )
    with pytest.raises(ValueError, match="as_of_utc"):
        build_descriptive_packet(
            "R", "2026-09-25", "", [_row()],
            discovery_sha256="c" * 64,
        )


def test_packet_is_immutable_after_evening_and_morning_uses_same_claim(tmp_path):
    root = tmp_path / "R"
    source = root / "discovery" / "discovery_candidates_ultimate_R.csv"
    source.parent.mkdir(parents=True)
    with source.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(_row()))
        writer.writeheader()
        writer.writerow(_row())
    (root / "run_meta.json").write_text(json.dumps({
        "canonical_run_id": "R", "pipeline_mode": "EOD",
        "dynamic_plan": {"last_completed_session": "2026-09-25",
                         "evidence_cutoff_utc": "2026-09-26T17:37:30Z"},
    }), encoding="utf-8")
    first = load_or_publish_descriptive_packet(root)
    assert first["rows"][0]["forecast_target_spot"] == 110.0
    with source.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(_row()))
        writer.writeheader()
        writer.writerow(_row(structural_target="120"))
    second = load_or_publish_descriptive_packet(root)
    assert second == first


def test_lab_projection_never_promotes_legacy_option_or_ev_into_c5_c8():
    packet = build_descriptive_packet(
        "R", "2026-09-25", "2026-09-26T17:37:30Z", [_row()],
        discovery_sha256="a" * 64,
    )
    source = [{"ticker": "XYZ", "lab_verdict": "GO", "ev3_ev_conservative_return": 0.8,
               "selected_contract_symbols": "XYZ261016C00100000"},
              {"ticker": "ABC", "lab_verdict": "WAIT"}]
    result = project_lab_descriptive_rows(source, packet)
    assert result[0]["forecast_direction"] == "BULL"
    assert result[0]["option_expression_state"] == "LEGACY_PROPOSAL_UNVALUED"
    assert result[0]["c8_numeric_ev"] is None
    assert result[0]["lab_verdict"] == "GO"
    assert result[1]["forecast_state"] == "DATA_INSUFFICIENT"
    assert result[1]["forecast_reason"] == "TICKER_NOT_IN_DISCOVERY_PACKET"
    empty = project_lab_descriptive_rows(
        [{"ticker": "XYZ", "selected_contract_symbols": "[]"}], packet
    )
    assert empty[0]["option_expression_state"] == "NO_VERIFIED_EXPRESSION"
    unresolved = project_lab_descriptive_rows(
        [{"ticker": "ABC", "selected_contract_symbol": "ABC261016C00100000"}], packet
    )
    assert unresolved[0]["option_expression_state"] == "NOT_APPLICABLE_NO_GOVERNED_FORECAST"
    invalidated = project_lab_descriptive_rows(
        [{"ticker": "XYZ", "selected_contract_symbol": "XYZ261016C00100000",
          "validation_transition": "THESIS_INVALIDATED"}], packet
    )
    assert invalidated[0]["forecast_state"] == "DESCRIPTIVE_ONLY"
    assert invalidated[0]["option_expression_state"] == "NOT_APPLICABLE_CURRENTLY_INVALIDATED"


def test_final_book_csv_json_and_interpreter_view_receive_frozen_description(tmp_path, monkeypatch):
    required = {"forecast_state", "forecast_direction", "forecast_reason",
                "forecast_target_spot", "c4_reliability_state",
                "c8_valuation_state", "c8_numeric_ev", "option_expression_state"}
    assert required <= set(FINAL_BOOK_FIELDS)
    root = tmp_path / RUN_ID
    source = root / "discovery" / f"discovery_candidates_ultimate_{RUN_ID}.csv"
    source.parent.mkdir(parents=True)
    discovery_row = _row("AAA", bar_data_asof="2099-01-01")
    with source.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(discovery_row))
        writer.writeheader()
        writer.writerow(discovery_row)
    (root / "run_meta.json").write_text(json.dumps({
        "canonical_run_id": RUN_ID, "pipeline_mode": "EOD",
        "dynamic_plan": {"last_completed_session": "2099-01-01",
                         "evidence_cutoff_utc": "2099-01-02T17:37:30Z"},
    }), encoding="utf-8")
    result = write_final_opportunity_book(
        RUN_ID, [_base_signal()], {"pipeline_mode": "EOD", "fatal_flags": []},
        tmp_path, sync_interpreter=False,
    )
    row = result["rows"][0]
    assert row["forecast_direction"] == "BULL"
    assert row["c4_reliability_state"] == "NOT_ESTIMABLE"
    assert row["c8_numeric_ev"] is None
    assert result["reconciliation"]["forecast_projected_rows"] == 1
    assert result["reconciliation"]["forecast_descriptive_rows"] == 1
    assert result["reconciliation"]["forecast_insufficient_rows"] == 0
    assert result["reconciliation"]["c8_not_valued_rows"] == 1
    assert result["reconciliation"]["forecast_population_preserved"] is True
    assert _output_files(root, RUN_ID)["ticker_forecast_descriptive"].endswith("packet.json")
    import importlib.util
    from pathlib import Path
    lab_file = Path(__file__).resolve().parents[1] / "intelligence-lab" / "intelligence_lab.py"
    spec = importlib.util.spec_from_file_location("lab_descriptive_api_test", lab_file)
    lab = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(lab)
    monkeypatch.setattr(lab, "RUNS_DIR", tmp_path)
    served = lab.app.test_client().get(f"/api/opportunity_book/{RUN_ID}?full=1")
    assert served.status_code == 200
    served_row = served.get_json()["opportunity_book"]["rows"][0]
    assert served_row["forecast_direction"] == "BULL"
    assert served_row["c8_numeric_ev"] is None
    with open(result["triage_csv_path"], newline="", encoding="utf-8") as handle:
        triage = next(csv.DictReader(handle))
    assert triage["forecast_state"] == "DESCRIPTIVE_ONLY"
    assert triage["c8_valuation_state"] == "NOT_VALUED_STATISTICAL_SUPPORT"
    interpreter_target = tmp_path / "interpreter_desc.json"
    build_structured_lab_manifest(
        ticker="AAA", pipeline_outputs=root / "intelligence_lab",
        output_file=interpreter_target,
    )
    manifest = json.loads(interpreter_target.read_text(encoding="utf-8"))
    assert manifest["sections"]["ticker_forecast"]["forecast_direction"] == "BULL"
    assert manifest["sections"]["expression_valuation_status"]["c8_valuation_state"] == "NOT_VALUED_STATISTICAL_SUPPORT"
    # Morning may revise the option context but cannot rewrite the frozen
    # pre-option Evening assessment, even if a source CSV later changes.
    with source.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(discovery_row))
        writer.writeheader()
        writer.writerow({**discovery_row, "structural_target": "120"})
    morning = write_final_opportunity_book(
        RUN_ID, [_base_signal()], {"pipeline_mode": "MORNING", "fatal_flags": []},
        tmp_path, sync_interpreter=False,
    )
    assert morning["rows"][0]["forecast_target_spot"] == 110.0
    assert morning["reconciliation"]["forecast_descriptive_rows"] == 1


def test_lab_detail_labels_the_two_states_and_never_displays_a_fabricated_c8_ev():
    from pathlib import Path
    page = (Path(__file__).resolve().parents[1] / "intelligence-lab" / "static" / "index.html").read_text(encoding="utf-8")
    assert "Ticker Forecast: Pre-option Discovery" in page
    assert "Option Expression: Separate Assessment" in page
    assert "s.forecast_state" in page
    assert "s.c8_valuation_state" in page
    assert "s.c8_numeric_ev" not in page
