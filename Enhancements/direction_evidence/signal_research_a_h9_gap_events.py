"""Signal research plan A — H9 gap drift event study (read-only; pre-registered in SIGNAL_RESEARCH_PLAN_A.md Addendum 1).

Event: |open_t - close_(t-1)| >= 2 x ATR14 (ending t-1) and volume_t >= 2 x median volume of the prior 20 sessions;
liquid (20-session median dollar volume >= $5M ending t-1); DQ-12 clean over [t-260, t+20]; first event per ticker in
any 20-session span. Entry at close_t; outcome log return close_t -> close_(t+h), h = 5/10/20, net of the liquid
universe median over the same window, signed by gap direction. Splits (pre-declared only): gap up / down; held / faded.
Standard errors clustered by event date. Train 2022-09..2024-12, test 2025-01..2026-08.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
import sys

import numpy as np
import pandas as pd
from scipy import stats

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from signal_research_a_price import load_panel  # noqa: E402

HORIZONS = (5, 10, 20)
TRAIN_END = "2024-12-31"
START = "2022-09-01"


def clustered_t(values: pd.Series, clusters: pd.Series) -> float:
    x = values.to_numpy(dtype=float)
    ok = np.isfinite(x)
    x, c = x[ok], clusters.to_numpy()[ok]
    n = len(x)
    if n < 20 or len(np.unique(c)) < 10:
        return float("nan")
    e = x - x.mean()
    sums = pd.Series(e).groupby(c).sum().to_numpy()
    g = len(sums)
    se = math.sqrt((g / (g - 1)) * (sums @ sums)) / n
    return float(x.mean() / se) if se > 0 else float("nan")


def main():
    p = load_panel()
    close, high, low, open_, vol = p["close"], p["high"], p["low"], p["open"], p["volume"]
    logc = np.log(close.where(close > 0))
    r1 = logc.diff()
    bad = ((r1.abs() >= math.log(10)) | (close < 0.01)).astype(float)
    clean = (bad.rolling(261, min_periods=1).max() < 1) & (bad[::-1].rolling(21, min_periods=1).max()[::-1] < 1)
    prev_close = close.shift(1)
    tr = pd.concat([(high - low).stack(), (high - prev_close).abs().stack(), (low - prev_close).abs().stack()], axis=1).max(axis=1)
    atr_prev = tr.unstack().reindex(index=close.index, columns=close.columns).rolling(14, min_periods=14).mean().shift(1)
    med_vol_prev = vol.rolling(20, min_periods=15).median().shift(1)
    liquid_prev = ((close * vol).rolling(20, min_periods=15).median() >= 5_000_000).shift(1).fillna(False)
    gap = open_ - prev_close
    is_event = (gap.abs() >= 2 * atr_prev) & (vol >= 2 * med_vol_prev) & liquid_prev & clean
    universe_fwd = {}
    liquid_now = (close * vol).rolling(20, min_periods=15).median() >= 5_000_000
    for h in HORIZONS:
        fwd = logc.shift(-h) - logc
        universe_fwd[h] = fwd.where(liquid_now & clean).median(axis=1)

    dates = close.index
    events = []
    for ticker in close.columns:
        flags = is_event[ticker].to_numpy()
        idx = np.nonzero(flags)[0]
        last = -10_000
        for i in idx:
            if dates[i] < START or i + max(HORIZONS) >= len(dates) or i - last < 20:
                continue
            last = i
            sign = 1.0 if gap[ticker].iat[i] > 0 else -1.0
            held = bool(sign * (close[ticker].iat[i] - open_[ticker].iat[i]) > 0)
            row = {"ticker": ticker, "date": dates[i], "year": dates[i][:4],
                   "period": "TRAIN" if dates[i] <= TRAIN_END else "TEST", "direction": "UP" if sign > 0 else "DOWN",
                   "held": "HELD" if held else "FADED",
                   "gap_atr": float(abs(gap[ticker].iat[i]) / atr_prev[ticker].iat[i])}
            # median round-trip share spread proxy (Abdi-Ranaldo, 60 sessions ending t)
            window = slice(max(0, i - 60), i + 1)
            c, hh, ll = logc[ticker].iloc[window], np.log(high[ticker].iloc[window]), np.log(low[ticker].iloc[window])
            eta = (hh + ll) / 2
            prod = ((c - eta) * (c - eta.shift(-1))).dropna()
            row["share_spread"] = float(math.sqrt(max(4 * prod.mean(), 0))) if len(prod) >= 20 else np.nan
            for h in HORIZONS:
                raw = logc[ticker].iat[i + h] - logc[ticker].iat[i]
                row[f"signed_net_{h}"] = float(sign * (raw - universe_fwd[h].iat[i])) if np.isfinite(raw) else np.nan
            events.append(row)
    ev = pd.DataFrame(events)
    ev.to_csv(HERE / "signal_research_a_h9_events.csv", index=False)

    rows = []
    splits = {"ALL": ev, "UP": ev[ev.direction == "UP"], "DOWN": ev[ev.direction == "DOWN"],
              "HELD": ev[ev.held == "HELD"], "FADED": ev[ev.held == "FADED"]}
    for split, g in splits.items():
        for h in HORIZONS:
            col = f"signed_net_{h}"
            row = {"split": split, "horizon": h}
            for period in ("TRAIN", "TEST"):
                s = g[g.period == period]
                row[f"{period.lower()}_events"] = len(s)
                row[f"{period.lower()}_event_dates"] = int(s["date"].nunique())
                row[f"{period.lower()}_mean_bps"] = float(s[col].mean() * 1e4) if len(s) else np.nan
                row[f"{period.lower()}_t"] = clustered_t(s[col], s["date"]) if len(s) else np.nan
                row[f"{period.lower()}_share_positive"] = float((s[col] > 0).mean()) if len(s) else np.nan
            yearly = g.groupby("year")[col].mean()
            row["yearly_bps"] = {k: round(float(v) * 1e4, 1) for k, v in yearly.items()}
            row["same_sign_years"] = int((yearly > 0).sum())
            row["median_share_spread_bps"] = float(g["share_spread"].median() * 1e4)
            rows.append(row)
    sm = pd.DataFrame(rows)
    sm["test_p"] = [2 * stats.norm.sf(abs(t)) if np.isfinite(t) else 1.0 for t in sm["test_t"]]
    order = sm["test_p"].sort_values().index
    m = len(sm)
    passed = sm.loc[order, "test_p"].to_numpy() <= 0.10 * np.arange(1, m + 1) / m
    k = np.max(np.nonzero(passed)[0]) + 1 if passed.any() else 0
    sm["test_fdr"] = False
    sm.loc[order[:k], "test_fdr"] = True
    sm["train_pass"] = (sm["train_mean_bps"] > 0) & (sm["train_t"] >= 2.5)
    sm["test_pass"] = (sm["test_mean_bps"] > 0) & (sm["test_t"] >= 2.0) & sm["test_fdr"]
    sm["years_pass"] = sm["same_sign_years"] >= 4
    sm["economic_10d"] = (sm["horizon"] == 10) & (sm["test_mean_bps"] > sm["median_share_spread_bps"])
    sm["passes"] = sm["train_pass"] & sm["test_pass"] & sm["years_pass"]
    sm.to_csv(HERE / "signal_research_a_h9_summary.csv", index=False)
    (HERE / "signal_research_a_h9_summary.json").write_text(sm.to_json(orient="records", indent=2), encoding="utf-8")
    print(f"events {len(ev)} (train {int((ev.period == 'TRAIN').sum())}, test {int((ev.period == 'TEST').sum())}), "
          f"tickers {ev.ticker.nunique()}, median gap {ev.gap_atr.median():.2f} ATR")
    cols = ["split", "horizon", "train_events", "train_mean_bps", "train_t", "test_events", "test_mean_bps", "test_t",
            "same_sign_years", "median_share_spread_bps", "train_pass", "test_pass", "years_pass", "economic_10d", "passes"]
    print(sm[cols].round(2).to_string(index=False))


if __name__ == "__main__":
    main()
