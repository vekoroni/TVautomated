"""
VANGUARD Main Entry Point
Enhanced end-to-end intelligence pipeline

PATCH NOTES
-----------
FIX-04 (2026-04-13): Multi-horizon actuarial fields added to layer_2_result.
    ActuarialOutcomes already computed win_rate_5d, win_rate_10d, expected_value_5d/10d,
    median_gain_if_up_5d/10d, and 9 other 5d/10d fields. None were written to
    layer_2_result, so signal_to_row() received None for all _ov() lookups and
    vanguard_signals.csv had blank win_rate_5d/10d columns.

    Effect: EVEngineV2 _blend_win_probability() triggered DataQualityWarning on every
    row ("All hit rates zero") and fell back to p=0.40. All EV estimates were
    path-layer-only — max ev_final in run 20260412 was +0.031 across 680 rows.

    Fix: 14 fields (7 per horizon) added to layer_2_result. They flow to CSV via:
      1. layer2__win_rate_5d/10d (from flatten_dict(l2) in signal_to_row — read by
         EVEngineV2 PATCH-01 as 0-1 scale values)
      2. win_rate_5d/10d headline columns (extracted by _ov() in signal_to_row —
         read by EVEngineV2 as primary 0-1 scale values)

    schema_version and bucket_schema_version also added (were falling back to "unknown").
"""

from __future__ import annotations

from typing import Optional

from .schemas.input_schema import VanguardInput
from .schemas.trade_schema import VanguardSignal

from .layer1_auction import AuctionStateSynthesizer
from .layer2_statistical import StateVectorCalculator, ActuarialQueryEngine, EdgeDetector
from .layer3_execution import TradeBuilder
import dataclasses

from .config import ACTUARIAL_DATABASE_PATH


def analyze_ticker(vanguard_input: VanguardInput, actuarial_db_path: Optional[str] = None) -> VanguardSignal:
    """
    Convenience function so package imports remain stable.
    """
    engine = VanguardEngine(actuarial_db_path=actuarial_db_path)
    return engine.analyze(vanguard_input)


class VanguardEngine:
    """
    VANGUARD Intelligence System (Enhanced)

    Philosophy:
    - Discovery is NOT execution
    - Edge is continuous, not binary
    - Statistics inform, they do not dictate
    """

    def __init__(self, actuarial_db_path: Optional[str] = None):
        self.auction_synthesizer = AuctionStateSynthesizer()
        self.state_calculator = StateVectorCalculator()
        self.actuarial_engine = ActuarialQueryEngine(actuarial_db_path or ACTUARIAL_DATABASE_PATH)
        self.edge_detector = EdgeDetector()
        self.trade_builder = TradeBuilder()

    def analyze(self, vanguard_input: VanguardInput) -> VanguardSignal:
        ticker = vanguard_input.ticker

        print(f"\n{'=' * 60}")
        print(f"VANGUARD ANALYSIS: {ticker}")
        print(f"{'=' * 60}\n")

        # =========================
        # DATA INTEGRITY HEADER
        # =========================
        # (Fail-open for discovery; fail-closed for execution)
        intraday_rows = 0
        try:
            intraday_rows = 0 if vanguard_input.intraday_df is None else len(vanguard_input.intraday_df)
        except Exception:
            intraday_rows = 0

        print("[DATA] Input Integrity")
        print(f"  current_price: {getattr(vanguard_input, 'current_price', None)}")
        print(f"  intraday_rows: {intraday_rows}")
        print(f"  has_macro_regime: {hasattr(vanguard_input, 'macro_regime') and vanguard_input.macro_regime is not None}")
        print(f"  has_wyckoff_phase: {hasattr(vanguard_input, 'wyckoff_phase') and vanguard_input.wyckoff_phase is not None}")
        print(f"  has_compression: {hasattr(vanguard_input, 'compression_ratio') and vanguard_input.compression_ratio is not None}")

        # =========================
        # LAYER 1 — AUCTION
        # =========================
        print("\n[LAYER 1] Auction Intelligence")
        auction = self.auction_synthesizer.synthesize(vanguard_input)

        print(f"  State: {auction.auction_state}")
        print(f"  Acceptance: {auction.acceptance.classification} ({auction.acceptance.score}/100)")
        print(f"  Control: {auction.control.controller} ({auction.control.confidence*100:.1f}%)")

        # =========================
        # LAYER 2 — STATISTICAL
        # =========================
        print("\n[LAYER 2] Statistical Context")
        state = self.state_calculator.calculate_state(vanguard_input, auction)
        outcomes = self.actuarial_engine.query(state)

        print(f"  State Hash: {state.state_hash}")
        print(f"  Matches: {outcomes.n_observations if outcomes else 0}")

        # --- Edge quality (informational, not a hard reject) ---
        edge_quality = "NONE"
        discovery_flag = False

        if outcomes is not None and outcomes.n_observations >= 50:
            discovery_flag = True

            if outcomes.expected_value_20d >= 0.03 and outcomes.prob_up_10pct_20d >= 0.40:
                edge_quality = "STRONG"
            elif outcomes.expected_value_20d >= 0.015:
                edge_quality = "MODERATE"
            else:
                edge_quality = "WEAK"

            # ── AUDITABLE METRICS ─────────────────────────────────────────────
            # Each label matches the exact formula used in _calculate_outcomes()
            # P(return > 0)     = outcome_20d_return > 0  (directional win rate)
            # P(hit +10%/20d)   = outcome_hit_10pct_up    (target hit rate)
            # EV(20d)           = P(up)*median_gain + P(down)*median_loss
            print(f"  P(return > 0, 20d):    {outcomes.win_rate:.1%}   <- directional win rate")
            print(f"  P(hit +10% / 20d):     {outcomes.prob_up_10pct_20d:.1%}   <- target hit rate")
            print(f"  Median gain  (if up):  {outcomes.median_gain_if_up:.2%}")
            print(f"  Median loss  (if down):{outcomes.median_loss_if_down:.2%}")
            print(f"  EV(20d):               {outcomes.expected_value_20d:.2%}   <- P(up)*gain + P(down)*loss")
            print(f"  Sharpe(20d):           {outcomes.sharpe_ratio:.2f}")
            print(f"  Edge Quality:          {edge_quality}  (N={outcomes.n_observations:,})")
        else:
            print("  Insufficient actuarial history (n < 50) — discovery only")

        # =========================
        # EDGE DETECTION (SOFT FOR DISCOVERY)
        # =========================
        if outcomes is not None:
            edge = self.edge_detector.detect_edge(
                state=state,
                outcomes=outcomes,
                auction_verdict=auction
            )
        else:
            # Create a no-edge result when outcomes is None
            from .schemas.trade_schema import EdgeAssessment
            edge = EdgeAssessment(
                has_edge=False,
                edge_direction="NONE",
                edge_magnitude=0.0,
                confidence=0.0,
                right_side_score=0.0,
                verdict_tier="NO_EDGE",
                gate_failed="NO_DATA",
                rationale="No actuarial data available",
                supporting_factors=[],
                risk_warnings=[]
            )

        # =========================
        # LAYER 3 — EXECUTION
        # =========================
        execution_plan = None
        verdict = "OBSERVE"
        recommendation = "MONITOR"

        # TRADE requires BOTH:
        # (1) statistical edge and (2) edge_quality at least MODERATE
        # (Optionally later: acceptance/control thresholds too)
        if edge.has_edge and edge_quality in {"MODERATE", "STRONG"}:
            execution_plan = self.trade_builder.build_trade_plan(
                ticker=ticker,
                current_price=vanguard_input.current_price,
                edge=edge
            )
            verdict = "TRADE"
            recommendation = f"{edge.edge_direction} ({edge_quality})"
        elif discovery_flag and edge_quality != "WEAK":
            verdict = "DISCOVERY"
            recommendation = f"EDGE_{edge_quality}"
        # WEAK edge falls through to OBSERVE — insufficient to surface as discovery

        print(f"\nVERDICT: {verdict} — {recommendation}")
        print(f"{'=' * 60}\n")

        # Build state descriptor for debug signature
        _state_sig = f"{state.vol_regime}|{state.trend_direction}|{state.trend_maturity}|{state.structure_quality}"

        return VanguardSignal(
            ticker=ticker,
            timestamp=vanguard_input.analysis_timestamp.isoformat(),
            verdict=verdict,
            final_recommendation=recommendation,
            layer_1_result=dataclasses.asdict(auction) if dataclasses.is_dataclass(auction) else vars(auction),
            layer_2_result={
                # --- identity ---
                "state_hash":        state.state_hash,
                "debug_signature":   _state_sig,

                # --- actuarial outcomes ---
                # NOTE: win_rate_20d = P(20d_return > 0) — directional win rate
                #       prob_up_10pct_20d = P(hit +10% within 20d) — target hit rate
                #       These are DIFFERENT metrics — do not conflate
                "n_observations":          outcomes.n_observations if outcomes else 0,
                "win_rate_20d":            getattr(outcomes, "win_rate", None),            # P(return > 0) — directional
                "prob_up_10pct_20d":       getattr(outcomes, "prob_up_10pct_20d", None),   # P(hit +10%) — target rate
                "expected_value_20d":      getattr(outcomes, "expected_value_20d", None),
                "confidence_level":        getattr(outcomes, "confidence_level", None),
                "prob_down_5pct_first":    getattr(outcomes, "prob_down_5pct_before_up_10pct", None),
                "median_gain_if_up":       getattr(outcomes, "median_gain_if_up", None),
                "median_loss_if_down":     getattr(outcomes, "median_loss_if_down", None),
                "median_max_drawdown":     getattr(outcomes, "median_max_drawdown", None),
                "kelly_fraction":          getattr(outcomes, "kelly_fraction", None),
                "sharpe_ratio":            getattr(outcomes, "sharpe_ratio", None),
                "recommended_hold_days":   getattr(outcomes, "recommended_hold_days", None),

                # FIX-04: Multi-horizon actuarial fields (5d + 10d).
                # ActuarialOutcomes already computes these fields but they were never
                # written to layer_2_result, so signal_to_row() received None for all
                # _ov("win_rate_5d") etc. calls → vanguard_signals.csv had blank
                # win_rate_5d/10d columns → EVEngineV2 fell back to p=0.40 for every
                # row → all EV estimates were structurally degraded.
                #
                # These flow to CSV via two paths:
                #   1. layer2__win_rate_5d etc. (from flatten_dict(l2) in signal_to_row)
                #   2. win_rate_5d etc. (direct headline fields extracted by _ov() in signal_to_row)
                # EVEngineV2 PATCH-01 reads layer2__win_rate_5d on 0-100 scale first,
                # then win_rate_5d on 0-1 scale — both paths now populated.
                #
                # --- 5-day horizon ---
                "win_rate_5d":             getattr(outcomes, "win_rate_5d",  None),
                "expected_value_5d":       getattr(outcomes, "expected_value_5d",  None),
                "prob_up_5pct_5d":         getattr(outcomes, "prob_up_5pct_5d",  None),
                "median_gain_if_up_5d":    getattr(outcomes, "median_gain_if_up_5d",  None),
                "median_loss_if_down_5d":  getattr(outcomes, "median_loss_if_down_5d",  None),
                "median_max_drawdown_5d":  getattr(outcomes, "median_max_drawdown_5d",  None),
                "sharpe_ratio_5d":         getattr(outcomes, "sharpe_ratio_5d",  None),
                # --- 10-day horizon ---
                "win_rate_10d":            getattr(outcomes, "win_rate_10d", None),
                "expected_value_10d":      getattr(outcomes, "expected_value_10d", None),
                "prob_up_7pct_10d":        getattr(outcomes, "prob_up_7pct_10d", None),
                "median_gain_if_up_10d":   getattr(outcomes, "median_gain_if_up_10d", None),
                "median_loss_if_down_10d": getattr(outcomes, "median_loss_if_down_10d", None),
                "median_max_drawdown_10d": getattr(outcomes, "median_max_drawdown_10d", None),
                "sharpe_ratio_10d":        getattr(outcomes, "sharpe_ratio_10d", None),

                # --- edge assessment ---
                "has_edge":         edge.has_edge,
                "edge_direction":   edge.edge_direction,
                "edge_quality":     edge_quality,
                "failed_gate":      getattr(edge, "gate_failed", None),   # matches EdgeAssessment.gate_failed
                "no_edge_reason":   getattr(edge, "rationale", None) if not edge.has_edge else None,

                # --- discovery / classification ---
                "discovery_flag":   discovery_flag,

                # --- schema versioning (written to every row for audit traceability) ---
                # signal_to_row() reads these from l2; without them it falls back to "unknown"
                "schema_version":        state.schema_version,
                "bucket_schema_version": state.bucket_schema_version,

                # --- state vector fields (for post-mortem analysis) ---
                "vol_regime":        state.vol_regime,
                "trend_direction":   state.trend_direction,
                "trend_maturity":    state.trend_maturity,
                "structure_quality": state.structure_quality,
            },
            layer_3_result=execution_plan,
            reasoning=edge.rationale if edge.has_edge else "Statistical context only",
            execution_plan=execution_plan,
        )


