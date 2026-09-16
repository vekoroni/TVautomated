"""p22_M2_analysis.py -- AVS-TD-001 track M2 (discovery). READ-ONLY. RESEARCH_ONLY.

Reads probes/p22_M2_panel.csv (+ p22_M2_greeks_iv.csv if present) and writes:
  p22_M2_regressions.csv      (a) y~F, (b) y~IV, (c) y~F+IV per h x direction x IV source x y-type
  p22_M2_alg10.csv            ALG-10 diagnostics per h x group (overall, direction, hidden_state)
  p22_M2_stability.csv        per forecast session x h
  p22_M2_state_correction.csv time-ordered train/test of overall vs per-state multiplier
  p22_M2_gapfields.csv        pipeline-published forecast-vs-IV fields on books
  p22_M2_analysis_log.txt
Conventions:
  * Dedupe: one row per (ticker, forecast_session), keeping the latest run_id.
  * sigma_f valid: 0 < sigma_f <= 3.0 (ALG-01 DATA_DEFECT bound).
  * F_h = sigma_f*sqrt(h/252); IV_h = IV*sqrt(h/252) (same scale); IV kept if 0.03 < IV < 3.0.
  * y: abs = |ln(C_{d+h}/C_d)|; rv = RV_h*sqrt(h/252) (period RV); mx = max(|ln High/C_d|, |ln C_d/Low|) over d+1..d+h.
  * SEs: HC1; one-way cluster CR1 by forecast session and by ticker (t with G-1 df).
  * n_nonoverlap: per ticker greedy keep of sessions >= h sessions apart within the regression sample;
    (c) re-estimated on that subset (HC1).
"""
import os, json
import numpy as np, pandas as pd
from scipy import stats

AUD = r"C:\Users\ACKVerissimo\AVSHUNTER-Intelligence\audit\td\AVS-TD-001"
PR = os.path.join(AUD, "probes")
H = (5, 10, 20)
L = []
def log(*a):
    s = " ".join(str(x) for x in a); print(s); L.append(s)

P0 = pd.read_csv(os.path.join(PR, "p22_M2_panel.csv"), low_memory=False)
log("panel rows (all runs):", len(P0))
# pipeline-used IV, backed out of l3_iv_tailwind_score = implied_vol - ann_vol (layer3_forward_variance.py:531; 0.0 when IV absent)
ROOT = os.path.abspath(os.path.join(AUD, "..", "..", ".."))
_tw = []
for _r in sorted(P0.run_id.astype(str).unique()):
    _f = os.path.join(ROOT, "data", "output", "runs", _r, "qomega", f"garch_forecasts_{_r}.csv")
    _d = pd.read_csv(_f, usecols=["ticker", "l3_iv_tailwind_score", "l3_iv_tailwind_score_capped"]); _d["run_id"] = _r; _tw.append(_d)
_tw = pd.concat(_tw).drop_duplicates(["run_id", "ticker"])
P0["run_id"] = P0.run_id.astype(str)
P0 = P0.merge(_tw, on=["run_id", "ticker"], how="left")
P0["IV_pipe_raw"] = np.where(P0.l3_iv_tailwind_score.notna() & (P0.l3_iv_tailwind_score != 0), P0.sigma_f + P0.l3_iv_tailwind_score, np.nan)
log("l3_iv_tailwind_score non-null:", int(P0.l3_iv_tailwind_score.notna().sum()), "non-zero:", int((P0.l3_iv_tailwind_score.fillna(0) != 0).sum()),
    "capped differs from raw:", int((P0.l3_iv_tailwind_score != P0.l3_iv_tailwind_score_capped).sum()))
log("IV_pipe non-null by run:", P0.groupby("run_id").IV_pipe_raw.apply(lambda s: int(s.notna().sum())).to_dict())
P = P0.sort_values("run_id").drop_duplicates(["ticker", "forecast_session"], keep="last").copy()
log("after dedupe (ticker, forecast_session) keep latest run:", len(P))
P = P[(P.sigma_f > 0) & (P.sigma_f <= 3.0)].copy()
log("sigma_f in (0,3]:", len(P))
P["in_book"] = P.hidden_state != "UNKNOWN"
P["dir_detail"] = np.where(~P.in_book, "NOT_IN_BOOK", P.direction_raw.astype(str))

def clean_iv(s):
    return s.where((s > 0.03) & (s < 3.0))

for h in H:
    P[f"IVs_surf_{h}"] = clean_iv(P[f"IV_surf_{h}"])
P["IVs_cache"] = clean_iv(P["IV_cache"])
P["IVs_pipe"] = clean_iv(P["IV_pipe_raw"])
P["IVs_book"] = clean_iv(P["book_atm_iv"]) if "book_atm_iv" in P else np.nan
gpath = os.path.join(PR, "p22_M2_greeks_iv.csv")
HAVE_GRK = os.path.exists(gpath)
if HAVE_GRK:
    G = pd.read_csv(gpath)
    for h in H:
        gh = G[G.h == h][["ticker", "snapshot_date", "atm_iv_greeks"]].rename(
            columns={"snapshot_date": "iv_surf_date", "atm_iv_greeks": f"IVs_grk_{h}"})
        P = P.merge(gh, on=["ticker", "iv_surf_date"], how="left")
        P[f"IVs_grk_{h}"] = clean_iv(P[f"IVs_grk_{h}"])
    log("greeks subsample rows:", len(G))

# ------------------------------------------------------------------ OLS helpers
def ols(y, X, groups):
    n, k = X.shape
    XtX_inv = np.linalg.pinv(X.T @ X)
    b = XtX_inv @ X.T @ y
    e = y - X @ b
    sst = ((y - y.mean()) ** 2).sum()
    r2 = 1 - (e @ e) / sst if sst > 0 else np.nan
    meat = X.T @ (X * (e ** 2)[:, None])
    V = XtX_inv @ meat @ XtX_inv * n / (n - k)
    res = dict(b=b, se_hc1=np.sqrt(np.diag(V)), r2=r2, n=n)
    for name, g in groups.items():
        codes = pd.factorize(g)[0]; Gn = codes.max() + 1
        U = np.zeros((Gn, k)); np.add.at(U, codes, X * e[:, None])
        if Gn > 1:
            c = Gn / (Gn - 1) * (n - 1) / (n - k)
            Vc = c * XtX_inv @ (U.T @ U) @ XtX_inv
            res[f"se_{name}"] = np.sqrt(np.diag(Vc))
        else:
            res[f"se_{name}"] = np.full(k, np.nan)
        res[f"G_{name}"] = Gn
    return res

def nonoverlap_mask(df, h):
    keep = np.zeros(len(df), bool)
    order = np.lexsort((df.i_d.values, df.ticker.values))
    last_t, last_i = None, -10**9
    tk = df.ticker.values; idd = df.i_d.values
    for pos in order:
        if tk[pos] != last_t:
            last_t, last_i = tk[pos], -10**9
        if idd[pos] >= last_i + h:
            keep[pos] = True; last_i = idd[pos]
    return keep

def ycol(h, kind):
    if kind == "abs": return P[f"real_abs_{h}"]
    if kind == "rv": return P[f"RV_{h}"] * np.sqrt(h / 252.0)
    if kind == "mx": return P[f"max_exc_abs_{h}"]

DIRS = ["POOLED", "CALL", "PUT", "OTHER"]
reg_rows = []
def run_block(h, iv_src, ykind, full_a=False):
    F = P.sigma_f * np.sqrt(h / 252.0)
    y = ycol(h, ykind)
    if iv_src == "none":
        IV = pd.Series(np.nan, index=P.index)
        base = P[f"fwd_ok_{h}"] & y.notna()
    else:
        col = {"surf": f"IVs_surf_{h}", "cache": "IVs_cache", "book": "IVs_book", "greeks": f"IVs_grk_{h}", "pipe": "IVs_pipe"}[iv_src]
        if col not in P: return
        IV = P[col] * np.sqrt(h / 252.0)
        base = P[f"fwd_ok_{h}"] & y.notna() & IV.notna()
    for d in DIRS:
        m = base if d == "POOLED" else base & (P.direction == d)
        sub = P[m]
        n = int(m.sum())
        rec0 = dict(h=h, direction=d, iv_source=iv_src, y=ykind, n=n,
                    n_sessions=sub.forecast_session.nunique(), n_tickers=sub.ticker.nunique(),
                    sessions=";".join(sorted(sub.forecast_session.unique())))
        if n < 10:
            for model in (["a"] if iv_src == "none" else ["a", "b", "c"]):
                reg_rows.append({**rec0, "model": model, "power": "INSUFFICIENT_POWER"})
            continue
        yy = y[m].values.astype(float); ff = F[m].values.astype(float); iv = IV[m].values.astype(float)
        grp = {"cl_session": sub.forecast_session.values, "cl_ticker": sub.ticker.values}
        nonov = nonoverlap_mask(sub, h)
        rec0["n_nonoverlap"] = int(nonov.sum())
        rec0["mean_F_over_mean_y"] = ff.mean() / yy.mean()
        pos = yy > 0
        rec0["median_F_over_y"] = float(np.median(ff[pos] / yy[pos])) if pos.any() else np.nan
        if iv_src != "none":
            rec0["corr_F_IV"] = float(np.corrcoef(ff, iv)[0, 1])
            rec0["median_sigmaf_over_IV"] = float(np.median(ff / iv))
            rec0["mean_IV_over_mean_y"] = iv.mean() / yy.mean()
        models = {"a": [ff]} if iv_src == "none" else {"a": [ff], "b": [iv], "c": [ff, iv]}
        for model, cols in models.items():
            X = np.column_stack([np.ones(n)] + cols)
            r = ols(yy, X, grp)
            rec = {**rec0, "model": model, "power": "INSUFFICIENT_POWER" if n < 100 else "OK",
                   "a": r["b"][0], "se_a_hc1": r["se_hc1"][0], "R2": r["r2"],
                   "G_session": r["G_cl_session"], "G_ticker": r["G_cl_ticker"]}
            names = {"a": ["F"], "b": ["IV"], "c": ["F", "IV"]}[model]
            for j, nm in enumerate(names, start=1):
                b = r["b"][j]
                rec[f"b_{nm}"] = b
                rec[f"se_{nm}_hc1"] = r["se_hc1"][j]
                rec[f"t_{nm}_hc1"] = b / r["se_hc1"][j]
                rec[f"p_{nm}_hc1"] = 2 * stats.norm.sf(abs(b / r["se_hc1"][j]))
                for cl in ("cl_session", "cl_ticker"):
                    se = r[f"se_{cl}"][j]; Gn = r[f"G_{cl}"]
                    rec[f"se_{nm}_{cl}"] = se
                    rec[f"t_{nm}_{cl}"] = b / se if se and np.isfinite(se) else np.nan
                    rec[f"p_{nm}_{cl}"] = 2 * stats.t.sf(abs(b / se), df=Gn - 1) if se and np.isfinite(se) and Gn > 1 else np.nan
            if model == "c" and nonov.sum() >= 10:
                Xn = X[nonov]; rn = ols(yy[nonov], Xn, {"cl_ticker": sub.ticker.values[nonov]})
                rec["b_F_nonov"] = rn["b"][1]; rec["se_F_nonov_hc1"] = rn["se_hc1"][1]
                rec["t_F_nonov_hc1"] = rn["b"][1] / rn["se_hc1"][1]
                rec["p_F_nonov_hc1"] = 2 * stats.norm.sf(abs(rec["t_F_nonov_hc1"]))
                rec["b_IV_nonov"] = rn["b"][2]; rec["t_IV_nonov_hc1"] = rn["b"][2] / rn["se_hc1"][2]
                rec["R2_nonov"] = rn["r2"]
            reg_rows.append(rec)

for h in H:
    run_block(h, "none", "abs")
    for src in ["surf", "pipe", "cache", "book", "greeks"]:
        for yk in ["abs", "rv", "mx"]:
            run_block(h, src, yk)
REG = pd.DataFrame(reg_rows)
REG.to_csv(os.path.join(PR, "p22_M2_regressions.csv"), index=False)
show = ["h", "direction", "iv_source", "y", "model", "n", "n_nonoverlap", "G_session", "G_ticker", "b_F", "se_F_hc1", "se_F_cl_session", "se_F_cl_ticker",
        "t_F_hc1", "p_F_hc1", "t_F_cl_session", "p_F_cl_session", "t_F_cl_ticker", "b_IV", "t_IV_hc1", "R2", "b_F_nonov", "t_F_nonov_hc1", "corr_F_IV", "power"]
pd.set_option("display.width", 250); pd.set_option("display.max_columns", 40)
log("\n=== (c) headline: y=abs, IV=surface ===")
log(REG[(REG.model == "c") & (REG.y == "abs") & (REG.iv_source == "surf")][[c for c in show if c in REG]].round(4).to_string(index=False))
log("\n=== (a)/(b) R2 compare, y=abs, IV=surface ===")
log(REG[(REG.y == "abs") & (REG.iv_source.isin(["surf", "none"]))][["h", "direction", "iv_source", "model", "n", "a", "b_F", "b_IV", "t_F_hc1", "t_IV_hc1", "R2", "mean_F_over_mean_y", "median_F_over_y", "mean_IV_over_mean_y", "median_sigmaf_over_IV"]].round(4).to_string(index=False))
log("\n=== (c) other IV sources / y types, POOLED ===")
log(REG[(REG.model == "c") & (REG.direction == "POOLED")][["h", "iv_source", "y", "n", "n_nonoverlap", "G_session", "b_F", "t_F_hc1", "t_F_cl_session", "p_F_cl_session", "t_F_cl_ticker", "b_IV", "t_IV_hc1", "R2", "b_F_nonov", "t_F_nonov_hc1", "corr_F_IV", "sessions"]].round(4).to_string(index=False))

# ------------------------------------------------------------------ ALG-10
a_rows = []
def alg10(h, label, key, m):
    s = P[m & P[f"fwd_ok_{h}"] & P[f"RV_{h}"].notna()]
    n = len(s)
    rec = dict(h=h, group_type=label, group=key, n=n, power="INSUFFICIENT_POWER" if n < 100 else "OK")
    if n:
        ratio = s[f"RV_{h}"] / s.sigma_f
        q = ratio.quantile([0.25, 0.5, 0.75])
        cov = (s[f"real_abs_{h}"] <= s.sigma_f * np.sqrt(h / 252.0)).mean()
        rec.update(median_ratio_RV_over_sigmaf=q[0.5], q25=q[0.25], q75=q[0.75], IQR=q[0.75] - q[0.25],
                   coverage_1sigma=cov, median_sigmaf_over_RV=(s.sigma_f / s[f"RV_{h}"]).replace(np.inf, np.nan).median(),
                   median_abs_over_F=(s[f"real_abs_{h}"] / (s.sigma_f * np.sqrt(h / 252.0))).median(),
                   n_sessions=s.forecast_session.nunique())
    a_rows.append(rec)
for h in H:
    alg10(h, "overall", "ALL", pd.Series(True, index=P.index))
    for d in ["CALL", "PUT", "OTHER"]:
        alg10(h, "direction", d, P.direction == d)
    for st in sorted(P.hidden_state.unique()):
        alg10(h, "hidden_state", st, P.hidden_state == st)
    for d in sorted(P.dir_detail.unique()):
        alg10(h, "direction_detail", d, P.dir_detail == d)
A = pd.DataFrame(a_rows)
A.to_csv(os.path.join(PR, "p22_M2_alg10.csv"), index=False)
log("\n=== ALG-10 ===")
log(A.round(4).to_string(index=False))

# ------------------------------------------------------------------ stability over forecast sessions
s_rows = []
for h in H:
    for d, s in P[P[f"fwd_ok_{h}"] & P[f"RV_{h}"].notna()].groupby("forecast_session"):
        ratio = s.sigma_f / s[f"RV_{h}"]
        r2 = s[f"RV_{h}"] / s.sigma_f
        s_rows.append(dict(h=h, forecast_session=d, runs=";".join(sorted(s.run_id.unique())), n=len(s),
                           power="INSUFFICIENT_POWER" if len(s) < 100 else "OK",
                           median_sigmaf_over_RV=ratio.replace(np.inf, np.nan).median(),
                           median_RV_over_sigmaf=r2.median(), IQR_RV_over_sigmaf=r2.quantile(.75) - r2.quantile(.25),
                           coverage_1sigma=(s[f"real_abs_{h}"] <= s.sigma_f * np.sqrt(h / 252.0)).mean(),
                           median_sigmaf=s.sigma_f.median(), median_RV=s[f"RV_{h}"].median()))
S = pd.DataFrame(s_rows)
S.to_csv(os.path.join(PR, "p22_M2_stability.csv"), index=False)
log("\n=== stability ===")
log(S.drop(columns="runs").round(4).to_string(index=False))
for h in H:
    ss = S[(S.h == h) & (S.power == "OK")]
    log(f"h={h} sessions={len(ss)} median(sigmaf/RV) across sessions: min={ss.median_sigmaf_over_RV.min():.3f} max={ss.median_sigmaf_over_RV.max():.3f} "
        f"mean={ss.median_sigmaf_over_RV.mean():.3f} sd={ss.median_sigmaf_over_RV.std():.3f}; coverage min={ss.coverage_1sigma.min():.3f} max={ss.coverage_1sigma.max():.3f}")

# ------------------------------------------------------------------ per-state correction, time-ordered
c_rows = []
SPLIT = "2026-08-15"
for h in (5, 10):
    s = P[P[f"fwd_ok_{h}"] & P[f"RV_{h}"].notna() & P.in_book].copy()
    s["ratio"] = s[f"RV_{h}"] / s.sigma_f
    tr = s[s.forecast_session < SPLIT]; te = s[s.forecast_session >= SPLIT]
    m_all = float(np.clip(tr.ratio.median(), 0.5, 1.5))
    m_state = {}
    for st, g in tr.groupby("hidden_state"):
        m_state[st] = float(np.clip(g.ratio.median(), 0.5, 1.5)) if len(g) >= 100 else m_all
    te = te.assign(m_state=te.hidden_state.map(m_state).fillna(m_all))
    for label, mm in [("none", 1.0), ("overall", m_all), ("per_state", te.m_state)]:
        mult = mm if np.isscalar(mm) else mm.values
        adj = te.ratio / mult
        cov = (te[f"real_abs_{h}"] <= te.sigma_f * mult * np.sqrt(h / 252.0)).mean()
        c_rows.append(dict(h=h, scheme=label, train_sessions=tr.forecast_session.nunique(), n_train=len(tr), test_sessions=te.forecast_session.nunique(),
                           n_test=len(te), m_overall=m_all, m_state=json.dumps({k: round(v, 3) for k, v in m_state.items()}),
                           test_median_ratio=adj.median(), test_median_abs_log_ratio=np.abs(np.log(adj)).median(), test_coverage_1sigma=cov))
        for st, g in te.groupby("hidden_state"):
            gm = mult if np.isscalar(mult) else te.loc[g.index, "m_state"].values
            c_rows.append(dict(h=h, scheme=label + ":" + st, n_test=len(g), power="INSUFFICIENT_POWER" if len(g) < 100 else "OK",
                               test_median_ratio=(g.ratio / gm).median(),
                               test_coverage_1sigma=(g[f"real_abs_{h}"] <= g.sigma_f * gm * np.sqrt(h / 252.0)).mean()))
CC = pd.DataFrame(c_rows)
CC.to_csv(os.path.join(PR, "p22_M2_state_correction.csv"), index=False)
log("\n=== per-state correction (train < %s, test >=) ===" % SPLIT)
log(CC.round(4).to_string(index=False))

# ------------------------------------------------------------------ legacy differenced field + pipeline gap fields
g_rows = []
fr = P0.copy()
fr["lt"] = fr.l3_expected_move_6_10d < fr.l3_expected_move_1_5d
fr["r610"] = fr.l3_expected_move_6_10d / fr.l3_expected_move_1_5d
fr["chk15"] = fr.l3_expected_move_1_5d / (fr.sigma_f * np.sqrt(5 * 5 / 7 / 252) * 100)
v = fr[fr.l3_expected_move_1_5d.notna() & fr.l3_expected_move_6_10d.notna()]
log("\n=== _6_10d < _1_5d ===")
log(f"rows with both fields: {len(v)} of {len(fr)}; fraction 6_10 < 1_5: {v["lt"].mean():.6f}; ratio 6_10/1_5 median {v.r610.median():.6f} min {v.r610.min():.6f} max {v.r610.max():.6f}; "
    f"1_5d/(sigma_f*sqrt(25/7/252)*100) median {v.chk15.median():.6f} p01 {v.chk15.quantile(.01):.6f} p99 {v.chk15.quantile(.99):.6f}")
for d in ["CALL", "PUT", "OTHER"]:
    vv = v[v.direction == d]; log(f"  {d}: n={len(vv)} frac={vv["lt"].mean():.6f}")
byrun = v.groupby("run_id")["lt"].agg(["size", "mean"])
log("  by run fraction min/max:", byrun["mean"].min(), byrun["mean"].max())
g_rows.append(dict(item="frac_6_10_lt_1_5", n=len(v), value=v["lt"].mean()))
g_rows.append(dict(item="ratio_6_10_over_1_5_median", n=len(v), value=v.r610.median()))

B = P0[P0.run_id >= "20260831"].copy()
B = B[B.hidden_state != "UNKNOWN"]
log("\n=== pipeline gap fields on books (runs >= 20260831, book rows) ===")
log("book rows:", len(B))
for c in ["book_iv_vs_hv", "book_garch_iv_tailwind_score", "book_contract_iv", "book_atm_iv", "book_garch_forecast_vol", "book_iv_rank"]:
    if c in B:
        x = B[c]
        log(f"  {c}: non-null {x.notna().sum()} median {x.median():.4f} q25 {x.quantile(.25):.4f} q75 {x.quantile(.75):.4f}")
        g_rows.append(dict(item=c + "_median", n=int(x.notna().sum()), value=x.median()))
bb = B[B.book_garch_forecast_vol.notna()]
d_abs = (bb.book_garch_forecast_vol - bb.sigma_f).abs()
log(f"  garch_forecast_vol == l3_forward_realised_vol (|diff|<1e-4): {(d_abs < 1e-4).mean():.4f} of {len(bb)}; median |diff| {d_abs.median():.6f}")
g_rows.append(dict(item="garch_forecast_vol_equals_sigma_f_frac", n=len(bb), value=(d_abs < 1e-4).mean()))
bi = B[B.book_atm_iv.notna() & (B.book_atm_iv > 0.03)]
ratio = bi.sigma_f / bi.book_atm_iv
log(f"  sigma_f / book atm_iv: n={len(bi)} median {ratio.median():.4f} q25 {ratio.quantile(.25):.4f} q75 {ratio.quantile(.75):.4f}; frac sigma_f>atm_iv {(ratio>1).mean():.4f}")
g_rows.append(dict(item="sigma_f_over_book_atm_iv_median", n=len(bi), value=ratio.median()))
for c, target, nm in [("book_iv_vs_hv", bi.book_atm_iv / bi.sigma_f, "atm_iv/sigma_f"),
                      ("book_garch_iv_tailwind_score", bi.sigma_f / bi.book_atm_iv - 1, "sigma_f/atm_iv-1"),
                      ("book_garch_iv_tailwind_score", (bi.sigma_f - bi.book_atm_iv) / bi.book_atm_iv, "(sigma_f-atm_iv)/atm_iv"),
                      ("book_contract_iv", bi.book_atm_iv, "atm_iv")]:
    xx = bi[c]; ok = xx.notna() & target.notna()
    if ok.sum() > 2:
        rho = stats.spearmanr(xx[ok], target[ok]).statistic
        log(f"  spearman({c}, {nm}) = {rho:.4f} n={int(ok.sum())}; median({c}/{nm}) = {(xx[ok]/target[ok]).median():.4f}")
        g_rows.append(dict(item=f"spearman_{c}_vs_{nm}", n=int(ok.sum()), value=rho))
for h in H:
    for src, col in [("surf", f"IVs_surf_{h}"), ("cache", "IVs_cache")] + ([("greeks", f"IVs_grk_{h}")] if HAVE_GRK else []):
        x = P[P[col].notna()]
        r = x.sigma_f / x[col]
        log(f"  h={h} sigma_f/IV_{src}: n={len(x)} median {r.median():.4f} q25 {r.quantile(.25):.4f} q75 {r.quantile(.75):.4f} frac>1 {(r>1).mean():.4f}")
        g_rows.append(dict(item=f"sigma_f_over_IV_{src}_h{h}_median", n=len(x), value=r.median()))
    if HAVE_GRK:
        x = P[P[f"IVs_grk_{h}"].notna() & P[f"IVs_surf_{h}"].notna()]
        if len(x) > 2:
            log(f"  h={h} greeks vs surface ATM IV: n={len(x)} spearman {stats.spearmanr(x[f'IVs_grk_{h}'], x[f'IVs_surf_{h}']).statistic:.4f} median ratio grk/surf {(x[f'IVs_grk_{h}']/x[f'IVs_surf_{h}']).median():.4f}")
x = P[P.IVs_cache.notna() & P.IVs_surf_10.notna()]
if len(x) > 2:
    log(f"  cache vs surface(8_30) IV: n={len(x)} spearman {stats.spearmanr(x.IVs_cache, x.IVs_surf_10).statistic:.4f} median ratio {(x.IVs_cache/x.IVs_surf_10).median():.4f}")
bt = B[B.book_atm_iv.notna() & B.book_garch_iv_tailwind_score.notna()]
dd = bt.book_garch_iv_tailwind_score - (bt.book_atm_iv - bt.sigma_f)
log(f"  garch_iv_tailwind_score - (book atm_iv - sigma_f): n={len(bt)} |diff|<0.01 frac {(dd.abs()<0.01).mean():.4f} median |diff| {dd.abs().median():.4f}; tailwind==0 frac {(bt.book_garch_iv_tailwind_score==0).mean():.4f}")
g_rows.append(dict(item="tailwind_equals_atm_iv_minus_sigma_f_frac", n=len(bt), value=(dd.abs()<0.01).mean()))
x = P[P.IVs_pipe.notna() & P.IVs_book.notna()]
if len(x) > 2:
    log(f"  IV_pipe vs book atm_iv: n={len(x)} |diff|<0.005 frac {((x.IVs_pipe-x.IVs_book).abs()<0.005).mean():.4f} spearman {stats.spearmanr(x.IVs_pipe, x.IVs_book).statistic:.4f}")
for h in H:
    x = P[P.IVs_pipe.notna() & P[f"IVs_surf_{h}"].notna()]
    if len(x) > 2:
        log(f"  h={h} IV_pipe vs surface IV: n={len(x)} spearman {stats.spearmanr(x.IVs_pipe, x[f'IVs_surf_{h}']).statistic:.4f} median ratio pipe/surf {(x.IVs_pipe/x[f'IVs_surf_{h}']).median():.4f}")
x = P[P.IVs_pipe.notna()]
r = x.sigma_f / x.IVs_pipe
log(f"  sigma_f/IV_pipe (all sessions): n={len(x)} median {r.median():.4f} q25 {r.quantile(.25):.4f} q75 {r.quantile(.75):.4f} frac>1 {(r>1).mean():.4f}")
g_rows.append(dict(item="sigma_f_over_IV_pipe_median", n=len(x), value=r.median()))
pd.DataFrame(g_rows).to_csv(os.path.join(PR, "p22_M2_gapfields.csv"), index=False)

# ------------------------------------------------------------------ signed, in thesis direction (descriptive)
log("\n=== signed return in thesis direction (descriptive) ===")
for h in H:
    for d, sg in [("CALL", 1), ("PUT", -1)]:
        s = P[P[f"fwd_ok_{h}"] & (P.direction == d)]
        x = sg * s[f"real_signed_{h}"]
        log(f"  h={h} {d}: n={len(s)} mean {x.mean():.5f} median {x.median():.5f} frac>0 {(x>0).mean():.4f}")
log("\npanel counts: fwd_ok per h:", {h: int(P[f'fwd_ok_{h}'].sum()) for h in H},
    "direction:", P.direction.value_counts().to_dict(), "dir_detail:", P.dir_detail.value_counts().to_dict())
open(os.path.join(PR, "p22_M2_analysis_log.txt"), "w", encoding="utf-8").write("\n".join(L))
