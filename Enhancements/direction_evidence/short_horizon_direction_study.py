r"""Short-horizon direction study (7 Oct 2026). Implements SHORT_HORIZON_DIRECTION_STUDY_PREREG_20261007.md. Read-only.

    venv\Scripts\python.exe Enhancements\direction_evidence\short_horizon_direction_study.py \
        --out Enhancements\direction_evidence\short_horizon_direction_study_20261007.json
"""
from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "survivorship"))

from measure_survivorship import entity_map, load_bars, load_reference  # noqa: E402
from top_down_bias_study import (daily_inputs, daily_tables, forming_inputs, lag, period_tables,  # noqa: E402
                                 states)

SEED, RESAMPLES, MIN_BLOCKS = 20261007, 2000, 8
N_UNIVERSE, DV_WINDOW, DV_MIN_BARS, TOP, INTRADAY_STOCKS = 3122, 20, 15, 100, 300
HS = (1, 3, 5)
ETFS = ("SPY", "QQQ", "IWM", "DIA", "XLB", "XLC", "XLE", "XLF", "XLI", "XLK", "XLP", "XLRE", "XLU", "XLV", "XLY",
        "SMH")
INTRADAY_DIR = ROOT / "data" / "canonical" / "payloads" / "intraday_bar"


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


def evaluate(df, ret_col, ref_col, block_col="block"):
    """Excess hit over the reference for the side called; overall, halves and by side."""
    d = df.dropna(subset=[ret_col, ref_col]).copy()
    d = d[d[ret_col] != 0]
    d["hit"] = np.where(d["side"] == "UP", d[ret_col] > 0, d[ret_col] < 0).astype(float)
    d["excess"] = d["hit"] - np.where(d["side"] == "UP", d[ref_col], 1 - d[ref_col])
    if d.empty:
        return {"all": {"n": 0}}
    mid = sorted(d["date"].unique())[len(d["date"].unique()) // 2]
    h1, h2 = d[d["date"] < mid], d[d["date"] >= mid]
    return {"all": boot(d["excess"], d[block_col]), "hit_rate": round(float(d["hit"].mean()), 4),
            "H1": boot(h1["excess"], h1[block_col]), "H2": boot(h2["excess"], h2[block_col]),
            "by_side": {s: boot(g["excess"], g[block_col]) for s, g in d.groupby("side")},
            "first": str(d["date"].min()), "last": str(d["date"].max())}


# ------------------------------------------------------------------------------------------------ daily part
def daily_part(limit=0):
    raw = load_bars()
    raw["date"] = pd.to_datetime(raw["date"]).astype("datetime64[ns]")
    active, dl = load_reference(raw.groupby("ticker")["date"].max())
    bars = entity_map(raw, active, dl)
    opens = raw[["date", "ticker", "open"]]
    bars = bars.merge(opens, on=["date", "ticker"], how="left")
    del raw
    wide = {k: bars.pivot(index="date", columns="entity", values=k).astype("float64")
            for k in ("open", "high", "low", "close", "volume")}
    dates, ents = wide["close"].index, wide["close"].columns
    O, H, L, C, V = (wide[k].to_numpy() for k in ("open", "high", "low", "close", "volume"))
    del wide, bars
    atr = pd.DataFrame(np.fmax(H - L, np.fmax(np.abs(H - lag(C, 1)), np.abs(L - lag(C, 1))))) \
        .rolling(14, min_periods=14).mean().to_numpy()
    dv = pd.DataFrame(C * V).rolling(DV_WINDOW, min_periods=DV_MIN_BARS).median().to_numpy()
    daily, weekly, monthly = daily_tables(H, L, C), period_tables(dates, H, L, C, "W-FRI"), \
        period_tables(dates, H, L, C, "M")
    etf_cols = np.array([np.flatnonzero(ents == e)[0] for e in ETFS if e in set(ents)])
    n = len(dates)
    fwd_cc = {h: np.vstack([C[h:] / C[:-h] - 1, np.full((h, C.shape[1]), np.nan)]) for h in HS}
    nxt_open = np.vstack([O[1:], np.full((1, C.shape[1]), np.nan)])
    fwd_oc = {h: np.vstack([C[h:] / nxt_open[:-h] - 1, np.full((h, C.shape[1]), np.nan)]) for h in HS}
    start = max(25, int(np.flatnonzero(monthly["pid"] >= 18)[0]))
    sessions = list(range(start, n - 1))
    if limit:
        sessions = sessions[:limit]
    stock_rows, etf_rows, bias_lookup = [], [], {}
    for k, i in enumerate(sessions):
        ok = ~np.isnan(dv[i]) & ~np.isnan(C[i]) & ~np.isnan(atr[i]) & (atr[i] > 0) & ~np.isnan(C[i - 5])
        js = np.argsort(np.where(ok, -dv[i], np.inf))[: min(N_UNIVERSE, int(ok.sum()))]
        ref = {}
        for h in HS:
            for kind, m in (("cc", fwd_cc[h]), ("oc", fwd_oc[h])):
                r = m[i, js]
                r = r[np.isfinite(r) & (r != 0)]
                ref[f"{kind}{h}"] = float((r > 0).mean()) if len(r) else np.nan
        ind = {"M": forming_inputs(monthly, C, i, js), "W": forming_inputs(weekly, C, i, js),
               "D": daily_inputs(daily, C, i, js)}
        st = {tf: states(ind[tf]) for tf in ind}
        sm, sw, sd = st["M"][0], st["W"][0], st["D"][0]
        bias = np.where((sw == "UP") & (sd == "UP") & np.isin(sm, ["UP", "MIXED"]), "UP",
                        np.where((sw == "DOWN") & (sd == "DOWN") & np.isin(sm, ["DOWN", "MIXED"]), "DOWN", "NONE"))
        aligned = sum((st[tf][1] == np.char.add("TRENDING_", bias.astype(str))).astype(int) for tf in ("W", "D"))
        day = dates[i].strftime("%Y-%m-%d")
        for n_, j in enumerate(js):
            if bias[n_] in ("UP", "DOWN"):
                bias_lookup[(day, ents[j])] = bias[n_]
        picks = []
        biased = np.flatnonzero(np.isin(bias, ["UP", "DOWN"]))
        order = sorted(biased, key=lambda q: (-aligned[q], -np.nan_to_num(ind["W"]["adx"][q], nan=-1),
                                              -np.nan_to_num(ind["D"]["adx"][q], nan=-1), ents[js[q]]))[:TOP]
        picks += [("S1", js[q], bias[q]) for q in order]
        r5 = C[i, js] / C[i - 5, js] - 1
        o5 = np.argsort(r5)
        picks += [("S2", js[q], "UP") for q in o5[:TOP]] + [("S2", js[q], "DOWN") for q in o5[::-1][:TOP]]
        r1 = (C[i, js] / C[i - 1, js] - 1) / (atr[i, js] / C[i, js])
        o1 = np.argsort(np.nan_to_num(r1, nan=0.0))
        picks += [("S3", js[q], "DOWN") for q in o1[:TOP] if r1[q] < 0] + \
                 [("S3", js[q], "UP") for q in o1[::-1][:TOP] if r1[q] > 0]
        for sig, j, side in picks:
            row = {"signal": sig, "date": day, "block": k // 20, "entity": ents[j], "side": side}
            for h in HS:
                row[f"cc{h}"], row[f"oc{h}"] = fwd_cc[h][i, j], fwd_oc[h][i, j]
                row[f"ref_cc{h}"], row[f"ref_oc{h}"] = ref[f"cc{h}"], ref[f"oc{h}"]
            stock_rows.append(row)
        for j in etf_cols:
            prev = C[i, j] / C[i - 1, j] - 1
            pos = np.flatnonzero(js == j)
            b = bias[pos[0]] if len(pos) else "NONE"
            base = {"date": day, "block": k // 20, "entity": ents[j]}
            for h in HS:
                base[f"cc{h}"], base[f"oc{h}"] = fwd_cc[h][i, j], fwd_oc[h][i, j]
            if b in ("UP", "DOWN"):
                etf_rows.append({**base, "signal": "S1", "side": b})
            if np.isfinite(prev) and prev != 0:
                etf_rows.append({**base, "signal": "S3", "side": "UP" if prev > 0 else "DOWN"})
            etf_rows.append({**base, "signal": "ALL", "side": "UP"})
        if k % 50 == 0:
            print(f"daily {k + 1}/{len(sessions)} {day}", flush=True)
    stocks, etfs = pd.DataFrame(stock_rows), pd.DataFrame(etf_rows)
    # ETF reference: each ETF's own up-share over the whole period, per window.
    allrows = etfs[etfs["signal"] == "ALL"]
    for h in HS:
        for kind in ("cc", "oc"):
            col = f"{kind}{h}"
            share = allrows[allrows[col] != 0].groupby("entity")[col].apply(lambda x: float((x > 0).mean()))
            etfs[f"ref_{col}"] = etfs["entity"].map(share)
    etfs = etfs[etfs["signal"] != "ALL"]
    return stocks, etfs, bias_lookup, (dates, ents, C, dv, atr)


# ------------------------------------------------------------------------------------------------ pipeline side
def pipeline_part():
    from direction_edge_study import Bars, load_panel, to_readings
    from domain.structure_behaviour.engine import handoff_thesis
    from domain.structure_behaviour.policy import load_policy
    policy, rows = load_policy(), []
    for name in ("eval_v4", "eval_v4_holdout"):
        panel = load_panel(name)
        bars = {t: Bars(t) for t in panel["ticker"].unique()}
        cuts = sorted(panel["cut"].unique())
        cut_n = {c: n for n, c in enumerate(cuts)}
        for (t, cut), g in panel.groupby(["ticker", "cut"]):
            b = bars.get(t)
            if b is None or not b.ok or cut not in b.pos:
                continue
            i = b.pos[cut]
            side = {"BULL": "UP", "BEAR": "DOWN"}.get(
                handoff_thesis(to_readings(g.to_dict("records"), False, b.c[i]), policy)["thesis__side"])
            if side is None:
                continue
            row = {"panel": name, "date": cut, "block": cut_n[cut] // 2, "entity": t, "side": side}
            for h in HS:
                row[f"cc{h}"] = b.c[i + h] / b.c[i] - 1 if i + h < len(b.c) else np.nan
            rows.append(row)
        print(f"pipeline side: {name} done", flush=True)
    df = pd.DataFrame(rows)
    # Reference: same-cut up-share across all evaluated ticker-cuts of that panel (all panel tickers).
    for h in HS:
        col = f"cc{h}"
        df[f"ref_{col}"] = df.groupby(["panel", "date"])[col].transform(
            lambda x: float((x[x != 0] > 0).mean()) if (x != 0).any() else np.nan)
    return df


# ------------------------------------------------------------------------------------------------ intraday part
def read_session(day: str, ticker: str):
    folder = INTRADAY_DIR / day / ticker
    if not folder.is_dir():
        return None
    files = list(folder.glob("*.parquet"))
    if not files:
        return None
    frames = [pd.read_parquet(f, columns=["open", "close", "timestamp_utc", "acquired_at_utc"]) for f in files]
    d = max(frames, key=lambda f: f["acquired_at_utc"].max()).sort_values("timestamp_utc")
    if len(d) < 70:
        return None
    o, c = d["open"].to_numpy(float), d["close"].to_numpy(float)
    return {"o1": o[0], "c3": c[2], "c6": c[5], "close": c[-1]}


def intraday_part(daily_ctx, bias_lookup, limit=0):
    dates, ents, C, dv, atr = daily_ctx
    pos = {d.strftime("%Y-%m-%d"): i for i, d in enumerate(dates)}
    col_of = {e: j for j, e in enumerate(ents)}
    days = sorted(p.name for p in INTRADAY_DIR.iterdir() if p.is_dir() and p.name in pos)
    if limit:
        days = days[:limit]
    jobs = []
    for d in days:
        i = pos[d]
        ok = ~np.isnan(dv[i - 1])
        top = [ents[j] for j in np.argsort(np.where(ok, -dv[i - 1], np.inf))[:N_UNIVERSE]
               if "|" not in ents[j] and ents[j] not in ETFS][:INTRADAY_STOCKS * 2]
        jobs += [(d, t, "ETF") for t in ETFS] + [(d, t, "STOCK") for t in top]
    with ThreadPoolExecutor(max_workers=16) as pool:
        got = list(pool.map(lambda job: (job, read_session(job[0], job[1])), jobs))
    rows, per_day_stocks = [], {}
    for (d, t, kind), s in got:
        if s is None:
            continue
        if kind == "STOCK":
            per_day_stocks.setdefault(d, [])
            if len(per_day_stocks[d]) >= INTRADAY_STOCKS:
                continue
            per_day_stocks[d].append(t)
        i, j = pos[d], col_of.get(t)
        nxt = C[i + 1, j] if (j is not None and i + 1 < len(dates)) else np.nan
        atr_pct = atr[i - 1, j] / C[i - 1, j] if j is not None else np.nan
        rows.append({"date": d, "entity": t, "kind": kind, "orb15": s["c3"] / s["o1"] - 1, "orb30": s["c6"] / s["o1"] - 1,
                     "r15_close": s["close"] / s["c3"] - 1, "r30_close": s["close"] / s["c6"] - 1,
                     "r15_next": nxt / s["c3"] - 1, "atr_pct": atr_pct,
                     "prev_bias": bias_lookup.get((dates[i - 1].strftime("%Y-%m-%d"), t), "NONE")})
    df = pd.DataFrame(rows)
    day_n = {d: n for n, d in enumerate(sorted(df["date"].unique()))}
    df["block"] = df["date"].map(day_n) // 10
    return df


# ------------------------------------------------------------------------------------------------ report
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--limit", type=int, default=0, help="smoke test: first N sessions")
    args = ap.parse_args()
    stocks, etfs, bias_lookup, ctx = daily_part(args.limit)
    stocks.to_parquet(HERE / "short_horizon_stock_records_20261007.parquet", index=False)
    etfs.to_parquet(HERE / "short_horizon_etf_records_20261007.parquet", index=False)
    pipe = pipeline_part() if not args.limit else pd.DataFrame()
    intra = intraday_part(ctx, bias_lookup, args.limit)
    intra.to_parquet(HERE / "short_horizon_intraday_records_20261007.parquet", index=False)
    report = {"prereg": "Enhancements/direction_evidence/SHORT_HORIZON_DIRECTION_STUDY_PREREG_20261007.md",
              "stocks": {}, "etfs": {}, "pipeline_side": {}, "intraday": {}}
    for sig, g in stocks.groupby("signal"):
        report["stocks"][sig] = {f"{kind}{h}": evaluate(g, f"{kind}{h}", f"ref_{kind}{h}")
                                 for h in HS for kind in ("cc", "oc")}
    for sig, g in etfs.groupby("signal"):
        report["etfs"][sig] = {f"{kind}{h}": evaluate(g, f"{kind}{h}", f"ref_{kind}{h}")
                               for h in HS for kind in ("cc", "oc")}
        report["etfs"][sig]["per_etf_cc1"] = {e: evaluate(x, "cc1", "ref_cc1")["all"] for e, x in g.groupby("entity")}
    if len(pipe):
        report["pipeline_side"] = {f"cc{h}": evaluate(pipe, f"cc{h}", f"ref_cc{h}") for h in HS}
    if len(intra):
        for kind in ("ETF", "STOCK"):
            g = intra[intra["kind"] == kind].copy()
            for orb, ret in (("orb15", "r15_close"), ("orb30", "r30_close"), ("orb15", "r15_next")):
                x = g[g[orb] != 0].copy()
                x["side"] = np.where(x[orb] > 0, "UP", "DOWN")
                if kind == "ETF":
                    share = x[x[ret] != 0].groupby("entity")[ret].apply(lambda r: float((r > 0).mean()))
                    x["ref"] = x["entity"].map(share)
                else:
                    x["score"] = (x[orb].abs() / x["atr_pct"]).replace([np.inf, -np.inf], np.nan)
                    x["ref"] = x.groupby("date")[ret].transform(lambda r: float((r[r != 0] > 0).mean()))
                    x = x.dropna(subset=["score"]).sort_values(["date", "score"], ascending=[True, False])
                    x = x.groupby("date").head(TOP)
                key = f"I1_{orb}_to_{ret.split('_')[1]}"
                report["intraday"].setdefault(kind, {})[key] = evaluate(x, ret, "ref")
                if orb == "orb15" and ret == "r15_close":
                    agree = x[x["side"] == x["prev_bias"]]
                    report["intraday"][kind]["I2_agrees_with_daily_bias"] = evaluate(agree, ret, "ref")
    family = {"S1_stocks_h1": report["stocks"]["S1"]["oc1"], "S1_stocks_h5": report["stocks"]["S1"]["oc5"],
              "S2_stocks_h1": report["stocks"]["S2"]["oc1"], "S2_stocks_h5": report["stocks"]["S2"]["oc5"],
              "S3_stocks_h1": report["stocks"]["S3"]["oc1"], "S3_stocks_h5": report["stocks"]["S3"]["oc5"],
              "S1_etfs_h1": report["etfs"]["S1"]["oc1"], "S1_etfs_h5": report["etfs"]["S1"]["oc5"],
              "S3_etfs_h1": report["etfs"]["S3"]["oc1"], "S3_etfs_h5": report["etfs"]["S3"]["oc5"]}
    twins = {"S1_stocks_h1": report["stocks"]["S1"]["cc1"], "S1_stocks_h5": report["stocks"]["S1"]["cc5"],
             "S2_stocks_h1": report["stocks"]["S2"]["cc1"], "S2_stocks_h5": report["stocks"]["S2"]["cc5"],
             "S3_stocks_h1": report["stocks"]["S3"]["cc1"], "S3_stocks_h5": report["stocks"]["S3"]["cc5"],
             "S1_etfs_h1": report["etfs"]["S1"]["cc1"], "S1_etfs_h5": report["etfs"]["S1"]["cc5"],
             "S3_etfs_h1": report["etfs"]["S3"]["cc1"], "S3_etfs_h5": report["etfs"]["S3"]["cc5"]}
    if report["pipeline_side"]:
        family["S4_pipeline_h1"], family["S4_pipeline_h5"] = report["pipeline_side"]["cc1"], report["pipeline_side"]["cc5"]
    if report["intraday"]:
        family["I1_etfs"] = report["intraday"]["ETF"]["I1_orb15_to_close"]
        family["I1_stocks"] = report["intraday"]["STOCK"]["I1_orb15_to_close"]
    ps = sorted(((v["all"].get("p", 1.0) if v["all"].get("p") is not None else 1.0), k) for k, v in family.items())
    running, holm = 0.0, {}
    for r, (p, k) in enumerate(ps):
        running = max(running, min(1.0, (len(ps) - r) * p))
        holm[k] = round(running, 4)
    verdicts = {}
    for k, v in family.items():
        checks = {"holm_p_lt_0_05": holm[k] < 0.05, "lo95_gt_0": (v["all"].get("lo95") or -1) > 0,
                  "both_halves": all((v[h].get("mean") or -1) > 0 for h in ("H1", "H2"))}
        if k in twins:
            checks["close_to_close_also_positive"] = (twins[k]["all"].get("mean") or -1) > 0
        verdicts[k] = {"mean": v["all"].get("mean"), "lo95": v["all"].get("lo95"), "hit": v.get("hit_rate"),
                       "holm_p": holm[k], "checks": checks,
                       "verdict": "CONFIRMATION_CANDIDATE" if all(checks.values()) else "NOT_ACCEPTED"}
    report["family"] = verdicts
    Path(args.out).write_text(json.dumps(report, indent=1, default=str), encoding="utf-8")
    print(json.dumps(verdicts, indent=1, default=str))


if __name__ == "__main__":
    main()
