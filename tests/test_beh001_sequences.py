"""BEH-001 L1-L2: bars become dated swings, waves, the current leg and ranges.

Business rules:
- Only completed, valid bars are read; invalid bars give NOT_EVALUATED.
- A pivot exists only from the bar that confirms it (as-of; no future bars).
- Swings are tracked at two degrees (major for campaign, minor for setup).
- The current, unconfirmed leg is always part of the structure.
- One rule for both sides: a log-reflected chart gives mirrored structure.
"""
import math

import numpy as np
import pandas as pd

from domain.structure_behaviour.policy import load_policy
from domain.structure_behaviour.sequences import build_sequences, reflect_bars

import copy

POLICY = copy.deepcopy(dict(load_policy()))
POLICY["timeframes"]["1d"]["min_bars"] = 20  # structural fixtures are short


def zigzag_bars(points, bars_per_leg=6, start="2026-01-02", volume=1_000_000.0):
    """Piecewise log-linear closes through the given turning points."""
    closes = [points[0]]
    for a, b in zip(points, points[1:]):
        for k in range(1, bars_per_leg + 1):
            closes.append(a * (b / a) ** (k / bars_per_leg))
    closes = np.array(closes)
    opens = np.concatenate([[closes[0]], closes[:-1]])
    frame = pd.DataFrame({
        "date": pd.bdate_range(start, periods=len(closes)),
        "open": opens, "close": closes,
        "high": np.maximum(opens, closes) * math.exp(0.004),
        "low": np.minimum(opens, closes) * math.exp(-0.004),
        "volume": volume,
    })
    return frame


TREND_DOWN = [100, 92, 96, 86, 90, 80, 84, 74, 77]
RANGE = [100, 90, 99, 90.5, 99.5, 90.2, 99.2, 90.4, 99.4, 91, 98]


def test_invalid_bars_are_not_evaluated():
    bars = zigzag_bars(TREND_DOWN)
    bars.loc[10, "low"] = bars.loc[10, "high"] * 1.01
    result = build_sequences(bars, "1d", POLICY)
    assert result.status == "NOT_EVALUATED_INVALID_BARS"
    assert result.minor_pivots == () and result.major_pivots == ()


def test_pivots_carry_confirmation_lag_and_never_use_future_bars():
    bars = zigzag_bars(TREND_DOWN)
    full = build_sequences(bars, "1d", POLICY)
    assert full.status == "EVALUATED"
    for pivot in full.minor_pivots:
        assert pivot.confirmed_index > pivot.index
        if pivot.confirmed_index < POLICY["timeframes"]["1d"]["min_bars"]:
            continue  # a cut shorter than the minimum is NOT_EVALUATED by design
        cut = build_sequences(bars.iloc[: pivot.confirmed_index + 1].reset_index(drop=True), "1d", POLICY)
        assert any(p.index == pivot.index and p.kind == pivot.kind for p in cut.minor_pivots)
        early = build_sequences(bars.iloc[: pivot.confirmed_index].reset_index(drop=True), "1d", POLICY)
        assert not any(p.index == pivot.index and p.kind == pivot.kind for p in early.minor_pivots)


def test_major_degree_is_coarser_than_minor():
    result = build_sequences(zigzag_bars(TREND_DOWN), "1d", POLICY)
    assert 0 < len(result.major_pivots) <= len(result.minor_pivots)


def test_current_leg_is_always_present():
    result = build_sequences(zigzag_bars(TREND_DOWN), "1d", POLICY)
    leg = result.current_leg
    assert leg is not None
    assert leg.confirmed is False
    assert leg.direction in {"UP", "DOWN"}
    assert leg.end_index == len(zigzag_bars(TREND_DOWN)) - 1 or leg.extreme_index <= leg.end_index


def test_range_is_detected_and_trend_is_not_a_range():
    ranged = build_sequences(zigzag_bars(RANGE), "1d", POLICY)
    trending = build_sequences(zigzag_bars(TREND_DOWN), "1d", POLICY)
    assert ranged.trading_range is not None
    assert ranged.trading_range.support < ranged.trading_range.resistance
    assert trending.trading_range is None


def test_reflected_bars_give_mirrored_structure():
    bars = zigzag_bars(TREND_DOWN)
    original = build_sequences(bars, "1d", POLICY)
    mirrored = build_sequences(reflect_bars(bars), "1d", POLICY)
    swap = {"H": "L", "L": "H"}
    assert [(p.index, swap[p.kind]) for p in original.minor_pivots] == [(p.index, p.kind) for p in mirrored.minor_pivots]
    for a, b in zip(original.minor_waves, mirrored.minor_waves):
        assert math.isclose(a.distance_atr, b.distance_atr, rel_tol=1e-9)
        assert {a.direction, b.direction} == {"UP", "DOWN"}


def test_too_few_bars_is_not_evaluated_never_a_guess():
    short = zigzag_bars(TREND_DOWN)
    result = build_sequences(short, "1d", load_policy())  # live policy: 120 daily bars
    assert result.status == "NOT_EVALUATED_INSUFFICIENT_BARS"
    assert result.minor_pivots == ()
