"""Business rules for the Daily review, section 3: where the opportunity is strongest (ACK 9 Oct 2026).

Top-down: market (QQQ vs SPY, broad or concentrated), then sectors (relative strength kept apart
from absolute direction), then constituents (do the holdings confirm the move), then price
location (room before the next obstacle). Display only; thresholds PROVISIONAL in config.
No live data or network.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from macro_board import holdings as hold
from macro_board import opportunity as opp

CFG = {
    "leader_band_pp": {"1": 0.1, "5": 0.3, "20": 0.75},
    "relative_band_pp": {"1": 0.1, "5": 0.25, "20": 0.5},
    "rsp_concentration_band_pp": 1.0,
    "participation_broad_min_pct": 50.0,
    "confirmation_min_pct": 60.0,
}
HORIZONS = [1, 5, 20]


def _m(**kw):
    base = {"status": "FRESH", "ret_1d": 0.0, "ret_5d": 0.0, "ret_20d": 0.0, "close": 100.0, "rv20": 16.0}
    base.update(kw)
    return base


# -- market: QQQ vs SPY, broad or concentrated ------------------------------------------------------

def test_qqq_leads_when_it_beats_spy_by_more_than_the_band_and_a_small_gap_is_neither():
    metrics = {"SPY": _m(ret_20d=2.0, ret_5d=1.0, ret_1d=0.2), "QQQ": _m(ret_20d=4.0, ret_5d=1.1, ret_1d=-0.5),
               "RSP": _m(ret_20d=1.5)}
    lead = opp.leadership(metrics, {}, HORIZONS, CFG)
    assert lead["windows"]["20"]["leader"] == "QQQ" and lead["windows"]["20"]["qqq_minus_spy_pp"] == 2.0
    assert lead["windows"]["5"]["leader"] == "NEITHER"
    assert lead["windows"]["1"]["leader"] == "SPY"


def test_leadership_is_concentrated_when_equal_weight_lags_or_few_holdings_participate():
    holdings = {"SPY": {"windows": {"20": {"participation_weight_pct": 42.0}}}}
    metrics = {"SPY": _m(ret_20d=3.0), "QQQ": _m(ret_20d=5.0), "RSP": _m(ret_20d=0.5)}
    lead = opp.leadership(metrics, holdings, HORIZONS, CFG)
    assert lead["breadth"]["state"] == "CONCENTRATED"
    assert lead["breadth"]["rsp_minus_spy_20d_pp"] == -2.5
    broad = opp.leadership({"SPY": _m(ret_20d=3.0), "QQQ": _m(ret_20d=3.2), "RSP": _m(ret_20d=2.8)},
                           {"SPY": {"windows": {"20": {"participation_weight_pct": 64.0}}}}, HORIZONS, CFG)
    assert broad["breadth"]["state"] == "BROAD"


def test_breadth_without_rsp_or_holdings_is_unknown_not_broad():
    lead = opp.leadership({"SPY": _m(ret_20d=3.0), "QQQ": _m(ret_20d=3.0)}, {}, HORIZONS, CFG)
    assert lead["breadth"]["state"] == "UNKNOWN"


# -- sectors: relative strength is not absolute direction -----------------------------------------

def test_a_sector_outperforming_a_falling_market_is_defensive_preference_not_a_call_setup():
    metrics = {"SPY": _m(ret_5d=-2.0), "XLU": _m(ret_5d=-0.5), "XLK": _m(ret_5d=-3.5), "XLE": _m(ret_5d=1.5)}
    rows = {r["ticker"]: r for r in opp.sector_rows(metrics, ["XLU", "XLK", "XLE"], {}, HORIZONS, CFG)}
    assert rows["XLU"]["windows"]["5"]["relative_pp"] == 1.5 and rows["XLU"]["windows"]["5"]["absolute_pct"] == -0.5
    assert rows["XLU"]["windows"]["5"]["label"] == "OUTPERFORMING_WHILE_FALLING"
    assert rows["XLK"]["windows"]["5"]["label"] == "UNDERPERFORMING_AND_FALLING"
    assert rows["XLE"]["windows"]["5"]["label"] == "OUTPERFORMING_AND_RISING"


def test_a_relative_gap_inside_the_band_is_in_line_and_missing_data_is_missing():
    metrics = {"SPY": _m(ret_20d=2.0), "XLP": _m(ret_20d=2.3), "XLB": {"status": "MISSING"}}
    rows = {r["ticker"]: r for r in opp.sector_rows(metrics, ["XLP", "XLB"], {}, HORIZONS, CFG)}
    assert rows["XLP"]["windows"]["20"]["label"] == "IN_LINE"
    assert rows["XLB"]["windows"]["20"]["label"] == "MISSING" and rows["XLB"]["windows"]["20"]["relative_pp"] is None


# -- constituents: do the holdings confirm the move ------------------------------------------------

def test_confirming_weight_is_the_share_of_priced_weight_moving_with_the_fund():
    idx = pd.bdate_range("2026-09-01", periods=30)
    closes = pd.DataFrame({"AAA": np.linspace(100, 110, 30), "BBB": np.linspace(100, 105, 30),
                           "CCC": np.linspace(100, 95, 30)}, index=idx)
    holdings = [{"ticker": "AAA", "weight_pct": 50.0}, {"ticker": "BBB", "weight_pct": 30.0},
                {"ticker": "CCC", "weight_pct": 20.0}]
    out = hold.contribution(holdings, closes, window=5, trend_sessions=10, holdings_as_of=idx[-1])
    assert out["sum_contribution_pp"] > 0
    assert 79.0 < out["confirming_weight_pct"] < 81.0          # AAA + BBB rose with the fund, CCC fell


def test_a_sector_move_is_confirmed_only_when_enough_weight_moves_with_it():
    metrics = {"SPY": _m(ret_5d=0.0), "XLK": _m(ret_5d=2.0), "XLF": _m(ret_5d=1.0)}
    holdings = {"XLK": {"windows": {"5": {"confirming_weight_pct": 72.0, "top_contributors": [{"ticker": "NVDA"}]}}},
                "XLF": {"windows": {"5": {"confirming_weight_pct": 48.0, "top_contributors": [{"ticker": "JPM"}]}}}}
    rows = {r["ticker"]: r for r in opp.sector_rows(metrics, ["XLK", "XLF", "XLE"], holdings, HORIZONS, CFG)}
    assert rows["XLK"]["windows"]["5"]["constituents"] == "CONFIRMED"
    assert rows["XLF"]["windows"]["5"]["constituents"] == "NOT_CONFIRMED"
    assert rows["XLE"]["windows"]["5"]["constituents"] == "NO_HOLDINGS"


# -- price location: room before the next obstacle ------------------------------------------------

def test_room_is_the_distance_to_the_nearest_obstacle_above_and_below_in_daily_moves():
    idx = pd.bdate_range("2025-09-01", periods=260)
    series = pd.Series(np.r_[np.linspace(90, 120, 200), np.linspace(120, 100, 60)], index=idx)
    levels = {"call_wall": 104.0, "put_wall": 96.0, "pipeline_target": 108.0}
    room = opp.price_room(series, rv20_pct=15.874, extra_levels=levels)       # daily move = 1% of price
    assert room["close"] == 100.0
    assert room["above"]["name"] == "call_wall" and room["above"]["distance_pct"] == 4.0
    assert room["above"]["distance_daily_moves"] == 4.0
    assert room["below"]["name"] == "put_wall" and room["below"]["distance_pct"] == -4.0
    assert {"high_252", "sma50", "sma200", "pipeline_target"} <= set(room["levels"])


def test_gex_levels_carry_their_own_session_date_into_the_room_table():
    idx = pd.bdate_range("2026-01-01", periods=60)
    closes = pd.DataFrame({"SPY": np.linspace(700, 774, 60)}, index=idx)
    gex = [{"Ticker": "SPY", "Date": "2026-10-05", "Call_Wall": 785.0, "Put_Wall": 755.0, "Gamma_Flip": 776.5}]
    out = opp.build(metrics={"SPY": _m(rv20=16.0)}, closes=closes, holdings={}, horizons=HORIZONS, sectors=[],
                    gex_records=gex, proposals={}, room_tickers=["SPY"], cfg=CFG)
    assert out["room"]["SPY"]["gex_as_of"] == "2026-10-05"
    assert out["room"]["SPY"]["above"]["name"] == "gamma_flip"


def test_the_252_session_high_and_low_are_where_price_actually_traded_not_the_best_close():
    # 9 Oct 2026: QQQ's highest close was 759.66 but it traded to 762.86 the same day; the obstacle
    # is the traded high. Averages stay on closes.
    idx = pd.bdate_range("2025-09-01", periods=260)
    closes = pd.Series(np.r_[np.linspace(90, 120, 200), np.linspace(120, 100, 60)], index=idx)
    highs, lows = closes + 2.0, closes - 3.0
    room = opp.price_room(closes, rv20_pct=15.874, extra_levels={}, highs=highs, lows=lows)
    assert room["levels"]["high_252"] == round(float(highs.iloc[-252:].max()), 4)
    assert room["levels"]["low_252"] == round(float(lows.iloc[-252:].min()), 4)
    assert room["levels"]["sma50"] == round(float(closes.iloc[-50:].mean()), 4)
    assert room["range_basis"] == "INTRADAY_HIGH_LOW"
    without = opp.price_room(closes, rv20_pct=15.874, extra_levels={})
    assert without["range_basis"] == "CLOSES" and without["levels"]["high_252"] == 120.0


def test_room_without_volatility_still_gives_percent_but_no_daily_move_count():
    idx = pd.bdate_range("2026-01-01", periods=60)
    room = opp.price_room(pd.Series(np.linspace(50, 60, 60), index=idx), rv20_pct=None, extra_levels={})
    assert room["below"]["distance_pct"] is not None and room["below"]["distance_daily_moves"] is None
