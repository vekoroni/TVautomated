"""
AVSHUNTER — Scenario Builder (FIXED v1.1)
==========================================
Computes scenario probabilities from composite score.

FIXES FROM ORIGINAL
--------------------
- prob_drift clamped to minimum 0.05 (prevents negative probability
  at extreme composite values > ~112)
- Probabilities normalised to sum exactly to 1.0 after clamping
- All outputs rounded to 4dp for log readability
"""


def compute_scenario_probabilities(row: dict) -> dict:
    """
    Derive breakout / rejection / drift probabilities from composite score.

    Args:
        row: signal row dict (must contain 'composite' key, default 50)

    Returns:
        dict with prob_breakout, prob_rejection, prob_drift (sum = 1.0)
    """
    base = float(row.get("composite", 50) or 50)
    base = max(0.0, min(100.0, base))  # clamp composite to valid range

    prob_breakout  = min(0.65, 0.25 + base / 200)
    prob_rejection = max(0.10, 0.45 - base / 250)
    prob_drift     = max(0.05, 1.0 - prob_breakout - prob_rejection)

    # Normalise to ensure exact sum = 1.0
    total = prob_breakout + prob_rejection + prob_drift
    if total > 0:
        prob_breakout  /= total
        prob_rejection /= total
        prob_drift     /= total

    return {
        "prob_breakout":  round(prob_breakout,  4),
        "prob_rejection": round(prob_rejection, 4),
        "prob_drift":     round(prob_drift,     4),
    }
