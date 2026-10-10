"""CandidateRecord contract (Phase 1, design DISCOVERY_VANGUARD_REDESIGN_20261007.md §9).

Every behavioural engine candidate is published as one record that carries ITS OWN levels. This module adds the
contract fields to the engine's candidate dict in place; it never changes a level, a side or a state:
  Record_Version, Family, Proposed_Side, Compression_Episode_Start (compression family),
  Distance_To_Trigger_ATR (+ _Status), Levels_Status.
Families are labels with no authority. Contributor fields carry MEASURED / NOT_MEASURED:<reason>; a missing input
is never a neutral default (R1). Levels_Status describes the geometry against the price; it is a label, not a gate.
"""
from __future__ import annotations

import math
from typing import Any, Mapping, MutableMapping, Optional

CANDIDATE_RECORD_VERSION = "candidate_record_v1"

FAMILY_BY_SIGNAL_TYPE = {
    "SOS -> LPS continuation": "CONTINUATION",
    "SOW -> LPSY continuation": "CONTINUATION",
    "Trend Continuation after Shallow Test": "CONTINUATION",
    "Failed Spring Continuation": "FAILED_TEST",
    "Failed Upthrust Continuation": "FAILED_TEST",
    "Spring Candidate": "REVERSAL",
    "Upthrust Candidate": "REVERSAL",
    "UTAD Test": "REVERSAL",
    "Change-of-Behaviour Reversal": "REVERSAL",
    "Mature Trend Exhaustion": "REVERSAL",
    "Buyer Absorption Breakout": "ABSORPTION_BREAK",
    "Seller Absorption Breakdown": "ABSORPTION_BREAK",
    "Crabel Compression Breakout": "COMPRESSION",
    "Hinge / Apex Expansion": "COMPRESSION",
}


def family_of(signal_type: Any) -> str:
    return FAMILY_BY_SIGNAL_TYPE.get(str(signal_type or ""), "UNCLASSIFIED")


def _num(value: Any) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _levels_status(side: Optional[str], close: Optional[float], invalidation: Optional[float],
                   target: Optional[float]) -> str:
    if side not in {"BULL", "BEAR"}:
        return "NOT_DIRECTED"
    if close is None or invalidation is None or target is None:
        return "INCOMPLETE"
    sign = 1.0 if side == "BULL" else -1.0
    ok = sign * (invalidation - close) < 0 and sign * (target - close) > 0
    return "COMPLETE" if ok else "WRONG_SIDE"


def enrich_candidate(candidate: MutableMapping, *, close: Any, atr_daily: Any,
                     readings: Mapping[str, Mapping]) -> MutableMapping:
    """Add the CandidateRecord fields to one engine candidate (in place) and return it."""
    side = candidate.get("Direction") if candidate.get("Direction") in {"BULL", "BEAR"} else None
    family = family_of(candidate.get("Signal_Type"))
    px, atr, trigger = _num(close), _num(atr_daily), _num(candidate.get("Trigger_Level"))
    if px is None:
        distance, status = None, "NOT_MEASURED:NO_PRICE"
    elif atr is None or atr <= 0:
        distance, status = None, "NOT_MEASURED:NO_ATR"
    elif trigger is None:
        distance, status = None, "NOT_MEASURED:NO_TRIGGER_LEVEL"
    else:
        distance, status = round(abs(trigger - px) / atr, 4), "MEASURED"
    episode = None
    if family == "COMPRESSION":
        episode = (readings.get(str(candidate.get("Timeframe"))) or {}).get("Compression_Episode_Start")
    candidate.update({
        "Record_Version": CANDIDATE_RECORD_VERSION,
        "Family": family,
        "Proposed_Side": side,
        "Compression_Episode_Start": episode,
        "Distance_To_Trigger_ATR": distance,
        "Distance_To_Trigger_ATR_Status": status,
        "Levels_Status": _levels_status(side, px, _num(candidate.get("Invalidation_Level")),
                                        _num(candidate.get("Outcome_Level"))),
    })
    return candidate
