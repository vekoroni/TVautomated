"""Business rules for the scheduled part of the event payload, measured locally (ACK 10 Oct 2026).

The ChatGPT event payload mixes scheduled US releases with news. The scheduled part is measurable from
FRED: release dates (the calendar), the print as known on the release day (vintage), the previous value
and its revision, a surprise measured against the series' own history (no free consensus source - stated,
never implied), how markets reacted that session, and how much more the market has moved on that
release's past days. ChatGPT keeps only the unscheduled news. Display only. No network: FRED is a
transport the tests replace.
"""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

from macro_board import scheduled_events as se

RELEASES = [{"release_id": 10, "name": "CPI", "series_id": "CPIAUCSL", "time_et": "08:30", "transform": "pct_change",
             "unit": "% m/m", "why_it_matters": "Inflation, the Fed path and yields."},
            {"release_id": 180, "name": "Jobless claims", "series_id": "ICSA", "time_et": "08:30", "transform": "diff",
             "unit": "claims", "why_it_matters": "Labour-market slack."}]
CFG = {"releases": RELEASES, "lookback_changes": 12, "surprise_band_z": 1.0, "reaction_tickers": ["SPY", "TLT"],
       "event_day_tickers": ["SPY", "TLT"], "sessions_ahead": 20, "min_event_days": 3}


# -- the surprise is measured against the series' own history, never called a consensus surprise ---------------

def test_a_monthly_index_is_read_as_its_month_on_month_change_against_its_own_past_changes():
    idx = pd.date_range("2025-01-01", periods=15, freq="MS")
    values = 100 * np.cumprod(np.r_[1.0, np.full(13, 1.002), 1.008])          # 0.2% a month, then 0.8%
    out = se.measured_surprise(pd.Series(values, index=idx), "pct_change", lookback=12, band_z=1.0)
    assert round(out["change"], 3) == 0.8 and out["label"] == "ABOVE_OWN_TREND"
    assert out["basis"] == "change vs its own past 12 changes; not a consensus surprise"
    flat = se.measured_surprise(pd.Series(100 * np.cumprod(np.full(15, 1.002)), index=idx), "pct_change", lookback=12, band_z=1.0)
    assert flat["label"] == "IN_LINE_WITH_OWN_TREND"


def test_a_short_series_has_no_surprise_label_rather_than_a_guess():
    out = se.measured_surprise(pd.Series([1.0, 2.0], index=pd.date_range("2026-01-01", periods=2, freq="MS")),
                               "diff", lookback=12, band_z=1.0)
    assert out["label"] == "INSUFFICIENT_HISTORY" and out["z"] is None


# -- how the market behaves on this release's days ------------------------------------------------------------

def test_event_days_are_compared_with_other_days_on_the_same_instrument():
    idx = pd.bdate_range("2026-01-01", periods=60)
    moves = np.where(np.arange(60) % 10 == 5, 0.02, 0.005) * np.where(np.arange(60) % 2 == 0, 1, -1)
    closes = pd.DataFrame({"SPY": 100 * np.cumprod(1 + moves)}, index=idx)
    release_days = [d.date() for d in idx[5::10]] + [date(2026, 1, 3)]          # a Saturday is ignored
    out = se.event_day_moves(closes, release_days, ["SPY"], as_of=idx[-1].date(), min_days=3)
    spy = out["SPY"]
    assert spy["n"] == 6 and round(spy["mean_abs_event_pct"], 2) == 2.0 and round(spy["mean_abs_other_pct"], 2) == 0.5
    assert round(spy["ratio"], 1) == 4.0
    few = se.event_day_moves(closes, release_days[:2], ["SPY"], as_of=idx[-1].date(), min_days=3)
    assert few["SPY"]["ratio"] is None and few["SPY"]["n"] == 2


# -- released this session vs upcoming; the print as known that day ---------------------------------------------

def _transport(calls):
    def get(url, params):
        calls.append((url, dict(params)))
        if url.endswith("/release/dates"):
            rid = int(params["release_id"])
            dates = {10: ["2026-09-11", "2026-10-09", "2026-11-12"], 180: ["2026-10-01", "2026-10-15"]}[rid]
            return 200, {"release_dates": [{"release_id": rid, "date": d} for d in dates]}
        if url.endswith("/series/observations"):
            sid = params["series_id"]
            rt = params.get("realtime_end")
            if sid == "CPIAUCSL" and rt == "2026-10-09":
                return 200, {"observations": [{"date": "2026-08-01", "value": "320.0"}, {"date": "2026-09-01", "value": "321.6"}]}
            if sid == "CPIAUCSL" and rt == "2026-10-08":
                return 200, {"observations": [{"date": "2026-07-01", "value": "319.0"}, {"date": "2026-08-01", "value": "319.8"}]}
            months = pd.date_range("2025-01-01", "2026-09-01", freq="MS")
            vals = 300 * np.cumprod(np.full(len(months), 1.002)) if sid == "CPIAUCSL" else np.full(len(months), 200000.0)
            return 200, {"observations": [{"date": str(m.date()), "value": str(v)} for m, v in zip(months, vals)]}
        return 404, {}
    return get


def test_a_release_on_the_session_is_released_with_the_print_as_known_that_day_and_the_revision(tmp_path):
    calls = []
    data = se.fetch(RELEASES, as_of="2026-10-09", cache_dir=tmp_path, transport=_transport(calls), api_key="k")
    assert data["status"] == "OK"
    cpi = data["vintages"][10]
    assert cpi["on_day"][-1] == {"date": "2026-09-01", "value": 321.6}
    assert cpi["day_before"][-1] == {"date": "2026-08-01", "value": 319.8}
    idx = pd.bdate_range("2026-08-01", "2026-10-09")
    closes = pd.DataFrame({"SPY": np.linspace(700, 778, len(idx)), "TLT": np.linspace(90, 88, len(idx))}, index=idx)
    block = se.build(data, as_of_session="2026-10-09", upcoming_sessions=[date(2026, 10, 12), date(2026, 10, 13), date(2026, 10, 14), date(2026, 10, 15)],
                     closes=closes, reactions={"SPY": {"key": "ACCEPTED_UP", "close_pct": 0.6}}, cfg=CFG)
    rel = {e["name"]: e for e in block["released"]}
    assert set(rel) == {"CPI"}
    cpi_e = rel["CPI"]
    assert cpi_e["actual"] == 321.6 and cpi_e["observation_date"] == "2026-09-01" and cpi_e["previous"] == 320.0
    assert cpi_e["previous_as_first_known"] == 319.8 and cpi_e["revision_of_previous"] == round(320.0 - 319.8, 6)
    assert cpi_e["reaction"]["SPY"]["key"] == "ACCEPTED_UP" and cpi_e["reaction"]["TLT"]["key"] == "UNKNOWN"
    assert cpi_e["forecast"] is None and cpi_e["forecast_source"] == "NOT_AVAILABLE_LOCALLY"
    upcoming = [(e["name"], e["date"], e["sessions_ahead"]) for e in block["upcoming"]]
    assert upcoming == [("Jobless claims", "2026-10-15", 4)]                     # CPI 12 Nov is beyond the window


def test_fred_reads_are_cached_and_reused_offline_and_a_missing_key_is_stated_not_invented(tmp_path):
    calls = []
    se.fetch(RELEASES, as_of="2026-10-09", cache_dir=tmp_path, transport=_transport(calls), api_key="k")
    first = len(calls)
    offline = lambda url, params: (599, {})
    again = se.fetch(RELEASES, as_of="2026-10-09", cache_dir=tmp_path, transport=offline, api_key="k")
    assert again["status"] == "OK" and first > 0
    assert se.fetch(RELEASES, as_of="2026-10-09", cache_dir=tmp_path / "empty", transport=None, api_key="")["status"] == "NO_KEY"


def test_the_local_events_are_written_in_the_event_payload_schema_with_the_route_and_no_invented_consensus(tmp_path):
    data = se.fetch(RELEASES, as_of="2026-10-09", cache_dir=tmp_path, transport=_transport([]), api_key="k")
    idx = pd.bdate_range("2026-08-01", "2026-10-09")
    closes = pd.DataFrame({"SPY": np.linspace(700, 778, len(idx))}, index=idx)
    block = se.build(data, as_of_session="2026-10-09", upcoming_sessions=[date(2026, 10, 12)], closes=closes, reactions={}, cfg=CFG)
    doc = se.as_event_payload(block)
    assert doc["schema_version"] == "avshunter_us_economic_event_impact_v1_0"
    assert doc["generated_from_report_date"] == "2026-10-09"
    assert doc["run_context"]["route"] == "SCHEDULED_RELEASES_MEASURED" and doc["run_context"]["automatic_execution_enabled"] is False
    e = doc["events"][0]
    assert e["status"] == "RELEASED" and e["forecast"] is None and e["forecast_source"] == "NOT_AVAILABLE_LOCALLY"
    assert e["release_time_us_eastern"].startswith("2026-10-09T08:30") and e["evidence_quality"] == 100
    assert "not a consensus surprise" in e["surprise_basis"]
