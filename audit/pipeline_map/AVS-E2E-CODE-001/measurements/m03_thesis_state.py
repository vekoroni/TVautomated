"""m03 - lifecycle state distributions in options_intelligence and their PUT/CALL splits.

Claims:
  s11.3: 442 Options rows classified THESIS_INVALIDATED, of which 437 PUT and 5 CALL.
  s11.4: 657 Options rows labelled DTE_UNSUITABLE.

The literal token THESIS_INVALIDATED lives in `remaining_runway_state`;
`thesis_state` carries the shorter token INVALIDATED. DTE_UNSUITABLE lives in
`liquidity_state`. Column identification was done by scanning every cell of every
column for the tokens (see m03b_token_scan.py).

Read-only.
"""
import csv
import os
from collections import Counter

RUN = r"C:\Users\ACKVerissimo\AVSHUNTER-Intelligence\data\output\runs\20260831_010309"
RID = "20260831_010309"
OPT = os.path.join(RUN, "options", f"options_intelligence_{RID}.csv")
csv.field_size_limit(2**31 - 1)

DIRCOLS = ["canonical_direction", "final_direction", "governed_direction", "options_direction", "side"]
STATECOLS = ["thesis_state", "remaining_runway_state", "liquidity_state"]

with open(OPT, "r", encoding="utf-8", newline="") as fh:
    rdr = csv.reader(fh)
    hdr = next(rdr)
    i_state = {c: hdr.index(c) for c in STATECOLS if c in hdr}
    i_dir = {c: hdr.index(c) for c in DIRCOLS if c in hdr}
    dist = {c: Counter() for c in i_state}
    cross = {c: {} for c in i_state}
    total = 0
    for r in rdr:
        total += 1
        for sc, si in i_state.items():
            st = r[si]
            dist[sc][st] += 1
            bucket = cross[sc].setdefault(st, {c: Counter() for c in i_dir})
            for dc, di in i_dir.items():
                bucket[dc][r[di]] += 1

print(f"options_intelligence rows = {total}")
for sc in i_state:
    print(f"\n=== {sc} distribution (denominator {total}) ===")
    for k, v in dist[sc].most_common():
        print(f"  {k!r}: {v}")

for sc, token in (("remaining_runway_state", "THESIS_INVALIDATED"),
                  ("thesis_state", "INVALIDATED"),
                  ("liquidity_state", "DTE_UNSUITABLE")):
    n = dist[sc].get(token, 0)
    print(f"\n--- {sc} == {token}: {n} of {total} ---")
    if not n:
        continue
    for dc in i_dir:
        cnt = cross[sc][token][dc]
        print(f"  by {dc}: " + ", ".join(f"{k!r}={v}" for k, v in cnt.most_common()))
