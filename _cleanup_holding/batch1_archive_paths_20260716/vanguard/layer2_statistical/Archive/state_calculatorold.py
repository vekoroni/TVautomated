"""
VANGUARD Layer 2 - State Vector Calculator
Transforms raw market data into quantified STATE

This state will be matched against historical database to find probability distributions
"""

import pandas as pd
import numpy as np
from typing import Dict
from ..schemas.state_outcomes_schema import StateVector
from ..schemas.auction_schema import AuctionVerdict
from ..schemas.input_schema import VanguardInput
from ..config import VOLATILITY_THRESHOLDS, TREND_THRESHOLDS, STRUCTURE_THRESHOLDS
import hashlib


class StateVectorCalculator:
    """
    Calculates complete state fingerprint for actuarial matching
    
    Every dimension of state is quantified:
    - Volatility regime
    - Trend maturity
    - Structure quality (enhanced with auction data)
    - Positioning bias
    - Catalyst proximity
    - Macro backdrop
    """
    
    def __init__(self):
        self.vol_thresholds = VOLATILITY_THRESHOLDS
        self.trend_thresholds = TREND_THRESHOLDS
        self.structure_thresholds = STRUCTURE_THRESHOLDS
        
    def calculate_state(self,
                       vanguard_input: VanguardInput,
                       auction_verdict: AuctionVerdict) -> StateVector:
        """
        Main entry: Build complete state vector
        
        Args:
            vanguard_input: Complete input package
            auction_verdict: Output from Layer 1
            
        Returns:
            StateVector ready for actuarial query
        """
        
        ticker = vanguard_input.ticker
        current_price = vanguard_input.current_price
        tech = vanguard_input.technical
        options = vanguard_input.options
        macro = vanguard_input.macro
        calendar = vanguard_input.calendar
        
        # Calculate each dimension
        vol_state = self._calculate_volatility_regime(tech)
        trend_state = self._calculate_trend_maturity(tech)
        structure_state = self._calculate_structure_quality(tech, auction_verdict)
        positioning_state = self._calculate_positioning_bias(options)
        catalyst_state = self._calculate_catalyst_proximity(calendar)
        macro_state = self._calculate_macro_regime(macro)
        
        # Generate state hash
        state_hash = self._generate_state_hash(
            ticker, vol_state, trend_state, structure_state,
            positioning_state, catalyst_state, macro_state
        )
        
        # Calculate confidence
        confidence = self._calculate_state_confidence(
            vanguard_input, auction_verdict
        )
        
        return StateVector(
            # Identification
            ticker=ticker,
            timestamp=vanguard_input.analysis_timestamp,
            price=current_price,
            
            # Volatility Regime
            atr_current=tech.atr_current,
            atr_percentile=vol_state['atr_percentile'],
            bb_width_percentile=vol_state['bb_percentile'],
            iv_percentile=vol_state['iv_percentile'],
            vol_regime=vol_state['regime'],
            vol_regime_score=vol_state['score'],
            
            # Trend Maturity
            distance_from_52w_high=trend_state['pct_from_high'],
            distance_from_52w_low=trend_state['pct_from_low'],
            days_since_52w_high=trend_state['days_since_high'],
            trend_length_days=trend_state['length'],
            trend_direction=trend_state['direction'],
            adx=tech.adx,
            trend_maturity=trend_state['maturity'],
            trend_strength_score=trend_state['strength'],
            
            # Structure
            price_vs_vwap_1h=structure_state['pct_from_vwap_1h'],
            price_vs_vwap_daily=structure_state['pct_from_vwap_daily'],
            price_vs_poc=structure_state['pct_from_poc'],
            price_position_in_value=structure_state['position_in_value'],
            value_acceptance_score=auction_verdict.acceptance.score,
            failed_breakouts_20d=tech.failed_breakout_count,
            control_state=auction_verdict.control.controller,
            control_confidence=auction_verdict.control.confidence,
            structure_quality=structure_state['quality'],
            
            # Liquidity
            relative_volume=structure_state['relative_volume'],
            spread_percentile=50.0,  # TODO: Calculate from microstructure data
            liquidity_condition=structure_state['liquidity'],
            
            # Positioning
            put_call_ratio=positioning_state['pc_ratio'],
            put_call_oi_ratio=positioning_state['pc_oi_ratio'],
            options_skew=positioning_state['skew'],
            net_gamma_exposure=positioning_state['net_gex'],
            net_delta_exposure=positioning_state['net_dex'],
            positioning_bias=positioning_state['bias'],
            
            # Macro
            vix=macro.vix,
            vix_percentile=macro_state['vix_percentile'],
            spy_trend=macro.spy_trend,
            sector_relative_strength=macro.sector_relative_strength,
            macro_regime=macro_state['regime'],
            
            # Catalyst
            days_to_earnings=catalyst_state['days_to'],
            earnings_window=catalyst_state['window'],
            days_since_earnings=catalyst_state['days_since'],
            catalyst_proximity=catalyst_state['proximity'],
            
            # Auction Integration
            value_migration_direction=auction_verdict.migration.direction,
            value_migration_speed=auction_verdict.migration.speed,
            auction_state=auction_verdict.auction_state,
            
            # Intraday Market Profile (from real-time data)
            intraday_position=getattr(tech, 'intraday_position', 'UNKNOWN'),
            volume_profile_context=getattr(tech, 'volume_profile_context', 'BALANCED'),
            control_dynamics=getattr(tech, 'control_dynamics', 'NEUTRAL'),
            intraday_support=getattr(tech, 'intraday_support', 0.0),
            intraday_resistance=getattr(tech, 'intraday_resistance', 0.0),
            
            # Meta
            state_hash=state_hash,
            confidence=confidence
        )
        
    def _calculate_volatility_regime(self, tech: 'TechnicalData') -> Dict:
        """
        Determine volatility regime (COMPRESSION, NORMAL, EXPANSION)
        """
        
        # Calculate percentiles
        atr_pct = self._percentile(tech.atr_current, tech.atr_history) if tech.atr_history else 50.0
        bb_pct = self._percentile(tech.bb_width, tech.bb_width_history) if tech.bb_width_history else 50.0
        
        # IV percentile (from options data if available)
        iv_pct = 50.0  # Default, would calculate from options.iv_term_structure
        
        # Weighted average
        weights = [
            self.vol_thresholds['atr_weight'],
            self.vol_thresholds['bb_weight'],
            self.vol_thresholds['iv_weight']
        ]
        avg_pct = (atr_pct * weights[0] + bb_pct * weights[1] + iv_pct * weights[2])
        
        # Classify regime
        if avg_pct < self.vol_thresholds['compression_percentile']:
            regime = "COMPRESSION"
            score = self.vol_thresholds['compression_percentile'] - avg_pct
        elif avg_pct > self.vol_thresholds['expansion_percentile']:
            regime = "EXPANSION"
            score = avg_pct - self.vol_thresholds['expansion_percentile']
        else:
            regime = "NORMAL"
            score = 50 - abs(avg_pct - 50)
            
        return {
            'regime': regime,
            'score': score,
            'atr_percentile': atr_pct,
            'bb_percentile': bb_pct,
            'iv_percentile': iv_pct
        }
        
    def _calculate_trend_maturity(self, tech: 'TechnicalData') -> Dict:
        """
        Determine trend direction and maturity
        """
        
        current_price = tech.ohlcv['close'].iloc[-1] if len(tech.ohlcv) > 0 else 0
        
        # Distance from 52w high/low
        pct_from_high = (current_price - tech.high_52w) / tech.high_52w if tech.high_52w > 0 else 0
        pct_from_low = (current_price - tech.low_52w) / tech.low_52w if tech.low_52w > 0 else 0
        
        # Days since extremes
        days_since_high = (pd.Timestamp.now() - tech.date_52w_high).days if tech.date_52w_high else 365
        days_since_low = (pd.Timestamp.now() - tech.date_52w_low).days if tech.date_52w_low else 365
        
        # Direction (using EMA alignment + ADX)
        if tech.ema21 > tech.ema50 and current_price > tech.ema21 and tech.adx > self.trend_thresholds['uptrend_adx_min']:
            direction = "UP"
        elif tech.ema21 < tech.ema50 and current_price < tech.ema21 and tech.adx > self.trend_thresholds['uptrend_adx_min']:
            direction = "DOWN"
        else:
            direction = "SIDEWAYS"
            
        # Maturity
        if direction == "UP":
            if abs(pct_from_high) < self.trend_thresholds['late_trend_percent_from_extreme']:
                maturity = "LATE"
            elif days_since_high < self.trend_thresholds['early_trend_days_from_extreme']:
                maturity = "EARLY"
            else:
                maturity = "MIDDLE"
        elif direction == "DOWN":
            if abs(pct_from_low) < self.trend_thresholds['late_trend_percent_from_extreme']:
                maturity = "LATE"
            elif days_since_low < self.trend_thresholds['early_trend_days_from_extreme']:
                maturity = "EARLY"
            else:
                maturity = "MIDDLE"
        else:
            maturity = "N/A"
            
        # Strength score (ADX)
        strength = min(tech.adx, 100) if tech.adx > 0 else 0
        
        return {
            'direction': direction,
            'maturity': maturity,
            'length': tech.trend_length_days,
            'strength': strength,
            'pct_from_high': pct_from_high,
            'pct_from_low': pct_from_low,
            'days_since_high': days_since_high,
            'days_since_low': days_since_low
        }
        
    def _calculate_structure_quality(self,
                                     tech: 'TechnicalData',
                                     auction: AuctionVerdict) -> Dict:
        """
        Structure quality incorporating auction analysis
        """
        
        current_price = tech.ohlcv['close'].iloc[-1] if len(tech.ohlcv) > 0 else 0
        
        # VWAP positioning
        pct_from_vwap_1h = (current_price - tech.vwap_1h) / tech.vwap_1h if tech.vwap_1h > 0 else 0
        pct_from_vwap_daily = (current_price - tech.vwap_daily) / tech.vwap_daily if tech.vwap_daily > 0 else 0
        
        # POC positioning (from auction)
        poc = auction.profile.poc
        pct_from_poc = (current_price - poc) / poc if poc > 0 else 0
        
        # Position in value area
        position = auction.acceptance.position_in_profile
        
        # Quality score (0-100)
        quality_score = 0.0
        
        # VWAP position (30 points)
        if pct_from_vwap_1h > 0 and pct_from_vwap_daily > 0:
            quality_score += 30  # Above both VWAPs
        elif pct_from_vwap_1h < 0 and pct_from_vwap_daily < 0:
            quality_score += 0  # Below both
        else:
            quality_score += 15  # Mixed
            
        # Value acceptance (40 points)
        quality_score += (auction.acceptance.score / 100) * 40
        
        # Control alignment (30 points)
        if auction.control.controller != "NEUTRAL":
            quality_score += auction.control.confidence * 30
        else:
            quality_score += 10
            
        # Classify
        if quality_score >= self.structure_thresholds['strong_quality_score']:
            quality = "STRONG"
        elif quality_score >= self.structure_thresholds['neutral_quality_score']:
            quality = "NEUTRAL"
        else:
            quality = "WEAK"
            
        # Liquidity (from volume)
        avg_volume = tech.ohlcv['volume'].mean() if len(tech.ohlcv) > 0 else 1
        current_volume = tech.ohlcv['volume'].iloc[-1] if len(tech.ohlcv) > 0 else 0
        relative_volume = current_volume / avg_volume if avg_volume > 0 else 1.0
        
        if relative_volume > 1.5:
            liquidity = "HIGH"
        elif relative_volume > 0.7:
            liquidity = "NORMAL"
        else:
            liquidity = "LOW"
            
        return {
            'pct_from_vwap_1h': pct_from_vwap_1h,
            'pct_from_vwap_daily': pct_from_vwap_daily,
            'pct_from_poc': pct_from_poc,
            'position_in_value': position,
            'quality': quality,
            'quality_score': quality_score,
            'relative_volume': relative_volume,
            'liquidity': liquidity
        }
        
    def _calculate_positioning_bias(self, options: 'OptionsData') -> Dict:
        """
        Options positioning bias from options flow
        """
        
        # Default values
        pc_ratio = 1.0
        pc_oi_ratio = 1.0
        skew = 0.0
        net_gex = 0.0
        net_dex = 0.0
        
        # Calculate from UOA if available
        if options.uoa is not None and len(options.uoa) > 0:
            # P/C ratio from recent flow
            calls = options.uoa[options.uoa['right'] == 'C']
            puts = options.uoa[options.uoa['right'] == 'P']
            
            call_volume = calls['volume'].sum() if len(calls) > 0 else 1
            put_volume = puts['volume'].sum() if len(puts) > 0 else 1
            
            pc_ratio = put_volume / call_volume if call_volume > 0 else 1.0
            
        # Determine bias
        if pc_ratio < 0.7 and skew > 0.2:
            bias = "NET_LONG"
        elif pc_ratio > 1.3 and skew < -0.2:
            bias = "NET_SHORT"
        else:
            bias = "NEUTRAL"
            
        return {
            'pc_ratio': pc_ratio,
            'pc_oi_ratio': pc_oi_ratio,
            'skew': skew,
            'net_gex': net_gex,
            'net_dex': net_dex,
            'bias': bias
        }
        
    def _calculate_catalyst_proximity(self, calendar: 'CalendarData') -> Dict:
        """
        Catalyst proximity and type
        """
        
        if calendar.next_earnings_date is None or calendar.days_to_earnings is None:
            return {
                'days_to': -1,
                'window': 'FAR',
                'days_since': 90,
                'proximity': 'NONE'
            }
            
        days_to = calendar.days_to_earnings
        
        # Classify window
        if days_to <= 10:
            window = "PRE_10D"
            proximity = "HIGH"
        elif days_to <= 20:
            window = "PRE_20D"
            proximity = "HIGH"
        elif days_to <= 30:
            window = "PRE_30D"
            proximity = "MEDIUM"
        elif days_to <= 60:
            window = "FAR"
            proximity = "LOW"
        else:
            window = "FAR"
            proximity = "NONE"
            
        return {
            'days_to': days_to,
            'window': window,
            'days_since': 90,  # TODO: Calculate from calendar
            'proximity': proximity
        }
        
    def _calculate_macro_regime(self, macro: 'MacroData') -> Dict:
        """
        Overall market regime
        """
        
        # VIX percentile
        vix_pct = self._percentile(macro.vix, macro.vix_history) if macro.vix_history else 50.0
        
        # Regime classification
        if macro.vix < 15 and macro.spy_trend == "UP":
            regime = "RISK_ON"
        elif macro.vix > 25 or macro.spy_trend == "DOWN":
            regime = "RISK_OFF"
        else:
            regime = "TRANSITIONAL"
            
        return {
            'regime': regime,
            'vix_percentile': vix_pct
        }
        
    def _percentile(self, value: float, history: list) -> float:
        """
        Calculate percentile rank of value in history
        """
        if not history or len(history) == 0:
            return 50.0
            
        history_array = np.array(history)
        percentile = (np.sum(history_array <= value) / len(history_array)) * 100
        return float(percentile)
        
    def _generate_state_hash(self, ticker: str, *states) -> str:
        """
        Generate unique hash for this state combination
        """
        # Create signature from key state elements
        signature_parts = [
            ticker,
            states[0]['regime'],  # vol regime
            states[1]['direction'],  # trend direction
            states[1]['maturity'],  # trend maturity
            states[2]['quality'],  # structure quality
            states[4]['proximity'],  # catalyst proximity
        ]
        
        signature = "_".join(str(p) for p in signature_parts)
        
        # Generate hash
        return hashlib.md5(signature.encode()).hexdigest()[:16]
        
    def _calculate_state_confidence(self,
                                    vanguard_input: VanguardInput,
                                    auction: AuctionVerdict) -> float:
        """
        How confident are we in this state measurement?
        """
        
        confidence = 1.0
        
        # Reduce for low data quality
        confidence *= vanguard_input.data_quality_score
        
        # Reduce for low volume
        tech = vanguard_input.technical
        if len(tech.ohlcv) > 0:
            avg_volume = tech.ohlcv['volume'].mean()
            current_volume = tech.ohlcv['volume'].iloc[-1]
            if current_volume < avg_volume * 0.5:
                confidence *= 0.8
                
        # Boost for high auction confidence
        confidence *= (0.7 + 0.3 * auction.confidence)
        
        return float(min(confidence, 1.0))
