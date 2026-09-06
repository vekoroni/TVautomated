from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from canonical_data.run_plan import resolve_run_plan
from canonical_data.run_plan_store import RunPlanStore
from domain.run_planning import (
    RequestedAction,
    RunPlanningContext,
    resolve_plan,
)
from domain.session_authority import SessionFacts, SessionPhase


ROOT = Path(__file__).resolve().parents[1]


def _context(
    phase: SessionPhase,
    *,
    thesis_id: str | None = None,
    thesis_session: date | None = None,
    finalised: bool = False,
) -> RunPlanningContext:
    instant = datetime(2026, 9, 8, 15, tzinfo=timezone.utc)
    return RunPlanningContext(
        as_of_utc=instant,
        evidence_cutoff_utc=instant,
        session_facts=SessionFacts(
            phase=phase,
            last_completed_session=date(2026, 9, 4),
            current_session=date(2026, 9, 8),
        ),
        existing_thesis_id=thesis_id,
        existing_thesis_session=thesis_session,
        authorised_tickers=("msft", "AAPL"),
        provider_session_finalised=finalised,
        pipeline_run_id="DDD_PLAN_TEST",
    )


@pytest.mark.parametrize(
    ("phase", "thesis_id", "thesis_session", "finalised", "expected"),
    [
        (SessionPhase.PREMARKET, None, None, False, "BUILD_THESIS"),
        (SessionPhase.PREMARKET, "thesis", date(2026, 9, 4), False, "VALIDATE"),
        (SessionPhase.REGULAR, "thesis", date(2026, 9, 4), False, "VALIDATE"),
        (SessionPhase.AFTER_HOURS, "thesis", date(2026, 9, 4), False, "VALIDATE"),
        (SessionPhase.AFTER_HOURS, "thesis", date(2026, 9, 4), True, "FINALISE"),
        (SessionPhase.CLOSED, "thesis", date(2026, 9, 4), False, "AUTO"),
    ],
)
def test_pure_domain_resolves_business_action(
    phase, thesis_id, thesis_session, finalised, expected
) -> None:
    plan = resolve_plan(
        requested_action=RequestedAction.AUTO,
        context=_context(
            phase,
            thesis_id=thesis_id,
            thesis_session=thesis_session,
            finalised=finalised,
        ),
    )
    assert plan.resolved_action == expected
    assert plan.last_completed_session == "2026-09-04"


def test_clock_facade_and_pure_domain_have_parity() -> None:
    instant = datetime(2026, 9, 8, 15, tzinfo=timezone.utc)
    facade = resolve_run_plan(
        as_of_utc=instant,
        existing_thesis_id="thesis",
        existing_thesis_session=date(2026, 9, 4),
        authorised_tickers=("msft", "AAPL"),
        pipeline_run_id="DDD_PLAN_TEST",
    )
    pure = resolve_plan(
        context=_context(
            SessionPhase.REGULAR,
            thesis_id="thesis",
            thesis_session=date(2026, 9, 4),
        )
    )
    assert facade.to_dict() == pure.to_dict()


def test_domain_module_has_no_infrastructure_dependencies() -> None:
    source = (ROOT / "domain" / "run_planning.py").read_text(encoding="utf-8")
    forbidden = (
        "import sqlite3",
        "from pathlib import Path",
        "import os",
        "canonical_data",
        "urllib",
        "pandas",
    )
    assert not [token for token in forbidden if token in source]


def test_repository_is_append_only_and_rejects_forged_retry(tmp_path: Path) -> None:
    store = RunPlanStore(tmp_path / "plans.sqlite")
    plan = resolve_plan(context=_context(SessionPhase.PREMARKET))
    assert store.persist(plan) is True
    assert store.persist(plan) is False
    assert store.load(plan.invocation_id)["plan_hash"] == plan.plan_hash

    forged = replace(plan, plan_hash="")
    object.__setattr__(forged, "expected_outputs", ("forged",))
    object.__setattr__(forged, "plan_hash", forged.compute_hash())
    with pytest.raises(ValueError, match="different immutable plan content"):
        store.persist(forged)


def test_legacy_facade_preserves_public_contract() -> None:
    from canonical_data import run_plan as facade

    assert facade.RequestedAction is RequestedAction
    assert facade.RunPlanStore is RunPlanStore
    assert callable(facade.thesis_identity)
    assert callable(facade.validation_event_identity)
