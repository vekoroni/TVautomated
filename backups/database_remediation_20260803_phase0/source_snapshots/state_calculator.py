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

# ── SCHEMA VERSIONING ──────────────────────────────────────────────────────────
# Increment SCHEMA_VERSION whenever the hash dimensions or bucket logic changes.
# Increment BUCKET_SCHEMA_VERSION whenever bucket boundaries change (ADX/ATR thresholds).
# These are written to every signal row and every DB build so future debugging can
# immediately answer: "did the live schema match the DB schema when this ran?"
SCHEMA_VERSION        = "2.2.0"   # 9-dim: vol|trend_dir|trend_mat|structure|catalyst|adx|atr|wyckoff|macro
                                   # v2.2.0: SIDEWAYS trend_maturity N/A → SIDEWAYS_BUILDING | SIDEWAYS_RANGING
BUCKET_SCHEMA_VERSION = "1.1.0"   # ADX: <20=WEAK,20-35=MOD,>35=STRONG | ATR: <33=LOW,33-66=MID,>66=HIGH
# ──────────────────────────────────────────────────────────────────────────────


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
        # Pass vol_regime and wyckoff_phase_bucket into trend state so sideways
        # classification can use them to distinguish BUILDING vs RANGING.
        raw_wyckoff_for_trend = getattr(tech, 'wyckoff_phase_bucket', None) or getattr(tech, 'wyckoff_phase', None) or ''
        trend_state = self._calculate_trend_maturity(tech, vol_regime=vol_state['regime'], wyckoff_phase=raw_wyckoff_for_trend)
        structure_state = self._calculate_structure_quality(tech, auction_verdict)
        positioning_state = self._calculate_positioning_bias(options)
        catalyst_state = self._calculate_catalyst_proximity(calendar)
        macro_state = self._calculate_macro_regime(macro)
        
        # Generate state hash
        # Compute bucket values — stored on StateVector for actuarial_query Stage 1 filter
        # Compute bucket values — stored on StateVector for actuarial_query Stage 1 filter
        adx_bucket     = self._adx_bucket(trend_state.get('strength', 0))
        atr_pct_bucket = self._atr_percentile_bucket(vol_state.get('atr_percentile', 50))

        # Wyckoff phase bucket — from technical data (populated by run_vanguard_from_packages)
        # FIX (2026-03-07): Check pre-computed wyckoff_phase_bucket first (from discovery CSV),
        # then fall back to raw wyckoff_phase string for bucket calculation.
        # run_vanguard_from_packages MUST wire either:
        #   technical_data.wyckoff_phase_bucket = row['wyckoff_phase_bucket']  (preferred)
        #   OR technical_data.wyckoff_phase      = row['phase'] / row['current_phase']
        # Without one of these, hash collapses to UNKNOWN for all tickers → collision.
        raw_wyckoff_bucket = getattr(vanguard_input.technical, 'wyckoff_phase_bucket', None) or ''
        if raw_wyckoff_bucket and raw_wyckoff_bucket.upper() in ('ACCUMULATION', 'MARKUP', 'DISTRIBUTION'):
            wyckoff_bucket = raw_wyckoff_bucket.upper()
        else:
            raw_wyckoff    = getattr(vanguard_input.technical, 'wyckoff_phase', None) or ''
            wyckoff_bucket = self._wyckoff_phase_bucket(raw_wyckoff)

        state_hash = self._generate_state_hash(
            ticker, vol_state, trend_state, structure_state,
            positioning_state, catalyst_state, macro_state,
            wyckoff_bucket=wyckoff_bucket,
            macro_regime=macro_state.get('regime', 'TRANSITIONAL'),
        )
        
        # Calculate confidence
        confidence = self._calculate_state_confidence(
            vanguard_input, auction_verdict
        )

        # =========================
        # STATE V2 CALCULATION
        # =========================

        # phase_v2 thresholds aligned to v6 DB build script (build_state_v2.py)
        # SA spec: atr<45, adx<22, bb<55 for EARLY_TRANSITION
        # atr>=45, adx>=22, rsi<72, bb<95 for CONTINUATION
        def _phase_v2_calc(atr, adx, bb, rsi):
            if (atr < 45 and adx < 22 and bb < 55):
                return "EARLY_TRANSITION"
            elif (atr >= 45 and adx >= 22 and rsi < 72 and bb < 95):
                return "CONTINUATION"
            else:
                return "EXHAUSTION"

        _rsi_val = getattr(tech, 'rsi', 50) or 50
        phase_v2 = _phase_v2_calc(
            vol_state['atr_percentile'],
            tech.adx,
            vol_state['bb_percentile'],
            _rsi_val
        )

        momentum_score = (tech.adx * vol_state['atr_percentile']) / 100

        # Thresholds MUST match DB builder (build_state_v2.py) exactly.
        # Schema drift here causes Stage 0 to query the wrong historical cohort.
        # DB builder: < 15 LOW | < 30 MID | < 45 HIGH | >= 45 EXTREME
        if momentum_score >= 45:
            momentum_bucket = "EXTREME"
        elif momentum_score >= 30:
            momentum_bucket = "HIGH"
        elif momentum_score >= 15:
            momentum_bucket = "MID"
        else:
            momentum_bucket = "LOW"

        # pct_from_high is negative (price below 52w high) — use abs()
        _pfh = abs(trend_state['pct_from_high'])
        _pfl = abs(trend_state['pct_from_low'])

        # MUST match DB builder (build_state_v2.py) exactly.
        # MID_RANGE requires BOTH distances > 30% — not just pfh between 10-30%.
        # Previous: 0.10 <= _pfh <= 0.30 -- WRONG, caused wrong cohort matching.
        if _pfh < 0.10:
            location_bucket = "NEAR_HIGH"
        elif _pfl < 0.10:
            location_bucket = "NEAR_LOW"
        elif _pfh > 0.30 and _pfl > 0.30:
            location_bucket = "MID_RANGE"
        else:
            location_bucket = "TRANSITION_ZONE"

        transition_flag_v2 = (phase_v2 == "EARLY_TRANSITION")

        # early_candidate: pre-participation / before-the-herd condition
        # Matches add_early_candidate.py from v6 DB build:
        #   MID momentum + NEAR_LOW or MID_RANGE location + EARLY_TRANSITION phase
        early_candidate = int(
            momentum_bucket == "MID"
            and location_bucket in ("MID_RANGE", "NEAR_LOW")
            and phase_v2 == "EARLY_TRANSITION"
        )

        # === 9-DIM MATCH DIMENSIONS ==========================================
        # iv_regime: realized-vol proxy matching enrich_actuarial_9dim.py.
        _vol_regime_str = vol_state['regime']
        _atr_pct_val    = vol_state['atr_percentile']
        if _vol_regime_str == "COMPRESSION":
            iv_regime = "LOW_IV"
        elif _vol_regime_str == "EXPANSION":
            iv_regime = "HIGH_IV"
        elif _atr_pct_val >= 50:
            iv_regime = "ELEVATED_IV"
        else:
            iv_regime = "NORMAL_IV"

        # volume_bucket: derived from relative_volume already in structure_state.
        _rel_vol = structure_state.get('relative_volume', 1.0) or 1.0
        if _rel_vol < 0.7:
            volume_bucket = "LOW"
        elif _rel_vol <= 1.5:
            volume_bucket = "NORMAL"
        elif _rel_vol <= 3.0:
            volume_bucket = "HIGH"
        else:
            volume_bucket = "SPIKE"

        # crabel_state: compression proxy. Override with discovery pipeline value
        # if available (wyckoff_crabel_precor_logic_v2.crabel_compression_state).
        _disc_crabel = (
            getattr(vanguard_input.technical, 'crabel_compression_state', None)
            or getattr(vanguard_input.technical, 'crabel_state', None)
        )
        if _disc_crabel and str(_disc_crabel).upper() in ("CRABEL_READY", "COILING", "NONE"):
            crabel_state = str(_disc_crabel).upper()
        else:
            # Fallback proxy matching enrich_actuarial_9dim.py
            if _vol_regime_str == "COMPRESSION" and adx_bucket == "WEAK":
                crabel_state = "CRABEL_READY"
            elif atr_pct_bucket == "LOW" and adx_bucket in ("WEAK", "MODERATE"):
                crabel_state = "COILING"
            else:
                crabel_state = "NONE"

        # horizon_bucket: routing hint from discovery pipeline; defaults MEDIUM.
        _disc_horizon = getattr(vanguard_input.technical, 'horizon_bucket', None)
        if _disc_horizon and str(_disc_horizon).upper() in ("SHORT", "MEDIUM", "LONG"):
            horizon_bucket = str(_disc_horizon).upper()
        else:
            horizon_bucket = "MEDIUM"
        # =====================================================================

        state_v2 = (
            f"{vol_state['regime']}|{trend_state['direction']}|"
            f"{structure_state['quality']}|{phase_v2}|"
            f"{momentum_bucket}|{location_bucket}"
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
            
            # Bucket discriminators (for actuarial_query Stage 1 filter)
            atr_pct_bucket=atr_pct_bucket,
            adx_bucket=adx_bucket,
            intraday_rows=getattr(vanguard_input, 'intraday_rows', 0),
            # D3 FIX: wyckoff_bucket computed above — must be passed so
            # actuarial_query Stage 1 filter can separate ACCUMULATION from MARKUP.
            wyckoff_phase_bucket=wyckoff_bucket,

            # Schema versioning — written to every signal row for audit traceability
            schema_version=SCHEMA_VERSION,
            bucket_schema_version=BUCKET_SCHEMA_VERSION,

            # Meta
            state_hash=state_hash,
            confidence=confidence,

            # =========================
            # STATE V2 FIELDS
            # =========================
            phase_v2=phase_v2,
            momentum_bucket=momentum_bucket,
            location_bucket=location_bucket,
            momentum_score=momentum_score,
            transition_flag_v2=transition_flag_v2,
            state_v2=state_v2,
            early_candidate=early_candidate,
            positional_strategy=True,

            # =========================
            # 9-DIM MATCH DIMENSIONS
            # =========================
            iv_regime=iv_regime,
            volume_bucket=volume_bucket,
            crabel_state=crabel_state,
            horizon_bucket=horizon_bucket,
        )
        
    def _calculate_volatility_regime(self, tech: 'TechnicalData') -> Dict:
        """
        Determine volatility regime (COMPRESSION, NORMAL, EXPANSION)
        """
        
        # Calculate percentiles
        atr_pct = self._percentile(tech.atr_current, tech.atr_history) if tech.atr_history else 50.0
        # FIX: Use pre-computed atr_percentile_rank from discovery if available.
        # Discovery computes this as a rank vs the ticker's own 60-bar ATR history.
        # This is more accurate than computing it here from atr_history which may be shorter.
        if hasattr(tech, 'atr_percentile_rank') and tech.atr_percentile_rank is not None:
            v = float(tech.atr_percentile_rank)
            if 0.0 <= v <= 100.0:
                atr_pct = v
        bb_pct = self._percentile(tech.bb_width, tech.bb_width_history) if tech.bb_width_history else 50.0
        
        # IV percentile — use options layer ivp_252d if available on tech object.
        # run_vanguard_from_packages wires options intelligence fields into technical_data,
        # so we read from tech here. Hard-coding 50 permanently disables Gate 4
        # IV spike check and distorts vol_regime classification.
        iv_pct = 50.0  # default
        # Try ivp_252d first (most accurate — 252-day lookback)
        if hasattr(tech, 'ivp_252d') and tech.ivp_252d is not None:
            v = tech.ivp_252d
            iv_pct = float(v) * 100.0 if float(v) <= 1.0 else float(v)
        elif hasattr(tech, 'iv_percentile') and tech.iv_percentile is not None:
            iv_pct = float(tech.iv_percentile)
        elif hasattr(tech, 'iv_rank') and tech.iv_rank is not None:
            iv_pct = float(tech.iv_rank)
        
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
        
    def _calculate_trend_maturity(self, tech: 'TechnicalData',
                                   vol_regime: str = 'NORMAL',
                                   wyckoff_phase: str = '') -> Dict:
        """
        Determine trend direction and maturity.

        THRESHOLD SAFETY NOTE (permanent fix):
        late_trend_percent_from_extreme controls when a trend is labelled LATE.
        This feeds directly into the TREND_EXHAUSTED gate in edge_detector.py.
        Safe range: 0.05–0.08 (5%–8% from 52w extreme).
          - Too tight (< 0.03): over-fires, vetoes too many valid setups
          - Too loose (> 0.12): under-fires, lets exhausted trends through
        The fallback below ensures this never silently defaults to 0.

        v2.2.0 — SIDEWAYS sub-classification:
          N/A is no longer emitted. SIDEWAYS tickers are sub-classified as:
            SIDEWAYS_BUILDING — vol_regime=COMPRESSION or wyckoff=ACCUMULATION
                                 Ticker is coiling. EV historically higher on breakout.
            SIDEWAYS_RANGING  — everything else SIDEWAYS.
                                 Ticker is drifting. Treat as lower-confidence.
        """
        
        current_price = tech.ohlcv['close'].iloc[-1] if len(tech.ohlcv) > 0 else 0
        
        # Distance from 52w high/low
        pct_from_high = (current_price - tech.high_52w) / tech.high_52w if tech.high_52w > 0 else 0
        pct_from_low = (current_price - tech.low_52w) / tech.low_52w if tech.low_52w > 0 else 0
        
        # Days since extremes
        days_since_high = (pd.Timestamp.now() - tech.date_52w_high).days if tech.date_52w_high else 365
        days_since_low = (pd.Timestamp.now() - tech.date_52w_low).days if tech.date_52w_low else 365
        
        # === SAFE THRESHOLD RESOLUTION ===
        # Explicit fallback prevents config.py omission from silently breaking gate logic.
        # If late_trend_percent_from_extreme is missing or 0, default to 0.07 (7%).
        late_pct = self.trend_thresholds.get('late_trend_percent_from_extreme', 0.07)
        if not late_pct or late_pct <= 0:
            late_pct = 0.07
        early_days = self.trend_thresholds.get('early_trend_days_from_extreme', 30)
        if not early_days or early_days <= 0:
            early_days = 30
        
        # Direction (using EMA alignment + ADX)
        if tech.ema21 > tech.ema50 and current_price > tech.ema21 and tech.adx > self.trend_thresholds['uptrend_adx_min']:
            direction = "UP"
        elif tech.ema21 < tech.ema50 and current_price < tech.ema21 and tech.adx > self.trend_thresholds['uptrend_adx_min']:
            direction = "DOWN"
        else:
            direction = "SIDEWAYS"
            
        # Maturity
        if direction == "UP":
            if abs(pct_from_high) < late_pct:
                maturity = "LATE"
            elif days_since_high < early_days:
                maturity = "EARLY"
            else:
                maturity = "MIDDLE"
        elif direction == "DOWN":
            if abs(pct_from_low) < late_pct:
                maturity = "LATE"
            elif days_since_low < early_days:
                maturity = "EARLY"
            else:
                maturity = "MIDDLE"
        else:
            maturity = self._sideways_maturity(vol_regime=vol_regime, wyckoff_phase=wyckoff_phase)
            
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

    @staticmethod
    def _sideways_maturity(vol_regime: str = 'NORMAL', wyckoff_phase: str = '') -> str:
        """
        Sub-classify SIDEWAYS tickers into BUILDING or RANGING.

        Called when trend_direction = SIDEWAYS (neither UP nor DOWN by EMA/ADX test).
        Replaces the previous flat 'N/A' maturity label which collapsed all sideways
        tickers to one hash bucket regardless of whether they were coiling for a breakout
        or aimlessly drifting.

        Classification rules (either condition sufficient for BUILDING):
          BUILDING  →  vol_regime == 'COMPRESSION'         (ATR+BB historically tight)
                    OR wyckoff_phase_bucket == 'ACCUMULATION' (Phase A/B/C cause-building)

        Everything else  →  RANGING

        Evidence base (why these signals matter):
          COMPRESSION vol_regime: ticker's ATR and Bollinger Width are in the lowest
            tercile of their 60-bar history. Price is coiling. Statistically, COMPRESSION
            resolves with directional expansion within 5-15 sessions.
          Wyckoff ACCUMULATION (Phase A/B/C): price is testing the spring/shakeout zone
            and volume characteristics suggest institutional absorption. Cause is building.

        DB rebuild implication:
          Historical rows with trend_maturity='N/A' are re-tagged to BUILDING or RANGING
          using the vol_regime and wyckoff_phase_bucket columns already stored in the DB.
          No market data re-fetch is required.

        Schema version: 2.2.0 — first version to emit SIDEWAYS_BUILDING / SIDEWAYS_RANGING.
        """
        v = str(vol_regime or '').strip().upper()
        w = str(wyckoff_phase or '').strip().upper()

        is_compression  = (v == 'COMPRESSION')
        is_accumulation = (
            w in ('ACCUMULATION', 'A', 'B', 'C')
            or any(x in w for x in ('PHASE_A', 'PHASE_B', 'PHASE_C', 'PHASE A', 'PHASE B', 'PHASE C'))
        )

        if is_compression or is_accumulation:
            return 'SIDEWAYS_BUILDING'
        return 'SIDEWAYS_RANGING'

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
            
        # ── Liquidity (volume) — timing-aware ────────────────────────────────────
        # ROOT CAUSE FIX (2026-04-10): Running from the UK means the evening pipeline
        # fires at ~16:00 BST = ~11:00 ET — mid-session in the US market. The last
        # OHLCV bar is a partial intraday bar containing only 2-3 hours of volume
        # against an avg_volume baseline of full 6.5-hour sessions.
        #
        # Example: Stock averaging 2M shares/day has ~700k by 11am ET.
        # relative_volume = 700k / 2000k = 0.35 → classified LOW → OPTIONS veto fires
        # for 76% of the universe — blocking all EXECUTE verdicts.
        #
        # Fix: detect whether the pipeline is running during US market hours and
        # scale current_volume to a projected full-day estimate before classifying.
        # Scaling formula: full_day_estimate = current_volume × (390 / minutes_elapsed)
        # where 390 = total US market minutes (6.5 hours).
        #
        # Detection: if current_volume < 50% of avg_volume AND the UTC clock is in
        # the US session window (13:30–21:00 UTC = 09:30–17:00 ET with DST margin),
        # treat the bar as partial and scale. On genuine low-volume days (holidays,
        # half-days), the scaling will overshoot slightly — acceptable because the
        # alternative is wrongly classifying every name as LOW liquidity.

        from datetime import datetime as _dt, timezone as _tz

        avg_volume = tech.ohlcv['volume'].mean() if len(tech.ohlcv) > 0 else 1
        current_volume = tech.ohlcv['volume'].iloc[-1] if len(tech.ohlcv) > 0 else 0

        _now_utc      = _dt.now(_tz.utc)
        _utc_hour     = _now_utc.hour
        _utc_minute   = _now_utc.minute
        _utc_minutes  = _utc_hour * 60 + _utc_minute

        # US market: 13:30–20:00 UTC (accounts for both EST and EDT)
        _MARKET_OPEN_UTC  = 13 * 60 + 30   # 13:30 UTC
        _MARKET_CLOSE_UTC = 20 * 60          # 20:00 UTC
        _MARKET_TOTAL_MIN = 390              # 6.5 hours = 390 minutes

        _in_session = _MARKET_OPEN_UTC <= _utc_minutes < _MARKET_CLOSE_UTC

        if _in_session and avg_volume > 0 and current_volume < avg_volume * 0.50:
            # Partial day detected — scale to projected full-day volume
            _elapsed_min = max(1, _utc_minutes - _MARKET_OPEN_UTC)
            _scale       = _MARKET_TOTAL_MIN / _elapsed_min
            _adjusted_volume = current_volume * _scale
        else:
            # Market closed or already a full-day bar — use as-is
            _adjusted_volume = current_volume

        relative_volume = _adjusted_volume / avg_volume if avg_volume > 0 else 1.0

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

        # FIX 4: Compute days_since_earnings from calendar data.
        # Hard-coding 90 permanently disables the Gate 4 post-earnings re-entry
        # blackout (0 < days_since <= 3). Three resolution strategies in priority order:
        if hasattr(calendar, 'last_earnings_date') and calendar.last_earnings_date is not None:
            # Best: actual last earnings date available
            days_since = max(0, (pd.Timestamp.now() - pd.Timestamp(calendar.last_earnings_date)).days)
        elif hasattr(calendar, 'days_since_earnings') and calendar.days_since_earnings is not None:
            # Good: field already computed upstream
            days_since = max(0, int(calendar.days_since_earnings))
        else:
            # Proxy: standard ~91-day earnings cycle. If next is 10d away, last was ~81d ago.
            # Not perfect but enables the gate to fire correctly near earnings boundaries.
            days_since = max(0, 91 - int(days_to))

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
            'days_since': days_since,
            'proximity': proximity
        }
        
    def _calculate_macro_regime(self, macro: 'MacroData') -> Dict:
        """
        Overall market regime — ENHANCEMENT 2 (2026-04-16):
        Sub-classify TRANSITIONAL into BULLISH / BEARISH / NEUTRAL variants
        using VIX level, SPY trend, and macro JSON sub-fields where available.

        This doubles actuarial pool precision. TRANSITIONAL was previously
        applied to 100% of signals (run 20260415: all 1,475 candidates),
        meaning regime conditioning provided zero discriminating information.

        Sub-regime mapping:
          RISK_ON                — VIX < 15 and SPY uptrend (unchanged)
          RISK_OFF               — VIX > 25 or SPY downtrend (unchanged)
          TRANSITIONAL_BULLISH   — TRANSITIONAL + SPY above 20d MA + VIX falling
          TRANSITIONAL_BEARISH   — TRANSITIONAL + SPY below 20d MA or VIX rising
          TRANSITIONAL_NEUTRAL   — TRANSITIONAL + mixed signals
        """
        vix_pct = self._percentile(macro.vix, macro.vix_history) if macro.vix_history else 50.0

        # Primary regime (unchanged thresholds)
        if macro.vix < 15 and macro.spy_trend == "UP":
            regime = "RISK_ON"
        elif macro.vix > 25 or macro.spy_trend == "DOWN":
            regime = "RISK_OFF"
        else:
            # ENHANCEMENT 2: sub-classify TRANSITIONAL
            # Use SPY trend and VIX direction as the two split dimensions.
            # vix_history[-1] vs vix_history[-5] detects rising/falling.
            _spy_bullish = (macro.spy_trend == "UP")

            _vix_falling = False
            if macro.vix_history and len(macro.vix_history) >= 5:
                _vix_falling = float(macro.vix) < float(macro.vix_history[-5])

            if _spy_bullish and _vix_falling:
                regime = "TRANSITIONAL_BULLISH"   # tailwind for longs
            elif not _spy_bullish or (macro.vix_history and not _vix_falling and macro.vix > 20):
                regime = "TRANSITIONAL_BEARISH"   # headwind for longs
            else:
                regime = "TRANSITIONAL_NEUTRAL"   # indeterminate

        return {
            'regime': regime,
            'vix_percentile': vix_pct,
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
        
    # ── BUCKET HELPERS ────────────────────────────────────────────────────────

    @staticmethod
    def _adx_bucket(adx: float) -> str:
        """
        Bucket ADX into 3 regimes.
        <20  = weak/no trend
        20-35 = moderate trend
        >35  = strong trend
        """
        if adx < 20:
            return "WEAK"
        elif adx <= 35:
            return "MODERATE"
        else:
            return "STRONG"

    @staticmethod
    def _atr_percentile_bucket(atr_pct: float) -> str:
        """
        Bucket ATR percentile into 3 bands.
        <33  = low volatility
        33-66 = mid volatility
        >66  = high volatility
        """
        if atr_pct < 33:
            return "LOW"
        elif atr_pct <= 66:
            return "MID"
        else:
            return "HIGH"

    @staticmethod
    def _wyckoff_phase_bucket(wyckoff_phase: str) -> str:
        """
        Collapse Wyckoff phases into 3 buckets:
        ACCUMULATION = Phase A, B, C (building cause)
        MARKUP       = Phase D, E  (trend in motion)
        DISTRIBUTION = Distribution / Re-distribution phases

        FIX (2026-03-07): Discovery writes single-letter phases ("A","B","C","D","E").
        Previous code only matched "PHASE_C" / "PHASE C" style strings, so a bare
        "C" fell through to UNKNOWN, collapsing all TRADE rows to one hash bucket.
        Single-letter exact match is now evaluated FIRST.
        """
        if not wyckoff_phase:
            return "UNKNOWN"
        p = str(wyckoff_phase).strip().upper()

        # ── Single-letter exact match (Discovery canonical format) ────────────
        if p in ("A", "B", "C"):
            return "ACCUMULATION"
        if p in ("D", "E"):
            return "MARKUP"

        # ── Long-form / prefixed formats ──────────────────────────────────────
        if any(x in p for x in ["DISTRIBUTION", "REDISTRIBUTION"]):
            return "DISTRIBUTION"
        if any(x in p for x in ["PHASE_D", "PHASE_E", "MARKUP", "PHASE D", "PHASE E"]):
            return "MARKUP"
        if any(x in p for x in ["PHASE_A", "PHASE_B", "PHASE_C", "ACCUMULATION",
                                  "PHASE A", "PHASE B", "PHASE C"]):
            return "ACCUMULATION"
        return "UNKNOWN"

    def _generate_state_hash(self, ticker: str, *states,
                              wyckoff_bucket: str = 'UNKNOWN',
                              macro_regime: str = 'TRANSITIONAL') -> str:
        """
        Generate unique hash for this state combination.

        IMPORTANT: ticker is intentionally excluded from the hash so that
        observations pool across all stocks in the same market state.
        This gives thousands of observations per state combination rather
        than tens, enabling statistically meaningful edge detection.

        Hash components (9 dimensions):
            vol_regime | trend_direction | trend_maturity | structure_quality
            | catalyst_proximity | adx_bucket | atr_pct_bucket
            | wyckoff_phase_bucket | macro_regime   ← NEW

        wyckoff_phase_bucket separates ACCUMULATION (A/B/C) from MARKUP (D/E)
        from DISTRIBUTION — the single most impactful dimension for options buyers.

        macro_regime separates RISK_ON from RISK_OFF historical pools.
        Phase D setups in RISK_ON have materially different win rates than
        Phase D setups in RISK_OFF — they must not be pooled.

        BACKWARD COMPATIBILITY: DB rows without wyckoff_phase_bucket will not
        match Stage 1 filter — actuarial_query falls back to Stage 2 (4-dim).
        Once DB is rebuilt, Stage 1 will match correctly.
        """
        # Core 5 (original)
        adx_bucket = self._adx_bucket(states[1].get('strength', 0))
        atr_bucket = self._atr_percentile_bucket(states[0].get('atr_percentile', 50))

        signature_parts = [
            states[0]['regime'],      # vol_regime
            states[1]['direction'],   # trend_direction
            states[1]['maturity'],    # trend_maturity
            states[2]['quality'],     # structure_quality
            states[4]['proximity'],   # catalyst_proximity
            adx_bucket,               # adx_bucket
            atr_bucket,               # atr_pct_bucket
            wyckoff_bucket,           # wyckoff_phase_bucket  ← NEW
            macro_regime,             # macro_regime          ← NEW
        ]

        signature = "_".join(str(p) for p in signature_parts)
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
