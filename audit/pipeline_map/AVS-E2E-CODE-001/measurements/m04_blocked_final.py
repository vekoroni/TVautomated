"""m04 - blocked rows in the final 201-row Intelligence Lab book and their direction.

Claim (s11.3): "106 of the final 201 Lab rows were blocked as invalidated; all 106 were PUTs."

Reports every status-ish column's distribution, and the direction split for any
value containing BLOCK, plus the cross-tab of thesis_state / remaining_runway_state
against canonical_direction.

Read-only.
"""
import csv
import os
import re
from collections import Counter

RUN = r"C:\Users\ACKVerissimo\AVSHUNTER-Intelligence\data\output\runs\20260831_010309"
RID = "20260831_010309"
BOOK = os.path.join(RUN, "intelligence_lab", f"final_opportunity_book_{RID}.csv")
csv.field_size_limit(2**31 - 1)

STATUSCOLS = ["lab_status", "lab_execution_status", "eod_candidate_status",
              "thesis_state", "remaining_runway_state", "liquidity_state",
              "monetisability_status", "gate_reason"]

with open(BOOK, "r", encoding="utf-8", newline="") as fh:
    rdr = csv.reader(fh)
    hdr = next(rdr)
    present = [c for c in STATUSCOLS if c in hdr]
    missing = [c for c in STATUSCOLS if c not in hdr]
    i_s = {c: hdr.index(c) for c in present}
    i_dir = hdr.index("canonical_direction")
    n = len(hdr)
    dist = {c: Counter() for c in present}
    cross = {c: {} for c in present}
    blockcols = [Counter() for _ in range(n)]
    total = 0
    for r in rdr:
        total += 1
        for c, i in i_s.items():
            dist[c][r[i]] += 1
            cross[c].setdefault(r[i], Counter())[r[i_dir]] += 1
        for i in range(min(n, len(r))):
            if "BLOCK" in r[i].upper():
                blockcols[i][r[i]] += 1

print(f"final_opportunity_book rows = {total}")
print(f"status columns absent from book: {missing}")
for c in present:
    print(f"\n=== {c} (denominator {total}) ===")
    for k, v in dist[c].most_common(12):
        dirs = ", ".join(f"{dk}={dv}" for dk, dv in cross[c][k].most_common())
        print(f"  {k!r}: {v}   [canonical_direction: {dirs}]")

print("\n=== columns containing the token BLOCK in any value (counts only) ===")
for i in range(n):
    if blockcols[i]:
        tot = sum(blockcols[i].values())
        print(f"  {hdr[i]}: {tot} rows, {len(blockcols[i])} distinct values")
