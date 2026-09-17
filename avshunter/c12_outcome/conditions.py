"""Condition labels for outcome analysis (P0-8 §6a; pure).

Guard: these labels are analysis dimensions in outcome reports only. No gate, score,
rank, valuation or thesis may read them (spec §14, CLAUDE.md rule 6).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Mapping, Sequence

import numpy as np

from avshunter.shared.xnys_calendar import xnys_sessions_between

CONDITION_VERSION = "c12-conditions-v1.0.0"

MACRO_FIELDS = (
    "regime_label", "regime_state", "regime_probability", "macro_conviction",
    "risk_on_off_switch", "credit_state", "net_liquidity_score", "rates_impulse",
)


@dataclass(frozen=True, slots=True)
class ConditionSettings:
    market_ticker: str
    trend_short_sessions: int
    trend_long_sessions: int
    vol_sessions: int
    vol_lookback_sessions: int
    breadth_sessions: int
    drawdown_lookback_sessions: int
    vol_state_bands: tuple[float, float]
    breadth_state_bands: tuple[float, float]

    @property
    def market_history_sessions(self) -> int:
        return max(self.trend_long_sessions, self.vol_lookback_sessions + self.vol_sessions + 1,
                   self.drawdown_lookback_sessions)


def band(value: float | None, edges: Sequence[float]) -> str:
    if value is None or not np.isfinite(value):
        return "MISSING"
    low, high = edges
    if value < low:
        return "LOW"
    if value < high:
        return "MID"
    return "HIGH"


@dataclass(frozen=True, slots=True)
class MacroCondition:
    macro_source: str            # RUN_SNAPSHOT | NONE
    macro_run_id: str | None
    macro_as_of_utc: str | None
    macro_report_date: str | None
    macro_freshness: str         # CURRENT | STALE | MISSING
    macro_lag_sessions: int | None
    fields: dict


def macro_condition(snapshot: Mapping[str, Any] | None, run_id: str | None, evidence_session: date) -> MacroCondition:
    if not snapshot:
        return MacroCondition("NONE", run_id, None, None, "MISSING", None, {name: None for name in MACRO_FIELDS})
    report_text = snapshot.get("report_date")
    try:
        report_date = date.fromisoformat(str(report_text).split("T")[0]) if report_text else None
    except ValueError:
        report_date = None
    if report_date is None:
        freshness, lag = "MISSING", None
    elif report_date >= evidence_session:
        freshness, lag = "CURRENT", 0
    else:
        freshness, lag = "STALE", xnys_sessions_between(report_date, evidence_session)
    fields = {name: snapshot.get(name) for name in MACRO_FIELDS}
    return MacroCondition("RUN_SNAPSHOT", run_id, snapshot.get("as_of_utc"),
                          report_date.isoformat() if report_date else None, freshness, lag, fields)


@dataclass(frozen=True, slots=True)
class MarketCondition:
    market_trend_state: str      # ABOVE_BOTH | ABOVE_LONG_ONLY | ABOVE_SHORT_ONLY | BELOW_BOTH | INSUFFICIENT_HISTORY
    market_vol_percentile: float | None
    market_vol_state: str
    market_breadth: float | None
    market_breadth_state: str
    market_drawdown_pct: float | None


def market_condition(market_closes: Sequence[float], panel_closes: np.ndarray, settings: ConditionSettings) -> MarketCondition:
    """``market_closes``: benchmark closes up to and including the evidence session (chronological).
    ``panel_closes``: session x ticker closes ending at the evidence session."""
    closes = np.asarray([c for c in market_closes if c is not None and np.isfinite(c)], dtype=float)
    last = closes[-1] if closes.size else np.nan

    if closes.size >= settings.trend_long_sessions:
        short = closes[-settings.trend_short_sessions:].mean()
        long = closes[-settings.trend_long_sessions:].mean()
        above_short, above_long = last > short, last > long
        trend = ("ABOVE_BOTH" if above_short and above_long else "ABOVE_LONG_ONLY" if above_long
                 else "ABOVE_SHORT_ONLY" if above_short else "BELOW_BOTH")
    else:
        trend = "INSUFFICIENT_HISTORY"

    percentile = None
    needed = settings.vol_lookback_sessions + settings.vol_sessions + 1
    if closes.size >= needed:
        returns = np.diff(np.log(closes[-needed:]))
        windows = np.lib.stride_tricks.sliding_window_view(returns, settings.vol_sessions)
        vols = windows.std(axis=1, ddof=1)
        current, prior = vols[-1], vols[:-1]
        percentile = float(np.mean(prior <= current))

    breadth = None
    if panel_closes.shape[0] >= settings.breadth_sessions:
        window = panel_closes[-settings.breadth_sessions:]
        complete = np.all(np.isfinite(window), axis=0)
        if complete.any():
            breadth = float(np.mean(window[-1, complete] > window[:, complete].mean(axis=0)))

    drawdown = None
    if closes.size >= settings.drawdown_lookback_sessions:
        drawdown = float(last / closes[-settings.drawdown_lookback_sessions:].max() - 1.0)

    return MarketCondition(trend, percentile, band(percentile, settings.vol_state_bands),
                           breadth, band(breadth, settings.breadth_state_bands), drawdown)
