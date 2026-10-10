"""Output-trust item 10, part 10.4 (C-2; ACK approved 9-10 Oct 2026): end-of-line scorecards.

Today the end-of-line verifier (tools/avs_verify) is run by hand and covers data, calculation and structure only.

Business rules:
- After the Evening and the Morning the verifier runs and a scorecard reports five sections - data, calculation,
  structure, calibration, trading performance - each PASS / REVIEW / FAIL / NOT_AVAILABLE with its facts.
- Missing evidence is NOT_AVAILABLE (stated), never PASS. The scorecard never stops the run (the stations do).
"""
from __future__ import annotations

import json
from pathlib import Path

from domain.run_scorecard import build_scorecard


def _run(tmp_path, *, verdict="TRUST_WITH_CAVEATS", station_stop=0, semantic="DEGRADED"):
    run = tmp_path / "runs" / "R1"
    (run / "diagnostics").mkdir(parents=True)
    (run / "final_run_manifest.json").write_text(json.dumps({
        "pipeline_technical_health": "PASS", "pipeline_semantic_health": semantic, "semantic_defect_count": 35,
        "fatal_flags": [], "run_tradeable_label": "REVIEW_REQUIRED_SEMANTIC_HANDOFF_DEFECTS"}), encoding="utf-8")
    (run / "diagnostics" / "handoff_contract_audit_R1.json").write_text(json.dumps(
        {"overall_status": "WARN", "fail_count": 0, "warn_count": 4}), encoding="utf-8")
    for st in ("discovery", "options", "eod", "book"):
        (run / "diagnostics" / f"station_{st}_R1.json").write_text(json.dumps(
            {"station": st, "rows": 10, "stop_defects": [{"check": "x"}] * (station_stop if st == "book" else 0),
             "other_defects": []}), encoding="utf-8")
    (run / "diagnostics" / "outcome_scoring_R1.json").write_text(json.dumps({"status": "COMPLETED"}), encoding="utf-8")
    verify = tmp_path / "audit" / "verify" / "R1" / "evening"
    verify.mkdir(parents=True)
    (verify / "verify_report.json").write_text(json.dumps({"verdict": verdict, "reason": "ok"}), encoding="utf-8")
    return run, tmp_path / "audit" / "verify"


def test_five_sections_with_their_facts(tmp_path):
    run, verify_root = _run(tmp_path)
    card = build_scorecard(run, run_id="R1", phase="evening", verify_root=verify_root)
    assert list(card["sections"]) == ["data", "calculation", "structure", "calibration", "trading_performance"]
    assert card["sections"]["data"]["status"] == "REVIEW"                 # handoff audit WARN
    assert card["sections"]["calculation"]["status"] == "REVIEW"          # verifier: trust with caveats
    assert card["sections"]["structure"]["status"] == "REVIEW"            # semantic health DEGRADED
    cal = card["sections"]["calibration"]
    assert cal["status"] == "REVIEW" and cal["facts"]["replay_slope"] is not None
    assert cal["facts"]["forward_state"] == "NOT_AVAILABLE"           # no outcome store given: stated, never assumed
    assert card["sections"]["trading_performance"]["status"] in {"NOT_AVAILABLE", "REVIEW"}
    assert card["overall"] == "REVIEW" and card["authority"] == "REPORT_ONLY"


def test_failures_and_missing_evidence_are_stated(tmp_path):
    run, verify_root = _run(tmp_path, verdict="DO_NOT_TRADE", station_stop=1)
    card = build_scorecard(run, run_id="R1", phase="evening", verify_root=verify_root)
    assert card["sections"]["calculation"]["status"] == "FAIL" and card["overall"] == "FAIL"
    empty = build_scorecard(tmp_path / "nothing", run_id="R2", phase="morning", verify_root=tmp_path / "none")
    assert empty["sections"]["calculation"]["status"] == "NOT_AVAILABLE"
    assert empty["overall"] == "NOT_AVAILABLE"


def test_the_run_writes_the_scorecard_after_the_evening_and_the_morning():
    import inspect
    import intelligent_orchestrator
    src = inspect.getsource(intelligent_orchestrator)
    assert '_run_end_of_line_scorecard(canonical_run_id, "evening")' in src
    assert '_run_end_of_line_scorecard(' in src and '"morning")' in src
