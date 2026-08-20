"""
AVSHUNTER EIL — Strategy S2: IV Distortion Check
=================================================
Detects whether IV has moved materially since the overnight run,
making the premium estimate in the Options tab stale.

Checks:
  - IV ask premium above mid (vol points)
  - IV ask/mid ratio for thin names (low OI)
  - Relative spread of IV across bid/ask

A flagged IV distortion means: verify live mid in Tastytrade before
entering the premium shown in the ENTER TRADE modal.
"""
import sys, os

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, os.path.join(_HERE, ".."))

from execution_schema import (
    ExecutionContext, StrategyResult,
    IV_DISTORTION_THRESHOLD_ABS, IV_DISTORTION_THRESHOLD_REL,
    IV_THIN_NAME_OI_THRESHOLD,
)


def run(ctx: ExecutionContext) -> StrategyResult:
    iv_bid = ctx.iv_bid
    iv_mid = ctx.iv_mid
    iv_ask = ctx.iv_ask
    oi     = ctx.options_open_interest or 0

    # ── Insufficient data ────────────────────────────────────────────────────
    if iv_mid is None or iv_ask is None:
        result = StrategyResult(
            strategy_name  = "S2_IV_DISTORTION",
            score          = 70.0,   # neutral when no data
            passed         = True,
            verdict        = "CLEAN",
            detail         = "No IV data available — cannot assess distortion",
            size_multiplier= 1.0,
            block          = False,
        )
        result.iv_ask_premium  = 0.0
        result.spread_pct_live = None
        return result

    # ── IV ask premium (vol points above mid) ────────────────────────────────
    iv_premium_pts = (iv_ask - iv_mid) * 100   # convert to vol points (percentage)
    iv_ratio       = iv_ask / iv_mid if iv_mid > 0 else 1.0

    # For thin names, use relative ratio; for liquid names use absolute threshold
    is_thin = oi < IV_THIN_NAME_OI_THRESHOLD

    if is_thin:
        distorted = iv_ratio >= IV_DISTORTION_THRESHOLD_REL
    else:
        distorted = iv_premium_pts >= IV_DISTORTION_THRESHOLD_ABS

    # ── IV spread quality ────────────────────────────────────────────────────
    if iv_bid is not None and iv_mid > 0:
        iv_spread_pct = (iv_ask - iv_bid) / iv_mid * 100
    else:
        iv_spread_pct = None

    # ── Score ────────────────────────────────────────────────────────────────
    if distorted:
        if is_thin and iv_ratio >= 1.15:
            score     = 30
            size_mult = 0.7
            verdict   = "IV_DISTORTED"
            detail    = (f"THIN NAME: IV ask/mid ratio {iv_ratio:.3f} >= {IV_DISTORTION_THRESHOLD_REL} "
                        f"(OI={oi}). Premium estimate unreliable — verify live.")
        elif not is_thin and iv_premium_pts >= IV_DISTORTION_THRESHOLD_ABS * 1.5:
            score     = 35
            size_mult = 0.75
            verdict   = "IV_DISTORTED"
            detail    = (f"IV ask premium {iv_premium_pts:.2f} vol pts — "
                        f"significantly above mid. Options tab premium may be understated.")
        else:
            score     = 55
            size_mult = 0.9
            verdict   = "WATCH"
            detail    = (f"IV ask premium {iv_premium_pts:.2f} vol pts "
                        f"(threshold {IV_DISTORTION_THRESHOLD_ABS}). Monitor.")
        passed = False
    else:
        score     = 90
        size_mult = 1.0
        passed    = True
        verdict   = "CLEAN"
        detail    = f"IV ask premium {iv_premium_pts:.2f} vol pts — within normal range"

    result = StrategyResult(
        strategy_name  = "S2_IV_DISTORTION",
        score          = round(score, 1),
        passed         = passed,
        verdict        = verdict,
        detail         = detail,
        size_multiplier= size_mult,
        block          = False,   # IV distortion never hard-blocks; it warns
    )
    result.iv_ask_premium  = round(iv_premium_pts, 3)
    result.spread_pct_live = round(iv_spread_pct, 2) if iv_spread_pct is not None else None
    return result
