"""Readiness report for a manual run now (ACK 19 Oct 2026: "we also need a function where I can run manually").

Before a manual run the report says, for the moment it is run, what the board will and will not have: US
pre-market open or not, today's 08:30 ET releases out or not, and every input that is stale or missing with its
reason. Business rules, written before the code."""

from __future__ import annotations

from datetime import datetime, timezone

from macro_board import readiness as rd
from macro_board.sources import SourceRead

RELEASES = [{"date": "2026-10-19", "name": "Leading indicators", "time_et": "10:00"},
            {"date": "2026-10-19", "name": "CPI", "time_et": "08:30"},
            {"date": "2026-10-20", "name": "PPI", "time_et": "08:30"}]
INPUTS = {"us_money_index": SourceRead("US Money Index (transmission score)", "x", "STALE", "2026-10-16T19:06:08+00:00",
                                       61.0, note="1 US session closed since it was produced; older than 48 h"),
          "bond_state": SourceRead("Bond macro state", "y", "FRESH", "2026-10-17T16:27:04+00:00", 40.0),
          "gex": SourceRead("Dealer gamma (GEX) SPY/QQQ", "z", "MISSING", note="file not found")}


def _report(et_hhmm: str, session="PreOpen"):
    h, m = (int(x) for x in et_hhmm.split(":"))
    now = datetime(2026, 10, 19, h + 4, m, tzinfo=timezone.utc)          # EDT = UTC-4
    return rd.report(now=now, session=session, segment=rd.segment_at(now), last_session="2026-10-16",
                     releases=RELEASES, inputs=INPUTS)


def test_before_pre_market_opens_it_says_the_board_will_use_the_last_close():
    text = "\n".join(_report("03:50")["lines"])
    assert "pre-market opens 04:00 ET" in text and "2026-10-16 close" in text


def test_before_0830_it_lists_todays_0830_releases_as_not_out_yet():
    text = "\n".join(_report("07:10")["lines"])
    assert "not out yet" in text and "CPI 08:30" in text and "PPI" not in text


def test_after_0835_the_releases_are_reported_as_out():
    out = _report("08:40")
    assert not any("not out yet" in line for line in out["lines"])
    assert out["timing"] == "GOOD"


def test_stale_and_missing_inputs_are_listed_with_their_reasons_and_fresh_ones_are_not():
    text = "\n".join(_report("08:40")["lines"])
    assert "US Money Index" in text and "1 US session closed" in text
    assert "Dealer gamma" in text and "file not found" in text
    assert "Bond macro state" not in text


def test_during_regular_hours_it_warns_that_todays_bars_are_partial():
    out = _report("11:00")
    assert out["timing"] == "INTRADAY" and any("partial" in line for line in out["lines"])


def test_too_early_is_flagged_so_the_prompt_can_say_so():
    assert _report("03:50")["timing"] == "EARLY"


def test_the_scheduled_pre_open_time_comes_from_the_schedule_config():
    # ACK 20 Nov 2026: pre-open build at 07:00 ET (12:00 UK); 08:30 releases still listed as not out yet before then
    assert rd.scheduled_preopen_et({"pre_open_minutes": 150}) == "07:00"
    h, m = 6, 30
    now = datetime(2026, 10, 19, h + 4, m, tzinfo=timezone.utc)
    out = rd.report(now=now, session="PreOpen", segment="PREMARKET", last_session="2026-10-16", releases=RELEASES,
                    inputs=INPUTS, preopen_et="07:00")
    assert out["timing"] == "WAIT_RELEASES" and any("07:00 ET" in line for line in out["lines"])
    later = rd.report(now=datetime(2026, 10, 19, 11, 10, tzinfo=timezone.utc), session="PreOpen", segment="PREMARKET",
                      last_session="2026-10-16", releases=RELEASES, inputs=INPUTS, preopen_et="07:00")
    assert later["timing"] == "GOOD" and any("CPI 08:30" in line for line in later["lines"])
