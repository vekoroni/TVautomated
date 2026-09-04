from pathlib import Path
import sys
import tempfile

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from eod_candidate_engine import build_candidate_manifest  # noqa: E402


def _row(ticker: str, *, route: str, vetoes: str = "") -> dict:
    return {
        "ticker": ticker,
        "direction": "CALL",
        "options_direction": "CALL",
        "signal_price": 100.0,
        "target_price": 110.0,
        "sector": "Health Care",
        "eil_v3_verdict": "EXECUTE",
        "effective_execution_verdict": "MORNING_VALIDATION_REQUIRED",
        "capital_authorization_state": "EOD_CANDIDATE_ONLY",
        "capital_permission": "EOD_CANDIDATE_ONLY",
        "eod_candidate_authorized": True,
        "execution_authorized": False,
        "ev3_authority_active": False,
        "ev3_authority_state": "NEGATIVE",
        "ev3_ev_eligible": False,
        "signal_authority_reason": "CURRENT_EDGE_EOD_CANDIDATE",
        "pse_execution_mode": "CURRENT_EDGE_REVIEW",
        "sizing_policy": "PSE_IGNORED_MANUAL_SIZING",
        "trigger_quality": "STRONG",
        "trigger_go_eligible": "TRUE",
        "options_score": 82.0,
        "rr_underlying": 2.1,
        "rr_options": 3.0,
        "composite": 72.0,
        "ev2_ev_structural": 0.15,
        "sb_conv_score": 3.0,
        "sb_campaign": "CORE_CAMPAIGN",
        "recommended_contract": f"{ticker}260619C00100000",
        "contract_strike": 100.0,
        "contract_expiry": "2026-06-19",
        "contract_dte": 30,
        "contract_premium": 2.0,
        "contract_delta": 0.42,
        "contract_oi": 900,
        "contract_volume": 150,
        "contract_spread_pct": 5.0 if not vetoes else 30.0,
        "execution_permission": "NONE_OPTIONS_RESEARCH_ONLY",
        "final_route": route,
        "options_research_score": 84.0,
        "hard_vetoes": vetoes,
        "missing_data": "",
        "breakeven_feasibility": 1.7,
        "estimated_R": 3.0,
        "theta_decay_expected": 12.0,
        "runway_to_wall_pct": 8.0,
    }


def test_eod_manifest_preserves_options_research_contract_and_blocks_vetoes() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        eil_path = root / "execution_v3_5_TEST.csv"
        output_path = root / "morning_candidates_TEST.csv"
        pd.DataFrame(
            [
                _row("GOOD", route="OPTIONS_GO_REVIEW"),
                _row("BAD", route="OPTIONS_BLOCKED", vetoes="SPREAD_GT_15PCT"),
            ]
        ).to_csv(eil_path, index=False)

        out = build_candidate_manifest(
            eil_path=eil_path,
            output_path=output_path,
            run_id="TEST",
            max_candidates=10,
        )
        audit = pd.read_csv(root / "eod_dropoff_audit_TEST.csv")

    by_ticker = {str(row["ticker"]): row for row in out.to_dict("records")}
    audit_by_ticker = {str(row["ticker"]): row for row in audit.to_dict("records")}

    assert by_ticker["GOOD"]["final_route"] == "OPTIONS_GO_REVIEW"
    assert by_ticker["GOOD"]["options_research_permission"] == "NONE_OPTIONS_RESEARCH_ONLY"
    assert by_ticker["GOOD"]["eod_candidate_status"] == "EOD_TRIGGER_READY"
    assert by_ticker["GOOD"]["authority_source_stage"] == "FINAL_EXECUTION"
    assert bool(by_ticker["GOOD"]["eod_candidate_authorized"]) is True
    assert by_ticker["GOOD"]["ev3_authority_state"] == "NEGATIVE"

    assert "BAD" not in by_ticker
    assert audit_by_ticker["BAD"]["final_route"] == "OPTIONS_BLOCKED"
    assert audit_by_ticker["BAD"]["hard_vetoes"] == "SPREAD_GT_15PCT"
    assert audit_by_ticker["BAD"]["eod_candidate_status"] == "EOD_BLOCK"
    assert "OPTIONS_RESEARCH_BLOCKED" in audit_by_ticker["BAD"]["eod_dropoff_reason"]


def test_eod_manifest_preserves_a_valid_thesis_when_liquidity_is_still_developing() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        eil_path = root / "execution_v3_5_TEST.csv"
        output_path = root / "morning_candidates_TEST.csv"
        pending = _row("PENDING", route="OPTIONS_GO_REVIEW")
        pending.update({
            "thesis_id": "PENDING:CALL:2026-08-29",
            "thesis_state": "ACTIVE",
            "liquidity_state": "LIQUIDITY_PENDING",
            "maturation_score_1d": 41.0,
            "maturation_score_2d": 58.0,
            "maturation_score_3d": 67.0,
            "maturation_score_is_probability": False,
            "maturation_execution_authority": False,
            "remaining_runway_pct": 72.0,
            "contract_selection_reason": "BEST_MONITORABLE_LONG_OPTION_CONTRACT",
        })
        pd.DataFrame([pending]).to_csv(eil_path, index=False)

        out = build_candidate_manifest(
            eil_path=eil_path,
            output_path=output_path,
            run_id="TEST",
            max_candidates=10,
        )

    row = out.iloc[0]
    assert row["eod_candidate_status"] == "EOD_THESIS_READY_REPAIR_AT_OPEN"
    assert row["liquidity_state"] == "LIQUIDITY_PENDING"
    assert row["thesis_id"] == "PENDING:CALL:2026-08-29"
    assert float(row["maturation_score_2d"]) == 58.0
    assert bool(row["maturation_execution_authority"]) is False


def test_trigger_authority_overlay_drives_status_and_preserves_exact_categories() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        execution_path = root / "execution_v3_5_TEST.csv"
        trigger_path = root / "eil_enriched_TEST.csv"
        output_path = root / "morning_candidates_TEST.csv"
        execution_row = _row("TRIG", route="OPTIONS_GO_REVIEW")
        execution_row.update({
            "trigger_primary": "",
            "trigger_quality": "",
            "trigger_codes": "",
            "trigger_go_eligible": "",
            "eil_v3_verdict": "ARMED",
        })
        pd.DataFrame([execution_row]).to_csv(execution_path, index=False)
        pd.DataFrame([{
            "ticker": "TRIG",
            "trigger_primary": "VOL_COMPRESSION",
            "trigger_quality": "STRONG",
            "trigger_codes": "VOL_COMPRESSION|RANGE_BREAK",
            "trigger_go_eligible": True,
            "trigger_count": 2,
            "trigger_score": 4.0,
            "trigger_state": "TRIGGER_EARLY_PROBE",
            "trigger_freshness_state": "UNKNOWN",
        }]).to_csv(trigger_path, index=False)

        out = build_candidate_manifest(
            eil_path=execution_path,
            trigger_overlay_path=trigger_path,
            output_path=output_path,
            run_id="TEST",
            max_candidates=10,
        )

    row = out.iloc[0]
    assert row["trigger_primary"] == "VOL_COMPRESSION"
    assert row["trigger_quality"] == "STRONG"
    assert row["trigger_codes"] == "VOL_COMPRESSION|RANGE_BREAK"
    assert row["eod_candidate_status"] == "EOD_TRIGGER_READY"


def test_eod_monetisability_uses_completed_session_exact_contract() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        execution_path = root / "execution_v3_5_TEST.csv"
        output_path = root / "morning_candidates_TEST.csv"
        row = _row("MON", route="OPTIONS_GO_REVIEW")
        row.update({
            "canonical_direction": "CALL",
            "final_direction": "CALL",
            "target_spot": 115.0,
            "structural_target": 115.0,
            "contract_ask": 5.0,
            "contract_strike": 100.0,
            "strike": 100.0,
            "contract_quote_timestamp_utc": "2026-08-28T20:00:00Z",
            "selected_quote_dataset_id": "quote-dataset-1",
        })
        pd.DataFrame([row]).to_csv(execution_path, index=False)

        out = build_candidate_manifest(
            eil_path=execution_path,
            output_path=output_path,
            run_id="TEST",
            max_candidates=10,
        )

    result = out.iloc[0]
    assert result["monetisability_evaluation_phase"] == "EOD_CLOSE"
    assert result["monetisability_refresh_status"] == "PENDING_MORNING_REFRESH"
    assert result["monetisability_status"] == "COMPLETE"
    assert result["monetisability_state"] == "MONETISABLE"
    assert float(result["monetisability_target_profit_pct"]) == 200.0


if __name__ == "__main__":
    test_eod_manifest_preserves_options_research_contract_and_blocks_vetoes()
    print("eod options research handoff tests passed")
