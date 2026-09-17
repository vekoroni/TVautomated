"""Forward hypothesis tests (pure) — H9R gap-up reversal (ACK 17 Sep 2026; SIGNAL_RESEARCH_PLAN_A.md Addendum 2).

Measurement only: events and outcomes are recorded and evaluated; nothing here feeds a decision.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import math
from typing import Iterable, Mapping, Sequence

import numpy as np

EVENT_UP, EVENT_DOWN = "UP", "DOWN"
HELD, FADED = "HELD", "FADED"
SCORED, DATA_BREAK = "SCORED", "DATA_BREAK"
INSUFFICIENT_EVIDENCE, PASS, NOT_PASSED = "INSUFFICIENT_EVIDENCE", "PASS", "NOT_PASSED"


@dataclass(frozen=True, slots=True)
class GapHypothesisSettings:
    hypothesis_id: str
    forward_start: date
    gap_atr_multiple: float
    volume_multiple: float
    atr_sessions: int
    volume_lookback_sessions: int
    liquidity_lookback_sessions: int
    liquidity_min_dollar_volume: float
    integrity_lookback_sessions: int
    break_ratio: float
    sub_cent_price: float
    spacing_sessions: int
    horizons: tuple[int, ...]
    primary_horizon: int
    primary_direction: str
    min_event_dates: int
    min_events: int
    pass_t: float
    share_spread_sessions: int = 60

    @property
    def lookback_sessions(self) -> int:
        return max(self.atr_sessions + 1, self.volume_lookback_sessions, self.liquidity_lookback_sessions,
                   self.integrity_lookback_sessions, self.share_spread_sessions)


@dataclass(frozen=True, slots=True)
class PricePanel:
    """Dense session x ticker arrays (NaN where a bar is missing)."""
    sessions: tuple[date, ...]
    tickers: tuple[str, ...]
    open: np.ndarray
    high: np.ndarray
    low: np.ndarray
    close: np.ndarray
    volume: np.ndarray


@dataclass(frozen=True, slots=True)
class GapEvent:
    ticker: str
    event_session: date
    direction: str
    held: str
    gap_atr: float
    entry_close: float
    share_spread: float | None


@dataclass(frozen=True, slots=True)
class HypothesisOutcome:
    ticker: str
    event_session: date
    horizon: int
    exit_session: date
    raw_return: float | None
    universe_median: float | None
    net_return: float | None
    state: str


def settings_from_snapshot(snapshot) -> GapHypothesisSettings:
    def value(key: str):
        return snapshot.get(key).value
    return GapHypothesisSettings(
        hypothesis_id=str(value("outcome.hypothesis.h9r.hypothesis_id")),
        forward_start=date.fromisoformat(str(value("outcome.hypothesis.h9r.forward_start"))),
        gap_atr_multiple=float(value("outcome.hypothesis.h9r.gap_atr_multiple")),
        volume_multiple=float(value("outcome.hypothesis.h9r.volume_multiple")),
        atr_sessions=int(value("outcome.atr_period")),
        volume_lookback_sessions=int(value("outcome.hypothesis.h9r.volume_lookback_sessions")),
        liquidity_lookback_sessions=int(value("outcome.hypothesis.h9r.liquidity_lookback_sessions")),
        liquidity_min_dollar_volume=float(value("outcome.hypothesis.h9r.liquidity_min_dollar_volume")),
        integrity_lookback_sessions=int(value("outcome.hypothesis.h9r.integrity_lookback_sessions")),
        break_ratio=float(value("outcome.hypothesis.h9r.break_ratio")),
        sub_cent_price=float(value("outcome.hypothesis.h9r.sub_cent_price")),
        spacing_sessions=int(value("outcome.hypothesis.h9r.spacing_sessions")),
        horizons=tuple(int(h) for h in value("outcome.hypothesis.h9r.horizons")),
        primary_horizon=int(value("outcome.hypothesis.h9r.primary_horizon")),
        primary_direction=str(value("outcome.hypothesis.h9r.primary_direction")),
        min_event_dates=int(value("outcome.hypothesis.h9r.min_event_dates")),
        min_events=int(value("outcome.hypothesis.h9r.min_events")),
        pass_t=float(value("outcome.hypothesis.h9r.pass_t")),
        share_spread_sessions=int(value("outcome.hypothesis.h9r.share_spread_sessions")),
    )


def _clean_rows(close: np.ndarray, s: GapHypothesisSettings) -> np.ndarray:
    """True per ticker when no close is sub-cent and no one-bar move reaches the break ratio in these rows."""
    with np.errstate(divide="ignore", invalid="ignore"):
        steps = np.abs(np.diff(np.log(close), axis=0))
    no_break = ~(steps >= math.log(s.break_ratio)).any(axis=0)
    no_sub_cent = ~(close < s.sub_cent_price).any(axis=0)
    complete = np.isfinite(close).all(axis=0)
    return no_break & no_sub_cent & complete


def _share_spread(p: PricePanel, i: int, j: int, s: GapHypothesisSettings) -> float | None:
    rows = slice(i - s.share_spread_sessions + 1, i + 1)
    c = np.log(p.close[rows, j])
    eta = (np.log(p.high[rows, j]) + np.log(p.low[rows, j])) / 2
    products = (c[:-1] - eta[:-1]) * (c[:-1] - eta[1:])
    products = products[np.isfinite(products)]
    if products.size == 0:
        return None
    return float(math.sqrt(max(4.0 * float(products.mean()), 0.0)))


def detect_events(p: PricePanel, i: int, s: GapHypothesisSettings,
                  last_event_session: Mapping[str, date]) -> list[GapEvent]:
    if p.sessions[i] < s.forward_start or i < s.lookback_sessions:
        return []
    prev_close = p.close[i - 1]
    rows = slice(i - s.atr_sessions, i)
    prior_close = p.close[i - s.atr_sessions - 1:i - 1]
    high, low = p.high[rows], p.low[rows]
    true_range = np.maximum.reduce([high - low, np.abs(high - prior_close), np.abs(low - prior_close)])
    atr = true_range.mean(axis=0)
    gap = p.open[i] - prev_close
    median_volume = np.median(p.volume[i - s.volume_lookback_sessions:i], axis=0)
    dollar = np.median(p.close[i - s.liquidity_lookback_sessions:i] * p.volume[i - s.liquidity_lookback_sessions:i], axis=0)
    clean = _clean_rows(p.close[i - s.integrity_lookback_sessions:i + 1], s)
    with np.errstate(invalid="ignore"):
        is_event = ((np.abs(gap) >= s.gap_atr_multiple * atr) & (atr > 0)
                    & (p.volume[i] >= s.volume_multiple * median_volume)
                    & (dollar >= s.liquidity_min_dollar_volume) & clean)
    events = []
    for j in np.nonzero(is_event)[0]:
        ticker = p.tickers[j]
        last = last_event_session.get(ticker)
        if last is not None and last in p.sessions and i - p.sessions.index(last) < s.spacing_sessions:
            continue
        sign = 1.0 if gap[j] > 0 else -1.0
        held = HELD if sign * (p.close[i, j] - p.open[i, j]) > 0 else FADED
        events.append(GapEvent(ticker, p.sessions[i], EVENT_UP if sign > 0 else EVENT_DOWN, held,
                               float(abs(gap[j]) / atr[j]), float(p.close[i, j]), _share_spread(p, i, j, s)))
    return events


def score_outcome(p: PricePanel, event: GapEvent, horizon: int, s: GapHypothesisSettings) -> HypothesisOutcome | None:
    if event.event_session not in p.sessions or event.ticker not in p.tickers:
        return None
    i, j = p.sessions.index(event.event_session), p.tickers.index(event.ticker)
    if i + horizon >= len(p.sessions):
        return None
    exit_session = p.sessions[i + horizon]
    window = p.close[i:i + horizon + 1]
    if not _clean_rows(window[:, [j]], s)[0]:
        return HypothesisOutcome(event.ticker, event.event_session, horizon, exit_session, None, None, None, DATA_BREAK)
    raw = float(math.log(p.close[i + horizon, j] / p.close[i, j]))
    liquid = np.median(p.close[i - s.liquidity_lookback_sessions + 1:i + 1] * p.volume[i - s.liquidity_lookback_sessions + 1:i + 1],
                       axis=0) >= s.liquidity_min_dollar_volume
    universe = liquid & _clean_rows(p.close[i - s.integrity_lookback_sessions:i + horizon + 1], s)
    with np.errstate(divide="ignore", invalid="ignore"):
        returns = np.log(p.close[i + horizon] / p.close[i])
    median = float(np.nanmedian(returns[universe]))
    return HypothesisOutcome(event.ticker, event.event_session, horizon, exit_session, raw, median, raw - median, SCORED)


def evaluate(items: Iterable[tuple[str, float, float | None]], s: GapHypothesisSettings) -> dict:
    """items: (event date, net return, share spread). Clustered-by-date t; gated verdict."""
    rows = [(d, float(x), spread) for d, x, spread in items if x is not None and math.isfinite(float(x))]
    dates = sorted({d for d, _, _ in rows})
    out = {"events": len(rows), "event_dates": len(dates), "mean": None, "t": None, "median_share_spread": None,
           "verdict": INSUFFICIENT_EVIDENCE}
    if not rows:
        return out
    values = np.array([x for _, x, _ in rows])
    spreads = [sp for _, _, sp in rows if sp is not None and math.isfinite(sp)]
    out["mean"] = float(values.mean())
    out["median_share_spread"] = float(np.median(spreads)) if spreads else None
    if len(dates) < s.min_event_dates or len(rows) < s.min_events:
        return out
    residual = values - values.mean()
    cluster_sums = {}
    for (d, _, _), e in zip(rows, residual):
        cluster_sums[d] = cluster_sums.get(d, 0.0) + e
    sums = np.array(list(cluster_sums.values()))
    g = len(sums)
    se = math.sqrt((g / (g - 1)) * float(sums @ sums)) / len(values)
    t = float(values.mean() / se) if se > 0 else float("nan")
    out["t"] = t
    beyond = t <= s.pass_t if s.pass_t < 0 else t >= s.pass_t
    economic = out["median_share_spread"] is not None and abs(out["mean"]) > out["median_share_spread"]
    out["verdict"] = PASS if (beyond and economic) else NOT_PASSED
    return out
