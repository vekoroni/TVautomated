"""C3 dated structure episodes and explicit, non-forced transitions.

The reducer records observed changes; it never assumes an accumulation must
advance on a schedule or substitutes an option outcome for structure evidence.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Sequence


MODES = {"ACCUMULATION", "DISTRIBUTION", "REACCUMULATION", "REDISTRIBUTION", "NO_RANGE", "UNRESOLVED"}
COMPRESSION = {"READY", "COILING", "RELEASING", "NONE", "DATA_INSUFFICIENT"}


@dataclass(frozen=True, slots=True)
class StructureObservation:
    ticker: str
    evidence_session: str
    as_of_utc: str
    mode: str
    phase: str | None
    range_id: str | None
    compression_state: str
    event: str | None
    source_id: str
    source_family: str = "PRICE_VOLUME"

    def __post_init__(self) -> None:
        if not self.ticker or not self.source_id or self.mode not in MODES or self.compression_state not in COMPRESSION:
            raise ValueError("structure observation identity or vocabulary invalid")
        date.fromisoformat(self.evidence_session)
        stamp = datetime.fromisoformat(self.as_of_utc.replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            raise ValueError("structure observation requires an as-of timezone")
        if self.mode in {"NO_RANGE", "UNRESOLVED"} and self.phase is not None:
            raise ValueError("unresolved/no-range mode cannot assert a phase")
        if self.phase is not None and self.phase not in {"A", "B", "C", "D", "E"}:
            raise ValueError("phase must be A–E within an explicit mode")


def describe_structure_transition(previous: StructureObservation | None, current: StructureObservation) -> dict:
    if previous is None:
        state = "NEW_RANGE" if current.range_id else "UNRESOLVED"
        changed = ("INITIAL_OBSERVATION",)
    else:
        if previous.ticker != current.ticker or previous.source_family != current.source_family:
            raise ValueError("structure transition identity mismatch")
        if (date.fromisoformat(current.evidence_session) <= date.fromisoformat(previous.evidence_session)
                or datetime.fromisoformat(current.as_of_utc.replace("Z", "+00:00"))
                <= datetime.fromisoformat(previous.as_of_utc.replace("Z", "+00:00"))):
            raise ValueError("structure transition is not later than prior observation")
        changed = tuple(key for key in ("range_id", "mode", "phase", "compression_state", "event")
                        if getattr(previous, key) != getattr(current, key))
        if previous.range_id != current.range_id:
            state = "NEW_RANGE" if current.range_id else "TRANSITION_SUSPECTED"
        elif previous.mode != current.mode:
            # One new observation cannot prove a new structural regime.
            state = "TRANSITION_SUSPECTED"
        elif current.event and current.event.startswith("FAILED_"):
            state = "FAILED_TRANSITION"
        elif previous.phase != current.phase:
            state = "DEVELOPING"
        elif previous.compression_state != current.compression_state or previous.event != current.event:
            state = "DEVELOPING"
        else:
            state = "PERSISTING"
    return {
        "ticker": current.ticker,
        "prior_source_id": previous.source_id if previous else None,
        "current_source_id": current.source_id,
        "evidence_session": current.evidence_session,
        "as_of_utc": current.as_of_utc,
        "state": state,
        "changed_fields": changed,
        "mode_phase_key": f"{current.mode}:{current.phase}" if current.phase else current.mode,
        "compression_state": current.compression_state,
        "authority": "STRUCTURE_OBSERVATION_ONLY",
    }


def replay_structure_observations(observations: Sequence[StructureObservation]) -> list[dict]:
    result = []
    previous: StructureObservation | None = None
    for current in observations:
        result.append(describe_structure_transition(previous, current))
        previous = current
    return result
