"""Volatility lead on real option prices (pre-registration:
Enhancements/assessment/AVS_VOLATILITY_LEAD_REAL_PRICE_TEST_PREREGISTRATION_20260929.md). Read-only.

  venv\\Scripts\\python.exe Enhancements\\direction_evidence\\volatility_lead_real_price_test_20260929.py REPLAY_DIR OUT_DIR [WORKERS]
"""
from __future__ import annotations

import bisect
import sqlite3
import sys
import time
from datetime import date, timedelta
from multiprocessing import Pool
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.special import ndtr

ROOT = Path(__file__).resolve().parents[2]
PHANTOM = ROOT / "data" / "phantom" / "phantom_history.db"
PRICES = ROOT / "data" / "canonical" / "historical_prices.sqlite"
START = "2024-01-01"
HORIZONS = (28,)          # amended 29 Sep: snapshots hold expiries only up to 56 days
TYPES = {"ITM56": (40, 60, 56, 0.05), "ATM45": (30, 60, 45, 0.0)}
MAX_SPREAD = 0.35
RATE = 0.04
_FEATURES: dict = {}


def _init(features):
    global _FEATURES
    _FEATURES = features


def _bs(S, K, T, sig, call):
    T = max(T, 1e-6)
    d1 = (np.log(S / K) + (RATE + 0.5 * sig ** 2) * T) / (sig * np.sqrt(T))
    d2 = d1 - sig * np.sqrt(T)
    c = S * ndtr(d1) - K * np.exp(-RATE * T) * ndtr(d2)
    return float(c if call else c - S + K * np.exp(-RATE * T))


def _implied_vol(price, S, K, T, call):
    """Black-Scholes implied volatility by bisection; NaN when the price is outside no-arbitrage bounds."""
    lo, hi = 0.01, 5.0
    if not (price > 0 and S > 0 and K > 0 and T > 0):
        return np.nan
    if price < _bs(S, K, T, lo, call) or price > _bs(S, K, T, hi, call):
        return np.nan
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        if _bs(S, K, T, mid, call) > price:
            hi = mid
        else:
            lo = mid
    return 0.5 * (lo + hi)


def _worker(ticker):
    feats = _FEATURES.get(ticker)
    if not feats:
        return []
    con = sqlite3.connect(f"file:{PHANTOM.as_posix()}?mode=ro", uri=True, timeout=30)
    q = pd.read_sql_query(
        "SELECT quote_date, option_symbol, side, strike, dte, bid, ask, iv, underlying_price FROM chain_snapshots "
        "WHERE ticker = ? AND quote_date >= ? AND dte BETWEEN 1 AND 115", con, params=(ticker, START))
    con.close()
    if q.empty:
        return []
    for col in ("strike", "dte", "bid", "ask", "iv", "underlying_price"):
        q[col] = pd.to_numeric(q[col], errors="coerce")      # some tickers store missing values as NULL objects
    pc = sqlite3.connect(f"file:{PRICES.as_posix()}?mode=ro", uri=True)
    bars = pd.read_sql_query("SELECT trading_date d, close FROM ohlcv_daily WHERE ticker = ? AND trading_date >= ? "
                             "ORDER BY trading_date", pc, params=(ticker, "2023-10-01"))
    pc.close()
    closes = bars.set_index("d")["close"]
    lr = np.log(closes).diff()
    rv20 = (lr.rolling(20).std() * np.sqrt(252))
    q["side"] = q["side"].str.lower()
    by_date = {d: g for d, g in q.groupby("quote_date")}
    by_sym = {(d, s): r for d, s, r in zip(q["quote_date"], q["option_symbol"], q["bid"])}
    spot_by_date = q.groupby("quote_date")["underlying_price"].median().to_dict()
    dates = sorted(by_date)
    out = []
    for session, tercile, atr_rank in feats:
        i = bisect.bisect_right(dates, session)
        if i >= len(dates):
            continue
        d = dates[i]
        if (date.fromisoformat(d) - date.fromisoformat(session)).days > 7:
            continue
        chain = by_date[d]
        S = spot_by_date.get(d)
        if not S or not S > 0:
            continue
        rv = rv20.loc[:d].iloc[-1] if len(rv20.loc[:d]) else np.nan
        for tname, (dlo, dhi, dt, itm) in TYPES.items():
            for side in ("call", "put"):
                c = chain[(chain["side"] == side) & chain["dte"].between(dlo, dhi) & (chain["bid"] > 0) & (chain["ask"] > 0)]
                if c.empty:
                    continue
                c = c[c["dte"] == c.iloc[(c["dte"] - dt).abs().argsort()].iloc[0]["dte"]]
                target_k = S * (1 - itm) if side == "call" else S * (1 + itm)
                r = c.iloc[(c["strike"] - target_k).abs().argsort()].iloc[0]
                mid = (r["bid"] + r["ask"]) / 2
                if not mid > 0 or (r["ask"] - r["bid"]) / mid > MAX_SPREAD:
                    continue
                rec = {"ticker": ticker, "session": session, "entry_date": d, "atr_tercile": tercile,
                       "atr_rank": atr_rank, "type": tname, "side": side, "symbol": r["option_symbol"],
                       "strike": r["strike"], "dte": r["dte"], "spot": S, "ask": r["ask"], "bid": r["bid"],
                       "iv": r["iv"] if r["iv"] == r["iv"] and r["iv"] > 0 else _implied_vol(mid, S, r["strike"], r["dte"] / 365, side == "call"),
                       "iv_source": "SNAPSHOT" if r["iv"] == r["iv"] and r["iv"] > 0 else "INVERTED_FROM_MID",
                       "rv20": rv, "spread": (r["ask"] - r["bid"]) / mid}
                for H in HORIZONS:
                    lo = (date.fromisoformat(d) + timedelta(days=H)).isoformat()
                    hi = (date.fromisoformat(d) + timedelta(days=H + 10)).isoformat()
                    j = bisect.bisect_left(dates, lo)
                    exit_bid, exit_date, exit_spot = np.nan, None, np.nan
                    while j < len(dates) and dates[j] <= hi:
                        b = by_sym.get((dates[j], r["option_symbol"]))
                        if b is not None:
                            exit_bid, exit_date, exit_spot = b, dates[j], spot_by_date.get(dates[j], np.nan)
                            break
                        j += 1
                    rec[f"exit_date_{H}"] = exit_date
                    rec[f"real_ret_{H}"] = exit_bid / r["ask"] - 1 if exit_date else np.nan
                    if exit_date and rv == rv and rv > 0 and exit_spot == exit_spot:
                        sig = 1.1 * rv
                        m0 = _bs(S, r["strike"], r["dte"] / 365, sig, side == "call")
                        m1 = _bs(exit_spot, r["strike"], (r["dte"] - H) / 365, sig, side == "call")
                        rec[f"model_ret_{H}"] = (m1 * 0.97) / (m0 * 1.03) - 1 if m0 > 0 else np.nan
                    else:
                        rec[f"model_ret_{H}"] = np.nan
                out.append(rec)
    return out


def main():
    replay, out_dir = Path(sys.argv[1]), Path(sys.argv[2])
    workers = int(sys.argv[3]) if len(sys.argv) > 3 else 6
    rows = pd.read_parquet(replay / "replay_rows.parquet", columns=["ticker", "session", "x__atr_percentile_rank"])
    rows = rows[rows["session"] >= "2023-12-01"].dropna(subset=["x__atr_percentile_rank"])
    q = rows.groupby("session")["x__atr_percentile_rank"].rank(pct=True)
    rows["tercile"] = np.where(q <= 1 / 3, "CALM", np.where(q > 2 / 3, "VOLATILE", "MID"))
    feats = {t: list(zip(g["session"], g["tercile"], g["x__atr_percentile_rank"])) for t, g in rows.groupby("ticker")}
    print(f"tickers {len(feats)}, replay rows since Dec 2023: {len(rows)}", flush=True)
    started, recs = time.time(), []
    with Pool(workers, initializer=_init, initargs=(feats,)) as pool:
        for i, part in enumerate(pool.imap_unordered(_worker, sorted(feats), chunksize=2), 1):
            recs.extend(part)
            if i % 100 == 0:
                print(f"{i}/{len(feats)} tickers, {len(recs)} contracts, {time.time() - started:.0f}s", flush=True)
    out_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(recs).to_parquet(out_dir / "real_price_contracts.parquet", index=False)
    print(f"done: {len(recs)} contracts, {time.time() - started:.0f}s", flush=True)


if __name__ == "__main__":
    main()
