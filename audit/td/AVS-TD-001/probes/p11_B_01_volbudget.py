"""p11_B_01_volbudget.py — Track B, check B1 (REQ-WP1-01/02, ALG-01).

Read-only probe. For both stored runs:
  * does the Layer-3 output carry the v2 cumulative fields?
  * legacy ratio l3_expected_move_6_10d / l3_expected_move_1_5d distribution
  * offline reproduction of v2 via domain.volatility_budget on the run's
    l3_forward_realised_vol values, and the resulting 10d/5d, 20d/5d ratios
  * ALG-01 worked example, REQ-WP1-02 fixture, edge cases
  * CALL/PUT/OTHER split by the run's governed_direction
Outputs: p11_B_01_volbudget.json beside this script.
"""
from __future__ import annotations
import json, math, os, sys
import numpy as np, pandas as pd

ROOT = r"C:\Users\ACKVerissimo\AVSHUNTER-Intelligence"
sys.path.insert(0, ROOT)
from domain.volatility_budget import calculate_volatility_budget, checkpoint_fields  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
RUNS = ["20260911_115904", "20260910_150045"]
V2 = ["expected_move_5d_fraction", "expected_move_10d_fraction", "expected_move_20d_fraction",
      "volatility_budget_version", "horizon_convention", "forecast_horizon_basis",
      "vol_validation_state", "l3_expected_move_legacy_deprecated", "l3_expected_move_legacy_unit"]
LEG = ["l3_expected_move_1_5d", "l3_expected_move_6_10d", "l3_expected_move_11_20d",
       "garch_expected_move_1_5d", "garch_expected_move_6_10d", "garch_expected_move_11_20d",
       "l3_forward_realised_vol", "forward_realised_vol", "l3_forward_realised_vol"]

out: dict = {"runs": {}, "offline": {}}


def stats(s: pd.Series) -> dict:
    s = pd.to_numeric(s, errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
    if s.empty:
        return {"n": 0}
    return {"n": int(len(s)), "min": float(s.min()), "max": float(s.max()),
            "median": float(s.median()), "n_in_1407_1421": int(((s >= 1.407) & (s <= 1.421)).sum()),
            "n_outside_1407_1421": int(((s < 1.407) | (s > 1.421)).sum()),
            "n_eq_0.4142_pm_0.001": int(((s - 0.4142).abs() <= 0.001).sum())}


def direction_map(run: str) -> pd.Series:
    p = f"{ROOT}/data/output/runs/{run}/intelligence_lab/final_opportunity_book_{run}.csv"
    df = pd.read_csv(p, usecols=["ticker", "governed_direction"], low_memory=False)
    d = df.drop_duplicates("ticker").set_index("ticker")["governed_direction"].astype(str).str.upper()
    return d.where(d.isin(["CALL", "PUT"]), "OTHER")


for run in RUNS:
    base = f"{ROOT}/data/output/runs/{run}"
    files = {
        "qomega/garch_forecasts": f"{base}/qomega/garch_forecasts_{run}.csv",
        "options/options_intelligence": f"{base}/options/options_intelligence_{run}.csv",
        "execution/execution_v3_5": f"{base}/execution/execution_v3_5_{run}.csv",
        "intelligence_lab/final_opportunity_book": f"{base}/intelligence_lab/final_opportunity_book_{run}.csv",
    }
    dmap = direction_map(run)
    rr: dict = {"direction_map_counts": dmap.value_counts().to_dict(), "files": {}}
    for label, path in files.items():
        cols = list(pd.read_csv(path, nrows=0).columns)
        v2_present = [c for c in V2 if c in cols]
        leg_present = [c for c in LEG if c in cols]
        use = ["ticker"] + leg_present + [c for c in ("governed_direction",) if c in cols]
        df = pd.read_csv(path, usecols=sorted(set(use)), low_memory=False)
        rec: dict = {"nrows": int(len(df)), "ncols": len(cols), "v2_present": v2_present,
                     "v2_absent": [c for c in V2 if c not in cols], "legacy_present": leg_present}
        pre = "l3_" if "l3_expected_move_1_5d" in cols else ("garch_" if "garch_expected_move_1_5d" in cols else None)
        if pre:
            a = pd.to_numeric(df[f"{pre}expected_move_1_5d"], errors="coerce")
            b = pd.to_numeric(df[f"{pre}expected_move_6_10d"], errors="coerce")
            c = pd.to_numeric(df[f"{pre}expected_move_11_20d"], errors="coerce")
            df["_dir"] = df["ticker"].map(dmap).fillna("OTHER") if "governed_direction" not in cols \
                else df["governed_direction"].astype(str).str.upper().where(lambda s: s.isin(["CALL", "PUT"]), "OTHER")
            rec["legacy_unit_hint"] = {"em_1_5d_min": float(a.min()), "em_1_5d_max": float(a.max()),
                                      "em_1_5d_median": float(a.median()),
                                      "n_gt_1": int((a > 1).sum()), "n_le_1": int((a <= 1).sum()),
                                      "n_zero": int((a == 0).sum()), "n_null": int(a.isna().isna().sum() - a.notna().sum())}
            rec["legacy_ratio_6_10_over_1_5"] = {"ALL": stats(b / a)}
            rec["legacy_ratio_11_20_over_6_10"] = {"ALL": stats(c / b)}
            rec["legacy_cumulative_10_over_5"] = {"ALL": stats((a + b) / a)}
            for d in ("CALL", "PUT", "OTHER"):
                m = df["_dir"] == d
                rec["legacy_ratio_6_10_over_1_5"][d] = stats((b / a)[m])
                rec["legacy_cumulative_10_over_5"][d] = stats(((a + b) / a)[m])
            rec["n_6_10_lt_1_5"] = int((b < a).sum())
        vcol = "l3_forward_realised_vol" if "l3_forward_realised_vol" in cols else None
        if vcol:
            v = pd.to_numeric(df[vcol], errors="coerce")
            rec["forward_realised_vol"] = {"n": int(v.notna().sum()), "min": float(v.min()), "max": float(v.max()),
                                          "median": float(v.median()), "n_null": int(v.isna().sum()),
                                          "n_le_0": int((v <= 0).sum()), "n_gt_3": int((v > 3).sum())}
            # offline v2 reproduction row by row
            recs = [checkpoint_fields(None if pd.isna(x) else float(x)) for x in v]
            e5 = pd.Series([r["expected_move_5d_fraction"] for r in recs], dtype="float64")
            e10 = pd.Series([r["expected_move_10d_fraction"] for r in recs], dtype="float64")
            e20 = pd.Series([r["expected_move_20d_fraction"] for r in recs], dtype="float64")
            rec["offline_v2_ratio_10_over_5"] = {"ALL": stats(e10 / e5)}
            rec["offline_v2_ratio_20_over_5"] = {"ALL": stats(e20 / e5)}
            for d in ("CALL", "PUT", "OTHER"):
                m = (df["_dir"] == d).values
                rec["offline_v2_ratio_10_over_5"][d] = stats((e10 / e5)[m])
            rec["offline_v2_null_count"] = int(e5.isna().sum())
            rec["offline_v2_version_set"] = sorted({r["volatility_budget_version"] for r in recs})
            rec["offline_v2_horizon_convention_set"] = sorted({r["horizon_convention"] for r in recs})
            rec["offline_v2_basis_set"] = sorted({r["forecast_horizon_basis"] for r in recs})
            # relationship of legacy 1_5d (percent, calendar-day) to v2 5d fraction
            if pre == "l3_":
                k = (a / 100.0) / e5
                rec["legacy_1_5d_pct_over_100_div_v2_5d"] = stats(k) | {"sqrt_5_over_7": math.sqrt(5 / 7)}
                rec["n_legacy_never_equals_v2"] = int(((a / 100.0 - e5).abs() > 1e-9).sum())
        rr["files"][label] = rec
    out["runs"][run] = rr

# ALG-01 worked example
w = {h: calculate_volatility_budget(0.30, h).expected_move_fraction for h in (5, 10, 20)}
out["offline"]["alg01_worked_example_sigma_0.30"] = {
    "h5": w[5], "h10": w[10], "h20": w[20], "ratio_10_5": w[10] / w[5],
    "expected": {"h5": 0.04226, "h10": 0.05976, "h20": 0.08452},
    "pass": all(abs(w[h] - e) < 5e-5 for h, e in ((5, 0.04226), (10, 0.05976), (20, 0.08452)))}
# REQ-WP1-02 fixture
f = calculate_volatility_budget(0.40, 7)
out["offline"]["req_wp1_02_fixture_0.40_h7"] = f.to_dict() | {"expected": 0.06667, "pass": abs(f.expected_move_fraction - 0.06667) < 5e-5}
# edge cases
edge = {}
for label, sig, h in (("sigma_null", None, 5), ("sigma_0", 0.0, 5), ("sigma_neg", -0.2, 5), ("sigma_3.5", 3.5, 5),
                      ("sigma_3.0_boundary", 3.0, 5), ("sigma_nan", float("nan"), 5)):
    edge[label] = calculate_volatility_budget(sig, h).to_dict()
for label, h in (("h0", 0), ("h21", 21), ("h-1", -1), ("h5.5", 5.5)):
    try:
        edge[label] = calculate_volatility_budget(0.3, h).to_dict()
    except Exception as e:  # noqa: BLE001
        edge[label] = f"{type(e).__name__}: {e}"
out["offline"]["edge_cases"] = edge
out["offline"]["checkpoint_fields_0.30"] = checkpoint_fields(0.30)

with open(os.path.join(HERE, "p11_B_01_volbudget.json"), "w", encoding="utf-8") as fh:
    json.dump(out, fh, indent=2, default=str)
print(json.dumps(out, indent=1, default=str)[:12000])
