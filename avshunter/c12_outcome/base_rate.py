"""Matched base rate: the same barrier distances (in ATR units) applied to every ticker (pure)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Mapping, Sequence

import numpy as np

from .geometry import classify
from .model import Bar, Direction, Geometry, UnderlyingOutcome
from .passage import evaluate_passage


def average_true_range(bars_before: Sequence[Bar], period: int) -> float | None:
    """Simple mean of the last ``period`` true ranges ending at the evidence session."""
    if len(bars_before) <= period:
        return None
    window = bars_before[-(period + 1):]
    ranges = []
    for previous, current in zip(window, window[1:]):
        ranges.append(max(current.high - current.low, abs(current.high - previous.close), abs(current.low - previous.close)))
    value = sum(ranges) / len(ranges)
    return value if value > 0 else None


def distances_in_atr(geometry: Geometry, atr: float) -> tuple[float | None, float]:
    stop_distance = abs(geometry.reference_price - geometry.invalidation_price) / atr
    target_distance = (
        abs(geometry.target_price - geometry.reference_price) / atr
        if geometry.target_state.value == "LEVEL" else None
    )
    return target_distance, stop_distance


def synthetic_geometry(direction: Direction, reference: float, atr: float,
                       target_atr: float | None, stop_atr: float) -> Geometry:
    sign = direction.sign
    invalidation = reference - sign * stop_atr * atr
    target = None if target_atr is None else reference + sign * target_atr * atr
    return classify(direction.value, reference, invalidation, target, None)


def matched_outcomes(
    direction: Direction,
    target_atr: float | None,
    stop_atr: float,
    universe: Mapping[str, tuple[Sequence[Bar], Mapping[date, Bar]]],
    window_sessions: Sequence[date],
    window_length: int,
    atr_period: int,
) -> list[tuple[str, UnderlyingOutcome]]:
    """``universe``: ticker -> (bars up to and including the evidence session, bars after it by session)."""
    outcomes = []
    for ticker, (history, future) in universe.items():
        atr = average_true_range(history, atr_period)
        if atr is None or not history:
            continue
        geometry = synthetic_geometry(direction, history[-1].close, atr, target_atr, stop_atr)
        if not geometry.scorable:
            continue
        outcomes.append((ticker, evaluate_passage(geometry, window_sessions, future, window_length)))
    return outcomes


# --- vectorised matched base rate over a price panel (P0-8 increment 2) --------------

BASE_RATE_VERSION = "c12-base-rate-v1.0.0"


@dataclass(frozen=True, slots=True)
class Panel:
    """Dense session x ticker arrays (NaN where a bar is missing)."""
    sessions: tuple[date, ...]
    tickers: tuple[str, ...]
    open: np.ndarray
    high: np.ndarray
    low: np.ndarray
    close: np.ndarray

    def index_of(self, session: date) -> int | None:
        try:
            return self.sessions.index(session)
        except ValueError:
            return None


def build_panel(bars_by_ticker: Mapping[str, Sequence[Bar]], sessions: Sequence[date]) -> Panel:
    tickers = tuple(sorted(bars_by_ticker))
    row = {session: index for index, session in enumerate(sessions)}
    shape = (len(sessions), len(tickers))
    fields = ("open", "high", "low", "close")
    arrays = {name: np.full(shape, np.nan) for name in fields}
    for column, ticker in enumerate(tickers):
        for bar in bars_by_ticker[ticker]:
            index = row.get(bar.session)
            if index is None:
                continue
            for name in fields:
                arrays[name][index, column] = getattr(bar, name)
    return Panel(tuple(sessions), tickers, **arrays)


def panel_atr(panel: Panel, index: int, period: int) -> np.ndarray:
    """Simple mean true range over the ``period`` sessions ending at ``index``; NaN if any bar is missing."""
    first = index - period
    if first < 0:
        return np.full(len(panel.tickers), np.nan)
    previous_close = panel.close[first:index]
    high = panel.high[first + 1:index + 1]
    low = panel.low[first + 1:index + 1]
    true_range = np.maximum.reduce([high - low, np.abs(high - previous_close), np.abs(low - previous_close)])
    atr = true_range.mean(axis=0)            # NaN propagates when any bar is missing
    return np.where(atr > 0, atr, np.nan)


@dataclass(frozen=True, slots=True)
class MatchedIncidence:
    observed_sessions: int
    universe: int                  # tickers with complete bars and ATR
    excluded: int
    target_fractions: tuple[float, ...]   # share of universe resolving target-first at sessions 1..n
    stop_fractions: tuple[float, ...]     # stop-first (ambiguous counted as stop)


def matched_incidence(
    direction: Direction,
    target_atr: float | None,
    stop_atr: float,
    panel: Panel,
    evidence_index: int,
    observed_sessions: int,
    atr: np.ndarray,
) -> MatchedIncidence:
    """Apply the prediction's barrier distances (in ATR units) to every ticker in the panel."""
    reference = panel.close[evidence_index]
    span = slice(evidence_index + 1, evidence_index + 1 + observed_sessions)
    high, low = panel.high[span], panel.low[span]
    complete = np.all(np.isfinite(high) & np.isfinite(low), axis=0) if observed_sessions else np.ones(len(panel.tickers), bool)
    valid = np.isfinite(reference) & (reference > 0) & np.isfinite(atr) & complete
    count = int(valid.sum())
    if not count or not observed_sessions:
        empty = tuple(float(0) for _ in range(observed_sessions))
        return MatchedIncidence(observed_sessions, count, len(panel.tickers) - count, empty, empty)
    up = (high[:, valid] - reference[valid]) / atr[valid]
    down = (low[:, valid] - reference[valid]) / atr[valid]
    favourable, adverse = (up, -down) if direction is Direction.BULL else (-down, up)
    stop_hit = adverse >= stop_atr
    target_hit = favourable >= target_atr if target_atr is not None else np.zeros_like(stop_hit)
    any_hit = stop_hit | target_hit
    first = np.where(any_hit.any(axis=0), any_hit.argmax(axis=0), -1)
    resolved = first >= 0
    columns = np.nonzero(resolved)[0]
    at_first_stop = stop_hit[first[resolved], columns]
    sessions_hit = first[resolved]
    target_counts = np.bincount(sessions_hit[~at_first_stop], minlength=observed_sessions)
    stop_counts = np.bincount(sessions_hit[at_first_stop], minlength=observed_sessions)
    return MatchedIncidence(
        observed_sessions, count, len(panel.tickers) - count,
        tuple(float(v) / count for v in target_counts), tuple(float(v) / count for v in stop_counts),
    )
