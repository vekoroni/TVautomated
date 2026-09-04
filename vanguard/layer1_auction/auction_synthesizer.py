"""
VANGUARD Layer 1 - Auction Synthesizer
Combines all auction modules into final verdict

This is the CRITICAL decision point:
- Is market READY to trade?
- If not ready NOW, when MIGHT it be ready?
- Multi-scenario analysis (Aggressive, Moderate, Conservative)
"""

from typing import Dict, List, Optional
import pandas as pd
from ..schemas.auction_schema import (
    AcceptanceState,
    AuctionVerdict,
    ControlState,
    MarketProfile,
    MigrationState,
)
from contracts.market_profile_evidence import MarketProfileEvidence
from ..schemas.input_schema import VanguardInput
from .market_profile import MarketProfileCalculator
from .value_acceptance import ValueAcceptanceDetector
from .control_identifier import ControlIdentifier
from .value_migration import ValueMigrationTracker
from ..config import AUCTION_VERDICT_THRESHOLDS, SCENARIO_PROBABILITIES


class AuctionStateSynthesizer:
    """
    Synthesizes all Layer 1 auction intelligence
    Provides multi-scenario analysis instead of binary GO/NO-GO
    """
    
    def __init__(self):
        self.profile_calc = MarketProfileCalculator()
        self.acceptance_detector = ValueAcceptanceDetector()
        self.control_identifier = ControlIdentifier()
        self.migration_tracker = ValueMigrationTracker()
        self.thresholds = AUCTION_VERDICT_THRESHOLDS
        
    def synthesize(self, vanguard_input: VanguardInput) -> AuctionVerdict:
        """
        Main entry: Run complete auction analysis
        
        Args:
            vanguard_input: Complete input package from Orchestrator
            
        Returns:
            AuctionVerdict with multi-scenario analysis
        """
        
        ticker = vanguard_input.ticker
        current_price = vanguard_input.current_price

        # Governed path: profile evidence is calculated once from canonical
        # intraday bars before Vanguard. Vanguard consumes it; it must not
        # reconstruct an "intraday" profile from daily OHLCV.
        if getattr(vanguard_input, "market_profile_contract_required", False):
            return self._governed_profile_verdict(
                ticker=ticker,
                current_price=current_price,
                raw_evidence=getattr(vanguard_input, "market_profile_evidence", None),
            )
        
        # === RUN ALL AUCTION MODULES ===
        
        # 1. Market Profile - BUILD MULTIPLE SESSIONS
        # Split intraday bars into daily sessions for proper migration tracking
        bars = vanguard_input.technical.ohlcv
        profiles = []
        
        if bars is not None and len(bars) > 0 and 'date' in bars.columns:
            # Split by trading date (date column already exists)
            bars_copy = bars.copy()
            
            # Build one profile per session
            for date, session_bars in bars_copy.groupby('date'):
                session_profile = self.profile_calc.calculate_profile(
                    ticker=ticker,
                    bars=session_bars.reset_index(drop=True),
                    timeframe="intraday"
                )
                profiles.append(session_profile)
            
            # Use most recent profile for current analysis
            profile = profiles[-1] if profiles else self.profile_calc.calculate_profile(
                ticker, bars, "1D"
            )
        else:
            # Fallback: single profile
            profile = self.profile_calc.calculate_profile(
                ticker=ticker,
                bars=bars,
                timeframe="1D"
            )
            profiles = [profile]
        
        # 2. Value Acceptance
        acceptance = self.acceptance_detector.detect_acceptance(
            ticker=ticker,
            current_price=current_price,
            profile=profile,
            volume_profile=vanguard_input.technical.volume_profile,
            recent_bars=vanguard_input.technical.ohlcv,
            time_and_sales=vanguard_input.microstructure.time_and_sales
        )
        
        # 3. Control
        control = self.control_identifier.identify_control(
            ticker=ticker,
            recent_bars=vanguard_input.technical.ohlcv,
            time_and_sales=vanguard_input.microstructure.time_and_sales
        )
        
        # 4. Migration - NOW WORKS WITH MULTIPLE PROFILES!
        migration = self.migration_tracker.track_migration(
            profiles=profiles if len(profiles) >= 2 else [profile],
            lookback_sessions=len(profiles) if len(profiles) >= 2 else 1
        )
        
        # === GENERATE MULTI-SCENARIO ANALYSIS ===
        
        scenarios = self._generate_scenarios(
            current_price, profile, acceptance, control, migration
        )
        
        # === DETERMINE OVERALL VERDICT ===
        
        verdict_result = self._determine_verdict(
            acceptance, control, migration, scenarios
        )
        
        return AuctionVerdict(
            ready_to_trade=verdict_result['ready'],
            confidence=verdict_result['confidence'],
            auction_state=verdict_result['state'],
            profile=profile,
            acceptance=acceptance,
            control=control,
            migration=migration,
            scenarios=scenarios,
            reasoning=verdict_result['reasoning']
        )

    @staticmethod
    def _governed_profile_verdict(*, ticker: str, current_price: float, raw_evidence) -> AuctionVerdict:
        try:
            evidence = MarketProfileEvidence.from_mapping(raw_evidence or {})
        except Exception as error:
            return AuctionStateSynthesizer._not_evaluated(
                ticker, current_price, f"INVALID_GOVERNED_PROFILE:{type(error).__name__}"
            )
        if not evidence.usable:
            return AuctionStateSynthesizer._not_evaluated(
                ticker, current_price, evidence.reason_code or "UNUSABLE_GOVERNED_PROFILE"
            )
        profile = MarketProfile(
            poc=evidence.poc,
            value_area_high=evidence.value_area_high,
            value_area_low=evidence.value_area_low,
            profile_type=evidence.profile_type,
            balance="NOT_EVALUATED",
            tpo_distribution={},
            timestamp=pd.Timestamp(evidence.observed_at_utc),
            timeframe=f"{evidence.interval_minutes}min_{evidence.evidence_state}",
        )
        if current_price < float(evidence.value_area_low):
            position = "BELOW_VALUE"
        elif current_price > float(evidence.value_area_high):
            position = "ABOVE_VALUE"
        else:
            position = "INSIDE_VALUE"
        acceptance = AcceptanceState(
            level=current_price, score=0.0, classification="PROFILE_CONTEXT_ONLY",
            position_in_profile=position,
        )
        control = ControlState(
            controller="NEUTRAL", confidence=0.0,
            interpretation="No governed intraday order-flow/control evidence in completed profile",
        )
        migration = MigrationState(
            direction="UNKNOWN", speed="UNKNOWN", consistency="UNKNOWN", magnitude=0.0,
            interpretation="Single completed profile cannot establish value migration",
        )
        return AuctionVerdict(
            ready_to_trade=False,
            confidence=max(0.0, 1.0 - evidence.uncertainty_score),
            auction_state="PROFILE_CONTEXT_ONLY",
            profile=profile,
            acceptance=acceptance,
            control=control,
            migration=migration,
            scenarios={},
            reasoning=(
                f"Governed {evidence.evidence_state} Market Profile available for {ticker}; "
                "advisory context only and cannot grant readiness or capital."
            ),
        )

    @staticmethod
    def _not_evaluated(ticker: str, current_price: float, reason: str) -> AuctionVerdict:
        return AuctionVerdict(
            ready_to_trade=False,
            confidence=0.0,
            auction_state="NOT_EVALUATED",
            profile=MarketProfile(
                poc=None, value_area_high=None, value_area_low=None,
                profile_type="INSUFFICIENT_DATA", balance="UNKNOWN",
                tpo_distribution={}, timestamp=pd.Timestamp.now(tz="UTC"),
                timeframe="GOVERNED",
            ),
            acceptance=AcceptanceState(
                level=current_price, score=0.0, classification="NOT_EVALUATED",
                position_in_profile="UNKNOWN",
            ),
            control=ControlState(
                controller="NEUTRAL", confidence=0.0,
                interpretation="Market Profile unavailable",
            ),
            migration=MigrationState(
                direction="UNKNOWN", speed="UNKNOWN", consistency="UNKNOWN", magnitude=0.0,
                interpretation="Market Profile unavailable",
            ),
            scenarios={},
            reasoning=f"{ticker} Market Profile NOT_EVALUATED: {reason}",
        )
        
    def _generate_scenarios(self,
                           current_price: float,
                           profile: MarketProfile,
                           acceptance: 'AcceptanceState',
                           control: 'ControlState',
                           migration: 'MigrationState') -> Dict:
        """
        Generate multiple entry scenarios with probability estimates
        
        Returns dict with:
        - immediate: Can we enter NOW?
        - conditional_near: What's the near-term trigger?
        - conditional_far: What's the full confirmation trigger?
        """
        
        scenarios = {}
        
        # === SCENARIO 1: IMMEDIATE (AGGRESSIVE) ===
        scenarios['immediate'] = self._assess_immediate_scenario(
            current_price, acceptance, control, migration
        )
        
        # === SCENARIO 2: CONDITIONAL NEAR (MODERATE) ===
        scenarios['conditional_near'] = self._assess_conditional_near(
            current_price, profile, acceptance, control
        )
        
        # === SCENARIO 3: CONDITIONAL FAR (CONSERVATIVE) ===
        scenarios['conditional_far'] = self._assess_conditional_far(
            current_price, profile, acceptance, control
        )
        
        return scenarios
        
    def _assess_immediate_scenario(self,
                                   current_price: float,
                                   acceptance: 'AcceptanceState',
                                   control: 'ControlState',
                                   migration: 'MigrationState') -> Dict:
        """
        Can we enter RIGHT NOW (aggressive, pre-confirmation)?
        
        Feasible if:
        - Acceptance score >= 40 (not completely rejected)
        - Control not strongly against us
        - Migration not violently opposite
        """
        
        # Base probability for aggressive entry
        base_prob = SCENARIO_PROBABILITIES['aggressive_base_probability']
        prob_boost = SCENARIO_PROBABILITIES['aggressive_probability_boost_per_signal']
        
        probability = base_prob
        quality_score = 0
        risk_factors = []
        
        # Boost probability for supporting signals
        if acceptance.score >= 50:
            probability += prob_boost
            quality_score += 20
        else:
            risk_factors.append(f"Acceptance weak ({acceptance.score:.0f}/100)")
            
        if control.controller in ["BUYERS", "SELLERS"] and control.confidence > 0.60:
            probability += prob_boost
            quality_score += 20
        else:
            risk_factors.append("Control contested")
            
        if migration.direction != "SIDEWAYS" and migration.consistency.startswith("CONSISTENT"):
            probability += prob_boost
            quality_score += 10
            
        # Determine feasibility
        if acceptance.score < 30:
            feasible = False
            quality = "POOR"
        elif acceptance.score >= 50:
            feasible = True
            quality = "MEDIUM" if quality_score >= 30 else "FAIR"
        else:
            feasible = True
            quality = "FAIR"
            
        # Determine risk level
        if len(risk_factors) >= 3:
            risk_level = "VERY_HIGH"
        elif len(risk_factors) >= 2:
            risk_level = "HIGH"
        elif len(risk_factors) == 1:
            risk_level = "MODERATE"
        else:
            risk_level = "LOW"
            
        return {
            'feasible': feasible,
            'quality': quality,
            'risk_level': risk_level,
            'probability_estimate': min(probability, SCENARIO_PROBABILITIES['max_probability']),
            'risk_factors': risk_factors,
            'entry_price': current_price,
            'rationale': f"Immediate entry at ${current_price:.2f}. Quality: {quality}, Risk: {risk_level}."
        }
        
    def _assess_conditional_near(self,
                                current_price: float,
                                profile: MarketProfile,
                                acceptance: 'AcceptanceState',
                                control: 'ControlState') -> Dict:
        """
        What's the near-term trigger (moderate confirmation)?
        
        Typically:
        - VWAP reclaim
        - Value area entry
        - Control shift confirmation
        """
        
        # Identify likely trigger
        triggers = []
        
        # If below VWAP, VWAP reclaim is trigger
        if current_price < profile.poc:  # Using POC as proxy for VWAP
            trigger_price = profile.poc
            triggers.append(f"VWAP/POC reclaim at ${trigger_price:.2f}")
            
        # If below value area, VA entry is trigger
        if acceptance.position_in_profile == "BELOW_VALUE":
            trigger_price = profile.value_area_low
            triggers.append(f"Value Area entry at ${trigger_price:.2f}")
            
        # If control neutral, control shift is trigger
        if control.controller == "NEUTRAL":
            triggers.append("Clear control establishment (buyers or sellers)")
            trigger_price = current_price * 1.01  # Approximate
        else:
            trigger_price = current_price * 1.02
            
        # Base probability
        base_prob = SCENARIO_PROBABILITIES['moderate_base_probability']
        prob_boost = SCENARIO_PROBABILITIES['moderate_probability_boost_per_signal']
        
        probability = base_prob
        
        # Boost for supporting factors
        if acceptance.score >= 40:
            probability += prob_boost
        if control.confidence >= 0.55:
            probability += prob_boost
            
        return {
            'trigger': triggers[0] if triggers else "Structure improvement",
            'all_triggers': triggers,
            'trigger_price': trigger_price if 'trigger_price' in locals() else current_price * 1.02,
            'probability_estimate': min(probability, SCENARIO_PROBABILITIES['max_probability']),
            'rationale': "Wait for partial confirmation before entering"
        }
        
    def _assess_conditional_far(self,
                                current_price: float,
                                profile: MarketProfile,
                                acceptance: 'AcceptanceState',
                                control: 'ControlState') -> Dict:
        """
        What's the full confirmation trigger (conservative)?
        
        Typically:
        - Breakout above resistance
        - Full value area acceptance + control confirmation
        - Clear trend establishment
        """
        
        # Identify conservative trigger (breakout level)
        if profile.value_area_high > 0:
            trigger_price = profile.value_area_high * 1.02  # 2% above value area high
            trigger = f"Breakout above ${trigger_price:.2f} (Value Area High + 2%)"
        else:
            trigger_price = current_price * 1.05
            trigger = f"Breakout above ${trigger_price:.2f} (+5% from current)"
            
        # Base probability (highest for conservative)
        base_prob = SCENARIO_PROBABILITIES['conservative_base_probability']
        prob_boost = SCENARIO_PROBABILITIES['conservative_probability_boost_per_signal']
        
        probability = base_prob
        
        # Boost factors
        if acceptance.score >= 50:
            probability += prob_boost
        if control.confidence >= 0.65:
            probability += prob_boost
            
        return {
            'trigger': trigger,
            'trigger_price': trigger_price,
            'probability_estimate': min(probability, SCENARIO_PROBABILITIES['max_probability']),
            'rationale': "Wait for full confirmation and breakout"
        }
        
    def _determine_verdict(self,
                          acceptance: 'AcceptanceState',
                          control: 'ControlState',
                          migration: 'MigrationState',
                          scenarios: Dict) -> Dict:
        """
        Determine overall auction verdict
        
        NEW LOGIC: Instead of binary READY/NOT READY,
        we assess CURRENT STATE and provide scenario options
        """
        
        # === GATE CHECKS (Still apply, but don't block all scenarios) ===
        
        gates_passed = []
        gates_failed = []
        
        # Gate 1: Acceptance
        if acceptance.classification == "TOLERATED":
            gates_failed.append(
                f"Value TOLERATED (score: {acceptance.score}/100) - market searching, not agreeing"
            )
        else:
            gates_passed.append(f"Value {acceptance.classification}")
            
        # Gate 2: Control
        if control.controller == "NEUTRAL" and control.confidence < self.thresholds['ready_min_control_confidence']:
            gates_failed.append(
                f"Control contested ({control.controller} at {control.confidence:.0%})"
            )
        else:
            gates_passed.append(f"Control: {control.controller} ({control.confidence:.0%})")
            
        # Gate 3: Migration consistency
        if migration.consistency == "CHOPPY" and not self.thresholds['ready_allow_choppy_migration']:
            gates_failed.append("Value migration is choppy and unstable")
        else:
            gates_passed.append(f"Migration: {migration.direction} ({migration.consistency})")
            
        # === DETERMINE STATE ===
        
        if len(gates_failed) == 0:
            # All gates passed
            state = "ALIGNED"
            ready = True
            confidence = min(acceptance.score / 100, control.confidence) * 0.8  # Conservative
            
        elif len(gates_failed) == 1:
            # One gate failed
            state = "TRANSITIONING"
            ready = False  # Not ready for full position, but scenarios viable
            confidence = 0.5
            
        elif len(gates_failed) == 2:
            # Two gates failed
            state = "SEARCHING"
            ready = False
            confidence = 0.3
            
        else:
            # All gates failed
            state = "CONFLICTED"
            ready = False
            confidence = 0.1
            
        # === GENERATE REASONING ===
        
        reasoning_parts = []
        
        reasoning_parts.append(f"AUCTION STATE: {state}")
        reasoning_parts.append("")
        
        if gates_passed:
            reasoning_parts.append("âœ“ Favorable factors:")
            for gate in gates_passed:
                reasoning_parts.append(f"  â€¢ {gate}")
            reasoning_parts.append("")
            
        if gates_failed:
            reasoning_parts.append("âœ— Caution factors:")
            for gate in gates_failed:
                reasoning_parts.append(f"  â€¢ {gate}")
            reasoning_parts.append("")
            
        # Scenario summary
        reasoning_parts.append("SCENARIO ANALYSIS:")
        
        immediate = scenarios['immediate']
        if immediate['feasible']:
            reasoning_parts.append(
                f"  AGGRESSIVE: Feasible NOW (quality: {immediate['quality']}, "
                f"risk: {immediate['risk_level']}, prob: {immediate['probability_estimate']:.0%})"
            )
        else:
            reasoning_parts.append(f"  AGGRESSIVE: Not feasible (quality: {immediate['quality']})")
            
        near = scenarios['conditional_near']
        reasoning_parts.append(
            f"  MODERATE: {near['trigger']} (prob: {near['probability_estimate']:.0%})"
        )
        
        far = scenarios['conditional_far']
        reasoning_parts.append(
            f"  CONSERVATIVE: {far['trigger']} (prob: {far['probability_estimate']:.0%})"
        )
        
        reasoning = "\n".join(reasoning_parts)
        
        return {
            'ready': ready,
            'confidence': confidence,
            'state': state,
            'reasoning': reasoning
        }
