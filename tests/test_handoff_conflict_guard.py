from __future__ import annotations

import pandas as pd

import intelligent_orchestrator as orchestrator


RUN_ID = "20990101_010101"


def _phase2_fields() -> dict:
    return {field: "TEST_VALUE" for field in orchestrator.PHASE2_LAYER2_FIELDS}


def _write_eil(tmp_path, row: dict):
    path = tmp_path / RUN_ID / "superbrain" / f"eil_enriched_{RUN_ID}.csv"
    path.parent.mkdir(parents=True)
    pd.DataFrame([row]).to_csv(path, index=False)
    return path


def test_strict_guard_continues_after_execution_row_is_quarantined(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(orchestrator.cfg, "RUNS_DIR", tmp_path)
    monkeypatch.setattr(orchestrator, "_strict_actuarial_v6_enabled", lambda: True)
    path = _write_eil(
        tmp_path,
        {
            "ticker": "TEST",
            "pse_execution_mode": "EXECUTE",
            "pse_final_size": 0.5,
            "fd_verdict": "EXECUTE_WITH_CAUTION",
            "fd_size": 0.5,
            "thesis_decision": "GO",
            "eil_v3_verdict": "EXECUTE",
            "trigger_primary": "NONE",
            "trigger_quality": "NONE",
            "trigger_stale": True,
            "trigger_freshness_state": "STALE",
            "capital_permission": "YES",
            **_phase2_fields(),
        },
    )

    assert orchestrator.enforce_handoff_conflict_guard(RUN_ID) is True

    guarded = pd.read_csv(path, low_memory=False).iloc[0]
    assert guarded["handoff_status"] == "CONFLICT_DETECTED"
    assert guarded["capital_permission"] == "NO"
    assert guarded["pse_execution_mode"] == "WATCHLIST"
    assert guarded["fd_verdict"] == "WATCHLIST"
    assert guarded["thesis_decision"] == "WATCHLIST"
    assert float(guarded["pse_final_size"]) == 0.0
    assert float(guarded["fd_size"]) == 0.0
    assert "TRIGGER_MISSING_WITH_EXECUTION_MODE" in guarded["handoff_conflict_flags"]
    assert "TRIGGER_DATA_STALE_WITH_EXECUTION_MODE" in guarded["handoff_conflict_flags"]


def test_strict_guard_still_blocks_missing_phase2_schema(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(orchestrator.cfg, "RUNS_DIR", tmp_path)
    monkeypatch.setattr(orchestrator, "_strict_actuarial_v6_enabled", lambda: True)
    fields = _phase2_fields()
    fields.pop(orchestrator.PHASE2_LAYER2_FIELDS[0])
    _write_eil(
        tmp_path,
        {
            "ticker": "TEST",
            "pse_execution_mode": "WATCHLIST",
            "fd_verdict": "WATCHLIST",
            "trigger_primary": "RANGE_BREAK",
            "trigger_quality": "SINGLE",
            "trigger_stale": False,
            "capital_permission": "NO",
            **fields,
        },
    )

    assert orchestrator.enforce_handoff_conflict_guard(RUN_ID) is False
