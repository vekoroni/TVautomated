"""Application adapter from the exchange clock to Session Authority domain."""

from __future__ import annotations

from datetime import datetime, timezone

from canonical_data.session_clock import session_snapshot
from domain.session_authority import (
    SessionAuthorityDecision,
    SessionFacts,
    SessionPhase,
    resolve_session_authority,
)


def resolve_pipeline_session_authority(
    *,
    requested_mode: str = "AUTO",
    as_of_utc: datetime | None = None,
) -> SessionAuthorityDecision:
    instant = as_of_utc or datetime.now(timezone.utc)
    if instant.tzinfo is None:
        raise ValueError("session authority requires a timezone-aware instant")
    snapshot = session_snapshot(instant)
    facts = SessionFacts(
        phase=SessionPhase(snapshot.state.value),
        last_completed_session=snapshot.last_completed_session,
        current_session=snapshot.session_date,
    )
    return resolve_session_authority(requested_mode=requested_mode, facts=facts)

