"""Offline regression: no orchestrator entrypoint or provider is executed."""
from __future__ import annotations

import ast
import copy
from datetime import datetime, timezone
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from orchestrator.production_eligibility import (
    code_identity_reasons, warn_production_eligibility,
)
from orchestrator.dynamic_dispatcher import resolve_dispatch_plan

ROOT = Path(__file__).resolve().parents[1]
CLEAN = {"baseline_commit_hash": "f4968c788e1f70c2809d85cfab8698569d637995",
         "git_describe": "rel-20260923-2-93-gf4968c7"}
DIRTY = {**CLEAN, "git_describe": CLEAN["git_describe"] + "-dirty"}


def function(name, **bindings):
    """Load the exact production function without module startup side effects."""
    tree = ast.parse((ROOT / "intelligent_orchestrator.py").read_text(encoding="utf-8-sig"))
    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name)
    scope = dict(Path=Path, json=json, **bindings)
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(ROOT / "intelligent_orchestrator.py"), "exec"), scope)
    return scope[name]


@pytest.mark.parametrize("identity,reason", [
    (DIRTY, "CODE_UNCOMMITTED"),
    ({**CLEAN, "baseline_commit_hash": "UNAVAILABLE"}, "CODE_IDENTITY_UNAVAILABLE"),
    ({**CLEAN, "git_describe": "UNAVAILABLE"}, "CODE_IDENTITY_UNAVAILABLE"),
    ({}, "CODE_IDENTITY_UNAVAILABLE"),
])
def test_standard_production_warns_and_continues(identity, reason, caplog):
    assert reason in warn_production_eligibility(identity)
    assert reason in caplog.text
    assert "continues" in caplog.text


def test_clean_production_is_allowed():
    assert code_identity_reasons(CLEAN) == ()
    warn_production_eligibility(CLEAN)


@pytest.mark.parametrize("mode", ["LIVE_PROVING", "TEST", "REPLAY", "FORCE"])
def test_explicit_non_baseline_modes_remain_available(mode):
    warn_production_eligibility(DIRTY, operator_mode=mode)


def test_validation_is_not_misidentified_as_eod_build():
    warn_production_eligibility(DIRTY, action="VALIDATE")


@pytest.mark.parametrize("dirty,condition", [(False, "NORMAL_COMPLETED_SESSION"), (True, "TEST")])
def test_dispatch_plan_receives_code_fact(tmp_path, dirty, condition):
    plan, _ = resolve_dispatch_plan(
        output_dir=tmp_path, requested_action="BUILD_THESIS",
        as_of_utc=datetime(2026, 11, 11, 23, 19, 51, tzinfo=timezone.utc),
        code_dirty=dirty,
    )
    assert plan.run_condition == condition
    assert plan.baseline_eligible is (not dirty)
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("action", ["VALIDATE", "AUTO"])
def test_dirty_checkout_does_not_change_morning_validation_phase(tmp_path, monkeypatch, action):
    import orchestrator.dynamic_dispatcher as dispatcher
    thesis = SimpleNamespace(pipeline_run_id="saved_thesis", thesis_book_id="thesis",
                             completed_session=__import__("datetime").date(2026, 11, 11),
                             authorised_tickers=("SYM", "NAN"))
    monkeypatch.setattr(dispatcher, "resolve_accepted_thesis", lambda *a, **k: thesis)
    plan, _ = resolve_dispatch_plan(
        output_dir=tmp_path, requested_action=action,
        as_of_utc=datetime(2026, 11, 12, 12, 0, tzinfo=timezone.utc), code_dirty=True,
    )
    assert plan.resolved_action == "VALIDATE"
    assert plan.run_condition == "PREOPEN_THESIS_CHECK"
    assert plan.baseline_eligible is False


def test_dirty_evening_starts_with_warning_before_session_or_provider_work(caplog):
    import logging
    source = (ROOT / "intelligent_orchestrator.py").read_text(encoding="utf-8-sig")
    node = next(n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef) and n.name == "evening_workflow")
    # Execute exactly the launch prefix, stopping before session/provider work.
    cutoff = next(i for i, n in enumerate(node.body) if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "session_id" for t in n.targets))
    node.body = node.body[:cutoff]
    scope = dict(Optional=__import__("typing").Optional, datetime=datetime, Path=Path,
                 _git_baseline_identity=lambda: DIRTY, os=SimpleNamespace(getenv=lambda *args: "PRODUCTION"),
                 logger=logging.getLogger("bf03-launch"))
    exec(compile(ast.Module(body=[node], type_ignores=[]), "launch-prefix", "exec"), scope)
    scope["evening_workflow"]()
    assert "CODE_UNCOMMITTED" in caplog.text
    assert "continues" in caplog.text


def test_cli_warning_precedes_plan_persistence():
    source = (ROOT / "intelligent_orchestrator.py").read_text(encoding="utf-8-sig")
    section = source.split("plan, selected_thesis = resolve_dispatch_plan(", 1)[1]
    assert "code_dirty=bool(code_identity_reasons(_dispatch_code_identity))" in section
    assert section.index("warn_production_eligibility(") < section.index("persist_dispatch_plan(")


@pytest.mark.parametrize("identity,provider,mode,expected,reason", [
    (CLEAN, True, "STANDARD", "NORMAL_COMPLETED_SESSION", None),
    (DIRTY, True, "STANDARD", "TEST", "CODE_UNCOMMITTED"),
    (CLEAN, False, "STANDARD", "TEST", "PROVIDER_NOT_COMPLETED_SESSION"),
    ({**CLEAN, "git_describe": "UNAVAILABLE"}, True, "STANDARD", "TEST", "CODE_IDENTITY_UNAVAILABLE"),
    (DIRTY, False, "LIVE_PROVING", "LIVE_PROVING", "LIVE_PROVING"),
])
def test_final_assessment_preserves_plan_and_explains_exclusion(tmp_path, identity, provider, mode, expected, reason):
    # Compact saved 11-Nov run facts; the real run is never opened for writing.
    original_plan = {"resolved_action": "BUILD_THESIS", "session_state": "AFTER_HOURS",
                     "last_completed_session": "2026-11-11",
                     "run_condition": "NORMAL_COMPLETED_SESSION", "baseline_eligible": True,
                     "plan_hash": "03639ac34d7edb073476ffa950c6837c28b772d4d9c8dfe5a7ffa378bc5ed814"}
    meta = {"run_meta_schema_version": "run_meta_v2", **identity,
            "dynamic_plan": copy.deepcopy(original_plan)}
    run = tmp_path / "20261111_231951"
    run.mkdir()
    (run / "run_meta.json").write_text(json.dumps(meta), encoding="utf-8")
    summary = tmp_path / "summary.json"
    summary.write_text(json.dumps({"provider_completeness_evidence": {
        "status": "ASSESSED", "threshold_version": "provider_completeness_v1",
        "normal_completed_session_eligible": provider,
        "complete_chains": 2687, "chains_expected": 2799, "closes_present": 2799,
    }}), encoding="utf-8")
    integrate = function("_integrate_provider_completeness_into_run_meta", cfg=SimpleNamespace(RUNS_DIR=tmp_path))
    result = integrate(run.name, options_summary_path=summary, operator_mode=mode)
    assert result["run_condition"] == expected
    assert result["baseline_eligible"] is (expected == "NORMAL_COMPLETED_SESSION")
    assert result["baseline_ineligibility_reason"] == reason
    assert result["classification_status"] == "FINAL"
    assert result["dynamic_plan"] == original_plan
    assert json.loads((run / "run_meta.json").read_text())["run_condition"] == expected


def test_pin_publishes_provisional_top_level_labels():
    source = (ROOT / "intelligent_orchestrator.py").read_text(encoding="utf-8-sig")
    node = next(n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef) and n.name == "pin_run_directory")
    segment = ast.get_source_segment(source, node)
    assert 'meta.update(run_condition=run_plan.run_condition' in segment
    assert 'classification_status="PROVISIONAL"' in segment
    assert 'IMMUTABLE_PLANNED_INTENT_NOT_FINAL_ELIGIBILITY' in segment
    assert 'git_identity = code_identity if code_identity is not None' in segment


def test_launch_identity_is_carried_to_pin_not_recaptured_after_discovery():
    source = (ROOT / "intelligent_orchestrator.py").read_text(encoding="utf-8-sig")
    tree = ast.parse(source)
    evening = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "evening_workflow")
    calls = [n for n in ast.walk(evening) if isinstance(n, ast.Call)]
    assert sum(isinstance(n.func, ast.Name) and n.func.id == "_git_baseline_identity" for n in calls) == 1
    vanguard = next(n for n in calls if isinstance(n.func, ast.Name) and n.func.id == "run_vanguard_pipeline")
    assert next(k.value.id for k in vanguard.keywords if k.arg == "code_identity") == "_launch_code_identity"
