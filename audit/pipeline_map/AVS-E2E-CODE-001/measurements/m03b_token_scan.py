"""m03b - locate which columns of options_intelligence carry the tokens
'UNSUITABLE' and 'INVALIDAT' anywhere in their values. Used to identify the
lifecycle columns referenced by s11.3 and s11.4 without guessing.

Read-only.
"""
import csv
import os
from collections import Counter

RUN = r"C:\Users\ACKVerissimo\AVSHUNTER-Intelligence\data\output\runs\20260831_010309"
RID = "20260831_010309"
OPT = os.path.join(RUN, "options", f"options_intelligence_{RID}.csv")
csv.field_size_limit(2**31 - 1)

with open(OPT, "r", encoding="utf-8", newline="") as fh:
    rdr = csv.reader(fh)
    hdr = next(rdr)
    n = len(hdr)
    cnt = [Counter() for _ in range(n)]
    rows = 0
    for r in rdr:
        rows += 1
        for i in range(min(n, len(r))):
            v = r[i]
            if "UNSUITABLE" in v or "INVALIDAT" in v.upper():
                cnt[i][v] += 1

print(f"rows = {rows}")
for i in range(n):
    if cnt[i]:
        print(hdr[i], dict(cnt[i].most_common(6)))
