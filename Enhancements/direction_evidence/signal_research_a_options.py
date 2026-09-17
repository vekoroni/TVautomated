"""Signal research plan A — options-based hypotheses O1-O5 (read-only; pre-registered in SIGNAL_RESEARCH_PLAN_A.md).

Source: phantom `options_greeks_history` (per-contract IV / delta, weekly snapshots Aug 2025 -> Sep 2026; computed
Black-Scholes IV unless provider values exist). Per ticker and snapshot date:
  O1  skew = median IV of puts |delta| 0.20-0.30 minus median IV of calls |delta| 0.40-0.60 (20-45 DTE)   expected -
  O2  call-put IV spread: mean (call IV - put IV) over same strike and expiry pairs, calls |delta| 0.35-0.65
      (20-45 DTE)                                                                                          expected +
  O3  ATM IV (calls and puts |delta| 0.40-0.60, 20-45 DTE) minus EWMA(0.94) realised forecast (annualised,
      price store, point-in-time)                                                                          expected -
  O4  put / call open-interest ratio over the stored chain (7-60 DTE)                                     expected -
  O5  change in ATM IV since the ticker's previous snapshot (5-9 calendar days earlier)                   expected -
Forward log returns 5 / 10 / 20 sessions from the snapshot-date close, net of the date's cross-sectional median.
Single period: Newey-West t, first vs second half of dates, BH q = 0.10 across O x horizon, partial IC controlling
for past 5-session return, economic size (top-bottom quintile 10-session net return vs median share spread).
Exploratory: any pass needs confirmation on forward sessions (plan A).
"""

from __future__ import annotations

import json
import math
from multiprocessing import Pool
from pathlib import Path
import sqlite3
import time

import numpy as np
import pandas as pd
from scipy import stats

ROOT = Path(__file__).resolve().parents[2]
CHAINS = ROOT / "data" / "phantom" / "phantom_history.db"
PRICES = ROOT / "data" / "canonical" / "historical_prices.sqlite"
OUT = Path(__file__).resolve().parent
HORIZONS = (5, 10, 20)
EXPECTED = {"O1": -1, "O2": 1, "O3": -1, "O4": -1, "O5": -1}
MIN_CROSS_SECTION = 100
WORKERS = 4


def _features(ticker: str):
    con = sqlite3.connect(f"file:{CHAINS.as_posix()}?mode=ro", uri=True)
    g = pd.read_sql_query(
        "SELECT snapshot_date, expiration_date, strike, dte, side, iv, delta, open_interest FROM options_greeks_history "
        "WHERE ticker = ? AND quality_status LIKE 'OK%' AND iv > 0 AND dte BETWEEN 7 AND 60", con, params=(ticker,))
    con.close()
    if g.empty:
        return []
    g["side"] = g["side"].str.lower()
    g["ad"] = g["delta"].abs()
    rows = []
    for day, d in g.groupby("snapshot_date"):
        tenor = d[(d["dte"] >= 20) & (d["dte"] <= 45)]
        calls, puts = tenor[tenor["side"] == "call"], tenor[tenor["side"] == "put"]
        atm_call = calls[(calls["ad"] >= 0.40) & (calls["ad"] <= 0.60)]["iv"]
        atm_put = puts[(puts["ad"] >= 0.40) & (puts["ad"] <= 0.60)]["iv"]
        put25 = puts[(puts["ad"] >= 0.20) & (puts["ad"] <= 0.30)]["iv"]
        row = {"ticker": ticker, "date": day}
        if len(put25) and len(atm_call):
            row["O1"] = float(put25.median() - atm_call.median())
        near = calls[(calls["ad"] >= 0.35) & (calls["ad"] <= 0.65)][["expiration_date", "strike", "iv"]]
        pairs = near.merge(puts[["expiration_date", "strike", "iv"]], on=["expiration_date", "strike"], suffixes=("_c", "_p"))
        if len(pairs):
            row["O2"] = float((pairs["iv_c"] - pairs["iv_p"]).mean())
        atm = pd.concat([atm_call, atm_put])
        if len(atm):
            row["atm_iv"] = float(atm.median())
        oi_calls = d.loc[d["side"] == "call", "open_interest"].sum()
        oi_puts = d.loc[d["side"] == "put", "open_interest"].sum()
        if oi_calls > 0:
            row["O4"] = float(oi_puts / oi_calls)
        rows.append(row)
    return rows


def newey_west_t(x, lag):
    x = np.asarray(x, dtype=float)
    x = x[np.isfinite(x)]
    n = len(x)
    if n < 8:
        return float("nan")
    d = x - x.mean()
    var = (d @ d) / n
    for k in range(1, lag + 1):
        var += 2 * (1 - k / (lag + 1)) * (d[k:] @ d[:-k]) / n
    return float(x.mean() / math.sqrt(var / n)) if var > 0 else float("nan")


def main():
    started = time.time()
    pc = sqlite3.connect(f"file:{PRICES.as_posix()}?mode=ro", uri=True)
    cc = sqlite3.connect(f"file:{CHAINS.as_posix()}?mode=ro", uri=True)
    chain_tickers = {r[0] for r in cc.execute("SELECT DISTINCT ticker FROM backfill_audit WHERE status = 'OK'")}
    cc.close()
    price_tickers = {r[0] for r in pc.execute("SELECT ticker FROM ohlcv_daily WHERE bar_status='COMPLETE' GROUP BY ticker HAVING COUNT(*) >= 120")}
    tickers = sorted(chain_tickers & price_tickers)
    print(f"tickers {len(tickers)}", flush=True)
    rows = []
    with Pool(WORKERS) as pool:
        for i, part in enumerate(pool.imap_unordered(_features, tickers, chunksize=8), 1):
            rows.extend(part)
            if i % 250 == 0:
                print(f"{i}/{len(tickers)} tickers, {len(rows)} rows, {time.time() - started:.0f}s", flush=True)
    feats = pd.DataFrame(rows)
    feats = feats[pd.to_datetime(feats["date"]).dt.dayofweek < 5]
    # O5: change in ATM IV vs the previous snapshot 5-9 calendar days earlier
    feats = feats.sort_values(["ticker", "date"])
    feats["prev_date"] = feats.groupby("ticker")["date"].shift(1)
    feats["prev_iv"] = feats.groupby("ticker")["atm_iv"].shift(1)
    gap = (pd.to_datetime(feats["date"]) - pd.to_datetime(feats["prev_date"])).dt.days
    feats["O5"] = np.where(gap.between(5, 9), feats["atm_iv"] - feats["prev_iv"], np.nan)

    # prices: forward returns, EWMA forecast (O3), past 5-session return, share spread, DQ-12 and liquidity
    px = pd.read_sql_query("SELECT ticker, trading_date, high, low, close, volume FROM ohlcv_daily WHERE bar_status='COMPLETE' "
                           "AND trading_date >= '2024-06-01'", pc)
    pc.close()
    close = px.pivot(index="trading_date", columns="ticker", values="close").sort_index()
    high = px.pivot(index="trading_date", columns="ticker", values="high").reindex(close.index)
    low = px.pivot(index="trading_date", columns="ticker", values="low").reindex(close.index)
    vol = px.pivot(index="trading_date", columns="ticker", values="volume").reindex(close.index)
    logc = np.log(close.where(close > 0))
    r1 = logc.diff()
    ewma = np.sqrt((r1 ** 2).ewm(alpha=0.06, adjust=False).mean()) * math.sqrt(252)
    past5 = logc - logc.shift(5)
    bad = ((r1.abs() >= math.log(10)) | (close < 0.01)).astype(float)
    clean = (bad.rolling(121, min_periods=1).max() < 1) & (bad[::-1].rolling(21, min_periods=1).max()[::-1] < 1)
    liquid = (close * vol).rolling(20, min_periods=15).median() >= 5_000_000
    eta = (np.log(high) + np.log(low)) / 2
    spread = np.sqrt((4 * ((logc - eta) * (logc - eta.shift(-1))).shift(1).rolling(60, min_periods=20).mean()).clip(lower=0))

    def lookup(frame, key):
        stacked = frame.stack()
        stacked.index.names = ["date", "ticker"]
        return stacked.rename(key)

    base = feats.set_index(["date", "ticker"])
    for key, frame in (("ewma", ewma), ("past5", past5), ("clean", clean.astype(float)), ("liquid", liquid.astype(float)),
                       ("spread", spread)):
        base = base.join(lookup(frame, key), how="left")
    for h in HORIZONS:
        base = base.join(lookup(logc.shift(-h) - logc, f"fwd_{h}"), how="left")
    base["O3"] = base["atm_iv"] - base["ewma"]
    data = base.reset_index()
    data = data[(data["clean"] == 1) & (data["liquid"] == 1)]
    data.to_parquet(OUT / "signal_research_a_options_rows.parquet", index=False)

    records = []
    for day, g in data.groupby("date"):
        for h in HORIZONS:
            y = g[f"fwd_{h}"]
            if y.notna().sum() < MIN_CROSS_SECTION:
                continue
            net = y - y.median()
            for name in EXPECTED:
                ok = g[name].notna() & net.notna()
                if ok.sum() < MIN_CROSS_SECTION or g.loc[ok, name].nunique() < 3:
                    continue
                x, yy = g.loc[ok, name], net[ok]
                ic = stats.spearmanr(x, yy).statistic
                q = pd.qcut(x.rank(method="first"), 5, labels=False)
                okc = ok & g["past5"].notna()
                partial = np.nan
                if okc.sum() >= MIN_CROSS_SECTION:
                    rc = g.loc[okc, "past5"].rank()
                    rx, ry = g.loc[okc, name].rank(), net[okc].rank()
                    bx, by = np.polyfit(rc, rx, 1), np.polyfit(rc, ry, 1)
                    partial = stats.spearmanr(rx - (bx[0] * rc + bx[1]), ry - (by[0] * rc + by[1])).statistic
                records.append({"date": day, "signal": name, "horizon": h, "ic": ic, "partial": partial, "n": int(ok.sum()),
                                "top_bottom": float(yy[q == 4].mean() - yy[q == 0].mean()),
                                "spread": float(g.loc[ok, "spread"][(q == 4) | (q == 0)].median())})
    ic = pd.DataFrame(records)
    ic.to_csv(OUT / "signal_research_a_options_per_date.csv", index=False)
    rows = []
    for (name, h), g in ic.groupby(["signal", "horizon"]):
        g = g.sort_values("date")
        lag = max(0, math.ceil(h / 5) - 1)
        half = len(g) // 2
        es = EXPECTED[name]
        rows.append({"signal": name, "horizon": h, "expected_sign": es, "dates": len(g), "first_date": g["date"].iloc[0],
                     "last_date": g["date"].iloc[-1], "median_names": int(g["n"].median()), "ic": float(g["ic"].mean()),
                     "t": newey_west_t(g["ic"], lag), "expected_sign_share": float((np.sign(g["ic"]) == es).mean()),
                     "first_half_ic": float(g["ic"].iloc[:half].mean()), "second_half_ic": float(g["ic"].iloc[half:].mean()),
                     "partial_ic": float(g["partial"].mean()), "partial_t": newey_west_t(g["partial"], lag),
                     "top_bottom_net": float(g["top_bottom"].mean()), "median_share_spread": float(g["spread"].median())})
    sm = pd.DataFrame(rows)
    sm["p"] = [2 * stats.norm.sf(abs(t)) if np.isfinite(t) else 1.0 for t in sm["t"]]
    order = sm["p"].sort_values().index
    m = len(sm)
    passed = sm.loc[order, "p"].to_numpy() <= 0.10 * np.arange(1, m + 1) / m
    k = np.max(np.nonzero(passed)[0]) + 1 if passed.any() else 0
    sm["fdr"] = False
    sm.loc[order[:k], "fdr"] = True
    es = sm["expected_sign"]
    sm["expected_sign_and_t"] = (np.sign(sm["ic"]) == es) & (sm["t"].abs() >= 2.0)
    sm["stable_halves"] = (np.sign(sm["first_half_ic"]) == es) & (np.sign(sm["second_half_ic"]) == es)
    sm["not_reversal"] = (np.sign(sm["partial_ic"]) == es) & (sm["partial_t"].abs() >= 2.0)
    sm["economic_10d"] = (sm["horizon"] == 10) & ((sm["top_bottom_net"] * es) > sm["median_share_spread"])
    sm["exploratory_pass"] = sm["expected_sign_and_t"] & sm["fdr"] & sm["stable_halves"] & sm["not_reversal"]
    sm.to_csv(OUT / "signal_research_a_options_summary.csv", index=False)
    (OUT / "signal_research_a_options_summary.json").write_text(sm.to_json(orient="records", indent=2), encoding="utf-8")
    print(f"feature rows {len(feats)}, evaluated rows {len(data)}, dates {ic['date'].nunique()}, {time.time() - started:.0f}s")
    print(sm.drop(columns=["first_date", "last_date"]).round(4).to_string(index=False))


if __name__ == "__main__":
    main()
