"""BEH-001 L5/L7: one current phase per timeframe, with confidence and transition.

Phase comes from control plus range context (F5) and current events; earlier
phases need not be visible (rule PHASE_INFERENCE). A local pause is scoped
separately from the parent campaign (rule NESTED_STRUCTURE).
"""
from __future__ import annotations

from typing import List, Mapping

from .control import ControlAssessment
from .sequences import SequenceResult

TEST_EVENTS = {"SPRING", "UPTHRUST", "UTAD"}


def movement_maturity(control: ControlAssessment, policy: Mapping) -> str:
    if control.controller not in {"BUYERS", "SELLERS"}:
        return "NOT_APPLICABLE"
    cfg = policy["maturity"]
    n = control.thrust_count
    if n < int(cfg["developing"]):
        return "EARLY"
    if n < int(cfg["mature"]):
        return "DEVELOPING"
    deep = bool(control.last_reaction and control.last_reaction.get("depth") == "DEEP")
    if control.sot == "SHORTENING":
        return "EXHAUSTING" if deep else "LATE"
    return "MATURE"


def assess_phase(seq: SequenceResult, control: ControlAssessment, events: List[dict], policy: Mapping,
                 scope: str = "CAMPAIGN") -> dict:
    """Phase for the campaign (major-swing range) or the local (minor) structure."""
    if control.controller == "NOT_EVALUATED":
        return {"phase": None, "confidence": "NOT_EVALUATED", "transition": None,
                "context": control.status, "local_phase": None}
    end = seq.last_index
    recent = end - 3 * int(policy["events"]["reclaim_within_bars"])
    tests = [e for e in events if e["event"] in TEST_EVENTS and e["state"] in {"DETECTED", "CONFIRMED"}
             and e["index"] >= recent]
    cob = [e for e in events if e["event"] == "CHANGE_OF_BEHAVIOUR"]
    rng = seq.trading_range if scope == "CAMPAIGN" else seq.local_range
    local = seq.local_range if scope == "CAMPAIGN" else None
    local_phase = None
    if control.controller in {"BUYERS", "SELLERS"}:
        side = "Markup" if control.controller == "BUYERS" else "Markdown"
        beyond_range = rng is None or not rng.price_inside
        if beyond_range and control.thrust_count >= 2:
            phase = "E"
            confidence = "HIGH" if control.thrust_count >= 3 and control.quality != "WEAKENING" else "MEDIUM"
            transition = "E_TO_A" if cob else "STABLE"
            context = f"{side} campaign beyond the originating range"
        else:
            phase, confidence = "D", "MEDIUM"
            transition = "D_TO_E" if beyond_range else "STABLE"
            context = f"{side} developing; one side retaining progress"
        if local is not None and local.price_inside and phase in {"D", "E"}:
            local_phase = "B"
            context += "; local pause (local Phase B) inside the campaign"
    elif rng is not None and rng.price_inside:
        if tests:
            phase = "C"
            confirmed = any(e["state"] == "CONFIRMED" for e in tests)
            confidence = "HIGH" if confirmed else "MEDIUM"
            transition = "C_TO_D" if confirmed else "STABLE"
            context = "Range: a consequential boundary test is under way"
        else:
            phase, confidence, transition = "B", "MEDIUM", "STABLE"
            context = "Range: competing control is being tested"
    elif cob:
        phase, confidence, transition = "A", "MEDIUM", "A_TO_B"
        context = "Established control interrupted by an abnormal counter-move"
    else:
        phase, confidence, transition = "B", "LOW", "STABLE"
        context = "Control shifting without a defined range; testing competing control"
    return {"phase": phase, "confidence": confidence, "transition": transition,
            "context": context, "local_phase": local_phase}
