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
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime

# Canonical enum strings — prevents drift vs fusion/precor modules
from enums_structural import ControlState


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
        
        # Force event selection
        if event_scores:
            dominant_event = max(event_scores, key=event_scores.get)
            event_evidence_strength = event_scores[dominant_event]
            event_confidence = self._calculate_event_confidence(event_scores, dominant_event)
        else:
            dominant_event = "TR"  # Trading Range default
            event_evidence_strength = 40
            event_confidence = 70
        
        # Transition analysis
        transition = self._analyze_transition(phase_scores, current_phase, features)
        
        # Regime conflicts (flags — fusion decides whether to veto, not this engine)
        conflicts = self._check_regime_conflicts(trend_context, control, current_phase, features)
        
        # --- Contradictions (truthfulness layer) ----------------------------
        contradictions = self._build_contradictions(
            phase_scores, current_phase, phase_evidence_strength,
            event_evidence_strength, control, features
        )

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
            
            # Regime conflicts (flags — macro_micro_block is a flag, NOT a hard veto)
            "regime_conflicts":        conflicts,
            "macro_micro_block":       len(conflicts) > 0,

            "warnings":                warnings,
            "timestamp":               datetime.now().isoformat()
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
        
        # Range boundaries
        features['range_high'] = df['high'].max()
        features['range_low'] = df['low'].min()
        features['range_width'] = features['range_high'] - features['range_low']
        features['range_width_pct'] = features['range_width'] / df['close'].mean()
        
        # Boundary touches
        recent_20 = df.tail(20)
        features['high_touches'] = sum(recent_20['high'] >= features['range_high'] * 0.98)
        features['low_touches'] = sum(recent_20['low'] <= features['range_low'] * 1.02)
        
        # Break/reclaim counts
        features['break_count'] = 0
        features['reclaim_count'] = 0
        for i in range(len(df) - 10, len(df)):
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
                scores['Spring'] = 55
                scores['UTAD'] = 55
        
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
            "regime_conflicts": [f"Insufficient bars (need {self.min_bars})"],
            "macro_micro_block": True,
            "warnings": [f"Need {self.min_bars} bars minimum"],
            "timestamp": datetime.now().isoformat()
        }
    
    def _error(self, ticker: str, msg: str) -> Dict:
        """Error - still force outputs"""
        return self._insufficient_data(ticker)
