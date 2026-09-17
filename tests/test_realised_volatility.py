"""Realised volatility estimators (WP1 volatility step, ACK 17 Sep 2026) — business rules first.

Units: per-session volatility of log price (not annualised). Annualisation is a separate,
explicit conversion so a comparison with implied volatility states its day-count basis.
"""

from __future__ import annotations

import math

import pytest

from contracts.realised_volatility import (
    MissingPriceData, annualise, close_to_close, ewma_forecast, garman_klass, parkinson, yang_zhang,
)


def test_close_to_close_matches_hand_computation():
    closes = [100.0, 101.0, 99.0, 102.0]
    r = [math.log(101 / 100), math.log(99 / 101), math.log(102 / 99)]
    mean = sum(r) / 3
    expected = math.sqrt(sum((x - mean) ** 2 for x in r) / 2)
    assert close_to_close(closes) == pytest.approx(expected)


def test_parkinson_uses_high_low_range():
    highs, lows = [102.0, 104.0], [98.0, 100.0]
    expected = math.sqrt((math.log(102 / 98) ** 2 + math.log(104 / 100) ** 2) / 2 / (4 * math.log(2)))
    assert parkinson(highs, lows) == pytest.approx(expected)


def test_garman_klass_hand_computation():
    o, h, l, c = [100.0], [103.0], [99.0], [102.0]
    expected = math.sqrt(0.5 * math.log(103 / 99) ** 2 - (2 * math.log(2) - 1) * math.log(102 / 100) ** 2)
    assert garman_klass(o, h, l, c) == pytest.approx(expected)


def test_yang_zhang_captures_overnight_gaps_that_range_estimators_miss():
    # identical intraday ranges, but the second series gaps overnight every session
    prev = [100.0, 100.0, 100.0, 100.0, 100.0]
    no_gap = yang_zhang(opens=[100.0] * 4, highs=[101.0] * 4, lows=[99.0] * 4, closes=[100.0] * 4, previous_closes=prev[:4])
    gapped_opens = [104.0, 96.0, 104.0, 96.0]
    gap = yang_zhang(opens=gapped_opens, highs=[o + 1 for o in gapped_opens], lows=[o - 1 for o in gapped_opens],
                     closes=gapped_opens, previous_closes=prev[:4])
    assert gap > no_gap * 2
    assert parkinson([o + 1 for o in gapped_opens], [o - 1 for o in gapped_opens]) == pytest.approx(
        parkinson([101.0] * 4, [99.0] * 4), rel=0.05)


def test_ewma_forecast_weights_recent_returns_more():
    calm_then_wild = [0.001] * 30 + [0.05] * 5
    wild_then_calm = [0.05] * 5 + [0.001] * 30
    assert ewma_forecast(calm_then_wild, decay=0.94) > ewma_forecast(wild_then_calm, decay=0.94)


def test_missing_or_non_positive_prices_are_never_neutral():
    with pytest.raises(MissingPriceData):
        close_to_close([100.0])
    with pytest.raises(MissingPriceData):
        close_to_close([100.0, float("nan"), 101.0])
    with pytest.raises(MissingPriceData):
        parkinson([101.0], [0.0])


def test_annualise_states_its_basis():
    assert annualise(0.02, sessions_per_year=252) == pytest.approx(0.02 * math.sqrt(252))
