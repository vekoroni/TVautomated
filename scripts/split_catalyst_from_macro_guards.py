#!/usr/bin/env python3
"""
Split catalyst_calendar_latest.csv into:
  - catalyst_calendar_clean_latest.csv   — genuine ticker catalysts only
  - macro_session_context_latest.csv     — MACRO_SESSION_GUARD rows (context only)

Genuine catalyst types: EARNINGS, M&A, BUYBACK, FDA, INDEX_EVENT,
RESTRUCTURING, SPIN_OFF, CONVERTIBLE, DEBT_REFINANCING.

Does NOT modify the original file.
"""

from __future__ import annotations

import csv
import logging
import sys
from pathlib import Path

log = logging.getLogger("AVSHUNTER.SPLIT_CATALYST")

REPO = Path(__file__).resolve().parents[1]
INPUT_FILE  = REPO / "dropbox" / "inputs" / "catalyst_calendar_latest.csv"
CLEAN_FILE  = REPO / "dropbox" / "inputs" / "catalyst_calendar_clean_latest.csv"
GUARDS_FILE = REPO / "dropbox" / "inputs" / "macro_session_context_latest.csv"

MACRO_GUARD_TYPE = "MACRO_SESSION_GUARD"


def split(
    input_path: Path = INPUT_FILE,
    clean_path: Path = CLEAN_FILE,
    guards_path: Path = GUARDS_FILE,
) -> dict:
    if not input_path.exists():
        log.error("Input file not found: %s", input_path)
        return {"status": "ERROR", "reason": f"not found: {input_path}"}

    with input_path.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        fieldnames = reader.fieldnames or []
        rows = list(reader)

    original_total = len(rows)
    clean_rows: list = []
    guard_rows: list = []

    for row in rows:
        catalyst_type = str(row.get("catalyst_type", "") or "").strip().upper()
        if catalyst_type == MACRO_GUARD_TYPE:
            guard_rows.append(row)
        else:
            clean_rows.append(row)

    def _write(path: Path, data: list) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(data)

    _write(clean_path, clean_rows)
    _write(guards_path, guard_rows)

    result = {
        "status":         "OK",
        "original_total": original_total,
        "clean_rows":     len(clean_rows),
        "guard_rows":     len(guard_rows),
        "sum_check":      len(clean_rows) + len(guard_rows) == original_total,
        "clean_path":     str(clean_path),
        "guards_path":    str(guards_path),
        "original_path":  str(input_path),
    }

    log.info(
        "[SPLIT] original=%d  clean=%d  guards=%d  sum_ok=%s",
        original_total, len(clean_rows), len(guard_rows), result["sum_check"],
    )
    log.info("[SPLIT] clean  → %s", clean_path)
    log.info("[SPLIT] guards → %s", guards_path)

    if not result["sum_check"]:
        log.error("[SPLIT] Row count mismatch — check output files!")

    return result


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    result = split()
    if result.get("status") != "OK":
        print(f"ERROR: {result.get('reason')}", file=sys.stderr)
        return 1
    print(
        f"[OK] original={result['original_total']}  "
        f"clean={result['clean_rows']}  "
        f"guards={result['guard_rows']}  "
        f"sum_ok={result['sum_check']}"
    )
    print(f"  clean  -> {result['clean_path']}")
    print(f"  guards -> {result['guards_path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
