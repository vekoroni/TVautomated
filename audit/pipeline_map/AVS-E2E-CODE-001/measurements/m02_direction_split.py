"""m02 - direction split in the final 201-row Intelligence Lab book.

Claim (s11.2): "Direction population is 111 PUT / 90 CALL in the final 201-row book."

Reports the value distribution of EVERY direction-ish / contract-side column in the
book, and flags which (if any) yields 111 PUT / 90 CALL.

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

PAT = re.compile(r"(direction|contract_type|option_type|_side$|^side$|put_call|call_put)", re.I)
SKIP = re.compile(r"(json|sha256|policy_version|_score$|_confidence$|_margin$|_count$|_pct$|_share$)", re.I)

with open(BOOK, "r", encoding="utf-8", newline="") as fh:
    rdr = csv.reader(fh)
    hdr = next(rdr)
    cols = [c for c in hdr if PAT.search(c) and not SKIP.search(c)]
    idxs = {c: hdr.index(c) for c in cols}
    counters = {c: Counter() for c in cols}
    total = 0
    for r in rdr:
        total += 1
        for c, i in idxs.items():
            counters[c][r[i] if i < len(r) else "<SHORT_ROW>"] += 1

print(f"final_opportunity_book rows = {total}")
print(f"direction-ish columns found = {len(cols)}\n")
hits = []
for c in cols:
    cnt = counters[c]
    put = cnt.get("PUT", 0) + cnt.get("put", 0)
    call = cnt.get("CALL", 0) + cnt.get("call", 0)
    items = ", ".join(f"{k!r}={v}" for k, v in cnt.most_common(8))
    extra = "" if len(cnt) <= 8 else f" (+{len(cnt)-8} more values)"
    flag = "  <<< 111/90 MATCH" if (put, call) == (111, 90) else ""
    print(f"{c}: PUT={put} CALL={call}{flag}")
    print(f"    values: {items}{extra}")
    if (put, call) == (111, 90):
        hits.append(c)

print("\ncolumns yielding exactly 111 PUT / 90 CALL:", hits if hits else "NONE")
