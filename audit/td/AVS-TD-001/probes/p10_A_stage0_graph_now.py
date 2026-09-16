"""p10_A_stage0_graph_now.py -- Track A / A7: call the Stage 0 gate's own read-only import_graph() at HEAD (cc509cb)
with its DEFAULT_ENTRYPOINTS; compare to STAGE0_BASELINE_MANIFEST (cfa1a25) and to p10_A_import_graph 6-root walk.
No manifest is written. Output: probes/p10_A_stage0_graph_now_out.json"""
import json, os, sys
ROOT = r"C:\Users\ACKVerissimo\AVSHUNTER-Intelligence"; sys.path.insert(0, ROOT); os.chdir(ROOT)
from pathlib import Path
import tools.avs_fix_002_stage0 as s0
g = s0.import_graph(Path(ROOT), s0.DEFAULT_ENTRYPOINTS)
man = json.load(open(os.path.join(ROOT, "audit", "avs_fix_002", "stage0", "STAGE0_BASELINE_MANIFEST.json"), encoding="utf-8-sig"))["import_graph"]
mine = json.load(open(os.path.join(ROOT, "audit", "td", "AVS-TD-001", "probes", "p10_A_import_graph_out.json"), encoding="utf-8"))["stage0_six_roots"]["modules"]
now_nodes = {n["path"] if isinstance(n, dict) else str(n) for n in g["nodes"]}
man_nodes = {n["path"] for n in man["nodes"]}
out = {"head_entrypoints": list(g["entrypoints"]), "head_node_count": g.get("node_count", len(now_nodes)), "head_edge_count": g.get("edge_count"),
       "head_untracked": g["untracked_reachable_dependencies"], "head_missing_entrypoints": g["missing_entrypoints"], "head_passed": g["passed"],
       "manifest_node_count": man["node_count"], "manifest_edge_count": man["edge_count"],
       "head_minus_manifest": sorted(now_nodes - man_nodes), "manifest_minus_head": sorted(man_nodes - now_nodes),
       "tester6_minus_head": sorted(set(mine) - now_nodes), "head_minus_tester6": sorted(now_nodes - set(mine))}
json.dump(out, open(os.path.join(ROOT, "audit", "td", "AVS-TD-001", "probes", "p10_A_stage0_graph_now_out.json"), "w", encoding="utf-8"), indent=1)
print(json.dumps({k: (v if not isinstance(v, list) or len(v) < 8 else f"{len(v)} items") for k, v in out.items()}, indent=1))
