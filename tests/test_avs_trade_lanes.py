"""Trade lanes (ACK 4 Oct 2026): isolate setups by how often they reach their level, never mix them.

Evidence (eval_v5 + held-out, level before invalidation): activated daily setups 57% / 54%, detected 33% / 33%.
Detected setups "are still tradable but I am concerned about the 2 in 3 failure rate" (ACK).
Business rules:
- Lane A (trade now): timeframe x type x state at >= 50% on both panels; the table is per timeframe
  (a daily activated Spring is A, a weekly one is not).
- Lane B (early entry): ACK "reduce the number to 1 in 3". A detected Spring / SOS->LPS / Buyer Absorption whose
  level is within 2 daily ATR and whose invalidation is at least 2 ATR away (74% / 76% reach the level first),
  kept only when the option's value multiple at the anticipated time is at least 1 / hit rate.
- Lane C: every other live setup, visible for human judgement; intraday is C until its evidence is built.
- A ticker takes its best lane across all its live setups; with no live setup it is NO_LIVE_SETUP.
"""
from domain.structure_behaviour.trade_lane import confirm_early_entry, load_lanes, ticker_lane


def c(tf, kind, state, outcome=None, invalidation=None):
    return {"Timeframe": tf, "Signal_Type": kind, "Signal_State": state,
            "Outcome_Level": outcome, "Invalidation_Level": invalidation}


PX, ATR = 100.0, 2.0     # near level: 102 (1 ATR); far invalidation: 95 (2.5 ATR)


def test_measured_trade_now_setup_is_lane_a():
    out = ticker_lane([c("1d", "SOS -> LPS continuation", "ACTIVATED")])
    assert out["trade_lane"] == "A" and out["trade_lane_hit_original"] == 0.726


def test_lane_table_is_per_timeframe():
    assert ticker_lane([c("1d", "Spring Candidate", "ACTIVATED")])["trade_lane"] == "A"
    assert ticker_lane([c("1w", "Spring Candidate", "ACTIVATED")])["trade_lane"] == "C"


def test_detected_setup_with_near_level_and_far_invalidation_is_early_entry():
    out = ticker_lane([c("1d", "Spring Candidate", "DETECTED", 102.0, 95.0)], price=PX, atr_daily=ATR)
    assert out["trade_lane"] == "B" and out["trade_lane_hit_holdout"] == 0.76


def test_detected_setup_without_the_geometry_waits_in_lane_c():
    far_level = ticker_lane([c("1d", "Spring Candidate", "DETECTED", 110.0, 95.0)], price=PX, atr_daily=ATR)
    tight_inval = ticker_lane([c("1d", "Spring Candidate", "DETECTED", 102.0, 98.0)], price=PX, atr_daily=ATR)
    unknown = ticker_lane([c("1d", "Spring Candidate", "DETECTED", 102.0, 95.0)])
    assert far_level["trade_lane"] == tight_inval["trade_lane"] == "C"
    assert far_level["trade_lane_basis"] == "EARLY_ENTRY_GEOMETRY_NOT_MET"
    assert unknown["trade_lane"] == "C" and unknown["trade_lane_basis"] == "EARLY_ENTRY_GEOMETRY_UNKNOWN"


def test_other_live_setups_wait_for_human_judgement():
    assert ticker_lane([c("1d", "Upthrust Candidate", "ACTIVATED")])["trade_lane"] == "C"
    # Superseded 5 Oct 2026 (ACK change 1): an intraday-only ticker is held out, not lane C. Beside a setup on a
    # tested timeframe, the tested setup sets the lane (see the mixed case in the intraday-only test).
    intraday = ticker_lane([c("15m", "SOS -> LPS continuation", "ACTIVATED")])
    assert intraday["trade_lane"] == "INTRADAY_ONLY_UNTESTED"


def test_best_lane_wins_and_no_live_setup_is_stated():
    out = ticker_lane([c("1d", "Upthrust Candidate", "DETECTED"), c("1w", "SOW -> LPSY continuation", "ACTIVATED")])
    assert out["trade_lane"] == "A" and out["trade_lane_setup"].startswith("1w|")
    none = ticker_lane([c("1d", "Spring Candidate", "OUTCOME_REACHED"), c("1d", "Spring Candidate", "FAILED")])
    assert none["trade_lane"] == "NO_LIVE_SETUP"


def test_early_entry_needs_wins_big_enough_to_cover_the_failures():
    b = ticker_lane([c("1d", "Spring Candidate", "DETECTED", 102.0, 95.0)], price=PX, atr_daily=ATR)
    assert confirm_early_entry(b, 1.5)["trade_lane"] == "B"            # hit 0.74 -> needs >= 1.35x
    assert confirm_early_entry(b, 1.5)["trade_lane_required_multiple"] == 1.35
    small = confirm_early_entry(b, 1.2)
    assert small["trade_lane"] == "C" and small["trade_lane_basis"] == "EARLY_ENTRY_PAYOFF_TOO_SMALL"
    assert confirm_early_entry(b, None)["trade_lane_basis"] == "EARLY_ENTRY_PAYOFF_UNKNOWN"
    a = ticker_lane([c("1d", "SOS -> LPS continuation", "ACTIVATED")])
    assert confirm_early_entry(a, 0.5)["trade_lane"] == "A"


def test_every_lane_a_entry_meets_the_line_on_both_panels():
    table = load_lanes()
    for tf, entries in table["lane_a_trade_now"].items():
        for e in entries:
            assert min(e["hit"]) >= table["hit_line"], (tf, e)


def test_lane_values_read_back_from_csv_are_handled():
    nan = float("nan")
    b = {"trade_lane": "B", "trade_lane_hit_original": 0.74, "trade_lane_hit_holdout": nan}
    assert confirm_early_entry(b, 1.4)["trade_lane"] == "B"
    assert confirm_early_entry(b, nan)["trade_lane_basis"] == "EARLY_ENTRY_PAYOFF_UNKNOWN"


def test_the_book_carries_the_lane_and_confirms_early_entry():
    import inspect
    import eod_candidate_engine as eod
    from domain.structure_behaviour.trade_lane import TRADE_LANE_FIELDS
    src = inspect.getsource(eod)
    assert "*TRADE_LANE_FIELDS" in src and "confirm_early_entry(" in src
    assert {"trade_lane", "trade_lane_basis", "trade_lane_setup", "intake_flags", "price_band"} <= set(TRADE_LANE_FIELDS)


def test_intraday_only_tickers_are_held_out_until_their_evidence_is_tested():
    # ACK 5 Oct 2026 (change 1): 803 tickers had only intraday setups (no tested evidence); they caused 267 of 279
    # partial market profiles, 718 book rows and thousands of Morning quote requests.
    only_intraday = ticker_lane([c("15m", "SOS -> LPS continuation", "ACTIVATED"), c("60m", "Spring Candidate", "DETECTED")])
    assert only_intraday["trade_lane"] == "INTRADAY_ONLY_UNTESTED"
    assert only_intraday["trade_lane_basis"] == "INTRADAY_ONLY_UNTESTED"
    mixed = ticker_lane([c("15m", "SOS -> LPS continuation", "ACTIVATED"), c("1d", "Upthrust Candidate", "DETECTED")])
    assert mixed["trade_lane"] == "C" and mixed["trade_lane_setup"].startswith("1d|")


def test_a_tested_intraday_timeframe_rejoins_automatically():
    table = dict(load_lanes()); table["untested_timeframes"] = ["5m", "15m"]          # 60m tested by step 4
    assert ticker_lane([c("60m", "Spring Candidate", "DETECTED")], table)["trade_lane"] == "C"


# --- Fix A (ACK 5 Oct 2026): the lane comes only from setups on the trade's side. ---------------------------------
# Run 20261005_072245: 174 of 506 lane A/B rows took their lane from an opposite-side setup (the NVS put was lane A
# from a BULL monthly Failed Upthrust Continuation); on trade-side setups 134 had none, 36 were C and 4 A.

def cs(tf, kind, state, direction, outcome=None, invalidation=None):
    return {**c(tf, kind, state, outcome, invalidation), "Direction": direction}


def test_lane_uses_only_setups_on_the_trade_side():
    setups = [cs("1mo", "Failed Upthrust Continuation", "ACTIVATED", "BULL"),
              cs("1d", "Upthrust Candidate", "DETECTED", "BEAR")]
    put = ticker_lane(setups, side="BEAR")
    assert put["trade_lane"] == "C" and put["trade_lane_setup"].startswith("1d|Upthrust")
    assert ticker_lane(setups, side="BULL")["trade_lane"] == "A"


def test_only_opposite_side_setups_leave_the_ticker_visible_in_lane_c():
    out = ticker_lane([cs("1d", "SOS -> LPS continuation", "ACTIVATED", "BULL")], side="BEAR")
    assert out["trade_lane"] == "C" and out["trade_lane_basis"] == "NO_LIVE_SETUP_ON_TRADE_SIDE"


def test_no_trade_side_is_lane_c_and_stated():
    out = ticker_lane([cs("1d", "SOS -> LPS continuation", "ACTIVATED", "BULL")], side="UNASSIGNED")
    assert out["trade_lane"] == "C" and out["trade_lane_basis"] == "NO_TRADE_SIDE"


def test_lane_records_its_side_and_is_demoted_if_the_side_changes():
    a = ticker_lane([cs("1d", "SOS -> LPS continuation", "ACTIVATED", "BULL")], side="BULL")
    assert a["trade_lane_side"] == "BULL"
    flipped = confirm_early_entry(a, None, final_direction="PUT")
    assert flipped["trade_lane"] == "C" and flipped["trade_lane_basis"] == "LANE_SIDE_CHANGED"
    assert confirm_early_entry(a, None, final_direction="CALL")["trade_lane"] == "A"


def test_discovery_passes_its_thesis_side_to_the_lane():
    import inspect
    import avshunter_discovery_ULTIMATE as d
    assert "side=_thesis_side" in inspect.getsource(d.scan_ticker_ultimate)
