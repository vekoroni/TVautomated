"""GARCH vs HAR-RV vs EWMA volatility forecasts (read-only; ACK approved 17 Sep 2026).

Runs ONLY in the isolated test environment C:\\Users\\ACKVerissimo\\AVSHUNTER_testenv_arch (arch 8.0.0,
numpy/pandas/scipy pinned to the production lock). Production venv is unchanged.

Same sample as legacy_forward_variance_study.py: 300 random tickers (seed 7), every 20th session from
2022, 252-bar history (as garch_runner.py), horizon 20 sessions, delivered = zero-mean RMS of daily log
returns over the next 20 sessions, annualised sqrt(252). No floor, cap or macro multiplier.

Forecasts:
  HAR_RV        legacy layer3_forward_variance._har_rv_forecast (production path)
  LEGACY_ARCH   legacy layer3_forward_variance._garch_forecast with HAR-RV disabled (EGARCH, then GARCH(1,1))
  EGARCH        arch EGARCH(1,1) fitted directly, legacy horizon formula
  GARCH11       arch GARCH(1,1) fitted directly, legacy horizon formula (stationary fits only)
  EWMA          0.94

  C:\\Users\\ACKVerissimo\\AVSHUNTER_testenv_arch\\Scripts\\python.exe Enhancements\\expression_forensics\\garch_comparison_study.py
"""

from __future__ import annotations

from collections import Counter
import json
import logging
import math
from pathlib import Path
import sqlite3
import sys
import time
import warnings

import numpy as np
import pandas as pd
from arch import arch_model

MAIN = Path(r"C:\Users\ACKVerissimo\AVSHUNTER-Intelligence")
sys.path.insert(0, str(MAIN))
logging.disable(logging.WARNING)
warnings.filterwarnings("ignore")
import layer3_forward_variance as l3  # noqa: E402

PRICES = MAIN / "data" / "canonical" / "historical_prices.sqlite"
OUT = Path(__file__).resolve().parent / "garch_comparison_study.json"
HORIZON, STEP, START, SAMPLE, HISTORY = 20, 20, "2022-01-01", 300, 252


def horizon_average(lr_var, cur_var, persist, horizon):
    return max(sum(lr_var + (persist ** h) * (cur_var - lr_var) for h in range(1, horizon + 1)) / horizon, 1e-8)


def fit(r_pct, vol):
    res = arch_model(r_pct, vol=vol, p=1, q=1, dist="Normal", rescale=True).fit(disp="off", show_warning=False,
                                                                                  options={"maxiter": 200})
    return res


def egarch_forecast(r_pct, stats):
    try:
        res = fit(r_pct, "EGARCH")
    except Exception:
        stats["EGARCH_error"] += 1
        return None
    if res.scale != 1.0:
        stats["EGARCH_rescaled"] += 1
    last = float(res.conditional_volatility[-1]) / res.scale
    if not (np.isfinite(last) and last > 0):
        stats["EGARCH_bad"] += 1
        return None
    beta = float(np.clip(res.params.get("beta[1]", 0.95), 0.0, 1.0))
    avg = horizon_average(float(np.std(r_pct)) ** 2, last ** 2, beta, HORIZON)
    stats["EGARCH_converged" if res.convergence_flag == 0 else "EGARCH_not_converged"] += 1
    return math.sqrt(avg) / 100 * math.sqrt(252)


def garch11_forecast(r_pct, stats):
    try:
        res = fit(r_pct, "Garch")
    except Exception:
        stats["GARCH_error"] += 1
        return None
    if res.scale != 1.0:
        stats["GARCH_rescaled"] += 1
    omega, alpha, beta = (float(res.params.get(k, np.nan)) for k in ("omega", "alpha[1]", "beta[1]"))
    omega /= res.scale ** 2
    if not (np.isfinite(omega) and np.isfinite(alpha) and np.isfinite(beta) and alpha + beta < 1 and alpha >= 0
            and beta >= 0 and omega > 0):
        stats["GARCH_non_stationary"] += 1
        return None
    persist = alpha + beta
    last = float(res.conditional_volatility[-1]) / res.scale
    avg = horizon_average(omega / (1 - persist), last ** 2, persist, HORIZON)
    stats["GARCH_converged" if res.convergence_flag == 0 else "GARCH_not_converged"] += 1
    return math.sqrt(avg) / 100 * math.sqrt(252)


def qlike(f, d):
    x = d * d / (f * f)
    return x - math.log(x) - 1


def main():
    con = sqlite3.connect(f"file:{PRICES.as_posix()}?mode=ro", uri=True)
    tickers = [r[0] for r in con.execute("SELECT DISTINCT ticker FROM ohlcv_daily")]
    rng = np.random.default_rng(7)
    sample = sorted(rng.choice(tickers, size=min(SAMPLE, len(tickers)), replace=False))
    rows, stats = [], Counter()
    started = time.time()
    real_har = l3._har_rv_forecast
    for n, ticker in enumerate(sample):
        closes = pd.read_sql_query("SELECT trading_date, close FROM ohlcv_daily WHERE ticker = ? AND bar_status = 'COMPLETE' "
                                   "ORDER BY trading_date", con, params=(ticker,))
        closes = closes[closes["close"] > 0].reset_index(drop=True)
        r_all = np.log(closes["close"] / closes["close"].shift(1))
        ewma = np.sqrt((r_all ** 2).ewm(alpha=1 - 0.94, adjust=False).mean())
        for i in range(HISTORY, len(closes) - HORIZON, STEP):
            if closes.loc[i, "trading_date"] < START:
                continue
            future = r_all.iloc[i + 1:i + 1 + HORIZON]
            delivered = math.sqrt(float((future ** 2).mean())) * math.sqrt(252)
            if not delivered > 0 or future.isna().any():
                continue
            returns = r_all.iloc[i - HISTORY + 1:i + 1].dropna().to_numpy()
            if len(returns) < HISTORY - 5:
                continue
            row = {"ticker": ticker, "date": closes.loc[i, "trading_date"], "delivered": delivered,
                   "EWMA": float(ewma.iloc[i]) * math.sqrt(252)}
            har = real_har(returns, HORIZON)
            row["HAR_RV"] = har["ann_vol"] if har else None
            l3._har_rv_forecast = lambda *_a, **_k: None
            try:
                legacy = l3._garch_forecast(returns, horizon=HORIZON)
            finally:
                l3._har_rv_forecast = real_har
            row["LEGACY_ARCH"] = legacy["ann_vol"] if legacy else None
            row["LEGACY_ARCH_model"] = "RETURNED_FORECAST" if legacy else "NONE"
            r_pct = returns * 100
            row["EGARCH"] = egarch_forecast(r_pct, stats)
            row["GARCH11"] = garch11_forecast(r_pct, stats)
            rows.append(row)
        if n % 25 == 0:
            print(f"{n}/{len(sample)} rows={len(rows)} {time.time() - started:.0f}s", flush=True)
    df = pd.DataFrame(rows)
    df.to_csv(OUT.with_suffix(".rows.csv"), index=False)
    models = ["HAR_RV", "EGARCH", "GARCH11", "EWMA"]   # LEGACY_ARCH reported by availability only
    common = df.dropna(subset=models)
    out = {"evaluations": len(df), "tickers": int(df["ticker"].nunique()), "common_evaluations": len(common),
           "fit_stats": dict(stats), "legacy_arch_model_used": df["LEGACY_ARCH_model"].value_counts().to_dict(),
           "availability": {m: float(df[m].notna().mean()) for m in models + ["LEGACY_ARCH"]}, "models": {}}
    for m in models:
        f, d = common[m].astype(float), common["delivered"].astype(float)
        lr = np.log(f / d)
        out["models"][m] = {"qlike": float(np.mean([qlike(a, b) for a, b in zip(f, d)])),
                            "mean_abs_log": float(lr.abs().mean()), "median_log_ratio": float(lr.median()),
                            "share_below_delivered": float((lr < 0).mean()),
                            "share_extreme_over_2x_or_under_half": float(((lr > math.log(2)) | (lr < -math.log(2))).mean())}
    # QLIKE by volatility regime (tercile of delivered-free EWMA level)
    common = common.copy()
    common["regime"] = pd.qcut(common["EWMA"], 3, labels=["LOW_VOL", "MID_VOL", "HIGH_VOL"])
    out["qlike_by_regime"] = {str(g): {m: float(np.mean([qlike(a, b) for a, b in zip(part[m], part["delivered"])]))
                                       for m in models} for g, part in common.groupby("regime", observed=True)}
    OUT.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
