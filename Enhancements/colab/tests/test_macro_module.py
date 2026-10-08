"""Business rules for the macro module (Colab "AVSHUNTER_Polygon_Macro_Loader", v2.8).

An API key never reaches the console, the errors list, macro_module_contract.json or the
errors file — a requests error message carries the full URL and Polygon / FRED put the key
in the query string. Importing the module fetches, prints and writes nothing.
No network, no live data.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
import requests

SCRIPT = Path(__file__).resolve().parents[1] / "avshunter_macro_module_v2_8.py"
SECRET = "SECRETKEY1234567890"


def _module():
    spec = importlib.util.spec_from_file_location("macro_module", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _refuse(url, params=None, **kwargs):
    query = "&".join(f"{k}={v}" for k, v in (params or {}).items())
    raise requests.exceptions.ConnectionError(f"Max retries exceeded with url: {url}?{query}")


def test_importing_the_module_fetches_and_prints_nothing(capsys):
    m = _module()
    assert m.POLYGON_API_KEY is None and m.FRED_API_KEY is None
    assert capsys.readouterr().out == ""


@pytest.mark.parametrize("call", ["polygon", "snapshot", "fred"])
def test_an_api_key_never_reaches_the_console_or_the_errors_list(call, monkeypatch, capsys):
    m = _module()
    monkeypatch.setattr(m.requests, "get", _refuse)
    m.errors.clear()
    if call == "polygon":
        m.fetch_polygon("SPY", "2026-01-01", "2026-10-07", SECRET)
    elif call == "snapshot":
        m.fetch_polygon_snapshot("SPY", SECRET)
    else:
        m.fetch_fred_all({"DGS10": "10Y"}, "2026-01-01", SECRET)
    printed = capsys.readouterr().out
    assert m.errors, "the failure itself must still be recorded"
    assert SECRET not in printed
    assert all(SECRET not in entry for entry in m.errors)


GEX_HEADER = "Ticker,Date,As_Of,Data_Mode,Spot,Net_GEX_Bn,Regime,Gamma_Flip,Data_Status,Coverage_Pct\n"


def _gex_file(tmp_path, as_of):
    path = tmp_path / "avshunter_gex_proxy.csv"
    path.write_text(GEX_HEADER + f"SPY,2026-10-05,{as_of},HISTORICAL,774.74,-1.35,NEGATIVE,776.50,OK,100\n",
                    encoding="utf-8")
    return path


def test_gex_published_two_days_ago_with_a_utc_timestamp_is_fresh(tmp_path, monkeypatch):
    # The GEX proxy writes As_Of as an ISO UTC timestamp; its age is counted in calendar days.
    m = _module()
    monkeypatch.setattr(m, "END_DATE", "2026-10-07")
    out = m.load_gex(_gex_file(tmp_path, "2026-10-05T20:00:00Z"))
    assert out["age_days"] == 2
    assert out["state"] == "OK"


def test_gex_older_than_its_limit_is_stale_with_its_real_age(tmp_path, monkeypatch):
    m = _module()
    monkeypatch.setattr(m, "END_DATE", "2026-10-07")
    out = m.load_gex(_gex_file(tmp_path, "2026-09-30T20:00:00Z"))
    assert out["age_days"] == 7
    assert out["state"] == "STALE"


def test_the_bond_modules_auction_calendar_is_read_from_dropbox_macro(tmp_path, monkeypatch):
    # bond_macro_intelligence writes auction_calendar.csv to dropbox\macro, beside market_data.
    import datetime as dt
    m = _module()
    market_data, macro = tmp_path / "market_data", tmp_path / "macro"
    market_data.mkdir(); macro.mkdir()
    (macro / "auction_calendar.csv").write_text(
        "date,tenor,type,offering_usd_bn\n2026-10-08,10Y,Note,42\n", encoding="utf-8")
    monkeypatch.setattr(m, "TODAY", dt.date(2026, 10, 7))
    files = m.event_calendar_files(market_data)
    assert macro / "auction_calendar.csv" in files
    window = m.load_event_window(files=files)
    assert window["active"] is True
    assert any("10Y" in e for e in window["events"])


def test_an_empty_auction_calendar_is_found_with_no_events_not_reported_missing(tmp_path, monkeypatch):
    # With no auctions scheduled the bond module writes the header and one blank row.
    import datetime as dt
    m = _module()
    market_data, macro = tmp_path / "market_data", tmp_path / "macro"
    market_data.mkdir(); macro.mkdir()
    (macro / "auction_calendar.csv").write_text("date,tenor,type,offering_usd_bn\n,,,\n", encoding="utf-8")
    monkeypatch.setattr(m, "TODAY", dt.date(2026, 10, 7))
    m.errors.clear()
    window = m.load_event_window(files=m.event_calendar_files(market_data))
    assert window["source"] == "auction_calendar.csv"
    assert window["active"] is False and window["events"] == []
    assert not any("TypeError" in e for e in m.errors)


def test_redaction_covers_every_key_parameter_name():
    m = _module()
    text = f"u?apiKey={SECRET}&x=1 api_key={SECRET} token={SECRET}"
    assert SECRET not in m.redact(text)


class _Resp:
    def __init__(self, status, payload):
        self.status_code, self._payload = status, payload

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.exceptions.HTTPError(f"HTTP {self.status_code}", response=self)


def test_a_slow_fred_answer_is_retried_not_turned_into_a_missing_series(monkeypatch):
    m = _module()
    calls = []
    def get(url, params=None, timeout=None, **kw):
        calls.append(timeout)
        if len(calls) < 3:
            raise requests.exceptions.ReadTimeout("read timed out")
        return _Resp(200, {"observations": [{"date": "2026-10-06", "value": "4.13"}]})
    monkeypatch.setattr(m.requests, "get", get)
    monkeypatch.setattr(m.time, "sleep", lambda s: None)
    m.errors.clear()
    out = m.fetch_fred_all({"DGS10": "10Y"}, "2026-10-01", "k")
    assert "DGS10" in out and out["DGS10"].iloc[-1] == 4.13
    assert len(calls) == 3 and all(t >= 60 for t in calls)
    assert not m.errors
