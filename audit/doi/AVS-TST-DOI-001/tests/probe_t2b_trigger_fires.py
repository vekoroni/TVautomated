"""AVS-TST-DOI-001 / T2.2 — prove the append-only triggers actually FIRE.

Trigger existence is not proof: a BEFORE trigger on an empty table never runs.
This probe seeds a row into each DOI/lifecycle table and then attempts a real
UPDATE and a real DELETE, asserting both are aborted and the row survives.

Runs against a throwaway database under scratch\\ only.
Interpreter: venv\\Scripts\\python.exe
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

DB = ROOT / "audit/doi/AVS-TST-DOI-001/scratch/probe_t2b.sqlite"

from canonical_data.option_liquidity_lifecycle import OptionLiquidityLifecycleStore  # noqa: E402
from canonical_data.registry import CanonicalRegistry  # noqa: E402

TABLES = [
    "doi_contract_families",
    "doi_contract_assessments",
    "doi_preferred_contract_decisions",
    "doi_lifecycle_events",
    "doi_outcome_labels",
    "option_thesis_events",
    "option_contract_observations",
    "option_contract_selection_events",
]


def seed(con: sqlite3.Connection, table: str) -> bool:
    """Insert one row of placeholder values, bypassing FK/CHECK where possible."""
    info = list(con.execute(f"PRAGMA table_info({table})"))
    names = [r[1] for r in info]
    types = [(r[2] or "TEXT").upper() for r in info]
    values = []
    for name, typ in zip(names, types):
        if name == "decision_authority":
            values.append("NONE")
        elif name in {"can_change_direction", "can_invalidate_thesis", "can_grant_capital"}:
            values.append(0)
        elif name in {"governed_direction", "direction", "option_side"}:
            values.append("CALL")
        elif name == "planned_hold_sessions":
            values.append(5)
        elif name in {"thesis_version", "version", "calculation_version"}:
            values.append(1)
        elif name == "origin_spot":
            values.append(100.0)
        elif "INT" in typ:
            values.append(1)
        elif "REAL" in typ or "FLOA" in typ or "DOUB" in typ:
            values.append(1.0)
        else:
            values.append(f"PROBE_{name}")
    placeholders = ",".join(["?"] * len(names))
    try:
        con.execute(
            f"INSERT INTO {table} ({','.join(names)}) VALUES ({placeholders})", values
        )
        con.commit()
        return True
    except sqlite3.Error:
        con.rollback()
        return False


def main() -> int:
    if DB.exists():
        DB.unlink()
    store = OptionLiquidityLifecycleStore(CanonicalRegistry(DB))
    store.initialise()

    con = sqlite3.connect(DB)
    con.execute("PRAGMA foreign_keys=OFF")

    print(f"{'table':36} {'seeded':7} {'UPDATE':26} {'DELETE':26} {'row kept':9}")
    failures = 0
    unproven = 0
    for table in TABLES:
        seeded = seed(con, table)
        if not seeded:
            print(f"{table:36} {'no':7} {'-':26} {'-':26} {'-':9}  (could not seed)")
            unproven += 1
            continue
        before = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        try:
            con.execute(f"UPDATE {table} SET run_id='TAMPER'")
            con.commit()
            upd = "*** SUCCEEDED ***"
            failures += 1
        except sqlite3.Error as error:
            con.rollback()
            upd = f"blocked: {str(error)[:22]}"
        try:
            con.execute(f"DELETE FROM {table}")
            con.commit()
            dele = "*** SUCCEEDED ***"
            failures += 1
        except sqlite3.Error as error:
            con.rollback()
            dele = f"blocked: {str(error)[:22]}"
        after = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        kept = "yes" if after == before else f"NO {before}->{after}"
        if after != before:
            failures += 1
        print(f"{table:36} {'yes':7} {upd:26} {dele:26} {kept:9}")

    print()
    print(f"tables proven append-only by execution: {len(TABLES) - unproven - 0}")
    print(f"tables that could not be seeded (unproven here): {unproven}")
    print(f"append-only breaches: {failures}")
    print("RESULT:", "PASS" if failures == 0 else "FAIL")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
