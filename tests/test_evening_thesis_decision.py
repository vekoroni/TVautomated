"""Evening thesis decisions are distinct from Morning execution authority."""

import csv
from pathlib import Path
from datetime import datetime, timezone

from domain.pretrade_focus import project_evening_thesis
import morning_gate
from contracts.lab_control import (
    FINAL_BOOK_FIELDS,
    _enrich_lab_extract_rows_from_run_sources,
    opportunity_book_row,
)


def _row(**overrides):
    row = {
        "pipeline_mode": "EOD",
        "direction": "CALL",
        "signal_price": 100.0,
        "invalidation_price": 90.0,
        "invalidation_state": "AVAILABLE",
        "target_price": 110.0,
        "target_price_source": "DISCOVERY_TARGET",
        "target_state": "AVAILABLE",
        "contract_symbol": "TEST261120C00100000",
        "contract_bid": 4.0,
        "contract_ask": 4.2,
        "selected_quote_dataset_id": "quote-1",
        "monetisability_quote_snapshot_id": "quote-1",
        "selected_quote_timestamp_utc": "2026-09-18T20:00:00Z",
        "evidence_session_date": "2026-09-18",
        "monetisability_contract_symbol": "TEST261120C00100000",
        "monetisability_state": "MONETISABLE",
        "contract_repair_required": False,
        "direction_conflict_status": "NO_CONFLICT",
        "direction_resolution_call_score": 1.0,
        "direction_resolution_put_score": 0.0,
        "direction_resolution_evidence_json": '[{"family":"PRICE_FLOW","side":"CALL","direction_independent":true}]',
        "trigger_primary": "RANGE_BREAK",
        "trigger_price": 99.0,
        "trigger_price_source": "WBS_PHASE_C_CONFIRMED_BREAK",
        "wyckoff_execution_bias": "BULLISH",
        "wyckoff_entry_trigger": "Enter LONG on bullish confirmation",
        "garch_expected_move_1_5d": 5.0,
        "time_horizon": "1_5d",
        "doi_reachable_target_spot": 112.0,
    }
    row.update(overrides)
    return row


def test_evening_ready_setup_requires_multiple_reconciled_facts():
    result = project_evening_thesis(_row())
    assert result["evening_thesis_bucket"] == "EOD_ACTION_SETUP_READY"
    assert result["evening_thesis_candidate"] is True
    assert result["evening_thesis_authority"] == "ADVISORY_PENDING_MORNING_CHECK"


def test_independent_opposing_direction_is_not_no_conflict():
    result = project_evening_thesis(
        _row(direction_resolution_call_score=0.0, direction_resolution_put_score=1.0)
    )
    assert result["evening_thesis_bucket"] == "EOD_DIRECTION_EVIDENCE_REVIEW"
    assert result["evening_thesis_candidate"] is False
    assert "PUT" in result["evening_thesis_reason"]
    assert "OPPOSING_DIRECTION_EVIDENCE" in result["evening_evidence_flags"]


def test_opposing_price_flow_is_review_even_when_aggregate_scores_tie():
    result = project_evening_thesis(_row(
        direction_resolution_call_score=1.0,
        direction_resolution_put_score=1.0,
        direction_resolution_evidence_json='[{"family":"PRICE_FLOW","side":"PUT","direction_independent":true}]',
    ))
    assert result["evening_thesis_bucket"] == "EOD_DIRECTION_EVIDENCE_REVIEW"


def test_neutral_price_flow_is_missing_alignment_not_opposition():
    result = project_evening_thesis(_row(
        direction_resolution_evidence_json='[{"family":"PRICE_FLOW","side":"NEUTRAL","direction_independent":true}]',
    ))
    assert result["evening_thesis_bucket"] == "EOD_DIRECTION_EVIDENCE_REVIEW"
    assert "Aligned Vanguard price/trend proxy evidence is missing" in result["evening_thesis_reason"]
    assert "OPPOSING_DIRECTION_EVIDENCE" not in result["evening_evidence_flags"]


def test_early_trigger_and_observe_only_preserve_thesis_as_watch():
    result = project_evening_thesis(
        _row(trigger_primary="VOL_COMPRESSION", wyckoff_execution_bias="OBSERVE_ONLY")
    )
    assert result["evening_thesis_bucket"] == "EOD_TRIGGER_WATCH"
    assert result["evening_thesis_candidate"] is False
    assert result["evening_next_condition"]


def test_extreme_target_is_review_not_invalid():
    result = project_evening_thesis(
        _row(target_price=180.0, doi_reachable_target_spot="")
    )
    assert result["evening_thesis_bucket"] == "EOD_TARGET_FEASIBILITY_REVIEW"
    assert result["evening_thesis_candidate"] is False
    assert "TARGET_BEYOND_EXPECTED_MOVE_REVIEW_BAND" in result["evening_evidence_flags"]


def test_generated_three_r_target_is_a_scenario_not_a_supported_target():
    result = project_evening_thesis(_row(target_price_source="TARGET_3R"))
    assert result["evening_thesis_bucket"] == "EOD_TARGET_FEASIBILITY_REVIEW"
    assert "TARGET_GENERATED_3R_SCENARIO" in result["evening_evidence_flags"]
    assert result["evening_thesis_candidate"] is False


def test_options_handoff_preserves_generated_target_origin_on_nonselection():
    from scripts.avshunter_options_intelligence import _common_options_handoff_fields

    fields = _common_options_handoff_fields({
        "ticker": "TEST", "direction": "CALL", "structural_target_state": "TARGET_3R",
        "_signal_row": {},
    })
    assert fields["structural_target_state"] == "TARGET_3R"


def test_primary_reason_does_not_hide_secondary_evidence():
    result = project_evening_thesis(_row(
        target_price=180.0,
        trigger_primary="VOL_COMPRESSION",
        wyckoff_execution_bias="OBSERVE_ONLY",
        direction_resolution_call_score=0.0,
        direction_resolution_put_score=1.0,
    ))
    assert result["evening_thesis_bucket"] == "EOD_DIRECTION_EVIDENCE_REVIEW"
    assert "TARGET_BEYOND_EXPECTED_MOVE_REVIEW_BAND" in result["evening_evidence_flags"]
    assert "TRIGGER_NOT_PRICE_CONFIRMED" in result["evening_evidence_flags"]
    assert "WYCKOFF_OBSERVE_ONLY" in result["evening_evidence_flags"]


def test_explicit_terminal_thesis_is_invalid_but_missing_data_is_not():
    invalid = project_evening_thesis(_row(liquidity_thesis_state="THESIS_INVALIDATED"))
    missing = project_evening_thesis(_row(selected_quote_dataset_id=""))
    assert invalid["evening_thesis_bucket"] == "EOD_THESIS_INVALIDATED"
    assert missing["evening_thesis_bucket"] == "EOD_EVIDENCE_REVIEW"


def test_cross_contract_quote_cannot_be_action_setup_ready():
    result = project_evening_thesis(_row(monetisability_quote_snapshot_id="other"))
    assert result["evening_thesis_bucket"] == "EOD_EVIDENCE_REVIEW"


def test_morning_does_not_rewrite_frozen_evening_bucket():
    result = project_evening_thesis(
        _row(pipeline_mode="MORNING", evening_thesis_bucket="EOD_TRIGGER_WATCH")
    )
    assert result["evening_thesis_bucket"] == "EOD_TRIGGER_WATCH"
    assert result["evening_thesis_candidate"] is False
    copied_eod_mode = project_evening_thesis(
        _row(
            pipeline_mode="EOD", morning_data_state="AVAILABLE",
            evening_thesis_bucket="EOD_TRIGGER_WATCH",
        )
    )
    assert copied_eod_mode["evening_thesis_bucket"] == "EOD_TRIGGER_WATCH"


def test_lab_book_publishes_evening_bucket_and_exact_quote_lineage():
    sig = _row(horizon_bucket="1_5d", invalidation_spot=90.0)
    book_row = opportunity_book_row(sig, "RUN", 1)
    assert book_row["evening_thesis_bucket"] == "EOD_ACTION_SETUP_READY"
    assert book_row["monetisability_quote_snapshot_id"] == "quote-1"
    assert book_row["evidence_session_date"] == "2026-09-18"
    assert book_row["target_price_source"] == "DISCOVERY_TARGET"
    assert book_row["lab_tradeable"] is False
    assert "evening_thesis_bucket" in FINAL_BOOK_FIELDS


def test_lab_fails_to_review_if_eod_candidate_bucket_disagrees():
    sig = _row(
        horizon_bucket="1_5d", invalidation_spot=90.0,
        evening_thesis_bucket="EOD_DIRECTION_EVIDENCE_REVIEW",
    )
    book_row = opportunity_book_row(sig, "RUN", 1)
    assert book_row["evening_thesis_bucket"] == "EOD_EVIDENCE_REVIEW"
    assert book_row["evening_thesis_candidate"] is False
    assert "disagree" in book_row["evening_thesis_reason"]


def test_lab_source_bridge_recovers_quote_identity_from_eod_candidate(tmp_path):
    run_id = "20260920_203115"
    folder = tmp_path / run_id / "morning_validation"
    folder.mkdir(parents=True)
    path = folder / f"morning_candidates_{run_id}.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=[
            "ticker", "monetisability_quote_snapshot_id", "evidence_session_date",
            "liquidity_thesis_state", "target_price_source",
        ])
        writer.writeheader()
        writer.writerow({
            "ticker": "TEST", "monetisability_quote_snapshot_id": "quote-1",
            "evidence_session_date": "2026-09-18", "liquidity_thesis_state": "ACTIVE",
            "target_price_source": "TARGET_3R",
        })
    rows = [{"ticker": "TEST"}]
    _enrich_lab_extract_rows_from_run_sources(rows, tmp_path, run_id)
    assert rows[0]["monetisability_quote_snapshot_id"] == "quote-1"
    assert rows[0]["evidence_session_date"] == "2026-09-18"
    assert rows[0]["liquidity_thesis_state"] == "ACTIVE"
    assert rows[0]["target_price_source"] == "TARGET_3R"


def test_lab_ui_exposes_evening_bucket_and_next_condition():
    html = (Path(__file__).resolve().parents[1] / "intelligence-lab" / "static" / "index.html").read_text(encoding="utf-8")
    assert 'id="evening-thesis-filter-select"' in html
    assert "s.evening_thesis_bucket" in html
    assert "s.evening_next_condition" in html
    assert "targetScenarioNeedsReview(s)" in html
    assert "TARGET REVIEW" in html
    assert "s.target_price_source" in html


def test_morning_gate_retains_frozen_evening_homework():
    row = {
        "ticker": "TEST", "direction": "CALL", "instrument": "LONG_CALL",
        "contract_symbol": "O:TEST261016C00100000",
        "invalidation_spot": 95.0,
        "capital_permission": "EOD_CANDIDATE_ONLY",
        "capital_authorization_state": "EOD_CANDIDATE_ONLY",
        "eod_candidate_authorized": True,
        "authority_source_stage": "FINAL_EXECUTION",
        "execution_authorized": False,
        "final_route": "OPTIONS_GO_REVIEW",
        "monetisability_status": "COMPLETE",
        "monetisability_state": "MONETISABLE",
        "evening_thesis_bucket": "EOD_TRIGGER_WATCH",
        "evening_thesis_reason": "Trigger level not yet crossed",
    }
    live = {
        "live_price": 101.0, "live_contract_bid": 1.0,
        "live_contract_ask": 1.1, "live_contract_spread_pct": 9.52,
        "live_contract_delta": 0.45, "live_contract_iv": 0.32,
        "live_contract_provider_updated": datetime.now(timezone.utc).isoformat(),
    }
    morning = morning_gate.run_gate(
        row, live, current_regime="BULLISH", spread_threshold=25.0,
        bond_state={}, macro_state={"regime_state": "BULLISH", "macro_filter": "GO"},
    )
    assert morning["evening_thesis_bucket"] == "EOD_TRIGGER_WATCH"
    assert morning["evening_thesis_reason"] == "Trigger level not yet crossed"
