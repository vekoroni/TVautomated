"""
VANGUARD Layer 1 - Value Acceptance Detector
Determines if current price is ACCEPTED or merely TOLERATED

ACCEPTED = Market agrees this is fair value (high volume, time, balanced flow)
TOLERATED = Market is just passing through (low volume, brief, imbalanced)

This is THE critical filter that blocks 80% of trades
"""

import pandas as pd
import numpy as np
from typing import Dict, Optional
from ..schemas.auction_schema import (
    AcceptanceState, VolumeQuality, TimeQuality, 
    FlowBalance, ParticipantQuality, MarketProfile
)
from ..config import ACCEPTANCE_THRESHOLDS


class ValueAcceptanceDetector:
    """
    Detects whether current price is being ACCEPTED or TOLERATED
    
    This answers Peter Steidlmayer's core question:
    "Is price being agreed upon, or is it still searching for value?"
    """
    
    def __init__(self):
        self.thresholds = ACCEPTANCE_THRESHOLDS

    # --- Data integrity helpers (fail-closed) ---
    @staticmethod
    def _has_columns(df: Optional[pd.DataFrame], cols) -> bool:
        if df is None:
            return False
        missing = [c for c in cols if c not in df.columns]
        return len(missing) == 0

    @staticmethod
    def _empty_quality_volume() -> VolumeQuality:
        return VolumeQuality(absolute=0, relative=0, quality="UNKNOWN")

    @staticmethod
    def _empty_quality_time() -> TimeQuality:
        return TimeQuality(bars_at_level=0, quality="UNKNOWN")

    @staticmethod
    def _empty_quality_flow() -> FlowBalance:
        return FlowBalance(buy_volume=0, sell_volume=0, ratio=0.5, quality="UNKNOWN")

    @staticmethod
    def _empty_quality_participants() -> ParticipantQuality:
        return ParticipantQuality(unique_sizes=0, quality="UNKNOWN")
        
    def detect_acceptance(self,
                         ticker: str,
                         current_price: float,
                         profile: MarketProfile,
                         volume_profile: pd.DataFrame,
                         recent_bars: pd.DataFrame,
                         time_and_sales: Optional[pd.DataFrame] = None) -> AcceptanceState:
        """
        Main entry: Determine acceptance state at current price
        
        Args:
            ticker: Stock symbol
            current_price: Current price level to evaluate
            profile: MarketProfile from market_profile.py
            volume_profile: DataFrame with columns [price_level, volume, buys, sells]
            recent_bars: Recent intraday bars (last 4 hours minimum)
            time_and_sales: Optional T&S data for flow analysis
            
        Returns:
            AcceptanceState with score and classification
        """
        
        # Classify position relative to value area
        position = self._classify_position_in_profile(current_price, profile)
        
        # Measure volume at current level
        volume_quality = self._measure_volume_at_price(
            current_price, volume_profile
        )
        
        # Measure time at current level
        time_quality = self._measure_time_at_price(
            current_price, recent_bars
        )
        
        # Measure buy/sell flow balance
        flow_quality = self._measure_flow_balance(
            current_price, recent_bars, time_and_sales
        )
        
        # Measure participant diversity
        participant_quality = self._measure_participant_diversity(
            current_price, time_and_sales
        )
        
        # Calculate aggregate acceptance score
        acceptance_score = self._calculate_acceptance_score(
            position, volume_quality, time_quality, 
            flow_quality, participant_quality
        )
        
        # Classify acceptance
        classification = self._classify_acceptance(acceptance_score)
        
        return AcceptanceState(
            level=current_price,
            score=acceptance_score,
            classification=classification,
            position_in_profile=position,
            volume_quality=volume_quality,
            time_quality=time_quality,
            flow_quality=flow_quality,
            participant_quality=participant_quality
        )
        
    def _classify_position_in_profile(self,
                                     price: float,
                                     profile: MarketProfile) -> str:
        """
        Where is current price relative to value area?
        
        Returns:
            INSIDE_VALUE: In acceptance zone (strong)
            ABOVE_VALUE: Above acceptance (testing higher value)
            BELOW_VALUE: Below acceptance (testing lower value)
        """
        
        if profile.value_area_low <= price <= profile.value_area_high:
            return "INSIDE_VALUE"
        elif price > profile.value_area_high:
            return "ABOVE_VALUE"
        else:
            return "BELOW_VALUE"
            
    def _measure_volume_at_price(self,
                                price: float,
                                volume_profile: pd.DataFrame) -> VolumeQuality:
        """
        How much volume at this specific price level?
        
        High volume = acceptance
        Low volume = tolerance (just passing through)
        """
        
        if volume_profile is None or len(volume_profile) == 0:
            return self._empty_quality_volume()

        # Fail-closed if expected columns are missing
        if not self._has_columns(volume_profile, ['price_level', 'volume']):
            return self._empty_quality_volume()
            
        # Define price range (±0.5%)
        price_min = price * 0.995
        price_max = price * 1.005
        
        # Get volume at this level
        at_level = volume_profile[
            (volume_profile['price_level'] >= price_min) &
            (volume_profile['price_level'] <= price_max)
        ]
        
        volume_at_level = at_level['volume'].sum() if len(at_level) > 0 else 0
        
        # Calculate average volume per price level
        avg_volume_per_level = volume_profile['volume'].mean()
        
        # Relative volume
        relative = volume_at_level / avg_volume_per_level if avg_volume_per_level > 0 else 0
        
        # Classify quality
        if relative > self.thresholds['volume_high_threshold']:
            quality = "HIGH"
        elif relative > self.thresholds['volume_normal_threshold']:
            quality = "NORMAL"
        else:
            quality = "LOW"
            
        return VolumeQuality(
            absolute=volume_at_level,
            relative=relative,
            quality=quality
        )
        
    def _measure_time_at_price(self,
                              price: float,
                              recent_bars: pd.DataFrame) -> TimeQuality:
        """
        How long has price been at this level?
        
        Extended time = acceptance (comfortable here)
        Brief time = tolerance (just visiting)
        """
        
        if recent_bars is None or len(recent_bars) == 0:
            return self._empty_quality_time()
            
        # Define price range (±0.5%)
        price_min = price * 0.995
        price_max = price * 1.005
        
        # Count bars that touched this level (vectorised)
        if not self._has_columns(recent_bars, ['low', 'high']):
            return self._empty_quality_time()

        bars_at_level = int(((recent_bars['low'] <= price_max) & (recent_bars['high'] >= price_min)).sum())
                
        # Classify quality
        if bars_at_level >= self.thresholds['time_extended_bars']:
            quality = "EXTENDED"
        elif bars_at_level >= self.thresholds['time_moderate_bars']:
            quality = "MODERATE"
        else:
            quality = "BRIEF"
            
        return TimeQuality(
            bars_at_level=bars_at_level,
            quality=quality
        )
        
    def _measure_flow_balance(self,
                             price: float,
                             recent_bars: pd.DataFrame,
                             time_and_sales: Optional[pd.DataFrame] = None) -> FlowBalance:
        """
        At this price, is flow balanced (acceptance) or one-sided (searching)?
        
        Balanced = Both buyers and sellers active (agreement on value)
        Imbalanced = One side dominant (still searching for equilibrium)
        """
        
        # If we have T&S data, use it (more accurate)
        if time_and_sales is not None and len(time_and_sales) > 0:
            return self._measure_flow_from_tns(price, time_and_sales)
            
        # Fallback: Estimate from bars (less accurate)
        return self._estimate_flow_from_bars(price, recent_bars)
        
    def _measure_flow_from_tns(self,
                               price: float,
                               tns: pd.DataFrame) -> FlowBalance:
        """
        Measure buy/sell balance from Time & Sales data
        """
        
        # Fail-closed if expected columns are missing
        if not self._has_columns(tns, ['price', 'size', 'aggressor']):
            return self._empty_quality_flow()

        # Filter to price range
        price_min = price * 0.995
        price_max = price * 1.005
        
        at_level = tns[
            (tns['price'] >= price_min) &
            (tns['price'] <= price_max)
        ]
        
        if len(at_level) == 0:
            return FlowBalance(
                buy_volume=0,
                sell_volume=0,
                ratio=0.5,
                quality="UNKNOWN"
            )
            
        # Separate buy and sell volume
        buy_volume = at_level[at_level['aggressor'] == 'BUY']['size'].sum()
        sell_volume = at_level[at_level['aggressor'] == 'SELL']['size'].sum()
        total_volume = buy_volume + sell_volume
        
        # Calculate ratio
        buy_ratio = buy_volume / total_volume if total_volume > 0 else 0.5
        
        # Classify balance
        if (self.thresholds['flow_balanced_min'] <= buy_ratio <= 
            self.thresholds['flow_balanced_max']):
            quality = "BALANCED"
        elif (self.thresholds['flow_slightly_imbalanced_min'] <= buy_ratio <= 
              self.thresholds['flow_slightly_imbalanced_max']):
            quality = "SLIGHTLY_IMBALANCED"
        else:
            quality = "IMBALANCED"
            
        return FlowBalance(
            buy_volume=buy_volume,
            sell_volume=sell_volume,
            ratio=buy_ratio,
            quality=quality
        )
        
    def _estimate_flow_from_bars(self,
                                price: float,
                                recent_bars: pd.DataFrame) -> FlowBalance:
        """
        Estimate flow balance from bar closes (less accurate fallback)
        """
        
        if recent_bars is None or len(recent_bars) == 0:
            return self._empty_quality_flow()

        if not self._has_columns(recent_bars, ['low','high','open','close','volume']):
            return self._empty_quality_flow()
            
        # Filter bars near this price
        price_min = price * 0.99
        price_max = price * 1.01
        
        relevant_bars = recent_bars[
            (recent_bars['low'] <= price_max) &
            (recent_bars['high'] >= price_min)
        ]
        
        if len(relevant_bars) == 0:
            return FlowBalance(0, 0, 0.5, "UNKNOWN")
            
        # Estimate: If close > open = buying pressure, else selling
        buy_bars = relevant_bars[relevant_bars['close'] > relevant_bars['open']]
        sell_bars = relevant_bars[relevant_bars['close'] < relevant_bars['open']]
        
        buy_volume = buy_bars['volume'].sum()
        sell_volume = sell_bars['volume'].sum()
        total_volume = buy_volume + sell_volume
        
        buy_ratio = buy_volume / total_volume if total_volume > 0 else 0.5
        
        # Classify
        if 0.45 <= buy_ratio <= 0.55:
            quality = "BALANCED"
        elif 0.40 <= buy_ratio <= 0.60:
            quality = "SLIGHTLY_IMBALANCED"
        else:
            quality = "IMBALANCED"
            
        return FlowBalance(
            buy_volume=buy_volume,
            sell_volume=sell_volume,
            ratio=buy_ratio,
            quality=quality
        )
        
    def _measure_participant_diversity(self,
                                      price: float,
                                      time_and_sales: Optional[pd.DataFrame] = None) -> ParticipantQuality:
        """
        How many different participants trading at this level?
        
        Many participants = real market (acceptance)
        Few participants = market maker only (tolerance)
        """
        
        if time_and_sales is None or len(time_and_sales) == 0:
            return self._empty_quality_participants()

        if not self._has_columns(time_and_sales, ['price', 'size']):
            return self._empty_quality_participants()

        # Filter to price range
        price_min = price * 0.995
        price_max = price * 1.005
        
        at_level = time_and_sales[
            (time_and_sales['price'] >= price_min) &
            (time_and_sales['price'] <= price_max)
        ]
        
        if len(at_level) == 0:
            return ParticipantQuality(0, "UNKNOWN")
            
        # Proxy: Count unique trade sizes (different players trade different sizes)
        unique_sizes = at_level['size'].nunique()
        
        # Classify
        if unique_sizes >= self.thresholds['participants_diverse_threshold']:
            quality = "DIVERSE"
        elif unique_sizes >= self.thresholds['participants_moderate_threshold']:
            quality = "MODERATE"
        else:
            quality = "CONCENTRATED"
            
        return ParticipantQuality(
            unique_sizes=unique_sizes,
            quality=quality
        )
        
    def _calculate_acceptance_score(self,
                                   position: str,
                                   volume: VolumeQuality,
                                   time: TimeQuality,
                                   flow: FlowBalance,
                                   participants: ParticipantQuality) -> float:
        """
        Aggregate all signals into single acceptance score (0-100)
        
        FIX 4: Detect when running entirely on fallbacks
        
        Weighting:
        - Position in value area: 30 points
        - Volume quality: 25 points
        - Time quality: 20 points
        - Flow balance: 15 points
        - Participant diversity: 10 points
        """
        
        # FIX 4: DETECT FALLBACK MODE
        # If most signals are UNKNOWN, we're running on weak data
        running_on_fallbacks = (
            volume.quality == "UNKNOWN" and
            time.quality == "UNKNOWN" and
            flow.quality == "UNKNOWN" and
            participants.quality == "UNKNOWN"
        )
        
        if running_on_fallbacks:
            # Flag as insufficient data (will trigger DATA_INSUFFICIENT in Layer 1)
            return -1.0  # Special value meaning "no real data"
        
        score = 0.0
        
        # Position in value area (30 points)
        if position == "INSIDE_VALUE":
            score += 30
        elif position == "ABOVE_VALUE" or position == "BELOW_VALUE":
            score += 10  # Can still accept value outside VA
            
        # Volume quality (25 points)
        volume_scores = {"HIGH": 25, "NORMAL": 15, "LOW": 5, "UNKNOWN": 10}
        score += volume_scores.get(volume.quality, 10)
        
        # Time quality (20 points)
        time_scores = {"EXTENDED": 20, "MODERATE": 10, "BRIEF": 0, "UNKNOWN": 5}
        score += time_scores.get(time.quality, 5)
        
        # Flow balance (15 points)
        flow_scores = {
            "BALANCED": 15,
            "SLIGHTLY_IMBALANCED": 8,
            "IMBALANCED": 0,
            "UNKNOWN": 5
        }
        score += flow_scores.get(flow.quality, 5)
        
        # Participant diversity (10 points)
        participant_scores = {
            "DIVERSE": 10,
            "MODERATE": 5,
            "CONCENTRATED": 0,
            "UNKNOWN": 3
        }
        score += participant_scores.get(participants.quality, 3)
        
        return float(score)
        
    def _classify_acceptance(self, score: float) -> str:
        """
        Convert score to classification
        
        FIX 4: Handle fallback detection signal
        
        >=75 = ACCEPTED (high confidence, market agrees)
        >=50 = TRANSITIONING (moving toward acceptance)
        <50 = TOLERATED (just passing through, not agreeing)
        -1 = INSUFFICIENT_DATA (running on fallbacks)
        """
        
        # FIX 4: Check for fallback signal
        if score < 0:
            return "INSUFFICIENT_DATA"
        
        if score >= self.thresholds['acceptance_score_accepted']:
            return "ACCEPTED"
        elif score >= self.thresholds['acceptance_score_transitioning']:
            return "TRANSITIONING"
        else:
            return "TOLERATED"


# Backwards-compatibility alias — pipeline may import ValueAcceptance from this module
ValueAcceptance = ValueAcceptanceDetector
