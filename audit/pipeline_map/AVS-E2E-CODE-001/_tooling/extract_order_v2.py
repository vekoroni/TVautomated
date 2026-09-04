"""AVS-E2E-CODE-001 Step 1 (v2): full ordered call sequence for the workflows.

Improves on v1 by resolving inline `from X import y as z` aliases (the Trigger
Layer is invoked this way and v1 missed it), and by attributing each call to the
repo module that defines it.
READ-ONLY. Writes only under audit/pipeline_map/AVS-E2E-CODE-001/.
"""
from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
OUT = ROOT / "audit" / "pipeline_map" / "AVS-E2E-CODE-001"
TARGET = ROOT / "intelligent_orchestrator.py"
WORKFLOWS = {"evening_workflow", "premarket_workflow", "run_phase_9c"}


def callee(node: ast.Call) -> str:
    f = node.func
    if isinstance(f, ast.Name):
        return f.id
    if isinstance(f, ast.Attribute):
        parts, cur = [], f
        while isinstance(cur, ast.Attribute):
            parts.append(cur.attr)
            cur = cur.value
        if isinstance(cur, ast.Name):
            parts.append(cur.id)
        return ".".join(reversed(parts))
    return "<dynamic>"


def main() -> None:
    src = TARGET.read_text(encoding="utf-8", errors="replace")
    tree = ast.parse(src)
    lines = src.splitlines()

    # module-level function names defined in the orchestrator itself
    local_defs = {n.name for n in tree.body if isinstance(n, ast.FunctionDef)}

    out = {}
    for fn in ast.walk(tree):
        if not isinstance(fn, ast.FunctionDef) or fn.name not in WORKFLOWS:
            continue

        # alias -> "module.origname" for every import inside this workflow
        alias_map: dict[str, str] = {}
        for node in ast.walk(fn):
            if isinstance(node, ast.ImportFrom) and node.module:
                for a in node.names:
                    alias_map[a.asname or a.name] = f"{node.module}.{a.name}"
            elif isinstance(node, ast.Import):
                for a in node.names:
                    alias_map[a.asname or a.name] = a.name

        events = []
        for node in ast.walk(fn):
            if isinstance(node, ast.ImportFrom) and node.module:
                events.append({
                    "line": node.lineno, "kind": "INLINE_IMPORT",
                    "detail": f"from {node.module} import "
                              + ", ".join(a.asname and f"{a.name} as {a.asname}"
                                          or a.name for a in a_names(node)),
                })
                continue
            if not isinstance(node, ast.Call):
                continue
            name = callee(node)
            root = name.split(".")[0]
            origin = alias_map.get(root)
            is_local = name in local_defs
            if not (is_local or origin):
                continue
            if origin and origin.split(".")[0] in {
                    "os", "sys", "json", "time", "pathlib", "datetime", "re",
                    "logging", "typing", "shutil", "math", "csv", "collections",
                    "subprocess", "dataclasses", "itertools", "functools"}:
                continue
            events.append({
                "line": node.lineno,
                "kind": "LOCAL_STAGE_FN" if is_local else "REPO_MODULE_CALL",
                "call": name,
                "resolves_to": origin or f"intelligent_orchestrator.{name}",
                "src": lines[node.lineno - 1].strip()[:140],
            })

        seen, dedup = set(), []
        for e in sorted(events, key=lambda d: d["line"]):
            k = (e["line"], e.get("call") or e.get("detail"))
            if k in seen:
                continue
            seen.add(k)
            dedup.append(e)
        out[fn.name] = dedup

    (OUT / "_tooling" / "execution_order_v2.json").write_text(
        json.dumps(out, indent=1), encoding="utf-8")

    for fname, seq in out.items():
        calls = [e for e in seq if e["kind"] != "INLINE_IMPORT"]
        print(f"\n=== {fname} ({len(calls)} resolved calls) ===")
        for e in seq:
            if e["kind"] == "INLINE_IMPORT":
                print(f"  L{e['line']:<6} IMPORT     {e['detail'][:110]}")
            else:
                print(f"  L{e['line']:<6} {e['kind'][:10]:<10} {e['call']:<42} <- {e['resolves_to'][:55]}")


def a_names(node):
    return node.names


if __name__ == "__main__":
    main()
