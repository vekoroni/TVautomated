"""AVS-RCA-002 A2d - three-direction exposure of the None-target defect. READ ONLY."""
import pandas as pd, pathlib
RID="20260904_004338"; RUN=pathlib.Path(r"data\output\runs")/RID
OP=pd.read_csv(RUN/"options"/f"options_intelligence_{RID}.csv", low_memory=False)
def blank(s): return s.isna() | (s.astype(str).str.strip().isin(["","nan","None","NaN","<NA>"]))
bt = blank(OP["structural_target"])
print("blank structural_target by direction:", OP.loc[bt,"final_direction"].value_counts().to_dict())
te = OP["stand_down_reason"].astype(str).str.contains("unsupported operand type", na=False)
print("TypeError rows:", int(te.sum()), OP.loc[te,"final_direction"].value_counts().to_dict())
print("\n--- CALL rows with blank structural_target: what happened instead ---")
c = bt & (OP["final_direction"]=="CALL")
print(OP.loc[c,["ticker","options_verdict","invalidation_state","stand_down_reason"]].to_string(index=False)[:2500])
print("\n--- PUT rows with blank structural_target and NOT TypeError ---")
p = bt & (OP["final_direction"]=="PUT") & ~te
print(OP.loc[p,["ticker","options_verdict","invalidation_state","stand_down_reason"]].to_string(index=False)[:2000])
print("\n--- invalidation_state distribution overall ---")
print(OP["invalidation_state"].fillna("<NULL>").value_counts().to_string())
print("\ninvalidation_state x direction:")
print(pd.crosstab(OP["invalidation_state"].fillna("<NULL>"), OP["final_direction"]).to_string())
print("\n--- blank invalidation_spot by direction & verdict ---")
bi = blank(OP["invalidation_spot"])
print(pd.crosstab(OP.loc[bi,"final_direction"], OP.loc[bi,"options_verdict"]).to_string())
