from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import morning_gate


def _row(**overrides):
    row = {
        "ticker": "SAFE",
        "direction": "CALL",
        "instrument": "LONG_CALL",
        "contract_symbol": "O:SAFE261016C00100000",
        "macro_regime": "BULLISH",
        "invalidation_spot": 95.0,
        "rr_premium_expected": 1.5,
        "capital_permission": "EOD_CANDIDATE_ONLY",
        "capital_authorization_state": "EOD_CANDIDATE_ONLY",
        "eod_candidate_authorized": True,
        "authority_source_stage": "FINAL_EXECUTION",
        "execution_authorized": False,
        "final_route": "OPTIONS_GO_REVIEW",
        "ev3_authority_active": False,
        "monetisability_status": "COMPLETE",
        "monetisability_state": "MONETISABLE",
        "monetisability_reason": "TEST_TARGET_CLEARS_BREAKEVEN",
    }
    row.update(overrides)
    return row


def _live():
    return {
        "live_price": 101.0,
        "live_contract_bid": 1.00,
        "live_contract_ask": 1.10,
        "live_contract_spread_pct": 9.52,
        "live_contract_delta": 0.45,
        "live_contract_iv": 0.32,
    }


def _macro(filter_value: str = "GO"):
    return {
        "regime_state": "BULLISH",
        "macro_filter": filter_value,
        "dir_bias": "NEUTRAL",
        "sector_lead": ["XLE", "XLV"],
        "sector_avoid": ["XLK", "XLF"],
        "size_multiplier": 0.7,
        "macro_loaded": True,
    }


def _gate(row, macro=None):
    return morning_gate.run_gate(
        row,
        _live(),
        current_regime="BULLISH",
        spread_threshold=25.0,
        bond_state={},
        macro_state=macro or _macro(),
    )


def test_go_is_validation_only_and_never_live_authority() -> None:
    gated = _gate(_row())

    assert gated["verdict"] == "GO"
    assert gated["morning_execution_permission"] == "GO_LIMIT"
    assert gated["morning_execution_route"] == "GO_LIMIT"
    assert gated["execution_permission"] == "HUMAN_APPROVAL_REQUIRED"
    assert gated["final_capital_permission"] == "HUMAN_APPROVAL_REQUIRED"
    assert gated["execution_authorized"] is False


def test_legacy_nonfinal_source_cannot_reach_morning_go() -> None:
    gated = _gate(_row(authority_source_stage="LEGACY_NONFINAL"))

    assert gated["verdict"] == "BLOCK"
    assert gated["morning_execution_permission"] == "NOT_ELIGIBLE"
    assert gated["check_upstream_authority_reason"].startswith(
        "UNSAFE_AUTHORITY_SOURCE"
    )
    assert gated["execution_authorized"] is False


def test_not_authorized_or_watch_only_can_never_upgrade() -> None:
    denied = _gate(
        _row(
            capital_permission="NO",
            capital_authorization_state="NOT_AUTHORIZED",
            eod_candidate_authorized=False,
        )
    )
    watch = _gate(
        _row(
            capital_permission="WATCH_ONLY",
            capital_authorization_state="NOT_AUTHORIZED",
            eod_candidate_authorized=False,
        )
    )

    for gated in (denied, watch):
        assert gated["verdict"] == "BLOCK"
        assert gated["execution_permission"] == "BLOCKED"
        assert gated["morning_execution_permission"] == "NOT_ELIGIBLE"
        assert gated["execution_authorized"] is False


def test_macro_no_go_is_advisory_and_cannot_deny_trade_authority() -> None:
    gated = _gate(_row(), macro=_macro("NO_GO"))

    assert gated["check_macro_change_pass"] == "TRUE"
    assert gated["check_macro_permission_pass"] == "TRUE"
    assert gated["macro_capital_authority"] == "ADVISORY_ONLY"
    assert gated["macro_filter_advisory"] == "NO_GO"
    assert gated["verdict"] == "GO"
    assert gated["morning_execution_permission"] == "GO_LIMIT"


def test_missing_evening_regime_is_diagnostic_not_a_trade_gate() -> None:
    gated = _gate(_row(macro_regime=""))

    assert gated["check_macro_change_pass"] == "FALSE"
    assert gated["verdict"] == "GO"
    assert gated["morning_execution_permission"] == "GO_LIMIT"
    assert gated["execution_authorized"] is False


def test_macro_sector_rotation_is_direction_aware_and_advisory() -> None:
    call_leader = _gate(_row(direction="CALL", sector_etf="XLE"))
    put_leader = _gate(_row(direction="PUT", sector_etf="XLE", invalidation_spot=105.0))
    call_laggard = _gate(_row(direction="CALL", sector_etf="XLK"))
    put_laggard = _gate(_row(direction="PUT", sector_etf="XLK", invalidation_spot=105.0))

    assert call_leader["macro_direction_alignment"] == "TAILWIND"
    assert put_leader["macro_direction_alignment"] == "HEADWIND"
    assert call_laggard["macro_direction_alignment"] == "HEADWIND"
    assert put_laggard["macro_direction_alignment"] == "TAILWIND"
    assert {row["verdict"] for row in (call_leader, put_leader, call_laggard, put_laggard)} == {"GO"}


def test_bond_macro_is_advisory_and_cannot_deny_trade_authority() -> None:
    gated = morning_gate.run_gate(
        _row(),
        _live(),
        current_regime="BULLISH",
        spread_threshold=25.0,
        bond_state={
            "bond_trade_go": False,
            "bond_macro_score": 20,
            "bond_macro_flag": "BOND_MACRO_CAUTION",
        },
        macro_state=_macro(),
    )

    assert gated["check_bond_macro_pass"] == "FALSE"
    assert gated["verdict"] == "GO"
    assert gated["morning_execution_permission"] == "GO_LIMIT"


def test_legacy_non_positive_rr_has_no_capital_authority() -> None:
    gated = _gate(_row(rr_premium_expected=0.0))

    assert gated["check_premium_economics_pass"] == "TRUE"
    assert gated["verdict"] == "GO"


def test_scenario_not_monetisable_is_advisory_when_execution_quote_is_viable() -> None:
    gated = _gate(_row(monetisability_state="NOT_MONETISABLE"))

    assert gated["check_premium_economics_pass"] == "TRUE"
    assert gated["verdict"] == "GO"
    assert gated["morning_execution_permission"] == "GO_LIMIT"


def test_legacy_ev_status_is_advisory_when_premium_rr_is_positive() -> None:
    gated = _gate(_row(ev_status="AVOID", rr_premium_expected=1.5))

    assert gated["check_premium_economics_pass"] == "TRUE"
    assert gated["verdict"] == "GO"
    assert gated["morning_execution_permission"] == "GO_LIMIT"


def test_ev3_negative_and_positive_states_are_both_advisory() -> None:
    negative = _gate(
        _row(
            ev3_authority_active=True,
            ev3_authority_state="NEGATIVE",
            ev3_ev_eligible=False,
        )
    )
    positive = _gate(
        _row(
            ev3_authority_active=True,
            ev3_authority_state="POSITIVE",
            ev3_ev_eligible=True,
        )
    )

    assert negative["verdict"] == "GO"
    assert negative["morning_execution_permission"] == "GO_LIMIT"
    assert negative["ev3_authority_requested"] is True
    assert negative["ev3_authority_active"] is False
    assert negative["ev3_capital_authority"] == "ADVISORY_ONLY"
    assert positive["verdict"] == "GO"
    assert positive["morning_execution_permission"] == "GO_LIMIT"


def test_options_blocked_route_is_absorbing() -> None:
    gated = _gate(_row(final_route="OPTIONS_BLOCKED"))

    assert gated["verdict"] == "BLOCK"
    assert "UPSTREAM_OPTIONS_ROUTE_BLOCKED" in gated["morning_unlock_condition"]


def test_zero_score_comparisons_are_not_integrity_pass(tmp_path) -> None:
    report = morning_gate._normalise_score_integrity(
        tmp_path,
        "TEST",
        {
            "run_id": "TEST",
            "lab_source": "NOT_FOUND",
            "compared": 0,
            "integrity_pass": True,
        },
    )

    assert report["integrity_pass"] is False
    assert report["integrity_status"] == "NOT_EVALUATED"
    assert (tmp_path / "score_integrity_TEST.json").exists()


def test_governed_spread_policy_separates_execute_review_and_block() -> None:
    executable_live = _live()
    executable_live["live_contract_spread_pct"] = 18.0
    executable = morning_gate.run_gate(
        _row(), executable_live, "BULLISH", 25.0, bond_state={}, macro_state=_macro()
    )

    review_live = _live()
    review_live["live_contract_spread_pct"] = 20.0
    review = morning_gate.run_gate(
        _row(), review_live, "BULLISH", 25.0, bond_state={}, macro_state=_macro()
    )

    blocked_live = _live()
    blocked_live["live_contract_spread_pct"] = 25.1
    blocked = morning_gate.run_gate(
        _row(), blocked_live, "BULLISH", 30.0, bond_state={}, macro_state=_macro()
    )

    assert executable["verdict"] == "GO"
    assert executable["contract_spread_policy_state"] == "EXECUTABLE_SPREAD"
    assert review["verdict"] == "FLAG"
    assert review["morning_execution_permission"] == "MANUAL_LIQUIDITY_REVIEW"
    assert review["morning_execution_route"] == "MANUAL_LIQUIDITY_REVIEW"
    assert review["morning_entry_action"] == "NO_TRADE_UNTIL_LIQUIDITY_APPROVED"
    assert blocked["verdict"] == "BLOCK"
    assert blocked["morning_execution_permission"] == "NO_GO_LIQUIDITY"
    assert blocked["contract_spread_review_max_pct"] == 25.0


def test_non_long_single_strategy_is_research_only() -> None:
    live = _live()
    live.update(
        selected_structure="BULL_CALL_DEBIT",
        selected_contract_symbols=(
            '["SAFE260918C00100000", "SAFE260918C00110000"]'
        ),
    )
    gated = morning_gate.run_gate(
        _row(options_strategy="DEBIT_SPREAD_CALL"),
        live,
        "BULLISH",
        25.0,
        bond_state={},
        macro_state=_macro(),
    )

    assert gated["verdict"] == "BLOCK"
    assert gated["morning_execution_permission"] == "RESEARCH_ONLY"
    assert gated["morning_execution_route"] == "OPTIONS_RESEARCH_ONLY"
    assert gated["production_strategy_eligible"] == "FALSE"
    assert "UNSUPPORTED_PRODUCTION_STRUCTURE" in gated["production_strategy_reason"]


def test_morning_handoff_score_integrity_compares_completed_rows() -> None:
    report = morning_gate._check_morning_handoff_score_integrity(
        "TEST",
        [
            {"ticker": "AAA", "scs_score": "71.5"},
            {"ticker": "BBB", "scs_score": "62"},
        ],
        [
            {"ticker": "AAA", "scs_score": 71.5},
            {"ticker": "BBB", "scs_score": 62.0},
        ],
    )

    assert report["compared"] == 2
    assert report["coverage_complete"] is True
    assert report["mismatches"] == 0
    assert report["integrity_pass"] is True
    assert report["lab_score_integrity_status"] == "PENDING_POST_LAB_MATERIALISATION"


def test_morning_handoff_score_integrity_fails_when_a_ticker_disappears() -> None:
    report = morning_gate._check_morning_handoff_score_integrity(
        "TEST",
        [
            {"ticker": "AAA", "scs_score": 71.5},
            {"ticker": "BBB", "scs_score": 62.0},
        ],
        [{"ticker": "AAA", "scs_score": 71.5}],
    )

    assert report["compared"] == 1
    assert report["coverage_complete"] is False
    assert report["missing_from_output"] == ["BBB"]
    assert report["integrity_pass"] is False


def test_post_lab_score_integrity_reads_preserved_source_payload(tmp_path) -> None:
    import csv
    import json

    lab_path = tmp_path / "final_opportunity_book_TEST.csv"
    with lab_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["ticker", "composite_score", "source_payload_json"])
        writer.writeheader()
        writer.writerow({
            "ticker": "AAA",
            "composite_score": 44.0,
            "source_payload_json": json.dumps({"ticker": "AAA", "scs_score": 71.5}),
        })
        writer.writerow({
            "ticker": "BBB",
            "composite_score": 91.0,
            "source_payload_json": json.dumps({"ticker": "BBB", "scs_score": 62.0}),
        })

    report = morning_gate._check_post_lab_score_integrity(
        "TEST",
        [
            {"ticker": "AAA", "scs_score": 71.5},
            {"ticker": "BBB", "scs_score": 62.0},
        ],
        lab_path,
    )

    assert report["compared"] == 2
    assert report["coverage_complete"] is True
    assert report["mismatches"] == 0
    assert report["integrity_pass"] is True
    assert report["score_field"] == "scs_score"


def test_morning_closure_updates_manifest_without_live_authority(tmp_path) -> None:
    manifest_path = tmp_path / "final_run_manifest.json"
    manifest_path.write_text(
        '{"phase_status":{"morning_validation":"PENDING"},'
        '"stale_flags":["EOD_MORNING_VALIDATION_PENDING"]}',
        encoding="utf-8",
    )
    summary = {
        "validated_at_utc": "2026-08-21T12:00:00Z",
        "input_candidates": 10,
        "go_count": 2,
        "flag_count": 3,
        "block_count": 5,
    }
    morning_gate._close_final_run_manifest(
        tmp_path,
        "TEST",
        summary,
        {"integrity_status": "NOT_EVALUATED"},
    )

    import json

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["phase_status"]["morning_validation"] == "PASS"
    assert manifest["run_tradeable"] is False
    assert manifest["run_execution_permission"] == "HUMAN_APPROVAL_REQUIRED"
    assert "EOD_MORNING_VALIDATION_PENDING" not in manifest["stale_flags"]
    assert "SCORE_INTEGRITY_NOT_EVALUATED" in manifest["stale_flags"]


def test_passing_morning_integrity_clears_prior_not_evaluated_flag(tmp_path) -> None:
    manifest_path = tmp_path / "final_run_manifest.json"
    manifest_path.write_text(
        '{"stale_flags":["SCORE_INTEGRITY_NOT_EVALUATED"]}',
        encoding="utf-8",
    )
    morning_gate._close_final_run_manifest(
        tmp_path,
        "TEST",
        {
            "validated_at_utc": "2026-08-25T08:00:00Z",
            "input_candidates": 2,
            "go_count": 1,
            "flag_count": 0,
            "block_count": 1,
        },
        {
            "integrity_status": "PASS",
            "integrity_scope": "MORNING_CANDIDATES_TO_VALIDATED_HANDOFF",
            "compared": 2,
            "lab_score_integrity_status": "PENDING_POST_LAB_MATERIALISATION",
        },
    )

    import json

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert "SCORE_INTEGRITY_NOT_EVALUATED" not in manifest["stale_flags"]
    assert manifest["score_integrity_compared"] == 2
    assert manifest["lab_score_integrity_status"] == "PENDING_POST_LAB_MATERIALISATION"
