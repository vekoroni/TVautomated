"""Step 6 (ACK 3 Oct 2026, D-C): does the anticipated move rank outcomes at least as well as stop-based R:R?

Fixed before results are read:
- Population: HOLDOUT panel stage-A candidates (eval_v4_holdout; 500 tickers never used to design a rule) that
  are DETECTED or ACTIVATED, directed, with a structural Outcome_Level on the trade side and a published level
  evidence group (config/beh001_duration_evidence_v3.json, built on the OTHER panel; OUTCOME_FROM_DETECTION for
  DETECTED, OUTCOME for ACTIVATED; age bucket else ALL). Cuts with >= 60 forward sessions of data.
- Measures at the cut (underlying level; the replay has no option chains):
    OLD_RR    |Outcome_Level - close| / |close - invalidation|        (stop-based R:R, retired)
    NEW_MOVE  anticipated move %: Outcome_Level capped at close*(1 +/- 1.5*sigma*sqrt(t80/252)), sigma = 20-session
              realised log vol annualised, t80 = level q80 in sessions (governed sessions_per_bar)
    NEW_COVER NEW_MOVE / breakeven move of an ATM option with runway t80 + 8 sessions: 0.4*sigma*sqrt(T/252)
              (proxy for 'does the move pay' without chain data)
- Outcomes (trade direction): R20 = signed 20-session close-to-close return; HIT2 = first touch of +2 ATR(14) in the
  trade direction before -2 ATR within 60 sessions (ambiguous/unresolved excluded), minus same-cut drift
  (share of candidates on that cut whose favourable touch came first, by direction).
- Statistic: per cut, Spearman rank correlation of each measure with each outcome; mean over cuts; date-block
  bootstrap (2 cuts per block), 2,000 resamples, seed 20261003. Also top-quintile minus bottom-quintile outcome.
- Criterion (per new measure, per outcome): mean IC_new - IC_old >= 0 and its 95% lower bound > -0.01 -> PASS.
Usage: anticipated_move_ranking_validation.py <candidates.jsonl> <evidence.json> <out.json>
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from dir002_replay import read_bars  # noqa: E402

SPB = json.loads((ROOT / "config" / "governed_constants_v1.json").read_text(encoding="utf-8-sig"))["anticipated_move"]["sessions_per_bar"]
K, BUFFER = 1.5, 8


def bucket(age, edges):
    for lo, hi in zip(edges, edges[1:]):
        if lo <= age < hi:
            return f"{lo}-{hi - 1}"
    return f"{edges[-1]}+"


def spearman(a, b):
    if len(a) < 10:
        return np.nan
    return float(pd.Series(a).rank().corr(pd.Series(b).rank()))


def main():
    cand = pd.read_json(sys.argv[1], lines=True)
    ev = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
    idx = {(g["timeframe"], g["scope"], g["signal_type"], g["direction"], g["test"], g["age_bucket"]): g
           for g in ev["groups"] if g["status"] != "INSUFFICIENT_SAMPLE"}
    edges = ev["age_bucket_edges"]
    cand = cand[cand.state.isin(["DETECTED", "ACTIVATED"]) & cand.dir.isin(["BULL", "BEAR"]) & cand.outcome.notna()]
    if len(sys.argv) > 4:                       # exploratory, post hoc: restrict to one timeframe
        cand = cand[cand.tf.eq(sys.argv[4])]
    rows = []
    for ticker, tg in cand.groupby("ticker"):
        bars = read_bars(ticker)
        if bars.empty:
            continue
        pos = {d: i for i, d in enumerate(bars["date"].dt.strftime("%Y-%m-%d"))}
        h, l, c = (bars[x].to_numpy(float) for x in ("high", "low", "close"))
        lr = np.diff(np.log(c))
        tr = np.maximum.reduce([h[1:] - l[1:], np.abs(h[1:] - c[:-1]), np.abs(l[1:] - c[:-1])])
        for r in tg.itertuples(index=False):
            i = pos.get(r.cut)
            if i is None or i < 21 or i + 60 >= len(c):
                continue
            test = "OUTCOME_FROM_DETECTION" if r.state == "DETECTED" else "OUTCOME"
            key = (r.tf, r.scope, r.type, r.dir, test)
            g = idx.get(key + (bucket(int(r.age_bars), edges),)) or idx.get(key + ("ALL",))
            if g is None or g.get("remaining_bars_q80") is None or str(r.tf) not in SPB:
                continue
            sign = 1.0 if r.dir == "BULL" else -1.0
            close, inv, level = c[i], float(r.invalidation), float(r.outcome)
            if sign * (level - close) <= 0 or sign * (close - inv) <= 0:
                continue
            sigma = float(np.std(lr[i - 20:i], ddof=1) * math.sqrt(252))
            if not sigma > 0:
                continue
            t80 = max(1, round(g["remaining_bars_q80"] * SPB[str(r.tf)]))
            reach = close * (1 + sign * K * sigma * math.sqrt(t80 / 252))
            anticipated = level if abs(level - close) <= abs(reach - close) else reach
            move = sign * (anticipated - close) / close
            be = 0.4 * sigma * math.sqrt((t80 + BUFFER) / 252)
            atr = float(tr[i - 14:i].mean())
            hit = np.nan
            for j in range(i + 1, i + 61):
                up, dn = h[j] >= close + 2 * atr, l[j] <= close - 2 * atr
                if up and dn:
                    break
                if up or dn:
                    hit = 1.0 if (up and sign > 0) or (dn and sign < 0) else 0.0
                    break
            rows.append({"cut": r.cut, "dir": r.dir, "OLD_RR": abs(level - close) / abs(close - inv),
                         "NEW_MOVE": move, "NEW_COVER": move / be,
                         "R20": sign * (c[i + 20] / close - 1), "HIT2": hit})
    df = pd.DataFrame(rows)
    hits = df[df.HIT2.notna()].copy()
    drift = hits.groupby(["cut", "dir"]).HIT2.transform("mean")
    df.loc[hits.index, "HIT2X"] = hits.HIT2 - drift
    cuts = sorted(df.cut.unique())
    block = {cu: k // 2 for k, cu in enumerate(cuts)}
    rng = np.random.default_rng(20261003)
    report = {"candidates": int(len(df)), "cuts": len(cuts), "results": {}}
    for outcome in ("R20", "HIT2X"):
        sub = df[df[outcome].notna()]
        ic = {m: sub.groupby("cut").apply(lambda g: spearman(g[m], g[outcome])) for m in ("OLD_RR", "NEW_MOVE", "NEW_COVER")}
        frame = pd.DataFrame(ic).dropna()
        frame["block"] = frame.index.map(block)
        blocks = frame.groupby("block").mean()
        draws = rng.integers(0, len(blocks), size=(2000, len(blocks)))
        res = {"cuts_with_ic": int(len(frame)), "mean_ic": {m: round(float(frame[m].mean()), 4) for m in ic}}
        for m in ("NEW_MOVE", "NEW_COVER"):
            diff = (blocks[m] - blocks["OLD_RR"]).to_numpy()[draws].mean(axis=1)
            point = float((frame[m] - frame["OLD_RR"]).mean())
            lo, hi = float(np.quantile(diff, 0.025)), float(np.quantile(diff, 0.975))
            res[f"{m}_minus_OLD"] = {"diff": round(point, 4), "lo95": round(lo, 4), "hi95": round(hi, 4),
                                     "pass": bool(point >= 0 and lo > -0.01)}
        q = {}
        for m in ("OLD_RR", "NEW_MOVE", "NEW_COVER"):
            ranks = sub.groupby("cut")[m].rank(pct=True)
            q[m] = round(float(sub.loc[ranks >= 0.8, outcome].mean() - sub.loc[ranks <= 0.2, outcome].mean()), 4)
        res["top_minus_bottom_quintile"] = q
        report["results"][outcome] = res
    Path(sys.argv[3]).write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()
