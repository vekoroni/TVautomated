"""AVS-E2E-CODE-001 Step 0c (v2): classification including subprocess-launched stages.

v1 followed imports only and therefore missed every stage the orchestrator
launches as a subprocess (Discovery, Vanguard, EIL runner, GARCH, WBS, ...).
v2 seeds the ORCHESTRATED root set with those script literals as well, then
walks the import graph transitively from all of them.
READ-ONLY. Writes only under audit/pipeline_map/AVS-E2E-CODE-001/.
"""
from __future__ import annotations

import csv
import json
import re
from collections import deque
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
OUT = ROOT / "audit" / "pipeline_map" / "AVS-E2E-CODE-001"


def find_script_roots(entry: Path, known: set[str]) -> set[str]:
    """Resolve .py literals in a driver file to real repo paths."""
    src = entry.read_text(encoding="utf-8-sig", errors="replace")
    out = set()
    for lit in set(re.findall(r'["\']([A-Za-z0-9_\-/\\.]+\.py)["\']', src)):
        name = lit.replace("\\", "/").split("/")[-1]
        cands = [k for k in known if k.split("/")[-1] == name]
        # prefer scripts/<name> then root <name> then any
        for pref in (f"scripts/{name}", name):
            if pref in cands:
                out.add(pref)
                break
        else:
            if cands:
                out.add(sorted(cands, key=len)[0])
    return out


def main() -> None:
    g = json.loads((OUT / "02_import_graph.json").read_text(encoding="utf-8"))
    edges, imported_by = g["internal_edges"], g["imported_by"]

    inv = list(csv.DictReader((OUT / "01_inventory.csv").open(encoding="utf-8")))
    inv = [r for r in inv if not r["path"].startswith(
        "audit/pipeline_map/AVS-E2E-CODE-001/")]
    known = {r["path"] for r in inv}

    orch_roots = {"intelligent_orchestrator.py"}
    orch_roots |= find_script_roots(ROOT / "intelligent_orchestrator.py", known)
    # second hop: scripts launched by those scripts
    for r in sorted(orch_roots):
        p = ROOT / r
        if p.exists():
            orch_roots |= find_script_roots(p, known)

    morning_roots = {"morning_gate.py", "execution_gate.py",
                     "morning_handoff_finalizer.py"}
    for r in sorted(morning_roots):
        p = ROOT / r
        if p.exists():
            morning_roots |= find_script_roots(p, known)

    lab_roots = {"intelligence-lab/intelligence_lab.py"}
    interp_roots = {p for p in known if p.startswith("pipeline_interpreter/")}

    def reach(roots: set[str]) -> set[str]:
        seen, q = set(), deque(r for r in roots if r in known)
        while q:
            cur = q.popleft()
            if cur in seen:
                continue
            seen.add(cur)
            for nxt in edges.get(cur, []):
                if nxt not in seen:
                    q.append(nxt)
        return seen

    label: dict[str, str] = {}
    for name, roots in (("ORCHESTRATED", orch_roots), ("MORNING", morning_roots),
                        ("LAB", lab_roots), ("INTERPRETER", interp_roots)):
        for p in reach(roots):
            label.setdefault(p, name)

    counts, rows = {}, []
    for r in inv:
        p = r["path"]
        lab = label.get(p)
        if lab is None:
            lab = ("LIBRARY" if p in imported_by
                   else "STANDALONE_CLI" if r["entry_points"] else "ORPHAN")
        r["classification"] = lab
        r["imported_by_count"] = len(set(imported_by.get(p, [])))
        r["is_subprocess_stage"] = "Y" if p in orch_roots else ""
        counts[lab] = counts.get(lab, 0) + 1
        rows.append(r)

    with (OUT / "01_inventory.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    (OUT / "_tooling" / "roots.json").write_text(json.dumps({
        "orchestrated_roots": sorted(orch_roots),
        "morning_roots": sorted(morning_roots),
        "lab_roots": sorted(lab_roots),
        "unresolved_script_literals": sorted(
            l for l in find_script_roots(ROOT / "intelligent_orchestrator.py", known)
            if l not in known),
    }, indent=1), encoding="utf-8")

    print(f"TOTAL_LIVE_PY = {len(rows)}")
    for k in ["ORCHESTRATED", "MORNING", "LAB", "INTERPRETER", "LIBRARY",
              "STANDALONE_CLI", "ORPHAN"]:
        print(f"  {k:<15} {counts.get(k,0):>4}")
    core = [r for r in rows if r["classification"] in
            ("ORCHESTRATED", "MORNING", "LAB", "INTERPRETER", "LIBRARY")]
    print(f"\nATLAS SCOPE (Step 2)      = {len(core)}")
    print(f"APPENDIX                  = {len(rows)-len(core)}")
    print(f"\nSubprocess stage roots resolved = {len(orch_roots)}")


if __name__ == "__main__":
    main()
