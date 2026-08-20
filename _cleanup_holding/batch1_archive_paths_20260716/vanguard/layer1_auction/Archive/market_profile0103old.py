"""
VANGUARD Layer 1 - Market Profile Calculator
Builds Market Profile (TPO chart) from intraday price data
Identifies Point of Control, Value Area, and profile characteristics
"""

import pandas as pd
import numpy as np
from typing import Dict, Tuple
from ..schemas.auction_schema import MarketProfile
from ..config import MARKET_PROFILE_CONFIG


class MarketProfileCalculator:
    """
    Calculates Market Profile for a given trading session
    
    Market Profile identifies where price spent the most time (acceptance)
    vs where it was rejected (brief visits)
    
    Key outputs:
    - POC (Point of Control): Price with most time/volume
    - Value Area: Zone containing 70% of time/volume (acceptance zone)
    - Profile Type: Shape tells story (P-shaped, B-shaped, Normal, Trend)
    """
    
    def __init__(self):
        self.tpo_interval = MARKET_PROFILE_CONFIG['tpo_interval_minutes']
        self.value_area_percent = MARKET_PROFILE_CONFIG['value_area_percent']
        self.min_bars = MARKET_PROFILE_CONFIG['min_bars_for_profile']
        
    def calculate_profile(self, 
                         ticker: str,
                         bars: pd.DataFrame,
                         timeframe: str = "1D") -> MarketProfile:
        """
        Main entry: Calculate Market Profile from intraday bars
        
        Args:
            ticker: Stock symbol
            bars: DataFrame with OHLCV data (intraday, e.g., 5-min, 15-min, 30-min)
                  Columns: timestamp, open, high, low, close, volume
            timeframe: Profile timeframe ("1D" for daily, "1W" for weekly)
            
        Returns:
            MarketProfile object
        """
        
        # Validate input
        if bars is None or len(bars) < self.min_bars:
            return self._empty_profile(ticker, timeframe, 
                                      reason=f"Insufficient data ({len(bars) if bars is not None else 0} bars)")
        
        # Build TPO (Time-Price-Opportunity) distribution
        tpo_counts = self._build_tpo_distribution(bars)
        
        if not tpo_counts:
            return self._empty_profile(ticker, timeframe, reason="No TPO data generated")
        
        # Find Point of Control (highest volume price)
        poc = self._find_point_of_control(tpo_counts)
        
        # Calculate Value Area (70% of volume around POC)
        value_area = self._calculate_value_area(tpo_counts, poc)
        
        # Classify profile type
        profile_type = self._classify_profile_type(tpo_counts, poc, value_area)
        
        # Assess balance
        balance = self._assess_balance(bars, poc, value_area)
        
        return MarketProfile(
            poc=poc,
            value_area_high=value_area['high'],
            value_area_low=value_area['low'],
            profile_type=profile_type,
            balance=balance,
            tpo_distribution=tpo_counts,
            timestamp=bars['timestamp'].iloc[-1] if 'timestamp' in bars.columns else pd.Timestamp.now(),
            timeframe=timeframe
        )
        
    def _build_tpo_distribution(self, bars: pd.DataFrame) -> Dict[float, int]:
        """
        Build TPO chart: Count how many time periods each price touched
        
        TPO = Time-Price-Opportunity
        Each bar represents a "letter" in Market Profile terminology
        We count how many bars touched each price level
        """
        
        tpo_counts = {}
        
        # Price precision (round to nearest $0.10)
        price_increment = 0.10
        
        for _, bar in bars.iterrows():
            # Get price range for this bar
            bar_low = bar['low']
            bar_high = bar['high']
            
            # Round to price increment
            bar_low = np.floor(bar_low / price_increment) * price_increment
            bar_high = np.ceil(bar_high / price_increment) * price_increment
            
            # Generate all price levels touched by this bar
            price_levels = np.arange(bar_low, bar_high + price_increment, price_increment)
            price_levels = np.round(price_levels, 2)  # Avoid floating point errors
            
            # Increment TPO count for each level
            for price in price_levels:
                if price not in tpo_counts:
                    tpo_counts[price] = 0
                tpo_counts[price] += 1
                
        return tpo_counts
        
    def _find_point_of_control(self, tpo_counts: Dict[float, int]) -> float:
        """
        POC = Price level with most TPO count
        This is where market spent the MOST time = strongest acceptance
        """
        
        if not tpo_counts:
            return 0.0
            
        poc = max(tpo_counts, key=tpo_counts.get)
        return float(poc)
        
    def _calculate_value_area(self, 
                              tpo_counts: Dict[float, int],
                              poc: float) -> Dict[str, float]:
        """
        Value Area = Price range containing 70% of TPO volume
        Centered on POC, expanded up/down until we capture 70%
        
        This is the ACCEPTANCE ZONE - where market agreed on fair value
        """
        
        if not tpo_counts:
            return {'high': 0.0, 'low': 0.0}
            
        total_tpo = sum(tpo_counts.values())
        target_tpo = total_tpo * self.value_area_percent
        
        # Start with POC
        accumulated_tpo = tpo_counts.get(poc, 0)
        
        # Get sorted price levels
        prices_sorted = sorted(tpo_counts.keys())
        
        try:
            poc_idx = prices_sorted.index(poc)
        except ValueError:
            # POC not in list (shouldn't happen, but handle gracefully)
            return {'high': poc, 'low': poc}
        
        # Initialize value area boundaries
        value_high_idx = poc_idx
        value_low_idx = poc_idx
        
        # Expand up and down alternately, choosing direction with more TPO
        while accumulated_tpo < target_tpo:
            # Can we expand up?
            can_expand_up = value_high_idx < len(prices_sorted) - 1
            # Can we expand down?
            can_expand_down = value_low_idx > 0
            
            if not can_expand_up and not can_expand_down:
                break  # Reached limits
                
            # Get TPO counts for next levels
            tpo_above = tpo_counts.get(prices_sorted[value_high_idx + 1], 0) if can_expand_up else 0
            tpo_below = tpo_counts.get(prices_sorted[value_low_idx - 1], 0) if can_expand_down else 0
            
            # Expand toward higher TPO
            if can_expand_up and (tpo_above >= tpo_below or not can_expand_down):
                value_high_idx += 1
                accumulated_tpo += tpo_above
            elif can_expand_down:
                value_low_idx -= 1
                accumulated_tpo += tpo_below
                
        return {
            'high': float(prices_sorted[value_high_idx]),
            'low': float(prices_sorted[value_low_idx])
        }
        
    def _classify_profile_type(self,
                               tpo_counts: Dict[float, int],
                               poc: float,
                               value_area: Dict[str, float]) -> str:
        """
        Classify the profile shape
        
        Types:
        - NORMAL: Bell curve, balanced distribution
        - P_SHAPED: Tail at bottom (price rejected lower prices - bullish)
        - B_SHAPED: Tail at top (price rejected higher prices - bearish)
        - TREND: Elongated, directional movement (trending day)
        """
        
        if not tpo_counts:
            return "UNKNOWN"
            
        prices = sorted(tpo_counts.keys())
        
        try:
            poc_idx = prices.index(poc)
        except ValueError:
            return "UNKNOWN"
            
        # Calculate distribution above/below POC
        tpo_above_poc = sum(tpo_counts[p] for p in prices[poc_idx+1:]) if poc_idx < len(prices) - 1 else 0
        tpo_below_poc = sum(tpo_counts[p] for p in prices[:poc_idx]) if poc_idx > 0 else 0
        total_tpo = sum(tpo_counts.values())
        
        pct_above = tpo_above_poc / total_tpo if total_tpo > 0 else 0
        pct_below = tpo_below_poc / total_tpo if total_tpo > 0 else 0
        
        # Calculate value area width
        va_width = value_area['high'] - value_area['low']
        price_range = max(prices) - min(prices)
        va_ratio = va_width / price_range if price_range > 0 else 0
        
        # Classification logic
        if abs(pct_above - pct_below) < 0.15:
            # Relatively balanced
            if va_ratio > 0.60:
                return "NORMAL"  # Wide value area, balanced
            else:
                return "TREND"  # Narrow value area, trending
        elif pct_below > pct_above + 0.20:
            return "P_SHAPED"  # More time below POC (rejected lower prices)
        elif pct_above > pct_below + 0.20:
            return "B_SHAPED"  # More time above POC (rejected higher prices)
        else:
            return "NORMAL"
            
    def _assess_balance(self,
                       bars: pd.DataFrame,
                       poc: float,
                       value_area: Dict[str, float]) -> str:
        """
        Assess if trading was balanced or dominated by one side
        
        Returns:
        - BALANCED: Even distribution of buying/selling
        - BUYER_DOMINATED: Strong buying throughout session
        - SELLER_DOMINATED: Strong selling throughout session
        """
        
        if bars is None or len(bars) < 5:
            return "UNKNOWN"
            
        # Simple heuristic: Compare close to open and volume pattern
        session_open = bars['open'].iloc[0]
        session_close = bars['close'].iloc[-1]
        session_high = bars['high'].max()
        session_low = bars['low'].min()
        
        # Price change
        price_change_pct = (session_close - session_open) / session_open
        
        # Where did we close relative to range?
        if session_high != session_low:
            close_position = (session_close - session_low) / (session_high - session_low)
        else:
            close_position = 0.5
            
        # Classification
        if close_position > 0.70 and price_change_pct > 0.01:
            return "BUYER_DOMINATED"  # Closed near highs, up on day
        elif close_position < 0.30 and price_change_pct < -0.01:
            return "SELLER_DOMINATED"  # Closed near lows, down on day
        else:
            return "BALANCED"  # Closed mid-range or mixed signals
            
    def _empty_profile(self, ticker: str, timeframe: str, reason: str = "") -> MarketProfile:
        """
        Return empty/invalid profile when data is insufficient
        """
        return MarketProfile(
            poc=0.0,
            value_area_high=0.0,
            value_area_low=0.0,
            profile_type="INSUFFICIENT_DATA",
            balance="UNKNOWN",
            tpo_distribution={},
            timestamp=pd.Timestamp.now(),
            timeframe=timeframe
        )
