"""BEH-001: can structure resolve tickers with live candidates on both sides? (exploratory)

Fixed before results are read:
- Population: (ticker, cut) pairs in eval_v3 stage-A candidates with live directed
  candidates on BOTH sides.
- Outcome: from the cut close, which daily barrier is touched first, +k or -k daily ATR(14)
  (k = 2; high/low touches; both in one bar = AMBIGUOUS, excluded; none within 60 sessions
  = UNRESOLVED, excluded). UP_FIRST means the BULL side was right.
- Drift reference: the share of UP_FIRST among ALL evaluated (ticker, cut) pairs on the
  same cut (same-date market drift), averaged over the rule's picks.
- Rules (each picks a side or abstains):
    ACTIVATION   the side with an ACTIVATED candidate when only one side has one;
    TIMEFRAME    the side of the highest-timeframe candidate when it is one-sided on that timeframe;
    SCOPE        the CAMPAIGN side on the daily timeframe when daily CAMPAIGN is one-sided
                 and the other side is only LOCAL there;
    PROXIMITY    the side whose nearest DETECTED trigger is closer in ATR (abstains on ties
                 within 0.25 ATR or when either side has no DETECTED candidate);
    RANGE_EDGES  abstains by design when Spring and Upthrust/UTAD are both live on one timeframe (reported).
- Statistic: hit rate of each rule vs its drift reference; date-block bootstrap
  (2 cuts per block), 2,000 resamples, seed 20261001.
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

K, LIMIT = 2.0, 60
TF_ORDER = {"1mo": 3, "1w": 2, "1d": 1}


def first_touch(frame, i, atr):
    c0 = frame["close"].iat[i]
    up, dn = c0 + K * atr, c0 - K * atr
    hi, lo = frame["high"].to_numpy(), frame["low"].to_numpy()
    for j in range(i + 1, min(len(frame), i + 1 + LIMIT)):
        u, d = hi[j] >= up, lo[j] <= dn
        if u and d:
            return "AMBIGUOUS"
        if u:
            return "UP"
        if d:
            return "DOWN"
    return "UNRESOLVED"


def rules(g: pd.DataFrame) -> dict:
    out = {}
    act = set(g.loc[g.state == "ACTIVATED", "dir"])
    out["ACTIVATION"] = act.pop() if len(act) == 1 else None
    top = g[g.tf.map(TF_ORDER) == g.tf.map(TF_ORDER).max()]
    out["TIMEFRAME"] = top.dir.iat[0] if top.dir.nunique() == 1 else None
    d = g[g.tf == "1d"]
    camp = set(d.loc[d.scope == "CAMPAIGN", "dir"])
    local = set(d.loc[d.scope == "LOCAL", "dir"])
    out["SCOPE"] = next(iter(camp)) if len(camp) == 1 and (local - camp) else None
    det = g[g.state == "DETECTED"].copy()
    if det.dir.nunique() == 2:
        det["dist"] = (det.trigger - det.close).abs() / det.atr_d
        near = det.groupby("dir").dist.min()
        out["PROXIMITY"] = near.idxmin() if abs(near["BULL"] - near["BEAR"]) > 0.25 else None
    else:
        out["PROXIMITY"] = None
    edges = any({"Spring Candidate"} <= set(h.type) and ({"Upthrust Candidate", "UTAD Test"} & set(h.type))
                for _, h in g.groupby("tf"))
    out["RANGE_EDGES"] = "PRESENT" if edges else None
    return out


def main():
    cand = pd.read_json(sys.argv[1], lines=True)
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
            touch = first_touch(frame, i, atr)
            row = {"ticker": ticker, "cut": cut, "touch": touch, "two_sided": g.dir.nunique() == 2}
            if row["two_sided"]:
                row.update(rules(g.assign(atr_d=atr)))
                row["config"] = ("CROSS_TIMEFRAME" if g.groupby("dir").tf.apply(set).pipe(
                    lambda s: s["BULL"].isdisjoint(s["BEAR"])) else "SAME_TIMEFRAME")
            rows.append(row)
    df = pd.DataFrame(rows)
    df = df[df.touch.isin(["UP", "DOWN"])]
    drift = df.groupby("cut").touch.apply(lambda s: (s == "UP").mean())
    two = df[df.two_sided].copy()
    two["drift_up"] = two.cut.map(drift)
    cuts = sorted(df.cut.unique())
    block = {c: i // 2 for i, c in enumerate(cuts)}
    rng = np.random.default_rng(20261001)
    print(f"evaluated pairs {len(df)}; two-sided {len(two)} ({len(two) / len(df):.0%}); configs "
          f"{two.config.value_counts().to_dict()}")
    print(f"range-edge two-sided cases: {(two.RANGE_EDGES == 'PRESENT').sum()}")
    report = {}
    for rule in ("ACTIVATION", "TIMEFRAME", "SCOPE", "PROXIMITY"):
        r = two[two[rule].isin(["BULL", "BEAR"])].copy()
        if r.empty:
            continue
        r["hit"] = ((r[rule] == "BULL") & (r.touch == "UP")) | ((r[rule] == "BEAR") & (r.touch == "DOWN"))
        r["ref"] = np.where(r[rule] == "BULL", r.drift_up, 1 - r.drift_up)
        r["block"] = r.cut.map(block)
        gsum = r.groupby("block").agg(h=("hit", "sum"), b=("ref", "sum"), n=("hit", "count"))
        idx = rng.integers(0, len(gsum), size=(2000, len(gsum)))
        hs, bs, ns = (gsum[x].to_numpy()[idx].sum(1) for x in ("h", "b", "n"))
        ex = (hs - bs) / ns
        report[rule] = {"picks": len(r), "coverage_of_two_sided": round(len(r) / len(two), 3),
                        "bull_share": round((r[rule] == "BULL").mean(), 3), "hit_rate": round(r.hit.mean(), 4),
                        "drift_ref": round(r.ref.mean(), 4), "excess": round(r.hit.mean() - r.ref.mean(), 4),
                        "excess_lo95": round(float(np.quantile(ex, 0.025)), 4),
                        "excess_hi95": round(float(np.quantile(ex, 0.975)), 4)}
        for cfg_name, cg in r.groupby(two.loc[r.index, "config"]):
            report[rule][f"hit_{cfg_name}"] = f"{cg.hit.mean():.3f} vs {cg.ref.mean():.3f} (n={len(cg)})"
    print(json.dumps(report, indent=1))
    Path(sys.argv[2]).write_text(json.dumps(report, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
