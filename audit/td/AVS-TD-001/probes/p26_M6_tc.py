"""M6 step 4 - transfer coefficient (no outcomes). Read-only. Per run x direction (ALL/CALL/PUT/OTHER):
UNGATED populations: Spearman and Pearson (point-biserial) between an inclusion indicator and each unconstrained score.
  - DISCOVERY_SURVIVORS (dropoff audit rows past Discovery): inclusion = reached the book; scores discovery_composite_score, scanner_score, vanguard_probability_edge, oi_options_score.
  - BOOK (all book rows): inclusion = lab GO/GO_LIMIT; lab non-BLOCKED; eil EXECUTE*; opportunity_tier != BLOCK; morning GO_LIMIT/GO/CONTRACT_REPAIR.
GATED book: within survivors of lab non-BLOCKED and of lab GO/GO_LIMIT, weight proxy = -lab_rank and -priority_rank (rank 1 = best; no sizing exists: PSE_IGNORED_MANUAL_SIZING).
Output p26_M6_tc.csv."""
import os
import numpy as np, pandas as pd
from scipy import stats

ROOT = r"C:\Users\ACKVerissimo\AVSHUNTER-Intelligence"
RUNS = os.path.join(ROOT, "data", "output", "runs")
PR = os.path.join(ROOT, "audit", "td", "AVS-TD-001", "probes")
BS = ["composite_score", "priority_score", "options_score", "trigger_score", "eil_composite_eod", "ev3_ev_lower_bound_return"]
AS = ["discovery_composite_score", "scanner_score", "vanguard_probability_edge", "oi_options_score"]
rows = []


def corr(run, pop, d3, incl_name, x, y, kind):
    ok = x.notna() & y.notna()
    x, y = x[ok].astype(float), y[ok].astype(float)
    rec = dict(run_id=run, population=pop, direction=d3, inclusion_or_weight=incl_name, score=y.name, kind=kind, n=int(len(x)),
               n_included=int(x.sum()) if kind == "INCLUSION" else np.nan)
    if len(x) < 3 or x.nunique() < 2 or y.nunique() < 2:
        rec.update(spearman=np.nan, pearson=np.nan, note="UNDEFINED_CONSTANT" if len(x) >= 3 else "N_LT_3")
    else:
        rec.update(spearman=stats.spearmanr(x, y).statistic, pearson=stats.pearsonr(x, y).statistic, note="")
    rec["power"] = "INSUFFICIENT_POWER" if rec["n"] < 100 else "n>=100"
    rows.append(rec)


def d3s(s):
    s = s.astype(str).str.upper()
    return s.where(s.isin(["CALL", "PUT"]), "OTHER")


for run in sorted(os.listdir(RUNS)):
    bk = os.path.join(RUNS, run, "intelligence_lab", f"final_opportunity_book_{run}.csv")
    if not os.path.exists(bk):
        continue
    B = pd.read_csv(bk, low_memory=False)
    B["d3"] = d3s(B["governed_direction"] if "governed_direction" in B else B["direction"])
    A = pd.read_csv(os.path.join(RUNS, run, "diagnostics", f"dropoff_audit_{run}.csv"), low_memory=False)
    A = A[~A.dropoff_stage.isin(["BETWEEN_UNIVERSE_AND_DISCOVERY", "BETWEEN_SCANNER_AND_DISCOVERY"]) & ~A.last_stage_reached.isin(["UNIVERSE", "SCANNER"])].copy()
    A["d3"] = d3s(A.eod_direction.where(A.eod_direction.notna(), A.discovery_direction))
    A["incl"] = A.ticker.isin(set(B.ticker)).astype(float)
    incl = {}
    if "lab_verdict" in B:
        incl["lab_GO_or_GO_LIMIT"] = B.lab_verdict.isin(["GO", "GO_LIMIT"]).astype(float)
        incl["lab_not_BLOCKED"] = B.lab_verdict.ne("BLOCKED").astype(float)
    if "eil_signal_verdict" in B:
        incl["eil_EXECUTE_any"] = B.eil_signal_verdict.isin(["EXECUTE", "EXECUTE_WITH_CAUTION"]).astype(float)
    if "opportunity_tier" in B:
        incl["opportunity_tier_not_BLOCK"] = B.opportunity_tier.ne("BLOCK").astype(float)
    if "morning_execution_permission" in B and B.morning_execution_permission.notna().any():
        incl["morning_GO"] = B.morning_execution_permission.isin(["GO", "GO_LIMIT", "CONTRACT_REPAIR"]).astype(float)
    for d3 in ("ALL", "CALL", "PUT", "OTHER"):
        am = A if d3 == "ALL" else A[A.d3 == d3]
        for s in AS:
            if s in am:
                corr(run, "UNGATED_DISCOVERY_SURVIVORS", d3, "reached_book", am.incl, pd.to_numeric(am[s], errors="coerce").rename(s), "INCLUSION")
        bm = B if d3 == "ALL" else B[B.d3 == d3]
        for iname, iv in incl.items():
            for s in BS:
                if s in bm:
                    corr(run, "UNGATED_BOOK", d3, iname, iv.loc[bm.index], pd.to_numeric(bm[s], errors="coerce").rename(s), "INCLUSION")
        for gname, gm in (("GATED_lab_not_BLOCKED", bm.lab_verdict.ne("BLOCKED") if "lab_verdict" in bm else None),
                          ("GATED_lab_GO_or_GO_LIMIT", bm.lab_verdict.isin(["GO", "GO_LIMIT"]) if "lab_verdict" in bm else None)):
            if gm is None:
                continue
            g = bm[gm]
            for wname in ("lab_rank", "priority_rank"):
                if wname in g:
                    w = -pd.to_numeric(g[wname], errors="coerce")
                    for s in BS:
                        if s in g:
                            corr(run, gname, d3, "-" + wname, w, pd.to_numeric(g[s], errors="coerce").rename(s), "WEIGHT_PROXY")
            # also rank vs score on the ungated book for reference
        for wname in ("lab_rank", "priority_rank"):
            if wname in bm:
                w = -pd.to_numeric(bm[wname], errors="coerce")
                for s in BS:
                    if s in bm:
                        corr(run, "UNGATED_BOOK", d3, "-" + wname, w, pd.to_numeric(bm[s], errors="coerce").rename(s), "WEIGHT_PROXY")
    print(run, len(B), len(A))

T = pd.DataFrame(rows)
T.to_csv(os.path.join(PR, "p26_M6_tc.csv"), index=False)
pd.set_option("display.width", 250)
p = T[(T.run_id == "20260911_115904") & (T.direction == "ALL")]
print(p[["population", "inclusion_or_weight", "score", "n", "n_included", "spearman", "pearson", "note"]].round(3).to_string(index=False))
q = T[(T.direction == "ALL") & T.spearman.notna()].groupby(["population", "inclusion_or_weight", "score"]).agg(
    runs=("run_id", "nunique"), med_spearman=("spearman", "median"), min_sp=("spearman", "min"), max_sp=("spearman", "max"), med_pearson=("pearson", "median"), med_n=("n", "median"))
print(q.round(3).to_string())
u = T[(T.direction == "ALL") & T.spearman.isna()].groupby(["population", "inclusion_or_weight", "note"]).run_id.nunique()
print(u.to_string())
