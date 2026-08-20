"""
AVSHUNTER EIL — Strategy 2: Options Bid/Ask IV Distortion Detection
===================================================================
Sprint 2 | Priority: HIGH | Data: MarketData.app options quotes

RATIONALE
---------
The bid/ask spread on an options contract encodes the market maker's
uncertainty about fair value. On Tastytrade, options fill at or near
the ask on buys — the IV premium paid vs mid-IV is the real execution
cost before any directional move. This premium is a direct, measurable
drag on actuarial edge.

Example: If mid-IV = 45.0 and ask-IV = 49.2, you are paying 4.2 vol
points of premium. On a $5.00 option with 30 DTE, this is approximately
0.3–0.5% of underlying value in additional breakeven hurdle.

DATA SOURCE: MarketData.app /v1/options/quotes/{symbol}/
Fields used: iv (at mid), bid, ask, openInterest
IV at bid and ask must be computed separately via Black-Scholes
if MarketData.app does not provide them directly. The EIL runner
handles this computation before calling run().

THRESHOLDS
----------
Primary (liquid names, OI >= 500):
    ask_IV - mid_IV > 3.0 vol points → DISTORTED

Secondary (thin names, OI < 500):
    ask_IV / mid_IV > 1.08 → DISTORTED

SCORING
-------
    Premium < 1.0 vol pts  → 100  pristine spread
    Premium 1.0–2.0        → 80   acceptable
    Premium 2.0–3.0        → 60   marginal
    Premium 3.0–5.0        → 30   distorted — scale down
    Premium > 5.0          → 10   severely distorted
    No options data         → 75  neutral (equities/ETFs without options)

SIZE MULTIPLIER when DISTORTED
------------------------------
    Reducing size when spreads are wide means Kelly fraction is applied
    to a smaller base — the EV calculation remains valid because the
    per-unit spread cost is unchanged but total capital at risk is lower.
    Multiplier = max(0.5, 1.0 - (premium - 3.0) * 0.1)
    e.g. 4.0 vol pts → 0.9, 5.0 vol pts → 0.8, 8.0 vol pts → 0.5

Version : 1.0.0
Date    : 2026-03-08
"""

import math
from typing import Optional

from execution_schema import (
    ExecutionContext, StrategyResult,
    IV_DISTORTION_THRESHOLD_ABS,
    IV_DISTORTION_THRESHOLD_REL,
    IV_THIN_NAME_OI_THRESHOLD,
)


def _black_scholes_iv_approx(option_price: float, underlying: float,
                               strike: float, tte_years: float,
                               rate: float = 0.05) -> Optional[float]:
    """
    Simplified IV approximation using Brenner-Subrahmanyam formula.
    Used when MarketData.app provides bid/ask prices but not IV at those prices.

    This is an approximation (±1-2 vol points) — sufficient for distortion
    detection. For production, replace with scipy's brentq solver against
    full Black-Scholes.

    Returns IV as decimal (0.45 = 45%) or None if inputs invalid.
    """
    if tte_years <= 0 or underlying <= 0 or strike <= 0:
        return None
    try:
        atm_approx = option_price / (underlying * math.sqrt(tte_years / (2 * math.pi)))
        return atm_approx
    except (ZeroDivisionError, ValueError):
        return None


def _score_from_premium(premium: float) -> float:
    """Convert vol-point premium to 0–100 score."""
    if premium < 1.0:
        return 100.0
    elif premium < 2.0:
        return 80.0
    elif premium < 3.0:
        return 60.0
    elif premium < 5.0:
        return 30.0
    else:
        return 10.0


def _size_multiplier_from_premium(premium: float) -> float:
    """
    Graduated size reduction as IV distortion increases.
    Full size below threshold, progressively reduced above it.
    Floors at 0.5 — never completely block on IV alone.
    """
    if premium <= IV_DISTORTION_THRESHOLD_ABS:
        return 1.0
    reduction = (premium - IV_DISTORTION_THRESHOLD_ABS) * 0.1
    return max(0.5, round(1.0 - reduction, 2))


def run(ctx: ExecutionContext) -> StrategyResult:
    """
    Evaluate options IV distortion for the signal's target contract.

    If no options data is available (equity entry without options,
    or ETF direct), returns neutral score — does not penalise.

    Args:
        ctx: ExecutionContext populated by EIL runner

    Returns:
        StrategyResult with score, distortion flag, and size_multiplier
    """

    # ── No options data — neutral pass (equity/ETF direct entry) ─────────────
    if ctx.iv_mid is None or ctx.iv_ask is None:
        return StrategyResult(
            strategy_name   = "S2_IV_DISTORTION",
            score           = 75.0,
            passed          = True,
            verdict         = "NO_OPTIONS_DATA",
            detail          = (
                "No options IV data in ExecutionContext. "
                "Equity or ETF direct entry assumed. Neutral score."
            ),
            size_multiplier = 1.0,
            block           = False,
        )

    # ── Compute IV premium at ask vs mid ─────────────────────────────────────
    # IV values from MarketData.app are decimals (0.45 = 45%)
    # Convert to vol points (× 100) for human-readable thresholds
    iv_mid_pts  = ctx.iv_mid  * 100
    iv_ask_pts  = ctx.iv_ask  * 100
    iv_premium  = iv_ask_pts - iv_mid_pts   # vol points above mid

    # ── Determine which threshold applies ────────────────────────────────────
    oi = ctx.options_open_interest or 0
    if oi < IV_THIN_NAME_OI_THRESHOLD:
        # Thin name — use relative threshold
        threshold_met = (ctx.iv_ask / ctx.iv_mid) > IV_DISTORTION_THRESHOLD_REL
        threshold_desc = f"Relative: ask_IV/mid_IV = {ctx.iv_ask/ctx.iv_mid:.3f} vs {IV_DISTORTION_THRESHOLD_REL} limit (thin name, OI={oi})"
    else:
        # Liquid name — use absolute vol point threshold
        threshold_met = iv_premium > IV_DISTORTION_THRESHOLD_ABS
        threshold_desc = f"Absolute: premium = {iv_premium:.1f} vol pts vs {IV_DISTORTION_THRESHOLD_ABS} limit (OI={oi})"

    score        = _score_from_premium(iv_premium)
    size_mult    = _size_multiplier_from_premium(iv_premium) if threshold_met else 1.0
    passed       = not threshold_met

    # ── Build verdict ─────────────────────────────────────────────────────────
    if threshold_met:
        verdict = "DISTORTED"
        detail  = (
            f"IV distortion detected. Mid-IV={iv_mid_pts:.1f}  Ask-IV={iv_ask_pts:.1f}  "
            f"Premium={iv_premium:.1f} vol pts. "
            f"{threshold_desc}. "
            f"Breakeven hurdle elevated before directional edge applies. "
            f"Size reduced to {size_mult:.0%}."
        )
    elif iv_premium < 1.0:
        verdict = "PRISTINE"
        detail  = (
            f"Excellent spread. Mid-IV={iv_mid_pts:.1f}  Ask-IV={iv_ask_pts:.1f}  "
            f"Premium={iv_premium:.1f} vol pts. Full size permitted."
        )
    else:
        verdict = "ACCEPTABLE"
        detail  = (
            f"Acceptable spread. Mid-IV={iv_mid_pts:.1f}  Ask-IV={iv_ask_pts:.1f}  "
            f"Premium={iv_premium:.1f} vol pts. Full size permitted."
        )

    # ── Spread % for eil_spread_pct_live ─────────────────────────────────────
    # Also compute the raw spread as % of mid for the ExecutionVerdict field
    if ctx.options_mid and ctx.options_mid > 0 and ctx.options_bid and ctx.options_ask:
        spread_pct = (ctx.options_ask - ctx.options_bid) / ctx.options_mid * 100
        detail += f"  |  Options spread={spread_pct:.2f}% of mid."
    else:
        spread_pct = None

    result = StrategyResult(
        strategy_name   = "S2_IV_DISTORTION",
        score           = score,
        passed          = passed,
        verdict         = verdict,
        detail          = detail,
        size_multiplier = size_mult,
        block           = False,   # IV distortion never hard-blocks — only scales
    )

    # Attach spread_pct as extra attribute for EIL engine to pick up
    result.spread_pct_live = spread_pct
    result.iv_ask_premium  = iv_premium

    return result


# ── STANDALONE TEST ──────────────────────────────────────────────────────────
if __name__ == "__main__":
    from datetime import datetime, timezone

    test_cases = [
        ("Pristine spread",     0.42, 0.43, 0.425, 5.15, 5.25, 5.20, 61289),
        ("Acceptable spread",   0.42, 0.445, 0.432, 5.05, 5.35, 5.20, 3000),
        ("Marginal spread",     0.42, 0.465, 0.442, 4.90, 5.50, 5.20, 2000),
        ("Distorted — liquid",  0.42, 0.49,  0.455, 4.70, 5.70, 5.20, 1500),
        ("Distorted — thin",    0.42, 0.50,  0.455, 4.70, 5.70, 5.20, 200),
        ("No IV data",          None, None,  None,  None, None, None, None),
    ]

    print("\n── S2 IV Distortion — Test Runs ──\n")
    now = datetime(2026, 3, 8, 16, 0, tzinfo=timezone.utc)

    for label, iv_mid, iv_ask, iv_bid, bid, ask, mid, oi in test_cases:
        ctx = ExecutionContext(
            ticker                  = "TEST",
            signal_time             = now,
            superbrain_verdict      = "EXECUTE",
            wbs_grade               = "PROBABLE",
            wbs_score               = 58.0,
            signal_direction        = "LONG",
            current_price           = 100.0,
            check_time              = now,
            iv_mid                  = iv_mid,
            iv_ask                  = iv_ask,
            iv_bid                  = iv_bid,
            options_bid             = bid,
            options_ask             = ask,
            options_mid             = mid,
            options_open_interest   = oi,
        )
        result = run(ctx)
        print(f"  {label}")
        print(f"    Verdict : {result.verdict}")
        print(f"    Score   : {result.score}")
        print(f"    Passed  : {result.passed}")
        print(f"    Size ×  : {result.size_multiplier}")
        print(f"    Detail  : {result.detail}")
        print()
