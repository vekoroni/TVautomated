"""
layer4_mispricing.py
====================
Q-OMEGA Layer 4 — Mispricing & Edge Extraction Engine

Purpose:
    Compare market-implied pricing with AVSHUNTER's forward variance forecast
    to identify genuine edge. This is the soul of Q-OMEGA.

    Three core metrics produced:
        RIEG  — Realised-Implied Edge Gap
                Positive = market IV > forecast vol = options EXPENSIVE (headwind)
                Negative = market IV < forecast vol = options CHEAP (tailwind for buyer)
                Named from long-option buyer perspective: negative RIEG = edge exists.

        CCR   — Convexity Capture Ratio
                Can the contract actually monetise the forecast move after
                theta, spread and skew tax?
                > 1.0 = contract pays out more than it costs to hold = good geometry
                < 1.0 = contract bleeds before thesis matures = poor geometry

        vol_mispricing_score — 0-100 composite of RIEG + surface richness + term structure
                > 60 = options are cheap vs forecast = edge exists
                < 40 = options are expensive = headwind

Dependencies:
    layer3_forward_variance.ForwardVarianceResult (or garch_forecasts CSV)
    options_intelligence CSV (for IV, greeks, contract economics)

Position in pipeline:
    Input : garch_forecasts_{run_id}.csv (Layer 3 output)
            options_intelligence_{run_id}.csv
    Output: qomega_mispricing_{run_id}.csv
    Called by: qomega_engine.py (master orchestrator, not yet built)
    For now: can be called standalone for each ticker after GARCH batch.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Optional

import numpy as np

log = logging.getLogger('layer4_mispricing')

# ── Thresholds ─────────────────────────────────────────────────────────────────
RIEG_CHEAP_THRESHOLD      = -0.03   # RIEG < -3% = cheap vol (tailwind for buyer)
RIEG_EXPENSIVE_THRESHOLD  =  0.05   # RIEG >  5% = expensive vol (headwind)
CCR_GOOD_THRESHOLD        =  1.0    # CCR >= 1.0 = good payoff geometry
CCR_POOR_THRESHOLD        =  0.6    # CCR <  0.6 = poor geometry
EDGE_GAP_STRONG           =  0.10   # 10%+ expected-vs-implied gap = strong edge
EDGE_GAP_MODERATE         =  0.05   # 5%+ = moderate edge
MISPRICING_CHEAP_FLOOR    =  60     # vol_mispricing_score >= 60 = cheap (buy signal)
MISPRICING_EXPENSIVE_CAP  =  40     # vol_mispricing_score <  40 = expensive (avoid)


# ── Output dataclass ───────────────────────────────────────────────────────────

@dataclass
class MispricingResult:
    ticker:                str
    rieg:                  float   # Realised-Implied Edge Gap (signed decimal)
    ccr:                   float   # Convexity Capture Ratio
    vol_mispricing_score:  float   # 0-100
    edge_gap_pct:          float   # % difference: forecast_move - breakeven_move
    mispricing_state:      str     # CHEAP / FAIR / EXPENSIVE
    expected_value_after_decay: float   # EV adjusted for theta drag
    convexity_value_score: float   # standalone convexity quality 0-100
    rieg_label:            str
    ccr_label:             str
    error:                 Optional[str] = None

    def to_dict(self) -> dict:
        return {
            'ticker':                       self.ticker,
            'l4_rieg':                      round(self.rieg,                 4),
            'l4_ccr':                        round(self.ccr,                  3),
            'l4_vol_mispricing_score':       round(self.vol_mispricing_score, 1),
            'l4_edge_gap_pct':               round(self.edge_gap_pct,         2),
            'l4_mispricing_state':           self.mispricing_state,
            'l4_ev_after_decay':             round(self.expected_value_after_decay, 4),
            'l4_convexity_value_score':      round(self.convexity_value_score, 1),
            'l4_rieg_label':                 self.rieg_label,
            'l4_ccr_label':                  self.ccr_label,
            'l4_error':                      self.error,
        }


# ── Core computations ──────────────────────────────────────────────────────────

def _compute_rieg(forward_realised_vol: float, implied_vol: float) -> tuple[float, str]:
    """
    RIEG = implied_vol - forward_realised_vol
    Positive = IV > forecast = options expensive for buyer
    Negative = IV < forecast = options cheap for buyer (TAILWIND)

    From long-option buyer perspective:
        RIEG < -3%  → CHEAP_VOL  — buy signal
        RIEG -3–5%  → FAIR_VOL
        RIEG > 5%   → EXPENSIVE_VOL — avoid or reduce size
    """
    rieg = implied_vol - forward_realised_vol

    if rieg <= RIEG_CHEAP_THRESHOLD:
        label = 'CHEAP_VOL'
    elif rieg >= RIEG_EXPENSIVE_THRESHOLD:
        label = 'EXPENSIVE_VOL'
    else:
        label = 'FAIR_VOL'

    return float(rieg), label


def _compute_ccr(
    expected_move_pct:  float,   # forecast move % over hold period
    breakeven_pct:      float,   # % move needed to break even on option
    premium:            float,   # option premium paid (per share)
    theta_per_day:      float,   # daily theta (negative, e.g. -0.03)
    hold_days:          int,     # expected hold period
    spread_pct:         float,   # bid-ask spread as % of premium
) -> tuple[float, str]:
    """
    CCR = (Expected Payoff) / (Total Cost of Carry)

    Expected payoff: how much the option is worth if the forecast move occurs
    Total cost of carry: premium + theta drag over hold period + spread cost

    CCR >= 1.0  → GOOD — option pays out more than it costs to hold
    CCR  0.6-1  → MARGINAL
    CCR <  0.6  → POOR — contract bleeds before thesis matures
    """
    if premium <= 0 or breakeven_pct <= 0:
        return 0.0, 'UNKNOWN'

    # If the forecast move covers breakeven, estimate payoff proportionally
    if expected_move_pct <= 0:
        return 0.0, 'POOR'

    # Payoff if forecast move occurs: scale by how far beyond breakeven we go
    # If expected_move > breakeven: option is in profit by the excess
    excess_move   = max(expected_move_pct - breakeven_pct, 0.0)
    payoff_factor = excess_move / breakeven_pct   # ratio of excess to cost basis
    expected_payoff = premium * payoff_factor

    # Cost of carry
    theta_cost  = abs(theta_per_day) * hold_days   # theta decay over hold
    spread_cost = premium * spread_pct * 0.5        # half-spread on entry
    total_cost  = premium + theta_cost + spread_cost

    if total_cost <= 0:
        return 0.0, 'UNKNOWN'

    ccr = expected_payoff / total_cost

    if ccr >= CCR_GOOD_THRESHOLD:
        label = 'GOOD'
    elif ccr >= CCR_POOR_THRESHOLD:
        label = 'MARGINAL'
    else:
        label = 'POOR'

    return float(np.clip(ccr, 0.0, 10.0)), label


def _compute_edge_gap(
    expected_move_pct: float,   # AVSHUNTER forecast move %
    breakeven_pct:     float,   # option breakeven %
) -> float:
    """
    Edge gap = forecast_move% - breakeven%
    Positive = forecast move exceeds breakeven = positive expected value
    Negative = forecast move does not cover breakeven = negative EV
    """
    return float(expected_move_pct - breakeven_pct)


def _compute_ev_after_decay(
    edge_gap_pct:   float,   # % excess over breakeven
    win_prob:       float,   # P(move sufficient) — from Layer 2
    premium:        float,   # option cost
    theta_per_day:  float,   # daily decay
    hold_days:      int,
) -> float:
    """
    EV = P(win) × (edge_gap / breakeven × premium) - P(lose) × (premium + theta_drag)
    Returns decimal ratio of EV to premium (e.g. 0.25 = 25% of premium as EV).
    """
    theta_drag   = abs(theta_per_day) * hold_days
    total_outlay = premium + theta_drag

    if total_outlay <= 0 or premium <= 0:
        return 0.0

    p_win  = float(np.clip(win_prob, 0.0, 1.0))
    p_lose = 1.0 - p_win

    # Win payoff: proportional to edge gap over breakeven
    if edge_gap_pct > 0:
        win_payoff = (edge_gap_pct / max(edge_gap_pct, 0.01)) * premium * 0.5
    else:
        win_payoff = 0.0

    ev = p_win * win_payoff - p_lose * total_outlay
    return float(ev / premium)  # normalised to premium


def _compute_vol_mispricing_score(
    rieg:              float,
    edge_gap_pct:      float,
    ccr:               float,
    iv_tailwind_score: float,   # from Layer 3 (negative = cheap = tailwind)
    skew_tax:          float,   # surface richness penalty 0-1 (1 = very rich surface)
    term_structure:    str,     # 'CONTANGO' | 'BACKWARDATION' | 'UNKNOWN'
) -> float:
    """
    Composite 0-100 score. > 60 = options cheap relative to forecast.

    Component weights:
        RIEG signal          30% — core mispricing signal
        Edge gap             25% — forecast vs breakeven
        CCR geometry         25% — contract payoff quality
        Surface richness     20% — how overpriced is the vol surface
    """
    # RIEG component (30pts): cheaper = higher score
    # Map RIEG from [-0.20, +0.20] to [100, 0]
    rieg_score = float(np.clip((0.20 - rieg) / 0.40 * 100, 0, 100)) * 0.30

    # Edge gap component (25pts): larger positive gap = higher score
    # Map edge_gap from [-10%, +20%] to [0, 100]
    gap_score = float(np.clip((edge_gap_pct + 10.0) / 30.0 * 100, 0, 100)) * 0.25

    # CCR component (25pts): CCR 0→0pts, CCR 2.0→100pts
    ccr_score = float(np.clip(ccr / 2.0 * 100, 0, 100)) * 0.25

    # Surface richness component (20pts): low skew tax = cheap surface = higher score
    surf_score = float(np.clip((1.0 - skew_tax) * 100, 0, 100)) * 0.20

    # Term structure modifier: contango adds a slight tailwind for long options
    ts_mod = 3.0 if term_structure == 'CONTANGO' else (-3.0 if term_structure == 'BACKWARDATION' else 0.0)

    raw = rieg_score + gap_score + ccr_score + surf_score + ts_mod
    return float(np.clip(raw, 0.0, 100.0))


def _mispricing_state(vol_mispricing_score: float) -> str:
    if vol_mispricing_score >= MISPRICING_CHEAP_FLOOR:
        return 'CHEAP'
    elif vol_mispricing_score <= MISPRICING_EXPENSIVE_CAP:
        return 'EXPENSIVE'
    return 'FAIR'


def _convexity_value_score(ccr: float, edge_gap_pct: float, rieg: float) -> float:
    """
    Standalone convexity quality score 0-100.
    Captures whether the contract has good payoff geometry independent of
    the absolute vol mispricing level.
    """
    ccr_comp = float(np.clip(ccr / 2.0 * 50, 0, 50))
    gap_comp = float(np.clip((edge_gap_pct + 10) / 30.0 * 30, 0, 30))
    rieg_comp = float(np.clip((-rieg + 0.10) / 0.20 * 20, 0, 20))
    return float(np.clip(ccr_comp + gap_comp + rieg_comp, 0, 100))


# ── Public API ─────────────────────────────────────────────────────────────────

def compute_mispricing(
    ticker:               str,
    # Layer 3 inputs
    forward_realised_vol: float,        # annualised decimal from GARCH
    expected_move_pct:    float,        # forecast move % over hold period (Layer 3)
    iv_tailwind_score:    float,        # from Layer 3
    # Options intelligence inputs
    implied_vol:          float,        # current ATM IV (annualised decimal)
    breakeven_pct:        float,        # % move needed to break even
    premium:              float,        # option mark price
    theta_per_day:        float,        # daily theta (negative)
    spread_pct:           float,        # bid-ask spread / mid
    hold_days:            int,          # expected hold
    win_prob:             float,        # P(return > 0) from Layer 2
    skew_tax:             float = 0.3,  # surface richness penalty (0=cheap, 1=rich)
    term_structure:       str   = 'UNKNOWN',
) -> MispricingResult:
    """
    Main entry point. All vol inputs in annualised decimal form.
    breakeven_pct, expected_move_pct in % (e.g. 3.5 for 3.5%).
    """
    try:
        if forward_realised_vol <= 0 or implied_vol <= 0:
            return MispricingResult(
                ticker=ticker, rieg=0.0, ccr=0.0,
                vol_mispricing_score=50.0, edge_gap_pct=0.0,
                mispricing_state='FAIR', expected_value_after_decay=0.0,
                convexity_value_score=50.0, rieg_label='UNKNOWN',
                ccr_label='UNKNOWN', error='missing_vol_inputs',
            )

        rieg, rieg_label = _compute_rieg(forward_realised_vol, implied_vol)

        ccr, ccr_label = _compute_ccr(
            expected_move_pct = expected_move_pct,
            breakeven_pct     = breakeven_pct,
            premium           = premium,
            theta_per_day     = theta_per_day,
            hold_days         = hold_days,
            spread_pct        = spread_pct,
        )

        edge_gap = _compute_edge_gap(expected_move_pct, breakeven_pct)

        ev_decay = _compute_ev_after_decay(
            edge_gap_pct  = edge_gap,
            win_prob      = win_prob,
            premium       = premium,
            theta_per_day = theta_per_day,
            hold_days     = hold_days,
        )

        vms = _compute_vol_mispricing_score(
            rieg           = rieg,
            edge_gap_pct   = edge_gap,
            ccr            = ccr,
            iv_tailwind_score = iv_tailwind_score,
            skew_tax       = skew_tax,
            term_structure = term_structure,
        )

        convex_score = _convexity_value_score(ccr, edge_gap, rieg)
        state        = _mispricing_state(vms)

        return MispricingResult(
            ticker                    = ticker,
            rieg                      = rieg,
            ccr                       = ccr,
            vol_mispricing_score      = vms,
            edge_gap_pct              = edge_gap,
            mispricing_state          = state,
            expected_value_after_decay= ev_decay,
            convexity_value_score     = convex_score,
            rieg_label                = rieg_label,
            ccr_label                 = ccr_label,
        )

    except Exception as e:
        log.error(f'[{ticker}] Layer 4 error: {e}')
        return MispricingResult(
            ticker=ticker, rieg=0.0, ccr=0.0,
            vol_mispricing_score=50.0, edge_gap_pct=0.0,
            mispricing_state='FAIR', expected_value_after_decay=0.0,
            convexity_value_score=50.0, rieg_label='UNKNOWN',
            ccr_label='UNKNOWN', error=str(e),
        )
