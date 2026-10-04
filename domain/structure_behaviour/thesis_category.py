"""Phase and Event categorisation of a trade (XLU-D10, ACK 2 Oct 2026).

A trade is categorised by the Wyckoff Phase and the behavioural Event on its own side,
read from the BEH-001 timeframe readings. There is no "observe" decision: when structure
shows no event on the trade's side, the category says so and names any opposing event.

Preference: daily first, then weekly, monthly, 60m, 15m, 5m; within a timeframe an
ACTIVATED event before a DETECTED one, then Candidate_ID (deterministic).
"""
from __future__ import annotations

from typing import Dict, Mapping, Optional

SIDES = {"CALL": "BULL", "PUT": "BEAR"}
ORDER = ("1d", "1w", "1mo", "60m", "15m", "5m")
LIVE = {"ACTIVATED": 0, "DETECTED": 1}
FIELDS = ("thesis_phase", "thesis_event", "thesis_event_state", "thesis_event_timeframe",
          "thesis_event_scope", "thesis_event_candidate_id", "thesis_structure_alignment", "thesis_category")
# The trade-side event's own evidence, for the anticipated move (ACK 3 Oct 2026; display only). Published only
# when the event is on the trade's side; an opposing event's level is never a target.
EVIDENCE_FIELDS = ("thesis_outcome_level", "thesis_outcome_definition", "thesis_duration_test",
                   "thesis_duration_status", "thesis_duration_n", "thesis_duration_q50_bars",
                   "thesis_duration_q80_bars", "thesis_p_outcome_by_limit", "thesis_p_invalidation_by_limit",
                   "thesis_activation_q50_bars", "thesis_activation_q80_bars", "thesis_p_activation_by_limit")
# Step 4a (ACK 3 Oct 2026): the thesis_duration_* fields are the time and probability to the event's Outcome_Level
# (Duration_Level_*: OUTCOME_FROM_DETECTION for DETECTED, OUTCOME for ACTIVATED). Activation timing for a DETECTED
# event is published separately and never stands in for reaching the level.
_EVIDENCE_SOURCE = {"thesis_outcome_level": "Outcome_Level", "thesis_outcome_definition": "Outcome_Definition",
                    "thesis_duration_test": "Duration_Level_Test", "thesis_duration_status": "Duration_Level_Status",
                    "thesis_duration_n": "Duration_Level_N", "thesis_duration_q50_bars": "Duration_Level_Q50_Bars",
                    "thesis_duration_q80_bars": "Duration_Level_Q80_Bars",
                    "thesis_p_outcome_by_limit": "Duration_Level_P_Event_At_Limit",
                    "thesis_p_invalidation_by_limit": "Duration_Level_P_Invalidation_At_Limit"}
_ACTIVATION_SOURCE = {"thesis_activation_q50_bars": "Duration_Remaining_Q50_Bars",
                      "thesis_activation_q80_bars": "Duration_Remaining_Q80_Bars",
                      "thesis_p_activation_by_limit": "Duration_P_Event_At_Limit"}


def _pick(readings: Mapping[str, Mapping], side: str) -> Optional[dict]:
    for tf in ORDER:
        reading = readings.get(tf) or {}
        if reading.get("Status") != "EVALUATED":
            continue
        live = [c for c in reading.get("candidates", [])
                if c.get("Direction") == side and c.get("Signal_State") in LIVE]
        if live:
            return sorted(live, key=lambda c: (LIVE[c["Signal_State"]], str(c["Candidate_ID"])))[0]
    return None


def _phase(candidate: Optional[Mapping], readings: Mapping[str, Mapping]) -> str:
    if candidate is not None:
        if candidate.get("Structure_Scope") == "LOCAL" and candidate.get("Local_Phase"):
            return str(candidate["Local_Phase"])
        if candidate.get("Wyckoff_Phase"):
            return str(candidate["Wyckoff_Phase"])
    return str((readings.get("1d") or {}).get("Wyckoff_Phase") or "UNKNOWN")


def _describe(candidate: Mapping) -> str:
    return f"{candidate['Signal_Type']} ({str(candidate['Signal_State']).lower()}, {candidate['Timeframe']})"


def thesis_category(readings: Mapping[str, Mapping], trade_direction: str) -> Dict[str, Optional[str]]:
    out: Dict[str, Optional[str]] = {field: None for field in (*FIELDS, *EVIDENCE_FIELDS)}
    side = SIDES.get(str(trade_direction or "").upper())
    if side is None:
        out["thesis_structure_alignment"] = "NOT_APPLICABLE_NON_DIRECTIONAL"
        out["thesis_category"] = "No directional trade to categorise"
        return out
    own = _pick(readings, side)
    if own is not None:
        phase = _phase(own, readings)
        out.update({
            "thesis_phase": phase, "thesis_event": own["Signal_Type"],
            "thesis_event_state": own["Signal_State"], "thesis_event_timeframe": own["Timeframe"],
            "thesis_event_scope": own.get("Structure_Scope"), "thesis_event_candidate_id": own["Candidate_ID"],
            "thesis_structure_alignment": "ALIGNED",
            "thesis_category": f"Phase {phase} · {_describe(own)}",
        })
        out.update({field: own.get(source) for field, source in _EVIDENCE_SOURCE.items()})
        if own.get("Signal_State") == "DETECTED" and own.get("Duration_Test") == "ACTIVATION":
            out.update({field: own.get(source) for field, source in _ACTIVATION_SOURCE.items()})
        return out
    other = _pick(readings, "BEAR" if side == "BULL" else "BULL")
    phase = _phase(other, readings)
    out["thesis_phase"] = phase
    if other is not None:
        out["thesis_structure_alignment"] = "OPPOSING_ONLY"
        out["thesis_category"] = (f"Phase {phase} · no event on the {str(trade_direction).upper()} side; "
                                  f"opposing {_describe(other)}")
    else:
        out["thesis_structure_alignment"] = "NO_EVENT"
        out["thesis_category"] = f"Phase {phase} · no behavioural event"
    return out
