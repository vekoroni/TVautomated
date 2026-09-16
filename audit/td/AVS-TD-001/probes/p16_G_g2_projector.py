"""p16_G_g2_projector.py -- Track G / G2 (REQ-WP6-02 presentation projector).  READ-ONLY.

Part A (stored run): enumerate the state/verdict columns present on final_opportunity_book_<run>.csv,
cross-tab (thesis_state x execution_viability_state x monetisability_state) by direction, find every
summary/verdict column with GO/EXECUTE/BUY-like values, cross-tab those against the execution state and
quote-staleness columns, and count BLOCK-beside-GO rows.
Part B (offline): run derive_opportunity_presentation_v1 over SD 9.1 x 9.3 x 9.5 (10 x 8 x 6 = 480) and
record which branch each combination takes, whether any executable summary appears without
EXECUTION_EXECUTABLE_NOW, and whether the summary_reason contradicts the thesis input.
Outputs p16_G_g2_projector.json beside this file.
"""
from __future__ import annotations
import json, sys, itertools
from collections import Counter
from pathlib import Path
import pandas as pd

ROOT = Path(r"C:\Users\ACKVerissimo\AVSHUNTER-Intelligence")
RUN = "20260911_115904"
R = ROOT / "data/output/runs" / RUN
OUT = Path(__file__).with_suffix(".json")
sys.path.insert(0, str(ROOT))
from domain.presentation import derive_opportunity_presentation_v1  # noqa: E402
from domain.lab_signal_book_v4 import project_lab_signal_v4  # noqa: E402

fb = pd.read_csv(R / f"intelligence_lab/final_opportunity_book_{RUN}.csv", dtype=str, keep_default_na=False)
v3 = pd.read_csv(R / "intelligence_lab/lab_signal_book_v3.csv", dtype=str, keep_default_na=False)
res = {"run": RUN, "final_book_rows": len(fb), "v3_rows": len(v3)}

def direction_of(df):
    d = df["final_direction"].where(df["final_direction"] != "", df.get("governed_direction", ""))
    d = d.where(d != "", df.get("canonical_direction", ""))
    return d.str.upper().map(lambda x: x if x in ("CALL", "PUT") else "OTHER")

fb["_dir"] = direction_of(fb); v3["_dir"] = direction_of(v3)
res["direction_counts_final_book"] = fb["_dir"].value_counts().to_dict()
res["direction_counts_v3"] = v3["_dir"].value_counts().to_dict()

# ---- which state / verdict columns exist ----------------------------------------------------
CANDIDATES = ["thesis_state", "execution_state", "execution_permission", "execution_viability_state", "olm_state",
              "monetisability_state", "monetisability_status", "lab_verdict", "final_action", "opportunity_tier", "verdict",
              "campaign_verdict", "morning_verdict", "morning_execution_permission", "morning_entry_action",
              "execution_eligibility_state", "final_capital_permission", "lab_execution_status", "lab_status",
              "eod_candidate_status", "action_category", "prep_permission", "eil_v3_verdict", "eil_signal_verdict",
              "tier", "quote_freshness", "is_stale", "morning_transition_state", "contract_data_state",
              "doi_monetisability_state", "doi_projection_state", "lab_v4_summary_state", "lab_v4_execution_state",
              "execution_quote_status", "execution_authorized", "execution_can_grant_capital", "lab_tradeable",
              "execution_category", "display_execution_mode", "model_final_action", "lab_status_banner"]
res["columns_present"] = {c: (c in fb.columns, c in v3.columns) for c in CANDIDATES}
res["value_counts"] = {c: fb[c].value_counts().head(12).to_dict() for c in CANDIDATES if c in fb.columns}
res["v3_value_counts"] = {c: v3[c].value_counts().head(12).to_dict() for c in CANDIDATES if c in v3.columns}
res["lab_v4_columns_on_run"] = [c for c in fb.columns if c.startswith("lab_v4_")]

# ---- three-state cross-tab by direction ------------------------------------------------------
exec_col = "execution_state" if "execution_state" in fb.columns else "execution_viability_state"
res["execution_state_column_used"] = exec_col
trip = fb.groupby(["thesis_state", exec_col, "monetisability_state", "_dir"]).size()
combos = {}
for (t, e, m, d), n in trip.items():
    combos.setdefault(f"{t or '<blank>'} x {e or '<blank>'} x {m or '<blank>'}", {})[d] = int(n)
res["thesis_x_execution_x_monetisability"] = combos
res["distinct_combinations"] = len(combos)

# ---- GO/EXECUTE/BUY-like summary values vs execution state and staleness -----------------------
GO_RE = r"^(GO|GO_LIMIT|EXECUTE|EXECUTE_NOW|BUY|BUY_SMALL|BUY_NOW|ENTER|ENTER_NOW|EXECUTABLE|EXECUTABLE_NOW|APPROVED|PROBE|READY_PROBE|EXECUTION_REVIEW)$"
summary_cols = [c for c in CANDIDATES if c in fb.columns and fb[c].str.upper().str.match(GO_RE).any()]
res["summary_columns_with_go_like_values"] = summary_cols
stale_cols = [c for c in ("quote_freshness", "is_stale", "execution_quote_status", "morning_quote_timestamp_utc") if c in fb.columns]
xt = {}
for c in summary_cols:
    go_mask = fb[c].str.upper().str.match(GO_RE)
    sub = fb[go_mask]
    xt[c] = {
        "go_like_values": sub[c].value_counts().to_dict(),
        "by_direction": sub["_dir"].value_counts().to_dict(),
        "vs_" + exec_col: sub[exec_col].value_counts().to_dict(),
        "go_like_while_execution_state_ne_EXECUTABLE_NOW": int((sub[exec_col] != "EXECUTION_EXECUTABLE_NOW").sum()),
        "go_like_while_execution_state_ne_EXECUTABLE_NOW_by_dir": sub[sub[exec_col] != "EXECUTION_EXECUTABLE_NOW"]["_dir"].value_counts().to_dict(),
    }
    for s in stale_cols:
        xt[c]["vs_" + s] = sub[s].value_counts().head(8).to_dict()
    if "quote_freshness" in fb.columns:
        stale = sub[sub["quote_freshness"].str.upper().str.contains("STALE|PRIOR|OLD|UNAVAILABLE", regex=True)]
        xt[c]["go_like_while_quote_stale"] = int(len(stale))
        xt[c]["go_like_while_quote_stale_by_dir"] = stale["_dir"].value_counts().to_dict()
res["go_like_crosstabs"] = xt

# ---- BLOCK beside GO ---------------------------------------------------------------------------
BLOCK_RE = r"BLOCK"
GO_STRICT = r"^(GO|GO_LIMIT|PROBE|BUY|BUY_SMALL|EXECUTE|EXECUTE_NOW)$"
block_cols = [c for c in fb.columns if fb[c].str.upper().str.contains(BLOCK_RE, regex=True).any() and fb[c].nunique() < 60]
go_cols = [c for c in fb.columns if fb[c].str.upper().str.match(GO_STRICT).any() and fb[c].nunique() < 60]
res["block_bearing_columns"] = block_cols
res["go_bearing_columns"] = go_cols
pairs = {}
for b in block_cols:
    for g in go_cols:
        if b == g:
            continue
        m = fb[b].str.upper().str.contains(BLOCK_RE, regex=True) & fb[g].str.upper().str.match(GO_STRICT)
        n = int(m.sum())
        if n:
            pairs[f"{b} BLOCK* beside {g} GO*"] = {"n": n, "by_dir": fb[m]["_dir"].value_counts().to_dict(),
                                                  "example": fb[m][[ "ticker", b, g]].head(3).values.tolist()}
res["block_beside_go_pairs"] = pairs
res["block_beside_go_rows_any_pair"] = int(pd.concat([
    (fb[b].str.upper().str.contains(BLOCK_RE, regex=True) & fb[g].str.upper().str.match(GO_STRICT))
    for b in block_cols for g in go_cols if b != g], axis=1).any(axis=1).sum()) if block_cols and go_cols else 0
res["block_beside_go_rows_any_pair_by_dir"] = fb[pd.concat([
    (fb[b].str.upper().str.contains(BLOCK_RE, regex=True) & fb[g].str.upper().str.match(GO_STRICT))
    for b in block_cols for g in go_cols if b != g], axis=1).any(axis=1)]["_dir"].value_counts().to_dict() if block_cols and go_cols else {}
# canonical pair the REQ names: opportunity_tier BLOCK beside lab_verdict GO*
if "opportunity_tier" in fb.columns and "lab_verdict" in fb.columns:
    m = fb["opportunity_tier"].str.upper().str.contains("BLOCK") & fb["lab_verdict"].str.upper().str.match(GO_STRICT)
    res["opportunity_tier_BLOCK_beside_lab_verdict_GO"] = {"n": int(m.sum()), "by_dir": fb[m]["_dir"].value_counts().to_dict(),
                                                            "lab_verdict_values": fb[m]["lab_verdict"].value_counts().to_dict()}
    m3 = v3["opportunity_tier"].str.upper().str.contains("BLOCK") & v3["lab_verdict"].str.upper().str.match(GO_STRICT)
    res["v3_opportunity_tier_BLOCK_beside_lab_verdict_GO"] = {"n": int(m3.sum()), "of": len(v3), "by_dir": v3[m3]["_dir"].value_counts().to_dict()}

# ---- Part B: offline exhaustive projector run --------------------------------------------------
THESIS = ["THESIS_DEVELOPING", "THESIS_ACTIVE", "THESIS_VALIDATED", "THESIS_UNDER_PRESSURE", "THESIS_CONDITION_BREACHED",
          "THESIS_TARGET_TOUCHED", "THESIS_CONTINUATION_REVIEW_REQUIRED", "THESIS_RECOVERING", "THESIS_HORIZON_ELAPSED_REASSESS",
          "THESIS_DATA_INSUFFICIENT"]
EXECUTION = ["EXECUTION_QUOTE_UNAVAILABLE", "EXECUTION_QUOTE_STALE_MONITOR", "EXECUTION_ZERO_BID_MONITOR", "EXECUTION_WIDE_SPREAD_MONITOR",
             "EXECUTION_CROSSED_MARKET_DATA_DEFECT", "EXECUTION_UNVALIDATED_INPUT", "EXECUTION_REVIEWABLE", "EXECUTION_EXECUTABLE_NOW"]
MONET = ["SCENARIO_MONETISABLE", "SCENARIO_LIMITED", "NOT_CURRENTLY_MONETISABLE", "INDETERMINATE", "NOT_EVALUATED_DATA_MISSING", "NOT_APPLICABLE"]
EXEC_LIKE = {"EXECUTION_REVIEW", "EXECUTABLE", "EXECUTE", "GO"}
branch = Counter(); violations = []; reason_contradicts_thesis = []; combos_out = []
for t, e, m in itertools.product(THESIS, EXECUTION, MONET):
    p = derive_opportunity_presentation_v1(thesis_state=t, contract_state=m, execution_state=e, macro_context="UNAVAILABLE")
    if p.summary_state == "THESIS_INVALID": b = "branch1_thesis_invalid"
    elif p.summary_state == "EXECUTION_REVIEW": b = "branch2_executable_now"
    else: b = "branch3_default_MONITOR"
    branch[b] += 1
    if p.summary_state in EXEC_LIKE and e != "EXECUTION_EXECUTABLE_NOW":
        violations.append((t, e, m, p.summary_state))
    if "THESIS_ACTIVE" in p.summary_reason and t != "THESIS_ACTIVE":
        reason_contradicts_thesis.append((t, e, m, p.summary_state, p.summary_reason))
    combos_out.append({"thesis": t, "execution": e, "monetisability": m, "summary_state": p.summary_state, "summary_reason": p.summary_reason, "branch": b})
res["offline_480"] = {
    "total": len(combos_out), "branch_counts": dict(branch),
    "executable_summary_without_EXECUTABLE_NOW": len(violations), "violations_sample": violations[:5],
    "summary_reason_says_THESIS_ACTIVE_when_thesis_is_not_ACTIVE": len(reason_contradicts_thesis),
    "contradiction_sample": reason_contradicts_thesis[:6],
    "thesis_values_recognised_by_branch1": ["INVALID", "THESIS_INVALIDATED"],
    "branch1_values_in_SD_9_1_vocabulary": [v for v in ("INVALID", "THESIS_INVALIDATED") if v in THESIS],
    "distinct_summary_states": sorted({c["summary_state"] for c in combos_out}),
    "monetisability_influences_summary_state": len({(c["thesis"], c["execution"], c["summary_state"]) for c in combos_out}) != len({(c["thesis"], c["execution"], c["monetisability"], c["summary_state"]) for c in combos_out}) and False,
}
# does monetisability change summary_state at all?
by_tm = {}
for c in combos_out:
    by_tm.setdefault((c["thesis"], c["execution"]), set()).add(c["summary_state"])
res["offline_480"]["monetisability_changes_summary_state_for_any_thesis_execution_pair"] = any(len(v) > 1 for v in by_tm.values())
# examples: breached thesis + executable now
ex = [c for c in combos_out if c["thesis"] in ("THESIS_CONDITION_BREACHED", "THESIS_DATA_INSUFFICIENT") and c["execution"] == "EXECUTION_EXECUTABLE_NOW" and c["monetisability"] == "NOT_CURRENTLY_MONETISABLE"]
res["offline_480"]["examples_breached_or_insufficient_with_executable_now"] = ex
# v4 projector fallbacks (NFR-07 "invents no fallbacks")
empty = project_lab_signal_v4({})
res["v4_projector_defaults_on_empty_row"] = empty
# apply the v4 projector to the stored final book rows (offline projection of stored run) and summarise
proj = [project_lab_signal_v4(r) for r in fb.to_dict("records")]
pj = pd.DataFrame(proj); pj["_dir"] = fb["_dir"].values
res["offline_v4_projection_of_stored_book"] = {
    "summary_state_by_dir": pj.groupby(["lab_v4_summary_state", "_dir"]).size().to_dict().__class__.__name__ and {f"{k[0]}|{k[1]}": int(v) for k, v in pj.groupby(["lab_v4_summary_state", "_dir"]).size().items()},
    "execution_state_source_values": pj["lab_v4_execution_state"].value_counts().head(10).to_dict(),
    "thesis_state_values": pj["lab_v4_thesis_state"].value_counts().head(10).to_dict(),
    "contract_state_values": pj["lab_v4_contract_state"].value_counts().head(10).to_dict(),
    "rows_where_execution_state_defaulted_to_EXECUTION_REVIEWABLE_because_missing": int(((fb.get("execution_state", pd.Series([""]*len(fb))) == "") & (fb["execution_viability_state"] == "")).sum()),
}
OUT.write_text(json.dumps(res, indent=2, default=str), encoding="utf-8")
print(json.dumps({k: res[k] for k in ("direction_counts_final_book", "direction_counts_v3", "execution_state_column_used", "distinct_combinations", "lab_v4_columns_on_run", "summary_columns_with_go_like_values", "block_beside_go_rows_any_pair", "block_beside_go_rows_any_pair_by_dir", "opportunity_tier_BLOCK_beside_lab_verdict_GO", "v3_opportunity_tier_BLOCK_beside_lab_verdict_GO", "offline_480", "v4_projector_defaults_on_empty_row", "offline_v4_projection_of_stored_book")}, indent=1, default=str))
print("columns_present:", {k: v for k, v in res["columns_present"].items()})
print("value_counts:", json.dumps(res["value_counts"], indent=0, default=str)[:4000])
print("combos:", json.dumps(res["thesis_x_execution_x_monetisability"], indent=0)[:3000])
print("go-like crosstabs:", json.dumps(xt, indent=0, default=str)[:5000])
print("block/go pairs:", json.dumps(pairs, indent=0, default=str)[:3000])
