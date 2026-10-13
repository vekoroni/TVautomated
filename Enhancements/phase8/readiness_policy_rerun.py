"""Readiness re-run under READINESS_FIRST_CLOSE_PREREG_AMENDMENT_1_20261012.md (read-only).

Five decomposed policies on one frozen cohort, next-open fills, matched all-days control, ambiguity variants, and the
four validation invariants as hard assertions - each proven by a synthetic manipulated run before the real result is
reported (synthetic controls are labelled and never enter the result). Writes readiness_policy_rerun.json.
"""
from __future__ import annotations

import contextlib
import copy
import json
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
PANELS = {"original": ROOT / "Enhancements/outcomes/beh001/eval_v4/candidates.jsonl",
          "holdout": ROOT / "Enhancements/outcomes/beh001/eval_v4_holdout/candidates.jsonl"}
WINDOW, HORIZON, FAST, BUF, SEED = 20, 10, 3, 0.25, 20261012
POLICIES = ("P0", "P1", "P2", "P3", "P4")
NI_HIT, NI_RET = -0.02, -0.05


class InvariantBreach(AssertionError):
    pass


def audit(results: pd.DataFrame, cohort_keys: set) -> None:
    """The four invariants (frozen cohort, point-in-time eligibility, unique episodes, feasible fills)."""
    for p, g in results.groupby("policy"):
        if set(g["episode"]) != cohort_keys:
            raise InvariantBreach(f"COHORT_MEMBERSHIP_CHANGED:{p}")
        if g["episode"].duplicated().any():
            raise InvariantBreach(f"DUPLICATED_EPISODES:{p}")
    entered = results[results["entered"]]
    if (entered["signal_idx"] < entered["first_eligible_idx"]).any():
        raise InvariantBreach("FUTURE_INFORMATION_IN_SELECTION")
    if (entered["fill_idx"] <= entered["signal_idx"]).any():
        raise InvariantBreach("INFEASIBLE_ENTRY_TIME")


def positive_controls(results: pd.DataFrame, cohort_keys: set) -> dict:
    """SYNTHETIC: each manipulation must be rejected by the audit (never reported as evidence)."""
    out = {}
    entered = results[results["entered"] & (results["policy"] == "P3")]
    rigs = {
        "drop_P3_losses": lambda r: r.drop(entered[entered["hit_loss"] == 0].index[:500]),
        "select_on_future_outcome": lambda r: r.assign(signal_idx=np.where(r["entered"], r["first_eligible_idx"] - 1, r["signal_idx"])),
        "duplicate_P3_winners": lambda r: pd.concat([r, r[(r["policy"] == "P3") & (r["hit_loss"] == 1)].head(500)]),
        "fill_before_signal": lambda r: r.assign(fill_idx=np.where(r["entered"], r["signal_idx"], r["fill_idx"])),
    }
    for name, rig in rigs.items():
        try:
            audit(rig(copy.deepcopy(results)), cohort_keys)
            out[name] = "NOT_DETECTED"
        except InvariantBreach as breach:
            out[name] = f"REJECTED:{str(breach).split(':')[0]}"
    return out


def load_bars(tickers):
    with contextlib.closing(sqlite3.connect(f"file:{(ROOT / 'data/canonical/historical_prices.sqlite').as_posix()}?mode=ro", uri=True)) as conn:
        bars = pd.read_sql_query("SELECT ticker, trading_date AS date, open, high, low, close FROM ohlcv_daily "
                                 "WHERE trading_date >= '2021-06-01' ORDER BY ticker, trading_date", conn)
    series = {}
    for t, g in bars[bars["ticker"].isin(tickers)].groupby("ticker"):
        g = g.reset_index(drop=True)
        prev = g["close"].shift(1)
        tr = np.maximum(g["high"] - g["low"], np.maximum((g["high"] - prev).abs(), (g["low"] - prev).abs()))
        series[t] = {"dates": pd.to_datetime(g["date"]).to_numpy(), "open": g["open"].to_numpy(float),
                     "high": g["high"].to_numpy(float), "low": g["low"].to_numpy(float),
                     "close": g["close"].to_numpy(float), "atr": tr.rolling(14).mean().to_numpy(float)}
    return series


def outcome(s, sig, sign):
    """From the next-open fill after signal index sig. Returns dict or None."""
    j = sig + 1
    a = s["atr"][sig]
    if j + HORIZON - 1 >= len(s["close"]) or not np.isfinite(a) or a <= 0:
        return None
    fill = s["open"][j]
    up, dn = fill + sign * a, fill - sign * a
    res = None
    for k in range(j, j + HORIZON):
        fav = s["high"][k] >= up if sign > 0 else s["low"][k] <= up
        adv = s["low"][k] <= dn if sign > 0 else s["high"][k] >= dn
        if fav or adv:
            res = "AMBIGUOUS" if (fav and adv) else ("WIN" if fav else "LOSS")
            break
    res = res or "LOSS"
    fast = any((s["high"][k] >= up if sign > 0 else s["low"][k] <= up) for k in range(j, j + FAST))
    ret = sign * (s["close"][j + HORIZON - 1] - fill) / a
    return {"fill_idx": j, "res": res, "ret": ret, "fast": float(fast)}


def signals(s, i0, sign, trig):
    c, atr = s["close"], s["atr"]
    end = min(len(c), i0 + WINDOW)
    beyond = [sign * (c[i] - trig) for i in range(i0, end)]
    buf = [np.isfinite(atr[i]) and sign * (c[i] - trig) > BUF * atr[i] for i in range(i0, end)]
    out = {p: None for p in POLICIES}
    for n, i in enumerate(range(i0, end)):
        if out["P0"] is None and beyond[n] > 0:
            out["P0"] = i
        if out["P1"] is None and buf[n]:
            out["P1"] = i
        if out["P2"] is None and n > 0 and beyond[n] > 0 and beyond[n - 1] > 0:
            out["P2"] = i
        if out["P3"] is None and n > 0 and buf[n] and buf[n - 1]:
            out["P3"] = i
    if out["P3"] is not None:
        i = out["P3"]
        after = [sign * (c[k] - trig) for k in range(i + 1, min(len(c), i + 3))]
        out["P4"] = i + 2 if len(after) == 2 and all(x >= 0 for x in after) else None
    return out


def run_panel(name, path, series, rng):
    c = pd.read_json(path, lines=True)
    c = c[(c["tf"] == "1d") & (c["state"] == "DETECTED") & c["dir"].isin(["BULL", "BEAR"]) & c["trigger"].notna()]
    c = c.sort_values("cut").drop_duplicates("id", keep="first")
    c["episode"] = (c["ticker"] + "|" + c["dir"] + "|" + c["trigger"].round(2).astype(str) + "|" + c["cut"].astype(str).str[:10])
    c = c.drop_duplicates("episode", keep="first")
    c = c[c["ticker"].isin(series)]
    rows, control = [], {}
    for r in c.itertuples():
        s = series[r.ticker]
        sign = 1.0 if r.dir == "BULL" else -1.0
        i0 = int(np.searchsorted(s["dates"], np.datetime64(pd.Timestamp(r.cut)), side="right"))
        sig = signals(s, i0, sign, float(r.trigger))
        for p in POLICIES:
            o = outcome(s, sig[p], sign) if sig[p] is not None else None
            rows.append({"episode": r.episode, "cut": str(r.cut)[:10], "type": r.type, "policy": p,
                         "first_eligible_idx": i0, "signal_idx": sig[p] if o else -1, "entered": o is not None,
                         "fill_idx": o["fill_idx"] if o else -1, "res": o["res"] if o else "NO_ENTRY",
                         "ret": o["ret"] if o else 0.0, "fast": o["fast"] if o else np.nan,
                         "delay_vs_p0": (sig[p] - sig["P0"]) if (o and sig["P0"] is not None) else np.nan})
        for d in range(max(14, i0 - 60), i0):
            key = (r.ticker, r.dir, d)
            if key not in control:
                o = outcome(s, d, sign)
                if o:
                    control[key] = {"cut": str(r.cut)[:10], "res": o["res"]}
    res = pd.DataFrame(rows)
    res["hit_loss"] = (res["res"] == "WIN").astype(float)                 # ambiguous = loss (primary)
    res["hit_win"] = res["res"].isin(["WIN", "AMBIGUOUS"]).astype(float)
    cohort = set(c["episode"])
    controls = positive_controls(res, cohort)
    audit(res, cohort)                                                       # the real result must pass
    ctl = pd.DataFrame(control.values())
    ctl["hit"] = (ctl["res"] == "WIN").astype(float)
    cuts = np.array(sorted(res["cut"].unique()))
    cut_pos = {k: i for i, k in enumerate(cuts)}

    def per_cut(frame, col):
        """Sum and count of ``col`` per cut date (pre-aggregated: the bootstrap resamples these totals)."""
        g = frame.groupby("cut")[col].agg(["sum", "size"])
        s, n = np.zeros(len(cuts)), np.zeros(len(cuts))
        for k, (a, b) in g.iterrows():
            if k in cut_pos:
                s[cut_pos[k]], n[cut_pos[k]] = a, b
        return s, n

    weights = rng.multinomial(len(cuts), np.full(len(cuts), 1.0 / len(cuts)), size=2000)   # cut-date resamples

    def rate(stat):
        s, n = stat
        return (weights @ s) / np.maximum(weights @ n, 1e-12)

    def ci(diff):
        return [round(float(np.percentile(diff, q)), 4) for q in (2.5, 97.5)]

    ent = lambda d, p: d[(d["policy"] == p) & d["entered"]]
    summary = {"episodes": len(cohort), "control_obs": len(ctl), "control_hit": round(ctl["hit"].mean(), 4),
               "synthetic_positive_controls": controls, "policies": {}}
    for p in POLICIES:
        e = ent(res, p)
        allp = res[res["policy"] == p]
        summary["policies"][p] = {
            "entries": int(len(e)), "entry_rate": round(len(e) / len(cohort), 4),
            "hit_ambiguous_loss": round(e["hit_loss"].mean(), 4), "hit_ambiguous_win": round(e["hit_win"].mean(), 4),
            "hit_ambiguous_excluded": round(e[e["res"] != "AMBIGUOUS"]["hit_loss"].mean(), 4),
            "ret_atr_10": round(e["ret"].mean(), 4), "p_fast_3": round(e["fast"].mean(), 4),
            "expectancy_per_episode_atr": round(allp["ret"].mean(), 4),
            "median_delay_vs_P0_sessions": float(e["delay_vs_p0"].median()) if len(e) else None,
            "minus_control_hit_ci": ci(rate(per_cut(e, "hit_loss")) - rate(per_cut(ctl, "hit"))),
        }
    e0, e3 = ent(res, "P0"), ent(res, "P3")
    summary["P0_minus_P3"] = {
        "hit_ci": ci(rate(per_cut(e0, "hit_loss")) - rate(per_cut(e3, "hit_loss"))),
        "ret_ci": ci(rate(per_cut(e0, "ret")) - rate(per_cut(e3, "ret"))),
    }
    p0, p3 = summary["P0_minus_P3"]["hit_ci"], summary["P0_minus_P3"]["ret_ci"]
    summary["P0_non_inferior_to_P3"] = bool(p0[0] > NI_HIT and p3[0] > NI_RET)
    top = res[res["policy"].isin(["P0", "P3"]) & res["entered"]].groupby(["type", "policy"])["hit_loss"].agg(["mean", "size"])
    summary["descriptive_by_type"] = {f"{t}|{p}": [round(m, 3), int(n)] for (t, p), (m, n) in top.iterrows() if n >= 300}
    return summary, c[["ticker", "cut"]]


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--panel", choices=list(PANELS))
    parser.add_argument("--combine", action="store_true")
    args = parser.parse_args()
    here = Path(__file__)
    if args.combine:
        out = {p: json.loads(here.with_name(f"readiness_policy_rerun_{p}.json").read_text(encoding="utf-8")) for p in PANELS}
        keys = {p: set(map(tuple, out[p].pop("_ticker_cut"))) for p in PANELS}
        out["cross_panel_ticker_cut_overlap"] = len(keys["original"] & keys["holdout"])
        out["decision_inputs"] = {"P0_non_inferior_both": all(out[p]["P0_non_inferior_to_P3"] for p in PANELS),
                                  "edge_vs_control_both": {pol: all(out[p]["policies"][pol]["minus_control_hit_ci"][0] > 0
                                                                    for p in PANELS) for pol in POLICIES}}
        here.with_suffix(".json").write_text(json.dumps(out, indent=1, default=str), encoding="utf-8")
        print(json.dumps(out, indent=1, default=str))
        return
    rng = np.random.default_rng(SEED + (0 if args.panel == "original" else 1))
    tickers = set(pd.read_json(PANELS[args.panel], lines=True)["ticker"])
    series = load_bars(tickers)
    summary, keys = run_panel(args.panel, PANELS[args.panel], series, rng)
    summary["_ticker_cut"] = keys.astype(str).values.tolist()
    here.with_name(f"readiness_policy_rerun_{args.panel}.json").write_text(json.dumps(summary, indent=1, default=str),
                                                                            encoding="utf-8")
    print(json.dumps({k: v for k, v in summary.items() if k != "_ticker_cut"}, indent=1, default=str))


if __name__ == "__main__":
    main()
