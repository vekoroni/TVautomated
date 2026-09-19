"""IA-3 on the weekly-chain year (scenario register layer B, ACK 19 Sep 2026). Read-only research code.

Question: in which states does a stock realise MORE movement than its options price?
For every ticker on every Friday sample in the IV cache (Sep 2025 - Aug 2026; ATM IV derived from Phantom's stored
chains), realised forward return over h = 1 / 3 / 5 / 10 sessions from the price store, against the implied move
ATM_IV x sqrt(h / 252). Measures per state bucket:
  variance ratio = mean(ret^2) / mean(implied^2)   (1.0 = fairly priced on average; > 1 options underpriced)
  median |ret| / implied                           (0.674 is the fair median for a normal move)
  share |ret| > implied                             (0.317 fair)
States (point-in-time at the sample date): compression score quintile (ATR + Bollinger ranks, 252 bars), 20-day
volume-ratio quintile, true IV percentile tercile (>= 20 prior samples), and IV / trailing 20-day realised vol
quintile. Reported for the whole year and for each half separately (stability).
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
PRICES = REPO / "data" / "canonical" / "historical_prices.sqlite"
IV_CACHE = REPO / "data" / "cache" / "iv_history_cache.db"
HORIZONS = (1, 3, 5, 10)
START, END = "2025-09-18", "2026-09-04"


def main() -> int:
    con = sqlite3.connect(f"file:{PRICES.as_posix()}?mode=ro", uri=True)
    px = pd.read_sql_query("SELECT ticker, trading_date, high, low, close, volume FROM ohlcv_daily "
                           "WHERE trading_date >= '2024-08-01' AND trading_date <= '2026-09-18'", con)
    con.close()
    w = {k: px.pivot_table(index="trading_date", columns="ticker", values=k, aggfunc="last").sort_index()
         for k in ("high", "low", "close", "volume")}
    close, high, low, vol = w["close"], w["high"], w["low"], w["volume"]
    prev = close.shift(1)
    tr = np.maximum(high - low, np.maximum((high - prev).abs(), (low - prev).abs()))
    atr_rank = (tr.ewm(span=14, adjust=False).mean() / close).rolling(252, min_periods=60).rank(pct=True)
    bb_rank = (4 * close.rolling(20).std() / close.rolling(20).mean()).rolling(252, min_periods=60).rank(pct=True)
    compression = -(atr_rank + bb_rank)
    vratio = vol / vol.rolling(20).mean().shift(1)
    rv20 = np.log(close / prev).rolling(20).std() * np.sqrt(252)
    dollar = (close * vol).rolling(20).mean()

    cache = sqlite3.connect(f"file:{IV_CACHE.as_posix()}?mode=ro", uri=True)
    iv = pd.read_sql_query("SELECT ticker, sample_date, atm_iv FROM iv_history WHERE atm_iv > 0.01 AND atm_iv < 5", cache)
    cache.close()
    iv = iv.sort_values(["ticker", "sample_date"])
    iv["prior_n"] = iv.groupby("ticker").cumcount()
    iv["iv_pctile"] = iv.groupby("ticker")["atm_iv"].transform(
        lambda s: s.expanding().apply(lambda x: (x[:-1] < x[-1]).mean() if len(x) > 1 else np.nan, raw=True))
    iv.loc[iv.prior_n < 20, "iv_pctile"] = np.nan
    iv = iv[(iv.sample_date >= START) & (iv.sample_date <= END) & iv.sample_date.isin(close.index)]
    idx = {d: i for i, d in enumerate(close.index)}
    records = []
    for d, g in iv.groupby("sample_date"):
        i = idx[d]
        tick = [t for t in g.ticker if t in close.columns]
        g = g.set_index("ticker").loc[tick]
        base = pd.DataFrame({"iv": g.atm_iv, "iv_pctile": g.iv_pctile,
                             "compression": compression.loc[d, tick], "vratio": vratio.loc[d, tick],
                             "iv_over_rv": g.atm_iv / rv20.loc[d, tick], "close": close.loc[d, tick],
                             "dollar": dollar.loc[d, tick]})
        base = base[(base.close > 5) & (base.dollar > 5e6)]
        for h in HORIZONS:
            if i + h >= len(close.index):
                continue
            ret = close.iloc[i + h][base.index] / base.close - 1
            f = base.assign(h=h, ret=ret, implied=base.iv * np.sqrt(h / 252.0), date=d).dropna(subset=["ret"])
            records.append(f[f.ret.abs() < 1.0].reset_index().rename(columns={"index": "ticker"}))
    data = pd.concat(records)
    for col, q in (("compression", 5), ("vratio", 5), ("iv_over_rv", 5)):
        data[f"{col}_q"] = data.groupby(["date", "h"])[col].transform(
            lambda s: pd.qcut(s.rank(method="first"), q, labels=False) if s.notna().sum() >= q else np.nan)
    data["iv_pctile_t"] = pd.cut(data.iv_pctile, [-0.01, 1 / 3, 2 / 3, 1.01], labels=[0, 1, 2]).astype(float)
    mid = sorted(data.date.unique())[len(data.date.unique()) // 2]

    def measure(frame):
        if len(frame) < 200:
            return None
        return {"n": int(len(frame)),
                "variance_ratio": round(float((frame.ret ** 2).mean() / (frame.implied ** 2).mean()), 3),
                "median_abs_over_implied": round(float((frame.ret.abs() / frame.implied).median()), 3),
                "share_beyond_implied": round(float((frame.ret.abs() > frame.implied).mean()), 3)}

    report = {"period": [START, END], "samples": int(data.date.nunique()), "rows": int(len(data)), "horizons": {}}
    for h in HORIZONS:
        dh = data[data.h == h]
        entry = {"all": measure(dh), "first_half": measure(dh[dh.date < mid]), "second_half": measure(dh[dh.date >= mid])}
        for state in ("compression_q", "vratio_q", "iv_over_rv_q", "iv_pctile_t"):
            entry[state] = {}
            for b, g in dh.groupby(state):
                entry[state][int(b)] = {"all": measure(g), "first_half": measure(g[g.date < mid]),
                                        "second_half": measure(g[g.date >= mid])}
        report["horizons"][h] = entry
    (HERE / "ia3_weekly_chain_year.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(json.dumps({"samples": report["samples"], "rows": report["rows"]}))
    for h, e in report["horizons"].items():
        print(f"\n=== h {h} all {e['all']}")
        for state in ("compression_q", "vratio_q", "iv_over_rv_q", "iv_pctile_t"):
            print(" ", state, {b: (v["all"]["variance_ratio"], v["first_half"]["variance_ratio"] if v["first_half"] else None,
                                   v["second_half"]["variance_ratio"] if v["second_half"] else None)
                               for b, v in e[state].items() if v["all"]})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
