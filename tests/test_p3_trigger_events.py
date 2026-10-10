"""Phase 3: the trigger layer detects EVENTS against the thesis's own recorded levels (design §7, P8).

Business rules:
- A close beyond the break level is a BREAK_ATTEMPT; when the engine's acceptance rule is met (closes persist
  beyond the level by the configured ATR margin) it is BREAK_ACCEPTED at that bar - one acceptance rule, reused.
- A close back inside before (or right after) acceptance is a FAILED_BREAK - a trap for the opposite side.
- After acceptance, a return to the broken level that closes beyond it is RETEST_HELD; closing back is RETEST_FAILED.
- Acceptance beyond the invalidation is INVALIDATED; a close at or beyond the target is OUTCOME_REACHED.
- VWAP reclaim / loss are computed from the bars themselves (anchored at the thesis origin) - no other field.
- Too few bars -> NOT_MEASURED, never "no event". The detector carries no direction logic.
"""
import copy

import numpy as np
import pandas as pd

from domain.structure_behaviour.policy import load_policy
from domain.structure_behaviour.sequences import build_sequences
from domain.structure_behaviour.trigger_events import detect_events

POLICY = copy.deepcopy(dict(load_policy()))
POLICY["timeframes"]["1d"]["min_bars"] = 20


def _seq(closes, spread=0.6, volume=None):
    closes = np.asarray(closes, float)
    dates = pd.bdate_range("2026-01-02", periods=len(closes))
    vol = np.full(len(closes), 1e6) if volume is None else np.asarray(volume, float)
    df = pd.DataFrame({"date": dates, "open": closes, "high": closes + spread, "low": closes - spread,
                       "close": closes, "volume": vol})
    return build_sequences(df, "1d", POLICY)


BASE = [100 + 0.5 * np.sin(i) for i in range(30)]          # a range around 100 (ATR ~1.2)


def _events(seq, **levels):
    return detect_events(seq, levels=levels, from_index=25, policy=POLICY)


def _types(res):
    return [e["event"] for e in res["events"]]


def test_break_attempt_then_acceptance_at_the_accepting_bar():
    s = _seq(BASE + [102.5, 103.5, 104.0, 104.2, 104.4])
    r = _events(s, up=102.0)
    t = [x for x in _types(r) if x.startswith("BREAK_")]          # VWAP events are independent of the break
    assert t[0] == "BREAK_ATTEMPT_UP" and "BREAK_ACCEPTED_UP" in t
    acc = next(e for e in r["events"] if e["event"] == "BREAK_ACCEPTED_UP")
    assert acc["date"] == s.label(acc["index"]) and acc["level"] == 102.0


def test_close_back_inside_is_a_failed_break():
    s = _seq(BASE + [102.4, 101.2, 100.6, 100.2])
    assert "FAILED_BREAK_UP" in _types(_events(s, up=102.0))


def test_retest_held_after_acceptance():
    s = _seq(BASE + [103.5, 104.0, 104.5, 103.0, 102.4, 103.6])
    assert "RETEST_HELD_UP" in _types(_events(s, up=102.0))


def test_invalidation_and_outcome():
    s = _seq(BASE + [98.0, 97.0, 96.5, 96.0])
    assert "INVALIDATED" in _types(_events(s, up=102.0, invalidation=(98.5, "BELOW")))
    s = _seq(BASE + [103.0, 104.0, 106.0, 108.5])
    assert "OUTCOME_REACHED" in _types(_events(s, up=102.0, target=(108.0, "ABOVE")))


def test_vwap_events_come_from_bars_alone():
    flat = [100.0] * 30
    s = _seq(flat + [101.0, 97.0, 102.0], volume=[1e6] * 33)
    t = _types(_events(s))
    assert "VWAP_LOSS" in t and "VWAP_RECLAIM" in t


def test_too_few_bars_is_not_measured():
    res = detect_events(None, levels={"up": 102.0}, from_index=0, policy=POLICY)
    assert res["status"].startswith("NOT_MEASURED") and res["events"] == []


def test_discovery_attaches_each_candidates_last_event_on_its_own_levels():
    import avshunter_discovery_ULTIMATE as disc
    closes = BASE + [102.5, 103.5, 104.0, 104.2]
    dates = pd.bdate_range("2026-01-02", periods=len(closes))
    df = pd.DataFrame({"date": dates, "open": closes, "high": np.array(closes) + 0.6,
                       "low": np.array(closes) - 0.6, "close": closes, "volume": 1e6})
    origin = dates[24].strftime("%Y-%m-%d")
    cand = {"Candidate_ID": f"T|1d|CAMPAIGN|SOS -> LPS continuation|{origin}", "Timeframe": "1d",
            "Proposed_Side": "BULL", "Adoption_State": "ADOPTED", "Family": "CONTINUATION",
            "Trigger_Level": 102.0, "Invalidation_Level": 98.0, "Outcome_Level": 110.0}
    beh = {"candidates": [cand], "readings": {}}
    disc._attach_trigger_events(beh, df, POLICY)
    assert cand["Events_Status"] == "MEASURED"
    assert cand["Last_Event"] in {"BREAK_ACCEPTED_UP", "VWAP_RECLAIM", "VWAP_LOSS", "RETEST_HELD_UP"}
    assert "BREAK_ACCEPTED_UP" in [e["event"] for e in __import__("json").loads(cand["Events_JSON"])]
    assert cand["Last_Event_Date"] and cand["Last_Event_Interval"] == "1d"


def test_detector_output_carries_no_direction():
    s = _seq(BASE + [102.5, 103.5, 104.0])
    r = _events(s, up=102.0)
    assert all("side" not in e and "direction" not in e for e in r["events"])
    assert "direction" not in r and "side" not in r
