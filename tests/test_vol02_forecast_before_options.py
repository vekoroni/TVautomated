"""VOL-02 (orchestrator half): the forecast exists before Options Intelligence values a contract.

Business rule (ACK, 21 Nov 2026: worklist approved, "build all fixes that are feasible before the run"; Codex brief
BF-01 / VOL-02):

  The price forecast is produced from the run's Discovery candidates before Options Intelligence runs, so the contract
  valuer finds the current run's forecast instead of none. The stage needs no Options, SuperBrain or execution-layer
  file. It is evidence, not authority: when it cannot run, the reason is recorded and the Evening continues.

  The later forecast stage after the execution layer stays: it adds the comparison with the 30-day IV and delivers the
  columns to the files that are written after Options. The pre-Options result is kept in its own folder, so what the
  valuer could see is not overwritten.

Legacy behaviour replaced: the forecast ran only after the execution layer, from a ticker list written after Options.
On runs 14, 18 and 19 Nov every selected row was VALUE_INPUTS_UNAVAILABLE with forecast source UNAVAILABLE.

Isolated: temporary run folder; the runner process is replaced; no provider, no network.
"""
from __future__ import annotations

import inspect
import json
from pathlib import Path

import pytest

import intelligent_orchestrator as orch

RUN_ID = "20261119_234734"


@pytest.fixture
def run_root(tmp_path, monkeypatch):
    runs = tmp_path / "runs"
    root = runs / RUN_ID
    (root / "discovery").mkdir(parents=True)
    (root / "discovery" / f"discovery_candidates_ultimate_{RUN_ID}.csv").write_text("ticker\nAAA\nBBB\n", encoding="utf-8")
    monkeypatch.setattr(orch.cfg, "RUNS_DIR", runs)
    monkeypatch.setattr(orch.cfg, "OUTPUT_DIR", tmp_path / "output")
    return root


def _fake_runner(root: Path, calls: list, *, ok: bool = True, write: bool = True):
    def run(name, cmd, critical=True, **_kwargs):
        calls.append({"name": name, "cmd": [str(part) for part in cmd], "critical": critical})
        if ok and write:
            out = root / "qomega"
            out.mkdir(parents=True, exist_ok=True)
            (out / f"garch_forecasts_{RUN_ID}.csv").write_text("ticker,l3_forecast_state\nAAA,FORECAST_OK\nBBB,FORECAST_OK\n", encoding="utf-8")
            (out / f"garch_forecast_receipt_{RUN_ID}.json").write_text(json.dumps({"worklist_kind": "EXPLICIT_WORKLIST"}), encoding="utf-8")
        return ok
    return run


def test_the_forecast_is_built_from_the_discovery_worklist_with_no_options_file(run_root, monkeypatch):
    calls: list = []
    monkeypatch.setattr(orch, "_run", _fake_runner(run_root, calls))

    state = orch.run_pre_options_forecast(RUN_ID)

    assert state == "PUBLISHED"
    cmd = calls[0]["cmd"]
    assert "--worklist_csv" in cmd and cmd[cmd.index("--worklist_csv") + 1].endswith(f"discovery_candidates_ultimate_{RUN_ID}.csv")
    assert "--superbrain_csv" not in cmd
    assert calls[0]["critical"] is False                                   # never a run-stopping stage
    assert not (run_root / "options").exists() and not (run_root / "superbrain").exists()


def test_what_the_valuer_could_see_is_kept_apart_from_the_later_stage(run_root, monkeypatch):
    monkeypatch.setattr(orch, "_run", _fake_runner(run_root, []))

    orch.run_pre_options_forecast(RUN_ID)

    kept = run_root / "qomega" / "pre_options"
    assert (kept / f"garch_forecasts_{RUN_ID}.csv").read_text(encoding="utf-8").count("FORECAST_OK") == 2
    assert (kept / f"garch_forecast_receipt_{RUN_ID}.json").is_file()
    status = json.loads((kept / "status.json").read_text(encoding="utf-8"))
    assert status["state"] == "PUBLISHED" and status["authority"] == "EVIDENCE_ONLY" and status["forecast_rows"] == 2


@pytest.mark.parametrize("ok, write", [(False, False), (True, False)])
def test_a_failed_or_empty_forecast_is_recorded_and_the_evening_continues(run_root, monkeypatch, ok, write):
    monkeypatch.setattr(orch, "_run", _fake_runner(run_root, [], ok=ok, write=write))

    state = orch.run_pre_options_forecast(RUN_ID)

    assert state == "UNAVAILABLE"
    status = json.loads((run_root / "qomega" / "pre_options" / "status.json").read_text(encoding="utf-8"))
    assert status["state"] == "UNAVAILABLE" and status["reason"]


def test_a_missing_worklist_is_recorded_not_raised(run_root, monkeypatch):
    (run_root / "discovery" / f"discovery_candidates_ultimate_{RUN_ID}.csv").unlink()
    monkeypatch.setattr(orch, "_run", lambda *a, **k: pytest.fail("the runner must not start without a worklist"))

    assert orch.run_pre_options_forecast(RUN_ID) == "UNAVAILABLE"
    status = json.loads((run_root / "qomega" / "pre_options" / "status.json").read_text(encoding="utf-8"))
    assert "worklist" in status["reason"].lower()


def test_an_unexpected_error_never_reaches_the_evening(run_root, monkeypatch):
    def boom(*_a, **_k):
        raise RuntimeError("runner crashed")

    monkeypatch.setattr(orch, "_run", boom)

    assert orch.run_pre_options_forecast(RUN_ID) == "UNAVAILABLE"


def test_the_evening_runs_the_forecast_before_options_and_keeps_the_later_stage():
    source = inspect.getsource(orch.evening_workflow)

    before = source.index("run_pre_options_forecast(canonical_run_id)")
    options = source.index("if not run_options_intelligence(")
    assert source.index("_publish_pre_option_forecast_packet(canonical_run_id)") < before < options
    assert "run_garch_layer(canonical_run_id)" in source                    # the IV comparison and delivery stage stays
    assert source.index("run_garch_layer(canonical_run_id)") > options
