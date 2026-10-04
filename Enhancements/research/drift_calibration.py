"""Drift calibration — expected forward move per signal decile (read-only; ACK 18 Sep 2026).

Why: the path valuation simulates with ZERO drift, because no direction edge had been demonstrated. With zero
drift no long option can price positively and shares price at zero, so the expression choice is meaningless. This
measures whether a composite of the signals that survived earlier study carries a forward move large enough to
matter, and calibrates that move per decile and horizon so the valuation can use it.

Pre-registered before running (no post-hoc additions):

  Universe per session: 20-session median dollar volume >= $5M, close >= $5, DQ-12 clean over the prior 260
  sessions (no one-bar move >= 10x, no sub-cent close), and a complete bar for the session.

  Signals (each cross-sectionally z-scored, winsorised at +/-3; a name is scored only when ALL are available):
    S1 reversal_5d      = -(close/close[-5] - 1)          (5-session reversal; survived plan A)
    S2 low_52w_distance = close/min(low, 252) - 1          (distance from the 52-week low; survived plan A)
    S3 momentum_12_1    = close[-21]/close[-252] - 1       (classic 12-1 momentum; included as a control)
  Composite = mean of the three z-scores.

  Forward return at horizon h (1, 3, 5, 10 sessions) = log(close[t+h]/close[t]) net of that session's universe
  mean, so the measure is market-neutral.

  Reported: Spearman IC per session with a t-statistic clustered by session; decile mean forward returns; the
  top-minus-bottom decile spread gross and net of the Abdi-Ranaldo round-trip share spread; all of it by year.

  Pass (pre-declared): mean IC same-signed in at least 4 of 5 years, |t| >= 3 on non-overlapping samples, and a
  net decile spread above zero at the primary horizon (5 sessions).

Usage: python Enhancements/research/drift_calibration.py [--start 2022-01-03]
"""

from __future__ import annotations

import argparse
from datetime import date
import json
import math
from pathlib import Path
import sys

import numpy as np
import pandas as pd
from scipy import stats

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from avshunter.c12_outcome.adapters import prices  # noqa: E402

HERE = Path(__file__).resolve().parent
PRICE_DB = REPO / "data" / "canonical" / "historical_prices.sqlite"
HORIZONS = (1, 3, 5, 10)
PRIMARY_HORIZON = 5
MIN_DOLLAR_VOLUME = 5_000_000.0
MIN_PRICE = 5.0
BREAK_RATIO = 10.0
SUB_CENT = 0.01
INTEGRITY_LOOKBACK = 260
DECILES = 10


def zscore(values: np.ndarray) -> np.ndarray:
    """Cross-sectional z-score per row, winsorised at +/-3; NaN stays NaN."""
    mean = np.nanmean(values, axis=1, keepdims=True)
    sd = np.nanstd(values, axis=1, keepdims=True)
    with np.errstate(invalid="ignore", divide="ignore"):
        z = (values - mean) / sd
    return np.clip(z, -3.0, 3.0)


def build(panel) -> dict:
    close, low, volume = panel.close, panel.low, panel.volume
    sessions, tickers = len(panel.sessions), len(panel.tickers)
    with np.errstate(invalid="ignore", divide="ignore"):
        logc = np.log(np.where(close > 0, close, np.nan))
        step = np.abs(np.diff(logc, axis=0, prepend=np.nan))
    broken = (step >= math.log(BREAK_RATIO)) | (close < SUB_CENT)
    broken = pd.DataFrame(broken).rolling(INTEGRITY_LOOKBACK, min_periods=1).max().to_numpy() > 0
    dollar = pd.DataFrame(close * volume).rolling(20, min_periods=15).median().to_numpy()
    eligible = (dollar >= MIN_DOLLAR_VOLUME) & (close >= MIN_PRICE) & np.isfinite(close) & ~broken

    shift = lambda a, k: np.vstack([np.full((k, tickers), np.nan), a[:-k]])  # noqa: E731
    with np.errstate(invalid="ignore", divide="ignore"):
        reversal = -(close / shift(close, 5) - 1.0)
        low_52w = close / pd.DataFrame(low).rolling(252, min_periods=200).min().to_numpy() - 1.0
        momentum = shift(close, 21) / shift(close, 252) - 1.0
    signals = {"reversal_5d": reversal, "low_52w_distance": low_52w, "momentum_12_1": momentum}
    scored = {name: np.where(eligible, zscore(np.where(eligible, values, np.nan)), np.nan)
              for name, values in signals.items()}
    stack = np.stack(list(scored.values()))
    composite = np.where(np.isfinite(stack).all(axis=0), np.nanmean(stack, axis=0), np.nan)
    scored["composite"] = composite

    forward = {}
    for h in HORIZONS:
        future = np.vstack([logc[h:], np.full((h, tickers), np.nan)])
        raw = future - logc
        raw = np.where(eligible, raw, np.nan)
        forward[h] = raw - np.nanmean(raw, axis=1, keepdims=True)
    return {"signals": scored, "forward": forward, "eligible": eligible}


def evaluate(name: str, signal: np.ndarray, forward: dict, sessions, spread: np.ndarray) -> list[dict]:
    out = []
    for h, future in forward.items():
        ics, dates = [], []
        decile_returns = np.full((len(sessions), DECILES), np.nan)
        decile_costs = np.full((len(sessions), DECILES), np.nan)
        for i in range(len(sessions)):
            s, f = signal[i], future[i]
            usable = np.isfinite(s) & np.isfinite(f)
            if usable.sum() < 100:
                continue
            ic = stats.spearmanr(s[usable], f[usable]).statistic
            if np.isfinite(ic):
                ics.append(ic)
                dates.append(sessions[i])
            order = np.argsort(s[usable])
            buckets = np.array_split(order, DECILES)
            values, costs = f[usable], spread[i][usable]
            for d, bucket in enumerate(buckets):
                decile_returns[i, d] = np.nanmean(values[bucket])
                decile_costs[i, d] = np.nanmean(costs[bucket])
        if len(ics) < 50:
            continue
        ics = np.array(ics)
        # non-overlapping sample for the t-statistic
        sample = ics[::h] if h > 1 else ics
        t = float(sample.mean() / (sample.std(ddof=1) / math.sqrt(len(sample)))) if sample.std(ddof=1) > 0 else float("nan")
        years = pd.Series(ics, index=pd.to_datetime([d.isoformat() for d in dates])).groupby(lambda x: x.year).mean()
        means = np.nanmean(decile_returns, axis=0)
        cost = np.nanmean(decile_costs, axis=0)
        spread_gross = float(means[-1] - means[0])
        spread_net = float(spread_gross - (cost[-1] + cost[0]))      # one round trip per leg
        out.append({
            "signal": name, "horizon": h, "sessions": len(ics), "mean_ic": round(float(ics.mean()), 5),
            "t_non_overlapping": round(t, 2), "ic_by_year": {int(y): round(float(v), 5) for y, v in years.items()},
            "same_sign_years": int((np.sign(years) == np.sign(ics.mean())).sum()),
            "decile_mean_returns_bps": [round(float(x) * 1e4, 1) for x in means],
            "top_minus_bottom_bps": round(spread_gross * 1e4, 1),
            "round_trip_cost_bps": round(float(cost[-1] + cost[0]) * 1e4, 1),
            "top_minus_bottom_net_bps": round(spread_net * 1e4, 1),
        })
    return out


def main() -> int:
    global MIN_DOLLAR_VOLUME
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default="2022-01-03")
    parser.add_argument("--min-dollar-volume", type=float, default=5_000_000.0)
    args = parser.parse_args()
    MIN_DOLLAR_VOLUME = args.min_dollar_volume
    start, end = date.fromisoformat(args.start), prices.latest_session(PRICE_DB)
    print(f"loading panel {start} -> {end} ...", flush=True)
    panel = prices.load_price_panel(start, end, PRICE_DB)
    print(f"panel: {len(panel.sessions)} sessions x {len(panel.tickers)} tickers", flush=True)
    built = build(panel)
    # Abdi-Ranaldo half-spread per name per session (60-session window), used as the per-leg cost
    c = np.log(np.where(panel.close > 0, panel.close, np.nan))
    eta = (np.log(np.where(panel.high > 0, panel.high, np.nan)) + np.log(np.where(panel.low > 0, panel.low, np.nan))) / 2
    product = (c - eta) * (c - np.vstack([eta[1:], np.full((1, len(panel.tickers)), np.nan)]))
    rolling = pd.DataFrame(product).rolling(60, min_periods=20).mean().to_numpy()
    spread = np.sqrt(np.clip(4.0 * rolling, 0.0, None)) / 2.0
    results = []
    for name, signal in built["signals"].items():
        results.extend(evaluate(name, signal, built["forward"], panel.sessions, spread))
    frame = pd.DataFrame(results)
    tag = f"_{int(MIN_DOLLAR_VOLUME/1e6)}m" if MIN_DOLLAR_VOLUME != 5_000_000.0 else ""
    frame.to_csv(HERE / f"drift_calibration_results{tag}.csv", index=False)
    primary = [r for r in results if r["signal"] == "composite" and r["horizon"] == PRIMARY_HORIZON]
    drift = {}
    if primary:
        row = primary[0]
        drift = {"horizon_sessions": PRIMARY_HORIZON, "signal": "composite",
                 "decile_expected_move_bps": row["decile_mean_returns_bps"],
                 "mean_ic": row["mean_ic"], "t_non_overlapping": row["t_non_overlapping"],
                 "net_top_minus_bottom_bps": row["top_minus_bottom_net_bps"]}
    payload = {"start": str(start), "end": str(end), "universe_rule": {
        "min_dollar_volume": MIN_DOLLAR_VOLUME, "min_price": MIN_PRICE, "integrity_lookback": INTEGRITY_LOOKBACK},
        "results": results, "calibrated_drift": drift}
    (HERE / f"drift_calibration_summary{tag}.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    cols = ["signal", "horizon", "sessions", "mean_ic", "t_non_overlapping", "same_sign_years",
            "top_minus_bottom_bps", "round_trip_cost_bps", "top_minus_bottom_net_bps"]
    print(frame[cols].to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
