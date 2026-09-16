"""p12_C_c6_crosstab.py -- Track C / C6, C7, C9, C10 summaries from p12_C_offline_sample.py outputs (read-only).
Output: p12_C_c6_crosstab.out.json
"""
from __future__ import annotations
import json
from pathlib import Path
import pandas as pd

HERE = Path(__file__).resolve().parent
allc = pd.read_csv(HERE / "p12_C_offline_assessments_all_contracts.csv", low_memory=False)
fam = pd.read_csv(HERE / "p12_C_offline_assessments.csv", low_memory=False)
g = allc.loc[allc["pass"] == "GARCH_SUB"].copy()
out = {}

# C6: recompute state on every contract with a grid; mismatches
has = g["net:REACHABLE:LATE:BASE"].notna()
out["c6_contracts_with_grid"] = {d: int((has & (g.direction == d)).sum()) for d in ("CALL", "PUT")}
out["c6_mismatches"] = int((has & (g["tester_state"] != g["monetisability_state"])).sum())
out["c6_grid_but_state_not_scenario"] = int((has & ~g["monetisability_state"].str.startswith(("SCENARIO_", "NOT_CURRENTLY"))).sum())
out["c6_no_grid_states"] = g.loc[~has].groupby("direction")["monetisability_state"].value_counts().unstack(fill_value=0).to_dict("index")

# NOT_EVALUATED_DATA_MISSING causes
m = g.loc[g["monetisability_state"] == "NOT_EVALUATED_DATA_MISSING"]
cause = pd.DataFrame({
    "direction": m["direction"],
    "no_structural_target": m["structural_target"].isna(),
    "no_invalidation": m["invalidation"].isna(),
    "no_forecast_vol": m["annual_forecast_vol"].isna(),
    "no_iv": m["iv"].isna(),
    "no_bid_or_ask": m["bid"].isna() | m["ask"].isna(),
})
out["not_evaluated_causes"] = {d: {c: int(cause.loc[cause.direction == d, c].sum()) for c in cause.columns if c != "direction"}
                               | {"n": int((cause.direction == d).sum())} for d in ("CALL", "PUT")}
out["not_evaluated_only_cause_is_missing_target"] = {
    d: int((cause.direction == d).__and__(cause.no_structural_target & ~cause.no_invalidation & ~cause.no_forecast_vol & ~cause.no_iv & ~cause.no_bid_or_ask).sum())
    for d in ("CALL", "PUT")}

# family rows: legacy book state vs v2 state
out["family_legacy_vs_v2"] = {d: pd.crosstab(fam.loc[fam.direction == d, "legacy_book_monetisability_state"].fillna("NULL"),
                                             fam.loc[fam.direction == d, "monetisability_state"]).to_dict("index") for d in ("CALL", "PUT")}
leg_mon = fam["legacy_book_monetisability_state"].eq("MONETISABLE")
out["family_legacy_MONETISABLE_but_v2_not_SCENARIO_MONETISABLE"] = {
    d: int((leg_mon & (fam.direction == d) & fam["monetisability_state"].ne("SCENARIO_MONETISABLE")).sum()) for d in ("CALL", "PUT")}

# C7 convexity on contracts with a score
cs = g.dropna(subset=["convexity_score"])
out["c7_convexity"] = {d: {"n": int((cs.direction == d).sum()), "distinct": int(cs.loc[cs.direction == d, "convexity_score"].round(10).nunique()),
                           "median": float(cs.loc[cs.direction == d, "convexity_score"].median()),
                           "iqr": [float(cs.loc[cs.direction == d, "convexity_score"].quantile(q)) for q in (.25, .75)],
                           "max_share_single_value": float(cs.loc[cs.direction == d, "convexity_score"].round(10).value_counts(normalize=True).iloc[0]),
                           "labels": cs.loc[cs.direction == d, "convexity_label"].value_counts().to_dict()} for d in ("CALL", "PUT")}
out["c7_legacy_book_convexity_on_sample"] = fam["legacy_book_convexity_score"].value_counts(dropna=False).to_dict()

# C9 propagation
out["c9"] = {d: {"reach_rows": int(((g.direction == d) & g["reach_ratio"].notna()).sum()),
                 "reach_rows_UNVALIDATED_INPUT": int(((g.direction == d) & g["reach_ratio"].notna() & g["reach_quality_state"].eq("UNVALIDATED_INPUT")).sum()),
                 "validation_state_UNVALIDATED": int(((g.direction == d) & g["validation_state"].eq("UNVALIDATED")).sum()),
                 "bias_multiplier_applied_true": int(((g.direction == d) & g["bias_multiplier_applied"].astype(str).str.lower().eq("true")).sum()),
                 "economics_rows_with_grid": int(((g.direction == d) & has).sum()),
                 "economics_rows_carrying_validation_state": int(((g.direction == d) & has & g["economics_carries_validation_state"].astype(str).str.lower().eq("true")).sum())}
             for d in ("CALL", "PUT")}

# C10: field semantics of assessment.ranking_score_uncalibrated
out["c10_ranking_score_field"] = {
    "equals_v2_where_v2_present": int((g["utility_v2"].notna() & (g["assessment_ranking_score_uncalibrated"] == g["utility_v2"])).sum()),
    "v2_present": int(g["utility_v2"].notna().sum()),
    "equals_v1_where_v2_absent_and_v1_present": int((g["utility_v2"].isna() & g["utility_v1"].notna() & (g["assessment_ranking_score_uncalibrated"] == g["utility_v1"])).sum()),
    "v2_absent_v1_present": int((g["utility_v2"].isna() & g["utility_v1"].notna()).sum()),
}
# premise on family rows
f = fam.dropna(subset=["net:REACHABLE:LATE:BASE", "net:STRUCTURAL_DISCLOSURE:LATE:BASE"])
out["premise_family_rows"] = {d: {"n": int((f.direction == d).sum()),
                                  "median_reachable_net": float(f.loc[f.direction == d, "net:REACHABLE:LATE:BASE"].median()),
                                  "median_structural_net": float(f.loc[f.direction == d, "net:STRUCTURAL_DISCLOSURE:LATE:BASE"].median()),
                                  "median_reach_ratio": float(f.loc[f.direction == d, "reach_ratio"].median()),
                                  "structural_ge_floor_but_reachable_below": int(((f.direction == d) & (f["net:STRUCTURAL_DISCLOSURE:LATE:BASE"] >= .25) & (f["net:REACHABLE:LATE:BASE"] < .25)).sum()),
                                  "reachable_ge_floor_but_structural_below": int(((f.direction == d) & (f["net:REACHABLE:LATE:BASE"] >= .25) & (f["net:STRUCTURAL_DISCLOSURE:LATE:BASE"] < .25)).sum())}
                              for d in ("CALL", "PUT")}
(HERE / "p12_C_c6_crosstab.out.json").write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
print(json.dumps(out, indent=1, default=str))
