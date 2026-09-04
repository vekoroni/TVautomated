"""AVS-OPS-001 - static reachability graph. Parses only; never imports target modules."""
import ast, json, os, sys, re, pathlib

ROOT = pathlib.Path(".").resolve()
SKIP_DIRS = {".git", "venv", ".venv", "node_modules", "__pycache__", "data", "backups",
             "dropbox", ".pytest_cache", ".mypy_cache", "_attic", "Archive", "archive",
             ".codex_py312_testenv", ".codex_python313_runtime", ".codex_test_runtime",
             ".codex_test_temp", ".codex_test_tmp", "pytest-of-ACKVerissimo",
             "_cleanup_holding", "reports", "logs"}

def py_files():
    out = []
    for dp, dn, fn in os.walk(ROOT):
        dn[:] = [d for d in dn if d not in SKIP_DIRS and not d.startswith("tmp")
                 and not d.startswith("pip-") and not d.startswith("avs_macro_check_")]
        for f in fn:
            if f.endswith(".py"):
                out.append(pathlib.Path(dp, f).resolve().relative_to(ROOT))
    return sorted(out, key=lambda p: str(p))

FILES = py_files()
BY_POSIX = {p.as_posix(): p for p in FILES}
# module-name -> candidate files (dotted package path and bare stem)
MODMAP = {}
for p in FILES:
    parts = list(p.parts)
    stem = p.stem
    MODMAP.setdefault(stem, set()).add(p)
    dotted = ".".join(parts[:-1] + [stem]) if len(parts) > 1 else stem
    MODMAP.setdefault(dotted, set()).add(p)
    if stem == "__init__" and len(parts) > 1:
        MODMAP.setdefault(".".join(parts[:-1]), set()).add(p)
        MODMAP.setdefault(parts[-2], set()).add(p)

def parse(p):
    try:
        src = (ROOT / p).read_text(encoding="utf-8-sig", errors="replace")
    except OSError as e:
        return None, f"io:{e}"
    try:
        return ast.parse(src), None
    except SyntaxError as e:
        return None, f"syntax:{e.msg} (line {e.lineno})"

STR_PY = re.compile(r"['\"]([^'\" ]+[.]py)['\"]")

def edges_from(p):
    """Return (import_targets, stringref_targets, error)."""
    tree, err = parse(p)
    imports, strefs = set(), set()
    if tree is None:
        # still scan raw text for .py string references
        try:
            src = (ROOT / p).read_text(encoding="utf-8-sig", errors="replace")
            for m in STR_PY.finditer(src):
                strefs.add(m.group(1))
        except OSError:
            pass
        return imports, strefs, err
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                imports.add(a.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level and node.level > 0:
                base = list(p.parts[:-1])
                up = node.level - 1
                base = base[:len(base) - up] if up else base
                if node.module:
                    imports.add(".".join(base + node.module.split(".")))
                for a in node.names:
                    imports.add(".".join(base + ([node.module] if node.module else []) + [a.name]))
            elif node.module:
                imports.add(node.module)
                for a in node.names:
                    imports.add(f"{node.module}.{a.name}")
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            v = node.value
            if v.endswith(".py"):
                strefs.add(v)
    return imports, strefs, err

def resolve_import(name):
    hits = set()
    if name in MODMAP:
        hits |= MODMAP[name]
    parts = name.split(".")
    for i in range(len(parts), 0, -1):
        cand = ".".join(parts[:i])
        if cand in MODMAP:
            hits |= MODMAP[cand]
            break
    return hits

def resolve_stref(s):
    s = s.replace("\\", "/")
    base = s.rsplit("/", 1)[-1]
    hits = set()
    for p in FILES:
        if p.name == base:
            hits.add(p)
    return hits

GRAPH, ERRORS = {}, {}
for p in FILES:
    imp, sref, err = edges_from(p)
    if err:
        ERRORS[p.as_posix()] = err
    tgt = set()
    for n in imp:
        tgt |= resolve_import(n)
    for s in sref:
        tgt |= resolve_stref(s)
    tgt.discard(p)
    GRAPH[p.as_posix()] = sorted(t.as_posix() for t in tgt)

ENTRY = ["intelligent_orchestrator.py", "morning_gate.py",
         "intelligence-lab/intelligence_lab.py"]
ENTRY += [p.as_posix() for p in FILES if p.parts and p.parts[0] == "pipeline_interpreter"
          and len(p.parts) == 2]
ENTRY = [e for e in ENTRY if e in GRAPH]

seen, stack = set(), list(ENTRY)
while stack:
    cur = stack.pop()
    if cur in seen:
        continue
    seen.add(cur)
    stack.extend(GRAPH.get(cur, []))

inbound = {p: [] for p in GRAPH}
for src, tgts in GRAPH.items():
    for t in tgts:
        inbound.setdefault(t, []).append(src)

out = {
    "generated_utc": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
    "baseline_head": os.popen("git rev-parse HEAD").read().strip(),
    "method": "static ast.parse + .py string-literal references; modules are never imported",
    "entry_points": ENTRY,
    "node_count": len(GRAPH),
    "edge_count": sum(len(v) for v in GRAPH.values()),
    "reachable_count": len(seen),
    "reachable": sorted(seen),
    "unreachable": sorted(set(GRAPH) - seen),
    "inbound": {k: sorted(v) for k, v in sorted(inbound.items())},
    "graph": GRAPH,
    "parse_errors": ERRORS,
}
dest = sys.argv[1] if len(sys.argv) > 1 else "audit/ops/AVS-OPS-001/usage_graph_20260904.json"
pathlib.Path(dest).write_text(json.dumps(out, indent=1), encoding="utf-8")
print(f"nodes={out['node_count']} edges={out['edge_count']} "
      f"reachable={out['reachable_count']} unreachable={len(out['unreachable'])} "
      f"entry_points={len(ENTRY)} parse_errors={len(ERRORS)}")
for k, v in ERRORS.items():
    print(f"  PARSE_ERROR {k}: {v}")
