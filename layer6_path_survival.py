"""
layer6_path_survival.py
=======================
Q-OMEGA Layer 6 — Path Risk & Survivability Engine

Purpose:
    Estimate whether an options contract can survive the journey to its
    structural target before theta decay or adverse price movement kills it.

    Being right on direction is necessary but not sufficient. A contract
    that expires worthless because the stock took too long to move — or
    dipped too far before recovering — is a losing trade regardless of
    direction.

    This layer answers:
        "Even if we are directionally right, can the CONTRACT survive
         long enough to get paid?"

Key Outputs:
    PSI (Path Survivability Index) — 0-100
        > 70  : HIGH — contract likely survives the journey
        40-70 : MEDIUM — survivable but tight
        < 40  : LOW — contract likely decays before thesis matures

    time_to_pain_estimate    — days until theta decay consumes 50% of premium
    time_to_target_estimate  — days until forecast move reaches breakeven
    stop_feasibility         — VIABLE / TIGHT / INFEASIBLE
    runway_score             — 0-100 (wall proximity adjusted for direction)
    mae_survivability        — True if typical MAE does not breach stop

Dependencies:
    mae_mfe_calculator.MAEMFEResult
    layer3_forward_variance outputs (expected_move, vol_forecast_confidence)
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Optional

import numpy as np

log = logging.getLogger('layer6_path_survival')

# ── Thresholds ─────────────────────────────────────────────────────────────────
PSI_HIGH_THRESHOLD   = 70
PSI_MEDIUM_THRESHOLD = 40
PAIN_THRESHOLD_PCT   = 0.50   # time_to_pain = days until 50% premium decayed by theta
STOP_TIGHT_RATIO     = 0.5    # stop distance < 50% of typical MAE = TIGHT
STOP_INFEASIBLE_RATIO= 0.25   # stop distance < 25% of typical MAE = INFEASIBLE


# ── Output dataclass ───────────────────────────────────────────────────────────

@dataclass
class PathSurvivalResult:
    ticker:                  str
    psi:                     float    # 0-100 Path Survivability Index
    psi_label:               str      # HIGH / MEDIUM / LOW
    time_to_pain_estimate:   float    # days until 50% premium decayed by theta
    time_to_target_estimate: float    # days until forecast move hits breakeven
    stop_feasibility:        str      # VIABLE / TIGHT / INFEASIBLE
    runway_score:            float    # 0-100
    mae_survivability:       bool     # True if typical MAE does not breach stop
    mae_survivability_margin: float   # stop_dist - typical_mae_pct (positive = safe margin)
    error:                   Optional[str] = None

    def to_dict(self) -> dict:
        return {
            'ticker':                     self.ticker,
            'l6_psi':                     round(self.psi,                      1),
            'l6_psi_label':               self.psi_label,
            'l6_time_to_pain_days':       round(self.time_to_pain_estimate,     1),
            'l6_time_to_target_days':     round(self.time_to_target_estimate,   1),
            'l6_stop_feasibility':        self.stop_feasibility,
            'l6_runway_score':            round(self.runway_score,              1),
            'l6_mae_survivable':          self.mae_survivability,
            'l6_mae_survival_margin_pct': round(self.mae_survivability_margin,  2),
            'l6_error':                   self.error,
        }


# ── Component calculators ──────────────────────────────────────────────────────

def _time_to_pain(premium: float, theta_per_day: float) -> float:
    """
    Days until theta decay consumes 50% of option premium.
    theta_per_day is negative (e.g. -0.03 = 3 cents/day decay).
    Returns float days, capped at 365.
    """
    if theta_per_day >= 0 or premium <= 0:
        return 365.0  # no decay or no premium — pain is far away
    daily_decay = abs(theta_per_day)
    target_loss = premium * PAIN_THRESHOLD_PCT
    return float(min(target_loss / daily_decay, 365.0))


def _time_to_target(
    expected_move_pct:    float,   # forecast % move over full hold window (Layer 3)
    breakeven_pct:        float,   # % move needed to break even
    hold_days:            int,
) -> float:
    """
    Estimate days until breakeven is reached, assuming linear move.
    Returns float days. Returns hold_days + 1 if move insufficient.
    """
    if expected_move_pct <= 0 or breakeven_pct <= 0:
        return float(hold_days + 1)
    if expected_move_pct < breakeven_pct:
        # Forecast does not reach breakeven — return hold_days + 1 (unreachable)
        return float(hold_days + 1)
    # Interpolate: if breakeven is X% of expected move, it is hit at X% of hold period
    frac = breakeven_pct / expected_move_pct
    return float(frac * hold_days)


def _stop_feasibility(
    stop_dist_pct:   float,   # stop distance as % of entry price
    typical_mae_pct: float,   # typical adverse excursion % (from MAE P50)
) -> str:
    """
    VIABLE    : stop is wider than typical MAE — survives normal noise
    TIGHT     : stop is 25-50% of typical MAE — will be hit by normal noise
    INFEASIBLE: stop is < 25% of typical MAE — almost certain stop-out before thesis
    """
    if typical_mae_pct <= 0:
        return 'VIABLE'  # no MAE data — assume viable
    ratio = stop_dist_pct / typical_mae_pct
    if ratio >= STOP_TIGHT_RATIO:
        return 'VIABLE'
    elif ratio >= STOP_INFEASIBLE_RATIO:
        return 'TIGHT'
    return 'INFEASIBLE'


def _runway_score(
    runway_to_wall_pct: float,   # % from current price to gamma wall
    breakeven_pct:      float,   # % move needed to break even
    pin_risk_score:     float,   # 0-100 from Layer 7 (WBS)
) -> float:
    """
    Runway score 0-100.
    High score = plenty of room between current price and gamma wall,
    and wall is not densely defended (low pin risk).

    Penalised when:
        - Runway to wall is < breakeven (wall blocks profit)
        - Pin risk is high (wall is likely to magnetise price)
    """
    if runway_to_wall_pct <= 0:
        return 0.0

    # Base: how much runway vs breakeven requirement
    # 2× breakeven runway → 100 pts; breakeven runway → 50 pts; 0 → 0 pts
    runway_ratio  = runway_to_wall_pct / max(breakeven_pct, 0.5)
    runway_base   = float(np.clip(runway_ratio / 2.0 * 100, 0, 100))

    # Pin risk penalty: 0 pin risk = no penalty; 100 pin risk = -40 pts
    pin_penalty   = (pin_risk_score / 100.0) * 40.0

    return float(np.clip(runway_base - pin_penalty, 0.0, 100.0))


def _compute_psi(
    time_to_pain:    float,   # days until 50% decay
    time_to_target:  float,   # days until breakeven reached
    stop_feasibility:str,
    runway_score:    float,
    mae_survivable:  bool,
    vol_forecast_conf: float, # 0-100 from Layer 3
) -> float:
    """
    PSI = weighted composite of all survivability factors.

    Component weights:
        Pain vs Target timing   30% — can contract outlive its theta?
        Stop feasibility        25% — will stop be hit by normal noise?
        Runway score            25% — is there room for the move?
        MAE survivability       10% — does typical adverse excursion breach stop?
        Vol forecast confidence 10% — how trustworthy is the forecast?
    """
    # Timing component: time_to_pain > time_to_target = pain arrives AFTER target
    # i.e. contract still alive when breakeven is reached
    if time_to_target <= 0:
        timing_score = 0.0
    else:
        timing_ratio  = time_to_pain / time_to_target  # > 1 = good
        timing_score  = float(np.clip(timing_ratio * 50, 0, 100))

    # Stop feasibility component
    stop_score = {'VIABLE': 100.0, 'TIGHT': 45.0, 'INFEASIBLE': 0.0}.get(stop_feasibility, 50.0)

    # MAE component
    mae_score = 80.0 if mae_survivable else 20.0

    # Vol confidence component (already 0-100)
    conf_score = float(np.clip(vol_forecast_conf, 0, 100))

    raw = (0.30 * timing_score +
           0.25 * stop_score   +
           0.25 * runway_score +
           0.10 * mae_score    +
           0.10 * conf_score)

    return float(np.clip(raw, 0.0, 100.0))


# ── Public API ─────────────────────────────────────────────────────────────────

def compute_psi(
    ticker:               str,
    # Contract economics
    premium:              float,     # option mark price (per share)
    theta_per_day:        float,     # daily theta (negative)
    breakeven_pct:        float,     # % move to break even
    stop_dist_pct:        float,     # stop distance as % of entry
    hold_days:            int,       # expected hold window
    # Layer 3 inputs
    expected_move_pct:    float,     # forecast % move
    vol_forecast_confidence: float,  # 0-100
    # Layer 7 inputs
    runway_to_wall_pct:   float,     # % from price to gamma wall
    pin_risk_score:       float,     # 0-100
    # MAE/MFE inputs (from mae_mfe_calculator)
    typical_mae_pct:      float,     # abs(mae_p50) * 100
) -> PathSurvivalResult:
    """
    Main entry point. Returns PathSurvivalResult with PSI and all components.
    """
    try:
        t_pain   = _time_to_pain(premium, theta_per_day)
        t_target = _time_to_target(expected_move_pct, breakeven_pct, hold_days)

        stop_feas    = _stop_feasibility(stop_dist_pct, typical_mae_pct)
        run_score    = _runway_score(runway_to_wall_pct, breakeven_pct, pin_risk_score)

        # MAE survivability: stop distance > typical MAE = trade survives normal noise
        mae_surv         = (stop_dist_pct >= typical_mae_pct) if typical_mae_pct > 0 else True
        mae_surv_margin  = stop_dist_pct - typical_mae_pct

        psi = _compute_psi(
            time_to_pain      = t_pain,
            time_to_target    = t_target,
            stop_feasibility  = stop_feas,
            runway_score      = run_score,
            mae_survivable    = mae_surv,
            vol_forecast_conf = vol_forecast_confidence,
        )

        psi_label = ('HIGH' if psi >= PSI_HIGH_THRESHOLD else
                     'MEDIUM' if psi >= PSI_MEDIUM_THRESHOLD else 'LOW')

        return PathSurvivalResult(
            ticker                   = ticker,
            psi                      = psi,
            psi_label                = psi_label,
            time_to_pain_estimate    = t_pain,
            time_to_target_estimate  = t_target,
            stop_feasibility         = stop_feas,
            runway_score             = run_score,
            mae_survivability        = mae_surv,
            mae_survivability_margin = mae_surv_margin,
        )

    except Exception as e:
        log.error(f'[{ticker}] Layer 6 PSI error: {e}')
        return PathSurvivalResult(
            ticker=ticker, psi=50.0, psi_label='MEDIUM',
            time_to_pain_estimate=0.0, time_to_target_estimate=0.0,
            stop_feasibility='UNKNOWN', runway_score=50.0,
            mae_survivability=True, mae_survivability_margin=0.0,
            error=str(e),
        )
