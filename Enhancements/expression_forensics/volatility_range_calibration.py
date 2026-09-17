"""Calibration for volatility-range path valuation (read-only; ACK 17 Sep 2026, item 2 increment 2).

Produces config/calibration/volatility_range_calibration_v1.json with:
  forecast_error_bands   quantiles (p10, p50, p90) of delivered / forecast annualised volatility for the production
                         Layer 3 forecast (layer3_forward_variance.compute_forward_variance, regime '') at horizons of
                         5, 10 and 20 sessions — the volatility scenarios (cautious / central / upside);
  innovation_quantiles   101 quantiles (p0.5 ... p99.5 plus tails) of standardised daily log returns
                         r_t / sigma_(t-1) with sigma from EWMA(0.94) — the empirical shape of daily moves used to
                         simulate paths (fat tails from reality, not a normal assumption).
Sample: 300 random tickers (seed 11), every 20th session from 2022, 252-bar history, DQ-12 price-history rules
applied by the production forecast; innovations from the same tickers' full histories after their latest break.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import logging
import math
from pathlib import Path
import sqlite3
import sys

import numpy as np
import pandas as pd

MAIN = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(MAIN))
logging.disable(logging.WARNING)
import layer3_forward_variance as l3  # noqa: E402

PRICES = MAIN / "data" / "canonical" / "historical_prices.sqlite"
OUT = MAIN / "config" / "calibration" / "volatility_range_calibration_v1.json"
HORIZONS, STEP, START, SAMPLE, HISTORY = (5, 10, 20), 20, "2022-01-01", 300, 252
QUANTILES = [0.001, 0.005] + [round(q, 3) for q in np.linspace(0.01, 0.99, 99)] + [0.995, 0.999]


def main():
    con = sqlite3.connect(f"file:{PRICES.as_posix()}?mode=ro", uri=True)
    tickers = [r[0] for r in con.execute("SELECT DISTINCT ticker FROM ohlcv_daily")]
    sample = sorted(np.random.default_rng(11).choice(tickers, size=SAMPLE, replace=False))
    ratios = {h: [] for h in HORIZONS}
    innovations = []
    for ticker in sample:
        frame = pd.read_sql_query("SELECT trading_date AS date, open, high, low, close, volume FROM ohlcv_daily WHERE ticker = ? "
                                  "AND bar_status = 'COMPLETE' ORDER BY trading_date", con, params=(ticker,))
        if len(frame) < HISTORY + 30:
            continue
        frame["date"] = pd.to_datetime(frame["date"])
        segment, state, _, _ = l3._price_history_segment(frame, "close")
        if state == l3.PRICE_HISTORY_SUB_CENT or len(segment) < HISTORY + 30:
            continue
        segment = segment.reset_index(drop=True)
        r = np.log(segment["close"] / segment["close"].shift(1))
        ewma = np.sqrt((r ** 2).ewm(alpha=1 - 0.94, adjust=False).mean())
        z = (r / ewma.shift(1)).replace([np.inf, -np.inf], np.nan).dropna()
        innovations.extend(z.iloc[60:].tolist())
        for i in range(HISTORY, len(segment) - max(HORIZONS), STEP):
            if segment.loc[i, "date"] < pd.Timestamp(START):
                continue
            window = segment.iloc[i - HISTORY + 1:i + 1].reset_index(drop=True)
            forecast = l3.compute_forward_variance(ticker, window, implied_vol=None, regime="")
            if forecast.forward_realised_vol_raw is None or not forecast.forward_realised_vol_raw > 0:
                continue
            for h in HORIZONS:
                future = r.iloc[i + 1:i + 1 + h]
                if future.isna().any():
                    continue
                delivered = math.sqrt(float((future ** 2).mean())) * math.sqrt(252)
                if delivered > 0:
                    ratios[h].append(delivered / forecast.forward_realised_vol_raw)
    innov = np.asarray(innovations)
    payload = {
        "version": "volatility_range_calibration_v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "method": {
            "forecast": "layer3_forward_variance.compute_forward_variance (HAR-RV primary, regime '', DQ-12 applied)",
            "delivered": "zero-mean RMS of daily log returns over the horizon, annualised sqrt(252)",
            "innovation": "log return / EWMA(0.94) sigma of the previous session, pooled",
            "sample": {"tickers": SAMPLE, "seed": 11, "every_nth_session": STEP, "from": START, "history_bars": HISTORY},
        },
        "forecast_error_bands": {
            str(h): {"n": len(v), "p10": float(np.quantile(v, 0.10)), "p50": float(np.quantile(v, 0.50)),
                     "p90": float(np.quantile(v, 0.90))} for h, v in ratios.items()
        },
        "innovation_quantiles": {
            "n": int(innov.size), "levels": QUANTILES, "values": [float(v) for v in np.quantile(innov, QUANTILES)],
            "std": float(innov.std()), "kurtosis_excess": float(pd.Series(innov).kurt()),
        },
        "configuration_owner": "ACK",
        "validation_state": "EVIDENCE_CALIBRATION_SHADOW",
    }
    body = json.dumps(payload, indent=2, sort_keys=True)
    payload["content_sha256"] = hashlib.sha256(body.encode("utf-8")).hexdigest()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps({k: payload[k] for k in ("forecast_error_bands",)}, indent=1))
    print({k: payload["innovation_quantiles"][k] for k in ("n", "std", "kurtosis_excess")},
          dict(zip(["p0.1", "p1", "p50", "p99", "p99.9"],
                   [round(payload["innovation_quantiles"]["values"][i], 2) for i in (0, 2, 51, 100, 102)])))


if __name__ == "__main__":
    main()
