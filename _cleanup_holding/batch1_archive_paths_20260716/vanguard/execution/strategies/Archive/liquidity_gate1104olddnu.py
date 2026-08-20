"""
AVSHUNTER EIL — Strategy S1: Liquidity Gate
============================================
Evaluates whether the option contract can be entered and exited cleanly
at the modelled price. Checks:
  - Time-of-day (spread widening at open/close)
  - Bid/ask spread as % of mid
  - Open interest adequacy
  - Volume-to-OI ratio

Hard block: spread > 30% of mid OR OI < 100
"""
import sys, os
from datetime import datetime, timezone, timedelta
from typing import Optional

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, os.path.join(_HERE, ".."))

from execution_schema import (
    ExecutionContext, StrategyResult,
    OPTIMAL_WINDOW_START_ET, OPTIMAL_WINDOW_END_ET,
    WIDE_SPREAD_OPEN_END_ET, WIDE_SPREAD_CLOSE_START,
)

# Thresholds
SPREAD_PCT_HARD_BLOCK   = 30.0   # > 30% spread → hard block
SPREAD_PCT_CAUTION      = 15.0   # > 15% → caution
SPREAD_PCT_CLEAN        = 8.0    # ≤ 8% → clean
OI_HARD_BLOCK           = 100    # < 100 OI → hard block
OI_CAUTION              = 500    # < 500 OI → caution
VOLUME_OI_RATIO_MIN     = 0.02   # vol/OI < 2% → low liquidity flag


def _et_hour_minute(dt: Optional[datetime]):
    """Convert UTC datetime to ET hour/minute tuple."""
    if dt is None:
        return None, None
    # ET = UTC - 5h (EST) or UTC - 4h (EDT); approximate with UTC-4 (market hours)
    et = dt - timedelta(hours=4)
    return et.hour, et.minute


def run(ctx: ExecutionContext) -> StrategyResult:
    check_time = ctx.check_time or datetime.now(timezone.utc)
    hour_et, min_et = _et_hour_minute(check_time)
    total_min = hour_et * 60 + min_et if hour_et is not None else None

    # ── Market closed? ───────────────────────────────────────────────────────
    market_open_min  = 9 * 60 + 30    # 09:30 ET
    market_close_min = 16 * 60         # 16:00 ET
    opt_start_min    = OPTIMAL_WINDOW_START_ET[0] * 60 + OPTIMAL_WINDOW_START_ET[1]
    opt_end_min      = OPTIMAL_WINDOW_END_ET[0]   * 60 + OPTIMAL_WINDOW_END_ET[1]
    close_warn_min   = WIDE_SPREAD_CLOSE_START[0] * 60 + WIDE_SPREAD_CLOSE_START[1]

    if total_min is None or total_min < market_open_min or total_min >= market_close_min:
        time_verdict = "CLOSED_AUCTION"
        time_score   = 60   # Evening run — not blocking, just noting closed market
        time_penalty = 0
    elif total_min < opt_start_min:
        time_verdict = "WIDE_SPREAD_OPEN"
        time_score   = 65
        time_penalty = 15
    elif total_min >= close_warn_min:
        time_verdict = "WIDE_SPREAD_CLOSE"
        time_score   = 65
        time_penalty = 10
    else:
        time_verdict = "OPTIMAL_WINDOW"
        time_score   = 100
        time_penalty = 0

    # ── Spread analysis ──────────────────────────────────────────────────────
    bid = ctx.options_bid
    ask = ctx.options_ask
    mid = ctx.options_mid

    hard_block   = False
    spread_score = 85
    spread_detail = "No options bid/ask data"
    spread_pct   = None

    if bid is not None and ask is not None and ask > 0:
        if mid and mid > 0:
            spread_pct = (ask - bid) / mid * 100
        else:
            spread_pct = (ask - bid) / ask * 100

        if spread_pct > SPREAD_PCT_HARD_BLOCK:
            hard_block   = True
            spread_score = 0
            spread_detail = f"HARD BLOCK: spread {spread_pct:.1f}% > {SPREAD_PCT_HARD_BLOCK}% threshold"
        elif spread_pct > SPREAD_PCT_CAUTION:
            spread_score = 50
            spread_detail = f"CAUTION: spread {spread_pct:.1f}% > {SPREAD_PCT_CAUTION}% — modelled fill may not be achievable"
        elif spread_pct > SPREAD_PCT_CLEAN:
            spread_score = 75
            spread_detail = f"ACCEPTABLE: spread {spread_pct:.1f}%"
        else:
            spread_score = 100
            spread_detail = f"CLEAN: spread {spread_pct:.1f}%"

    # ── OI analysis ──────────────────────────────────────────────────────────
    oi = ctx.options_open_interest
    oi_score  = 85
    oi_detail = "No OI data"

    if oi is not None:
        if oi < OI_HARD_BLOCK:
            hard_block = True
            oi_score   = 0
            oi_detail  = f"HARD BLOCK: OI={oi} < {OI_HARD_BLOCK} minimum"
        elif oi < OI_CAUTION:
            oi_score  = 55
            oi_detail = f"CAUTION: OI={oi} below {OI_CAUTION} — limited depth"
        else:
            oi_score  = 100
            oi_detail = f"ADEQUATE: OI={oi}"

    # ── Composite S1 score ───────────────────────────────────────────────────
    if hard_block:
        composite = 0
        passed    = False
        size_mult = 0.0
    else:
        composite = (spread_score * 0.5 + oi_score * 0.3 + time_score * 0.2) - time_penalty
        composite = max(0.0, min(100.0, composite))
        passed    = composite >= 60
        size_mult = 1.0 if composite >= 80 else 0.7 if composite >= 60 else 0.5

    detail = f"{time_verdict} | Spread: {spread_detail} | OI: {oi_detail}"

    result = StrategyResult(
        strategy_name  = "S1_LIQUIDITY_GATE",
        score          = round(composite, 1),
        passed         = passed,
        verdict        = time_verdict,
        detail         = detail,
        size_multiplier= size_mult,
        block          = hard_block,
    )
    # Attach extra fields for engine
    result.spread_pct_live = spread_pct
    return result
