"""Volatility forecast study (read-only): which realised-volatility forecast predicts delivered volatility?

For every ticker in the canonical price store and every 5th session (non-overlapping-ish evaluation
points, 2022-01 → last session minus 20), compute point-in-time forecasts from bars up to the evaluation
session and compare them with the volatility delivered over the next h sessions (h = 5, 10, 20;
zero-mean root-mean-square of daily log returns).

Forecasts: close-to-close, Parkinson, Garman-Klass, Yang-Zhang over 10 / 20 / 60 sessions; EWMA (0.94).
Metrics per forecast and horizon: median log(forecast / delivered) (bias), mean |log ratio|, QLIKE.
Rolling pandas implementations are checked against the pure estimators in contracts/realised_volatility.py.

  venv\\Scripts\\python.exe Enhancements\\expression_forensics\\volatility_forecast_study.py
"""

from __future__ import annotations

import json
import math
from pathlib import Path
import sqlite3
import sys

import numpy as np
import pandas as pd

WORKTREE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(WORKTREE))
from contracts import realised_volatility as rv  # noqa: E402

PRICES = Path(r"C:\Users\ACKVerissimo\AVSHUNTER-Intelligence\data\canonical\historical_prices.sqlite")
OUT = Path(__file__).resolve().parent
HORIZONS = (5, 10, 20)
WINDOWS = (10, 20, 60)
EVAL_STEP = 5
START = "2022-01-01"
LN2 = math.log(2.0)


def forecasts(frame: pd.DataFrame) -> pd.DataFrame:
    o, h, l, c = (frame[k] for k in ("open", "high", "low", "close"))
    prev = c.shift(1)
    r = np.log(c / prev)
    hl2 = np.log(h / l) ** 2
    co2 = np.log(c / o) ** 2
    overnight = np.log(o / prev)
    open_close = np.log(c / o)
    rs = np.log(h / c) * np.log(h / o) + np.log(l / c) * np.log(l / o)
    out = {}
    for w in WINDOWS:
        out[f"cc_{w}"] = r.rolling(w).std()
        out[f"park_{w}"] = np.sqrt(hl2.rolling(w).mean() / (4 * LN2))
        out[f"gk_{w}"] = np.sqrt((0.5 * hl2 - (2 * LN2 - 1) * co2).rolling(w).mean().clip(lower=0))
        k = rv.YZ_ALPHA / (rv.YZ_BETA + (w + 1) / (w - 1))
        out[f"yz_{w}"] = np.sqrt((overnight.rolling(w).var() + k * open_close.rolling(w).var()
                                  + (1 - k) * rs.rolling(w).mean()).clip(lower=0))
    out["ewma_094"] = np.sqrt((r ** 2).ewm(alpha=1 - 0.94, adjust=False).mean())
    for hz in HORIZONS:
        future_sq = (r ** 2).shift(-1).rolling(hz).mean().shift(-(hz - 1))
        out[f"delivered_{hz}"] = np.sqrt(future_sq)
        out[f"max_abs_future_{hz}"] = r.abs().shift(-1).rolling(hz).max().shift(-(hz - 1))
    return pd.DataFrame(out, index=frame.index)


def self_check(frame: pd.DataFrame, table: pd.DataFrame) -> dict:
    i = len(frame) - 30
    window = frame.iloc[i - 19:i + 1]
    prev_close = frame["close"].iloc[i - 20:i].tolist()
    checks = {
        "cc_20": (table["cc_20"].iloc[i], rv.close_to_close(frame["close"].iloc[i - 20:i + 1].tolist())),
        "park_20": (table["park_20"].iloc[i], rv.parkinson(window["high"].tolist(), window["low"].tolist())),
        "gk_20": (table["gk_20"].iloc[i], rv.garman_klass(*(window[k].tolist() for k in ("open", "high", "low", "close")))),
        "yz_20": (table["yz_20"].iloc[i], rv.yang_zhang(window["open"].tolist(), window["high"].tolist(),
                                                      window["low"].tolist(), window["close"].tolist(), prev_close)),
    }
    return {k: {"rolling": a, "pure": b, "match": bool(abs(a - b) <= 1e-9 * max(1.0, abs(b)))} for k, (a, b) in checks.items()}


def main() -> None:
    con = sqlite3.connect(f"file:{PRICES.as_posix()}?mode=ro", uri=True)
    tickers = [r[0] for r in con.execute("SELECT DISTINCT ticker FROM ohlcv_daily")]
    names = [f"{e}_{w}" for w in WINDOWS for e in ("cc", "park", "gk", "yz")] + ["ewma_094"]
    sums = {(n, hz): {"n": 0, "abs": 0.0, "qlike": 0.0, "logs": []} for n in names for hz in HORIZONS}
    jump_sums = {(n, hz): {"n": 0, "abs": 0.0} for n in ("yz_20", "ewma_094", "cc_20") for hz in HORIZONS}
    check = None
    rng = np.random.default_rng(0)
    for index, ticker in enumerate(tickers):
        frame = pd.read_sql_query(
            "SELECT trading_date, open, high, low, close FROM ohlcv_daily WHERE ticker = ? AND bar_status = 'COMPLETE' "
            "ORDER BY trading_date", con, params=(ticker,), index_col="trading_date")
        frame = frame[(frame[["open", "high", "low", "close"]] > 0).all(axis=1) & (frame["high"] >= frame["low"])]
        if len(frame) < 120:
            continue
        table = forecasts(frame)
        if check is None and len(frame) > 200:
            check = {"ticker": ticker, **self_check(frame, table)}
        sample = table[(table.index >= START)].iloc[::EVAL_STEP]
        for hz in HORIZONS:
            delivered = sample[f"delivered_{hz}"]
            for n in names:
                f = sample[n]
                ok = (f > 0) & (delivered > 0) & np.isfinite(f) & np.isfinite(delivered)
                if not ok.any():
                    continue
                ratio = np.log(f[ok] / delivered[ok])
                s = sums[(n, hz)]
                s["n"] += int(ok.sum())
                s["abs"] += float(ratio.abs().sum())
                x = (delivered[ok] ** 2) / (f[ok] ** 2)
                s["qlike"] += float((x - np.log(x) - 1).sum())
                keep = ratio.values if len(s["logs"]) < 400000 else ratio.values[rng.random(len(ratio)) < 0.1]
                s["logs"].extend(keep.tolist())
                if (n, hz) in jump_sums:
                    jumpy = sample.loc[ok[ok].index, f"max_abs_future_{hz}"] > 4 * f[ok]
                    j = jump_sums[(n, hz)]
                    j["n"] += int(jumpy.sum())
        if index % 500 == 0:
            print(f"{index}/{len(tickers)} {ticker}", flush=True)
    results = []
    for (n, hz), s in sums.items():
        if not s["n"]:
            continue
        results.append({"forecast": n, "horizon": hz, "n": s["n"], "median_log_ratio": float(np.median(s["logs"])),
                        "mean_abs_log_ratio": s["abs"] / s["n"], "qlike": s["qlike"] / s["n"],
                        "share_forecast_below_delivered": float(np.mean(np.array(s["logs"]) < 0))})
    results.sort(key=lambda d: (d["horizon"], d["qlike"]))
    jumps = {f"{n}_h{hz}": j["n"] / sums[(n, hz)]["n"] for (n, hz), j in jump_sums.items() if sums[(n, hz)]["n"]}
    payload = {"self_check": check, "results": results, "share_windows_with_jump_over_4x_forecast": jumps,
               "settings": {"horizons": HORIZONS, "windows": WINDOWS, "eval_step": EVAL_STEP, "start": START}}
    (OUT / "volatility_forecast_study.json").write_text(json.dumps(payload, indent=2, default=float), encoding="utf-8")
    print(json.dumps(check, indent=1, default=float))
    for hz in HORIZONS:
        print(f"-- horizon {hz}")
        for d in [d for d in results if d["horizon"] == hz][:8]:
            print(f"{d['forecast']:>9} n={d['n']:>8} qlike={d['qlike']:.4f} mean|log|={d['mean_abs_log_ratio']:.3f} "
                  f"median log(f/d)={d['median_log_ratio']:+.3f} below={d['share_forecast_below_delivered']:.2f}")
    print(json.dumps(jumps, indent=1))


if __name__ == "__main__":
    main()
