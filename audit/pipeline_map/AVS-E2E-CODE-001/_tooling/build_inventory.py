"""AVS-E2E-CODE-001 Step 0: inventory + import graph.

READ-ONLY. Writes only under audit/pipeline_map/AVS-E2E-CODE-001/.
Run:  python audit/pipeline_map/AVS-E2E-CODE-001/_tooling/build_inventory.py
"""
from __future__ import annotations

import ast
import csv
import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
OUT = ROOT / "audit" / "pipeline_map" / "AVS-E2E-CODE-001"

# Trees excluded from the LIVE inventory. Archival trees are counted separately
# and reported as an aggregate in 00_README.md / the appendix.
VENV_MARKERS = {"venv", ".venv", "site-packages", "node_modules", "__pycache__",
                ".git", ".codex_python313_runtime", ".codex_py312_testenv",
                ".pytest_cache", ".codex_test_temp", ".codex_test_tmp"}
ARCHIVAL_TOP = {"backups", "Archive", "_cleanup_holding", "decommissioned",
                "datadnuold2404", "legacy", "audit_baseline", "pytest-of-ACKVerissimo",
                "tmpmvmp0agl", "tmpujgjsk2n"}


def is_excluded(rel: Path) -> bool:
    return any(part in VENV_MARKERS for part in rel.parts)


def is_archival(rel: Path) -> bool:
    return rel.parts and rel.parts[0] in ARCHIVAL_TOP


def git_info(rel: str) -> tuple[str, str]:
    try:
        out = subprocess.run(
            ["git", "log", "-1", "--format=%h|%ad", "--date=short", "--", rel],
            cwd=ROOT, capture_output=True, text=True, timeout=20,
        ).stdout.strip()
        if "|" in out:
            h, d = out.split("|", 1)
            return h, d
    except Exception:
        pass
    return "UNTRACKED", ""


def analyse(path: Path):
    """Return (docstring_first_line, entrypoints, imports, defs)."""
    try:
        src = path.read_text(encoding="utf-8-sig", errors="replace")
    except Exception:
        return "", [], [], []
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return "<SYNTAX_ERROR>", [], [], []

    doc = (ast.get_docstring(tree) or "").strip().splitlines()
    doc0 = doc[0] if doc else ""

    imports, defs, entry = [], [], []
    has_main = "__main__" in src and "if __name__" in src
    if has_main:
        entry.append("__main__")

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                imports.append(a.name)
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            lvl = "." * (node.level or 0)
            imports.append(f"{lvl}{mod}")
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.col_offset == 0 and not node.name.startswith("_"):
                defs.append(node.name)
        elif isinstance(node, ast.ClassDef):
            if node.col_offset == 0:
                defs.append(f"class:{node.name}")

    low = src.lower()
    if "argparse" in low and "add_argument" in low:
        entry.append("argparse-CLI")
    if "click.command" in low or "@app.command" in low:
        entry.append("click/typer-CLI")
    if "flask(" in low or "fastapi(" in low:
        entry.append("web-app")
    return doc0, sorted(set(entry)), sorted(set(imports)), sorted(set(defs))


def main() -> None:
    live, archival_count = [], 0
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in VENV_MARKERS]
        for fn in filenames:
            if not fn.endswith(".py"):
                continue
            p = Path(dirpath) / fn
            rel = p.relative_to(ROOT)
            if is_excluded(rel):
                continue
            if is_archival(rel):
                archival_count += 1
                continue
            live.append(rel)

    live.sort()
    rows, import_graph = [], {}
    for rel in live:
        p = ROOT / rel
        rels = rel.as_posix()
        try:
            nlines = sum(1 for _ in p.open("r", encoding="utf-8-sig", errors="replace"))
        except Exception:
            nlines = -1
        doc0, entry, imports, defs = analyse(p)
        h, d = git_info(rels)
        rows.append({
            "path": rels,
            "lines": nlines,
            "commit": h,
            "commit_date": d,
            "docstring_first_line": doc0[:300],
            "entry_points": ";".join(entry),
            "public_defs": ";".join(defs[:40]),
            "n_imports": len(imports),
        })
        import_graph[rels] = imports

    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / "01_inventory.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    (OUT / "02_import_graph.json").write_text(
        json.dumps({"raw_imports": import_graph}, indent=1), encoding="utf-8")

    stems = {}
    for rels in import_graph:
        stems.setdefault(Path(rels).stem, []).append(rels)

    resolved, unresolved = {}, {}
    for rels, imps in import_graph.items():
        r, u = [], []
        for imp in imps:
            base = imp.lstrip(".").split(".")[0]
            if base in stems:
                r.extend(stems[base])
            else:
                u.append(imp)
        resolved[rels] = sorted(set(r))
        unresolved[rels] = sorted(set(u))

    imported_by = {}
    for src_f, tgts in resolved.items():
        for t in tgts:
            imported_by.setdefault(t, []).append(src_f)

    (OUT / "02_import_graph.json").write_text(json.dumps({
        "internal_edges": resolved,
        "imported_by": {k: sorted(set(v)) for k, v in imported_by.items()},
        "external_or_unresolved": unresolved,
    }, indent=1), encoding="utf-8")

    print(f"LIVE_PY_FILES={len(live)}")
    print(f"ARCHIVAL_PY_FILES_EXCLUDED={archival_count}")
    print(f"FILES_WITH_ENTRYPOINT={sum(1 for r in rows if r['entry_points'])}")
    print(f"FILES_IMPORTED_BY_SOMETHING={len(imported_by)}")
    print(f"UNTRACKED={sum(1 for r in rows if r['commit']=='UNTRACKED')}")
    top = sorted(imported_by.items(), key=lambda kv: -len(set(kv[1])))[:15]
    print("\nMOST-IMPORTED:")
    for k, v in top:
        print(f"  {len(set(v)):4d}  {k}")


if __name__ == "__main__":
    main()
