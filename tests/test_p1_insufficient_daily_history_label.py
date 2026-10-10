"""P0-07 (Phase 1): a ticker whose daily chart was never read is reported as INSUFFICIENT_DAILY_HISTORY.

Business rule (R1/R6, labels say what was measured): when the behavioural engine could not read the daily chart
because the stored history is shorter than its minimum, the drop reason states that. It must not claim
"intraday only untested" or "no live setup", which describe a chart that WAS read.
Phase 0 found 918 + 303 tickers mislabelled this way on run 20261006_060401.
"""
import avshunter_discovery_ULTIMATE as disc


def _signal(lane, status_1d):
    return {"trade_lane": lane, "beh__1d_status": status_1d, "tier": 3}


def test_unread_daily_chart_is_reported_as_insufficient_history():
    for lane in ("INTRADAY_ONLY_UNTESTED", "NO_LIVE_SETUP"):
        assert disc._lane_drop_reason(_signal(lane, "NOT_EVALUATED_INSUFFICIENT_BARS")) == "INSUFFICIENT_DAILY_HISTORY"


def test_read_daily_chart_keeps_the_lane_reason():
    assert disc._lane_drop_reason(_signal("NO_LIVE_SETUP", "EVALUATED")) == "NO_LIVE_SETUP"
    assert disc._lane_drop_reason(_signal("INTRADAY_ONLY_UNTESTED", "EVALUATED")) == "INTRADAY_ONLY_UNTESTED"


def test_live_lanes_are_not_dropped():
    for lane in ("A", "B", "C"):
        assert disc._lane_drop_reason(_signal(lane, "NOT_EVALUATED_INSUFFICIENT_BARS")) is None
