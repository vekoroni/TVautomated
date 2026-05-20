"""
VANGUARD Actuarial Database Builder - POLYGON POWERED
======================================================

This version pulls historical data directly from Polygon API
No local data required - builds complete 4-year database from scratch
Polygon plan: Starter (Unlimited API calls)
"""

import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime, timedelta
import sys
import os
import time
import requests
from typing import Dict, List
import warnings
warnings.filterwarnings('ignore')

# Add vanguard to path
vanguard_path = Path(__file__).parent.parent
sys.path.insert(0, str(vanguard_path))


class PolygonActuarialBuilder:
    """
    Builds actuarial database using Polygon API
    """
    
    def __init__(self, polygon_api_key: str, output_path: str = None):
        """
        Args:
            polygon_api_key: Polygon API key
            output_path: Where to save database
        """
        
        self.api_key = polygon_api_key
        self.base_url = "https://api.polygon.io"
        self.output_path = Path(output_path) if output_path else Path(vanguard_path) / 'data' / 'actuarial_database.parquet'
        
        # Results accumulator
        self.all_observations = []
        
        # Rate limiting — Polygon Starter plan: Unlimited API calls
        self.calls_per_minute = 600  # 600/min = 0.1s between calls, safe for Starter unlimited
        self.last_call_time = 0
        
    def build_database(self, 
                      ticker_list: List[str],
                      years_back: int = 3,
                      max_tickers: int = None):
        """
        Build actuarial database from Polygon data
        
        Args:
            ticker_list: List of tickers to process
            years_back: Years of history to fetch (default: 3)
            max_tickers: Limit for testing
        """
        
        print("="*80)
        print("VANGUARD ACTUARIAL DATABASE BUILDER - POLYGON POWERED")
        print("="*80)
        print(f"Output path: {self.output_path}")
        print(f"Historical period: {years_back} years")
        print(f"API rate limit: {self.calls_per_minute} calls/minute")
        print("="*80)
        
        if max_tickers:
            ticker_list = ticker_list[:max_tickers]
            
        print(f"\nProcessing {len(ticker_list)} tickers...")
        print(f"Estimated time: {len(ticker_list) * 0.1 / 60:.1f} minutes\n")
        
        # Calculate date range
        to_date = datetime.now().strftime("%Y-%m-%d")
        from_date = (datetime.now() - timedelta(days=years_back*365)).strftime("%Y-%m-%d")
        
        # Process each ticker
        success_count = 0
        fail_count = 0
        
        for idx, ticker in enumerate(ticker_list, 1):
            print(f"[{idx}/{len(ticker_list)}] {ticker}...", end=" ")
            
            try:
                # Fetch data from Polygon
                df = self.fetch_daily_bars(ticker, from_date, to_date)
                
                if len(df) < 50:
                    print(f"⚠ Insufficient data ({len(df)} days)")
                    fail_count += 1
                    continue
                    
                # Process ticker
                observations = self.process_ticker(ticker, df)
                
                if len(observations) > 0:
                    self.all_observations.extend(observations)
                    print(f"✓ {len(observations)} obs from {len(df)} days")
                    success_count += 1
                else:
                    print(f"⚠ No valid observations")
                    fail_count += 1
                    
            except Exception as e:
                print(f"❌ Error: {e}")
                fail_count += 1
                continue
                
            # Progress update
            if idx % 50 == 0:
                print(f"\n  Progress: {idx}/{len(ticker_list)} | Success: {success_count} | Observations: {len(self.all_observations)}\n")
                
        # Save database
        print(f"\n{'='*80}")
        print(f"BUILDING DATABASE...")
        print(f"{'='*80}")
        print(f"Total observations: {len(self.all_observations)}")
        print(f"Successful tickers: {success_count}")
        print(f"Failed tickers: {fail_count}")
        
        if len(self.all_observations) > 0:
            self._save_database()
            print(f"\n✓ Database saved: {self.output_path}")
            print(f"  Size: {self.output_path.stat().st_size / 1024 / 1024:.2f} MB")
        else:
            print(f"\n❌ No observations to save")
            
        print(f"{'='*80}\n")
        
    def fetch_daily_bars(self, ticker: str, from_date: str, to_date: str) -> pd.DataFrame:
        """Fetch daily bars from Polygon"""
        
        # Rate limiting
        self._respect_rate_limit()
        
        url = f"{self.base_url}/v2/aggs/ticker/{ticker}/range/1/day/{from_date}/{to_date}"
        
        params = {
            'adjusted': 'true',
            'sort': 'asc',
            'limit': 5000,
            'apiKey': self.api_key
        }
        
        try:
            response = requests.get(url, params=params, timeout=10)
            
            # Debug: print response details
            if response.status_code != 200:
                print(f"\n  HTTP {response.status_code}: {response.text[:200]}")
                return pd.DataFrame()
            
            data = response.json()
            
            # Debug: check response
            if data.get('status') == 'ERROR':
                print(f"\n  API Error: {data.get('error', 'Unknown')}")
                return pd.DataFrame()
            
            # Accept both OK and DELAYED status
            status = data.get('status', '')
            if status not in ['OK', 'DELAYED'] or 'results' not in data:
                print(f"\n  No data - Status: {status}, Keys: {list(data.keys())}")
                return pd.DataFrame()
                
            results = data['results']
            df = pd.DataFrame(results)
            
            df = df.rename(columns={
                't': 'timestamp',
                'o': 'open',
                'h': 'high',
                'l': 'low',
                'c': 'close',
                'v': 'volume'
            })
            
            df['date'] = pd.to_datetime(df['timestamp'], unit='ms')
            
            return df[['date', 'open', 'high', 'low', 'close', 'volume']].sort_values('date').reset_index(drop=True)
            
        except Exception as e:
            print(f"\n  Exception: {str(e)}")
            return pd.DataFrame()
        
    def process_ticker(self, ticker: str, df: pd.DataFrame) -> List[Dict]:
        """Process ticker and extract observations"""
        
        # Calculate technicals
        df = self._calculate_all_technicals(df)
        
        observations = []
        
        # Need 20 days at end for forward outcomes
        cutoff_idx = len(df) - 20
        
        for idx in range(21, cutoff_idx):  # Start at 21 (need history for EMA21)
            row = df.iloc[idx]
            
            # Calculate state
            state = self._calculate_state_at_date(df, idx, row)
            
            if state is None:
                continue
                
            # Calculate outcomes
            outcomes = self._calculate_forward_outcomes(df, idx)
            
            if outcomes is None:
                continue
                
            # Combine
            observation = {
                **state,
                **outcomes,
                'ticker': ticker,
                'date': row['date'],
                'price': row['close']
            }
            
            observations.append(observation)
            
        return observations
        
    def _calculate_all_technicals(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate all technical indicators"""
        
        # ATR
        df['tr'] = df['high'] - df['low']
        df['atr'] = df['tr'].rolling(window=14).mean()
        df['atr_pct'] = (df['atr'] / df['close']) * 100
        
        # EMAs
        df['ema21'] = df['close'].ewm(span=21, adjust=False).mean()
        df['ema50'] = df['close'].ewm(span=50, adjust=False).mean()
        df['ema200'] = df['close'].ewm(span=200, adjust=False).mean()
        
        # RSI
        delta = df['close'].diff()
        gain = delta.where(delta > 0, 0).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df['rsi'] = 100 - (100 / (1 + rs))
        
        # Bollinger Bands
        df['bb_mid'] = df['close'].rolling(window=20).mean()
        df['bb_std'] = df['close'].rolling(window=20).std()
        df['bb_width'] = (df['bb_std'] * 4 / df['bb_mid']) * 100
        
        # 52-week high/low
        df['high_252'] = df['high'].rolling(window=252, min_periods=50).max()
        df['low_252'] = df['low'].rolling(window=252, min_periods=50).min()
        df['dist_from_high'] = (df['high_252'] - df['close']) / df['high_252']
        df['dist_from_low'] = (df['close'] - df['low_252']) / df['low_252']
        
        # ADX (14-period EWM — replaces hardcoded 30.0 placeholder)
        high  = df['high']
        low   = df['low']
        close = df['close']
        dm_plus  = (high.diff()).clip(lower=0)
        dm_minus = (-low.diff()).clip(lower=0)
        # Where both are positive, keep only the larger; zero the smaller
        mask = dm_plus >= dm_minus
        dm_plus  = dm_plus.where(mask, 0)
        dm_minus = dm_minus.where(~mask, 0)
        # Use the already-computed ATR (EWM-smoothed true range)
        atr14    = df['tr'].ewm(span=14, adjust=False).mean()
        di_plus  = 100 * dm_plus.ewm(span=14, adjust=False).mean()  / atr14.replace(0, float('nan'))
        di_minus = 100 * dm_minus.ewm(span=14, adjust=False).mean() / atr14.replace(0, float('nan'))
        dx       = 100 * (di_plus - di_minus).abs() / (di_plus + di_minus).replace(0, float('nan'))
        df['adx'] = dx.ewm(span=14, adjust=False).mean().fillna(0.0).round(2)
        
        return df
        
    def _calculate_state_at_date(self, df: pd.DataFrame, idx: int, row: pd.Series) -> Dict:
        """Calculate state vector"""
        
        close = row['close']
        atr_pct = row['atr_pct']
        bb_width = row['bb_width']
        rsi = row['rsi']
        adx = row['adx']
        
        dist_from_high = row['dist_from_high']
        dist_from_low = row['dist_from_low']
        
        ema21 = row['ema21']
        ema50 = row['ema50']
        ema200 = row['ema200']
        
        # Skip if missing data
        if pd.isna(atr_pct) or pd.isna(bb_width) or pd.isna(rsi):
            return None
            
        # VOL REGIME
        atr_percentile = self._calculate_percentile(df['atr_pct'].iloc[:idx+1], atr_pct)
        bb_percentile = self._calculate_percentile(df['bb_width'].iloc[:idx+1], bb_width)
        
        if atr_percentile < 30 and bb_percentile < 30:
            vol_regime = "COMPRESSION"
        elif atr_percentile > 70 or bb_percentile > 70:
            vol_regime = "EXPANSION"
        else:
            vol_regime = "NORMAL"
            
        # TREND DIRECTION
        if pd.notna(ema21) and pd.notna(ema50) and pd.notna(ema200):
            if close > ema21 and ema21 > ema50 and ema50 > ema200:
                trend_direction = "UP"
            elif close < ema21 and ema21 < ema50 and ema50 < ema200:
                trend_direction = "DOWN"
            else:
                trend_direction = "SIDEWAYS"
        else:
            trend_direction = "SIDEWAYS"
            
        # TREND MATURITY
        if pd.notna(dist_from_high) and pd.notna(dist_from_low):
            if trend_direction == "UP":
                if dist_from_high < 0.05:
                    trend_maturity = "LATE"
                elif dist_from_high < 0.15:
                    trend_maturity = "MIDDLE"
                else:
                    trend_maturity = "EARLY"
            elif trend_direction == "DOWN":
                if dist_from_low < 0.05:
                    trend_maturity = "LATE"
                elif dist_from_low < 0.15:
                    trend_maturity = "MIDDLE"
                else:
                    trend_maturity = "EARLY"
            else:
                trend_maturity = "N/A"
        else:
            trend_maturity = "N/A"
            
        # STRUCTURE QUALITY
        if rsi > 50:
            structure = "STRONG"
        elif rsi < 40:
            structure = "WEAK"
        else:
            structure = "NEUTRAL"
            
        # ── BUCKET COLUMNS (baked in — no post-build patch needed) ─────────
        # atr_pct_bucket: LOW = bottom 33rd pct, HIGH = top 33rd pct
        if atr_percentile < 33:
            atr_pct_bucket = 'LOW'
        elif atr_percentile > 66:
            atr_pct_bucket = 'HIGH'
        else:
            atr_pct_bucket = 'MID'

        # adx_bucket: WEAK <20, STRONG >35, MODERATE in between
        if adx < 20:
            adx_bucket = 'WEAK'
        elif adx > 35:
            adx_bucket = 'STRONG'
        else:
            adx_bucket = 'MODERATE'

        # ── WYCKOFF PHASE (baked in — matches Discovery layer output) ────────
        wyckoff_phase        = self._classify_wyckoff_phase(df, idx)
        wyckoff_phase_bucket = self._wyckoff_phase_bucket(wyckoff_phase)

        # ── MACRO REGIME (derived from EMA stack + ATR percentile proxy) ─────
        # True VIX not available in OHLCV — use ATR rank + EMA trend as proxy.
        ema_bullish_local = (pd.notna(ema21) and pd.notna(ema50) and pd.notna(ema200)
                             and close > ema21 and ema21 > ema50 and ema50 > ema200)
        ema_bearish_local = (pd.notna(ema21) and pd.notna(ema50) and pd.notna(ema200)
                             and close < ema21 and ema21 < ema50 and ema50 < ema200)
        atr_series_local  = df['atr_pct'].iloc[max(0, idx-60):idx+1].dropna()
        atr_pct_rank_local = float((atr_series_local < atr_pct).sum() / len(atr_series_local) * 100) if len(atr_series_local) > 0 else 50.0

        if ema_bullish_local and atr_pct_rank_local < 50:
            macro_regime = 'RISK_ON'
        elif ema_bearish_local or atr_pct_rank_local > 70:
            macro_regime = 'RISK_OFF'
        else:
            macro_regime = 'TRANSITIONAL'

        # ── VOLUME BUCKET (9-dim enrichment) ─────────────────────────────────
        # vol_ratio = 5-bar avg / 20-bar avg, computed above for Wyckoff logic.
        # LOW < 0.7x avg | NORMAL 0.7-1.5x | HIGH 1.5-3x | SPIKE > 3x
        if vol_ratio < 0.7:
            volume_bucket = 'LOW'
        elif vol_ratio <= 1.5:
            volume_bucket = 'NORMAL'
        elif vol_ratio <= 3.0:
            volume_bucket = 'HIGH'
        else:
            volume_bucket = 'SPIKE'

        # ── CRABEL STATE (9-dim enrichment) ──────────────────────────────────
        # Daily-bar proxy for intraday Crabel inside-bar compression.
        # Uses ATR rank + vol_ratio (already computed for Wyckoff).
        # CRABEL_READY: maximum compression (ATR < 30th pct, vol < 0.6x avg)
        # COILING:      building compression (ATR < 40th pct, vol < 0.85x avg)
        # NONE:         trending or vol-expanding
        if atr_pct_rank_local < 30 and vol_ratio < 0.6:
            crabel_state = 'CRABEL_READY'
        elif atr_pct_rank_local < 40 and vol_ratio < 0.85:
            crabel_state = 'COILING'
        else:
            crabel_state = 'NONE'

        # ── IV REGIME (9-dim enrichment) ─────────────────────────────────────
        # Realized-vol proxy matching enrich_actuarial_9dim.py and state_calculator.
        if vol_regime == 'COMPRESSION':
            iv_regime = 'LOW_IV'
        elif vol_regime == 'EXPANSION':
            iv_regime = 'HIGH_IV'
        elif atr_pct_rank_local >= 50:
            iv_regime = 'ELEVATED_IV'
        else:
            iv_regime = 'NORMAL_IV'

        return {
            'vol_regime': vol_regime,
            'trend_direction': trend_direction,
            'trend_maturity': trend_maturity,
            'structure_quality': structure,
            'atr_percentile': float(atr_percentile),
            'bb_percentile': float(bb_percentile),
            'adx': float(adx),
            'rsi': float(rsi),
            'dist_from_high': float(dist_from_high) if pd.notna(dist_from_high) else 0.5,
            'dist_from_low': float(dist_from_low) if pd.notna(dist_from_low) else 0.5,
            # ── Bucket discriminators (used by actuarial_query Stage 1 filter)
            'atr_pct_bucket': atr_pct_bucket,
            'adx_bucket': adx_bucket,
            # ── Wyckoff phase (NEW — enables phase-aware actuarial matching)
            'wyckoff_phase': wyckoff_phase,
            'wyckoff_phase_bucket': wyckoff_phase_bucket,
            # ── Macro regime (NEW — separates RISK_ON/OFF historical pools)
            'macro_regime': macro_regime,
            # ── catalyst_proximity: always NONE for historical rows
            'catalyst_proximity': 'NONE',
            # ── 9-dim match dimensions (Sprint 9-dim)
            'volume_bucket': volume_bucket,
            'crabel_state': crabel_state,
            'iv_regime': iv_regime,
        }
        
    def _calculate_forward_outcomes(self, df: pd.DataFrame, idx: int) -> Dict:
        """Calculate 20-day forward outcomes"""
        
        current_price = df.loc[idx, 'close']
        future_df = df.iloc[idx+1:idx+21].copy()
        
        if len(future_df) < 20:
            return None
            
        future_df['return'] = (future_df['close'] - current_price) / current_price
        future_df['max_return'] = future_df['return'].cummax()
        future_df['min_return'] = future_df['return'].cummin()
        
        max_gain_20d = future_df['max_return'].max()
        max_loss_20d = future_df['min_return'].min()
        final_return_20d = future_df['return'].iloc[-1]
        
        hit_10pct_up = (max_gain_20d >= 0.10)
        hit_5pct_down = (max_loss_20d <= -0.05)
        hit_5pct_down_before_10pct_up = False
        
        if hit_10pct_up:
            idx_10up = future_df[future_df['return'] >= 0.10].index[0]
            drawdowns_before = future_df.loc[:idx_10up, 'min_return']
            if (drawdowns_before <= -0.05).any():
                hit_5pct_down_before_10pct_up = True
                
        if hit_10pct_up:
            days_to_10pct = len(future_df[future_df['return'] < 0.10]) + 1
        else:
            days_to_10pct = 20
            
        if final_return_20d >= 0.10:
            outcome_category = "BIG_WIN"
        elif final_return_20d >= 0.05:
            outcome_category = "SMALL_WIN"
        elif final_return_20d >= 0:
            outcome_category = "FLAT"
        elif final_return_20d >= -0.05:
            outcome_category = "SMALL_LOSS"
        else:
            outcome_category = "BIG_LOSS"
            
        # ── 5-DAY OUTCOMES (baked in — no post-build patch needed) ─────────
        future_5d = df.iloc[idx+1:idx+6].copy()
        if len(future_5d) >= 5:
            future_5d['ret'] = (future_5d['close'] - current_price) / current_price
            ret_5d = float(future_5d['ret'].iloc[-1])
            min_5d = float(future_5d['ret'].min())
            hit_5pct_5d = bool(future_5d['ret'].max() >= 0.05)
        else:
            ret_5d = 0.0
            min_5d = 0.0
            hit_5pct_5d = False

        # ── 10-DAY OUTCOMES ───────────────────────────────────────────────────
        future_10d = df.iloc[idx+1:idx+11].copy()
        if len(future_10d) >= 10:
            future_10d['ret'] = (future_10d['close'] - current_price) / current_price
            ret_10d = float(future_10d['ret'].iloc[-1])
            min_10d = float(future_10d['ret'].min())
            hit_7pct_10d = bool(future_10d['ret'].max() >= 0.07)
        else:
            ret_10d = 0.0
            min_10d = 0.0
            hit_7pct_10d = False

        return {
            # ── 20d outcomes
            'outcome_20d_return': float(final_return_20d),
            'outcome_max_gain_20d': float(max_gain_20d),
            'outcome_max_drawdown_20d': float(max_loss_20d),
            'outcome_hit_10pct_up': bool(hit_10pct_up),
            'outcome_hit_5pct_down_before_10up': bool(hit_5pct_down_before_10pct_up),
            'outcome_days_to_10pct': int(days_to_10pct),
            'outcome_category': outcome_category,
            # ── 5d outcomes
            'outcome_5d_return': ret_5d,
            'outcome_max_drawdown_5d': min_5d,
            'outcome_hit_5pct_up_5d': hit_5pct_5d,
            # ── 10d outcomes
            'outcome_10d_return': ret_10d,
            'outcome_max_drawdown_10d': min_10d,
            'outcome_hit_7pct_up_10d': hit_7pct_10d,
        }
        
    def _classify_wyckoff_phase(self, df: pd.DataFrame, idx: int) -> str:
        """
        Classify Wyckoff phase at a historical bar using OHLCV + technicals.

        Maps to the same single-letter phases (A/B/C/D/E) that Discovery outputs,
        which the state_calculator._wyckoff_phase_bucket() then buckets into:
          ACCUMULATION = A, B, C
          MARKUP       = D, E
          DISTRIBUTION = detected via bearish structure

        Logic mirrors the Discovery layer's Wyckoff classification:

        Phase A — Stopping action. Price near 52w low, vol spike, ATR expanding.
                  Trend was DOWN, now SIDEWAYS. First sign of supply exhaustion.

        Phase B — Building cause. Price range-bound, SIDEWAYS trend, moderate vol.
                  EMA stack still bearish but flattening. Price testing lows.

        Phase C — Spring/Test. Brief dip below support then recovery.
                  Price near/below 52w low, ATR compressed, RSI recovering >40.
                  This is the highest-conviction entry point — "the trap".

        Phase D — SOS (Sign of Strength). Price breaks above range with volume.
                  Uptrend established (EMA alignment UP). ADX strengthening.
                  dist_from_low increasing, dist_from_high still moderate.

        Phase E — Markup / full trend. Strong uptrend, price extended,
                  dist_from_high < 15%, ADX > 25, sustained vol.

        Distribution — Price near 52w high with weakening internals.
                       EMA stack turning, RSI diverging, vol declining on rallies.

        Returns: 'A', 'B', 'C', 'D', 'E', or 'DISTRIBUTION'
        """
        if idx < 20:
            return 'B'  # insufficient history — default to building cause

        row       = df.iloc[idx]
        close     = row['close']
        adx       = row.get('adx', 0.0)
        rsi       = row.get('rsi', 50.0)
        ema21     = row.get('ema21', close)
        ema50     = row.get('ema50', close)
        ema200    = row.get('ema200', close)

        dist_high = float(row.get('dist_from_high', 0.5)) if pd.notna(row.get('dist_from_high')) else 0.5
        dist_low  = float(row.get('dist_from_low', 0.5))  if pd.notna(row.get('dist_from_low'))  else 0.5

        atr_pct   = row.get('atr_pct', 2.0)

        # Recent volume context (5-bar vs 20-bar avg)
        vol_window = df['volume'].iloc[max(0, idx-20):idx+1]
        vol_recent = df['volume'].iloc[max(0, idx-5):idx+1]
        avg_vol    = vol_window.mean() if len(vol_window) > 0 else 1.0
        recent_vol = vol_recent.mean() if len(vol_recent) > 0 else avg_vol
        vol_ratio  = recent_vol / avg_vol if avg_vol > 0 else 1.0

        # ATR percentile over trailing window (compression = Phase C signal)
        atr_series = df['atr_pct'].iloc[max(0, idx-60):idx+1].dropna()
        atr_pct_rank = float((atr_series < atr_pct).sum() / len(atr_series) * 100) if len(atr_series) > 0 else 50.0

        # EMA alignment
        ema_bullish   = (ema21 > ema50) and (ema50 > ema200) and (close > ema21)
        ema_bearish   = (ema21 < ema50) and (ema50 < ema200) and (close < ema21)
        ema_flattening = (abs(ema21 - ema50) / close < 0.02)  # within 2% — transitioning

        # ── DISTRIBUTION: near 52w high, weakening internals ──────────────
        if dist_high < 0.08 and rsi > 60 and (ema_bullish or ema21 > ema50):
            if vol_ratio < 0.85 or rsi > 75:
                return 'DISTRIBUTION'

        # ── PHASE E: Full markup — strong uptrend, extended ───────────────
        if ema_bullish and dist_high < 0.15 and adx > 25 and rsi > 55:
            return 'E'

        # ── PHASE D: SOS — uptrend just established ───────────────────────
        if ema_bullish and dist_high >= 0.15 and adx > 18 and rsi > 48:
            return 'D'

        # ── PHASE C: Spring/Test — compressed, near low, RSI recovering ───
        if dist_low < 0.10 and atr_pct_rank < 35 and rsi > 38 and not ema_bearish:
            return 'C'

        # ── PHASE A: Stopping action — near low, vol spike, ATR expanding ─
        if dist_low < 0.15 and vol_ratio > 1.4 and atr_pct_rank > 55:
            return 'A'

        # ── PHASE B: Range-bound cause building ───────────────────────────
        # Default for sideways / transitioning / bearish-but-stabilising
        return 'B'

    def _wyckoff_phase_bucket(self, phase: str) -> str:
        """
        Bucket single-letter phase into the 3-tier system that
        state_calculator._wyckoff_phase_bucket() uses at runtime.
        Must match exactly — this is the DB-side counterpart.
        """
        p = str(phase).upper()
        if p in ('D', 'E'):
            return 'MARKUP'
        if p == 'DISTRIBUTION':
            return 'DISTRIBUTION'
        if p in ('A', 'B', 'C'):
            return 'ACCUMULATION'
        return 'UNKNOWN'

    def _calculate_percentile(self, series: pd.Series, value: float) -> float:
        """Calculate percentile"""
        valid_series = series.dropna()
        if len(valid_series) == 0:
            return 50.0
        percentile = (valid_series < value).sum() / len(valid_series) * 100
        return percentile
        
    def _respect_rate_limit(self):
        """Rate limiting for Polygon API"""
        current_time = time.time()
        time_since_last_call = current_time - self.last_call_time
        min_time_between_calls = 60.0 / self.calls_per_minute
        
        if time_since_last_call < min_time_between_calls:
            time.sleep(min_time_between_calls - time_since_last_call)
            
        self.last_call_time = time.time()
        
    def _save_database(self):
        """Save to parquet"""
        df = pd.DataFrame(self.all_observations)
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(self.output_path, index=False)
        
        print(f"\nDATABASE STATISTICS:")
        print(f"  Total observations: {len(df)}")
        print(f"  Unique tickers: {df['ticker'].nunique()}")
        print(f"  Date range: {df['date'].min()} to {df['date'].max()}")
        print(f"\nOUTCOME DISTRIBUTION:")
        print(df['outcome_category'].value_counts())
        print(f"\nWIN RATE (>10% in 20d): {df['outcome_hit_10pct_up'].mean():.1%}")


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Build VANGUARD Actuarial Database from Polygon')
    parser.add_argument('--polygon-key', type=str, help='Polygon API key (or use POLYGON_API_KEY env var)')
    parser.add_argument('--tickers-file', type=str,
                       help='CSV file with ticker list (column: ticker)')
    parser.add_argument('--tickers', type=str, nargs='+',
                       help='Specific tickers to process')
    parser.add_argument('--max-tickers', type=int, help='Limit for testing')
    parser.add_argument('--years', type=int, default=4, help='Years of history (default: 4)')
    parser.add_argument('--output', type=str, help='Output path')
    
    args = parser.parse_args()
    
    # Get API key from args or environment
    api_key = args.polygon_key or os.getenv('POLYGON_API_KEY')
    if not api_key:
        print("Error: Polygon API key required. Use --polygon-key or set POLYGON_API_KEY environment variable")
        return
    
    # Get ticker list
    if args.tickers_file:
        df = pd.read_csv(args.tickers_file)
        ticker_list = df['ticker'].unique().tolist()
    elif args.tickers:
        ticker_list = args.tickers
    else:
        # Default: Load from premarket_actions
        default_path = r"C:\Users\ACKVerissimo\AVSHUNTER-Intelligence\data\universe\clean_universe.csv"
        if Path(default_path).exists():
            df = pd.read_csv(default_path)
            ticker_list = df['ticker'].unique().tolist()
        else:
            print("Error: No ticker list provided. Use --tickers or --tickers-file")
            return
            
    # Build database
    builder = PolygonActuarialBuilder(
        polygon_api_key=api_key,
        output_path=args.output
    )
    
    builder.build_database(
        ticker_list=ticker_list,
        years_back=args.years,
        max_tickers=args.max_tickers
    )


if __name__ == "__main__":
    main()
