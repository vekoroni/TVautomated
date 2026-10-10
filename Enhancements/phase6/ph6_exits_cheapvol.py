"""Phase 6 study E (exits into strength) and V (cheap volatility against forecast).

Implements PHASE6_EXITS_AND_CHEAP_VOL_PREREG_20261009.md exactly; written before any result was read.
Read-only: lp2 trades, canonical daily bars, the pipeline's HAR-RV forecast. Output: ph6_trades.parquet,
ph6_results.json, PH6_RESULTS.md (numbers only).
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import norm

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "Enhancements" / "direction_evidence"))
sys.path.insert(0, str(ROOT / "Enhancements" / "lean_path_test"))
from dir002_replay import read_bars  # noqa: E402
from layer3_forward_variance import _har_rv_forecast  # noqa: E402
from lp3_analyse import TRAIN_END, TEST_START, TEST_END, boot, describe, halves, holm  # noqa: E402

TP = {"E1": 1.5, "E2": 2.0, "E3": 3.0}
TRAIL_ARM, TRAIL_KEEP = 1.5, 0.75
COLS = ["kind", "ticker", "entry_date", "side", "strike_rule", "option_symbol", "strike", "expiry", "spread_pct",
        "entry_bid", "entry_ask", "entry_close", "entry_atm_iv", "policy", "status", "exit_date", "exit_value",
        "exit_source", "ret"]


def bs(S, K, T, sig, call):
    S, K, T, sig = map(np.asarray, (S, K, T, sig))
    T = np.maximum(T, 1e-6)
    d1 = (np.log(S / K) + 0.5 * sig ** 2 * T) / (sig * np.sqrt(T))
    d2 = d1 - sig * np.sqrt(T)
    c = S * norm.cdf(d1) - K * norm.cdf(d2)
    return np.where(call, c, c - S + K)


def implied_vol(price, S, K, T, call):
    lo, hi = 0.01, 5.0
    if not (price > max(0.0, (S - K) if call else (K - S)) and T > 0):
        return None
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        if bs(S, K, T, mid, call) > price:
            hi = mid
        else:
            lo = mid
    return 0.5 * (lo + hi)


def period(d):
    return np.where(d <= TRAIN_END, "TRAIN", np.where((d >= TEST_START) & (d <= TEST_END), "TEST", "OUT"))


def per_trade(t: pd.DataFrame, bars: pd.DataFrame) -> pd.DataFrame:
    out = []
    b = bars.set_index("date")
    for r in t.itertuples(index=False):
        rec = {"row_id": r.row_id, "model_status": "OK"}   # unique per trade (several setups share a contract)
        call = r.side == "BULL"
        exp = pd.Timestamp(r.expiry)
        mid0 = 0.5 * (r.entry_bid + r.entry_ask)
        T0 = max((exp - pd.Timestamp(r.entry_date)).days, 1) / 365.0
        iv = implied_vol(mid0, r.entry_close, r.strike, T0, call)
        path = b[(b.index > r.entry_date) & (b.index <= r.exit_date)]
        if iv is None or path.empty or not (r.entry_ask > 0):
            rec["model_status"] = "NO_IV" if iv is None else "NO_PATH"
            out.append(rec)
            continue
        half = 0.5 * (float(r.spread_pct) if pd.notna(r.spread_pct) else 0.0)
        T = np.array([max((exp - pd.Timestamp(d)).days, 0) / 365.0 for d in path.index])
        ext = (path["high"] if call else path["low"]).to_numpy(float)
        cls = path["close"].to_numpy(float)
        v_ext = bs(ext, r.strike, T, iv, call) * (1 - half)
        v_cls = bs(cls, r.strike, T, iv, call) * (1 - half)
        rec["entry_iv"] = iv
        rec["model_exit_value"] = float(v_cls[-1])
        rec["max_value_mult"] = float(v_ext.max() / r.entry_ask)
        for k, mult in TP.items():
            hit = np.nonzero(v_ext >= mult * r.entry_ask)[0]
            rec[f"ret_{k}"] = (mult - 1.0) if len(hit) else r.ret
            rec[f"{k}_fired"] = bool(len(hit))
        armed, peak, ret4, fired = False, 0.0, r.ret, False
        for v in v_cls:
            if not armed and v >= TRAIL_ARM * r.entry_ask:
                armed = True
            peak = max(peak, v)
            if armed and v <= TRAIL_KEEP * peak:
                ret4, fired = v / r.entry_ask - 1.0, True
                break
        rec["ret_E4"], rec["E4_fired"] = ret4, fired
        out.append(rec)
    return pd.DataFrame(out)


def main():
    t = pd.read_parquet(ROOT / "Enhancements/lean_path_test/lp2_trades.parquet", columns=COLS)
    t = t[(t.status == "TRADED") & (t.policy == "X1") & t.exit_date.notna()].copy().reset_index(drop=True)
    t["row_id"] = np.arange(len(t))
    t["period"] = period(t.entry_date)
    rows, vol_rows = [], []
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else None          # smoke test: first N tickers only
    groups = list(t.groupby("ticker"))[:limit] if limit else t.groupby("ticker")
    for i, (tk, g) in enumerate(groups):
        try:
            bars = read_bars(tk)
        except Exception:
            continue
        bars = bars.sort_values("date").reset_index(drop=True)
        rows.append(per_trade(g, bars))
        lr = np.log(bars["close"].astype(float)).diff()
        for d in g.entry_date.unique():
            r = lr[bars.date <= d].dropna().to_numpy()[-400:]
            f = _har_rv_forecast(r, horizon=20) if len(r) >= 60 else None
            vol_rows.append({"ticker": tk, "entry_date": d, "har20": f["ann_vol"] if f else None})
        if i % 200 == 0:
            print("tickers", i, flush=True)
    m = pd.concat(rows, ignore_index=True)
    n_before = len(t)
    t = t.merge(m, on="row_id", how="left", validate="one_to_one").merge(
        pd.DataFrame(vol_rows).drop_duplicates(["ticker", "entry_date"]), on=["ticker", "entry_date"], how="left",
        validate="many_to_one")
    assert len(t) == n_before, "row count changed in merge"
    t["vol_ratio"] = t.entry_atm_iv / t.har20
    q = t.loc[t.period == "TRAIN", "vol_ratio"].dropna().quantile([0.2, 0.8]).to_list()
    t["vol_group"] = np.where(t.vol_ratio <= q[0], "CHEAP", np.where(t.vol_ratio >= q[1], "RICH",
                              np.where(t.vol_ratio.notna(), "MID", "NOT_MEASURED")))
    t.to_parquet(HERE / "ph6_trades.parquet", index=False)

    fridays = sorted(t.entry_date.unique())
    idx = {d: i for i, d in enumerate(fridays)}
    blk = lambda df: np.array([idx[d] // 4 for d in df.entry_date])  # noqa: E731
    test = t[t.period == "TEST"]
    lean = {s: test[(test.kind == "LEAN") & (test.strike_rule == s)] for s in ("ATM", "D35")}
    plac = test[test.kind == "PLACEBO"]
    res = {"quintile_cuts_train": q, "coverage": {
        "trades": len(t), "test": len(test),
        "model_status": t.model_status.fillna("NOT_RUN").value_counts().to_dict(),
        "vol_group_test": {f"{k}|{g}": int(n) for (k, g), n in test.groupby(["kind", "vol_group"]).size().items()}}}
    # Model check: model sellable value vs the actual exit bid at the X1 exit Friday.
    chk = t[(t.model_status == "OK") & (t.exit_source == "BID") & (t.exit_value > 0)]
    ratio = chk.model_exit_value / chk.exit_value
    res["model_check"] = {s: {"n": int((chk.side == s).sum()), "median_model_over_actual": float(ratio[chk.side == s].median()),
                              "p25": float(ratio[chk.side == s].quantile(0.25)), "p75": float(ratio[chk.side == s].quantile(0.75))}
                          for s in ("BULL", "BEAR")}

    def hyp_mean(df, col):
        d = df.dropna(subset=[col])
        b = boot(d[col].to_numpy(float), blk(d))
        h = halves(d.rename(columns={col: "_v"}), col="_v")
        return {**b, "n": len(d), "halves": h, "same_sign_halves": bool(all(x > 0 for x in h) or all(x < 0 for x in h))}

    def hyp_diff(a, c, col="ret"):
        a, c = a.dropna(subset=[col]), c.dropna(subset=[col])
        b = boot(a[col].to_numpy(float), blk(a), values2=c[col].to_numpy(float), blk2=blk(c))
        dates = sorted(set(a.entry_date) | set(c.entry_date))
        cut = dates[len(dates) // 2] if dates else ""
        h = [float(a[a.entry_date < cut][col].mean() - c[c.entry_date < cut][col].mean()),
             float(a[a.entry_date >= cut][col].mean() - c[c.entry_date >= cut][col].mean())]
        return {**b, "n": [len(a), len(c)], "halves": h,
                "same_sign_halves": bool(all(x > 0 for x in h) or all(x < 0 for x in h))}

    V = {"V1": hyp_mean(lean["ATM"][lean["ATM"].vol_group == "CHEAP"], "ret"),
         "V2": hyp_diff(lean["ATM"][lean["ATM"].vol_group == "CHEAP"], lean["ATM"][lean["ATM"].vol_group == "RICH"]),
         "V3": hyp_diff(plac[plac.vol_group == "CHEAP"], plac[plac.vol_group == "RICH"])}
    E = {}
    a = lean["ATM"][lean["ATM"].model_status == "OK"].copy()
    for k in ("E1", "E2", "E3", "E4"):
        a[f"d_{k}"] = a[f"ret_{k}"] - a["ret"]
        E[k] = hyp_mean(a, f"d_{k}")
    for fam in (V, E):
        hp = holm({k: v.get("p_one_sided", 1.0) for k, v in fam.items()})
        for k, v in fam.items():
            v["p_holm"] = hp[k]
            v["pass"] = bool(v.get("status") == "OK" and v.get("estimate", 0) > 0 and hp[k] < 0.05
                             and v.get("same_sign_halves", False))
    res["V"], res["E"] = V, E
    desc = {}
    for name, df in (("LEAN_ATM", lean["ATM"]), ("LEAN_D35", lean["D35"]), ("PLACEBO_ATM", plac)):
        ok = df[df.model_status == "OK"]
        desc[name] = {"X1": describe(df.ret),
                      **{k: describe(ok[f"ret_{k}"]) for k in ("E1", "E2", "E3", "E4")},
                      "fired": {k: float(ok[f"{k}_fired"].mean()) for k in ("E1", "E2", "E3", "E4")},
                      "max_value_mult_median": float(ok.max_value_mult.median()),
                      "share_reached_1_5x": float((ok.max_value_mult >= 1.5).mean()),
                      "share_reached_2x": float((ok.max_value_mult >= 2.0).mean()),
                      "vol_groups": {g: describe(df[df.vol_group == g].ret) for g in ("CHEAP", "MID", "RICH")}}
    res["describe_test"] = desc
    best = max(("E1", "E2", "E3", "E4"), key=lambda k: E[k].get("estimate", float("-inf")))
    cheap = lean["ATM"][(lean["ATM"].vol_group == "CHEAP") & (lean["ATM"].model_status == "OK")]
    res["combination_cheap_x_best_exit"] = {"best_exit": best, "cheap_x_best": describe(cheap[f"ret_{best}"])}
    (HERE / "ph6_results.json").write_text(json.dumps(res, indent=2, default=str))
    lines = ["# Phase 6 results: exits (E) and cheap volatility (V) - numbers only", ""]
    for fam_name, fam in (("V", V), ("E", E)):
        lines += [f"## Family {fam_name} (ATM, test period)", "", "| Test | n | Estimate | 95% CI | p | Holm p | Halves | Pass |",
                  "|---|---|---|---|---|---|---|---|"]
        for k, v in fam.items():
            ci = v.get("ci95") or [float("nan"), float("nan")]
            lines.append(f"| {k} | {v.get('n')} | {v.get('estimate', float('nan')):+.3f} | "
                         f"[{ci[0]:+.3f}, {ci[1]:+.3f}] | {v.get('p_one_sided', float('nan')):.3f} | {v['p_holm']:.3f} | "
                         f"{v.get('halves', '')} | {'yes' if v['pass'] else 'no'} |")
        lines.append("")
    (HERE / "PH6_RESULTS.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"V": V, "E": E, "model_check": res["model_check"]}, indent=1, default=str)[:4000])


if __name__ == "__main__":
    main()
