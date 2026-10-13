"""How each claim in a behavioural reading is known (step 2 of the behavioural-stage design, ACK approved 12 Oct 2026).

Design: Enhancements/phase8/DISCOVERY_VANGUARD_BEHAVIOURAL_STAGE_DESIGN_20261012.md (section 2.1 and the step 2
specification), from ACK's Soul of the Chart teaching format: observed, inferred and unresolved labels are kept apart.
- OBSERVED: read directly from completed bars (structure, levels, compression measures, an event the later bars settled);
- INFERRED: an interpretation of observed bars (controller, phase, transition, an event candidate not yet decisive);
- UNRESOLVED: not decidable from the bars yet (two-sided or shifting control, a low-confidence phase, a monitored
  contraction without a direction, and always the right edge).
A timeframe whose bars are not OK (stale, incomplete, disagreeing with the daily bar) carries no OBSERVED claim: it is
capped at INFERRED and the cap names the reason. Labels only - nothing here changes a reading, a side or a rank.
"""
from __future__ import annotations

from typing import Any, Dict, Mapping

OBSERVED, INFERRED, UNRESOLVED, NOT_EVALUATED = "OBSERVED", "INFERRED", "UNRESOLVED", "NOT_EVALUATED"
_SETTLED_EVENT_STATES = {"ACTIVATED", "CONFIRMED", "FAILED", "OUTCOME_REACHED", "INVALIDATED"}
_UNDECIDED_CONTROL = {"TWO-SIDED", "CONTROL SHIFTING"}


def _cap(basis: str, capped: bool) -> str:
    return INFERRED if capped and basis == OBSERVED else basis


def label_reading(reading: Dict[str, Any]) -> Dict[str, Any]:
    """Adds *_Basis fields to one timeframe reading and its candidates (in place; returns the reading)."""
    if reading.get("Status") != "EVALUATED":
        reading.update(Controller_Basis=NOT_EVALUATED, Phase_Basis=NOT_EVALUATED, Transition_Basis=NOT_EVALUATED,
                       Compression_Basis=NOT_EVALUATED, Right_Edge_Basis=NOT_EVALUATED, Basis_As_Of=None,
                       Basis_Cap=reading.get("Status") or "")
        return reading
    data_status = str(reading.get("Data_Status") or "OK")
    capped = data_status != "OK"
    controller = str(reading.get("Controller") or "").upper()
    reading["Controller_Basis"] = (UNRESOLVED if controller in _UNDECIDED_CONTROL or not controller
                                   else INFERRED)
    confidence = str(reading.get("Phase_Confidence") or "").upper()
    reading["Phase_Basis"] = (INFERRED if reading.get("Wyckoff_Phase") and confidence in {"MEDIUM", "HIGH"}
                              else UNRESOLVED)
    reading["Transition_Basis"] = INFERRED if reading.get("Phase_Transition") else UNRESOLVED
    reading["Compression_Basis"] = _cap(OBSERVED if reading.get("Compression_State") else UNRESOLVED, capped)
    reading["Right_Edge_Basis"] = UNRESOLVED
    reading["Basis_As_Of"] = reading.get("As_Of")
    reading["Basis_Cap"] = data_status if capped else ""
    for c in reading.get("candidates") or []:
        state = str(c.get("Signal_State") or "").upper()
        event = OBSERVED if state in _SETTLED_EVENT_STATES else UNRESOLVED if state == "MONITOR" else INFERRED
        c["Event_Basis"] = _cap(event, capped)
        c["Levels_Basis"] = _cap(OBSERVED, capped)
        c["Basis_Cap"] = reading["Basis_Cap"]
    return reading


def basis_summary(reading: Mapping[str, Any]) -> Dict[str, Any]:
    """The reading's labels for a flat per-ticker row."""
    return {k: reading.get(k) for k in ("Controller_Basis", "Phase_Basis", "Transition_Basis", "Compression_Basis",
                                         "Basis_Cap")}
