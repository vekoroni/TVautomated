"""Batch 1 of the scenario register (layers A/B, ACK 19 Sep 2026). Read-only research code.

Part A - IA-1 / IA-2 on U (exploration period ONLY, 2021-10-01 .. 2024-12-31; the 2025-2026 holdout stays sealed):
  pre-specified bar-derived features, point-in-time (rolling windows on past data only), cross-sectional Spearman
  information coefficient per date against
    - market-adjusted forward return (return minus the cross-sectional median) at h = 1, 2, 3, 5, 10, 20 sessions
    - magnitude surprise: |forward return| / (trailing 20-day realised volatility x sqrt(h/252)) - the historical
      proxy for "moved more than expected" (implied volatility is not available point-in-time before Sep 2025)
  Dates sampled every 5 sessions; t-statistic = mean IC / std IC x sqrt(n dates) (overlap inflates t for h > 5).
  Tradeable universe: close > $5 and 20-day average dollar volume > $5m.
Part B - IA-3 on H: realised move / real implied move (ATM IV from the restored IV cache on the book session)
  for the universe, all candidates, the top cautious quintile and tickets, at h = 1, 3, 5.
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))
HERE = Path(__file__).resolve().parent
PRICES = REPO / "data" / "canonical" / "historical_prices.sqlite"
IV_CACHE = REPO / "data" / "cache" / "iv_history_cache.db"
ROWS = REPO / "Enhancements" / "backtest" / "signal_ticket_backtest_rows.csv"
EXPLORE_FROM, EXPLORE_TO = "2021-10-01", "2024-12-31"
HORIZONS = (1, 2, 3, 5, 10, 20)


def load_wide(start: str, end: str) -> dict[str, pd.DataFrame]:
    con = sqlite3.connect(f"file:{PRICES.as_posix()}?mode=ro", uri=True)
    frame = pd.read_sql_query(
        "SELECT ticker, trading_date, high, low, close, volume FROM ohlcv_daily "
        "WHERE trading_date >= ? AND trading_date <= ?", con, params=(start, end))
    con.close()
    return {f: frame.pivot_table(index="trading_date", columns="ticker", values=f, aggfunc="last").sort_index()
            .astype("float32") for f in ("high", "low", "close", "volume")}


def rolling_rank(frame: pd.DataFrame, window: int) -> pd.DataFrame:
    return frame.rolling(window, min_periods=60).rank(pct=True)


def features(w: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    close, high, low, vol = w["close"], w["high"], w["low"], w["volume"]
    prev = close.shift(1)
    tr = pd.concat([(high - low).stack(), (high - prev).abs().stack(), (low - prev).abs().stack()], axis=1).max(axis=1).unstack()
    atr_pct = tr.ewm(span=14, adjust=False).mean() / close
    bb = 4 * close.rolling(20).std() / close.rolling(20).mean()
    ret5, ret20 = close / close.shift(5) - 1, close / close.shift(20) - 1
    spy20 = ret20["SPY"] if "SPY" in ret20 else ret20.median(axis=1)
    atr_rank, bb_rank = rolling_rank(atr_pct, 252), rolling_rank(bb, 252)
    return {
        "atr_rank_252": atr_rank,
        "bb_rank_252": bb_rank,
        "compression_score": -(atr_rank + bb_rank),            # higher = more compressed
        "ret_5d": ret5,
        "ret_20d": ret20,
        "rs_vs_spy_20d": ret20.sub(spy20, axis=0),
        "volume_ratio_20d": vol / vol.rolling(20).mean().shift(1),
        "dist_52w_low": close / close.rolling(252, min_periods=120).min() - 1,
        "dist_52w_high": close / close.rolling(252, min_periods=120).max() - 1,
    }


def ic_series(feature: pd.DataFrame, outcome: pd.DataFrame, dates) -> pd.Series:
    f = feature.loc[dates].rank(axis=1)
    o = outcome.loc[dates].rank(axis=1)
    mask = f.notna() & o.notna()
    f, o = f.where(mask), o.where(mask)
    fc, oc = f.sub(f.mean(axis=1), axis=0), o.sub(o.mean(axis=1), axis=0)
    num = (fc * oc).sum(axis=1)
    den = np.sqrt((fc ** 2).sum(axis=1) * (oc ** 2).sum(axis=1))
    return (num / den).where(mask.sum(axis=1) >= 100)


def part_a() -> dict:
    w = load_wide("2020-09-01", "2025-02-15")                  # warm-up before, forward window after exploration
    close = w["close"]
    dollar = (close * w["volume"]).rolling(20).mean()
    tradeable = (close > 5) & (dollar > 5e6)
    feats = {k: v.where(tradeable) for k, v in features(w).items()}
    logret = np.log(close / close.shift(1))
    rv20 = logret.rolling(20).std() * np.sqrt(252)
    dates = [d for d in close.index if EXPLORE_FROM <= d <= EXPLORE_TO][::5]
    out = {"period": [EXPLORE_FROM, EXPLORE_TO], "dates_sampled": len(dates), "features": {}}
    for h in HORIZONS:
        fwd = close.shift(-h) / close - 1
        adj = fwd.sub(fwd.median(axis=1), axis=0)
        surprise = fwd.abs() / (rv20 * np.sqrt(h / 252))
        for name, feat in feats.items():
            for label, outcome in (("direction", adj), ("magnitude", surprise)):
                s = ic_series(feat, outcome.where(tradeable), dates).dropna()
                out["features"].setdefault(name, {}).setdefault(label, {})[h] = {
                    "mean_ic": round(float(s.mean()), 4), "t": round(float(s.mean() / s.std() * np.sqrt(len(s))), 2),
                    "share_positive": round(float((s > 0).mean()), 3), "n_dates": int(len(s))}
    return out


def part_b() -> dict:
    rows = pd.read_csv(ROWS, low_memory=False)
    rows["is_ticket"] = rows["ticket"].astype(str).isin(["True", "true", "1"])
    rows["q"] = rows.groupby("session")["cautious"].transform(lambda x: pd.qcut(x.rank(method="first"), 5, labels=False))
    sessions = sorted(rows["session"].unique())
    w = load_wide("2026-08-01", "2026-09-18")
    close = w["close"]
    cache = sqlite3.connect(f"file:{IV_CACHE.as_posix()}?mode=ro", uri=True)
    iv = pd.read_sql_query("SELECT ticker, sample_date, atm_iv FROM iv_history WHERE sample_date >= '2026-08-28'", cache)
    cache.close()
    iv = iv.pivot_table(index="sample_date", columns="ticker", values="atm_iv", aggfunc="last")
    idx = list(close.index)
    res = {}
    for h in (1, 3, 5):
        groups = {"universe": [], "candidates": [], "top_quintile": [], "tickets": []}
        for s in sessions:
            if s not in idx or s not in iv.index or idx.index(s) + h >= len(idx):
                continue
            end = idx[idx.index(s) + h]
            move = (close.loc[end] / close.loc[s] - 1).abs()
            implied = iv.loc[s] * np.sqrt(h / 252)
            ratio = (move / implied).replace([np.inf, -np.inf], np.nan).dropna()
            ratio = ratio[(ratio < 20) & (move < 1)]
            groups["universe"].append(ratio)
            sub = rows[rows["session"] == s]
            for g, sel in (("candidates", sub), ("top_quintile", sub[sub["q"] == 4]), ("tickets", sub[sub["is_ticket"]])):
                groups[g].append(ratio.reindex(sel["ticker"]).dropna())
        res[h] = {g: {"n": int(sum(len(x) for x in v)),
                      "median_realised_over_implied": round(float(pd.concat(v).median()), 3) if v else None,
                      "mean_realised_over_implied": round(float(pd.concat(v).mean()), 3) if v else None,
                      "share_moved_more_than_priced": round(float((pd.concat(v) > 1).mean()), 3) if v else None}
                  for g, v in groups.items()}
    return res


def main() -> int:
    report = {"IA3_H": part_b()}
    print(json.dumps(report, indent=1))
    report["IA1_IA2_U_exploration"] = part_a()
    (HERE / "ia1_ia3_premises.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    print("written")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
