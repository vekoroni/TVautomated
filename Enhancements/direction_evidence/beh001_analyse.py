"""BEH-001 acceptance §8.2 (distributions, mirror, sanity) and §8.5 (evaluation).

Metrics are fixed here before results are read (reported only; no promotion):

Distributions: phase / controller (campaign and local), handoff side, signal
type x state x scope, share of tickers with a directed daily candidate.

Population mirror (29 Sep 2026 cut and every cut): reflected bars must give
the mirrored handoff side and controller for every row (exact, per row).

Sanity: no BULL Spring Candidate is published as live when its own event has
FAILED; no directed candidate without trigger and invalidation levels.

Evaluation (rule EVALUATION), daily directed candidates, horizon 20 sessions:
  * DETECTED: first passage between trigger acceptance (close beyond the
    trigger level) and invalidation (close beyond the invalidation level):
    TRIGGER_FIRST / INVALIDATION_FIRST / NEITHER.
  * ACTIVATED at the cut: signed return in sigma units at 5/10/20 sessions,
    raw and drift-adjusted (minus the same-cut mean of all rows), and the
    first passage of +1 sigma*sqrt(20) in the candidate direction versus a
    close beyond its invalidation level.
  * Date-block bootstrap (blocks of two consecutive cuts = 20 sessions),
    2,000 resamples, seed 20261001. Types with < 100 activated rows or < 20
    blocks are NOT_ESTIMABLE.
"""
from __future__ import annotations

import collections
import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from dir002_replay import read_bars  # noqa: E402

SEED, RESAMPLES = 20261001, 2000
FLIP = {"BULL": "BEAR", "BEAR": "BULL", "UNASSIGNED": "UNASSIGNED"}
CFLIP = {"BUYERS": "SELLERS", "SELLERS": "BUYERS"}


def load(path):
    return [json.loads(l) for l in Path(path).read_text(encoding="utf-8").splitlines() if l.strip()]


def boot(values: pd.Series, blocks: pd.Series):
    d = pd.DataFrame({"v": values, "b": blocks}).dropna()
    if d.empty:
        return {"n": 0, "blocks": 0, "mean": None, "lo95": None, "hi95": None}
    g = d.groupby("b")["v"].agg(["sum", "count"])
    rng = np.random.default_rng(SEED)
    idx = rng.integers(0, len(g), size=(RESAMPLES, len(g)))
    means = g["sum"].to_numpy()[idx].sum(1) / g["count"].to_numpy()[idx].sum(1)
    return {"n": int(len(d)), "blocks": int(len(g)), "mean": round(float(d["v"].mean()), 4),
            "lo95": round(float(np.percentile(means, 2.5)), 4), "hi95": round(float(np.percentile(means, 97.5)), 4)}


def first_passage(close, start, horizon, up, trigger, invalidation):
    end = min(len(close) - 1, start + horizon)
    for j in range(start + 1, end + 1):
        c = close[j]
        hit_t = (c > trigger) if up else (c < trigger)
        hit_i = (c < invalidation) if up else (c > invalidation)
        if hit_i:
            return "INVALIDATION_FIRST"
        if hit_t:
            return "TRIGGER_FIRST"
    return "NEITHER" if end - start >= horizon else "CENSORED"


def main(path):
    rows = load(path)
    report = {"rows": len(rows)}
    c = collections.Counter()
    for r in rows:
        c[("campaign", r["phase"], r["controller"])] += 1
        c[("local", r["local_phase"], r["local_controller"])] += 1
        c[("handoff", r["handoff"])] += 1
        for k in r["candidates"]:
            c[("cand", k["Structure_Scope"], k["Signal_Type"], k["Direction"], k["Signal_State"])] += 1
    report["distributions"] = {" | ".join(map(str, k)): v for k, v in sorted(c.items(), key=lambda x: -x[1])}
    report["directed_handoff_share"] = round(sum(r["handoff"] in {"BULL", "BEAR"} for r in rows) / len(rows), 4)

    # Mirror: every row.
    mismatches = collections.Counter()
    for r in rows:
        if "m" not in r:
            continue
        if r["m_handoff"] != FLIP[r["handoff"]]:
            mismatches["handoff"] += 1
        if r["m"]["controller"] != CFLIP.get(r["controller"], r["controller"]):
            mismatches["controller"] += 1
        if r["m"]["phase"] != r["phase"]:
            mismatches["phase"] += 1
    report["mirror_mismatches"] = dict(mismatches)
    report["mirror_rows"] = sum("m" in r for r in rows)

    # Sanity.
    sanity = collections.Counter()
    for r in rows:
        failed_springs = {e[0] for e in r["events"] if e[1] == "FAILED"}
        for k in r["candidates"]:
            if k["Direction"] in {"BULL", "BEAR"} and (k["Trigger_Level"] is None or k["Invalidation_Level"] is None):
                sanity["directed_without_levels"] += 1
            if k["Signal_Type"] == "Spring Candidate" and k["Signal_State"] in {"DETECTED", "ACTIVATED"} \
                    and "SPRING" in failed_springs and k["Direction"] == "BULL":
                sanity["live_bull_spring_with_failed_spring_event"] += 1
    report["sanity"] = dict(sanity)

    # Evaluation on daily candidates.
    cuts = sorted({r["cut_date"] for r in rows})
    block = {cut: i // 2 for i, cut in enumerate(cuts)}
    z20_mean = pd.DataFrame([(r["cut_date"], r["ret_20"] / (r["sigma_d"] * math.sqrt(20)))
                             for r in rows if r.get("ret_20") == r.get("ret_20") and r.get("sigma_d")],
                            columns=["cut", "z"]).groupby("cut")["z"].mean()
    bars_cache = {}
    detected, activated = [], []
    for r in rows:
        for k in r["candidates"]:
            if k["Direction"] not in {"BULL", "BEAR"} or k["Trigger_Level"] is None:
                continue
            up = k["Direction"] == "BULL"
            key = (k["Structure_Scope"], k["Signal_Type"])
            if k["Signal_State"] == "DETECTED":
                if r["ticker"] not in bars_cache:
                    bars_cache[r["ticker"]] = read_bars(r["ticker"])
                f = bars_cache[r["ticker"]]
                pos = f.index[f["date"].dt.strftime("%Y-%m-%d") == r["cut_date"]]
                if len(pos):
                    detected.append({"key": key, "block": block[r["cut_date"]],
                                     "fp": first_passage(f["close"].to_numpy(), int(pos[0]), 20, up,
                                                         k["Trigger_Level"], k["Invalidation_Level"])})
            elif k["Signal_State"] == "ACTIVATED" and r.get("sigma_d") and r.get("ret_20") == r.get("ret_20"):
                s = 1.0 if up else -1.0
                zz = {h: s * r[f"ret_{h}"] / (r["sigma_d"] * math.sqrt(h)) for h in (5, 10, 20)}
                barrier = r["sigma_d"] * math.sqrt(20)
                fav = (r["mfe_up_20"] >= barrier) if up else (r["mfe_dn_20"] <= -barrier)
                activated.append({"key": key, "block": block[r["cut_date"]], **{f"z{h}": v for h, v in zz.items()},
                                  "xz20": zz[20] - s * z20_mean.get(r["cut_date"], 0.0), "fav_touch": float(fav)})
    det = pd.DataFrame(detected)
    act = pd.DataFrame(activated)
    evaluation = {}
    for key in sorted(set(map(tuple, act["key"])) | set(map(tuple, det["key"])) if len(det) else set(map(tuple, act["key"]))):
        entry = {}
        if len(det):
            d = det[det["key"].apply(tuple) == key]
            if len(d):
                fp = d["fp"].value_counts().to_dict()
                decided = fp.get("TRIGGER_FIRST", 0) + fp.get("INVALIDATION_FIRST", 0)
                entry["detected"] = {"n": int(len(d)), **{k2: int(v) for k2, v in fp.items()},
                                     "trigger_first_share_of_decided": round(fp.get("TRIGGER_FIRST", 0) / decided, 3) if decided else None}
        a = act[act["key"].apply(tuple) == key] if len(act) else act
        if len(a):
            res = {h: boot(a[h], a["block"]) for h in ("z5", "z10", "z20", "xz20")}
            res["fav_touch_rate"] = round(float(a["fav_touch"].mean()), 3)
            enough = res["z20"]["n"] >= 100 and res["z20"]["blocks"] >= 20
            res["estimability"] = "ESTIMABLE" if enough else "NOT_ESTIMABLE"
            entry["activated"] = res
        evaluation[" | ".join(key)] = entry
    report["evaluation"] = evaluation
    if len(act):
        report["evaluation_all_activated"] = {h: boot(act[h], act["block"]) for h in ("z5", "z10", "z20", "xz20")}
    return report


if __name__ == "__main__":
    out = main(sys.argv[1])
    Path(sys.argv[2]).write_text(json.dumps(out, indent=1, default=str), encoding="utf-8")
    print(json.dumps({k: v for k, v in out.items() if k not in {"distributions", "evaluation"}}, indent=1, default=str))
