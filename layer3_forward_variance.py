"""
layer3_forward_variance.py
==========================
Q-OMEGA Layer 3 — Forward Variance Forecast Engine

Purpose:
    Produce a forward realised volatility estimate for each ticker using
    GARCH(1,1) with regime-awareness. This is the predictive engine that
    powers the RIEG (Realised-Implied Edge Gap) in Layer 4.

    Without this, AVSHUNTER can see that IV is elevated or cheap but cannot
    compare it to what volatility is ACTUALLY LIKELY TO REALISE — which is
    the core of professional options mispricing detection.

Architecture:
    Input  : Daily OHLCV price series (minimum 60 bars, ideally 252)
    Output : ForwardVarianceResult dataclass with:
               forward_realised_vol    — annualised, decimal (e.g. 0.28 = 28%)
               vol_forecast_confidence — 0-100
               expected_move_1_5d      — % move expected over 1-5 days
               expected_move_6_10d     — % move expected over 6-10 days
               expected_move_11_20d    — % move expected over 11-20 days
               iv_tailwind_score       — signed: positive = IV cheap vs forecast
               jump_risk_flag          — True if recent vol cluster suggests jump
               method                  — 'GARCH' | 'EWMA_FALLBACK' | 'ATR_PROXY'

Dependencies:
    numpy, pandas, scipy (all already in pipeline venv)
    arch library (pip install arch --break-system-packages)
    Falls back gracefully if arch not installed.

Position in pipeline:
    Called by garch_runner.py nightly after orchestrator discovery phase.
    Output written to data/output/runs/{run_id}/qomega/garch_forecasts_{run_id}.csv
    Consumed by layer4_mispricing.py to compute RIEG and CCR.
"""

from __future__ import annotations

import logging
import math
import warnings
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd

warnings.filterwarnings('ignore')
log = logging.getLogger('layer3_forward_variance')

# ── Constants ──────────────────────────────────────────────────────────────────
TRADING_DAYS_YEAR   = 252
MIN_BARS_GARCH      = 60    # minimum daily bars for GARCH calibration
MIN_BARS_EWMA       = 20    # minimum bars for EWMA fallback
EWMA_LAMBDA         = 0.94  # RiskMetrics lambda for EWMA
GARCH_MAX_ITER      = 200   # GARCH optimisation iteration cap
VOL_FLOOR           = 0.05  # 5% annualised — never report below this
VOL_CAP             = 2.50  # 250% annualised — never report above this

# Layer 3 model-risk guardrails. These do not mutate the raw forecast; they
# add audit flags and bounded scoring companions for downstream capital gates.
L3_MODEL_RISK_VOL_HARDCAP     = VOL_CAP
L3_LOW_CONF_THRESHOLD         = 65.0
L3_HIGH_VOL_THRESHOLD         = 1.50
L3_THIN_HISTORY_MIN_BARS      = 100
L3_IV_TAILWIND_SCORE_CAP      = 1.50

# Jump risk: if realised vol over last 5 days is 1.5× the 20-day vol, flag jump
JUMP_RISK_RATIO     = 1.5
JUMP_LOOKBACK_SHORT = 5
JUMP_LOOKBACK_LONG  = 20

# Confidence scoring weights
CONF_BARS_WEIGHT    = 0.40   # more history = more confidence
CONF_STABLE_WEIGHT  = 0.35   # stable vol = more predictable
CONF_METHOD_WEIGHT  = 0.25   # GARCH > EWMA > ATR


# ── Output dataclass ───────────────────────────────────────────────────────────

@dataclass
class ForwardVarianceResult:
    ticker:                 str
    forward_realised_vol:   float           # annualised decimal
    vol_forecast_confidence: float          # 0-100
    expected_move_1_5d:     float           # % (e.g. 3.2 = 3.2%)
    expected_move_6_10d:    float
    expected_move_11_20d:   float
    iv_tailwind_score:      float           # implied_vol - forward_realised_vol (signed)
    jump_risk_flag:         bool
    method:                 str             # 'GARCH' | 'EWMA_FALLBACK' | 'ATR_PROXY'
    garch_omega:            Optional[float] = None
    garch_alpha:            Optional[float] = None
    garch_beta:             Optional[float] = None
    n_bars_used:            int = 0
    error:                  Optional[str]  = None

    def _model_risk_flags(self) -> list:
        flags = []
        raw_tailwind = float(self.iv_tailwind_score or 0.0)

        if self.forward_realised_vol >= L3_MODEL_RISK_VOL_HARDCAP:
            flags.append("VOL_HARDCAP")
        if (
            self.vol_forecast_confidence <= L3_LOW_CONF_THRESHOLD
            and self.forward_realised_vol >= L3_HIGH_VOL_THRESHOLD
        ):
            flags.append("LOW_CONF_HIGH_VOL")
        if self.n_bars_used and self.n_bars_used < L3_THIN_HISTORY_MIN_BARS:
            flags.append("THIN_HISTORY")
        if abs(raw_tailwind) > L3_IV_TAILWIND_SCORE_CAP:
            flags.append("IV_TAILWIND_EXTREME")

        return flags

    def to_dict(self) -> dict:
        from domain.volatility_budget import checkpoint_fields
        budget_v2 = checkpoint_fields(
            None if self.error else float(self.forward_realised_vol)
        )
        raw_tailwind = float(self.iv_tailwind_score or 0.0)
        capped_tailwind = float(np.clip(
            raw_tailwind,
            -L3_IV_TAILWIND_SCORE_CAP,
            L3_IV_TAILWIND_SCORE_CAP,
        ))
        model_risk_flags = self._model_risk_flags()
        return {
            'ticker':                         self.ticker,
            'l3_forward_realised_vol':        round(self.forward_realised_vol, 4),
            'l3_vol_forecast_conf':           round(self.vol_forecast_confidence, 1),
            'l3_expected_move_1_5d':          round(self.expected_move_1_5d, 2),
            'l3_expected_move_6_10d':         round(self.expected_move_6_10d, 2),
            'l3_expected_move_11_20d':        round(self.expected_move_11_20d, 2),
            # Preserve raw tailwind/headwind for audit, add capped companion for scoring.
            'l3_iv_tailwind_score':           round(raw_tailwind, 4),
            'l3_iv_tailwind_score_capped':    round(capped_tailwind, 4),
            'l3_jump_risk_flag':              self.jump_risk_flag,
            # FIX RC-7b: method now correctly reflects actual model used.
            # 'HAR_RV'  - Heterogeneous Autoregressive Realised Volatility (primary)
            # 'GARCH'   - EGARCH or GARCH(1,1) fallback (arch library)
            # 'EWMA_FALLBACK' - RiskMetrics EWMA (insufficient bars for HAR-RV)
            # 'ATR_PROXY'     - ATR-based estimate (< MIN_BARS_EWMA bars)
            'l3_method':                      self.method,
            # garch_alpha/beta are None when method='HAR_RV'. HAR-RV OLS
            # coefficients are not stored here to prevent false validity alarms.
            'l3_garch_alpha':                 round(self.garch_alpha, 4) if self.garch_alpha is not None else None,
            'l3_garch_beta':                  round(self.garch_beta,  4) if self.garch_beta  is not None else None,
            'l3_n_bars':                      self.n_bars_used,
            'l3_model_risk_flags':            "|".join(model_risk_flags),
            'l3_model_risk_flag_count':       len(model_risk_flags),
            'l3_model_risk_capital_guard':    bool(model_risk_flags),
            'l3_error':                       self.error,
            **budget_v2,
            'l3_expected_move_legacy_deprecated': True,
            'l3_expected_move_legacy_unit': 'PERCENT',
        }


# ── Core functions ─────────────────────────────────────────────────────────────

def _log_returns(prices: pd.Series) -> np.ndarray:
    """Compute log returns, dropping NaN."""
    return np.log(prices / prices.shift(1)).dropna().values


def _annualise(daily_vol: float) -> float:
    """Convert daily vol to annualised, clamped to floor/cap."""
    ann = daily_vol * math.sqrt(TRADING_DAYS_YEAR)
    return float(np.clip(ann, VOL_FLOOR, VOL_CAP))


def _expected_move(annualised_vol: float, days: float) -> float:
    """1-sigma expected move % over N calendar days.

    The engine intentionally converts calendar days to a trading-day fraction:
        trading_days = days * 5 / 7

    Formula:
        annualised_vol * sqrt(trading_days / 252) * 100

    A 5-calendar-day move is therefore about sqrt(5/7) of the naive
    5-trading-day formula. This is expected output behavior, not drift.
    """
    trading_frac = days * (5 / 7)
    return float(annualised_vol * math.sqrt(trading_frac / TRADING_DAYS_YEAR) * 100)


def _jump_risk(returns: np.ndarray) -> bool:
    """True if short-term realised vol is JUMP_RISK_RATIO× long-term."""
    if len(returns) < JUMP_LOOKBACK_LONG:
        return False
    short_vol = float(np.std(returns[-JUMP_LOOKBACK_SHORT:], ddof=1))
    long_vol  = float(np.std(returns[-JUMP_LOOKBACK_LONG:],  ddof=1))
    if long_vol <= 0:
        return False
    return (short_vol / long_vol) >= JUMP_RISK_RATIO


def _confidence_score(n_bars: int, vol_stability: float, method: str) -> float:
    """
    Compute 0-100 confidence score.
    vol_stability: coefficient of variation of rolling 20-day vol (lower = more stable).
    """
    # Bars score: 252 bars → 100%, 60 bars → ~24%
    bars_score  = min(100.0, (n_bars / TRADING_DAYS_YEAR) * 100.0)

    # Stability score: CV < 0.2 is very stable; CV > 0.8 is chaotic
    stab_score  = max(0.0, min(100.0, (1.0 - vol_stability / 0.8) * 100.0))

    # Method score — FIX RC-7b: HAR_RV added as the highest-confidence method.
    # HAR-RV outperforms GARCH in out-of-sample forecasting (Corsi 2009) and
    # has no convergence or stationarity constraints.
    method_score = {'HAR_RV': 100.0, 'GARCH': 90.0, 'EWMA_FALLBACK': 65.0, 'ATR_PROXY': 35.0}.get(method, 0.0)

    raw = (CONF_BARS_WEIGHT   * bars_score +
           CONF_STABLE_WEIGHT * stab_score +
           CONF_METHOD_WEIGHT * method_score)

    return round(float(np.clip(raw, 0.0, 100.0)), 1)


def _vol_stability(returns: np.ndarray) -> float:
    """Coefficient of variation of rolling 20-day vol. Lower = more stable."""
    if len(returns) < 40:
        return 0.5  # assume moderate stability if insufficient data
    rolling_vols = [
        np.std(returns[i:i+20], ddof=1)
        for i in range(0, len(returns) - 20, 5)
    ]
    arr = np.array(rolling_vols)
    mean_v = arr.mean()
    if mean_v <= 0:
        return 0.5
    return float(arr.std() / mean_v)


# ── Volatility engine — HAR-RV primary, EWMA-calibrated GARCH fallback ─────────
#
# Why HAR-RV instead of GARCH for RISK_OFF regimes:
#   GARCH(1,1) and EGARCH both fail when persistence > 0.9999 (current market).
#   HAR-RV (Heterogeneous Autoregressive Realised Volatility) directly models
#   realised volatility as a weighted sum of 1-day, 5-day, and 22-day lags.
#   No distribution assumption, no convergence, no stationarity constraint.
#   Corsi (2009) showed HAR-RV outperforms GARCH in forecasting over all horizons.
#   Works on any market condition including extreme stress regimes.

def _har_rv_forecast(returns: np.ndarray, horizon: int = 20) -> Optional[dict]:
    """
    HAR-RV forecast: vol = a + b1*RV(1d) + b5*RV(5d) + b22*RV(22d)
    Fit by OLS on rolling windows. No convergence issues, no stationarity constraint.
    Returns annualised vol forecast.
    """
    if len(returns) < 30:
        return None
    try:
        # Realised variance series (daily squared returns as RV proxy)
        rv = returns ** 2

        # Build HAR lags
        rv1  = rv                                                    # 1-day RV
        rv5  = np.array([np.mean(rv[max(0,i-5):i])  for i in range(len(rv))])   # 5-day avg
        rv22 = np.array([np.mean(rv[max(0,i-22):i]) for i in range(len(rv))])   # 22-day avg

        # Use last 180 observations for fit (recent data weighted implicitly by recency)
        n_fit = min(180, len(rv) - 23)
        if n_fit < 20:
            return None

        Y  = rv1[23:23+n_fit]          # target: next-day RV
        X1 = rv1[22:22+n_fit]
        X5 = rv5[22:22+n_fit]
        X22= rv22[22:22+n_fit]

        # OLS: Y = a + b1*X1 + b5*X5 + b22*X22
        X = np.column_stack([np.ones(n_fit), X1, X5, X22])
        try:
            coeffs, _, _, _ = np.linalg.lstsq(X, Y, rcond=None)
        except np.linalg.LinAlgError:
            return None

        a, b1, b5, b22 = coeffs

        # Forecast: use last known values
        last_rv1  = float(rv[-1])
        last_rv5  = float(np.mean(rv[-5:]))
        last_rv22 = float(np.mean(rv[-22:]))

        # H-day ahead: HAR is naturally multi-horizon
        # For h > 1, use the 5d and 22d components which capture mean reversion
        daily_rv_forecast = float(a + b1*last_rv1 + b5*last_rv5 + b22*last_rv22)
        daily_rv_forecast = max(daily_rv_forecast, float(np.mean(rv[-5:])) * 0.5)

        # Average forecast over horizon using decay toward long-run mean
        lr_rv = float(np.mean(rv[-60:]))
        decay = 0.92  # empirical mean-reversion speed
        h_sum = sum(
            lr_rv + (decay ** h) * (daily_rv_forecast - lr_rv)
            for h in range(horizon)
        )
        avg_rv = max(h_sum / horizon, 1e-10)

        # Convert daily variance to annualised vol (decimal)
        ann_vol = float(np.sqrt(avg_rv) * np.sqrt(252))
        ann_vol = float(np.clip(ann_vol, 0.05, 2.50))

        return {
            # FIX RC-7a (2026-04-16): Keys renamed from 'alpha'/'beta' to 'har_b1'/'har_b5_b22'.
            # These are HAR-RV OLS regression coefficients — they are NOT GARCH alpha/beta.
            # HAR-RV b1 CAN be negative (mean-reverting 1-day component); this is mathematically
            # valid and does NOT indicate a problem. The previous naming caused these to be
            # stored in l3_garch_alpha/l3_garch_beta in the CSV, triggering false validity
            # alarms in downstream code that checked GARCH stationarity constraints.
            # The ann_vol forecast is unaffected — it is derived from the OLS fit, not from
            # the raw coefficients. Expected_moves are correct regardless of coefficient sign.
            'har_b1':       float(b1),
            'har_b5_b22':   float(b5 + b22),
            'omega':        float(a),      # HAR-RV intercept (kept for audit)
            'method_used':  'HAR_RV',
            'ann_vol':  ann_vol,
            'daily_var':daily_rv_forecast,
            'last_var': last_rv1,
            'persist':  decay,
        }
    except Exception as e:
        log.debug(f'HAR-RV failed: {e}')
        return None


def _garch_forecast(returns: np.ndarray, horizon: int = 20) -> Optional[dict]:
    """
    HAR-RV primary (always works), EGARCH fallback, GARCH(1,1) last resort.
    HAR-RV is used first because it has no convergence or stationarity issues.
    """
    # ── Primary: HAR-RV ───────────────────────────────────────────────────────
    result = _har_rv_forecast(returns, horizon)
    if result is not None:
        return result

    # ── Fallback: arch library models ─────────────────────────────────────────
    try:
        from arch import arch_model  # type: ignore
    except ImportError:
        return None

    r_pct = returns * 100.0

    # EGARCH — no stationarity constraint
    try:
        am  = arch_model(r_pct, vol='EGARCH', p=1, q=1, dist='Normal', rescale=True)
        res = am.fit(disp='off', show_warning=False, options={'maxiter': 200})
        cv  = res.conditional_volatility
        if cv is not None and len(cv) > 0:
            last_pct = float(cv.iloc[-1])
            if np.isfinite(last_pct) and last_pct > 0:
                beta_e  = float(np.clip(res.params.get('beta[1]', 0.95), 0.0, 1.0))
                lr_var  = float(np.std(r_pct)) ** 2
                cur_var = last_pct ** 2
                avg_var = max(
                    sum(lr_var + (beta_e**h)*(cur_var-lr_var) for h in range(1, horizon+1)) / horizon,
                    1e-8
                )
                return {
                    'omega':    float(res.params.get('omega', np.nan)),
                    'alpha':    float(res.params.get('alpha[1]', np.nan)),
                    'beta':     beta_e,
                    'ann_vol':  _annualise(math.sqrt(avg_var) / 100.0),
                    'daily_var':avg_var,
                    'last_var': cur_var,
                    'persist':  beta_e,
                }
    except Exception:
        pass

    # GARCH(1,1) — strict stationarity only
    try:
        am  = arch_model(r_pct, vol='Garch', p=1, q=1, dist='Normal', rescale=True)
        res = am.fit(disp='off', show_warning=False, options={'maxiter': 200})
        omega = float(res.params.get('omega', np.nan))
        alpha = float(res.params.get('alpha[1]', np.nan))
        beta  = float(res.params.get('beta[1]',  np.nan))
        if (np.isfinite(omega) and np.isfinite(alpha) and np.isfinite(beta)
                and alpha + beta < 1.0 and alpha >= 0 and beta >= 0 and omega > 0):
            persist  = alpha + beta
            lr_var   = omega / (1.0 - persist)
            last_var = float(res.conditional_volatility.iloc[-1] ** 2)
            avg_var  = max(
                sum(lr_var + (persist**h)*(last_var-lr_var) for h in range(1, horizon+1)) / horizon,
                1e-8
            )
            return {
                'omega': omega, 'alpha': alpha, 'beta': beta,
                'ann_vol': _annualise(math.sqrt(avg_var) / 100.0),
                'daily_var': avg_var, 'last_var': last_var, 'persist': persist,
            }
    except Exception:
        pass

    return None
def _ewma_forecast(returns: np.ndarray) -> float:
    """
    EWMA (RiskMetrics) volatility estimate.
    σ²_t = λ·σ²_{t-1} + (1-λ)·r²_{t-1}
    Returns annualised decimal vol.
    """
    if len(returns) < 5:
        return 0.25  # last-resort default: 25% vol
    var = float(np.var(returns[:10], ddof=1))  # seed
    lam = EWMA_LAMBDA
    for r in returns:
        var = lam * var + (1 - lam) * r * r
    return _annualise(math.sqrt(max(var, 1e-10)))


def _atr_proxy(ohlcv: pd.DataFrame) -> float:
    """
    ATR-based vol proxy when only OHLCV available.
    Approximates daily vol from True Range / Close.
    Returns annualised decimal vol.
    """
    try:
        high  = ohlcv['high'].values  if 'high'  in ohlcv.columns else ohlcv['High'].values
        low   = ohlcv['low'].values   if 'low'   in ohlcv.columns else ohlcv['Low'].values
        close = ohlcv['close'].values if 'close' in ohlcv.columns else ohlcv['Close'].values
        tr    = np.maximum(high - low,
                np.maximum(np.abs(high - np.roll(close, 1)),
                           np.abs(low  - np.roll(close, 1))))[1:]
        atr14 = np.mean(tr[-14:]) if len(tr) >= 14 else np.mean(tr)
        last_close = close[-1]
        daily_vol  = (atr14 / last_close) / 1.25  # ATR ≈ 1.25σ for lognormal
        return _annualise(daily_vol)
    except Exception:
        return 0.25


# ── Public API ─────────────────────────────────────────────────────────────────

def compute_forward_variance(
    ticker:       str,
    ohlcv:        pd.DataFrame,
    implied_vol:  float = 0.0,    # current market IV for tailwind score (annualised decimal)
    regime:       str   = '',     # macro regime label for confidence adjustment
) -> ForwardVarianceResult:
    """
    Main entry point. Accepts OHLCV DataFrame, returns ForwardVarianceResult.

    ohlcv must have columns: close (or Close), optionally high/low.
    Sorted oldest-first.

    implied_vol: pass the current ATM IV from options intelligence (annualised decimal).
    If 0, iv_tailwind_score will be 0 (neutral).
    """
    close_col = 'close' if 'close' in ohlcv.columns else 'Close'

    if ohlcv.empty or close_col not in ohlcv.columns:
        return ForwardVarianceResult(
            ticker=ticker, forward_realised_vol=0.25,
            vol_forecast_confidence=0.0,
            expected_move_1_5d=0.0, expected_move_6_10d=0.0,
            expected_move_11_20d=0.0, iv_tailwind_score=0.0,
            jump_risk_flag=False, method='ATR_PROXY',
            error='empty_or_no_close_column',
        )

    prices  = ohlcv[close_col].dropna()
    returns = _log_returns(prices)
    n_bars  = len(returns)

    # ── Attempt GARCH ──────────────────────────────────────────────────────────
    method     = 'GARCH'
    garch_res  = None
    ann_vol    = 0.0
    garch_alpha = garch_beta = garch_omega = None

    if n_bars >= MIN_BARS_GARCH:
        garch_res = _garch_forecast(returns, horizon=20)

    if garch_res is not None:
        ann_vol      = garch_res['ann_vol']
        garch_omega  = garch_res.get('omega')

        # FIX RC-7b (2026-04-16): Detect which model actually ran via 'method_used' key.
        # HAR-RV (primary path) stores 'har_b1'/'har_b5_b22' — NOT GARCH alpha/beta.
        # Only EGARCH and GARCH(1,1) fallbacks store true 'alpha'/'beta' parameters
        # that satisfy GARCH stationarity constraints (alpha>=0, beta>=0, sum<1).
        # Previously ALL paths stored into result['alpha']/result['beta'], causing
        # HAR-RV OLS coefficients to appear in l3_garch_alpha/l3_garch_beta with
        # negative values that incorrectly triggered GARCH validity alarms downstream.
        _method_used = garch_res.get('method_used', '')
        if _method_used == 'HAR_RV':
            # HAR-RV: label correctly, leave garch params as None (not applicable)
            method      = 'HAR_RV'
            garch_alpha = None   # HAR-RV b1 is NOT a GARCH alpha — do not store
            garch_beta  = None   # HAR-RV b5+b22 is NOT a GARCH beta — do not store
        else:
            # EGARCH or GARCH(1,1): store real stationarity parameters
            method      = 'GARCH'
            garch_alpha = garch_res.get('alpha')
            garch_beta  = garch_res.get('beta')
    elif n_bars >= MIN_BARS_EWMA:
        # EWMA fallback
        method  = 'EWMA_FALLBACK'
        ann_vol = _ewma_forecast(returns)
    else:
        # ATR proxy — insufficient return history
        method  = 'ATR_PROXY'
        ann_vol = _atr_proxy(ohlcv)

    # ── Regime adjustment ──────────────────────────────────────────────────────
    # In RISK_OFF regimes, realised vol tends to be 20-30% higher than model predicts.
    # Apply a conservative +10% buffer so RIEG does not overstate edge in bear markets.
    regime_upper = str(regime).upper()
    if 'RISK_OFF' in regime_upper or 'BEAR' in regime_upper:
        ann_vol = min(ann_vol * 1.10, VOL_CAP)
    elif 'TRANSITIONAL' in regime_upper:
        ann_vol = min(ann_vol * 1.05, VOL_CAP)

    ann_vol = float(np.clip(ann_vol, VOL_FLOOR, VOL_CAP))

    # ── Expected moves ─────────────────────────────────────────────────────────
    em_1_5   = _expected_move(ann_vol, 5)
    em_6_10  = _expected_move(ann_vol, 10) - _expected_move(ann_vol, 5)
    em_11_20 = _expected_move(ann_vol, 20) - _expected_move(ann_vol, 10)

    # ── IV tailwind score ──────────────────────────────────────────────────────
    # Positive = market IV > forecast realised vol = options EXPENSIVE (headwind)
    # Negative = market IV < forecast realised vol = options CHEAP (tailwind)
    # Named "tailwind" from the long-option buyer's perspective:
    #   negative value means you are buying cheap → tailwind
    iv_tailwind = float(implied_vol - ann_vol) if implied_vol > 0 else 0.0

    # ── Jump risk ──────────────────────────────────────────────────────────────
    jump_flag = _jump_risk(returns) if n_bars >= JUMP_LOOKBACK_LONG else False

    # ── Confidence ────────────────────────────────────────────────────────────
    stab  = _vol_stability(returns)
    conf  = _confidence_score(n_bars, stab, method)

    # Penalise confidence in RISK_OFF: vol regime is less predictable
    if 'RISK_OFF' in regime_upper:
        conf = max(0.0, conf - 10.0)

    return ForwardVarianceResult(
        ticker                  = ticker,
        forward_realised_vol    = ann_vol,
        vol_forecast_confidence = conf,
        expected_move_1_5d      = em_1_5,
        expected_move_6_10d     = em_6_10,
        expected_move_11_20d    = em_11_20,
        iv_tailwind_score       = iv_tailwind,
        jump_risk_flag          = jump_flag,
        method                  = method,
        garch_omega             = garch_omega,
        garch_alpha             = garch_alpha,
        garch_beta              = garch_beta,
        n_bars_used             = n_bars,
    )
