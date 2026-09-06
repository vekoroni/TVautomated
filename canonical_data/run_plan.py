"""Compatibility façade for the Run Planning bounded context.

New code should import business types from :mod:`domain.run_planning` and the
repository from :mod:`canonical_data.run_plan_store`.  This façade preserves
the established import contract while translating the exchange clock into
pure domain facts.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Iterable, Mapping

from domain.run_planning import (
    AuthorityCeiling,
    DatasetRequirement,
    RequestedAction,
    RunPlan,
    RunPlanningContext,
    contract_episode_identity,
    evidence_identity,
    quote_observation_identity,
    resolve_plan,
    thesis_identity,
    validation_event_identity,
)
from domain.session_authority import SessionFacts, SessionPhase

from .run_plan_store import RunPlanStore, write_plan_atomic
from .session_clock import session_snapshot


def _normalise_instant(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("as_of_utc and evidence_cutoff_utc must be timezone-aware")
    return value.astimezone(timezone.utc).replace(microsecond=0)


def resolve_run_plan(
    *,
    requested_action: RequestedAction | str = RequestedAction.AUTO,
    as_of_utc: datetime,
    evidence_cutoff_utc: datetime | None = None,
    exchange_calendar: str = "XNYS",
    existing_thesis_id: str | None = None,
    existing_thesis_session: date | None = None,
    authorised_tickers: Iterable[str] = (),
    provider_session_finalised: bool = False,
    cache_coverage: Mapping[str, int] | None = None,
    pipeline_run_id: str | None = None,
    retry_of_invocation_id: str | None = None,
    supersedes_invocation_id: str | None = None,
) -> RunPlan:
    """Translate infrastructure time into facts and invoke the pure domain."""

    as_of = _normalise_instant(as_of_utc)
    cutoff = _normalise_instant(evidence_cutoff_utc or as_of)
    snapshot = session_snapshot(as_of)
    return resolve_plan(
        requested_action=requested_action,
        context=RunPlanningContext(
            as_of_utc=as_of,
            evidence_cutoff_utc=cutoff,
            session_facts=SessionFacts(
                phase=SessionPhase(snapshot.state.value),
                last_completed_session=snapshot.last_completed_session,
                current_session=snapshot.session_date,
            ),
            exchange_calendar=exchange_calendar,
            existing_thesis_id=existing_thesis_id,
            existing_thesis_session=existing_thesis_session,
            authorised_tickers=tuple(authorised_tickers),
            provider_session_finalised=provider_session_finalised,
            cache_coverage=cache_coverage,
            pipeline_run_id=pipeline_run_id,
            retry_of_invocation_id=retry_of_invocation_id,
            supersedes_invocation_id=supersedes_invocation_id,
        ),
    )


__all__ = [
    "AuthorityCeiling",
    "DatasetRequirement",
    "RequestedAction",
    "RunPlan",
    "RunPlanStore",
    "contract_episode_identity",
    "evidence_identity",
    "quote_observation_identity",
    "resolve_run_plan",
    "thesis_identity",
    "validation_event_identity",
    "write_plan_atomic",
]
