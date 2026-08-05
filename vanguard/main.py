"""
VANGUARD Main Entry Point
Enhanced end-to-end intelligence pipeline
"""

from __future__ import annotations

from typing import Optional
from pathlib import Path

from .schemas.input_schema import VanguardInput
from .schemas.trade_schema import VanguardSignal

from .layer1_auction import AuctionStateSynthesizer
from .layer2_statistical import StateVectorCalculator, ActuarialQueryEngine, EdgeDetector
# layer3_execution (TradeBuilder) intentionally excluded — Vanguard is an intelligence
# layer only. Execution authority belongs to Options Intelligence → EIL → PSE → MVE.
import dataclasses

from .config import (
    ACTUARIAL_DATABASE_PATH,
    ACTUARIAL_DATABASE_FILENAME,
    REQUIRED_ACTUARIAL_V6_COLUMNS,
    OPTIONAL_ACTUARIAL_V6_COLUMNS,
)


def _sample_confidence_bucket(n: int) -> str:
    """
    Classify actuarial sample size for downstream governance.
    Does not block calculations — controls how much trust the pipeline
    is allowed to place in the result.

    Downstream consumers (EIL, MVE, PSE) must gate on this field.
    INSUFFICIENT_SAMPLE / CONTEXT_ONLY must never reach execution.
    """
    if n >= 100: return "HIGH_SAMPLE"
    if n >= 50:  return "USABLE_SAMPLE"
    if n >= 30:  return "WEAK_SAMPLE"
    if n >= 10:  return "CONTEXT_ONLY"
    return "INSUFFICIENT_SAMPLE"


def _select_preferred_horizon(outcomes) -> str:
    """
    Select the best actuarial horizon using EV first, then win rate.
    Not an execution instruction — a historical edge label for downstream routing.

    Horizon with highest EV wins. Win rate used as tiebreaker.
    Returns NONE when outcomes is None or all EV/win_rate values are missing.
    """
    if outcomes is None:
        return "NONE"

    candidates = [
        ("5D",  getattr(outcomes, "expected_value_5d",  None), getattr(outcomes, "win_rate_5d",  None)),
        ("10D", getattr(outcomes, "expected_value_10d", None), getattr(outcomes, "win_rate_10d", None)),
        ("20D", getattr(outcomes, "expected_value_20d", None), getattr(outcomes, "win_rate",     None)),
    ]

    valid = [c for c in candidates if c[1] is not None and c[2] is not None]
    if not valid:
        return "NONE"

    best = sorted(valid, key=lambda x: (x[1], x[2]), reverse=True)[0]
    return best[0]


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

        db_path = Path(actuarial_db_path or ACTUARIAL_DATABASE_PATH)

        if not db_path.exists():
            raise FileNotFoundError(
                f"Actuarial database not found: {db_path}\n"
                "Build the v6 database before running the pipeline."
            )

        if db_path.name != ACTUARIAL_DATABASE_FILENAME:
            raise RuntimeError(
                f"Wrong actuarial database loaded: {db_path.name}. "
                f"Expected {ACTUARIAL_DATABASE_FILENAME}. "
                "Refusing to continue — v5 fallback breaks Stage 0 "
                "future_momentum_bucket logic and will produce incorrect sizing."
            )

        self._validate_actuarial_database_contract(db_path)
        self.actuarial_engine = ActuarialQueryEngine(str(db_path))
        self.edge_detector = EdgeDetector()
        # TradeBuilder intentionally not instantiated — execution is downstream authority

    def _validate_actuarial_database_contract(self, db_path: Path) -> None:
        """
        Fix 2 — validate parquet schema, not just filename.
        A correctly named file can still be missing required canonical columns.
        Reads parquet metadata only (fast) to check column names without loading all rows.
        Raises RuntimeError listing any missing required columns.
        """
        try:
            import pandas as pd
        except ImportError as exc:
            raise RuntimeError("pandas is required to validate the actuarial parquet schema.") from exc

        try:
            # Read schema only — do not load full dataset for validation
            import pyarrow.parquet as pq
            schema = pq.read_schema(str(db_path))
            columns = set(schema.names)
        except Exception:
            # Fallback: load with pandas if pyarrow metadata read fails
            try:
                df = pd.read_parquet(db_path)
                columns = set(df.columns)
            except Exception as exc:
                raise RuntimeError(
                    f"Unable to read actuarial database for schema validation: {db_path}"
                ) from exc

        missing_required = [col for col in REQUIRED_ACTUARIAL_V6_COLUMNS if col not in columns]
        if missing_required:
            raise RuntimeError(
                f"Actuarial database at {db_path.name} does not satisfy the required database contract. "
                f"Missing required columns: {missing_required}. "
                "Rebuild the governed actuarial parquet before running the pipeline."
            )

        missing_optional = [col for col in OPTIONAL_ACTUARIAL_V6_COLUMNS if col not in columns]

        print(f"[DB] Actuarial database: {db_path.name}")
        print(f"[DB] required contract: PASS ({len(REQUIRED_ACTUARIAL_V6_COLUMNS)} required columns present)")
        if missing_optional:
            print(f"[DB] Optional v6 columns absent: {missing_optional} — early_candidate logic will be skipped")
        else:
            print(f"[DB] early_candidate column: PRESENT")

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

        # Fix 2: compute sample confidence and preferred horizon immediately.
        # Both are defined here regardless of outcomes None/non-None so that
        # the Layer 3 classification block can always read them safely.
        preferred_horizon = _select_preferred_horizon(outcomes)
        sample_confidence_bucket = (
            getattr(outcomes, "sample_confidence_bucket", None)
            if outcomes else None
        ) or _sample_confidence_bucket(outcomes.n_observations if outcomes else 0)

        print(f"  State Hash: {state.state_hash}")
        print(f"  Matches: {outcomes.n_observations if outcomes else 0}")
        print(f"  Sample Confidence: {sample_confidence_bucket}")
        print(f"  Preferred Horizon: {preferred_horizon}")

        # Patch G — match-method audit fields
        # Exposes how Vanguard created the historical sample.
        # HIGH_SAMPLE from CORE_4D_FALLBACK != HIGH_SAMPLE from exact state match.
        state_match_method     = getattr(outcomes, "state_match_method",     "UNKNOWN") if outcomes else "NO_MATCH"
        state_match_stage      = getattr(outcomes, "state_match_stage",      "UNKNOWN") if outcomes else "NO_MATCH"
        state_match_dimensions = getattr(outcomes, "state_match_dimensions", "")        if outcomes else ""
        state_match_quality    = getattr(outcomes, "state_match_quality",    "UNKNOWN") if outcomes else "NO_MATCH"
        state_match_similarity = getattr(outcomes, "state_match_similarity", 0.0)       if outcomes else 0.0
        state_match_is_exact   = bool(getattr(outcomes, "state_match_is_exact", False)) if outcomes else False
        state_match_sample_size = getattr(
            outcomes, "sample_size", outcomes.n_observations if outcomes else 0
        ) if outcomes else 0
        matched_state_key      = getattr(outcomes, "matched_state_key", "")             if outcomes else ""
        original_state_key     = getattr(outcomes, "original_state_key", "")            if outcomes else ""
        fallback_reason        = (getattr(outcomes, "fallback_reason", "") or "NONE")  if outcomes else "NO_OUTCOMES"
        confidence_penalty     = getattr(outcomes, "confidence_penalty", 0.30)          if outcomes else 0.30
        confidence_weight      = getattr(outcomes, "confidence_weight", confidence_penalty) if outcomes else 0.30
        probability_verdict    = getattr(outcomes, "probability_verdict", "NO_STAT_EDGE") if outcomes else "NO_STAT_EDGE"
        probability_edge       = getattr(outcomes, "probability_edge", 0.0)             if outcomes else 0.0
        try:
            probability_edge = float(probability_edge or 0.0)
        except (TypeError, ValueError):
            probability_edge = 0.0

        print(f"  Match Method:      {state_match_method}")
        print(f"  Match Stage:       {state_match_stage}")
        print(f"  Match Quality:     {state_match_quality}")
        print(f"  Match Similarity:  {state_match_similarity}")
        print(f"  Match Exact:       {state_match_is_exact}")
        print(f"  Confidence Weight: {confidence_weight}")
        print(f"  Probability Edge:  {probability_edge} ({probability_verdict})")

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

        # Fix 7 — v6 bucket intelligence print block
        print("\n  [V2 BUCKET INTELLIGENCE]")
        print(f"  phase_v2:                         {getattr(state, 'phase_v2', None)}")
        print(f"  momentum_score:                   {getattr(state, 'momentum_score', None):.2f}" if getattr(state, 'momentum_score', None) is not None else "  momentum_score:                   N/A")
        print(f"  momentum_bucket:                  {getattr(state, 'momentum_bucket', None)}")
        print(f"  location_bucket:                  {getattr(state, 'location_bucket', None)}")
        print(f"  state_v2:                         {getattr(state, 'state_v2', None)}")
        print(f"  early_candidate:                  {getattr(state, 'early_candidate', None)}")
        _fmb      = getattr(outcomes, 'future_momentum_bucket', None) if outcomes else None
        _fmb_conf = getattr(outcomes, 'future_momentum_bucket_confidence', None) if outcomes else None
        _fmb_n    = getattr(outcomes, 'future_momentum_bucket_sample_size', None) if outcomes else None
        _fmb_dist = getattr(outcomes, 'future_momentum_bucket_distribution', None) if outcomes else None
        _tfr      = getattr(outcomes, 'transition_flag_rate_v2', None) if outcomes else None
        _amd      = getattr(outcomes, 'avg_momentum_delta', None) if outcomes else None
        _aad      = getattr(outcomes, 'avg_atr_delta', None) if outcomes else None
        _addx     = getattr(outcomes, 'avg_adx_delta', None) if outcomes else None
        _ecr      = getattr(outcomes, 'early_candidate_rate', None) if outcomes else None
        print(f"  dominant future_momentum_bucket:  {_fmb}")
        print(f"  future bucket confidence:         {f'{_fmb_conf:.1%}' if _fmb_conf is not None else 'N/A'}")
        print(f"  future bucket sample size:        {_fmb_n}")
        print(f"  future bucket distribution:       {_fmb_dist}")
        print(f"  transition flag rate v2:          {f'{_tfr:.1%}' if _tfr is not None else 'N/A'}")
        print(f"  avg momentum delta:               {f'{_amd:.4f}' if _amd is not None else 'N/A'}")
        print(f"  avg ATR delta:                    {f'{_aad:.4f}' if _aad is not None else 'N/A'}")
        print(f"  avg ADX delta:                    {f'{_addx:.4f}' if _addx is not None else 'N/A'}")
        print(f"  early candidate rate:             {f'{_ecr:.1%}' if _ecr is not None else 'N/A'}")

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
        # LAYER 3 — ACTUARIAL CLASSIFICATION ONLY
        # =========================
        # Vanguard authority:
        #   - determine historical edge quality
        #   - determine sample strength
        #   - determine preferred horizon
        #   - provide probability evidence
        #
        # Vanguard must NOT finalise execution, choose contracts,
        # size risk, or issue execution-style verdicts.
        # That authority belongs to: Options Intelligence → EIL → PSE → MVE.

        execution_plan = None
        verdict = "OBSERVE"
        recommendation = "MONITOR"

        _n = outcomes.n_observations if outcomes else 0
        bucket_edge_quality = str(getattr(edge, "bucket_edge_quality", "") or "").upper().strip()

        # Vanguard is the first place the pipeline can lose monetisable signal.
        # Keep the legacy EV label for audit, but export a promoted quality label
        # when the v6 bucket/statistical layer finds a repeatable probability edge.
        strong_bucket_labels = {
            "EARLY_EXPANSION_STRONG",
            "BUCKET_STRONG",
            "STATISTICAL_STRONG",
        }
        moderate_bucket_labels = {
            "EARLY_CANDIDATE_MODERATE",
            "STATISTICAL_MODERATE",
            "LEGACY_MODERATE",
        }
        exported_edge_quality = edge_quality
        if bucket_edge_quality in strong_bucket_labels:
            exported_edge_quality = "STRONG"
        elif bucket_edge_quality in moderate_bucket_labels and exported_edge_quality != "STRONG":
            exported_edge_quality = "MODERATE"
        elif _n >= 100 and probability_edge >= 0.10:
            exported_edge_quality = "STRONG"
        elif _n >= 100 and probability_edge >= 0.05 and exported_edge_quality != "STRONG":
            exported_edge_quality = "MODERATE"
        statistical_has_edge = bool(edge.has_edge or exported_edge_quality in {"STRONG", "MODERATE"})
        legacy_failed_gate = getattr(edge, "failed_gate", None) or getattr(edge, "gate_failed", None)
        legacy_no_edge_reason = getattr(edge, "rationale", None) if not edge.has_edge else None
        active_failed_gate = None if statistical_has_edge else legacy_failed_gate
        active_no_edge_reason = None if statistical_has_edge else legacy_no_edge_reason
        support_note = legacy_no_edge_reason if statistical_has_edge and not edge.has_edge else None
        edge_direction_label = (
            edge.edge_direction
            if str(edge.edge_direction).upper() in {"CALL", "PUT"}
            else "STAT"
        )

        if _n < 10:
            verdict        = "INSUFFICIENT_SAMPLE"
            recommendation = "NO_ACTUARIAL_DATA"

        elif _n < 30:
            verdict        = "ACTUARIAL_CONTEXT_ONLY"
            recommendation = "THIN_SAMPLE_CONTEXT_ONLY"

        elif _n < 50:
            verdict        = "ACTUARIAL_WEAK_SAMPLE"
            recommendation = "WEAK_SAMPLE_NO_PROMOTION"

        elif statistical_has_edge and exported_edge_quality == "STRONG":
            verdict        = "ACTUARIAL_SUPPORT"
            recommendation = f"{edge_direction_label}_EDGE_STRONG_{preferred_horizon}"

        elif statistical_has_edge and exported_edge_quality == "MODERATE":
            verdict        = "ACTUARIAL_MODERATE"
            recommendation = f"{edge_direction_label}_EDGE_MODERATE_{preferred_horizon}"

        elif discovery_flag and exported_edge_quality == "WEAK":
            verdict        = "ACTUARIAL_WEAK"
            recommendation = f"EDGE_WEAK_CONTEXT_ONLY_{preferred_horizon}"

        else:
            verdict        = "ACTUARIAL_NEUTRAL"
            recommendation = "NO_HISTORICAL_EDGE"

        print(f"\nVANGUARD VERDICT: {verdict} — {recommendation}")
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
                #
                # FIX-04: win_rate_5d and win_rate_10d are now written explicitly so that
                # run_vanguard_from_packages._ov() finds them as top-level l2 keys.
                # Previously only win_rate_20d was present; EVEngineV2 fell back to
                # a=0.40 (flat prior) for every row, causing DataQualityWarning on all rows.
                "n_observations":              outcomes.n_observations if outcomes else 0,
                "sample_confidence_bucket":    sample_confidence_bucket,
                "preferred_horizon":           preferred_horizon,
                # Patch H — match-method audit fields in layer_2_result.
                # Runner flattens these into layer2__state_match_* CSV columns automatically.
                "state_match_method":          state_match_method,
                "state_match_stage":           state_match_stage,
                "state_match_dimensions":      state_match_dimensions,
                "state_match_quality":         state_match_quality,
                "state_match_similarity":      state_match_similarity,
                "state_match_is_exact":        state_match_is_exact,
                "sample_size":                 state_match_sample_size,
                "confidence_penalty":          confidence_penalty,
                "confidence_weight":           confidence_weight,
                "matched_state_key":           matched_state_key,
                "original_state_key":          original_state_key,
                "fallback_reason":             fallback_reason,
                # Phase 2 probability calibration. Raw probabilities come from the
                # selected historical sample; adjusted values use shrinkage.
                "raw_prob_up_5d":              getattr(outcomes, "raw_prob_up_5d", None),
                "raw_prob_up_10d":             getattr(outcomes, "raw_prob_up_10d", None),
                "raw_prob_up_20d":             getattr(outcomes, "raw_prob_up_20d", None),
                "raw_prob_down_5d":            getattr(outcomes, "raw_prob_down_5d", None),
                "raw_prob_down_10d":           getattr(outcomes, "raw_prob_down_10d", None),
                "raw_prob_down_20d":           getattr(outcomes, "raw_prob_down_20d", None),
                "raw_prob_target_hit":         getattr(outcomes, "raw_prob_target_hit", None),
                "raw_prob_stop_hit":           getattr(outcomes, "raw_prob_stop_hit", None),
                "raw_expected_return":         getattr(outcomes, "raw_expected_return", None),
                "raw_expected_drawdown":       getattr(outcomes, "raw_expected_drawdown", None),
                "raw_expected_time_to_target": getattr(outcomes, "raw_expected_time_to_target", None),
                "baseline_probability":        getattr(outcomes, "baseline_probability", None),
                "adjusted_prob_target_hit":    getattr(outcomes, "adjusted_prob_target_hit", None),
                "adjusted_expected_return":    getattr(outcomes, "adjusted_expected_return", None),
                "probability_edge":            probability_edge,
                "probability_verdict":         probability_verdict,
                # 20-day horizon (primary)
                "win_rate_20d":            getattr(outcomes, "win_rate", None),
                "prob_up_10pct_20d":       getattr(outcomes, "prob_up_10pct_20d", None),
                "expected_value_20d":      getattr(outcomes, "expected_value_20d", None),
                "confidence_level":        getattr(outcomes, "confidence_level", None),
                "prob_down_5pct_first":    getattr(outcomes, "prob_down_5pct_before_up_10pct", None),
                "median_gain_if_up":       getattr(outcomes, "median_gain_if_up", None),
                "median_loss_if_down":     getattr(outcomes, "median_loss_if_down", None),
                "median_max_drawdown":     getattr(outcomes, "median_max_drawdown", None),
                "kelly_fraction":          getattr(outcomes, "kelly_fraction", None),
                "sharpe_ratio":            getattr(outcomes, "sharpe_ratio", None),
                "recommended_hold_days":   getattr(outcomes, "recommended_hold_days", None),
                # 5-day horizon (FIX-04: was missing — caused DataQualityWarning in EVEngineV2)
                "win_rate_5d":             getattr(outcomes, "win_rate_5d", None),
                "expected_value_5d":       getattr(outcomes, "expected_value_5d", None),
                "prob_up_5pct_5d":         getattr(outcomes, "prob_up_5pct_5d", None),
                "median_gain_if_up_5d":    getattr(outcomes, "median_gain_if_up_5d", None),
                "median_loss_if_down_5d":  getattr(outcomes, "median_loss_if_down_5d", None),
                "median_max_drawdown_5d":  getattr(outcomes, "median_max_drawdown_5d", None),
                "sharpe_ratio_5d":         getattr(outcomes, "sharpe_ratio_5d", None),
                # 10-day horizon (FIX-04: was missing — caused DataQualityWarning in EVEngineV2)
                "win_rate_10d":            getattr(outcomes, "win_rate_10d", None),
                "expected_value_10d":      getattr(outcomes, "expected_value_10d", None),
                "prob_up_7pct_10d":        getattr(outcomes, "prob_up_7pct_10d", None),
                "median_gain_if_up_10d":   getattr(outcomes, "median_gain_if_up_10d", None),
                "median_loss_if_down_10d": getattr(outcomes, "median_loss_if_down_10d", None),
                "median_max_drawdown_10d": getattr(outcomes, "median_max_drawdown_10d", None),
                "sharpe_ratio_10d":        getattr(outcomes, "sharpe_ratio_10d", None),
                # Return-distribution percentiles (Actuarial Distribution sprint).
                # Explicit, like win_rate_5d/_10d above (see FIX-04 note) — the
                # nested "outcomes" dict below would otherwise be the only path
                # these reach, flattened as layer2__outcomes__* instead of the
                # primary layer2__* keys other pipeline stages actually read.
                **{
                    f"ret_pctl_{h}_{p}": getattr(outcomes, f"ret_pctl_{h}_{p}", None)
                    for h in ("5d", "10d", "20d")
                    for p in ("p01","p05","p10","p20","p30","p40","p50",
                              "p60","p70","p80","p90","p95","p99")
                },
                "n_obs_5d":  getattr(outcomes, "n_obs_5d", None),
                "n_obs_10d": getattr(outcomes, "n_obs_10d", None),
                "n_obs_20d": getattr(outcomes, "n_obs_20d", None),
                # Nested outcomes dict for run_vanguard_from_packages._ov() fallback path.
                # SERIALISATION: must be a plain dict — NOT the raw dataclass object.
                # A raw dataclass would survive csv.DictWriter (written as repr string)
                # but break any downstream code that calls .get() on that column.
                "outcomes": (
                    dataclasses.asdict(outcomes)
                    if outcomes is not None
                    and dataclasses.is_dataclass(outcomes)
                    and not isinstance(outcomes, type)
                    else (dict(outcomes.__dict__) if hasattr(outcomes, "__dict__") else {})
                ),

                # --- edge assessment ---
                "has_edge":         statistical_has_edge,
                "edge_direction":   edge.edge_direction,
                "edge_quality":     exported_edge_quality,
                "legacy_edge_quality": edge_quality,
                "failed_gate":      active_failed_gate,
                "no_edge_reason":   active_no_edge_reason,
                # Separate the old EV gate note from the active trade-support
                # label. Downstream should not see STRONG_EDGE and NO_EDGE as
                # competing truths in the same fields.
                "edge_gate_has_edge": bool(edge.has_edge),
                "legacy_failed_gate": legacy_failed_gate,
                "legacy_no_edge_reason": legacy_no_edge_reason,
                "statistical_support_note": support_note,

                # --- discovery / classification ---
                "discovery_flag":   discovery_flag,

                # --- state vector fields (for post-mortem analysis) ---
                "vol_regime":        state.vol_regime,
                "trend_direction":   state.trend_direction,
                "trend_maturity":    state.trend_maturity,
                "structure_quality": state.structure_quality,

                # Fix 8 — v6 current-state bucket fields
                "phase_v2":              getattr(state, "phase_v2", None),
                "momentum_score":        getattr(state, "momentum_score", None),
                "momentum_bucket":       getattr(state, "momentum_bucket", None),
                "location_bucket":       getattr(state, "location_bucket", None),
                "state_v2":              getattr(state, "state_v2", None),
                "early_candidate":       getattr(state, "early_candidate", None),
                "transition_flag_v2":    getattr(state, "transition_flag_v2", None),

                # Fix 8 — v6 future bucket outcome fields
                "future_momentum_bucket":              getattr(outcomes, "future_momentum_bucket", None),
                "future_momentum_bucket_distribution": getattr(outcomes, "future_momentum_bucket_distribution", None),
                "future_momentum_bucket_confidence":   getattr(outcomes, "future_momentum_bucket_confidence", None),
                "future_momentum_bucket_sample_size":  getattr(outcomes, "future_momentum_bucket_sample_size", None),
                "transition_flag_rate_v2":             getattr(outcomes, "transition_flag_rate_v2", None),
                "avg_momentum_delta":                  getattr(outcomes, "avg_momentum_delta", None),
                "avg_atr_delta":                       getattr(outcomes, "avg_atr_delta", None),
                "avg_adx_delta":                       getattr(outcomes, "avg_adx_delta", None),
                "early_candidate_rate":                getattr(outcomes, "early_candidate_rate", None),

                # Fix 6 — v6 bucket-aware edge quality (from EdgeDetector)
                "bucket_edge_quality":  getattr(edge, "bucket_edge_quality", None),
            },
            layer_3_result=execution_plan,
            reasoning=edge.rationale if edge.has_edge else (
                "Statistical support promoted for downstream options review"
                if statistical_has_edge else "Statistical context only"
            ),
            execution_plan=execution_plan,
        )
