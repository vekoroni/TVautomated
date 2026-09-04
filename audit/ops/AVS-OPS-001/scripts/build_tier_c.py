"""AVS-OPS-001 Tier C - root-level .py unreachable from the four entry points,
not already in Tier A or Tier B. LIST ONLY - nothing here is moved."""
import csv, json, os, pathlib, subprocess

ROOT = pathlib.Path(".").resolve()
G = json.loads(pathlib.Path("audit/ops/AVS-OPS-001/usage_graph_20260904.json").read_text(encoding="utf-8"))
REACH = set(G["reachable"]); INBOUND = G["inbound"]; NODES = set(G["graph"])
prior = {r["path"] for r in csv.DictReader(
    open("audit/ops/AVS-OPS-001/03_candidates.csv", encoding="utf-8"))}

def tracked(p):
    return subprocess.run(["git","ls-files","--error-unmatch",p],capture_output=True).returncode==0
def ignored(p):
    return subprocess.run(["git","check-ignore","-q",p],capture_output=True).returncode==0

rows=[]
for f in sorted(x for x in os.listdir(".") if x.endswith(".py") and os.path.isfile(x)):
    if f in prior:
        continue
    reachable = f in REACH
    inb = [g for g in INBOUND.get(f, []) if g != f]
    rows.append({
        "path": f,
        "in_graph": f in NODES,
        "graph_reachable": reachable,
        "graph_inbound": len(inb),
        "graph_inbound_refs": ";".join(sorted(inb)[:6]),
        "tracked": tracked(f),
        "gitignored": ignored(f),
        "size_bytes": os.path.getsize(f),
        "tier_c_status": ("REACHABLE_KEEP" if reachable else
                          ("UNREACHABLE_BUT_REFERENCED" if inb else "UNREACHABLE_NO_INBOUND")),
        "decision": "LIST_ONLY_NOT_MOVED",
    })
out = pathlib.Path("audit/ops/AVS-OPS-001/04_tier_c_candidates.csv")
with out.open("w", newline="", encoding="utf-8") as fh:
    w = csv.DictWriter(fh, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)

from collections import Counter
c = Counter(r["tier_c_status"] for r in rows)
print(f"root .py not in Tier A/B: {len(rows)}")
for k,v in c.most_common(): print(f"   {k}: {v}")
print("\nUNREACHABLE_NO_INBOUND (the post-MVP quarantine shortlist):")
for r in rows:
    if r["tier_c_status"]=="UNREACHABLE_NO_INBOUND":
        print(f"   {r['path']:46s} {r['size_bytes']:>8d} B  tracked={r['tracked']} ignored={r['gitignored']}")
