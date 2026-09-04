"""m10 - options asof_date versus selected contract quote timestamps.

Claim (s11.8):
  Options asof_date: 31 August 2026;
  selected quote timestamps: completed Friday, 28 August 2026.

Also reports thesis_id date components, for the DB comparison in m13.

Read-only.
"""
import csv
import os
from collections import Counter

RUN = r"C:\Users\ACKVerissimo\AVSHUNTER-Intelligence\data\output\runs\20260831_010309"
RID = "20260831_010309"
OPT = os.path.join(RUN, "options", f"options_intelligence_{RID}.csv")
csv.field_size_limit(2**31 - 1)

COLS = ("ticker", "asof_date", "quote_as_of", "contract_quote_timestamp_utc",
        "quote_timestamp_utc", "thesis_id", "contract_quote_timestamp_source",
        "contract_symbol", "contract_expiry")

with open(OPT, "r", encoding="utf-8", newline="") as fh:
    rdr = csv.reader(fh)
    hdr = next(rdr)
    absent = [c for c in COLS if c not in hdr]
    idx = {c: hdr.index(c) for c in COLS if c in hdr}
    rows = [r for r in rdr]

print(f"options rows = {len(rows)}; absent columns = {absent}")
for c in ("asof_date", "quote_as_of", "contract_quote_timestamp_source"):
    if c in idx:
        print(f"\n{c}:")
        for k, v in Counter(r[idx[c]] for r in rows).most_common(8):
            print(f"  {k!r}: {v}")

for c in ("contract_quote_timestamp_utc", "quote_timestamp_utc"):
    if c in idx:
        print(f"\n{c} (date part only):")
        for k, v in Counter((r[idx[c]] or "")[:10] for r in rows).most_common(8):
            print(f"  {k!r}: {v}")
        sample = [r[idx[c]] for r in rows if r[idx[c]]][:3]
        print(f"  sample full values: {sample}")

if "thesis_id" in idx:
    print("\nthesis_id samples:")
    for r in rows[:5]:
        print(f"  {r[idx['thesis_id']]!r}")
    tail = Counter((r[idx["thesis_id"]] or "").split(":")[-1] for r in rows)
    print("thesis_id trailing component:")
    for k, v in tail.most_common(8):
        print(f"  {k!r}: {v}")
