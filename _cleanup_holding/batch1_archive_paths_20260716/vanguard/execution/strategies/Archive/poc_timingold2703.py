"""
AVSHUNTER EIL — Strategy 5: Volume Profile POC Migration Timing
===============================================================
Sprint 1 | Priority: MEDIUM | Complexity: LOW | Data: Existing pipeline fields

RATIONALE
---------
The Point of Control (POC) is the price level with the highest traded
volume in the current session's volume profile. It acts as a gravitational
centre — price away from POC is in an active auction seeking acceptance.

For Tastytrade live execution, the fill quality insight is:
    BEST fills  : Price proximate to POC (within 0.5%) with directional bias.
                  Volume profile acts as a launch pad.
    WORST fills : Chasing price 2%+ extended from POC into thin volume nodes.
                  High risk of POC snapback before the trade develops.
                  On options this snapback erodes both delta and time value.

This strategy builds ENTIRELY on existing AVSHUNTER pipeline fields:
    - price_vs_poc  (StateVector — % from Point of Control)
    - current_price (ExecutionContext — live last trade)
    - poc_price     (ExecutionContext — from intraday volume profile)

No new data sources required.

SCORING
-------
    AT_POC    (±0.5%)   → 100  full score — optimal launch zone
    ABOVE_POC (0.5–2%)  → 80   good — price accepted above value area
    BELOW_POC (0.5–2%)  → 70   acceptable — testing value from below
    EXTENDED  (>2%)     → 30   caution — chasing, high reversion risk
    UNKNOWN             → 50   neutral — poc_price not available, no penalty

SIZE MULTIPLIER
---------------
    AT_POC / ABOVE_POC  → 1.0  (full size)
    BELOW_POC           → 0.85 (slight reduction — less structural support)
    EXTENDED            → 0.65 (meaningful reduction — reversion risk)

ADVISORY NOTE
-------------
Strategy 5 is the lowest-weight strategy (10%) and is NEVER a hard block.
It functions as an advisory layer that modifies size — it cannot alone
trigger STAND_DOWN_MICROSTRUCTURE.

Version : 1.0.0
Date    : 2026-03-08
"""

from execution_schema import (
    ExecutionContext, StrategyResult,
    POC_AT_THRESHOLD, POC_EXTENDED_THRESHOLD,
)


def _classify_poc_position(proximity_pct: float, signal_direction: str) -> tuple[str, float, float]:
    """
    Classify price position relative to POC and return
    (position_label, score, size_multiplier).

    proximity_pct: abs(current_price - poc_price) / poc_price
    signal_direction: LONG | SHORT
    """
    abs_prox = abs(proximity_pct)

    if abs_prox <= POC_AT_THRESHOLD:
        return "AT_POC", 100.0, 1.0

    if abs_prox <= POC_EXTENDED_THRESHOLD:
        if proximity_pct > 0:
            # Price above POC
            label = "ABOVE_POC"
            # For LONG: entering above POC is fine, value supports price
            # For SHORT: entering above POC is ideal — shorting into resistance
            score = 80.0
            size  = 1.0
        else:
            # Price below POC
            label = "BELOW_POC"
            # For LONG: below POC means buying below value — needs volume confirmation
            # For SHORT: below POC is less ideal — value area may pull price back up
            score = 70.0 if signal_direction == "SHORT" else 75.0
            size  = 0.85
        return label, score, size

    # Extended — beyond 2% from POC
    return "EXTENDED", 30.0, 0.65


def run(ctx: ExecutionContext) -> StrategyResult:
    """
    Evaluate Volume Profile POC proximity for execution timing.

    Attempts to use poc_price from ExecutionContext first (live intraday),
    then falls back to price_vs_poc_existing from StateVector if poc_price
    is not populated.

    Args:
        ctx: ExecutionContext populated by EIL runner

    Returns:
        StrategyResult with score, verdict, and size_multiplier
    """

    # ── ATTEMPT 1: Live poc_price from ExecutionContext ──────────────────────
    if ctx.poc_price is not None and ctx.poc_price > 0 and ctx.current_price > 0:
        proximity_pct = (ctx.current_price - ctx.poc_price) / ctx.poc_price
        poc_position, score, size_mult = _classify_poc_position(
            proximity_pct, ctx.signal_direction
        )

        detail_parts = [
            f"Current: ${ctx.current_price:.2f}  POC: ${ctx.poc_price:.2f}",
            f"Proximity: {proximity_pct:+.2%}",
            f"Position: {poc_position}",
        ]

        if poc_position == "EXTENDED":
            detail_parts.append(
                "Price extended from POC — elevated reversion risk. "
                "Size reduced to protect against POC snapback on options delta."
            )
        elif poc_position == "AT_POC":
            detail_parts.append(
                "At Point of Control — volume profile provides structural support. "
                "Optimal entry zone."
            )

        return StrategyResult(
            strategy_name   = "S5_POC_TIMING",
            score           = score,
            passed          = score >= 65,
            verdict         = poc_position,
            detail          = "  |  ".join(detail_parts),
            size_multiplier = size_mult,
            block           = False,   # S5 never blocks — advisory only
        )

    # ── ATTEMPT 2: Fallback to existing StateVector price_vs_poc field ───────
    if ctx.price_vs_poc_existing is not None:
        proximity_pct = ctx.price_vs_poc_existing / 100.0  # Convert % to decimal
        poc_position, score, size_mult = _classify_poc_position(
            proximity_pct, ctx.signal_direction
        )
        return StrategyResult(
            strategy_name   = "S5_POC_TIMING",
            score           = score,
            passed          = score >= 65,
            verdict         = poc_position,
            detail          = (
                f"Using StateVector price_vs_poc={ctx.price_vs_poc_existing:.2f}% "
                f"(live poc_price not available). Position: {poc_position}."
            ),
            size_multiplier = size_mult,
            block           = False,
        )

    # ── FALLBACK: POC data not available — neutral score, no penalty ─────────
    return StrategyResult(
        strategy_name   = "S5_POC_TIMING",
        score           = 50.0,
        passed          = True,   # Neutral — don't penalise for missing data
        verdict         = "UNKNOWN",
        detail          = (
            "POC data not available in ExecutionContext or StateVector. "
            "Neutral score applied — no size adjustment."
        ),
        size_multiplier = 1.0,
        block           = False,
    )


# ── STANDALONE TEST ──────────────────────────────────────────────────────────
if __name__ == "__main__":
    from datetime import datetime, timezone

    test_cases = [
        ("At POC — LONG",         100.00, 100.25, "LONG"),
        ("Above POC — LONG",      100.00, 101.20, "LONG"),
        ("Below POC — LONG",      100.00,  99.10, "LONG"),
        ("Extended above — SHORT", 100.00, 103.00, "SHORT"),
        ("Extended below — LONG",  100.00,  97.50, "LONG"),
        ("No POC data",           100.00,   None,  "LONG"),
    ]

    print("\n── S5 POC Timing — Test Runs ──\n")
    now = datetime(2026, 3, 8, 16, 0, tzinfo=timezone.utc)

    for label, poc, price, direction in test_cases:
        ctx = ExecutionContext(
            ticker              = "TEST",
            signal_time         = now,
            superbrain_verdict  = "EXECUTE",
            wbs_grade           = "PROBABLE",
            wbs_score           = 58.0,
            signal_direction    = direction,
            current_price       = price if price else 100.0,
            check_time          = now,
            poc_price           = poc if price else None,
        )
        result = run(ctx)
        print(f"  {label}")
        print(f"    Verdict : {result.verdict}")
        print(f"    Score   : {result.score}")
        print(f"    Size ×  : {result.size_multiplier}")
        print(f"    Passed  : {result.passed}")
        print(f"    Detail  : {result.detail}")
        print()
