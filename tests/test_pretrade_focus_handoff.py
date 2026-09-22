"""The EOD focus lane is review order, never Morning or execution authority."""

import csv

import pytest

from contracts.lab_control import (
    _enrich_lab_extract_rows_from_run_sources,
    opportunity_book_row,
)
from domain.pretrade_focus import FOCUS_PRIMARY, project_pretrade_focus
from eod_candidate_engine import _candidate_permission_fields, _eod_candidate_status
from scripts.replay_pretrade_focus import replay


def _row(**updates):
    row = {
        "ticker": "TEST",
        "direction": "CALL",
        "signal_price": 100,
        "invalidation_state": "AVAILABLE",
        "invalidation_spot": 95,
        "target_state": "AVAILABLE",
        "target_price": 110,
        "contract_symbol": "TEST261120C00100000",
        "contract_bid": 4.5,
        "contract_ask": 4.7,
        "contract_dte": 60,
        "selected_quote_timestamp_utc": "2026-09-18T20:00:00Z",
        "selected_quote_dataset_id": "quote-dataset-1",
        "monetisability_quote_snapshot_id": "quote-dataset-1",
        "monetisability_contract_symbol": "TEST261120C00100000",
        "evidence_session_date": "2026-09-18",
        "liquidity_state": "EOD_QUOTE_PENDING_MORNING_REQUOTE",
        "contract_oi": 0,
        "contract_delta": 0.8,
        "monetisability_state": "MONETISABLE",
        "contract_repair_required": "FALSE",
        "contract_repair_status": "CONTRACT_OK",
        "trigger_go_eligible": "TRUE",
        "direction_conflict_status": "NO_CONFLICT",
        "candidate_status": "REPAIR_AT_OPEN",
        "capital_permission": "EOD_CANDIDATE_ONLY",
    }
    row.update(updates)
    return row


def test_completed_eod_quote_supports_focus_without_entry_authority():
    source = _row()
    result = project_pretrade_focus(source)
    assert result["pretrade_thesis_state"] == "READY_FOR_MORNING_THESIS_CHECK"
    assert result["pretrade_contract_evidence_state"] == "COMPLETED_SESSION_QUOTE_OBSERVED"
    assert result["pretrade_entry_quote_state"] == "NOT_EVALUATED_AT_EOD"
    assert result["pretrade_focus_lane"] == FOCUS_PRIMARY
    assert result["pretrade_focus_candidate"] is True
    assert result["pretrade_focus_authority"] == "ADVISORY_ONLY"
    assert source["candidate_status"] == "REPAIR_AT_OPEN"
    assert source["capital_permission"] == "EOD_CANDIDATE_ONLY"


def test_thesis_gaps_are_independent_of_contract_quote():
    cases = (
        ({"direction": "STRANGLE"}, "DIRECTION_REVIEW"),
        ({"invalidation_state": "MISSING", "invalidation_spot": None}, "INVALIDATION_REVIEW"),
        ({"target_state": "UNRESOLVED", "target_price": None}, "TARGET_REVIEW"),
        ({"target_price": 90}, "THESIS_GEOMETRY_REVIEW"),
    )
    for changes, expected in cases:
        result = project_pretrade_focus(_row(**changes))
        assert result["pretrade_thesis_state"] == expected
        assert result["pretrade_focus_lane"] == "THESIS_EVIDENCE_REVIEW"


def test_missing_or_bad_exact_quote_does_not_become_a_focus_contract():
    for changes in (
        {"contract_symbol": "", "recommended_contract": ""},
        {"selected_quote_timestamp_utc": ""},
        {"selected_quote_dataset_id": ""},
        {"contract_bid": 0},
        {"contract_bid": 5, "contract_ask": 4},
    ):
        result = project_pretrade_focus(_row(**changes))
        assert result["pretrade_focus_lane"] == "CONTRACT_EVIDENCE_REVIEW"
        assert result["pretrade_focus_candidate"] is False


def test_cross_contract_or_session_mismatch_is_review_only():
    for changes in (
        {"monetisability_contract_symbol": "OTHER261120C00100000"},
        {"monetisability_quote_snapshot_id": "different-dataset"},
        {"selected_quote_timestamp_utc": "2026-09-17T20:00:00Z"},
    ):
        result = project_pretrade_focus(_row(**changes))
        assert result["pretrade_contract_evidence_state"] == "CONTRACT_EVIDENCE_CONFLICT_REVIEW"
        assert result["pretrade_focus_candidate"] is False


def test_eod_quote_pending_does_not_fabricate_contract_repair_or_entry_authority():
    row = _row(contract_repair_required="FALSE", capital_permission="EOD_CANDIDATE_ONLY")
    status, reason = _eod_candidate_status(row, "A")
    assert (status, reason) == ("EOD_TRIGGER_READY", "TRIGGER_GO_ELIGIBLE")
    permission = _candidate_permission_fields(row, "EOD_THESIS_READY_REPAIR_AT_OPEN")
    assert permission["eod_candidate_permission"] == "MORNING_VALIDATION_REQUIRED"
    assert permission["execution_authorized"] is False


def test_developing_and_conflicted_opportunities_remain_visible():
    assert project_pretrade_focus(_row(contract_repair_required="TRUE"))[
        "pretrade_focus_lane"
    ] == "FOCUS_CONTRACT_REPAIR"
    assert project_pretrade_focus(_row(contract_repair_required=""))[
        "pretrade_focus_lane"
    ] == "CONTRACT_REPAIR_EVIDENCE_REVIEW"
    assert project_pretrade_focus(_row(direction_conflict_status="MITIGATED_REQUIRES_CONFIRMATION"))[
        "pretrade_focus_lane"
    ] == "FOCUS_DIRECTION_CONFIRMATION"
    assert project_pretrade_focus(_row(direction_conflict_status="NOT_EVALUATED"))[
        "pretrade_focus_lane"
    ] == "FOCUS_DIRECTION_EVIDENCE_REVIEW"
    assert project_pretrade_focus(_row(trigger_go_eligible="FALSE"))[
        "pretrade_focus_lane"
    ] == "FOCUS_TRIGGER_DEVELOPING"
    assert project_pretrade_focus(_row(monetisability_state="LIMITED"))[
        "pretrade_focus_lane"
    ] == "FOCUS_LIMITED_MONETISATION"
    assert project_pretrade_focus(_row(monetisability_state="NOT_MONETISABLE"))[
        "pretrade_focus_lane"
    ] == "WATCH_CONTRACT_MONETISATION"


def test_lab_projection_carries_focus_evidence_without_changing_authority():
    source = _row()
    source.update(project_pretrade_focus(source))
    source.update({"run_id": "20260920_203115", "final_action": "MANUAL_REVIEW"})
    result = opportunity_book_row(source, "20260920_203115", 1)
    assert result["pretrade_focus_lane"] == FOCUS_PRIMARY
    assert result["pretrade_focus_authority"] == "ADVISORY_ONLY"
    assert result["pretrade_entry_quote_state"] == "NOT_EVALUATED_AT_EOD"
    assert result["final_action"] == "MANUAL_REVIEW"


def test_lab_source_bridge_reads_focus_only_from_eod_candidate_manifest(tmp_path):
    run_id = "20260920_203115"
    morning = tmp_path / run_id / "morning_validation"
    morning.mkdir(parents=True)
    path = morning / f"morning_candidates_{run_id}.csv"
    projected = project_pretrade_focus(_row())
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["ticker", *projected])
        writer.writeheader()
        writer.writerow({"ticker": "TEST", **projected})
    rows = [{"ticker": "TEST", "trade_idea_id": f"{run_id}:TEST:CALL:NA:NA"}]
    _enrich_lab_extract_rows_from_run_sources(rows, tmp_path, run_id)
    assert rows[0]["pretrade_focus_lane"] == FOCUS_PRIMARY
    assert rows[0]["pretrade_entry_quote_state"] == "NOT_EVALUATED_AT_EOD"
    assert rows[0]["pretrade_focus_authority"] == "ADVISORY_ONLY"


def test_frozen_run_replay_writes_only_primary_without_overwriting_source(tmp_path):
    source = tmp_path / "morning_candidates_TEST.csv"
    destination = tmp_path / "pretrade_focus_TEST.csv"
    rows = [_row(ticker="GOOD"), _row(ticker="REPAIR", contract_repair_required="TRUE")]
    with source.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0])
        writer.writeheader()
        writer.writerows(rows)
    original = source.read_bytes()
    result = replay(source, destination)
    with destination.open("r", encoding="utf-8", newline="") as handle:
        focused = list(csv.DictReader(handle))
    assert result["total_rows"] == 2
    assert result["primary_focus"] == 1
    assert result["contract_repair_watch"] == 1
    assert [row["ticker"] for row in focused] == ["GOOD"]
    assert source.read_bytes() == original
    with pytest.raises(FileExistsError):
        replay(source, destination)
