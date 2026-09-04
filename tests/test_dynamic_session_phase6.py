from __future__ import annotations

import csv
from datetime import date, datetime, timezone
import json
from pathlib import Path
import sqlite3

import pytest

from canonical_data.run_plan import RequestedAction, resolve_run_plan
from orchestrator.dynamic_dispatcher import (
    execute_dispatch_plan,
    operator_summary,
    persist_dispatch_plan,
    requested_action_from_cli,
    resolve_accepted_thesis,
    resolve_dispatch_plan,
)


def _accepted_run(root: Path, run_id: str = "20260904_220000", *, sessions=("2026-09-04",)) -> Path:
    output = root / "output"
    run = output / "runs" / run_id
    lab = run / "intelligence_lab"
    lab.mkdir(parents=True)
    (output / "latest.json").write_text(json.dumps({"run_id": run_id}), encoding="utf-8")
    (run / "run_meta.json").write_text(
        json.dumps({"run_status": "COMPLETED"}), encoding="utf-8"
    )
    book = lab / f"final_opportunity_book_{run_id}.csv"
    with book.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=("ticker", "thesis_id", "evidence_session_date")
        )
        writer.writeheader()
        for index, session in enumerate(sessions):
            ticker = ("AAPL", "MSFT")[index % 2]
            writer.writerow(
                {
                    "ticker": ticker,
                    "thesis_id": f"{ticker}:CALL:{session}:OLM2",
                    "evidence_session_date": session,
                }
            )
    return output


def test_resolver_uses_governed_pointer_and_explicit_session(tmp_path: Path) -> None:
    output = _accepted_run(tmp_path)
    thesis = resolve_accepted_thesis(output)
    assert thesis is not None
    assert thesis.pipeline_run_id == "20260904_220000"
    assert thesis.completed_session == date(2026, 9, 4)
    assert thesis.authorised_tickers == ("AAPL",)
    assert thesis.source_sha256


def test_resolver_rejects_mixed_completed_sessions(tmp_path: Path) -> None:
    output = _accepted_run(tmp_path, sessions=("2026-09-03", "2026-09-04"))
    with pytest.raises(ValueError, match="ambiguous completed sessions"):
        resolve_accepted_thesis(output)


def test_resolver_ignores_unaccepted_run(tmp_path: Path) -> None:
    output = _accepted_run(tmp_path)
    meta = output / "runs" / "20260904_220000" / "run_meta.json"
    meta.write_text(json.dumps({"run_status": "FAILED"}), encoding="utf-8")
    assert resolve_accepted_thesis(output) is None


def test_cli_compatibility_switches_have_one_action() -> None:
    assert requested_action_from_cli(evening=True) is RequestedAction.BUILD_THESIS
    assert requested_action_from_cli(morning=True) is RequestedAction.VALIDATE
    assert requested_action_from_cli(premarket=True) is RequestedAction.VALIDATE
    assert requested_action_from_cli(auto=True) is RequestedAction.AUTO
    with pytest.raises(ValueError, match="exactly one"):
        requested_action_from_cli(evening=True, morning=True)


def test_plan_preview_is_read_only_and_current_closed_thesis_is_reused(tmp_path: Path) -> None:
    output = _accepted_run(tmp_path)
    before = sorted(str(path.relative_to(tmp_path)) for path in tmp_path.rglob("*"))
    plan, thesis = resolve_dispatch_plan(
        output_dir=output,
        requested_action="AUTO",
        as_of_utc=datetime(2026, 9, 5, 12, tzinfo=timezone.utc),
    )
    after = sorted(str(path.relative_to(tmp_path)) for path in tmp_path.rglob("*"))
    assert before == after
    assert thesis is not None
    assert plan.resolved_action == "AUTO"
    assert plan.stages_to_run == ()
    assert plan.estimated_physical_requests == 0


def test_after_hours_old_thesis_waits_then_finalises_without_overwrite(tmp_path: Path) -> None:
    output = _accepted_run(tmp_path, sessions=("2026-09-03",))
    common = dict(
        output_dir=output,
        requested_action="AUTO",
        as_of_utc=datetime(2026, 9, 4, 21, tzinfo=timezone.utc),
    )
    partial, _ = resolve_dispatch_plan(**common, provider_session_finalised=False)
    finalised, _ = resolve_dispatch_plan(**common, provider_session_finalised=True)
    assert partial.resolved_action == "VALIDATE"
    assert partial.pipeline_run_id == "20260904_220000"
    assert finalised.resolved_action == "FINALISE"
    assert finalised.pipeline_run_id != "20260904_220000"


def test_explicit_morning_retains_selected_run_identity(tmp_path: Path) -> None:
    output = _accepted_run(tmp_path)
    plan, _ = resolve_dispatch_plan(
        output_dir=output,
        requested_action="VALIDATE",
        as_of_utc=datetime(2026, 9, 8, 12, tzinfo=timezone.utc),
    )
    assert plan.pipeline_run_id == "20260904_220000"
    assert plan.resolved_action == "VALIDATE"


def test_plan_persistence_precedes_execution_and_is_idempotent(tmp_path: Path) -> None:
    plan = resolve_run_plan(
        requested_action="BUILD_THESIS",
        as_of_utc=datetime(2026, 9, 5, 12, tzinfo=timezone.utc),
        pipeline_run_id="run-new",
    )
    output = tmp_path / "output"
    database = tmp_path / "canonical" / "plans.sqlite"
    path, inserted = persist_dispatch_plan(
        plan, output_dir=output, plan_store_path=database
    )
    second_path, second_inserted = persist_dispatch_plan(
        plan, output_dir=output, plan_store_path=database
    )
    assert path == second_path and path.is_file()
    assert inserted is True and second_inserted is False
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT COUNT(*) FROM run_plans").fetchone()[0] == 1


def test_dispatch_executes_only_resolved_callback() -> None:
    plan = resolve_run_plan(
        requested_action="VALIDATE",
        as_of_utc=datetime(2026, 9, 8, 12, tzinfo=timezone.utc),
        existing_thesis_id="book-1",
        existing_thesis_session=date(2026, 9, 4),
        pipeline_run_id="run-1",
    )
    calls: list[str] = []
    result = execute_dispatch_plan(
        plan,
        callbacks={"VALIDATE": lambda value: calls.append(value.plan_hash) or True},
    )
    assert result.success and result.executed and not result.reused
    assert calls == [plan.plan_hash]


def test_operator_summary_exposes_action_cost_and_authority(tmp_path: Path) -> None:
    output = _accepted_run(tmp_path)
    plan, thesis = resolve_dispatch_plan(
        output_dir=output,
        requested_action="AUTO",
        as_of_utc=datetime(2026, 9, 5, 12, tzinfo=timezone.utc),
    )
    summary = operator_summary(plan, thesis)
    assert "resolved=AUTO" in summary
    assert "requests<=0" in summary
    assert "ceiling=REVIEW_ONLY" in summary


def test_completed_profile_stage_uses_frozen_thesis_flag() -> None:
    source = (Path(__file__).parents[1] / "intelligent_orchestrator.py").read_text(
        encoding="utf-8"
    )
    assert "AVSHUNTER_COMPLETED_PROFILE_ENABLED" not in source
    assert 'COMPLETED_PROFILE_ENABLED = os.environ.get(\n        "AVSHUNTER_DYNAMIC_THESIS_ENABLED"' in source
