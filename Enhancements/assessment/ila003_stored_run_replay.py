"""AVS-SD-ILA-003 acceptance: read-only replay of stored Morning runs.

Mirrors the finalizer's publication input (morning_validated_trades rows ->
write_final_opportunity_book) into a temporary directory, then:
  1. merges the re-published book against the run's real accepted handoff and
     reports overlaid/rejected counts (business acceptance);
  2. with --ab, publishes the same rows a second time with the pre-fix publisher
     emulated in-process (no singular identity fields) and diffs the two books:
     only the two identity fields and their two provenance labels may differ
     (design rule R5 guard on real data).

Never writes under data/. Usage:
  venv\\Scripts\\python.exe Enhancements\\assessment\\ila003_stored_run_replay.py [--ab] RUN_ID [RUN_ID ...]
"""
from __future__ import annotations

import csv
import json
import sys
import tempfile
from collections import Counter
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from contracts import lab_control  # noqa: E402
from contracts.interpreter_handoff import validate_handoff_manifest  # noqa: E402
from contracts.lab_control import write_final_opportunity_book  # noqa: E402
from domain.dynamic_options_projection import merge_all_opportunities  # noqa: E402

RUNS = ROOT / "data" / "output" / "runs"
NEW_FIELDS = {"selected_contract_symbol", "selected_contract_identity_state"}


def _norm(value):
    if value is None:
        return ""
    if isinstance(value, float) and value != value:
        return ""
    return str(value).strip()


def _source_rows(run_id: str) -> list[dict]:
    csv.field_size_limit(1 << 30)
    path = RUNS / run_id / "morning_validation" / f"morning_validated_trades_{run_id}.csv"
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def _publish(run_id: str, rows: list[dict]) -> list[dict]:
    manifest = json.loads((RUNS / run_id / "final_run_manifest.json").read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory(prefix="ila003_replay_") as tmp:
        book = write_final_opportunity_book(run_id, [dict(r) for r in rows], manifest, Path(tmp), sync_interpreter=False)
    return list(book["rows"])


@contextmanager
def _prefix_publisher():
    """Emulate the publisher as it was before AVS-SD-ILA-003, in-process only."""
    original = lab_control._economics_identity
    fields = list(lab_control.FINAL_BOOK_FIELDS)

    def without_identity(*args, **kwargs):
        out = original(*args, **kwargs)
        for key in NEW_FIELDS:
            out.pop(key, None)
        return out

    lab_control._economics_identity = without_identity
    lab_control.FINAL_BOOK_FIELDS[:] = [f for f in fields if f not in NEW_FIELDS]
    try:
        yield
    finally:
        lab_control._economics_identity = original
        lab_control.FINAL_BOOK_FIELDS[:] = fields


def replay(run_id: str, ab: bool = False) -> dict:
    source = _source_rows(run_id)
    rows = _publish(run_id, source)
    states = Counter(r.get("selected_contract_identity_state") for r in rows)
    populated = sum(1 for r in rows if r.get("selected_contract_symbol"))
    handoff = validate_handoff_manifest(RUNS / run_id / "interpreter" / "handoff_manifest.json", require_accepted=True)
    _merged, reconciliation = merge_all_opportunities(rows, [dict(r) for r in handoff.book_rows])
    result = {
        "run_id": run_id,
        "source_rows": len(source), "republished_rows": len(rows),
        "selected_contract_symbol_populated": populated, "identity_states": dict(states),
        "handoff_rows": reconciliation["actionable_handoff_count"],
        "overlaid": reconciliation["actionable_rows_overlaid"],
        "rejected": reconciliation["actionable_rows_rejected"],
        "reject_reasons": dict(Counter(e["reason"] for e in reconciliation["overlay_exceptions"]).most_common(5)),
        "merge_status": reconciliation["status"],
    }
    if ab:
        with _prefix_publisher():
            before = _publish(run_id, source)
        by_ticker = {r["ticker"]: r for r in before}
        changed = Counter()
        provenance_extra = Counter()
        for row in rows:
            old = by_ticker[row["ticker"]]
            for key in set(row) | set(old):
                if key in NEW_FIELDS:
                    continue
                if key == "field_provenance_json":
                    new_p = json.loads(row.get(key) or "{}")
                    old_p = json.loads(old.get(key) or "{}")
                    extra = {k: v for k, v in new_p.items() if old_p.get(k) != v}
                    provenance_extra[json.dumps(sorted(extra))] += 1
                    continue
                if _norm(row.get(key)) != _norm(old.get(key)):
                    changed[key] += 1
        result["ab_prefix_rows"] = len(before)
        result["ab_fields_changed_besides_identity"] = dict(changed)
        result["ab_provenance_extra_labels"] = dict(provenance_extra)
        result["ab_new_fields_only_in_post"] = sorted(set(rows[0]) - set(before[0]))
    return result


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    ab = "--ab" in sys.argv
    for run_id in args or ["20260922_223221"]:
        print(json.dumps(replay(run_id, ab=ab), indent=1), flush=True)
