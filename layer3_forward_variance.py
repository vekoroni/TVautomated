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
               iv_tailwind_score       — signed: implied_vol - forecast (None when IV or forecast missing)
               jump_risk_flag          — True if recent vol cluster suggests jump; None when not assessed
               jump_risk_state         — 'ASSESSED' | 'NOT_ASSESSED_NO_FORECAST' | 'NOT_ASSESSED_SHORT_HISTORY'
                                         | 'NOT_ASSESSED_NO_PRICE_VARIATION'
               method                  — 'HAR_RV' | 'GARCH' | 'EWMA_FALLBACK' | 'ATR_PROXY' | 'NO_FORECAST'
               forecast_state          — 'FORECAST_OK' | 'MISSING_PRICE_HISTORY' | 'FORECAST_UNAVAILABLE'
                                         | 'FORECAST_FAILED' (runner: unexpected error, reason in error)
                                         | 'CLIPPED_AT_FLOOR' | 'CLIPPED_AT_CAP' (value is the bound, not the model)
               forward_realised_vol_raw — unbounded model output (None when no forecast)
               iv_tailwind_state       — 'IV_TAILWIND_OK' | 'IV_MISSING' | 'FORECAST_MISSING'

    Missing is never neutral (R1): no usable price history gives no numeric forecast, and a
    missing implied vol gives no tailwind. The macro regime is recorded for display only and
    never changes a model value (CLAUDE.md rule 6; ACK 17 Sep 2026).

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

import json
import logging
import math
import warnings
from dataclasses import dataclass, field
from pathlib import Path
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

# Forecast range guard, governed configuration (config/governed_constants_v1.json
# "layer3_forecast_bounds"; loaded fail-closed). Evidence (Enhancements/expression_forensics/
# VOL_FLOOR_CAP_EVIDENCE.md): the bounds are a range guard, not an accuracy improvement, so a
# bounded forecast is labelled CLIPPED_AT_FLOOR / CLIPPED_AT_CAP with the raw model output kept
# in forward_realised_vol_raw (tests/test_layer3_volatility_leftovers.py V5).
GOVERNED_CONSTANTS_PATH = Path(__file__).resolve().parent / 'config' / 'governed_constants_v1.json'


def _load_forecast_bounds(path: Path = GOVERNED_CONSTANTS_PATH) -> tuple:
    payload = json.loads(Path(path).read_text(encoding='utf-8-sig'))
    bounds = payload['layer3_forecast_bounds']
    if bounds.get('version') != 'l3_forecast_bounds_v1':
        raise ValueError('unsupported layer3_forecast_bounds version')
    floor = float(bounds['floor_annual_vol_fraction'])
    cap = float(bounds['cap_annual_vol_fraction'])
    if not (0.0 < floor < cap and math.isfinite(cap)):
        raise ValueError('layer3_forecast_bounds must satisfy 0 < floor < cap')
    return floor, cap


VOL_FLOOR, VOL_CAP = _load_forecast_bounds()   # annualised decimal fractions


# DQ-12 price history integrity (ACK 17 Sep 2026; config "price_history_integrity", fail-closed).
# A one-bar move of >= ratio (either way), sub-cent closes or a long gap mark the start of a different
# security (unadjusted corporate action, ticker reuse, re-emergence): the forecast uses only the history
# from the latest break (tests/test_layer3_price_history_integrity.py).
def _load_price_history_integrity(path: Path = GOVERNED_CONSTANTS_PATH) -> tuple:
    payload = json.loads(Path(path).read_text(encoding='utf-8-sig'))
    rules = payload['price_history_integrity']
    if rules.get('version') != 'price_history_integrity_v1':
        raise ValueError('unsupported price_history_integrity version')
    ratio = float(rules['one_bar_break_ratio'])
    sub_cent = float(rules['sub_cent_price'])
    gap = int(rules['max_gap_sessions'])
    if not (ratio > 1.0 and sub_cent > 0.0 and gap > 0):
        raise ValueError('price_history_integrity values out of range')
    return ratio, sub_cent, gap


PRICE_BREAK_RATIO, SUB_CENT_PRICE, PRICE_GAP_SESSIONS = _load_price_history_integrity()

PRICE_HISTORY_INTACT               = 'INTACT'
PRICE_HISTORY_BREAK_TRUNCATED      = 'BREAK_TRUNCATED'
PRICE_HISTORY_BREAK_INSUFFICIENT   = 'BREAK_INSUFFICIENT_HISTORY'
PRICE_HISTORY_SUB_CENT             = 'SUB_CENT_PRICE'
BREAK_REASON_RATIO                 = 'ONE_BAR_MOVE_AT_OR_ABOVE_RATIO'
BREAK_REASON_SUB_CENT              = 'SUB_CENT_PRICE'
BREAK_REASON_GAP                   = 'GAP_OVER_SESSIONS'

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


# Explicit states (R1 missing is never neutral; R6 labels say what was measured)
FORECAST_OK                  = 'FORECAST_OK'
FORECAST_MISSING_PRICES      = 'MISSING_PRICE_HISTORY'
FORECAST_UNAVAILABLE         = 'FORECAST_UNAVAILABLE'
FORECAST_FAILED              = 'FORECAST_FAILED'
FORECAST_CLIPPED_AT_FLOOR    = 'CLIPPED_AT_FLOOR'
FORECAST_CLIPPED_AT_CAP      = 'CLIPPED_AT_CAP'
METHOD_NO_FORECAST           = 'NO_FORECAST'
IV_TAILWIND_OK               = 'IV_TAILWIND_OK'
IV_TAILWIND_IV_MISSING       = 'IV_MISSING'
IV_TAILWIND_FORECAST_MISSING = 'FORECAST_MISSING'
JUMP_RISK_ASSESSED                  = 'ASSESSED'
JUMP_RISK_NOT_ASSESSED_NO_FORECAST  = 'NOT_ASSESSED_NO_FORECAST'
JUMP_RISK_NOT_ASSESSED_SHORT        = 'NOT_ASSESSED_SHORT_HISTORY'
JUMP_RISK_NOT_ASSESSED_FLAT         = 'NOT_ASSESSED_NO_PRICE_VARIATION'


def _round_or_none(value: Optional[float], digits: int) -> Optional[float]:
    return None if value is None else round(float(value), digits)


# ── Output dataclass ───────────────────────────────────────────────────────────

@dataclass
class ForwardVarianceResult:
    ticker:                 str
    forward_realised_vol:   Optional[float] # annualised decimal; None when no forecast
    vol_forecast_confidence: Optional[float] # 0-100; None when no forecast
    expected_move_1_5d:     Optional[float] # % (e.g. 3.2 = 3.2%)
    expected_move_6_10d:    Optional[float]
    expected_move_11_20d:   Optional[float]
    iv_tailwind_score:      Optional[float] # implied_vol - forward_realised_vol (signed); None when missing
    jump_risk_flag:         Optional[bool]  # None when jump risk could not be assessed (never False-means-safe)
    method:                 str             # 'HAR_RV' | 'GARCH' | 'EWMA_FALLBACK' | 'ATR_PROXY' | 'NO_FORECAST'
    garch_omega:            Optional[float] = None
    garch_alpha:            Optional[float] = None
    garch_beta:             Optional[float] = None
    n_bars_used:            int = 0
    error:                  Optional[str]  = None
    forecast_state:         str = FORECAST_OK
    iv_tailwind_state:      Optional[str] = None   # derived from the values when not given
    macro_regime_display:   str = ''        # display/audit only; never used in any value
    jump_risk_state:        Optional[str] = None   # derived when not given
    forward_realised_vol_raw: Optional[float] = None  # model output before the range guard
    price_history_state:    str = 'INTACT'  # DQ-12: INTACT | BREAK_TRUNCATED | BREAK_INSUFFICIENT_HISTORY | SUB_CENT_PRICE
    price_history_break_date: Optional[str] = None
    price_history_break_reason: Optional[str] = None

    def __post_init__(self) -> None:
        if self.jump_risk_state is None:
            if self.jump_risk_flag is not None:
                self.jump_risk_state = JUMP_RISK_ASSESSED
            elif self.forward_realised_vol is None:
                self.jump_risk_state = JUMP_RISK_NOT_ASSESSED_NO_FORECAST
            else:
                self.jump_risk_state = JUMP_RISK_NOT_ASSESSED_SHORT
        if self.iv_tailwind_state is None:
            if self.forward_realised_vol is None:
                self.iv_tailwind_state = IV_TAILWIND_FORECAST_MISSING
            elif self.iv_tailwind_score is None:
                self.iv_tailwind_state = IV_TAILWIND_IV_MISSING
            else:
                self.iv_tailwind_state = IV_TAILWIND_OK

    def _model_risk_flags(self) -> list:
        flags = []
        vol = self.forward_realised_vol

        if vol is not None and vol >= L3_MODEL_RISK_VOL_HARDCAP:
            flags.append("VOL_HARDCAP")
        if (
            vol is not None
            and self.vol_forecast_confidence is not None
            and self.vol_forecast_confidence <= L3_LOW_CONF_THRESHOLD
            and vol >= L3_HIGH_VOL_THRESHOLD
        ):
            flags.append("LOW_CONF_HIGH_VOL")
        if self.n_bars_used and self.n_bars_used < L3_THIN_HISTORY_MIN_BARS:
            flags.append("THIN_HISTORY")
        if self.iv_tailwind_score is not None and abs(self.iv_tailwind_score) > L3_IV_TAILWIND_SCORE_CAP:
            flags.append("IV_TAILWIND_EXTREME")

        return flags

    def to_dict(self) -> dict:
        from domain.volatility_budget import checkpoint_fields
        budget_v2 = checkpoint_fields(
            None if (self.error or self.forward_realised_vol is None) else float(self.forward_realised_vol)
        )
        raw_tailwind = self.iv_tailwind_score
        capped_tailwind = None if raw_tailwind is None else float(np.clip(
            raw_tailwind,
            -L3_IV_TAILWIND_SCORE_CAP,
            L3_IV_TAILWIND_SCORE_CAP,
        ))
        model_risk_flags = self._model_risk_flags()
        return {
            'ticker':                         self.ticker,
            'l3_forward_realised_vol':        _round_or_none(self.forward_realised_vol, 4),
            'l3_forward_realised_vol_raw':    _round_or_none(self.forward_realised_vol_raw, 4),
            'l3_forecast_state':              self.forecast_state,
            'l3_price_history_state':         self.price_history_state,
            'l3_price_history_break_date':    self.price_history_break_date,
            'l3_price_history_break_reason':  self.price_history_break_reason,
            'l3_vol_forecast_conf':           _round_or_none(self.vol_forecast_confidence, 1),
            'l3_expected_move_1_5d':          _round_or_none(self.expected_move_1_5d, 2),
            'l3_expected_move_6_10d':         _round_or_none(self.expected_move_6_10d, 2),
            'l3_expected_move_11_20d':        _round_or_none(self.expected_move_11_20d, 2),
            # Preserve raw tailwind/headwind for audit, add capped companion for scoring.
            # None + l3_iv_tailwind_state when IV or forecast is missing (never neutral 0).
            'l3_iv_tailwind_score':           _round_or_none(raw_tailwind, 4),
            'l3_iv_tailwind_score_capped':    _round_or_none(capped_tailwind, 4),
            'l3_iv_tailwind_state':           self.iv_tailwind_state,
            'l3_jump_risk_flag':              self.jump_risk_flag,   # None when not assessed
            'l3_jump_risk_state':             self.jump_risk_state,
            # FIX RC-7b: method now correctly reflects actual model used.
            # 'HAR_RV'  - Heterogeneous Autoregressive Realised Volatility (primary)
            # 'GARCH'   - GARCH(1,1) fallback (arch library; EGARCH removed 17 Sep 2026)
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
            # Display/audit only (CLAUDE.md rule 6): never an input to any value above.
            'l3_macro_regime_display':        self.macro_regime_display,
            **budget_v2,
            'l3_expected_move_legacy_deprecated': True,
            'l3_expected_move_legacy_unit': 'PERCENT',
        }


# ── Core functions ─────────────────────────────────────────────────────────────

def _log_returns(prices: pd.Series) -> np.ndarray:
    """Compute log returns, dropping NaN."""
    return np.log(prices / prices.shift(1)).dropna().values


def _annualise(daily_vol: float) -> float:
    """Convert daily vol to annualised (unbounded; the range guard is applied and labelled once,
    in compute_forward_variance)."""
    return float(daily_vol * math.sqrt(TRADING_DAYS_YEAR))


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


def _jump_risk(returns: np.ndarray) -> tuple:
    """(flag, state): flag True if short-term realised vol is JUMP_RISK_RATIO× long-term.

    Too few returns or no price variation cannot be assessed: flag None with the reason, never
    False (R1; tests/test_layer3_volatility_leftovers.py V7).
    """
    if len(returns) < JUMP_LOOKBACK_LONG:
        return None, JUMP_RISK_NOT_ASSESSED_SHORT
    short_vol = float(np.std(returns[-JUMP_LOOKBACK_SHORT:], ddof=1))
    long_vol  = float(np.std(returns[-JUMP_LOOKBACK_LONG:],  ddof=1))
    if not math.isfinite(long_vol) or long_vol <= 0:
        return None, JUMP_RISK_NOT_ASSESSED_FLAT
    return bool((short_vol / long_vol) >= JUMP_RISK_RATIO), JUMP_RISK_ASSESSED


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
        # No clip here: the governed range guard is applied and labelled in compute_forward_variance.

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
    HAR-RV primary, GARCH(1,1) fallback; the caller falls back to EWMA when this returns None.
    Order decided by ACK on 17 Sep 2026 from the model comparison
    (Enhancements/expression_forensics/garch_comparison_study.json): HAR-RV QLIKE 0.511,
    GARCH(1,1) 0.593, EGARCH as coded unsafe (QLIKE 319) and therefore removed.
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

    # arch returns ndarray attributes for ndarray input (``_log_returns`` yields an
    # ndarray), and reports values in rescaled units when ``rescale=True`` changes the
    # data; ``res.scale`` converts them back to percent returns. Failed fits are logged
    # with their reason, never swallowed (fix 17 Sep 2026, tests/test_layer3_garch_fallback.py).

    # GARCH(1,1) — strict stationarity only
    try:
        am  = arch_model(r_pct, vol='Garch', p=1, q=1, dist='Normal', rescale=True)
        res = am.fit(disp='off', show_warning=False, options={'maxiter': 200})
        scale = float(getattr(res, 'scale', 1.0) or 1.0)
        omega = float(res.params.get('omega', np.nan)) / (scale ** 2)
        alpha = float(res.params.get('alpha[1]', np.nan))
        beta  = float(res.params.get('beta[1]',  np.nan))
        if (np.isfinite(omega) and np.isfinite(alpha) and np.isfinite(beta)
                and alpha + beta < 1.0 and alpha >= 0 and beta >= 0 and omega > 0):
            persist  = alpha + beta
            lr_var   = omega / (1.0 - persist)
            last_var = (float(np.asarray(res.conditional_volatility, dtype=float)[-1]) / scale) ** 2
            avg_var  = max(
                sum(lr_var + (persist**h)*(last_var-lr_var) for h in range(1, horizon+1)) / horizon,
                1e-8
            )
            return {
                'omega': omega, 'alpha': alpha, 'beta': beta,
                'ann_vol': _annualise(math.sqrt(avg_var) / 100.0),
                'daily_var': avg_var, 'last_var': last_var, 'persist': persist,
                'method_used': 'GARCH',
            }
        log.warning('[L3] GARCH(1,1) fit is not stationary (alpha=%s beta=%s omega=%s); no GARCH forecast',
                    alpha, beta, omega)
    except Exception as exc:
        log.warning('[L3] GARCH(1,1) fit failed (%s: %s); no GARCH forecast', type(exc).__name__, exc)

    return None
def _ewma_forecast(returns: np.ndarray) -> Optional[float]:
    """
    EWMA (RiskMetrics) volatility estimate.
    σ²_t = λ·σ²_{t-1} + (1-λ)·r²_{t-1}
    Returns annualised decimal vol, or None when there are too few returns (never a default).
    """
    if len(returns) < 5:
        return None
    var = float(np.var(returns[:10], ddof=1))  # seed
    lam = EWMA_LAMBDA
    for r in returns:
        var = lam * var + (1 - lam) * r * r
    return _annualise(math.sqrt(max(var, 1e-10)))


def _atr_proxy(ohlcv: pd.DataFrame) -> Optional[float]:
    """
    ATR-based vol proxy when only OHLCV available.
    Approximates daily vol from True Range / Close.
    Returns annualised decimal vol, or None when it cannot be computed (never a default).
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
        if not math.isfinite(float(daily_vol)) or daily_vol <= 0:
            return None
        return _annualise(daily_vol)
    except Exception as exc:
        log.debug('[L3] ATR proxy unavailable (%s: %s)', type(exc).__name__, exc)
        return None


# ── Public API ─────────────────────────────────────────────────────────────────

def _sessions_between(previous, current) -> int:
    """XNYS sessions strictly after ``previous`` up to and including ``current`` (dates or datetimes)."""
    from avshunter.shared.xnys_calendar import xnys_sessions_between
    return xnys_sessions_between(pd.Timestamp(previous).date(), pd.Timestamp(current).date())


def _price_history_segment(ohlcv: pd.DataFrame, close_col: str):
    """Return (segment, state, break_date, reason) for the current security's price history (DQ-12)."""
    frame = ohlcv[ohlcv[close_col].notna()].reset_index(drop=True)
    closes = frame[close_col].astype(float).to_numpy()
    if closes.size == 0:
        return frame, PRICE_HISTORY_INTACT, None, None
    if closes[-1] < SUB_CENT_PRICE:
        return frame.iloc[0:0], PRICE_HISTORY_SUB_CENT, None, BREAK_REASON_SUB_CENT
    dates = frame['date'] if 'date' in frame.columns else None
    break_at, reason = None, None
    for i in range(1, closes.size):
        previous, current = closes[i - 1], closes[i]
        cause = None
        if previous > 0 and current > 0 and (current / previous >= PRICE_BREAK_RATIO
                                              or previous / current >= PRICE_BREAK_RATIO):
            cause = BREAK_REASON_RATIO
        elif previous < SUB_CENT_PRICE and current >= SUB_CENT_PRICE:
            cause = BREAK_REASON_SUB_CENT
        elif dates is not None and pd.notna(dates.iloc[i - 1]) and pd.notna(dates.iloc[i]) \
                and _sessions_between(dates.iloc[i - 1], dates.iloc[i]) > PRICE_GAP_SESSIONS:
            cause = BREAK_REASON_GAP
        if cause is not None:
            break_at, reason = i, cause
    if break_at is None:
        return frame, PRICE_HISTORY_INTACT, None, None
    segment = frame.iloc[break_at:].reset_index(drop=True)
    break_date = str(pd.Timestamp(dates.iloc[break_at]).date()) if dates is not None else None
    return segment, PRICE_HISTORY_BREAK_TRUNCATED, break_date, reason


def compute_forward_variance(
    ticker:       str,
    ohlcv:        pd.DataFrame,
    implied_vol:  Optional[float] = None,  # current market IV (annualised decimal); None/NaN/<=0 = missing
    regime:       str   = '',     # macro regime label: recorded for display only, never used in a value
) -> ForwardVarianceResult:
    """
    Main entry point. Accepts OHLCV DataFrame, returns ForwardVarianceResult.

    ohlcv must have columns: close (or Close), optionally high/low.
    Sorted oldest-first.

    implied_vol: pass the current ATM IV from options intelligence (annualised decimal).
    If missing (None, NaN or <= 0), iv_tailwind_score is None with iv_tailwind_state='IV_MISSING'.
    No usable price history gives forward_realised_vol=None with an explicit forecast_state.
    """
    regime_display = '' if regime is None else str(regime)

    history_state, break_date, break_reason = PRICE_HISTORY_INTACT, None, None

    def _no_forecast(state: str, error: str, n_bars: int = 0) -> ForwardVarianceResult:
        return ForwardVarianceResult(
            ticker=ticker, forward_realised_vol=None,
            vol_forecast_confidence=None,
            expected_move_1_5d=None, expected_move_6_10d=None,
            expected_move_11_20d=None, iv_tailwind_score=None,
            jump_risk_flag=None, method=METHOD_NO_FORECAST,
            n_bars_used=n_bars, error=error, forecast_state=state,
            jump_risk_state=JUMP_RISK_NOT_ASSESSED_NO_FORECAST,
            macro_regime_display=regime_display,
            price_history_state=history_state, price_history_break_date=break_date,
            price_history_break_reason=break_reason,
        )

    close_col = 'close' if 'close' in ohlcv.columns else 'Close'

    if ohlcv.empty or close_col not in ohlcv.columns:
        return _no_forecast(FORECAST_MISSING_PRICES, 'empty_or_no_close_column')

    ohlcv, history_state, break_date, break_reason = _price_history_segment(ohlcv, close_col)
    if history_state == PRICE_HISTORY_SUB_CENT:
        return _no_forecast(FORECAST_MISSING_PRICES, 'latest_close_below_sub_cent_threshold')
    prices  = ohlcv[close_col].dropna()
    if history_state == PRICE_HISTORY_BREAK_TRUNCATED and len(prices) <= MIN_BARS_EWMA:
        history_state = PRICE_HISTORY_BREAK_INSUFFICIENT
        return _no_forecast(FORECAST_MISSING_PRICES, 'too_little_history_after_price_break', max(len(prices) - 1, 0))
    if len(prices) < 2:
        return _no_forecast(FORECAST_MISSING_PRICES, 'fewer_than_two_closes')
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
        # Only the GARCH(1,1) fallback stores true 'alpha'/'beta' parameters
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
            # GARCH(1,1): store real stationarity parameters
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

    if ann_vol is None or not math.isfinite(float(ann_vol)):
        return _no_forecast(FORECAST_UNAVAILABLE, f'{method.lower()}_unavailable', n_bars)

    # No macro-regime adjustment: the former x1.10 (RISK_OFF/BEAR) and x1.05 (TRANSITIONAL)
    # multipliers let a macro label change the forecast, against CLAUDE.md rule 6 (removed
    # 17 Sep 2026, tests/test_layer3_volatility_integrity.py V1).
    raw_vol = float(ann_vol)
    if raw_vol < VOL_FLOOR:
        ann_vol, forecast_state = float(VOL_FLOOR), FORECAST_CLIPPED_AT_FLOOR
    elif raw_vol > VOL_CAP:
        ann_vol, forecast_state = float(VOL_CAP), FORECAST_CLIPPED_AT_CAP
    else:
        ann_vol, forecast_state = raw_vol, FORECAST_OK

    # ── Expected moves ─────────────────────────────────────────────────────────
    em_1_5   = _expected_move(ann_vol, 5)
    em_6_10  = _expected_move(ann_vol, 10) - _expected_move(ann_vol, 5)
    em_11_20 = _expected_move(ann_vol, 20) - _expected_move(ann_vol, 10)

    # ── IV tailwind score ──────────────────────────────────────────────────────
    # Positive = market IV > forecast realised vol = options EXPENSIVE (headwind)
    # Negative = market IV < forecast realised vol = options CHEAP (tailwind)
    # Named "tailwind" from the long-option buyer's perspective:
    #   negative value means you are buying cheap → tailwind
    try:
        iv_value = None if implied_vol is None else float(implied_vol)
    except (TypeError, ValueError):
        iv_value = None
    iv_present = iv_value is not None and math.isfinite(iv_value) and iv_value > 0
    iv_tailwind = float(iv_value - ann_vol) if iv_present else None

    # ── Jump risk ──────────────────────────────────────────────────────────────
    jump_flag, jump_state = _jump_risk(returns)

    # ── Confidence ────────────────────────────────────────────────────────────
    stab  = _vol_stability(returns)
    conf  = _confidence_score(n_bars, stab, method)
    # No macro-regime confidence penalty (rule 6; removed 17 Sep 2026).

    return ForwardVarianceResult(
        ticker                  = ticker,
        forward_realised_vol    = ann_vol,
        vol_forecast_confidence = conf,
        expected_move_1_5d      = em_1_5,
        expected_move_6_10d     = em_6_10,
        expected_move_11_20d    = em_11_20,
        iv_tailwind_score       = iv_tailwind,
        jump_risk_flag          = jump_flag,
        jump_risk_state         = jump_state,
        method                  = method,
        garch_omega             = garch_omega,
        garch_alpha             = garch_alpha,
        garch_beta              = garch_beta,
        n_bars_used             = n_bars,
        forecast_state          = forecast_state,
        macro_regime_display    = regime_display,
        forward_realised_vol_raw = raw_vol,
        price_history_state     = history_state,
        price_history_break_date = break_date,
        price_history_break_reason = break_reason,
    )
