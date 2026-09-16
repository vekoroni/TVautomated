"""p23_M3_coverage_addendum: coverage of option history by run and snapshot date; position of the priced snapshot inside the hold window
(calendar days after decision_session / hold calendar span); side-correct vs monetised on unique theses with sessions 1..h. Read-only. RESEARCH_ONLY."""
import os, numpy as np, pandas as pd
OUT = os.path.dirname(os.path.abspath(__file__))
M = pd.read_csv(os.path.join(OUT, "p23_M3_monetisation.csv"), low_memory=False)
U = M.sort_values("run_id").drop_duplicates(["ticker", "direction", "decision_session"])
print("coverage_state by run (unique theses):\n", pd.crosstab([U.run_id, U.decision_session], U.coverage_state, margins=True).to_string())
p = U[U.coverage_state == "PRICED"].copy()
print("\nbest_bid_date by condition x direction:\n", pd.crosstab(p.best_bid_date, [p.condition, p.direction], margins=True).to_string())
span = (pd.to_datetime(p.window_end) - pd.to_datetime(p.decision_session)).dt.days
pos = (pd.to_datetime(p.best_bid_date) - pd.to_datetime(p.decision_session)).dt.days
p["snap_pos_frac"] = pos / span
print("\nsnapshot position in window (fraction of calendar span) quantiles by condition x direction:\n",
      p.groupby(["condition", "direction"]).snap_pos_frac.quantile([.1, .5, .9]).unstack().round(2).to_string())
p["mon125"] = p.monetised_125.astype(float) > 0
print("\nmass location (unique priced theses):\n", pd.crosstab([p.condition, p.direction], [p.side_correct, p.mon125], normalize="index").round(3).to_string())
print("\nmass location all conditions by direction:\n", pd.crosstab(p.direction, [p.side_correct, p.mon125], margins=True).to_string())
print("\npriced vs all-labelled side_correct rate (selection check):\n", pd.DataFrame({"priced": p.groupby(["condition","direction"]).side_correct.mean(),
      "all": U.groupby(["condition","direction"]).side_correct.mean(), "priced_TF_V": p.groupby(["condition","direction"]).label_V.apply(lambda s:(s=="TARGET_FIRST").mean()),
      "all_TF_V": U.groupby(["condition","direction"]).label_V.apply(lambda s:(s=="TARGET_FIRST").mean())}).round(3).to_string())
print("\nside_mismatch rows (CALL with P symbol / PUT with C symbol) by run:\n", M[M.contract_state=="SIDE_MISMATCH"].groupby(["run_id","direction"]).size().to_string())
