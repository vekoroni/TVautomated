"""M8: session-stratified re-test of ELIGIBLE cells (DISCOVERY, RESEARCH_ONLY). Read-only.
Input p28_M8_joined.csv + p28_M8_cells.csv. For each eligible (variable, stratum, level, outcome):
  per decision_session 2x2 (cell vs rest-of-stratum x outcome); Cochran-Mantel-Haenszel chi2 (1 df, no continuity correction)
  over sessions where both cell and rest have >=1 row; MH-weighted risk difference (w = n1*n0/N).
  No session with both -> SESSION_CONFOUNDED (the level only varies between sessions; not testable within session).
BH over tests with a within-session contrast; haircut 1 - z_adj/z_raw for survivors (BH and Bonferroni)."""
import os
import numpy as np, pandas as pd
from scipy import stats

OUT = r"C:\Users\ACKVerissimo\AVSHUNTER-Intelligence\audit\td\AVS-TD-001\probes"
D = pd.read_csv(os.path.join(OUT, "p28_M8_joined.csv"), low_memory=False)
C = pd.read_csv(os.path.join(OUT, "p28_M8_cells.csv"), low_memory=False)
E = D[D.label_V.isin(["TARGET_FIRST", "INVALIDATION_FIRST", "TIMEOUT"])].copy()
E["TF"] = (E.label_V == "TARGET_FIRST").astype(int)
E["SC"] = E.side_correct.astype(str).str.lower().eq("true").astype(int)
E["stratum"] = E.direction.astype(str) + " " + E.horizon_bucket.astype(str)
EL = C[C.status == "ELIGIBLE"].copy()
out = []
for _, r in EL.iterrows():
    g = E[E.stratum == r.stratum]
    a_sum = e_sum = v_sum = 0.0
    rd_num = rd_den = 0.0
    k_sess = 0; n_in_contrast = 0
    for s, gs in g.groupby("decision_session"):
        inc = (gs[r.variable].astype(str) == str(r.level)).values
        n1, n0 = inc.sum(), (~inc).sum()
        if n1 == 0 or n0 == 0:
            continue
        y = gs[r.outcome].values
        N = n1 + n0; m1 = y.sum(); m0 = N - m1; a = y[inc].sum()
        k_sess += 1; n_in_contrast += n1
        a_sum += a; e_sum += n1 * m1 / N
        if N > 1:
            v_sum += n1 * n0 * m1 * m0 / (N ** 2 * (N - 1))
        w = n1 * n0 / N
        rd_num += w * (a / n1 - y[~inc].mean()); rd_den += w
    rec = r.to_dict()
    rec.update(sessions_with_contrast=k_sess, n_cell_in_contrast_sessions=int(n_in_contrast))
    if k_sess == 0:
        rec.update(cmh_status="SESSION_CONFOUNDED", p_cmh=np.nan, rd_mh=np.nan)
    elif v_sum <= 0:
        rec.update(cmh_status="NO_VARIANCE", p_cmh=np.nan, rd_mh=rd_num / rd_den if rd_den else np.nan)
    else:
        chi2 = (a_sum - e_sum) ** 2 / v_sum
        rec.update(cmh_status="TESTED", chi2_cmh=chi2, p_cmh=stats.chi2.sf(chi2, 1), rd_mh=rd_num / rd_den)
    out.append(rec)
R = pd.DataFrame(out)
t = (R.cmh_status == "TESTED").values
m = int(t.sum())
for c in ("p_cmh_bh", "p_cmh_bonf", "haircut_cmh_bh", "haircut_cmh_bonf", "rd_mh_after_bh_haircut"):
    R[c] = np.nan
if m:
    p = R.loc[t, "p_cmh"].values; o = np.argsort(p)
    adj = np.minimum(np.minimum.accumulate((p[o] * m / (np.arange(m) + 1))[::-1])[::-1], 1.0)
    a = np.empty(m); a[o] = adj
    R.loc[t, "p_cmh_bh"] = a
    bf = np.minimum(p * m, 1.0); R.loc[t, "p_cmh_bonf"] = bf
    zr = stats.norm.isf(np.clip(p, 1e-300, 1) / 2)
    zb = stats.norm.isf(np.clip(a, 1e-300, 0.999999) / 2); zf = stats.norm.isf(np.clip(bf, 1e-300, 0.999999) / 2)
    with np.errstate(divide="ignore", invalid="ignore"):
        R.loc[t, "haircut_cmh_bh"] = np.clip(1 - zb / zr, 0, 1)
        R.loc[t, "haircut_cmh_bonf"] = np.clip(1 - zf / zr, 0, 1)
    R.loc[t, "rd_mh_after_bh_haircut"] = R.loc[t, "rd_mh"].values * (1 - R.loc[t, "haircut_cmh_bh"].values)
R["survives_cmh_bh_005"] = t & (R.p_cmh_bh <= 0.05).values
R["survives_both"] = R.survives_cmh_bh_005 & R.survives_bh_005.astype(str).str.lower().eq("true")
R.to_csv(os.path.join(OUT, "p28_M8_cmh.csv"), index=False)
lines = []
lines.append(f"eligible tests {len(R)} | cmh_status {R.cmh_status.value_counts().to_dict()} | CMH family m = {m}")
lines.append(f"survive CMH-BH q=0.05: {int(R.survives_cmh_bh_005.sum())} | survive both pooled-BH and CMH-BH: {int(R.survives_both.sum())}")
lines.append("SESSION_CONFOUNDED tests (pooled-BH survivors among them): " + str(int((R.cmh_status == 'SESSION_CONFOUNDED').sum())) + " (" + str(int(((R.cmh_status == 'SESSION_CONFOUNDED') & R.survives_bh_005.astype(str).str.lower().eq('true')).sum())) + ")")
lines.append("survivors (both) by variable x direction x outcome:\n" + R[R.survives_both].groupby(["variable", "direction", "outcome"]).size().to_string())
lines.append("sign agreement pooled diff vs MH diff among survivors: " + str(float((np.sign(R[R.survives_both]["diff"]) == np.sign(R[R.survives_both].rd_mh)).mean())))
cols = ["variable", "stratum", "level", "outcome", "n", "rate", "base_rate", "diff", "rd_mh", "p_raw", "p_bh", "p_cmh", "p_cmh_bh", "haircut_cmh_bh", "haircut_cmh_bonf", "rd_mh_after_bh_haircut", "sessions_in_cell", "sessions_with_contrast"]
pd.set_option("display.width", 400)
lines.append("\nSURVIVORS (pooled BH and CMH BH), sorted by p_cmh:\n" + R[R.survives_both].sort_values("p_cmh")[cols].to_string(index=False, float_format=lambda x: f"{x:.3g}"))
lines.append("\nSESSION_CONFOUNDED tests:\n" + R[R.cmh_status == "SESSION_CONFOUNDED"][["variable", "stratum", "level", "outcome", "n", "diff", "p_raw", "p_bh", "sessions_in_cell"]].to_string(index=False, float_format=lambda x: f"{x:.3g}"))
lines.append("\npooled-BH survivors that do NOT survive CMH-BH:\n" + R[R.survives_bh_005.astype(str).str.lower().eq("true") & ~R.survives_cmh_bh_005][["variable", "stratum", "level", "outcome", "n", "diff", "rd_mh", "p_bh", "p_cmh", "p_cmh_bh", "cmh_status", "sessions_with_contrast"]].to_string(index=False, float_format=lambda x: f"{x:.3g}"))
txt = "\n".join(lines)
print(txt)
with open(os.path.join(OUT, "p28_M8_cmh.txt"), "w", encoding="utf-8") as fh:
    fh.write(txt)
