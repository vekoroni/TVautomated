"""AVS-E2E-CODE-001 Step 0c: classify every live .py by reachability.

ORCHESTRATED : reachable from intelligent_orchestrator.py
MORNING      : reachable from morning_gate.py / execution_gate.py / morning_handoff_finalizer.py
LAB          : reachable from intelligence-lab/intelligence_lab.py
INTERPRETER  : reachable from pipeline_interpreter/
LIBRARY      : imported by something, no entry point, not in a root set above
STANDALONE_CLI: has an entry point, not reachable from any root
ORPHAN       : no entry point and never imported
Precedence: ORCHESTRATED > MORNING > LAB > INTERPRETER > LIBRARY > STANDALONE_CLI > ORPHAN
READ-ONLY. Writes only under audit/pipeline_map/AVS-E2E-CODE-001/.
"""
from __future__ import annotations

import csv
import json
from collections import deque
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
OUT = ROOT / "audit" / "pipeline_map" / "AVS-E2E-CODE-001"

ROOTS = [
    ("ORCHESTRATED", ["intelligent_orchestrator.py"]),
    ("MORNING", ["morning_gate.py", "execution_gate.py",
                 "morning_handoff_finalizer.py"]),
    ("LAB", ["intelligence-lab/intelligence_lab.py"]),
    ("INTERPRETER", ["pipeline_interpreter/pipeline_interpreter.py"]),
]


def main() -> None:
    g = json.loads((OUT / "02_import_graph.json").read_text(encoding="utf-8"))
    edges = g["internal_edges"]
    imported_by = g["imported_by"]

    inv = list(csv.DictReader((OUT / "01_inventory.csv").open(encoding="utf-8")))
    # exclude this audit's own tooling from the population
    inv = [r for r in inv if not r["path"].startswith(
        "audit/pipeline_map/AVS-E2E-CODE-001/")]
    all_paths = {r["path"] for r in inv}

    label: dict[str, str] = {}
    for name, roots in ROOTS:
        seen, q = set(), deque([r for r in roots if r in edges])
        for r in roots:
            if r not in edges:
                print(f"  !! root not found in graph: {r}")
        while q:
            cur = q.popleft()
            if cur in seen:
                continue
            seen.add(cur)
            for nxt in edges.get(cur, []):
                if nxt not in seen:
                    q.append(nxt)
        for p in seen:
            label.setdefault(p, name)

    interp_extra = [p for p in all_paths if p.startswith("pipeline_interpreter/")]
    for p in interp_extra:
        label.setdefault(p, "INTERPRETER")

    counts: dict[str, int] = {}
    rows = []
    for r in inv:
        p = r["path"]
        lab = label.get(p)
        if lab is None:
            if p in imported_by:
                lab = "LIBRARY"
            elif r["entry_points"]:
                lab = "STANDALONE_CLI"
            else:
                lab = "ORPHAN"
        r["classification"] = lab
        r["imported_by_count"] = len(set(imported_by.get(p, [])))
        counts[lab] = counts.get(lab, 0) + 1
        rows.append(r)

    fields = list(rows[0].keys())
    with (OUT / "01_inventory.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)

    print(f"TOTAL_LIVE_PY (excl. this audit's tooling) = {len(rows)}")
    for k in ["ORCHESTRATED", "MORNING", "LAB", "INTERPRETER", "LIBRARY",
              "STANDALONE_CLI", "ORPHAN"]:
        print(f"  {k:<15} {counts.get(k,0):>4}")

    core = [r for r in rows if r["classification"] in
            ("ORCHESTRATED", "MORNING", "LAB", "INTERPRETER", "LIBRARY")]
    print(f"\nDESCRIBE_IN_ATLAS (Step 2 scope) = {len(core)}")
    print(f"APPENDIX (standalone/orphan)      = {len(rows)-len(core)}")

    print("\nORCHESTRATED files:")
    for r in sorted(rows, key=lambda x: x["path"]):
        if r["classification"] == "ORCHESTRATED":
            print(f"   {r['path']}")


if __name__ == "__main__":
    main()
