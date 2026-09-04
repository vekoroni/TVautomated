"""AVS-RCA-002 A2b/A3/A4 focused probes. READ ONLY."""
import pandas as pd, pathlib, re
RID="20260904_004338"; RUN=pathlib.Path(r"data\output\runs")/RID
OP=pd.read_csv(RUN/"options"/f"options_intelligence_{RID}.csv", low_memory=False)
LAB=pd.read_csv(RUN/"intelligence_lab"/f"final_opportunity_book_{RID}.csv", low_memory=False)
MC=pd.read_csv(RUN/"morning_validation"/f"morning_candidates_{RID}.csv", low_memory=False)
def blank(s): return s.isna() | (s.astype(str).str.strip().isin(["","nan","None","NaN","<NA>"]))

print("### A2b: the 36 TypeError rows ###")
te = OP["stand_down_reason"].astype(str).str.contains("unsupported operand type", na=False)
print("count:", int(te.sum()), "by direction:", OP.loc[te,"final_direction"].value_counts().to_dict())
show=[c for c in ("ticker","final_direction","structural_target","target_price","invalidation_spot","structural_stop",
                  "structural_target_source","options_verdict","verdict","recommendation","gate_status") if c in OP.columns]
print(OP.loc[te, show].head(40).to_string(index=False))

print("\n### A2b: does any status field record UNRESOLVED_EXCEPTION? ###")
for c in OP.columns:
    if re.search(r"verdict|status|state$|recommendation|action", c, re.I):
        vals = OP.loc[te, c].astype(str).value_counts()
        if len(vals) and not (len(vals)==1 and vals.index[0] in ("nan","")):
            print(f"  {c}: {vals.head(4).to_dict()}")

print("\n### A2b: structural_target null by direction across ALL options rows ###")
for c in ("structural_target","target_price","structural_target_source","thesis_target","selected_structural_target"):
    if c in OP.columns:
        print(f"  {c}: blank_by_dir={OP.groupby(OP['final_direction'].astype(str))[c].apply(lambda s:int(blank(s).sum())).to_dict()} total={int(blank(OP[c]).sum())}")

print("\n### A2b: EOD_CANDIDATE_ONLY search across artefacts ###")
for nm,df in (("OPTIONS",OP),("MORNING",MC),("LAB",LAB)):
    hits=[]
    for c in df.columns:
        try:
            if df[c].astype(str).eq("EOD_CANDIDATE_ONLY").any(): hits.append((c,int(df[c].astype(str).eq("EOD_CANDIDATE_ONLY").sum())))
        except Exception: pass
    print(f"  {nm}: {hits}")
for nm,df in (("MORNING",MC),("LAB",LAB)):
    for c in df.columns:
        if re.search(r"eod_candidate", c, re.I):
            print(f"  {nm}.{c}: {df[c].fillna('<NULL>').value_counts().to_dict()}")

print("\n### A3: quote lineage ###")
FIELDS=["contract_bid_size","contract_ask_size","selected_quote_timestamp_utc","execution_viability_state"]
for f in FIELDS:
    for nm,df in (("OPTIONS",OP),("MORNING",MC),("LAB",LAB)):
        if f in df.columns:
            print(f"  {f:32s} {nm:8s} present={int((~blank(df[f])).sum())}/{len(df)}")
        else:
            print(f"  {f:32s} {nm:8s} COLUMN ABSENT")
print("\n-- OPTIONS size/quote-ts/viability candidates --")
for c in OP.columns:
    if re.search(r"(bid|ask)_size|size_(bid|ask)|quote_ts|quote_timestamp|quote_as_of|viab", c, re.I):
        print(f"   OPTIONS {c}: present={int((~blank(OP[c])).sum())}/{len(OP)}")
print("-- MORNING size/quote-ts/viability candidates --")
for c in MC.columns:
    if re.search(r"(bid|ask)_size|quote_timestamp|quote_as_of|viab", c, re.I):
        print(f"   MORNING {c}: present={int((~blank(MC[c])).sum())}/{len(MC)}")

print("\n### A3: restrict OPTIONS to the 256 Lab tickers ###")
labt=set(LAB["ticker"].astype(str))
sub=OP[OP["ticker"].astype(str).isin(labt)]
print("options rows for lab tickers:", len(sub))
for c in sub.columns:
    if re.search(r"(bid|ask)_size|quote_timestamp|quote_as_of|viab", c, re.I):
        print(f"   {c}: present={int((~blank(sub[c])).sum())}/{len(sub)}")

print("\n### A4: monetisability ###")
for c in ("monetisability_status","monetisability_state","monetisability_reason","monetisability_eligible","monetisability_authority"):
    if c in LAB.columns: print(f"  {c}: {LAB[c].fillna('<NULL>').value_counts().to_dict()}")
T=["BAND","AMAT","WDC","CRDO","KLAC","NVTS","KTOS"]
cols=[c for c in LAB.columns if c.startswith("monetisability_")]
print(LAB[LAB["ticker"].astype(str).isin(T)][["ticker","final_direction"]+cols].to_string(index=False))
