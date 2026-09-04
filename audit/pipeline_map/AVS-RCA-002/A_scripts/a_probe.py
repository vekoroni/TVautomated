"""AVS-RCA-002 Part A probes A1(L2 uplift), A2, A3, A4, A7. READ ONLY."""
import pandas as pd, numpy as np, pathlib, json
pd.set_option("display.width", 200)
RID="20260904_004338"
RUN=pathlib.Path(r"data\output\runs")/RID
VG=pd.read_csv(RUN/"options"/f"vanguard_signals_enriched_{RID}.csv", low_memory=False)
OP=pd.read_csv(RUN/"options"/f"options_intelligence_{RID}.csv", low_memory=False)
LAB=pd.read_csv(RUN/"intelligence_lab"/f"final_opportunity_book_{RID}.csv", low_memory=False)
MC=pd.read_csv(RUN/"morning_validation"/f"morning_candidates_{RID}.csv", low_memory=False)

def blank(s):
    return s.isna() | (s.astype(str).str.strip().isin(["","nan","None","NaN","<NA>"]))

print("### A1e Layer2 +25 uplift reach ###")
aligned = VG.loc[VG["layer1__auction_state"]=="ALIGNED","ticker"].astype(str).unique()
print("ALIGNED tickers:", len(aligned))
labt = set(LAB["ticker"].astype(str))
print("Lab rows:", len(LAB), "unique lab tickers:", len(labt))
print("Lab tickers that were ALIGNED in Vanguard:", len(labt & set(aligned)))
print("Lab rows whose ticker was ALIGNED:", int(LAB["ticker"].astype(str).isin(set(aligned)).sum()))
print("Lab rows whose ticker was TRANSITIONING:",
      int(LAB["ticker"].astype(str).isin(set(VG.loc[VG['layer1__auction_state']=='TRANSITIONING','ticker'].astype(str))).sum()))
print("Lab direction breakdown of ALIGNED-sourced rows:")
sub=LAB[LAB["ticker"].astype(str).isin(set(aligned))]
print(sub["final_direction"].fillna("<NULL>").value_counts().to_string())

print("\n### A7 direction populations ###")
for name, df, col in (("OPTIONS","",""),):
    pass
for col in ("direction","final_direction","governed_direction","canonical_direction"):
    if col in OP.columns:
        print(f"OPTIONS {col}:", OP[col].fillna("<NULL>").value_counts().to_dict())
for col in ("final_direction","governed_direction","canonical_direction","direction"):
    if col in LAB.columns:
        print(f"LAB {col}:", LAB[col].fillna("<NULL>").value_counts().to_dict())
for col in ("final_direction","governed_direction","direction"):
    if col in MC.columns:
        print(f"MORNING {col}:", MC[col].fillna("<NULL>").value_counts().to_dict())

print("\n### A2 invalidation geometry ###")
# Options: directional rows missing stop
for c in ("structural_stop","stop_loss","invalidation_spot","governed_invalidation_spot","selected_invalidation_spot"):
    if c in OP.columns:
        print(f"OPTIONS col {c}: null={int(blank(OP[c]).sum())}/{len(OP)}")
dcol = "direction" if "direction" in OP.columns else "final_direction"
dirmask = OP[dcol].astype(str).isin(["CALL","PUT"])
print("OPTIONS directional rows (CALL/PUT):", int(dirmask.sum()))
for c in ("structural_stop","stop_loss","invalidation_spot","governed_invalidation_spot"):
    if c in OP.columns:
        m = dirmask & blank(OP[c])
        print(f"  directional & blank {c}: {int(m.sum())}  by dir: {OP.loc[m,dcol].value_counts().to_dict()}")

print("\nLAB invalidation_price blank:", int(blank(LAB["invalidation_price"]).sum()), "/", len(LAB))
lb = blank(LAB["invalidation_price"])
print("  by final_direction:", LAB.loc[lb,"final_direction"].fillna("<NULL>").value_counts().to_dict())
