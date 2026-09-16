"""M8 conditional outcomes (DISCOVERY, RESEARCH_ONLY). Read-only.
Unique theses (ticker x direction x decision_session, earliest run kept) from p32_labels.csv (vol-budget labels label_V).
Outcomes: TF = label_V == TARGET_FIRST; SC = side_correct. AMBIGUOUS_TOUCH_ORDER (and NO_SIGMA) excluded from denominators.
Stratum = direction x horizon_bucket. Cell = stratum x level of one conditioning variable.
Primary test: two-proportion z, cell vs rest of stratum (Fisher exact when any expected count < 5). Secondary: exact binomial vs stratum base rate.
n < 100 -> INSUFFICIENT_POWER (excluded from BH). Level == whole stratum -> NO_CONTRAST (excluded). MISSING levels not tested.
BH over one family = all eligible cells x both outcomes. Session-clustered z reported for eligible cells."""
import os, glob, csv, math
import numpy as np, pandas as pd
from scipy import stats

ROOT = r"C:\Users\ACKVerissimo\AVSHUNTER-Intelligence"
OUT = os.path.join(ROOT, "audit", "td", "AVS-TD-001", "probes")
RD = os.path.join(ROOT, "data", "output", "runs")
log = []


def P(*a):
    s = " ".join(str(x) for x in a)
    print(s)
    log.append(s)


def hdr(f):
    with open(f, newline="", encoding="utf-8", errors="replace") as fh:
        return next(csv.reader(fh))


def read(f, want):
    if not os.path.exists(f):
        return None
    cols = [c for c in want if c in hdr(f)]
    return pd.read_csv(f, usecols=cols, low_memory=False) if len(cols) > 1 else None


L0 = pd.read_csv(os.path.join(OUT, "p32_labels.csv"), low_memory=False)
P("rows", len(L0), "direction:", L0.direction.value_counts(dropna=False).to_dict())
P("label_V all rows:", L0.label_V.value_counts(dropna=False).to_dict())
L = L0.sort_values("run_id").drop_duplicates(["ticker", "direction", "decision_session"], keep="first").copy()
P("unique theses", len(L), "| repeated rows collapsed", len(L0) - len(L))
rep = L0.groupby(["ticker", "direction", "decision_session"]).run_id.nunique()
P("theses appearing in >1 run:", int((rep > 1).sum()))
P("label_V unique:", L.label_V.value_counts(dropna=False).to_dict())

# ---------- joins per run ----------
fb_parts, mc_parts, sec_parts, earn_parts, dup_notes = [], [], [], [], []
for rid in sorted(L0.run_id.unique()):
    fb = read(os.path.join(RD, rid, "intelligence_lab", f"final_opportunity_book_{rid}.csv"),
              ["ticker", "contract_delta", "dte", "delta_band", "macro_regime", "regime", "regime_drift_status", "trigger_primary",
               "morning_execution_permission", "thesis_state", "gics_sector", "iv_rank", "catalyst_type", "catalyst_event_status",
               "usmi_sector_alignment", "macro_sector_alignment"])
    dup_notes.append((rid, "final_book", len(fb), int(fb.ticker.duplicated().sum())))
    fb = fb.drop_duplicates("ticker").rename(columns={c: "fb_" + c for c in fb.columns if c != "ticker"})
    fb["run_id"] = rid
    fb_parts.append(fb)
    mc = read(os.path.join(RD, rid, "morning_validation", f"morning_candidates_{rid}.csv"),
              ["ticker", "thesis_state", "iv_rank", "catalyst_type", "catalyst_event_status"])
    if mc is not None:
        dup_notes.append((rid, "morning_candidates", len(mc), int(mc.ticker.duplicated().sum())))
        mc = mc.drop_duplicates("ticker").rename(columns={c: "mc_" + c for c in mc.columns if c != "ticker"})
        mc["run_id"] = rid
        mc_parts.append(mc)
    for hf in glob.glob(os.path.join(RD, rid, "horizon", f"horizon_*_{rid}.csv")):
        h = read(hf, ["ticker", "sector", "gics_sector"])
        if h is not None:
            for c in ("sector", "gics_sector"):
                if c in h:
                    sec_parts.append(h[["ticker", c]].rename(columns={c: "sec"}))
    if "fb_gics_sector" in fb:
        sec_parts.append(fb[["ticker", "fb_gics_sector"]].rename(columns={"fb_gics_sector": "sec"}))
    mv = read(os.path.join(RD, rid, "morning_validation", f"morning_validated_trades_{rid}.csv"), ["ticker", "earnings_date"])
    if mv is not None:
        mv = mv.drop_duplicates("ticker")
        mv["run_id"] = rid
        earn_parts.append(mv)
P("per-run duplicate tickers (run, artefact, rows, dup):", dup_notes)
FB = pd.concat(fb_parts)
MC = pd.concat(mc_parts)
EA = pd.concat(earn_parts) if earn_parts else pd.DataFrame(columns=["ticker", "earnings_date", "run_id"])
S = pd.concat(sec_parts)
S = S[S.sec.notna() & (S.sec.astype(str).str.strip() != "")]
secmode = S.groupby("ticker").sec.agg(lambda s: s.value_counts().index[0])
secn = S.groupby("ticker").sec.nunique()
P("sector map tickers", len(secmode), "| tickers with >1 distinct sector label", int((secn > 1).sum()))
P("earnings_date artefact present on runs:", sorted(EA.run_id.unique()) if len(EA) else [],
  "fill", float(EA.earnings_date.notna().mean()) if len(EA) else None)

J = L.merge(FB, on=["run_id", "ticker"], how="left").merge(MC, on=["run_id", "ticker"], how="left").merge(EA, on=["run_id", "ticker"], how="left")
assert len(J) == len(L)
P("join: final book matched", float(J.fb_macro_regime.notna().mean()), "| morning_candidates matched", float(J.mc_thesis_state.notna().mean()))


def col(name):
    return J[name] if name in J else pd.Series(np.nan, index=J.index)


# ---------- conditioning variables ----------
V = pd.DataFrame(index=J.index)
V["hidden_state"] = J.hidden_state.fillna("MISSING")
V["phase"] = J.phase.fillna("MISSING")
V["compression_bucket"] = J.compression_bucket.fillna("MISSING")
V["sector"] = J.ticker.map(secmode).fillna("MISSING")
ct = col("mc_catalyst_type").fillna(col("fb_catalyst_type"))
cs = col("mc_catalyst_event_status").fillna(col("fb_catalyst_event_status"))
ed = pd.to_datetime(col("earnings_date"), errors="coerce")
earn_in = ed.notna() & (ed > pd.to_datetime(J.decision_session)) & (ed <= pd.to_datetime(J.window_end))
nonstruct = ct.notna() & (ct.astype(str) != "STRUCTURAL")
cat_present = nonstruct | cs.notna() | earn_in
V["catalyst_presence"] = np.where(cat_present, "PRESENT", np.where(ct.isna() & cs.isna() & ed.isna(), "MISSING", "NONE_OR_STRUCTURAL"))
P("catalyst components: non-STRUCTURAL type", int(nonstruct.sum()), "| event_status", int(cs.notna().sum()),
  "| earnings_date populated", int(ed.notna().sum()), "| earnings in window", int(earn_in.sum()))
ivm = pd.to_numeric(col("mc_iv_rank"), errors="coerce")
ivf = pd.to_numeric(col("fb_iv_rank"), errors="coerce")
iv = ivm.fillna(ivf)
both = ivm.notna() & ivf.notna()
if both.any():
    P("iv_rank morning_candidates == final_book where both present:", float(np.isclose(ivm[both], ivf[both], atol=0.05).mean()), "n", int(both.sum()))
below = iv[(iv < 99.95) & iv.notna()]
q1, q2 = below.quantile([1 / 3, 2 / 3]).values
P("iv_rank: at 100 share", float((iv >= 99.95).mean()), "| terciles of <100 values cut at", round(q1, 2), round(q2, 2), "| missing", int(iv.isna().sum()))
V["iv_percentile"] = np.select([iv.isna(), iv >= 99.95, iv <= q1, iv <= q2], ["MISSING", "AT_CAP_100", "T1_LOW", "T2_MID"], "T3_HIGH")
dl = pd.to_numeric(col("fb_contract_delta"), errors="coerce")
dt = pd.to_numeric(col("fb_dte"), errors="coerce")
zero = (dl == 0) | dl.isna()
P("contract_delta==0 or null share", float(zero.mean()), "| of those dte==30", float((dt[zero] == 30).mean()),
  "| dte==30 among delta!=0", float((dt[~zero] == 30).mean()))
ad = dl.abs()
V["delta_band"] = np.select([zero, ad < 0.20, ad < 0.35, ad < 0.60, ad < 0.75],
                            ["MISSING", "FAR_OTM_LT_020", "DEVELOPING_OTM_020_035", "NEAR_ATM_035_060", "ITM_060_075"], "DEEP_ITM_GT_075")
bdb = col("fb_delta_band")
m3 = bdb.notna() & ~zero
if m3.any():
    P("derived delta_band == book delta_band (runs carrying it):", float((V.delta_band[m3] == bdb[m3]).mean()), "n", int(m3.sum()))
dmiss = dt.isna() | (zero & (dt == 30))
V["dte_band"] = np.select([dmiss, dt <= 7, dt <= 14, dt <= 21, dt <= 35, dt <= 60],
                          ["MISSING", "DTE_LE_7", "DTE_8_14", "DTE_15_21", "DTE_22_35", "DTE_36_60"], "DTE_GT_60")
V["regime_macro_regime"] = col("fb_macro_regime").fillna("MISSING")
V["regime_drift_status"] = col("fb_regime_drift_status").fillna("MISSING")
V["confirm_thesis_state"] = col("mc_thesis_state").fillna(col("fb_thesis_state")).fillna("MISSING")
tp = col("fb_trigger_primary").astype("object")
V["confirm_trigger_primary"] = tp.where(tp.notna() & (tp != "NONE"), "NONE_OR_NULL")
V["confirm_morning_permission"] = col("fb_morning_execution_permission").fillna("MISSING")
V["regime_drift_x_sector"] = np.where(V.sector == "MISSING", "MISSING", V.regime_drift_status.astype(str) + "|" + V.sector.astype(str))
VARS = list(V.columns)

D = pd.concat([J[["run_id", "ticker", "direction", "decision_session", "horizon_bucket", "label_V", "side_correct", "terminal_return"]], V], axis=1)
D.to_csv(os.path.join(OUT, "p28_M8_joined.csv"), index=False)
for v in VARS:
    P(f"var {v}: levels={D[v].nunique()} missing={int((D[v] == 'MISSING').sum())} top={D[v].value_counts().head(8).to_dict()}")

E = D[D.label_V.isin(["TARGET_FIRST", "INVALIDATION_FIRST", "TIMEOUT"])].copy()
P("denominator set (non-AMBIGUOUS, labelled):", len(E), "| excluded", len(D) - len(E), D.label_V.value_counts().to_dict())
E["TF"] = (E.label_V == "TARGET_FIRST").astype(int)
E["SC"] = E.side_correct.astype(str).str.lower().eq("true").astype(int)
E["stratum"] = E.direction.astype(str) + " " + E.horizon_bucket.astype(str)
P("OTHER (non CALL/PUT) rows in denominator set:", int((~E.direction.isin(["CALL", "PUT"])).sum()))
P("distinct decision sessions:", E.decision_session.nunique(), "| theses per session:", E.decision_session.value_counts().sort_index().to_dict())


def cluster_z(y, incell, sess):
    n1, n0 = incell.sum(), (~incell).sum()
    if n1 == 0 or n0 == 0:
        return np.nan
    p1, p0 = y[incell].mean(), y[~incell].mean()
    inf = np.where(incell, (y - p1) / n1, -(y - p0) / n0)
    t = pd.Series(inf).groupby(np.asarray(sess)).sum()
    G = len(t)
    if G < 2:
        return np.nan
    var = G / (G - 1) * (t ** 2).sum()
    return (p1 - p0) / math.sqrt(var) if var > 0 else np.nan


BR = E.groupby("stratum").agg(n=("TF", "size"), TF=("TF", "mean"), SC=("SC", "mean"), sessions=("decision_session", "nunique")).reset_index()
P("stratum base rates:\n" + BR.to_string(index=False))
BR.to_csv(os.path.join(OUT, "p28_M8_base_rates.csv"), index=False)

rows = []
for v in VARS:
    for st, g in E.groupby("stratum"):
        g = g.reset_index(drop=True)
        for lev in sorted(g[v].unique()):
            incell = (g[v] == lev).values
            for oc in ("TF", "SC"):
                y = g[oc].values.astype(float)
                n1 = int(incell.sum()); k1 = int(y[incell].sum()); n0 = int((~incell).sum()); k0 = int(y[~incell].sum())
                base = y.mean(); rate = k1 / n1
                r = dict(variable=v, stratum=st, direction=st.split()[0], horizon=st.split()[1], level=lev, outcome=oc, n=n1, k=k1, rate=rate,
                         base_rate=base, diff=rate - base, n_rest=n0, rate_rest=(k0 / n0 if n0 else np.nan),
                         sessions_in_cell=int(g.decision_session[incell].nunique()))
                if lev == "MISSING":
                    r["status"] = "MISSING_NOT_TESTED"
                elif n0 == 0:
                    r["status"] = "NO_CONTRAST"
                elif n1 < 100:
                    r["status"] = "INSUFFICIENT_POWER"
                else:
                    r["status"] = "ELIGIBLE"
                r["p_binom"] = stats.binomtest(k1, n1, base).pvalue if 0 < base < 1 else np.nan
                pz, test = np.nan, ""
                if n0 > 0:
                    pp = (k1 + k0) / (n1 + n0)
                    exp_min = min(n1 * pp, n1 * (1 - pp), n0 * pp, n0 * (1 - pp))
                    if exp_min < 5:
                        pz = stats.fisher_exact([[k1, n1 - k1], [k0, n0 - k0]])[1]; test = "fisher"
                    else:
                        se = math.sqrt(pp * (1 - pp) * (1 / n1 + 1 / n0))
                        z = (rate - k0 / n0) / se if se > 0 else 0.0
                        pz = 2 * stats.norm.sf(abs(z)); test = "z2prop"; r["z"] = z
                r["p_raw"] = pz; r["test"] = test
                if r["status"] == "ELIGIBLE":
                    zc = cluster_z(y, incell, g.decision_session.values)
                    r["z_cluster_session"] = zc
                    r["p_cluster_session"] = 2 * stats.norm.sf(abs(zc)) if pd.notna(zc) else np.nan
                rows.append(r)
C = pd.DataFrame(rows)
el = (C.status == "ELIGIBLE").values
m = int(el.sum())
for c_ in ("p_bh", "p_bonferroni", "haircut_bh", "haircut_bonferroni", "diff_after_bh_haircut"):
    C[c_] = np.nan
if m:
    p = C.loc[el, "p_raw"].values
    o = np.argsort(p)
    ranked = p[o] * m / (np.arange(m) + 1)
    adj = np.minimum(np.minimum.accumulate(ranked[::-1])[::-1], 1.0)
    a = np.empty(m); a[o] = adj
    C.loc[el, "p_bh"] = a
    C.loc[el, "p_bonferroni"] = np.minimum(p * m, 1.0)
    zr = stats.norm.isf(p / 2)
    zb = stats.norm.isf(np.clip(a, 1e-300, 0.999999) / 2)
    zf = stats.norm.isf(np.clip(np.minimum(p * m, 1.0), 1e-300, 0.999999) / 2)
    C.loc[el, "haircut_bh"] = np.clip(1 - zb / zr, 0, 1)
    C.loc[el, "haircut_bonferroni"] = np.clip(1 - zf / zr, 0, 1)
    C.loc[el, "diff_after_bh_haircut"] = C.loc[el, "diff"].values * (1 - C.loc[el, "haircut_bh"].values)
C["survives_bh_005"] = el & (C.p_bh <= 0.05).values
C.to_csv(os.path.join(OUT, "p28_M8_cells.csv"), index=False)
C[el].sort_values("p_raw").to_csv(os.path.join(OUT, "p28_M8_bh.csv"), index=False)
P("\nsplits (variable partitions):", len(VARS), VARS)
P("cells (variable x stratum x level):", len(C) // 2, "| tests (x2 outcomes):", len(C))
P("status counts (per test):", C.status.value_counts().to_dict())
P("status counts by direction (per test):", C.groupby(["direction", "status"]).size().to_dict())
P("BH family size m =", m, "| survivors at q=0.05:", int(C.survives_bh_005.sum()), "| raw p<0.05 among eligible:", int((C.loc[el, "p_raw"] < 0.05).sum()))
P("eligible tests by variable:", C[el].groupby("variable").size().to_dict())
cols = ["variable", "stratum", "level", "outcome", "n", "rate", "base_rate", "diff", "p_raw", "p_binom", "p_cluster_session", "p_bh",
        "haircut_bh", "diff_after_bh_haircut", "sessions_in_cell"]
P("\nELIGIBLE sorted by p_raw:\n" + C[el].sort_values("p_raw")[cols].to_string(index=False, float_format=lambda x: f"{x:.4g}"))

pw = []
za = stats.norm.isf(0.025); zbeta = stats.norm.isf(0.20); zabf = stats.norm.isf(0.025 / max(m, 1))
for _, b in BR.iterrows():
    for oc in ("TF", "SC"):
        p0 = b[oc]
        for sgn in (+1, -1):
            p1 = p0 + sgn * 0.05
            if not (0 < p1 < 1):
                continue
            n1 = ((za * math.sqrt(p0 * (1 - p0)) + zbeta * math.sqrt(p1 * (1 - p1))) / 0.05) ** 2
            nb = ((zabf * math.sqrt(p0 * (1 - p0)) + zbeta * math.sqrt(p1 * (1 - p1))) / 0.05) ** 2
            pw.append(dict(stratum=b.stratum, outcome=oc, base_rate=p0, alt=p1, n_req_alpha05=math.ceil(n1), n_req_bonferroni_m=math.ceil(nb), m=m, stratum_n=b.n))
PW = pd.DataFrame(pw)
PW.to_csv(os.path.join(OUT, "p28_M8_power.csv"), index=False)
P("\npower (one-sample vs base, 80%, +/-5pt):\n" + PW.to_string(index=False, float_format=lambda x: f"{x:.3f}"))
ss = E.groupby(["stratum", "decision_session"]).agg(n=("TF", "size"), TF=("TF", "mean"), SC=("SC", "mean")).reset_index()
ss.to_csv(os.path.join(OUT, "p28_M8_session_rates.csv"), index=False)
P("\nper-session TF/SC range within stratum (sessions with n>=30):\n" +
  ss[ss.n >= 30].groupby("stratum").agg(sessions=("n", "size"), TF_min=("TF", "min"), TF_max=("TF", "max"), SC_min=("SC", "min"), SC_max=("SC", "max")).to_string(float_format=lambda x: f"{x:.3f}"))
with open(os.path.join(OUT, "p28_M8_cells.txt"), "w", encoding="utf-8") as fh:
    fh.write("\n".join(log))
