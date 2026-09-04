"""m08 - selected contract and two-sided completed-session quote counts in the
final 201-row book.

Claims (s11.2):
  191 of 201 rows have a selected contract;
  175 have positive two-sided completed-session quotes.

"Two-sided positive" is taken as contract_bid > 0 and contract_ask > 0 on the
selected (EOD, completed-session) contract quote.

Read-only.
"""
import csv
import os
from collections import Counter

RUN = r"C:\Users\ACKVerissimo\AVSHUNTER-Intelligence\data\output\runs\20260831_010309"
RID = "20260831_010309"
BOOK = os.path.join(RUN, "intelligence_lab", f"final_opportunity_book_{RID}.csv")
csv.field_size_limit(2**31 - 1)

NULLS = {"", "nan", "NaN", "None", "NULL", "null"}
COLS = ("contract_symbol", "contract_bid", "contract_ask", "contract_mid",
        "selected_quote_timestamp_utc", "contract_data_state", "canonical_direction")


def num(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f == f else None


with open(BOOK, "r", encoding="utf-8", newline="") as fh:
    rdr = csv.reader(fh)
    hdr = next(rdr)
    absent = [c for c in COLS if c not in hdr]
    idx = {c: hdr.index(c) for c in COLS if c in hdr}
    rows = [r for r in rdr]

n = len(rows)
print(f"final book rows = {n}; absent columns = {absent}")

has_contract = [r for r in rows if r[idx["contract_symbol"]] not in NULLS]
print(f"contract_symbol populated: {len(has_contract)} of {n}")

two_sided = [r for r in rows
             if (num(r[idx['contract_bid']]) or 0) > 0 and (num(r[idx['contract_ask']]) or 0) > 0]
print(f"contract_bid > 0 AND contract_ask > 0: {len(two_sided)} of {n}")

both = [r for r in has_contract
        if (num(r[idx['contract_bid']]) or 0) > 0 and (num(r[idx['contract_ask']]) or 0) > 0]
print(f"selected contract AND two-sided positive: {len(both)} of {n}")

print("\ncontract_data_state distribution:")
for k, v in Counter(r[idx["contract_data_state"]] for r in rows).most_common():
    print(f"  {k!r}: {v}")

ts = Counter((r[idx["selected_quote_timestamp_utc"]] or "")[:10] for r in rows)
print("\nselected_quote_timestamp_utc, date part:")
for k, v in ts.most_common():
    print(f"  {k!r}: {v}")
