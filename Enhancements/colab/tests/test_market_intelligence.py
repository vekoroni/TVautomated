"""Business rules for the market intelligence extractor (Colab "Future Bias", v5.4.3).

1. A run in the shared dropbox\\market_data folder never deletes a file: it only moves its own
   earlier timestamped outputs to archive\\, and never touches another producer's file.
2. An API key never reaches the console, the collection-error record or any written output.
No network, no live data.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
import requests

SCRIPT = Path(__file__).resolve().parents[1] / "avshunter_market_intelligence_v5_4_3.py"


def _module():
    spec = importlib.util.spec_from_file_location("market_intelligence", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)          # must not fetch, print keys or write on import
    return module


OTHER_PRODUCERS = ["macro_series_threshold_flags.csv", "macro_module_contract.json",
                   "macro_breadth.png", "macro_sector_rank.png", "avshunter_vix_engine_v3.csv",
                   "avshunter_daily_macro_regime.csv", "report_notes.md"]
OWN_PRIOR_RUN = ["forward_bias_20261005_134900.csv", "report_20261005_134900.json",
                 "macro_20261005_134900.csv", "equity_etf_20261005_134900.csv",
                 "collection_errors_20261005_134900.txt"]
CURRENT = "20261007_211500"


def test_a_run_moves_only_its_own_earlier_outputs_and_deletes_nothing(tmp_path):
    m = _module()
    for name in OTHER_PRODUCERS + OWN_PRIOR_RUN + [f"forward_bias_{CURRENT}.csv"]:
        (tmp_path / name).write_text(name, encoding="utf-8")
    m.purge_prior_runs(str(tmp_path), CURRENT)
    for name in OTHER_PRODUCERS + [f"forward_bias_{CURRENT}.csv"]:
        assert (tmp_path / name).exists(), f"{name} was touched"
    for name in OWN_PRIOR_RUN:
        assert not (tmp_path / name).exists()
        assert (tmp_path / "archive" / name).read_text(encoding="utf-8") == name   # kept, not deleted


class _Refused(requests.HTTPError):
    pass


def _raise_with_url(url_key_param):
    def get(url, params=None, **kwargs):
        query = "&".join(f"{k}={v}" for k, v in (params or {}).items())
        raise _Refused(f"403 Client Error: Forbidden for url: {url}?{query}")
    return get


@pytest.mark.parametrize("source", ["polygon", "fred"])
def test_an_api_key_never_reaches_the_console_or_the_error_record(source, monkeypatch, capsys):
    m = _module()
    secret = "SECRETKEY1234567890"
    monkeypatch.setattr(m.requests, "get", _raise_with_url(secret))
    m.COLLECTION_ERRORS.clear()
    if source == "polygon":
        m.PolygonExtractor(secret).get_data("SPY")
    else:
        m.FREDExtractor(secret).get_series("DGS10")
    printed = capsys.readouterr().out
    assert m.COLLECTION_ERRORS, "the failure itself must still be recorded"
    assert secret not in printed
    assert all(secret not in entry for entry in m.COLLECTION_ERRORS)
