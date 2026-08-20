"""
AVSHUNTER EIL — Strategy S5: POC Timing
========================================
Evaluates the current price position relative to the Point of Control
(highest-volume price level over the lookback window).

POC is the most contested price zone. Entries at/near POC carry higher
resolution uncertainty — the market has spent the most time here, which
means both support and resistance are strongest at this level.

For PUT trades:
  - Price ABOVE POC and declining → favourable (moving away from support)
  - Price AT POC → caution (congestion zone, direction uncertain)
  - Price BELOW POC → extended move, mean reversion risk

For CALL trades: mirror logic applies.

Uses either:
  1. ctx.poc_price (direct POC price from pipeline) — preferred
  2. ctx.price_vs_poc_existing (pre-computed % from POC in superbrain CSV)
"""
import sys, os

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, os.path.join(_HERE, ".."))

from execution_schema import (
    ExecutionContext, StrategyResult,
    POC_AT_THRESHOLD, POC_EXTENDED_THRESHOLD,
)


def run(ctx: ExecutionContext) -> StrategyResult:
    price     = ctx.current_price
    poc       = ctx.poc_price
    poc_pct   = ctx.price_vs_poc_existing   # pre-computed % from POC (positive = above)
    direction = (ctx.signal_direction or "LONG").upper()
    is_long   = direction not in ("SHORT", "PUT")

    # ── Resolve POC distance ─────────────────────────────────────────────────
    if poc is not None and price and price > 0:
        pct_from_poc = (price - poc) / poc   # positive = price above POC
    elif poc_pct is not None:
        pct_from_poc = float(poc_pct) / 100  # convert from % string/float
    else:
        # No POC data — return neutral
        result = StrategyResult(
            strategy_name  = "S5_POC_TIMING",
            score          = 65.0,
            passed         = True,
            verdict        = "NO_POC_DATA",
            detail         = "No POC price available in superbrain or context",
            size_multiplier= 1.0,
            block          = False,
        )
        return result

    abs_pct = abs(pct_from_poc)

    # ── Position classification ──────────────────────────────────────────────
    if abs_pct <= POC_AT_THRESHOLD:
        position = "AT_POC"
    elif pct_from_poc > 0:
        position = "ABOVE_POC"
    else:
        position = "BELOW_POC"

    if abs_pct > POC_EXTENDED_THRESHOLD:
        position = "EXTENDED"

    # ── Timing logic ─────────────────────────────────────────────────────────
    # For PUT trades: ideal = above POC (about to move down through it)
    # For CALL trades: ideal = below POC (about to move up through it)

    if position == "AT_POC":
        score     = 55
        size_mult = 0.9
        passed    = True
        detail    = f"AT_POC ({pct_from_poc*100:+.2f}%) — congestion zone, direction uncertain"

    elif position == "EXTENDED":
        # Price far from POC — mean reversion risk for both directions
        score     = 50
        size_mult = 0.85
        passed    = True
        detail    = f"EXTENDED from POC ({pct_from_poc*100:+.2f}%) — elevated mean reversion risk"

    elif position == "ABOVE_POC":
        if not is_long:  # PUT/SHORT — ideal setup
            score     = 88
            size_mult = 1.0
            passed    = True
            detail    = f"ABOVE_POC ({pct_from_poc*100:+.2f}%) — PUT thesis: price above POC, downside momentum favourable"
        else:  # CALL/LONG — price above POC, less room before extension
            score     = 72
            size_mult = 1.0
            passed    = True
            detail    = f"ABOVE_POC ({pct_from_poc*100:+.2f}%) — CALL thesis: price above POC, watch for extension"

    else:  # BELOW_POC
        if is_long:  # CALL/LONG — ideal setup
            score     = 88
            size_mult = 1.0
            passed    = True
            detail    = f"BELOW_POC ({pct_from_poc*100:+.2f}%) — CALL thesis: price below POC, upside momentum favourable"
        else:  # PUT/SHORT — price already below POC, mean reversion risk
            score     = 65
            size_mult = 0.9
            passed    = True
            detail    = f"BELOW_POC ({pct_from_poc*100:+.2f}%) — PUT thesis: price already below POC, watch for mean reversion"

    return StrategyResult(
        strategy_name  = "S5_POC_TIMING",
        score          = round(score, 1),
        passed         = passed,
        verdict        = position,
        detail         = detail,
        size_multiplier= size_mult,
        block          = False,
    )
