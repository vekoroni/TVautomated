"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  AVSHUNTER · SCENARIO BUILDER                                              ║
║                                                                             ║
║  Deploy to: C:/Users/ACKVerissimo/AVSHUNTER-Intelligence/                  ║
║  Imports in: execution_intelligence_runner.py (FIX-08)                     ║
║                                                                             ║
║  PURPOSE:                                                                   ║
║  Computes forward scenario probabilities (breakout / rejection / drift)    ║
║  for each signal row. Called by EIL runner before EVEngineV2 so that       ║
║  prob_breakout, prob_rejection, prob_drift are available as EV inputs.     ║
║                                                                             ║
║  PROBLEM THIS SOLVES:                                                       ║
║  execution_intelligence_runner.py line 114 imports:                        ║
║    from scenario_builder import compute_scenario_probabilities              ║
║  The file was physically absent from the filesystem, causing Phase 9 to    ║
║  crash at startup with:                                                     ║
║    ModuleNotFoundError: No module named 'scenario_builder'                 ║
║                                                                             ║
║  The runner has an inline fallback (lines 121-131) which is a crude        ║
║  linear approximation using composite score only. This production version  ║
║  uses the full Vanguard actuarial and structural inputs, then falls back   ║
║  to the same linear approximation when those are absent — ensuring the     ║
║  fallback and production paths produce identical results for the same data. ║
║                                                                             ║
║  CALL SIGNATURE (from runner line 292):                                    ║
║    probs = compute_scenario_probabilities(row)   # row is a dict           ║
║    row.update(probs)                                                        ║
║                                                                             ║
║  RETURN CONTRACT (row.update()d into the signal dict):                     ║
║    prob_breakout   — probability price moves in signal direction (0-1)     ║
║    prob_rejection  — probability price reverses against signal (0-1)       ║
║    prob_drift      — probability sideways / theta decay dominates (0-1)    ║
║    prob_source     — audit: which data path was used                       ║
║    (prob_breakout + prob_rejection + prob_drift == 1.0)                    ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

from __future__ import annotations

import logging

log = logging.getLogger("avshunter.scenario_builder")

# ─── PROBABILITY BOUNDS ───────────────────────────────────────────────────────
# Prevents extreme values from flowing into EVEngineV2.
# Bounds match those implied by the runner's inline fallback:
#   pb = min(0.65, ...) — BREAKOUT_MAX
#   pr = max(0.10, ...) — REJECTION_MIN
#   pd = max(0.05, ...) — DRIFT_MIN
BREAKOUT_MIN  = 0.10
BREAKOUT_MAX  = 0.65
REJECTION_MIN = 0.10
REJECTION_MAX = 0.60
DRIFT_MIN     = 0.05


# ─── SAFE FIELD READER ────────────────────────────────────────────────────────

def _f(row: dict, *keys, default: float = 0.0) -> float:
    """Safe float with fallback chain — identical to runner's _f() helper."""
    for k in keys:
        v = row.get(k)
        if v in (None, "", "nan", "NaN", "N/A"):
            continue
        try:
            f = float(v)
            if f == f:  # NaN guard
                return f
        except (TypeError, ValueError):
            pass
    return default


# ─── NORMALISATION ────────────────────────────────────────────────────────────

def _clip_and_normalise(pb: float, pr: float, pd: float) -> tuple[float, float, float]:
    """
    Apply bounds then normalise to sum=1.0.
    Matches the rounding used by the runner's inline fallback.
    """
    pb = max(BREAKOUT_MIN,  min(BREAKOUT_MAX,  pb))
    pr = max(REJECTION_MIN, min(REJECTION_MAX, pr))
    pd = max(DRIFT_MIN,     pd)
    total = pb + pr + pd
    if total <= 0:
        return 0.35, 0.40, 0.25
    return round(pb / total, 4), round(pr / total, 4), round(pd / total, 4)


# ─── DATA PATHS ──────────────────────────────────────────────────────────────

def _from_actuarial(row: dict) -> tuple[float, float, float] | None:
    """
    Path 1: Actuarial DB probabilities.
    Written by Vanguard Layer 2 with layer2__ prefix.
    These are empirical frequencies from the 1.28M observation database — 
    the most reliable source when available.
    """
    pb = (
        _f(row, "layer2__prob_up_10pct_before_down_5pct") or
        _f(row, "layer2__prob_breakout")
    )
    pr = (
        _f(row, "layer2__prob_down_5pct_before_up_10pct") or
        _f(row, "layer2__prob_rejection")
    )
    if pb > 0 and pr > 0:
        pd = max(DRIFT_MIN, 1.0 - pb - pr)
        return _clip_and_normalise(pb, pr, pd)
    return None


def _from_structural(row: dict) -> tuple[float, float, float] | None:
    """
    Path 2: Vanguard structural scores.
    Uses composite (0-100), value_acceptance_score, control_score,
    predictability_score (all 0-1) and wbs_score (0-100).
    Blends with empirical win rates when available.
    """
    composite  = _f(row, "composite", default=0.0)
    acceptance = _f(row, "value_acceptance_score", default=0.0)
    control    = _f(row, "control_score", default=0.0)
    predict    = _f(row, "predictability_score", default=0.0)
    wbs        = _f(row, "wbs_score", "wbs", default=0.0)

    # Need at least one structural signal to use this path
    if composite <= 0 and acceptance <= 0 and control <= 0:
        return None

    # composite 0-100 → base breakout probability 0.25-0.65
    comp_norm = max(0.0, min(1.0, composite / 100.0))
    pb = 0.25 + comp_norm * 0.40

    # Structural quality adjustments (additive, each bounded)
    pb += acceptance * 0.08   # value acceptance → buyers engaged → breakout
    pb += control    * 0.07   # buyers in control → momentum
    pb += predict    * 0.05   # predictable Wyckoff state → reliable signal
    pb += (wbs / 100.0) * 0.05  # wall break approaching → catalyst confirmed

    # Empirical win rate blending if available (normalise 0-100 to 0-1)
    win_rates = []
    for col in ("win_rate_5d", "win_rate_10d", "win_rate_20d",
                "layer2__win_rate_5d", "layer2__win_rate_10d", "layer2__win_rate_20d"):
        v = _f(row, col)
        if v > 0:
            v = v / 100.0 if v > 1.0 else v
            if 0.05 < v < 0.95:
                win_rates.append(v)
    if win_rates:
        avg_wr = sum(win_rates) / len(win_rates)
        pb = pb * 0.60 + avg_wr * 0.40

    pr = max(REJECTION_MIN, 0.50 - pb * 0.60)
    pd = max(DRIFT_MIN, 1.0 - pb - pr)
    return _clip_and_normalise(pb, pr, pd)


def _from_linear_fallback(row: dict) -> tuple[float, float, float]:
    """
    Path 3: Linear fallback — IDENTICAL to runner's inline copy (lines 121-131).
    Used when no Vanguard data is available.
    Kept byte-for-byte compatible so replacing the inline copy never changes results.
    """
    base = float(row.get("composite", 50) or 50)
    base = max(0.0, min(100.0, base))
    pb = min(BREAKOUT_MAX, 0.25 + base / 200.0)
    pr = max(REJECTION_MIN, 0.45 - base / 250.0)
    pd = max(DRIFT_MIN, 1.0 - pb - pr)
    t  = pb + pr + pd
    return round(pb / t, 4), round(pr / t, 4), round(pd / t, 4)


# ─── PUBLIC INTERFACE ─────────────────────────────────────────────────────────

def compute_scenario_probabilities(row: dict) -> dict:
    """
    Compute forward scenario probabilities for a signal row.

    Called by execution_intelligence_runner.py line 292:
        probs = compute_scenario_probabilities(row)
        row.update(probs)

    Data priority:
      1. Actuarial DB path probabilities (layer2__prob_* fields)
      2. Vanguard structural scores (composite, acceptance, control, wbs)
      3. Linear fallback (matches runner inline copy — zero dependencies)

    Returns dict with: prob_breakout, prob_rejection, prob_drift, prob_source
    """
    ticker = row.get("ticker", "?")

    # Path 1: actuarial
    result = _from_actuarial(row)
    if result is not None:
        pb, pr, pd = result
        log.debug("[SB] %s actuarial: B=%.3f R=%.3f D=%.3f", ticker, pb, pr, pd)
        return {
            "prob_breakout":  pb,
            "prob_rejection": pr,
            "prob_drift":     pd,
            "prob_source":    "actuarial",
        }

    # Path 2: structural
    result = _from_structural(row)
    if result is not None:
        pb, pr, pd = result
        log.debug("[SB] %s structural: B=%.3f R=%.3f D=%.3f", ticker, pb, pr, pd)
        return {
            "prob_breakout":  pb,
            "prob_rejection": pr,
            "prob_drift":     pd,
            "prob_source":    "structural",
        }

    # Path 3: linear fallback
    pb, pr, pd = _from_linear_fallback(row)
    log.debug("[SB] %s linear fallback: B=%.3f R=%.3f D=%.3f", ticker, pb, pr, pd)
    return {
        "prob_breakout":  pb,
        "prob_rejection": pr,
        "prob_drift":     pd,
        "prob_source":    "linear_fallback",
    }
