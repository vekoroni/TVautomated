"""Pure domain policy for selecting evidence used by a pipeline invocation.

The thesis-building pipeline is run-anytime, but its evidence authority is not
time-agnostic: completed-session evidence may form a thesis; a current-session
snapshot may only enrich or validate one.  This module owns that distinction.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum


class SessionPhase(str, Enum):
    CLOSED = "CLOSED"
    PREMARKET = "PREMARKET"
    REGULAR = "REGULAR"
    AFTER_HOURS = "AFTER_HOURS"


class EvidenceMode(str, Enum):
    AUTO = "AUTO"
    COMPLETED = "COMPLETED"
    CURRENT = "CURRENT"


class EvidenceState(str, Enum):
    COMPLETED_SESSION = "COMPLETED_SESSION"
    CURRENT_SNAPSHOT = "CURRENT_SNAPSHOT"


class EvidenceAuthority(str, Enum):
    EOD_PREPARED = "EOD_PREPARED"
    REVIEW_ONLY = "REVIEW_ONLY"


@dataclass(frozen=True, slots=True)
class SessionFacts:
    phase: SessionPhase
    last_completed_session: date
    current_session: date | None


@dataclass(frozen=True, slots=True)
class SessionAuthorityDecision:
    requested_mode: EvidenceMode
    resolved_mode: EvidenceMode
    evidence_state: EvidenceState
    evidence_session: date
    provider_query_end: date
    include_developing_bar: bool
    authority_ceiling: EvidenceAuthority
    reason_code: str

    @property
    def legacy_data_mode(self) -> str:
        """Compatibility translation for existing calculation stages."""
        return "LATEST" if self.resolved_mode is EvidenceMode.CURRENT else "EOD"


def _normalise_mode(value: EvidenceMode | str) -> EvidenceMode:
    raw = str(getattr(value, "value", value)).strip().upper()
    aliases = {
        "EOD": EvidenceMode.COMPLETED,
        "COMPLETED_SESSION": EvidenceMode.COMPLETED,
        "LATEST": EvidenceMode.CURRENT,
        "CURRENT_SESSION": EvidenceMode.CURRENT,
    }
    if raw in aliases:
        return aliases[raw]
    return EvidenceMode(raw)


def resolve_session_authority(
    *,
    requested_mode: EvidenceMode | str,
    facts: SessionFacts,
) -> SessionAuthorityDecision:
    """Resolve one authoritative evidence contract without external effects.

    ``AUTO`` deliberately resolves to completed evidence for thesis building.
    The time at which the command is run never grants a developing bar the
    authority of a completed exchange session.
    """

    requested = _normalise_mode(requested_mode)
    if requested in {EvidenceMode.AUTO, EvidenceMode.COMPLETED}:
        return SessionAuthorityDecision(
            requested_mode=requested,
            resolved_mode=EvidenceMode.COMPLETED,
            evidence_state=EvidenceState.COMPLETED_SESSION,
            evidence_session=facts.last_completed_session,
            provider_query_end=facts.last_completed_session,
            include_developing_bar=False,
            authority_ceiling=EvidenceAuthority.EOD_PREPARED,
            reason_code="LAST_COMPLETED_SESSION_FOR_THESIS",
        )

    current_is_observable = (
        facts.current_session is not None
        and facts.phase
        in {SessionPhase.PREMARKET, SessionPhase.REGULAR, SessionPhase.AFTER_HOURS}
    )
    evidence_session = (
        facts.current_session if current_is_observable else facts.last_completed_session
    )
    return SessionAuthorityDecision(
        requested_mode=requested,
        resolved_mode=EvidenceMode.CURRENT,
        evidence_state=EvidenceState.CURRENT_SNAPSHOT,
        evidence_session=evidence_session,
        # Historical daily data is always bounded by the completed-session
        # authority.  Any current bar is appended separately and labelled.
        provider_query_end=facts.last_completed_session,
        include_developing_bar=(facts.phase is SessionPhase.REGULAR),
        authority_ceiling=EvidenceAuthority.REVIEW_ONLY,
        reason_code=(
            "CURRENT_SESSION_REVIEW"
            if current_is_observable
            else "NO_CURRENT_SESSION_REUSE_LAST_COMPLETED"
        ),
    )
