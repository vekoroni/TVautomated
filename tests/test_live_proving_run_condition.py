"""LIVE_PROVING run condition (ACK 8 Oct 2026: "it should be labelled live proving as we can still use the data").

Business rules:
- ACK can start a run as live proving (`--live-proving`). Its condition is LIVE_PROVING, never relabelled TEST because
  the code is uncommitted or the option quotes are not the completed session's.
- Its data is used: the outcome scorer records and measures it under its own condition. It is kept out of model
  fitting (baseline_eligible False), and the run record states each deviation from a clean completed-session run:
  CODE_UNCOMMITTED and PROVIDER_NOT_COMPLETED_SESSION.
- A normal run is unchanged: uncommitted code or an unsettled provider still makes it TEST.
"""
import json
from pathlib import Path

from domain.run_planning import OperatorMode, RunCondition, resolve_run_condition

ROOT = Path(__file__).resolve().parents[1]


def test_live_proving_is_its_own_condition_even_with_uncommitted_code():
    assert resolve_run_condition(requested_action="BUILD_THESIS", session_phase="REGULAR",
                                 operator_mode=OperatorMode.LIVE_PROVING, code_dirty=True) is RunCondition.LIVE_PROVING
    assert resolve_run_condition(requested_action="BUILD_THESIS", session_phase="REGULAR",
                                 operator_mode="STANDARD", code_dirty=True) is RunCondition.TEST


def _run_meta(tmp_path, monkeypatch, *, mode, dirty, provider_eligible):
    import intelligent_orchestrator as orch
    run_id = "20990101_000000"
    run_dir = tmp_path / run_id
    run_dir.mkdir()
    (run_dir / "run_meta.json").write_text(json.dumps({
        "run_meta_schema_version": "run_meta_v2",
        "git_describe": "abc123-dirty" if dirty else "abc123", "baseline_commit_hash": "abc123",
        "dynamic_plan": {"resolved_action": "BUILD_THESIS", "session_state": "REGULAR"}}), encoding="utf-8")
    summary = tmp_path / "summary.json"
    summary.write_text(json.dumps({"provider_completeness_evidence": {
        "threshold_version": "provider_completeness_v1", "status": "ASSESSED",
        "normal_completed_session_eligible": provider_eligible}}), encoding="utf-8")
    monkeypatch.setattr(orch.cfg, "RUNS_DIR", tmp_path)
    return orch._integrate_provider_completeness_into_run_meta(run_id, options_summary_path=summary,
                                                                operator_mode=mode)


def test_a_live_proving_run_keeps_its_label_and_states_its_deviations(tmp_path, monkeypatch):
    meta = _run_meta(tmp_path, monkeypatch, mode="LIVE_PROVING", dirty=True, provider_eligible=False)
    assert meta["run_condition"] == "LIVE_PROVING" and meta["baseline_eligible"] is False
    assert meta["live_proving_deviations"] == ["CODE_UNCOMMITTED", "PROVIDER_NOT_COMPLETED_SESSION"]
    assert meta["baseline_ineligibility_reason"] == "LIVE_PROVING"


def test_a_normal_run_is_still_test_when_dirty(tmp_path, monkeypatch):
    meta = _run_meta(tmp_path, monkeypatch, mode="STANDARD", dirty=True, provider_eligible=True)
    assert meta["run_condition"] == "TEST"


def test_the_evening_cli_offers_live_proving():
    src = (ROOT / "intelligent_orchestrator.py").read_text(encoding="utf-8-sig")
    assert '"--live-proving"' in src
    assert 'operator_mode="LIVE_PROVING" if live_proving' in src


def test_the_dynamic_dispatcher_carries_live_proving_to_the_plan_and_the_evening():
    # Verification 20261008_220129 G2-01: the active dynamic dispatcher passed STANDARD to the plan and omitted
    # live_proving from its evening_workflow call; only the legacy --evening branch forwarded the flag.
    src = (ROOT / "intelligent_orchestrator.py").read_text(encoding="utf-8-sig")
    dispatch = src.split("plan, selected_thesis = resolve_dispatch_plan(", 1)[1].split(")\n", 1)[0]
    assert "LIVE_PROVING" in dispatch and "args.live_proving" in dispatch
    run_evening = src.split("def _run_evening(planned):", 1)[1].split("return", 1)[0]
    assert "live_proving=args.live_proving" in run_evening


def test_a_live_proving_morning_keeps_its_session_phase_condition():
    # The Morning uses run_condition as its execution mode (pre-open thesis check vs post-open contract refresh);
    # live proving labels the Evening's evidence record and must not replace that phase.
    assert resolve_run_condition(requested_action="VALIDATE", session_phase="REGULAR",
                                 operator_mode="LIVE_PROVING", code_dirty=True) is RunCondition.POSTOPEN_CONTRACT_REFRESH
    assert resolve_run_condition(requested_action="VALIDATE", session_phase="PREMARKET",
                                 operator_mode="LIVE_PROVING", code_dirty=True) is RunCondition.PREOPEN_THESIS_CHECK
