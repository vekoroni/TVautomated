"""
VANGUARD Layer 1 - Value Migration Tracker
Determines if value is MIGRATING (trending) or HOLDING (range-bound)

Migration = Value area moving up/down over multiple sessions
Holding = Value area stable across sessions
"""

import pandas as pd
import numpy as np
from typing import List
from ..schemas.auction_schema import MigrationState, MarketProfile
from ..config import MIGRATION_THRESHOLDS


class ValueMigrationTracker:
    """
    Tracks how value area migrates over multiple sessions
    
    Migrating value = Trending market (follow the trend)
    Holding value = Range-bound market (fade extremes)
    """
    
    def __init__(self):
        self.thresholds = MIGRATION_THRESHOLDS
        
    def track_migration(self,
                       profiles: List[MarketProfile],
                       lookback_sessions: int = 5) -> MigrationState:
        """
        Track value migration across multiple sessions
        
        Args:
            profiles: List of MarketProfile objects (most recent first)
            lookback_sessions: How many sessions to analyze
            
        Returns:
            MigrationState with direction, speed, consistency
        """
        
        if not profiles or len(profiles) < 2:
            return self._no_migration_available()
            
        # Limit to lookback period
        profiles = profiles[:min(len(profiles), lookback_sessions)]
        
        # Extract value metrics over time
        migration_data = self._extract_migration_metrics(profiles)
        
        # Analyze direction
        direction = self._analyze_direction(migration_data)
        
        # Analyze speed
        speed = self._analyze_speed(migration_data)
        
        # Analyze consistency
        consistency = self._analyze_consistency(migration_data)
        
        # Calculate magnitude
        magnitude = migration_data['total_change']
        
        # Generate interpretation
        interpretation = self._interpret_migration(direction, speed, consistency, magnitude)
        
        return MigrationState(
            direction=direction,
            speed=speed,
            consistency=consistency,
            magnitude=magnitude,
            interpretation=interpretation
        )
        
    def _extract_migration_metrics(self, profiles: List[MarketProfile]) -> dict:
        """
        Extract POC and Value Area movements over time
        """
        
        poc_series = [p.poc for p in profiles]
        va_high_series = [p.value_area_high for p in profiles]
        va_low_series = [p.value_area_low for p in profiles]
        va_mid_series = [(p.value_area_high + p.value_area_low) / 2 for p in profiles]
        
        # Calculate changes (most recent - oldest)
        poc_change = (poc_series[0] - poc_series[-1]) / poc_series[-1] if poc_series[-1] > 0 else 0
        va_high_change = (va_high_series[0] - va_high_series[-1]) / va_high_series[-1] if va_high_series[-1] > 0 else 0
        va_low_change = (va_low_series[0] - va_low_series[-1]) / va_low_series[-1] if va_low_series[-1] > 0 else 0
        va_mid_change = (va_mid_series[0] - va_mid_series[-1]) / va_mid_series[-1] if va_mid_series[-1] > 0 else 0
        
        # Average change across all metrics
        avg_change = (poc_change + va_high_change + va_low_change + va_mid_change) / 4
        
        # Daily changes (for consistency analysis)
        poc_daily_changes = [
            (poc_series[i] - poc_series[i+1]) / poc_series[i+1] if poc_series[i+1] > 0 else 0
            for i in range(len(poc_series) - 1)
        ]
        
        return {
            'poc_series': poc_series,
            'va_mid_series': va_mid_series,
            'total_change': avg_change,
            'daily_changes': poc_daily_changes,
            'num_sessions': len(profiles)
        }
        
    def _analyze_direction(self, migration_data: dict) -> str:
        """
        Determine migration direction
        
        Returns: UP, DOWN, SIDEWAYS
        """
        
        total_change = migration_data['total_change']
        
        if total_change > self.thresholds['migration_significant_percent']:
            return "UP"
        elif total_change < -self.thresholds['migration_significant_percent']:
            return "DOWN"
        else:
            return "SIDEWAYS"
            
    def _analyze_speed(self, migration_data: dict) -> str:
        """
        Determine migration speed
        
        Returns: FAST, MODERATE, SLOW
        """
        
        total_change = abs(migration_data['total_change'])
        num_sessions = migration_data['num_sessions']
        
        # Average daily change
        daily_change = total_change / num_sessions if num_sessions > 0 else 0
        
        if daily_change > self.thresholds['migration_fast_daily_percent']:
            return "FAST"
        elif daily_change > self.thresholds['migration_moderate_daily_percent']:
            return "MODERATE"
        else:
            return "SLOW"
            
    def _analyze_consistency(self, migration_data: dict) -> str:
        """
        Determine migration consistency
        
        Returns:
        - CONSISTENT_UP: All or most sessions moved up
        - CONSISTENT_DOWN: All or most sessions moved down
        - TRENDING: General direction but with some back-and-forth
        - CHOPPY: No clear direction, erratic movement
        """
        
        daily_changes = migration_data['daily_changes']
        
        if not daily_changes:
            return "UNKNOWN"
            
        # Count directional days
        up_days = sum(1 for change in daily_changes if change > 0)
        down_days = sum(1 for change in daily_changes if change < 0)
        total_days = len(daily_changes)
        
        up_ratio = up_days / total_days if total_days > 0 else 0
        down_ratio = down_days / total_days if total_days > 0 else 0
        
        # Very consistent (80%+ in one direction)
        if up_ratio >= 0.80:
            return "CONSISTENT_UP"
        elif down_ratio >= 0.80:
            return "CONSISTENT_DOWN"
        
        # Mostly consistent (60%+ in one direction)
        elif up_ratio >= 0.60:
            return "TRENDING_UP"
        elif down_ratio >= 0.60:
            return "TRENDING_DOWN"
        
        # Mixed/choppy
        else:
            # Check if standard deviation is high (choppy)
            std_change = np.std(daily_changes) if len(daily_changes) > 1 else 0
            mean_change = abs(np.mean(daily_changes)) if len(daily_changes) > 0 else 0
            
            if std_change > mean_change * 2:  # High volatility of changes
                return "CHOPPY"
            else:
                return "MIXED"
                
    def _interpret_migration(self,
                            direction: str,
                            speed: str,
                            consistency: str,
                            magnitude: float) -> str:
        """
        Generate human-readable interpretation
        """
        
        if direction == "SIDEWAYS":
            return f"Value is holding (range-bound). Magnitude: {magnitude:.1%}. Strategy: Fade extremes."
            
        elif consistency.startswith("CONSISTENT"):
            return f"Value is migrating {direction} consistently at {speed.lower()} pace. Magnitude: {magnitude:.1%}. Strategy: Follow the migration."
            
        elif consistency.startswith("TRENDING"):
            return f"Value is trending {direction} with occasional consolidation. Speed: {speed}. Magnitude: {magnitude:.1%}. Strategy: Trend following with patience."
            
        elif consistency == "CHOPPY":
            return f"Value migration is choppy and erratic. Direction: {direction}, but inconsistent. Magnitude: {magnitude:.1%}. Strategy: Avoid or reduce size."
            
        else:
            return f"Value direction: {direction}, Speed: {speed}, Consistency: {consistency}. Magnitude: {magnitude:.1%}."
            
    def _no_migration_available(self) -> MigrationState:
        """
        Return when insufficient data
        """
        return MigrationState(
            direction="UNKNOWN",
            speed="UNKNOWN",
            consistency="UNKNOWN",
            magnitude=0.0,
            interpretation="Insufficient data to determine value migration"
        )
