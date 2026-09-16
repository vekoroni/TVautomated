"""p12_C_c2_c3_reach_geometry.py -- Track C / C2 reachability + C3 geometry on the primary governed book (read-only).

C2: recompute reachable_target_spot / reach_ratio per ALG-02 (e_h = sigma_a * sqrt(h/252), k = 1.5) on every
    directed row of intelligence_lab/final_opportunity_book_<run>.csv, compare to domain.reachability output
    (within 1e-6), look for any published doi_reach_* field, reproduce the 19-GO-row verification figure.
C3: count wrong-side target / invalidation per direction and cross-tab with named exception fields.
Outputs: p12_C_c2_c3_reach_geometry.out.json and p12_C_c2_reach_rows.csv beside this script.
"""
from __future__ import annotations
import json, math, sys
from pathlib import Path
import numpy as np, pandas as pd

ROOT = Path(r"C:\Users\ACKVerissimo\AVSHUNTER-Intelligence")
sys.path.insert(0, str(ROOT))
from domain.volatility_budget import calculate_volatility_budget  # noqa: E402
from domain.reachability import assess_reachability  # noqa: E402

RUN = "20260911_115904"
RD = ROOT / "data/output/runs" / RUN
HERE = Path(__file__).resolve().parent
K = 1.5
HOLD = {"1_5d": 5, "6_10d": 10, "11_20d": 20}
out: dict = {"run": RUN, "k": K}

fb = pd.read_csv(RD / "intelligence_lab" / f"final_opportunity_book_{RUN}.csv", low_memory=False)
out["book_shape"] = list(fb.shape)
out["governed_direction_counts"] = fb["governed_direction"].value_counts(dropna=False).to_dict()

# --- published reachability fields anywhere? ---------------------------------------------------------
pub = {}
for label, path in {
    "final_book": RD / "intelligence_lab" / f"final_opportunity_book_{RUN}.csv",
    "lab_triage": RD / "intelligence_lab" / f"lab_triage_view_{RUN}.csv",
    "morning_validated": RD / "morning_validation" / f"morning_validated_trades_{RUN}.csv",
    "options_csv": RD / "options" / f"options_intelligence_{RUN}.csv",
    "execution_gated": RD / "trades" / f"execution_gated_{RUN}.csv",
}.items():
    if path.is_file():
        cols = pd.read_csv(path, nrows=0, low_memory=False).columns
        pub[label] = sorted(c for c in cols if any(s in c.lower() for s in (
            "reach_ratio", "reachable_target", "volatility_budget", "structural_distance", "sigma_multiple",
            "expected_move_hold", "expected_move_5d_fraction", "expected_move_10d_fraction",
            "bias_multiplier", "validation_state", "l3_forward_realised_vol", "forecast_vol_annual_fraction",
            "forward_realised_vol", "garch_forecast_vol", "dte_inside_hold", "applicability")))
out["published_reachability_fields"] = pub

# --- C2 recompute on directed rows -------------------------------------------------------------------
d = fb.copy()
d["dir"] = d["governed_direction"].astype(str).str.upper()
d["directed"] = d["dir"].isin(["CALL", "PUT"])
d["S0"] = pd.to_numeric(d["underlying_price"], errors="coerce")
d["Ts"] = pd.to_numeric(d["structural_target"], errors="coerce")
d.loc[d["Ts"].isna(), "Ts"] = pd.to_numeric(d.loc[d["Ts"].isna(), "target_price"], errors="coerce")
d["I"] = pd.to_numeric(d["invalidation_price"], errors="coerce")
d["sigma"] = pd.to_numeric(d["garch_forecast_vol"], errors="coerce")
d["h"] = d["hold_period"].map(HOLD)
d["sign"] = np.where(d["dir"] == "CALL", 1.0, np.where(d["dir"] == "PUT", -1.0, np.nan))
d["e_h"] = d["sigma"] * np.sqrt(d["h"] / 252.0)
d["my_reachable"] = d["S0"] * (1 + d["sign"] * K * d["e_h"])
d["my_struct_dist"] = (d["Ts"] - d["S0"]).abs() / d["S0"]
d["my_reach_ratio"] = d["my_struct_dist"] / d["e_h"]
d["target_wrong_side"] = d["directed"] & d["Ts"].notna() & (d["sign"] * (d["Ts"] - d["S0"]) <= 0)
d["inval_wrong_side"] = d["directed"] & d["I"].notna() & (d["sign"] * (d["S0"] - d["I"]) <= 0)

# production function comparison
fn_reach, fn_ratio, fn_state, fn_vstate, fn_bias, maxdiff = [], [], [], [], [], 0.0
for _, r in d.iterrows():
    if not r["directed"] or not (r["S0"] > 0) or pd.isna(r["h"]):
        fn_reach.append(np.nan); fn_ratio.append(np.nan); fn_state.append("NOT_CALLED"); fn_vstate.append(None); fn_bias.append(None)
        continue
    budget = calculate_volatility_budget(None if pd.isna(r["sigma"]) else float(r["sigma"]), int(r["h"]))
    a = assess_reachability(direction=r["dir"], origin_spot=float(r["S0"]),
                            structural_target_spot=None if pd.isna(r["Ts"]) else float(r["Ts"]),
                            budget=budget, sigma_multiple=K)
    fn_reach.append(a.reachable_target_spot if a.reachable_target_spot is not None else np.nan)
    fn_ratio.append(a.reach_ratio if a.reach_ratio is not None else np.nan)
    fn_state.append(a.quality_state); fn_vstate.append(a.validation_state); fn_bias.append(a.bias_multiplier_applied)
    if a.reach_ratio is not None:
        maxdiff = max(maxdiff, abs(a.reach_ratio - r["my_reach_ratio"]), abs(a.reachable_target_spot - r["my_reachable"]))
d["fn_reachable"] = fn_reach; d["fn_reach_ratio"] = fn_ratio; d["fn_quality_state"] = fn_state
d["fn_validation_state"] = fn_vstate; d["fn_bias_multiplier_applied"] = fn_bias
out["c2_max_abs_diff_formula_vs_function"] = maxdiff
out["c2_function_quality_state_counts"] = pd.crosstab(d.loc[d["directed"], "dir"], d.loc[d["directed"], "fn_quality_state"]).to_dict()
out["c2_function_validation_state_counts"] = d.loc[d["directed"], "fn_validation_state"].value_counts(dropna=False).to_dict()
out["c2_function_bias_applied_counts"] = d.loc[d["directed"], "fn_bias_multiplier_applied"].value_counts(dropna=False).astype(int).to_dict()


def dist(s: pd.Series) -> dict:
    s = s.dropna()
    if s.empty:
        return {"n": 0}
    return {"n": int(len(s)), "median": float(s.median()), "q1": float(s.quantile(.25)), "q3": float(s.quantile(.75)),
            "n_gt_1_5": int((s > 1.5).sum()), "n_gt_3": int((s > 3).sum()), "n_le_1": int((s <= 1).sum()),
            "min": float(s.min()), "max": float(s.max())}


valid = d["directed"] & d["fn_reach_ratio"].notna()
out["c2_reach_ratio_distribution"] = {
    side: dist(d.loc[valid & (d["dir"] == side), "fn_reach_ratio"]) for side in ("CALL", "PUT")}
out["c2_reach_ratio_distribution"]["ALL_DIRECTED"] = dist(d.loc[valid, "fn_reach_ratio"])
out["c2_rows_directed"] = int(d["directed"].sum())
out["c2_rows_with_reach_ratio"] = int(valid.sum())
out["c2_rows_directed_missing_inputs"] = {
    "missing_sigma": int((d["directed"] & d["sigma"].isna()).sum()),
    "missing_target": int((d["directed"] & d["Ts"].isna()).sum()),
    "missing_hold": int((d["directed"] & d["h"].isna()).sum()),
    "missing_spot": int((d["directed"] & ~(d["S0"] > 0)).sum()),
}
put_ok = d.loc[valid & (d["dir"] == "PUT")]
out["c2_put_reachable_below_spot"] = {"n": int(len(put_ok)), "n_below_spot": int((put_ok["fn_reachable"] < put_ok["S0"]).sum())}
call_ok = d.loc[valid & (d["dir"] == "CALL")]
out["c2_call_reachable_above_spot"] = {"n": int(len(call_ok)), "n_above_spot": int((call_ok["fn_reachable"] > call_ok["S0"]).sum())}

# GO rows verification figure
lab = pd.read_csv(RD / "intelligence_lab" / "lab_signal_book_v3.csv", low_memory=False)
g = lab.copy()
g["dir"] = g["governed_direction"].astype(str).str.upper()
g["S0"] = pd.to_numeric(g["underlying_price"], errors="coerce")
g["Ts"] = pd.to_numeric(g["structural_target"], errors="coerce")
g["sigma"] = pd.to_numeric(g["garch_forecast_vol"], errors="coerce")
g["dist"] = (g["Ts"] - g["S0"]).abs() / g["S0"]
go = {}
for label, h in (("h_from_hold_period", g["hold_period"].map(HOLD)), ("h_5_all", 5), ("h_10_all", 10), ("h_20_all", 20)):
    rr = g["dist"] / (g["sigma"] * np.sqrt(pd.Series(h, index=g.index) / 252.0))
    go[label] = {"n": int(rr.notna().sum()), "median": float(rr.median()), "n_gt_3": int((rr > 3).sum()),
                 "values": [round(float(x), 3) for x in rr]}
# also legacy differenced field: structural distance / (garch_expected_move_6_10d/100)
rr_legacy = g["dist"] / (pd.to_numeric(g["garch_expected_move_6_10d"], errors="coerce") / 100.0)
go["legacy_garch_expected_move_6_10d_pct"] = {"median": float(rr_legacy.median()), "n_gt_3": int((rr_legacy > 3).sum())}
rr_legacy2 = g["dist"] / ((pd.to_numeric(g["garch_expected_move_1_5d"], errors="coerce") + pd.to_numeric(g["garch_expected_move_6_10d"], errors="coerce")) / 100.0)
go["legacy_cumulative_1_5d_plus_6_10d_pct"] = {"median": float(rr_legacy2.median()), "n_gt_3": int((rr_legacy2 > 3).sum())}
out["c2_go_rows_verification"] = go
out["c2_go_rows_tickers"] = g["ticker"].tolist()

# --- C3 geometry --------------------------------------------------------------------------------------
geo = {}
for side in ("CALL", "PUT"):
    m = d["directed"] & (d["dir"] == side)
    geo[side] = {
        "directed_rows": int(m.sum()),
        "target_present": int((m & d["Ts"].notna()).sum()),
        "inval_present": int((m & d["I"].notna()).sum()),
        "target_wrong_side": int((m & d["target_wrong_side"]).sum()),
        "inval_wrong_side": int((m & d["inval_wrong_side"]).sum()),
        "either_wrong_side": int((m & (d["target_wrong_side"] | d["inval_wrong_side"])).sum()),
        "both_present_and_valid": int((m & d["Ts"].notna() & d["I"].notna() & ~d["target_wrong_side"] & ~d["inval_wrong_side"]).sum()),
    }
geo["OTHER"] = {"rows": int((~d["directed"]).sum()), "note": "STRANGLE/UNRESOLVED: no directional geometry defined"}
out["c3_geometry_counts"] = geo
wrong = d[d["directed"] & (d["target_wrong_side"] | d["inval_wrong_side"])]
xt = {}
for col in ("invalidation_state", "invalidation_source", "target_state", "target_unresolved_reason",
            "monetisability_state", "monetisability_state_timevalue", "monetisability_status", "contract_data_state"):
    if col in wrong.columns:
        xt[col] = wrong[col].fillna("<NA>").astype(str).value_counts().to_dict()
out["c3_wrong_side_rows_crosstab"] = xt
named = {"WRONG_SIDED", "DATA_DEFECT_WRONG_SIDE", "MISSING_AUTHORITATIVE", "GEOMETRY_INVALID", "INVALIDATION_MISSING"}
def is_named(row):
    vals = " ".join(str(row.get(c, "")) for c in ("invalidation_state", "invalidation_source", "target_state", "target_unresolved_reason"))
    return any(n in vals for n in named)
out["c3_wrong_side_rows_with_named_exception"] = int(wrong.apply(is_named, axis=1).sum()) if len(wrong) else 0
out["c3_wrong_side_rows_valued_legacy_MONETISABLE"] = int((wrong["monetisability_state"].astype(str) == "MONETISABLE").sum()) if len(wrong) else 0
out["c3_wrong_side_rows"] = wrong[["ticker", "dir", "S0", "Ts", "I", "target_wrong_side", "inval_wrong_side",
                                   "invalidation_state", "invalidation_source", "target_state", "monetisability_state",
                                   "monetisability_state_timevalue", "contract_symbol"]].to_dict(orient="records")
out["c3_invalidation_state_counts_by_dir"] = pd.crosstab(d["dir"], d["invalidation_state"].fillna("<NA>")).to_dict()
out["c3_invalidation_source_counts"] = d["invalidation_source"].fillna("<NA>").value_counts().to_dict()
man = json.loads((RD / "final_run_manifest.json").read_text(encoding="utf-8-sig"))
out["c3_manifest_missing_selected_handoff"] = man.get("missing_selected_handoff")
out["c3_directed_rows_missing_invalidation"] = {side: int((d["directed"] & (d["dir"] == side) & d["I"].isna()).sum()) for side in ("CALL", "PUT")}
out["c3_directed_rows_missing_target"] = {side: int((d["directed"] & (d["dir"] == side) & d["Ts"].isna()).sum()) for side in ("CALL", "PUT")}

d[["ticker", "dir", "directed", "S0", "Ts", "I", "sigma", "h", "e_h", "my_reachable", "my_struct_dist", "my_reach_ratio",
   "fn_reachable", "fn_reach_ratio", "fn_quality_state", "fn_validation_state", "fn_bias_multiplier_applied",
   "target_wrong_side", "inval_wrong_side", "invalidation_state", "invalidation_source", "target_state",
   "monetisability_state", "contract_symbol"]].to_csv(HERE / "p12_C_c2_reach_rows.csv", index=False)
(HERE / "p12_C_c2_c3_reach_geometry.out.json").write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
print(json.dumps({k: v for k, v in out.items() if k != "c3_wrong_side_rows"}, indent=2, default=str))
print("wrong-side rows:", len(out["c3_wrong_side_rows"]))
