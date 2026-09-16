"""p22_M2_robustness.py -- AVS-TD-001 track M2 (discovery). READ-ONLY. RESEARCH_ONLY.
Robustness of the (c) forecast coefficient: per-session cross-sections (HC1), Fama-MacBeth mean across
sessions (n>=100 per session), surface IV with lag <= 1 session, and an averaged IV (mean of available
surface/cache/pipeline IV where >= 2 present) to reduce IV measurement error. Same conventions as p22_M2_analysis.py.
Writes probes/p22_M2_robustness.csv.
"""
import os
import numpy as np, pandas as pd
from scipy import stats
AUD = r"C:\Users\ACKVerissimo\AVSHUNTER-Intelligence\audit\td\AVS-TD-001"
ROOT = os.path.abspath(os.path.join(AUD, "..", "..", ".."))
PR = os.path.join(AUD, "probes")
P0 = pd.read_csv(os.path.join(PR, "p22_M2_panel.csv"), low_memory=False); P0["run_id"] = P0.run_id.astype(str)
tw = pd.concat([pd.read_csv(os.path.join(ROOT, "data", "output", "runs", r, "qomega", f"garch_forecasts_{r}.csv"), usecols=["ticker", "l3_iv_tailwind_score"]).assign(run_id=r)
                for r in sorted(P0.run_id.unique())]).drop_duplicates(["run_id", "ticker"])
P0 = P0.merge(tw, on=["run_id", "ticker"], how="left")
P = P0.sort_values("run_id").drop_duplicates(["ticker", "forecast_session"], keep="last")
P = P[(P.sigma_f > 0) & (P.sigma_f <= 3)].copy()
cl = lambda s: s.where((s > 0.03) & (s < 3.0))
P["IV_pipe"] = cl(pd.Series(np.where(P.l3_iv_tailwind_score.fillna(0) != 0, P.sigma_f + P.l3_iv_tailwind_score, np.nan), index=P.index))
P["IV_cache"] = cl(P.IV_cache)
for h in (5, 10, 20):
    P[f"IV_surf_{h}"] = cl(P[f"IV_surf_{h}"])
    P[f"IV_avg_{h}"] = P[[f"IV_surf_{h}", "IV_cache", "IV_pipe"]].mean(axis=1).where(P[[f"IV_surf_{h}", "IV_cache", "IV_pipe"]].notna().sum(axis=1) >= 2)

def ols_hc1(y, X):
    n, k = X.shape; XtXi = np.linalg.pinv(X.T @ X); b = XtXi @ X.T @ y; e = y - X @ b
    V = XtXi @ (X.T @ (X * (e ** 2)[:, None])) @ XtXi * n / (n - k)
    return b, np.sqrt(np.diag(V))
def cl_se(y, X, g):
    n, k = X.shape; XtXi = np.linalg.pinv(X.T @ X); b = XtXi @ X.T @ y; e = y - X @ b
    codes = pd.factorize(g)[0]; G = codes.max() + 1; U = np.zeros((G, k)); np.add.at(U, codes, X * e[:, None])
    V = G / (G - 1) * (n - 1) / (n - k) * XtXi @ (U.T @ U) @ XtXi
    return np.sqrt(np.diag(V)), G

rows = []
def fit(label, h, ivcol, mask, direction="POOLED"):
    m = mask & P[f"fwd_ok_{h}"] & P[ivcol].notna() & P[f"real_abs_{h}"].notna()
    if direction != "POOLED": m &= P.direction == direction
    s = P[m]; n = len(s)
    if n < 10:
        rows.append(dict(label=label, h=h, iv=ivcol, direction=direction, n=n, power="INSUFFICIENT_POWER")); return
    sc = np.sqrt(h / 252); y = s[f"real_abs_{h}"].values
    X = np.column_stack([np.ones(n), s.sigma_f.values * sc, s[ivcol].values * sc])
    b, se = ols_hc1(y, X); sct, Gt = cl_se(y, X, s.ticker.values)
    rows.append(dict(label=label, h=h, iv=ivcol, direction=direction, n=n, power="INSUFFICIENT_POWER" if n < 100 else "OK",
                     sessions=s.forecast_session.nunique(), b_F=b[1], se_F_hc1=se[1], t_F_hc1=b[1] / se[1], p_F_hc1=2 * stats.norm.sf(abs(b[1] / se[1])),
                     se_F_cl_ticker=sct[1], t_F_cl_ticker=b[1] / sct[1], b_IV=b[2], t_IV_hc1=b[2] / se[2]))
ALL = pd.Series(True, index=P.index)
# 1) per-session cross sections + Fama-MacBeth
for h, ivcol in [(5, "IV_surf_5"), (10, "IV_surf_10"), (20, "IV_surf_20"), (5, "IV_pipe"), (10, "IV_pipe"), (20, "IV_pipe"), (5, "IV_cache"), (10, "IV_cache")]:
    for d in sorted(P.forecast_session.unique()):
        fit(f"session:{d}", h, ivcol, P.forecast_session == d)
    sub = pd.DataFrame([r for r in rows if r["label"].startswith("session:") and r["h"] == h and r["iv"] == ivcol and r.get("power") == "OK"])
    if len(sub) >= 2:
        bm, sd, S = sub.b_F.mean(), sub.b_F.std(ddof=1), len(sub)
        t = bm / (sd / np.sqrt(S))
        rows.append(dict(label="fama_macbeth", h=h, iv=ivcol, direction="POOLED", n=int(sub.n.sum()), sessions=S, b_F=bm, se_F_hc1=sd / np.sqrt(S), t_F_hc1=t,
                         p_F_hc1=2 * stats.t.sf(abs(t), S - 1), power="OK", frac_sessions_bF_pos=(sub.b_F > 0).mean(), frac_sessions_tF_gt2=(sub.t_F_hc1 > 2).mean()))
    else:
        rows.append(dict(label="fama_macbeth", h=h, iv=ivcol, direction="POOLED", sessions=len(sub), power="INSUFFICIENT_SESSIONS"))
# 2) surface IV lag <= 1
for d in ["POOLED", "CALL", "PUT", "OTHER"]:
    fit("surf_lag_le1", 5, "IV_surf_5", P.iv_surf_lag <= 1, d)
    fit("surf_lag_le1", 10, "IV_surf_10", P.iv_surf_lag <= 1, d)
# 3) averaged IV
for h in (5, 10, 20):
    for d in ["POOLED", "CALL", "PUT", "OTHER"]:
        fit("iv_avg_ge2_sources", h, f"IV_avg_{h}", ALL, d)
R = pd.DataFrame(rows); R.to_csv(os.path.join(PR, "p22_M2_robustness.csv"), index=False)
pd.set_option("display.width", 250); pd.set_option("display.max_columns", 30)
cols = ["label", "h", "iv", "direction", "n", "sessions", "b_F", "se_F_hc1", "t_F_hc1", "p_F_hc1", "t_F_cl_ticker", "b_IV", "t_IV_hc1", "frac_sessions_bF_pos", "frac_sessions_tF_gt2", "power"]
print(R[[c for c in cols if c in R]].round(4).to_string(index=False))
REG = pd.read_csv(os.path.join(PR, "p22_M2_regressions.csv"))
print("\n=== (c) pipeline IV by direction, y=abs ===")
print(REG[(REG.model == "c") & (REG.y == "abs") & (REG.iv_source.isin(["pipe", "cache", "greeks"]))][["h", "iv_source", "direction", "n", "n_nonoverlap", "G_session", "b_F", "se_F_hc1", "t_F_hc1", "p_F_hc1", "t_F_cl_session", "p_F_cl_session", "t_F_cl_ticker", "b_IV", "t_IV_hc1", "R2", "t_F_nonov_hc1", "power"]].round(4).to_string(index=False))
print("\n=== (a)/(b) R2 by source, pooled, y=abs ===")
print(REG[(REG.y == "abs") & (REG.direction == "POOLED") & (REG.model.isin(["a", "b"]))][["h", "iv_source", "model", "n", "R2", "mean_F_over_mean_y", "mean_IV_over_mean_y", "median_sigmaf_over_IV"]].round(4).to_string(index=False))
