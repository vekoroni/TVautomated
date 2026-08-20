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
        eil_path = root / "eil.csv"
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

    by_ticker = {str(row["ticker"]): row for row in out.to_dict("records")}

    assert by_ticker["GOOD"]["final_route"] == "OPTIONS_GO_REVIEW"
    assert by_ticker["GOOD"]["options_research_permission"] == "NONE_OPTIONS_RESEARCH_ONLY"
    assert by_ticker["GOOD"]["eod_candidate_status"] == "EOD_EXECUTE_CANDIDATE"

    assert by_ticker["BAD"]["final_route"] == "OPTIONS_BLOCKED"
    assert by_ticker["BAD"]["hard_vetoes"] == "SPREAD_GT_15PCT"
    assert by_ticker["BAD"]["eod_candidate_status"] == "EOD_BLOCK"
    assert "OPTIONS_RESEARCH_BLOCKED" in by_ticker["BAD"]["eod_dropoff_reason"]


if __name__ == "__main__":
    test_eod_manifest_preserves_options_research_contract_and_blocks_vetoes()
    print("eod options research handoff tests passed")
