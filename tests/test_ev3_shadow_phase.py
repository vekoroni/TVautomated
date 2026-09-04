from __future__ import annotations

import json

import pandas as pd

from scripts.run_ev3_shadow_phase import build_coverage, run_phase
from tests.test_ev_engine_v3 import NOW, _cache, _row, _vertical_row


def test_coverage_reports_complete_and_missing_selected_handoffs() -> None:
    complete = {
        "ticker": "TEST",
        "canonical_direction": "CALL",
        "direction_status": "AGREEMENT",
        "entry_spot": 100.0,
        "target_spot": 110.0,
        "invalidation_spot": 95.0,
        "planned_hold_sessions": 10,
        "ev3_barrier_state_key": "A|B|C|D|E|F|G",
        "recommended_contract": "TEST260918C00100000",
        "contract_quote_timestamp_utc": "2026-08-14T10:30:00Z",
        "contract_multiplier": 100,
    }
    incomplete = dict(complete)
    incomplete["contract_multiplier"] = None
    coverage = build_coverage(pd.DataFrame([complete, incomplete]))
    assert coverage["rows"] == 2
    assert coverage["selected_contract_rows"] == 2
    assert coverage["directional_selected_contract_rows"] == 2
    assert coverage["complete_selected_handoff_rows"] == 1
    assert coverage["complete_selected_handoff_coverage"] == 0.5
    assert coverage["fields"]["contract_multiplier"]["missing"] == 1
    assert coverage["fields"]["contract_multiplier"]["selected_coverage"] == 0.5


def test_coverage_excludes_non_directional_selected_contract_from_directional_contract() -> None:
    directional = {
        "ticker": "CALL1", "canonical_direction": "CALL",
        "direction_resolution_status": "RESOLVED", "entry_spot": 100,
        "target_spot": 110, "invalidation_spot": 95, "planned_hold_sessions": 10,
        "ev3_barrier_state_key": "A|B|C|D|E|F|G",
        "recommended_contract": "CALL1260918C00100000",
        "contract_quote_timestamp_utc": "2026-08-14T10:30:00Z",
        "contract_multiplier": 100,
    }
    non_directional = dict(directional)
    non_directional.update(ticker="STR1", canonical_direction="STRANGLE", contract_multiplier=None)
    coverage = build_coverage(pd.DataFrame([directional, non_directional]))
    assert coverage["selected_contract_rows"] == 2
    assert coverage["directional_selected_contract_rows"] == 1
    assert coverage["non_directional_selected_contract_rows"] == 1
    assert coverage["complete_selected_handoff_coverage"] == 1.0


def test_shadow_marks_missing_selected_contract_not_applicable(tmp_path) -> None:
    run_id = "20260814_120003"
    options_dir = tmp_path / run_id / "options"
    options_dir.mkdir(parents=True)
    source = _row()
    source.pop("contract_symbol")
    pd.DataFrame([source]).to_csv(
        options_dir / f"options_intelligence_{run_id}.csv", index=False
    )
    barrier_path = tmp_path / "barriers.parquet"
    _cache().frame.to_parquet(barrier_path, index=False)
    status = run_phase(
        run_id, runs_dir=tmp_path, barrier_cache=barrier_path, now_utc=NOW
    )
    results = pd.read_parquet(
        tmp_path / run_id / "ev3_shadow" / "ev3_stage1_shadow_results.parquet"
    )
    assert status["rows_evaluated"] == 0
    assert status["rows_not_applicable"] == 1
    assert status["rows_applicable"] == 0
    assert status["ev3_coverage_health"] == "NOT_APPLICABLE"
    assert results.iloc[0]["ev3_status"] == "NOT_APPLICABLE"
    assert results.iloc[0]["ev3_reason_code"] == "NOT_APPLICABLE_NO_SELECTED_CONTRACT"


def test_missing_barrier_cache_is_governed_non_authoritative_skip(tmp_path) -> None:
    run_id = "20260814_120000"
    options_dir = tmp_path / run_id / "options"
    options_dir.mkdir(parents=True)
    pd.DataFrame([{"ticker": "TEST"}]).to_csv(
        options_dir / f"options_intelligence_{run_id}.csv", index=False
    )
    status = run_phase(
        run_id,
        runs_dir=tmp_path,
        barrier_cache=tmp_path / "missing.parquet",
    )
    assert status["health"] == "SKIPPED_BARRIER_CACHE_MISSING"
    assert status["production_authority"] is False
    assert status["pipeline_blocking"] is False
    written = json.loads(
        (tmp_path / run_id / "ev3_shadow" / f"ev3_shadow_phase_status_{run_id}.json").read_text()
    )
    assert written["capital_eligibility_enabled"] is False


def test_governed_production_evidence_runs_end_to_end_without_authority(tmp_path) -> None:
    run_id = "20260814_120001"
    options_dir = tmp_path / run_id / "options"
    options_dir.mkdir(parents=True)
    pd.DataFrame([_row()]).to_csv(
        options_dir / f"options_intelligence_{run_id}.csv", index=False
    )
    barrier_path = tmp_path / "barriers.parquet"
    _cache().frame.to_parquet(barrier_path, index=False)

    status = run_phase(
        run_id,
        runs_dir=tmp_path,
        barrier_cache=barrier_path,
        now_utc=NOW,
    )

    shadow_dir = tmp_path / run_id / "ev3_shadow"
    assert status["health"] == "PRODUCTION_EVIDENCE_COMPLETE"
    assert status["mode"] == "PRODUCTION_EVIDENCE"
    assert status["production_consumer_enabled"] is True
    assert status["rows_received"] == 1
    assert status["rows_evaluated"] == 1
    assert status["production_authority"] is False
    assert status["capital_eligibility_enabled"] is False
    assert status["functional_test_clock_override"] is True
    assert status["evaluation_clock_mode"] == "FIXED_FUNCTIONAL_TEST"
    assert status["strict_production_freshness"] is False
    assert status["technical_health"] == "PASS"
    assert status["ev_functional_health"] == "PRODUCTION_EVIDENCE_COMPLETE"
    assert status["morning_capital_permission"] == "NOT_EVALUATED_BY_EV3_EVIDENCE"
    assert status["system_defects"] == {}
    assert (shadow_dir / "ev3_stage1_shadow_results.parquet").exists()
    assert (shadow_dir / "ev3_stage1_shadow_audit.json").exists()


def test_governed_phase_compares_single_and_vertical_candidates(tmp_path) -> None:
    run_id = "20260814_120002"
    options_dir = tmp_path / run_id / "options"
    options_dir.mkdir(parents=True)
    source = _row()
    source["recommended_contract"] = source["contract_symbol"]
    vertical = _vertical_row()
    source["alternative_contracts_json"] = json.dumps([{
        "symbol": vertical["contract_symbol"],
        "structure": vertical["contract_structure"],
        "candidate_policy_version": "fixture-vertical-v1",
        "candidate_generation_rank": 1,
        "long_leg": vertical["long_leg"],
        "short_leg": vertical["short_leg"],
        "strike_width": 5.0,
        "entry_debit_mid": 2.4,
    }])
    pd.DataFrame([source]).to_csv(
        options_dir / f"options_intelligence_{run_id}.csv", index=False
    )
    barrier_path = tmp_path / "barriers.parquet"
    _cache().frame.to_parquet(barrier_path, index=False)

    status = run_phase(
        run_id, runs_dir=tmp_path, barrier_cache=barrier_path, now_utc=NOW
    )
    evaluations = pd.read_parquet(
        tmp_path / run_id / "ev3_shadow" / "ev3_stage1_contract_evaluations.parquet"
    )
    assert status["health"] == "PRODUCTION_EVIDENCE_COMPLETE"
    assert status["engine_stage"] == "EV-2B"
    assert len(evaluations) == 2
    assert set(evaluations["ev3_structure"]) == {"LONG_SINGLE", "BULL_CALL_DEBIT"}
