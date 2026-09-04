"""m01 - population flow: rows, unique tickers and duplicate tickers per artefact.

Claim (AVS-E2E-DATA-LOGIC-001 s11.1):
  1,527 / 1,481 / 1,248 / 1,248 / 1,248 / 31 / 201 / 201 rows,
  unique tickers equal to rows, duplicates zero in every artefact.

Read-only. Streams with csv to avoid loading 20 MB frames.
"""
import csv
import os
import sys
from collections import Counter

RUN = r"C:\Users\ACKVerissimo\AVSHUNTER-Intelligence\data\output\runs\20260831_010309"
RID = "20260831_010309"
csv.field_size_limit(2**31 - 1)

ORDER = [
    ("Discovery", os.path.join(RUN, "discovery", f"discovery_candidates_ultimate_{RID}.csv")),
    ("Vanguard", os.path.join(RUN, "vanguard", "vanguard_signals.csv")),
    ("Options Intelligence", os.path.join(RUN, "options", f"options_intelligence_{RID}.csv")),
    ("Execution", os.path.join(RUN, "execution", f"execution_v3_5_{RID}.csv")),
    ("EIL", os.path.join(RUN, "superbrain", f"eil_enriched_{RID}.csv")),
    ("Wall Break", os.path.join(RUN, "superbrain", f"wall_break_scores_{RID}.csv")),
    ("Morning candidates", os.path.join(RUN, "morning_validation", f"morning_candidates_{RID}.csv")),
    ("Final Lab book", os.path.join(RUN, "intelligence_lab", f"final_opportunity_book_{RID}.csv")),
]

TICKER_CANDIDATES = ("ticker", "symbol", "Ticker", "Symbol", "underlying", "underlying_symbol")

print(f"{'artefact':<22} {'rows':>6} {'ticker_col':<12} {'unique':>7} {'dup_rows':>9} {'dup_tickers':>12}")
for label, path in ORDER:
    if not os.path.exists(path):
        print(f"{label:<22} FILE MISSING: {path}")
        continue
    with open(path, "r", encoding="utf-8", newline="") as fh:
        rdr = csv.reader(fh)
        hdr = next(rdr)
        tcol = next((c for c in TICKER_CANDIDATES if c in hdr), None)
        if tcol is None:
            print(f"{label:<22} NO TICKER COLUMN among {TICKER_CANDIDATES}")
            continue
        idx = hdr.index(tcol)
        rows = 0
        cnt = Counter()
        for r in rdr:
            rows += 1
            if idx < len(r):
                cnt[r[idx]] += 1
    uniq = len(cnt)
    dup_tickers = sum(1 for v in cnt.values() if v > 1)
    dup_rows = sum(v - 1 for v in cnt.values() if v > 1)
    print(f"{label:<22} {rows:>6} {tcol:<12} {uniq:>7} {dup_rows:>9} {dup_tickers:>12}")
