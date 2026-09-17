"""DQ-12 price history integrity in the Layer 3 forecast (ACK 17 Sep 2026).

Evidence (Enhancements/expression_forensics/dq12_price_history_integrity_scan.csv): 47 of 3,618 tickers in the
canonical price store carry structural breaks — 55 one-bar moves of 10x or more (17 tickers), 214 sub-cent bars
(18 tickers), 37 gaps over 20 sessions (27 tickers). SOLS joins a defunct penny stock ($7.50 -> $0.000001,
2021-2025) to a new listing at $48.60 on 2025-10-30 (one-bar log return +13.1); its raw HAR-RV forecast reached
2,449% against 32% delivered. Unadjusted reverse splits, bankruptcy re-emergence and ticker reuse all look alike.

Rules:
  P1 a one-bar move at or above the governed break ratio starts a new security: the forecast uses only the
     bars from the break onwards, and the result records BREAK_TRUNCATED with the break date and reason;
  P2 an intact history (including genuine large but sub-break moves) is unchanged and records INTACT;
  P3 a break that leaves too little history gives no forecast (MISSING_PRICE_HISTORY) with
     BREAK_INSUFFICIENT_HISTORY — never a number built across the break;
  P4 sub-cent closes are not the current security's history: the forecast uses bars after the last one;
     a latest close below the threshold gives no forecast (SUB_CENT_PRICE);
  P5 a gap longer than the governed number of sessions (when dates are present) is a break;
  P6 thresholds come from governed configuration (config/governed_constants_v1.json price_history_integrity,
     loaded fail-closed);
  P7 the state and break date are published in the Layer 3 output (l3_price_history_state,
     l3_price_history_break_date, l3_price_history_break_reason).
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

import layer3_forward_variance as l3


def _frame(closes, start="2025-01-02", dates=None):
    closes = np.asarray(closes, dtype=float)
    if dates is None:
        dates = pd.bdate_range(start, periods=len(closes))
    return pd.DataFrame({"date": pd.to_datetime(dates), "open": closes, "high": closes * 1.01,
                         "low": closes * 0.99, "close": closes, "volume": 1_000_000})


def _walk(n, start_price, daily_vol, seed):
    rng = np.random.default_rng(seed)
    return start_price * np.exp(np.cumsum(rng.normal(0, daily_vol, n)))


def test_p6_thresholds_are_governed():
    ratio, sub_cent, gap_sessions = l3.PRICE_BREAK_RATIO, l3.SUB_CENT_PRICE, l3.PRICE_GAP_SESSIONS
    assert (ratio, sub_cent, gap_sessions) == (10.0, 0.01, 20)


def test_p1_ten_fold_jump_truncates_to_the_new_security():
    old = _walk(150, 5.0, 0.03, 1)
    new = _walk(120, 48.6, 0.02, 2)
    frame = _frame(np.concatenate([old * 0.001, new]))            # collapse then a 10x+ jump into the new listing
    result = l3.compute_forward_variance("SOLS", frame, implied_vol=0.4, regime="")
    only_new = l3.compute_forward_variance("SOLS", frame.iloc[150:].reset_index(drop=True), implied_vol=0.4, regime="")
    assert result.price_history_state == "BREAK_TRUNCATED"
    assert result.price_history_break_reason == "ONE_BAR_MOVE_AT_OR_ABOVE_RATIO"
    assert result.price_history_break_date == str(frame["date"].iloc[150].date())
    assert result.forward_realised_vol == pytest.approx(only_new.forward_realised_vol)
    assert result.forward_realised_vol < 1.0


def test_p2_intact_history_is_unchanged():
    closes = _walk(260, 100.0, 0.04, 3)
    closes[200] = closes[199] * 1.6                                 # a genuine +60% day is not a break
    frame = _frame(closes)
    result = l3.compute_forward_variance("REAL", frame, implied_vol=0.5, regime="")
    assert result.price_history_state == "INTACT" and result.price_history_break_date is None


def test_p3_break_with_too_little_history_gives_no_forecast():
    frame = _frame(np.concatenate([_walk(200, 0.5, 0.05, 4) * 0.01, [48.6]]))
    result = l3.compute_forward_variance("NEWLIST", frame, implied_vol=0.4, regime="")
    assert result.forward_realised_vol is None
    assert result.forecast_state == "MISSING_PRICE_HISTORY"
    assert result.price_history_state == "BREAK_INSUFFICIENT_HISTORY"


def test_p4_sub_cent_history_is_excluded_and_current_sub_cent_gives_no_forecast():
    shell = np.full(40, 0.0002)
    recovered = _walk(130, 0.8, 0.03, 5)
    frame = _frame(np.concatenate([_walk(60, 2.0, 0.03, 6), shell, recovered]))
    result = l3.compute_forward_variance("SHELL", frame, implied_vol=0.6, regime="")
    assert result.price_history_state == "BREAK_TRUNCATED"
    assert result.price_history_break_reason in {"SUB_CENT_PRICE", "ONE_BAR_MOVE_AT_OR_ABOVE_RATIO"}
    assert result.forward_realised_vol == pytest.approx(
        l3.compute_forward_variance("SHELL", frame.iloc[100:].reset_index(drop=True), implied_vol=0.6, regime="").forward_realised_vol)
    dead = l3.compute_forward_variance("DEAD", _frame(np.concatenate([_walk(100, 1.0, 0.03, 7), np.full(30, 0.000001)])),
                                       implied_vol=0.6, regime="")
    assert dead.forward_realised_vol is None and dead.price_history_state == "SUB_CENT_PRICE"


def test_p5_long_gap_is_a_break_when_dates_present():
    first = pd.bdate_range("2024-01-02", periods=120)
    second = pd.bdate_range("2024-09-02", periods=130)              # ~100 sessions missing
    closes = np.concatenate([_walk(120, 20.0, 0.02, 8), _walk(130, 21.0, 0.02, 9)])
    frame = _frame(closes, dates=list(first) + list(second))
    result = l3.compute_forward_variance("GAPPY", frame, implied_vol=0.3, regime="")
    assert result.price_history_state == "BREAK_TRUNCATED"
    assert result.price_history_break_reason == "GAP_OVER_SESSIONS"
    assert result.price_history_break_date == "2024-09-02"


def test_p7_state_published_in_output():
    frame = _frame(np.concatenate([_walk(150, 5.0, 0.03, 1) * 0.001, _walk(120, 48.6, 0.02, 2)]))
    row = l3.compute_forward_variance("SOLS", frame, implied_vol=0.4, regime="").to_dict()
    assert row["l3_price_history_state"] == "BREAK_TRUNCATED"
    assert row["l3_price_history_break_reason"] == "ONE_BAR_MOVE_AT_OR_ABOVE_RATIO"
    assert row["l3_price_history_break_date"] is not None
