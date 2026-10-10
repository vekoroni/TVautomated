"""S2-1 governing setup (ACK 6 Oct 2026: design approved, invalidation option I-c).

Business rule: the setup that qualifies a ticker for a lane is the setup whose move, time and invalidation are used
to value and express the trade. A level price has already passed is not a move still to come. Ties between setups
are decided by stated evidence (state, holdout hit rate, duration evidence, distance, age), never by spelling.

Run 20261006_060401: 32 of 51 GOs were valued on a 1d event that was not their 1w/1mo lane setup; 4 on a level price
had already passed (BLDR: a 1d BEAR Failed Spring Continuation at 63.90 with price 55.63, chosen only because its ID
sorts first); all 7 GOs without a computed value traced to this.

I-c: the governing setup's own invalidation decides "thesis wrong"; the daily primary's nearer level is published as
an early warning (supporting, never gating).
"""
from __future__ import annotations

from pathlib import Path

from domain.structure_behaviour.thesis_category import governed_thesis, thesis_category
from domain.structure_behaviour.trade_lane import (TRADE_LANE_FIELDS, governed_invalidation, select_governing,
                                                   ticker_lane)

ROOT = Path(__file__).resolve().parents[1]
PX = 100.0


def cand(tf, kind, state, direction, outcome, invalidation, cid=None, n=100, age=5):
    return {"Timeframe": tf, "Signal_Type": kind, "Signal_State": state, "Direction": direction,
            "Outcome_Level": outcome, "Invalidation_Level": invalidation, "Age_Bars": age,
            "Candidate_ID": cid or f"T|{tf}|CAMPAIGN|{kind}|2026-09-01", "Duration_Level_N": n,
            "Duration_Level_Q50_Bars": 2, "Duration_Level_Q80_Bars": 4, "Duration_Level_Status": "IN_SAMPLE_REPLAY_NOT_VALIDATED",
            "Outcome_Definition": "measured move", "Structure_Scope": "CAMPAIGN"}


# BLDR-like put: a stale 1d BEAR event whose level is above price (already passed), a valid 1w lane A setup,
# and a valid nearer 1d lane C event that is the daily primary.
STALE_1D = cand("1d", "Failed Spring Continuation", "ACTIVATED", "BEAR", 110.0, 115.0)
WEEKLY_A = cand("1w", "SOW -> LPSY continuation", "ACTIVATED", "BEAR", 85.0, 120.0)
DAILY_C = cand("1d", "Seller Absorption Breakdown", "DETECTED", "BEAR", 95.0, 104.0)
SETUPS = [STALE_1D, WEEKLY_A, DAILY_C]


def readings(cands):
    out = {}
    for c in cands:
        out.setdefault(c["Timeframe"], {"Status": "EVALUATED", "Wyckoff_Phase": "D", "candidates": []})
        out[c["Timeframe"]]["candidates"].append(c)
    return out


# --- characterisation: the legacy thesis pick is unchanged for callers that pass no governing setup -------------

def test_legacy_thesis_pick_still_prefers_1d_and_spelling():
    out = thesis_category(readings(SETUPS), "PUT")
    assert out["thesis_event_timeframe"] == "1d" and out["thesis_event"] == "Failed Spring Continuation"


# --- the governing setup -------------------------------------------------------------------------------------------

def test_a_level_price_has_already_passed_never_governs():
    fields, g = select_governing(SETUPS, price=PX, atr_daily=2.0, side="BEAR")
    assert g is WEEKLY_A
    assert fields["trade_lane"] == "A" and fields["trade_lane_candidate_id"] == WEEKLY_A["Candidate_ID"]
    assert fields["trade_lane_levels_passed"] == 1


def test_the_setup_that_sets_the_lane_is_the_setup_that_is_valued():
    fields, g = select_governing(SETUPS, price=PX, atr_daily=2.0, side="BEAR")
    thesis = governed_thesis(readings(SETUPS), "PUT", g)
    assert thesis["thesis_event_candidate_id"] == fields["trade_lane_candidate_id"]
    assert thesis["thesis_event_timeframe"] == "1w" and thesis["thesis_outcome_level"] == 85.0
    assert thesis["thesis_duration_q50_bars"] == 2


def test_the_daily_event_is_kept_as_supporting_and_never_valued():
    _, g = select_governing(SETUPS, price=PX, atr_daily=2.0, side="BEAR")
    thesis = governed_thesis(readings(SETUPS), "PUT", g)
    assert thesis["daily_event_candidate_id"] == STALE_1D["Candidate_ID"]       # what the legacy pick chose
    assert thesis["thesis_outcome_level"] != thesis["daily_event_outcome_level"]


def test_no_governing_setup_leaves_the_thesis_missing_and_says_why():
    thesis = governed_thesis(readings(SETUPS), "PUT", None)
    assert thesis["thesis_event"] is None and thesis["thesis_outcome_level"] is None
    assert thesis["thesis_structure_alignment"] == "NO_GOVERNING_SETUP"


def test_all_trade_side_levels_passed_is_stated():
    fields, g = select_governing([STALE_1D, cand("1d", "SOS -> LPS continuation", "ACTIVATED", "BULL", 108, 96)],
                                 price=PX, atr_daily=2.0, side="BEAR")
    assert g is None and fields["trade_lane"] == "C"
    assert fields["trade_lane_basis"] == "ALL_TRADE_SIDE_LEVELS_PASSED"


# --- ties are decided by evidence, never by spelling -----------------------------------------------------------------

def test_higher_holdout_hit_rate_beats_alphabetical_order():
    # both lane A, 1d, ACTIVATED; "Failed Spring Continuation" sorts first but has the lower holdout hit (.523 < .686)
    failed = cand("1d", "Failed Spring Continuation", "ACTIVATED", "BEAR", 90.0, 104.0)
    sow = cand("1d", "SOW -> LPSY continuation", "ACTIVATED", "BEAR", 90.0, 104.0)
    _, g = select_governing([failed, sow], price=PX, atr_daily=2.0, side="BEAR")
    assert g is sow


def test_activated_beats_detected_within_a_lane():
    detected = cand("1d", "Change-of-Behaviour Reversal", "DETECTED", "BEAR", 90.0, 104.0)      # lane A, .615
    activated = cand("1w", "SOW -> LPSY continuation", "ACTIVATED", "BEAR", 90.0, 104.0)        # lane A, .680
    _, g = select_governing([detected, activated], price=PX, atr_daily=2.0, side="BEAR")
    assert g is activated


def test_then_more_evidence_then_nearer_level_then_newer_then_id():
    base = ("1d", "SOW -> LPSY continuation", "ACTIVATED", "BEAR")
    more_n = cand(*base, 90.0, 104.0, cid="T|1d|A|SOW|z", n=500)
    less_n = cand(*base, 90.0, 104.0, cid="T|1d|A|SOW|a", n=100)
    assert select_governing([less_n, more_n], price=PX, atr_daily=2.0, side="BEAR")[1] is more_n
    near = cand(*base, 95.0, 104.0, cid="T|1d|A|SOW|z")
    far = cand(*base, 80.0, 104.0, cid="T|1d|A|SOW|a")
    assert select_governing([far, near], price=PX, atr_daily=2.0, side="BEAR")[1] is near
    new = cand(*base, 90.0, 104.0, cid="T|1d|A|SOW|z", age=2)
    old = cand(*base, 90.0, 104.0, cid="T|1d|A|SOW|a", age=20)
    assert select_governing([old, new], price=PX, atr_daily=2.0, side="BEAR")[1] is new
    b = cand(*base, 90.0, 104.0, cid="T|1d|A|SOW|b")
    a = cand(*base, 90.0, 104.0, cid="T|1d|A|SOW|a")
    assert select_governing([b, a], price=PX, atr_daily=2.0, side="BEAR")[1] is a       # spelling only at the end


def test_ticker_lane_is_the_governing_selection():
    assert ticker_lane(SETUPS, price=PX, atr_daily=2.0, side="BEAR") == \
        select_governing(SETUPS, price=PX, atr_daily=2.0, side="BEAR")[0]


# --- I-c invalidation ------------------------------------------------------------------------------------------------

def test_the_governing_setup_decides_thesis_wrong_and_the_daily_level_is_an_early_warning():
    out = governed_invalidation(WEEKLY_A, DAILY_C)
    assert out["governed_invalidation_level"] == 120.0
    assert out["thesis_invalidation_setup_id"] == WEEKLY_A["Candidate_ID"]
    assert out["early_warning_invalidation_level"] == 104.0
    assert out["early_warning_setup_id"] == DAILY_C["Candidate_ID"]


def test_no_early_warning_when_the_daily_primary_is_the_governing_setup():
    out = governed_invalidation(DAILY_C, DAILY_C)
    assert out["governed_invalidation_level"] == 104.0 and out["early_warning_invalidation_level"] is None


def test_no_governing_setup_leaves_invalidation_missing():
    out = governed_invalidation(None, DAILY_C)
    assert out["governed_invalidation_level"] is None and out["thesis_invalidation_setup_id"] is None


# --- wiring ----------------------------------------------------------------------------------------------------------

def test_the_new_fields_travel_with_the_lane():
    assert {"trade_lane_candidate_id", "trade_lane_levels_passed", "daily_event_candidate_id",
            "early_warning_invalidation_level", "thesis_invalidation_setup_id"} <= set(TRADE_LANE_FIELDS)


def test_discovery_selects_once_and_feeds_lane_thesis_and_invalidation_from_it():
    src = (ROOT / "avshunter_discovery_ULTIMATE.py").read_text(encoding="utf-8")
    assert src.count("select_governing(") == 1
    assert "governed_thesis(" in src and "governed_invalidation(" in src
    assert "ticker_lane(_beh['candidates']" not in src                         # no second lane pick
    assert "invalidation_price=_primary.get('Invalidation_Level')" not in src   # the daily primary no longer decides


# --- the book carries it and the card shows it (I-c) -----------------------------------------------------------------

def test_the_book_row_carries_the_governing_setup_and_early_warning():
    from contracts.lab_control import FINAL_BOOK_FIELDS, opportunity_book_row
    sig = {"ticker": "BLDR", "direction": "PUT", "trade_lane": "A", "trade_lane_candidate_id": WEEKLY_A["Candidate_ID"],
           "early_warning_invalidation_level": 104.0, "daily_event": "Seller Absorption Breakdown"}
    row = opportunity_book_row(sig, "RUN", 1)
    assert {"trade_lane_candidate_id", "early_warning_invalidation_level"} <= set(FINAL_BOOK_FIELDS)
    assert row["trade_lane_candidate_id"] == WEEKLY_A["Candidate_ID"] and row["early_warning_invalidation_level"] == 104.0


def test_the_card_shows_the_deciding_exit_and_the_daily_early_warning():
    import json
    import shutil
    import subprocess

    import pytest
    if shutil.which("node") is None:
        pytest.skip("node not installed")
    script = (ROOT / "intelligence-lab" / "static" / "trade-card.js").read_text(encoding="utf-8")
    probe = script + """
const html = renderTradeCard({ticker:'BLDR', direction:'PUT', invalidation_price:120, early_warning_invalidation_level:104});
const none = renderTradeCard({ticker:'BLDR', direction:'PUT', invalidation_price:120});
console.log(JSON.stringify({warn: html.includes('Early warning (daily)') && html.includes('104'),
  decides: html.includes('(decides)'), stated: none.includes('the daily setup is the qualifying setup')}));
"""
    out = subprocess.run(["node"], input=probe, capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert out.returncode == 0, out.stderr
    assert json.loads(out.stdout.strip().splitlines()[-1]) == {"warn": True, "decides": True, "stated": True}
