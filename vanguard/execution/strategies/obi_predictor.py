"""
AVSHUNTER EIL — Strategy S4: Order Book Imbalance (OBI)  [v2.0 — flow synthesis]
==================================================================================
Measures directional pressure using Polygon.io NBBO top-of-book data, then
synthesises with GEX regime and OI wall position for a truer flow alignment score.

v2.0 changes
------------
- True flow alignment synthesis:
    true_alignment = OBI_direction + GEX_direction + wall_clearance_direction
  This replaces the equity-only OBI proxy with a three-signal composite.

- GEX regime integration:
    AMPLIFYING GEX (dealers short gamma) + aligned OBI = strong confirmation
    DAMPENING GEX (dealers long gamma) + aligned OBI = dampened, but still valid
    Contradicting GEX overrides OBI alignment if GEX > OBI by weight

- Wall clearance: if price is below call wall (for CALL) or above put wall (for PUT),
  alignment is confirmed. If at the wall, flag as friction even if OBI is bullish.

- OBI opposition: 10% size tax only (unchanged). OBI alone never hard-blocks.
- size_multiplier scales with alignment strength, not binary passed/failed.

Note: equity top-of-book still used as OBI input (Sprint 2 upgrade: options flow).
GEX and wall data are passed via ctx.gex_by_strike and derived fields on ctx.
"""
import sys, os
from typing import Optional, Dict

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, os.path.join(_HERE, ".."))

from execution_schema import (
    ExecutionContext, StrategyResult,
    OBI_BULLISH_THRESHOLD, OBI_BEARISH_THRESHOLD,
)

# Synthesis weights
W_OBI  = 0.45   # OBI is primary (direct flow signal)
W_GEX  = 0.35   # GEX regime is structural context
W_WALL = 0.20   # Wall clearance is geometric constraint


def _gex_score(ctx: ExecutionContext, is_long: bool) -> float:
    """
    Return +1 (GEX aligned), 0 (neutral), -1 (opposed) based on regime.
    AMPLIFYING GEX + LONG  = dealers short gamma = momentum works for us = +1
    DAMPENING GEX + LONG   = dealers long gamma  = price pinned         = -0.5
    NEUTRAL                                                              =  0
    """
    gex = ctx.gex_by_strike or {}
    price = ctx.current_price
    if not gex or not price:
        return 0.0

    band    = price * 0.10
    net_gex = sum(v for k, v in gex.items() if abs(k - price) <= band)

    if net_gex > 500_000:
        regime = "DAMPENING"
    elif net_gex < -500_000:
        regime = "AMPLIFYING"
    else:
        regime = "NEUTRAL"

    if regime == "AMPLIFYING":
        return 1.0 if is_long else 1.0   # both long/short benefit from amplifying vol
    elif regime == "DAMPENING":
        return -0.5   # price pins near POC — neither direction gets free run
    return 0.0


def _wall_clearance_score(ctx: ExecutionContext, is_long: bool) -> float:
    """
    Return +1 if price has clearance to target wall, -1 if at the wall.
    Uses gex_by_strike to infer call_wall and put_wall positions.
    """
    gex   = ctx.gex_by_strike or {}
    price = ctx.current_price
    if not gex or not price:
        return 0.0

    strikes = sorted(gex.keys())
    if not strikes:
        return 0.0

    # Call wall = strike with highest positive GEX above current price
    above  = [(k, v) for k, v in gex.items() if k > price and v > 0]
    below  = [(k, v) for k, v in gex.items() if k < price and v < 0]

    call_wall = min(above, key=lambda x: x[0])[0] if above else None
    put_wall  = max(below, key=lambda x: x[0])[0] if below else None

    if is_long and call_wall is not None:
        gap_pct = (call_wall - price) / price
        if gap_pct > 0.03:     # > 3% clearance = clear runway
            return 1.0
        elif gap_pct > 0.01:
            return 0.0
        else:
            return -1.0        # at the wall = friction

    if not is_long and put_wall is not None:
        gap_pct = (price - put_wall) / price
        if gap_pct > 0.03:
            return 1.0
        elif gap_pct > 0.01:
            return 0.0
        else:
            return -1.0

    return 0.0


def run(ctx: ExecutionContext) -> StrategyResult:
    bid_sz    = ctx.l2_bid_size
    ask_sz    = ctx.l2_ask_size
    direction = (ctx.signal_direction or "LONG").upper()
    is_long   = direction not in ("SHORT", "PUT")

    # ── No OBI data ───────────────────────────────────────────────────────────
    if bid_sz is None or ask_sz is None or (bid_sz + ask_sz) <= 0:
        # Still run GEX and wall synthesis even without OBI
        gex_s  = _gex_score(ctx, is_long)
        wall_s = _wall_clearance_score(ctx, is_long)
        synth  = W_GEX * gex_s + W_WALL * wall_s

        if synth > 0.20:
            score = 72; size_mult = 1.0; regime = "GEX_ALIGNED"
            detail = f"No NBBO data — GEX+wall synthesis: aligned ({synth:+.2f})"
        elif synth < -0.20:
            score = 50; size_mult = 0.90; regime = "GEX_OPPOSED"
            detail = f"No NBBO data — GEX+wall synthesis: friction ({synth:+.2f})"
        else:
            score = 65; size_mult = 1.0; regime = "NEUTRAL"
            detail = "No NBBO data — neutral synthesis from GEX+wall"

        result = StrategyResult(
            strategy_name  = "S4_OBI",
            score          = round(score, 1),
            passed         = True,
            verdict        = regime,
            detail         = detail,
            size_multiplier= size_mult,
            block          = False,
        )
        result.obi_raw    = 0.5
        result.obi_regime = regime
        return result

    # ── OBI computation ───────────────────────────────────────────────────────
    obi = bid_sz / (bid_sz + ask_sz)

    if obi > OBI_BULLISH_THRESHOLD:
        obi_regime  = "BULLISH"
        obi_aligned = 1.0 if is_long else -1.0
    elif obi < OBI_BEARISH_THRESHOLD:
        obi_regime  = "BEARISH"
        obi_aligned = -1.0 if is_long else 1.0
    else:
        obi_regime  = "NEUTRAL"
        obi_aligned = 0.0

    # ── Flow synthesis: OBI + GEX + wall ────────────────────────────────────
    gex_s  = _gex_score(ctx, is_long)
    wall_s = _wall_clearance_score(ctx, is_long)

    # Normalise OBI alignment to -1..+1 by strength of imbalance
    if obi_aligned > 0:
        obi_strength = min(1.0, (obi - OBI_BULLISH_THRESHOLD) / (1.0 - OBI_BULLISH_THRESHOLD) + 0.5)
    elif obi_aligned < 0:
        obi_strength = max(-1.0, -(OBI_BEARISH_THRESHOLD - obi) / OBI_BEARISH_THRESHOLD - 0.5)
    else:
        obi_strength = 0.0

    synthesis = W_OBI * obi_strength + W_GEX * gex_s + W_WALL * wall_s

    # ── Score and size ────────────────────────────────────────────────────────
    if synthesis >= 0.6:
        score      = 92
        size_mult  = 1.0
        verdict    = "STRONGLY_ALIGNED"
        detail     = (f"OBI={obi:.3f} ({obi_regime}) + GEX={gex_s:+.1f} + Wall={wall_s:+.1f} "
                      f"→ synthesis={synthesis:+.2f} — strong flow alignment")
    elif synthesis >= 0.2:
        score      = 78
        size_mult  = 1.0
        verdict    = "ALIGNED"
        detail     = (f"OBI={obi:.3f} ({obi_regime}) + GEX={gex_s:+.1f} + Wall={wall_s:+.1f} "
                      f"→ synthesis={synthesis:+.2f} — moderate alignment")
    elif synthesis >= -0.1:
        score      = 65
        size_mult  = 1.0
        verdict    = "NEUTRAL"
        detail     = (f"OBI={obi:.3f} neutral synthesis ({synthesis:+.2f}) "
                      f"— no directional flow confirmation")
    elif synthesis >= -0.4:
        score      = 50
        size_mult  = 0.90   # 10% size tax for opposition — never a block
        verdict    = "OPPOSED"
        detail     = (f"OBI={obi:.3f} ({obi_regime}) + GEX={gex_s:+.1f} + Wall={wall_s:+.1f} "
                      f"→ synthesis={synthesis:+.2f} — mild flow opposition (size tax)")
    else:
        score      = 35
        size_mult  = 0.80   # stronger tax for clear multi-signal opposition
        verdict    = "STRONGLY_OPPOSED"
        detail     = (f"OBI={obi:.3f} ({obi_regime}) + GEX={gex_s:+.1f} + Wall={wall_s:+.1f} "
                      f"→ synthesis={synthesis:+.2f} — multi-signal flow opposition")

    passed = score >= 50   # OPPOSED still passes — it is a tax, not a veto

    result = StrategyResult(
        strategy_name  = "S4_OBI",
        score          = round(score, 1),
        passed         = passed,
        verdict        = verdict,
        detail         = detail,
        size_multiplier= size_mult,
        block          = False,   # OBI+GEX synthesis never hard-blocks
    )
    result.obi_raw    = round(obi, 4)
    result.obi_regime = obi_regime
    return result
