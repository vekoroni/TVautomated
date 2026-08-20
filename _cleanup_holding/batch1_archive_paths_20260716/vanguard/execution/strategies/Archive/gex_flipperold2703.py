"""
AVSHUNTER EIL — Strategy 3: Gamma Exposure Flip Level Detection
===============================================================
Sprint 2 | Priority: HIGH | Data: MarketData.app option chain (gamma × OI)

RATIONALE
---------
Dealer gamma exposure (GEX) determines whether market makers amplify or
dampen price moves via their delta-hedging flow.

    Net SHORT gamma (GEX < 0): Dealers buy when price rises, sell when
    price falls → amplifies directional moves → good for momentum entries.

    Net LONG gamma  (GEX > 0): Dealers sell when price rises, buy when
    price falls → dampens moves → mean-reversion environment.

The GEX zero-crossing (flip level) is the price where the regime changes.
Entering WITH dealer flow (in an AMPLIFYING regime, near a flip level
that will amplify the move in your direction) produces materially better
fills and faster profit development.

AVSHUNTER already carries net_gamma_exposure in StateVector. This strategy
adds the flip level — the specific PRICE at which GEX changes sign — and
measures proximity. A signal near a flip level in the right direction is
structurally superior.

DATA DERIVATION
---------------
GEX per strike = gamma × open_interest × 100 (contract multiplier)
    Positive GEX strike: dealers net long gamma at this strike (dampening)
    Negative GEX strike: dealers net short gamma at this strike (amplifying)

GEX flip level = strike price where cumulative GEX changes sign
    (scanning from current price outward in signal direction)

DATA SOURCE: MarketData.app /v1/options/chain/{ticker}/
Fields: gamma, openInterest per strike per expiration
ctx.gex_by_strike is pre-computed by EIL runner as: {strike: gex_value}

SCORING
-------
    AMPLIFYING + price near flip level (<1%)  → 100  optimal — move will accelerate
    AMPLIFYING + price away from flip (1-5%)  → 85   good — in amplifying regime
    NEUTRAL                                   → 65   acceptable
    DAMPENING + price away from flip (>5%)    → 40   caution — headwinds
    DAMPENING + price near flip (<2%)         → 55   mixed — may flip to amplifying soon
    No GEX data                               → 65   neutral

Version : 1.0.0
Date    : 2026-03-08
"""

from typing import Dict, Optional, Tuple
from execution_schema import ExecutionContext, StrategyResult


def _compute_gex_regime(
    gex_by_strike: Dict[float, float],
    current_price: float,
    signal_direction: str,
) -> Tuple[str, Optional[float], float]:
    """
    Determine GEX regime and flip level from strike-level GEX data.

    Returns:
        (regime, flip_level_price, proximity_pct)
        regime: AMPLIFYING | DAMPENING | NEUTRAL
        flip_level_price: price where GEX changes sign (None if not found)
        proximity_pct: distance from current_price to flip_level as decimal
    """
    if not gex_by_strike or current_price <= 0:
        return "NEUTRAL", None, 1.0

    # Aggregate total GEX to determine current regime
    total_gex = sum(gex_by_strike.values())

    if abs(total_gex) < 1e6:   # Below $1M GEX — effectively neutral
        regime = "NEUTRAL"
    elif total_gex > 0:
        regime = "DAMPENING"   # Dealers net long gamma
    else:
        regime = "AMPLIFYING"  # Dealers net short gamma

    # ── Find flip level ───────────────────────────────────────────────────────
    # Sort strikes and scan in signal direction to find where cumulative GEX
    # changes sign. This is the price level where regime flips.
    sorted_strikes = sorted(gex_by_strike.keys())

    # Start from current_price, scan in direction of signal
    if signal_direction == "LONG":
        # For longs: flip level above current price (upside amplification point)
        relevant_strikes = [s for s in sorted_strikes if s >= current_price]
    else:
        # For shorts: flip level below current price (downside amplification point)
        relevant_strikes = [s for s in sorted_strikes if s <= current_price]
        relevant_strikes = list(reversed(relevant_strikes))

    flip_level = None
    cumulative = 0.0
    sign_at_current = 1.0 if total_gex >= 0 else -1.0

    for strike in relevant_strikes:
        cumulative += gex_by_strike.get(strike, 0)
        if cumulative != 0 and (cumulative * sign_at_current) < 0:
            flip_level = strike
            break

    # Proximity calculation
    if flip_level is not None:
        proximity_pct = abs(current_price - flip_level) / current_price
    else:
        proximity_pct = 1.0   # No flip found — treat as far away

    return regime, flip_level, proximity_pct


def _score_from_regime_and_proximity(
    regime: str,
    proximity_pct: float,
    signal_direction: str,
    flip_level: Optional[float],
    current_price: float,
) -> Tuple[float, float, str]:
    """
    Returns (score, size_multiplier, verdict_detail).
    """
    if regime == "AMPLIFYING":
        if proximity_pct < 0.01:
            # Very near flip level — about to enter amplifying zone
            return 100.0, 1.0, (
                f"AMPLIFYING regime + price within 1% of flip level "
                f"(${flip_level:.2f}). Dealer hedging will accelerate move."
            )
        elif proximity_pct < 0.05:
            return 85.0, 1.0, (
                f"AMPLIFYING regime. Flip level at ${flip_level:.2f} "
                f"({proximity_pct:.1%} away). Dealer flow supports direction."
            )
        else:
            return 75.0, 1.0, (
                f"AMPLIFYING regime. Flip level distant "
                f"({proximity_pct:.1%} away). Directional dealer flow present."
            )

    elif regime == "DAMPENING":
        if flip_level and proximity_pct < 0.02:
            # Near a flip — regime about to change, mixed signal
            return 55.0, 0.85, (
                f"DAMPENING regime but flip level approaching at ${flip_level:.2f} "
                f"({proximity_pct:.1%} away). May transition to amplifying soon. "
                f"Slight size reduction."
            )
        else:
            flip_str = f"${flip_level:.2f}" if flip_level else "not detected"
            return 40.0, 0.75, (
                f"DAMPENING regime. Dealers net long gamma — moves will be "
                f"dampened. Flip level at {flip_str}. "
                f"Consider waiting for regime shift. Size reduced."
            )

    else:  # NEUTRAL
        return 65.0, 1.0, (
            "GEX regime NEUTRAL — insufficient directional gamma imbalance. "
            "No material dealer hedging flow in either direction."
        )


def run(ctx: ExecutionContext) -> StrategyResult:
    """
    Evaluate Gamma Exposure regime and flip level proximity.

    Args:
        ctx: ExecutionContext with gex_by_strike populated by EIL runner

    Returns:
        StrategyResult with regime, flip level, score, and size_multiplier
    """

    # ── No GEX data — neutral ─────────────────────────────────────────────────
    if not ctx.gex_by_strike:
        return StrategyResult(
            strategy_name   = "S3_GEX_FLIP",
            score           = 65.0,
            passed          = True,
            verdict         = "NO_GEX_DATA",
            detail          = (
                "GEX by strike not available. "
                "Falling back to existing StateVector net_gamma_exposure field "
                "for directional context only (no flip level calculable)."
            ),
            size_multiplier = 1.0,
            block           = False,
        )

    # ── Compute regime and flip level ─────────────────────────────────────────
    regime, flip_level, proximity_pct = _compute_gex_regime(
        ctx.gex_by_strike, ctx.current_price, ctx.signal_direction
    )

    score, size_mult, detail = _score_from_regime_and_proximity(
        regime, proximity_pct, ctx.signal_direction, flip_level, ctx.current_price
    )

    result = StrategyResult(
        strategy_name   = "S3_GEX_FLIP",
        score           = score,
        passed          = score >= 60,
        verdict         = regime,
        detail          = detail,
        size_multiplier = size_mult,
        block           = False,
    )

    # Attach structured fields for ExecutionVerdict
    result.gex_flip_level   = flip_level
    result.gex_proximity_pct = proximity_pct
    result.gex_regime       = regime

    return result


# ── STANDALONE TEST ──────────────────────────────────────────────────────────
if __name__ == "__main__":
    from datetime import datetime, timezone

    now = datetime(2026, 3, 8, 16, 0, tzinfo=timezone.utc)

    # Simulate GEX profile: negative above current price (amplifying), flips at 105
    gex_amplifying = {
        95.0:  -500_000,
        97.5:  -800_000,
        100.0: -1_200_000,
        102.5: -600_000,
        105.0:  900_000,   # Flip point — positive GEX above here
        107.5:  1_500_000,
        110.0:  2_000_000,
    }

    # Simulate dampening (positive GEX throughout)
    gex_dampening = {k: abs(v) for k, v in gex_amplifying.items()}

    test_cases = [
        ("Amplifying — LONG at $100",   gex_amplifying, 100.0, "LONG"),
        ("Dampening — LONG at $100",    gex_dampening,  100.0, "LONG"),
        ("Near flip — LONG at $104",    gex_amplifying, 104.0, "LONG"),
        ("No GEX data",                 {},             100.0, "LONG"),
    ]

    print("\n── S3 GEX Flip — Test Runs ──\n")
    for label, gex, price, direction in test_cases:
        ctx = ExecutionContext(
            ticker              = "TEST",
            signal_time         = now,
            superbrain_verdict  = "EXECUTE",
            wbs_grade           = "PROBABLE",
            wbs_score           = 58.0,
            signal_direction    = direction,
            current_price       = price,
            check_time          = now,
            gex_by_strike       = gex,
        )
        result = run(ctx)
        print(f"  {label}")
        print(f"    Regime  : {getattr(result, 'gex_regime', 'N/A')}")
        print(f"    Flip $  : {getattr(result, 'gex_flip_level', 'N/A')}")
        print(f"    Score   : {result.score}")
        print(f"    Size ×  : {result.size_multiplier}")
        print(f"    Detail  : {result.detail}")
        print()
