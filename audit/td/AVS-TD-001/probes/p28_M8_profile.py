"""M8: value profile of candidate conditioning columns per run (labelled rows only). Read-only."""
import os, glob
import pandas as pd
ROOT = r"C:\Users\ACKVerissimo\AVSHUNTER-Intelligence"
OUT = os.path.join(ROOT, "audit", "td", "AVS-TD-001", "probes")
L = pd.read_csv(os.path.join(OUT, "p32_labels.csv"), usecols=["run_id", "ticker"])
C = pd.read_csv(os.path.join(OUT, "p28_M8_columns.csv"))
want = ["gics_sector","gics_sector_norm","sector","sector_etf","sector_tilt","catalyst_overlay","catalyst_type","catalyst_date","catalyst_event_status","catalyst_truth_score",
        "iv_rank","contract_delta","delta_band","dte","contract_dte","macro_regime","regime","macro_sector_alignment","usmi_sector_alignment","regime_drift_status",
        "morning_execution_permission","thesis_state","trigger_primary"]
for rid in sorted(L.run_id.unique()):
    f = os.path.join(ROOT, "data", "output", "runs", rid, "intelligence_lab", f"final_opportunity_book_{rid}.csv")
    have = set(C[C.run_id == rid].column)
    cols = ["ticker"] + [c for c in want if c in have]
    B = pd.read_csv(f, usecols=cols, low_memory=False)
    n = len(L[L.run_id == rid])
    print(f"\n=== {rid} labelled_rows={n} book_rows={len(B)} cols={cols[1:]}")
    for c in cols[1:]:
        s = B[c]
        fill = s.notna().mean()
        vc = s.astype(str).value_counts().head(6).to_dict()
        print(f"  {c}: fill={fill:.2f} nuniq={s.nunique()} top={vc}")
