"""Layer 3 forecast floor (5%) / cap (250%) evidence study (read-only, V5, 17 Sep 2026).

Runs the production path `layer3_forward_variance.compute_forward_variance` (regime '') on every ticker in
the canonical price store, every 20th session since 2022-01-01, on a 252-bar window (the runner's
PRICE_BARS), with the clipping disabled so the raw model output is seen. The clipped value is
min(max(raw, VOL_FLOOR), VOL_CAP) (both clip sites are idempotent; checked on a sample below).
Each forecast is scored against the close-to-close volatility delivered over the next 20 sessions.

  venv\\Scripts\\python.exe Enhancements\\expression_forensics\\vol_floor_cap_study.py

Writes vol_floor_cap_study.json next to this file. Never writes to data/, never calls a provider.
"""

from __future__ import annotations

import json
import logging
import math
from pathlib import Path
import sqlite3
import sys

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
CODE = HERE.parents[1]                      # repo (worktree) containing layer3_forward_variance.py
MAIN = Path(r"C:\Users\ACKVerissimo\AVSHUNTER-Intelligence")
sys.path.insert(0, str(CODE))
logging.disable(logging.WARNING)
import layer3_forward_variance as l3  # noqa: E402

PRICES = MAIN / "data" / "canonical" / "historical_prices.sqlite"
OUT = HERE / "vol_floor_cap_study.json"
HORIZON, STEP, START, BARS = 20, 20, "2022-01-01", 252
FLOOR, CAP = 0.05, 2.50


class _NoClipNumpy:
    """numpy proxy for the l3 module whose clip returns its input (raw model output)."""

    def __getattr__(self, name):
        return getattr(np, name)

    @staticmethod
    def clip(a, lo, hi):
        return a


def qlike(forecast, delivered):
    x = (delivered ** 2) / (forecast ** 2)
    return x - math.log(x) - 1


def _clip(v):
    return min(max(v, FLOOR), CAP)


def main():
    con = sqlite3.connect(f"file:{PRICES.as_posix()}?mode=ro", uri=True)
    tickers = [r[0] for r in con.execute("SELECT DISTINCT ticker FROM ohlcv_daily WHERE bar_status='COMPLETE'")]
    rows, checked = [], 0
    for ticker in tickers:
        frame = pd.read_sql_query(
            "SELECT trading_date, open, high, low, close FROM ohlcv_daily WHERE ticker = ? "
            "AND bar_status = 'COMPLETE' ORDER BY trading_date", con, params=(ticker,))
        frame = frame[frame["close"] > 0].reset_index(drop=True)
        r = np.log(frame["close"] / frame["close"].shift(1))
        for i in range(BARS - 1, len(frame) - HORIZON, STEP):
            if frame.loc[i, "trading_date"] < START:
                continue
            fwd = r.iloc[i + 1:i + 1 + HORIZON]
            delivered = math.sqrt(float((fwd ** 2).mean())) * math.sqrt(252)
            window = frame.iloc[i - BARS + 1:i + 1]
            l3.np = _NoClipNumpy()
            try:
                raw = l3.compute_forward_variance(ticker, window, implied_vol=None, regime="")
            finally:
                l3.np = np
            if raw.forward_realised_vol is None:
                continue
            rv = float(raw.forward_realised_vol)
            if checked < 200 and (rv < FLOOR or rv > CAP or checked < 50):
                clipped = l3.compute_forward_variance(ticker, window, implied_vol=None, regime="")
                assert abs(clipped.forward_realised_vol - _clip(rv)) < 1e-9, (ticker, rv, clipped.forward_realised_vol)
                checked += 1
            hist = r.iloc[i - BARS + 2:i + 1]
            rows.append({
                "ticker": ticker, "date": frame.loc[i, "trading_date"], "method": raw.method,
                "raw": rv, "clipped": _clip(rv), "delivered": delivered,
                "hist_zero_return_share": float((hist == 0).mean()),
                "fwd_zero_return_share": float((fwd == 0).mean()),
                "hist_realised": float(math.sqrt(float((hist ** 2).mean())) * math.sqrt(252)),
            })
    df = pd.DataFrame(rows)
    out = {"n": int(len(df)), "tickers": int(df["ticker"].nunique()), "clip_checks": checked,
           "methods": df["method"].value_counts().to_dict(), "floor": FLOOR, "cap": CAP}

    def score(sub):
        ok = sub[sub["delivered"] > 0]
        res = {"n": int(len(sub)), "n_delivered_zero": int((sub["delivered"] <= 0).sum()),
               "tickers": int(sub["ticker"].nunique())}
        if len(sub):
            res.update({
                "raw_quantiles": sub["raw"].quantile([0, .1, .5, .9, 1]).round(4).tolist(),
                "delivered_quantiles": sub["delivered"].quantile([0, .1, .5, .9, 1]).round(4).tolist(),
                "hist_realised_quantiles": sub["hist_realised"].quantile([0, .1, .5, .9, 1]).round(4).tolist(),
                "median_hist_zero_return_share": float(sub["hist_zero_return_share"].median()),
                "median_fwd_zero_return_share": float(sub["fwd_zero_return_share"].median()),
                "share_delivered_below_floor": float((sub["delivered"] < FLOOR).mean()),
                "share_delivered_above_cap": float((sub["delivered"] > CAP).mean()),
                "examples": sub.sort_values("raw").head(5)[["ticker", "date", "raw", "delivered"]]
                .round(4).to_dict("records") + sub.sort_values("raw").tail(5)[["ticker", "date", "raw", "delivered"]]
                .round(4).to_dict("records"),
            })
        if len(ok):
            for name in ("raw", "clipped"):
                lr = np.log(ok[name] / ok["delivered"])
                res[name] = {"qlike_mean": float(np.mean([qlike(f, d) for f, d in zip(ok[name], ok["delivered"])])),
                             "qlike_median": float(np.median([qlike(f, d) for f, d in zip(ok[name], ok["delivered"])])),
                             "mean_abs_log": float(lr.abs().mean()), "median_log_ratio": float(lr.median())}
            res["clipped_closer_share"] = float(
                (np.abs(np.log(ok["clipped"] / ok["delivered"])) < np.abs(np.log(ok["raw"] / ok["delivered"]))).mean())
        return res

    out["below_floor"] = score(df[df["raw"] < FLOOR])
    out["above_cap"] = score(df[df["raw"] > CAP])
    out["all"] = score(df)
    out["share_below_floor"] = float((df["raw"] < FLOOR).mean())
    out["share_above_cap"] = float((df["raw"] > CAP).mean())
    out["near_bounds"] = {"raw_below_0.10": int((df["raw"] < 0.10).sum()), "raw_above_1.50": int((df["raw"] > 1.5).sum())}
    OUT.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print(json.dumps(out, indent=1, default=str))


if __name__ == "__main__":
    main()
