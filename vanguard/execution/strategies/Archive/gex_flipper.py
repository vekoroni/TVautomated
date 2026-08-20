"""
AVSHUNTER EIL — Strategy S3: GEX Flip Proximity
================================================
Identifies whether the underlying is near the Gamma Flip level —
the price at which dealer gamma crosses from positive to negative.

Near the flip: dealer hedging becomes reflexive, volatility expands.
For PUTs: approaching from above is often accelerating (beneficial).
For CALLs: approaching the flip from below risks sharp reversal.

GEX map: {strike: gamma_exposure_dollars}
  Positive GEX → dealers long gamma (dampening)
  Negative GEX → dealers short gamma (amplifying)

Flip level = strike closest to zero crossing.
"""
import sys, os
from typing import Dict, Optional

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, os.path.join(_HERE, ".."))

from execution_schema import ExecutionContext, StrategyResult

# Proximity thresholds (% distance from current price to flip)
FLIP_NEAR_PCT   = 0.03   # Within 3% → AT_FLIP
FLIP_CLOSE_PCT  = 0.07   # Within 7% → APPROACHING
# Beyond 7% → FAR


def _find_gex_flip(gex_by_strike: Dict[float, float], current_price: float) -> Optional[float]:
    """Find the GEX zero-crossing level nearest to current price."""
    if not gex_by_strike or len(gex_by_strike) < 2:
        return None

    strikes = sorted(gex_by_strike.keys())
    best_flip = None
    best_dist = float("inf")

    for i in range(len(strikes) - 1):
        s1, s2 = strikes[i], strikes[i + 1]
        g1, g2 = gex_by_strike[s1], gex_by_strike[s2]

        # Zero crossing between s1 and s2
        if g1 * g2 < 0:
            # Linear interpolation of zero crossing
            flip = s1 + (0 - g1) * (s2 - s1) / (g2 - g1)
            dist = abs(flip - current_price)
            if dist < best_dist:
                best_dist = dist
                best_flip = flip

    return best_flip


def _gex_regime(gex_by_strike: Dict[float, float], current_price: float) -> str:
    """Determine current GEX regime based on net GEX around current price."""
    if not gex_by_strike:
        return "NEUTRAL"

    # Weight GEX by proximity to current price (within 10%)
    band = current_price * 0.10
    net_gex = sum(
        v for k, v in gex_by_strike.items()
        if abs(k - current_price) <= band
    )

    if net_gex > 500_000:
        return "DAMPENING"
    elif net_gex < -500_000:
        return "AMPLIFYING"
    return "NEUTRAL"


def run(ctx: ExecutionContext) -> StrategyResult:
    gex   = ctx.gex_by_strike or {}
    price = ctx.current_price
    direction = (ctx.signal_direction or "LONG").upper()

    # ── No GEX data ──────────────────────────────────────────────────────────
    if not gex or price is None or price <= 0:
        result = StrategyResult(
            strategy_name  = "S3_GEX_FLIP",
            score          = 70.0,
            passed         = True,
            verdict        = "FAR",
            detail         = "No GEX data — cannot assess flip proximity",
            size_multiplier= 1.0,
            block          = False,
        )
        result.gex_flip_level    = None
        result.gex_proximity_pct = 1.0
        result.gex_regime        = "NEUTRAL"
        return result

    regime    = _gex_regime(gex, price)
    flip_level = _find_gex_flip(gex, price)

    if flip_level is None:
        proximity_pct = 1.0
        proximity_str = "FAR"
    else:
        proximity_pct = abs(flip_level - price) / price
        if proximity_pct <= FLIP_NEAR_PCT:
            proximity_str = "AT_FLIP"
        elif proximity_pct <= FLIP_CLOSE_PCT:
            proximity_str = "APPROACHING"
        else:
            proximity_str = "FAR"

    # ── Scoring logic ────────────────────────────────────────────────────────
    # AMPLIFYING GEX near flip is good for directional options (moves larger)
    # DAMPENING GEX far from flip is safest (mean-reversion, stable)

    if proximity_str == "FAR":
        if regime == "DAMPENING":
            score     = 85
            size_mult = 1.0
            detail    = f"FAR from flip ({proximity_pct*100:.1f}%) | DAMPENING regime — stable"
        elif regime == "AMPLIFYING":
            score     = 80
            size_mult = 1.0
            detail    = f"FAR from flip ({proximity_pct*100:.1f}%) | AMPLIFYING — momentum favourable"
        else:
            score     = 82
            size_mult = 1.0
            detail    = f"FAR from flip ({proximity_pct*100:.1f}%) | NEUTRAL GEX"
        passed = True
        block  = False

    elif proximity_str == "APPROACHING":
        if direction in ("SHORT", "PUT"):
            # For PUT trades, approaching flip from above accelerates the move
            score     = 75
            size_mult = 1.0
            detail    = f"APPROACHING flip ${flip_level:.2f} ({proximity_pct*100:.1f}%) | PUT — momentum likely accelerates"
        else:
            # For CALL trades, approaching flip is a reversal risk
            score     = 60
            size_mult = 0.85
            detail    = f"APPROACHING flip ${flip_level:.2f} ({proximity_pct*100:.1f}%) | CALL — reversal risk at flip"
        passed = True
        block  = False

    else:  # AT_FLIP
        if direction in ("SHORT", "PUT"):
            score     = 65
            size_mult = 0.8
            detail    = f"AT_FLIP ${flip_level:.2f} ({proximity_pct*100:.1f}%) | Dealer gamma zero — high volatility zone, PUT may benefit"
        else:
            score     = 40
            size_mult = 0.7
            detail    = f"AT_FLIP ${flip_level:.2f} ({proximity_pct*100:.1f}%) | CALL at gamma zero — bidirectional risk, caution"
        passed = score >= 50
        block  = False

    result = StrategyResult(
        strategy_name  = "S3_GEX_FLIP",
        score          = round(score, 1),
        passed         = passed,
        verdict        = proximity_str,
        detail         = detail,
        size_multiplier= size_mult,
        block          = block,
    )
    result.gex_flip_level    = round(flip_level, 2) if flip_level else None
    result.gex_proximity_pct = round(proximity_pct, 4)
    result.gex_regime        = regime
    return result
