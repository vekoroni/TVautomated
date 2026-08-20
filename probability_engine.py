"""
AVSHUNTER — Probability Engine
================================
Version : 1.0.0
Date    : 2026-04-12

Used by execution_intelligence_runner_v3_3.py as the derive_probabilities()
call that was previously imported but never existed.

This module provides ONE function: derive_probabilities(row)
It returns (prob_breakout, prob_rejection, prob_drift) as a tuple.

The underlying logic mirrors EVEngineV2._blend_win_probability() but is
exposed here as a standalone callable so the runner can access probabilities
without constructing a full EVInputs object.
"""

from typing import Tuple


def _safe(v, default: float = 0.0) -> float:
    try:
        if v is None: return default
        f = float(v)
        return default if f != f else f
    except (TypeError, ValueError):
        return default


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def derive_probabilities(row: dict) -> Tuple[float, float, float]:
    """
    Derive (prob_breakout, prob_rejection, prob_drift) from a signal row.

    Logic:
    1. Use explicit prob_* fields if already computed by scenario_builder
    2. Otherwise derive from composite score
    3. Ensure probabilities sum to 1.0 and are all > 0

    Returns:
        Tuple (prob_breakout, prob_rejection, prob_drift)
    """
    # If scenario_builder already ran and populated these, use them
    pb = _safe(row.get("prob_breakout"))
    pr = _safe(row.get("prob_rejection"))
    pd = _safe(row.get("prob_drift"))

    if pb > 0 and pr > 0 and pd > 0 and abs(pb + pr + pd - 1.0) < 0.05:
        # Already computed and sane — normalise and return
        total = pb + pr + pd
        return round(pb / total, 4), round(pr / total, 4), round(pd / total, 4)

    # Derive from composite score
    base = _clamp(_safe(row.get("composite", 50)), 0.0, 100.0)

    # Breakout probability rises with composite quality
    # At composite=50 → 0.50; at composite=80 → 0.65; at composite=20 → 0.35
    # PE-01: base constant corrected 0.35 → 0.25 to match scenario_builder and runner inline.
    # Previous 0.35 gave +10% systematic optimism bias vs both fallback implementations.
    prob_breakout  = _clamp(0.25 + (base / 200.0), 0.25, 0.65)

    # Rejection probability falls as composite rises (inverse relationship)
    prob_rejection = _clamp(0.45 - (base / 250.0), 0.10, 0.45)

    # Drift is the remainder, clamped to minimum 0.05
    prob_drift     = _clamp(1.0 - prob_breakout - prob_rejection, 0.05, 0.50)

    # Normalise
    total = prob_breakout + prob_rejection + prob_drift
    if total > 0:
        prob_breakout  /= total
        prob_rejection /= total
        prob_drift     /= total

    return round(prob_breakout, 4), round(prob_rejection, 4), round(prob_drift, 4)
