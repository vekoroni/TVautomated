"""ThesisRecord contract and the ticker spine (Phase 2, design DISCOVERY_VANGUARD_REDESIGN_20261007.md §5, §9).

Discovery's thesis step is the ONE owner of direction. For every CandidateRecord it decides:
  ADOPTED    - directed, live (DETECTED / ACTIVATED) and its own geometry COMPLETE: the thesis takes ITS side;
  REFUSED    - directed but geometry WRONG_SIDE (move already happened or invalidation crossed);
  UNRESOLVED - no side, or levels missing; Unresolved_Condition states what would resolve it. An undirected
               compression thesis carries both conditional boundaries (BULL above box_high, BEAR below box_low);
  CLOSED     - FAILED or OUTCOME_REACHED.
The levels are always the candidate's own (one candidate, one story); this module never edits them.

Readiness (Phase 5.3, ACK 8 Oct 2026) is decided by event_readiness from the thesis's own events, not here.

Ticker spine (ACK 8 Oct 2026, until Phase 5 makes every stage per-thesis): the highest TESTED timeframe with an
adopted thesis sets the ticker's side (1mo > 1w > 1d). Opposite adopted theses on that timeframe leave it
UNRESOLVED (SAME_TIMEFRAME_CONFLICT). Intraday theses never set the side (untested, ACK 5 Oct 2026); they label the
spine with intraday_alignment (ALIGNED / OPPOSED / NONE / NOT_MEASURED) - the build-up of the move, no authority.
"""
from __future__ import annotations

import hashlib
from typing import Any, Dict, List, Mapping, Optional, Tuple

from domain.trade_geometry import TRADE_GEOMETRY_FIELDS

THESIS_RECORD_VERSION = "thesis_record_v1"
# Phase 5.1 (8 Oct 2026): the ticker-row fields Discovery's thesis step publishes, defined ONCE. EOD, the Lab book and
# the Lab API read this tuple, so no stage can drop or rename the thesis's own story fields.
THESIS_SPINE_FIELDS = (
    "thesis_trigger_level", "thesis_trigger_source", "thesis_trigger_candidate_id",
    "thesis__spine_rule", "thesis__top_timeframe", "thesis__side_setter_id", "thesis__conflicting_count",
    "thesis__intraday_alignment", "thesis__adopted_count",
    "thesis__events_status", "thesis__last_event", "thesis__last_event_date", "thesis__last_event_level",
    "thesis__last_event_interval", "legacy_beh_daily_primary_side",
    "thesis__readiness", "thesis__readiness_reason", "thesis__readiness_event_date",
    "thesis__conditional_count",
    # B4.2 (ACK 12 Oct 2026): the governing thesis event's id, developing status and clocks (R1 / N2), for mining.
    *("thesis__event_id", "thesis__event_status", "thesis__event_evidence", "thesis__entry_opportunity_id", "thesis__trigger_close_date",
      "thesis__trigger_age_sessions", "thesis__event_occurred_at", "thesis__event_confirmed_at",
      "thesis__event_failed_at", "thesis__policy_qualified_at", "thesis__source_bar_end_at",
      "thesis__discovery_read_at", "thesis__data_received_at", "thesis__data_provider", "thesis__setup_first_detected_at", "thesis__setup_first_detected_run",
      # stamped by the stage that acts: Options (contract), Morning (revalidation), book publish (delivery)
      "thesis__contract_prepared_at", "thesis__last_revalidated_at", "thesis__delivered_at",
      "thesis__timeline_version"),
    # Output-trust item 3 (9 Oct 2026): the trade geometry from the planned entry travels with the thesis.
    *TRADE_GEOMETRY_FIELDS,
)
# Vanguard's context (Phase 4): display only, never authority. Carried with the thesis.
VANGUARD_CONTEXT_FIELDS = ("vanguard_context_flags", "vanguard_context_flag_horizon", "vanguard_context_authority",
                           # M-REVIEW-01 (ACK 10 Oct 2026): the legacy execution permission (from Vanguard's signal_type),
                           # published by the Morning gate as context only - it no longer decides.
                           "legacy_execution_permission_context")
# Phase 5.4: the other theses priced by the Options candidate lane (per-ticker summary on the Options row).
OPTIONS_ALTERNATIVE_FIELDS = ("thesis_alternatives_count", "thesis_alternatives_tested", "thesis_alternatives_json")
# Morning intraday build-up (Phase 3b): advisory only, carried with the thesis to the Lab.
INTRADAY_BUILDUP_FIELDS = ("ib_state", "ib_reason", "ib_interval", "ib_authority", "ib_events", "ib_last_event",
                           "ib_last_event_time", "ib_last_event_level", "ib_trigger_source")
SPINE_RULE = "TOP_DOWN_ADOPTED_THESIS_V1"
TESTED_TIMEFRAMES = ("1mo", "1w", "1d")
INTRADAY_TIMEFRAMES = ("60m", "15m", "5m")
LIVE_STATES = {"DETECTED", "ACTIVATED"}
_LIFECYCLE = {"DETECTED": "DEVELOPING", "ACTIVATED": "ACTIVATED", "FAILED": "INVALIDATED",
              "OUTCOME_REACHED": "OUTCOME_REACHED", "MONITOR": "MONITORING"}


def _num(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def build_thesis(candidate: Mapping, *, readings: Mapping[str, Mapping]) -> Dict[str, Any]:
    """The thesis decision for one CandidateRecord. Returns the Thesis_* fields (the candidate is not modified)."""
    state = str(candidate.get("Signal_State") or "").upper()
    side = candidate.get("Proposed_Side") if candidate.get("Proposed_Side") in {"BULL", "BEAR"} else None
    levels = str(candidate.get("Levels_Status") or "")
    lifecycle = _LIFECYCLE.get(state, "UNKNOWN")
    out: Dict[str, Any] = {
        "Candidate_ID": candidate.get("Candidate_ID"), "Timeframe": candidate.get("Timeframe"),
        "Thesis_Record_Version": THESIS_RECORD_VERSION, "Thesis_ID": f"{candidate.get('Candidate_ID')}#thesis",
        "Thesis_Side": None, "Adoption_State": None, "Deciding_Reason": None, "Unresolved_Condition": None,
        "Lifecycle_State": lifecycle, "Readiness": None,
        "Conditional_Bull_Trigger": None, "Conditional_Bear_Trigger": None,
    }
    if state in {"FAILED", "OUTCOME_REACHED"}:
        out.update(Adoption_State="CLOSED", Deciding_Reason=f"LIFECYCLE_{state}")
        return out
    if side is None:
        reading = readings.get(str(candidate.get("Timeframe"))) or {}
        if candidate.get("Family") == "COMPRESSION":
            hi, lo = _num(reading.get("Compression_Box_High")), _num(reading.get("Compression_Box_Low"))
            out.update(Conditional_Bull_Trigger=hi, Conditional_Bear_Trigger=lo,
                       Unresolved_Condition=(f"BULL if accepted above {hi:.4g}; BEAR if accepted below {lo:.4g}"
                                             if hi is not None and lo is not None else "COMPRESSION_BOX_NOT_MEASURED"))
        else:
            out["Unresolved_Condition"] = "NO_DIRECTIONAL_READING"
        out.update(Adoption_State="UNRESOLVED", Deciding_Reason="NO_SIDE")
        return out
    if state not in LIVE_STATES:
        out.update(Adoption_State="UNRESOLVED", Deciding_Reason=f"STATE_{state or 'UNKNOWN'}",
                   Unresolved_Condition="CANDIDATE_NOT_LIVE")
        return out
    if levels == "WRONG_SIDE":
        out.update(Adoption_State="REFUSED", Deciding_Reason="LEVELS_WRONG_SIDE")
        return out
    if levels != "COMPLETE":
        out.update(Adoption_State="UNRESOLVED", Deciding_Reason="LEVELS_INCOMPLETE",
                   Unresolved_Condition="LEVELS_MISSING: trigger, invalidation or target not measured")
        return out
    # Readiness is decided from the thesis's own events (event_readiness), not from the engine state (Phase 5.3).
    out.update(Thesis_Side=side, Adoption_State="ADOPTED", Deciding_Reason="SETUP_SIDE_WITH_COMPLETE_GEOMETRY",
               Readiness="PENDING_EVENTS")
    return out


_TAG = {"BULL": "UP", "BEAR": "DOWN"}


def event_readiness(events: List[Mapping], *, side: Optional[str], adoption_state: Optional[str],
                    events_status: Optional[str]) -> Dict[str, Any]:
    """Readiness of one thesis from ITS OWN events (Phase 5.3, ACK 8 Oct 2026 "Thesis activated").

    READY_FOR_HUMAN_REVIEW: an accepted break or a held retest on the thesis side, not since closed by INVALIDATED,
    RETEST_FAILED on that side or OUTCOME_REACHED. Events are walked in order, so a later VWAP cross does not undo
    an activation. WAIT_TRIGGER: adopted, trigger not accepted yet. NOT_MEASURED / NOT_ADOPTED: never ready.
    """
    out: Dict[str, Any] = {"Readiness": None, "Readiness_Reason": None, "Readiness_Event": None,
                           "Readiness_Event_Date": None}
    if adoption_state != "ADOPTED" or side not in _TAG:
        out.update(Readiness="NOT_ADOPTED", Readiness_Reason=f"ADOPTION_{adoption_state or 'MISSING'}")
        return out
    if str(events_status or "") != "MEASURED":
        out.update(Readiness="NOT_MEASURED", Readiness_Reason=f"EVENTS_{events_status or 'MISSING'}")
        return out
    tag = _TAG[side]
    activating = {f"BREAK_ACCEPTED_{tag}", f"RETEST_HELD_{tag}"}
    closing = {"INVALIDATED": "CLOSED_INVALIDATED", f"RETEST_FAILED_{tag}": "CLOSED_RETEST_FAILED",
               "OUTCOME_REACHED": "CLOSED_OUTCOME_REACHED"}
    state, deciding = "WAIT_TRIGGER", None
    for event in events or []:
        name = str(event.get("event") or "")
        if name in activating:                       # the latest activation is the deciding event
            state, deciding = "READY_FOR_HUMAN_REVIEW", event
        elif name in closing and (state == "READY_FOR_HUMAN_REVIEW" or name != f"RETEST_FAILED_{tag}"):
            state, deciding = closing[name], event
            break                                    # closed is terminal: never revived by a later event
    out["Readiness"] = state
    if deciding:
        out.update(Readiness_Event=deciding.get("event"), Readiness_Event_Date=deciding.get("date"),
                   Readiness_Reason=f"{deciding.get('event')}@{deciding.get('date')}")
    else:
        out["Readiness_Reason"] = f"NO_ACCEPTED_{tag}_BREAK"
    return out


EVENT_TIMELINE_VERSION = "EVENT_CLOCKS_V1"


def _short_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def event_timeline(events: List[Mapping], *, side: Optional[str], candidate_id: Optional[str],
                   events_status: Optional[str], trigger_level, session_dates: List[str]) -> Dict[str, Any]:
    """B4.2 (ACK 12 Oct 2026): the thesis trigger event's stable id, developing status and clocks (R1, N2, B1).

    The event is published at the FIRST close beyond the trigger (OBSERVED) and develops: a provisional accepted break
    -> PROVISIONALLY_SUCCESSFUL; a full acceptance or a held retest -> CONFIRMED; a failed break, failed retest or
    invalidation -> FAILED (terminal). No crossing -> FORMING. Only the thesis side's events count. The id is
    candidate + side + trigger level, so it survives development; each crossing is its own entry opportunity.
    Readiness (legacy policy v0) is not changed here.
    """
    tag = _TAG.get(side or "")
    out: Dict[str, Any] = {"Event_ID": None, "Event_Status": None, "Entry_Opportunity_ID": None,
                           "Trigger_Close_Date": None, "Trigger_Age_Sessions": None, "Event_Occurred_At": None,
                           "Event_Confirmed_At": None, "Event_Failed_At": None,
                           "Event_Evidence": "", "Event_Timeline_Version": EVENT_TIMELINE_VERSION}
    try:
        level = round(float(trigger_level), 4) if trigger_level is not None else None
    except (TypeError, ValueError):
        level = None
    if tag is None or level is None or not candidate_id:
        out["Event_Status"] = "NO_DIRECTED_TRIGGER"
        return out
    out["Event_ID"] = _short_hash(f"{candidate_id}|BREAK_{tag}|{level}")
    if str(events_status or "") != "MEASURED":
        out["Event_Status"] = "NOT_MEASURED"
        return out
    status, attempt, evidence = "FORMING", None, []
    # The detector lists events by kind; the life cycle is walked in bar order (index, then date).
    ordered = sorted(events or [], key=lambda e: (e.get("index") if e.get("index") is not None else 10 ** 9,
                                                  str(e.get("date") or "")))
    for event in ordered:
        name, date = str(event.get("event") or ""), event.get("date")
        if status == "FAILED":
            break                                          # failure is terminal
        before = status
        if name == f"BREAK_ATTEMPT_{tag}":
            status, attempt = "OBSERVED", date
            out.update(Trigger_Close_Date=date, Event_Occurred_At=date)
        elif name == "INVALIDATED":                        # the thesis is wrong, crossed or not
            status = "FAILED"
            out.update(Event_Failed_At=date, Event_Occurred_At=date)
        elif attempt is None:
            continue
        elif name == f"BREAK_ACCEPTED_{tag}":
            if event.get("provisional"):
                status = "PROVISIONALLY_SUCCESSFUL"
            else:
                status = "CONFIRMED"
                out["Event_Confirmed_At"] = date
            out["Event_Occurred_At"] = date
        elif name == f"RETEST_HELD_{tag}":
            status = "CONFIRMED"
            out.update(Event_Confirmed_At=date, Event_Occurred_At=date)
        elif name in {f"FAILED_BREAK_{tag}", f"RETEST_FAILED_{tag}"}:
            status = "FAILED"
            out.update(Event_Failed_At=date, Event_Occurred_At=date)
        if status != before or name in {f"RETEST_HELD_{tag}", f"BREAK_ACCEPTED_{tag}"}:
            evidence.append(f"{name}@{str(date)[:10]}")     # the bars that set the status (N2 evidence)
    out["Event_Status"] = status
    out["Event_Evidence"] = ";".join(evidence)
    if attempt is not None:
        key = str(attempt)[:10]
        out["Entry_Opportunity_ID"] = _short_hash(f"{out['Event_ID']}|{key}")
        out["Trigger_Age_Sessions"] = sum(1 for d in session_dates if key < str(d)[:10])
    return out


def ticker_spine(theses: List[Mapping], *, intraday_measured: bool = True) -> Tuple[str, Dict[str, Any]]:
    """The ticker's single side for downstream stages until Phase 5 (ACK 8 Oct 2026 top-down rule)."""
    adopted = [t for t in theses if t.get("Adoption_State") == "ADOPTED"]
    info: Dict[str, Any] = {"rule": SPINE_RULE, "top_timeframe": None, "side_setter_id": None,
                            "conflicting_ids": [], "reason": "", "intraday_alignment": "NONE"}
    side = "UNASSIGNED"
    for tf in TESTED_TIMEFRAMES:
        at_tf = [t for t in adopted if t.get("Timeframe") == tf]
        if not at_tf:
            continue
        info["top_timeframe"] = tf
        sides = {t["Thesis_Side"] for t in at_tf}
        if len(sides) > 1:
            info["reason"] = "SAME_TIMEFRAME_CONFLICT"
            info["conflicting_ids"] = sorted(t["Candidate_ID"] for t in at_tf)
            break
        side = sides.pop()
        setter = sorted(at_tf, key=lambda t: (0 if t.get("Lifecycle_State") == "ACTIVATED" else 1,
                                              str(t.get("Candidate_ID"))))[0]
        info["side_setter_id"] = setter["Candidate_ID"]
        info["conflicting_ids"] = sorted(t["Candidate_ID"] for t in adopted
                                         if t.get("Timeframe") in TESTED_TIMEFRAMES and t["Thesis_Side"] != side)
        break
    else:
        info["reason"] = "NO_ADOPTED_THESIS_ON_TESTED_TIMEFRAME" if adopted else "NO_ADOPTED_THESIS"
    if not intraday_measured:
        info["intraday_alignment"] = "NOT_MEASURED"
    elif side in {"BULL", "BEAR"}:
        intraday = [t for t in adopted if t.get("Timeframe") in INTRADAY_TIMEFRAMES]
        same = any(t["Thesis_Side"] == side for t in intraday)
        opposite = any(t["Thesis_Side"] != side for t in intraday)
        info["intraday_alignment"] = "ALIGNED" if same else "OPPOSED" if opposite else "NONE"
    return side, info


def spine_roles(theses: List[Mapping], side: str, info: Mapping, governing_id: Optional[str]) -> Dict[str, str]:
    """Role of each thesis relative to the spine: GOVERNING / SIDE_SETTER / SUPPORTING / CONFLICTING / OTHER."""
    roles = {}
    for t in theses:
        cid = t.get("Candidate_ID")
        if cid == governing_id:
            roles[cid] = "GOVERNING"
        elif cid == info.get("side_setter_id"):
            roles[cid] = "SIDE_SETTER"
        elif t.get("Adoption_State") == "ADOPTED" and side in {"BULL", "BEAR"}:
            roles[cid] = "SUPPORTING" if t.get("Thesis_Side") == side else "CONFLICTING"
        elif cid in (info.get("conflicting_ids") or []):
            roles[cid] = "CONFLICTING"
        else:
            roles[cid] = "OTHER"
    return roles
