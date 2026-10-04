"""BEH-001: can a higher timeframe set the side when the daily reading has no live directed candidate?

Parked 2 Oct 2026 until the database refresh; resumed 2 Oct after the refresh (ACK).
Fixed before results are read:
- Population: (ticker, cut) pairs in stage-A candidates (beh001_eval_candidates.py, refreshed
  bars) with NO live directed daily candidate and at least one on 1w or 1mo. This is the
  production status NO_DIRECTIONAL_CANDIDATE with higher-timeframe structure present.
- Rule (mirrors production handoff_thesis precedence, config handoff.higher_timeframes):
    HTF  walk 1mo then 1w; the first timeframe with live candidates decides; one-sided ->
         that side; two-sided -> abstain (stays UNASSIGNED).
- Outcome: from the cut close, which daily barrier is touched first, +k or -k daily ATR(14)
  (high/low touches; both in one bar = AMBIGUOUS, excluded; none within 60 sessions =
  UNRESOLVED, excluded). k = 2 primary; k = 1 and 3 robustness.
- Drift reference: share of UP_FIRST among all evaluated pairs on the same cut, averaged
  over the rule's picks (same as beh001_two_sided_resolution.py).
- Statistic: hit rate minus drift reference; date-block bootstrap (2 cuts per block),
  2,000 resamples, seed 20261002.
- Breakdowns: deciding timeframe, ACTIVATED vs DETECTED on the chosen side, period
  (cut < 2024-09-01 vs >=), Discovery eligibility.
- Decision criterion (fixed now): adopt only if, at k = 2, the excess is positive with its
  95% lower bound > 0 on the HOLDOUT panel (tickers never used to design a rule), and the
  point estimate is positive in both periods on both panels. Otherwise the row stays
  UNASSIGNED and the higher-timeframe structure is displayed, not used for the side.
Usage: beh001_empty_daily_resolution.py <candidates.jsonl> <out.json>
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from dir002_replay import read_bars  # noqa: E402

LIMIT, SPLIT = 60, "2024-09-01"
KS = (1.0, 2.0, 3.0)


def first_touches(frame, i, atr):
    c0 = frame["close"].iat[i]
    hi, lo = frame["high"].to_numpy(), frame["low"].to_numpy()
    out = {}
    for k in KS:
        up, dn, res = c0 + k * atr, c0 - k * atr, "UNRESOLVED"
        for j in range(i + 1, min(len(frame), i + 1 + LIMIT)):
            u, d = hi[j] >= up, lo[j] <= dn
            if u or d:
                res = "AMBIGUOUS" if (u and d) else ("UP" if u else "DOWN")
                break
        out[k] = res
    return out


def htf_rule(g: pd.DataFrame):
    for tf in ("1mo", "1w"):
        h = g[g.tf == tf]
        if h.empty:
            continue
        if h.dir.nunique() == 1:
            side = h.dir.iat[0]
            state = "ACTIVATED" if (h.state == "ACTIVATED").any() else "DETECTED"
            return side, tf, state
        return None, tf, "TWO_SIDED"
    return None, None, None


def _excess(r, rng):
    cuts = sorted(r.cut.unique())
    block = {c: i // 2 for i, c in enumerate(cuts)}
    gsum = r.assign(block=r.cut.map(block)).groupby("block").agg(h=("hit", "sum"), b=("ref", "sum"), n=("hit", "count"))
    idx = rng.integers(0, len(gsum), size=(2000, len(gsum)))
    hs, bs, ns = (gsum[x].to_numpy()[idx].sum(1) for x in ("h", "b", "n"))
    ex = (hs - bs) / ns
    return {"n": int(len(r)), "hit_rate": round(float(r.hit.mean()), 4), "drift_ref": round(float(r.ref.mean()), 4),
            "excess": round(float(r.hit.mean() - r.ref.mean()), 4),
            "lo95": round(float(np.quantile(ex, 0.025)), 4), "hi95": round(float(np.quantile(ex, 0.975)), 4)}


def main():
    cand = pd.read_json(sys.argv[1], lines=True)
    cand = cand[cand.get("engine_error").isna()] if "engine_error" in cand else cand
    rows = []
    for ticker, tg in cand.groupby("ticker"):
        frame = read_bars(ticker)
        if frame.empty:
            continue
        pos = {d: i for i, d in enumerate(frame["date"].dt.strftime("%Y-%m-%d"))}
        h, l, c = (frame[x].to_numpy() for x in ("high", "low", "close"))
        tr = np.maximum.reduce([h[1:] - l[1:], np.abs(h[1:] - c[:-1]), np.abs(l[1:] - c[:-1])])
        for cut, g in tg.groupby("cut"):
            i = pos.get(cut)
            if i is None or i < 15:
                continue
            atr = float(tr[i - 14:i].mean())
            row = {"ticker": ticker, "cut": cut, "eligibility": g.eligibility.iat[0],
                   **{f"t{k:g}": v for k, v in first_touches(frame, i, atr).items()}}
            daily = g[g.tf == "1d"]
            row["daily_sides"] = daily.dir.nunique()
            row["empty_daily_htf"] = daily.empty and not g[g.tf.isin(["1w", "1mo"])].empty
            if row["empty_daily_htf"]:
                row["pick"], row["tf"], row["state"] = htf_rule(g)
            rows.append(row)
    df = pd.DataFrame(rows)
    rng = np.random.default_rng(20261002)
    pop = df[df.empty_daily_htf]
    report = {"pairs_with_candidates": int(len(df)),
              "empty_daily_with_htf": int(len(pop)),
              "share_of_pairs": round(len(pop) / len(df), 3),
              "one_sided_daily": int((df.daily_sides == 1).sum()),
              "two_sided_daily": int((df.daily_sides == 2).sum()),
              "rule_coverage_of_population": round(float(pop.pick.notna().mean()), 3),
              "abstain_two_sided_htf": int((pop.state == "TWO_SIDED").sum()),
              "by_k": {}}
    for k in KS:
        col = f"t{k:g}"
        ev = df[df[col].isin(["UP", "DOWN"])]
        drift = ev.groupby("cut")[col].apply(lambda s: (s == "UP").mean())
        r = ev[ev.empty_daily_htf & ev.pick.isin(["BULL", "BEAR"])].copy()
        r["hit"] = ((r.pick == "BULL") & (r[col] == "UP")) | ((r.pick == "BEAR") & (r[col] == "DOWN"))
        r["ref"] = np.where(r.pick == "BULL", r.cut.map(drift), 1 - r.cut.map(drift))
        out = {"all": _excess(r, rng), "bull_share": round(float((r.pick == "BULL").mean()), 3)}
        if k == 2.0:
            for name, sub in (("tf_1mo", r[r.tf == "1mo"]), ("tf_1w", r[r.tf == "1w"]),
                              ("activated", r[r.state == "ACTIVATED"]), ("detected", r[r.state == "DETECTED"]),
                              ("period_2022_24", r[r.cut < SPLIT]), ("period_2024_26", r[r.cut >= SPLIT]),
                              ("eligible", r[r.eligibility == "ELIGIBLE"]), ("bull", r[r.pick == "BULL"]),
                              ("bear", r[r.pick == "BEAR"])):
                if len(sub) >= 30:
                    out[name] = _excess(sub, rng)
        report["by_k"][f"{k:g}"] = out
    print(json.dumps(report, indent=1))
    Path(sys.argv[2]).write_text(json.dumps(report, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
