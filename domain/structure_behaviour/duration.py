"""BEH-001 remaining-duration estimates (C-04, C-05, RQ-3; A2 Part 4; design rule DURATION).

Evidence comes from replayed candidates on the same timeframe
(`Enhancements/direction_evidence/beh001_duration_evidence.py`). The estimate is the
remaining time, in own-timeframe bars, to the candidate's next event:
- DETECTED: time to activation (trigger before invalidation);
- ACTIVATED: time to outcome (Outcome_Level before invalidation).

The candidate's age bucket is used when its sample is sufficient, else all ages, else
UNESTIMATED. Evidence whose data_end is not before the candidate's As_Of is never used
(causal). Display and measurement only: never a gate, never a fixed window.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, List, Mapping, MutableMapping, Optional

TESTS = {"DETECTED": "ACTIVATION", "ACTIVATED": "OUTCOME"}
FIELDS = ("Duration_Test", "Duration_Basis", "Duration_Status", "Duration_N", "Duration_Remaining_Q50_Bars",
          "Duration_Remaining_Q80_Bars", "Duration_P_Event_At_Limit", "Duration_P_Invalidation_At_Limit",
          "Duration_Unresolved_At_Limit", "Duration_Evidence_Version")
UNESTIMATED = "UNESTIMATED"
# Step 4a (ACK 3 Oct 2026): time and probability to the candidate's Outcome_Level, measured. DETECTED candidates
# use OUTCOME_FROM_DETECTION (many detected types never become ACTIVATED themselves); ACTIVATED use OUTCOME.
# Activation timing (the fields above, for DETECTED) is never relabelled as reaching the level.
LEVEL_TESTS = {"DETECTED": "OUTCOME_FROM_DETECTION", "ACTIVATED": "OUTCOME"}
LEVEL_FIELDS = ("Duration_Level_Test", "Duration_Level_Basis", "Duration_Level_Status", "Duration_Level_N",
                "Duration_Level_Q50_Bars", "Duration_Level_Q80_Bars", "Duration_Level_P_Event_At_Limit",
                "Duration_Level_P_Invalidation_At_Limit")


def load_duration_evidence(path: Path | str | None) -> Optional[dict]:
    """The evidence document, or None when it is missing or unreadable (never raises)."""
    try:
        evidence = json.loads(Path(path).read_text(encoding="utf-8"))
        return evidence if isinstance(evidence, dict) and "groups" in evidence else None
    except Exception:
        return None


def _bucket(age: int, edges: List[int]) -> str:
    for lo, hi in zip(edges, edges[1:]):
        if lo <= age < hi:
            return f"{lo}-{hi - 1}"
    return f"{edges[-1]}+"


def _blank(c: MutableMapping, status: str, reason: str, test: Optional[str] = None) -> None:
    for field in FIELDS:
        c[field] = None
    c["Duration_Test"], c["Duration_Status"] = test, status
    c["Expected_Duration"] = f"{UNESTIMATED}: {reason} (rule DURATION; never hard-coded)"


def _blank_level(c: MutableMapping, status: str, test: Optional[str] = None) -> None:
    for field in LEVEL_FIELDS:
        c[field] = None
    c["Duration_Level_Test"], c["Duration_Level_Status"] = test, status


def _choose(index: Mapping, key: tuple, bucket: str):
    for age_key, label in ((bucket, f"AGE_{bucket}"), ("ALL", "ALL_AGES")):
        g = index.get(key + (age_key,))
        if g is not None and g.get("status") != "INSUFFICIENT_SAMPLE":
            return g, label
    return None, None


def _attach_level(c: MutableMapping, index: Mapping, bucket: str) -> None:
    test = LEVEL_TESTS.get(c.get("Signal_State"))
    if test is None:
        _blank_level(c, "NOT_APPLICABLE")
        return
    if c.get("Outcome_Level") is None:
        _blank_level(c, "NO_OUTCOME_LEVEL", test)
        return
    key = (c.get("Timeframe"), c.get("Structure_Scope"), c.get("Signal_Type"), c.get("Direction"), test)
    g, basis = _choose(index, key, bucket)
    if g is None:
        _blank_level(c, "NO_COMPARABLE_EVIDENCE", test)
        return
    c.update({"Duration_Level_Test": test, "Duration_Level_Basis": basis, "Duration_Level_Status": g["status"],
              "Duration_Level_N": g.get("n"), "Duration_Level_Q50_Bars": g.get("remaining_bars_q50"),
              "Duration_Level_Q80_Bars": g.get("remaining_bars_q80"),
              "Duration_Level_P_Event_At_Limit": g.get("p_event_at_limit"),
              "Duration_Level_P_Invalidation_At_Limit": g.get("p_invalidation_at_limit")})


def attach_duration(candidates: Iterable[MutableMapping], evidence: Optional[Mapping]) -> None:
    candidates = list(candidates)
    if evidence is None:
        for c in candidates:
            _blank(c, "NO_EVIDENCE_FILE", "no duration evidence available")
            _blank_level(c, "NO_EVIDENCE_FILE")
        return
    edges = list(evidence.get("age_bucket_edges") or [0])
    data_end = str(evidence.get("data_end") or "")
    index = {(g["timeframe"], g["scope"], g["signal_type"], g["direction"], g["test"], g["age_bucket"]): g
             for g in evidence["groups"]}
    for c in candidates:
        test = TESTS.get(c.get("Signal_State"))
        if test is None or c.get("Direction") not in {"BULL", "BEAR"}:
            _blank(c, "NOT_APPLICABLE", f"no next event to time for state {c.get('Signal_State')}")
            _blank_level(c, "NOT_APPLICABLE")
            continue
        if not data_end or str(c.get("As_Of") or "")[:10] <= data_end:
            _blank(c, "EVIDENCE_NOT_CAUSAL", f"evidence observed to {data_end}, not before as-of {c.get('As_Of')}", test)
            _blank_level(c, "EVIDENCE_NOT_CAUSAL", LEVEL_TESTS.get(c.get("Signal_State")))
            continue
        key = (c.get("Timeframe"), c.get("Structure_Scope"), c.get("Signal_Type"), c.get("Direction"), test)
        bucket = _bucket(int(c.get("Age_Bars") or 0), edges)
        _attach_level(c, index, bucket)
        chosen, basis = _choose(index, key, bucket)
        if chosen is None:
            _blank(c, "NO_COMPARABLE_EVIDENCE", "no sufficient comparable sample on this timeframe", test)
            continue
        q50, q80 = chosen.get("remaining_bars_q50"), chosen.get("remaining_bars_q80")
        c.update({
            "Duration_Test": test, "Duration_Basis": basis, "Duration_Status": chosen["status"],
            "Duration_N": chosen.get("n"), "Duration_Remaining_Q50_Bars": q50, "Duration_Remaining_Q80_Bars": q80,
            "Duration_P_Event_At_Limit": chosen.get("p_event_at_limit"),
            "Duration_P_Invalidation_At_Limit": chosen.get("p_invalidation_at_limit"),
            "Duration_Unresolved_At_Limit": chosen.get("unresolved_at_limit"),
            "Duration_Evidence_Version": evidence.get("version"),
        })
        event = "activation" if test == "ACTIVATION" else "outcome"
        c["Expected_Duration"] = (
            f"ESTIMATED ({chosen['status']}): remaining time to {event} about {q50} bars (median) and "
            f"{q80} bars (80%) on {c.get('Timeframe')}, of the cases that reach it; "
            f"P({event} first)={chosen.get('p_event_at_limit')}, n={chosen.get('n')}, basis {basis}")
