"""Business rules for the macro module (Colab "AVSHUNTER_Polygon_Macro_Loader", v2.7).

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

SCRIPT = Path(__file__).resolve().parents[1] / "avshunter_macro_module_v2_7.py"
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


def test_redaction_covers_every_key_parameter_name():
    m = _module()
    text = f"u?apiKey={SECRET}&x=1 api_key={SECRET} token={SECRET}"
    assert SECRET not in m.redact(text)
