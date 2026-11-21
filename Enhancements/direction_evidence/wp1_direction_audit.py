r"""WP1 audit of the 7 Oct direction study, Part A (ACK 7 Oct 2026). Implements
WP1_DIRECTION_AUDIT_PREREG_20261007.md exactly. Read-only.

    venv\Scripts\python.exe Enhancements\direction_evidence\wp1_direction_audit.py \
        --out Enhancements\direction_evidence\wp1_direction_audit_20261007.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))

from direction_edge_study import HORIZON, SPLIT, Bars, lane_a, load_panel  # noqa: E402

SEEDS = (20261007, 20261008, 20261009, 20261010, 20261011)
MATCH_SEED, PLACEBOS, RESAMPLES, BLOCK_CUTS, HOLM_MIN_EPISODES = 20261007, 5, 2000, 12, 100
SURVIVORS = ("type=SOW -> LPSY continuation|tf=1w|state=ACTIVATED",
             "type=SOW -> LPSY continuation|tf=1mo|state=DETECTED",
             "type=Seller Absorption Breakdown|tf=1mo|state=DETECTED")


def touch(b, i, up, dn, horizon, on):
    """LEVEL categories for an up/down barrier pair: UP / DOWN / NEITHER / AMBIGUOUS / NO_HORIZON."""
    end = i + 1 + horizon
    if end > len(b.c):
        return "NO_HORIZON"
    hi, lo = (b.h[i + 1:end], b.l[i + 1:end]) if on == "hl" else (b.c[i + 1:end], b.c[i + 1:end])
    u, d = np.flatnonzero(hi >= up), np.flatnonzero(lo <= dn)
    fu, fd = (u[0] if len(u) else None), (d[0] if len(d) else None)
    if fu is None and fd is None:
        return "NEITHER"
    if fu is not None and fd is not None and fu == fd:
        return "AMBIGUOUS"
    return "UP" if fd is None or (fu is not None and fu < fd) else "DOWN"


def boot(values, blocks):
    d = pd.DataFrame({"v": values, "b": blocks}).dropna()
    if d.empty:
        return {"n": 0, "blocks": 0, "mean": None, "lo95": None, "hi95": None, "p": None}
    g = d.groupby("b")["v"].agg(["sum", "count"])
    rng = np.random.default_rng(MATCH_SEED)
    idx = rng.integers(0, len(g), size=(RESAMPLES, len(g)))
    means = g["sum"].to_numpy()[idx].sum(1) / g["count"].to_numpy()[idx].sum(1)
    p = min(1.0, 2 * min((means <= 0).mean(), (means >= 0).mean()))
    return {"n": int(len(d)), "blocks": int(len(g)), "mean": round(float(d["v"].mean()), 4),
            "lo95": round(float(np.percentile(means, 2.5)), 4), "hi95": round(float(np.percentile(means, 97.5)), 4),
            "p": round(float(p), 4)}


def episodes(panel):
    p = panel.copy()
    p["setup_date"] = p["id"].str.rsplit("|", n=1).str[-1]
    p = p.sort_values(["cut", "scope"])
    first = p.drop_duplicates(["ticker", "tf", "type", "setup_date", "state"], keep="first")
    return first, {"rows": int(len(panel)), "episodes": int(len(first))}


def part_a(panel, bars, sectors):
    la = lane_a()
    cuts = sorted(panel["cut"].unique())
    block = {c: i // BLOCK_CUTS for i, c in enumerate(cuts)}
    by_cut, cell = {}, {}
    for c in cuts:
        pool = [t for t, b in bars.items() if b.ok and c in b.pos and b.atr[b.pos[c]] > 0]
        by_cut[c] = pool
        if pool:
            atrpct = pd.Series({t: bars[t].atr[bars[t].pos[c]] / bars[t].c[bars[t].pos[c]] for t in pool})
            q = pd.qcut(atrpct.rank(method="first"), 5, labels=False)
            cell[c] = {t: (sectors.get(t, "UNKNOWN"), int(q[t])) for t in pool}
    rngs = [np.random.default_rng(s) for s in SEEDS]
    mrng = np.random.default_rng(MATCH_SEED)
    eps, counts = episodes(panel)
    out, excluded_past, fallback = [], 0, 0
    unresolved = {"hl": {}, "close": {}}
    for r in eps.itertuples(index=False):
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
        obs = {}
        for on in ("hl", "close"):
            h = touch(b, i, up, dn, H, on)
            key = "LEVEL_FIRST" if h in ("UP", "DOWN") and (h == "UP") == (s > 0) else \
                  "INVALIDATION_FIRST" if h in ("UP", "DOWN") else h
            unresolved[on][key] = unresolved[on].get(key, 0) + 1
            obs[on] = None if h not in ("UP", "DOWN") else (1.0 if (h == "UP") == (s > 0) else 0.0)
        if obs["hl"] is None and obs["close"] is None:
            continue
        a_atr, b_atr = a / b.atr[i], bb / b.atr[i]
        pool = [t for t in by_cut[r.cut] if t != r.ticker]
        if not pool:
            continue

        def placebo(donors):
            res = {"hl": [], "close": []}
            for t in donors:
                pb = bars[t]
                j = pb.pos[r.cut]
                cp, at = pb.c[j], pb.atr[j]
                lvl, inv = cp + s * a_atr * at, cp - s * b_atr * at
                u, d = (lvl, inv) if s > 0 else (inv, lvl)
                for on in ("hl", "close"):
                    h2 = touch(pb, j, u, d, H, on)
                    if h2 in ("UP", "DOWN"):
                        res[on].append(1.0 if (h2 == "UP") == (s > 0) else 0.0)
            return res

        seed_res = [placebo([pool[k] for k in g.choice(len(pool), size=min(PLACEBOS, len(pool)), replace=False)])
                    for g in rngs]
        my = cell[r.cut][r.ticker]
        matched = [t for t in pool if cell[r.cut][t] == my]
        if len(matched) < PLACEBOS:
            fallback += 1
            matched = [t for t in pool if cell[r.cut][t][1] == my[1]]
        m_res = placebo([matched[k] for k in mrng.choice(len(matched), size=min(PLACEBOS, len(matched)), replace=False)])
        rec = {"cut": r.cut, "block": block[r.cut], "period": "P1" if r.cut <= SPLIT else "P2", "tf": r.tf,
               "state": r.state, "side": r.dir, "type": r.type, "laneA": (r.tf, r.type, r.state) in la,
               "geom": bb / (a + bb)}
        for on in ("hl", "close"):
            o = obs[on]
            rec[f"obs_{on}"] = o
            pooled = [v for sr in seed_res for v in sr[on]]
            rec[f"edge_pooled_{on}"] = o - np.mean(pooled) if o is not None and pooled else np.nan
            rec[f"edge_matched_{on}"] = o - np.mean(m_res[on]) if o is not None and m_res[on] else np.nan
            rec[f"edge_geom_{on}"] = o - rec["geom"] if o is not None else np.nan
            for k, sr in enumerate(seed_res):
                rec[f"edge_seed{k}_{on}"] = o - np.mean(sr[on]) if o is not None and sr[on] else np.nan
        out.append(rec)
    df = pd.DataFrame(out)
    groups = {"ALL": df}
    for col in ("tf", "state", "side", "laneA"):
        for v, g in df.groupby(col):
            groups[f"{col}={v}"] = g
    for (tf, st), g in df.groupby(["tf", "state"]):
        groups[f"tf={tf}|state={st}"] = g
    for (ty, tf, st), g in df.groupby(["type", "tf", "state"]):
        groups[f"type={ty}|tf={tf}|state={st}"] = g
    res = {}
    for name, g in groups.items():
        entry = {"episodes": int(len(g))}
        for on in ("hl", "close"):
            entry[on] = {"observed": round(float(g[f"obs_{on}"].mean()), 4) if g[f"obs_{on}"].notna().any() else None,
                         "edge_pooled": boot(g[f"edge_pooled_{on}"], g["block"]),
                         "edge_matched": boot(g[f"edge_matched_{on}"], g["block"]),
                         "edge_geometry": boot(g[f"edge_geom_{on}"], g["block"]),
                         "edge_by_seed": [boot(g[f"edge_seed{k}_{on}"], g["block"])["mean"] for k in range(len(SEEDS))],
                         "matched_by_period": {p: boot(gp[f"edge_matched_{on}"], gp["block"]) for p, gp in g.groupby("period")}}
        res[name] = entry
    return res, {"episode_counts": counts, "excluded_already_past": excluded_past,
                 "matched_fallback_to_volatility_only": fallback, "observed_outcomes": unresolved}


def holm(results, family):
    ps = sorted(((results[n]["hl"]["edge_matched"]["p"], n) for n in family
                 if results[n]["hl"]["edge_matched"]["p"] is not None), key=lambda x: x[0])
    m, adj, running = len(ps), {}, 0.0
    for rank, (p, n) in enumerate(ps):
        running = max(running, min(1.0, (m - rank) * p))
        adj[n] = round(running, 4)
    return adj


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--limit", type=int, default=0, help="smoke test: first N tickers per panel")
    args = ap.parse_args()
    uni = pd.read_csv(ROOT / "data" / "universe" / "polygon_liquid_universe.csv")
    sectors = dict(zip(uni["ticker"].str.upper(), uni["sector"].fillna("UNKNOWN")))
    report = {"prereg": "Enhancements/direction_evidence/WP1_DIRECTION_AUDIT_PREREG_20261007.md",
              "survivorship": "SURVIVOR_ONLY_PANELS (today's config/tickers.csv); see survivorship/"}
    for name in ("eval_v4", "eval_v4_holdout"):
        panel = load_panel(name)
        if args.limit:
            panel = panel[panel["ticker"].isin(sorted(panel["ticker"].unique())[: args.limit])]
        bars = {t: Bars(t) for t in panel["ticker"].unique()}
        res, meta = part_a(panel, bars, sectors)
        report[name] = {"part_a": res, "meta": meta}
        print(f"{name}: done", flush=True)
    hold = report["eval_v4_holdout"]["part_a"]
    family = [n for n in hold if n.startswith("type=") and hold[n]["episodes"] >= HOLM_MIN_EPISODES]
    adj = holm(hold, family)
    report["holm"] = {"family_size": len(family), "alpha": 0.05, "adjusted_p": adj}
    verdicts = {}
    for n in SURVIVORS:
        h, o = hold.get(n), report["eval_v4"]["part_a"].get(n)
        if not h or not o:
            verdicts[n] = "NOT_ESTIMABLE"
            continue
        checks = {
            "holdout_matched_lo95_gt_0": (h["hl"]["edge_matched"]["lo95"] or -1) > 0,
            "positive_on_hl_and_close": all((h[on]["edge_matched"]["mean"] or -1) > 0 for on in ("hl", "close")),
            "positive_both_periods_both_panels": all(
                (x["hl"]["matched_by_period"].get(p, {}).get("mean") or -1) > 0 for x in (h, o) for p in ("P1", "P2")),
            "holm_p_lt_0_05": adj.get(n, 1.0) < 0.05,
        }
        verdicts[n] = {"checks": checks, "verdict": "SURVIVES_AUDIT" if all(checks.values()) else "NOT_CONFIRMED"}
    report["survivor_verdicts"] = verdicts
    Path(args.out).write_text(json.dumps(report, indent=1, default=str), encoding="utf-8")
    print(json.dumps({"holm": {"family_size": len(family)}, "survivor_verdicts": verdicts}, indent=1))


if __name__ == "__main__":
    main()
