"""AVS-E2E-CODE-001 Step 1: extract real execution order from the orchestrator.

Walks the AST of evening_workflow / premarket_workflow and emits every call in
source order, tagging stage-like calls (run_*, apply_*, publish_*, merge_*,
patch_*, write_*, archive_*, enforce_*, inject_*) and every subprocess launch
with the script it invokes.
READ-ONLY. Writes only under audit/pipeline_map/AVS-E2E-CODE-001/.
"""
from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
OUT = ROOT / "audit" / "pipeline_map" / "AVS-E2E-CODE-001"
TARGET = ROOT / "intelligent_orchestrator.py"

STAGE_PREFIXES = ("run_", "apply_", "publish_", "prepare_", "merge_", "patch_",
                  "write_", "archive_", "enforce_", "inject_", "build_",
                  "generate_", "pin_", "resolve_", "validate_", "emit_",
                  "finalise_", "finalize_", "sync_", "export_", "load_")


def callee_name(node: ast.Call) -> str:
    f = node.func
    if isinstance(f, ast.Name):
        return f.id
    if isinstance(f, ast.Attribute):
        parts = []
        cur = f
        while isinstance(cur, ast.Attribute):
            parts.append(cur.attr)
            cur = cur.value
        if isinstance(cur, ast.Name):
            parts.append(cur.id)
        return ".".join(reversed(parts))
    return "<dynamic>"


def literal_scripts(node: ast.Call) -> list[str]:
    """Pull any .py filename literals out of a call's args (subprocess cmds)."""
    found = []
    for sub in ast.walk(node):
        if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
            v = sub.value
            if v.endswith(".py") or "/" in v and v.endswith(".py"):
                found.append(v)
    return found


def main() -> None:
    tree = ast.parse(TARGET.read_text(encoding="utf-8", errors="replace"))
    result = {}
    for fn in ast.walk(tree):
        if not isinstance(fn, ast.FunctionDef):
            continue
        if fn.name not in {"evening_workflow", "premarket_workflow", "main",
                           "run_phase_9c"}:
            continue
        seq = []
        for node in ast.walk(fn):
            if not isinstance(node, ast.Call):
                continue
            name = callee_name(node)
            is_stage = name.startswith(STAGE_PREFIXES)
            is_proc = name.startswith(("subprocess.", "sp.")) or name in {
                "check_call", "check_output", "Popen", "run"}
            scripts = literal_scripts(node) if is_proc else []
            if is_stage or is_proc or scripts:
                seq.append({
                    "line": node.lineno,
                    "call": name,
                    "kind": "SUBPROCESS" if (is_proc or scripts) else "STAGE_FN",
                    "scripts": sorted(set(scripts)),
                })
        seq.sort(key=lambda d: d["line"])
        # de-duplicate consecutive identical calls on the same line
        dedup, seen = [], set()
        for s in seq:
            k = (s["line"], s["call"])
            if k in seen:
                continue
            seen.add(k)
            dedup.append(s)
        result[fn.name] = dedup

    (OUT / "_tooling" / "raw_execution_order.json").write_text(
        json.dumps(result, indent=1), encoding="utf-8")

    for fname, seq in result.items():
        print(f"\n=== {fname} ({len(seq)} calls) ===")
        for s in seq:
            sc = f"  scripts={s['scripts']}" if s["scripts"] else ""
            print(f"  L{s['line']:<6} {s['kind']:<10} {s['call']}{sc}")


if __name__ == "__main__":
    main()
