"""AVS-E2E-CODE-001: normalise the merged field-authority trace.

Two defects arise from merging independently-authored lane CSVs:
 1. concept names differ in case and wording between lanes, splitting the
    task's 14 concepts into 28 buckets;
 2. a small number of rows are field-shifted because a lane emitted an
    unescaped comma or quote, which shows up as a write_type that is not one
    of the six legal values.

This script folds concept aliases onto the canonical 14 (plus any genuinely
extra concept found), and quarantines malformed rows into a separate file
rather than silently keeping or dropping them.
READ-ONLY on production. Writes only under audit/pipeline_map/AVS-E2E-CODE-001/.
"""
from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path

OUT = Path(__file__).resolve().parents[1]
COLS = ["concept", "field_name", "role", "file", "line", "stage",
        "source_or_formula", "write_type", "reader_accepts", "notes"]
LEGAL_WRITE_TYPES = {"authority", "alias", "fallback", "recompute", "display",
                     "NOT_APPLICABLE", ""}

# canonical concept -> accepted aliases (lower-cased comparison)
CANON = {
    "Direction": {"direction"},
    "Horizon bucket": {"horizon", "horizon bucket", "horizon_bucket"},
    "Planned hold": {"hold", "planned hold", "planned_hold",
                     "remaining hold sessions"},
    "DTE": {"dte"},
    "Structural target": {"target", "structural target", "structural_target"},
    "Invalidation / stop": {"invalidation", "stop", "invalidation / stop",
                            "invalidation/stop"},
    "Trigger block": {"trigger", "trigger block"},
    "Verdict / permission": {"verdict", "permission", "verdict / permission",
                             "verdict/permission"},
    "Monetisability": {"monetisability", "monetizability"},
    "Selected contract identity": {"contract-identity", "contract identity",
                                   "selected contract identity",
                                   "selected_contract_identity"},
    "Quote": {"quote"},
    "Run identity vs session vs quote timestamp": {
        "timestamp", "run identity vs session vs quote ts",
        "run identity vs session vs quote timestamp", "run identity"},
    "Macro / regime": {"macro", "regime", "macro / regime", "macro/regime"},
    "Lifecycle state": {"lifecycle", "lifecycle state", "lifecycle_state"},
    "Lab display": {"lab display", "lab_display"},
}
ALIAS = {a: c for c, aliases in CANON.items() for a in aliases}
ALIAS.update({c.lower(): c for c in CANON})


def main() -> None:
    rows = list(csv.DictReader((OUT / "06_field_authority_trace.csv")
                               .open(encoding="utf-8", errors="replace")))
    clean, bad = [], []
    for r in rows:
        r = {c: (r.get(c) or "").strip() for c in COLS}
        key = r["concept"].strip().lower()
        r["concept"] = ALIAS.get(key, r["concept"].strip() or "UNCLASSIFIED")
        if r["write_type"] not in LEGAL_WRITE_TYPES:
            bad.append(r)
        else:
            clean.append(r)

    clean.sort(key=lambda r: (r["concept"], r["field_name"].lower(),
                              r["role"], r["file"]))
    with (OUT / "06_field_authority_trace.csv").open(
            "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLS)
        w.writeheader()
        w.writerows(clean)

    if bad:
        with (OUT / "06_field_authority_trace_MALFORMED.csv").open(
                "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=COLS)
            w.writeheader()
            w.writerows(bad)

    print(f"clean rows       = {len(clean)}")
    print(f"quarantined rows = {len(bad)}  -> 06_field_authority_trace_MALFORMED.csv")
    print(f"concepts         = {len(set(r['concept'] for r in clean))}")
    print("\nrows per concept (writers / readers):")
    for c, n in Counter(r["concept"] for r in clean).most_common():
        sub = [r for r in clean if r["concept"] == c]
        wr = sum(1 for r in sub if r["role"] == "writer")
        rd = sum(1 for r in sub if r["role"] == "reader")
        auth = sum(1 for r in sub if r["write_type"] == "authority")
        print(f"  {n:>4}  w={wr:<3} r={rd:<3} authority={auth:<3} {c}")
    print("\nwrite_type (writers only):")
    for k, v in Counter(r["write_type"] for r in clean
                        if r["role"] == "writer").most_common():
        print(f"  {v:>4}  {k or '(blank)'}")


if __name__ == "__main__":
    main()
