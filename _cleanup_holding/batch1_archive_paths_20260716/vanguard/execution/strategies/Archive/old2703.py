"""
AVSHUNTER EIL — Strategy 4: Order Book Imbalance (OBI) Fill Predictor
======================================================================
Sprint 3 | Priority: MEDIUM | Data: Polygon.io NBBO (single-level)

RATIONALE
---------
Order book imbalance at the NBBO measures the ratio of bid-side size to
total size at the best quote. When bid_size dominates, buyers are queueing
aggressively — short-term price pressure is upward. When ask_size dominates,
sellers are queueing — downward pressure.

For AVSHUNTER on Tastytrade live:
    - Entering a LONG when OBI is bullish means filling into natural buying
      pressure — the order book will support the fill.
    - Entering a LONG when OBI is bearish means filling against the tape —
      higher slippage, more adverse fills.

DATA LIMITATION (documented)
-----------------------------
Polygon.io does NOT provide Level 2 (multi-level) order book.
This implementation uses NBBO top-of-book only (single level):
    OBI = bid_size / (bid_size + ask_size)

Single-level OBI is less predictive than 5-level L2 OBI but still
adds directional signal. Academic literature suggests single-level OBI
explains ~40% of the predictive power of full L2 OBI.

UPGRADE PATH: When AVSHUNTER moves to Interactive Brokers integration
(future sprint), TWS API provides full 10-level L2 depth at no extra
cost. This module is designed to accept multi-level data when available.

POLYGON ENDPOINT
----------------
    REST (snapshot):  GET https://api.polygon.io/v2/last/nbbo/{ticker}
    WebSocket:        wss://socket.polygon.io/stocks  (channel: Q.*)
    Fields:           bid_price, bid_size, ask_price, ask_size

NOTE: Post Nov-2025, Polygon reports bid_size/ask_size in SHARES
(not round lots). This module assumes shares. No conversion needed.

SCORING
-------
For LONG signals:
    OBI > 0.70  → 100  strong bullish pressure
    OBI 0.65–0.70 → 85  bullish
    OBI 0.50–0.65 → 65  neutral
    OBI 0.35–0.50 → 40  mild bearish — slight fill headwind
    OBI < 0.35   → 20   strong bearish — defer or scale

For SHORT signals: thresholds invert (low OBI = favourable).

VERSION: 1.0.0 — single-level NBBO implementation
UPGRADE: v2.0.0 will add multi-level L2 when IB integration available

Date    : 2026-03-08
"""

from typing import Optional
from execution_schema import (
    ExecutionContext, StrategyResult,
    OBI_BULLISH_THRESHOLD, OBI_BEARISH_THRESHOLD,
)


def _compute_obi(bid_size: Optional[float], ask_size: Optional[float]) -> Optional[float]:
    """
    Compute Order Book Imbalance ratio.
    Returns float 0.0–1.0 or None if data unavailable.
    """
    if bid_size is None or ask_size is None:
        return None
    total = bid_size + ask_size
    if total <= 0:
        return None
    return bid_size / total


def _score_and_verdict(obi: float, direction: str) -> tuple[float, float, str, str]:
    """
    Returns (score, size_multiplier, obi_regime, detail) based on OBI and direction.
    """
    # For LONG: high OBI (bid heavy) is favourable
    # For SHORT: low OBI (ask heavy) is favourable — we invert
    if direction == "SHORT":
        obi = 1.0 - obi   # Flip perspective for shorts

    if obi > 0.70:
        return 100.0, 1.0, "BULLISH", (
            f"Strong directional pressure (OBI={obi:.2f}). "
            f"Order book heavily weighted toward entry direction. "
            f"Fill quality expected to be excellent."
        )
    elif obi > OBI_BULLISH_THRESHOLD:  # 0.65–0.70
        return 85.0, 1.0, "BULLISH", (
            f"Bullish order book (OBI={obi:.2f}). "
            f"Bid-side dominance supports entry direction."
        )
    elif obi > 0.50:   # 0.50–0.65 neutral-bullish
        return 65.0, 1.0, "NEUTRAL", (
            f"Neutral order book (OBI={obi:.2f}). "
            f"No strong directional pressure — fill quality should be normal."
        )
    elif obi > OBI_BEARISH_THRESHOLD:  # 0.35–0.50 neutral-bearish
        return 40.0, 0.85, "BEARISH", (
            f"Mild contra-directional pressure (OBI={obi:.2f}). "
            f"Ask-side weighted against entry direction. "
            f"Slight size reduction recommended."
        )
    else:   # < 0.35 strongly bearish
        return 20.0, 0.70, "BEARISH", (
            f"Strong contra-directional pressure (OBI={obi:.2f}). "
            f"Order book opposing entry direction. "
            f"Consider deferring until OBI > {OBI_BULLISH_THRESHOLD}."
        )


def run(ctx: ExecutionContext) -> StrategyResult:
    """
    Evaluate Order Book Imbalance from Polygon NBBO data.

    Args:
        ctx: ExecutionContext with l2_bid_size and l2_ask_size populated
             by EIL runner from Polygon /v2/last/nbbo/{ticker}

    Returns:
        StrategyResult with OBI score and fill quality assessment
    """

    # ── Compute OBI ───────────────────────────────────────────────────────────
    obi = _compute_obi(ctx.l2_bid_size, ctx.l2_ask_size)

    # ── No NBBO data — neutral, no penalty ───────────────────────────────────
    if obi is None:
        return StrategyResult(
            strategy_name   = "S4_OBI",
            score           = 60.0,
            passed          = True,
            verdict         = "NO_NBBO_DATA",
            detail          = (
                "Polygon NBBO data not available in ExecutionContext. "
                "Neutral score. Upgrade path: Polygon NBBO REST endpoint "
                "GET /v2/last/nbbo/{ticker} with existing API key."
            ),
            size_multiplier = 1.0,
            block           = False,
        )

    # ── Score based on direction ──────────────────────────────────────────────
    score, size_mult, obi_regime, detail = _score_and_verdict(obi, ctx.signal_direction)

    # ── Compute live spread % from NBBO for eil_spread_pct_live ──────────────
    spread_pct_live = None

    result = StrategyResult(
        strategy_name   = "S4_OBI",
        score           = score,
        passed          = score >= 60,
        verdict         = obi_regime,
        detail          = detail,
        size_multiplier = size_mult,
        block           = False,
    )

    # Attach structured fields for ExecutionVerdict
    result.obi_raw   = obi
    result.obi_regime = obi_regime

    return result


# ── STANDALONE TEST ──────────────────────────────────────────────────────────
if __name__ == "__main__":
    from datetime import datetime, timezone

    now = datetime(2026, 3, 8, 16, 0, tzinfo=timezone.utc)

    test_cases = [
        ("Strong bullish OBI — LONG",    8500,  1500, "LONG"),
        ("Bullish OBI — LONG",           7000,  3000, "LONG"),
        ("Neutral OBI — LONG",           5500,  4500, "LONG"),
        ("Bearish OBI — LONG",           3000,  7000, "LONG"),
        ("Strong bearish OBI — SHORT",   8500,  1500, "SHORT"),  # OBI 0.85 inverts for SHORT
        ("No data",                      None,  None, "LONG"),
    ]

    print("\n── S4 OBI Predictor — Test Runs ──\n")
    for label, bid_sz, ask_sz, direction in test_cases:
        ctx = ExecutionContext(
            ticker              = "TEST",
            signal_time         = now,
            superbrain_verdict  = "EXECUTE",
            wbs_grade           = "PROBABLE",
            wbs_score           = 58.0,
            signal_direction    = direction,
            current_price       = 100.0,
            check_time          = now,
            l2_bid_size         = bid_sz,
            l2_ask_size         = ask_sz,
        )
        result = run(ctx)
        obi_val = _compute_obi(bid_sz, ask_sz)
        print(f"  {label}")
        print(f"    OBI raw : {obi_val:.3f}" if obi_val else "    OBI raw : None")
        print(f"    Regime  : {result.verdict}")
        print(f"    Score   : {result.score}")
        print(f"    Size ×  : {result.size_multiplier}")
        print(f"    Detail  : {result.detail}")
        print()
