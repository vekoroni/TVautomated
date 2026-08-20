"""
AVSHUNTER EIL — Strategy S1: Liquidity Gate  [v2.0 — EV-aware]
===============================================================
Evaluates whether the option contract can be entered and exited cleanly.

v2.0 changes
------------
- EV-aware spread gate: execution_edge = expected_move / spread_pct
  A 12% spread on a 40% expected move is tradeable; a 12% spread on
  a 5% expected move is not. Static thresholds alone cannot distinguish.
- Ticker-aware hard block: large-cap liquid names (SPY, NVDA, AAPL etc.)
  use tighter clean threshold (5%); small/mid-cap use 10%.
- Size multiplier derived from execution_edge ratio, not fixed buckets.
- Hard block conditions retained: spread > 20% OR OI < 100 (unchanged).
- Time-of-day windows unchanged.

Original hard blocks (kept)
---------------------------
  Spread > 20% of mid  → always block regardless of expected move
  OI < 100             → always block (no exit liquidity)
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

# ── Thresholds ────────────────────────────────────────────────────────────────
SPREAD_PCT_HARD_BLOCK     = 0.20    # > 20% → always block
OI_HARD_BLOCK             = 100     # < 100 OI → always block

# EV-aware execution edge thresholds
EXEC_EDGE_BLOCK           = 1.0     # expected_move / spread < 1x → block (paying more than you get)
EXEC_EDGE_SIZE_DOWN       = 2.5     # < 2.5x → go small
EXEC_EDGE_FULL            = 4.0     # >= 4x  → full size

# Fallback static spread thresholds (used when expected_move unavailable)
SPREAD_PCT_CAUTION_STATIC = 0.12
SPREAD_PCT_CLEAN_STATIC   = 0.06

OI_CAUTION                = 500

# Large-cap / high-liquidity tickers — tighter static clean threshold
LIQUID_NAMES = {
    'SPY','QQQ','AAPL','MSFT','GOOGL','AMZN','TSLA','NVDA',
    'META','NFLX','AMD','INTC','XLP','GLD','SLV','TLT',
}


def _et_hour_minute(dt: Optional[datetime]):
    if dt is None:
        return None, None
    et = dt - timedelta(hours=4)
    return et.hour, et.minute


def run(ctx: ExecutionContext) -> StrategyResult:
    check_time = ctx.check_time or datetime.now(timezone.utc)
    hour_et, min_et = _et_hour_minute(check_time)
    total_min = hour_et * 60 + min_et if hour_et is not None else None

    # ── Time-of-day ──────────────────────────────────────────────────────────
    market_open_min  = 9 * 60 + 30
    market_close_min = 16 * 60
    opt_start_min    = OPTIMAL_WINDOW_START_ET[0] * 60 + OPTIMAL_WINDOW_START_ET[1]
    opt_end_min      = OPTIMAL_WINDOW_END_ET[0]   * 60 + OPTIMAL_WINDOW_END_ET[1]
    close_warn_min   = WIDE_SPREAD_CLOSE_START[0] * 60 + WIDE_SPREAD_CLOSE_START[1]

    if total_min is None or total_min < market_open_min or total_min >= market_close_min:
        time_verdict = "CLOSED_AUCTION"
        time_score   = 60
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

    # ── Spread analysis (EV-aware) ────────────────────────────────────────────
    bid     = ctx.options_bid
    ask     = ctx.options_ask
    mid     = ctx.options_mid
    ticker  = (ctx.ticker or "").upper()

    hard_block   = False
    spread_score = 85
    spread_detail = "No options bid/ask data"
    spread_pct   = None
    size_mult_spread = 1.0

    if bid is not None and ask is not None and ask > 0:
        spread_pct = (ask - bid) / mid * 100 if mid and mid > 0 else (ask - bid) / ask * 100

        # Hard block — always fires regardless of expected move
        if spread_pct > SPREAD_PCT_HARD_BLOCK * 100:
            hard_block       = True
            spread_score     = 0
            size_mult_spread = 0.0
            spread_detail    = f"HARD BLOCK: spread {spread_pct:.1f}% > {SPREAD_PCT_HARD_BLOCK*100:.0f}% absolute limit"
        else:
            # EV-aware gate: compute execution_edge = expected_move / spread_pct
            # expected_move is expressed as decimal (e.g. 0.08 = 8%)
            # spread_pct here is 0-100 scale, so normalise to decimal for comparison
            spread_dec = spread_pct / 100.0

            # Try to get expected move from context (set by orchestrator adapter)
            expected_move = getattr(ctx, 'expected_move_pct', None)

            if expected_move and expected_move > 0 and spread_dec > 0:
                exec_edge = expected_move / spread_dec
                if exec_edge < EXEC_EDGE_BLOCK:
                    hard_block       = True
                    spread_score     = 0
                    size_mult_spread = 0.0
                    spread_detail    = (
                        f"EV BLOCK: execution_edge={exec_edge:.1f}x "
                        f"(move {expected_move*100:.1f}% / spread {spread_pct:.1f}%) "
                        f"< {EXEC_EDGE_BLOCK}x minimum — spread destroys edge"
                    )
                elif exec_edge < EXEC_EDGE_SIZE_DOWN:
                    spread_score     = 55
                    size_mult_spread = 0.70
                    spread_detail    = (
                        f"CAUTION: execution_edge={exec_edge:.1f}x "
                        f"(move {expected_move*100:.1f}% / spread {spread_pct:.1f}%) "
                        f"— thin edge, size down"
                    )
                elif exec_edge < EXEC_EDGE_FULL:
                    spread_score     = 78
                    size_mult_spread = 0.90
                    spread_detail    = (
                        f"ACCEPTABLE: execution_edge={exec_edge:.1f}x "
                        f"(spread {spread_pct:.1f}%)"
                    )
                else:
                    spread_score     = 100
                    size_mult_spread = 1.0
                    spread_detail    = (
                        f"CLEAN: execution_edge={exec_edge:.1f}x "
                        f"(spread {spread_pct:.1f}%) — ample edge vs spread cost"
                    )
            else:
                # Fallback: static thresholds when expected_move unavailable
                clean_threshold = SPREAD_PCT_CLEAN_STATIC * 100
                caution_threshold = SPREAD_PCT_CAUTION_STATIC * 100
                if ticker in LIQUID_NAMES:
                    clean_threshold   = 5.0   # tighter for liquid names
                    caution_threshold = 10.0
                if spread_pct > caution_threshold:
                    spread_score     = 50
                    size_mult_spread = 0.75
                    spread_detail    = f"CAUTION: spread {spread_pct:.1f}% (no expected_move for EV calc)"
                elif spread_pct > clean_threshold:
                    spread_score     = 78
                    size_mult_spread = 0.90
                    spread_detail    = f"ACCEPTABLE: spread {spread_pct:.1f}%"
                else:
                    spread_score     = 100
                    size_mult_spread = 1.0
                    spread_detail    = f"CLEAN: spread {spread_pct:.1f}%"

    # ── OI analysis ──────────────────────────────────────────────────────────
    oi       = ctx.options_open_interest
    oi_score = 85
    oi_detail = "No OI data"

    if oi is not None:
        if oi < OI_HARD_BLOCK:
            hard_block = True
            oi_score   = 0
            oi_detail  = f"HARD BLOCK: OI={oi} < {OI_HARD_BLOCK} minimum — no exit liquidity"
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
        size_mult = size_mult_spread if composite >= 60 else 0.5

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
    result.spread_pct_live = spread_pct
    return result
