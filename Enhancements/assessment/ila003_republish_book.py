"""AVS-SD-ILA-003, decision D1 alternative: one-off, logged republish of a stored Morning book.

Reproduces the finalizer's documented offline replay for the book only. The Execution
Gate is re-run in memory from the Morning CSV (its artefacts go to a temp folder, and its
decisions are cross-checked against the stored trades/ output before anything is
published); macro advisory comes from the run's stored packet; validation events are
read, never rewritten; the MSI handoff, run manifest and handoff summary are untouched:

  morning_validation/morning_validated_trades_{run}.csv -> run_execution_gate (in memory)
  -> advisory_fields_for_row(stored interpreter_macro_context.json packet)
  -> _attach_persisted_validation_events(morning_validation/validation_events)
  -> write_final_opportunity_book(run_id, rows, stored final_run_manifest.json, runs_dir)

Modes:
  --preview RUNS_DIR   publish into a mirrored runs directory and diff against the stored book
  --live               back up the three book files, publish into data/output/runs, verify

Usage:
  venv\\Scripts\\python.exe Enhancements\\assessment\\ila003_republish_book.py RUN_ID --preview MIRROR_RUNS_DIR
  venv\\Scripts\\python.exe Enhancements\\assessment\\ila003_republish_book.py RUN_ID --live
"""
from __future__ import annotations

import csv
import hashlib
import json
import shutil
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from canonical_data.session_chain_quote_lookup import StoredSessionChainQuoteLookup  # noqa: E402
from contracts.interpreter_handoff import validate_handoff_manifest  # noqa: E402
from contracts.interpreter_macro_context import advisory_fields_for_row  # noqa: E402
from contracts.lab_control import write_final_opportunity_book  # noqa: E402
from domain.dynamic_options_projection import merge_all_opportunities  # noqa: E402
from morning_handoff_finalizer import (  # noqa: E402
    _attach_persisted_validation_events, _execution_lab_mismatches, _read_csv,
)

LIVE_RUNS = ROOT / "data" / "output" / "runs"
NEW_FIELDS = {"selected_contract_symbol", "selected_contract_identity_state"}
EVENT_FIELDS = {
    "validation_event_id", "validation_transition", "validation_reason",
    "validation_data_status", "validation_evidence_cutoff_utc", "validation_current_price",
    "validation_gap_pct", "validation_underlying_observation_id",
    "validation_option_quote_observation_id", "lab_projection_integrity_state",
}
BOOK_FILES = ("final_opportunity_book_{run}.json", "final_opportunity_book_{run}.csv", "lab_triage_view_{run}.csv")


def _norm(value):
    if value is None:
        return ""
    if isinstance(value, float) and value != value:
        return ""
    return str(value).strip()


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _finalizer_rows(run_id: str) -> tuple[list[dict], dict]:
    """Exactly the finalizer's offline replay input: Morning CSV -> Execution Gate in memory.

    The gate's own artefacts go to a temporary directory so the run's trades/ folder
    (the original gate output) is never rewritten; the gate reconstructs the
    dict-typed contract fields the book writer's reselection path needs.
    """
    import tempfile
    from execution_gate import run_execution_gate
    run = LIVE_RUNS / run_id
    csv.field_size_limit(1 << 30)
    source_rows = _read_csv(run / "morning_validation" / f"morning_validated_trades_{run_id}.csv")
    with tempfile.TemporaryDirectory(prefix="ila003_gate_") as gate_tmp:
        rows, gate_summary = run_execution_gate(signals=source_rows, run_id=run_id, output_dir=Path(gate_tmp))
    rows = [dict(r) for r in rows]
    if len(rows) != len(source_rows):
        raise SystemExit(f"gate reconciliation failed: {len(source_rows)} -> {len(rows)}")
    stored_gate = {r["ticker"]: r for r in _read_csv(run / "trades" / f"execution_gated_{run_id}.csv")}
    drift = Counter()
    for r in rows:
        s = stored_gate.get(r["ticker"]) or {}
        for key in ("final_action", "morning_execution_permission", "governed_direction", "contract_symbol",
                    "morning_selected_contract_symbol", "olm_guard_disposition", "capital_permission"):
            if _norm(r.get(key)) != _norm(s.get(key)):
                drift[key] += 1
    if drift:
        raise SystemExit(f"replayed gate decisions differ from the stored gate output: {dict(drift)}")
    summary = json.loads((run / "morning_validation" / f"morning_handoff_summary_{run_id}.json").read_text(encoding="utf-8"))
    macro = summary["macro_advisory"]
    packet = json.loads(Path(macro["packet_path"]).read_text(encoding="utf-8-sig"))
    guarded = ("governed_direction", "selected_contract_symbol", "thesis_state", "olm_guard_disposition",
               "final_action", "capital_permission", "execution_permission", "position_size_pct")
    for row in rows:
        before = {k: row.get(k) for k in guarded}
        row.update(advisory_fields_for_row(packet, row, packet_sha256=str(macro.get("sha256") or "")))
        if before != {k: row.get(k) for k in guarded}:
            raise SystemExit(f"macro advisory mutated governed fields for {row.get('ticker')}")
    issues = _attach_persisted_validation_events(rows, run / "morning_validation" / "validation_events", run_id=run_id)
    manifest = json.loads((run / "final_run_manifest.json").read_text(encoding="utf-8"))
    return rows, {"gated_rows": len(rows), "gate_decisions_match_stored": True,
                  "validation_projection_issues": issues[:5],
                  "validation_issue_count": len(issues), "macro_packet_id": macro.get("packet_id")}


def _publish(run_id: str, rows: list[dict], runs_dir: Path) -> dict:
    manifest = json.loads((LIVE_RUNS / run_id / "final_run_manifest.json").read_text(encoding="utf-8"))
    lookup = StoredSessionChainQuoteLookup(ROOT / "data" / "canonical" / "control_plane.sqlite", run_id=run_id)
    return write_final_opportunity_book(run_id, rows, manifest, runs_dir, sync_interpreter=False, contract_quote_lookup=lookup)


def _diff_against_stored(run_id: str, new_rows: list[dict]) -> dict:
    stored = json.loads((LIVE_RUNS / run_id / "intelligence_lab" / f"final_opportunity_book_{run_id}.json").read_text(encoding="utf-8"))
    by = {r["ticker"]: r for r in stored["rows"]}
    changed = Counter()
    for row in new_rows:
        old = by.get(row["ticker"])
        if old is None:
            changed["<missing in stored>"] += 1
            continue
        for key in set(row) | set(old):
            if key in NEW_FIELDS or key in EVENT_FIELDS or key == "field_provenance_json":
                continue
            if _norm(row.get(key)) != _norm(old.get(key)):
                changed[key] += 1
    return {"stored_rows": len(stored["rows"]), "new_rows": len(new_rows),
            "fields_changed_besides_identity_event_provenance": dict(changed.most_common(15))}


def _merge_check(run_id: str, rows: list[dict]) -> dict:
    handoff = validate_handoff_manifest(LIVE_RUNS / run_id / "interpreter" / "handoff_manifest.json", require_accepted=True)
    _m, rec = merge_all_opportunities(rows, [dict(r) for r in handoff.book_rows])
    return {"handoff_rows": rec["actionable_handoff_count"], "overlaid": rec["actionable_rows_overlaid"],
            "rejected": rec["actionable_rows_rejected"], "merge_status": rec["status"]}


def main() -> None:
    run_id = sys.argv[1]
    mode = sys.argv[2]
    rows, prep = _finalizer_rows(run_id)
    print(json.dumps({"prepared": prep}, indent=1), flush=True)
    if mode == "--preview":
        runs_dir = Path(sys.argv[3])
        book = _publish(run_id, rows, runs_dir)
        new_rows = list(book["rows"])
        out = {"mode": "preview", "runs_dir": str(runs_dir),
               "identity_states": dict(Counter(r.get("selected_contract_identity_state") for r in new_rows)),
               **_diff_against_stored(run_id, new_rows), **_merge_check(run_id, new_rows),
               "authority_mismatches": _execution_lab_mismatches(rows, new_rows)[:5]}
        print(json.dumps(out, indent=1), flush=True)
        return
    if mode != "--live":
        raise SystemExit("mode must be --preview RUNS_DIR or --live")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup = ROOT / "backups" / f"ila003_republish_{run_id}_prechange_{stamp}"
    backup.mkdir(parents=True, exist_ok=False)
    lab_dir = LIVE_RUNS / run_id / "intelligence_lab"
    before = {}
    for name in BOOK_FILES:
        path = lab_dir / name.format(run=run_id)
        shutil.copy2(path, backup / path.name)
        before[path.name] = {"sha256": _sha(path), "size": path.stat().st_size}
    book = _publish(run_id, rows, LIVE_RUNS)
    new_rows = list(book["rows"])
    after = {}
    for name in BOOK_FILES:
        path = lab_dir / name.format(run=run_id)
        after[path.name] = {"sha256": _sha(path), "size": path.stat().st_size}
    republished = json.loads((lab_dir / f"final_opportunity_book_{run_id}.json").read_text(encoding="utf-8"))
    record = {
        "mode": "live", "run_id": run_id, "republished_at_utc": datetime.now(timezone.utc).isoformat(),
        "reason": "AVS-SD-ILA-003 D1 alternative: publish selected_contract_symbol on a pre-fix Morning book",
        "backup_dir": str(backup), "files_before": before, "files_after": after,
        "rows": len(republished["rows"]),
        "identity_states": dict(Counter(r.get("selected_contract_identity_state") for r in republished["rows"])),
        "authority_mismatches": _execution_lab_mismatches(rows, new_rows)[:5],
        **_merge_check(run_id, republished["rows"]),
    }
    (backup / "republish_record.json").write_text(json.dumps(record, indent=1), encoding="utf-8")
    print(json.dumps(record, indent=1), flush=True)


if __name__ == "__main__":
    main()
