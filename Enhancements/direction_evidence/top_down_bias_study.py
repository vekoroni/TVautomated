r"""Top-down bias study (ACK 7 Oct 2026). Implements TOP_DOWN_BIAS_STUDY_PREREG_20261007.md exactly. Read-only.

    venv\Scripts\python.exe Enhancements\direction_evidence\top_down_bias_study.py \
        --out Enhancements\direction_evidence\top_down_bias_study_20261007.json

Survivorship-free point-in-time universe from survivorship/ (Polygon grouped daily, delisted names included).
Monthly/weekly indicators at a cut use the completed bars before the cut's period plus the forming
period-to-date bar - exactly what the chart shows at the cut, nothing later.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "survivorship"))

from measure_survivorship import entity_map, load_bars, load_reference  # noqa: E402

SEED, RESAMPLES = 20261007, 2000
N_UNIVERSE, DV_WINDOW, DV_MIN_BARS = 3122, 20, 15
CUT_STEP, BLOCK_CUTS, MIN_BLOCKS = 10, 6, 8
KS, HORIZONS, PRIMARY = (2, 3), (20, 60), (2, 60)
TOPS = (100, 200)
ADX_LEN, ADX_TREND = 14, 25.0
FIELDS = ("close", "ma5", "ma5_prev", "roc", "rocma", "adx", "adx_prev", "pdi", "mdi")


# ---------------------------------------------------------------- indicators (ACK's charts), vectorised
# Wilder smoothing = exponential average with alpha 1/14 seeded at the first value (pandas ewm, adjust=False).
# ADX is reported only after 2 x 14 + 1 valid bars so the seed has faded.
def rma(x: np.ndarray) -> np.ndarray:
    return pd.DataFrame(x).ewm(alpha=1.0 / ADX_LEN, adjust=False, ignore_na=True).mean().to_numpy()


def lag(x: np.ndarray, n: int) -> np.ndarray:
    return np.vstack([np.full((n, x.shape[1]), np.nan), x[:-n]])


def dmi_tables(h, l, c):
    """Smoothed TR/+DM/-DM, +DI/-DI and ADX for each bar (rows) and name (columns)."""
    ph, pl, pc = lag(h, 1), lag(l, 1), lag(c, 1)
    up, dn = h - ph, pl - l
    pdm = np.where((up > dn) & (up > 0), up, 0.0)
    mdm = np.where((dn > up) & (dn > 0), dn, 0.0)
    tr = np.fmax(h - l, np.fmax(np.abs(h - pc), np.abs(l - pc)))
    gap = np.isnan(c) | np.isnan(pc)
    pdm[gap], mdm[gap], tr[gap] = np.nan, np.nan, np.nan
    s_tr, s_p, s_m = rma(tr), rma(pdm), rma(mdm)
    with np.errstate(divide="ignore", invalid="ignore"):
        pdi, mdi = 100 * s_p / s_tr, 100 * s_m / s_tr
        dx = 100 * np.abs(pdi - mdi) / (pdi + mdi)
    adx = rma(dx)
    adx[np.cumsum(~np.isnan(c), axis=0) < 2 * ADX_LEN + 1] = np.nan
    return {"s_tr": s_tr, "s_p": s_p, "s_m": s_m, "pdi": pdi, "mdi": mdi, "adx": adx}


def daily_tables(H, L, C):
    t = dmi_tables(H, L, C)
    t["ma5"] = pd.DataFrame(C).rolling(5).mean().to_numpy()
    t["roc"] = 100 * (C / lag(C, 12) - 1)
    t["rocma"] = pd.DataFrame(t["roc"]).rolling(6).mean().to_numpy()
    return t


def daily_inputs(t, C, i, js):
    return {"close": C[i, js], "ma5": t["ma5"][i, js], "ma5_prev": t["ma5"][i - 1, js], "roc": t["roc"][i, js],
            "rocma": t["rocma"][i, js], "adx": t["adx"][i, js], "adx_prev": t["adx"][i - 1, js],
            "pdi": t["pdi"][i, js], "mdi": t["mdi"][i, js]}


def period_tables(dates, H, L, C, rule):
    """Completed period bars (max high, min low, last close) with indicator tables, plus each day's
    period-to-date high/low (the forming bar at any cut)."""
    pid = pd.factorize(dates.to_period(rule), sort=True)[0]

    def grouped(m):
        return pd.DataFrame(m).groupby(pid)

    ph, pl, pc = grouped(H).max().to_numpy(), grouped(L).min().to_numpy(), grouped(C).last().to_numpy()
    t = dmi_tables(ph, pl, pc)
    t.update(pid=pid, ph=ph, pl=pl, pc=pc, fh=grouped(H).cummax().to_numpy(), fl=grouped(L).cummin().to_numpy())
    t["roc"] = 100 * (pc / lag(pc, 12) - 1)
    return t


def forming_inputs(t, C, i, js):
    """Indicators on the bar forming at day i: completed bars before its period plus the period-to-date bar."""
    p = int(t["pid"][i])
    if p < 18:
        return {k: np.full(len(js), np.nan) for k in FIELDS}
    pc, cf, hf, lf = t["pc"][:, js], C[i, js], t["fh"][i, js], t["fl"][i, js]
    q = p - 1
    roc_f = 100 * (cf / pc[p - 12] - 1)
    tr_f = np.fmax(hf - lf, np.fmax(np.abs(hf - pc[q]), np.abs(lf - pc[q])))
    up, dn = hf - t["ph"][q, js], t["pl"][q, js] - lf
    pdm_f = np.where((up > dn) & (up > 0), up, 0.0)
    mdm_f = np.where((dn > up) & (dn > 0), dn, 0.0)
    a = 1.0 / ADX_LEN
    s_tr = t["s_tr"][q, js] + a * (tr_f - t["s_tr"][q, js])
    s_p = t["s_p"][q, js] + a * (pdm_f - t["s_p"][q, js])
    s_m = t["s_m"][q, js] + a * (mdm_f - t["s_m"][q, js])
    with np.errstate(divide="ignore", invalid="ignore"):
        pdi, mdi = 100 * s_p / s_tr, 100 * s_m / s_tr
        dx = 100 * np.abs(pdi - mdi) / (pdi + mdi)
    adx_prev = t["adx"][q, js]
    return {"close": cf, "ma5": (pc[p - 4:p].sum(0) + cf) / 5, "ma5_prev": pc[p - 5:p].mean(0), "roc": roc_f,
            "rocma": (t["roc"][p - 5:p, js].sum(0) + roc_f) / 6, "adx": adx_prev + a * (dx - adx_prev),
            "adx_prev": adx_prev, "pdi": pdi, "mdi": mdi}


def states(ind):
    """Timeframe state (UP / DOWN / MIXED / UNAVAILABLE) and strength tag, vectorised."""
    avail = ~(np.isnan(ind["ma5"]) | np.isnan(ind["ma5_prev"]) | np.isnan(ind["roc"]) | np.isnan(ind["rocma"]))
    up = (ind["close"] > ind["ma5"]) & (ind["ma5"] > ind["ma5_prev"]) & (ind["roc"] > ind["rocma"])
    dn = (ind["close"] < ind["ma5"]) & (ind["ma5"] < ind["ma5_prev"]) & (ind["roc"] < ind["rocma"])
    state = np.where(~avail, "UNAVAILABLE", np.where(up, "UP", np.where(dn, "DOWN", "MIXED")))
    adx_ok = ~(np.isnan(ind["adx"]) | np.isnan(ind["adx_prev"]))
    trending = adx_ok & (ind["adx"] >= ADX_TREND) & (ind["adx"] > ind["adx_prev"])
    strength = np.where(~adx_ok, "ADX_UNAVAILABLE",
                        np.where(trending, np.where(ind["pdi"] > ind["mdi"], "TRENDING_UP", "TRENDING_DOWN"), "WEAK"))
    return state, strength


# ---------------------------------------------------------------- statistics and outcome
def boot(values, blocks):
    d = pd.DataFrame({"v": values, "b": blocks}).dropna()
    if d.empty:
        return {"n": 0, "blocks": 0, "mean": None}
    g = d.groupby("b")["v"].agg(["sum", "count"])
    res = {"n": int(len(d)), "blocks": int(len(g)), "mean": round(float(d["v"].mean()), 4)}
    if len(g) < MIN_BLOCKS:
        res["inference"] = f"NOT_MADE_FEWER_THAN_{MIN_BLOCKS}_BLOCKS"
        return res
    rng = np.random.default_rng(SEED)
    idx = rng.integers(0, len(g), size=(RESAMPLES, len(g)))
    means = g["sum"].to_numpy()[idx].sum(1) / g["count"].to_numpy()[idx].sum(1)
    res.update(lo95=round(float(np.percentile(means, 2.5)), 4), hi95=round(float(np.percentile(means, 97.5)), 4),
               p=round(float(min(1.0, 2 * min((means <= 0).mean(), (means >= 0).mean()))), 4))
    return res


def first_passage(H, L, C, i, j, k, horizon, atr, on):
    end = i + 1 + horizon
    if end > H.shape[0]:
        return "NO_HORIZON"
    c0 = C[i, j]
    up, dn = c0 + k * atr, c0 - k * atr
    hi, lo = (H[i + 1:end, j], L[i + 1:end, j]) if on == "hl" else (C[i + 1:end, j], C[i + 1:end, j])
    u, d = np.flatnonzero(hi >= up), np.flatnonzero(lo <= dn)
    fu, fd = (u[0] if len(u) else None), (d[0] if len(d) else None)
    if fu is None and fd is None:
        traded = int((~np.isnan(C[i + 1:end, j])).sum())
        return "DELISTED_BEFORE_RESOLUTION" if traded < horizon * 0.5 else "NEITHER"
    if fu is not None and fd is not None and fu == fd:
        return "AMBIGUOUS"
    return "UP" if fd is None or (fu is not None and fu < fd) else "DOWN"


# ---------------------------------------------------------------- study
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--limit-cuts", type=int, default=0, help="smoke test: first N cuts only")
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
    daily = daily_tables(H, L, C)
    weekly = period_tables(dates, H, L, C, "W-FRI")
    monthly = period_tables(dates, H, L, C, "M")

    start = int(np.flatnonzero(monthly["pid"] >= 18)[0])          # monthly ROC(12) + 6-bar MA computable
    cut_idx = list(range(start, len(dates), CUT_STEP))
    if args.limit_cuts:
        cut_idx = cut_idx[: args.limit_cuts]
    recs = []
    for n_cut, i in enumerate(cut_idx):
        ok = ~np.isnan(dv[i]) & ~np.isnan(C[i]) & ~np.isnan(atr[i]) & (atr[i] > 0)
        js = np.argsort(np.where(ok, -dv[i], np.inf))[: min(N_UNIVERSE, int(ok.sum()))]
        ind = {"M": forming_inputs(monthly, C, i, js), "W": forming_inputs(weekly, C, i, js),
               "D": daily_inputs(daily, C, i, js)}
        st = {tf: states(ind[tf]) for tf in ind}
        sm, sw, sd = st["M"][0], st["W"][0], st["D"][0]
        bias = np.where((sw == "UP") & (sd == "UP") & np.isin(sm, ["UP", "MIXED"]), "UP",
                        np.where((sw == "DOWN") & (sd == "DOWN") & np.isin(sm, ["DOWN", "MIXED"]), "DOWN",
                                 "NO_BIAS"))
        bias = np.where((sm == "UNAVAILABLE") | (sw == "UNAVAILABLE") | (sd == "UNAVAILABLE"), "UNAVAILABLE", bias)
        # Amendment A1 (before any result): monthly ADX is unreliable on 5 years of bars (MSFT check: 23.5 vs the
        # chart's 12.6), so only weekly and daily strength count; monthly strength is reported, never ranked.
        aligned = sum((st[tf][1] == np.char.add("TRENDING_", bias.astype(str))).astype(int)
                      for tf in ("W", "D"))
        m_completion = int((monthly["pid"][: i + 1] == monthly["pid"][i]).sum())
        w_completion = int((weekly["pid"][: i + 1] == weekly["pid"][i]).sum())
        for n, j in enumerate(js):
            rec = {"cut": dates[i].strftime("%Y-%m-%d"), "cut_n": n_cut, "block": n_cut // BLOCK_CUTS,
                   "entity": ents[j], "bias": str(bias[n]), "pattern": f"{sm[n]}|{sw[n]}|{sd[n]}",
                   "strength": f"{st['M'][1][n]}|{st['W'][1][n]}|{st['D'][1][n]}",
                   "aligned_trending": int(aligned[n]), "adx_w": ind["W"]["adx"][n], "adx_d": ind["D"]["adx"][n],
                   "m_completion": m_completion, "w_completion": w_completion}
            for k in KS:
                for hz in HORIZONS:
                    for on in ("hl", "close"):
                        rec[f"o_{k}_{hz}_{on}"] = first_passage(H, L, C, i, j, k, hz, atr[i, j], on)
            recs.append(rec)
        print(f"cut {n_cut + 1}/{len(cut_idx)} {dates[i]:%Y-%m-%d} biased "
              f"{int(np.isin(bias, ['UP', 'DOWN']).sum())}", flush=True)
    df = pd.DataFrame(recs)
    df.to_parquet(HERE / "top_down_bias_records_20261007.parquet", index=False)

    report = {"prereg": "Enhancements/direction_evidence/TOP_DOWN_BIAS_STUDY_PREREG_20261007.md",
              "cuts": len(cut_idx), "first_cut": df["cut"].min(), "last_cut": df["cut"].max(),
              "name_cuts": int(len(df)), "bias_counts": df["bias"].value_counts().to_dict(), "results": {}}
    cuts_sorted = sorted(df["cut"].unique())
    half = cuts_sorted[len(cuts_sorted) // 2]
    for k in KS:
        for hz in HORIZONS:
            for on in ("hl", "close"):
                col = f"o_{k}_{hz}_{on}"
                res = df[df[col].isin(["UP", "DOWN"])]
                drift = res.groupby("cut")[col].apply(lambda x: (x == "UP").mean())
                biased = df[df["bias"].isin(["UP", "DOWN"])].copy()
                biased["drift_up"] = biased["cut"].map(drift)
                biased["hit"] = np.where(biased[col].isin(["UP", "DOWN"]),
                                         (biased[col] == biased["bias"]).astype(float), np.nan)
                biased["excess"] = biased["hit"] - np.where(biased["bias"] == "UP", biased["drift_up"],
                                                            1 - biased["drift_up"])
                biased = biased.sort_values(["cut", "aligned_trending", "adx_w", "adx_d", "entity"],
                                            ascending=[True, False, False, False, True])
                biased["rank"] = biased.groupby("cut").cumcount() + 1
                entry = {"outcomes_biased": biased[col].value_counts().to_dict(),
                         "all_biased": boot(biased["excess"], biased["block"]),
                         "by_side": {s: boot(g["excess"], g["block"]) for s, g in biased.groupby("bias")}}
                for top in TOPS:
                    t = biased[biased["rank"] <= top].sort_values(["entity", "cut_n"]).copy()
                    prev_n = t.groupby("entity")["cut_n"].shift(1)
                    prev_b = t.groupby("entity")["bias"].shift(1)
                    ep = t[~((prev_n == t["cut_n"] - 1) & (prev_b == t["bias"]))]
                    h1, h2 = ep[ep["cut"] < half], ep[ep["cut"] >= half]
                    entry[f"top{top}"] = {
                        "episodes": boot(ep["excess"], ep["block"]),
                        "episodes_hit_rate": round(float(ep["hit"].mean()), 4),
                        "all_appearances": boot(t["excess"], t["block"]),
                        "halves": {"H1": boot(h1["excess"], h1["block"]), "H2": boot(h2["excess"], h2["block"])},
                        "by_side": {s: boot(g["excess"], g["block"]) for s, g in ep.groupby("bias")},
                        "unresolved_share": round(float(ep[col].isin(
                            ["NEITHER", "AMBIGUOUS", "DELISTED_BEFORE_RESOLUTION"]).mean()), 4)}
                report["results"][f"k={k}|h={hz}|{on}"] = entry

    # Secondary, exploratory: 27 patterns, train on the first half, Holm, test on the second (primary event).
    col = f"o_{PRIMARY[0]}_{PRIMARY[1]}_hl"
    res = df[df[col].isin(["UP", "DOWN"])].copy()
    res["up"] = (res[col] == "UP").astype(float)
    res["ex_up"] = res["up"] - res["cut"].map(res.groupby("cut")["up"].mean())
    train, test = res[res["cut"] < half], res[res["cut"] >= half]
    pats = {}
    for p, g in train.groupby("pattern"):
        if "UNAVAILABLE" not in p and len(g) >= 500:
            b = boot(g["ex_up"], g["block"])
            if b.get("p") is not None:
                pats[p] = b
    running, adj = 0.0, {}
    for r, (p, b) in enumerate(sorted(pats.items(), key=lambda x: x[1]["p"])):
        running = max(running, min(1.0, (len(pats) - r) * b["p"]))
        adj[p] = round(running, 4)
    chosen = {p: ("UP" if pats[p]["mean"] > 0 else "DOWN") for p in adj if adj[p] < 0.05}
    tested = test[test["pattern"].isin(chosen)].copy()
    tested["excess"] = np.where(tested["pattern"].map(chosen) == "UP", tested["ex_up"], -tested["ex_up"])
    report["secondary_exploratory"] = {"train_patterns": {p: {**pats[p], "holm_p": adj[p]} for p in pats},
                                       "chosen": chosen, "test": boot(tested["excess"], tested["block"])}

    p_res = report["results"][f"k={PRIMARY[0]}|h={PRIMARY[1]}|hl"]["top100"]
    c_res = report["results"][f"k={PRIMARY[0]}|h={PRIMARY[1]}|close"]["top100"]
    checks = {
        "top100_lo95_gt_0": (p_res["episodes"].get("lo95") or -1) > 0,
        "both_halves_positive": all((p_res["halves"][x].get("mean") or -1) > 0 for x in ("H1", "H2")),
        "closes_and_hl_positive": (p_res["episodes"].get("mean") or -1) > 0
                                  and (c_res["episodes"].get("mean") or -1) > 0,
    }
    report["acceptance"] = {"checks": checks,
                            "verdict": "CONFIRMATION_CANDIDATE" if all(checks.values()) else "NOT_ACCEPTED"}
    Path(args.out).write_text(json.dumps(report, indent=1, default=str), encoding="utf-8")
    print(json.dumps({"acceptance": report["acceptance"], "top100": p_res["episodes"],
                      "bias_counts": report["bias_counts"]}, indent=1, default=str))


if __name__ == "__main__":
    main()
