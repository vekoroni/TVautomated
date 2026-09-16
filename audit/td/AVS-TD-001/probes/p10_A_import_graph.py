"""p10_A_import_graph.py -- Track A / A7 (REQ-WP0-07/08 production import graph, tracked check).
Read-only static `ast` import walk from intelligent_orchestrator.py, orchestrator/dynamic_dispatcher.py,
morning_gate.py, build_macro_json.py (recursive over local modules). Every resolved module is checked with
`git ls-files --error-unmatch`. Reports module/edge counts, untracked modules, unresolved local-looking
imports, quarantined-path hits, and whether scripts/release_baseline.py implements the gate / names
scripts/actuarial_cache_builder.py.
Output: probes/p10_A_import_graph_out.json (and stdout)
"""
import ast, os, re, sys, json, subprocess

ROOT = r"C:\Users\ACKVerissimo\AVSHUNTER-Intelligence"
OUT = os.path.join(ROOT, "audit", "td", "AVS-TD-001", "probes", "p10_A_import_graph_out.json")
ROOTS = ["intelligent_orchestrator.py", "orchestrator/dynamic_dispatcher.py", "morning_gate.py", "build_macro_json.py"]
# Stage 0's own six entry points (audit/avs_fix_002/stage0/STAGE0_BASELINE_MANIFEST.json import_graph.entrypoints)
STAGE0_ROOTS = ["intelligent_orchestrator.py", "morning_gate.py", "scripts/avshunter_options_intelligence.py",
                "intelligence-lab/intelligence_lab.py", "pipeline_interpreter/pipeline_interpreter.py", "worker3/integration/runner.py"]
STAGE0_MANIFEST = os.path.join(ROOT, "audit", "avs_fix_002", "stage0", "STAGE0_BASELINE_MANIFEST.json")
QUAR_RE = re.compile(r"(^|/)(quarantine|tmp|pip-|avs_macro_check_|\.codex|\.bak|_backup|_old|\d{8}_)", re.I)


def resolve(modname, from_file, level=0):
    """Return absolute path of a local module or None. Tries repo root, then the importing file's dir
    (covers sys.path.insert(dirname) idioms), then common src dirs."""
    bases = [ROOT, os.path.dirname(from_file), os.path.join(ROOT, "scripts"), os.path.join(ROOT, "intelligence-lab"), os.path.join(ROOT, "worker3")]
    if level:
        base = os.path.dirname(from_file)
        for _ in range(level - 1):
            base = os.path.dirname(base)
        bases = [base]
    parts = modname.split(".") if modname else []
    for b in bases:
        for n in range(len(parts), 0, -1):
            p = os.path.join(b, *parts[:n])
            for cand in (p + ".py", os.path.join(p, "__init__.py")):
                if os.path.isfile(cand):
                    return os.path.normpath(cand)
        if level and not parts:
            c = os.path.join(b, "__init__.py")
            if os.path.isfile(c):
                return os.path.normpath(c)
    return None


def imports_of(path):
    try:
        # utf-8-sig: several production modules carry a BOM (U+FEFF) and ast.parse rejects it otherwise
        tree = ast.parse(open(path, encoding="utf-8-sig", errors="replace").read(), filename=path)
    except SyntaxError as e:
        return [], f"SyntaxError: {e}"
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                out.append((a.name, 0, None))
        elif isinstance(node, ast.ImportFrom):
            out.append((node.module or "", node.level, [a.name for a in node.names]))
    return out, None


def walk(roots):
    seen = {}
    edges = set()
    unresolved = {}
    stack = [os.path.normpath(os.path.join(ROOT, r)) for r in roots if os.path.isfile(os.path.join(ROOT, r))]
    missing_roots = [r for r in roots if not os.path.isfile(os.path.join(ROOT, r))]
    while stack:
        f = stack.pop()
        if f in seen:
            continue
        imps, err = imports_of(f)
        seen[f] = err
        for mod, level, names in imps:
            tgt = resolve(mod, f, level)
            if tgt is None and names and level == 0 and mod:
                # `from pkg import submodule` where submodule is a module
                for n in names:
                    t2 = resolve(mod + "." + n, f, 0)
                    if t2:
                        edges.add((f, t2)); stack.append(t2)
                continue
            if tgt is None and names and level:
                for n in names:
                    t2 = resolve((mod + "." if mod else "") + n, f, level)
                    if t2:
                        edges.add((f, t2)); stack.append(t2)
                continue
            if tgt is None:
                top = (mod.split(".")[0] if mod else "")
                # local-looking: a directory or .py of that name exists at root but resolution failed
                if top and (os.path.isdir(os.path.join(ROOT, top)) or os.path.isfile(os.path.join(ROOT, top + ".py"))):
                    unresolved.setdefault(os.path.relpath(f, ROOT), []).append(mod)
                continue
            edges.add((f, tgt))
            if tgt not in seen:
                stack.append(tgt)
            # `from pkg import name` where name is a submodule under a package __init__
            if names and tgt.endswith("__init__.py"):
                for n in names:
                    t2 = resolve(mod + "." + n, f, level) if mod else resolve(n, f, level)
                    if t2 and t2 != tgt:
                        edges.add((f, t2)); stack.append(t2)
    mods = sorted(os.path.relpath(m, ROOT).replace("\\", "/") for m in seen)
    # git tracked check
    untracked = []
    for m in mods:
        r = subprocess.run(["git", "ls-files", "--error-unmatch", m], cwd=ROOT, capture_output=True, text=True)
        if r.returncode != 0:
            untracked.append(m)
    quarantined = [m for m in mods if QUAR_RE.search(m)]
    syntax_err = {os.path.relpath(k, ROOT): v for k, v in seen.items() if v}
    return {"roots": roots, "missing_roots": missing_roots, "n_modules": len(mods), "n_edges": len(edges), "untracked": untracked,
            "quarantined_path_hits": quarantined, "syntax_errors": syntax_err, "unresolved_local_looking": unresolved, "modules": mods,
            "edges": sorted(f"{os.path.relpath(a, ROOT)} -> {os.path.relpath(b, ROOT)}".replace("\\", "/") for a, b in edges)}


def main():
    g4 = walk(ROOTS)
    g6 = walk(STAGE0_ROOTS)
    mods, untracked, quarantined, syntax_err, unresolved, missing_roots = g4["modules"], g4["untracked"], g4["quarantined_path_hits"], g4["syntax_errors"], g4["unresolved_local_looking"], g4["missing_roots"]
    edges = g4["edges"]
    # compare six-root graph to Stage 0 manifest
    stage0 = {}
    if os.path.isfile(STAGE0_MANIFEST):
        man = json.load(open(STAGE0_MANIFEST, encoding="utf-8-sig"))
        ig = man.get("import_graph") or {}
        man_nodes = sorted(n["path"] for n in ig.get("nodes", []))
        stage0 = {"entrypoints": ig.get("entrypoints"), "node_count": ig.get("node_count"), "edge_count": ig.get("edge_count"),
                  "manifest_untracked_nodes": [n["path"] for n in ig.get("nodes", []) if not n.get("tracked", True)],
                  "my6_minus_manifest": sorted(set(g6["modules"]) - set(man_nodes)),
                  "manifest_minus_my6": sorted(set(man_nodes) - set(g6["modules"]))}
    # release_baseline.py checks
    rb = os.path.join(ROOT, "scripts", "release_baseline.py")
    rb_info = {"exists": os.path.isfile(rb)}
    if rb_info["exists"]:
        src = open(rb, encoding="utf-8", errors="replace").read().splitlines()
        rb_info["lines"] = len(src)
        rb_info["import_graph_hits"] = [f"{i}: {l.strip()[:150]}" for i, l in enumerate(src, 1) if re.search(r"import.graph|import_graph|ls-files|error-unmatch|untracked|ast\.|walk_imports|production_modules|manifest|sha256|dynamic_dispatcher|intelligent_orchestrator", l, re.I)]
        rb_info["actuarial_cache_builder_hits"] = [f"{i}: {l.strip()[:150]}" for i, l in enumerate(src, 1) if "actuarial_cache_builder" in l]
        rb_info["defs"] = [f"{i}: {l.strip()[:100]}" for i, l in enumerate(src, 1) if re.match(r"\s*def ", l)]
    # dangling reference repo-wide (excluding audit/, tests)
    dangling = subprocess.run(["git", "grep", "-n", "actuarial_cache_builder", "--", ":!audit/*", ":!*.md"], cwd=ROOT, capture_output=True, text=True).stdout.splitlines()
    acb_exists = os.path.isfile(os.path.join(ROOT, "scripts", "actuarial_cache_builder.py"))
    # quarantine manifest
    qman = subprocess.run(["git", "ls-files", "--", "*quarantine*", "*QUARANTINE*"], cwd=ROOT, capture_output=True, text=True).stdout.splitlines()
    out = {"roots": ROOTS, "missing_roots": missing_roots, "n_modules": len(mods), "n_edges": len(edges), "untracked": untracked,
           "quarantined_path_hits": quarantined, "syntax_errors": syntax_err, "unresolved_local_looking": unresolved,
           "release_baseline": rb_info, "actuarial_cache_builder_exists": acb_exists, "actuarial_cache_builder_refs": dangling,
           "quarantine_tracked_files": qman, "modules": mods, "edges": edges,
           "stage0_six_roots": {k: v for k, v in g6.items() if k != "edges"}, "stage0_manifest_compare": stage0}
    print("4-root graph: modules", len(mods), "edges", len(edges), "untracked", untracked, "quarantined", quarantined, "missing_roots", missing_roots)
    print("6-root (Stage 0) graph: modules", g6["n_modules"], "edges", g6["n_edges"], "untracked", g6["untracked"], "quarantined", g6["quarantined_path_hits"], "missing_roots", g6["missing_roots"], "syntax", g6["syntax_errors"])
    print("stage0 manifest compare:", json.dumps(stage0, indent=1)[:2500])
    print("syntax errors", syntax_err)
    print("unresolved local-looking", json.dumps(unresolved, indent=1)[:2000])
    print("release_baseline:", json.dumps(rb_info, indent=1)[:3000])
    print("actuarial_cache_builder exists:", acb_exists, "refs:", dangling)
    print("quarantine tracked files:", qman[:30])
    print("top-level dirs in graph:", sorted({m.split('/')[0] for m in mods}))
    json.dump(out, open(OUT, "w", encoding="utf-8"), indent=1)
    print("wrote", OUT)


if __name__ == "__main__":
    main()
