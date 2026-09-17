"""Matched base rate: the same barrier distances (in ATR units) applied to every ticker (pure)."""

from __future__ import annotations

from datetime import date
from typing import Mapping, Sequence

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
