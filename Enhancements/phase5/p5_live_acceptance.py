"""Phase 1-5 acceptance on a live run (read-only). Usage: p5_live_acceptance.py <run_id>

Checks the design's acceptance criteria on the run's own outputs, independently of the verification agent:
one story per card, trigger = thesis trigger, GO = thesis readiness, one rank owner (blocked last), priced
alternatives present, drop-off audit complete, run label.
"""
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from domain.opportunity_rank import rank_key  # noqa: E402

run = sys.argv[1]
R = ROOT / "data" / "output" / "runs" / run
out = {"run": run}

book = pd.read_csv(R / "intelligence_lab" / f"final_opportunity_book_{run}.csv", low_memory=False)
out["book_rows"] = len(book)
directed = book[book.get("thesis__side", pd.Series(dtype=str)).isin(["BULL", "BEAR"])] if "thesis__side" in book else \
    book[book["thesis_trigger_level"].notna()]
tp, tl = pd.to_numeric(book["trigger_price"], errors="coerce"), pd.to_numeric(book["thesis_trigger_level"], errors="coerce")
has_thesis = tl.notna()
out["one_story"] = {
    "rows_with_thesis_trigger": int(has_thesis.sum()),
    "trigger_price_equals_thesis_trigger": int(((tp - tl).abs() < 1e-9)[has_thesis].sum()),
    "trigger_price_source": book["trigger_price_source"].fillna("<missing>").value_counts().to_dict(),
    "thesis_rows_with_candidate_id": int(book.loc[has_thesis, "thesis_trigger_candidate_id"].notna().sum()),
    "thesis_rows_with_events_status": int(book.loc[has_thesis, "thesis__events_status"].notna().sum()),
    "rows_without_thesis_trigger_but_trigger_price": int((tp.notna() & ~has_thesis).sum()),
}
ready = book["thesis__readiness"].fillna("<missing>").astype(str)
go = book["trigger_go_eligible"].astype(str).str.upper().isin({"TRUE", "1", "YES"})
out["go_is_readiness"] = {
    "readiness_mix": ready.value_counts().to_dict(),
    "go_true": int(go.sum()),
    "go_true_and_ready": int((go & (ready == "READY_FOR_HUMAN_REVIEW")).sum()),
    "ready_but_not_go": int((~go & (ready == "READY_FOR_HUMAN_REVIEW")).sum()),
    "go_but_not_ready": int((go & (ready != "READY_FOR_HUMAN_REVIEW")).sum()),
}
order = sorted(book.to_dict("records"), key=rank_key)
expected = {r["ticker"]: i for i, r in enumerate(order, 1)}
lab_rank = pd.to_numeric(book["lab_rank"], errors="coerce")
out["one_rank_owner"] = {
    "lab_rank_equals_rank_key_order": int((lab_rank == book["ticker"].map(expected)).sum()),
    "rank_basis_present": int(book["rank_basis"].notna().sum()),
    "blocked_rows": int((book["lab_verdict"] == "BLOCKED").sum()),
    "worst_non_blocked_rank": int(lab_rank[book["lab_verdict"] != "BLOCKED"].max()),
    "best_blocked_rank": int(lab_rank[book["lab_verdict"] == "BLOCKED"].min()) if (book["lab_verdict"] == "BLOCKED").any() else None,
}
alt_tested = pd.to_numeric(book.get("thesis_alternatives_tested"), errors="coerce")
out["alternatives"] = {"rows_with_alternatives_tested": int(alt_tested.notna().sum()),
                       "rows_with_alternative_contract": int((pd.to_numeric(book.get("thesis_alternatives_count"), errors="coerce") > 0).sum())}
audit = R / "diagnostics" / f"dropoff_audit_{run}.json"
if audit.exists():
    a = json.loads(audit.read_text(encoding="utf-8"))
    out["dropoff_audit"] = {"stages": a.get("dropoff_stage_counts"), "classes": a.get("dropoff_reason_class_counts")}
meta = json.loads((R / "run_meta.json").read_text(encoding="utf-8-sig"))
out["run_label"] = {k: meta.get(k) for k in ("run_condition", "operator_mode", "baseline_eligible", "run_status")}
print(json.dumps(out, indent=2, default=str))
(ROOT / "Enhancements" / "phase5" / f"p5_live_acceptance_{run}.json").write_text(json.dumps(out, indent=2, default=str))
