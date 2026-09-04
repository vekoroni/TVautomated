"""AVS-RCA-002 A2/A3/A4 probes. READ ONLY."""
import pandas as pd, pathlib
RID="20260904_004338"; RUN=pathlib.Path(r"data\output\runs")/RID
OP=pd.read_csv(RUN/"options"/f"options_intelligence_{RID}.csv", low_memory=False)
LAB=pd.read_csv(RUN/"intelligence_lab"/f"final_opportunity_book_{RID}.csv", low_memory=False)
MC=pd.read_csv(RUN/"morning_validation"/f"morning_candidates_{RID}.csv", low_memory=False)
def blank(s): return s.isna() | (s.astype(str).str.strip().isin(["","nan","None","NaN","<NA>"]))

print("### A2: eod_candidate_status ###")
print(LAB["eod_candidate_status"].fillna("<NULL>").value_counts().to_string())
lb = blank(LAB["invalidation_price"])
print("\nLab rows blank invalidation_price by eod_candidate_status:")
print(LAB.loc[lb,"eod_candidate_status"].fillna("<NULL>").value_counts().to_string())
print("\nEOD_CANDIDATE_ONLY & blank invalidation, by final_direction:")
m = lb & (LAB["eod_candidate_status"].astype(str)=="EOD_CANDIDATE_ONLY")
print(int(m.sum()), LAB.loc[m,"final_direction"].value_counts().to_dict())
print("tickers:", sorted(LAB.loc[m,"ticker"].astype(str).tolist()))

print("\n### A2: stand_down_reason in OPTIONS ###")
print(OP["stand_down_reason"].fillna("<NONE>").value_counts().head(20).to_string())
sd = ~blank(OP["stand_down_reason"])
print("rows with stand_down_reason:", int(sd.sum()))
print("by direction:", OP.loc[sd,"final_direction"].value_counts().to_dict())
for r,g in OP.loc[sd].groupby(OP.loc[sd,"stand_down_reason"].astype(str)):
    print(f"  {r!r}: {len(g)}  dirs={g['final_direction'].value_counts().to_dict()}")

print("\n### A2: structural_target nullity by direction (OPTIONS) ###")
for c in ("structural_target","target_price","structural_target_source","invalidation_spot","structural_stop"):
    if c in OP.columns:
        t=OP.groupby(OP["final_direction"].astype(str))[c].apply(lambda s: int(blank(s).sum()))
        print(f"{c}: blank by dir {t.to_dict()}  total_blank={int(blank(OP[c]).sum())}")

print("\n### A3: quote lineage 4 fields ###")
FIELDS=["contract_bid_size","contract_ask_size","selected_quote_timestamp_utc","execution_viability_state"]
for f in FIELDS:
    for nm,df in (("OPTIONS",OP),("MORNING",MC),("LAB",LAB)):
        if f in df.columns:
            nb=int((~blank(df[f])).sum())
            print(f"  {f:34s} {nm:8s} present={nb}/{len(df)}")
        else:
            print(f"  {f:34s} {nm:8s} COLUMN ABSENT")
print("\n-- OPTIONS bid/ask size candidate columns --")
import re
for c in OP.columns:
    if re.search(r"(bid|ask).*(size)|size.*(bid|ask)", c, re.I):
        print(f"   OPTIONS {c}: present={int((~blank(OP[c])).sum())}/{len(OP)}")
print("\n-- MORNING viability/quote cols --")
for c in MC.columns:
    if re.search(r"viab|quote_timestamp|quote_as_of|bid_size|ask_size", c, re.I):
        print(f"   MORNING {c}: present={int((~blank(MC[c])).sum())}/{len(MC)}")

print("\n### A4: monetisability ###")
print(LAB["monetisability_status"].fillna("<NULL>").value_counts().to_string())
print(LAB["monetisability_state"].fillna("<NULL>").value_counts().to_string() if "monetisability_state" in LAB else "")
T=["BAND","AMAT","WDC","CRDO","KLAC","NVTS","KTOS"]
cols=[c for c in LAB.columns if c.startswith("monetisability_")]
sub=LAB[LAB["ticker"].astype(str).isin(T)][["ticker","final_direction"]+cols]
print(sub.to_string(index=False))
