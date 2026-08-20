"""
AVSHUNTER EIL — Strategy 1: Time-of-Day Liquidity Regime Gate
==============================================================
Sprint 1 | Priority: HIGHEST | Complexity: LOW | Data: None required

RATIONALE
---------
Bid/ask spreads follow a U-shape intraday — widest at open and close,
tightest between 10:15–15:30 ET. Options spreads during the open auction
can be 40–60% wider than the midday window. On a live Tastytrade account
trading equities, options, and ETFs, entering during the wide-spread
windows systematically erodes the actuarial edge before the trade begins.

This gate is a hard filter: if the signal arrives during CLOSED_AUCTION
or WIDE_SPREAD_WINDOW the EIL composite is capped and the verdict cannot
reach EXECUTE_NOW regardless of other strategy scores.

WINDOWS
-------
    CLOSED_AUCTION   : Before 09:30 ET / After 16:00 ET
    WIDE_SPREAD_OPEN : 09:30–10:15 ET  (first 45 min)
    OPTIMAL_WINDOW   : 10:15–15:30 ET
    WIDE_SPREAD_CLOSE: 15:30–16:00 ET  (final 30 min)

TASTYTRADE SPECIFICS
--------------------
Tastytrade routes options via PFOF-optimised internalisers. During the
open auction their fill quality degrades further than exchange-routed
orders — the effective wide-spread window is conservatively 09:30–10:30 ET
for options. The gate uses 10:15 as a compromise across all instrument types.

SCORING
-------
    OPTIMAL_WINDOW      → 100  (full pass)
    WIDE_SPREAD_OPEN    → 30   (soft fail — EXECUTE_DEFER, not block)
    WIDE_SPREAD_CLOSE   → 40   (softer fail — market makers more predictable)
    CLOSED_AUCTION      → 0    (hard block)

Version : 1.0.0
Date    : 2026-03-08
"""

from datetime import datetime, time
from zoneinfo import ZoneInfo

from execution_schema import (
    ExecutionContext, StrategyResult,
    OPTIMAL_WINDOW_START_ET, OPTIMAL_WINDOW_END_ET,
    WIDE_SPREAD_OPEN_END_ET, WIDE_SPREAD_CLOSE_START,
)

ET = ZoneInfo("America/New_York")

# Window definitions as (start_hour, start_min, end_hour, end_min)
_MARKET_OPEN  = time(9,  30)
_WIDE_END     = time(10, 15)   # end of wide open window
_OPTIMAL_END  = time(15, 30)   # end of optimal window
_MARKET_CLOSE = time(16,  0)


def _et_time(dt: datetime) -> time:
    """Convert a UTC or naive datetime to Eastern Time and return time portion."""
    if dt.tzinfo is None:
        # Assume UTC if naive — log a warning in production
        from zoneinfo import ZoneInfo as _ZI
        import datetime as _dt
        dt = dt.replace(tzinfo=_ZI("UTC"))
    return dt.astimezone(ET).time()


def run(ctx: ExecutionContext) -> StrategyResult:
    """
    Evaluate the Time-of-Day Liquidity Regime for the signal.

    Args:
        ctx: ExecutionContext populated by EIL runner

    Returns:
        StrategyResult with score, verdict, and size_multiplier
    """
    et_now = _et_time(ctx.check_time)

    # ── CLOSED AUCTION ──────────────────────────────────────────────────────
    if et_now < _MARKET_OPEN or et_now >= _MARKET_CLOSE:
        return StrategyResult(
            strategy_name   = "S1_LIQUIDITY_GATE",
            score           = 0.0,
            passed          = False,
            verdict         = "CLOSED_AUCTION",
            detail          = (
                f"Market closed at {et_now.strftime('%H:%M')} ET. "
                f"No execution permitted outside 09:30–16:00 ET."
            ),
            size_multiplier = 0.0,
            block           = True,   # Hard gate — overrides composite
        )

    # ── WIDE SPREAD — OPEN (09:30–10:15 ET) ─────────────────────────────────
    if _MARKET_OPEN <= et_now < _WIDE_END:
        elapsed_mins = (et_now.hour * 60 + et_now.minute) - (9 * 60 + 30)
        detail = (
            f"Open auction liquidity window ({elapsed_mins} min since open). "
            f"Options spreads typically 40–60% wider than midday. "
            f"Defer until 10:15 ET for optimal fill quality."
        )
        return StrategyResult(
            strategy_name   = "S1_LIQUIDITY_GATE",
            score           = 30.0,
            passed          = False,
            verdict         = "WIDE_SPREAD_OPEN",
            detail          = detail,
            size_multiplier = 0.75,   # Allow scaled entry if other signals very strong
            block           = False,
        )

    # ── OPTIMAL WINDOW (10:15–15:30 ET) ─────────────────────────────────────
    if _WIDE_END <= et_now < _OPTIMAL_END:
        mins_remaining = (15 * 60 + 30) - (et_now.hour * 60 + et_now.minute)
        return StrategyResult(
            strategy_name   = "S1_LIQUIDITY_GATE",
            score           = 100.0,
            passed          = True,
            verdict         = "OPTIMAL_WINDOW",
            detail          = (
                f"Optimal liquidity window. {mins_remaining} min remaining. "
                f"Full size permitted."
            ),
            size_multiplier = 1.0,
            block           = False,
        )

    # ── WIDE SPREAD — CLOSE (15:30–16:00 ET) ────────────────────────────────
    if _OPTIMAL_END <= et_now < _MARKET_CLOSE:
        mins_to_close = (16 * 60) - (et_now.hour * 60 + et_now.minute)
        detail = (
            f"Pre-close spread widening window ({mins_to_close} min to close). "
            f"Market makers pulling liquidity. "
            f"New positions not recommended — consider deferring to next session."
        )
        return StrategyResult(
            strategy_name   = "S1_LIQUIDITY_GATE",
            score           = 40.0,
            passed          = False,
            verdict         = "WIDE_SPREAD_CLOSE",
            detail          = detail,
            size_multiplier = 0.6,
            block           = False,
        )

    # Should never reach here — defensive fallback
    return StrategyResult(
        strategy_name   = "S1_LIQUIDITY_GATE",
        score           = 0.0,
        passed          = False,
        verdict         = "UNKNOWN",
        detail          = f"Could not classify time {et_now.strftime('%H:%M')} ET.",
        size_multiplier = 0.0,
        block           = True,
    )


# ── STANDALONE TEST ──────────────────────────────────────────────────────────
if __name__ == "__main__":
    from datetime import timezone
    import json

    test_times_utc = [
        ("Pre-open 08:00 ET",   datetime(2026, 3, 8, 13,  0, tzinfo=timezone.utc)),
        ("Open auction 09:35ET",datetime(2026, 3, 8, 14, 35, tzinfo=timezone.utc)),
        ("Optimal 11:00 ET",    datetime(2026, 3, 8, 16,  0, tzinfo=timezone.utc)),
        ("Pre-close 15:45 ET",  datetime(2026, 3, 8, 20, 45, tzinfo=timezone.utc)),
        ("Post-close 16:05 ET", datetime(2026, 3, 8, 21,  5, tzinfo=timezone.utc)),
    ]

    print("\n── S1 Liquidity Gate — Test Runs ──\n")
    for label, utc_dt in test_times_utc:
        ctx = ExecutionContext(
            ticker              = "TEST",
            signal_time         = utc_dt,
            superbrain_verdict  = "EXECUTE",
            wbs_grade           = "PROBABLE",
            wbs_score           = 58.0,
            signal_direction    = "LONG",
            current_price       = 100.0,
            check_time          = utc_dt,
        )
        result = run(ctx)
        print(f"  {label}")
        print(f"    Verdict : {result.verdict}")
        print(f"    Score   : {result.score}")
        print(f"    Block   : {result.block}")
        print(f"    Size ×  : {result.size_multiplier}")
        print(f"    Detail  : {result.detail}")
        print()
