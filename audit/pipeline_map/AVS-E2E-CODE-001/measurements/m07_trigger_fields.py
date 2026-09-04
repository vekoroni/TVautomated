"""m07 - trigger field state at the EOD candidate boundary and in EIL.

Claims (s11.2 / s11.5):
  trigger_quality is null for all 201 morning-candidate rows;
  trigger_primary is null at that boundary;
  legacy trigger_score remains 55.0 for 191 rows;
  EIL has 61 STRONG / 92 SINGLE / 48 NONE for the 201 final tickers.

Reports the EIL trigger_quality distribution BOTH over all 1,248 EIL rows and
over the 201-ticker final subset, since the claim does not state its denominator.

Read-only.
"""
import csv
import os
from collections import Counter

RUN = r"C:\Users\ACKVerissimo\AVSHUNTER-Intelligence\data\output\runs\20260831_010309"
RID = "20260831_010309"
MORN = os.path.join(RUN, "morning_validation", f"morning_candidates_{RID}.csv")
EIL = os.path.join(RUN, "superbrain", f"eil_enriched_{RID}.csv")
BOOK = os.path.join(RUN, "intelligence_lab", f"final_opportunity_book_{RID}.csv")
csv.field_size_limit(2**31 - 1)

NULLS = {"", "nan", "NaN", "None", "NULL", "null"}


def load(path, cols):
    with open(path, "r", encoding="utf-8", newline="") as fh:
        rdr = csv.reader(fh)
        hdr = next(rdr)
        absent = [c for c in cols if c not in hdr]
        idx = {c: hdr.index(c) for c in cols if c in hdr}
        return hdr, idx, absent, [r for r in rdr]


TRIG = ["trigger_quality", "trigger_primary", "trigger_score", "trigger_count",
        "trigger_evidence", "trigger_state"]

hdr, idx, absent, rows = load(MORN, TRIG + ["ticker"])
print(f"morning_candidates rows = {len(rows)}; absent columns = {absent}")
for c in TRIG:
    if c not in idx:
        continue
    vals = Counter(r[idx[c]] for r in rows)
    nulls = sum(v for k, v in vals.items() if k in NULLS)
    print(f"  {c}: null/blank {nulls}/{len(rows)}; top values: "
          + ", ".join(f"{k!r}={v}" for k, v in vals.most_common(5)))

# 55.0 count specifically
if "trigger_score" in idx:
    def is55(v):
        try:
            return float(v) == 55.0
        except (TypeError, ValueError):
            return False
    n55 = sum(1 for r in rows if is55(r[idx["trigger_score"]]))
    print(f"  trigger_score == 55.0 : {n55} of {len(rows)}")

# EIL
ehdr, eidx, eabsent, erows = load(EIL, TRIG + ["ticker"])
print(f"\neil_enriched rows = {len(erows)}; absent columns = {eabsent}")
bhdr, bidx, babsent, brows = load(BOOK, ["ticker"])
final_tickers = {r[bidx["ticker"]] for r in brows}
print(f"final book tickers = {len(final_tickers)}")

if "trigger_quality" in eidx:
    all_dist = Counter(r[eidx["trigger_quality"]] for r in erows)
    sub_dist = Counter(r[eidx["trigger_quality"]] for r in erows
                       if r[eidx["ticker"]] in final_tickers)
    print(f"\nEIL trigger_quality over ALL {len(erows)} rows:")
    for k, v in all_dist.most_common():
        print(f"  {k!r}: {v}")
    print(f"\nEIL trigger_quality over the {sum(sub_dist.values())} final-ticker rows:")
    for k, v in sub_dist.most_common():
        print(f"  {k!r}: {v}")

if "trigger_score" in eidx:
    sub = [r for r in erows if r[eidx["ticker"]] in final_tickers]
    def f(v):
        try:
            return float(v)
        except (TypeError, ValueError):
            return None
    print(f"\nEIL trigger_score == 55.0 over final-ticker subset: "
          f"{sum(1 for r in sub if f(r[eidx['trigger_score']]) == 55.0)} of {len(sub)}")
