"""AVS-E2E-CODE-001: merge lane outputs into the final deliverables.

Merges:
  _lane_*_registers.csv -> 07_contradictions_register.csv + 08_gaps_register.csv
  _lane_*_fields.csv    -> 06_field_authority_trace.csv
  04_atlas_part*.md     -> 04_atlas.md (in real execution order)
Detects ID collisions across lanes and refuses to merge silently if found.
READ-ONLY on production. Writes only under audit/pipeline_map/AVS-E2E-CODE-001/.
"""
from __future__ import annotations

import csv
import sys
from collections import Counter
from pathlib import Path

OUT = Path(__file__).resolve().parents[1]

# atlas fragments in real execution order (upstream -> downstream -> read path)
ATLAS_ORDER = [
    ("04_atlas_partC_upstream.md", "Upstream — macro, packages, Discovery, Vanguard"),
    ("04_atlas_partB_hotspots.md", "Core contracts and hotspot stages"),
    ("04_atlas_partD_midstream.md", "Midstream — EIL, Execution, GARCH, WBS, EV3"),
    ("04_atlas_partE_canonical_contracts.md", "Canonical data substrate and contracts"),
    ("04_atlas_partK_automation_v2_read.md", "pipeline_interpreter/automation_v2 — read sections"),
    ("04_atlas_partK2_interpreter_generated.md", "pipeline_interpreter/ — generated sections"),
    ("04_atlas_partL_final_generated.md", "vanguard/, canonical remainder, tools/, tests/ — generated sections"),
    ("04_atlas_partF_lab_interpreter.md", "Read path — Intelligence Lab and Pipeline Interpreter"),
    ("04_atlas_partH_canonical_remainder.md", "Canonical data remainder and macro contracts"),
    ("04_atlas_partI_scripts.md", "scripts/ — read sections"),
    ("04_atlas_partI2_scripts_generated.md", "scripts/ — generated sections"),
    ("04_atlas_partJ_root_read.md", "Repository root — read sections"),
    ("04_atlas_partJ2_root_generated.md", "Repository root — generated sections"),
    ("04_atlas_partG_peripheral.md", "Peripheral packages — orchestrator/, market_structure/, ml_confidence_layer/, news_terminal/, ma_cockpit/, short_swing/, zero_dte/, bridge/"),
]

REG_COLS = ["id", "kind", "category", "files_lines", "what_A", "what_B",
            "evidence", "implication", "confidence"]
FLD_COLS = ["concept", "field_name", "role", "file", "line", "stage",
            "source_or_formula", "write_type", "reader_accepts", "notes"]


def read_rows(p: Path, cols: list[str]) -> list[dict]:
    if not p.exists():
        return []
    with p.open(encoding="utf-8", errors="replace", newline="") as f:
        rd = csv.DictReader(f)
        out = []
        for r in rd:
            out.append({c: (r.get(c) or "").strip() for c in cols})
        return out


def main() -> None:
    # ---- registers -------------------------------------------------
    reg_files = sorted(OUT.glob("_lane_*_registers.csv"))
    all_reg: list[dict] = []
    for p in reg_files:
        rows = read_rows(p, REG_COLS)
        print(f"  {p.name:<42} {len(rows):>4} rows")
        all_reg.extend(rows)

    ids = [r["id"] for r in all_reg if r["id"]]
    dupes = [i for i, n in Counter(ids).items() if n > 1]
    if dupes:
        print(f"\n!! ID COLLISIONS ACROSS LANES: {sorted(dupes)}")
        print("   Resolve before merging; not writing merged registers.")
        sys.exit(1)

    cons = [r for r in all_reg if r["kind"].upper() == "CON"]
    gaps = [r for r in all_reg if r["kind"].upper() == "GAP"]

    def write_reg(path: Path, rows: list[dict]) -> None:
        rows = sorted(rows, key=lambda r: r["id"])
        with path.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=REG_COLS)
            w.writeheader()
            w.writerows(rows)

    write_reg(OUT / "07_contradictions_register.csv", cons)
    write_reg(OUT / "08_gaps_register.csv", gaps)

    # ---- fields ----------------------------------------------------
    fld_files = sorted(OUT.glob("_lane_*_fields.csv"))
    all_fld: list[dict] = []
    for p in fld_files:
        rows = read_rows(p, FLD_COLS)
        print(f"  {p.name:<42} {len(rows):>4} rows")
        all_fld.extend(rows)
    all_fld.sort(key=lambda r: (r["concept"].lower(), r["field_name"].lower(),
                                r["role"], r["file"]))
    with (OUT / "06_field_authority_trace.csv").open(
            "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FLD_COLS)
        w.writeheader()
        w.writerows(all_fld)

    # ---- atlas -----------------------------------------------------
    parts, missing = [], []
    parts.append(
        "# 04 — Atlas: per-file, per-stage description\n\n"
        "**Document:** AVS-E2E-CODE-001 · Step 2\n"
        "**Evidence run:** `data/output/runs/20260831_010309/`\n\n"
        "Sections follow the template in the task specification. Files appear "
        "grouped by pipeline area, ordered to follow the real execution order "
        "established in `03_execution_order.md`. Non-orchestrated files are in "
        "`04_appendix_standalone_orphan_retired.md`.\n\n"
        "Claim tags: **OBSERVED** (read in code), **MEASURED** (computed from "
        "a run artefact or DB query), **INFERRED** (deduced; basis and "
        "confidence stated).\n\n---\n")
    for fn, title in ATLAS_ORDER:
        p = OUT / fn
        if not p.exists():
            missing.append(fn)
            continue
        body = p.read_text(encoding="utf-8", errors="replace")
        parts.append(f"\n\n# Part — {title}\n\n_Source fragment: `{fn}`_\n\n{body}")
    (OUT / "04_atlas.md").write_text("\n".join(parts), encoding="utf-8")

    # ---- coverage --------------------------------------------------
    inv = list(csv.DictReader((OUT / "01_inventory.csv").open(encoding="utf-8")))
    inv = [r for r in inv
           if not r["path"].startswith("audit/pipeline_map/AVS-E2E-CODE-001/")]
    core = [r for r in inv if r["classification"] in
            ("ORCHESTRATED", "MORNING", "LAB", "INTERPRETER", "LIBRARY")]
    atlas_text = (OUT / "04_atlas.md").read_text(encoding="utf-8", errors="replace")
    app_text = (OUT / "04_appendix_standalone_orphan_retired.md").read_text(
        encoding="utf-8", errors="replace")
    # A file counts as described only if it has its OWN section heading.
    # A bare path mention (a cross-reference from another file's section) is
    # not a description and must not inflate coverage.
    import re as _re
    headed = set()
    for m in _re.finditer(r"^###\s+`?([^\s`]+\.py)`?", atlas_text, _re.M):
        headed.add(m.group(1).replace("\\", "/"))
    described = [r for r in core if r["path"] in headed]
    undescribed = [r["path"] for r in core if r["path"] not in headed]
    # appendix entries are bolded `path` bullets, one per file
    in_app = [r for r in inv if f"**`{r['path']}`**" in app_text]

    print(f"\nCON rows                 = {len(cons)}")
    print(f"GAP rows                 = {len(gaps)}")
    print(f"field-trace rows         = {len(all_fld)}")
    print(f"concepts covered         = {len(set(r['concept'] for r in all_fld))}")
    if missing:
        print(f"MISSING atlas fragments  = {missing}")
    print(f"\nCOVERAGE: core files described  {len(described)}/{len(core)}")
    print(f"COVERAGE: appendix entries      {len(in_app)}")
    print(f"COVERAGE: total accounted       {len(described)+len(in_app)}/{len(inv)}")
    if undescribed:
        print(f"\nNOT YET DESCRIBED ({len(undescribed)}):")
        for p in undescribed[:40]:
            print(f"   {p}")
        if len(undescribed) > 40:
            print(f"   ... and {len(undescribed)-40} more")


if __name__ == "__main__":
    main()
