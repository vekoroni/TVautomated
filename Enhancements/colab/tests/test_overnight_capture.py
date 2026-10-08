"""Business rules for the overnight capture in the market intelligence extractor (v5.4.3, step 4).

The pre-open run (08:35-09:00 ET) prepares the morning run. It must say what happened since the
last US close: US index futures, the US pre-market, overnight VIX, FX, Asia's finished sessions,
Europe's session in progress and the 08:30 ET prints.

1. Everything that trades through the night is measured from its price at the last US close.
2. A non-US index reports its own session state (closed / in progress / no session today) and
   its move from its own previous close; a reopening after a holiday is flagged.
3. An old quote is reported with its age and flagged, never dropped or treated as current;
   a missing reading is MISSING, never a zero move.
4. An 08:30 print is RELEASED only when FRED has it, with value and prior.
5. The document is display-only and names the US close it measures from.
No network, no live data.
"""

from __future__ import annotations

import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

SCRIPT = Path(__file__).resolve().parents[1] / "avshunter_market_intelligence_v5_4_3.py"
NOW = datetime(2026, 10, 8, 12, 41, tzinfo=timezone.utc)          # 08:41 ET
US_CLOSE = datetime(2026, 10, 7, 20, 0, tzinfo=timezone.utc)      # 16:00 ET on 7 Oct


def _module():
    spec = importlib.util.spec_from_file_location("market_intelligence_overnight", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _bars(points):
    """5-minute bars labelled by their start time (UTC), as yfinance returns them."""
    return pd.Series([p for _, p in points], index=pd.DatetimeIndex([pd.Timestamp(t, tz="UTC") for t, _ in points]))


def _daily(points, tz):
    return pd.Series([p for _, p in points], index=pd.DatetimeIndex([pd.Timestamp(d).tz_localize(tz) for d, _ in points]))


# -- 1. measured from the last US close --------------------------------------------------------------

def test_a_us_future_is_measured_from_its_price_at_the_last_us_close():
    m = _module()
    bars = _bars([("2026-10-07 19:50", 7850.0), ("2026-10-07 19:55", 7852.0),   # 19:55 bar closes at 16:00 ET
                  ("2026-10-07 20:00", 7856.0), ("2026-10-08 12:30", 7820.5)])
    row = m.measure_since_us_close("ES=F", "S&P 500 e-mini", bars, US_CLOSE, NOW)
    assert row["state"] == "OK"
    assert row["reference"] == 7852.0 and row["last"] == 7820.5
    assert round(row["change_pct"], 3) == round((7820.5 / 7852.0 - 1) * 100, 3)
    assert row["last_bar_utc"] == "2026-10-08T12:30:00Z" and row["age_minutes"] == 11 and row["stale"] is False


def test_an_old_quote_is_reported_with_its_age_and_flagged_not_dropped():
    m = _module()
    bars = _bars([("2026-10-07 19:55", 11.80), ("2026-10-07 20:15", 11.78)])
    row = m.measure_since_us_close("^VIX9D", "VIX9D", bars, US_CLOSE, NOW, stale_after_minutes=60)
    assert row["last"] == 11.78 and row["stale"] is True and row["age_minutes"] == 986
    assert row["change_pct"] is not None


def test_an_instrument_with_no_bar_before_the_us_close_is_missing_not_a_zero_move():
    m = _module()
    row = m.measure_since_us_close("CNH=X", "USD/CNH", _bars([("2026-10-08 12:30", 7.1)]), US_CLOSE, NOW)
    assert row["state"] == "MISSING_REFERENCE" and row["change_pct"] is None
    empty = m.measure_since_us_close("CNH=X", "USD/CNH", pd.Series(dtype="float64"), US_CLOSE, NOW)
    assert empty["state"] == "MISSING" and empty["change_pct"] is None and empty["last"] is None


def test_an_official_close_supplied_as_the_reference_is_used_instead_of_the_last_bar():
    m = _module()
    bars = _bars([("2026-10-07 19:55", 777.10), ("2026-10-08 12:25", 774.25)])
    row = m.measure_since_us_close("SPY", "S&P 500 ETF", bars, US_CLOSE, NOW,
                                   reference=777.22, reference_label="official close 2026-10-07 (Polygon)")
    assert row["reference"] == 777.22 and row["reference_label"].startswith("official close")
    assert round(row["change_pct"], 4) == round((774.25 / 777.22 - 1) * 100, 4)


# -- 2. non-US sessions ------------------------------------------------------------------------------

def test_an_asian_index_that_finished_today_is_closed_with_its_session_move():
    m = _module()
    daily = _daily([("2026-10-06", 69800.0), ("2026-10-07", 70035.71), ("2026-10-08", 69042.11)], "Asia/Tokyo")
    row = m.local_session_reading("^N225", "Nikkei 225", daily, NOW, "Asia/Tokyo", "09:00", "15:30")
    assert row["state"] == "CLOSED" and row["session_date"] == "2026-10-08"
    assert row["prev_session_date"] == "2026-10-07"
    assert round(row["change_pct"], 3) == round((69042.11 / 70035.71 - 1) * 100, 3)
    assert row["after_break"] is False


def test_a_market_reopening_after_a_holiday_is_flagged():
    m = _module()
    daily = _daily([("2026-09-29", 3830.0), ("2026-09-30", 3842.20), ("2026-10-08", 3811.90)], "Asia/Shanghai")
    row = m.local_session_reading("000001.SS", "Shanghai Composite", daily, NOW, "Asia/Shanghai", "09:30", "15:00")
    assert row["state"] == "CLOSED" and row["break_days"] == 8 and row["after_break"] is True
    assert "first session" in row["note"]


def test_a_european_index_during_its_session_is_intraday():
    m = _module()
    daily = _daily([("2026-10-07", 25104.36), ("2026-10-08", 24889.33)], "Europe/Berlin")
    row = m.local_session_reading("^GDAXI", "DAX", daily, NOW, "Europe/Berlin", "09:00", "17:30")
    assert row["state"] == "INTRADAY" and row["session_date"] == "2026-10-08"
    assert row["change_pct"] < 0


def test_a_weekday_without_a_session_bar_reports_no_session_today_and_the_last_session():
    m = _module()
    daily = _daily([("2026-10-06", 24000.0), ("2026-10-07", 24130.50)], "Asia/Hong_Kong")
    row = m.local_session_reading("^HSI", "Hang Seng", daily, NOW, "Asia/Hong_Kong", "09:30", "16:10")
    assert row["state"] == "NO_SESSION_TODAY" and row["session_date"] == "2026-10-07"


# -- 4. 08:30 prints -----------------------------------------------------------------------------------

def test_an_0830_print_already_on_fred_is_released_with_value_and_prior():
    m = _module()
    obs = [{"date": "2026-10-03", "value": "197000"}, {"date": "2026-09-26", "value": "199000"}]
    row = m.release_reading(180, "Jobless claims", "ICSA", "08:30", obs, "2026-10-08 07:33:30-05", NOW)
    assert row["state"] == "RELEASED"
    assert row["value"] == 197000.0 and row["prior"] == 199000.0 and row["observation_date"] == "2026-10-03"
    assert row["change"] == -2000.0


def test_a_scheduled_print_not_yet_on_fred_is_pending_before_its_time_and_flagged_after():
    m = _module()
    obs = [{"date": "2026-08-01", "value": "320.1"}, {"date": "2026-07-01", "value": "319.4"}]
    early = m.release_reading(10, "CPI", "CPIAUCSL", "08:30", obs, "2026-09-11 08:37:49-05",
                              datetime(2026, 10, 8, 12, 0, tzinfo=timezone.utc))      # 08:00 ET
    late = m.release_reading(10, "CPI", "CPIAUCSL", "08:30", obs, "2026-09-11 08:37:49-05", NOW)
    assert early["state"] == "PENDING" and early["value"] is None
    assert late["state"] == "NOT_YET_ON_FRED" and late["value"] is None


# -- 5. the US close it measures from ---------------------------------------------------------------

def test_the_reference_close_follows_the_runner_including_a_half_day(monkeypatch):
    m = _module()
    monkeypatch.setenv("AVSH_SESSION_CUTOFF", "2026-11-27")
    monkeypatch.setenv("AVSH_US_CLOSE_UTC", "2026-11-27T18:00:00Z")
    session, close_utc, source = m.us_reference_close(datetime(2026, 11, 30, 13, 40, tzinfo=timezone.utc))
    assert session == "2026-11-27" and close_utc == datetime(2026, 11, 27, 18, 0, tzinfo=timezone.utc)
    assert source == "runner"


def test_without_the_runner_the_reference_close_is_derived_and_says_so(monkeypatch):
    m = _module()
    monkeypatch.delenv("AVSH_SESSION_CUTOFF", raising=False)
    monkeypatch.delenv("AVSH_US_CLOSE_UTC", raising=False)
    session, close_utc, source = m.us_reference_close(datetime(2026, 10, 12, 12, 40, tzinfo=timezone.utc))  # Mon
    assert session == "2026-10-09" and close_utc == datetime(2026, 10, 9, 20, 0, tzinfo=timezone.utc)
    assert "no trading calendar" in source


def test_overnight_outputs_are_archived_like_the_other_outputs(tmp_path):
    m = _module()
    (tmp_path / "overnight_20261007_211500.json").write_text("{}", encoding="utf-8")
    (tmp_path / "overnight_20261008_124100.json").write_text("{}", encoding="utf-8")
    m.purge_prior_runs(str(tmp_path), "20261008_124100")
    assert (tmp_path / "archive" / "overnight_20261007_211500.json").exists()
    assert (tmp_path / "overnight_20261008_124100.json").exists()


class _Response:
    def __init__(self, payload, status=200):
        self._payload, self.status_code = payload, status
        self.text = json.dumps(payload)

    def json(self):
        return self._payload


def test_the_overnight_document_is_display_only_names_its_reference_and_carries_no_key(monkeypatch):
    m = _module()
    monkeypatch.setenv("AVSH_SESSION_CUTOFF", "2026-10-07")
    monkeypatch.setenv("AVSH_US_CLOSE_UTC", "2026-10-07T20:00:00Z")
    monkeypatch.setenv("AVSH_RUN_SESSION", "PreOpen")
    secret = "SECRETKEY1234567890"
    calls = []

    def history(symbol, period, interval):
        if interval == "1d":
            return pd.DataFrame({"Close": [100.0, 101.0]},
                                index=pd.DatetimeIndex([pd.Timestamp("2026-10-07", tz="UTC"),
                                                        pd.Timestamp("2026-10-08", tz="UTC")]))
        return pd.DataFrame({"Close": [100.0, 99.0], "Volume": [0, 0]},
                            index=pd.DatetimeIndex([pd.Timestamp("2026-10-07 19:55", tz="UTC"),
                                                    pd.Timestamp("2026-10-08 12:30", tz="UTC")]))

    def get(url, params=None, headers=None, timeout=None):
        calls.append(url)
        if "cboe" in url:
            return _Response({"data": {"current_price": 15.69, "prev_day_close": 15.08}})
        if "marketdata" in url:
            return _Response({"s": "ok", "t": [1791402900, 1791462300], "c": [777.1, 774.25], "v": [10, 20]}, 203)
        if "releases/dates" in url:
            return _Response({"release_dates": [{"release_id": 180, "release_name": "Claims", "date": "2026-10-08"}]})
        if url.endswith("/series"):
            return _Response({"seriess": [{"last_updated": "2026-10-08 07:33:30-05"}]})
        if "observations" in url:
            return _Response({"observations": [{"date": "2026-10-03", "value": "197000"},
                                               {"date": "2026-09-26", "value": "199000"}]})
        return _Response({}, 404)

    ext = m.OvernightExtractor(marketdata_key=secret, fred_key=secret, now_utc=NOW, history=history, http_get=get,
                               official_closes={"SPY": (777.22, "2026-10-07")})
    doc = ext.extract()
    assert doc["authority"] == "DISPLAY_ONLY" and doc["run_session"] == "PreOpen"
    assert doc["us_reference_session"] == "2026-10-07" and doc["us_reference_close_utc"] == "2026-10-07T20:00:00Z"
    for group in ("us_futures", "us_premarket", "volatility", "rates_commodities", "fx", "asia", "europe"):
        assert doc["groups"][group], group
    vix = doc["groups"]["volatility"][0]
    assert vix["last"] == 15.69 and vix["reference"] == 15.08 and vix["source"] == "CBOE_DELAYED"
    spy = next(r for r in doc["groups"]["us_premarket"] if r["symbol"] == "SPY")
    assert spy["reference"] == 777.22
    assert doc["releases_today"][0]["state"] == "RELEASED"
    assert secret not in json.dumps(doc)
