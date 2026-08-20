"""
AVSHUNTER EIL — Strategy S4: Order Book Imbalance (OBI)
========================================================
Measures directional pressure in the top-of-book using Polygon.io
NBBO data (l2_bid_size / l2_ask_size).

OBI = bid_size / (bid_size + ask_size)
  OBI > 0.65 → BULLISH (more buyers at bid, upward pressure)
  OBI < 0.35 → BEARISH (more sellers at ask, downward pressure)
  0.35–0.65  → NEUTRAL

For a LONG/CALL trade: BULLISH OBI is ALIGNED, BEARISH is OPPOSED.
For a SHORT/PUT trade: BEARISH OBI is ALIGNED, BULLISH is OPPOSED.

Note: This uses equity top-of-book as a proxy for options flow direction.
Sprint 2 will replace with live options order flow data.
"""
import sys, os

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, os.path.join(_HERE, ".."))

from execution_schema import (
    ExecutionContext, StrategyResult,
    OBI_BULLISH_THRESHOLD, OBI_BEARISH_THRESHOLD,
)


def run(ctx: ExecutionContext) -> StrategyResult:
    bid_sz = ctx.l2_bid_size
    ask_sz = ctx.l2_ask_size
    direction = (ctx.signal_direction or "LONG").upper()
    is_long = direction not in ("SHORT", "PUT")

    # ── No data ──────────────────────────────────────────────────────────────
    if bid_sz is None or ask_sz is None or (bid_sz + ask_sz) <= 0:
        result = StrategyResult(
            strategy_name  = "S4_OBI",
            score          = 65.0,   # neutral
            passed         = True,
            verdict        = "NEUTRAL",
            detail         = "No L2 NBBO data — cannot assess order book imbalance",
            size_multiplier= 1.0,
            block          = False,
        )
        result.obi_raw    = 0.5
        result.obi_regime = "NEUTRAL"
        return result

    # ── OBI calculation ──────────────────────────────────────────────────────
    obi = bid_sz / (bid_sz + ask_sz)

    if obi > OBI_BULLISH_THRESHOLD:
        regime = "BULLISH"
    elif obi < OBI_BEARISH_THRESHOLD:
        regime = "BEARISH"
    else:
        regime = "NEUTRAL"

    # ── Alignment with trade direction ───────────────────────────────────────
    if regime == "NEUTRAL":
        aligned = "NEUTRAL"
        score     = 65
        size_mult = 1.0
        detail    = f"OBI={obi:.3f} — neutral order flow, no directional confirmation"
        passed    = True
    elif (is_long and regime == "BULLISH") or (not is_long and regime == "BEARISH"):
        aligned = "ALIGNED"
        # Scale score by strength of imbalance
        if is_long:
            strength = (obi - OBI_BULLISH_THRESHOLD) / (1.0 - OBI_BULLISH_THRESHOLD)
        else:
            strength = (OBI_BEARISH_THRESHOLD - obi) / OBI_BEARISH_THRESHOLD
        score     = 75 + strength * 20   # 75–95
        score     = min(95, score)
        size_mult = 1.0
        detail    = f"OBI={obi:.3f} — {regime} flow ALIGNED with {direction} thesis"
        passed    = True
    else:
        aligned = "OPPOSED"
        # Penalise based on severity of opposition
        if is_long:
            severity = (OBI_BEARISH_THRESHOLD - obi) / OBI_BEARISH_THRESHOLD if obi < OBI_BEARISH_THRESHOLD else 0
        else:
            severity = (obi - OBI_BULLISH_THRESHOLD) / (1.0 - OBI_BULLISH_THRESHOLD) if obi > OBI_BULLISH_THRESHOLD else 0
        score     = 50 - severity * 25   # 25–50
        score     = max(25, score)
        size_mult = 0.8
        detail    = f"OBI={obi:.3f} — {regime} flow OPPOSED to {direction} thesis"
        passed    = False

    result = StrategyResult(
        strategy_name  = "S4_OBI",
        score          = round(score, 1),
        passed         = passed,
        verdict        = aligned,
        detail         = detail,
        size_multiplier= size_mult,
        block          = False,   # OBI never hard-blocks
    )
    result.obi_raw    = round(obi, 4)
    result.obi_regime = regime
    return result
