"""Rapid rotation flag reads the freshest data per instrument (ACK 19 Oct 2026: "build it all").

The Colab futures CSVs it was written for no longer exist, so it always fell back to the previous session's
ETF bars. The pre-open overnight capture already holds live crude and gold futures and pre-market SPY/QQQ.
Order per instrument: fresh overnight capture, then the Colab CSV, then Polygon's previous session; every
result states its source and the window it covers."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

import rapid_rotation_flag as rrf


def _capture(tmp_path, *, age_hours=0.2, cl_state="OK", cl_stale=False, run_session="PreOpen"):
    when = datetime.now(timezone.utc) - timedelta(hours=age_hours)
    doc = {"as_of_utc": when.isoformat(), "us_reference_session": "2026-10-16", "run_session": run_session,
           "groups": {"rates_commodities": [{"symbol": "CL=F", "state": cl_state, "stale": cl_stale, "change_pct": 2.6},
                                            {"symbol": "GC=F", "state": "OK", "stale": False, "change_pct": 0.31}],
                      "us_premarket": [{"symbol": "SPY", "state": "OK", "stale": False, "change_pct": -0.9},
                                       {"symbol": "QQQ", "state": "OK", "stale": True, "change_pct": -1.2}]}}
    (tmp_path / "overnight_20261019_123500.json").write_text(json.dumps(doc), encoding="utf-8")


@pytest.fixture
def polygon(monkeypatch):
    calls = []

    def fake(ticker):
        calls.append(ticker)
        return {"ticker": ticker, "pct_change": 0.1, "status": "OK", "source": "polygon"}
    monkeypatch.setattr(rrf, "get_polygon_change", fake)
    return calls


def test_live_futures_from_a_fresh_overnight_capture_come_first(tmp_path, monkeypatch, polygon):
    _capture(tmp_path)
    monkeypatch.setattr(rrf, "COLAB_DROP_DIR", tmp_path)
    r = rrf.fetch_commodity("CL=F", rrf.COMMODITY_FUTURES["CL=F"])
    assert r["pct_change"] == 2.6 and r["source"] == "overnight_capture"
    assert "since the 2026-10-16 close" in r["window"] and polygon == []


def test_a_stale_or_failed_capture_line_falls_back_to_polygon_with_its_window_stated(tmp_path, monkeypatch, polygon):
    _capture(tmp_path, cl_state="NO_DATA")
    monkeypatch.setattr(rrf, "COLAB_DROP_DIR", tmp_path)
    r = rrf.fetch_commodity("CL=F", rrf.COMMODITY_FUTURES["CL=F"])
    assert r["source"] == "polygon" and r["etf_used"] == "USO" and polygon == ["USO"]
    assert r["window"] == "previous session, open to close"


def test_an_old_capture_is_not_used(tmp_path, monkeypatch, polygon):
    _capture(tmp_path, age_hours=20)
    monkeypatch.setattr(rrf, "COLAB_DROP_DIR", tmp_path)
    assert rrf.fetch_commodity("GC=F", rrf.COMMODITY_FUTURES["GC=F"])["source"] == "polygon"


def test_pre_market_paper_assets_come_from_the_capture_only_when_live(tmp_path, monkeypatch, polygon):
    _capture(tmp_path)
    monkeypatch.setattr(rrf, "COLAB_DROP_DIR", tmp_path)
    spy, qqq = rrf.fetch_paper("SPY"), rrf.fetch_paper("QQQ")
    assert spy["source"] == "overnight_capture" and spy["pct_change"] == -0.9
    assert qqq["source"] == "polygon"                                   # its pre-market line was stale


def test_without_any_capture_the_flag_works_as_before(tmp_path, monkeypatch, polygon):
    monkeypatch.setattr(rrf, "COLAB_DROP_DIR", tmp_path)
    assert rrf.fetch_commodity("SI=F", rrf.COMMODITY_FUTURES["SI=F"])["etf_used"] == "SLV"


def test_an_evening_capture_is_not_used_because_after_the_close_it_measures_almost_nothing(tmp_path, monkeypatch, polygon):
    _capture(tmp_path, run_session="PostClose")
    monkeypatch.setattr(rrf, "COLAB_DROP_DIR", tmp_path)
    assert rrf.fetch_commodity("CL=F", rrf.COMMODITY_FUTURES["CL=F"])["source"] == "polygon"
