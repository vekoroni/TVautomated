"""AVS-RCA-002 A6 shadow-book intent + A7 positives. READ ONLY."""
import pandas as pd, pathlib, json
RID="20260904_004338"; RUN=pathlib.Path(r"data\output\runs")/RID
def blank(s): return s.isna() | (s.astype(str).str.strip().isin(["","nan","None","NaN","<NA>"]))

print("### A6 shadow-book emptiness intent ###")
ED=pd.read_csv(RUN/"morning_validation"/f"eod_dropoff_audit_{RID}.csv", low_memory=False)
print("eod_dropoff_audit rows:", len(ED))
s=pd.to_numeric(ED.get("shadow_opportunity_score"), errors="coerce").fillna(0)
print("shadow_opportunity_score: max=", s.max(), " >=40:", int((s>=40).sum()), " >0:", int((s>0).sum()))
print("score distribution:", s.value_counts().head(10).to_dict())
if "shadow_opportunity_label" in ED.columns:
    print("labels:", ED["shadow_opportunity_label"].fillna("<NULL>").value_counts().to_dict())
SB=pd.read_csv(RUN/"morning_validation"/f"missed_opportunity_shadow_book_{RID}.csv")
print("shadow book rows:", len(SB), " cols:", len(SB.columns), " has 'ticker':", "ticker" in SB.columns)

print("\n### A7 positives ###")
DS=pd.read_csv(RUN/"discovery"/f"discovery_candidates_ultimate_{RID}.csv", low_memory=False)
print("discovery rows:", len(DS))
DO=pd.read_csv(RUN/"diagnostics"/f"dropoff_audit_{RID}.csv", low_memory=False)
print("dropoff audit rows:", len(DO))
if "stage" in DO.columns: print("stages:", DO["stage"].value_counts().to_dict())
LAB=pd.read_csv(RUN/"intelligence_lab"/f"final_opportunity_book_{RID}.csv", low_memory=False)
MC=pd.read_csv(RUN/"morning_validation"/f"morning_candidates_{RID}.csv", low_memory=False)
print("\nLab rows:", len(LAB), "unique trade_idea_id:", LAB["trade_idea_id"].nunique(), "unique ticker:", LAB["ticker"].nunique())
print("Morning rows:", len(MC), "unique ticker:", MC["ticker"].nunique())
print("Lab tickers == Morning tickers:", set(LAB.ticker.astype(str))==set(MC.ticker.astype(str)))
for c in ("hold_period","hold_window","planned_hold_sessions","horizon_bucket","expected_move_window"):
    if c in LAB.columns: print(f"LAB {c}: {LAB[c].fillna('<NULL>').value_counts().to_dict()}")
print("\nMacro advisory present:", int((~blank(LAB["macro_plain_language_advisory"])).sum()), "/", len(LAB))
for c in ("macro_authority","macro_data_role","macro_regime"):
    if c in LAB.columns: print(f"  {c}: {LAB[c].fillna('<NULL>').value_counts().to_dict()}")
print("\nmorning_execution_permission / prep_permission:")
for c in ("prep_permission","lab_verdict","morning_execution_permission","options_research_permission"):
    if c in LAB.columns: print(f"  LAB {c}: {LAB[c].fillna('<NULL>').value_counts().to_dict()}")
print("\n### A7 direction lineage: governed record id match Options<->Lab ###")
OP=pd.read_csv(RUN/"options"/f"options_intelligence_{RID}.csv", low_memory=False)
key="governed_direction_record_sha256"
if key in OP.columns and key in LAB.columns:
    m=LAB[["ticker","final_direction",key]].merge(OP[["ticker","final_direction",key]], on="ticker", suffixes=("_lab","_op"))
    print("joined:", len(m))
    print("direction match:", int((m["final_direction_lab"]==m["final_direction_op"]).sum()))
    print("record sha match:", int((m[key+"_lab"]==m[key+"_op"]).sum()))
    print("lab sha non-null:", int((~blank(m[key+"_lab"])).sum()), " op sha non-null:", int((~blank(m[key+"_op"])).sum()))
print("\n### where did STRANGLE(141)/UNRESOLVED(49) go? ###")
st=OP[OP["final_direction"].isin(["STRANGLE","UNRESOLVED"])]
print("options STRANGLE/UNRESOLVED:", len(st), st["final_direction"].value_counts().to_dict())
print("of which in Lab:", int(st["ticker"].astype(str).isin(set(LAB.ticker.astype(str))).sum()))
print("their verdicts:", st["options_verdict"].value_counts().to_dict())
print("their invalidation_state:", st["invalidation_state"].value_counts().to_dict())
# governed direction records jsonl
p=RUN/"options"/f"governed_direction_records_{RID}.jsonl"
n=sum(1 for _ in open(p, encoding="utf-8"))
print("\ngoverned_direction_records jsonl rows:", n)
