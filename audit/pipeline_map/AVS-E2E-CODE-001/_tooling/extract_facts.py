"""AVS-E2E-CODE-001: per-file fact extractor for the remaining atlas sections.

Pulls the template-relevant evidence for each undescribed file so that sections
can be written with real file:line citations rather than impressions:

  docstring, entry points, imports / imported-by, public defs,
  direction branches, fallback chains, file writes, raise sites,
  numeric literals in assignments, atomicity markers, authority-claim comments.

Usage:  python _tooling/extract_facts.py <path-prefix> [...]
Writes: _tooling/facts/<slug>.json  and prints a compact digest.
READ-ONLY on production. Writes only under audit/pipeline_map/AVS-E2E-CODE-001/.
"""
from __future__ import annotations

import ast
import csv
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parents[1]
FACTS = OUT / "_tooling" / "facts"

DIRECTION = re.compile(
    r"""(direction\s*[=!]=|options_direction|canonical_direction|
        governed_direction|final_direction|trade_direction|contract_type|
        ["']CALL["']|["']PUT["']|["']STRANGLE["']|["']UNRESOLVED["'])""",
    re.X)
FALLBACK = re.compile(
    r"""(\.get\([^)]*,\s*[^)]+\)|\bor\s+["'0-9]|setdefault\(|
        \bfirst\(|except[^:]*:\s*pass)""", re.X)
WRITE = re.compile(
    r"""(to_csv\(|to_parquet\(|write_text\(|write_bytes\(|json\.dump|
        open\([^)]*["']w|open\([^)]*["']a|DictWriter|\.replace\(|os\.replace)""",
    re.X)
ATOMIC = re.compile(r"(os\.replace|mkstemp|\.tmp|tempfile|NamedTemporary)")
AUTHORITY = re.compile(
    r"(single (?:source|authority)|sole authority|advisory only|never default|"
    r"authoritative|must not|read-only|does not (?:modify|write)|"
    r"NEVER|ONLY|canonical)", re.I)
VERSION = re.compile(r"(schema_version|__version__|contract_version|"
                     r"calculation_version|VERSION\s*=)")


def facts_for(rel: str, graph: dict, inv: dict) -> dict:
    p = ROOT / rel
    try:
        src = p.read_text(encoding="utf-8-sig", errors="replace")
    except Exception as e:
        return {"path": rel, "error": str(e)}
    lines = src.splitlines()
    d: dict = {"path": rel, "n_lines": len(lines)}
    r = inv.get(rel, {})
    d["classification"] = r.get("classification", "")
    d["commit"] = r.get("commit", "")
    d["entry_points"] = r.get("entry_points", "")
    d["imported_by"] = sorted(set(graph["imported_by"].get(rel, [])))[:12]
    d["imports"] = [x for x in graph["internal_edges"].get(rel, [])][:14]

    try:
        tree = ast.parse(src)
        d["docstring"] = (ast.get_docstring(tree) or "").strip()[:600]
        defs, classes = [], []
        for n in tree.body:
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                defs.append(f"{n.name}:{n.lineno}")
            elif isinstance(n, ast.ClassDef):
                meths = [f"{m.name}:{m.lineno}" for m in n.body
                         if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef))]
                classes.append({"name": f"{n.name}:{n.lineno}",
                                "methods": meths[:18]})
        d["functions"] = defs[:30]
        d["classes"] = classes[:8]
        d["raises"] = sorted({
            f"{getattr(n.exc.func,'id',getattr(getattr(n.exc,'func',None),'attr','?'))}:{n.lineno}"
            for n in ast.walk(tree)
            if isinstance(n, ast.Raise) and isinstance(n.exc, ast.Call)})[:20]
    except SyntaxError as e:
        d["docstring"] = "<SYNTAX_ERROR>"
        d["syntax_error"] = str(e)

    def hits(rx, cap=14):
        out = []
        for i, ln in enumerate(lines, 1):
            if rx.search(ln):
                out.append(f"{i}: {ln.strip()[:150]}")
                if len(out) >= cap:
                    break
        return out

    d["direction_branches"] = hits(DIRECTION)
    d["fallbacks"] = hits(FALLBACK)
    d["writes"] = hits(WRITE, 10)
    d["atomic_markers"] = hits(ATOMIC, 6)
    d["authority_comments"] = [h for h in hits(AUTHORITY, 12)
                               if "#" in h or '"""' in h or "'''" in h][:8]
    d["version_fields"] = hits(VERSION, 6)
    d["counts"] = {
        "direction": sum(1 for ln in lines if DIRECTION.search(ln)),
        "fallback": sum(1 for ln in lines if FALLBACK.search(ln)),
        "write": sum(1 for ln in lines if WRITE.search(ln)),
    }
    return d


def main() -> None:
    prefixes = sys.argv[1:]
    if not prefixes:
        print("usage: extract_facts.py <path-prefix> [...]")
        return
    graph = json.loads((OUT / "02_import_graph.json").read_text(encoding="utf-8"))
    inv = {r["path"]: r for r in csv.DictReader(
        (OUT / "01_inventory.csv").open(encoding="utf-8"))}
    cov = json.loads((OUT / "_tooling" / "coverage.json").read_text(encoding="utf-8"))
    def match(path: str) -> bool:
        for pref in prefixes:
            if pref == "ROOT":
                if "/" not in path:
                    return True
            elif path.startswith(pref):
                return True
        return False

    todo = [p for p in cov["undescribed"] if match(p)]

    FACTS.mkdir(parents=True, exist_ok=True)
    out = []
    for rel in sorted(todo):
        out.append(facts_for(rel, graph, inv))
    slug = re.sub(r"[^a-z0-9]+", "_", "_".join(prefixes).lower()).strip("_")[:60]
    (FACTS / f"{slug}.json").write_text(json.dumps(out, indent=1),
                                        encoding="utf-8")

    print(f"files = {len(out)}   -> _tooling/facts/{slug}.json\n")
    for d in out:
        c = d.get("counts", {})
        print(f"{d['n_lines']:>6}L {d.get('classification',''):<12} {d['path']}")
        _doc = (d.get('docstring') or '(none)')[:110]
        _doc = _doc.encode('ascii', 'replace').decode('ascii')
        _doc = " ".join(_doc.split())
        print(f"        doc: {_doc}")
        print(f"        dir={c.get('direction',0):<3} fb={c.get('fallback',0):<3} "
              f"wr={c.get('write',0):<3} imported_by={len(d.get('imported_by',[]))} "
              f"entry={d.get('entry_points') or '-'}")


if __name__ == "__main__":
    main()
