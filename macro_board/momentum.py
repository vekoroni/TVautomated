"""The ETF's own price momentum and what followed similar runs on recorded history.

Replaces the textbook assumption that an extended move means a late entry. On 6 Oct 2026
the 2021-2026 history showed the opposite for SPY and QQQ: after 5+ consecutive up closes
the next 20 sessions averaged +2.19% (SPY) and +2.86% (QQQ) against +0.92% / +1.18% for all
sessions. The board measures this per ETF instead of assuming either way.
"""

from __future__ import annotations

from typing import Mapping, Sequence

import numpy as np
import pandas as pd

from .conditions import MISSING
from .evidence import ticker_evidence


def streak(closes: pd.Series) -> pd.Series:
    """Consecutive up closes (positive) or down closes (negative); 0 on an unchanged close."""
    change = np.sign(closes.diff())
    out = np.zeros(len(closes))
    for i in range(1, len(closes)):
        step = change.iloc[i]
        if not np.isfinite(step) or step == 0:
            out[i] = 0
        elif step > 0:
            out[i] = out[i - 1] + 1 if out[i - 1] > 0 else 1
        else:
            out[i] = out[i - 1] - 1 if out[i - 1] < 0 else -1
    result = pd.Series(out, index=closes.index)
    result[closes.isna()] = np.nan
    return result


def streak_state(streaks: pd.Series, buckets: Sequence[Sequence]) -> pd.Series:
    def label(value):
        if value is None or not np.isfinite(value):
            return MISSING
        for low, high, name in buckets:
            if low <= value <= high:
                return name
        return "UNCHANGED"
    return streaks.map(label)


def extension_state(closes: pd.Series, sessions: int, rv_sessions: int, band_sd: float) -> tuple[pd.Series, pd.Series]:
    """Return over ``sessions`` in units of trailing realised vol, and its band label."""
    log_returns = np.log(closes).diff()
    rv = log_returns.rolling(rv_sessions, min_periods=rv_sessions).std() * np.sqrt(252)
    z = (closes / closes.shift(sessions) - 1.0) / (rv * np.sqrt(sessions / 252.0))
    state = np.where(z >= band_sd, "EXTENDED_UP", np.where(z <= -band_sd, "EXTENDED_DOWN", "NOT_EXTENDED"))
    return z, pd.Series(np.where(z.isna(), MISSING, state), index=closes.index)


def state_evidence(fwd: pd.Series, states: pd.Series, current: str, horizon: int, settings: Mapping) -> dict:
    """What the ETF did next after sessions in the same momentum state (same lean rules,
    independent windows and holdout as the macro leans)."""
    if current == MISSING:
        return {"lean": "INSUFFICIENT_SAMPLE", "holdout": "NOT_APPLICABLE", "state": current}
    mask = states.reindex(fwd.index) == current
    return {**ticker_evidence(fwd, mask, horizon, settings), "state": current}


def momentum_block(closes: pd.Series, fwd_by_h: Mapping[int, pd.Series], settings: Mapping, cfg: Mapping) -> dict:
    """Current momentum states and the measured evidence for each, per horizon."""
    s = closes.dropna()
    if len(s) < int(cfg["rv_sessions"]) + 25:
        return {"status": "INSUFFICIENT_HISTORY"}
    streaks = streak(closes)
    states = {"streak": streak_state(streaks, cfg["streak_buckets"])}
    z = {}
    for window in cfg["extension_windows"]:
        z[str(window)], states[f"ext{window}"] = extension_state(closes, int(window), int(cfg["rv_sessions"]),
                                                                 float(cfg["extension_band_sd"]))
    last = closes.last_valid_index()
    current = {name: str(series.loc[last]) for name, series in states.items()}
    evidence = {name: {str(h): state_evidence(fwd, states[name], current[name], h, settings)
                       for h, fwd in fwd_by_h.items()} for name in states}
    return {"status": "OK", "streak": None if pd.isna(streaks.loc[last]) else int(streaks.loc[last]),
            "z": {k: (None if pd.isna(v.loc[last]) else round(float(v.loc[last]), 3)) for k, v in z.items()},
            "current": current, "evidence": evidence}
