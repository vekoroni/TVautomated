"""
VANGUARD Layer 1 - Control Identifier
Determines who controls the tape: BUYERS, SELLERS, or NEUTRAL

Control = Who is DRIVING price vs who is DEFENDING
Initiative = Aggressive (taking liquidity)
Responsive = Passive (providing liquidity)
"""

import pandas as pd
import numpy as np
from typing import Dict, Optional
from ..schemas.auction_schema import (
    ControlState, AggressionMetrics, EfficiencyMetrics, VolumeTrend
)
from ..config import CONTROL_THRESHOLDS


class ControlIdentifier:
    """
    Identifies who controls the tape
    
    Control manifests through:
    1. Aggression (who takes liquidity?)
    2. Efficiency (how much volume to move price?)
    3. Trend (whose participation is accelerating?)
    """
    
    def __init__(self):
        self.thresholds = CONTROL_THRESHOLDS
        
    def identify_control(self,
                        ticker: str,
                        recent_bars: pd.DataFrame,
                        time_and_sales: Optional[pd.DataFrame] = None) -> ControlState:
        """
        Main entry: Identify who controls the tape
        
        Args:
            ticker: Stock symbol
            recent_bars: Recent bars (last 1-4 hours minimum)
            time_and_sales: Optional T&S data for aggression analysis
            
        Returns:
            ControlState with controller, confidence, and component metrics
        """
        
        # Measure aggression (who takes liquidity?)
        aggression = self._measure_aggression(time_and_sales, recent_bars)
        
        # Measure efficiency (how efficiently moving price?)
        efficiency = self._measure_efficiency(recent_bars)
        
        # Measure volume trend (whose volume accelerating?)
        trend = self._measure_volume_trend(recent_bars, time_and_sales)
        
        # Determine control
        control_result = self._determine_control(aggression, efficiency, trend)
        
        # Generate interpretation
        interpretation = self._interpret_control(control_result, aggression, efficiency, trend)
        
        return ControlState(
            controller=control_result['controller'],
            confidence=control_result['confidence'],
            aggression=aggression,
            efficiency=efficiency,
            trend=trend,
            interpretation=interpretation
        )
        
    def _measure_aggression(self,
                           tns: Optional[pd.DataFrame],
                           bars: pd.DataFrame) -> AggressionMetrics:
        """
        Who is TAKING liquidity (aggressive) vs PROVIDING (passive)?
        
        Aggressive = Lifting offers (buying at ask) or hitting bids (selling at bid)
        This shows who has URGENCY
        """
        
        if tns is not None and len(tns) > 0:
            return self._measure_aggression_from_tns(tns)
        else:
            return self._estimate_aggression_from_bars(bars)
            
    def _measure_aggression_from_tns(self, tns: pd.DataFrame) -> AggressionMetrics:
        """
        Measure aggression from Time & Sales data
        """
        
        # Identify aggressive trades
        # Aggressive buy = trade at ask or above
        # Aggressive sell = trade at bid or below
        
        buy_aggressive = tns[
            (tns['aggressor'] == 'BUY') &
            (tns['price'] >= tns['ask'])
        ]['size'].sum()
        
        sell_aggressive = tns[
            (tns['aggressor'] == 'SELL') &
            (tns['price'] <= tns['bid'])
        ]['size'].sum()
        
        total_aggressive = buy_aggressive + sell_aggressive
        
        if total_aggressive == 0:
            return AggressionMetrics(
                buy_aggressive=0,
                sell_aggressive=0,
                buy_pct=0.5,
                sell_pct=0.5,
                interpretation="BALANCED"
            )
            
        buy_pct = buy_aggressive / total_aggressive
        sell_pct = sell_aggressive / total_aggressive
        
        # Classify
        if buy_pct > self.thresholds['aggression_buyer_threshold']:
            interpretation = "BUYERS_AGGRESSIVE"
        elif sell_pct > self.thresholds['aggression_seller_threshold']:
            interpretation = "SELLERS_AGGRESSIVE"
        else:
            interpretation = "BALANCED"
            
        return AggressionMetrics(
            buy_aggressive=buy_aggressive,
            sell_aggressive=sell_aggressive,
            buy_pct=buy_pct,
            sell_pct=sell_pct,
            interpretation=interpretation
        )
        
    def _estimate_aggression_from_bars(self, bars: pd.DataFrame) -> AggressionMetrics:
        """
        Estimate aggression from bars (fallback when no T&S)
        """
        
        if bars is None or len(bars) == 0:
            return AggressionMetrics(0, 0, 0.5, 0.5, "UNKNOWN")
            
        # Estimate: Green bars = buying aggression, red bars = selling aggression
        green_bars = bars[bars['close'] > bars['open']]
        red_bars = bars[bars['close'] < bars['open']]
        
        buy_volume = green_bars['volume'].sum()
        sell_volume = red_bars['volume'].sum()
        total_volume = buy_volume + sell_volume
        
        buy_pct = buy_volume / total_volume if total_volume > 0 else 0.5
        sell_pct = sell_volume / total_volume if total_volume > 0 else 0.5
        
        # Classify
        if buy_pct > 0.60:
            interpretation = "BUYERS_AGGRESSIVE"
        elif sell_pct > 0.60:
            interpretation = "SELLERS_AGGRESSIVE"
        else:
            interpretation = "BALANCED"
            
        return AggressionMetrics(
            buy_aggressive=buy_volume,
            sell_aggressive=sell_volume,
            buy_pct=buy_pct,
            sell_pct=sell_pct,
            interpretation=interpretation
        )
        
    def _measure_efficiency(self, bars: pd.DataFrame) -> EfficiencyMetrics:
        """
        How efficiently is each side moving price?
        
        Efficient = Small volume → Big price move (strong side)
        Inefficient = Large volume → Small price move (weak side)
        """
        
        if bars is None or len(bars) < 2:
            return EfficiencyMetrics(
                price_change_pct=0,
                volume_used=0,
                efficiency_score=0,
                driver="NEUTRAL"
            )
            
        # Calculate price change
        start_price = bars['close'].iloc[0]
        end_price = bars['close'].iloc[-1]
        price_change = end_price - start_price
        price_change_pct = price_change / start_price if start_price > 0 else 0
        
        # Total volume used
        total_volume = bars['volume'].sum()
        
        # Efficiency: Price change per million shares
        # Normalize to per 1M shares
        efficiency_score = (price_change_pct / (total_volume / 1_000_000)) if total_volume > 0 else 0
        
        # Determine driver
        if price_change_pct > 0.005:  # >0.5% up
            driver = "BUYERS"
        elif price_change_pct < -0.005:  # >0.5% down
            driver = "SELLERS"
            efficiency_score = abs(efficiency_score)  # Make positive for sellers
        else:
            driver = "NEUTRAL"
            
        return EfficiencyMetrics(
            price_change_pct=price_change_pct,
            volume_used=total_volume,
            efficiency_score=efficiency_score,
            driver=driver
        )
        
    def _measure_volume_trend(self,
                             bars: pd.DataFrame,
                             tns: Optional[pd.DataFrame] = None) -> VolumeTrend:
        """
        Is participation ACCELERATING or DECELERATING?
        Whose volume is increasing?
        """
        
        if tns is not None and len(tns) > 10:
            return self._measure_volume_trend_from_tns(tns)
        else:
            return self._measure_volume_trend_from_bars(bars)
            
    def _measure_volume_trend_from_tns(self, tns: pd.DataFrame) -> VolumeTrend:
        """
        Measure volume trend from T&S data
        """
        
        # Split into first half vs second half
        midpoint = len(tns) // 2
        first_half = tns.iloc[:midpoint]
        second_half = tns.iloc[midpoint:]
        
        # Buy volume trend
        buy_vol_first = first_half[first_half['aggressor'] == 'BUY']['size'].sum()
        buy_vol_second = second_half[second_half['aggressor'] == 'BUY']['size'].sum()
        
        buy_trend = (buy_vol_second - buy_vol_first) / buy_vol_first if buy_vol_first > 0 else 0
        
        # Sell volume trend
        sell_vol_first = first_half[first_half['aggressor'] == 'SELL']['size'].sum()
        sell_vol_second = second_half[second_half['aggressor'] == 'SELL']['size'].sum()
        
        sell_trend = (sell_vol_second - sell_vol_first) / sell_vol_first if sell_vol_first > 0 else 0
        
        # Classify
        acceleration_threshold = self.thresholds['volume_trend_acceleration']
        
        if buy_trend > acceleration_threshold and buy_trend > sell_trend:
            interpretation = "BUYERS_ACCELERATING"
        elif sell_trend > acceleration_threshold and sell_trend > buy_trend:
            interpretation = "SELLERS_ACCELERATING"
        else:
            interpretation = "STABLE"
            
        return VolumeTrend(
            buy_trend=buy_trend,
            sell_trend=sell_trend,
            interpretation=interpretation
        )
        
    def _measure_volume_trend_from_bars(self, bars: pd.DataFrame) -> VolumeTrend:
        """
        Estimate volume trend from bars (fallback)
        """
        
        if bars is None or len(bars) < 10:
            return VolumeTrend(0, 0, "UNKNOWN")
            
        # Split into first half vs second half
        midpoint = len(bars) // 2
        first_half = bars.iloc[:midpoint]
        second_half = bars.iloc[midpoint:]
        
        # Green vs red bars
        buy_vol_first = first_half[first_half['close'] > first_half['open']]['volume'].sum()
        buy_vol_second = second_half[second_half['close'] > second_half['open']]['volume'].sum()
        
        sell_vol_first = first_half[first_half['close'] < first_half['open']]['volume'].sum()
        sell_vol_second = second_half[second_half['close'] < second_half['open']]['volume'].sum()
        
        buy_trend = (buy_vol_second - buy_vol_first) / buy_vol_first if buy_vol_first > 0 else 0
        sell_trend = (sell_vol_second - sell_vol_first) / sell_vol_first if sell_vol_first > 0 else 0
        
        # Classify
        if buy_trend > 0.20 and buy_trend > sell_trend:
            interpretation = "BUYERS_ACCELERATING"
        elif sell_trend > 0.20 and sell_trend > buy_trend:
            interpretation = "SELLERS_ACCELERATING"
        else:
            interpretation = "STABLE"
            
        return VolumeTrend(
            buy_trend=buy_trend,
            sell_trend=sell_trend,
            interpretation=interpretation
        )
        
    def _determine_control(self,
                          aggression: AggressionMetrics,
                          efficiency: EfficiencyMetrics,
                          trend: VolumeTrend) -> Dict:
        """
        Synthesize all signals to determine who controls tape
        
        Scoring:
        - Aggression: 40 points
        - Efficiency: 35 points
        - Trend: 25 points
        """
        
        buyer_points = 0.0
        seller_points = 0.0
        
        # Aggression (40 points)
        if aggression.interpretation == "BUYERS_AGGRESSIVE":
            buyer_points += 40
        elif aggression.interpretation == "SELLERS_AGGRESSIVE":
            seller_points += 40
        else:  # BALANCED
            buyer_points += 20
            seller_points += 20
            
        # Efficiency (35 points)
        if efficiency.driver == "BUYERS":
            buyer_points += 35
        elif efficiency.driver == "SELLERS":
            seller_points += 35
        else:  # NEUTRAL
            buyer_points += 17.5
            seller_points += 17.5
            
        # Trend (25 points)
        if trend.interpretation == "BUYERS_ACCELERATING":
            buyer_points += 25
        elif trend.interpretation == "SELLERS_ACCELERATING":
            seller_points += 25
        else:  # STABLE
            buyer_points += 12.5
            seller_points += 12.5
            
        # Determine controller
        total_points = buyer_points + seller_points
        buyer_pct = buyer_points / total_points if total_points > 0 else 0.5
        
        # Classification
        if buyer_pct > (1 - self.thresholds['control_strong_threshold']):
            controller = "BUYERS"
            confidence = buyer_pct
        elif buyer_pct < self.thresholds['control_strong_threshold']:
            controller = "SELLERS"
            confidence = 1 - buyer_pct
        else:
            controller = "NEUTRAL"
            confidence = 0.5
            
        return {
            'controller': controller,
            'confidence': confidence,
            'buyer_points': buyer_points,
            'seller_points': seller_points
        }
        
    def _interpret_control(self,
                          control: Dict,
                          aggression: AggressionMetrics,
                          efficiency: EfficiencyMetrics,
                          trend: VolumeTrend) -> str:
        """
        Generate human-readable interpretation
        """
        
        controller = control['controller']
        confidence = control['confidence']
        
        if controller == "BUYERS" and confidence > 0.75:
            return f"Strong buyer control ({confidence:.0%}): {aggression.interpretation}, {efficiency.driver} efficient, {trend.interpretation}"
        elif controller == "SELLERS" and confidence > 0.75:
            return f"Strong seller control ({confidence:.0%}): {aggression.interpretation}, {efficiency.driver} efficient, {trend.interpretation}"
        elif controller == "NEUTRAL":
            return "Control is contested - no clear directional bias"
        else:
            return f"Moderate {controller.lower()} control ({confidence:.0%}) - not yet decisive"
