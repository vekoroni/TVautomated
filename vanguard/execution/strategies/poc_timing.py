"""
AVSHUNTER EIL — Strategy S5: POC Timing  [v2.0 — regime-aware]
==============================================================
Evaluates price position relative to the Point of Control (POC).

v2.0 changes
------------
- Regime-aware extension logic using ADX:
    ADX > 25: EXTENDED from POC = CONTINUATION (strong trend lives in extension)
    ADX <= 25: EXTENDED from POC = MEAN_REVERSION_RISK (weak market reverts)
  This replaces the static penalty applied to all EXTENDED moves equally.

- The position classification is unchanged (AT_POC / ABOVE_POC / BELOW_POC / EXTENDED).
- Scoring is now ADX-adjusted within each position class.
- Size multiplier is graduated rather than stepped.

ADX source: ctx.adx_value (set by orchestrator adapter from signal row).
Falls back to default (regime = REVERT) if ADX unavailable.
"""
import sys, os

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, os.path.join(_HERE, ".."))

from execution_schema import (
    ExecutionContext, StrategyResult,
    POC_AT_THRESHOLD, POC_EXTENDED_THRESHOLD,
)

ADX_TREND_MIN = 25.0   # ADX >= this → extension is continuation, not overextension


def run(ctx: ExecutionContext) -> StrategyResult:
    price     = ctx.current_price
    poc       = ctx.poc_price
    poc_pct   = ctx.price_vs_poc_existing
    direction = (ctx.signal_direction or "LONG").upper()
    is_long   = direction not in ("SHORT", "PUT")
    adx       = getattr(ctx, "adx_value", None)   # wired by orchestrator adapter

    # ── Resolve POC distance ─────────────────────────────────────────────────
    if poc is not None and price and price > 0:
        pct_from_poc = (price - poc) / poc
    elif poc_pct is not None:
        pct_from_poc = float(poc_pct) / 100
    else:
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

    # ── ADX regime ───────────────────────────────────────────────────────────
    # In a strong trend (ADX >= 25), price living in extension is normal and
    # profitable — the market is doing what it is supposed to do.
    # In a weak or ranging market (ADX < 25), extension from POC increases
    # mean-reversion risk — the move is likely exhausted.
    strong_trend = (adx is not None and adx >= ADX_TREND_MIN)
    adx_note     = f"ADX={adx:.1f}" if adx is not None else "ADX=unknown"

    # ── Timing logic ─────────────────────────────────────────────────────────
    if position == "AT_POC":
        score     = 55
        size_mult = 0.90
        passed    = True
        detail    = (f"AT_POC ({pct_from_poc*100:+.2f}%) — congestion zone, "
                     f"direction uncertain. {adx_note}")

    elif position == "EXTENDED":
        if strong_trend:
            # Regime-aware: strong trend → extension = continuation
            score     = 80
            size_mult = 1.0
            passed    = True
            detail    = (f"EXTENDED ({pct_from_poc*100:+.2f}%) — {adx_note} confirms "
                         f"strong trend. Extension = CONTINUATION in current regime.")
        else:
            # Weak trend → extension = mean-reversion risk
            score     = 45
            size_mult = 0.80
            passed    = True
            detail    = (f"EXTENDED ({pct_from_poc*100:+.2f}%) — {adx_note} weak trend. "
                         f"Extension = MEAN_REVERSION_RISK. Reduced size.")

    elif position == "ABOVE_POC":
        if not is_long:  # PUT — price above POC, declining
            score     = 88
            size_mult = 1.0
            passed    = True
            detail    = (f"ABOVE_POC ({pct_from_poc*100:+.2f}%) — PUT: price above POC, "
                         f"downside momentum favourable. {adx_note}")
        else:            # CALL — above POC, less room before extension
            if strong_trend:
                score     = 80
                size_mult = 1.0
                detail    = (f"ABOVE_POC ({pct_from_poc*100:+.2f}%) — CALL: above POC with "
                             f"strong trend ({adx_note}). Continuation likely.")
            else:
                score     = 68
                size_mult = 0.95
                detail    = (f"ABOVE_POC ({pct_from_poc*100:+.2f}%) — CALL: above POC, "
                             f"watch for extension. {adx_note}")
            passed    = True

    else:  # BELOW_POC
        if is_long:  # CALL — below POC, upward potential
            score     = 88
            size_mult = 1.0
            passed    = True
            detail    = (f"BELOW_POC ({pct_from_poc*100:+.2f}%) — CALL: below POC, "
                         f"upside momentum favourable. {adx_note}")
        else:        # PUT — already below POC
            if strong_trend:
                score     = 75
                size_mult = 1.0
                detail    = (f"BELOW_POC ({pct_from_poc*100:+.2f}%) — PUT: below POC with "
                             f"strong downtrend ({adx_note}). Continuation probable.")
            else:
                score     = 60
                size_mult = 0.88
                detail    = (f"BELOW_POC ({pct_from_poc*100:+.2f}%) — PUT: below POC, "
                             f"mean-reversion risk in weak trend. {adx_note}")
            passed    = True

    return StrategyResult(
        strategy_name  = "S5_POC_TIMING",
        score          = round(score, 1),
        passed         = passed,
        verdict        = position,
        detail         = detail,
        size_multiplier= size_mult,
        block          = False,
    )
