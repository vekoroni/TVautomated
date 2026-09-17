"""Legacy forward-variance forecast vs EWMA (read-only).

Evaluates the pipeline's own `layer3_forward_variance.compute_forward_variance` (HAR-RV primary; the
`arch` package is not installed, so GARCH never runs) with regime = '' (no macro multiplier) against
EWMA (0.94) on the same random 300-ticker sample, every 20th session from 2022, horizon 20 sessions.

  venv\\Scripts\\python.exe Enhancements\\expression_forensics\\legacy_forward_variance_study.py
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

MAIN = Path(r"C:\Users\ACKVerissimo\AVSHUNTER-Intelligence")
sys.path.insert(0, str(MAIN))
logging.disable(logging.WARNING)
import layer3_forward_variance as l3  # noqa: E402

PRICES = MAIN / "data" / "canonical" / "historical_prices.sqlite"
OUT = Path(__file__).resolve().parent / "legacy_forward_variance_study.json"
HORIZON, STEP, START, SAMPLE, HISTORY = 20, 20, "2022-01-01", 300, 260


def qlike(forecast, delivered):
    x = (delivered ** 2) / (forecast ** 2)
    return x - math.log(x) - 1


def main():
    con = sqlite3.connect(f"file:{PRICES.as_posix()}?mode=ro", uri=True)
    tickers = [r[0] for r in con.execute("SELECT DISTINCT ticker FROM ohlcv_daily")]
    rng = np.random.default_rng(7)
    sample = sorted(rng.choice(tickers, size=min(SAMPLE, len(tickers)), replace=False))
    rows = []
    for ticker in sample:
        frame = pd.read_sql_query("SELECT trading_date, open, high, low, close, volume FROM ohlcv_daily WHERE ticker = ? "
                                  "AND bar_status = 'COMPLETE' ORDER BY trading_date", con, params=(ticker,))
        frame = frame[frame["close"] > 0].reset_index(drop=True)
        r = np.log(frame["close"] / frame["close"].shift(1))
        ewma = np.sqrt((r ** 2).ewm(alpha=1 - 0.94, adjust=False).mean())
        for i in range(HISTORY, len(frame) - HORIZON, STEP):
            if frame.loc[i, "trading_date"] < START:
                continue
            delivered = math.sqrt(float((r.iloc[i + 1:i + 1 + HORIZON] ** 2).mean())) * math.sqrt(252)
            if not delivered > 0:
                continue
            window = frame.iloc[i - HISTORY + 1:i + 1]
            result = l3.compute_forward_variance(ticker, window, implied_vol=0.0, regime="")
            if result.error:
                continue
            rows.append({"ticker": ticker, "date": frame.loc[i, "trading_date"], "method": result.method,
                         "legacy": float(result.forward_realised_vol), "ewma": float(ewma.iloc[i]) * math.sqrt(252),
                         "delivered": delivered})
    df = pd.DataFrame(rows)
    out = {"n": len(df), "tickers": int(df["ticker"].nunique()), "methods": df["method"].value_counts().to_dict()}
    for name in ("legacy", "ewma"):
        lr = np.log(df[name] / df["delivered"])
        out[name] = {"qlike": float(np.mean([qlike(f, d) for f, d in zip(df[name], df["delivered"])])),
                     "mean_abs_log": float(lr.abs().mean()), "median_log_ratio": float(lr.median()),
                     "share_below_delivered": float((lr < 0).mean())}
    OUT.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
