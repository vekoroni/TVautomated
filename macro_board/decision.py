"""Descriptive decision aids from the thesis review (6 Oct 2026).

Both are labels for the human, never permissions or probabilities:
- extension_state: how far a move has already run, in the ETF's own volatility (entry may have
  deteriorated even when the direction is still supported).
- classify_response: whether the ETF's own behaviour agrees with the macro pressure that has
  been *measured* for it (signs from the transmission evidence, never textbook signs).
"""

from __future__ import annotations

import math
from typing import Mapping


def extension_state(return_pct: float | None, rv_annual_pct: float | None, sessions: int, band_sd: float) -> dict:
    """Move over ``sessions`` expressed in standard deviations of the ETF's realised vol."""
    if return_pct is None or rv_annual_pct is None or not rv_annual_pct > 0:
        return {"state": "UNKNOWN", "z": None}
    sd = rv_annual_pct * math.sqrt(sessions / 252.0)
    z = return_pct / sd
    state = "EXTENDED_UP" if z >= band_sd else "EXTENDED_DOWN" if z <= -band_sd else "NOT_EXTENDED"
    return {"state": state, "z": round(z, 3)}


def classify_response(sensitivity: Mapping[str, Mapping], own_return_pct: float | None, t_min: float) -> dict:
    """Measured headwinds/tailwinds active today vs the ETF's own return over the same window.

    SUPPORTING_RESPONSE  price agrees with the net measured pressure
    ABSORBING_PRESSURE   net measured headwind, but the ETF rose
    REJECTING_RELIEF     net measured tailwind, but the ETF fell
    MIXED                headwinds and tailwinds in equal number
    INSUFFICIENT         nothing measured with |t| >= t_min, or no recent return
    """
    headwinds, tailwinds = [], []
    for key, entry in sensitivity.items():
        excess, t = entry.get("excess_pct"), entry.get("t")
        if excess is None or t is None or abs(t) < t_min:
            continue
        (tailwinds if excess > 0 else headwinds).append(key)
    result = {"headwinds": headwinds, "tailwinds": tailwinds, "own_return_pct": own_return_pct}
    if own_return_pct is None or not (headwinds or tailwinds):
        return {**result, "label": "INSUFFICIENT"}
    if len(headwinds) == len(tailwinds):
        return {**result, "label": "MIXED"}
    pressure_up = len(tailwinds) > len(headwinds)
    rising = own_return_pct > 0
    if pressure_up == rising:
        label = "SUPPORTING_RESPONSE"
    else:
        label = "REJECTING_RELIEF" if pressure_up else "ABSORBING_PRESSURE"
    return {**result, "label": label}


def remaining_opportunity(*, close: float | None, entry: float | None, target: float | None,
                          invalidation: float | None, direction: str | None) -> dict | None:
    """Distances from the *current* close to the pipeline's target and invalidation, and how much
    of the entry->target move is already used (thesis Scenario C). Distances, not probabilities."""
    if close is None or direction not in ("CALL", "PUT") or (target is None and invalidation is None):
        return None
    sign = 1.0 if direction == "CALL" else -1.0
    out = {"to_target_pct": None, "to_invalidation_pct": None, "target_consumed": None}
    if target is not None:
        out["to_target_pct"] = round(sign * (target - close) / close * 100.0, 4)
        if entry is not None and target != entry:
            out["target_consumed"] = round((close - entry) / (target - entry), 4)
    if invalidation is not None:
        out["to_invalidation_pct"] = round(sign * (close - invalidation) / close * 100.0, 4)
    return out
