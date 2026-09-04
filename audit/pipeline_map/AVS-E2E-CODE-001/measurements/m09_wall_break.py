"""m09 - Wall Break Scorer population and its intersection with the final book.

Claims (s11.2 / s11.3 / s11.7):
  Wall Break produced 31 scored candidates;
  Wall Break 14 = intersection with the 201 final candidates;
  it removed 17 of the 31 Wall Break rows from the 201-row book;
  excluded PROBABLE candidates included WHD, HD, SMCI and FORM.

Read-only.
"""
import csv
import os
from collections import Counter

RUN = r"C:\Users\ACKVerissimo\AVSHUNTER-Intelligence\data\output\runs\20260831_010309"
RID = "20260831_010309"
WBS = os.path.join(RUN, "superbrain", f"wall_break_scores_{RID}.csv")
BOOK = os.path.join(RUN, "intelligence_lab", f"final_opportunity_book_{RID}.csv")
OPT = os.path.join(RUN, "options", f"options_intelligence_{RID}.csv")
csv.field_size_limit(2**31 - 1)

with open(WBS, "r", encoding="utf-8", newline="") as fh:
    rdr = csv.reader(fh)
    whdr = next(rdr)
    wrows = [r for r in rdr]
wi = whdr.index("ticker")
wbs_tickers = [r[wi] for r in wrows]

with open(BOOK, "r", encoding="utf-8", newline="") as fh:
    rdr = csv.reader(fh)
    bhdr = next(rdr)
    brows = [r for r in rdr]
bi = bhdr.index("ticker")
book_tickers = {r[bi] for r in brows}

inter = [t for t in wbs_tickers if t in book_tickers]
excl = [t for t in wbs_tickers if t not in book_tickers]

print(f"wall_break_scores rows = {len(wrows)}, unique tickers = {len(set(wbs_tickers))}")
print(f"final book tickers = {len(book_tickers)}")
print(f"intersection = {len(inter)}")
print(f"excluded from book = {len(excl)}")
print(f"excluded tickers: {sorted(excl)}")

# WBS verdict/classification columns, to check the PROBABLE claim
cand = [c for c in whdr if "wbs" in c.lower() or "break" in c.lower()]
print(f"\nWBS-named columns: {cand[:40]}")
for c in cand:
    ci = whdr.index(c)
    vals = Counter(r[ci] for r in wrows)
    if 1 < len(vals) <= 8 and any(isinstance(k, str) and k.isupper() and k for k in vals):
        print(f"  {c}: " + ", ".join(f"{k!r}={v}" for k, v in vals.most_common()))

for label in ("PROBABLE",):
    for c in whdr:
        ci = whdr.index(c)
        if any(r[ci] == label for r in wrows):
            got = [r[wi] for r in wrows if r[ci] == label]
            print(f"\ncolumn {c!r} carries {label}: {len(got)} rows -> {sorted(got)}")
            print(f"  of which excluded from the book: {sorted(t for t in got if t not in book_tickers)}")

# book-side marker
if "wbs_break_direction" in bhdr:
    xi = bhdr.index("wbs_break_direction")
    nz = sum(1 for r in brows if r[xi] not in ("", "nan"))
    print(f"\nbook rows with non-blank wbs_break_direction: {nz} of {len(brows)}")

# where did the excluded ones stop? check options lifecycle state for them
with open(OPT, "r", encoding="utf-8", newline="") as fh:
    rdr = csv.reader(fh)
    ohdr = next(rdr)
    oi = ohdr.index("ticker")
    orr = ohdr.index("remaining_runway_state")
    od = ohdr.index("canonical_direction")
    st = {r[oi]: (r[orr], r[od]) for r in rdr if r[oi] in set(excl)}
print("\nexcluded WBS tickers, options remaining_runway_state / direction:")
for t in sorted(excl):
    print(f"  {t}: {st.get(t, ('<not in options>', ''))}")
