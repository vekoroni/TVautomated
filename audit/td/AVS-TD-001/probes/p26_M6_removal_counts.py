"""M6 step 1 - rows removed per run, per removal point, per direction (no outcomes needed). Read-only.
Pre-book points from diagnostics/dropoff_audit_<run>.csv (dropoff_stage x last_stage_reached);
label gates (row kept, labelled) from intelligence_lab/final_opportunity_book_<run>.csv;
contract-level spread/OI from options/contract_rejection_log_<run>.csv and dropoff audit_flags;
EOD manifest mask from morning_validation/eod_dropoff_audit_<run>.csv (eod_dropoff_reason).
Output: p26_M6_removal_counts.csv (run_id, has_book, point, state, removed_flag, CALL, PUT, OTHER, total)."""
import os, glob
import pandas as pd

ROOT = r"C:\Users\ACKVerissimo\AVSHUNTER-Intelligence"
RUNS = os.path.join(ROOT, "data", "output", "runs")
OUT = os.path.join(ROOT, "audit", "td", "AVS-TD-001", "probes")


def d3(x):
    x = str(x).upper()
    return x if x in ("CALL", "PUT") else "OTHER"


rows = []


def add(run, has_book, point, state, removed, dirs):
    vc = dirs.map(d3).value_counts()
    rows.append(dict(run_id=run, has_book=has_book, point=point, state=state, removed_flag=removed,
                     CALL=int(vc.get("CALL", 0)), PUT=int(vc.get("PUT", 0)), OTHER=int(vc.get("OTHER", 0)), total=int(len(dirs))))


for run in sorted(os.listdir(RUNS)):
    da = os.path.join(RUNS, run, "diagnostics", f"dropoff_audit_{run}.csv")
    if not os.path.exists(da):
        continue
    bk = os.path.join(RUNS, run, "intelligence_lab", f"final_opportunity_book_{run}.csv")
    hb = os.path.exists(bk)
    A = pd.read_csv(da, low_memory=False)
    dcol = A["eod_direction"].where(A["eod_direction"].notna(), A["discovery_direction"])
    for (ls, ds), g in A.groupby([A.last_stage_reached.fillna("NA"), A.dropoff_stage.fillna("NA")]):
        removed = ls != "EOD_CANDIDATE"
        add(run, hb, "DROPOFF_AUDIT_STAGE", f"{ls}|{ds}", removed, dcol.loc[g.index])
    # OI-scope heuristic label and flags (only rows that reached Vanguard)
    for s, g in A.groupby(A.vanguard_expected_options_scope.fillna("NA")):
        add(run, hb, "OI_SCOPE_EXPECTED", s, s.startswith("EXCLUDED"), dcol.loc[g.index])
    fl = A.audit_flags.fillna("")
    reached_oi = A.oi_verdict.notna()
    for tag in ("LOW_OI", "OI_SCORE_ZERO", "LOW_VOLUME"):
        m = reached_oi & fl.str.contains(tag)
        add(run, hb, "AUDIT_FLAG_" + tag, "flagged_among_reached_OI", True, dcol.loc[m[m].index])
    add(run, hb, "OI_VERDICT", "reached_OI_total", False, dcol.loc[reached_oi[reached_oi].index])
    for s, g in A[reached_oi].groupby(A.oi_verdict):
        add(run, hb, "OI_VERDICT", s, s == "STAND_DOWN", dcol.loc[g.index])
    cr = os.path.join(RUNS, run, "options", f"contract_rejection_log_{run}.csv")
    if os.path.exists(cr):
        C = pd.read_csv(cr, low_memory=False)
        sp = set(C.loc[C.rejection_reason.fillna("").str.contains("SPREAD_GT"), "ticker"])
        m = reached_oi & A.ticker.isin(sp)
        add(run, hb, "CONTRACT_LOG_SPREAD_GT_25PCT", "ticker_has_spread_rejection", True, dcol.loc[m[m].index])
    ed = os.path.join(RUNS, run, "morning_validation", f"eod_dropoff_audit_{run}.csv")
    if os.path.exists(ed):
        E = pd.read_csv(ed, low_memory=False, usecols=lambda c: c in ("ticker", "direction", "eod_dropoff_reason"))
        r = E.eod_dropoff_reason.fillna("NA")
        key = r.where(~r.str.contains("SPREAD_REPAIR|OI_REPAIR|OI_CAUTION|VOLUME_CAUTION|DELTA_REPAIR"), "CONTRACT_REPAIR_FLAGS")
        key = key.str.split(":").str[0]
        for s, g in E.groupby(key):
            add(run, hb, "EOD_DROPOFF_REASON", s, s != "PRESERVED_TO_MORNING_VALIDATION", E.loc[g.index, "direction"])
    if hb:
        cols = ["lab_verdict", "opportunity_tier", "opportunity_tier_reason", "eil_signal_verdict", "morning_execution_permission",
                "liquidity_state", "execution_viability_state", "quote_freshness", "usmi_sector_alignment", "macro_sector_alignment",
                "final_action", "campaign_verdict"]
        B = pd.read_csv(bk, low_memory=False, usecols=lambda c: c in cols + ["governed_direction", "direction", "ticker"])
        bd = B["governed_direction"] if "governed_direction" in B else B["direction"]
        for c in cols:
            if c not in B:
                continue
            for s, g in B.groupby(B[c].fillna("NA")):
                add(run, hb, "BOOK_" + c, s, None, bd.loc[g.index])

R = pd.DataFrame(rows)
R.to_csv(os.path.join(OUT, "p26_M6_removal_counts.csv"), index=False)
print(len(R), "rows;", R.run_id.nunique(), "runs")
p = R[(R.run_id == "20260911_115904")]
print(p[p.point.isin(["DROPOFF_AUDIT_STAGE", "OI_VERDICT", "CONTRACT_LOG_SPREAD_GT_25PCT", "AUDIT_FLAG_LOW_OI", "EOD_DROPOFF_REASON", "BOOK_opportunity_tier", "BOOK_usmi_sector_alignment", "BOOK_quote_freshness", "BOOK_morning_execution_permission"])].to_string(index=False))
# pooled pre-book removal per stage across the 22 book runs
q = R[(R.point == "DROPOFF_AUDIT_STAGE") & R.has_book].groupby("state")[["CALL", "PUT", "OTHER", "total"]].sum().sort_values("total", ascending=False)
print(q.to_string())
