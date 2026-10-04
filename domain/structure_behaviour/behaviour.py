"""BEH-001 L3: side-mirrored behaviour measures.

Repair is structural (F1), acceptance needs persistence beyond a level, thrust
comparisons use a tolerance band (F7), and true range is never counted as both
effort and result (refinement 3): effort is volume, result is close-to-close
displacement.
"""
from __future__ import annotations

import math
from typing import Mapping

import numpy as np

from .sequences import SequenceResult


def compare_thrusts(previous_atr: float, current_atr: float, policy: Mapping) -> str:
    """LENGTHENING / SHORTENING / UNCHANGED within the configured tolerance."""
    if previous_atr is None or current_atr is None or previous_atr <= 0:
        return "UNMEASURED"
    ratio = current_atr / previous_atr
    tolerance = float(policy["sot_tolerance"])
    if ratio > 1 + tolerance:
        return "LENGTHENING"
    if ratio < 1 - tolerance:
        return "SHORTENING"
    return "UNCHANGED"


def assess_reaction(*, origin: float, thrust_end: float, reaction_extreme: float,
                    thrust_direction: str, policy: Mapping | None = None) -> dict:
    """Did the reaction repair the thrust? Only regaining its origin repairs."""
    lo, le, lx = math.log(origin), math.log(thrust_end), math.log(reaction_extreme)
    span = abs(lo - le)
    retracement = abs(lx - le) / span if span > 0 else float("nan")
    if thrust_direction == "DOWN":
        repaired = lx > lo
    elif thrust_direction == "UP":
        repaired = lx < lo
    else:
        raise ValueError(f"Invalid thrust direction: {thrust_direction!r}")
    shallow = float((policy or {}).get("repair", {}).get("shallow_retrace_max", 0.382))
    deep = float((policy or {}).get("repair", {}).get("deep_retrace_min", 0.786))
    depth = "SHALLOW" if retracement <= shallow else "DEEP" if retracement >= deep else "MODERATE"
    return {"state": "FULL_REPAIR" if repaired else "NOT_REPAIRED",
            "retracement": retracement, "depth": depth}


def acceptance(seq: SequenceResult, *, level: float, side: str, from_index: int, policy: Mapping) -> dict:
    """Closes must persist beyond the level and survive the first test back.

    States: NOT_CROSSED, CROSSED_NOT_ACCEPTED, ACCEPTED_PROVISIONAL (too few
    later bars to see the response yet), ACCEPTED, REJECTED (closed back).
    """
    if side not in {"ABOVE", "BELOW"}:
        raise ValueError(f"Invalid acceptance side: {side!r}")
    frame = seq.frame
    need = int(policy["acceptance"]["closes"])
    margin = float(policy["acceptance"]["min_beyond_atr"])
    lc, atr = frame["lc"].to_numpy(), frame["atr"].to_numpy()
    level_log = math.log(level)
    sign = 1.0 if side == "ABOVE" else -1.0
    run = 0
    crossed = False
    for i in range(max(0, from_index), len(frame)):
        a = atr[i] if np.isfinite(atr[i]) else 0.0
        beyond = sign * (lc[i] - level_log) > margin * a
        crossed = crossed or sign * (lc[i] - level_log) > 0
        run = run + 1 if beyond else 0
        if run >= need:
            after = lc[i + 1:i + 1 + need]
            if (sign * (after - level_log) < 0).any():
                return {"state": "REJECTED", "index": i}
            if len(after) < need:
                return {"state": "ACCEPTED_PROVISIONAL", "index": i}
            return {"state": "ACCEPTED", "index": i}
    return {"state": "CROSSED_NOT_ACCEPTED" if crossed else "NOT_CROSSED", "index": None}


def effort_result(seq: SequenceResult, start: int, end: int, policy: Mapping) -> dict:
    """Volume (effort) against close-to-close displacement (result), in ATR."""
    frame = seq.frame
    cfg = policy["events"]
    volume = frame["volume"].to_numpy()
    lc, atr = frame["lc"].to_numpy(), frame["atr"].to_numpy()
    start, end = max(1, start), min(len(frame) - 1, end)
    baseline = volume[max(0, start - 20):start].mean() if start > 0 else np.nan
    high_effort_small_result = 0
    for i in range(start, end + 1):
        ratio = volume[i] / baseline if baseline and baseline > 0 else np.nan
        result = abs(lc[i] - lc[i - 1]) / atr[i] if np.isfinite(atr[i]) and atr[i] > 0 else np.nan
        if ratio >= float(cfg["absorption_volume_ratio_min"]) and result <= float(cfg["absorption_result_max_atr"]):
            high_effort_small_result += 1
    return {"absorption_bars": high_effort_small_result,
            "absorption": high_effort_small_result >= int(cfg["absorption_min_bars"])}
