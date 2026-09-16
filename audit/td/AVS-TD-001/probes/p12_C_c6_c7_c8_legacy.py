"""p12_C_c6_c7_c8_legacy.py -- Track C legacy-field census on both stored runs (read-only).
C6 (legacy): monetisability_state / _state_timevalue / _status / _authority by CALL/PUT/OTHER (governed book).
C7: convexity_score distinct values and fraction == 2.0 on both runs' governed books and options CSVs.
C8: count rr_* columns present in each CSV of the primary run.
Output: p12_C_c6_c7_c8_legacy.out.json
"""
from __future__ import annotations
import json
from pathlib import Path
import pandas as pd

ROOT = Path(r"C:\Users\ACKVerissimo\AVSHUNTER-Intelligence")
HERE = Path(__file__).resolve().parent
RUNS = {"primary": "20260911_115904", "comparison": "20260910_150045"}
out: dict = {}


def side(s: pd.Series) -> pd.Series:
    u = s.astype(str).str.upper()
    return u.where(u.isin(["CALL", "PUT"]), "OTHER")


for label, run in RUNS.items():
    rd = ROOT / "data/output/runs" / run
    entry: dict = {}
    fb = pd.read_csv(rd / "intelligence_lab" / f"final_opportunity_book_{run}.csv", low_memory=False)
    fb["side"] = side(fb["governed_direction"])
    entry["book_shape"] = list(fb.shape)
    entry["side_counts"] = fb["side"].value_counts().to_dict()
    # C6 legacy states
    c6 = {}
    for col in ("monetisability_state", "monetisability_state_timevalue", "monetisability_status", "monetisability_authority",
                "monetisability_calculation_version", "monetisability_timevalue_model", "monetisability_reason"):
        if col in fb.columns:
            c6[col] = {k: {str(kk): int(vv) for kk, vv in v.items()} for k, v in
                       pd.crosstab(fb[col].fillna("<NA>").astype(str), fb["side"]).to_dict().items()}
    entry["c6_legacy_states"] = c6
    entry["c6_scenario_vocabulary_present"] = sorted({v for c in ("monetisability_state", "monetisability_state_timevalue")
                                                      if c in fb.columns for v in fb[c].dropna().astype(str).unique()
                                                      if v.startswith("SCENARIO_") or v in ("NOT_CURRENTLY_MONETISABLE", "NOT_EVALUATED_DATA_MISSING", "INDETERMINATE")})
    entry["c6_doi_columns_populated"] = {c: int(fb[c].notna().sum()) for c in fb.columns if c.startswith("doi_")}
    # C7 convexity
    c7 = {}
    for name, df in (("final_book", fb),):
        cs = pd.to_numeric(df["convexity_score"], errors="coerce")
        c7[name] = {"n": int(len(cs)), "n_nonnull": int(cs.notna().sum()), "n_distinct": int(cs.nunique()),
                    "value_counts": {str(k): int(v) for k, v in cs.value_counts(dropna=False).head(12).items()},
                    "fraction_eq_2": float((cs == 2.0).mean()),
                    "by_side_fraction_eq_2": {s: float((cs[fb["side"] == s] == 2.0).mean()) for s in ("CALL", "PUT", "OTHER")}}
        for extra in ("doi_convexity_score", "doi_convexity_label", "convexity_label", "event_convexity_score"):
            if extra in df.columns:
                c7[name][extra + "_nonnull"] = int(df[extra].notna().sum())
    opt_path = rd / "options" / f"options_intelligence_{run}.csv"
    opt = pd.read_csv(opt_path, low_memory=False, usecols=lambda c: c in {"ticker", "convexity_score", "governed_direction", "event_convexity_score", "doi_convexity_score", "doi_convexity_label"})
    cs = pd.to_numeric(opt["convexity_score"], errors="coerce")
    c7["options_csv"] = {"n": int(len(cs)), "n_distinct": int(cs.nunique()), "fraction_eq_2": float((cs == 2.0).mean()),
                         "value_counts": {str(k): int(v) for k, v in cs.value_counts(dropna=False).head(12).items()},
                         "cols_present": [c for c in opt.columns]}
    entry["c7_convexity"] = c7
    out[label] = entry

# C8: rr_* columns across primary run CSVs
run = RUNS["primary"]; rd = ROOT / "data/output/runs" / run
c8 = {}
for rel in [f"intelligence_lab/final_opportunity_book_{run}.csv", f"intelligence_lab/lab_triage_view_{run}.csv",
            "intelligence_lab/lab_signal_book_v3.csv", f"morning_validation/morning_validated_trades_{run}.csv",
            f"morning_validation/morning_candidates_{run}.csv", f"options/options_intelligence_{run}.csv",
            f"execution/execution_v3_5_{run}.csv", f"trades/execution_gated_{run}.csv", f"trades/execution_actionable_{run}.csv"]:
    p = rd / rel
    if p.is_file():
        cols = pd.read_csv(p, nrows=0, low_memory=False).columns
        rr = [c for c in cols if c.startswith("rr_") or c in ("rr", "option_rr", "rr_options")]
        c8[rel] = {"n_cols": len(cols), "rr_cols": rr, "n_rr": len(rr)}
# population of rr_ columns on the governed book
fbp = pd.read_csv(rd / "intelligence_lab" / f"final_opportunity_book_{run}.csv", low_memory=False)
c8["final_book_rr_population"] = {c: int(fbp[c].notna().sum()) for c in fbp.columns if c.startswith("rr_")}
out["c8_rr_columns"] = c8
(HERE / "p12_C_c6_c7_c8_legacy.out.json").write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
print(json.dumps(out, indent=2, default=str))
