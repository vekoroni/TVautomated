"""Structural edge study, stage 2 (read-only): statistics for the trades built by build_short_vol_trades.py.

Per tenor x strategy x liquidity band (every leg's (ask - bid) / mid <= 10% / 20% / 35%, plus all
two-sided) x exit variant (hold / mid / tp50):
  trades, entry sessions, tickers, mean / median return per unit of risk (defined-risk: max loss;
  naked: 20% of underlying notional as a stated margin proxy), win rate, worst 1% / 5% quantiles,
  concentration (sum of the worst 5% trades vs gross gains and vs net total), entry spread cost
  (mid credit - fill credit, per unit of risk), and uncertainty by bootstrap over ENTRY SESSIONS
  (2,000 resamples; moving blocks of consecutive sessions, 4 weekly sessions for 20-45 DTE and 2 for
  7-20 DTE, because holding periods overlap; plus an i.i.d. session bootstrap for reference).
Breakdowns (band 20% and 35%): IV / EWMA-forecast band, jump window (a daily move > 4x the entry EWMA
daily sigma before expiry), underlying move over the hold, entry quarter.

  venv\\Scripts\\python.exe Enhancements\\structural_edge\\analyse_short_vol_trades.py
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
TRADES = HERE / "short_vol_trades.parquet"
OUT_JSON = HERE / "structural_edge_results.json"
OUT_MD = HERE / "structural_edge_tables.md"
BANDS = {"le10": 0.10, "le20": 0.20, "le35": 0.35, "all_two_sided": np.inf}
VARIANTS = {"hold": "ret_hold", "mid": "ret_mid", "tp50": "ret_tp50"}
BLOCK = {"t20_45": 4, "t07_20": 2}
N_BOOT = 2000
IV_BANDS = [0, 0.8, 1.0, 1.2, 1.5, 2.0, np.inf]
IV_LABELS = ["<=0.8", "0.8-1.0", "1.0-1.2", "1.2-1.5", "1.5-2.0", ">2.0"]
JUMP_MULTIPLE = 4.0
STRATS = ["short_straddle", "short_strangle_25d", "iron_condor_25_15", "put_credit_spread_25_15"]
rng = np.random.default_rng(20260917)


def bootstrap(frame, col, block):
    g = frame.groupby("entry")[col].agg(["sum", "count"]).sort_index()
    sums, counts = g["sum"].to_numpy(), g["count"].to_numpy()
    S = len(g)
    if S < 3:
        return None
    nb = int(np.ceil(S / block))
    starts = rng.integers(0, max(S - block + 1, 1), size=(N_BOOT, nb))
    idx = (starts[:, :, None] + np.arange(min(block, S))[None, None, :]).reshape(N_BOOT, -1)[:, :S]
    block_means = sums[idx].sum(1) / counts[idx].sum(1)
    iid = rng.integers(0, S, size=(N_BOOT, S))
    iid_means = sums[iid].sum(1) / counts[iid].sum(1)
    sess_mean = sums / counts
    return {
        "block_ci95": [float(np.quantile(block_means, 0.025)), float(np.quantile(block_means, 0.975))],
        "block_p_mean_le_0": float((block_means <= 0).mean()),
        "iid_session_ci95": [float(np.quantile(iid_means, 0.025)), float(np.quantile(iid_means, 0.975))],
        "session_equal_weight_mean": float(sess_mean.mean()),
    }


def stats(frame, col, block, boot=True):
    x = frame[col].dropna()
    f = frame.loc[x.index]
    n = len(x)
    if n == 0:
        return {"n": 0}
    xs = np.sort(x.to_numpy())
    k5 = max(int(np.ceil(0.05 * n)), 1)
    worst5 = xs[:k5].sum()
    gains = xs[xs > 0].sum()
    out = {
        "n": int(n), "sessions": int(f["entry"].nunique()), "tickers": int(f["ticker"].nunique()),
        "mean": float(xs.mean()), "median": float(np.median(xs)), "win_rate": float((xs > 0).mean()),
        "p01": float(np.quantile(xs, 0.01)), "p05": float(np.quantile(xs, 0.05)),
        "worst5_sum_over_gross_gains": float(-worst5 / gains) if gains > 0 else None,
        "worst5_sum_over_net_total": float(worst5 / abs(xs.sum())) if xs.sum() != 0 else None,
        "net_total": float(xs.sum()),
        "entry_spread_cost_per_risk": float(((f["mid_credit"] - f["credit"]) / f["risk"]).mean()),
        "mean_hold_days": float(f["hold_days"].mean()),
    }
    if boot:
        out["bootstrap"] = bootstrap(f.assign(**{col: x}), col, block)
    return out


def pct(v):
    return "–" if v is None or (isinstance(v, float) and np.isnan(v)) else f"{100 * v:+.1f}%"


def main():
    df = pd.read_parquet(TRADES)
    # Structure sanity (data-quality exclusion, counted): every leg strike within [0.6, 1.6] x underlying
    # (catches chains where the underlying price was split-adjusted before the strikes, e.g. CVNA May 2026),
    # straddle strike within 5% of the underlying, defined-risk credit <= 60% of the wing width.
    def strikes(col):
        return df[col].fillna("").map(lambda v: [float(x[1:]) for x in v.split(",") if x])
    all_k = strikes("short_strikes") + strikes("long_strikes")
    k_ok = [all(0.6 * S <= k <= 1.6 * S for k in ks) for ks, S in zip(all_k, df["S"])]
    straddle_bad = (df["strategy"] == "short_straddle") & (
        (strikes("short_strikes").map(lambda ks: ks[0] if ks else np.nan) / df["S"] - 1).abs() > 0.05)
    defined_bad = (df["risk_kind"] == "defined") & (df["credit"] / (df["risk"] + df["credit"]) > 0.60)
    keep = pd.Series(k_ok, index=df.index) & ~straddle_bad & ~defined_bad
    excluded = {"strike_outside_0.6_1.6x_underlying": int((~pd.Series(k_ok, index=df.index)).sum()),
                "straddle_strike_over_5pct_from_underlying": int(straddle_bad.sum()),
                "defined_credit_over_60pct_of_width": int(defined_bad.sum()),
                "total_excluded": int((~keep).sum())}
    df = df[keep].copy()
    df["hold_days"] = (pd.to_datetime(df["expiry"]) - pd.to_datetime(df["entry"])).dt.days
    df["iv_over_fc"] = df["atm_iv"] / df["ewma_annual"]
    df["iv_band"] = pd.cut(df["iv_over_fc"], IV_BANDS, labels=IV_LABELS)
    df["jump"] = np.where(df["max_abs_ret_over_sigma"] > JUMP_MULTIPLE, "jump", "no_jump")
    df["move"] = pd.cut(df["underlying_ret"], [-np.inf, -0.05, -0.02, 0.02, 0.05, np.inf],
                        labels=["down>5%", "down2-5%", "flat+-2%", "up2-5%", "up>5%"])
    df["quarter"] = pd.to_datetime(df["entry"]).dt.to_period("Q").astype(str)
    df["ret_hold_mid_fill"] = (df["pnl_hold"] + df["mid_credit"] - df["credit"]) / df["risk"]

    res = {"trades_total": int(len(df)), "entry_sessions": int(df["entry"].nunique()),
           "tickers": int(df["ticker"].nunique()),
           "entry_range": [df["entry"].min(), df["entry"].max()], "structure_sanity_exclusions": excluded,
           "main": {}, "breakdowns": {}}
    md = []
    for tenor in ["t20_45", "t07_20"]:
        md.append(f"\n### Tenor {tenor}\n")
        md.append("| Strategy | Band | Exit | Trades | Sessions | Tickers | Mean | 95% CI (block) | P(mean<=0) | Median | Win | Worst 1% | Worst 5% | Worst-5% sum / gross gains | Entry spread cost | Mid-fill hold mean |")
        md.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
        for strat in STRATS:
            for band, thr in BANDS.items():
                sub = df[(df["tenor"] == tenor) & (df["strategy"] == strat) & (df["max_leg_spread"] <= thr)]
                for var, col in VARIANTS.items():
                    s = stats(sub, col, BLOCK[tenor])
                    if var == "mid":
                        s["mid_exit_quote_coverage"] = float(sub["ret_mid"].notna().mean()) if len(sub) else None
                    if var == "hold" and len(sub):
                        s["mid_fill_hold_mean"] = float(sub["ret_hold_mid_fill"].mean())
                    res["main"][f"{tenor}|{strat}|{band}|{var}"] = s
                    if s["n"] == 0:
                        continue
                    b = s.get("bootstrap") or {}
                    ci = b.get("block_ci95")
                    extra = f" (quote cov {100 * s['mid_exit_quote_coverage']:.0f}%)" if var == "mid" else ""
                    md.append(f"| {strat} | {band} | {var}{extra} | {s['n']} | {s['sessions']} | {s['tickers']} | {pct(s['mean'])} | "
                              f"{'[' + pct(ci[0]) + ', ' + pct(ci[1]) + ']' if ci else '–'} | {b.get('block_p_mean_le_0', float('nan')):.2f} | "
                              f"{pct(s['median'])} | {100 * s['win_rate']:.0f}% | {pct(s['p01'])} | {pct(s['p05'])} | "
                              f"{s['worst5_sum_over_gross_gains']:.2f} | {pct(s['entry_spread_cost_per_risk'])} | "
                              f"{pct(s.get('mid_fill_hold_mean')) if var == 'hold' else ''} |")
        for dim in ["iv_band", "jump", "move", "quarter"]:
            for band in ["le20", "le35"]:
                md.append(f"\n#### {tenor} by {dim}, band {band} (hold to expiry; tp50 mean in last column)\n")
                md.append("| Strategy | " + dim + " | Trades | Sessions | Mean (hold) | 95% CI (block) | Median | Win | Worst 5% | Mean (tp50) |")
                md.append("|---|---|---|---|---|---|---|---|---|---|")
                for strat in STRATS:
                    sub = df[(df["tenor"] == tenor) & (df["strategy"] == strat) & (df["max_leg_spread"] <= BANDS[band])]
                    for level, g in sub.groupby(dim, observed=True):
                        s = stats(g, "ret_hold", BLOCK[tenor])
                        t = stats(g, "ret_tp50", BLOCK[tenor], boot=False)
                        res["breakdowns"][f"{tenor}|{strat}|{band}|{dim}|{level}"] = {"hold": s, "tp50": t}
                        ci = (s.get("bootstrap") or {}).get("block_ci95")
                        md.append(f"| {strat} | {level} | {s['n']} | {s['sessions']} | {pct(s['mean'])} | "
                                  f"{'[' + pct(ci[0]) + ', ' + pct(ci[1]) + ']' if ci else '–'} | {pct(s['median'])} | "
                                  f"{100 * s['win_rate']:.0f}% | {pct(s['p05'])} | {pct(t['mean'])} |")
    # context: volatility premium inside this sample (straddle rows carry one row per ticker-session-tenor)
    ctx = df[df["strategy"] == "short_straddle"].dropna(subset=["atm_iv", "delivered_annual"])
    res["context_iv_vs_delivered"] = {
        t: {"n": int(len(g)), "median_iv_over_delivered": float((g["atm_iv"] / g["delivered_annual"]).median()),
            "share_iv_above_delivered": float((g["atm_iv"] > g["delivered_annual"]).mean()),
            "median_underlying_ret": float(g["underlying_ret"].median()),
            "share_jump_windows": float((g["jump"] == "jump").mean())}
        for t, g in ctx.groupby("tenor")}
    # missing later quotes: do trades with a mid-life quote differ at expiry from those without?
    miss = {}
    for (tenor, strat), g in df[df["max_leg_spread"] <= 0.35].groupby(["tenor", "strategy"]):
        has = g["ret_mid"].notna()
        miss[f"{tenor}|{strat}"] = {"with_mid_quote_hold_mean": float(g.loc[has, "ret_hold"].mean()) if has.any() else None,
                                    "without_mid_quote_hold_mean": float(g.loc[~has, "ret_hold"].mean()) if (~has).any() else None,
                                    "coverage": float(has.mean())}
    res["missing_quote_check_le35"] = miss
    per_session = df.groupby(["tenor", "entry"]).size()
    res["trades_per_entry_session"] = {t: {"median": float(g.median()), "min": int(g.min()), "max": int(g.max())}
                                       for t, g in per_session.groupby(level=0)}
    OUT_JSON.write_text(json.dumps(res, indent=1, default=str))
    OUT_MD.write_text("\n".join(md), encoding="utf-8")
    print(json.dumps({k: res[k] for k in ["trades_total", "entry_sessions", "tickers", "entry_range",
                                          "context_iv_vs_delivered", "trades_per_entry_session"]}, indent=1, default=str))


if __name__ == "__main__":
    main()
