"""P0-3: decision clock, pre-flight gate (Option A), run context, legacy flags."""

from __future__ import annotations

from datetime import date, datetime, timezone
import json

import pytest

from avshunter.c0_run.clock import build_decision_clock
from avshunter.c0_run.context import build_run_context, resolve_legacy_flags
from avshunter.c0_run.model import (
    Action,
    CheckOutcome,
    EnvironmentFacts,
    GateVerdict,
    GitFacts,
    OperatorMode,
    ThesisFacts,
)
from avshunter.c0_run.preflight import evaluate_preflight
from avshunter.config import ConfigRegistry
from avshunter.config.adapters import load_documents, load_lock
from avshunter.shared.xnys_calendar import SessionPhase

INTERPRETER = r"C:\Users\ACKVerissimo\AVSHUNTER-Intelligence\venv\Scripts\python.exe"
EVENING = datetime(2026, 9, 17, 21, 30, tzinfo=timezone.utc)   # 17:30 ET, after the close
MORNING = datetime(2026, 9, 18, 13, 45, tzinfo=timezone.utc)   # 09:45 ET


def snapshot_for(session: date, **overrides):
    documents = load_documents()
    if overrides:
        for document in documents:
            for entry in document["entries"]:
                if entry["config_key"] in overrides:
                    entry["value"] = overrides[entry["config_key"]]
        return ConfigRegistry.from_documents(documents).resolve(session)
    return ConfigRegistry.from_documents(documents, load_lock()).resolve(session)


def git_facts(**overrides) -> GitFacts:
    base = dict(
        commit_hash="abc123", describe="rel-20260917-1", head_tags=("rel-20260917-1",),
        modified_tracked_files=(), untracked_production_files=(), untracked_imported_modules=(),
    )
    base.update(overrides)
    return GitFacts(**base)


def env_facts(**overrides) -> EnvironmentFacts:
    base = dict(python_executable=INTERPRETER, python_version="3.14.0", host="test",
                shell_flags={}, running_data_writers=())
    base.update(overrides)
    return EnvironmentFacts(**base)


def thesis(session: date | None) -> ThesisFacts:
    tid = f"book:run:{session.isoformat()}:hash" if session else None
    return ThesisFacts(tid, session, session, "VALIDATE")


def gate(action=Action.BUILD, mode=OperatorMode.PRODUCTION, instant=EVENING, git=None, env=None,
         thesis_facts=None, snapshot=None):
    clock = build_decision_clock(instant)
    session = clock.evidence_session if action is Action.BUILD else clock.market_session
    return evaluate_preflight(
        action=action, requested_mode=mode, clock=clock, git=git or git_facts(), environment=env or env_facts(),
        snapshot=snapshot or snapshot_for(session), thesis=thesis_facts,
    )


def outcome(result, check_id):
    return next(c.outcome for c in result.checks if c.check_id == check_id)


# --- decision clock -----------------------------------------------------------

def test_decision_clock_sessions():
    evening = build_decision_clock(EVENING)
    assert (evening.session_phase, evening.evidence_session) == (SessionPhase.AFTER_HOURS, date(2026, 9, 17))
    overnight = build_decision_clock(datetime(2026, 9, 17, 1, 0, tzinfo=timezone.utc))
    assert (overnight.session_phase, overnight.evidence_session) == (SessionPhase.CLOSED, date(2026, 9, 16))
    morning = build_decision_clock(MORNING)
    assert (morning.session_phase, morning.market_session, morning.evidence_session) == (
        SessionPhase.REGULAR, date(2026, 9, 18), date(2026, 9, 17))


# --- gate verdicts ------------------------------------------------------------

def test_clean_release_proceeds_in_production():
    result = gate()
    assert result.verdict is GateVerdict.PROCEED
    assert result.effective_mode is OperatorMode.PRODUCTION


@pytest.mark.parametrize("git_overrides, env_overrides, failing_check", [
    ({"modified_tracked_files": ("x.py",)}, {}, "CLEAN_TREE"),
    ({"untracked_production_files": ("scripts/new.py",)}, {}, "CLEAN_TREE"),
    ({"head_tags": ()}, {}, "RELEASE_TAG_AT_HEAD"),
    ({}, {"python_executable": r"C:\Python314\python.exe"}, "PRODUCTION_INTERPRETER"),
])
def test_release_failures_downgrade_production_to_research(git_overrides, env_overrides, failing_check):
    result = gate(git=git_facts(**git_overrides), env=env_facts(**env_overrides))
    assert result.verdict is GateVerdict.PROCEED_DOWNGRADED
    assert result.effective_mode is OperatorMode.RESEARCH
    assert outcome(result, failing_check) is CheckOutcome.FAIL
    assert "DOWNGRADED TO RESEARCH" in result.banner()


def test_release_failures_do_not_affect_research_requests():
    result = gate(mode=OperatorMode.RESEARCH, git=git_facts(head_tags=()))
    assert (result.verdict, result.effective_mode) == (GateVerdict.PROCEED, OperatorMode.RESEARCH)


def test_refuse_mode_from_configuration():
    snap = snapshot_for(date(2026, 9, 17), **{"run.production_gate_failure_mode": "REFUSE"})
    result = gate(git=git_facts(head_tags=()), snapshot=snap)
    assert result.verdict is GateVerdict.REFUSE


@pytest.mark.parametrize("mode", list(OperatorMode))
def test_concurrent_writer_blocks_in_every_mode(mode):
    result = gate(mode=mode, env=env_facts(running_data_writers=("pid 1: run_phantom_backfill",)))
    assert result.verdict is GateVerdict.REFUSE
    assert result.effective_mode is None


def test_untracked_import_blocks():
    result = gate(git=git_facts(untracked_imported_modules=("worker3/lab_contract.py (imported as worker3.lab_contract)",)))
    assert result.verdict is GateVerdict.REFUSE


def test_build_during_regular_session_blocks():
    # Configuration resolved for the 17 Sep session (a daytime BUILD's evidence session is the prior day).
    result = gate(instant=datetime(2026, 9, 18, 15, 0, tzinfo=timezone.utc), snapshot=snapshot_for(date(2026, 9, 17)))
    assert result.verdict is GateVerdict.REFUSE
    assert outcome(result, "ACTION_MATCHES_SESSION_PHASE") is CheckOutcome.FAIL


def test_revalue_with_current_thesis_proceeds():
    result = gate(action=Action.REVALUE, instant=MORNING, thesis_facts=thesis(date(2026, 9, 17)))
    assert result.verdict is GateVerdict.PROCEED


def test_revalue_with_stale_thesis_is_refused():
    result = gate(action=Action.REVALUE, instant=MORNING, thesis_facts=thesis(date(2026, 9, 16)))
    assert result.verdict is GateVerdict.REFUSE
    assert outcome(result, "THESIS_CURRENT_FOR_REVALUE") is CheckOutcome.FAIL


def test_revalue_without_resolvable_thesis_is_refused():
    missing = ThesisFacts(None, None, None, None, plan_error="no JSON plan")
    assert gate(action=Action.REVALUE, instant=MORNING, thesis_facts=missing).verdict is GateVerdict.REFUSE


def test_revalue_outside_session_is_refused():
    evening_revalue = gate(action=Action.REVALUE, instant=EVENING, thesis_facts=thesis(date(2026, 9, 17)))
    assert evening_revalue.verdict is GateVerdict.REFUSE


# --- legacy flags and context -------------------------------------------------

def test_legacy_flags_come_from_configuration():
    flags = resolve_legacy_flags(snapshot_for(date(2026, 9, 17)))
    assert flags["AVSHUNTER_CANONICAL_DATA_ENABLED"] == "1"
    assert flags["AVSHUNTER_CANONICAL_WRITE_THROUGH"] == "1"
    assert flags["AVSHUNTER_CDS2_OHLCV_MODE"] == "ACTIVE"
    assert flags["AVSHUNTER_DYNAMIC_PLAN_ENABLED"] == "1"
    assert flags["AVSHUNTER_DYNAMIC_AUTO_ENABLED"] == "0"


def test_run_context_is_deterministic_and_serialisable():
    snap = snapshot_for(date(2026, 9, 17))
    clock = build_decision_clock(EVENING)
    kwargs = dict(
        action=Action.BUILD, requested_mode=OperatorMode.PRODUCTION, clock=clock, git=git_facts(head_tags=()),
        environment=env_facts(), snapshot=snap, config_file_hashes={"config/x.json": "h"}, thesis=None,
        created_at_utc=EVENING, legacy_entrypoint=("python", "intelligent_orchestrator.py", "--evening"),
    )
    pre = gate(git=git_facts(head_tags=()))
    first = build_run_context(preflight=pre, **kwargs)
    second = build_run_context(preflight=pre, **kwargs)
    assert first.run_context_id == second.run_context_id
    assert first.run_context_id.startswith("AVS-20260917-213000-BUILD-")
    payload = json.loads(json.dumps(first.to_dict()))
    assert payload["operator_mode"] == "RESEARCH"
    assert payload["release_id"] is None
    assert payload["config_snapshot_id"] == snap.snapshot_id
    assert payload["feature_flags"]["AVSHUNTER_CDS2_OHLCV_MODE"] == "ACTIVE"
