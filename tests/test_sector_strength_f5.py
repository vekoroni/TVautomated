"""F5: sector alignment, sector momentum and relative strength measure the ticker (ACK, 19 Sep 2026).

Run 20260918_112522:
- ticker_sector_alignment was ALIGNED on 1,499 of 1,499 options rows: the macro packet's sector lists arrive as JSON
  text and were iterated letter by letter, so any letter matched (Discovery: 747 ALIGNED / 498 CONFLICTED / 385
  NEUTRAL). A blank gics_sector became the text "NAN" and could match a sector name.
- sector_5d_return was filled on 69 of 1,499 rows: only 89 hard-coded tickers were looked up, although Discovery
  supplies each candidate's sector ETF.
- No ticker-vs-SPY or ticker-vs-sector relative strength existed.
The canonical price store holds SPY, every sector ETF and each ticker up to the evidence session, so the values are
point-in-time and need no provider call. Relative strength is recorded for display and measurement only.
"""

from __future__ import annotations

import math
import sqlite3
from datetime import date, timedelta

import pytest

from scripts import avshunter_options_intelligence as oi
from scripts.macro_quant_packet import _ticker_alignment

PACKET = {"preferred_sectors": '["Technology", "Energy"]', "avoid_sectors": '["Utilities", "Financials"]'}


# --- alignment -------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("sector,expected", [("Utilities", "CONFLICTED"), ("Technology", "ALIGNED"),
                                             ("Health Care", "NEUTRAL")])
def test_alignment_reads_the_sector_lists_not_their_letters(sector, expected):
    assert _ticker_alignment(PACKET, {"sector": sector})[0] == expected


def test_a_blank_gics_sector_is_missing_not_the_text_nan():
    row = {"gics_sector": float("nan"), "sector": "Health Care"}
    assert _ticker_alignment({"preferred_sectors": [], "avoid_sectors": ["Financials"]}, row)[0] == "NEUTRAL"


# --- sector momentum and relative strength from the canonical price store ------------------------------------------

def _store(path, series: dict, last: date):
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE IF NOT EXISTS ohlcv_daily (ticker TEXT, trading_date TEXT, close REAL)")
    for symbol, closes in series.items():
        for i, close in enumerate(reversed(closes)):
            con.execute("INSERT INTO ohlcv_daily VALUES (?, ?, ?)", (symbol, (last - timedelta(days=i)).isoformat(), close))
    con.commit()
    con.close()


@pytest.fixture
def store(tmp_path, monkeypatch):
    path = tmp_path / "prices.sqlite"
    last = date(2026, 9, 17)
    up = [100.0 + i for i in range(22)]                 # ticker +21% over 21 bars
    flat = [100.0] * 22
    etf = [100.0 + 0.5 * i for i in range(22)]
    after = {"ZZZ": up + [500.0]}                        # a bar after the evidence session must be ignored
    _store(path, {"ZZZ": up, "SPY": flat, "XLE": etf}, last)
    _store(path, {k: v[-1:] for k, v in after.items()}, last + timedelta(days=1))
    monkeypatch.setattr(oi, "CANONICAL_PRICE_DB", path)
    oi._canonical_closes.cache_clear()
    return last


def test_an_unmapped_ticker_uses_its_discovery_sector_etf(store):
    result = oi.fetch_sector_regime("ZZZ", sector_etf="XLE", as_of=store)
    assert result["sector_etf"] == "XLE" and result["sector_etf_source"] == "DISCOVERY_SECTOR_ETF"
    assert result["sector_5d_return"] == pytest.approx(round((110.5 / 108.0 - 1) * 100, 2))
    assert result["sector_data_source"] == "CANONICAL_HISTORICAL_PRICE_DB"


def test_relative_strength_is_the_ticker_return_less_spy_and_less_its_sector(store):
    result = oi.fetch_sector_regime("ZZZ", sector_etf="XLE", as_of=store)
    ticker_20d = (121.0 / 101.0 - 1) * 100
    assert result["rs_vs_spy_20d_pct"] == pytest.approx(round(ticker_20d - 0.0, 2))
    assert result["rs_vs_sector_20d_pct"] == pytest.approx(round(ticker_20d - (110.5 / 100.5 - 1) * 100, 2))


def test_missing_prices_are_flagged_not_zero(store):
    result = oi.fetch_sector_regime("NOPE", sector_etf="XLE", as_of=store)
    assert result["rs_vs_spy_20d_pct"] is None and result["rs_vs_sector_20d_pct"] is None
    assert result["relative_strength_state"] == "TICKER_PRICES_UNAVAILABLE"


def test_the_options_row_passes_its_sector_etf_and_evidence_session():
    import inspect
    source = inspect.getsource(oi.process_ticker)
    assert "fetch_sector_regime(ticker, sector_etf=" in source
    for field in ("rs_vs_spy_20d_pct", "rs_vs_sector_20d_pct", "sector_etf_source", "relative_strength_state"):
        assert f"'{field}'" in inspect.getsource(oi), field
