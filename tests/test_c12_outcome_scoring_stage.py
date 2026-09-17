"""Item 1 (ACK 17 Sep 2026): the C12 outcome scorer runs after every completed evening run.

The scorer (`python -m avshunter.c12_outcome all`) is measurement only: it ingests recorded books, scores
underlying and expression outcomes, conditions and matched base rates, and writes the outcome report.
In the evening path it is a NON-CRITICAL, OBSERVATION_ONLY stage (same contract as outcome maturation):

  S1 it runs the scorer CLI as a subprocess from the repository root and publishes a summary artefact
     in the run's diagnostics folder with the scorer's own JSON result;
  S2 a non-zero exit is a named FAILED status with the error tail, never an exception;
  S3 a timeout or launch error is a named status, never an exception;
  S4 the stage grants no authority (OBSERVATION_ONLY, can_grant_capital False);
  S5 evening_workflow calls it after run_meta is closed as COMPLETED and before the completion banner,
     so the book it scores is the finished one.
"""

from __future__ import annotations

import inspect
import json
import subprocess
from pathlib import Path
from unittest.mock import patch

import intelligent_orchestrator as orchestrator


class _Runner:
    def __init__(self, result=None, exc=None):
        self.result, self.exc, self.calls = result, exc, []

    def __call__(self, cmd, **kwargs):
        self.calls.append((cmd, kwargs))
        if self.exc:
            raise self.exc
        return self.result


def _run_stage(tmp_path: Path, runner):
    with patch.object(orchestrator.cfg, "RUNS_DIR", tmp_path / "runs"):
        return orchestrator.run_c12_outcome_scoring_stage("20260917_223000", runner=runner)


def test_s1_runs_scorer_cli_and_publishes_its_result(tmp_path):
    payload = {"as_of": "2026-09-17", "report": "Enhancements/outcomes/2026-09-17/outcome_report.md",
               "score": {"written": 10}}
    runner = _Runner(subprocess.CompletedProcess(args=[], returncode=0, stdout=json.dumps(payload), stderr=""))
    summary = _run_stage(tmp_path, runner)
    cmd, kwargs = runner.calls[0]
    assert cmd[1:] == ["-m", "avshunter.c12_outcome", "all"]
    assert Path(kwargs["cwd"]) == Path(orchestrator.cfg.BASE_DIR)
    assert summary["status"] == "COMPLETED"
    assert summary["scorer_result"]["report"] == payload["report"]
    artefact = tmp_path / "runs" / "20260917_223000" / "diagnostics" / "outcome_scoring_20260917_223000.json"
    assert json.loads(artefact.read_text(encoding="utf-8"))["status"] == "COMPLETED"


def test_s2_non_zero_exit_is_named_failure(tmp_path):
    runner = _Runner(subprocess.CompletedProcess(args=[], returncode=2, stdout="", stderr="CONFIG ERROR: boom"))
    summary = _run_stage(tmp_path, runner)
    assert summary["status"] == "FAILED"
    assert "CONFIG ERROR: boom" in summary["reason"]


def test_s3_timeout_and_launch_errors_are_named(tmp_path):
    timeout = _run_stage(tmp_path, _Runner(exc=subprocess.TimeoutExpired(cmd="x", timeout=1)))
    assert timeout["status"] == "FAILED" and "TIMEOUT" in timeout["reason"]
    error = _run_stage(tmp_path, _Runner(exc=OSError("cannot start")))
    assert error["status"] == "FAILED" and "cannot start" in error["reason"]


def test_s4_stage_grants_no_authority(tmp_path):
    runner = _Runner(subprocess.CompletedProcess(args=[], returncode=0, stdout="{}", stderr=""))
    summary = _run_stage(tmp_path, runner)
    assert summary["authority"] == "OBSERVATION_ONLY" and summary["can_grant_capital"] is False


def test_s5_evening_workflow_scores_after_run_is_completed():
    source = inspect.getsource(orchestrator.evening_workflow)
    closed = source.index('_update_run_meta_status(canonical_run_id, "COMPLETED"')
    scored = source.index("run_c12_outcome_scoring_stage(canonical_run_id)")
    banner = source.index("EVENING WORKFLOW COMPLETE")
    assert closed < scored < banner
