"""Adapter to the legacy orchestrator (read-only plan resolution and run hand-off)."""

from __future__ import annotations

from datetime import date, datetime
import json
import os
from pathlib import Path
import re
import subprocess
import sys

from ..model import Action, ThesisFacts

ENTRYPOINT = "intelligent_orchestrator.py"
ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
ACTION_SWITCH = {Action.BUILD: "--evening", Action.REVALUE: "--morning"}


def legacy_command(action: Action, interpreter: str | None = None) -> tuple[str, ...]:
    return (interpreter or sys.executable, ENTRYPOINT, ACTION_SWITCH[action])


def _last_json_object(text: str) -> dict:
    end = text.rfind("}")
    while end != -1:
        start = text.rfind("\n{", 0, end)
        candidate_start = start + 1 if start != -1 else (0 if text.startswith("{") else -1)
        if candidate_start == -1:
            break
        try:
            return json.loads(text[candidate_start:end + 1])
        except json.JSONDecodeError:
            end = text.rfind("}", 0, end)
    raise ValueError("no JSON plan found in legacy --plan-only output")


def thesis_session_from_id(thesis_id: str | None) -> date | None:
    if not thesis_id:
        return None
    for part in str(thesis_id).split(":"):
        if ISO_DATE.fullmatch(part):
            try:
                return date.fromisoformat(part)
            except ValueError:
                return None
    return None


def resolve_revalue_thesis(repo: Path, decision_clock_utc: datetime, env: dict[str, str]) -> ThesisFacts:
    """Ask the legacy dispatcher which thesis a morning run would validate (no side effects)."""
    command = [
        sys.executable, ENTRYPOINT, "--morning", "--plan-only",
        "--as-of-utc", decision_clock_utc.isoformat(),
    ]
    result = subprocess.run(
        command, cwd=str(repo), env=env, capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    try:
        plan = _last_json_object(result.stdout)
    except ValueError as error:
        return ThesisFacts(None, None, None, None, plan_error=f"{error}; exit={result.returncode}")
    thesis_id = plan.get("existing_thesis_id")
    last_completed = plan.get("last_completed_session")
    return ThesisFacts(
        existing_thesis_id=thesis_id,
        thesis_session=thesis_session_from_id(thesis_id),
        plan_last_completed_session=date.fromisoformat(last_completed) if last_completed else None,
        plan_resolved_action=plan.get("resolved_action"),
    )


def run_legacy(repo: Path, command: tuple[str, ...], env: dict[str, str]) -> int:
    """Run the legacy orchestrator with output streamed to the operator's console."""
    return subprocess.call(list(command), cwd=str(repo), env=env)


def child_environment(base: dict[str, str], flags: dict[str, str], extra: dict[str, str]) -> dict[str, str]:
    env = dict(base)
    env.update(flags)
    env.update(extra)
    return env


def latest_legacy_run(repo: Path) -> dict[str, object]:
    output = repo / "data" / "output"
    try:
        latest = json.loads((output / "latest.json").read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as error:
        return {"error": repr(error)}
    run_id = str(latest.get("run_id") or "")
    summary: dict[str, object] = {"legacy_run_id": run_id}
    try:
        meta = json.loads((output / "runs" / run_id / "run_meta.json").read_text(encoding="utf-8-sig"))
        for key in ("run_status", "session_date", "run_condition", "baseline_eligible", "pipeline_mode"):
            summary[key] = meta.get(key)
    except (OSError, json.JSONDecodeError) as error:
        summary["run_meta_error"] = repr(error)
    return summary


def base_environment() -> dict[str, str]:
    return dict(os.environ)
