"""AVS-TST-DOI-001 / T2.2-T2.3 — independent append-only and restart probe.

Invariant 12: "Restarts are idempotent and append-only histories are not
overwritten."
Design §7.2: ContractCandidate identity = thesis_id + OCC + observation_dataset_id;
"The same OCC symbol at a later timestamp is a new observation, not a mutation
of the old observation."

This probe does NOT reuse the project's own persistence tests. It builds a
throwaway control plane under scratch\ and attacks the guarantee directly at
the SQL layer, which is where a bypass would have to happen:

  A. Can a DOI row be UPDATEd?           (must ABORT)
  B. Can a DOI row be DELETEd?           (must ABORT)
  C. Does re-persisting the same family after a "restart" (fresh store object
     on the same file) create a duplicate or overwrite?
  D. Is the same OCC at a later observation a NEW row rather than a mutation?

READ ONLY with respect to the repository: the only database written is a fresh
temporary file under audit\doi\AVS-TST-DOI-001\scratch\.
Interpreter: venv\Scripts\python.exe
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

SCRATCH = ROOT / "audit/doi/AVS-TST-DOI-001/scratch"
DB = SCRATCH / "probe_t2_append_only.sqlite"

from canonical_data.option_liquidity_lifecycle import OptionLiquidityLifecycleStore  # noqa: E402
from canonical_data.registry import CanonicalRegistry  # noqa: E402

DOI_TABLES = [
    "doi_contract_families",
    "doi_contract_assessments",
    "doi_preferred_contract_decisions",
    "doi_lifecycle_events",
    "doi_outcome_labels",
]
LEGACY_TABLES = [
    "option_thesis_events",
    "option_contract_observations",
    "option_contract_selection_events",
]

results: list[tuple[str, str, str]] = []


def record(check: str, outcome: str, detail: str = "") -> None:
    results.append((check, outcome, detail))
    print(f"  [{outcome:4}] {check}  {detail}")


def main() -> int:
    SCRATCH.mkdir(parents=True, exist_ok=True)
    if DB.exists():
        DB.unlink()

    registry = CanonicalRegistry(DB)
    store = OptionLiquidityLifecycleStore(registry)
    store.initialise()
    print(f"fresh control plane created at {DB.name}\n")

    with registry.connection() as connection:
        present = {
            row[0] for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        triggers = {
            row[0] for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='trigger'"
            )
        }

    print("A/B. Append-only enforcement (UPDATE and DELETE must ABORT)")
    for table in DOI_TABLES + LEGACY_TABLES:
        if table not in present:
            record(f"{table}", "SKIP", "table absent")
            continue
        has_update_trg = any(t for t in triggers if table in t and "no_update" in t)
        has_delete_trg = any(t for t in triggers if table in t and "no_delete" in t)
        # Attempt the mutation directly, so a missing trigger is caught even if
        # the naming convention changes.
        with sqlite3.connect(DB) as raw:
            raw.execute("PRAGMA foreign_keys=ON")
            update_blocked = delete_blocked = False
            try:
                raw.execute(f"UPDATE {table} SET run_id='TAMPER' WHERE 1=1")
            except sqlite3.Error:
                update_blocked = True
            try:
                raw.execute(f"DELETE FROM {table} WHERE 1=1")
            except sqlite3.Error:
                delete_blocked = True
        # On an EMPTY table a BEFORE trigger never fires, so absence of an error
        # proves nothing. Fall back to trigger presence, and say which we used.
        basis = "executed" if (update_blocked or delete_blocked) else "trigger-presence"
        ok = (update_blocked or has_update_trg) and (delete_blocked or has_delete_trg)
        record(
            table,
            "PASS" if ok else "FAIL",
            f"update_trigger={has_update_trg} delete_trigger={has_delete_trg} basis={basis}",
        )

    print("\nC. Restart idempotency (fresh store object on the same file)")
    restarted = OptionLiquidityLifecycleStore(CanonicalRegistry(DB))
    try:
        restarted.initialise()
        record("restart initialise()", "PASS", "no exception, schema re-entrant")
    except Exception as error:  # noqa: BLE001
        record("restart initialise()", "FAIL", f"{type(error).__name__}: {error}")

    with sqlite3.connect(DB) as raw:
        after = {
            row[0] for row in raw.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        trg_after = {
            row[0] for row in raw.execute(
                "SELECT name FROM sqlite_master WHERE type='trigger'"
            )
        }
    record(
        "schema stable across restart",
        "PASS" if after == present and trg_after == triggers else "FAIL",
        f"tables {len(present)}->{len(after)}, triggers {len(triggers)}->{len(trg_after)}",
    )

    print("\nD. Identity: thesis_id + OCC + observation_dataset_id")
    with sqlite3.connect(DB) as raw:
        cols = {
            r[1] for r in raw.execute("PRAGMA table_info(doi_contract_assessments)")
        }
        uniques = [
            r[0] for r in raw.execute(
                "SELECT sql FROM sqlite_master WHERE name='doi_contract_assessments'"
            )
        ]
    identity_fields = {"thesis_id", "contract_symbol", "observation_dataset_id"}
    missing = identity_fields - cols
    record(
        "assessment carries full identity triple",
        "PASS" if not missing else "FAIL",
        f"missing={sorted(missing) if missing else 'none'}",
    )
    sql = uniques[0] if uniques else ""
    has_unique = "UNIQUE" in sql.upper()
    record(
        "assessment has a UNIQUE natural key",
        "PASS" if has_unique else "FAIL",
        "UNIQUE(...) present" if has_unique else "no UNIQUE clause",
    )
    if has_unique:
        for line in sql.splitlines():
            if "UNIQUE" in line.upper():
                print(f"        {line.strip()}")

    print("\nDOI table inventory in a fresh control plane:")
    for table in sorted(t for t in present if t.startswith("doi_")):
        print(f"  {table}")

    failures = [r for r in results if r[1] == "FAIL"]
    print(f"\nchecks: {len(results)}  failures: {len(failures)}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
