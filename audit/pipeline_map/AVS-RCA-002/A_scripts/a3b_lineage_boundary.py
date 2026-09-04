"""AVS-RCA-002 A3b - macro + quote lineage upstream presence. READ ONLY."""
import pandas as pd, pathlib
RID="20260904_004338"; RUN=pathlib.Path(r"data\output\runs")/RID
def blank(s): return s.isna() | (s.astype(str).str.strip().isin(["","nan","None","NaN","<NA>"]))
OP=pd.read_csv(RUN/"options"/f"options_intelligence_{RID}.csv", low_memory=False)
MC=pd.read_csv(RUN/"morning_validation"/f"morning_candidates_{RID}.csv", low_memory=False)
LAB=pd.read_csv(RUN/"intelligence_lab"/f"final_opportunity_book_{RID}.csv", low_memory=False)
labt=set(LAB.ticker.astype(str)); OPS=OP[OP.ticker.astype(str).isin(labt)]
MACRO=[c for c in LAB.columns if c.startswith("macro_")]
print(f"{'field':38s} {'OPTIONS(256)':>13s} {'MORNING(256)':>13s} {'LAB(256)':>9s}")
for c in MACRO:
    o = int((~blank(OPS[c])).sum()) if c in OPS.columns else -1
    m = int((~blank(MC[c])).sum()) if c in MC.columns else -1
    l = int((~blank(LAB[c])).sum())
    f=lambda v: "ABSENT" if v<0 else str(v)
    print(f"{c:38s} {f(o):>13s} {f(m):>13s} {f(l):>9s}")
print("\n### quote-lineage field map ###")
QL=["contract_bid_size","contract_ask_size","selected_quote_timestamp_utc","execution_viability_state",
    "l2_bid_size","l2_ask_size","l2_quote_timestamp_utc","contract_quote_timestamp_utc","quote_timestamp_utc",
    "quote_as_of","selected_quote_dataset_id","selected_quote_snapshot_id","contract_quote_quality",
    "underlying_nbbo_bid_size","underlying_nbbo_ask_size","execution_viability_reason","execution_viability_eligible",
    "execution_viability_bid","execution_viability_ask","execution_viability_spread_pct","execution_viability_policy_version",
    "contract_bid","contract_ask"]
print(f"{'field':38s} {'OPTIONS(256)':>13s} {'MORNING(256)':>13s} {'LAB(256)':>9s}")
for c in QL:
    o = int((~blank(OPS[c])).sum()) if c in OPS.columns else -1
    m = int((~blank(MC[c])).sum()) if c in MC.columns else -1
    l = int((~blank(LAB[c])).sum()) if c in LAB.columns else -1
    f=lambda v: "ABSENT" if v<0 else str(v)
    print(f"{c:38s} {f(o):>13s} {f(m):>13s} {f(l):>9s}")
