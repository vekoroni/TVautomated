from __future__ import annotations

import json
from pathlib import Path

import intelligent_orchestrator as orchestrator


def test_run_meta_status_is_advanced_atomically(tmp_path: Path, monkeypatch) -> None:
    run_id = "20260830_120000"
    run_dir = tmp_path / run_id
    run_dir.mkdir(parents=True)
    meta_path = run_dir / "run_meta.json"
    meta_path.write_text(
        json.dumps(
            {
                "canonical_run_id": run_id,
                "run_status": "IN_PROGRESS",
                "pipeline_mode": "EOD",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(orchestrator.cfg, "RUNS_DIR", tmp_path)

    orchestrator._update_run_meta_status(
        run_id,
        "COMPLETED",
        pipeline_mode="EOD",
    )

    payload = json.loads(meta_path.read_text(encoding="utf-8"))
    assert payload["canonical_run_id"] == run_id
    assert payload["run_status"] == "COMPLETED"
    assert payload["pipeline_mode"] == "EOD"
    assert payload["status_updated_at_utc"]
    assert not meta_path.with_suffix(".json.tmp").exists()


def test_run_meta_rejects_unknown_status(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(orchestrator.cfg, "RUNS_DIR", tmp_path)
    try:
        orchestrator._update_run_meta_status("run", "TRADEABLE")
    except ValueError as error:
        assert "invalid run status" in str(error)
    else:
        raise AssertionError("unknown run status must fail closed")


# ---------------------------------------------------------------------------
# AVS-FIX-001 W0.1 — every run records the released baseline it came from.
# ---------------------------------------------------------------------------


def test_git_baseline_identity_reports_hash_and_describe() -> None:
    identity = orchestrator._git_baseline_identity()
    assert set(identity) == {"baseline_commit_hash", "git_describe"}
    # In this repository both resolve; the point of the test is that neither is
    # silently dropped and neither is empty.
    assert identity["baseline_commit_hash"]
    assert identity["git_describe"]


def test_git_baseline_identity_degrades_without_git(monkeypatch) -> None:
    def _explode(*args, **kwargs):
        raise FileNotFoundError("git")

    monkeypatch.setattr(orchestrator.subprocess, "run", _explode)
    identity = orchestrator._git_baseline_identity()
    # A missing git must never abort a run — it degrades, visibly.
    assert identity == {
        "baseline_commit_hash": "UNAVAILABLE",
        "git_describe": "UNAVAILABLE",
    }


def test_pin_run_directory_writes_both_code_identity_fields() -> None:
    """The run-meta writer must carry `git_describe` beside the commit hash.

    Asserted structurally against the source of `pin_run_directory` because
    calling it end to end would require the whole Discovery/macro fixture set,
    which is exactly the pipeline execution AVS-IMP-FIX-001 forbids here.
    """
    import ast
    import inspect

    tree = ast.parse(inspect.getsource(orchestrator.pin_run_directory))
    keys = {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }
    assert "baseline_commit_hash" in keys
    assert "git_describe" in keys


def test_provider_finality_marks_clean_standard_run_baseline_eligible(
    tmp_path: Path, monkeypatch
) -> None:
    run_id = "20260912_200000"
    run_dir = tmp_path / run_id
    run_dir.mkdir(parents=True)
    (run_dir / "run_meta.json").write_text(json.dumps({
        "run_meta_schema_version": "run_meta_v2",
        "git_describe": "avs-release-1-gabc123",
        "baseline_commit_hash": "abc123",
        "run_kind": "PRODUCTION",
        "dynamic_plan": {
            "last_completed_session": "2026-09-11",
            "evidence_cutoff_utc": "2026-09-12T20:00:00Z",
        },
        "ddd_runtime_profile": {"sha256": "profile-hash", "release_id": "R1"},
    }), encoding="utf-8")
    summary = tmp_path / "summary.json"
    summary.write_text(json.dumps({
        "provider_completeness_evidence": {
            "threshold_version": "provider_completeness_v1",
            "status": "ASSESSED",
            "normal_completed_session_eligible": True,
            "complete_chains": 95,
            "chains_expected": 100,
            "closes_present": 100,
            "underlying_tickers_expected": 100,
            "governed_constants_sha256": "constants-hash",
        }
    }), encoding="utf-8")
    monkeypatch.setattr(orchestrator.cfg, "RUNS_DIR", tmp_path)

    result = orchestrator._integrate_provider_completeness_into_run_meta(
        run_id, options_summary_path=summary, operator_mode="STANDARD"
    )

    assert result["run_condition"] == "NORMAL_COMPLETED_SESSION"
    assert result["baseline_eligible"] is True
    assert result["code_identity"]["dirty"] is False
    assert result["config_identity"]["profile_hash"] == "profile-hash"
    assert result["config_identity"]["governed_constants_sha256"] == "constants-hash"


def test_provider_finality_never_promotes_dirty_or_forced_run(
    tmp_path: Path, monkeypatch
) -> None:
    run_id = "20260912_150000"
    run_dir = tmp_path / run_id
    run_dir.mkdir(parents=True)
    meta = {
        "run_meta_schema_version": "run_meta_v2",
        "git_describe": "abc123-dirty",
        "baseline_commit_hash": "abc123",
        "dynamic_plan": {},
        "ddd_runtime_profile": {},
    }
    (run_dir / "run_meta.json").write_text(json.dumps(meta), encoding="utf-8")
    summary = tmp_path / "summary.json"
    summary.write_text(json.dumps({
        "provider_completeness_evidence": {
            "threshold_version": "provider_completeness_v1",
            "status": "ASSESSED",
            "normal_completed_session_eligible": True,
        }
    }), encoding="utf-8")
    monkeypatch.setattr(orchestrator.cfg, "RUNS_DIR", tmp_path)

    result = orchestrator._integrate_provider_completeness_into_run_meta(
        run_id, options_summary_path=summary, operator_mode="FORCE"
    )

    assert result["run_condition"] == "TEST"
    assert result["baseline_eligible"] is False
