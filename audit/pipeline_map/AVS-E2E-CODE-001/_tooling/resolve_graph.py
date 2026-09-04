"""AVS-E2E-CODE-001 Step 0b: resolve the import graph by full dotted path.

Fixes the stem-collision ambiguity (e.g. `contracts` exists as both
`contracts/` package and `pipeline_interpreter/capture_v1/contracts.py`).
Resolution order: exact dotted path -> package __init__ -> unique stem ->
AMBIGUOUS (recorded, not guessed).
READ-ONLY. Writes only under audit/pipeline_map/AVS-E2E-CODE-001/.
"""
from __future__ import annotations

import ast
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
OUT = ROOT / "audit" / "pipeline_map" / "AVS-E2E-CODE-001"
VENV_MARKERS = {"venv", ".venv", "site-packages", "node_modules", "__pycache__",
                ".git", ".codex_python313_runtime", ".codex_py312_testenv",
                ".pytest_cache", ".codex_test_temp", ".codex_test_tmp"}
ARCHIVAL_TOP = {"backups", "Archive", "_cleanup_holding", "decommissioned",
                "datadnuold2404", "legacy", "audit_baseline",
                "pytest-of-ACKVerissimo", "tmpmvmp0agl", "tmpujgjsk2n"}


def live_files():
    out = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in VENV_MARKERS]
        for fn in filenames:
            if not fn.endswith(".py"):
                continue
            rel = (Path(dirpath) / fn).relative_to(ROOT)
            if any(p in VENV_MARKERS for p in rel.parts):
                continue
            if rel.parts and rel.parts[0] in ARCHIVAL_TOP:
                continue
            out.append(rel)
    return sorted(out)


def main() -> None:
    files = live_files()
    posix = [f.as_posix() for f in files]

    # dotted module path -> file
    by_dotted: dict[str, str] = {}
    for f in files:
        parts = list(f.parts)
        if parts[-1] == "__init__.py":
            dotted = ".".join(parts[:-1])
        else:
            dotted = ".".join(parts[:-1] + [f.stem])
        by_dotted.setdefault(dotted, f.as_posix())

    by_stem: dict[str, list[str]] = {}
    for f in files:
        by_stem.setdefault(f.stem, []).append(f.as_posix())

    edges: dict[str, list[str]] = {}
    ambiguous: dict[str, list[str]] = {}
    external: dict[str, list[str]] = {}

    for f in files:
        rels = f.as_posix()
        try:
            tree = ast.parse((ROOT / f).read_text(encoding="utf-8-sig", errors="replace"))
        except SyntaxError:
            edges[rels] = []
            continue
        mods: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                mods.extend(a.name for a in node.names)
            elif isinstance(node, ast.ImportFrom):
                if node.level:  # relative import
                    base = ".".join(f.parts[:-1])
                    mods.append(f"{base}.{node.module}" if node.module else base)
                elif node.module:
                    mods.append(node.module)

        res, amb, ext = [], [], []
        for m in mods:
            if m in by_dotted:
                res.append(by_dotted[m])
                continue
            # try progressively shorter dotted prefixes (from X.Y import Z)
            hit = None
            parts = m.split(".")
            for i in range(len(parts), 0, -1):
                cand = ".".join(parts[:i])
                if cand in by_dotted:
                    hit = by_dotted[cand]
                    break
            if hit:
                res.append(hit)
                continue
            stem = parts[0]
            if stem in by_stem:
                if len(by_stem[stem]) == 1:
                    res.append(by_stem[stem][0])
                else:
                    amb.append(f"{m} -> {'|'.join(by_stem[stem])}")
            else:
                ext.append(m)
        edges[rels] = sorted(set(res))
        if amb:
            ambiguous[rels] = sorted(set(amb))
        external[rels] = sorted(set(ext))

    imported_by: dict[str, list[str]] = {}
    for s, tgts in edges.items():
        for t in tgts:
            imported_by.setdefault(t, []).append(s)

    (OUT / "02_import_graph.json").write_text(json.dumps({
        "_note": "internal_edges resolved by full dotted path; ambiguous "
                 "stem collisions recorded separately and never guessed.",
        "internal_edges": edges,
        "imported_by": {k: sorted(set(v)) for k, v in imported_by.items()},
        "ambiguous_imports": ambiguous,
        "external_or_stdlib": external,
    }, indent=1), encoding="utf-8")

    never_imported = [p for p in posix if p not in imported_by]
    print(f"FILES={len(posix)}")
    print(f"IMPORTED_BY_SOMETHING={len(imported_by)}")
    print(f"NEVER_IMPORTED={len(never_imported)}")
    print(f"FILES_WITH_AMBIGUOUS_IMPORTS={len(ambiguous)}")
    print("\nMOST-IMPORTED (resolved):")
    for k, v in sorted(imported_by.items(), key=lambda kv: -len(set(kv[1])))[:20]:
        print(f"  {len(set(v)):4d}  {k}")


if __name__ == "__main__":
    main()
