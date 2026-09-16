"""Decomposition curves on the chain>chain subset only (same OCC contract, stored chain both ends). Reads p25_M5_repeats.csv. RESEARCH_ONLY."""
import os, pandas as pd
H = os.path.dirname(os.path.abspath(__file__))
R = pd.read_csv(os.path.join(H, "p25_M5_repeats.csv"), low_memory=False)
C = R[(R.src_t == "chain") & (R.src_td == "chain") & (R.premium_t > 0) & ~R.iv_floor.fillna(False).astype(bool)].copy()
for c in ["delta_premium_total", "theta_component", "IV_component", "move_component", "residual"]:
    C.loc[:, c + "_pct"] = C[c] / C.premium_t * 100
rows = []
for keys in [["d", "dir3"], ["d", "hidden_state_t", "dir3"], ["d", "verdict_t", "dir3"], ["d", "liquidity_state_t", "dir3"]]:
    for k, g in C.groupby(keys):
        k = k if isinstance(k, tuple) else (k,)
        r = dict(split="x".join(keys), d=k[0], cell=k[1] if len(k) == 3 else "", dir3=k[-1], n=len(g),
                 power="OK" if len(g) >= 100 else "INSUFFICIENT_POWER", sessions_t=g.session_t.nunique(), tickers=g.ticker.nunique())
        for c in ["delta_premium_total_pct", "theta_component_pct", "IV_component_pct", "move_component_pct", "residual_pct"]:
            r["med_" + c.split("_")[0] if c != "delta_premium_total_pct" else "med_total"] = round(g[c].median(), 2)
        r["p10_total"] = round(g.delta_premium_total_pct.quantile(.1), 2); r["p90_total"] = round(g.delta_premium_total_pct.quantile(.9), 2)
        r["iqr_total"] = round(g.delta_premium_total_pct.quantile(.75) - g.delta_premium_total_pct.quantile(.25), 2)
        r["n_delta_p_powered"] = int((g.delta_p_power == "OK").sum())
        r["share_ineq_signfix_true"] = round(g.waiting_ineq_sign_corrected.dropna().astype(bool).mean(), 3) if g.waiting_ineq_sign_corrected.notna().any() else None
        r["med_payoff_td_pct"] = round((g.payoff_td / g.premium_t * 100).median(), 1)
        r["med_friction_td_pct"] = round((g.friction_td / g.premium_t * 100).median(), 1)
        rows.append(r)
S = pd.DataFrame(rows)
S.to_csv(os.path.join(H, "p25_M5_repeats_chainonly.csv"), index=False)
pd.set_option("display.width", 320); pd.set_option("display.max_columns", 30); pd.set_option("display.max_rows", 200)
print("chain>chain pairs", len(C))
print(S.to_string(index=False))
