"""AVS-RCA-002 A2e - ARMED-without-invalidation propagation. READ ONLY."""
import pandas as pd, pathlib
RID="20260904_004338"; RUN=pathlib.Path(r"data\output\runs")/RID
OP=pd.read_csv(RUN/"options"/f"options_intelligence_{RID}.csv", low_memory=False)
LAB=pd.read_csv(RUN/"intelligence_lab"/f"final_opportunity_book_{RID}.csv", low_memory=False)
def blank(s): return s.isna() | (s.astype(str).str.strip().isin(["","nan","None","NaN","<NA>"]))
armed_nostop = OP[(OP["options_verdict"]=="ARMED") & (OP["invalidation_state"]=="MISSING")]
print("OPTIONS ARMED & invalidation MISSING:", len(armed_nostop), armed_nostop["final_direction"].value_counts().to_dict())
t=set(armed_nostop["ticker"].astype(str))
inlab = LAB[LAB["ticker"].astype(str).isin(t)]
print("of which reached Lab:", len(inlab), inlab["final_direction"].value_counts().to_dict())
print("Lab blank invalidation_price among them:", int(blank(inlab["invalidation_price"]).sum()))
print("\nOPTIONS ARMED total:", int((OP['options_verdict']=='ARMED').sum()),
      OP.loc[OP['options_verdict']=='ARMED','final_direction'].value_counts().to_dict())
print("ARMED with invalidation AVAILABLE:", int(((OP['options_verdict']=='ARMED')&(OP['invalidation_state']=='AVAILABLE')).sum()))
print("\nLab rows sourced from ARMED-no-stop tickers, options_research_permission:")
print(inlab["options_research_permission"].value_counts().to_dict())
