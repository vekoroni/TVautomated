r"""Magnitude and relative-strength study (7 Oct 2026). Implements MAGNITUDE_AND_STRENGTH_STUDY_PREREG_20261007.md.
Read-only.

    venv\Scripts\python.exe Enhancements\direction_evidence\magnitude_strength_study.py \
        --out Enhancements\direction_evidence\magnitude_strength_study_20261007.json

R lists are two-sided: the 100 strongest names are UP and the 100 weakest DOWN, evaluated together (signed).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "survivorship"))

from measure_survivorship import entity_map, load_bars, load_reference  # noqa: E402
from top_down_bias_study import boot, first_passage, forming_inputs, lag, period_tables  # noqa: E402

N_UNIVERSE, DV_WINDOW, DV_MIN_BARS = 3122, 20, 15
CUT_STEP, BLOCK_CUTS, LOOKBACK = 10, 6, 252
TOPS = (100, 200)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--limit-cuts", type=int, default=0)
    args = ap.parse_args()
    raw = load_bars()
    raw["date"] = pd.to_datetime(raw["date"]).astype("datetime64[ns]")
    active, dl = load_reference(raw.groupby("ticker")["date"].max())
    bars = entity_map(raw, active, dl)
    del raw
    wide = {k: bars.pivot(index="date", columns="entity", values=k).astype("float64")
            for k in ("high", "low", "close", "volume")}
    dates, ents = wide["close"].index, wide["close"].columns
    H, L, C, V = (wide[k].to_numpy() for k in ("high", "low", "close", "volume"))
    del wide, bars
    atr = pd.DataFrame(np.fmax(H - L, np.fmax(np.abs(H - lag(C, 1)), np.abs(L - lag(C, 1))))) \
        .rolling(14, min_periods=14).mean().to_numpy()
    dv = pd.DataFrame(C * V).rolling(DV_WINDOW, min_periods=DV_MIN_BARS).median().to_numpy()
    logret = np.log(C / lag(C, 1))
    rv20 = pd.DataFrame(logret).rolling(20, min_periods=15).std().to_numpy()
    v5 = pd.DataFrame(V).rolling(5, min_periods=4).mean().to_numpy()
    v50 = pd.DataFrame(V).rolling(50, min_periods=40).mean().to_numpy()
    hi20 = pd.DataFrame(H).rolling(20, min_periods=15).max().to_numpy()
    lo20 = pd.DataFrame(L).rolling(20, min_periods=15).min().to_numpy()
    hi252 = pd.DataFrame(H).rolling(252, min_periods=200).max().to_numpy()
    weekly = period_tables(dates, H, L, C, "W-FRI")
    atrpct = atr / C

    cut_idx = list(range(LOOKBACK, len(dates), CUT_STEP))
    if args.limit_cuts:
        cut_idx = cut_idx[: args.limit_cuts]
    recs = []
    for n_cut, i in enumerate(cut_idx):
        ok = ~np.isnan(dv[i]) & ~np.isnan(C[i]) & ~np.isnan(atr[i]) & (atr[i] > 0)
        js = np.argsort(np.where(ok, -dv[i], np.inf))[: min(N_UNIVERSE, int(ok.sum()))]
        window = atrpct[i - 250:i, js]
        valid = (~np.isnan(window)).sum(0)
        pct = np.where(valid >= 200, (window <= atrpct[i, js]).sum(0) / np.maximum(valid, 1), np.nan)
        adx_w = forming_inputs(weekly, C, i, js)["adx"]
        m1 = (pct <= 0.20) & (adx_w < 20)
        volratio = v5[i, js] / v50[i, js]
        edge = (C[i, js] >= hi20[i, js] - atr[i, js]) | (C[i, js] <= lo20[i, js] + atr[i, js])
        m2 = (volratio >= 1.5) & edge
        mom = C[i - 21, js] / C[i - 252, js] - 1
        near_high = C[i, js] / hi252[i, js]
        end20, end60 = i + 20, i + 60
        ret20 = C[end20, js] / C[i, js] - 1 if end20 < len(dates) else np.full(len(js), np.nan)
        ret60 = C[end60, js] / C[i, js] - 1 if end60 < len(dates) else np.full(len(js), np.nan)
        rel60 = ret60 - np.nanmedian(ret60) if np.isfinite(ret60).any() else ret60
        mvv = np.abs(ret20) / (rv20[i, js] * np.sqrt(20))
        for n, j in enumerate(js):
            rec = {"cut": dates[i].strftime("%Y-%m-%d"), "cut_n": n_cut, "block": n_cut // BLOCK_CUTS,
                   "entity": ents[j], "m1": bool(m1[n]), "m1_rank_key": pct[n], "m2": bool(m2[n]),
                   "m2_rank_key": volratio[n], "mom": mom[n], "near_high": near_high[n], "mvv": mvv[n],
                   "rel60": rel60[n]}
            for hz in (20, 60):
                for on in ("hl", "close"):
                    rec[f"big_{hz}_{on}"] = first_passage(H, L, C, i, j, 3, hz, atr[i, j], on)
            rec["dir_60_hl"] = first_passage(H, L, C, i, j, 2, 60, atr[i, j], "hl")
            rec["dir_60_close"] = first_passage(H, L, C, i, j, 2, 60, atr[i, j], "close")
            recs.append(rec)
        print(f"cut {n_cut + 1}/{len(cut_idx)} {dates[i]:%Y-%m-%d} m1 {int(m1.sum())} m2 {int(m2.sum())}", flush=True)
    df = pd.DataFrame(recs)
    df.to_parquet(HERE / "magnitude_strength_records_20261007.parquet", index=False)
    cuts_sorted = sorted(df["cut"].unique())
    half = cuts_sorted[len(cuts_sorted) // 2]

    def episodes(t, side_col=None):
        t = t.sort_values(["entity", "cut_n"]).copy()
        same = t.groupby("entity")["cut_n"].shift(1) == t["cut_n"] - 1
        if side_col:
            same &= t.groupby("entity")[side_col].shift(1) == t[side_col]
        return t[~same]

    def summarise(ep, col):
        h1, h2 = ep[ep["cut"] < half], ep[ep["cut"] >= half]
        return {"all": boot(ep[col], ep["block"]), "H1": boot(h1[col], h1["block"]), "H2": boot(h2[col], h2["block"])}

    report = {"prereg": "Enhancements/direction_evidence/MAGNITUDE_AND_STRENGTH_STUDY_PREREG_20261007.md",
              "cuts": len(cut_idx), "first_cut": df["cut"].min(), "last_cut": df["cut"].max(),
              "name_cuts": int(len(df)), "M": {}, "R": {}}
    # ---- Part M
    for hz in (20, 60):
        for on in ("hl", "close"):
            col = f"big_{hz}_{on}"
            d = df[df[col].isin(["UP", "DOWN", "AMBIGUOUS", "NEITHER"])].copy()
            d["big"] = (d[col] != "NEITHER").astype(float)
            d["big_ex"] = d["big"] - d["cut"].map(d.groupby("cut")["big"].mean())
            d["mvv_ex"] = d["mvv"] - d["cut"].map(d.groupby("cut")["mvv"].mean())
            report["M"][f"base_rate_{hz}_{on}"] = round(float(d["big"].mean()), 4)
            for sig, key, asc in (("m1", "m1_rank_key", True), ("m2", "m2_rank_key", False)):
                flagged = d[d[sig]].sort_values(["cut", key, "entity"], ascending=[True, asc, True])
                flagged["rank"] = flagged.groupby("cut").cumcount() + 1
                entry = {"flagged_per_cut": round(float(flagged.groupby("cut").size().mean()), 1),
                         "all_flagged": summarise(episodes(flagged), "big_ex")}
                for top in TOPS:
                    ep = episodes(flagged[flagged["rank"] <= top])
                    entry[f"top{top}"] = {"big_excess": summarise(ep, "big_ex"),
                                          "big_rate": round(float(ep["big"].mean()), 4),
                                          "move_vs_vol_excess": summarise(ep.dropna(subset=["mvv_ex"]), "mvv_ex")}
                report["M"].setdefault(sig, {})[f"{hz}_{on}"] = entry
    # ---- Part R
    for sig, key in (("r1", "mom"), ("r2", "near_high")):
        d = df.dropna(subset=[key]).copy()
        d["rk_desc"] = d.groupby("cut")[key].rank(ascending=False, method="first")
        d["rk_asc"] = d.groupby("cut")[key].rank(ascending=True, method="first")
        entry = {}
        for per in (100,):                                  # the list: 100 strongest UP + 100 weakest DOWN
            pick = d[(d["rk_desc"] <= per) | (d["rk_asc"] <= per)].copy()
            pick["side"] = np.where(pick["rk_desc"] <= per, "UP", "DOWN")
            pick["rel_signed"] = np.where(pick["side"] == "UP", pick["rel60"], -pick["rel60"])
            res = {}
            for on in ("hl", "close"):
                col = f"dir_60_{on}"
                r = d[d[col].isin(["UP", "DOWN"])]
                drift = r.groupby("cut")[col].apply(lambda x: (x == "UP").mean())
                p = pick.copy()
                p["hit"] = np.where(p[col].isin(["UP", "DOWN"]), (p[col] == p["side"]).astype(float), np.nan)
                p["dir_ex"] = p["hit"] - np.where(p["side"] == "UP", p["cut"].map(drift), 1 - p["cut"].map(drift))
                ep = episodes(p, "side")
                res[f"first_passage_{on}"] = summarise(ep, "dir_ex")
                res[f"first_passage_{on}_by_side"] = {s: boot(g["dir_ex"], g["block"]) for s, g in ep.groupby("side")}
            ep = episodes(pick, "side")
            res["relative_return_60"] = summarise(ep.dropna(subset=["rel_signed"]), "rel_signed")
            res["relative_return_60_by_side"] = {s: boot(g["rel_signed"], g["block"]) for s, g in ep.groupby("side")}
            entry["top100"] = res
        report["R"][sig] = entry

    # ---- acceptance + Holm across the four primary tests
    def acc_m(sig):
        e = report["M"][sig]["20_hl"]["top100"]["big_excess"]
        c = report["M"][sig]["20_close"]["top100"]["big_excess"]
        return e, {"lo95_gt_0": (e["all"].get("lo95") or -1) > 0,
                   "both_halves": all((e[h].get("mean") or -1) > 0 for h in ("H1", "H2")),
                   "hl_and_close": (e["all"].get("mean") or -1) > 0 and (c["all"].get("mean") or -1) > 0}

    def acc_r(sig):
        e = report["R"][sig]["top100"]["relative_return_60"]
        a = report["R"][sig]["top100"]["first_passage_hl"]
        return e, {"lo95_gt_0": (e["all"].get("lo95") or -1) > 0,
                   "both_halves": all((e[h].get("mean") or -1) > 0 for h in ("H1", "H2")),
                   "both_outcomes": (e["all"].get("mean") or -1) > 0 and (a["all"].get("mean") or -1) > 0}

    tests = {"M1": acc_m("m1"), "M2": acc_m("m2"), "R1": acc_r("r1"), "R2": acc_r("r2")}
    ps = sorted(((v[0]["all"].get("p", 1.0) if v[0]["all"].get("p") is not None else 1.0, k) for k, v in tests.items()))
    running, holm = 0.0, {}
    for r, (p, k) in enumerate(ps):
        running = max(running, min(1.0, (len(ps) - r) * p))
        holm[k] = round(running, 4)
    report["acceptance"] = {k: {"checks": {**v[1], "holm_p_lt_0_05": holm[k] < 0.05}, "holm_p": holm[k],
                                "verdict": "CONFIRMATION_CANDIDATE" if all(v[1].values()) and holm[k] < 0.05
                                else "NOT_ACCEPTED"} for k, v in tests.items()}
    Path(args.out).write_text(json.dumps(report, indent=1, default=str), encoding="utf-8")
    print(json.dumps(report["acceptance"], indent=1))


if __name__ == "__main__":
    main()
