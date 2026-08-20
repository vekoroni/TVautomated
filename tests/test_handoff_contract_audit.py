from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from handoff_contract_audit import audit_run  # noqa: E402


def test_vanguard_flattened_legacy_note_alias_is_accepted() -> None:
    with tempfile.TemporaryDirectory() as td:
        runs_dir = Path(td)
        run_id = "R1"
        run_dir = runs_dir / run_id
        (run_dir / "vanguard").mkdir(parents=True)
        (run_dir / "options").mkdir()
        (run_dir / "superbrain").mkdir()
        (run_dir / "execution").mkdir()
        (run_dir / "morning_validation").mkdir()

        pd.DataFrame([{
            "ticker": "AAPL",
            "verdict": "ACTUARIAL_SUPPORT",
            "final_recommendation": "CALL_EDGE_STRONG_5D",
            "layer2__edge_quality": "STRONG",
            "layer2__probability_verdict": "STRONG_EDGE",
            "layer2__probability_edge": 0.11,
            "edge_direction": "CALL",
            "no_edge_reason": "",
            "layer2__legacy_no_edge_reason": "Legacy EV gate note retained for audit",
        }]).to_csv(run_dir / "vanguard" / "vanguard_signals.csv", index=False)

        pd.DataFrame([{
            "ticker": "AAPL", "option_direction": "CALL", "recommended_contract": "AAPL260619C00100000",
            "contract_strike": 100, "contract_expiry": "2026-06-19", "contract_dte": 39,
            "contract_premium": 1.2, "contract_spread_pct": 5, "contract_oi": 500,
            "contract_volume": 100, "contract_delta": 0.35, "options_score": 75,
            "rr_options": 2.0, "option_gain_at_target": 3.0,
            "execution_permission": "NONE_OPTIONS_RESEARCH_ONLY", "final_route": "OPTIONS_GO_REVIEW",
            "options_research_score": 82, "hard_vetoes": "",
        }]).to_csv(run_dir / "options" / f"options_intelligence_{run_id}.csv", index=False)

        pd.DataFrame([{
            "ticker": "AAPL", "eil_v3_verdict": "PASS", "pse_execution_mode": "STRUCTURAL_WATCH",
            "trigger_quality": "STRONG", "option_direction": "CALL", "recommended_contract": "AAPL260619C00100000",
            "contract_spread_pct": 5, "contract_oi": 500, "catalyst_truth_score": 0.0, "catalyst_type": "STRUCTURAL",
            "execution_permission": "NONE_OPTIONS_RESEARCH_ONLY", "final_route": "OPTIONS_GO_REVIEW",
            "options_research_score": 82, "hard_vetoes": "",
        }]).to_csv(run_dir / "superbrain" / f"eil_enriched_{run_id}.csv", index=False)

        pd.DataFrame([{
            "ticker": "AAPL", "effective_execution_verdict": "MORNING_VALIDATION_REQUIRED",
            "capital_permission": "EOD_CANDIDATE_ONLY", "eod_candidate_permission": "MORNING_VALIDATION_REQUIRED",
            "candidate_size": 0.0, "sizing_policy": "POSITION_SIZING_RETIRED_ADVISORY_ONLY",
            "execution_authority_reason": "STRUCTURAL_MATCH_EOD_CANDIDATE",
            "execution_permission": "NONE_OPTIONS_RESEARCH_ONLY", "final_route": "OPTIONS_GO_REVIEW",
            "options_research_score": 82, "hard_vetoes": "",
        }]).to_csv(run_dir / "execution" / f"execution_v3_5_{run_id}.csv", index=False)

        pd.DataFrame([{
            "ticker": "AAPL", "eod_candidate_status": "EOD_EXECUTE_CANDIDATE",
            "eod_candidate_reason": "SURVIVED", "structural_tier": "A",
            "eod_candidate_permission": "MORNING_VALIDATION_REQUIRED",
            "candidate_size": 0.0, "sizing_policy": "POSITION_SIZING_RETIRED_ADVISORY_ONLY",
            "monetisation_fit_score": 88, "primary_direction": "CALL",
            "contract_quality_score": 80, "contract_spread_pct_eod": 5,
            "trigger_quality": "STRONG", "catalyst_truth_score": 0.0, "catalyst_type": "STRUCTURAL",
            "final_route": "OPTIONS_GO_REVIEW", "hard_vetoes": "",
        }]).to_csv(run_dir / "morning_validation" / f"morning_candidates_{run_id}.csv", index=False)

        pd.DataFrame([{
            "ticker": "AAPL", "shadow_opportunity_score": 0, "shadow_opportunity_label": "",
        }]).to_csv(run_dir / "morning_validation" / f"missed_opportunity_shadow_book_{run_id}.csv", index=False)

        result = audit_run(run_id, runs_dir=runs_dir)

    assert result["fail_count"] == 0
    assert not [
        item for item in result["outstanding_fixes"]
        if item["stage"] == "vanguard" and item["field_contract"] == "legacy_no_edge_note"
    ]
    assert not [
        item for item in result["outstanding_fixes"]
        if item["stage"] == "morning_validation" and item["status"] == "MISSING_ARTIFACT"
    ]


def test_options_blocked_cannot_be_promoted_to_eod_candidate() -> None:
    with tempfile.TemporaryDirectory() as td:
        runs_dir = Path(td)
        run_id = "R2"
        run_dir = runs_dir / run_id
        (run_dir / "vanguard").mkdir(parents=True)
        (run_dir / "options").mkdir()
        (run_dir / "superbrain").mkdir()
        (run_dir / "execution").mkdir()
        (run_dir / "morning_validation").mkdir()

        pd.DataFrame([{
            "ticker": "ABT", "verdict": "ACTUARIAL_SUPPORT",
            "final_recommendation": "CALL_EDGE_STRONG_5D",
            "layer2__edge_quality": "STRONG",
            "layer2__probability_verdict": "STRONG_EDGE",
        }]).to_csv(run_dir / "vanguard" / "vanguard_signals.csv", index=False)

        option_row = {
            "ticker": "ABT", "option_direction": "CALL",
            "recommended_contract": "ABT260619C00100000",
            "contract_spread_pct": 30, "contract_oi": 500,
            "options_score": 75, "rr_options": 2.0,
            "execution_permission": "NONE_OPTIONS_RESEARCH_ONLY",
            "final_route": "OPTIONS_BLOCKED",
            "options_research_score": 82,
            "hard_vetoes": "SPREAD_GT_15PCT",
        }
        pd.DataFrame([option_row]).to_csv(run_dir / "options" / f"options_intelligence_{run_id}.csv", index=False)
        pd.DataFrame([{
            **option_row,
            "eil_v3_verdict": "EXECUTE",
            "pse_execution_mode": "CURRENT_EDGE_REVIEW",
            "trigger_quality": "STRONG",
        }]).to_csv(run_dir / "superbrain" / f"eil_enriched_{run_id}.csv", index=False)
        pd.DataFrame([{
            **option_row,
            "effective_execution_verdict": "MORNING_VALIDATION_REQUIRED",
            "capital_permission": "EOD_CANDIDATE_ONLY",
            "eod_candidate_authorized": True,
            "candidate_size": 0.0,
            "sizing_policy": "POSITION_SIZING_RETIRED_ADVISORY_ONLY",
        }]).to_csv(run_dir / "execution" / f"execution_v3_5_{run_id}.csv", index=False)
        pd.DataFrame([{
            "ticker": "ABT", "eod_candidate_status": "EOD_EXECUTE_CANDIDATE",
            "eod_candidate_reason": "SURVIVED", "structural_tier": "A",
            "eod_candidate_permission": "MORNING_VALIDATION_REQUIRED",
            "candidate_size": 0.0, "sizing_policy": "POSITION_SIZING_RETIRED_ADVISORY_ONLY",
            "monetisation_fit_score": 88, "primary_direction": "CALL",
            "contract_quality_score": 80, "final_route": "OPTIONS_BLOCKED",
            "hard_vetoes": "SPREAD_GT_15PCT",
        }]).to_csv(run_dir / "morning_validation" / f"morning_candidates_{run_id}.csv", index=False)
        pd.DataFrame([{
            "ticker": "ABT", "shadow_opportunity_score": 0, "shadow_opportunity_label": "",
        }]).to_csv(run_dir / "morning_validation" / f"missed_opportunity_shadow_book_{run_id}.csv", index=False)

        result = audit_run(run_id, runs_dir=runs_dir)

    assert result["fail_count"] >= 1
    assert [
        item for item in result["outstanding_fixes"]
        if item["status"] == "OPTIONS_BLOCKED_PROMOTED_TO_EOD_CANDIDATE"
    ]


if __name__ == "__main__":
    test_vanguard_flattened_legacy_note_alias_is_accepted()
    test_options_blocked_cannot_be_promoted_to_eod_candidate()
    print("handoff_contract_audit tests passed")
