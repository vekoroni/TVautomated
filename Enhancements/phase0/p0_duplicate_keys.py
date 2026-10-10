"""Phase 0: find dict literals that write the same key twice (the later value silently wins).

A duplicated key in an output record means two producers for one field, with the first one
discarded without trace. Read-only static scan of the decision-path modules.
"""
import ast
import collections
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
GLOBS = ["*.py", "scripts/*.py", "contracts/*.py", "domain/**/*.py", "canonical_data/*.py", "vanguard/*.py",
         "vanguard/layer*/*.py", "avshunter/**/*.py"]
out = []
for g in GLOBS:
    for p in sorted(ROOT.glob(g)):
        try:
            tree = ast.parse(p.read_text(encoding="utf-8-sig", errors="ignore"))
        except SyntaxError:
            continue
        for n in ast.walk(tree):
            if isinstance(n, ast.Dict):
                ks = [k.value for k in n.keys if isinstance(k, ast.Constant) and isinstance(k.value, str)]
                dup = sorted(k for k, c in collections.Counter(ks).items() if c > 1)
                if dup:
                    out.append({"file": str(p.relative_to(ROOT)), "line": n.lineno, "keys": dup})
json.dump(out, open(pathlib.Path(__file__).with_suffix(".json"), "w"), indent=1)
for o in out:
    print(f"{o['file']}:{o['line']} {o['keys']}")
print("total", len(out), file=sys.stderr)
