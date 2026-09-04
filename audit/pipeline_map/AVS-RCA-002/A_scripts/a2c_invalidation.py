"""AVS-RCA-002 A2c - invalidation-less rows vs granted authority. READ ONLY."""
import pandas as pd, pathlib
RID="20260904_004338"; RUN=pathlib.Path(r"data\output\runs")/RID
LAB=pd.read_csv(RUN/"intelligence_lab"/f"final_opportunity_book_{RID}.csv", low_memory=False)
MC=pd.read_csv(RUN/"morning_validation"/f"morning_candidates_{RID}.csv", low_memory=False)
def blank(s): return s.isna() | (s.astype(str).str.strip().isin(["","nan","None","NaN","<NA>"]))
lb=blank(LAB["invalidation_price"])
print("LAB blank invalidation_price:", int(lb.sum()), "dirs:", LAB.loc[lb,"final_direction"].value_counts().to_dict())
print("\ncross-tab eod_candidate_status x blank:")
print(pd.crosstab(LAB["eod_candidate_status"], lb).to_string())
mcb = blank(MC["invalidation_price"]) if "invalidation_price" in MC.columns else None
for c in ("invalidation_price","invalidation_spot","governed_invalidation_spot"):
    if c in MC.columns: print(f"MORNING {c} blank: {int(blank(MC[c]).sum())}/{len(MC)}")
print("\nMORNING blank invalidation_price x eod_candidate_authorized:")
if mcb is not None:
    print(pd.crosstab(MC["eod_candidate_authorized"], mcb).to_string())
    print("\nMORNING blank invalidation x eod_candidate_permission:")
    print(pd.crosstab(MC["eod_candidate_permission"], mcb).to_string())
    print("\nMORNING blank invalidation x capital_permission:")
    print(pd.crosstab(MC["capital_permission"], mcb).to_string())
    print("\nblank-invalidation MORNING rows by direction:", MC.loc[mcb,"final_direction"].value_counts().to_dict())
    print("tickers:", sorted(MC.loc[mcb,"ticker"].astype(str).tolist()))
print("\nLAB blank invalidation x lab_verdict:")
print(pd.crosstab(LAB["lab_verdict"], lb).to_string())
for c in ("lab_execution_status","prep_permission","morning_execution_permission","options_research_permission"):
    if c in LAB.columns:
        print(f"\nLAB blank invalidation x {c}:"); print(pd.crosstab(LAB[c], lb).to_string())

print("\n=== MORNING invalidation_spot (correct col) ===")
mcb = blank(MC["invalidation_spot"])
print("blank:", int(mcb.sum()), "dirs:", MC.loc[mcb,"final_direction"].value_counts().to_dict())
for c in ("eod_candidate_authorized","eod_candidate_permission","eod_candidate_status","capital_permission","capital_authorization_state","live_capital_permission"):
    if c in MC.columns:
        print(f"\ncrosstab {c} x blank_invalidation_spot:")
        print(pd.crosstab(MC[c], mcb).to_string())
print("\ntickers blank:", sorted(MC.loc[mcb,"ticker"].astype(str).tolist()))
print("\nAUTHORIZED & blank:", int((MC["eod_candidate_authorized"].astype(str)=="True") .__and__(mcb).sum()))
