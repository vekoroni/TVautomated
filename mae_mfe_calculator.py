"""
mae_mfe_calculator.py
=====================
Q-OMEGA Layer 6 support — Historical MAE/MFE Distribution

Purpose:
    Compute historical Maximum Adverse Excursion (MAE) and Maximum Favourable
    Excursion (MFE) per ticker from price history.

    MAE: the worst drawdown typically experienced before the trade resolves.
         "How far against us does the stock typically go before it works?"
    MFE: the best gain typically experienced during the hold window.
         "How much does the stock typically move in our favour?"

    These are the raw inputs for the Path Survivability Index (PSI) in Layer 6.
    A contract that decays to zero before the MAE resolves is a losing trade
    even when direction is correct — this is what PSI measures.

Usage:
    Called by layer6_path_survival.compute_psi() — not called directly.
    Can also be run standalone to pre-cache MAE/MFE data per ticker.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd

log = logging.getLogger('mae_mfe_calculator')

# ── Config ─────────────────────────────────────────────────────────────────────
MIN_BARS_FOR_MAE  = 30    # minimum price bars to compute meaningful MAE/MFE
DEFAULT_HOLD_DAYS = 20    # default look-forward window if not specified
PERCENTILES       = [25, 50, 75, 90]   # distribution percentiles to compute


# ── Output dataclass ───────────────────────────────────────────────────────────

@dataclass
class MAEMFEResult:
    ticker:             str
    hold_days:          int
    n_observations:     int
    # MAE percentiles (negative values, e.g. -0.032 = 3.2% adverse)
    mae_p25:            float   # 25th pctile MAE (least bad)
    mae_p50:            float   # median MAE
    mae_p75:            float   # 75th pctile MAE (worse)
    mae_p90:            float   # 90th pctile MAE (tail risk)
    # MFE percentiles (positive values)
    mfe_p25:            float
    mfe_p50:            float
    mfe_p75:            float
    mfe_p90:            float
    # Derived
    typical_mae_pct:    float   # abs(mae_p50) as %, e.g. 3.2
    typical_mfe_pct:    float   # mfe_p50 as %
    mae_mfe_ratio:      float   # mfe_p50 / abs(mae_p50) — > 1.5 favourable
    pct_resolved_before_stop: float  # % of obs where MFE > 2× MAE (trade "worked")
    error:              Optional[str] = None

    def to_dict(self) -> dict:
        return {
            'ticker':                      self.ticker,
            'mae_hold_days':               self.hold_days,
            'mae_n_obs':                   self.n_observations,
            'mae_p25':                     round(self.mae_p25,  4),
            'mae_p50':                     round(self.mae_p50,  4),
            'mae_p75':                     round(self.mae_p75,  4),
            'mae_p90':                     round(self.mae_p90,  4),
            'mfe_p25':                     round(self.mfe_p25,  4),
            'mfe_p50':                     round(self.mfe_p50,  4),
            'mfe_p75':                     round(self.mfe_p75,  4),
            'mfe_p90':                     round(self.mfe_p90,  4),
            'typical_mae_pct':             round(self.typical_mae_pct, 2),
            'typical_mfe_pct':             round(self.typical_mfe_pct, 2),
            'mae_mfe_ratio':               round(self.mae_mfe_ratio,   2),
            'pct_resolved_before_stop':    round(self.pct_resolved_before_stop, 2),
        }


# ── Core computation ───────────────────────────────────────────────────────────

def compute_mae_mfe(
    ticker:    str,
    ohlcv:     pd.DataFrame,
    direction: str = 'CALL',   # 'CALL' (long) or 'PUT' (short)
    hold_days: int = DEFAULT_HOLD_DAYS,
) -> MAEMFEResult:
    """
    Compute historical MAE/MFE distribution from OHLCV price history.

    Method:
        For each bar in the historical series, simulate a trade entry.
        Over the next hold_days bars:
            MAE = worst adverse price move (min for CALL, max for PUT)
            MFE = best favourable price move (max for CALL, min for PUT)
        Aggregate across all entry points for percentile distribution.

    Parameters:
        ohlcv     : DataFrame with columns close (or Close), high, low
        direction : 'CALL' = long bias, 'PUT' = short bias
        hold_days : forward window in trading days
    """
    close_col = 'close' if 'close' in ohlcv.columns else 'Close'
    high_col  = 'high'  if 'high'  in ohlcv.columns else 'High'
    low_col   = 'low'   if 'low'   in ohlcv.columns else 'Low'

    if ohlcv.empty or close_col not in ohlcv.columns:
        return _empty_result(ticker, hold_days, 'missing_close_column')

    closes = ohlcv[close_col].values
    highs  = ohlcv[high_col].values  if high_col  in ohlcv.columns else closes
    lows   = ohlcv[low_col].values   if low_col   in ohlcv.columns else closes

    n = len(closes)
    if n < MIN_BARS_FOR_MAE + hold_days:
        return _empty_result(ticker, hold_days, f'insufficient_bars_{n}')

    mae_list, mfe_list = [], []
    is_long = direction.upper() not in ('PUT', 'SHORT', 'SELL')

    # Slide entry point across history (skip first bar for seed stability)
    for entry_idx in range(1, n - hold_days):
        entry_price = closes[entry_idx]
        if entry_price <= 0:
            continue

        # Extract the forward window
        fwd_highs  = highs[entry_idx + 1: entry_idx + 1 + hold_days]
        fwd_lows   = lows[ entry_idx + 1: entry_idx + 1 + hold_days]

        if len(fwd_highs) == 0:
            continue

        if is_long:
            # CALL: adverse = price falling below entry, favourable = rising above
            worst_low   = np.min(fwd_lows)
            best_high   = np.max(fwd_highs)
            mae = (worst_low  - entry_price) / entry_price   # negative
            mfe = (best_high  - entry_price) / entry_price   # positive
        else:
            # PUT: adverse = price rising above entry, favourable = falling below
            worst_high = np.max(fwd_highs)
            best_low   = np.min(fwd_lows)
            mae = (entry_price - worst_high) / entry_price   # negative (went against)
            mfe = (entry_price - best_low)   / entry_price   # positive (went in favour)

        mae_list.append(mae)
        mfe_list.append(mfe)

    if not mae_list:
        return _empty_result(ticker, hold_days, 'no_valid_observations')

    mae_arr = np.array(mae_list)
    mfe_arr = np.array(mfe_list)
    n_obs   = len(mae_arr)

    # Percentiles
    mae_p25, mae_p50, mae_p75, mae_p90 = np.percentile(mae_arr, [25, 50, 75, 90])
    mfe_p25, mfe_p50, mfe_p75, mfe_p90 = np.percentile(mfe_arr, [25, 50, 75, 90])

    # Derived metrics
    typical_mae = abs(float(mae_p50)) * 100
    typical_mfe = float(mfe_p50) * 100
    ratio       = (float(mfe_p50) / abs(float(mae_p50))) if abs(mae_p50) > 1e-6 else 1.0

    # % of observations where MFE was at least 2× the MAE magnitude
    # i.e. "the trade worked — reward was at least 2× the drawdown suffered"
    resolved    = np.sum(mfe_arr >= 2.0 * np.abs(mae_arr))
    pct_resolved = float(resolved / n_obs * 100)

    return MAEMFEResult(
        ticker                   = ticker,
        hold_days                = hold_days,
        n_observations           = n_obs,
        mae_p25                  = float(mae_p25),
        mae_p50                  = float(mae_p50),
        mae_p75                  = float(mae_p75),
        mae_p90                  = float(mae_p90),
        mfe_p25                  = float(mfe_p25),
        mfe_p50                  = float(mfe_p50),
        mfe_p75                  = float(mfe_p75),
        mfe_p90                  = float(mfe_p90),
        typical_mae_pct          = typical_mae,
        typical_mfe_pct          = typical_mfe,
        mae_mfe_ratio            = float(np.clip(ratio, 0.0, 20.0)),
        pct_resolved_before_stop = pct_resolved,
    )


def _empty_result(ticker: str, hold_days: int, error: str) -> MAEMFEResult:
    return MAEMFEResult(
        ticker=ticker, hold_days=hold_days, n_observations=0,
        mae_p25=0.0, mae_p50=0.0, mae_p75=0.0, mae_p90=0.0,
        mfe_p25=0.0, mfe_p50=0.0, mfe_p75=0.0, mfe_p90=0.0,
        typical_mae_pct=0.0, typical_mfe_pct=0.0,
        mae_mfe_ratio=1.0, pct_resolved_before_stop=50.0,
        error=error,
    )
