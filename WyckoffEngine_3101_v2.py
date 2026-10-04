"""
AVSHUNTER WyckoffEngine_3101 v2.1 - TRUTHFUL OUTPUT ARCHITECTURE
================================================================================
Fixes applied (2026-03):

FIX 1 — Confidence floors removed.
  Old: phase_confidence and event_confidence were always ≥ 70, masking weak
       evidence. Now: honest 0–100 derived from evidence separation.
  Impact: Downstream fusion can now distinguish clean vs noisy setups.

FIX 2 — Control state enum normalised to canonical set.
  Old: emitted BUYERS_IN_CONTROL / SELLERS_IN_CONTROL / CONTROL_SHIFTING
       which silently failed string comparisons in fusion/precor (expected
       BUYERS / SELLERS / SHIFTING).
  Now: emits BUYERS / SELLERS / EQUILIBRIUM / SHIFTING everywhere.
  Impact: Eliminates silent direction=NONE on valid buyer-controlled setups.

FIX 3 — truth_confidence and contradictions added to output.
  Old: no contradictions field, no honest uncertainty signal.
  Now: truth_confidence = f(evidence_strength, contradiction_count),
       contradictions = list[str] passed to fusion for alignment scoring.

FIX 4 — macro_micro_block clarified (ambiguous veto vs flag).
  Old: any conflict set macro_micro_block=True, implying hard veto even
       though comments said "flags not vetoes".
  Now: macro_micro_block remains as a flag (True = conflicts present),
       but its meaning is documented. Fusion decides whether to veto.

Original architecture retained:
- ALWAYS outputs current_phase ∈ {A, B, C, D, E, UNKNOWN}
- phase_evidence_strength (0-100) — truth metric for execution gates
- No Phase B prerequisite for Phase C/D/E
- Scoring-based, not gating-based
================================================================================
"""

import pandas as pd
import numpy as np
import json
import math
from pathlib import Path
from typing import Dict, List, Mapping, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime

# Canonical enum strings — prevents drift vs fusion/precor modules
from enums_structural import ControlState


def range_break(
    bars: pd.DataFrame,
    prior_range: Mapping[str, float],
    side: str,
    policy: Mapping[str, object],
) -> Dict[str, int]:
    """Count side-specific range breaks and next-bar fail-backs symmetrically.

    This is a structural observation, not a direction vote. The caller supplies
    a range fixed before the event bars and a versioned shadow policy.
    """
    if side not in {"BULL", "BEAR"}:
        raise ValueError(f"Invalid structural side: {side!r}")
    try:
        distance = float(policy["break_log_distance"])
        lookback = int(policy["event_lookback_bars"])
        lower = float(prior_range["low"])
        upper = float(prior_range["high"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("Incomplete DIR-002 range-break policy or range") from exc
    if (
        not all(math.isfinite(value) for value in (distance, lower, upper))
        or distance <= 0
        or lookback <= 0
        or lower <= 0
        or upper < lower
    ):
        raise ValueError("Invalid DIR-002 range-break policy or range")
    if not {"high", "low", "close"}.issubset(bars.columns):
        raise ValueError("Range-break bars must include high, low and close")

    boundary = lower * math.exp(-distance) if side == "BULL" else upper * math.exp(distance)
    breaks = 0
    fail_backs = 0
    for index in range(max(0, len(bars) - lookback), len(bars)):
        row = bars.iloc[index]
        high = float(row["high"])
        low = float(row["low"])
        close = float(row["close"])
        if (
            not all(math.isfinite(value) for value in (high, low, close))
            or low <= 0
            or low > high
            or not low <= close <= high
        ):
            raise ValueError("Invalid DIR-002 bar OHLC geometry")
        extreme = float(row["low"] if side == "BULL" else row["high"])
        breached = extreme < boundary if side == "BULL" else extreme > boundary
        if not breached:
            continue
        breaks += 1
        if index + 1 < len(bars):
            next_close = float(bars["close"].iloc[index + 1])
            if not math.isfinite(next_close) or next_close <= 0:
                raise ValueError("Invalid DIR-002 next-bar close")
            failed = next_close > lower if side == "BULL" else next_close < upper
            fail_backs += int(failed)
    return {"break_count": breaks, "fail_back_count": fail_backs}


def phase_c_event_candidate(
    bull_fail_back_count: Optional[int],
    bear_fail_back_count: Optional[int],
) -> str:
    """Describe Phase-C tests by breach location, never by a control vote."""
    if bull_fail_back_count is None or bear_fail_back_count is None:
        return "NOT_EVALUATED"
    if bull_fail_back_count < 0 or bear_fail_back_count < 0:
        raise ValueError("Phase-C fail-back counts cannot be negative")
    if bull_fail_back_count and bear_fail_back_count:
        return "AMBIGUOUS_TEST"
    if bull_fail_back_count:
        return "SPRING_CANDIDATE"
    if bear_fail_back_count:
        return "UTAD_CANDIDATE"
    return "NONE"


def symmetric_control_scores(
    bars: pd.DataFrame,
    bull_fail_back_count: int,
    bear_fail_back_count: int,
    policy: Mapping[str, object],
) -> Dict[str, float]:
    """Compute mirrored, capped C3 control observations without a trade vote.

    Fail-back, failed thrust, absorption and point-of-close location are one
    correlated STRUCTURE family. The returned 0–1 scores describe that family;
    they are not independent probabilities or an approved direction decision.
    """
    try:
        cfg = policy["control"]
        weights = {
            name: float(cfg[name]) for name in (
                "fail_back_weight", "failed_thrust_weight", "absorption_weight",
                "poc_bias_weight", "absorption_volume_ratio_min",
                "absorption_spread_ratio_max", "absorption_poc_high",
                "absorption_poc_low", "average_poc_high", "average_poc_low",
            )
        }
        caps = {name: int(cfg[name]) for name in (
            "fail_back_count_cap", "failed_thrust_count_cap", "absorption_count_cap",
        )}
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("Incomplete DIR-002 control policy") from exc
    if (
        not all(math.isfinite(v) and v >= 0 for v in weights.values())
        or not all(v > 0 for v in caps.values())
        or not 0 < weights["absorption_poc_low"] < 0.5 < weights["absorption_poc_high"] < 1
        or not 0 < weights["average_poc_low"] < 0.5 < weights["average_poc_high"] < 1
        or not isinstance(bull_fail_back_count, int)
        or not isinstance(bear_fail_back_count, int)
        or min(bull_fail_back_count, bear_fail_back_count) < 0
    ):
        raise ValueError("Invalid DIR-002 control policy or fail-back count")
    required = {"high", "low", "close", "poc", "vol_ratio", "spread_ratio"}
    if len(bars) < 3 or not required.issubset(bars.columns):
        raise ValueError("Incomplete DIR-002 control bars")
    recent = bars.tail(20)
    for row in recent.itertuples(index=False):
        high, low, close = (float(getattr(row, key)) for key in ("high", "low", "close"))
        poc, vol_ratio, spread_ratio = (
            float(getattr(row, key)) for key in ("poc", "vol_ratio", "spread_ratio")
        )
        if (
            not all(math.isfinite(v) for v in (high, low, close, poc, vol_ratio, spread_ratio))
            or low <= 0 or not low <= close <= high
            or not 0 <= poc <= 1 or vol_ratio < 0 or spread_ratio < 0
        ):
            raise ValueError("Invalid DIR-002 control bar")

    upward_failed = downward_failed = 0
    first = max(1, len(bars) - 10)
    for i in range(first, len(bars) - 1):
        close = float(bars["close"].iloc[i])
        if close > float(bars["high"].iloc[i - 1]) and float(bars["close"].iloc[i + 1]) < close:
            upward_failed += 1
        if close < float(bars["low"].iloc[i - 1]) and float(bars["close"].iloc[i + 1]) > close:
            downward_failed += 1

    absorption = recent.loc[
        (recent["vol_ratio"] > weights["absorption_volume_ratio_min"])
        & (recent["spread_ratio"] < weights["absorption_spread_ratio_max"])
    ]
    bull_absorption = int((absorption["poc"] > weights["absorption_poc_high"]).sum())
    bear_absorption = int((absorption["poc"] < weights["absorption_poc_low"]).sum())
    mean_poc = float(recent["poc"].mean())
    maximum = (
        caps["fail_back_count_cap"] * weights["fail_back_weight"]
        + caps["failed_thrust_count_cap"] * weights["failed_thrust_weight"]
        + caps["absorption_count_cap"] * weights["absorption_weight"]
        + weights["poc_bias_weight"]
    )
    if maximum <= 0:
        raise ValueError("DIR-002 control policy has no measurable weight")

    def score(fail_backs: int, failed_thrusts: int, absorption_count: int, poc_bias: bool) -> float:
        points = (
            min(fail_backs, caps["fail_back_count_cap"]) * weights["fail_back_weight"]
            + min(failed_thrusts, caps["failed_thrust_count_cap"]) * weights["failed_thrust_weight"]
            + min(absorption_count, caps["absorption_count_cap"]) * weights["absorption_weight"]
            + int(poc_bias) * weights["poc_bias_weight"]
        )
        return points / maximum

    return {
        "bull_score": score(bull_fail_back_count, downward_failed, bull_absorption,
                            mean_poc > weights["average_poc_high"]),
        "bear_score": score(bear_fail_back_count, upward_failed, bear_absorption,
                            mean_poc < weights["average_poc_low"]),
        "upward_failed_thrust_count": upward_failed,
        "downward_failed_thrust_count": downward_failed,
        "policy_version": str(policy["version"]),
    }


@dataclass
class WyckoffOutput:
    """Complete Wyckoff analysis output"""
    ticker: str
    
    # Phase (UNKNOWN allowed when evidence is genuinely weak)
    current_phase: str  # A/B/C/D/E/UNKNOWN
    phase_confidence: float       # 0–100 honest (no floor)
    phase_evidence_strength: float  # 0-100 (truth)
    
    dominant_event: str  # TR used as default, NEVER forced
    event_confidence: float       # 0–100 honest (no floor)
    event_evidence_strength: float  # 0-100 (truth)
    
    # Control — canonical enum: BUYERS/SELLERS/EQUILIBRIUM/SHIFTING
    control_state: str
    control_confidence: float
    
    # Transition
    transition_bias: str
    transition_confidence: float
    phase_progression: str
    
    # Trade setup
    trade_direction: str  # LONG/SHORT/NONE
    setup_quality: str    # Grade_A/B/C/Observe
    wyckoff_score: float
    execution_bias: str   # BULLISH/BEARISH/OBSERVE_ONLY
    
    # Levels
    entry_trigger: str
    stop_loss: Optional[float]
    initial_target: Optional[float]
    
    # Truthfulness fields (NEW — required by fusion)
    truth_confidence: float   # 0–100, derived from evidence + contradictions
    contradictions: List[str] # reasons to doubt phase/operator
    
    # Regime conflicts (flags — fusion decides whether to veto)
    regime_conflicts: List[str]
    macro_micro_block: bool   # True = conflicts present (FLAG, not hard veto)
    
    # Metadata
    warnings: List[str]
    timestamp: str


class WyckoffEngine_3101_v2:
    """
    Truthful Wyckoff engine — v2.1
    Detect broadly, execute narrowly.
    Confidence is earned from evidence separation, never forced.
    """
    
    def __init__(self, min_bars: int = 20):  # Lowered for CSV data
        self.min_bars = min_bars

        # DIR-002 side-evidence kernel policy (versioned config; fails closed).
        try:
            self._side_policy = load_side_evidence_policy()
        except (OSError, ValueError):
            self._side_policy = None

        # Event thresholds (relaxed for detection)
        self.climax_volume_mult = 1.8
        self.climax_spread_mult = 1.4
        self.spring_depth_max = 0.12
        
    def analyze(self, ticker: str, bars: pd.DataFrame, trend_context: str = "UNKNOWN") -> Dict:
        """
        Main analysis - ALWAYS returns complete output
        """
        
        if bars is None or len(bars) < self.min_bars:
            return self._insufficient_data(ticker)
        
        # Prepare
        df = self._prepare_dataframe(bars.copy())
        if df is None:
            return self._error(ticker, "Data preparation failed")
        
        # Extract features
        features = self._extract_features(df)
        features.update(self._side_evidence_fields(bars))
        
        # Control state
        control = self._determine_control(df, features)
        
        # Score all phases (independent scoring)
        phase_scores = {
            'A': self._score_phase_a(df, features, trend_context),
            'B': self._score_phase_b(df, features),
            'C': self._score_phase_c(df, features),
            'D': self._score_phase_d(df, features),
            'E': self._score_phase_e(df, features)
        }
        
        # FIX-09: If evidence is genuinely weak, emit UNKNOWN rather than forcing a phase.
        # This prevents false confidence feeding fusion/verdict.
        UNKNOWN_THRESHOLD = 40.0
        best_phase = max(phase_scores, key=phase_scores.get)
        best_score = phase_scores[best_phase]
        second_best = sorted(phase_scores.values(), reverse=True)[1] if len(phase_scores) > 1 else 0
        separation = best_score - second_best

        if best_score < UNKNOWN_THRESHOLD or separation < 10:
            # All phases score similarly or all score low — genuine ambiguity
            current_phase = "UNKNOWN"
            phase_evidence_strength = best_score  # honest — still record what we saw
        else:
            current_phase = best_phase
            phase_evidence_strength = best_score

        # Momentum override: strong 20d ROC + price above EMA50 → re-classify C/D as B.
        # Phase C (Spring/test of support) and Phase D (early markup) can be mis-classified
        # during high-momentum trending conditions; force Phase B (re-accumulation) instead.
        _momentum_override_note = ""
        if current_phase in {'C', 'D'} and len(df) >= 21:
            try:
                _close = df['close']
                _roc_20 = float((_close.iloc[-1] - _close.iloc[-21]) / _close.iloc[-21] * 100.0)
                _ema50 = float(_close.ewm(span=50, adjust=False).mean().iloc[-1])
                if _roc_20 > 30.0 and float(_close.iloc[-1]) > _ema50:
                    _momentum_override_note = (
                        f"Momentum override: 20d ROC {_roc_20:.1f}% > 30%% and price above EMA50 "
                        f"— re-classified Phase {current_phase}→B (re-accumulation)"
                    )
                    current_phase = 'B'
            except Exception:
                pass

        phase_confidence = self._calculate_phase_confidence(phase_scores, current_phase)
        
        # Score events within phase context
        event_scores = self._score_events(df, features, current_phase, control)
        
        # Event selection. Empty evidence stays low-confidence; do not force a
        # credible-looking TR event when no event actually scored.
        if event_scores:
            dominant_event = max(event_scores, key=event_scores.get)
            event_evidence_strength = event_scores[dominant_event]
            event_confidence = self._calculate_event_confidence(event_scores, dominant_event)
        else:
            dominant_event = "TR"  # Trading Range default
            event_evidence_strength = 0
            event_confidence = 30
        
        # Transition analysis
        transition = self._analyze_transition(phase_scores, current_phase, features)
        
        # Regime conflicts (flags — fusion decides whether to veto, not this engine)
        conflicts = self._check_regime_conflicts(trend_context, control, current_phase, features)
        
        # --- Contradictions (truthfulness layer) ----------------------------
        contradictions = self._build_contradictions(
            phase_scores, current_phase, phase_evidence_strength,
            event_evidence_strength, control, features
        )
        if _momentum_override_note:
            contradictions.append(_momentum_override_note)

        # truth_confidence: honest composite — penalised by contradictions
        truth_confidence = self._calculate_truth_confidence(
            phase_evidence_strength, event_evidence_strength, contradictions
        )
        
        # Trade direction and quality
        trade_dir, setup_quality = self._determine_trade_setup(
            current_phase, dominant_event, control, phase_evidence_strength, event_evidence_strength
        )
        
        # Execution bias
        exec_bias, exec_conf = self._determine_execution_bias(
            current_phase, dominant_event, control, phase_evidence_strength, 
            event_evidence_strength, conflicts
        )
        
        # Wyckoff composite score
        wyckoff_score = self._calculate_wyckoff_score(
            phase_evidence_strength, event_evidence_strength, control.get('confidence', 50)
        )
        
        # Levels
        entry_trigger, stop, target = self._calculate_levels(
            df, trade_dir, dominant_event, current_phase
        )
        
        # Warnings (include low evidence)
        warnings = []
        if _momentum_override_note:
            warnings.append(_momentum_override_note)
        if phase_evidence_strength < 50:
            warnings.append(f"Phase {current_phase} evidence weak ({phase_evidence_strength:.0f}/100)")
        if event_evidence_strength < 50:
            warnings.append(f"Event {dominant_event} evidence weak ({event_evidence_strength:.0f}/100)")
        if conflicts:
            warnings.extend(conflicts)
        if truth_confidence < 40:
            warnings.append(f"Low truth_confidence ({truth_confidence:.0f}) — treat with caution")
        
        # Infer operator from phase/control for fusion contract
        operator = self._infer_operator(current_phase, control['state'])

        return {
            "ticker": ticker,
            
            # Phase outputs (honest — no floors)
            "current_phase":           current_phase,
            "phase_confidence":        round(phase_confidence, 1),
            "phase_evidence_strength": round(phase_evidence_strength, 1),
            
            # Event outputs (honest — no floors)
            "dominant_event":          dominant_event,
            "event_confidence":        round(event_confidence, 1),
            "event_evidence_strength": round(event_evidence_strength, 1),
            
            # Control — CANONICAL ENUMS (BUYERS/SELLERS/EQUILIBRIUM/SHIFTING)
            "control_state":           control['state'],   # already normalised below
            "control_confidence":      round(control['confidence'], 1),
            
            # Truthfulness fields (NEW — consumed by fusion)
            "truth_confidence":        round(truth_confidence, 1),
            "contradictions":          contradictions,
            "operator":                operator,
            
            # Transition
            "transition_bias":         transition['next_phase'],
            "transition_confidence":   round(transition['confidence'], 1),
            "phase_progression":       transition['progression'],
            
            # Trade
            "trade_direction":         trade_dir,
            "setup_quality":           setup_quality,
            "wyckoff_score":           round(wyckoff_score, 1),
            "execution_bias":          exec_bias,
            "execution_confidence":    round(exec_conf, 1),
            
            # Levels
            "entry_trigger":           entry_trigger,
            "stop_loss":               stop,
            "initial_target":          target,

            # DIR-002 structural observations; never a direction or gate vote.
            "sym_range_break_authority": "IMPLEMENTED_FOR_REPLICATION",
            "sym_range_break_status": features.get("sym_range_break_status"),
            "sym_range_break_policy_version": features.get("sym_range_break_policy_version"),
            "sym_bull_break_count": features.get("sym_bull_break_count"),
            "sym_bull_fail_back_count": features.get("sym_bull_fail_back_count"),
            "sym_bear_break_count": features.get("sym_bear_break_count"),
            "sym_bear_fail_back_count": features.get("sym_bear_fail_back_count"),
            "sym_phase_c_event_candidate": features.get("sym_phase_c_event_candidate"),
            "sym_control_status": features.get("sym_control_status"),
            "sym_bull_control_score": features.get("sym_bull_control_score"),
            "sym_bear_control_score": features.get("sym_bear_control_score"),
            "sym_upward_failed_thrust_count": features.get("sym_upward_failed_thrust_count"),
            "sym_downward_failed_thrust_count": features.get("sym_downward_failed_thrust_count"),
            "side_evidence":           features.get("side_evidence"),
            
            # Regime conflicts (flags — macro_micro_block is a flag, NOT a hard veto)
            "regime_conflicts":        conflicts,
            "macro_micro_block":       len(conflicts) > 0,

            "warnings":                warnings,
            "timestamp":               datetime.now().isoformat()
        }
    
    def _side_evidence_fields(self, bars: pd.DataFrame) -> Dict:
        """Publish the DIR-002 kernel as namespaced observations (no vote)."""
        if self._side_policy is None:
            evidence = _side_unevaluated("NOT_EVALUATED_POLICY_INVALID", None, len(bars))
        else:
            evidence = side_structural_evidence(bars, self._side_policy)
        evaluated = evidence["status"] == "EVALUATED"
        bull, bear = evidence["bull"], evidence["bear"]
        return {
            "side_evidence": evidence,
            "sym_range_break_status": "AVAILABLE_SHADOW" if evaluated else evidence["status"],
            "sym_range_break_policy_version": evidence["policy_version"],
            "sym_bull_break_count": bull["break_count"],
            "sym_bull_fail_back_count": bull["fail_back_count"],
            "sym_bear_break_count": bear["break_count"],
            "sym_bear_fail_back_count": bear["fail_back_count"],
            "sym_phase_c_event_candidate": evidence["phase_c_event_candidate"],
            "sym_control_status": "AVAILABLE_SHADOW" if evaluated else evidence["status"],
            "sym_bull_control_score": bull["control_score"],
            "sym_bear_control_score": bear["control_score"],
            "sym_upward_failed_thrust_count": bear["failed_thrust_count"],
            "sym_downward_failed_thrust_count": bull["failed_thrust_count"],
        }

    # ==================== DATA PREPARATION ====================
    
    def _prepare_dataframe(self, df: pd.DataFrame) -> Optional[pd.DataFrame]:
        """Prepare with indicators"""
        try:
            df['tr'] = np.maximum(
                df['high'] - df['low'],
                np.maximum(
                    abs(df['high'] - df['close'].shift(1)),
                    abs(df['low'] - df['close'].shift(1))
                )
            )
            
            df['vol_avg'] = df['volume'].rolling(20, min_periods=1).mean()
            df['spread_avg'] = df['tr'].rolling(20, min_periods=1).mean()
            
            df['vol_ratio'] = df['volume'] / df['vol_avg']
            df['spread_ratio'] = df['tr'] / df['spread_avg']
            
            df['poc'] = np.where(
                df['high'] > df['low'],
                (df['close'] - df['low']) / (df['high'] - df['low']),
                0.5
            )
            
            return df
        except:
            return None
    
    def _extract_features(self, df: pd.DataFrame) -> Dict:
        """Extract Wyckoff features"""
        features = {}
        
        event_start = max(1, len(df) - 10)
        # Freeze a local range *before* the first material recent test.
        # The event bar may not set the reference boundary it is tested against.
        anchor_index = len(df) - 1
        for i in range(event_start, len(df)):
            prior = df.iloc[max(0, i - 20):i]
            if len(prior) < 10:
                continue
            prior_high = float(prior['high'].max())
            prior_low = float(prior['low'].min())
            if (float(df['high'].iloc[i]) > prior_high * 1.02 or
                    float(df['low'].iloc[i]) < prior_low * 0.98):
                anchor_index = i
                break
        anchor = df.iloc[max(0, anchor_index - 20):anchor_index]
        features['range_high'] = anchor['high'].max()
        features['range_low'] = anchor['low'].min()
        features['range_anchor_index'] = anchor_index
        features['range_width'] = features['range_high'] - features['range_low']
        features['range_width_pct'] = features['range_width'] / df['close'].mean()
        
        # Boundary touches
        recent_20 = df.tail(20)
        features['high_touches'] = sum(recent_20['high'] >= features['range_high'] * 0.98)
        features['low_touches'] = sum(recent_20['low'] <= features['range_low'] * 1.02)
        
        # Break/reclaim counts
        features['break_count'] = 0
        features['reclaim_count'] = 0
        for i in range(event_start, len(df)):
            if i < 1:
                continue
            if df['low'].iloc[i] < features['range_low'] * 0.98:
                features['break_count'] += 1
                if i < len(df) - 1 and df['close'].iloc[i+1] > features['range_low']:
                    features['reclaim_count'] += 1


        # Follow-through fail rate
        ft_fails = 0
        ft_attempts = 0
        for i in range(len(df) - 10, len(df) - 1):
            if df['close'].iloc[i] > df['high'].iloc[i-1]:  # Up breakout
                ft_attempts += 1
                if df['close'].iloc[i+1] < df['close'].iloc[i]:
                    ft_fails += 1
        features['follow_through_fail_rate'] = ft_fails / max(ft_attempts, 1)
        
        # EVR clusters
        recent = df.tail(20)
        high_vol_low_progress = sum(
            (recent['vol_ratio'] > 1.5) & (recent['spread_ratio'] < 0.8)
        )
        features['absorption_count'] = high_vol_low_progress
        
        # Thrust shortening (SOT)
        early_spread = df.tail(20).head(10)['tr'].mean()
        late_spread = df.tail(10)['tr'].mean()
        features['sot_ratio'] = late_spread / max(early_spread, 0.001)
        
        return features
    
    # ==================== CONTROL DETERMINATION ====================
    
    def _determine_control(self, df: pd.DataFrame, features: Dict) -> Dict:
        """Determine control state"""
        recent = df.tail(20)
        
        buyer_score = 0
        seller_score = 0
        
        # Absorption evidence
        if features.get('absorption_count', 0) > 2:
            for _, row in recent.iterrows():
                if row['vol_ratio'] > 1.5 and row['spread_ratio'] < 0.8:
                    if row['poc'] > 0.7:
                        buyer_score += 2
                    elif row['poc'] < 0.3:
                        seller_score += 2
        
        # Failed breakdowns/breakouts
        if features.get('reclaim_count', 0) > 0:
            buyer_score += features['reclaim_count'] * 3
        
        # Follow-through fails
        if features.get('follow_through_fail_rate', 0) > 0.5:
            seller_score += 2
        
        # POC bias
        avg_poc = recent['poc'].mean()
        if avg_poc > 0.65:
            buyer_score += 1
        elif avg_poc < 0.35:
            seller_score += 1
        
        diff = buyer_score - seller_score
        
        # FIX: emit CANONICAL enum values (BUYERS/SELLERS/EQUILIBRIUM/SHIFTING)
        # Old code emitted BUYERS_IN_CONTROL etc which silently failed downstream comparisons
        if diff > 3:
            state = ControlState.BUYERS       # was "BUYERS_IN_CONTROL"
            conf = min(85, 60 + diff * 3)
        elif diff < -3:
            state = ControlState.SELLERS      # was "SELLERS_IN_CONTROL"
            conf = min(85, 60 + abs(diff) * 3)
        elif abs(diff) <= 1:
            state = ControlState.EQUILIBRIUM
            conf = 65
        else:
            state = ControlState.SHIFTING     # was "CONTROL_SHIFTING"
            conf = 50
        
        return {'state': state, 'confidence': conf}
    
    # ==================== PHASE SCORING (INDEPENDENT) ====================
    
    def _score_phase_a(self, df: pd.DataFrame, features: Dict, trend_context: str) -> float:
        """Score Phase A - Stopping action"""
        score = 0
        
        # Climax evidence
        recent = df.tail(20)
        max_vol_ratio = recent['vol_ratio'].max()
        max_spread_ratio = recent['spread_ratio'].max()
        
        if max_vol_ratio > 2.0 and max_spread_ratio > 1.5:
            score += 40
        elif max_vol_ratio > 1.5 and max_spread_ratio > 1.2:
            score += 25
        
        # SOT shortening
        if features.get('sot_ratio', 1.0) < 0.75:
            score += 30
        
        # Trend reversal hint
        if trend_context in ["DOWN", "UP"]:
            score += 15
        
        return min(100, score)
    
    def _score_phase_b(self, df: pd.DataFrame, features: Dict) -> float:
        """Score Phase B - Range/cause building (NO PHASE A PREREQUISITE)"""
        score = 0
        
        # Range formation (stronger check)
        range_width_pct = features.get('range_width_pct', 0)
        if range_width_pct > 0.10:  # Wider range
            score += 25
        elif range_width_pct > 0.05:
            score += 15
        elif range_width_pct > 0.02:
            score += 5
        
        # Oscillations (key Phase B indicator)
        high_touches = features.get('high_touches', 0)
        low_touches = features.get('low_touches', 0)
        
        # Strong Phase B = multiple tests of both boundaries
        if high_touches >= 3 and low_touches >= 3:
            score += 50  # Strong range
        elif high_touches >= 2 and low_touches >= 2:
            score += 35  # Good range
        elif high_touches >= 1 and low_touches >= 1:
            score += 20  # Weak range
        elif high_touches == 0 or low_touches == 0:
            score -= 10  # One-sided = weak Phase B
        
        # Absorption (EVR patterns)
        absorption = features.get('absorption_count', 0)
        if absorption > 3:
            score += 25
        elif absorption > 1:
            score += 15
        elif absorption > 0:
            score += 10
        
        # Time in range (more time = more cause)
        if len(df) >= 60:
            score += 15
        elif len(df) >= 40:
            score += 10
        elif len(df) >= 20:
            score += 5
        
        # Penalty for too tight range (not really Phase B)
        if range_width_pct < 0.015:
            score -= 20  # Too tight
        
        return max(0, min(100, score))
    
    def _score_phase_c(self, df: pd.DataFrame, features: Dict) -> float:
        """Score Phase C - Test/Spring/UTAD"""
        score = 0
        
        # Spring/UTAD evidence (break + reclaim)
        break_count = features.get('break_count', 0)
        reclaim_count = features.get('reclaim_count', 0)
        
        if break_count > 0 and reclaim_count > 0:
            score += 60  # Classic spring/UTAD
        elif break_count > 0:
            score += 30  # Breakout without reclaim
        
        # Follow-through fails (key Phase C behavior)
        ft_fail_rate = features.get('follow_through_fail_rate', 0)
        if ft_fail_rate > 0.7:  # Most breakouts fail
            score += 35  # Strong Phase C
        elif ft_fail_rate > 0.5:
            score += 25  # Moderate Phase C
        elif ft_fail_rate > 0.3:
            score += 15  # Weak Phase C
        
        # Recent test behavior (narrow range after volatility)
        recent_5 = df.tail(5)
        if len(recent_5) >= 5:
            narrow_bars = sum(recent_5['spread_ratio'] < 0.7)
            if narrow_bars >= 3:
                score += 20  # Testing behavior
            elif narrow_bars >= 2:
                score += 10
        
        return min(100, score)
    
    def _score_phase_d(self, df: pd.DataFrame, features: Dict) -> float:
        """Score Phase D - Trend emerges"""
        score = 0
        
        # Escape from range (key Phase D indicator)
        current_price = df['close'].iloc[-1]
        range_high = features.get('range_high', current_price)
        range_low = features.get('range_low', current_price)
        range_width = range_high - range_low
        
        # Strong breakout above range
        if current_price > range_high * 1.05:  # 5% above range
            score += 60
        elif current_price > range_high * 1.03:  # 3% above
            score += 45
        elif current_price > range_high * 1.01:  # 1% above
            score += 30
        
        # Or breakdown below range  
        if current_price < range_low * 0.95:  # 5% below range
            score += 60
        elif current_price < range_low * 0.97:  # 3% below
            score += 45
        elif current_price < range_low * 0.99:  # 1% below
            score += 30
        
        # Momentum building (SOT expanding)
        sot_ratio = features.get('sot_ratio', 1.0)
        if sot_ratio > 1.3:  # Strong expansion
            score += 30
        elif sot_ratio > 1.1:  # Moderate expansion
            score += 20
        
        # Trend structure (directional movement)
        recent_10 = df.tail(10)
        if len(recent_10) >= 10:
            # Check for sustained direction
            closes = recent_10['close'].values
            if all(closes[i] >= closes[i-1] for i in range(1, len(closes))):
                score += 25  # Perfect uptrend
            elif sum(closes[i] > closes[i-1] for i in range(1, len(closes))) >= 7:
                score += 15  # Mostly up
            elif all(closes[i] <= closes[i-1] for i in range(1, len(closes))):
                score += 25  # Perfect downtrend
            elif sum(closes[i] < closes[i-1] for i in range(1, len(closes))) >= 7:
                score += 15  # Mostly down
        
        return min(100, score)
    
    def _score_phase_e(self, df: pd.DataFrame, features: Dict) -> float:
        """Score Phase E - Campaign/trend continuation"""
        score = 0
        
        # Sustained move
        current = df['close'].iloc[-1]
        earlier_20 = df.tail(30).head(10)['close'].mean()
        
        move_pct = abs((current - earlier_20) / earlier_20)
        if move_pct > 0.15:
            score += 50
        elif move_pct > 0.10:
            score += 30
        
        # Trend maturity
        if len(df) >= 40:
            score += 20
        
        return min(100, score)
    
    # ==================== EVENT SCORING ====================
    
    def _score_events(self, df: pd.DataFrame, features: Dict, phase: str, control: Dict) -> Dict:
        """Score events within phase context"""
        event_scores = {}
        
        # Phase-appropriate events
        if phase == 'A':
            event_scores.update(self._score_phase_a_events(df, features))
        elif phase == 'B':
            event_scores.update(self._score_phase_b_events(df, features))
        elif phase == 'C':
            event_scores.update(self._score_phase_c_events(df, features, control))
        elif phase == 'D':
            event_scores.update(self._score_phase_d_events(df, features, control))
        elif phase == 'E':
            event_scores.update(self._score_phase_e_events(df, features))
        
        # Always include TR as fallback
        if not event_scores:
            event_scores['TR'] = 40
        
        return event_scores
    
    def _score_phase_a_events(self, df: pd.DataFrame, features: Dict) -> Dict:
        """Phase A events: SC, BC, PS, PSY, AR"""
        scores = {}
        
        recent = df.tail(20)
        max_vol_ratio = recent['vol_ratio'].max()
        max_spread_ratio = recent['spread_ratio'].max()
        
        # Look for climax
        climax_idx = recent['vol_ratio'].idxmax()
        climax_row = df.loc[climax_idx]
        
        if max_vol_ratio > 1.8 and max_spread_ratio > 1.4:
            if climax_row['close'] < climax_row['open']:  # Down bar
                scores['SC'] = 70
                scores['PS'] = 50
            else:  # Up bar
                scores['BC'] = 70
                scores['PSY'] = 50
            
            # AR (reaction)
            if climax_idx < len(df) - 3:
                next_bars = df.iloc[climax_idx+1:climax_idx+4]
                if climax_row['close'] < climax_row['open'] and next_bars['close'].max() > climax_row['close'] * 1.02:
                    scores['AR'] = 65
                elif climax_row['close'] > climax_row['open'] and next_bars['close'].min() < climax_row['close'] * 0.98:
                    scores['AR'] = 65
        
        return scores
    
    def _score_phase_b_events(self, df: pd.DataFrame, features: Dict) -> Dict:
        """Phase B events: TR, ST, Test, Absorption"""
        scores = {}
        
        # Secondary Test (PRIORITY over TR)
        recent_10 = df.tail(10)
        low_vol_bars = (recent_10['vol_ratio'] < 0.8).sum()
        
        if low_vol_bars >= 4:  # Multiple low volume tests
            scores['ST'] = 75
            scores['Test'] = 70
        elif low_vol_bars >= 3:
            scores['ST'] = 65
            scores['Test'] = 60
        elif low_vol_bars >= 2:
            scores['ST'] = 55
            scores['Test'] = 50
        
        # Absorption (PRIORITY over TR)
        absorption = features.get('absorption_count', 0)
        if absorption > 3:
            scores['Absorption_Up'] = 70
            scores['Absorption_Down'] = 70
        elif absorption > 1:
            scores['Absorption_Up'] = 60
            scores['Absorption_Down'] = 60
        elif absorption > 0:
            scores['Absorption_Up'] = 50
            scores['Absorption_Down'] = 50
        
        # Trading Range (LOWER PRIORITY - only if nothing else detected)
        high_touches = features.get('high_touches', 0)
        low_touches = features.get('low_touches', 0)
        
        if high_touches >= 3 and low_touches >= 3:
            scores['TR'] = 65  # Strong range
        elif high_touches >= 2 and low_touches >= 2:
            scores['TR'] = 55  # Good range
        elif high_touches >= 1 and low_touches >= 1:
            scores['TR'] = 45  # Weak range (won't beat ST/Absorption)
        
        return scores
    
    def _score_phase_c_events(self, df: pd.DataFrame, features: Dict, control: Dict) -> Dict:
        """Phase C events: Spring, UTAD, Test"""
        scores = {}
        
        if features.get('break_count', 0) > 0:
            # FIX: use canonical ControlState enums (was BUYERS_IN_CONTROL)
            if control['state'] == ControlState.BUYERS:
                scores['Spring'] = 75
                scores['Test'] = 60
            elif control['state'] == ControlState.SELLERS:
                scores['UTAD'] = 75
                scores['UT'] = 60
            else:
                # EQUILIBRIUM/SHIFTING is structurally ambiguous in Phase C.
                # Keep both candidates below actionable strength instead of
                # creating a directional coin flip.
                scores['Spring'] = 45
                scores['UTAD'] = 45
        
        return scores
    
    def _score_phase_d_events(self, df: pd.DataFrame, features: Dict, control: Dict) -> Dict:
        """Phase D events: SOS, SOW, LPS, LPSY"""
        scores = {}
        
        current = df['close'].iloc[-1]
        range_high = features.get('range_high', current)
        range_low = features.get('range_low', current)
        
        if current > range_high * 1.02:
            scores['SOS'] = 70
            scores['LPS'] = 50
        elif current < range_low * 0.98:
            scores['SOW'] = 70
            scores['LPSY'] = 50
        
        return scores
    
    def _score_phase_e_events(self, df: pd.DataFrame, features: Dict) -> Dict:
        """Phase E events: Continuation, LPS/LPSY"""
        scores = {}
        
        scores['Trend_Continuation'] = 60
        scores['LPS'] = 45
        scores['LPSY'] = 45
        
        return scores
    
    # ==================== CONFIDENCE CALCULATIONS ====================
    
    def _calculate_phase_confidence(self, scores: Dict, chosen_phase: str) -> float:
        """
        Calculate honest phase confidence (0–100, no forced floor).

        FIX: Old version forced ≥70 always, masking genuinely weak readings.
        Now: confidence scales from separation between chosen and next-best.
        Low separation → low confidence (honestly reflects ambiguity).

        FIX-09 extension: when chosen_phase is UNKNOWN (emitted when evidence
        is too weak to commit to a phase), confidence is derived from the best
        raw score seen — we know nothing clearly, so confidence is low.
        """
        if chosen_phase == "UNKNOWN" or chosen_phase not in scores:
            # UNKNOWN = all phases ambiguous; report confidence proportional to
            # best raw score seen, capped at 35 (we explicitly refused to commit)
            best_raw = max(scores.values()) if scores else 0.0
            return round(min(35.0, best_raw * 0.5), 1)

        chosen_score = scores[chosen_phase]
        other_scores = [s for p, s in scores.items() if p != chosen_phase]

        if not other_scores:
            # Only one phase — confidence = evidence strength, capped at 80
            return min(80.0, chosen_score)

        max_other = max(other_scores)
        separation = chosen_score - max_other

        # Honest scale: 0 separation = 35 confidence, 50 separation = 85 confidence
        # (35 baseline represents "we had to pick something from weak evidence")
        confidence = 35.0 + min(50.0, max(0.0, separation * 1.0))
        return round(confidence, 1)
    
    def _calculate_event_confidence(self, scores: Dict, chosen_event: str) -> float:
        """
        Calculate honest event confidence (0–100, no forced floor).
        
        FIX: Same as phase — old version forced ≥70, now honest.
        """
        chosen_score = scores[chosen_event]
        other_scores = [s for e, s in scores.items() if e != chosen_event]
        
        if not other_scores:
            return min(80.0, chosen_score)
        
        max_other = max(other_scores)
        separation = chosen_score - max_other
        
        confidence = 35.0 + min(50.0, max(0.0, separation * 1.0))
        return round(confidence, 1)
    
    # ==================== TRANSITION ANALYSIS ====================
    
    def _analyze_transition(self, phase_scores: Dict, current_phase: str, features: Dict) -> Dict:
        """Analyze transition to next phase (honest confidence)"""
        
        phase_sequence = ['A', 'B', 'C', 'D', 'E']
        current_idx = phase_sequence.index(current_phase) if current_phase in phase_sequence else -1
        
        if current_idx < 0:
            # UNKNOWN phase: find which scored phase is leading to give a directional hint
            if phase_scores:
                best_hint = max(phase_scores, key=phase_scores.get)
                return {'next_phase': best_hint, 'confidence': 25.0, 'progression': 'ambiguous'}
            return {'next_phase': 'UNKNOWN', 'confidence': 20.0, 'progression': 'ambiguous'}
        
        # Check scores of adjacent phases
        if current_idx < len(phase_sequence) - 1:
            next_phase = phase_sequence[current_idx + 1]
            next_score = phase_scores.get(next_phase, 0)
            current_score = phase_scores.get(current_phase, 0)
            
            if next_score > current_score * 0.80:
                progression = "towards_next"
                bias = next_phase
                # FIX: honest confidence — not floored at 70
                conf = 45.0 + max(0.0, next_score - current_score) * 0.5
            else:
                progression = "stable"
                bias = current_phase
                conf = 55.0  # stable = moderate confidence (was forced 75)
        else:
            progression = "stable"
            bias = current_phase
            conf = 55.0
        
        return {
            'next_phase': bias,
            'confidence': round(min(90.0, conf), 1),
            'progression': progression
        }
    
    # ==================== REGIME CONFLICTS (FLAGS — fusion decides veto) ====================
    
    def _check_regime_conflicts(self, trend_context: str, control: Dict, 
                                phase: str, features: Dict) -> List[str]:
        """
        Check for regime conflicts.
        These are FLAGS for fusion to consume — this engine never vetoes on them.
        FIX: use canonical ControlState enums (was BUYERS_IN_CONTROL etc)
        """
        conflicts = []
        
        # Macro vs micro
        # FIX: canonical enum strings (BUYERS, SELLERS — not BUYERS_IN_CONTROL)
        if trend_context == "UP" and control['state'] == ControlState.SELLERS:
            conflicts.append("Macro bullish but micro seller-controlled (pullback/distribution)")
        elif trend_context == "DOWN" and control['state'] == ControlState.BUYERS:
            conflicts.append("Macro bearish but micro buyer-controlled (bounce/accumulation)")
        
        # Phase D with contracting momentum
        if phase == 'D' and features.get('sot_ratio', 1.0) < 0.75:
            conflicts.append("Phase D emergence but momentum contracting")
        
        return conflicts
    
    # ==================== TRADE SETUP ====================
    
    def _determine_trade_setup(self, phase: str, event: str, control: Dict,
                               phase_evidence: float, event_evidence: float) -> Tuple[str, str]:
        """Determine trade direction and quality — uses canonical ControlState enums"""
        
        # Direction from event
        long_events = ['Spring', 'SOS', 'LPS', 'Test', 'ST', 'AR']
        short_events = ['UTAD', 'UT', 'SOW', 'LPSY', 'BC']
        
        # FIX: canonical enum strings (was BUYERS_IN_CONTROL)
        if event in long_events and control['state'] in [ControlState.BUYERS, ControlState.EQUILIBRIUM]:
            direction = "LONG"
        elif event in short_events and control['state'] in [ControlState.SELLERS, ControlState.EQUILIBRIUM]:
            direction = "SHORT"
        else:
            direction = "NONE"
        
        # Quality from evidence
        avg_evidence = (phase_evidence + event_evidence) / 2
        if avg_evidence >= 70:
            quality = "Grade_A"
        elif avg_evidence >= 55:
            quality = "Grade_B"
        elif avg_evidence >= 40:
            quality = "Grade_C"
        else:
            quality = "Observe"
        
        return direction, quality
    
    def _determine_execution_bias(self, phase: str, event: str, control: Dict,
                                  phase_evidence: float, event_evidence: float,
                                  conflicts: List[str]) -> Tuple[str, float]:
        """Determine execution bias — conflicts lower confidence, don't veto"""
        
        # Range-edge events require decent Phase evidence
        range_edge_events = ['Spring', 'UTAD', 'UT']
        
        # Phase D gives trend mode
        has_trend = (phase == 'D')
        
        # Check evidence
        avg_evidence = (phase_evidence + event_evidence) / 2
        
        if avg_evidence < 35:
            return "OBSERVE_ONLY", 30
        
        # Range setups need Phase evidence unless in trend mode
        if event in range_edge_events and not has_trend and phase_evidence < 40:
            return "OBSERVE_ONLY", 40
        
        # FIX: canonical enum strings (was BUYERS_IN_CONTROL / SELLERS_IN_CONTROL)
        if control['state'] == ControlState.BUYERS:
            bias = "BULLISH"
            conf = 50.0 + (avg_evidence - 50) * 0.5
        elif control['state'] == ControlState.SELLERS:
            bias = "BEARISH"
            conf = 50.0 + (avg_evidence - 50) * 0.5
        else:
            bias = "OBSERVE_ONLY"
            conf = 40.0
        
        # Conflicts reduce confidence (don't veto — fusion decides)
        if conflicts:
            conf = max(20, conf - 25)
        
        return bias, round(conf, 1)
    
    def _calculate_wyckoff_score(self, phase_ev: float, event_ev: float, control_conf: float) -> float:
        """Calculate composite Wyckoff score"""
        return (phase_ev * 0.35 + event_ev * 0.35 + control_conf * 0.30)

    # ==================== TRUTHFULNESS LAYER (NEW) ====================

    def _build_contradictions(
        self,
        phase_scores: Dict,
        chosen_phase: str,
        phase_evidence: float,
        event_evidence: float,
        control: Dict,
        features: Dict,
    ) -> List[str]:
        """
        Identify reasons to doubt the chosen phase/operator.
        Consumed by fusion for alignment_score penalty.
        """
        contradictions: List[str] = []

        # 1. Weak evidence despite confident phase label
        if phase_evidence < 35:
            contradictions.append(
                f"Phase {chosen_phase} evidence low ({phase_evidence:.0f}/100) — phase may be misclassified"
            )

        # 2. Close competition from adjacent phase
        # Skip this check for UNKNOWN: the phase was already deemed ambiguous — no need
        # to add a redundant contradiction that would always fire (score[UNKNOWN]=0).
        if chosen_phase != "UNKNOWN":
            other_scores = {p: s for p, s in phase_scores.items() if p != chosen_phase}
            if other_scores:
                best_other_phase = max(other_scores, key=other_scores.get)
                best_other_score = other_scores[best_other_phase]
                if best_other_score > phase_scores.get(chosen_phase, 0) * 0.85:
                    contradictions.append(
                        f"Phase {chosen_phase} closely contested by Phase {best_other_phase} "
                        f"({phase_scores.get(chosen_phase, 0):.0f} vs {best_other_score:.0f})"
                    )

        # 3. Weak event evidence
        if event_evidence < 35:
            contradictions.append(
                f"Event evidence weak ({event_evidence:.0f}/100) — primary event uncertain"
            )

        # 4. Control shifting (neither buyer nor seller dominant)
        if control['state'] == ControlState.SHIFTING:
            contradictions.append("Control state SHIFTING — no clear directional bias")

        # 5. Absorption signals absent in Phase B/C (expected)
        if chosen_phase in ('B', 'C') and features.get('absorption_count', 0) == 0:
            contradictions.append(
                f"Phase {chosen_phase} expected absorption signals absent"
            )

        return contradictions

    def _calculate_truth_confidence(
        self,
        phase_evidence: float,
        event_evidence: float,
        contradictions: List[str],
    ) -> float:
        """
        Honest composite confidence incorporating evidence quality and contradictions.
        0–100, no forced floor.
        Replaces the old ≥70 forced floor which hid all uncertainty.
        """
        base = (phase_evidence * 0.6 + event_evidence * 0.4)
        # Each contradiction reduces confidence
        penalty = len(contradictions) * 10.0
        truth = max(0.0, base - penalty)
        return round(min(100.0, truth), 1)

    def _infer_operator(self, phase: str, control_state: str) -> str:
        """
        Infer Wyckoff operator (accumulation/distribution/markup/markdown/unclear)
        from phase and control. Required by fusion's direction logic.
        """
        from enums_structural import Operator
        if phase in ('D', 'E') and control_state == ControlState.BUYERS:
            return Operator.MARKUP
        if phase in ('D', 'E') and control_state == ControlState.SELLERS:
            return Operator.MARKDOWN
        if phase in ('A', 'B', 'C') and control_state == ControlState.BUYERS:
            return Operator.ACCUMULATION
        if phase in ('A', 'B', 'C') and control_state == ControlState.SELLERS:
            return Operator.DISTRIBUTION
        return Operator.UNCLEAR
    
    def _calculate_levels(self, df: pd.DataFrame, direction: str, event: str, phase: str) -> Tuple[str, Optional[float], Optional[float]]:
        """Calculate entry/stop/target"""
        if direction == "NONE":
            return "No entry - observe only", None, None
        
        recent = df.tail(20)
        current = df['close'].iloc[-1]
        
        if direction == "LONG":
            support = recent['low'].min()
            resistance = recent['high'].max()
            stop = support * 0.98
            target = resistance * 1.05
            
            if event == "Spring":
                trigger = "Enter LONG on reclaim above spring low with hold"
            elif event == "SOS":
                trigger = "Enter LONG on SOS breakout confirmation"
            else:
                trigger = "Enter LONG on bullish confirmation"
        else:
            support = recent['low'].min()
            resistance = recent['high'].max()
            stop = resistance * 1.02
            target = support * 0.95
            
            if event == "UTAD":
                trigger = "Enter SHORT on failure below UTAD level"
            elif event == "SOW":
                trigger = "Enter SHORT on SOW breakdown confirmation"
            else:
                trigger = "Enter SHORT on bearish confirmation"
        
        return trigger, stop, target
    
    # ==================== ERROR HANDLERS ====================
    
    def _insufficient_data(self, ticker: str) -> Dict:
        """Minimal bars — return honest low-confidence output (not forced 70s)"""
        return {
            "ticker": ticker,
            "current_phase": "UNKNOWN",          # FIX-09: insufficient data → honest UNKNOWN (was "B")
            "phase_confidence": 25.0,           # FIX: was 70.0 — honest for insufficient data
            "phase_evidence_strength": 20.0,
            "dominant_event": "TR",
            "event_confidence": 25.0,           # FIX: was 70.0
            "event_evidence_strength": 25.0,
            # FIX: canonical enum (was "EQUILIBRIUM" — still correct but explicitly referenced)
            "control_state": ControlState.EQUILIBRIUM,
            "control_confidence": 50.0,
            # NEW: truthfulness fields
            "truth_confidence": 15.0,
            "contradictions": [f"Insufficient bars (need {self.min_bars})"],
            "operator": "UNCLEAR",
            "transition_bias": "B",
            "transition_confidence": 30.0,      # FIX: was 70.0
            "phase_progression": "stable",
            "trade_direction": "NONE",
            "setup_quality": "Observe",
            "wyckoff_score": 20.0,              # FIX: was 30.0 — more honest
            "execution_bias": "OBSERVE_ONLY",
            "execution_confidence": 15.0,
            "entry_trigger": f"Insufficient data ({self.min_bars} bars minimum)",
            "stop_loss": None,
            "initial_target": None,
            "side_evidence": None,
            "regime_conflicts": [f"Insufficient bars (need {self.min_bars})"],
            "macro_micro_block": True,
            "warnings": [f"Need {self.min_bars} bars minimum"],
            "timestamp": datetime.now().isoformat()
        }
    
    def _error(self, ticker: str, msg: str) -> Dict:
        """Error - still force outputs"""
        return self._insufficient_data(ticker)


# =============================================================================
# DIR-002 symmetric side-evidence kernel (§4.2-4.3).
#
# One side-parameterised rule per observation, evaluated in log-price space.
# BEAR evidence is computed by the *same* BULL rule on the negated log series,
# so a log-reflected chart yields exactly the mirrored evidence (R-2a). These
# are C3 structure observations: no side is chosen here, nothing defaults to a
# side, and missing or invalid bars are NOT_EVALUATED, never measured zeros.
# =============================================================================

_SIDE_EVENT_NAMES = {
    "BULL": {"SPRING": "SPRING", "SOS": "SOS", "LPS": "LPS", "SC_TEST": "SC_TEST"},
    "BEAR": {"SPRING": "UTAD", "SOS": "SOW", "LPS": "LPSY", "SC_TEST": "BC_TEST"},
}


def load_side_evidence_policy(path: Optional[Path] = None) -> Dict:
    """Load the versioned DIR-002 structure-kernel policy, failing closed."""
    policy_path = path or Path(__file__).resolve().parent / "config" / "dir002_side_evidence_v1.json"
    policy = json.loads(Path(policy_path).read_text(encoding="utf-8"))
    if policy.get("version") != "dir002_side_evidence_v1" or policy.get(
        "authority_state"
    ) != "IMPLEMENTED_FOR_REPLICATION":
        raise ValueError("DIR-002 side-evidence policy version or authority invalid")
    for section in ("anchor", "control", "events", "intent", "trend"):
        if not isinstance(policy.get(section), dict):
            raise ValueError(f"DIR-002 side-evidence policy section missing: {section}")
    return policy


def side_log_frame(bars: pd.DataFrame) -> Optional[pd.DataFrame]:
    """Log OHLC features that mirror exactly under log reflection.

    Returns None when any bar is missing or geometrically invalid; callers
    publish NOT_EVALUATED rather than a measured value.
    """
    required = ("open", "high", "low", "close", "volume")
    if bars is None or not set(required).issubset(bars.columns):
        return None
    values = bars.loc[:, list(required)].apply(pd.to_numeric, errors="coerce")
    array = values.to_numpy(dtype=float)
    if not np.isfinite(array).all() or (array[:, :4] <= 0).any() or (array[:, 4] < 0).any():
        return None
    o, h, l, c, v = (array[:, i] for i in range(5))
    if (l > np.minimum(o, c)).any() or (h < np.maximum(o, c)).any():
        return None
    lo, lh, ll, lc = np.log(o), np.log(h), np.log(l), np.log(c)
    prev = np.concatenate([[lc[0]], lc[:-1]])
    ltr = np.maximum(lh - ll, np.maximum(np.abs(lh - prev), np.abs(ll - prev)))
    span = lh - ll
    lpoc = np.where(span > 0, (lc - ll) / np.where(span > 0, span, 1.0), 0.5)
    frame = pd.DataFrame({"lo": lo, "lh": lh, "ll": ll, "lc": lc, "ltr": ltr,
                          "lpoc": lpoc, "volume": v})
    vol_mean = frame["volume"].rolling(20, min_periods=1).mean()
    tr_mean = frame["ltr"].rolling(20, min_periods=1).mean()
    frame["vol_ratio"] = np.where(vol_mean > 0, frame["volume"] / vol_mean.where(vol_mean > 0, 1.0), 1.0)
    frame["ltr_ratio"] = np.where(tr_mean > 0, frame["ltr"] / tr_mean.where(tr_mean > 0, 1.0), 1.0)
    return frame


def _side_prior_range(lf: pd.DataFrame, policy: Mapping) -> Tuple[float, float, int]:
    """Prior range frozen before the first material recent test (log units)."""
    anchor_cfg = policy["anchor"]
    window = int(anchor_cfg["range_window_bars"])
    min_prior = int(anchor_cfg["min_prior_bars"])
    k = float(anchor_cfg["anchor_log_distance"])
    lookback = int(policy["event_lookback_bars"])
    lh, ll = lf["lh"].to_numpy(), lf["ll"].to_numpy()
    n = len(lf)
    anchor = n - 1
    for i in range(max(1, n - lookback), n):
        lo_i = max(0, i - window)
        if i - lo_i < min_prior:
            continue
        if lh[i] > lh[lo_i:i].max() + k or ll[i] < ll[lo_i:i].min() - k:
            anchor = i
            break
    lo_a = max(0, anchor - window)
    return float(ll[lo_a:anchor].min()), float(lh[lo_a:anchor].max()), anchor


def _side_arrays(lf: pd.DataFrame, range_low: float, range_high: float, side: str) -> Dict:
    """Express one side's question in BULL orientation (negated logs for BEAR)."""
    if side == "BULL":
        return {
            "high": lf["lh"].to_numpy(), "low": lf["ll"].to_numpy(), "close": lf["lc"].to_numpy(),
            "poc": lf["lpoc"].to_numpy(), "range_low": range_low, "range_high": range_high,
        }
    return {
        "high": -lf["ll"].to_numpy(), "low": -lf["lh"].to_numpy(), "close": -lf["lc"].to_numpy(),
        "poc": 1.0 - lf["lpoc"].to_numpy(), "range_low": -range_high, "range_high": -range_low,
    }


def _side_best_event(lf: pd.DataFrame, arrays: Dict, policy: Mapping) -> Tuple[str, Optional[int], float]:
    """Strongest confirmed BULL-orientation event: (generic type, bar index, strength)."""
    cfg = policy["events"]
    k_break = float(policy["break_log_distance"])
    lookback = int(policy["event_lookback_bars"])
    reclaim = int(cfg["reclaim_within_bars"])
    follow = int(cfg["followthrough_bars"])
    climax_lookback = int(cfg["climax_lookback_bars"])
    base = {name: float(value) for name, value in cfg["base_strength"].items()}
    decay = float(cfg["recency_decay"])
    high, low, close, poc = arrays["high"], arrays["low"], arrays["close"], arrays["poc"]
    lower, upper = arrays["range_low"], arrays["range_high"]
    volume = lf["volume"].to_numpy()
    vol_ratio = lf["vol_ratio"].to_numpy()
    tr_ratio = lf["ltr_ratio"].to_numpy()
    n = len(close)
    start = max(1, n - lookback)
    candidates: List[Tuple[str, int, int]] = []  # (type, event index, window)

    for i in range(start, n):
        if low[i] < lower - k_break:
            for j in range(i + 1, min(n, i + reclaim + 1)):
                if close[j] > lower:
                    candidates.append(("SPRING", i, lookback))
                    break
    sos_bars: List[int] = []
    for i in range(start, n - 1):
        if close[i] > upper + k_break and poc[i] >= float(cfg["breakout_poc_min"]):
            later = close[i + 1:]
            if (later > upper).all() and (close[i + 1:i + 1 + follow] >= close[i]).any():
                candidates.append(("SOS", i, lookback))
                sos_bars.append(i)
    for i in sos_bars:
        for j in range(n - 1, i, -1):
            if low[j] <= upper + float(cfg["retest_log_distance"]) and close[j] > upper:
                candidates.append(("LPS", j, lookback))
                break
    for c in range(max(1, n - climax_lookback), n - 1):
        if (vol_ratio[c] >= float(cfg["climax_volume_ratio_min"])
                and tr_ratio[c] >= float(cfg["climax_range_ratio_min"])
                and close[c] < close[c - 1]
                and poc[c] >= float(cfg["climax_close_off_extreme_poc"])):
            for j in range(n - 1, c + 1, -1):
                if (low[j] >= low[c]
                        and low[j] <= low[c] + float(cfg["test_log_distance"])
                        and volume[j] <= float(cfg["test_volume_fraction_max"]) * volume[c]):
                    candidates.append(("SC_TEST", j, climax_lookback))
                    break

    best: Tuple[str, Optional[int], float] = ("NONE", None, 0.0)
    for name, index, window in candidates:
        age = n - 1 - index
        strength = base[name] * max(0.0, 1.0 - decay * age / float(window))
        if strength > best[2]:
            best = (name, index, strength)
    return best


def _side_trend(lf: pd.DataFrame, policy: Mapping) -> Tuple[str, bool, bool]:
    cfg = policy["trend"]
    spans = [int(span) for span in cfg["spans"]]
    if len(lf) < int(cfg["min_completed_bars"]):
        return "TREND_INSUFFICIENT_HISTORY", False, False
    ema = [float(lf["lc"].ewm(span=span, adjust=False).mean().iloc[-1]) for span in spans]
    bull = all(a > b for a, b in zip(ema, ema[1:]))
    bear = all(a < b for a, b in zip(ema, ema[1:]))
    return "EVALUATED", bull, bear


def _side_unevaluated(status: str, policy_version: Optional[str], bars_count: int) -> Dict:
    empty = {
        "event_type": "NOT_EVALUATED", "event_strength": None, "event_session": "",
        "control_score": None, "break_count": None, "fail_back_count": None,
        "failed_thrust_count": None, "trend_aligned": False,
    }
    return {
        "status": status, "policy_version": policy_version,
        "trend_status": "NOT_EVALUATED", "trend_history_bars": bars_count,
        "range_low": None, "range_high": None, "range_anchor_session": "",
        "phase_c_event_candidate": "NOT_EVALUATED",
        "bull": dict(empty), "bear": dict(empty),
    }


def side_structural_evidence(bars: pd.DataFrame, policy: Mapping) -> Dict:
    """Per-side C3 evidence vectors for DIR-002 assignment (no side chosen)."""
    version = policy.get("version") if isinstance(policy, Mapping) else None
    try:
        window = int(policy["anchor"]["range_window_bars"]) + int(policy["event_lookback_bars"])
    except (KeyError, TypeError, ValueError):
        return _side_unevaluated("NOT_EVALUATED_POLICY_INVALID", version, 0 if bars is None else len(bars))
    count = 0 if bars is None else len(bars)
    if count < window:
        return _side_unevaluated("NOT_EVALUATED_INSUFFICIENT_BARS", version, count)
    lf = side_log_frame(bars)
    if lf is None:
        return _side_unevaluated("NOT_EVALUATED_INVALID_BARS", version, count)
    dates = (
        pd.to_datetime(bars["date"]).dt.strftime("%Y-%m-%d").tolist()
        if "date" in bars.columns else [str(i) for i in range(count)]
    )
    range_low, range_high, anchor = _side_prior_range(lf, policy)
    price_bars = pd.DataFrame({
        "high": np.exp(lf["lh"]), "low": np.exp(lf["ll"]), "close": np.exp(lf["lc"]),
        "poc": lf["lpoc"], "vol_ratio": lf["vol_ratio"], "spread_ratio": lf["ltr_ratio"],
    })
    price_range = {"low": math.exp(range_low), "high": math.exp(range_high)}
    breaks = {side: range_break(price_bars, price_range, side, policy) for side in ("BULL", "BEAR")}
    control = symmetric_control_scores(
        price_bars, breaks["BULL"]["fail_back_count"], breaks["BEAR"]["fail_back_count"], policy
    )
    trend_status, bull_trend, bear_trend = _side_trend(lf, policy)
    result = {
        "status": "EVALUATED",
        "policy_version": version,
        "trend_status": trend_status,
        "trend_history_bars": count,
        "range_low": math.exp(range_low),
        "range_high": math.exp(range_high),
        "range_anchor_session": dates[anchor],
        "phase_c_event_candidate": phase_c_event_candidate(
            breaks["BULL"]["fail_back_count"], breaks["BEAR"]["fail_back_count"]
        ),
    }
    for side, trend_aligned, score_key, thrust_key in (
        ("BULL", bull_trend, "bull_score", "downward_failed_thrust_count"),
        ("BEAR", bear_trend, "bear_score", "upward_failed_thrust_count"),
    ):
        generic, index, strength = _side_best_event(
            lf, _side_arrays(lf, range_low, range_high, side), policy
        )
        result[side.lower()] = {
            "event_type": _SIDE_EVENT_NAMES[side].get(generic, "NONE"),
            "event_strength": float(strength),
            "event_session": dates[index] if index is not None else "",
            "control_score": float(control[score_key]),
            "break_count": int(breaks[side]["break_count"]),
            "fail_back_count": int(breaks[side]["fail_back_count"]),
            "failed_thrust_count": int(control[thrust_key]),
            "trend_aligned": bool(trend_aligned),
        }
    return result
