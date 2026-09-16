"""p23_M3_thesis_outcomes: Track M3 (discovery). Directional outcome per unique thesis, independent of any contract.
Input: probes/p32_labels.csv (coordinator probe p32; labels are p32's, E1 verification running in parallel).
Unique thesis = (ticker, direction, decision_session); first row in run_id order kept.
Condition: run_id < 20260831 -> UNGOVERNED_PRE (books before governance); >= 20260831 -> GOVERNED. All TEST condition.
Directional outcome (vol-budget set, ALG-08): vb_dist = 1.5*sigma_a*sqrt(h/252); TARGET_FIRST_V = moved thesis way by thesis amount
within hold before invalidation. Also side_correct (terminal close in thesis direction), reached_V (MFE >= vb_dist at any time).
Structural set only where target>0 and correct side (target_distance_frac>0).
Side wrong: stop_dist = signed distance spot->invalidation; invalidation touched iff MAE >= stop_dist.
Outputs: p23_M3_thesis_outcomes.csv (row per unique thesis), p23_M3_thesis_tables.txt. Read-only. RESEARCH_ONLY."""
import os, numpy as np, pandas as pd
OUT = os.path.dirname(os.path.abspath(__file__))
L = pd.read_csv(os.path.join(OUT, "p32_labels.csv"), low_memory=False).sort_values(["run_id", "ticker", "direction"])
L["condition"] = np.where(L.run_id < "20260831", "UNGOVERNED_PRE", "GOVERNED")
L["presented_rows_for_thesis"] = L.groupby(["ticker", "direction", "decision_session"]).run_id.transform("size")
L["conditions_for_thesis"] = L.groupby(["ticker", "direction", "decision_session"]).condition.transform("nunique")
U = L.drop_duplicates(["ticker", "direction", "decision_session"]).copy()
sgn = np.where(U.direction == "CALL", 1.0, -1.0)
U["vb_dist"] = 1.5 * U.sigma_a * np.sqrt(U.hold_sessions / 252.0)
U["reached_V"] = U.mfe >= U.vb_dist
U["directional_success_V"] = U.label_V == "TARGET_FIRST"
U["valid_S"] = U.target_distance_frac > 0
U["directional_success_S"] = np.where(U.valid_S, U.label_S == "TARGET_FIRST", np.nan)
U["stop_dist"] = sgn * (1 - U.invalidation / U.spot)
U["inv_touched"] = U.mae >= U.stop_dist
U["side_wrong_class"] = np.where(U.side_correct, "", np.where(U.inv_touched, "INVALIDATION_TOUCHED", "TIMEOUT_NEGATIVE_NO_TOUCH"))
U["loss_over_stop"] = np.where(~U.side_correct, -U.terminal_return / U.stop_dist, np.nan)
U["mae_over_stop"] = U.mae / U.stop_dist
U["spot_path_mismatch_flag"] = (U.mae < -0.2) | (U.mfe < -0.2)  # whole window >20% away from book spot on the adverse/favourable side
U["hz"] = U.horizon_bucket
U.to_csv(os.path.join(OUT, "p23_M3_thesis_outcomes.csv"), index=False)

lines = []
P = lambda s: lines.append(str(s))
P(f"presented rows {len(L)}; unique theses {len(U)}; theses presented in both conditions {int((U.conditions_for_thesis>1).sum())}")
P("unique theses by condition x direction:\n" + pd.crosstab(U.condition, U.direction, margins=True).to_string())
P(f"spot_path_mismatch_flag rows: {int(U.spot_path_mismatch_flag.sum())}; sigma missing: {int(U.sigma_a.isna().sum())}")


def tab(g):
    n = len(g)
    return pd.Series(dict(n=n, power="INSUFFICIENT_POWER" if n < 100 else "", side_correct=g.side_correct.mean(), reached_V=g.reached_V.mean(),
                          TARGET_FIRST_V=(g.label_V == "TARGET_FIRST").mean(), INVALIDATION_FIRST_V=(g.label_V == "INVALIDATION_FIRST").mean(),
                          TIMEOUT_V=(g.label_V == "TIMEOUT").mean(), AMBIG_V=(g.label_V == "AMBIGUOUS_TOUCH_ORDER").mean(),
                          n_valid_S=int(g.valid_S.sum()), TARGET_FIRST_S=(g[g.valid_S].label_S == "TARGET_FIRST").mean() if g.valid_S.any() else np.nan,
                          med_terminal=g.terminal_return.median(), med_vb_dist=g.vb_dist.median(), med_mfe=g.mfe.median()))


T1 = U.groupby(["condition", "direction", "hz"]).apply(tab, include_groups=False)
T1b = U.groupby(["condition", "direction"]).apply(tab, include_groups=False)
T1c = U.groupby(["direction"]).apply(tab, include_groups=False)
pd.options.display.float_format = "{:.3f}".format
P("\nT1 directional outcome by condition x direction x horizon:\n" + T1.to_string())
P("\nT1b by condition x direction:\n" + T1b.to_string())
P("\nT1c by direction (all):\n" + T1c.to_string())
# side_correct x reached thesis amount
P("\nside_correct x TARGET_FIRST_V by condition x direction:\n" + pd.crosstab([U.condition, U.direction, U.side_correct], U.directional_success_V).to_string())
# side wrong
W = U[~U.side_correct]
P("\nside-wrong class by condition x direction:\n" + pd.crosstab([W.condition, W.direction], W.side_wrong_class, margins=True).to_string())
q = [0.1, 0.25, 0.5, 0.75, 0.9]
for (c, d, k), g in W.groupby(["condition", "direction", "side_wrong_class"]):
    tag = "INSUFFICIENT_POWER " if len(g) < 100 else ""
    P(f"{tag}{c} {d} {k} n={len(g)} loss/stop q10..q90 {np.round(g.loss_over_stop.quantile(q).values,3)} mae/stop {np.round(g.mae_over_stop.quantile(q).values,3)} "
      f"frac terminal loss > stop {np.mean(g.loss_over_stop>1):.3f} med stop_dist {g.stop_dist.median():.4f}")
open(os.path.join(OUT, "p23_M3_thesis_tables.txt"), "w").write("\n".join(lines))
T1.to_csv(os.path.join(OUT, "p23_M3_thesis_table_T1.csv"))
print("\n".join(lines))
