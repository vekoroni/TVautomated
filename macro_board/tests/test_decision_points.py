"""Business rules for the Daily review, section 2: tomorrow's decision points (ACK 9 Oct 2026).

Known scheduled events (releases with their times, FOMC decisions, constituent earnings,
holidays and shortened sessions) are placed in the sessions ahead and kept apart from
unscheduled developments (news / LLM overlays). Each focus ETF gets the list of what could force
participants to reassess it in the next session. Missing inputs are stated, never assumed empty.
No live data or network.
"""

from __future__ import annotations

from datetime import date

from macro_board import decision_points as dp

CFG = {
    "constituent_etfs": ["SPY", "QQQ"],
    "constituent_top_n": 2,
    "sector_top_n": 1,
    "near_level_daily_moves": 1.0,
    "max_sessions": 20,
    "fomc": {"decisions": [{"date": "2026-10-28", "sep": False}, {"date": "2026-12-09", "sep": True}],
             "minutes": [], "time_et": "14:00"},
}
OVERNIGHT = {"status": "FRESH", "releases_today": [],
             "releases_ahead": [{"date": "2026-10-09", "release_id": 999, "name": "Test print", "time_et": "08:30"},
                                {"date": "2026-10-14", "release_id": 10, "name": "CPI", "time_et": "08:30"},
                                {"date": "2026-12-30", "release_id": 50, "name": "Payrolls", "time_et": "08:30"}]}
HOLDINGS = {"SPY": {"top": [{"ticker": "NVDA", "weight_pct": 7.5}, {"ticker": "AAPL", "weight_pct": 6.8},
                            {"ticker": "MSFT", "weight_pct": 6.0}]},
            "QQQ": {"top": [{"ticker": "NVDA", "weight_pct": 9.0}, {"ticker": "MSFT", "weight_pct": 8.0}]},
            "XLK": {"top": [{"ticker": "NVDA", "weight_pct": 14.0}]}}
EARNINGS = {"NVDA": {"state": "SCHEDULED", "date": "2026-10-09", "report_time": "AFTER_CLOSE",
                     "date_confirmation": "PROVIDER_DATE_UNCONFIRMED"},
            "AAPL": {"state": "NONE_IN_LOOKAHEAD"},
            "MSFT": {"state": "UNKNOWN", "reason": "HTTP_500"}}


def _build(**kw):
    args = dict(as_of_session="2026-10-08", overnight=OVERNIGHT, holdings=HOLDINGS, earnings=EARNINGS,
                enrichment=None, event_payload=None, room={}, focus=["SPY", "QQQ"], sectors=["XLK"], cfg=CFG)
    args.update(kw)
    return dp.build(**args)


def test_the_constituents_whose_earnings_are_looked_up_are_the_top_holdings_of_the_index_and_sector_etfs():
    tickers = dp.constituent_tickers(HOLDINGS, CFG, sectors=["XLK"])
    assert tickers == {"NVDA": {"SPY": 7.5, "QQQ": 9.0, "XLK": 14.0}, "AAPL": {"SPY": 6.8}, "MSFT": {"QQQ": 8.0}}


def test_scheduled_events_are_placed_by_sessions_ahead_and_beyond_the_horizon_is_dropped():
    out = _build()
    assert out["next_session"] == "2026-10-09"
    by_name = {e["name"]: e for e in out["calendar"]}
    assert by_name["Test print"]["sessions_ahead"] == 1 and by_name["Test print"]["time_et"] == "08:30"
    assert by_name["CPI"]["sessions_ahead"] == 4 and by_name["CPI"]["windows"] == [5, 20]
    assert "Payrolls" not in by_name                      # beyond 20 sessions
    fomc = by_name["FOMC rate decision"]
    assert fomc["date"] == "2026-10-28" and fomc["kind"] == "FOMC" and fomc["windows"] == [20]


def test_an_event_dated_on_or_before_the_boards_close_is_not_a_decision_point():
    # Found on the 8 Oct 2026 build: past FOMC meetings (Jan-Sep) were shown as "next session".
    cfg = {**CFG, "fomc": {"decisions": [{"date": "2026-09-16", "sep": True}, {"date": "2026-10-08", "sep": False},
                                         {"date": "2026-10-28", "sep": False}], "minutes": ["2026-10-07"], "time_et": "14:00"}}
    past = {"status": "FRESH", "releases_today": [],
            "releases_ahead": [{"date": "2026-10-08", "release_id": 180, "name": "Jobless claims", "time_et": "08:30"}]}
    out = _build(cfg=cfg, overnight=past, earnings={"NVDA": {"state": "SCHEDULED", "date": "2026-10-01", "report_time": "AFTER_CLOSE"}})
    assert [e["date"] for e in out["calendar"]] == ["2026-10-28"]
    assert all(i["kind"] != "FOMC" for i in out["reassess"]["SPY"])


def test_constituent_earnings_carry_their_index_weights_and_unknown_dates_are_stated_not_dropped():
    out = _build()
    nvda = next(e for e in out["calendar"] if e["kind"] == "EARNINGS")
    assert nvda["name"] == "NVDA earnings" and nvda["time_et"] == "AFTER_CLOSE"
    assert nvda["weights"] == {"SPY": 7.5, "QQQ": 9.0, "XLK": 14.0}
    assert "reaction next session" in nvda["detail"]
    assert out["coverage"]["earnings_unknown"] == ["MSFT"]


def test_a_holiday_and_a_shortened_session_are_decision_points_in_their_own_right():
    out = _build(as_of_session="2026-11-25", overnight={"status": "FRESH", "releases_today": [], "releases_ahead": []},
                 earnings={})
    kinds = {(e["kind"], e["date"]) for e in out["calendar"]}
    assert ("HOLIDAY", "2026-11-26") in kinds
    assert ("SHORTENED_SESSION", "2026-11-27") in kinds
    assert out["next_session"] == "2026-11-27" and out["next_session_close_et"] == "13:00"


def test_unscheduled_developments_are_kept_apart_from_the_scheduled_calendar():
    enrichment = {"as_of_utc": "2026-10-08T21:23:00Z",
                  "event_guard_deltas": [{"event_name": "QQQ and semiconductor reclaim or continuation", "importance": "HIGH",
                                          "scenario_map": {"confirms": "extension", "fails": "reclaim"}}],
                  "trading_risk_overlay": {"red_team_challenge": "Will tech selling spread into SPY?"}}
    payload = {"counter_case": {"reversal_or_neutralisation_conditions": ["QQQ reclaims VWAP"]},
               "final_verdict": {"verdict": "TWO_WAY_RISK", "scope": "two-way"}}
    out = _build(enrichment=enrichment, event_payload=payload)
    assert all(e["kind"] != "UNSCHEDULED" for e in out["calendar"])
    un = out["unscheduled"]
    assert un["items"][0]["name"] == "QQQ and semiconductor reclaim or continuation" and un["items"][0]["source"] == "news enrichment (LLM)"
    assert un["red_team"] == "Will tech selling spread into SPY?"
    assert un["counter_conditions"] == ["QQQ reclaims VWAP"] and un["verdict"] == "TWO_WAY_RISK"


def test_reassessment_list_holds_next_session_events_its_own_constituents_and_levels_within_a_daily_move():
    room = {"SPY": {"above": {"name": "gamma_flip", "level": 776.5, "distance_pct": 0.33, "distance_daily_moves": 0.52},
                    "below": {"name": "sma50", "level": 766.8, "distance_pct": -0.92, "distance_daily_moves": 1.43}}}
    enrichment = {"event_guard_deltas": [{"event_name": "A", "importance": "HIGH"}, {"event_name": "B", "importance": "HIGH"},
                                         {"event_name": "C", "importance": "LOW"}]}
    out = _build(room=room, enrichment=enrichment)
    spy = [i["text"] for i in out["reassess"]["SPY"]]
    assert any("Test print" in t and "08:30" in t for t in spy)
    assert any("NVDA earnings" in t and "7.5%" in t for t in spy)
    assert any("GEX flip 776.50" in t for t in spy) and not any("50d avg" in t for t in spy)   # 1.43 moves away
    assert not any("CPI" in t for t in spy)                                                   # not next session
    unresolved = [t for t in spy if "unresolved" in t]
    assert unresolved == ["2 high-importance unresolved developments (listed under Unscheduled)"]   # once, not repeated


def test_missing_inputs_are_reported_missing():
    out = _build(overnight=None, earnings=None)
    assert out["coverage"]["releases"] == "MISSING" and out["coverage"]["earnings"] == "MISSING"
    assert out["coverage"]["speakers"] == "EVENT_PAYLOAD_ONLY"
