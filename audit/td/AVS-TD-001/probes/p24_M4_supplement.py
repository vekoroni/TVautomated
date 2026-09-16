"""M4 supplement: within-thesis normalised surface, selected-contract geometry by run, breakeven vs outcome,
DOI stored candidate counts (structure only). Reads p24_M4_* outputs and control_plane copy (read-only)."""
import json, sqlite3
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.stats import mannwhitneyu

AUD = Path(r"C:\Users\ACKVerissimo\AVSHUNTER-Intelligence\audit\td\AVS-TD-001"); PR = AUD / "probes"
out = open(PR / "p24_M4_supplement_stdout.txt", "w", encoding="utf-8")


def log(*a):
    s = " ".join(str(x) for x in a); print(s); out.write(s + "\n"); out.flush()


tk = ["ticker", "direction", "decision_session"]
F = pd.read_csv(PR / "p24_M4_family_contracts.csv")
F = F[F.hold.isin([5, 10])]
F["rel"] = F.payoff_per_dollar / F.groupby(tk).payoff_per_dollar.transform("max")
cell = F.groupby(tk + ["hold", "dband", "tband"]).agg(rel=("rel", "max"), pay=("payoff_per_dollar", "max")).reset_index()

# 1. conditional-on-cell normalised surface (all theses with a contract in the cell)
R1 = cell.groupby(["direction", "hold", "dband", "tband"]).agg(n_theses=("rel", "size"), rel_med=("rel", "median"),
                                                               share_cell_is_thesis_best=("rel", lambda x: (x >= 0.99999).mean())).reset_index()
R1["power"] = np.where(R1.n_theses >= 100, "n>=100", "INSUFFICIENT_POWER")
R1.to_csv(PR / "p24_M4_surface_within_thesis.csv", index=False)
for (d, h), g in R1.groupby(["direction", "hold"]):
    log(f"== within-thesis rel_med {d} h{h}\n" + g.pivot(index="dband", columns="tband", values="rel_med").round(3).to_string()
        + "\n n_theses\n" + g.pivot(index="dband", columns="tband", values="n_theses").to_string())
    pw = g[g.n_theses >= 100]
    if len(pw):
        p = pw.loc[pw.rel_med.idxmax()]; log(f" powered-cell peak (rel_med): {p.dband}/{p.tband} rel_med={p.rel_med:.3f} n={p.n_theses}")
    else:
        log(" no powered cell")

# 2. argmax marginals per thesis
best = F.loc[F.groupby(tk).payoff_per_dollar.idxmax()]
for (d, h), g in best.groupby(["direction", "hold"]):
    log(f"argmax marginals {d} h{h} n={len(g)} dband={g.dband.value_counts().to_dict()} tband={g.tband.value_counts().to_dict()} |delta| q={g.delta.abs().quantile([.25,.5,.75]).round(3).tolist()} dte_offset q={g.dte_offset.quantile([.25,.5,.75]).tolist()}")

# 3. head-to-head within thesis and same tband
H2H = []
wide = cell.pivot_table(index=tk + ["hold", "tband"], columns="dband", values="pay").reset_index()
for a, b in [("D010_025", "D040_060"), ("D025_040", "D040_060"), ("D060_085", "D040_060"), ("D010_025", "D025_040")]:
    for (d, h), g in wide.groupby(["direction", "hold"]):
        gg = g.dropna(subset=[a, b])
        th = gg.groupby(tk).apply(lambda x: (x[a] > x[b]).mean(), include_groups=False)
        H2H.append(dict(direction=d, hold=h, a=a, b=b, n_theses=len(th), share_a_beats_b=round(float((th > 0.5).mean()), 3) if len(th) else None,
                        med_ratio_a_over_b=round(float((gg[a] / gg[b]).median()), 3) if len(gg) else None,
                        power="n>=100" if len(th) >= 100 else "INSUFFICIENT_POWER"))
H2H = pd.DataFrame(H2H); H2H.to_csv(PR / "p24_M4_h2h_delta.csv", index=False); log(H2H.to_string())
# tenor head-to-head: shortest vs longest band within thesis & dband
wt = cell.pivot_table(index=tk + ["hold", "dband"], columns="tband", values="pay").reset_index()
T2 = []
for (d, h), g in wt.groupby(["direction", "hold"]):
    for a, b in [("H+05_15", "H+30_45"), ("H+15_30", "H+30_45"), ("H+05_15", "H+15_30")]:
        if a in g and b in g:
            gg = g.dropna(subset=[a, b]); th = gg.groupby(tk).apply(lambda x: (x[a] > x[b]).mean(), include_groups=False)
            T2.append(dict(direction=d, hold=h, a=a, b=b, n_theses=len(th), share_a_beats_b=round(float((th > 0.5).mean()), 3) if len(th) else None,
                           med_ratio=round(float((gg[a] / gg[b]).median()), 3) if len(gg) else None, power="n>=100" if len(th) >= 100 else "INSUFFICIENT_POWER"))
T2 = pd.DataFrame(T2); T2.to_csv(PR / "p24_M4_h2h_tenor.csv", index=False); log(T2.to_string())

# 4. selected contract geometry
S = pd.read_csv(PR / "p24_M4_selected_vs_peak.csv")
S["book_delta_num"] = pd.to_numeric(S.book_contract_delta, errors="coerce")
S["side_mismatch"] = np.where(S.sel_side_char.notna(), S.sel_side_char != np.where(S.direction == "CALL", "C", "P"), np.nan)
G = S.groupby(["run_id", "direction", "hold"]).agg(n=("ticker", "size"), with_symbol=("sel_symbol", lambda x: x.notna().sum()),
                                                    side_mismatch=("side_mismatch", lambda x: int(np.nansum(x.astype(float)))),
                                                    book_delta_zero=("book_delta_num", lambda x: int((x == 0).sum())),
                                                    book_delta_na=("book_delta_num", lambda x: int(x.isna().sum())),
                                                    dte_offset_med=("sel_dte_offset", "median"), dte_offset_lt5=("sel_dte_offset", lambda x: int((x < 5).sum())),
                                                    dte_offset_le0=("sel_dte_offset", lambda x: int((x <= 0).sum())),
                                                    in_family=("sel_status", lambda x: int((x == "IN_FAMILY").sum()))).reset_index()
G.to_csv(PR / "p24_M4_selected_geometry_by_run.csv", index=False); log(G.to_string())
IF = S[S.sel_status == "IN_FAMILY"]
Q = IF.groupby(["direction", "hold"]).agg(n=("ticker", "size"), in_bucket_peak_cell=("d_steps_vs_peak", lambda x: int(((x == 0) & (IF.loc[x.index, "t_steps_vs_peak"] == 0)).sum())),
                                          in_own_best_cell=("d_steps_vs_thesis_best", lambda x: int(((x == 0) & (IF.loc[x.index, "t_steps_vs_thesis_best"] == 0)).sum())),
                                          payoff_ge_90pct_best=("sel_payoff_over_best", lambda x: int((x >= 0.9).sum())),
                                          ratio_med=("sel_payoff_over_best", "median"), d_steps_vs_best_med=("d_steps_vs_thesis_best", "median"),
                                          higher_delta_than_best=("d_steps_vs_thesis_best", lambda x: int((x > 0).sum())),
                                          lower_delta_than_best=("d_steps_vs_thesis_best", lambda x: int((x < 0).sum()))).reset_index()
Q.to_csv(PR / "p24_M4_selected_in_family_summary.csv", index=False); log(Q.to_string())
Qd = IF.groupby("direction").agg(n=("ticker", "size"), ratio_med=("sel_payoff_over_best", "median"),
                                 ge90=("sel_payoff_over_best", lambda x: int((x >= 0.9).sum())), higher_delta=("d_steps_vs_thesis_best", lambda x: int((x > 0).sum())),
                                 same_band=("d_steps_vs_thesis_best", lambda x: int((x == 0).sum())), lower_delta=("d_steps_vs_thesis_best", lambda x: int((x < 0).sum())))
log(Qd.to_string())

# 5. breakeven vs outcomes
O = pd.read_csv(PR / "p24_M4_breakeven_outcomes.csv")
O = O[O.hold_sessions.isin([5, 10])]
O["sel_be_frac"] = O.sel_be_over_sigma_h * O.sigma_h
O["mfe_ge_sel_be"] = np.where(O.sel_be_frac.notna(), O.mfe >= O.sel_be_frac, np.nan)
rows = []
for key, g in list(O.groupby("direction")) + list(O.groupby(["direction", "hold_sessions"])):
    med = g.be_med.median(); lo_, hi_ = g[g.be_med < med], g[g.be_med >= med]
    mw = mannwhitneyu(g[g.side_correct].be_med, g[~g.side_correct].be_med) if g.side_correct.nunique() == 2 else None
    gs = g[g.sel_be_frac.notna()]
    rows.append(dict(key=str(key), n=len(g), be_min_med=round(g.be_min.median(), 3), be_med_p10=round(g.be_med.quantile(.1), 3), be_med_p50=round(med, 3), be_med_p90=round(g.be_med.quantile(.9), 3),
                     mfe_over_sigma_h_med=round(g.mfe_over_sigma_h.median(), 3), share_mfe_ge_be_min=round(g.mfe_ge_be_min.mean(), 3), share_mfe_ge_be_med=round(g.mfe_ge_be_med.mean(), 3),
                     share_term_ge_be_med=round(g.term_ge_be_med.mean(), 3), target_first=round(g.target_first.mean(), 3), side_correct=round(g.side_correct.mean(), 3),
                     n_low_be=len(lo_), n_high_be=len(hi_), side_correct_low_be=round(lo_.side_correct.mean(), 3), side_correct_high_be=round(hi_.side_correct.mean(), 3),
                     target_first_low_be=round(lo_.target_first.mean(), 3), target_first_high_be=round(hi_.target_first.mean(), 3),
                     be_med_side_correct=round(g[g.side_correct].be_med.median(), 3), be_med_side_wrong=round(g[~g.side_correct].be_med.median(), 3),
                     mw_p_be_by_side_correct=float(mw.pvalue) if mw else None,
                     n_sel_be=len(gs), sel_be_p50=round(gs.sel_be_over_sigma_h.median(), 3) if len(gs) else None,
                     share_mfe_ge_sel_be=round(float(gs.mfe_ge_sel_be.mean()), 3) if len(gs) else None,
                     side_correct_and_mfe_lt_be_med=int((g.side_correct & ~g.mfe_ge_be_med).sum()),
                     power="n>=100" if len(g) >= 100 else "INSUFFICIENT_POWER"))
BE = pd.DataFrame(rows); BE.to_csv(PR / "p24_M4_breakeven_summary.csv", index=False); log(BE.T.to_string())

# 6. stored DOI families: candidate counts (structure only)
con = sqlite3.connect(f"file:{AUD / 'db_copies/control_plane.sqlite'}?mode=ro", uri=True)
D = pd.read_sql("select run_id, governed_direction, family_state, family_policy_version, candidate_symbols_json, metadata_json from doi_contract_families", con)
D["n_cand"] = D.candidate_symbols_json.apply(lambda s: len(json.loads(s)) if isinstance(s, str) and s.strip().startswith("[") else np.nan)
DS = D.groupby(["run_id", "governed_direction"]).agg(families=("n_cand", "size"), median=("n_cand", "median"), zero=("n_cand", lambda x: int((x == 0).sum())), one=("n_cand", lambda x: int((x == 1).sum()))).reset_index()
DS.to_csv(PR / "p24_M4_doi_family_candidate_counts.csv", index=False); log(DS.to_string())
log("DOI all:", D.groupby("run_id").n_cand.agg(["size", "median", lambda x: int((x == 0).sum())]).to_string())
log("family_policy_version:", D.family_policy_version.value_counts().to_dict(), "family_state:", D.family_state.value_counts().to_dict())
log("metadata sample:", str(D.metadata_json.dropna().iloc[0])[:1500] if D.metadata_json.notna().any() else None)
