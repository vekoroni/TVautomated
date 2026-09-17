"""Decision clock (pure): every context derives session facts from one instant."""

from __future__ import annotations

from datetime import datetime

from avshunter.shared.xnys_calendar import session_state

from .model import DecisionClock


def build_decision_clock(instant: datetime) -> DecisionClock:
    phase, market_session, evidence_session = session_state(instant)
    return DecisionClock(
        decision_clock_utc=instant,
        session_phase=phase,
        market_session=market_session,
        evidence_session=evidence_session,
    )
