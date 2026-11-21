"""Export daily bars for the trade-card review (11 Nov 2026). Read-only on the price store.

PowerShell, from the repo root:
  venv\\Scripts\\python.exe tools\\export_card_bars.py
Writes data\\scratch\\workaround\\cards_review\\card_bars_<last session>.csv
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "canonical" / "historical_prices.sqlite"
OUT = ROOT / "data" / "scratch" / "workaround" / "cards_review"
TICKERS = ["EWG", "GME", "LWLG", "CDE", "ASO", "BKSY", "CAVA", "CBRL", "CPNG", "DQ", "D", "GO", "IFF", "LTC",
           "MMM", "NNE", "XLE", "OI", "BILI", "VALE", "VXX",
           "UUP", "XRT", "QQQ", "VIX", "^VIX", "XLP", "XLB", "NEE", "XLU", "KWEB", "XLY", "GDX", "SPY"]

with sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True) as con:
    q = ("SELECT ticker, trading_date, open, high, low, close, volume FROM ohlcv_daily "
         f"WHERE bar_status='COMPLETE' AND trading_date >= '2026-09-01' AND ticker IN ({','.join('?' * len(TICKERS))}) "
         "ORDER BY ticker, trading_date")
    df = pd.read_sql_query(q, con, params=TICKERS)
df = df.drop_duplicates(["ticker", "trading_date"])
OUT.mkdir(parents=True, exist_ok=True)
last = df["trading_date"].max()
path = OUT / f"card_bars_{last}.csv"
df.to_csv(path, index=False)
print(f"{len(df)} rows, {df['ticker'].nunique()} tickers, last session {last}")
print("Missing:", sorted(set(TICKERS) - set(df["ticker"])))
print(f"Saved {path}")
