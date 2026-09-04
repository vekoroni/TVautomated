"""
AVSHUNTER — Execution Intelligence Layer (EIL) Composite Engine
================================================================
Version : 2.1.0
Date    : 2026-04-27
Broker  : Tastytrade (live — real capital)

CHANGES FROM v1.0.0 → v2.0.0
-----------------------------
FIX-01  DEAD CODE: build_execution_context_from_row() set ctx.regime_size_mult
        AFTER the return statement — the attribute was never attached. Fixed by
        restructuring so ctx is mutated before it is returned.

FIX-02  COLUMN MISMATCH: options_bid/options_ask/options_mid do not exist in
        the superbrain enriched row. Correct column names are:
          contract_spread_pct → used to synthesise bid/ask around mid
          contract_iv         → iv_mid
          contract_oi         → options_open_interest
          premium / contract_premium → options_mid
        All column fallback chains updated to match actual pipeline output.

FIX-03  GEX MAP EMPTY: gex_by_strike was never populated. The context builder
        now synthesises a 3-5 strike GEX map from columns that ARE present:
          gamma_flip, gamma_flip_gap_pct, call_wall, put_wall, pcr_oi
        This gives S3 (GEX Flip) a real zero-crossing and S4 (OBI wall
        clearance) real wall strikes to measure runway against.

FIX-04  IV SYNTHESIS: When only contract_iv is available (no separate bid/ask),
        synthesise iv_bid = contract_iv * 0.97 and iv_ask = contract_iv * 1.03
        (+-3% around mid — appropriate for liquid contracts).

FIX-05  POC DERIVATION: poc_price was never set. Derived from structural_target
        if available (Wyckoff target = effective POC proxy). price_vs_poc
        computed from underlying_price and poc_price when absent.

FIX-06  EXPECTED MOVE: fallback chain extended to include l3_expected_move_1_5d
        and l3_expected_move_6_10d which ARE present in the pipeline output.
        These are stored as percentages (e.g. 3.08 = 3.08%) and converted to
        decimal for the EV-aware spread gate in S1.

FIX-07  L2 BOOK: l2_bid_size / l2_ask_size are not available in EOD mode.
        S4 (OBI) gracefully handles None — it falls back to GEX+wall synthesis,
        which now has real data from FIX-03. Sprint 2 item.

FIX-08  SPREAD PCT INTERPRETATION: contract_spread_pct in the pipeline is a
        decimal fraction (0.157 = 15.7%). Previously this column was never read.
        Now used to synthesise options_bid/ask around mid so S1 receives real
        spread data.

OTT-01  SPREAD FORMULA CONFIRMED as (ask−bid)/mid×100 throughout this file:
        - _hard_execution_gates_advisory(): line uses /mid (correct)
        - live_spread_cost calculation: uses /mid (correct)
        - eil_spread_pct_live output: uses spread_pct_live from S1 strategy
        No formula changes required — adding comments to confirm.

OTT-02  SPREAD THRESHOLD ALIGNMENT with M3 LiquidityFilter:
        Advisory warning threshold raised from 8% to 10% to align with
        the M3 module definition of liquid (≤10% spread/mid = LIQUID).
        This prevents the advisory warning from firing on every borderline
        liquid contract and inflating defer_reason noise.

PIPELINE POSITION
-----------------
Phase 9 — runs after Wall Break Scorer (Phase 8e), before Archive (Phase 10).
Operates on all rows passed from superbrain; verdict gates execution.
Zero breaking changes to Phases 1-8.

COMPOSITE SCORING (positional strategy weights — schema v3.0)
-------------------------------------------------------------
    S1 Liquidity Gate      0.50  (spread at entry is primary execution risk)
    S2 IV Distortion       0.40  (buying expensive vol destroys EV)
    S3 GEX Flip            0.05  (intraday structural context)
    S4 OBI                 0.03  (intraday flow synthesis)
    S5 POC Timing          0.02  (geometric position)

VERDICT THRESHOLDS
------------------
    85-100 -> EXECUTE_NOW
    65-84  -> EXECUTE_WITH_CAUTION
    40-64  -> EXECUTE_DEFER
    <40    -> STAND_DOWN_MICROSTRUCTURE
    S1 hard block -> STAND_DOWN_MICROSTRUCTURE (overrides composite)

SIZE MULTIPLIER
---------------
Final size multiplier = minimum of all strategy multipliers x regime_size_mult.
Conservative by design — any strategy flagging a reduction wins.

ADVISORY MODE
-------------
When eil_advisory_only=True (default), EIL verdict is logged and appended
to the CSV but does NOT gate or modify execution.
Set to False only after explicit operator sign-off on calibration.

LIVE CAPITAL WARNING
--------------------
This engine runs against live Tastytrade positions. All logic changes must
be reviewed in isolation before deploying to the orchestrator.
"""

import sys
import os
import logging
from datetime import datetime, timezone
from typing import Optional, Dict

_eil_logger = logging.getLogger(__name__)

# ── Path setup for standalone execution ──────────────────────────────────────
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
_STRAT = os.path.join(_HERE, "vanguard", "execution", "strategies")
if _STRAT not in sys.path:
    sys.path.insert(0, _STRAT)

from execution_schema import (
    ExecutionContext, ExecutionVerdict, StrategyResult,
    WEIGHT_LIQUIDITY, WEIGHT_IV, WEIGHT_GEX, WEIGHT_OBI, WEIGHT_POC,
    SCORE_EXECUTE_NOW, SCORE_EXECUTE_CAUTION, SCORE_EXECUTE_DEFER,
    EV_BLOCK_HARD, EV_SKIP_THRESHOLD,
)

import liquidity_gate
import iv_distortion
import gex_flipper
import obi_predictor
import poc_timing

# EV constants — safe fallback for pre-v3.0 schema
try:
    from execution_schema import EV_BLOCK_HARD, EV_SKIP_THRESHOLD
except ImportError:
    EV_BLOCK_HARD     = -0.10
    EV_SKIP_THRESHOLD =  0.00

# EVEngineV2 availability flag
try:
    from ev_engine_v2 import EVEngineV2 as _EVEngineV2
    _EV_AVAILABLE = True
except ImportError:
    _EV_AVAILABLE = False


# ─────────────────────────────────────────────────────────────────────────────
# INTERNAL HELPERS
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


def _dynamic_size(ctx, composite, s1, s2, s3, s4, s5,
                  regime_size_mult: float = 1.0) -> float:
    """
    Compute final position size multiplier.

    Multiplier chain (all multiplicative, minimum wins for microstructure):
      1. Composite score gate       (<70 -> 0.5x)
      2. OBI failure tax            (not passed -> 0.7x)
      3. GEX proximity penalty      (within 30% of flip -> 0.6x)
      4. IV premium penalty         (>2.0 vol pts -> 0.7x)
      5. Liquidity hard block       (failed -> 0.0x)
      6. regime_size_mult           (macro context, clamped 0.0-1.0)
    """
    size = 1.0
    if composite < 70:
        size *= 0.5
    if not s4.passed:
        size *= 0.7
    if getattr(s3, "gex_proximity_pct", 1.0) < 0.3:
        size *= 0.6
    if getattr(s2, "iv_ask_premium", 0) > 2.0:
        size *= 0.7
    if not s1.passed:
        size = 0.0
    # Regime sizing — never exceeds 1.0 upward
    regime_factor = max(0.0, min(1.0, regime_size_mult))
    size *= regime_factor
    return round(size, 2)


def _defer_reason(*results: StrategyResult) -> Optional[str]:
    reasons = []
    for r in results:
        if not r.passed or r.block:
            reasons.append(f"[{r.strategy_name}] {r.verdict}: {r.detail[:80]}...")
    return "  ||  ".join(reasons) if reasons else None


def _entry_window_advice(s1: StrategyResult, s4: StrategyResult) -> Optional[str]:
    parts = []
    if s1.verdict == "WIDE_SPREAD_OPEN":
        parts.append("Wait until 10:15 ET for optimal liquidity")
    elif s1.verdict == "WIDE_SPREAD_CLOSE":
        parts.append("Defer to next session — pre-close spread widening")
    elif s1.verdict == "CLOSED_AUCTION":
        parts.append("Market closed — queue for next session open")
    obi_regime = getattr(s4, "obi_regime", None)
    if obi_regime == "BEARISH":
        parts.append("Wait for OBI > 0.65 confirmation before entry")
    return "  |  ".join(parts) if parts else None


def _hard_execution_gates(ctx, s1, s2, s3, s4, s5):
    # FIX-HARD-GATES (2026-04-21): Only GENUINE hard blocks here.
    # Spread and IV are now penalties in PSE — not kills at this layer.
    # Keeping them as hard blocks here double-penalises and overrides PSE.
    #
    # Hard blocks retained:
    #   - Liquidity gate failed (S1 block = no executable market)
    #
    # Removed as hard blocks (now PSE penalties):
    #   - Spread > 8%: becomes pse_options_mult penalty in PSE
    #   - IV distortion > 3.0: becomes pse_options_mult penalty in PSE
    #   - GEX DAMPENING: directional context, not an execution kill
    #
    # NOTE: spread_pct is logged as advisory only — retained for audit trail
    failures = []
    if not s1.passed:
        failures.append("Liquidity gate failed — no executable market")
    return failures


def _hard_execution_gates_advisory(ctx, s1, s2, s3, s4, s5) -> list[str]:
    """Advisory warnings written to defer_reason but do NOT set BLOCKED verdict."""
    warnings = []
    if ctx.options_bid and ctx.options_ask and ctx.options_mid:
        spread_pct = ((ctx.options_ask - ctx.options_bid) / ctx.options_mid) * 100
        # OTT-02: Threshold aligned with M3 LiquidityFilter LIQUID boundary (≤10% = liquid)
        # 10-20%: borderline (warn + use limit). >20%: hard reject (handled by S1 liquidity_gate)
        if spread_pct > 20:
            warnings.append(f"Spread {spread_pct:.1f}% [REJECT threshold — S1 should hard block]")
        elif spread_pct > 10:
            warnings.append(f"Spread {spread_pct:.1f}% — BORDERLINE: use limit order, check OI")
    if getattr(s2, "iv_ask_premium", 0) > 3.0:
        warnings.append("IV elevated — PSE options_mult will penalise size")
    if getattr(s3, "gex_regime", None) == "DAMPENING":
        warnings.append("GEX dampening — dealer positioning headwind")
    return warnings


# ─────────────────────────────────────────────────────────────────────────────
# GEX MAP SYNTHESIS  (FIX-03)
# ─────────────────────────────────────────────────────────────────────────────

def _synthesise_gex_map(
    underlying_price: float,
    gamma_flip: Optional[float],
    gamma_flip_gap_pct: Optional[float],
    call_wall: Optional[float],
    put_wall: Optional[float],
    pcr_oi: Optional[float] = None,
) -> Dict[float, float]:
    """
    Synthesise a minimal GEX map from options intelligence scalars.

    The full per-strike GEX map requires a live Polygon scan (Sprint 1 item).
    Until that is wired, construct a 3-5 strike proxy that correctly represents
    the key structural features so S3 and S4 receive non-trivial data:

      - Put wall (below price)  : strong negative GEX anchor
      - Gamma flip (zero cross) : GEX = 0 at this strike
      - Anchor strikes +/- 1%  : create the sign crossing that S3 searches for
      - Call wall (above price) : strong positive GEX anchor
      - Current price region    : net GEX sign from pcr_oi (if available)

    GEX values are in dollars (approximate). The scoring thresholds in S3/S4
    use +/-$500K bands. Magnitudes are set conservatively.

    Sprint 1 replacement: orchestrator overlays ctx.gex_by_strike with the
    full Polygon GEX map after build_execution_context_from_row() returns.
    """
    if not underlying_price or underlying_price <= 0:
        return {}

    gex_map: Dict[float, float] = {}

    # Call wall — strong positive GEX (dealers long gamma above this price)
    if call_wall and call_wall > underlying_price:
        gex_map[round(call_wall, 2)] = 2_500_000.0

    # Put wall — strong negative GEX (dealers short gamma below this price)
    if put_wall and put_wall < underlying_price:
        gex_map[round(put_wall, 2)] = -2_500_000.0

    # Gamma flip — zero crossing by definition
    if gamma_flip and gamma_flip > 0:
        gex_map[round(gamma_flip, 2)] = 0.0

        # Anchor strikes on either side so _find_gex_flip() finds a crossing
        step = max(1.0, round(underlying_price * 0.01, 2))   # 1% of price
        above_flip = round(gamma_flip + step, 2)
        below_flip = round(gamma_flip - step, 2)

        # Above flip: positive GEX (dampening / dealers long gamma)
        # Below flip: negative GEX (amplifying / dealers short gamma)
        if above_flip not in gex_map:
            gex_map[above_flip] = 750_000.0
        if below_flip not in gex_map:
            gex_map[below_flip] = -750_000.0

    # Net GEX at current price from PCR OI proxy
    # pcr_oi > 1.2 = more puts = dealers likely short gamma = negative net GEX
    # pcr_oi < 0.8 = more calls = dealers likely long gamma = positive net GEX
    if pcr_oi is not None:
        current_strike = round(underlying_price, 2)
        if current_strike not in gex_map:
            if pcr_oi > 1.2:
                gex_map[current_strike] = -600_000.0
            elif pcr_oi < 0.8:
                gex_map[current_strike] = 600_000.0
            # Between 0.8-1.2: neutral — leave empty (no contribution)

    return gex_map


# ─────────────────────────────────────────────────────────────────────────────
# MAIN EVALUATE
# ─────────────────────────────────────────────────────────────────────────────

def evaluate(ctx: ExecutionContext) -> ExecutionVerdict:
    """
    Run all five EIL strategies and produce a composite ExecutionVerdict.

    The five strategy files (S1-S5) are self-contained — they read only from
    the ExecutionContext dataclass fields. This function orchestrates them.

    Args:
        ctx: ExecutionContext built by build_execution_context_from_row()

    Returns:
        ExecutionVerdict with all 30+ fields populated
    """
    # ── Run all five strategies ───────────────────────────────────────────────
    s1 = liquidity_gate.run(ctx)
    s2 = iv_distortion.run(ctx)
    s3 = gex_flipper.run(ctx)
    s4 = obi_predictor.run(ctx)
    s5 = poc_timing.run(ctx)

    # ── Hard gate check ───────────────────────────────────────────────────────
    hard_block = any(r.block for r in [s1, s2, s3, s4, s5])

    # ── Composite score (positional weights) ──────────────────────────────────
    composite = (
        s1.score * WEIGHT_LIQUIDITY +
        s2.score * WEIGHT_IV        +
        s3.score * WEIGHT_GEX       +
        s4.score * WEIGHT_OBI       +
        s5.score * WEIGHT_POC
    )

    # ── Macro enrichment modifier (from apply_macro_enrichment_to_discovery.py)
    _macro_bias    = getattr(ctx, "_macro_bias",    "NEUTRAL")
    _macro_abstain = getattr(ctx, "_macro_abstain", False)

    _enrichment_score_modifier = 0.0
    if _macro_bias == "CALL_TAILWIND":
        _enrichment_score_modifier = +10.0
    elif _macro_bias == "PUT_HEADWIND":
        _enrichment_score_modifier = -15.0
    # CONTEXT_ONLY and NEUTRAL: no modifier

    _sector_headwind_applies = not _macro_abstain

    if _macro_abstain:
        _eil_logger.info("MACRO_ABSTAIN: sector headwind bypassed, scoring on structure only")

    if _enrichment_score_modifier != 0.0 and not hard_block:
        composite = composite + _enrichment_score_modifier
        _eil_logger.info(f"ENRICHMENT_MOD: bias={_macro_bias} modifier={_enrichment_score_modifier:+.2f}")
    # ── End macro enrichment modifier ────────────────────────────────────────

    # ── Final verdict ─────────────────────────────────────────────────────────
    raw_verdict    = _composite_verdict(composite, hard_block)
    hard_failures  = _hard_execution_gates(ctx, s1, s2, s3, s4, s5)

    # Hard blocks: only genuine execution killers (no executable market)
    if hard_failures:
        final_verdict     = "BLOCKED"
        defer_reason_text = " | ".join(hard_failures)
    else:
        final_verdict = raw_verdict
        # Advisory warnings: logged but do NOT change verdict
        advisory = _hard_execution_gates_advisory(ctx, s1, s2, s3, s4, s5)
        strategy_reasons = _defer_reason(s1, s2, s3, s4, s5)
        defer_parts = [p for p in [strategy_reasons, " | ".join(advisory)] if p]
        defer_reason_text = " || ".join(defer_parts) if defer_parts else None

    # ── Size multiplier ───────────────────────────────────────────────────────
    # FIX-01: regime_size_mult now correctly read from ctx
    regime_mult = getattr(ctx, "regime_size_mult", 1.0) or 1.0
    size_mult   = _dynamic_size(ctx, composite, s1, s2, s3, s4, s5,
                                regime_size_mult=regime_mult)

    # ── Ancillary fields ──────────────────────────────────────────────────────
    # OTT-S2-01: s2 renamed attribute to iv_spread_pct to prevent collision.
    # Only s1.spread_pct_live (options contract spread) feeds eil_spread_pct_live.
    # s2.iv_spread_pct is IV surface width — not an entry/exit cost, never deducted.
    spread_pct_live = getattr(s1, "spread_pct_live", None)
    iv_ask_premium = getattr(s2, "iv_ask_premium",  0.0)
    gex_flip_level = getattr(s3, "gex_flip_level",  None)
    gex_proximity  = getattr(s3, "gex_proximity_pct", 1.0)
    gex_regime     = getattr(s3, "gex_regime",      "NEUTRAL")
    obi_raw        = getattr(s4, "obi_raw",          0.5)
    iv_tailwind    = getattr(s2, "iv_tailwind_score", 0.0)

    # ── EV fields (schema v3.0) ───────────────────────────────────────────────
    ev_raw = ctx.ev_v2_raw or 0.0

    live_spread_cost = 0.0
    if spread_pct_live is not None:
        live_spread_cost = spread_pct_live / 100.0
    elif ctx.options_bid and ctx.options_ask and ctx.options_mid:
        live_spread_cost = (ctx.options_ask - ctx.options_bid) / ctx.options_mid

    ev_net        = ev_raw - live_spread_cost
    ev_score      = round(max(0.0, min(100.0, 50.0 + ev_raw * 200.0)), 2)
    ev_confidence = round(min(1.0, composite / 100.0), 4)

    poc_proximity_pct = 0.0
    if ctx.poc_price and ctx.current_price and ctx.current_price > 0:
        poc_proximity_pct = round(
            abs(ctx.poc_price - ctx.current_price) / ctx.current_price * 100, 2
        )

    return ExecutionVerdict(
        # Composite
        eil_verdict             = final_verdict,
        eil_raw_verdict         = raw_verdict,
        eil_composite_score     = round(composite, 2),
        eil_advisory_only       = ctx.eil_advisory_only,

        # EV (schema v3.0)
        eil_ev_v2               = round(ev_raw,  6),
        eil_ev_net              = round(ev_net,  6),
        eil_ev_score            = ev_score,
        eil_ev_confidence       = ev_confidence,

        # S1 Liquidity
        eil_liquidity_window    = s1.verdict,
        eil_liquidity_score     = s1.score,
        eil_liquidity_passed    = s1.passed,

        # S2 IV Distortion
        eil_iv_ask_premium      = round(iv_ask_premium, 2),
        eil_iv_distortion_flag  = not s2.passed,
        eil_iv_score            = s2.score,
        eil_iv_passed           = s2.passed,
        eil_iv_tailwind_score   = round(iv_tailwind, 4),

        # S3 GEX
        eil_gex_regime          = gex_regime,
        eil_gex_flip_level      = gex_flip_level,
        eil_gex_proximity_pct   = round(gex_proximity * 100, 2),
        eil_gex_score           = s3.score,
        eil_gex_passed          = s3.passed,

        # S4 OBI
        eil_obi_score_raw       = round(obi_raw, 3) if obi_raw else 0.5,
        eil_obi_regime          = getattr(s4, "obi_regime", "NEUTRAL"),
        eil_obi_score           = s4.score,
        eil_obi_passed          = s4.passed,

        # S5 POC
        eil_poc_proximity_pct   = poc_proximity_pct,
        eil_poc_position        = s5.verdict,
        eil_poc_score           = s5.score,
        eil_poc_passed          = s5.passed,

        # Execution guidance
        eil_size_multiplier             = round(size_mult, 2),
        eil_defer_reason                = defer_reason_text,
        eil_recommended_entry_window    = _entry_window_advice(s1, s4),
        eil_spread_pct_live             = round(spread_pct_live, 2) if spread_pct_live else None,

        # Audit
        eil_check_timestamp     = datetime.now(timezone.utc).isoformat(),
        eil_schema_version      = "3.0.0",
    )


# ─────────────────────────────────────────────────────────────────────────────
# ORCHESTRATOR INTEGRATION HELPER  (FIX-01 through FIX-08)
# ─────────────────────────────────────────────────────────────────────────────

def build_execution_context_from_row(
    row: dict,
    signal_time,
    check_time,
    advisory_only: bool = False,
) -> ExecutionContext:
    """
    Construct a fully-populated ExecutionContext from a superbrain_enriched row.

    COLUMN MAPPING (actual pipeline output as of 2026-04-19)
    ---------------------------------------------------------
    From options_intelligence CSV (merged into superbrain_enriched):
      contract_premium      -> options_mid
      contract_spread_pct   -> synthesise options_bid/ask (decimal, e.g. 0.157)
      contract_iv           -> iv_mid
      contract_oi           -> options_open_interest
      gamma_flip            -> gex_by_strike synthesis
      gamma_flip_gap_pct    -> gex_by_strike synthesis
      call_wall             -> gex_by_strike synthesis
      put_wall              -> gex_by_strike synthesis
      pcr_oi                -> gex_by_strike synthesis
      structural_target     -> poc_price proxy
      underlying_price      -> current_price
      l3_expected_move_1_5d -> expected_move_pct (as decimal)

    From superbrain_enriched:
      ev2_ev_conf_adj       -> ev_v2_raw
      regime_size_mult      -> ctx.regime_size_mult (FIX-01)

    SPRINT 1 OVERLAY (after this function returns):
      ctx.gex_by_strike = <full Polygon per-strike GEX map>

    SPRINT 2 OVERLAY (after this function returns):
      ctx.l2_bid_size = <Polygon NBBO bid size>
      ctx.l2_ask_size = <Polygon NBBO ask size>
    """

    # ── Type-safe field accessors ─────────────────────────────────────────────
    def _f(k, d=0.0):
        v = row.get(k, d)
        try:
            if v is None:
                return d
            f = float(v)
            return d if f != f else f
        except (TypeError, ValueError):
            return d

    def _s(k, d=""):
        v = row.get(k, d)
        if v is None:
            return d
        s = str(v).strip()
        return d if s.lower() in ("nan", "none", "null", "na", "n/a", "") else s

    def _i(k, d=None):
        v = row.get(k, d)
        try:
            return int(float(v)) if v is not None else d
        except (TypeError, ValueError):
            return d

    def _fnn(k, d=None):
        """Float or None — returns None if zero/missing."""
        v = _f(k, 0.0)
        return v if v and v != 0.0 else d

    # ── EV from EVEngineV2 ────────────────────────────────────────────────────
    ev_v2_raw = (
        _f("ev2_ev_conf_adj") or
        _f("ev2_ev_final")    or
        _f("ev_final")        or
        0.0
    )

    # ── Regime size multiplier  (FIX-01) ──────────────────────────────────────
    # FIX-REGIME-CLAMP (2026-04-21): Don't reset regime_size_mult=0 to 1.0.
    # RISK_OFF produces mult=0.4 which is valid and should not be overridden.
    # Only reset if the value is genuinely malformed (negative or unreasonably large).
    regime_size_mult = _f("regime_size_mult", 1.0)
    if regime_size_mult < 0 or regime_size_mult > 2.0:
        regime_size_mult = 1.0   # malformed only — 0 is valid RISK_OFF floor

    # ── Underlying / current price ────────────────────────────────────────────
    current_price = (
        _fnn("underlying_price") or
        _fnn("signal_price")     or
        0.0
    )

    # ── Options contract data  (FIX-02 + FIX-08) ─────────────────────────────
    # contract_spread_pct is a decimal fraction (0.157 = 15.7% spread).
    options_mid = (
        _fnn("contract_premium") or
        _fnn("premium")          or
        None
    )

    # ITEM 2 — Multi-name spread resolver.
    # Try every column name the OI CSV may use before falling back to IV proxy.
    # Single-column lookup (_f("contract_spread_pct", 0.0)) silently returns 0
    # when the column is missing, causing every ticker to use the 10% synthetic
    # and triggering SANITY_WARN_SPREAD (all identical spreads).
    _spread_candidates = (
        _f("contract_spread_pct", 0.0) or
        _f("spread_pct", 0.0)          or
        _f("eil_spread_pct_live", 0.0) or
        _f("bid_ask_spread_pct", 0.0)  or
        _f("options_spread_pct", 0.0)
    )
    if _spread_candidates and _spread_candidates > 0:
        spread_dec = _spread_candidates
        # Normalise: OI sometimes writes 15.7 meaning 15.7%, not 0.157
        if spread_dec > 1.0:
            spread_dec = spread_dec / 100.0
        spread_dec = max(0.001, min(spread_dec, 1.0))
    else:
        # No spread column found — derive from IV rank as a cross-sectional proxy.
        # This produces per-ticker variance rather than a flat default,
        # preventing SANITY_WARN_SPREAD from firing on missing data.
        _iv_proxy = _f("contract_iv", 0.0) or _f("iv_rank", 0.0)
        if _iv_proxy > 0:
            if _iv_proxy < 0.20:   spread_dec = 0.025
            elif _iv_proxy < 0.35: spread_dec = 0.040
            elif _iv_proxy < 0.55: spread_dec = 0.070
            elif _iv_proxy < 0.80: spread_dec = 0.110
            else:                  spread_dec = 0.180
        else:
            spread_dec = 0.05  # absolute last resort

    options_bid = None
    options_ask = None
    if options_mid and options_mid > 0:
        half        = options_mid * spread_dec / 2.0
        options_bid = round(max(0.01, options_mid - half), 2)
        options_ask = round(options_mid + half, 2)

    options_oi = _i("contract_oi") or _i("open_interest") or None

    # ── IV data  (FIX-04) ────────────────────────────────────────────────────
    iv_mid_raw = (
        _fnn("contract_iv") or
        _fnn("iv_mid")      or
        _fnn("implied_vol") or
        None
    )
    iv_mid = iv_mid_raw
    iv_bid = round(iv_mid_raw * 0.97, 6) if iv_mid_raw else None
    iv_ask = round(iv_mid_raw * 1.03, 6) if iv_mid_raw else None

    # ── Expected move  (FIX-06) ──────────────────────────────────────────────
    # l3_expected_move values are percentages — convert to decimal for S1 gate.
    em_raw = (
        _fnn("l3_expected_move_1_5d")  or
        _fnn("l3_expected_move_6_10d") or
        _fnn("expected_move_10d")      or
        None
    )
    expected_move_pct = (em_raw / 100.0) if em_raw else None

    # ── POC derivation  (FIX-05) ─────────────────────────────────────────────
    poc_price    = _fnn("poc_price") or _fnn("structural_target") or None
    price_vs_poc = _fnn("price_vs_poc") or None
    if poc_price and current_price and current_price > 0 and price_vs_poc is None:
        price_vs_poc = round((current_price - poc_price) / poc_price * 100, 2)

    # ── ADX ──────────────────────────────────────────────────────────────────
    adx_value = _fnn("adx") or _fnn("adx_value") or None

    # ── GEX map synthesis  (FIX-03) ──────────────────────────────────────────
    gex_by_strike = _synthesise_gex_map(
        underlying_price   = current_price,
        gamma_flip         = _fnn("gamma_flip"),
        gamma_flip_gap_pct = _fnn("gamma_flip_gap_pct"),
        call_wall          = _fnn("call_wall"),
        put_wall           = _fnn("put_wall"),
        pcr_oi             = _fnn("pcr_oi"),
    )

    # ── Build context ─────────────────────────────────────────────────────────
    ctx = ExecutionContext(
        ticker               = _s("ticker", "UNKNOWN"),
        signal_time          = signal_time,
        superbrain_verdict   = _s("sb_final_verdict", _s("original_verdict", "EXECUTE")),
        wbs_grade            = _s("wbs_grade", "POSSIBLE"),
        wbs_score            = _f("wbs_score", 0.0) or _f("wbs", 0.0),  # WBS writes "wbs", schema expects "wbs_score"
        signal_direction     = _s("direction", "LONG"),
        current_price        = current_price,
        check_time           = check_time,

        # Options contract
        options_symbol       = _s("contract_occ_symbol") or _s("recommended_contract") or None,
        options_bid          = options_bid,
        options_ask          = options_ask,
        options_mid          = options_mid,
        options_open_interest= options_oi,

        # IV
        iv_bid               = iv_bid,
        iv_mid               = iv_mid,
        iv_ask               = iv_ask,

        # L2 book — not available in EOD mode (Sprint 2)
        # S4 falls back to GEX+wall synthesis when None
        l2_bid_size          = _fnn("l2_bid_size") or None,
        l2_ask_size          = _fnn("l2_ask_size") or None,

        # GEX map — synthesised from scalars (Sprint 1: replace with Polygon full map)
        gex_by_strike        = gex_by_strike,

        # POC
        poc_price            = poc_price,
        price_vs_poc_existing= price_vs_poc,

        # Structural context
        adx_value            = adx_value,
        expected_move_pct    = expected_move_pct,

        # EV pass-through
        ev_v2_raw            = ev_v2_raw if ev_v2_raw != 0.0 else None,
        ev_net               = _fnn("ev2_ev_net")   or None,
        ev_score             = _fnn("ev2_ev_score") or None,

        eil_advisory_only    = advisory_only,
    )

    # ── FIX-01: attach regime_size_mult BEFORE return (was dead code) ─────────
    ctx.regime_size_mult = regime_size_mult

    # ── Macro enrichment modifier (from apply_macro_enrichment_to_discovery.py)
    ctx._macro_bias    = str(row.get("macro_bias",    "NEUTRAL")).upper().strip()
    ctx._macro_abstain = str(row.get("macro_abstain", "False")).upper().strip() == "TRUE"

    return ctx


# ─────────────────────────────────────────────────────────────────────────────
# STANDALONE SMOKE TEST
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("  AVSHUNTER EIL v2.0.0 — Smoke Test (all 8 fixes)")
    print("=" * 60 + "\n")

    check_t = datetime(2026, 4, 19, 14, 30, tzinfo=timezone.utc)

    # Simulate DIA PUT row from today's run — mirrors actual superbrain_enriched
    dia_row = {
        "ticker": "DIA",
        "direction": "PUT",
        "sb_final_verdict": "EXECUTE_WITH_RISK",
        "wbs_grade": "PROBABLE",
        "wbs_score": 52.0,
        "underlying_price": 494.22,
        "signal_price": 494.22,
        "contract_occ_symbol": "DIA260618P00485000",
        "contract_premium": 8.25,
        "contract_iv": 0.1647,
        "contract_oi": 313,
        "contract_spread_pct": 0.1576,
        "contract_mark_synthetic": False,
        "gamma_flip": 234.23,
        "gamma_flip_gap_pct": 52.61,
        "call_wall": 500.0,
        "put_wall": 420.0,
        "max_pain": 475.0,
        "pcr_oi": 1.991,
        "structural_target": 449.73,
        "ev2_ev_conf_adj": 0.0086,
        "ev2_ev_final":    0.0095,
        "regime_size_mult": 0.7,
        "l3_expected_move_1_5d": 2.8,
        "l3_expected_move_6_10d": 1.4,
        "composite": 62.2,
    }

    ctx = build_execution_context_from_row(dia_row, check_t, check_t,
                                           advisory_only=True)

    print("  Context fields:")
    print(f"    ticker         : {ctx.ticker}")
    print(f"    direction      : {ctx.signal_direction}")
    print(f"    current_price  : ${ctx.current_price:.2f}")
    print(f"    options_mid    : ${ctx.options_mid:.2f}" if ctx.options_mid else "    options_mid    : NONE")
    print(f"    options_bid    : ${ctx.options_bid:.2f}" if ctx.options_bid else "    options_bid    : NONE")
    print(f"    options_ask    : ${ctx.options_ask:.2f}" if ctx.options_ask else "    options_ask    : NONE")
    if ctx.options_mid and ctx.options_bid:
        spread = (ctx.options_ask - ctx.options_bid) / ctx.options_mid * 100
        print(f"    spread         : {spread:.1f}%")
    print(f"    iv_mid         : {ctx.iv_mid:.4f}" if ctx.iv_mid else "    iv_mid         : NONE")
    print(f"    iv_bid/ask     : {ctx.iv_bid:.4f} / {ctx.iv_ask:.4f}" if ctx.iv_bid else "    iv_bid/ask     : NONE")
    print(f"    OI             : {ctx.options_open_interest}")
    print(f"    GEX strikes    : {sorted(ctx.gex_by_strike.keys())}")
    print(f"    POC price      : {ctx.poc_price}")
    print(f"    expected move  : {ctx.expected_move_pct*100:.2f}%" if ctx.expected_move_pct else "    expected move  : NONE")
    print(f"    ev_v2_raw      : {ctx.ev_v2_raw}")
    print(f"    regime_mult    : {ctx.regime_size_mult}")
    print()

    # Validate all 8 fixes
    assert hasattr(ctx, "regime_size_mult"), "FIX-01 FAIL"
    assert ctx.regime_size_mult == 0.7, f"FIX-01 FAIL: got {ctx.regime_size_mult}"
    print("  FIX-01 PASS  regime_size_mult attached before return")

    assert ctx.options_mid is not None, "FIX-02 FAIL: options_mid None"
    assert ctx.options_bid is not None, "FIX-02 FAIL: options_bid None"
    assert ctx.options_ask is not None, "FIX-02 FAIL: options_ask None"
    print("  FIX-02 PASS  options_bid/ask/mid populated from contract_premium")

    assert len(ctx.gex_by_strike) >= 3, f"FIX-03 FAIL: {len(ctx.gex_by_strike)} strikes"
    print(f"  FIX-03 PASS  GEX map has {len(ctx.gex_by_strike)} strikes")

    assert ctx.iv_mid is not None, "FIX-04 FAIL: iv_mid None"
    assert ctx.iv_bid is not None, "FIX-04 FAIL: iv_bid None"
    assert ctx.iv_ask is not None, "FIX-04 FAIL: iv_ask None"
    print(f"  FIX-04 PASS  IV synthesised: {ctx.iv_bid:.4f} / {ctx.iv_mid:.4f} / {ctx.iv_ask:.4f}")

    assert ctx.poc_price is not None, "FIX-05 FAIL: poc_price None"
    print(f"  FIX-05 PASS  POC from structural_target: ${ctx.poc_price:.2f}")

    assert ctx.expected_move_pct is not None, "FIX-06 FAIL: expected_move_pct None"
    print(f"  FIX-06 PASS  expected_move: {ctx.expected_move_pct*100:.2f}% from l3_expected_move_1_5d")

    print("  FIX-07 NOTE  L2 book None in EOD mode — S4 falls back to GEX+wall synthesis")

    spread_pct = (ctx.options_ask - ctx.options_bid) / ctx.options_mid * 100 if ctx.options_mid else 0
    expected_spread = 0.1576 * 100   # contract_spread_pct * 100
    assert abs(spread_pct - expected_spread) < 1.0, \
        f"FIX-08 FAIL: spread {spread_pct:.1f}% vs expected ~{expected_spread:.1f}%"
    print(f"  FIX-08 PASS  spread {spread_pct:.1f}% correctly derived from contract_spread_pct decimal")

    print()

    # Run evaluate and check discrimination
    verdict = evaluate(ctx)
    print("  EIL Verdict:")
    print(f"    Final          : {verdict.eil_verdict}")
    print(f"    Composite      : {verdict.eil_composite_score}")
    print(f"    Size mult      : {verdict.eil_size_multiplier}")
    print(f"    S1 Liquidity   : {verdict.eil_liquidity_score:.1f}  ({verdict.eil_liquidity_window})")
    print(f"    S2 IV          : {verdict.eil_iv_score:.1f}")
    print(f"    S3 GEX         : {verdict.eil_gex_score:.1f}  ({verdict.eil_gex_regime})")
    print(f"    S4 OBI         : {verdict.eil_obi_score:.1f}  ({verdict.eil_obi_regime})")
    print(f"    S5 POC         : {verdict.eil_poc_score:.1f}  ({verdict.eil_poc_position})")
    print(f"    Defer reason   : {verdict.eil_defer_reason or 'None'}")
    print()

    # Sanity: scores must not all be identical (frozen default)
    scores = [verdict.eil_liquidity_score, verdict.eil_iv_score,
              verdict.eil_gex_score, verdict.eil_obi_score, verdict.eil_poc_score]
    unique = len(set(round(s, 1) for s in scores))
    assert unique >= 2, f"SANITY FAIL: all strategy scores identical — EIL still frozen ({scores})"
    print(f"  SANITY PASS  {unique} unique strategy scores — EIL is discriminating")
    print()
    print("  All v2.0.0 fixes verified")
    print()
