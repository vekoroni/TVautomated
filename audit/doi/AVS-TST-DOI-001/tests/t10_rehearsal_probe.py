"""AVS-TST-DOI-001 track T10: offline re-run of the DOI-10 read-only rehearsal.

Read-only. Touches only copies made under audit/doi/AVS-TST-DOI-001/scratch/T10.
No provider client is imported: the only project modules used are
domain.dynamic_options_projection, canonical_data.dynamic_options_projection and
contracts.interpreter_handoff, all of which import stdlib only.
"""
from __future__ import annotations

import collections
import hashlib
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

from canonical_data.dynamic_options_projection import DynamicOptionsProjectionResolver
from contracts.interpreter_handoff import validate_handoff_manifest
from domain.dynamic_options_projection import merge_all_opportunities

RUN = "20260909_071646"
SCRATCH = ROOT / "audit" / "doi" / "AVS-TST-DOI-001" / "scratch" / "T10"
BOOK_JSON = ROOT / "data" / "output" / "runs" / RUN / "intelligence_lab" / f"final_opportunity_book_{RUN}.json"
HANDOFF = ROOT / "data" / "output" / "runs" / RUN / "interpreter" / "handoff_manifest.json"
SOURCE_DB = ROOT / "audit" / "doi" / "AVS-TST-DOI-001" / "scratch" / "control_plane.copy.sqlite"

DIR_FIELDS = ("governed_direction", "canonical_direction", "final_direction", "direction")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def direction_of(row) -> str:
    for field in DIR_FIELDS:
        value = str(row.get(field) or "").strip().upper()
        if value in {"CALL", "PUT"}:
            return value
    return "OTHER"


def split(rows) -> dict:
    counter = collections.Counter(direction_of(r) for r in rows)
    return {"CALL": counter.get("CALL", 0), "PUT": counter.get("PUT", 0),
            "OTHER": sum(v for k, v in counter.items() if k not in ("CALL", "PUT"))}


def main() -> int:
    SCRATCH.mkdir(parents=True, exist_ok=True)
    out: dict = {"run_id": RUN}

    # --- Task 2a: hash the DB copy BEFORE ---------------------------------
    db = SCRATCH / "cp_nodoi.sqlite"
    shutil.copy2(SOURCE_DB, db)
    out["db_sha256_before"] = sha256(db)

    # --- Task 1: governed v2 population ------------------------------------
    payload = json.loads(BOOK_JSON.read_text(encoding="utf-8"))
    out["lab_schema_version"] = payload.get("lab_schema_version")
    full_rows = payload["rows"]
    out["v2_population"] = len(full_rows)
    out["v2_population_split"] = split(full_rows)
    out["v2_candidate_count_field"] = payload.get("candidate_count")
    out["v2_doi_reconciliation"] = {
        k: v for k, v in (payload.get("reconciliation") or {}).items() if "doi" in k
    }
    out["v2_doi_state_counts"] = dict(
        collections.Counter(r.get("doi_projection_state") for r in full_rows)
    )

    # --- Task 1: accepted actionable handoff -------------------------------
    handoff = validate_handoff_manifest(HANDOFF, require_accepted=True)
    actionable = [dict(r) for r in handoff.book_rows]
    out["handoff_run_status"] = handoff.manifest.get("run_status")
    out["handoff_reconciliation_status"] = handoff.manifest.get("reconciliation_status")
    out["actionable_count"] = len(actionable)
    out["actionable_split"] = split(actionable)
    out["actionable_tickers"] = [r.get("ticker") for r in actionable]

    # --- Task 1: the merge (what the Lab ALL OPPORTUNITIES view does) ------
    before_ids = [(r.get("run_id"), r.get("ticker"), r.get("thesis_id"), r.get("trade_idea_id"))
                  for r in full_rows]
    merged, reconciliation = merge_all_opportunities(full_rows, actionable)
    after_ids = [(r.get("run_id"), r.get("ticker"), r.get("thesis_id"), r.get("trade_idea_id"))
                 for r in merged]
    out["merge_reconciliation"] = reconciliation
    out["merged_population"] = len(merged)
    out["merged_population_split"] = split(merged)
    out["identities_preserved"] = before_ids == after_ids
    out["identity_set_preserved"] = set(before_ids) == set(after_ids)
    out["overlaid_members"] = sum(1 for r in merged if r.get("lab_actionable_handoff_member") is True)
    out["overlaid_split"] = split([r for r in merged if r.get("lab_actionable_handoff_member") is True])

    # --- Task 10: did the merge change any non-DOI governed field? ---------
    protected = [
        "governed_direction", "canonical_direction", "final_direction", "direction",
        "thesis_id", "thesis_state", "trade_idea_id", "lifecycle_state",
        "final_action", "model_final_action", "action_category", "morning_entry_action",
        "position_size_display", "position_size_pct", "capital_permission",
        "morning_execution_permission", "lab_verdict", "lab_tradeable",
        "liquidity_state", "morning_transition_state", "olm_guard_disposition",
    ]
    base_by_ticker = {str(r.get("ticker") or "").upper(): r for r in
                      json.loads(BOOK_JSON.read_text(encoding="utf-8"))["rows"]}
    changed: dict = {}
    for row in merged:
        tk = str(row.get("ticker") or "").upper()
        base = base_by_ticker.get(tk, {})
        for field in protected:
            b, a = base.get(field), row.get(field)
            if str(b if b is not None else "") != str(a if a is not None else ""):
                changed.setdefault(field, []).append({"ticker": tk, "before": b, "after": a})
    out["merge_protected_field_changes"] = changed

    # full-column diff, non-DOI columns only
    all_cols = set()
    for r in list(base_by_ticker.values()) + merged:
        all_cols.update(r.keys())
    non_doi = sorted(c for c in all_cols
                     if not c.startswith("doi_") and c != "lab_actionable_handoff_member")
    col_changes: dict = {}
    for row in merged:
        tk = str(row.get("ticker") or "").upper()
        base = base_by_ticker.get(tk, {})
        for c in non_doi:
            b, a = base.get(c), row.get(c)
            if str(b if b is not None else "") != str(a if a is not None else ""):
                col_changes.setdefault(c, []).append(tk)
    out["merge_all_nondoi_column_changes"] = {k: v for k, v in sorted(col_changes.items())}
    out["merge_all_nondoi_columns_changed_count"] = len(col_changes)

    # --- Task 4: projection against a DOI-free schema ----------------------
    pop_before = len(merged)
    projected = DynamicOptionsProjectionResolver(db).project_rows(merged)
    out["projected_population"] = len(projected)
    out["projected_population_split"] = split(projected)
    out["projection_population_preserved"] = len(projected) == pop_before
    out["projection_state_counts"] = dict(
        collections.Counter(r.get("doi_projection_state") for r in projected)
    )
    out["projection_reason_counts"] = dict(
        collections.Counter(r.get("doi_projection_reason") for r in projected)
    )
    out["projection_state_counts_by_direction"] = {
        state: split([r for r in projected if r.get("doi_projection_state") == state])
        for state in out["projection_state_counts"]
    }
    # zero-valued evidence check
    numeric = ["doi_p_liquidity_3d", "doi_p_positive_return",
               "doi_p_target_before_invalidation", "doi_model_uncertainty"]
    out["projection_numeric_values"] = {
        f: dict(collections.Counter(repr(r.get(f)) for r in projected)) for f in numeric
    }
    out["projection_zero_valued_evidence_rows"] = sum(
        1 for r in projected if any(r.get(f) == 0 or r.get(f) == 0.0 for f in numeric)
    )
    out["projection_alignment_counts"] = dict(
        collections.Counter(r.get("doi_contract_alignment") for r in projected)
    )
    out["projection_authority_counts"] = dict(
        collections.Counter((r.get("doi_authority"), r.get("doi_decision_authority"),
                             r.get("doi_execution_authority")) for r in projected).items().__iter__()
    ) if False else {str(k): v for k, v in collections.Counter(
        (r.get("doi_authority"), r.get("doi_decision_authority"),
         r.get("doi_execution_authority")) for r in projected).items()}

    # Task 5: governed vs preferred contract shown separately
    out["projection_contract_fields_sample"] = [
        {"ticker": r.get("ticker"),
         "governed": r.get("doi_governed_contract_symbol"),
         "preferred": r.get("doi_preferred_contract_symbol"),
         "alignment": r.get("doi_contract_alignment"),
         "selected_contract_symbol": r.get("selected_contract_symbol")}
        for r in projected[:5]
    ]
    out["projection_governed_symbol_populated"] = sum(
        1 for r in projected if str(r.get("doi_governed_contract_symbol") or "").strip())
    out["projection_preferred_symbol_populated"] = sum(
        1 for r in projected if str(r.get("doi_preferred_contract_symbol") or "").strip())

    # --- Task 10 (projection leg): non-DOI columns unchanged by projection --
    proj_changes: dict = {}
    for base, row in zip(merged, projected):
        for c in non_doi:
            b, a = base.get(c), row.get(c)
            if str(b if b is not None else "") != str(a if a is not None else ""):
                proj_changes.setdefault(c, []).append(row.get("ticker"))
    out["projection_nondoi_column_changes"] = proj_changes

    # --- Task 2b: hash the DB copy AFTER ----------------------------------
    out["db_sha256_after"] = sha256(db)
    out["db_hash_unchanged"] = out["db_sha256_before"] == out["db_sha256_after"]

    result = SCRATCH / "t10_rehearsal_result.json"
    result.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print(json.dumps({k: v for k, v in out.items()
                      if k not in ("merge_all_nondoi_column_changes",
                                   "merge_protected_field_changes",
                                   "projection_numeric_values")},
                     indent=2, default=str))
    print("\n--- merge_protected_field_changes (fields only) ---")
    print(json.dumps({k: len(v) for k, v in out["merge_protected_field_changes"].items()},
                     indent=2))
    print("\n--- merge_all_nondoi_column_changes (fields -> n rows) ---")
    print(json.dumps({k: len(v) for k, v in out["merge_all_nondoi_column_changes"].items()},
                     indent=2))
    print("\n--- projection numeric value distributions ---")
    print(json.dumps(out["projection_numeric_values"], indent=2))
    print(f"\nFULL RESULT: {result}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
