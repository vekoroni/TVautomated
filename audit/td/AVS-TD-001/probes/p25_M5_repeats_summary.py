"""Summarise p25_M5_repeats.csv (no rebuild). RESEARCH_ONLY."""
import os, numpy as np, pandas as pd
H = os.path.dirname(os.path.abspath(__file__))
R = pd.read_csv(os.path.join(H, "p25_M5_repeats.csv"), low_memory=False)
X = R[R.premium_td.notna() & (R.premium_t > 0) & ~R.iv_floor.fillna(False).astype(bool)].copy()
for c in ["delta_premium_total", "theta_component", "IV_component", "move_component", "residual"]:
    X[c + "_pct"] = X[c] / X.premium_t * 100
X["confirmation"] = X.verdict_t
X["era"] = np.where(X.session_basis_t == "quote_as_of", "thesis_era(>=0831)", "pre_0831")
def agg(g):
    n = len(g)
    d = dict(n=n, power="OK" if n >= 100 else "INSUFFICIENT_POWER")
    for c in ["delta_premium_total_pct", "theta_component_pct", "IV_component_pct", "move_component_pct", "residual_pct"]:
        d["med_" + c.replace("_component_pct", "").replace("_pct", "")] = round(g[c].median(), 2)
    d["p10_tot"] = round(g.delta_premium_total_pct.quantile(.1), 2); d["p90_tot"] = round(g.delta_premium_total_pct.quantile(.9), 2)
    d["same_contract_src_chain_both"] = int(((g.src_t == "chain") & (g.src_td == "chain")).sum())
    w = g.waiting_ineq_as_written.dropna(); ws = g.waiting_ineq_sign_corrected.dropna()
    dp = g[g.delta_p_power == "OK"]
    d["n_delta_p_powered"] = len(dp)
    d["med_delta_p_powered"] = round(dp.delta_p.median(), 4) if len(dp) else None
    d["share_ineq_written_true(powered)"] = round(dp.waiting_ineq_as_written.dropna().astype(bool).mean(), 3) if len(dp.waiting_ineq_as_written.dropna()) else None
    d["share_ineq_signfix_true(powered)"] = round(dp.waiting_ineq_sign_corrected.dropna().astype(bool).mean(), 3) if len(dp.waiting_ineq_sign_corrected.dropna()) else None
    return pd.Series(d)
out = []
for keys in [["d", "dir3"], ["d", "hidden_state_t", "dir3"], ["d", "confirmation", "dir3"], ["d", "era", "dir3"]]:
    s = X.groupby(keys).apply(agg, include_groups=False).reset_index()
    s.insert(0, "split", "x".join(keys))
    out.append(s)
S = pd.concat(out, ignore_index=True)
S.to_csv(os.path.join(H, "p25_M5_repeats_summary.csv"), index=False)
pd.set_option("display.width", 320); pd.set_option("display.max_columns", 30); pd.set_option("display.max_rows", 300)
print("pairs", len(R), "repriced", int(R.premium_td.notna().sum()), "used (iv floor excluded)", len(X))
print(S.to_string(index=False))
# delta_p transitions
T = R.groupby(["d", "delta_p_power"]).size().unstack(fill_value=0); print(T)
print("state changes t->t+d:", {"hidden_state": round((R.hidden_state_t != R.hidden_state_td).mean(), 3), "verdict": round((R.verdict_t != R.verdict_td).mean(), 3)})
P = R[R.delta_p_power == "OK"]
print("powered delta_p by d:", P.groupby("d").delta_p.describe()[["count", "mean", "50%", "min", "max"]].round(4).to_string())
print("contract_changed share by d:", R.groupby("d").contract_changed.mean().round(3).to_dict())
print("reprice residual abs median % premium:", round(X.residual_pct.abs().median(), 2), "theta_linear vs BS theta ratio median:", round((X.theta_linear / X.theta_component).median(), 2))
print("same thesis_id pairs repriced:", int(X.same_thesis_id.sum()))
print(X[X.same_thesis_id].groupby(["d", "dir3"]).delta_premium_total_pct.agg(["count", "median"]).round(2))
