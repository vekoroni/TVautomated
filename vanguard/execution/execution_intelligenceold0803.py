"""
AVSHUNTER — Execution Intelligence Layer (EIL) Composite Engine
================================================================
Version : 1.0.0
Date    : 2026-03-08
Broker  : Tastytrade (live — real capital)

PIPELINE POSITION
-----------------
Phase 9 — runs after Wall Break Scorer (Phase 8e), before Archive (Phase 10).
Operates on actionable signals only (EXECUTE | EXECUTE_WITH_RISK verdicts).
Zero breaking changes to Phases 1–8.

COMPOSITE SCORING
-----------------
Weighted average of five strategy scores (weights sum to 1.0):
    S1 Liquidity Gate      0.30
    S2 IV Distortion       0.20
    S3 GEX Flip            0.20
    S4 OBI                 0.20
    S5 POC Timing          0.10

VERDICT THRESHOLDS
------------------
    85–100 → EXECUTE_NOW
    65–84  → EXECUTE_WITH_CAUTION
    40–64  → EXECUTE_DEFER
    <40    → STAND_DOWN_MICROSTRUCTURE
    S1 hard block → STAND_DOWN_MICROSTRUCTURE (overrides composite)

SIZE MULTIPLIER
---------------
Final size multiplier = minimum of all strategy multipliers.
This is deliberately conservative — if ANY strategy flags a size
reduction, the smallest multiplier wins. The operator can review
and override manually but the system defaults to protection.

ADVISORY MODE
-------------
When eil_advisory_only=True (default), the EIL verdict is logged
and appended to the CSV but does NOT gate or modify any execution.
Set to False only after explicit operator sign-off on calibration.

LIVE CAPITAL WARNING
--------------------
This engine runs against live Tastytrade positions. All logic
changes must be reviewed in isolation before deploying to the
orchestrator. The advisory flag is your safety net.
"""

import sys
import os
from datetime import datetime, timezone
from typing import Optional

# ── Path setup for standalone execution ─────────────────────────────────────
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
_STRAT = os.path.join(_HERE, "strategies")
if _STRAT not in sys.path:
    sys.path.insert(0, _STRAT)

from execution_schema import (
    ExecutionContext, ExecutionVerdict, StrategyResult,
    WEIGHT_LIQUIDITY, WEIGHT_IV, WEIGHT_GEX, WEIGHT_OBI, WEIGHT_POC,
    SCORE_EXECUTE_NOW, SCORE_EXECUTE_CAUTION, SCORE_EXECUTE_DEFER,
)

import liquidity_gate
import iv_distortion
import gex_flipper
import obi_predictor
import poc_timing


# ─────────────────────────────────────────────────────────────────────────────
def _composite_verdict(score: float, hard_block: bool) -> str:
    if hard_block:
        return "STAND_DOWN_MICROSTRUCTURE"
    if score >= SCORE_EXECUTE_NOW:
        return "EXECUTE_NOW"
    if score >= SCORE_EXECUTE_CAUTION:
        return "EXECUTE_WITH_CAUTION"
    if score >= SCORE_EXECUTE_DEFER:
        return "EXECUTE_DEFER"
    return "STAND_DOWN_MICROSTRUCTURE"


def _final_size_multiplier(*results: StrategyResult) -> float:
    """
    Conservative minimum — any strategy flagging a reduction wins.
    """
    return min(r.size_multiplier for r in results)


def _defer_reason(*results: StrategyResult) -> Optional[str]:
    """
    Collect reasons from all strategies that failed.
    """
    reasons = []
    for r in results:
        if not r.passed or r.block:
            reasons.append(f"[{r.strategy_name}] {r.verdict}: {r.detail[:80]}...")
    return "  ||  ".join(reasons) if reasons else None


def _entry_window_advice(s1: StrategyResult, s4: StrategyResult) -> Optional[str]:
    """
    Build a human-readable entry window recommendation from S1 + S4.
    """
    parts = []
    if s1.verdict == "WIDE_SPREAD_OPEN":
        parts.append("Wait until 10:15 ET for optimal liquidity")
    elif s1.verdict == "WIDE_SPREAD_CLOSE":
        parts.append("Defer to next session — pre-close spread widening")
    elif s1.verdict == "CLOSED_AUCTION":
        parts.append("Market closed — queue for next session open")

    obi_regime = getattr(s4, "obi_regime", None)
    if obi_regime == "BEARISH":
        parts.append(f"Wait for OBI > {0.65} confirmation before entry")

    return "  |  ".join(parts) if parts else None


# ─────────────────────────────────────────────────────────────────────────────
def evaluate(ctx: ExecutionContext) -> ExecutionVerdict:
    """
    Run all five EIL strategies and produce a composite ExecutionVerdict.

    Args:
        ctx: ExecutionContext fully populated by the EIL runner

    Returns:
        ExecutionVerdict — appended to superbrain_enriched CSV as 15 new columns
    """

    # ── Run all five strategies ───────────────────────────────────────────────
    s1 = liquidity_gate.run(ctx)
    s2 = iv_distortion.run(ctx)
    s3 = gex_flipper.run(ctx)
    s4 = obi_predictor.run(ctx)
    s5 = poc_timing.run(ctx)

    # ── Hard gate check ───────────────────────────────────────────────────────
    hard_block = any(r.block for r in [s1, s2, s3, s4, s5])

    # ── Composite score ───────────────────────────────────────────────────────
    composite = (
        s1.score * WEIGHT_LIQUIDITY +
        s2.score * WEIGHT_IV        +
        s3.score * WEIGHT_GEX       +
        s4.score * WEIGHT_OBI       +
        s5.score * WEIGHT_POC
    )

    # ── Final verdict ─────────────────────────────────────────────────────────
    raw_verdict = _composite_verdict(composite, hard_block)
    final_verdict = "ADVISORY_ONLY" if ctx.eil_advisory_only else raw_verdict

    # ── Size multiplier ───────────────────────────────────────────────────────
    size_mult = _final_size_multiplier(s1, s2, s3, s4, s5)
    if ctx.eil_advisory_only:
        size_mult = 1.0   # Advisory mode never overrides size

    # ── Ancillary fields ──────────────────────────────────────────────────────
    spread_pct_live = getattr(s2, "spread_pct_live", None)
    iv_ask_premium  = getattr(s2, "iv_ask_premium", 0.0)
    gex_flip_level  = getattr(s3, "gex_flip_level", None)
    gex_proximity   = getattr(s3, "gex_proximity_pct", 1.0)
    gex_regime      = getattr(s3, "gex_regime", "NEUTRAL")
    obi_raw         = getattr(s4, "obi_raw", 0.5)

    return ExecutionVerdict(
        # ── Composite ───────────────────────────────────────────────────────
        eil_verdict             = final_verdict,
        eil_composite_score     = round(composite, 2),
        eil_advisory_only       = ctx.eil_advisory_only,

        # ── S1 Liquidity ────────────────────────────────────────────────────
        eil_liquidity_window    = s1.verdict,
        eil_liquidity_score     = s1.score,
        eil_liquidity_passed    = s1.passed,

        # ── S2 IV Distortion ─────────────────────────────────────────────────
        eil_iv_ask_premium      = round(iv_ask_premium, 2),
        eil_iv_distortion_flag  = not s2.passed,
        eil_iv_score            = s2.score,
        eil_iv_passed           = s2.passed,

        # ── S3 GEX ──────────────────────────────────────────────────────────
        eil_gex_regime          = gex_regime,
        eil_gex_flip_level      = gex_flip_level,
        eil_gex_proximity_pct   = round(gex_proximity * 100, 2),
        eil_gex_score           = s3.score,
        eil_gex_passed          = s3.passed,

        # ── S4 OBI ──────────────────────────────────────────────────────────
        eil_obi_score_raw       = round(obi_raw, 3) if obi_raw else 0.5,
        eil_obi_regime          = getattr(s4, "obi_regime", "NEUTRAL"),
        eil_obi_score           = s4.score,
        eil_obi_passed          = s4.passed,

        # ── S5 POC ──────────────────────────────────────────────────────────
        eil_poc_proximity_pct   = round(
            abs(ctx.poc_price - ctx.current_price) / ctx.current_price * 100, 2
        ) if ctx.poc_price and ctx.current_price else 0.0,
        eil_poc_position        = s5.verdict,
        eil_poc_score           = s5.score,
        eil_poc_passed          = s5.passed,

        # ── Execution guidance ───────────────────────────────────────────────
        eil_size_multiplier             = round(size_mult, 2),
        eil_defer_reason                = _defer_reason(s1, s2, s3, s4, s5),
        eil_recommended_entry_window    = _entry_window_advice(s1, s4),
        eil_spread_pct_live             = round(spread_pct_live, 2) if spread_pct_live else None,

        # ── Audit ────────────────────────────────────────────────────────────
        eil_check_timestamp     = datetime.now(timezone.utc).isoformat(),
        eil_schema_version      = "1.0.0",
    )


# ── STANDALONE SMOKE TEST ────────────────────────────────────────────────────
if __name__ == "__main__":
    from datetime import timezone

    print("\n══════════════════════════════════════════════")
    print("  AVSHUNTER EIL — Composite Engine Smoke Test")
    print("══════════════════════════════════════════════\n")

    # Simulate an optimal signal arriving at 11:30 ET
    optimal_ctx = ExecutionContext(
        ticker              = "NVDA",
        signal_time         = datetime(2026, 3, 9, 15, 30, tzinfo=timezone.utc),  # 11:30 ET
        superbrain_verdict  = "EXECUTE",
        wbs_grade           = "PROBABLE",
        wbs_score           = 58.5,
        signal_direction    = "LONG",
        current_price       = 875.50,
        check_time          = datetime(2026, 3, 9, 15, 30, tzinfo=timezone.utc),
        iv_mid              = 0.45,
        iv_ask              = 0.462,
        iv_bid              = 0.438,
        options_bid         = 8.40,
        options_ask         = 8.80,
        options_mid         = 8.60,
        options_open_interest = 4500,
        l2_bid_size         = 7200,
        l2_ask_size         = 2800,
        poc_price           = 872.00,
        gex_by_strike       = {
            850.0: -2_000_000, 860.0: -1_500_000, 870.0: -800_000,
            880.0:  500_000,   890.0:  1_200_000,  900.0: 2_000_000,
        },
        eil_advisory_only   = True,
    )

    verdict = evaluate(optimal_ctx)

    print(f"  Ticker          : {optimal_ctx.ticker}")
    print(f"  Direction       : {optimal_ctx.signal_direction}")
    print(f"  WBS Score       : {optimal_ctx.wbs_score}")
    print()
    print(f"  EIL Verdict     : {verdict.eil_verdict}")
    print(f"  Composite Score : {verdict.eil_composite_score}")
    print(f"  Advisory Only   : {verdict.eil_advisory_only}")
    print(f"  Size Multiplier : {verdict.eil_size_multiplier}")
    print()
    print(f"  S1 Liquidity    : {verdict.eil_liquidity_window} ({verdict.eil_liquidity_score})")
    print(f"  S2 IV Premium   : {verdict.eil_iv_ask_premium} vol pts  Distorted={verdict.eil_iv_distortion_flag}")
    print(f"  S3 GEX Regime   : {verdict.eil_gex_regime}  Flip=${verdict.eil_gex_flip_level}")
    print(f"  S4 OBI Regime   : {verdict.eil_obi_regime} (raw={verdict.eil_obi_score_raw})")
    print(f"  S5 POC Position : {verdict.eil_poc_position} ({verdict.eil_poc_proximity_pct:.2f}% from POC)")
    print()
    if verdict.eil_defer_reason:
        print(f"  Defer Reason    : {verdict.eil_defer_reason}")
    if verdict.eil_recommended_entry_window:
        print(f"  Entry Window    : {verdict.eil_recommended_entry_window}")
    print(f"  Timestamp       : {verdict.eil_check_timestamp}")
    print()
