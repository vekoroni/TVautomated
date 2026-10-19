"""Input strip fixes and the rapid rotation flag record (ACK 19 Oct 2026: "why this amber and red", then
"build it all"). Business rules, written before the changes."""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest

from macro_board import holdings as hold
from macro_board import market_prices as mkt
from macro_board import scorecard as sc
from macro_board import sources as src

PROSHARES = """PORTFOLIO HOLDINGS INFORMATION,,,,
AS OF 10/16/2026,,,,
,,,,
Fund Ticker, Fund Name, Security Ticker, Security Sedol, Security Description, Coupon, Maturity Date, Shares/Contracts, Exposure Value (Notional + G/L), Market Value
"TQQQ","ProShares UltraPro QQQ","","","NASDAQ 100 Index SWAP Societe Generale",,,341686,9972977209.3,,
"TQQQ","ProShares UltraPro QQQ","","","NASDAQ 100 E-MINI EQUITY INDEX 18/DEC/2026 NQZ6 INDEX",,,7178,4219443740,,
"TQQQ","ProShares UltraPro QQQ","IQMM","BTGTPK8","PROSHARES GENIUS MNY MKT ETF",,,59872500,,5994434700
"TQQQ","ProShares UltraPro QQQ","","C0FRT41","TREASURY BILL",,,1100000000,,1087684466
"TQQQ","ProShares UltraPro QQQ","NVDA","2379504","NVIDIA CORP",,,100,,600
"TQQQ","ProShares UltraPro QQQ","AAPL","2046251","APPLE INC",,,100,,300
"TQQQ","ProShares UltraPro QQQ","MSFT","2588173","MICROSOFT CORP",,,100,,100
"TQQQ","ProShares UltraPro QQQ","","","Net Other Assets (Liabilities)",,,7820551202.39,,7820551202.39
"""


# --- QQQ holdings: Invesco blocks automated downloads (406 since 2 Oct); the Nasdaq-100 sleeve of ProShares'
# TQQQ daily file is the fallback (measured 19 Oct: weights match QQQ's, correlation 0.994) ------------------

def test_the_proshares_file_gives_nasdaq_100_stock_weights_without_swaps_bills_or_money_market_funds():
    holdings, as_of = hold.parse_proshares_csv(PROSHARES.encode("utf-8"), exclude=["IQMM"])
    assert as_of == "2026-10-16"
    assert [h["ticker"] for h in holdings] == ["NVDA", "AAPL", "MSFT"]
    assert [h["weight_pct"] for h in holdings] == pytest.approx([60.0, 30.0, 10.0])


def test_when_the_issuer_refuses_the_fallback_file_is_used_and_labelled(tmp_path, monkeypatch):
    sources = {"QQQ": {"issuer": "Invesco", "format": "invesco_json", "url": "https://invesco.example/qqq",
                       "fallback": {"issuer": "ProShares TQQQ (Nasdaq-100 sleeve)", "format": "proshares_csv",
                                    "url": "https://proshares.example/tqqq.csv", "exclude": ["IQMM"]}}}

    def fake_download(requests, source, timeout, **kw):
        if "invesco" in source["url"]:
            raise RuntimeError("HTTPError: 406 Client Error: Not Acceptable")
        return PROSHARES.encode("utf-8")

    monkeypatch.setattr(hold, "_download", fake_download)
    report = hold.refresh(sources, tmp_path)
    assert report["QQQ"]["status"] == "OK" and report["QQQ"]["source"] == "FALLBACK"
    assert "406" in report["QQQ"]["primary_error"]
    saved = hold.load_latest(tmp_path, ["QQQ"])["QQQ"]
    assert saved["issuer"] == "ProShares TQQQ (Nasdaq-100 sleeve)" and saved["as_of"] == "2026-10-16"


def test_when_both_sources_fail_the_refresh_is_reported_failed_with_both_errors(tmp_path, monkeypatch):
    sources = {"QQQ": {"issuer": "Invesco", "format": "invesco_json", "url": "https://invesco.example/qqq",
                       "fallback": {"issuer": "ProShares", "format": "proshares_csv", "url": "https://p.example/x.csv"}}}
    monkeypatch.setattr(hold, "_download", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("down")))
    report = hold.refresh(sources, tmp_path)
    assert report["QQQ"]["status"] == "FAILED" and "fallback" in report["QQQ"]["error"].lower()


# --- latest prices: before US pre-market (04:00 ET) no quote can exist after the close -------------------------

def test_an_empty_snapshot_while_the_us_market_is_closed_is_no_quote_yet_not_a_failure():
    assert mkt.classify_latest("EMPTY", "CLOSED") == "NO_QUOTE_YET"
    assert mkt.classify_latest("EMPTY", "PREMARKET") == "EMPTY"          # pre-market open and nothing came: a problem
    assert mkt.classify_latest("OK", "CLOSED") == "OK"


# --- input ages: a file is current while no US session has closed since it was produced ----------------------

def test_a_file_older_than_its_hour_limit_stays_fresh_when_no_session_has_closed_since():
    made = pd.Timestamp("2026-10-17T16:27:04Z")                         # Saturday
    now = datetime(2026, 10, 19, 12, 0, tzinfo=timezone.utc)            # Monday before the open
    assert src.freshness(made, now, max_age_hours=30) == ("FRESH", "no US session has closed since it was produced")


def test_a_file_that_missed_a_session_close_and_its_hour_limit_is_stale():
    made = pd.Timestamp("2026-10-16T19:06:08Z")                         # Friday 15:06 ET, before Friday's close
    now = datetime(2026, 10, 19, 8, 0, tzinfo=timezone.utc)
    status, note = src.freshness(made, now, max_age_hours=48)
    assert status == "STALE" and "1 US session" in note


def test_within_the_hour_limit_a_file_is_fresh_as_before():
    made = pd.Timestamp("2026-10-19T13:00:00Z")
    now = datetime(2026, 10, 19, 21, 0, tzinfo=timezone.utc)            # after Monday's close
    assert src.freshness(made, now, max_age_hours=30)[0] == "FRESH"


# --- the rapid rotation flag, measured: its rule replayed on daily closes since 2021 ------------------------

def _closes(n=300, seed=4):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2024-01-01", periods=n)
    r = pd.DataFrame(rng.normal(0, 0.01, (n, 6)), index=idx, columns=["USO", "GLD", "SLV", "GDX", "SPY", "QQQ"])
    shock = idx[100]
    r.loc[shock, ["USO", "GLD", "SLV"]] = 0.04                          # commodities spike
    r.loc[shock, ["SPY", "QQQ"]] = -0.02                                # paper drops
    return (1 + r).cumprod() * 100, shock


COMM = {"CL=F": {"spike_pct": 2.0, "etf_fallback": "USO"}, "GC=F": {"spike_pct": 1.2, "etf_fallback": "GLD"},
        "SI=F": {"spike_pct": 1.5, "etf_fallback": "SLV"}, "HG=F": {"spike_pct": 1.5, "etf_fallback": "CPER"},
        "GDX": {"spike_pct": 1.8, "etf_fallback": "GDX"}}
PAPER = {"SPY": {"drop_pct": -0.8}, "QQQ": {"drop_pct": -0.8}}


def test_the_flag_rule_is_replayed_on_history_and_scored_against_all_sessions():
    closes, shock = _closes()
    out = sc.score_rotation_flag(closes.shift(1), closes, commodities=COMM, paper=PAPER, active_threshold=2, horizons=[1, 5])
    day = out["history"][str(shock.date())]
    assert day == "SPECULATOR_ROTATION_ACTIVE"
    assert out["missing_inputs"] == ["CPER"]                           # copper is not in the store: stated, not guessed
    rec = out["record"]["5"]
    assert set(rec) >= {"all", "flagged"} and rec["all"]["n"] > rec["flagged"]["n"] >= 1
    assert "spy_mean_pct" in rec["flagged"] and "commodities_minus_spy_pp" in rec["flagged"]
