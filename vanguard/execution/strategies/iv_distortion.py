"""
AVSHUNTER EIL — Strategy S2: IV Distortion Check  [v2.0 — directional]
=======================================================================
Detects whether IV has moved materially since the overnight run AND
whether that movement is a tailwind or headwind for the thesis.

v2.0 changes
------------
- IV distortion is now directional, not binary.
  IV expanding → potential breakout catalyst (tailwind for directional options)
  IV compressing → potential pin or mean-reversion (headwind for long options)
  IV flat but expensive → cost headwind, not execution blocker

- iv_tailwind_score computed and attached to result:
    > 0 : IV moving WITH thesis (expansion for CALL into breakout, etc.)
    < 0 : IV moving AGAINST thesis (compression into CALL, expansion into PUT short)
    = 0 : neutral / no direction

- Scoring reflects direction of IV movement relative to trade thesis,
  not just the magnitude of distortion at the ask.

- Hard block retained ONLY for extreme thin-name IV distortion (ratio >= 1.20)
  where the quote is genuinely unreliable.

- iv_tailwind_score is passed downstream to:
    MonetisationPolicy (IV gate)
    avshunter_monetisation_policy.py map_options_row_to_policy_input()
"""
import sys, os
from typing import Optional

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, os.path.join(_HERE, ".."))

from execution_schema import (
    ExecutionContext, StrategyResult,
    IV_DISTORTION_THRESHOLD_ABS, IV_DISTORTION_THRESHOLD_REL,
    IV_THIN_NAME_OI_THRESHOLD,
)

# iv_tailwind_score thresholds
TAILWIND_STRONG   =  0.20   # IV clearly expanding in thesis direction
HEADWIND_STRONG   = -0.20   # IV clearly compressing against thesis
NEUTRAL_BAND      =  0.10   # within ±10% = neutral


def _iv_tailwind(iv_mid: float, iv_bid: Optional[float],
                 iv_ask: float, direction: str) -> float:
    """
    Compute iv_tailwind_score in [-1, +1].

    Proxy for IV direction: use (iv_ask - iv_bid) / iv_mid as a surface width
    signal. Wide surface = market uncertain / vol expanding = potential move.
    Narrow surface = vol suppressed.

    Directional adjustment:
      CALL/LONG: expanding IV = tailwind (move incoming), compressing = headwind
      PUT/SHORT: expanding IV into PUT = tailwind (fear rising), compressing = headwind
    Both directional trades benefit from expanding vol — they are long vega.
    """
    if iv_mid is None or iv_mid <= 0:
        return 0.0

    is_long = direction.upper() not in ("SHORT",)  # CALLs and PUTs are both long vega

    if iv_bid is not None and iv_mid > 0:
        iv_width_ratio = (iv_ask - iv_bid) / iv_mid   # 0 = perfectly liquid, 1+ = very wide
    else:
        iv_width_ratio = (iv_ask - iv_mid) / iv_mid * 2   # use ask premium as proxy

    # Scale to -1..+1: wide vol surface = expansion signal (positive for long vega)
    # Narrow (<5% width) = compression = negative for long vega
    if iv_width_ratio > 0.15:        # >15% spread = vol expanding
        raw = min(1.0, iv_width_ratio * 2)
    elif iv_width_ratio < 0.05:      # <5% spread = vol compressed
        raw = max(-1.0, (iv_width_ratio - 0.05) * 10)
    else:
        raw = 0.0

    # Both CALLs and PUTs are long vega — expanding vol helps both
    return round(raw if is_long else raw, 3)


def run(ctx: ExecutionContext) -> StrategyResult:
    iv_bid = ctx.iv_bid
    iv_mid = ctx.iv_mid
    iv_ask = ctx.iv_ask
    oi     = ctx.options_open_interest or 0
    direction = (ctx.signal_direction or "LONG").upper()

    # ── No data ───────────────────────────────────────────────────────────────
    if iv_mid is None or iv_ask is None:
        result = StrategyResult(
            strategy_name  = "S2_IV_DISTORTION",
            score          = 70.0,
            passed         = True,
            verdict        = "CLEAN",
            detail         = "No IV data — cannot assess distortion",
            size_multiplier= 1.0,
            block          = False,
        )
        result.iv_ask_premium   = 0.0
        result.spread_pct_live  = None
        result.iv_tailwind_score= 0.0
        return result

    # ── IV metrics ────────────────────────────────────────────────────────────
    iv_premium_pts = (iv_ask - iv_mid) * 100
    iv_ratio       = iv_ask / iv_mid if iv_mid > 0 else 1.0
    is_thin        = oi < IV_THIN_NAME_OI_THRESHOLD

    if is_thin:
        distorted = iv_ratio >= IV_DISTORTION_THRESHOLD_REL
    else:
        distorted = iv_premium_pts >= IV_DISTORTION_THRESHOLD_ABS

    # IV spread quality
    iv_spread_pct = (iv_ask - iv_bid) / iv_mid * 100 if iv_bid is not None and iv_mid > 0 else None

    # IV tailwind score
    tailwind = _iv_tailwind(iv_mid, iv_bid, iv_ask, direction)

    # ── Directional scoring ───────────────────────────────────────────────────
    if not distorted:
        # Clean IV surface — score by tailwind direction
        if tailwind > TAILWIND_STRONG:
            score     = 95
            size_mult = 1.0
            verdict   = "IV_TAILWIND"
            detail    = (f"IV surface clean. Tailwind score={tailwind:.2f} — "
                         f"vol expanding in thesis direction. Premium likely to increase.")
        elif tailwind < HEADWIND_STRONG:
            score     = 65
            size_mult = 0.90
            verdict   = "IV_HEADWIND"
            detail    = (f"IV surface clean but compressing (tailwind={tailwind:.2f}). "
                         f"Long vega headwind — option may lose value from vol decay.")
        else:
            score     = 90
            size_mult = 1.0
            verdict   = "CLEAN"
            detail    = f"IV ask premium {iv_premium_pts:.2f} vol pts — within normal range. Neutral direction."
        passed = True
        block  = False

    elif is_thin and iv_ratio >= 1.20:
        # Hard block only for extreme thin-name distortion — quote genuinely unreliable
        score     = 10
        size_mult = 0.0
        verdict   = "IV_DISTORTED_BLOCK"
        detail    = (f"THIN NAME extreme: IV ask/mid ratio {iv_ratio:.3f} >= 1.20 "
                     f"(OI={oi}). Quote unreliable — execution price unknowable.")
        passed    = False
        block     = True

    elif distorted and tailwind > TAILWIND_STRONG:
        # Distorted IV but expanding in thesis direction — reduce size, don't block
        score     = 65
        size_mult = 0.85
        verdict   = "IV_DISTORTED_TAILWIND"
        detail    = (f"IV ask premium {iv_premium_pts:.2f} vol pts — distorted but "
                     f"expanding in thesis direction (tailwind={tailwind:.2f}). "
                     f"Verify live mid in Tastytrade before entry.")
        passed    = True
        block     = False

    else:
        # Distorted with neutral or adverse direction
        if iv_premium_pts >= IV_DISTORTION_THRESHOLD_ABS * 1.5 or (is_thin and iv_ratio >= 1.15):
            score     = 35
            size_mult = 0.75
            verdict   = "IV_DISTORTED"
            detail    = (f"IV ask premium {iv_premium_pts:.2f} vol pts — "
                         f"significantly distorted (tailwind={tailwind:.2f}). "
                         f"Premium estimate unreliable — verify live mid in Tastytrade.")
        else:
            score     = 58
            size_mult = 0.90
            verdict   = "WATCH"
            detail    = (f"IV ask premium {iv_premium_pts:.2f} vol pts. "
                         f"Mild distortion (tailwind={tailwind:.2f}). Monitor.")
        passed = True
        block  = False

    result = StrategyResult(
        strategy_name  = "S2_IV_DISTORTION",
        score          = round(score, 1),
        passed         = passed,
        verdict        = verdict,
        detail         = detail,
        size_multiplier= size_mult,
        block          = block,
    )
    result.iv_ask_premium    = round(iv_premium_pts, 3)
    result.spread_pct_live   = round(iv_spread_pct, 2) if iv_spread_pct is not None else None
    result.iv_tailwind_score = tailwind
    return result

