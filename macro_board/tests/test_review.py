"""Business rules for the Daily review, section 1: the day's information and the market's reaction
(ACK 9 Oct 2026). Central question: did the market accept the new information, reject it, or absorb
it without meaningful displacement? Daily bars v1 (ACK): the opening gap is the immediate response,
the close against the previous close is the closing position, measured in the instrument's own
daily move from the 20 sessions BEFORE the day. Expectations come from the event payload and FRED;
missing consensus is stated. No live data or network.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from macro_board import review as rv

K = 0.5


# -- the label --------------------------------------------------------------------------------------

def test_a_gap_that_the_close_extends_is_accepted():
    r = rv.classify(prev_close=100.0, open_=101.0, close=101.5, daily_move_pct=1.0, k=K)
    assert r["label"] == "ACCEPTED" and r["direction"] == "UP" and r["path"] == "EXTENDED"
    assert r["gap_pct"] == 1.0 and r["close_pct"] == 1.5 and round(r["open_to_close_pct"], 4) == round((101.5 / 101 - 1) * 100, 4)


def test_a_gap_reversed_through_the_previous_close_is_rejected():
    r = rv.classify(prev_close=100.0, open_=101.0, close=99.4, daily_move_pct=1.0, k=K)
    assert r["label"] == "REJECTED" and r["direction"] == "UP" and r["path"] == "FADED"   # the up gap was rejected


def test_a_close_inside_half_a_daily_move_is_absorbed_even_after_a_gap():
    r = rv.classify(prev_close=100.0, open_=101.0, close=100.3, daily_move_pct=1.0, k=K)
    assert r["label"] == "ABSORBED" and r["path"] == "FADED"


def test_a_move_without_an_opening_reaction_is_accepted_in_its_own_direction():
    r = rv.classify(prev_close=100.0, open_=100.1, close=99.0, daily_move_pct=1.0, k=K)
    assert r["label"] == "ACCEPTED" and r["direction"] == "DOWN" and r["path"] == "NO_OPENING_REACTION"


def test_without_a_daily_move_the_label_is_unknown_not_absorbed():
    r = rv.classify(prev_close=100.0, open_=101.0, close=101.5, daily_move_pct=None, k=K)
    assert r["label"] == "UNKNOWN"


def test_the_daily_move_comes_from_the_sessions_before_the_day_not_the_day_itself():
    idx = pd.bdate_range("2026-01-01", periods=30)
    closes = pd.Series(100.0 * np.cumprod(np.r_[1.0, np.tile([1.01, 0.99], 14), 1.10]), index=idx)  # last day +10%
    opens = closes.shift(1).fillna(100.0)
    hist = rv.label_history(opens, closes, k=K, vol_sessions=20)
    before = np.log(closes).diff().iloc[-21:-1].std(ddof=1) * 100.0
    assert abs(hist["daily_move_pct"].iloc[-1] - before) < 1e-9
    assert hist["label"].iloc[-1] == "ACCEPTED" and hist["direction"].iloc[-1] == "UP"


# -- the label scored against what followed --------------------------------------------------------

def test_todays_label_is_scored_on_what_followed_past_days_with_the_same_label():
    idx = pd.bdate_range("2021-01-01", periods=700)
    rng = np.random.default_rng(7)
    closes = pd.Series(100.0 * np.cumprod(1.0 + rng.normal(0.0004, 0.01, 700)), index=idx)
    opens = closes.shift(1).fillna(100.0) * (1.0 + rng.normal(0.0, 0.004, 700))
    settings = {"min_history_sessions": 500, "holdout_fraction": 0.25, "lean_t_min": 1.5, "min_effective_n": 8,
                "min_effective_n_holdout": 3, "lean_min_abs_mean_pct": {"1": 0.05, "5": 0.25, "20": 0.75}}
    out = rv.label_evidence(opens.to_frame("SPY"), closes.to_frame("SPY"), "SPY", k=K, vol_sessions=20,
                            horizons=[1, 5], settings=settings)
    today = out["today"]
    assert today["label"] in ("ACCEPTED", "REJECTED", "ABSORBED")
    ev5 = out["evidence"]["5"]
    assert ev5["analog"]["n"] > 0 and "base" in ev5            # past days with today's label vs all days
    assert out["label_counts"][today["key"]] == ev5["analog"]["n"] + out["label_counts_without_outcome"].get(today["key"], 0)


# -- what changed and what was expected --------------------------------------------------------------

def test_expectations_are_shown_as_published_and_missing_consensus_is_stated():
    payload = {"generated_from_report_date": "2026-10-08",
               "events": [{"event_name": "Waller speech", "status": "CONFIRMED", "actual": {"hike_prob_dec_pct": 86},
                           "forecast": None, "previous": "one more hike by year-end", "revised_previous": None,
                           "surprise_direction": "HAWKISH"},
                          {"event_name": "30-year auction", "actual": {"high_yield_percent": 5.618},
                           "forecast": "No formal consensus for the auction.", "previous": {"high_yield_percent": 5.308}}]}
    overnight = {"releases_today": [{"name": "Jobless claims", "series_id": "ICSA", "state": "RELEASED", "value": 197000.0,
                                     "prior": 199000.0, "change": -2000.0, "observation_date": "2026-10-03", "time_et": "08:30"}]}
    events = rv.information(payload, overnight, session="2026-10-08")
    waller = next(e for e in events["items"] if e["name"] == "Waller speech")
    assert waller["expected"] == "MISSING" and waller["previous"] == "one more hike by year-end"
    assert waller["what_changed"] == "hike_prob_dec_pct: 86" and waller["source"] == "event payload (LLM)"
    auction = next(e for e in events["items"] if e["name"] == "30-year auction")
    assert auction["expected"].startswith("No formal consensus")
    claims = next(e for e in events["items"] if e["name"] == "Jobless claims")
    assert claims["what_changed"] == "197,000 (observation 2026-10-03)" and claims["previous"] == "199,000"
    assert claims["expected"] == "MISSING (no free consensus source)" and claims["source"] == "FRED"
    assert events["payload_session"] == "2026-10-08" and events["payload_matches_session"] is True


# -- what disagreed ---------------------------------------------------------------------------------

def test_moves_against_spy_beyond_their_own_threshold_are_disagreements():
    rows = {"SPY": {"label": "ACCEPTED", "direction": "DOWN", "close_pct": -0.8, "threshold_pct": 0.3},
            "XLE": {"label": "ACCEPTED", "direction": "UP", "close_pct": 2.0, "threshold_pct": 0.6},
            "XLK": {"label": "ACCEPTED", "direction": "DOWN", "close_pct": -1.8, "threshold_pct": 0.6},
            "TLT": {"label": "ABSORBED", "direction": "UP", "close_pct": 0.2, "threshold_pct": 0.4}}
    out = rv.disagreements(rows, confirming_weight_1d=38.0, contradictions=["TLT rallied while QQQ fell"], cfg={"confirmation_min_pct": 60.0})
    names = [d["ticker"] for d in out["measured"]]
    assert names == ["XLE"]
    assert out["constituents"] == "NOT_CONFIRMED" and out["published"] == ["TLT rallied while QQQ fell"]


def test_the_headline_answers_accept_reject_or_absorb_for_the_index_etfs():
    rows = {"SPY": {"label": "ABSORBED", "direction": "NONE"}, "QQQ": {"label": "ACCEPTED", "direction": "DOWN"}}
    assert rv.headline(rows, ["SPY", "QQQ"]) == "SPY absorbed · QQQ accepted (down)"
