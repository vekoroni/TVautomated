"""Summarise beh001_uncapped output (metrics fixed in beh001_uncapped.py).

Excess = observed rate - baseline rate. Interval: date-block bootstrap (blocks
of two consecutive cuts), 2,000 resamples, seed 20261001. Groups with fewer
than 100 resolved candidates or 20 blocks are NOT_ESTIMABLE.
"""
import collections
import json
import sys

import numpy as np
import pandas as pd

rows = [json.loads(l) for l in open(sys.argv[1], encoding="utf-8")]
df = pd.DataFrame(rows)
cuts = sorted(df["cut"].unique())
df["block"] = df["cut"].map({c: i // 2 for i, c in enumerate(cuts)})
rng = np.random.default_rng(20261001)


def boot_excess(sub, obs_col, base_col):
    g = sub.groupby("block").agg(o=(obs_col, "sum"), b=(base_col, "sum"), n=(obs_col, "count"))
    idx = rng.integers(0, len(g), size=(2000, len(g)))
    o, b, n = (g[c].to_numpy()[idx].sum(1) for c in ("o", "b", "n"))
    ex = (o - b) / n
    return round(float(np.percentile(ex, 2.5)), 3), round(float(np.percentile(ex, 97.5)), 3), len(g)


out = []
for kind in ("DETECTED", "ACTIVATED"):
    sub = df[df["kind"] == kind]
    for key, g in sub.groupby(["tf", "scope", "type"]):
        resolved = g[g["result"].isin(["FIRST", "SECOND"])].copy()
        total = len(g)
        unresolved = int((g["result"] == "UNRESOLVED").sum())
        if len(resolved) == 0:
            out.append({"kind": kind, "group": " | ".join(key), "n": total, "resolved": 0, "unresolved": unresolved})
            continue
        resolved["obs"] = (resolved["result"] == "FIRST").astype(float)
        if kind == "DETECTED":
            resolved["base"] = resolved["baseline"]
            opp = None
        else:
            resolved["base"] = 0.5
            o = g[g["opposite"].isin(["FIRST", "SECOND"])]
            opp = round(float((o["opposite"] == "FIRST").mean()), 3) if len(o) else None
        lo, hi, blocks = boot_excess(resolved, "obs", "base")
        t = resolved["sessions"].dropna()
        est = "ESTIMABLE" if len(resolved) >= 100 and blocks >= 20 else "NOT_ESTIMABLE"
        out.append({"kind": kind, "group": " | ".join(key), "n": total, "resolved": len(resolved),
                    "unresolved": unresolved, "observed": round(resolved["obs"].mean(), 3),
                    "baseline": round(resolved["base"].mean(), 3),
                    "excess": round(resolved["obs"].mean() - resolved["base"].mean(), 3),
                    "excess_lo95": lo, "excess_hi95": hi, "opposite_rate": opp,
                    "median_sessions": None if t.empty else float(t.median()),
                    "p80_sessions": None if t.empty else float(t.quantile(0.8)), "estimability": est})
res = pd.DataFrame(out).sort_values(["kind", "resolved"], ascending=[True, False])
pd.set_option("display.width", 250, "display.max_rows", 200, "display.max_colwidth", 60)
print(res.to_string(index=False))
res.to_json(sys.argv[2], orient="records", indent=1)
