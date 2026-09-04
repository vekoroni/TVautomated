"""m00b - search the dumped headers for columns matching keyword patterns."""
import json
import os
import re
import sys

here = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(here, "m00_headers.json"), "r", encoding="utf-8") as fh:
    hdrs = json.load(fh)

pats = sys.argv[1:]
if not pats:
    pats = ["direction", "contract_type", "thesis", "invalidat", "runway", "dte",
            "trigger", "block", "asof", "quote", "session"]

for name, info in hdrs.items():
    if not info.get("exists"):
        continue
    for p in pats:
        hits = [c for c in info["columns"] if re.search(p, c, re.I)]
        if hits:
            print(f"[{name}] /{p}/ -> {hits}")
