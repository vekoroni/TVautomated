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
