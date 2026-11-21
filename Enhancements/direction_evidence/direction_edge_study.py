r"""Direction edge study (ACK 7 Oct 2026). Implements DIRECTION_EDGE_STUDY_PREREG_20261007.md exactly. Read-only.

    venv\\Scripts\\python.exe Enhancements\\direction_evidence\\direction_edge_study.py \\
        --out Enhancements\\direction_evidence\\direction_edge_study_20261007.json
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from dir002_replay import read_bars  # noqa: E402
from domain.structure_behaviour.engine import handoff_thesis  # noqa: E402
from domain.structure_behaviour.policy import load_policy  # noqa: E402

SEED, RESAMPLES, PLACEBOS = 20261007, 2000, 5
HORIZON = {"1d": 60, "1w": 120, "1mo": 250}
SPLIT = "2024-09-15"
LEVEL_TEST = {"DETECTED": "OUTCOME_FROM_DETECTION", "ACTIVATED": "OUTCOME"}
BASE = ROOT / "Enhancements" / "outcomes" / "beh001"


def boot(values, blocks):
    d = pd.DataFrame({"v": values, "b": blocks}).dropna()
    if d.empty:
        return {"n": 0, "blocks": 0, "mean": None, "lo95": None, "hi95": None}
    g = d.groupby("b")["v"].agg(["sum", "count"])
    rng = np.random.default_rng(SEED)
    idx = rng.integers(0, len(g), size=(RESAMPLES, len(g)))
    means = g["sum"].to_numpy()[idx].sum(1) / g["count"].to_numpy()[idx].sum(1)
    return {"n": int(len(d)), "blocks": int(len(g)), "mean": round(float(d["v"].mean()), 4),
            "lo95": round(float(np.percentile(means, 2.5)), 4), "hi95": round(float(np.percentile(means, 97.5)), 4)}


class Bars:
    def __init__(self, ticker):
        f = read_bars(ticker)
        self.ok = len(f) > 300
        if not self.ok:
            return
        self.date = f["date"].dt.strftime("%Y-%m-%d").to_numpy()
        self.pos = {d: i for i, d in enumerate(self.date)}
        self.h, self.l, self.c = (f[k].to_numpy(float) for k in ("high", "low", "close"))
        prev = np.r_[self.c[0], self.c[:-1]]
        tr = np.maximum(self.h - self.l, np.maximum(abs(self.h - prev), abs(self.l - prev)))
        self.atr = pd.Series(tr).rolling(14).mean().to_numpy()
        sma = pd.Series(self.c).rolling(20).mean().to_numpy()
        roc = pd.Series(self.c).pct_change(12).to_numpy()
        self.sma, self.roc = sma, roc

    def first_touch(self, i, up_level, dn_level, horizon):
        """'UP' / 'DOWN' / None (ambiguous or neither or censored)."""
        end = i + 1 + horizon
        if end > len(self.c):
            return None
        hi, lo = self.h[i + 1:end], self.l[i + 1:end]
        u = np.flatnonzero(hi >= up_level)
        d = np.flatnonzero(lo <= dn_level)
        fu, fd = (u[0] if len(u) else None), (d[0] if len(d) else None)
        if fu is None and fd is None:
            return None
        if fu is not None and fd is not None and fu == fd:
            return None
        if fd is None or (fu is not None and fu < fd):
            return "UP"
        return "DOWN"

    def trend(self, i):
        if i < 26 or np.isnan(self.sma[i]) or np.isnan(self.sma[i - 5]):
            return None
        roc_window = self.roc[i - 5:i + 1]
        if np.isnan(roc_window).any():
            return None
        score = (np.sign(self.c[i] - self.sma[i]) + np.sign(self.sma[i] - self.sma[i - 5])
                 + np.sign(self.roc[i] - roc_window.mean()))
        return "UP" if score >= 2 else "DOWN" if score <= -2 else None


def load_panel(name):
    rows = [json.loads(line) for line in open(BASE / name / "candidates.jsonl", encoding="utf-8")]
    return pd.DataFrame(rows)


def evidence_index():
    ev = json.loads((ROOT / "config" / "beh001_duration_evidence_v3.json").read_text(encoding="utf-8"))
    return {(g["timeframe"], g["scope"], g["signal_type"], g["direction"], g["test"]): g.get("p_event_at_limit")
            for g in ev["groups"] if g.get("age_bucket") == "ALL" and g.get("status") != "INSUFFICIENT_SAMPLE"}


def lane_a():
    lanes = json.loads((ROOT / "config" / "beh001_lanes_v1.json").read_text(encoding="utf-8"))["lane_a_trade_now"]
    return {(tf, e["type"], e["state"]) for tf, v in lanes.items() for e in v}


def part_a(panel, bars, rng):
    la = lane_a()
    cuts = sorted(panel["cut"].unique())
    block = {c: i // 2 for i, c in enumerate(cuts)}
    by_cut = defaultdict(list)
    for t, b in bars.items():
        if b.ok:
            for c in cuts:
                i = b.pos.get(c)
                if i is not None and not np.isnan(b.atr[i]) and b.atr[i] > 0:
                    by_cut[c].append(t)
    out, excluded_past = [], 0
    for r in panel.itertuples(index=False):
        b = bars.get(r.ticker)
        if b is None or not b.ok or r.cut not in b.pos or pd.isna(r.outcome) or pd.isna(r.invalidation):
            continue
        i = b.pos[r.cut]
        s = 1.0 if r.dir == "BULL" else -1.0
        close = b.c[i]
        a, bb = s * (r.outcome - close), s * (close - r.invalidation)
        if a <= 0 or bb <= 0:
            excluded_past += 1
            continue
        H = HORIZON.get(r.tf)
        if H is None or np.isnan(b.atr[i]) or b.atr[i] <= 0:
            continue
        up, dn = (r.outcome, r.invalidation) if s > 0 else (r.invalidation, r.outcome)
        hit = b.first_touch(i, up, dn, H)
        if hit is None:
            continue
        obs = 1.0 if (hit == "UP") == (s > 0) else 0.0
        a_atr, b_atr = a / b.atr[i], bb / b.atr[i]
        pool = [t for t in by_cut[r.cut] if t != r.ticker]
        if not pool:
            continue
        picks = rng.choice(len(pool), size=min(PLACEBOS, len(pool)), replace=False)
        p_out = []
        for k in picks:
            pb = bars[pool[k]]
            j = pb.pos[r.cut]
            cp, at = pb.c[j], pb.atr[j]
            lvl, inv = cp + s * a_atr * at, cp - s * b_atr * at
            u, d = (lvl, inv) if s > 0 else (inv, lvl)
            h2 = pb.first_touch(j, u, d, H)
            if h2 is not None:
                p_out.append(1.0 if (h2 == "UP") == (s > 0) else 0.0)
        if not p_out:
            continue
        out.append({"cut": r.cut, "block": block[r.cut], "period": "P1" if r.cut <= SPLIT else "P2", "tf": r.tf,
                    "state": r.state, "side": r.dir, "type": r.type, "laneA": (r.tf, r.type, r.state) in la,
                    "obs": obs, "geom": bb / (a + bb), "placebo": float(np.mean(p_out))})
    df = pd.DataFrame(out)
    df["edge"] = df["obs"] - df["placebo"]
    df["edge_geom"] = df["obs"] - df["geom"]
    groups = {"ALL": df}
    for col in ("tf", "state", "side", "laneA"):
        for v, g in df.groupby(col):
            groups[f"{col}={v}"] = g
    for (tf, st), g in df.groupby(["tf", "state"]):
        groups[f"tf={tf}|state={st}"] = g
    for (ty, tf, st), g in df.groupby(["type", "tf", "state"]):
        if len(g) >= 200:
            groups[f"type={ty}|tf={tf}|state={st}"] = g
    res = {}
    for name, g in groups.items():
        res[name] = {"n": int(len(g)), "observed": round(g["obs"].mean(), 4), "geometry": round(g["geom"].mean(), 4),
                     "placebo": round(g["placebo"].mean(), 4), "edge_vs_placebo": boot(g["edge"], g["block"]),
                     "edge_vs_geometry": boot(g["edge_geom"], g["block"]),
                     "by_period": {p: boot(gp["edge"], gp["block"]) for p, gp in g.groupby("period")}}
    return res, excluded_past


def to_readings(group, price_checked, close):
    readings = {}
    for r in group:
        s = 1 if r["dir"] == "BULL" else -1
        if price_checked and (s * (close - r["invalidation"]) <= 0 or s * (r["outcome"] - close) <= 0):
            continue
        readings.setdefault(r["tf"], {"Status": "EVALUATED", "candidates": []})["candidates"].append(
            {"Direction": r["dir"], "Signal_State": r["state"], "Candidate_ID": r["id"], "Signal_Type": r["type"],
             "Structure_Scope": r["scope"]})
    readings.setdefault("1d", {"Status": "EVALUATED", "candidates": []})
    return readings


def part_b(panel, bars, policy, ev):
    cuts = sorted(panel["cut"].unique())
    block = {c: i // 2 for i, c in enumerate(cuts)}
    recs = []
    for (t, cut), g in panel.groupby(["ticker", "cut"]):
        b = bars.get(t)
        if b is None or not b.ok or cut not in b.pos:
            continue
        i = b.pos[cut]
        atr = b.atr[i]
        if np.isnan(atr) or atr <= 0:
            continue
        group = g.to_dict("records")
        close = b.c[i]
        side = lambda h: {"BULL": "UP", "BEAR": "DOWN"}.get(h["thesis__side"])
        r0 = side(handoff_thesis(to_readings(group, False, close), policy))
        h1 = handoff_thesis(to_readings(group, True, close), policy)
        r1 = side(h1)
        r2 = r1
        if r1 is None and h1.get("thesis__direction_status") == "CONFLICT_REVIEW":
            score = {}
            for r in group:
                s = 1 if r["dir"] == "BULL" else -1
                if s * (close - r["invalidation"]) <= 0 or s * (r["outcome"] - close) <= 0:
                    continue
                p = ev.get((r["tf"], r["scope"], r["type"], r["dir"], LEVEL_TEST.get(r["state"])))
                if p is not None:
                    score[r["dir"]] = max(score.get(r["dir"], 0.0), p)
            if len(score) == 2 and abs(score["BULL"] - score["BEAR"]) >= 0.05:
                r2 = "UP" if score["BULL"] > score["BEAR"] else "DOWN"
        r3 = b.trend(i)
        r4 = r2 if r2 is not None else r3
        rec = {"cut": cut, "block": block[cut], "period": "P1" if cut <= SPLIT else "P2",
               "R0": r0, "R1": r1, "R2": r2, "R3": r3, "R4": r4}
        for k in (1, 2, 3):
            rec[f"o{k}"] = b.first_touch(i, close + k * atr, close - k * atr, 60)
        recs.append(rec)
    df = pd.DataFrame(recs)
    res = {}
    for k in (1, 2, 3):
        o = f"o{k}"
        ev_df = df[df[o].notna()].copy()
        drift = ev_df.groupby("cut")[o].apply(lambda x: (x == "UP").mean())
        ev_df["drift_up"] = ev_df["cut"].map(drift)
        for rule in ("R0", "R1", "R2", "R3", "R4"):
            p = ev_df[ev_df[rule].notna()].copy()
            hit = (p[rule] == p[o]).astype(float)
            ref = np.where(p[rule] == "UP", p["drift_up"], 1 - p["drift_up"])
            p["excess"] = hit - ref
            res[f"k={k}|{rule}"] = {"coverage": round(len(p) / max(len(ev_df), 1), 4), "hit": round(hit.mean(), 4),
                                    "excess": boot(p["excess"], p["block"]),
                                    "by_period": {per: boot(gp["excess"], gp["block"]) for per, gp in p.groupby("period")}}
    return res


def main():
    a = argparse.ArgumentParser()
    a.add_argument("--out", required=True)
    a.add_argument("--limit", type=int, default=0, help="smoke test: first N tickers per panel")
    args = a.parse_args()
    policy, ev = load_policy(), evidence_index()
    report = {"prereg": "Enhancements/direction_evidence/DIRECTION_EDGE_STUDY_PREREG_20261007.md"}
    for name in ("eval_v4", "eval_v4_holdout"):
        panel = load_panel(name)
        if args.limit:
            panel = panel[panel["ticker"].isin(sorted(panel["ticker"].unique())[: args.limit])]
        bars = {t: Bars(t) for t in panel["ticker"].unique()}
        rng = np.random.default_rng(SEED)
        part_a_res, past = part_a(panel, bars, rng)
        report[name] = {"part_a": part_a_res, "excluded_already_past": past, "part_b": part_b(panel, bars, policy, ev)}
        print(f"{name}: done", flush=True)
    Path(args.out).write_text(json.dumps(report, indent=1, default=str), encoding="utf-8")
    print("written", args.out)


if __name__ == "__main__":
    main()
