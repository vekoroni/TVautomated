#!/usr/bin/env python3
"""
AVSHUNTER DISCOVERY ULTIMATE v1.0
==================================

COMBINES:
1. v15_fixed full discovery (643+ candidates with tiers/scoring)
2. Enhanced early position detection (50-150 early signals)
3. Crabel/Precor integration (Wyckoff state machine)

TIERS:
- TIER 0 (EARLY): 5-10 days before trigger, enter 33%
- TIER 1 (CONFIRMED): Triggered now, enter 100%
- TIER 2 (OBSERVE): Developing, monitor
- TIER 3 (WATCH): Early stage, low confidence

OUTPUT:
- discovery_candidates_ultimate_<TS>.csv (all signals)
- final_watchlist_ultimate_<TS>.csv (top ranked)
- early_positions_ultimate_<TS>.csv (Tier 0 only)
- discovery_summary_ultimate_<TS>.json

Usage:
    python avshunter_discovery_ULTIMATE.py --universe data/universe/polygon_liquid_universe.csv --force-update
"""

from __future__ import annotations

import argparse
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from WyckoffEngine_3101_v2 import WyckoffEngine_3101_v2 as WyckoffEngine
from polygon_data_fetcher import PolygonDataFetcher
from wyckoff_crabel_precor_logic_v2 import process_precore_signal
try:
    from scripts.macro_quant_packet import (
        build_macro_quant_packet,
        macro_quant_columns_for_row,
        missing_macro_quant_packet,
    )
except Exception:
    from macro_quant_packet import (  # type: ignore
        build_macro_quant_packet,
        macro_quant_columns_for_row,
        missing_macro_quant_packet,
    )

# DISC-01: swing_fusion is the single authority for direction + intent.
# asymmetry_gate_swing computes structural entry/stop/target from shelf geometry.
# Both files exist; previous versions did not import them.
try:
    from swing_fusion import fuse_wyckoff_crabel
    from asymmetry_gate_swing import compute_asymmetry_swing
    from enums_structural import Direction, Intent
    _SWING_FUSION_AVAILABLE = True
except ImportError as _sf_err:
    _SWING_FUSION_AVAILABLE = False
    import logging as _sflog
    _sflog.getLogger("AVSHUNTER_ULTIMATE").warning(
        f"swing_fusion/asymmetry_gate not importable ({_sf_err}) — "
        "direction/intent from WyckoffEngine only, asymmetry geometry skipped"
    )


# ============================= LOGGING =====================================

def setup_logger(level: str) -> logging.Logger:
    logger = logging.getLogger("AVSHUNTER_ULTIMATE")
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    if not logger.handlers:
        ch = logging.StreamHandler()
        ch.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
        logger.addHandler(ch)
    return logger


# ============================= CONFIG ======================================

@dataclass
class UltimateConfig:
    """Enhanced configuration for ULTIMATE discovery"""
    
    # Universe filters
    min_price: float = 5.0
    max_price: float = 500.0
    min_avg_vol20: float = 500_000
    
    # Compression thresholds
    compression_max: float = 0.85          # Max for any compression
    extreme_compression: float = 0.60      # Extreme compression threshold
    
    # EARLY POSITION thresholds (LOOSER than v3.0)
    early_compression_min: float = 0.45    # Lowered from 0.50
    early_compression_max: float = 0.85    # Raised from 0.80
    early_days_in_range_min: int = 3       # Lowered from 5
    early_days_in_range_max: int = 15      # Raised from 10
    early_phase_min: float = 35.0          # Lowered from 40
    early_min_conditions: int = 2          # Lowered from 3
    
    # Tier thresholds
    tier1_min: float = 50.0
    tier2_min: float = 35.0
    tier3_min: float = 25.0
    
    # Data requirements
    min_bars: int = 30

    # Enhancement 4: Options viability proxy filters
    # Options desks trade movement x liquidity, not geometry.
    # Reject structurally interesting but economically useless names.
    min_adv_dollars: float = 2_500_000    # Min avg daily dollar volume (price x vol)
    min_atr_dollars: float = 0.40         # Min ATR in $ terms (options need movement)
    min_atr_pct: float = 1.0              # Min ATR as % of price (1% minimum)

    # Enhancement 5: Regime-adaptive composite floor
    # Markets do not distribute edge evenly. Tighten floors in risk-off.
    # RISK_ON:      standard floor (tier1_min = 50)
    # TRANSITIONAL: 68 floor already in assign_tier
    # RISK_OFF:     raise Tier 1 floor to 72 - only high-conviction setups
    risk_off_composite_floor: float = 72.0


REQUIRED_COLS = {"open", "high", "low", "close", "volume"}


# ============================= INDICATORS ==================================

def ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


def true_range(df: pd.DataFrame) -> pd.Series:
    prev_close = df["close"].shift(1)
    tr = pd.concat([
        (df["high"] - df["low"]),
        (df["high"] - prev_close).abs(),
        (df["low"] - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    return true_range(df).rolling(period).mean()


def adx_14(df: pd.DataFrame, period: int = 14) -> float:
    """Calculate ADX(14) from OHLCV. Returns raw ADX value (0-100)."""
    try:
        high = df['high']
        low = df['low']
        close = df['close']
        tr = pd.concat([
            high - low,
            (high - close.shift(1)).abs(),
            (low - close.shift(1)).abs(),
        ], axis=1).max(axis=1)
        dm_p = high.diff()
        dm_m = -low.diff()
        dm_p = dm_p.where((dm_p > dm_m) & (dm_p > 0), 0.0)
        dm_m = dm_m.where((dm_m > dm_p) & (dm_m > 0), 0.0)
        atr_s = tr.ewm(span=period, adjust=False).mean()
        di_p = 100 * dm_p.ewm(span=period, adjust=False).mean() / atr_s
        di_m = 100 * dm_m.ewm(span=period, adjust=False).mean() / atr_s
        dx = 100 * (di_p - di_m).abs() / (di_p + di_m + 1e-10)
        adx_v = dx.ewm(span=period, adjust=False).mean()
        return round(float(adx_v.iloc[-1]), 2)
    except Exception:
        return 0.0


def atr_percentile_rank(df: pd.DataFrame, period: int = 14, lookback: int = 60) -> float:
    """ATR(14) percentile rank vs the ticker's own last-N-bar ATR history (0-100).
    <25 = genuinely compressed for this stock. This is NOT price-relative %."""
    try:
        high = df['high']
        low = df['low']
        close = df['close']
        tr = pd.concat([
            high - low,
            (high - close.shift(1)).abs(),
            (low - close.shift(1)).abs(),
        ], axis=1).max(axis=1)
        atr_series = tr.rolling(period).mean().dropna()
        hist = atr_series.tail(lookback)
        if len(hist) < 10:
            return 50.0
        current_atr = float(hist.iloc[-1])
        rank = float((hist < current_atr).sum() / len(hist) * 100)
        return round(rank, 1)
    except Exception:
        return 50.0


def catalyst_proximity_bucket(days_to_trigger: float) -> str:
    """Bucket days_to_trigger into catalyst proximity label matching actuarial DB.
    WITHIN_3D  = imminent (strongest signal)
    WITHIN_10D = developing, high proximity
    FAR        = no near-term trigger (default)
    """
    try:
        d = float(days_to_trigger)
    except (TypeError, ValueError):
        return 'FAR'
    if d <= 3:
        return 'WITHIN_3D'
    if d <= 10:
        return 'WITHIN_10D'
    return 'FAR'


def rolling_vwap(df: pd.DataFrame, window: int = 20) -> pd.Series:
    typical_price = (df["high"] + df["low"] + df["close"]) / 3
    return (typical_price * df["volume"]).rolling(window).sum() / df["volume"].rolling(window).sum()


# ============================= TREND MATURITY HELPERS =======================
# Used for intent reconciliation and Intelligence Lab display.
# These resolve the SELL SETUP / BUYERS contradiction and Phase E misclassification.

def _get_dominant_trend(df: pd.DataFrame) -> str:
    """Returns BULLISH / BEARISH / MIXED based on daily EMA stack alignment."""
    try:
        e9  = df['EMA9'].iloc[-1]
        e21 = df['EMA21'].iloc[-1]
        e50 = df['EMA50'].iloc[-1]
        e200 = df['EMA200'].iloc[-1]
        if e9 > e21 > e50 > e200:
            return 'BULLISH'
        if e9 < e21 < e50 < e200:
            return 'BEARISH'
        return 'MIXED'
    except Exception:
        return 'MIXED'


def _get_ema_stack(df: pd.DataFrame) -> str:
    """Returns ALIGNED / MIXED for EMA 9/21/50/200 bullish perfect stack."""
    try:
        e9  = df['EMA9'].iloc[-1]
        e21 = df['EMA21'].iloc[-1]
        e50 = df['EMA50'].iloc[-1]
        e200 = df['EMA200'].iloc[-1]
        return 'ALIGNED' if e9 > e21 > e50 > e200 else 'MIXED'
    except Exception:
        return 'MIXED'


def _days_above_ema50(df: pd.DataFrame) -> int:
    """Counts consecutive bars where close > EMA50 from the most recent bar backwards."""
    try:
        above = (df['close'] > df['EMA50']).astype(int)
        # Walk backwards from most recent
        count = 0
        for v in reversed(above.values):
            if v == 1:
                count += 1
            else:
                break
        return int(count)
    except Exception:
        return 0


def _pct_from_52w_low(df: pd.DataFrame) -> float:
    """Returns % gain from 52-week low to current price."""
    try:
        window = min(252, len(df))
        low_52w = df['low'].tail(window).min()
        px = df['close'].iloc[-1]
        if low_52w <= 0:
            return 0.0
        return round((px - low_52w) / low_52w * 100, 1)
    except Exception:
        return 0.0


def _reconcile_intent(
    raw_intent: str,
    precor_control: str,
    wyckoff_control: str,
    df: pd.DataFrame,
) -> str:
    """
    Reconcile precor_intent against control state to eliminate contradictions.

    Rules (in priority order):
    1. If SELL_SETUP but either control is BUYERS → downgrade to TRANSITION
    2. If BUY_SETUP but either control is SELLERS and dominant trend is BEARISH → downgrade to TRANSITION
    3. If dominant trend is strongly BULLISH (EMA stack + 60+ days above EMA50) and
       intent is SELL_SETUP → override to BUY_SETUP (trend-continuation setup)
    4. Otherwise pass through unchanged.

    The raw intent is always preserved in precor_intent_raw for auditability.
    """
    if not raw_intent:
        return raw_intent

    intent = raw_intent.upper().replace(' ', '_')
    dominant_trend = _get_dominant_trend(df)
    days_above = _days_above_ema50(df)
    pct_from_low = _pct_from_52w_low(df)
    ema_stack = _get_ema_stack(df)

    # Rule 1 — SELL_SETUP with buyer control is a contradiction
    if intent == 'SELL_SETUP':
        if 'BUYER' in precor_control.upper() or 'BUYER' in wyckoff_control.upper():
            return 'TRANSITION'

    # Rule 2 — BUY_SETUP with seller control in a downtrend is suspicious
    if intent == 'BUY_SETUP':
        if ('SELLER' in precor_control.upper() or 'SELLER' in wyckoff_control.upper()):
            if dominant_trend == 'BEARISH':
                return 'TRANSITION'

    # Rule 3 — Strong uptrend override: SELL_SETUP in a mature bull trend → BUY_SETUP
    # This catches AROC-type Phase E continuation stocks
    if intent == 'SELL_SETUP':
        if dominant_trend == 'BULLISH' and ema_stack == 'ALIGNED' and days_above >= 40 and pct_from_low >= 25:
            return 'BUY_SETUP'

    return raw_intent  # pass through unchanged if no rule fires


# ============================= CRABEL COMPRESSION ==========================

def crabel_compression(df: pd.DataFrame, cfg: UltimateConfig) -> Dict:
    """Enhanced Crabel compression detection with universe-relative percentile scoring.

    Enhancement 2: ATR compression is now assessed relative to the stock's own
    60-day ATR history (percentile rank), not just absolute thresholds.
    A compression_ratio of 0.70 means different things for NVDA vs a utility.
    Percentile < 25 = genuinely unusual compression for THIS stock.
    """
    if len(df) < cfg.min_bars:
        return {"passed": False, "reason": "INSUFFICIENT_BARS", "compression": np.nan, "score": 0}
    
    tmp = df[["high", "low", "volume"]].copy()
    tmp["range"] = tmp["high"] - tmp["low"]
    tmp["atr7"] = tmp["range"].rolling(7).mean()
    tmp["atr20"] = tmp["range"].rolling(20).mean()
    tmp["compression"] = tmp["atr7"] / tmp["atr20"]
    
    cur = tmp.iloc[-1]
    comp = float(cur["compression"]) if not pd.isna(cur["compression"]) else np.nan
    
    if pd.isna(comp) or comp > cfg.compression_max:
        return {"passed": False, "reason": "NO_COMPRESSION", "compression": comp, "score": 0}
    
    # Enhancement 2: Universe-relative percentile rank of compression
    # How compressed is this stock vs its own 60-day history?
    comp_series = tmp["compression"].dropna().tail(60)
    if len(comp_series) >= 10:
        comp_pct_rank = float((comp_series < comp).sum() / len(comp_series) * 100)
    else:
        comp_pct_rank = 50.0  # insufficient history — neutral

    # Volume percentile rank (relative dryness vs own history)
    vol_series = df["volume"].tail(60)
    vol_20ma = df["volume"].rolling(20).mean()
    cur_vol_ratio = df["volume"].iloc[-1] / vol_20ma.iloc[-1] if vol_20ma.iloc[-1] > 0 else 1.0
    vol_series_ratios = (df["volume"] / vol_20ma).dropna().tail(60)
    if len(vol_series_ratios) >= 10:
        vol_pct_rank = float((vol_series_ratios < cur_vol_ratio).sum() / len(vol_series_ratios) * 100)
    else:
        vol_pct_rank = 50.0

    # NR7 detection
    tmp["is_nr7"] = tmp["range"] == tmp["range"].rolling(7).min()
    tmp["vol_20ma"] = df["volume"].rolling(20).mean()
    tmp["vol_ratio"] = df["volume"] / tmp["vol_20ma"]
    
    cur = tmp.iloc[-1]
    is_nr7 = bool(cur["is_nr7"]) if not pd.isna(cur.get("is_nr7")) else False
    vol_ratio = float(cur["vol_ratio"]) if not pd.isna(cur.get("vol_ratio")) else 1.0
    
    # Scoring — base score from absolute thresholds (preserved)
    score = 65
    pattern = "Moderate"
    
    if is_nr7 and vol_ratio < 0.8:
        score, pattern = 90, "NR7+LowVol"
    elif is_nr7:
        score, pattern = 75, "NR7"
    elif comp < cfg.extreme_compression:
        score, pattern = 85, "Extreme"

    # Enhancement 2: Percentile bonus — reward genuinely rare compression
    # comp_pct_rank < 25 means this is in the bottom quartile of its own history
    if comp_pct_rank < 15:
        score = min(100, score + 10)  # Extremely rare compression
        pattern = pattern + "+UltraRare"
    elif comp_pct_rank < 25:
        score = min(100, score + 5)   # Unusual compression
        pattern = pattern + "+Rare"

    # Vol dryness bonus — bottom quartile of own vol history
    if vol_pct_rank < 25:
        score = min(100, score + 5)
    
    return {
        "passed": True,
        "reason": "OK",
        "compression": comp,
        "score": score,
        "pattern": pattern,
        "is_nr7": is_nr7,
        "vol_ratio": vol_ratio,
        "comp_pct_rank": round(comp_pct_rank, 1),
        "vol_pct_rank": round(vol_pct_rank, 1),
    }


# ============================= EARLY POSITION DETECTION ====================

def detect_early_position(df: pd.DataFrame, wyckoff_data: dict, precor_data: dict, cfg: UltimateConfig) -> Optional[dict]:
    """
    PURE COMPRESSION EARLY DETECTION - NO WYCKOFF PHASE REQUIRED
    Goal: Catch 50-150 setups BEFORE confirmation (5-10 days early)
    
    KEY: Focuses ONLY on compression + range + volume
    Does NOT wait for Wyckoff phase confirmation (that's Tier 1)
    """
    
    if len(df) < cfg.min_bars:
        return None
    
    # === 1. COMPRESSION BUILDING ===
    atr_series = atr(df, 14)
    atr_current = atr_series.iloc[-1]
    atr_60_avg = atr_series.tail(60).mean()
    
    atr_slope = atr_series.diff(5).iloc[-1]
    compression_building = atr_slope < 0  # ANY decline (removed strict -0.005)
    
    compression_ratio = atr_current / atr_60_avg if atr_60_avg > 0 else 1.0
    compression_in_zone = cfg.early_compression_min < compression_ratio < cfg.early_compression_max
    
    # === 2. RANGE FORMATION ===
    recent = df.tail(30)
    high_level = recent['high'].max()
    low_level = recent['low'].min()
    range_size = high_level - low_level
    
    if range_size == 0:
        return None
    
    tolerance_amt = range_size * 0.20  # 20% tolerance (looser)
    
    days_in_range = 0
    for i in range(len(recent) - 1, -1, -1):
        row = recent.iloc[i]
        near_high = (high_level - row['high']) < tolerance_amt
        near_low = (row['low'] - low_level) < tolerance_amt
        
        if near_high or near_low:
            days_in_range += 1
        else:
            break
    
    range_forming = cfg.early_days_in_range_min <= days_in_range <= cfg.early_days_in_range_max
    
    # === 3. VOLUME DECLINING ===
    vol_ma_5 = df['volume'].rolling(5).mean()
    vol_ma_20 = df['volume'].rolling(20).mean()
    
    volume_declining = (
        vol_ma_5.iloc[-1] < vol_ma_20.iloc[-1] * 0.85  # 85% threshold (looser)
        if not pd.isna(vol_ma_5.iloc[-1]) and not pd.isna(vol_ma_20.iloc[-1])
        else False
    )
    
    # === 4. PRICE STABILITY (NEW) ===
    recent_5 = df.tail(5)
    price_range_5d = (recent_5['high'].max() - recent_5['low'].min())
    avg_price = recent_5['close'].mean()
    
    price_stable = (price_range_5d / avg_price) < 0.10 if avg_price > 0 else False  # <10% range
    
    # === 5. CRABEL/PRECOR BONUS (OPTIONAL) ===
    crabel_bonus = 0
    crabel_state = 'NONE'
    
    if precor_data:
        crabel_state = precor_data.get('crabel_compression_state', 'NONE')
        control_state = precor_data.get('control_state', 'EQUILIBRIUM')
        
        if crabel_state in ['COILING', 'CRABEL_READY']:
            crabel_bonus = 15
        
        if control_state in ['BUYERS', 'SELLERS']:
            crabel_bonus += 10
    
    # === 6. CALCULATE SCORE (NO WYCKOFF PHASE) ===
    score = 0
    conditions = []
    
    if compression_building and compression_in_zone:
        score += 35
        conditions.append("compression")
    
    if range_forming:
        score += 30
        conditions.append("range")
    
    if volume_declining:
        score += 25
        conditions.append("volume_dry")
    
    if price_stable:
        score += 10
        conditions.append("price_stable")
    
    score += crabel_bonus
    if crabel_bonus > 0:
        conditions.append("crabel_bonus")
    
    # === 7. DECISION - 2 of 4 base conditions + score >= 50 ===
    base_conditions = ["compression", "range", "volume_dry", "price_stable"]
    base_met = sum(1 for c in conditions if c in base_conditions)
    
    # Qualify if: 2+ base conditions AND score >= 50
    if base_met >= 2 and score >= 50:
        
        current_price = float(df['close'].iloc[-1])
        stop_loss = current_price * 0.97
        
        # Estimate days to trigger based on compression
        if compression_ratio < 0.55:
            days_to_trigger = 3
        elif compression_ratio < 0.65:
            days_to_trigger = 5
        elif compression_ratio < 0.75:
            days_to_trigger = 8
        else:
            days_to_trigger = 10
        
        # Get phase for info only (NOT required)
        phase = str(wyckoff_data.get('current_phase', 'UNKNOWN')).upper()
        phase_strength = float(wyckoff_data.get('phase_evidence_strength', 0))
        
        if precor_data:
            precor_phase = precor_data.get('wyckoff_phase', '')
            precor_phase_conf = precor_data.get('wyckoff_phase_conf', 0.0)
            if precor_phase and precor_phase_conf > phase_strength:
                phase = precor_phase
                phase_strength = precor_phase_conf
        
        return {
            'tier': 0,  # Integer for tier_counts
            'tier_label': 'TIER_0_EARLY',
            'signal_type': 'EARLY_POSITION',
            'entry_size': 0.33,
            'entry_price': round(current_price, 2),
            'stop_loss': round(stop_loss, 2),
            'stop_pct': 3.0,
            'days_in_range': days_in_range,
            'days_to_trigger': days_to_trigger,
            'compression_ratio': round(compression_ratio, 3),
            'early_formation_score': score,
            'conditions_met': conditions,
            'base_conditions_count': base_met,
            'phase': phase,
            'phase_strength': round(phase_strength, 1),
            'crabel_state': crabel_state,
            'control_state': precor_data.get('control_state', 'UNKNOWN') if precor_data else 'UNKNOWN',
        }
    
    return None


# ============================= TIER ASSIGNMENT =============================

def assign_tier(wyckoff_score: float, crabel_score: float, composite_score: float, cfg: UltimateConfig) -> int:
    """Assign tier based on scores with regime-adaptive floors.

    Regime composite floors (Enhancement 5):
        RISK_OFF:     >= 72 for Tier 1 (high conviction only — edge is scarce)
        TRANSITIONAL: >= 68 for Tier 1 (existing logic preserved)
        RISK_ON:      >= 50 standard (broader opportunity set)

    Markets do not distribute edge evenly across regimes. Enforcing scarcity
    discipline in RISK_OFF prevents psychological noise from marginal setups.
    """
    active_regime = str(getattr(cfg, 'active_regime', 'UNKNOWN')).upper()
    transitional_floor = 68.0
    risk_off_floor = getattr(cfg, 'risk_off_composite_floor', 72.0)

    if composite_score >= cfg.tier1_min:
        if active_regime == 'RISK_OFF' and composite_score < risk_off_floor:
            return 2  # Demote: below RISK_OFF conviction threshold
        if active_regime == 'TRANSITIONAL' and composite_score < transitional_floor:
            return 2  # Demote: below TRANSITIONAL conviction threshold
        return 1
    elif composite_score >= cfg.tier2_min:
        return 2
    elif composite_score >= cfg.tier3_min:
        return 3
    else:
        return 4  # Rejected

# NOTE: Tier 3 (WATCH) — valid overflow bucket in RISK_OFF regimes.
# In RISK_ON/TRANSITIONAL: structural dead zone — DISTRIBUTION stocks penalised below T4,
#   non-DISTRIBUTION stocks boosted above T2. Nothing scores in the T3 band.
# In RISK_OFF: ACCUMULATION/MARKUP stocks receive +10/+12 prior boosts. Stocks with raw
#   scores ~39-41 land at ~51-53 adjusted — above T3 floor but below the elevated T2 floor (54).
#   These are genuine early-stage setups in a fearful market. T3 is a valid watch bucket.


def calculate_composite_score(wyckoff_score: float, crabel_score: float) -> float:
    """Calculate composite score"""
    
    if crabel_score > 0:
        # Both Wyckoff + Crabel
        return (wyckoff_score * 0.6) + (crabel_score * 0.4)
    else:
        # Wyckoff only
        return wyckoff_score


def calculate_win_probability(wyckoff_score: float, crabel_score: float) -> float:
    """Estimate win probability"""
    
    composite = calculate_composite_score(wyckoff_score, crabel_score)
    
    # Base probability from composite score
    base_prob = 40.0 + (composite * 0.25)
    
    # Cap at realistic levels
    return min(75.0, max(35.0, base_prob))


# ============================= STATE PRIOR WEIGHTING =======================

# Empirically derived from 3.7M cleaned actuarial observations.
# Key: (wyckoff_phase_bucket, macro_regime) → score adjustment
# Source: validate_enrichment.py output — Hit +10% / 20d rates by bucket × regime
#
# Baseline (mixed pool):       Hit10 = 28.8%
# MARKUP       × RISK_ON  :   Hit10 = 25.7%  → slight penalty vs baseline (already late)
# MARKUP       × RISK_OFF :   Hit10 = 30.2%  → boost (breakout against weak market = strong)
# MARKUP       × TRANS    :   Hit10 = 26.0%  → neutral
# ACCUMULATION × RISK_ON  :   Hit10 = 20.4%  → penalty (still building cause)
# ACCUMULATION × RISK_OFF :   Hit10 = 33.8%  → strong boost (cause building in adversity)
# ACCUMULATION × TRANS    :   Hit10 = 27.1%  → slight boost
# DISTRIBUTION × RISK_ON  :   Hit10 = 18.9%  → strong penalty
# DISTRIBUTION × RISK_OFF :   Hit10 = 22.0%  → penalty
# DISTRIBUTION × TRANS    :   Hit10 = 17.6%  → strong penalty
#
# Score adjustments are bounded: max +15, min -20
# Applied to composite_score BEFORE tier assignment so tier floors remain meaningful.

_STATE_PRIOR_ADJUSTMENTS: dict = {
    ('MARKUP',       'RISK_ON'):      +2.0,   # slight: already extended
    ('MARKUP',       'RISK_OFF'):    +10.0,   # strong: breakout vs weak market
    ('MARKUP',       'TRANSITIONAL'): +1.0,   # neutral
    ('ACCUMULATION', 'RISK_ON'):      -5.0,   # penalty: still building cause
    ('ACCUMULATION', 'RISK_OFF'):    +12.0,   # strongest signal in the DB
    ('ACCUMULATION', 'TRANSITIONAL'): +3.0,   # slight boost
    ('DISTRIBUTION', 'RISK_ON'):     -15.0,   # strong penalty: rolling over in bull
    ('DISTRIBUTION', 'RISK_OFF'):    -12.0,   # penalty: rolling over in bear
    ('DISTRIBUTION', 'TRANSITIONAL'):-12.0,  # strong penalty: only negative EV bucket
}

# Late trend maturity penalty — applied additionally when trend is LATE/EXHAUSTED
# in non-RISK_OFF regime (RISK_OFF late trend can still spring)
_LATE_TREND_PENALTY = -8.0


def _wyckoff_phase_to_bucket(phase: str) -> str:
    """
    Map Wyckoff sub-phase to granular bucket preserving setup completeness.

    Wyckoff sub-phases represent distinct structural locations with different
    probability profiles. Collapsing A, B, C → 'ACCUMULATION' loses the most
    important information: Phase C (spring/test) is the highest-probability
    entry in the entire cycle. Phase A is still supply exhaustion with no
    confirmation — categorically different from Phase C.

    This is the granular bucket used for setup quality scoring.
    The broad bucket (ACCUMULATION/MARKUP/DISTRIBUTION) is preserved separately
    for actuarial DB state hash backward compatibility.

      ACCUMULATION_EARLY   — Phase A/B: cause building, no spring yet
      ACCUMULATION_SPRING  — Phase C: spring or test confirmed (highest edge)
      MARKUP_ENTRY         — Phase D: sign of strength / last point of support
      MARKUP_CONTINUATION  — Phase E: markup underway
      DISTRIBUTION_EARLY   — Distribution A/B: buying exhaustion forming
      DISTRIBUTION_UTAD    — Distribution C: UTAD (highest PUT edge, mirrors spring)
      MARKDOWN             — Distribution D/E or confirmed decline
      UNKNOWN              — Insufficient evidence
    """
    p = str(phase).upper().strip()
    if p == 'A':                          return 'ACCUMULATION_EARLY'
    if p == 'B':                          return 'ACCUMULATION_EARLY'
    if p == 'C':                          return 'ACCUMULATION_SPRING'
    if p == 'D':                          return 'MARKUP_ENTRY'
    if p == 'E':                          return 'MARKUP_CONTINUATION'
    if 'DIST' in p and 'C' in p:          return 'DISTRIBUTION_UTAD'
    if 'DIST' in p:                       return 'DISTRIBUTION_EARLY'
    if 'MARKDOWN' in p or 'MARK_DOWN' in p: return 'MARKDOWN'
    return 'UNKNOWN'


def _normalise_event(raw: str) -> str:
    """
    Normalise dominant_event string to canonical uppercase form.
    Handles case variation, aliases, and missing values.
    Defect 3 fix: raw values may arrive as 'spring', 'SPRING', 'Spring',
    'Test_of_Spring' etc. All normalised here before use in scoring sets.
    """
    e = str(raw or 'TR').strip().upper().replace(' ', '_').replace('-', '_')
    aliases = {
        'SPRING':          'SPRING',
        'TEST':            'TEST',
        'TEST_OF_SPRING':  'TEST_OF_SPRING',
        'ST':              'TEST',           # Secondary Test alias
        'SOS':             'SOS',
        'SOW':             'SOW',
        'LPS':             'LPS',
        'LPSY':            'LPSY',
        'UTAD':            'UTAD',
        'UPTHRUST':        'UPTHRUST',
        'UT':              'UPTHRUST',        # Upthrust alias
        'SC':              'SC',
        'BC':              'BC',
        'AR':              'AR',
        'TR':              'TR',
        'NONE':            'TR',
        '':                'TR',
        'ABSORPTION_UP':   'AR',
        'ABSORPTION_DOWN': 'AR',
        'TREND_CONTINUATION': 'TR',
    }
    return aliases.get(e, e)


def _event_family(event_norm: str) -> str:
    """Map normalised event to broad family for Vanguard state routing."""
    bullish_rev   = {'SPRING', 'TEST_OF_SPRING', 'TEST'}
    bullish_cont  = {'SOS', 'LPS'}
    accum_press   = {'SC', 'AR'}
    bearish_rev   = {'UTAD', 'UPTHRUST'}
    bearish_cont  = {'SOW', 'LPSY'}
    dist_press    = {'BC'}
    if event_norm in bullish_rev:   return 'BULLISH_REVERSAL'
    if event_norm in bullish_cont:  return 'BULLISH_CONTINUATION'
    if event_norm in accum_press:   return 'ACCUMULATION_PRESSURE'
    if event_norm in bearish_rev:   return 'BEARISH_REVERSAL'
    if event_norm in bearish_cont:  return 'BEARISH_CONTINUATION'
    if event_norm in dist_press:    return 'DISTRIBUTION_PRESSURE'
    return 'RANGE_NEUTRAL'


def _dominant_event_bucket(event_norm: str) -> str:
    """Coarse bucket for actuarial state key."""
    HIGH = {'SPRING', 'UTAD', 'SOS', 'SOW', 'TEST_OF_SPRING'}
    MED  = {'TEST', 'LPS', 'LPSY', 'SC', 'BC', 'UPTHRUST', 'AR'}
    if event_norm in HIGH: return 'CONFIRMED_EVENT'
    if event_norm in MED:  return 'SECONDARY_EVENT'
    return 'RANGE_ONLY'


def _bucket_event_evidence(val: float) -> str:
    if val >= 80: return 'EXTREME'
    if val >= 60: return 'HIGH'
    if val >= 40: return 'MEDIUM'
    return 'LOW'


def _bucket_truth_confidence(val: float) -> str:
    if val >= 80: return 'ELITE'
    if val >= 60: return 'STRONG'
    if val >= 45: return 'ACCEPTABLE'
    return 'WEAK'


def _bucket_move_age(val) -> str:
    if val is None: return 'UNKNOWN'
    try:
        v = int(val)
        if v <= 2:  return 'FRESH'
        if v <= 5:  return 'ACTIVE'
        if v <= 10: return 'DEVELOPING'
        if v <= 20: return 'MATURE'
        return 'STALE'
    except (TypeError, ValueError):
        return 'UNKNOWN'


def _bucket_crabel(score: float, pattern: str = '') -> str:
    """
    Map crabel_score (0–100) and pattern to named compression bucket.
    RARE_COMPRESSION and ULTRA_RARE_COMPRESSION reserved for extreme events.
    """
    pat = str(pattern or '').upper()
    if score >= 90 or 'ULTRA' in pat:    return 'ULTRA_RARE_COMPRESSION'
    if score >= 71 or 'NR7+LOWVOL' in pat: return 'RARE_COMPRESSION'
    if score >= 57:                       return 'READY'
    if score >= 28:                       return 'COILING'
    if score > 0:                         return 'NONE'
    return 'NONE'


def _bar_days_old_safe(df) -> int:
    """
    Safely compute bar_data_days_old from df.attrs.
    Defect 2 fix: extracted from inline dict expression to named function.
    Returns 999 on any failure so downstream stale-check is safe.
    """
    try:
        data_as_of = str(getattr(df, 'attrs', {}).get('data_as_of', '') or '')
        if data_as_of in ('', 'UNKNOWN', 'None', 'nan'):
            return 999
        from datetime import date as _date
        return max(0, (_date.today() - _date.fromisoformat(data_as_of[:10])).days)
    except Exception:
        return 999


def _wyckoff_phase_to_broad_bucket(phase: str) -> str:
    """
    Broad bucket for actuarial DB state hash — backward compatible.
    Used for wyckoff_phase_bucket field only (do not use for scoring).
    """
    p = str(phase).upper().strip()
    if p in ('D', 'E'):    return 'MARKUP'
    if p in ('A', 'B', 'C'): return 'ACCUMULATION'
    if 'DIST' in p:        return 'DISTRIBUTION'
    if 'MARKDOWN' in p:    return 'MARKDOWN'
    return 'UNKNOWN'


def apply_state_prior_adjustment(
    composite_score: float,
    phase: str,
    active_regime: str,
    trend_maturity: str = '',
    data_as_of: str = '',   # E1: YYYY-MM-DD — decay penalises stale signals
) -> tuple:
    """
    Apply empirically-derived state prior adjustment to composite score.

    Returns:
        (adjusted_composite: float, prior_adj: float, prior_label: str)

    The adjustment is bounded to prevent extreme distortion:
        max boost: +15 points
        max penalty: -20 points

    This injects known historical asymmetry into Discovery WITHOUT querying
    the actuarial DB at runtime. The priors are pre-computed from 3.7M rows.
    """
    bucket  = _wyckoff_phase_to_bucket(phase)
    regime  = str(active_regime).upper().strip()

    # Map regime aliases
    if regime in ('RISK_ON', 'BULL', 'BULLISH'):
        regime = 'RISK_ON'
    elif regime in ('RISK_OFF', 'BEAR', 'BEARISH'):
        regime = 'RISK_OFF'
    else:
        regime = 'TRANSITIONAL'

    key = (bucket, regime)
    adj = _STATE_PRIOR_ADJUSTMENTS.get(key, 0.0)

    # Additional late trend penalty in non-RISK_OFF regimes
    maturity = str(trend_maturity).upper()
    if maturity in ('LATE', 'EXHAUSTED') and regime != 'RISK_OFF':
        adj += _LATE_TREND_PENALTY

    # Bound the adjustment
    adj = max(-20.0, min(+15.0, adj))

    adjusted = composite_score + adj

    # Human-readable label for output column — defined BEFORE decay block
    # so the decay suffix can safely append to it.
    if adj > 5:
        label = f"BOOSTED({bucket}×{regime}:{adj:+.0f})"
    elif adj < -5:
        label = f"PENALISED({bucket}×{regime}:{adj:+.0f})"
    else:
        label = f"NEUTRAL({bucket}×{regime}:{adj:+.0f})"

    # ── ENHANCEMENT 1: Signal decay (2026-04-16) ─────────────────────────────
    # Wyckoff phases have a half-life. A Phase C spring identified on Monday
    # can be a Phase D breakout by Wednesday — the original signal becomes a
    # late entry at full premium. Penalise composite by 3% per day of staleness
    # so fresh signals always rank above identical stale ones.
    # At 1 day stale: -3%.  At 3 days: -9%.  At 5 days: -15% (floor at -20%).
    try:
        from datetime import date as _date_cls
        if data_as_of:
            _data_dt  = _date_cls.fromisoformat(str(data_as_of)[:10])
            _days_old = max(0, (_date_cls.today() - _data_dt).days)
            _decay    = min(_days_old * 0.03, 0.20)   # 3%/day, cap 20%
            adjusted  = adjusted * (1.0 - _decay)
            if _days_old > 0:
                label = label + f"|DECAY-{_days_old}d({_decay*100:.0f}%)"
    except Exception:
        pass  # never block on date parsing failure

    return round(adjusted, 1), round(adj, 1), label


# ============================= DATA LOADING ================================

def load_universe(csv_path: Path) -> List[str]:
    df = pd.read_csv(csv_path)
    if "ticker" not in df.columns:
        raise ValueError("Universe CSV must have 'ticker' column")
    return df["ticker"].astype(str).str.upper().str.strip().dropna().unique().tolist()


def load_bars(
    data_dir: Path,
    ticker: str,
    polygon_fetcher: Optional[PolygonDataFetcher],
    force_update: bool,
    lookback_days: int,
) -> Optional[pd.DataFrame]:
    """
    Load OHLCV bars for a ticker.

    Returns a DataFrame with an extra attrs key:
      df.attrs["data_source"]  — "POLYGON_FRESH" | "STALE_CACHE" | "CACHE_OK"
      df.attrs["data_as_of"]   — ISO date string of the last bar, or "UNKNOWN"

    This metadata flows into the signal dict so the orchestrator can report
    how many tickers used stale data on any given run.
    """
    csv_path = data_dir / f"{ticker}.csv"

    if not force_update and csv_path.exists():
        try:
            df = pd.read_csv(csv_path)
            df.columns = [c.lower().strip() for c in df.columns]

            if not REQUIRED_COLS.issubset(df.columns):
                return None

            if "date" in df.columns:
                df["date"] = pd.to_datetime(df["date"], errors="coerce")
                latest_date = df["date"].max()
                if pd.notna(latest_date):
                    days_old = (datetime.now() - latest_date).days
                    if days_old <= 7:
                        df = df.sort_values("date")
                        df.attrs["data_source"] = "CACHE_OK"
                        df.attrs["data_as_of"] = str(latest_date.date())
                        return df
        except Exception as e:
            logging.getLogger("AVSHUNTER_ULTIMATE").debug(f"[{ticker}] CSV staleness check failed: {e}")

    if polygon_fetcher:
        try:
            end_date = datetime.now().strftime('%Y-%m-%d')
            start_date = (datetime.now() - timedelta(days=lookback_days)).strftime('%Y-%m-%d')

            df = polygon_fetcher.fetch_daily_bars(ticker, start_date, end_date)

            if df is not None and not df.empty:
                data_dir.mkdir(parents=True, exist_ok=True)
                df.to_csv(csv_path, index=False)
                # Tag as fresh Polygon data
                last_date = "UNKNOWN"
                try:
                    if "date" in df.columns:
                        last_date = str(pd.to_datetime(df["date"], errors="coerce").max().date())
                except Exception:
                    pass
                df.attrs["data_source"] = "POLYGON_FRESH"
                df.attrs["data_as_of"] = last_date
                return df
        except Exception as e:
            logging.getLogger("AVSHUNTER_ULTIMATE").debug(f"[{ticker}] Polygon fetch failed: {e}")

    # ── STALE FALLBACK — Polygon failed, use whatever cache exists ──────────
    # Tag explicitly so downstream can count stale tickers.
    if csv_path.exists():
        try:
            df = pd.read_csv(csv_path)
            df.columns = [c.lower().strip() for c in df.columns]
            if REQUIRED_COLS.issubset(df.columns):
                last_date = "UNKNOWN"
                try:
                    if "date" in df.columns:
                        last_date = str(pd.to_datetime(df["date"], errors="coerce").max().date())
                except Exception:
                    pass
                df.attrs["data_source"] = "STALE_CACHE"
                df.attrs["data_as_of"] = last_date
                logging.getLogger("AVSHUNTER_ULTIMATE").debug(
                    f"[{ticker}] Using STALE_CACHE fallback — last bar: {last_date}"
                )
                return df
        except Exception as e:
            logging.getLogger("AVSHUNTER_ULTIMATE").debug(f"[{ticker}] Fallback CSV read failed: {e}")

    return None


# ============================= SECTOR LOOKUP ===============================
# Priority: ticker override dict → sector_map.csv (built once) → SIC fallback
# Zero API calls at runtime. sector_map.csv is built once via Polygon reference API.

_TICKER_OVERRIDES: Dict[str, Tuple[str, str]] = {
    # (sector, industry) — add your regulars here
    "ABT":  ("Healthcare",           "Medical Devices"),
    "MMM":  ("Industrials",          "Conglomerates"),
    "FXI":  ("ETF",                  "China Large-Cap ETF"),
    "SYY":  ("Consumer Staples",     "Food Distribution"),
    "PAGP": ("Energy",               "Oil & Gas Pipelines"),
    "AMZN": ("Consumer Discretionary","E-Commerce & Cloud"),
    "AAPL": ("Technology",           "Consumer Electronics"),
    "MSFT": ("Technology",           "Enterprise Software"),
    "NVDA": ("Technology",           "Semiconductors"),
    "TSLA": ("Consumer Discretionary","Electric Vehicles"),
    "META": ("Communication Services","Social Media"),
    "GOOGL":("Communication Services","Internet Services"),
    "JPM":  ("Financials",           "Diversified Banks"),
    "BAC":  ("Financials",           "Diversified Banks"),
    "XOM":  ("Energy",               "Integrated Oil & Gas"),
}

# SIC code → (sector, industry) covering ~95% of US equity universe
_SIC_MAP: Dict[str, Tuple[str, str]] = {
    "01": ("Consumer Staples",      "Agriculture"),
    "07": ("Consumer Staples",      "Agriculture Services"),
    "10": ("Materials",             "Mining"),
    "12": ("Energy",                "Coal Mining"),
    "13": ("Energy",                "Oil & Gas Exploration"),
    "14": ("Materials",             "Nonmetallic Minerals"),
    "15": ("Industrials",           "Building Construction"),
    "16": ("Industrials",           "Heavy Construction"),
    "17": ("Industrials",           "Construction Trades"),
    "20": ("Consumer Staples",      "Food & Beverages"),
    "21": ("Consumer Staples",      "Tobacco"),
    "22": ("Consumer Discretionary","Textiles"),
    "23": ("Consumer Discretionary","Apparel"),
    "24": ("Materials",             "Lumber & Wood"),
    "25": ("Consumer Discretionary","Furniture"),
    "26": ("Materials",             "Paper & Packaging"),
    "27": ("Communication Services","Printing & Publishing"),
    "28": ("Healthcare",            "Pharmaceuticals & Chemicals"),
    "29": ("Energy",                "Petroleum Refining"),
    "30": ("Materials",             "Rubber & Plastics"),
    "31": ("Consumer Discretionary","Leather Goods"),
    "32": ("Materials",             "Stone, Clay & Glass"),
    "33": ("Materials",             "Primary Metals"),
    "34": ("Industrials",           "Fabricated Metal Products"),
    "35": ("Technology",            "Industrial Machinery"),
    "36": ("Technology",            "Electronics & Electrical Equipment"),
    "37": ("Consumer Discretionary","Motor Vehicles & Parts"),
    "38": ("Healthcare",            "Medical Instruments"),
    "39": ("Consumer Discretionary","Miscellaneous Manufacturing"),
    "40": ("Industrials",           "Railroads"),
    "41": ("Industrials",           "Transit & Ground Transport"),
    "42": ("Industrials",           "Trucking & Warehousing"),
    "44": ("Industrials",           "Water Transportation"),
    "45": ("Industrials",           "Airlines"),
    "46": ("Energy",                "Pipelines"),
    "47": ("Industrials",           "Transportation Services"),
    "48": ("Communication Services","Telecommunications"),
    "49": ("Utilities",             "Electric, Gas & Sanitary Services"),
    "50": ("Industrials",           "Wholesale Durable Goods"),
    "51": ("Consumer Staples",      "Wholesale Non-Durable Goods"),
    "52": ("Consumer Discretionary","Building Materials Retail"),
    "53": ("Consumer Discretionary","General Merchandise Retail"),
    "54": ("Consumer Staples",      "Food & Drug Retail"),
    "55": ("Consumer Discretionary","Auto Dealers & Service"),
    "56": ("Consumer Discretionary","Apparel Retail"),
    "57": ("Consumer Discretionary","Home Furnishings Retail"),
    "58": ("Consumer Discretionary","Eating & Drinking"),
    "59": ("Consumer Staples",      "Miscellaneous Retail"),
    "60": ("Financials",            "Depository Institutions"),
    "61": ("Financials",            "Non-Depository Credit"),
    "62": ("Financials",            "Security & Commodity Brokers"),
    "63": ("Financials",            "Insurance"),
    "64": ("Financials",            "Insurance Agents"),
    "65": ("Real Estate",           "Real Estate"),
    "67": ("Financials",            "Holding & Investment Companies"),
    "70": ("Consumer Discretionary","Hotels & Lodging"),
    "72": ("Consumer Discretionary","Personal Services"),
    "73": ("Technology",            "Business & Computer Services"),
    "75": ("Consumer Discretionary","Auto Repair & Services"),
    "76": ("Industrials",           "Miscellaneous Repair Services"),
    "78": ("Communication Services","Motion Picture Production"),
    "79": ("Communication Services","Amusement & Recreation"),
    "80": ("Healthcare",            "Health Services"),
    "82": ("Consumer Discretionary","Educational Services"),
    "83": ("Consumer Discretionary","Social Services"),
    "86": ("Industrials",           "Membership Organisations"),
    "87": ("Industrials",           "Engineering & Management Services"),
    "99": ("Industrials",           "Nonclassifiable Establishments"),
}

# Cache for sector_map.csv if present
_sector_map_cache: Optional[Dict[str, Tuple[str, str]]] = None

def _load_sector_map(base_dir: Path) -> Dict[str, Tuple[str, str]]:
    """Load sector_map.csv once and cache. Returns empty dict if not present."""
    global _sector_map_cache
    if _sector_map_cache is not None:
        return _sector_map_cache
    csv_path = base_dir / "data" / "sector_map.csv"
    _sector_map_cache = {}
    if csv_path.exists():
        try:
            df_sm = pd.read_csv(csv_path, dtype=str)
            for _, row in df_sm.iterrows():
                t = str(row.get("ticker", "")).strip().upper()
                s = str(row.get("sector", "")).strip()
                ind = str(row.get("industry", "")).strip()
                if t:
                    _sector_map_cache[t] = (s, ind)
        except Exception:
            pass
    return _sector_map_cache


# Enriched universe sector lookup — populated once from polygon_liquid_universe.csv
_universe_sector_lookup: Dict[str, Dict[str, str]] = {}

def _build_universe_sector_lookup(universe_path: Path) -> None:
    """
    Populate _universe_sector_lookup from the enriched universe CSV.
    Keys: uppercase ticker. Values: dict with sector, sector_etf, industry, macro_abstain.
    No-op and silent if file is missing or lacks sector columns.
    """
    global _universe_sector_lookup
    _universe_sector_lookup = {}
    try:
        df_u = pd.read_csv(universe_path, dtype=str, low_memory=False)
        if "ticker" not in df_u.columns:
            return
        for _, row in df_u.iterrows():
            t = str(row.get("ticker", "") or "").strip().upper()
            if t:
                _universe_sector_lookup[t] = {
                    "sector":        str(row.get("sector",        "") or ""),
                    "sector_etf":    str(row.get("sector_etf",    "") or ""),
                    "industry":      str(row.get("industry",      "") or ""),
                    "macro_abstain": str(row.get("macro_abstain", "False") or "False"),
                }
    except Exception:
        pass


def get_sector(ticker: str, sic_code: str = "", base_dir: Optional[Path] = None) -> Tuple[str, str]:
    """
    Return (sector, industry) for a ticker.
    Priority: hardcoded override → sector_map.csv → SIC prefix → unknown.
    """
    t = ticker.strip().upper()

    # 1. Hardcoded overrides — instant, zero I/O
    if t in _TICKER_OVERRIDES:
        return _TICKER_OVERRIDES[t]

    # 2. sector_map.csv — built once via Polygon reference API
    if base_dir is not None:
        sm = _load_sector_map(base_dir)
        if t in sm:
            return sm[t]

    # 3. SIC code prefix fallback
    if sic_code:
        sic_str = str(sic_code).strip().zfill(4)
        for prefix_len in (2, 1):
            prefix = sic_str[:prefix_len]
            if prefix in _SIC_MAP:
                return _SIC_MAP[prefix]

    return ("Unknown", "Unknown")


# ============================= MAIN SCAN LOGIC =============================

def scan_ticker_ultimate(
    ticker: str,
    df: pd.DataFrame,
    cfg: UltimateConfig,
    wyckoff_engine: WyckoffEngine,
) -> Optional[dict]:
    """
    ULTIMATE scan combining v15 + early detection + Crabel/Precor
    """
    
    if len(df) < cfg.min_bars:
        return None
    
    # Add EMAs
    for span in [9, 21, 50, 200]:
        df[f"EMA{span}"] = ema(df["close"], span)
    
    # Liquidity filters (basic — price and volume)
    last = df.iloc[-1]
    px = float(last["close"])
    
    if not (cfg.min_price <= px <= cfg.max_price):
        return None
    
    vol20 = df["volume"].tail(20).mean()
    if vol20 < cfg.min_avg_vol20:
        return None

    # Enhancement 4: Options viability proxy filters
    # Reject names that are structurally interesting but economically useless for options.
    atr_14_series = atr(df, 14)
    atr_14_val = float(atr_14_series.iloc[-1]) if not pd.isna(atr_14_series.iloc[-1]) else 0.0
    atr_pct_val = (atr_14_val / px * 100) if px > 0 else 0.0
    adv_dollars = px * vol20  # avg daily dollar volume

    if adv_dollars < cfg.min_adv_dollars:
        return None  # Insufficient dollar liquidity for options
    if atr_14_val < cfg.min_atr_dollars:
        return None  # Insufficient dollar movement
    if atr_pct_val < cfg.min_atr_pct:
        return None  # Insufficient percentage movement
    
    # === WYCKOFF ANALYSIS ===
    wyckoff_data = wyckoff_engine.analyze(ticker, df, trend_context="UNKNOWN")
    wyckoff_score = float(wyckoff_data.get('wyckoff_score', 0))
    
    # === CRABEL/PRECOR ANALYSIS ===
    precor_data = None
    try:
        precor_data = process_precore_signal(ticker, df)
    except Exception as e:
        logging.getLogger("AVSHUNTER_ULTIMATE").debug(f"[{ticker}] precor signal failed: {e}")
    
    # === CRABEL COMPRESSION ===
    crabel_result = crabel_compression(df, cfg)
    crabel_score = crabel_result.get('score', 0)

    # DISC-01: Run swing_fusion — single authority for direction + intent.
    # Fuses Wyckoff phase/operator/control with Crabel compression state.
    # Outputs: direction, intent, alignment_score, contradictions, fusion_rule_fired.
    # These supplement (not replace) wyckoff_score and crabel_score in tier assignment.
    fusion_result = {}
    asymmetry_result = {}
    if _SWING_FUSION_AVAILABLE:
        try:
            fusion_result = fuse_wyckoff_crabel(
                wyckoff  = wyckoff_data,
                crabel   = crabel_result,
                precor   = precor_data,
            )
            # Asymmetry gate: structural entry/stop/target from shelf geometry.
            # Only runs when fusion has a LONG or SHORT direction.
            _fuse_dir = fusion_result.get('direction', 'NONE')
            if _fuse_dir in ('LONG', 'SHORT'):
                asymmetry_result = compute_asymmetry_swing(
                    direction     = _fuse_dir,
                    crabel_result = crabel_result,
                    df_daily      = df,
                    cfg           = cfg,
                )
        except Exception as _fe:
            logging.getLogger("AVSHUNTER_ULTIMATE").debug(
                f"[{ticker}] swing_fusion error: {_fe}"
            )
    early_signal = detect_early_position(df, wyckoff_data, precor_data, cfg)
    
    # === COMPOSITE SCORING ===
    composite_score = calculate_composite_score(wyckoff_score, crabel_score)
    win_probability = calculate_win_probability(wyckoff_score, crabel_score)

    # Enhancement 1: State Prior Weighting
    # Inject empirically-derived regime x phase priors into composite score
    # BEFORE tier assignment so tier floors remain meaningful.
    active_regime = str(getattr(cfg, 'active_regime', 'UNKNOWN'))
    phase_raw = str(wyckoff_data.get('current_phase', '')).upper()
    if precor_data:
        precor_ph = precor_data.get('wyckoff_phase', '')
        precor_conf = precor_data.get('wyckoff_phase_conf', 0.0)
        wyckoff_conf = float(wyckoff_data.get('phase_evidence_strength', 0))
        if precor_ph and float(precor_conf) > wyckoff_conf:
            phase_raw = str(precor_ph).upper()

    trend_mat = str(wyckoff_data.get('trend_maturity', '')).upper()
    composite_adjusted, prior_adj, prior_label = apply_state_prior_adjustment(
        composite_score, phase_raw, active_regime, trend_mat,
        data_as_of=str(getattr(df, 'attrs', {}).get('data_as_of', '') or ''),  # E1: signal decay
    )

    # DISC-02: VMS composite adjustment.
    # VMS GO score ≥ 75 → +5 pts (IV and compression confirmed by scanner).
    # VMS PROBE score 60-74 → +2 pts (moderate confirmation).
    # VMS WAIT / BLOCK → no adjustment (do not penalise — scanner may be stale).
    # Applied to composite_adjusted so it compounds with state prior.
    _vms_ctx = getattr(cfg, 'vms_context', {})
    _vms_ticker_data = _vms_ctx.get(ticker, {})
    _vms_score    = int(_vms_ticker_data.get('vms_score',    0) or 0)
    _vms_decision = str(_vms_ticker_data.get('vms_decision', '') or '').upper()
    _scanner_source = str(_vms_ticker_data.get('scanner_source', '') or '')
    _scanner_signal_type = str(
        _vms_ticker_data.get('scanner_signal_type')
        or _vms_ticker_data.get('scanner_decision')
        or _vms_decision
        or ''
    ).upper()
    if _vms_decision == 'GO' and _vms_score >= 75:
        composite_adjusted = min(100.0, composite_adjusted + 5.0)
        prior_label = prior_label + '+VMS_GO'
    elif _vms_decision == 'PROBE' and _vms_score >= 60:
        composite_adjusted = min(100.0, composite_adjusted + 2.0)
        prior_label = prior_label + '+VMS_PROBE'

    # Enhancement 3: Conditional Lift Proxy Score
    # Combines compression strength, phase alignment, regime alignment,
    # trend maturity, and volatility expansion potential.
    # Weights derived from empirical Hit10 differentials in actuarial DB.
    phase_bucket         = _wyckoff_phase_to_broad_bucket(phase_raw)   # actuarial DB state hash
    phase_bucket_granular = _wyckoff_phase_to_bucket(phase_raw)        # setup quality scoring
    regime_norm  = 'RISK_ON' if 'ON' in active_regime.upper() else (
                   'RISK_OFF' if 'OFF' in active_regime.upper() else 'TRANSITIONAL')

    # Component 1: Compression strength (0-1 scale, lower ratio = stronger compression)
    comp_ratio = crabel_result.get('compression', 0.85) or 0.85
    comp_strength = max(0.0, min(1.0, (0.85 - float(comp_ratio)) / 0.85))

    # ── EVIDENCE-DRIVEN SCORING ──────────────────────────────────────────────
    # All scoring components now driven by what the Wyckoff and Crabel engines
    # actually measured — not by phase label alone.
    #
    # The core insight: a Spring at Phase C with truth_confidence=85 and
    # confirmed event_evidence is measurably more actionable than Phase C with
    # truth_confidence=31 and dominant_event=TR. The label is the same.
    # The evidence is not.
    #
    # Direction plays no role in any scoring component below.
    # A strong DISTRIBUTION setup scores identically to a strong ACCUMULATION
    # setup of the same evidence quality. Contract selection decides CALL/PUT.

    # ── Pull all engine evidence fields ──────────────────────────────────────
    _truth_conf      = float(wyckoff_data.get('truth_confidence',        50.0) or 50.0)
    _dom_event_raw   = str(wyckoff_data.get('dominant_event',            'TR') or 'TR').strip()
    _dom_event_norm  = _normalise_event(_dom_event_raw)   # D3 fix: canonical uppercase
    _dom_event       = _dom_event_norm                    # alias used throughout
    _event_ev_str    = float(wyckoff_data.get('event_evidence_strength', 0.0) or 0.0)
    _phase_ev_str    = float(wyckoff_data.get('phase_evidence_strength', 0.0) or 0.0)
    _exec_bias       = str(wyckoff_data.get('execution_bias',      'OBSERVE_ONLY') or 'OBSERVE_ONLY')
    _wyk_trans_to    = str(wyckoff_data.get('transition_bias',           '') or '')
    _wyk_trans_conf  = float(wyckoff_data.get('transition_confidence',   0.0) or 0.0)
    _wyk_setup_qual  = str(wyckoff_data.get('setup_quality',       'Observe') or 'Observe')

    _crabel_score_raw = 0.0
    _move_age_bars    = None
    _precor_trans_to  = ''
    _precor_trans_conf= 0.0
    _wyckoff_mode     = 'UNKNOWN'
    if precor_data:
        _crabel_score_raw = float(precor_data.get('crabel_score',         0.0) or 0.0)
        _move_age_bars    = precor_data.get('move_age_bars')
        _precor_trans_to  = str(precor_data.get('transition_to',          '') or '')
        _precor_trans_conf= float(precor_data.get('transition_conf',      0.0) or
                                  precor_data.get('transition_confidence', 0.0) or 0.0)
        _wyckoff_mode     = str(precor_data.get('wyckoff_mode',           'UNKNOWN') or 'UNKNOWN')

    # ── Component 2: Phase quality score — evidence-convergence driven ────────
    #
    # Formula:
    #   truth_confidence      30%  — engine's honest self-assessment
    #   event_evidence        25%  — how strong is the specific event
    #   phase_evidence        20%  — how strong is the phase reading
    #   event_quality_bonus    +fixed  — Spring/UTAD/SOS/SOW >> TR
    #   recency_score         15%  — how fresh is the event (move_age_bars)
    #   transition_alignment  10%  — is structure progressing toward actionable phase
    #
    # Regime modulation: RISK_OFF +5pts, RISK_ON +2pts (conviction, not direction)

    # Event quality bonus — confirmed specific events vs generic trading range
    # D4 fix: use uppercase sets — _dom_event is now normalised uppercase
    _HIGH_QUALITY_EVENTS = {'SPRING', 'UTAD', 'SOS', 'SOW', 'TEST_OF_SPRING'}
    _MED_QUALITY_EVENTS  = {'TEST', 'LPS', 'LPSY', 'SC', 'BC', 'UPTHRUST', 'AR'}
    if _dom_event in _HIGH_QUALITY_EVENTS:
        _event_bonus = 15.0   # confirmed break-and-reclaim or breakout with follow-through
    elif _dom_event in _MED_QUALITY_EVENTS:
        _event_bonus = 8.0    # secondary test or absorption evidence
    else:
        _event_bonus = 0.0    # TR or NONE — observing the range only

    # Recency score — move_age_bars: 0-2 bars = maximum freshness, 20+ bars = stale
    if _move_age_bars is not None:
        try:
            _age = int(_move_age_bars)
            if _age <= 2:    _recency = 1.0
            elif _age <= 5:  _recency = 0.8
            elif _age <= 10: _recency = 0.6
            elif _age <= 20: _recency = 0.4
            else:            _recency = 0.2
        except (TypeError, ValueError):
            _recency = 0.5
    else:
        _recency = 0.5  # unknown age — neutral

    # Transition alignment — is the structure heading toward Phase C or D?
    # Both engines agree: much stronger signal
    _actionable_phases = {'C', 'D'}
    _wyk_trans_actionable  = _wyk_trans_to.upper() in _actionable_phases
    _pre_trans_actionable  = _precor_trans_to.upper() in _actionable_phases
    _avg_trans_conf = (_wyk_trans_conf + _precor_trans_conf) / 2.0
    if _wyk_trans_actionable and _pre_trans_actionable:
        _trans_score = min(1.0, _avg_trans_conf / 100.0)  # both agree → full transition score
    elif _wyk_trans_actionable or _pre_trans_actionable:
        _trans_score = min(1.0, _avg_trans_conf / 100.0) * 0.6  # one agrees → partial
    else:
        _trans_score = 0.3  # neither pointing to actionable phase

    # Phase convergence — do both engines agree on the phase?
    _wyk_phase_raw  = str(wyckoff_data.get('current_phase', '')).upper().strip()
    _pre_phase_raw  = str(precor_data.get('wyckoff_phase', '') if precor_data else '').upper().strip()
    _phase_adjacent = {
        'A': {'A', 'B'}, 'B': {'A', 'B', 'C'}, 'C': {'B', 'C', 'D'},
        'D': {'C', 'D', 'E'}, 'E': {'D', 'E'}
    }
    if _wyk_phase_raw and _pre_phase_raw:
        if _wyk_phase_raw == _pre_phase_raw:
            _convergence_score = 1.0   # both engines identical phase
        elif _pre_phase_raw in _phase_adjacent.get(_wyk_phase_raw, set()):
            _convergence_score = 0.7   # adjacent phases — broadly consistent
        else:
            _convergence_score = 0.4   # diverged — one sees accumulation, one sees distribution
    else:
        _convergence_score = 0.6       # only one engine ran

    # Assemble phase_align (0–1 scale, normalised to 100 then /100)
    _pa_raw = (
        (_truth_conf / 100.0)  * 30.0 +
        (_event_ev_str / 100.0) * 25.0 +
        (_phase_ev_str / 100.0) * 20.0 +
        _event_bonus            +           # flat points for confirmed events
        (_recency               * 15.0) +
        (_trans_score           * 10.0)
    )
    # _pa_raw is now on 0–100 scale (max = 30+25+20+15+15+10 = 115)
    # Normalise to 0-1
    _pa_normalised = min(1.0, _pa_raw / 100.0)

    # Regime modulates conviction (not direction) — small boost for clean macro backdrop
    _regime_boost = {'RISK_OFF': 0.05, 'RISK_ON': 0.02}.get(regime_norm, 0.0)
    phase_align = round(min(1.0, _pa_normalised + _regime_boost), 3)

    # Derive candidate direction — metadata only, NOT used in any scoring component.
    _fuse_dir_raw = str(fusion_result.get('direction', 'NONE')).upper()
    _wyck_dir_raw = str(wyckoff_data.get('trade_direction', 'NONE')).upper()
    if _fuse_dir_raw in ('LONG', 'BULLISH'):
        _candidate_direction = 'CALL'
    elif _fuse_dir_raw in ('SHORT', 'BEARISH'):
        _candidate_direction = 'PUT'
    elif _wyck_dir_raw == 'LONG':
        _candidate_direction = 'CALL'
    elif _wyck_dir_raw == 'SHORT':
        _candidate_direction = 'PUT'
    elif phase_bucket in ('DISTRIBUTION', 'MARKDOWN'):
        _candidate_direction = 'PUT'
    else:
        _candidate_direction = 'CALL'

    # ── Component 3: Regime alignment — macro clarity score ──────────────────
    # Not direction-biased. Measures how clear the macro backdrop is for any move.
    # RISK_OFF = clearest directional moves historically. TRANSITIONAL = murky.
    regime_scores = {'RISK_ON': 0.6, 'RISK_OFF': 0.75, 'TRANSITIONAL': 0.45}
    regime_align  = regime_scores.get(regime_norm, 0.5)

    # ── Component 4: Trend maturity ────────────────────────────────────────────
    if trend_mat in ('EARLY', 'EMERGING'):
        maturity_score = 1.0
    elif trend_mat in ('DEVELOPING', 'MID'):
        maturity_score = 0.7
    elif trend_mat in ('LATE', 'EXHAUSTED'):
        maturity_score = 0.2
    else:
        maturity_score = 0.5

    # ── Component 5: Crabel compression quality ───────────────────────────────
    # Replaced comp_pct_rank (ATR percentile) with crabel_score — the actual
    # NR7/NR4/ATR-compression/inside-bar quality score from the state machine.
    # 0 = no compression, 100 = maximum compression (NR7 + ATR contracted + inside bars)
    vol_expansion_potential = min(1.0, _crabel_score_raw / 100.0)

    # ENHANCEMENT 3: Macro sector tilt alignment (2026-04-16)
    # The macro intelligence JSON scores each sector ETF (XLK, XLF, XLI, etc.)
    # with a signal: LEAD_LONG (+1.0), LONG (+0.5), NEUTRAL (0), REDUCE (-0.5).
    # Map the ticker's sector to its ETF and apply the regime score as a
    # 6th lift component. This surfaces signals in macro-favoured sectors
    # (currently XLK Tech, XLI Industrials, XLF Financials = LEAD_LONG)
    # and suppresses those fighting the macro tide (XLE Energy = REDUCE).
    # NOTE: _sector_etf_map is defined AFTER get_sector() below because
    # _sector must be assigned before it can be looked up here.
    # A placeholder is used so lift_proxy_score can be computed in one place.
    _sector_lift_placeholder = 0.0   # replaced after get_sector() below

    lift_proxy_score = round(
        (comp_strength           * 28.0) +
        (phase_align             * 19.0) +
        (regime_align            * 19.0) +
        (maturity_score          * 19.0) +
        (vol_expansion_potential *  9.0) +
        ((_sector_lift_placeholder + 1.0) / 2.0 * 6.0),
        1
    )

    # Use adjusted composite for tier assignment
    composite_for_tier = composite_adjusted
    
    # === TIER ASSIGNMENT ===
    if early_signal:
        tier = 0  # EARLY
        tier_label = "TIER_0_EARLY"
    else:
        tier = assign_tier(wyckoff_score, crabel_score, composite_for_tier, cfg)
        tier_label = f"TIER_{tier}"
    
    # Skip rejected tickers (tier 4)
    if tier == 4 and not early_signal:
        return None
    
    # === CALCULATE INDICATORS ===
    # atr_14_val already computed above for options viability check
    atr_14 = atr_14_val
    # Compute adx_14 and atr_percentile_rank for state hash dims 6-7
    adx_14_val = adx_14(df)
    atr_pct_rank = atr_percentile_rank(df)
    vwap = rolling_vwap(df, 20).iloc[-1]
    vwap_bias = "ABOVE" if px > vwap else "BELOW"
    vol_ratio = df['volume'].iloc[-1] / vol20 if vol20 > 0 else 1.0

    # ── SPRINT A: Abnormal Repricing Fields ──────────────────────────────────
    # All computed from bars already in memory — no API calls, no new data.
    # These feed the expanded lift_proxy_score_v2 and repricing labels.

    # 1. gap_pct — overnight gap as % of previous close
    _prev_close = float(df['close'].iloc[-2]) if len(df) >= 2 else px
    _open_today = float(df['open'].iloc[-1]) if 'open' in df.columns else px
    gap_pct = round((_open_today - _prev_close) / _prev_close * 100, 3) if _prev_close > 0 else 0.0

    # 2. range_pct — today's intraday range as % of price
    _high_today = float(df['high'].iloc[-1]) if 'high' in df.columns else px
    _low_today  = float(df['low'].iloc[-1])  if 'low'  in df.columns else px
    range_pct = round((_high_today - _low_today) / px * 100, 3) if px > 0 else 0.0

    # 3. range_expansion_vs_20d — today's range vs 20-day average range (normalised)
    _range_series = (df['high'] - df['low']).tail(21)
    _avg_range_20d = float(_range_series.iloc[:-1].mean()) if len(_range_series) >= 2 else (_high_today - _low_today)
    range_expansion_vs_20d = round((_high_today - _low_today) / _avg_range_20d, 3) if _avg_range_20d > 0 else 1.0

    # 4. dollar_volume_zscore — today's dollar volume vs 20d mean, in standard deviations
    _dv_series = (df['close'] * df['volume']).tail(21)
    _dv_today  = float(_dv_series.iloc[-1])
    _dv_20d    = _dv_series.iloc[:-1]
    _dv_mean   = float(_dv_20d.mean()) if len(_dv_20d) >= 5 else _dv_today
    _dv_std    = float(_dv_20d.std())  if len(_dv_20d) >= 5 else 1.0
    dollar_volume_zscore = round((_dv_today - _dv_mean) / _dv_std, 3) if _dv_std > 0 else 0.0

    # 5. vwap_acceptance_score — 0.0 to 1.0, direction-aware.
    # For CALL: gap up + holding above VWAP = institutional buying acceptance.
    # For PUT:  gap down + holding below VWAP = institutional selling acceptance.
    # Score measures alignment between gap direction and VWAP positioning
    # relative to the candidate's trade direction.
    _gap_dir_up  = gap_pct > 0
    _vwap_above  = px > vwap

    if _candidate_direction == 'CALL':
        if _gap_dir_up and _vwap_above:
            vwap_acceptance_score = 1.0   # gap up + above VWAP = strong CALL acceptance
        elif not _gap_dir_up and not _vwap_above:
            vwap_acceptance_score = 0.2   # gap down + below VWAP = wrong direction for CALL
        elif _gap_dir_up and not _vwap_above:
            vwap_acceptance_score = 0.3   # gap up but below VWAP = fading — weak CALL
        else:
            vwap_acceptance_score = 0.6   # gap down but above VWAP = recovery — moderate CALL
    else:  # PUT
        if not _gap_dir_up and not _vwap_above:
            vwap_acceptance_score = 1.0   # gap down + below VWAP = strong PUT acceptance
        elif _gap_dir_up and _vwap_above:
            vwap_acceptance_score = 0.2   # gap up + above VWAP = wrong direction for PUT
        elif not _gap_dir_up and _vwap_above:
            vwap_acceptance_score = 0.3   # gap down but above VWAP = recovering — weak PUT
        else:
            vwap_acceptance_score = 0.6   # gap up but below VWAP = exhaustion — moderate PUT

    # repricing_direction: is the abnormal repricing aligned with the candidate direction?
    _gap_aligned = (
        (_candidate_direction == 'CALL' and _gap_dir_up) or
        (_candidate_direction == 'PUT'  and not _gap_dir_up)
    )
    repricing_direction = _candidate_direction if _gap_aligned else f"COUNTER_{_candidate_direction}"

    # ── Sub-scores for repricing labels (0–1 each) ───────────────────────────
    _gap_score_raw    = min(abs(gap_pct) / 5.0, 1.0)          # 5% gap = full score
    _vol_score_raw    = min(max(vol_ratio - 1.0, 0.0) / 2.0, 1.0)  # 3× avg = full score
    _range_score_raw  = min(max(range_expansion_vs_20d - 1.0, 0.0) / 1.5, 1.0)  # 2.5× = full
    _dv_score_raw     = min(max(dollar_volume_zscore, 0.0) / 3.0, 1.0)  # 3σ = full score

    # Abnormal repricing composite (0–100) — used for labels only.
    # Trend shift proxy: use _get_dominant_trend (BULLISH/BEARISH/MIXED).
    # Defect 1 fix: _get_ema_stack returns ALIGNED/MIXED only — BEARISH never fired.
    dominant_trend = _get_dominant_trend(df)

    _ema_aligned = (
        (_candidate_direction == 'CALL' and dominant_trend == 'BULLISH') or
        (_candidate_direction == 'PUT'  and dominant_trend == 'BEARISH')
    )
    abnormal_repricing_score = round(
        (_gap_score_raw   * 20.0) +
        (_vol_score_raw   * 20.0) +
        (_range_score_raw * 15.0) +
        (vwap_acceptance_score * 15.0) +
        (_dv_score_raw    * 10.0) +
        (vol_expansion_potential * 10.0) +
        ((1.0 if _ema_aligned else 0.3) * 10.0),
        1
    )

    # Repricing state
    if abnormal_repricing_score >= 75:
        repricing_state = "EXTREME"
    elif abnormal_repricing_score >= 60:
        repricing_state = "ACTIVE"
    elif abnormal_repricing_score >= 45:
        repricing_state = "WATCH"
    else:
        repricing_state = "NORMAL"

    # Repricing reason codes
    _repr_reasons = []
    if abs(gap_pct) >= 1.5:              _repr_reasons.append("GAP_SHOCK")
    if vol_ratio >= 2.5:                 _repr_reasons.append("RVOL_SPIKE")
    if range_expansion_vs_20d >= 1.8:    _repr_reasons.append("RANGE_EXPANSION")
    if vwap_acceptance_score >= 0.8:     _repr_reasons.append("VWAP_ACCEPTANCE")
    if vwap_acceptance_score <= 0.3 and abs(gap_pct) > 0.5: _repr_reasons.append("VWAP_REJECTION")
    if dollar_volume_zscore >= 2.0:      _repr_reasons.append("LIQUIDITY_SURGE")
    if vol_expansion_potential >= 0.7:   _repr_reasons.append("VOL_DISPLACEMENT")
    repricing_reason_codes = "|".join(_repr_reasons) if _repr_reasons else "NONE"

    # ── END SPRINT A Fields ──────────────────────────────────────────────────   # === BUILD OUTPUT ===

    # DISC-01 / FIX-01: Structural stop/target hierarchy:
    #   1. asymmetry_gate (shelf geometry, R≥2.0)   — most precise
    #   2. Wyckoff initial_target / stop_loss        — structural range levels
    #   3. ATR fallback                              — last resort
    current_price = round(px, 2)

    _use_asymmetry = (
        _SWING_FUSION_AVAILABLE
        and asymmetry_result.get('asymmetry_pass', False)
        and asymmetry_result.get('stop') is not None
    )

    if _use_asymmetry:
        structural_stop   = round(float(asymmetry_result['stop']),    2)
        structural_target = round(float(asymmetry_result['target1']), 2)
        stop_loss         = structural_stop
        _stop_source      = 'ASYMMETRY_GATE'
        _target_source    = 'ASYMMETRY_GATE'
    else:
        _wyckoff_stop   = wyckoff_data.get('stop_loss')
        _wyckoff_target = wyckoff_data.get('initial_target')
        if _wyckoff_stop is not None:
            _ws = float(_wyckoff_stop)
            _valid_stop = (current_price * 0.75) <= _ws <= (current_price * 1.25)
        else:
            _valid_stop = False
        if _valid_stop:
            structural_stop = round(float(_wyckoff_stop), 2)
            stop_loss       = structural_stop
            _stop_source    = 'WYCKOFF'
        else:
            _atr_stop_dist  = max(atr_14 * 1.5, current_price * 0.02)
            structural_stop = round(current_price - _atr_stop_dist, 2)
            stop_loss       = structural_stop
            _stop_source    = 'ATR_FALLBACK'
        _trade_dir = str(wyckoff_data.get('trade_direction', 'NONE')).upper()
        if _wyckoff_target is not None:
            _wt = float(_wyckoff_target)
            _valid_target = (
                (_trade_dir == 'LONG'  and _wt > current_price) or
                (_trade_dir == 'SHORT' and _wt < current_price) or
                (_trade_dir == 'NONE'  and abs(_wt - current_price) / max(current_price, 0.01) < 0.30)
            )
        else:
            _valid_target = False
        if _valid_target:
            structural_target = round(float(_wyckoff_target), 2)
            _target_source    = 'WYCKOFF'
        else:
            structural_target = None
            _target_source    = 'PENDING_OI'

    # Sector / industry lookup — SIC code comes from universe CSV if present
    _sic = ""
    _base_dir = Path(__file__).resolve().parent
    try:
        _sic = str(df.attrs.get("sic_code", "")) if hasattr(df, "attrs") else ""
    except Exception:
        pass
    _sector, _industry = get_sector(ticker, _sic, _base_dir)

    # Universe sector lookup — wins over SIC fallback when available (Step 3)
    _univ_sec = _universe_sector_lookup.get(ticker, {})
    if _univ_sec:
        _sector   = _univ_sec.get("sector",   "") or _sector
        _industry = _univ_sec.get("industry", "") or _industry

    # ENHANCEMENT 3: Macro sector tilt — recompute lift_proxy_score now that
    # _sector is defined. Placed HERE because _sector must exist first.
    _sector_etf_map = {
        "Technology":             "XLK",
        "Industrials":            "XLI",
        "Financials":             "XLF",
        "Materials":              "XLB",
        "Consumer Discretionary": "XLY",
        "Healthcare":             "XLV",
        "Utilities":              "XLU",
        "Consumer Staples":       "XLP",
        "Real Estate":            "XLRE",
        "Energy":                 "XLE",
        "Communication Services": "XLC",
    }
    _etf_signal_score = {
        "LEAD_LONG":          1.0,
        "LONG":               0.5,
        "NEUTRAL":            0.0,
        "NEUTRAL_DEFENSIVE":  0.0,
        "REDUCE_TACTICAL":   -0.5,
        "AVOID":             -1.0,
    }
    _macro_sector_tilt = getattr(cfg, 'macro_sector_signals', {})
    _ticker_etf  = _sector_etf_map.get(_sector, '')
    _etf_signal  = _macro_sector_tilt.get(_ticker_etf, 'NEUTRAL')
    _sector_lift = _etf_signal_score.get(str(_etf_signal).upper(), 0.0)

    # If universe has explicit sector_etf, use it and recompute lift
    if _univ_sec.get("sector_etf"):
        _ticker_etf  = _univ_sec["sector_etf"]
        _etf_signal  = _macro_sector_tilt.get(_ticker_etf, "NEUTRAL")
        _sector_lift = _etf_signal_score.get(str(_etf_signal).upper(), 0.0)
    _macro_abstain = str(_univ_sec.get("macro_abstain", "False")).upper() == "TRUE"

    # Recompute lift_proxy_score with real sector lift (replaces placeholder above)
    # lift_proxy_score_v3 — evidence-convergence driven, direction-neutral.
    #
    # Component                    Weight   What it captures
    # comp_strength                  20     Crabel NR7/ATR compression → coiled energy
    # phase_align                    20     Evidence-driven setup quality (truth_conf + events)
    # regime_align                   10     Macro backdrop clarity (not direction)
    # maturity_score                 12     Trend maturity (early = higher options edge)
    # vol_expansion_potential        10     Crabel score — NR7/ATR/inside-bar quality
    # sector_lift                     6     Macro sector tilt
    # volume_abnormality             10     Institutional activity (vol vs 20d avg)
    # range_expansion                 6     Range vs 20d average (momentum displacement)
    # vwap_acceptance                 4     Gap × VWAP alignment
    # convergence                     2     Both engines agree on phase (bonus)
    # Total                         100
    _vol_abn = min(max(vol_ratio - 1.0, 0.0) / 2.0, 1.0)
    _rng_exp = min(max(range_expansion_vs_20d - 1.0, 0.0) / 1.5, 1.0)

    lift_proxy_score = round(
        (comp_strength             * 20.0) +
        (phase_align               * 20.0) +
        (regime_align              * 10.0) +
        (maturity_score            * 12.0) +
        (vol_expansion_potential   * 10.0) +
        ((_sector_lift + 1.0) / 2.0 *  6.0) +
        (_vol_abn                  * 10.0) +
        (_rng_exp                  *  6.0) +
        (vwap_acceptance_score     *  4.0) +
        (_convergence_score        *  2.0),
        1
    )
    
    # Get phase (use Precor if stronger, else Wyckoff)
    phase = str(wyckoff_data.get('current_phase', '')).upper()
    phase_strength = float(wyckoff_data.get('phase_evidence_strength', 0))

    if precor_data:
        precor_phase = precor_data.get('wyckoff_phase', '')
        precor_phase_conf = precor_data.get('wyckoff_phase_conf', 0.0)
        if precor_phase and precor_phase_conf > phase_strength:
            phase = precor_phase
            phase_strength = precor_phase_conf

    # ── Pre-dict computations (D2 fix — extracted from inline dict) ──────────
    # Stale data detection — used in candidate_lane and bar_data fields
    _bar_days_old_val  = _bar_days_old_safe(df)
    _data_source_attr  = str(getattr(df, 'attrs', {}).get('data_source', 'UNKNOWN') or 'UNKNOWN').upper()
    _data_asof_attr    = str(getattr(df, 'attrs', {}).get('data_as_of', 'UNKNOWN') or 'UNKNOWN')
    _is_stale          = _data_source_attr == 'STALE_CACHE' or _bar_days_old_val > 5

    # Candidate lane — computed cleanly outside dict (D2 fix)
    if _is_stale:
        _candidate_lane = 'SUPPRESSED'
    elif abnormal_repricing_score >= 55 and lift_proxy_score >= 40:
        _candidate_lane = 'HYBRID'
    elif abnormal_repricing_score >= 60:
        _candidate_lane = 'REPRICING'
    else:
        _candidate_lane = 'STRUCTURE'

    # Bucket fields for Vanguard contract (D5 + Section 6)
    _dom_event_bucket     = _dominant_event_bucket(_dom_event_norm)
    _event_fam            = _event_family(_dom_event_norm)
    _event_evidence_bkt   = _bucket_event_evidence(_event_ev_str)
    _truth_conf_bkt       = _bucket_truth_confidence(_truth_conf)
    _move_age_bkt         = _bucket_move_age(_move_age_bars)
    _crabel_bkt           = _bucket_crabel(_crabel_score_raw, crabel_result.get('pattern', ''))

    signal = {
        'ticker': ticker,
        'tier': tier,
        'tier_label': tier_label,
        'stock_price': current_price,
        'entry_price': current_price,
        # DISC-01 / FIX-01: structural stop — from asymmetry gate, Wyckoff, or ATR fallback
        'stop_loss':               structural_stop,
        'structural_stop':         structural_stop,
        'structural_stop_source':  _stop_source,
        'structural_target':       structural_target,
        'structural_target_source':_target_source,
        'wyckoff_entry_trigger':   str(wyckoff_data.get('entry_trigger', '') or ''),
        # rr_underlying = structural price R:R (computed below); rr = alias
        'phase': phase,
        
        # Scores
        'wyckoff_score': round(wyckoff_score, 1),
        'crabel_score': round(crabel_score, 1),
        'composite_score': round(composite_score, 1),          # raw (pre-prior)
        'composite_adjusted': round(composite_for_tier, 1),    # Enhancement 1: post-prior
        'prior_adjustment': prior_adj,                         # Enhancement 1: delta applied
        'prior_label': prior_label,                            # Enhancement 1: human label
        'lift_proxy_score': lift_proxy_score,                  # Enhancement 3 + Sprint A v2: 9-component ranking score
        # ── SPRINT A: Abnormal Repricing & Candidate Lane ─────────────────
        'gap_pct':                   gap_pct,
        'range_pct':                 range_pct,
        'range_expansion_vs_20d':    range_expansion_vs_20d,
        'dollar_volume_zscore':      dollar_volume_zscore,
        'vwap_acceptance_score':     round(vwap_acceptance_score, 3),
        'abnormal_repricing_score':  abnormal_repricing_score,
        'repricing_state':           repricing_state,
        'repricing_reason_codes':    repricing_reason_codes,
        'repricing_direction':       repricing_direction,  # CALL/PUT/COUNTER_CALL/COUNTER_PUT
        # candidate_lane — computed before dict (D2 fix, no inline date parsing)
        'candidate_lane':         _candidate_lane,
        # ── Vanguard bucket contract (D5 + Section 6) ─────────────────────────
        # These are the clean bucketed fields Vanguard state keys will use.
        # Do not add to actuarial hash yet — use as features and fallback dims.
        'dominant_event_norm':      _dom_event_norm,
        'dominant_event_bucket':    _dom_event_bucket,
        'event_family':             _event_fam,
        'event_evidence_bucket':    _event_evidence_bkt,
        'truth_confidence_bucket':  _truth_conf_bkt,
        'move_age_bucket':          _move_age_bkt,
        'crabel_bucket':            _crabel_bkt,

        # Canonical stale / data-quality fields for Vanguard, EIL, MVE and Intelligence Lab.
        'bar_data_days_old':        _bar_days_old_val,
        'bar_data_asof':            _data_asof_attr,
        'data_source':              _data_source_attr,
        'is_stale':                 bool(_is_stale),
        'win_probability': round(win_probability, 1),
        'wyckoff_phase_bucket':   phase_bucket,           # broad bucket — actuarial DB state hash
        'wyckoff_phase_granular': phase_bucket_granular,  # sub-phase — setup quality scoring
        'atr_pct': round(atr_pct_val, 2),                     # Enhancement 4: for viability audit
        'adv_dollars': round(adv_dollars, 0),                  # Enhancement 4: for viability audit
        'adx_14': adx_14_val,                                  # State hash dim 6 — ADX raw value
        'atr_percentile_rank': atr_pct_rank,                   # State hash dim 7 — ATR percentile rank (0-100)
        'catalyst_proximity': catalyst_proximity_bucket(        # State hash dim 5 — bucketed proximity
            early_signal.get('days_to_trigger', 999) if early_signal else 999
        ),
        
        # Wyckoff data — full evidence fields forwarded downstream
        'current_phase':          wyckoff_data.get('current_phase', ''),
        'phase_evidence_strength': round(phase_strength, 1),
        'dominant_event':         wyckoff_data.get('dominant_event', ''),
        'event_evidence_strength': round(float(wyckoff_data.get('event_evidence_strength', 0)), 1),
        'control_state':          wyckoff_data.get('control_state', ''),
        # Evidence quality fields — drive phase_align and EIL/MVE confidence
        'truth_confidence':       round(_truth_conf, 1),
        'wyckoff_setup_quality':  _wyk_setup_qual,
        'wyckoff_execution_bias': _exec_bias,
        'wyckoff_mode':           _wyckoff_mode,
        'phase_convergence':      round(_convergence_score, 3),
        'event_quality':          (
            'HIGH'    if _dom_event_norm in _HIGH_QUALITY_EVENTS else
            'MEDIUM'  if _dom_event_norm in _MED_QUALITY_EVENTS  else
            'OBSERVE'
        ),
        # Crabel data — full numeric score forwarded
        'crabel_score':           round(_crabel_score_raw, 1),
        'crabel_compression':     round(crabel_result.get('compression', float('nan')), 3),
        'crabel_pattern':         crabel_result.get('pattern', ''),
        # Move age — how fresh is the detected event
        'move_age_bars':          _move_age_bars,
        # Transition signal — where structure is heading
        'wyckoff_transition_to':  _wyk_trans_to,
        'wyckoff_transition_conf': round(_wyk_trans_conf, 1),
        'precor_transition_to':   _precor_trans_to,

        # DISC-01: swing_fusion outputs — direction + intent authority
        # 'direction' is the canonical field consumed by the horizon router and EIL.
        # Derived from fusion_direction → Wyckoff trade_direction → phase inference.
        # LONG/BULLISH → CALL, SHORT/BEARISH → PUT, DISTRIBUTION/MARKDOWN → PUT.
        'direction':             _candidate_direction,          # CALL or PUT — canonical
        'fusion_direction':      fusion_result.get('direction',       'NONE'),
        'fusion_intent':         fusion_result.get('intent',          'OBSERVE_ONLY'),
        'fusion_alignment_score':round(float(fusion_result.get('alignment_score', 0.0)), 1),
        'fusion_rule_fired':     fusion_result.get('fusion_rule_fired', ''),
        'fusion_contradictions': len(fusion_result.get('contradictions', [])),
        # DISC-01: asymmetry gate outputs — R:R from shelf geometry
        'asymmetry_pass':        asymmetry_result.get('asymmetry_pass', False),
        'asymmetry_R':           round(float(asymmetry_result.get('R_to_T1', 0.0)), 3),
        'shelf_high':            asymmetry_result.get('shelf_high'),
        'shelf_low':             asymmetry_result.get('shelf_low'),
        'asymmetry_entry':       asymmetry_result.get('entry'),
        'asymmetry_stop':        asymmetry_result.get('stop'),
        'asymmetry_target1':     asymmetry_result.get('target1'),
        # rr_underlying — structural price R:R (best available source)
        # Computed here once; all downstream modules read this field.
        'rr_underlying': round(
            abs(structural_target - current_price) /
            max(current_price - structural_stop, 0.01)
            if structural_target is not None
            else (asymmetry_result.get('R_to_T1') or round((atr_14 * 3.0) / max(current_price - structural_stop, 0.01), 2)),
            2
        ),
        'rr_confidence': (
            'HIGH'   if _stop_source in ('ASYMMETRY_GATE',) and _target_source == 'ASYMMETRY_GATE'
            else 'MEDIUM' if _stop_source == 'WYCKOFF'
            else 'LOW'
        ),
        'rr_source':   f'DISCOVERY_{_stop_source}_{_target_source}',
        'rr':          round(  # backward-compat alias → rr_underlying
            abs(structural_target - current_price) /
            max(current_price - structural_stop, 0.01)
            if structural_target is not None
            else (asymmetry_result.get('R_to_T1') or round((atr_14 * 3.0) / max(current_price - structural_stop, 0.01), 2)),
            2
        ),
        
        # Precor data — reconciled (see _reconcile_intent below)
        'precor_phase': precor_data.get('wyckoff_phase', '') if precor_data else '',
        'precor_intent': _reconcile_intent(
            raw_intent=precor_data.get('intent', '') if precor_data else '',
            precor_control=precor_data.get('control_state', '') if precor_data else '',
            wyckoff_control=wyckoff_data.get('control_state', ''),
            df=df,
        ),
        'precor_intent_raw': precor_data.get('intent', '') if precor_data else '',  # audit field
        'precor_control': precor_data.get('control_state', '') if precor_data else '',
        # Trend maturity fields — surfaced for Intelligence Lab and tier gating
        'dominant_trend': _get_dominant_trend(df),
        'ema_stack': _get_ema_stack(df),
        'days_above_ema50': _days_above_ema50(df),
        'pct_from_52w_low': _pct_from_52w_low(df),
        
        # Indicators
        'ATR_14': round(atr_14, 2),
        'VWAP': round(vwap, 2),
        'vwap_bias': vwap_bias,
        'volume_ratio': round(vol_ratio, 2),
        'EMA9': round(df['EMA9'].iloc[-1], 2),
        'EMA21': round(df['EMA21'].iloc[-1], 2),
        'EMA50': round(df['EMA50'].iloc[-1], 2),
        'EMA200': round(df['EMA200'].iloc[-1], 2),
        
        'timestamp': datetime.now().isoformat(),
        
        # Regime context (permanent — set by regime_threshold_injector at scan start)
        # Tells you which macro regime was active when this signal was scored.
        # Used for: post-run analysis, signal filtering, ML training labels.
        # NOTE: 'macro_regime' is the canonical field name read by Vanguard and Edge Detector.
        #       'active_regime' is retained as an audit/ML label alias — both are written.
        'macro_regime': getattr(cfg, 'active_regime', 'UNKNOWN'),
        'active_regime': getattr(cfg, 'active_regime', 'UNKNOWN'),
        # DISC-02: VMS scanner context — injected from scanner_context_{run_id}.json
        'vms_score':    _vms_score,
        'vms_decision': _vms_decision or 'UNKNOWN',
        'scanner_source': _scanner_source or ('UNIVERSE_SCANNER' if _vms_ticker_data else ''),
        'scanner_run_id': str(_vms_ticker_data.get('scanner_run_id', '') or ''),
        'scanner_timestamp_utc': str(_vms_ticker_data.get('scanner_timestamp_utc', '') or ''),
        'scanner_signal_type': _scanner_signal_type or 'UNKNOWN',
        'scanner_score': _vms_ticker_data.get('scanner_score', _vms_score),
        'scanner_decision': str(_vms_ticker_data.get('scanner_decision', _vms_decision) or 'UNKNOWN'),
        'scanner_confidence': _vms_ticker_data.get('scanner_confidence', ''),
        'scanner_data_quality': str(_vms_ticker_data.get('scanner_data_quality', '') or ('CONFIRMED' if _vms_ticker_data else 'MISSING')),
        'scanner_reason_codes': _vms_ticker_data.get('scanner_reason_codes', ''),
        'scanner_pattern_tags': _vms_ticker_data.get('scanner_pattern_tags', ''),
        'scanner_sector': _vms_ticker_data.get('scanner_sector', ''),
        'scanner_price': _vms_ticker_data.get('scanner_price', ''),
        'scanner_volume': _vms_ticker_data.get('scanner_volume', ''),
        'scanner_rvol': _vms_ticker_data.get('scanner_rvol', ''),
        'scanner_watchlist_lane': _vms_ticker_data.get('scanner_watchlist_lane', ''),
        'scanner_age_hrs': _vms_ticker_data.get('scanner_age_hrs', ''),
        'vol_spread': _vms_ticker_data.get('vol_spread', ''),
        'iv_rank': _vms_ticker_data.get('iv_rank', ''),

        # Sector context — from enriched universe file when available (Step 3)
        'sector':        _sector,
        'sector_etf':    _ticker_etf,
        'industry':      _industry,
        'macro_abstain': str(_macro_abstain).lower(),
        **macro_quant_columns_for_row(
            getattr(cfg, 'macro_quant_packet', None),
            {'ticker': ticker, 'sector': _sector, 'sector_etf': _ticker_etf},
        ),

        # ── Data provenance — set by load_bars() ──────────────────────────────
        # data_source: POLYGON_FRESH | CACHE_OK | STALE_CACHE
        # data_as_of:  ISO date of last bar in the series used for this signal.
        # is_stale:    True when stale-cache fallback is used or bar age > 5 days.
        # Used by orchestrator, Vanguard, MVE, EIL and Intelligence Lab.
        'data_source':       _data_source_attr,
        'data_as_of':        _data_asof_attr,
        'is_stale':          bool(_is_stale),

        # Canonical trust fields — names MVE and Intelligence Lab consume.
        # bar_data_source mirrors data_source with the canonical key name.
        # bar_data_days_old: integer days since last bar. 0 = today, >5 = stale.
        # bar_data_asof: same as data_as_of with the canonical key name.
        'bar_data_source':   _data_source_attr,
        'bar_data_asof':     _data_asof_attr,
        'bar_data_days_old': _bar_days_old_val,

        # ── OPTIONS CONTRACT SCAFFOLDING (FIX-DTE-01) ─────────────────────────
        # Discovery does not price options — that is avshunter_options_intelligence.py's job.
        # However discovery MUST write placeholder fields so that:
        #   1. build_packages_from_discovery.py can seed the options_contract block
        #   2. avshunter_monetisation_policy.py does not hard-block on dte=0
        #   3. The EIL CSV has non-null dte for the MP gate
        #
        # dte is derived from the DTE_MATRIX in options_intelligence using (tier, phase).
        # We replicate the same logic here so the field is populated before OI runs.
        # OI will overwrite with the actual selected contract DTE after chain fetch.
        'dte':           _derive_dte_from_phase(
                             int(tier) if isinstance(tier, (int, float)) else 2,
                             (phase[:1].upper() if phase else 'C')
                         ),
        'expiry':        None,   # OI populates after contract selection
        'strike':        None,   # OI populates after contract selection
        'contract_type': None,
        'bid':           None,
        'ask':           None,
        'premium':       None,
        'iv':            None,
        'ivp':           None,
        # rr is set above as rr_underlying — DO NOT overwrite with None here
    }

    # R/R cap: structural R/R can be anomalously high when stop is nearly at price
    # (max(price - stop, 0.01) clamps denominator to $0.01, producing values like 5125x).
    # Cap output at MAX_RR=50x and stamp rr_flag so the anomaly is visible in the manifest.
    _MAX_RR = 50.0
    _rr_raw = signal.get('rr_underlying')
    if _rr_raw is None or _rr_raw == 0:
        signal['rr_flag'] = 'RR_ANOMALY_ZERO_RISK'
    elif abs(_rr_raw) > _MAX_RR:
        signal['rr_flag'] = f'RR_ANOMALY_CAPPED_FROM_{round(abs(_rr_raw), 1)}'
        _capped = _MAX_RR if _rr_raw > 0 else -_MAX_RR
        signal['rr_underlying'] = _capped
        signal['rr'] = _capped
    else:
        signal['rr_flag'] = 'RR_OK'

    # Add early position fields if applicable
    if early_signal:
        signal.update(early_signal)

    return signal


# ============================= MAIN ========================================

# DTE scaffold — mirrors DTE_MATRIX in avshunter_options_intelligence.py
# (tier, phase) → target DTE. OI overwrites with actual contract DTE after chain fetch.
_DTE_SCAFFOLD = {
    (0, 'A'): 45, (0, 'B'): 45, (0, 'C'): 38, (0, 'D'): 30, (0, 'E'): 21,
    (1, 'A'): 45, (1, 'B'): 45, (1, 'C'): 38, (1, 'D'): 30, (1, 'E'): 21,
    (2, 'A'): 60, (2, 'B'): 60, (2, 'C'): 45, (2, 'D'): 38, (2, 'E'): 30,
    (3, 'A'): 75, (3, 'B'): 75, (3, 'C'): 60, (3, 'D'): 45, (3, 'E'): 38,
}

def _derive_dte_from_phase(tier: int, phase: str) -> int:
    """Return target DTE scaffold for (tier, phase) pair. Never returns 0."""
    return _DTE_SCAFFOLD.get((min(tier, 3), phase), 45)


def assign_discovery_horizon(signal: dict) -> str:
    """FIX 3: Assign horizon bucket based on signal quality and phase alignment.

    Returns: '1_5d', '6_10d', '11_20d', or None (genuine no-signal discard).
    Replaces binary has_current_phase_alignment filter with three-horizon router.

    1_5d  : Tier 0/1 with immediate trigger confirmed
    6_10d : Tier 2 or structural setup building
    11_20d: Tier 3 or regime transition watch
    None  : NO_SIGNAL_AT_ANY_HORIZON — only legitimate discard
    """
    tier = signal.get("tier", 99)
    wyckoff_phase = str(signal.get("wyckoff_phase", "") or signal.get("phase_best", "") or "").upper()
    trigger_quality = str(signal.get("trigger_quality", "") or "").upper()
    composite = float(signal.get("composite") or signal.get("composite_score") or 0.0)

    # Immediate edge confirmed (current phase alignment)
    if tier in (0, 1) or trigger_quality in ("STRONG", "SINGLE"):
        return "1_5d"
    # Structural setup building (6-10d)
    if tier == 2 or composite >= 45.0 or wyckoff_phase in ("B", "C"):
        return "6_10d"
    # Regime transition signal (11-20d watch)
    if tier == 3 or composite >= 30.0:
        return "11_20d"
    # Genuine no-signal
    return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--universe", default="config/tickers.csv")
    ap.add_argument("--data_dir", default="data/daily")
    ap.add_argument("--output_dir", default="data/output")
    ap.add_argument("--log_level", default="INFO")
    ap.add_argument("--force-update", action="store_true")
    ap.add_argument("--lookback-days", type=int, default=90)
    ap.add_argument("--progress-every", type=int, default=100)
    # DISC-02: VMS scanner context — written by orchestrator Phase 0
    ap.add_argument("--scanner-context", default="",
                    help="Path to scanner_context_{run_id}.json — injects VMS scores into composite scoring")

    args = ap.parse_args()
    logger = setup_logger(args.log_level)

    cfg = UltimateConfig()

    # === REGIME THRESHOLD INJECTION (permanent) ===
    # Reads macro_intelligence_latest.json and adjusts tier floors,
    # compression thresholds, and volume minimums based on current regime.
    # Fail-safe: if macro file is missing or unreadable, TRANSITIONAL defaults apply.
    try:
        from regime_threshold_injector import apply_regime_to_config
        macro_path = Path(__file__).resolve().parent / "dropbox" / "macro" / "macro_intelligence_latest.json"
        cfg = apply_regime_to_config(cfg, macro_path)

        # ENHANCEMENT 3: Load sector signals from macro JSON (2026-04-16)
        # Reads extras.sectors dict and builds {ETF_ticker: signal_string} map.
        # Stored on cfg so every process_ticker() call can reference it without
        # re-reading the file. Falls back to empty dict silently if missing.
        try:
            import json as _json
            with open(macro_path, encoding='utf-8') as _mf:
                _macro_raw = _json.load(_mf)
            cfg.macro_quant_packet = build_macro_quant_packet(_macro_raw, macro_path)
            _extras = (_macro_raw.get('extras') or {})
            # Handle nested extras structure (macro module v2.7 wraps twice)
            while 'extras' in _extras and isinstance(_extras.get('extras'), dict):
                _extras = _extras['extras']
            _sectors_raw = _extras.get('sectors', {})
            cfg.macro_sector_signals = {
                etf: info.get('signal', 'NEUTRAL')
                for etf, info in _sectors_raw.items()
                if isinstance(info, dict)
            }
            logger.info(f"📊 Macro sector signals loaded: {len(cfg.macro_sector_signals)} ETFs")
        except Exception as _se:
            cfg.macro_sector_signals = {}
            cfg.macro_quant_packet = missing_macro_quant_packet(macro_path)
            logger.debug(f"Macro sector signals not loaded: {_se}")

    except Exception as e:
        logger.warning(f"⚠️  Regime injection failed — running with default thresholds: {e}")
        cfg.active_regime = "TRANSITIONAL"
        cfg.active_regime_label = "DEFAULT (injection error)"
        cfg.macro_sector_signals = {}
        cfg.macro_quant_packet = missing_macro_quant_packet(
            Path(__file__).resolve().parent / "dropbox" / "macro" / "macro_intelligence_latest.json"
        )

    # DISC-02: Load VMS scanner context (written by orchestrator Phase 0).
    # Fields injected per ticker: vms_score, vms_decision, iv_rank, vol_spread.
    # cfg.vms_context is a dict keyed by ticker; scan_ticker_ultimate reads it.
    cfg.vms_context = {}
    if args.scanner_context:
        try:
            import json as _jvms
            _vms_path = Path(args.scanner_context)
            if _vms_path.exists():
                _vms_raw = _jvms.loads(_vms_path.read_text(encoding='utf-8'))
                cfg.vms_context = _vms_raw.get('tickers', {})
                for _ticker, _ctx in list(cfg.vms_context.items()):
                    if isinstance(_ctx, dict):
                        _ctx.setdefault('scanner_source', _vms_raw.get('scanner_source', 'UNIVERSE_SCANNER'))
                        _ctx.setdefault('scanner_run_id', _vms_raw.get('scanner_run_id', ''))
                        _ctx.setdefault('scanner_timestamp_utc', _vms_raw.get('scanner_timestamp_utc', ''))
                        _ctx.setdefault('scanner_age_hrs', _vms_raw.get('scanner_age_hrs', ''))
                        _ctx.setdefault('scanner_score', _ctx.get('vms_score', 0))
                        _ctx.setdefault('scanner_signal_type', _ctx.get('vms_decision', 'UNKNOWN'))
                        _ctx.setdefault('scanner_decision', _ctx.get('vms_decision', 'UNKNOWN'))
                        _ctx.setdefault('scanner_data_quality', 'CONFIRMED')
                logger.info(f"📡 VMS context loaded: {len(cfg.vms_context)} tickers from {_vms_path.name}")
            else:
                logger.warning(f"⚠️  VMS context path not found: {_vms_path}")
        except Exception as _ve:
            logger.warning(f"⚠️  VMS context load failed: {_ve}")

    # Regime diagnostic — critical for understanding tier floor activation
    active_regime = getattr(cfg, 'active_regime', 'UNKNOWN')
    active_regime_label = getattr(cfg, 'active_regime_label', active_regime)
    risk_off_floor = getattr(cfg, 'risk_off_composite_floor', 72.0)
    logger.info(f"📊 Active Regime       : {active_regime} ({active_regime_label})")
    if active_regime == 'RISK_OFF':
        logger.info(f"   Tier 1 floor       : {risk_off_floor} (RISK_OFF — scarcity mode)")
    elif active_regime == 'TRANSITIONAL':
        logger.info(f"   Tier 1 floor       : 68.0 (TRANSITIONAL)")
    else:
        logger.info(f"   Tier 1 floor       : 50.0 (RISK_ON — standard)")
    logger.info("")

    universe_path = Path(args.universe)
    data_dir = Path(args.data_dir)
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    tickers = load_universe(universe_path)
    _build_universe_sector_lookup(universe_path)
    logger.info(f"Universe sector lookup: {len(_universe_sector_lookup)} tickers with sector data")

    import os
    POLYGON_API_KEY = (
        os.environ.get("POLYGON_API_KEY") or
        os.environ.get("MARKETDATA_API_KEY") or
        ""
    )
    if not POLYGON_API_KEY:
        logger.warning("⚠️  POLYGON_API_KEY not set in environment — Polygon fetch disabled")

    polygon_fetcher: Optional[PolygonDataFetcher] = None
    if POLYGON_API_KEY:
        try:
            polygon_fetcher = PolygonDataFetcher(api_key=POLYGON_API_KEY)
            logger.info("✅ Polygon API initialized (UNLIMITED)")
        except Exception as e:
            logger.warning(f"⚠️  Polygon API unavailable: {e}")

    wyckoff_engine = WyckoffEngine(min_bars=20)

    logger.info("=" * 80)
    logger.info("AVSHUNTER DISCOVERY ULTIMATE v1.0")
    logger.info("=" * 80)
    logger.info(f"Universe: {len(tickers)} tickers")
    logger.info("")
    logger.info("ENHANCED SYSTEM:")
    logger.info(f"  🎯 TIER 0 (EARLY): Looser thresholds for early detection")
    logger.info(f"  🚨 TIER 1: High-quality confirmed setups")
    logger.info(f"  📊 TIER 2: Strong candidates (observe)")
    logger.info(f"  👀 TIER 3: Watch list")
    logger.info(f"  🔧 Crabel/Precor: ENABLED")
    logger.info("-" * 80)

    all_signals = []
    tickers_with_data = 0
    
    tier_counts = {0: 0, 1: 0, 2: 0, 3: 0}

    for i, t in enumerate(tickers, 1):
        df = load_bars(data_dir, t, polygon_fetcher, args.force_update, args.lookback_days)
        if df is None or df.empty:
            continue
        
        tickers_with_data += 1

        signal = scan_ticker_ultimate(t, df, cfg, wyckoff_engine)

        if signal:
            # FIX 3: Stamp horizon_bucket and discovery_basis using three-horizon router
            _horizon = assign_discovery_horizon(signal)
            if _horizon is None:
                # Genuine no-signal at any horizon — only legitimate discard
                logger.debug("NO_SIGNAL_AT_ANY_HORIZON: %s", t)
            else:
                signal["horizon_bucket"] = _horizon
                signal["discovery_basis"] = (
                    "CURRENT_PHASE_ALIGNMENT" if _horizon == "1_5d"
                    else "STRUCTURAL_SETUP_BUILDING" if _horizon == "6_10d"
                    else "REGIME_TRANSITION_SIGNAL"
                )
                if _horizon in ("6_10d", "11_20d"):
                    signal.setdefault("opportunity_label", "WATCH_FOR_REGIME_FLIP")
                all_signals.append(signal)
            # tier is an integer (0, 1, 2, 3)
            tier = signal['tier']
            if tier in tier_counts:
                tier_counts[tier] += 1
        else:
            logger.debug("NO_SIGNAL_AT_ANY_HORIZON: %s", t)

        if args.progress_every and i % int(args.progress_every) == 0:
            logger.info(
                f"Progress {i}/{len(tickers)} | data={tickers_with_data} | "
                f"T0={tier_counts[0]} | T1={tier_counts[1]} | T2={tier_counts[2]} | "
                f"total={len(all_signals)}"
            )

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    out_candidates = out_dir / f"discovery_candidates_ultimate_{ts}.csv"
    out_early = out_dir / f"early_positions_ultimate_{ts}.csv"
    out_watchlist = out_dir / f"final_watchlist_ultimate_{ts}.csv"
    out_summary = out_dir / f"discovery_summary_ultimate_{ts}.json"

    # Save all candidates
    if all_signals:
        df_all = pd.DataFrame(all_signals)
        # Enhancement 3: Sort by tier then lift_proxy_score (not raw composite)
        # This ensures within each tier, the highest-lift setups surface first.
        sort_col = 'lift_proxy_score' if 'lift_proxy_score' in df_all.columns else 'composite_score'
        df_all = df_all.sort_values(['tier', sort_col], ascending=[True, False])
        df_all.to_csv(out_candidates, index=False)
        
        # Early positions only
        df_early = df_all[df_all['tier'] == 0]
        if not df_early.empty:
            df_early.to_csv(out_early, index=False)
        
        # Final watchlist (Tier 0 + Tier 1)
        df_watchlist = df_all[df_all['tier'].isin([0, 1])]
        if not df_watchlist.empty:
            df_watchlist.to_csv(out_watchlist, index=False)
    
    # Summary
    stale_ticker_count = sum(
        1 for s in all_signals if s.get("data_source") == "STALE_CACHE"
    )
    out_summary.write_text(
        json.dumps({
            "timestamp": ts,
            "version": "ULTIMATE v1.0 (v15 + Early Detection + Crabel/Precor)",
            "universe_size": len(tickers),
            "tickers_scanned": tickers_with_data,
            "total_candidates": len(all_signals),
            "tier_0_early": tier_counts[0],
            "tier_1_confirmed": tier_counts[1],
            "tier_2_observe": tier_counts[2],
            "tier_3_watch": tier_counts[3],  # RISK_OFF: boosted-sub-T2 accumulation setups
            "candidate_ratio": round(len(all_signals) / len(tickers) * 100, 1) if tickers else 0,
            "early_ratio": round(tier_counts[0] / len(tickers) * 100, 1) if tickers else 0,
            "stale_ticker_count": stale_ticker_count,  # tickers that used STALE_CACHE fallback
        }, indent=2),
        encoding="utf-8",
    )

    
    # Run manifest (for Intelligence Lab / QA)
    out_manifest = out_dir / f"run_manifest_ultimate_{ts}.json"
    manifest = {
        "run_id": ts,
        "producer": "avshunter_discovery_ULTIMATE.py",
        "produced_at_local": ts,
        "active_regime": getattr(cfg, "active_regime", None),
        "active_regime_label": getattr(cfg, "active_regime_label", None),
        "outputs": {
            "candidates_csv": str(out_candidates.name) if out_candidates.exists() else None,
            "early_csv": str(out_early.name) if out_early.exists() else None,
            "watchlist_csv": str(out_watchlist.name) if out_watchlist.exists() else None,
            "summary_json": str(out_summary.name) if out_summary.exists() else None,
        },
        "counts": {
            "universe_size": len(tickers),
            "tickers_scanned": tickers_with_data,
            "total_candidates": len(all_signals),
            "tier_0": tier_counts[0],
            "tier_1": tier_counts[1],
            "tier_2": tier_counts[2],
            "tier_3": tier_counts[3],
        },
    }
    try:
        out_manifest.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    except Exception as e:
        logger.warning(f"⚠️ Could not write run manifest: {e}")

    logger.info("=" * 80)
    logger.info("SCAN COMPLETE")
    logger.info("=" * 80)
    logger.info(f"🎯 TIER 0 (EARLY): {tier_counts[0]} ({tier_counts[0]/len(tickers)*100:.1f}%)")
    logger.info(f"🚨 TIER 1 (CONFIRMED): {tier_counts[1]} ({tier_counts[1]/len(tickers)*100:.1f}%)")
    logger.info(f"📊 TIER 2 (OBSERVE): {tier_counts[2]} ({tier_counts[2]/len(tickers)*100:.1f}%)")
    logger.info(f"👀 TIER 3 (WATCH): {tier_counts[3]} ({tier_counts[3]/len(tickers)*100:.1f}%) — boosted-sub-T2 accumulation setups")
    logger.info(f"📈 TOTAL CANDIDATES: {len(all_signals)} ({len(all_signals)/len(tickers)*100:.1f}%)")
    logger.info("")
    logger.info("Output Files:")
    logger.info(f"  {out_candidates.name}")
    logger.info(f"  {out_early.name}")
    logger.info(f"  {out_watchlist.name}")
    logger.info("")


if __name__ == "__main__":
    main()
