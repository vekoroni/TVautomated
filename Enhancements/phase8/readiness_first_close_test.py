"""Readiness test (pre-registered in READINESS_FIRST_CLOSE_PREREG_20261012.md). Read-only; writes
readiness_first_close_test.json beside this file."""
from __future__ import annotations

import contextlib
import json
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
PANELS = {"original": ROOT / "Enhancements/outcomes/beh001/eval_v4/candidates.jsonl",
          "holdout": ROOT / "Enhancements/outcomes/beh001/eval_v4_holdout/candidates.jsonl"}
WINDOW, HORIZON, FAST, MARGIN, NEED = 20, 10, 3, 0.25, 2
rng = np.random.default_rng(7)


def load_candidates(path):
    c = pd.read_json(path, lines=True)
    c = c[(c["tf"] == "1d") & (c["state"] == "DETECTED") & c["dir"].isin(["BULL", "BEAR"]) & c["trigger"].notna()]
    return c.sort_values("cut").drop_duplicates("id", keep="first")


def outcome(close, high, low, atr, i, sign):
    """Side-signed outcomes from entry index i: hit (+1 ATR before -1 ATR within HORIZON), ret_atr at HORIZON, fast."""
    a = atr[i]
    if not np.isfinite(a) or a <= 0 or i + 1 >= len(close):
        return None
    up, dn = (close[i] + a, close[i] - a) if sign > 0 else (close[i] - a, close[i] + a)
    hit = None
    for k in range(i + 1, min(len(close), i + 1 + HORIZON)):
        fav = high[k] >= up if sign > 0 else low[k] <= up
        adv = low[k] <= dn if sign > 0 else high[k] >= dn
        if fav and adv:
            hit = 0.5
            break
        if fav:
            hit = 1.0
            break
        if adv:
            hit = 0.0
            break
    if hit is None:
        if i + HORIZON >= len(close):
            return None
        hit = 0.0
    j = min(len(close) - 1, i + HORIZON)
    ret = sign * (close[j] - close[i]) / a
    fast = any((high[k] >= up if sign > 0 else low[k] <= up) for k in range(i + 1, min(len(close), i + 1 + FAST)))
    return hit, ret, float(fast)


def main():
    cands = {k: load_candidates(p) for k, p in PANELS.items()}
    tickers = sorted(set().union(*[set(c["ticker"]) for c in cands.values()]))
    with contextlib.closing(sqlite3.connect(f"file:{(ROOT / 'data/canonical/historical_prices.sqlite').as_posix()}?mode=ro", uri=True)) as conn:
        bars = pd.read_sql_query("SELECT ticker, trading_date AS date, high, low, close FROM ohlcv_daily "
                                 "WHERE trading_date >= '2021-06-01' ORDER BY ticker, trading_date", conn)
    bars = bars[bars["ticker"].isin(tickers)]
    series = {}
    for t, g in bars.groupby("ticker"):
        g = g.reset_index(drop=True)
        prev = g["close"].shift(1)
        tr = np.maximum(g["high"] - g["low"], np.maximum((g["high"] - prev).abs(), (g["low"] - prev).abs()))
        series[t] = (pd.to_datetime(g["date"]).to_numpy(), g["close"].to_numpy(float), g["high"].to_numpy(float),
                     g["low"].to_numpy(float), tr.rolling(14).mean().to_numpy(float))
    report = {}
    for panel, c in cands.items():
        rows = []
        for r in c.itertuples():
            s = series.get(r.ticker)
            if s is None:
                continue
            dates, close, high, low, atr = s
            i0 = int(np.searchsorted(dates, np.datetime64(pd.Timestamp(r.cut)), side="right"))
            sign = 1.0 if r.dir == "BULL" else -1.0
            a_idx = b_idx = None
            run = 0
            for i in range(i0, min(len(close), i0 + WINDOW)):
                beyond = sign * (close[i] - r.trigger)
                if a_idx is None and beyond > 0:
                    a_idx = i
                run = run + 1 if (np.isfinite(atr[i]) and beyond > MARGIN * atr[i]) else 0
                if run >= NEED:
                    b_idx = i
                    break
            ctrl = []
            for i in range(max(0, i0 - 60), min(len(close) - HORIZON - 1, i0 + 60), 5):
                o = outcome(close, high, low, atr, i, sign)
                if o:
                    ctrl.append(o[0])
            base = {"cut": str(r.cut)[:10], "control_hit": float(np.mean(ctrl)) if ctrl else np.nan}
            if a_idx is not None:
                o = outcome(close, high, low, atr, a_idx, sign)
                if o:
                    rows.append({**base, "entry": "A", "accepted_later": b_idx is not None, "hit": o[0], "ret": o[1], "fast": o[2]})
            if b_idx is not None:
                o = outcome(close, high, low, atr, b_idx, sign)
                if o:
                    rows.append({**base, "entry": "B", "accepted_later": True, "hit": o[0], "ret": o[1], "fast": o[2],
                                 "sessions_after_A": (b_idx - a_idx) if a_idx is not None else None})
        df = pd.DataFrame(rows)
        A, B = df[df.entry == "A"], df[df.entry == "B"]
        cuts = df["cut"].unique()

        def boot(diff_fn):
            groups = {k: g for k, g in df.groupby("cut")}
            vals = []
            for _ in range(2000):
                pick = rng.choice(cuts, len(cuts))
                d = pd.concat([groups[k] for k in pick])
                vals.append(diff_fn(d))
            return [round(float(np.percentile(vals, q)), 4) for q in (2.5, 97.5)]

        bh = lambda d: d[d.entry == "B"]["hit"].mean() - d[d.entry == "A"]["hit"].mean()
        report[panel] = {
            "candidates": int(len(c)), "A_entries": int(len(A)), "B_entries": int(len(B)),
            "A_never_accepted": int((~A["accepted_later"]).sum()),
            "hit": {"A": round(A["hit"].mean(), 4), "B": round(B["hit"].mean(), 4),
                    "B_minus_A": round(B["hit"].mean() - A["hit"].mean(), 4), "B_minus_A_ci": boot(bh)},
            "ret_atr_10": {"A": round(A["ret"].mean(), 4), "B": round(B["ret"].mean(), 4)},
            "p_fast_3": {"A": round(A["fast"].mean(), 4), "B": round(B["fast"].mean(), 4)},
            "control_hit": {"A": round(A["control_hit"].mean(), 4), "B": round(B["control_hit"].mean(), 4)},
            "A_by_later_acceptance": {str(k): {"n": int(len(g)), "hit": round(g["hit"].mean(), 4),
                                               "ret": round(g["ret"].mean(), 4)} for k, g in A.groupby("accepted_later")},
            "median_sessions_A_to_B": float(B["sessions_after_A"].median()) if len(B) else None,
            "cut_dates": int(len(cuts)),
        }
    Path(__file__).with_suffix(".json").write_text(json.dumps(report, indent=1, default=str), encoding="utf-8")
    print(json.dumps(report, indent=1, default=str))


if __name__ == "__main__":
    main()
