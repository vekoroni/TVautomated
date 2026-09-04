"""AVS-RCA-002 A6b - was the empty shadow book correct? READ ONLY."""
import pandas as pd, pathlib, re
RID="20260904_004338"; RUN=pathlib.Path(r"data\output\runs")/RID
ED=pd.read_csv(RUN/"morning_validation"/f"eod_dropoff_audit_{RID}.csv", low_memory=False)
s=pd.to_numeric(ED["shadow_opportunity_score"], errors="coerce").fillna(0)
hi=ED[s>=40]
print("score>=40 rows:", len(hi))
print("their eod_candidate_status:", hi["eod_candidate_status"].fillna("<BLANK>").value_counts().to_dict())
print("their labels:", hi["shadow_opportunity_label"].fillna("<NULL>").value_counts().to_dict())
print("\nfull eod_candidate_status distribution (1454):")
print(ED["eod_candidate_status"].fillna("<BLANK>").value_counts().to_string())
print("\nREVIEW_FALSE_NEGATIVE rows:")
fn=ED[ED["shadow_opportunity_label"]=="REVIEW_FALSE_NEGATIVE"]
print(fn[["ticker","shadow_opportunity_score","eod_candidate_status","shadow_opportunity_reason"]].to_string(index=False))
print("\nregime_watch rows:", len(pd.read_csv(RUN/"morning_validation"/f"regime_watch_{RID}.csv", low_memory=False)))
print("\n### macro advisory columns in LAB ###")
LAB=pd.read_csv(RUN/"intelligence_lab"/f"final_opportunity_book_{RID}.csv", low_memory=False)
def blank(s): return s.isna() | (s.astype(str).str.strip().isin(["","nan","None","NaN","<NA>"]))
for c in LAB.columns:
    if c.startswith("macro_"):
        n=int((~blank(LAB[c])).sum())
        print(f"  {c}: {n}/256")
