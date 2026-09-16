from __future__ import annotations

from pathlib import Path

import pandas as pd

from eod_candidate_engine import build_candidate_manifest
from wall_break_scorer import run_wall_break_scorer


def _research_row(ticker: str, route: str) -> dict:
    return {
        "ticker": ticker,
        "sb_final_verdict": "STAND_DOWN",
        "final_route": route,
        "direction": "CALL",
        "options_direction": "CALL",
        "spot": 100.0,
        "signal_price": 100.0,
        "target_price": 110.0,
        "invalidation_spot": 95.0,
        "invalidation_state": "AVAILABLE",
        "effective_execution_verdict": "MORNING_VALIDATION_REQUIRED",
        "capital_authorization_state": "EOD_CANDIDATE_ONLY",
        "capital_permission": "EOD_CANDIDATE_ONLY",
        "eod_candidate_authorized": True,
        "execution_authorized": False,
        "trigger_quality": "STRONG",
        "trigger_go_eligible": True,
        "options_score": 80.0,
        "options_research_score": 80.0,
        "execution_permission": "NONE_OPTIONS_RESEARCH_ONLY",
        "hard_vetoes": "",
        "missing_data": "",
        "recommended_contract": f"{ticker}261016C00100000",
        "contract_strike": 100.0,
        "contract_expiry": "2026-10-16",
        "contract_dte": 33,
        "contract_premium": 2.0,
        "contract_bid": 1.9,
        "contract_ask": 2.1,
        "contract_quote_quality": "TWO_SIDED",
        "contract_quote_timestamp_utc": "2026-09-11T20:00:00Z",
    }


def test_wbs_scores_research_routes_without_granting_execution(tmp_path: Path) -> None:
    sb_path = tmp_path / "superbrain.csv"
    oi_path = tmp_path / "options.csv"
    pd.DataFrame([
        _research_row("REVIEW", "OPTIONS_GO_REVIEW"),
        _research_row("PROBE", "OPTIONS_PROBE_ONLY"),
        {**_research_row("PUT", "OPTIONS_ARMED_HALF"), "direction": "PUT", "options_direction": "PUT", "target_price": 90.0, "invalidation_spot": 105.0},
        _research_row("BLOCK", "OPTIONS_BLOCKED"),
    ]).to_csv(sb_path, index=False)
    pd.DataFrame([
        {"ticker": "REVIEW"},
        {"ticker": "PROBE"},
        {"ticker": "PUT"},
        {"ticker": "BLOCK"},
    ]).to_csv(oi_path, index=False)

    result, output_path = run_wall_break_scorer(
        sb_enriched_csv=str(sb_path),
        oi_csv=str(oi_path),
        run_id="TEST",
        output_dir=str(tmp_path),
    )

    assert set(result["ticker"]) == {"REVIEW", "PROBE", "PUT"}
    assert set(result["sb_final_verdict"]) == {"STAND_DOWN"}
    assert "execution_authorized" in result.columns
    assert set(result["execution_authorized"].astype(str).str.lower()) == {"false"}
    assert Path(output_path).exists()


def test_empty_wbs_is_schema_valid_and_does_not_block_eod_manifest(tmp_path: Path) -> None:
    sb_path = tmp_path / "superbrain.csv"
    oi_path = tmp_path / "options.csv"
    execution_path = tmp_path / "execution.csv"
    output_path = tmp_path / "morning_candidates_TEST.csv"
    blocked = _research_row("BLOCK", "OPTIONS_BLOCKED")
    pd.DataFrame([blocked]).to_csv(sb_path, index=False)
    pd.DataFrame([{"ticker": "BLOCK"}]).to_csv(oi_path, index=False)
    pd.DataFrame([blocked]).to_csv(execution_path, index=False)

    result, wbs_path = run_wall_break_scorer(
        sb_enriched_csv=str(sb_path),
        oi_csv=str(oi_path),
        run_id="TEST",
        output_dir=str(tmp_path),
    )
    persisted = pd.read_csv(wbs_path)
    assert result.empty
    assert persisted.empty
    assert {"ticker", "wbs", "wbs_grade"}.issubset(persisted.columns)

    candidates = build_candidate_manifest(
        eil_path=execution_path,
        wbs_path=wbs_path,
        output_path=output_path,
        run_id="TEST",
        max_candidates=10,
    )
    assert len(candidates) == 1
    assert candidates.iloc[0]["ticker"] == "BLOCK"


def test_legacy_schema_less_wbs_is_non_blocking(tmp_path: Path) -> None:
    execution_path = tmp_path / "execution.csv"
    wbs_path = tmp_path / "legacy_empty_wbs.csv"
    output_path = tmp_path / "morning_candidates_TEST.csv"
    row = _research_row("LEGACY", "OPTIONS_GO_REVIEW")
    pd.DataFrame([row]).to_csv(execution_path, index=False)
    wbs_path.write_text("\n", encoding="utf-8")

    candidates = build_candidate_manifest(
        eil_path=execution_path,
        wbs_path=wbs_path,
        output_path=output_path,
        run_id="TEST",
        max_candidates=10,
    )
    assert len(candidates) == 1
    assert candidates.iloc[0]["ticker"] == "LEGACY"
