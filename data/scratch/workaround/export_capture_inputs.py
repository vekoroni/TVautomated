#!/usr/bin/env python3
"""Export the inputs for the option capture analysis (v1, 16 Oct 2026). Read-only on every source.

Why: the week's test asked how much profit each trade made AVAILABLE during the hold and whether the card's rules
would have captured it. That needs the daily stock bars and every recorded option quote since the hand-offs, which
live in the 1.7 GB price store and the live_options folders on this PC.

Run from the repo root (PowerShell):
    venv\\Scripts\\python.exe data\\scratch\\workaround\\export_capture_inputs.py
    venv\\Scripts\\python.exe data\\scratch\\workaround\\export_capture_inputs.py --since 2026-10-08
Writes data\\scratch\\workaround\\monitor\\scorecard\\capture_inputs\\:
    bars.csv          ticker, trading_date, open, high, low, close (COMPLETE bars) for every ledger / card ticker
    option_marks.csv  date, ticker, contract, bid, ask, mid, iv, delta, oi, volume, quote_utc, source (live_options + monitor files)
"""
from __future__ import annotations

import argparse
import glob
import json
import sqlite3
from pathlib import Path

import pandas as pd

VERSION = "export_capture_inputs_v1"
WORK = Path("data") / "scratch" / "workaround"
DB = Path("data") / "canonical" / "historical_prices.sqlite"
LIVE = Path("data") / "canonical" / "live_options"
OUT = WORK / "monitor" / "scorecard" / "capture_inputs"
EXTRA = ["VXX", "SPY", "QQQ", "IWM", "OI", "BILI", "GME", "REPX", "SNAP", "TEVA", "IBKR", "EWG", "NAT", "PLUG", "PUMP",
         "TEM", "BTI", "IGV", "XOVR", "LWLG", "FISV", "FIGS", "USAR", "ARE", "WIX", "HIVE", "FRO"]


def tickers_from_ledgers(since: str) -> list[str]:
    t = set(EXTRA)
    for f in glob.glob(str(WORK / "decision_ledger_2026-*.csv")):
        if f.endswith(("_outcomes.csv", "_summary.csv")) or Path(f).stem[-10:] < since:
            continue
        t |= set(pd.read_csv(f, usecols=["ticker"]).ticker.astype(str).str.upper())
    for f in glob.glob(str(WORK / "handoff" / "*" / "handoff.csv")):
        try:
            t |= set(pd.read_csv(f, usecols=["ticker"]).ticker.astype(str).str.upper())
        except Exception:
            pass
    return sorted(t)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default="2026-10-08")
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    tick = tickers_from_ledgers(a.since)
    marks = ",".join("?" * len(tick))
    with sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True) as con:
        bars = pd.read_sql_query(
            f"SELECT ticker, trading_date, open, high, low, close FROM ohlcv_daily WHERE bar_status='COMPLETE' "
            f"AND trading_date >= ? AND ticker IN ({marks}) ORDER BY ticker, trading_date", con, params=[a.since, *tick])
    bars.to_csv(OUT / "bars.csv", index=False)

    rows, want = [], set(tick)
    for d in sorted(p for p in LIVE.iterdir() if p.is_dir() and p.name >= a.since):
        for td in d.iterdir():
            if not td.is_dir() or td.name.upper() not in want:
                continue
            for f in td.glob("*.json"):
                try:
                    j = json.loads(f.read_text(encoding="utf-8-sig"))
                except Exception:
                    continue
                rows.append({"date": d.name, "ticker": td.name.upper(), "contract": j.get("recommended_contract"),
                             "bid": j.get("contract_bid"), "ask": j.get("contract_ask"), "mid": j.get("contract_mid"),
                             "iv": j.get("contract_iv"), "delta": j.get("contract_delta"), "oi": j.get("contract_oi"),
                             "volume": j.get("contract_volume"), "quote_utc": j.get("contract_quote_timestamp_utc"),
                             "source": "live_options:" + str(j.get("contract_quote_source"))})
    for f in glob.glob(str(WORK / "monitor" / "option_closes.csv")) + glob.glob(str(WORK / "monitor" / "option_marks.csv")):
        try:
            m = pd.read_csv(f)
            m = m.rename(columns={"session": "date", "option_bid": "bid", "option_ask": "ask", "option_mid": "mid",
                                  "open_interest": "oi", "quote_time_utc": "quote_utc"})
            m["source"] = "monitor:" + Path(f).name
            rows += m.reindex(columns=["date", "ticker", "contract", "bid", "ask", "mid", "iv", "delta", "oi", "volume",
                                       "quote_utc", "source"]).to_dict("records")
        except Exception as e:
            print(f"WARNING: could not read {f}: {e}")
    pd.DataFrame(rows).to_csv(OUT / "option_marks.csv", index=False)
    print(f"{VERSION}: {len(tick)} tickers, {len(bars)} bars ({bars.trading_date.min()}..{bars.trading_date.max()}), "
          f"{len(rows)} option marks -> {OUT}")


if __name__ == "__main__":
    main()
