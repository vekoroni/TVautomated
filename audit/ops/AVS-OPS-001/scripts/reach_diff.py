"""AVS-OPS-001 verification item 6 - reachability diff.
The set of modules reachable from the four entry points must be IDENTICAL
before and after the move. Paths that moved into _attic/ are compared on their
original path, because a move must not change reachability.
Usage: reach_diff.py <before.json> <after.json> <out.txt>
"""
import json, pathlib, sys

before = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
after = json.loads(pathlib.Path(sys.argv[2]).read_text(encoding="utf-8"))
out = pathlib.Path(sys.argv[3])

def norm(paths):
    """_attic/X is the same module as X for reachability purposes."""
    s = set()
    for p in paths:
        s.add(p[len("_attic/"):] if p.startswith("_attic/") else p)
    return s

b, a = norm(before["reachable"]), norm(after["reachable"])
lost, gained = sorted(b - a), sorted(a - b)

lines = [
    "AVS-OPS-001 verification item 6 - reachability diff",
    f"before: {sys.argv[1]}  head={before.get('baseline_head','')[:12]}"
    f"  nodes={before['node_count']} reachable={before['reachable_count']}",
    f"after : {sys.argv[2]}  head={after.get('baseline_head','')[:12]}"
    f"  nodes={after['node_count']} reachable={after['reachable_count']}",
    f"entry points before: {len(before['entry_points'])}  after: {len(after['entry_points'])}",
    "",
    f"reachable set (normalised, _attic/ prefix stripped): before={len(b)} after={len(a)}",
    f"LOST   (reachable before, not after): {len(lost)}",
    f"GAINED (reachable after, not before): {len(gained)}",
    "",
]
for p in lost:
    lines.append(f"  LOST   {p}")
for p in gained:
    lines.append(f"  GAINED {p}")
if not lost and not gained:
    lines.append("EMPTY DIFF - reachability is identical. Item 6 PASS.")
else:
    lines.append("NON-EMPTY DIFF - item 6 FAIL. Revert commit 2.")

pe_b, pe_a = set(before.get("parse_errors", {})), set(after.get("parse_errors", {}))
lines += ["", f"parse errors before={len(pe_b)} after={len(pe_a)}"]
for p in sorted(pe_a - pe_b):
    lines.append(f"  NEW PARSE ERROR {p}")

out.write_text("\n".join(lines) + "\n", encoding="utf-8")
print("\n".join(lines[:12]))
print(f"...written to {out}")
sys.exit(0 if (not lost and not gained and not (pe_a - pe_b)) else 1)
