"""AVS-OPS-001 - the two reference checks from section 1, for one or many candidates.
Check A: inbound edge in the reachability graph (audit/ops/AVS-OPS-001/usage_graph_20260904.json)
Check B: git grep for the module stem across *.py *.ps1 *.bat *.json *.toml *.cfg *.ini *.md,
         excluding the file itself, _attic/, backups/, audit/, Archive/.
A candidate moves only when BOTH are clean.
"""
import json, pathlib, subprocess, sys, re, csv

ROOT = pathlib.Path(".").resolve()
G = json.loads((ROOT / "audit/ops/AVS-OPS-001/usage_graph_20260904.json").read_text(encoding="utf-8"))
INBOUND = G["inbound"]; REACHABLE = set(G["reachable"]); NODES = set(G["graph"])

EXCLUDE_PREFIX = ("_attic/", "backups/", "audit/", "Archive/", "archive/",
                  "_cleanup_holding/", "venv/", ".git/")
GLOBS = ["*.py", "*.ps1", "*.bat", "*.json", "*.toml", "*.cfg", "*.ini", "*.md", "*.sh"]

def git_grep(term):
    cmd = ["git", "grep", "-n", "--no-color", "-I", "-F", "--", term] + \
          [f":(glob){g}" for g in GLOBS] + [f":(glob,exclude){g}" for g in
                                            ["_attic/**", "backups/**", "audit/**",
                                             "Archive/**", "archive/**", "_cleanup_holding/**"]]
    p = subprocess.run(cmd, capture_output=True, text=True, errors="replace", cwd=str(ROOT))
    # git grep exits 1 on no match
    return [l for l in p.stdout.splitlines() if l.strip()]

def check(relpath):
    rel = relpath.replace("\\", "/")
    p = pathlib.Path(rel)
    stem = p.stem
    graph_inbound = sorted(set(INBOUND.get(rel, [])) - {rel})
    graph_inbound = [g for g in graph_inbound if not g.startswith(EXCLUDE_PREFIX)]
    in_reachable = rel in REACHABLE
    hits = []
    if stem:
        for line in git_grep(stem):
            fpath = line.split(":", 1)[0].replace("\\", "/")
            if fpath == rel:
                continue
            if fpath.startswith(EXCLUDE_PREFIX):
                continue
            hits.append(line)
    strict = []
    for line in git_grep(p.name):
        fpath = line.split(":", 1)[0].replace("\\", "/")
        if fpath == rel or fpath.startswith(EXCLUDE_PREFIX):
            continue
        strict.append(line)
    return {
        "path": rel,
        "grep_strict_n": len(strict),
        "grep_strict": strict,
        "in_graph": rel in NODES,
        "graph_reachable": in_reachable,
        "graph_inbound_n": len(graph_inbound),
        "graph_inbound": graph_inbound,
        "grep_hits_n": len(hits),
        "grep_hits": hits,
        "clean": (len(graph_inbound) == 0 and len(hits) == 0 and not in_reachable),
    }

if __name__ == "__main__":
    targets = sys.argv[1:]
    out = [check(t) for t in targets]
    for r in out:
        print(f"{r['path']:46s} reach={str(r['graph_reachable']):5s} "
              f"in={r['graph_inbound_n']:2d} grep={r['grep_hits_n']:3d} "
              f"CLEAN={r['clean']}")
        for g in r["graph_inbound"][:4]:
            print(f"      graph<- {g}")
        for h in r["grep_hits"][:6]:
            print(f"      grep  : {h[:150]}")
    (ROOT / "audit/ops/AVS-OPS-001/_refcheck_last.json").write_text(
        json.dumps(out, indent=1), encoding="utf-8")
