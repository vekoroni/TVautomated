"""AVS-E2E-CODE-001 Step 2 appendix: STANDALONE_CLI / ORPHAN / RETIRED entries.

One paragraph per non-orchestrated file, generated from inventory facts only
(docstring, entry points, size, git status, import fan-in). No inference beyond
what the inventory records; anything requiring judgement is left for manual
annotation and marked so.
READ-ONLY. Writes only under audit/pipeline_map/AVS-E2E-CODE-001/.
"""
from __future__ import annotations

import csv
import json
import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
OUT = ROOT / "audit" / "pipeline_map" / "AVS-E2E-CODE-001"

RETIRED_HINT = re.compile(
    r"retired|deprecated|do not use|dnu|obsolete|superseded|legacy|decommission",
    re.I)


def main() -> None:
    rows = list(csv.DictReader((OUT / "01_inventory.csv").open(encoding="utf-8")))
    rows = [r for r in rows
            if not r["path"].startswith("audit/pipeline_map/AVS-E2E-CODE-001/")]
    g = json.loads((OUT / "02_import_graph.json").read_text(encoding="utf-8"))
    imported_by = g["imported_by"]

    app = [r for r in rows
           if r["classification"] in ("STANDALONE_CLI", "ORPHAN")]

    # group by directory for navigability
    groups: dict[str, list[dict]] = defaultdict(list)
    for r in app:
        d = str(Path(r["path"]).parent)
        groups["<repo root>" if d == "." else d].append(r)

    lines = [
        "# 04 — Appendix: STANDALONE_CLI, ORPHAN and RETIRED files",
        "",
        "**Document:** AVS-E2E-CODE-001 · Step 2 appendix",
        "",
        "Files here are **not reachable** from `intelligent_orchestrator.py` "
        "(by import or by subprocess), from the Morning path, from the "
        "Intelligence Lab, or from the Pipeline Interpreter. Each gets a "
        "one-paragraph entry per the task specification. Classification is "
        "from `01_inventory.csv`; reachability is from `02_import_graph.json`.",
        "",
        "- **STANDALONE_CLI** — has an entry point (`__main__`, argparse, or a "
        "web app) but no orchestrated path reaches it.",
        "- **ORPHAN** — no entry point and never imported by anything in the "
        "live tree.",
        "- **RETIRED (hint)** — the filename or module docstring contains a "
        "retirement marker (retired/deprecated/DNU/obsolete/superseded/legacy). "
        "This is a *lexical* signal recorded as INFERRED-MEDIUM, not a "
        "verified decommissioning.",
        "",
        f"**Total appendix files: {len(app)}** "
        f"(STANDALONE_CLI {sum(1 for r in app if r['classification']=='STANDALONE_CLI')}, "
        f"ORPHAN {sum(1 for r in app if r['classification']=='ORPHAN')}).",
        "",
        "> An ORPHAN that is nonetheless imported by a *test* is noted; tests "
        "are outside the production inventory, so such a file remains ORPHAN "
        "for pipeline purposes.",
        "",
    ]

    retired_n = 0
    for d in sorted(groups):
        lines.append(f"## {d}")
        lines.append("")
        for r in sorted(groups[d], key=lambda x: x["path"]):
            p = r["path"]
            doc = (r["docstring_first_line"] or "").strip()
            eps = r["entry_points"] or "none"
            n = int(r["lines"])
            commit = r["commit"]
            fan_in = sorted(set(imported_by.get(p, [])))
            hint = bool(RETIRED_HINT.search(p) or RETIRED_HINT.search(doc))
            if hint:
                retired_n += 1
            tags = [r["classification"]]
            if hint:
                tags.append("RETIRED(hint)")
            if commit == "UNTRACKED":
                tags.append("UNTRACKED-BY-GIT")

            desc = doc if doc else "_No module docstring._"
            fan = ("Imported by: " + ", ".join(f"`{x}`" for x in fan_in)
                   if fan_in else "Never imported in the live tree.")
            lines.append(
                f"**`{p}`** — [{' · '.join(tags)}] {n} lines, "
                f"last commit `{commit}`{(' (' + r['commit_date'] + ')') if r['commit_date'] else ''}. "
                f"Entry points: {eps}. {desc} {fan} "
                f"[OBSERVED — inventory + import graph]"
            )
            lines.append("")
        lines.append("")

    lines.insert(
        14,
        f"**Files carrying a lexical retirement marker: {retired_n}.** "
        "Listed inline below with the `RETIRED(hint)` tag.\n")

    (OUT / "04_appendix_standalone_orphan_retired.md").write_text(
        "\n".join(lines), encoding="utf-8")

    print(f"appendix files      = {len(app)}")
    print(f"  STANDALONE_CLI    = {sum(1 for r in app if r['classification']=='STANDALONE_CLI')}")
    print(f"  ORPHAN            = {sum(1 for r in app if r['classification']=='ORPHAN')}")
    print(f"  RETIRED(hint)     = {retired_n}")
    print(f"  untracked by git  = {sum(1 for r in app if r['commit']=='UNTRACKED')}")
    print(f"directory groups    = {len(groups)}")


if __name__ == "__main__":
    main()
