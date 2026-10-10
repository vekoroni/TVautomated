"""The one ranking owner for the Lab book and the trade summary (Phase 5.5 / RC10, ACK 8 Oct 2026 "Expectancy").

Decision groups (ACK E11, 6 Oct 2026): BLOCKED rows sink below every other row (ACK 8 Oct 2026 "Blocked sink", keeping
the 18 Sep rule that review rows rank above blocked rows); then lane A, B, C (unassigned last), then the thesis
readiness inside each lane.
Within a group: expected option multiple = lane holdout hit rate x option value at the median time - 1 premium
(ACK 7 Oct 2026: long options are judged on expectancy and convexity, not hit rate). It supersedes E11a's hit-rate-first
order. It is a conditional estimate - the value assumes the level is reached by the median time and a failed trade
returns nothing - until the outcome scorer calibrates it. Missing inputs rank after measured ones, never as zero.
Ties: more replay evidence first, then ticker. Display ordering only: it gates nothing.
"""
from __future__ import annotations

import math
from typing import Any, Mapping, Optional, Tuple

RANK_BASIS = ("EXPECTANCY_V1: lane holdout hit rate x option value at the median time - 1 premium; "
              "conditional estimate, not calibrated by the outcome scorer")
_LANE = {"A": 0, "B": 1, "C": 2}
_READINESS = {"READY_FOR_HUMAN_REVIEW": 0, "WAIT_TRIGGER": 1, "NOT_MEASURED": 2, "NOT_ADOPTED": 3}
_CLOSED, _MISSING = 4, 5


def _num(value: Any) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def expected_option_multiple(row: Mapping[str, Any]) -> Optional[float]:
    """Expected multiple of the premium paid (0 = break-even). None when either input is not measured."""
    hit, value = _num(row.get("trade_lane_hit_holdout")), _num(row.get("anticipated_value_multiple_q50"))
    if hit is None or value is None or not 0.0 <= hit <= 1.0:
        return None
    return hit * value - 1.0


def rank_group(row: Mapping[str, Any]) -> str:
    lane = str(row.get("trade_lane") or "").strip().upper() or "UNASSIGNED"
    readiness = str(row.get("thesis__readiness") or "").strip().upper() or "NOT_RECORDED"
    return f"{lane}|{readiness}"


def rank_key(row: Mapping[str, Any]) -> Tuple:
    lane = str(row.get("trade_lane") or "").strip().upper()
    readiness = str(row.get("thesis__readiness") or "").strip().upper()
    ready_order = _READINESS.get(readiness, _CLOSED if readiness.startswith("CLOSED") else _MISSING)
    expected = expected_option_multiple(row)
    evidence = _num(row.get("anticipated_evidence_n")) or 0.0
    blocked = str(row.get("lab_verdict") or "").strip().upper() == "BLOCKED"
    return (blocked, _LANE.get(lane, 3), ready_order, expected is None, -(expected or 0.0), -evidence,
            str(row.get("ticker") or ""))
