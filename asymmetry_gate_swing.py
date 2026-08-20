"""
asymmetry_gate_swing.py
=======================
Swing Asymmetry Gate — v1.0

Computes entry / stop / target / R from Crabel shelf geometry + ATR.
Replaces ALL hardcoded stop_loss = price * 0.97 usage in discovery.

Contract (per SME spec):
    compute_asymmetry_swing(direction, crabel_result, df_daily, cfg) -> dict

Output fields:
    entry           : float
    stop            : float
    target1         : float
    R_to_T1         : float
    asymmetry_pass  : bool    (R_to_T1 >= min_r_multiple)
    reason          : str     (audit — what drove the result)
    shelf_high      : float
    shelf_low       : float
    shelf_width     : float
    atr14           : float

Rule: if any required value is missing → asymmetry_pass=False, intent degrades to OBSERVE_ONLY.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from typing import Dict, Optional

from enums_structural import Direction


# ---------------------------------------------------------------------------
# Config defaults (all overridable via cfg attributes)
# ---------------------------------------------------------------------------
_DEFAULT_BREAKOUT_BUFFER = 0.003   # 0.3% — buffer above shelf_high on entry
_DEFAULT_ATR_K           = 0.75    # k multiplier for ATR-based stop
_DEFAULT_MIN_R           = 2.0     # minimum R for asymmetry_pass
_SHELF_LOOKBACK          = 30      # bars for shelf detection if not in crabel_result


# ---------------------------------------------------------------------------
# Public contract
# ---------------------------------------------------------------------------

def compute_asymmetry_swing(
    direction: str,
    crabel_result: Dict,
    df_daily: pd.DataFrame,
    cfg=None,
) -> Dict:
    """
    Compute structural entry/stop/target geometry for swing setups.

    Parameters
    ----------
    direction     : Direction.LONG / Direction.SHORT / Direction.NONE
    crabel_result : output of crabel_compression() — must contain shelf fields
    df_daily      : raw OHLCV DataFrame (needs 'high','low','close' columns)
    cfg           : UltimateConfig or None (uses defaults if None)

    Returns
    -------
    dict — see module docstring for fields
    """

    # Read config overrides
    breakout_buffer = getattr(cfg, "asymmetry_breakout_buffer", _DEFAULT_BREAKOUT_BUFFER)
    atr_k           = getattr(cfg, "asymmetry_atr_k",           _DEFAULT_ATR_K)
    min_r           = getattr(cfg, "asymmetry_min_r",           _DEFAULT_MIN_R)

    # --- Retrieve shelf levels ----------------------------------------------
    shelf_high = crabel_result.get("shelf_high")
    shelf_low  = crabel_result.get("shelf_low")
    shelf_width = crabel_result.get("shelf_width")

    # If crabel_result didn't include shelf, compute it from raw bars
    if shelf_high is None or shelf_low is None:
        shelf_high, shelf_low = _compute_shelf(df_daily, _SHELF_LOOKBACK)

    if shelf_high is None or shelf_low is None:
        return _fail("shelf_high/shelf_low unavailable — cannot compute asymmetry")

    if shelf_width is None or shelf_width <= 0:
        shelf_width = float(shelf_high) - float(shelf_low)

    shelf_high  = float(shelf_high)
    shelf_low   = float(shelf_low)
    shelf_width = float(shelf_width)

    if shelf_width <= 0:
        return _fail("shelf_width <= 0 — degenerate shelf, cannot compute asymmetry")

    # --- ATR14 --------------------------------------------------------------
    atr14 = _compute_atr14(df_daily)
    if atr14 is None or atr14 <= 0:
        return _fail("ATR14 unavailable or zero — cannot compute stop")

    # --- Direction gate -----------------------------------------------------
    if direction == Direction.NONE:
        return _fail("direction=NONE — no asymmetry geometry for NONE direction")

    # --- Entry / stop / target per spec ------------------------------------
    if direction == Direction.LONG:
        entry   = shelf_high * (1.0 + breakout_buffer)
        stop    = shelf_low  - atr_k * atr14
        target1 = entry + shelf_width     # measured move
        if (entry - stop) <= 0:
            return _fail("LONG: entry <= stop — invalid geometry")
        R = (target1 - entry) / (entry - stop)

    else:  # SHORT
        entry   = shelf_low  * (1.0 - breakout_buffer)
        stop    = shelf_high + atr_k * atr14
        target1 = entry - shelf_width     # measured move down
        if (stop - entry) <= 0:
            return _fail("SHORT: stop <= entry — invalid geometry")
        R = (entry - target1) / (stop - entry)

    # --- Asymmetry pass -----------------------------------------------------
    asymmetry_pass = R >= min_r

    reason = (
        f"{'PASS' if asymmetry_pass else 'FAIL'}: "
        f"R={R:.2f} ({'≥' if asymmetry_pass else '<'} {min_r}), "
        f"direction={direction}, "
        f"shelf=[{shelf_low:.2f}–{shelf_high:.2f}], "
        f"width={shelf_width:.2f}, "
        f"ATR14={atr14:.3f}, "
        f"entry={entry:.2f}, stop={stop:.2f}, target={target1:.2f}"
    )

    return {
        "entry":          round(entry,   4),
        "stop":           round(stop,    4),
        "target1":        round(target1, 4),
        "R_to_T1":        round(R,       3),
        "asymmetry_pass": asymmetry_pass,
        "reason":         reason,
        "shelf_high":     round(shelf_high,  4),
        "shelf_low":      round(shelf_low,   4),
        "shelf_width":    round(shelf_width, 4),
        "atr14":          round(atr14,       4),
        "error":          None,
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _fail(reason: str) -> Dict:
    return {
        "entry":          None,
        "stop":           None,
        "target1":        None,
        "R_to_T1":        0.0,
        "asymmetry_pass": False,
        "reason":         reason,
        "shelf_high":     None,
        "shelf_low":      None,
        "shelf_width":    None,
        "atr14":          None,
        "error":          reason,
    }


def _compute_shelf(df: pd.DataFrame, lookback: int) -> tuple:
    """Compute shelf_high / shelf_low from recent bars if crabel didn't provide them."""
    try:
        recent = df.tail(lookback)
        return float(recent["high"].max()), float(recent["low"].min())
    except Exception:
        return None, None


def _compute_atr14(df: pd.DataFrame, period: int = 14) -> Optional[float]:
    """Compute ATR14 from raw bars."""
    try:
        if df is None or len(df) < period + 1:
            return None
        prev_close = df["close"].shift(1)
        tr = pd.concat([
            df["high"] - df["low"],
            (df["high"] - prev_close).abs(),
            (df["low"]  - prev_close).abs(),
        ], axis=1).max(axis=1)
        atr_val = tr.rolling(period).mean().iloc[-1]
        return float(atr_val) if not np.isnan(atr_val) else None
    except Exception:
        return None
