"""BF-03 business rules: no providers or live data; real source functions in isolated fixtures."""
import ast
import json
from pathlib import Path
from types import SimpleNamespace
import pytest
ROOT = Path(__file__).resolve().parents[1]

def load_function(path, name, **bindings):
    source = (ROOT/path).read_text(encoding="utf-8-sig")
    node = next(n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef) and n.name == name)
    scope = dict(Path=Path, **bindings)
    exec(compile("from __future__ import annotations", "future", "exec"), scope)
    exec(compile(ast.Module(body=[node], type_ignores=[]), path, "exec", flags=__import__("__future__").annotations.compiler_flag), scope)
    return scope[name]

@pytest.mark.parametrize("path", ["eod_candidate_engine.py", "execution_intelligence_runner.py", "morning_validation.py", "contracts/lab_control.py"])
def test_canonical_producers_have_no_legacy_copy_or_path_mutation(path):
    tree = ast.parse((ROOT/path).read_text(encoding="utf-8-sig"))
    legacy = [n for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and "ma_inputs_sync" in (n.module or "")]
    assert not legacy, f"canonical producer still imports retired sync: {path}"


def test_handoff_verifies_canonical_files_without_loading_or_copying_interpreter(tmp_path):
    import morning_handoff_finalizer as finalizer
    paths = []
    for name in ["morning.csv", "execution.csv", "triage.csv", "lab.csv"]:
        p=tmp_path/name;p.write_text("ticker,direction\nAAA,PUT\n", encoding="utf-8");paths.append(p)
    result = finalizer.verify_canonical_handoff(paths)
    assert len(result) == 4
    assert all(x["verified"] and x["sha256"] for x in result)
    assert all("destination" not in x for x in result)
    assert not (tmp_path/"pipeline_interpreter").exists()
    paths[-1].unlink()
    with pytest.raises(finalizer.MorningHandoffError, match="missing"):
        finalizer.verify_canonical_handoff(paths)


def test_handoff_cannot_publish_pass_when_canonical_hash_changed(tmp_path):
    import morning_handoff_finalizer as finalizer
    p=tmp_path/"lab.csv";p.write_text("original", encoding="utf-8")
    with pytest.raises(finalizer.MorningHandoffError, match="hash mismatch"):
        finalizer.verify_canonical_handoff([p], expected_hashes={str(p): "incorrect"})


def test_retired_desk_and_war_return_410_without_provider_or_package_import():
    from flask import Flask
    from contracts.legacy_interpreter_retirement import install_retired_interpreter_routes
    app=Flask(__name__);install_retired_interpreter_routes(app)
    with app.test_client() as client:
        for path in ["control", "preview", "reports", "deep_reports", "ask", "saved_reports", "war", "report/run/AAA/report", "war/run/AAA/report.html"]:
            for method in ["get", "post"]:
                response=getattr(client,method)("/api/interpreter/"+path)
                assert response.status_code == 410
                assert response.json["status"] == "RETIRED"
                assert response.json["provider_called"] is False


def test_lab_boot_does_not_mount_old_provider_or_war():
    source=(ROOT/"intelligence-lab/intelligence_lab.py").read_text(encoding="utf-8-sig")
    assert "from pipeline_interpreter." not in source
    assert "install_retired_interpreter_routes(app)" in source


def test_macro_publication_does_not_recreate_retired_inputs(tmp_path):
    from canonical_data.macro_publication import publish_macro_projections, macro_projection_paths
    authority=tmp_path/"dropbox/macro/macro_intelligence_latest.json";authority.parent.mkdir(parents=True)
    authority.write_text(json.dumps({"macro_authority":"ADVISORY_ONLY"}),encoding="utf-8")
    receipt=publish_macro_projections(authority)
    assert receipt["aligned"]
    assert len(macro_projection_paths(tmp_path)) == 1
    assert not (tmp_path/"pipeline_interpreter").exists()


@pytest.mark.parametrize("name", ["run_shadow_automation.bat", "watch_lab_exports.bat", "watch_lab_exports.ps1", "pipeline_interpreter/start.bat", "pipeline_interpreter/morning.bat"])
def test_retired_launchers_cannot_copy_capture_or_dispatch(name):
    text=(ROOT/name).read_text(encoding="utf-8-sig")
    assert "RETIRED" in text
    assert "python " not in text.lower()
    assert "Start-Process" not in text


def test_snapshot_stays_and_morning_core_calls_canonical_verifier():
    evening=(ROOT/"intelligent_orchestrator.py").read_text(encoding="utf-8-sig")
    morning=(ROOT/"morning_gate.py").read_text(encoding="utf-8-sig")
    assert "from pipeline_interpreter.interactive_snapshot import publish_eod_snapshot" in evening
    assert "publish_eod_snapshot(cfg.RUNS_DIR / canonical_run_id)" in evening
    assert "publish_verified_morning_handoff(handoff)" in morning
    assert "sync_interpreter=True" not in evening


def test_ui_cannot_dispatch_legacy_reports():
    index=(ROOT/"intelligence-lab/static/index.html").read_text(encoding="utf-8-sig")
    assert 'src="/static/interpreter-desk-controls.js"' not in index
    assert "previewInterpreterDesk()" not in index
    assert "selectInterpreterTicker(this)" not in index


@pytest.mark.parametrize("name", ['pipeline_interpreter/live_market_reader.py', 'pipeline_interpreter/ma_inputs_sync.py', 'pipeline_interpreter/pipeline_interpreter.py', 'pipeline_interpreter/prepare_interpreter_session.py', 'pipeline_interpreter/score_integrity_check.py', 'pipeline_interpreter/automation_v2/cli.py', 'pipeline_interpreter/automation_v2/e2e_orchestrator_cli.py', 'pipeline_interpreter/automation_v2/evidence_package_cli.py', 'pipeline_interpreter/automation_v2/lab_batch_cli.py', 'pipeline_interpreter/automation_v2/lab_structured_cli.py', 'pipeline_interpreter/automation_v2/package_publisher_cli.py', 'pipeline_interpreter/automation_v2/package_shadow_cli.py', 'pipeline_interpreter/automation_v2/production_deploy_cli.py', 'pipeline_interpreter/capture_v1/cli.py', 'pipeline_interpreter/capture_v1/market_screen_cli.py', 'pipeline_interpreter/capture_v1/navigation_cli.py', 'pipeline_interpreter/capture_v1/noii_calibration_cli.py', 'pipeline_interpreter/capture_v1/noii_cross_cli.py', 'pipeline_interpreter/capture_v1/ticker_batch_cli.py', 'pipeline_interpreter/capture_v1/ticker_cli.py', 'pipeline_interpreter/capture_v1/ticker_market_screen_cli.py', 'pipeline_interpreter/capture_v1/timeframe_batch_cli.py', 'pipeline_interpreter/capture_v1/timeframe_cli.py'])
def test_direct_retired_python_launch_stops_before_imports(name):
    import subprocess, sys
    result=subprocess.run([sys.executable, "-B", str(ROOT/name), "--help"], capture_output=True, text=True, timeout=20)
    assert result.returncode == 2
    assert "RETIRED" in result.stdout
    assert not result.stderr


def test_card_actions_do_not_call_removed_browser_functions():
    card=(ROOT/"intelligence-lab/static/trade-card.js").read_text(encoding="utf-8-sig")
    index=(ROOT/"intelligence-lab/static/index.html").read_text(encoding="utf-8-sig")
    for retired in ["INTERPRETER_SELECTED", "previewInterpreterDesk", "viewSavedInterpreterReports", "updateInterpreterSelection", "clearInterpreterSelection"]:
        assert retired not in card
        assert retired+"();" not in index


def test_eil_retains_enriched_morning_publication_without_legacy_copies(tmp_path):
    import os
    import pandas as pd
    import logging
    source=(ROOT/"execution_intelligence_runner.py").read_text(encoding="utf-8-sig")
    tree=ast.parse(source)
    candidates=[n for n in ast.walk(tree) if isinstance(n,ast.Try) and any(isinstance(x,ast.Assign) and any(isinstance(t,ast.Name) and t.id=="eil_enriched" for t in x.targets) for x in ast.walk(n))]
    assert candidates, "EIL must still publish enriched rows for Morning"
    node=min(candidates,key=lambda n:n.end_lineno-n.lineno)
    def physics(frame):
        return frame.assign(physics_state_id="fixture-physics")
    scope=dict(os=os, pd=pd, base=str(tmp_path), args=SimpleNamespace(run_id="BF03"),
               df=pd.DataFrame([{"ticker":"AAA","direction":"PUT","thesis_id":"T1","price":100}]),
               out=pd.DataFrame([{"ticker":"AAA","eil_v3_verdict":"REVIEW","eil_composite_score":42}]),
               logger=logging.getLogger("bf03-eil"), TRIGGER_HANDOFF_FIELDS=(),
               MACRO_QUANT_CSV_FIELDS=(), PHYSICS_FIELDS=(), TRUTH_PACKET_META_FIELDS=(),
               ensure_physics_fields=physics, _ensure_eil_audit_contract=lambda f:f,
               enrich_dataframe_with_truth_packets=lambda f,**kw:f, PRIORITY_EIL_PSE=1)
    exec(compile(ast.Module(body=[node],type_ignores=[]),"actual-eil-publication","exec"),scope)
    saved=tmp_path/"superbrain/eil_enriched_BF03.csv"
    assert saved.is_file(), "retiring sync must preserve canonical EIL-to-Morning publication"
    rows=pd.read_csv(saved)
    assert rows.loc[0,"direction"] == "PUT"
    assert rows.loc[0,"thesis_id"] == "T1"
    assert rows.loc[0,"eil_composite_score"] == 42
    assert not (tmp_path/"pipeline_interpreter").exists()
