"""m13 - control_plane.sqlite: table inventory, lifecycle-event tables, thesis
identity keying, and supersession/correction columns.

Claims tested:
  s11.8 temporal identity mismatch - whether thesis_id embeds the RUN date rather
        than the completed option-session date.
  (item 14) whether any supersession/correction column exists on lifecycle events.

Opened strictly read-only: sqlite3.connect("file:...?mode=ro", uri=True).
"""
import sqlite3
from collections import Counter

DB = r"C:\Users\ACKVerissimo\AVSHUNTER-Intelligence\data\canonical\control_plane.sqlite"
con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
cur = con.cursor()

print("=== tables ===")
tables = [r[0] for r in cur.execute(
    "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
for t in tables:
    n = cur.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
    print(f"  {t}: {n} rows")

TARGET = ["option_thesis_events", "option_contract_observations",
          "option_contract_selection_events"]

SUPERSESSION = ["calculation_version", "supersedes_event_id", "correction_reason",
                "corrected_by_run_id", "superseded", "supersede", "status",
                "state", "version", "corrected", "replaces", "replaced_by"]

for t in TARGET:
    print(f"\n=== {t} ===")
    if t not in tables:
        print("  TABLE ABSENT")
        continue
    cols = [(r[1], r[2]) for r in cur.execute(f'PRAGMA table_info("{t}")')]
    names = [c for c, _ in cols]
    n = cur.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
    print(f"  rows: {n}")
    print(f"  columns ({len(names)}): {names}")

    if "thesis_id" in names:
        d = cur.execute(f'SELECT COUNT(DISTINCT thesis_id) FROM "{t}"').fetchone()[0]
        print(f"  distinct thesis_id: {d}")
        sample = [r[0] for r in cur.execute(
            f'SELECT thesis_id FROM "{t}" LIMIT 8')]
        print(f"  thesis_id samples: {sample}")
        tail = Counter(str(r[0]).split(":")[-1] for r in cur.execute(
            f'SELECT thesis_id FROM "{t}"'))
        print("  thesis_id trailing component (top 12):")
        for k, v in tail.most_common(12):
            print(f"    {k!r}: {v}")

    hits = [c for c in names
            if any(s in c.lower() for s in SUPERSESSION)]
    print(f"  supersession/correction-candidate columns: {hits}")
    for c in hits:
        vals = Counter(str(r[0]) for r in cur.execute(
            f'SELECT "{c}" FROM "{t}"'))
        print(f"    {c}: " + ", ".join(f"{k!r}={v}" for k, v in vals.most_common(8)))

    # any value anywhere containing SUPERSEDED
    found = []
    for c in names:
        try:
            got = cur.execute(
                f'SELECT COUNT(*) FROM "{t}" WHERE CAST("{c}" AS TEXT) LIKE \'%SUPERSED%\''
            ).fetchone()[0]
        except sqlite3.Error:
            continue
        if got:
            found.append((c, got))
    print(f"  columns whose values contain 'SUPERSED': {found or 'NONE'}")

    # run-id spread for the evidence run
    for rc in ("run_id", "eod_run_id", "source_run_id"):
        if rc in names:
            rr = Counter(str(r[0]) for r in cur.execute(f'SELECT "{rc}" FROM "{t}"'))
            print(f"  {rc} (top 6): " + ", ".join(f"{k!r}={v}" for k, v in rr.most_common(6)))

# --- temporal identity test: thesis_id date vs the completed option-session date
print("\n=== s11.8 temporal identity test (option_contract_observations) ===")
EXPECT = ["calculation_version", "supersedes_event_id", "correction_reason",
          "corrected_by_run_id"]
for t in TARGET:
    if t in tables:
        names = [r[1] for r in cur.execute(f'PRAGMA table_info("{t}")')]
        print(f"  {t}: named supersession columns present = "
              f"{[c for c in EXPECT if c in names] or 'NONE'}")

rows = cur.execute(
    "SELECT thesis_id, quote_as_of, run_id FROM option_contract_observations "
    "WHERE run_id = '20260831_010309'").fetchall()
same = diff = unknown = 0
pairs = Counter()
for tid, qa, rid in rows:
    tdate = str(tid).split(":")[-1]
    qdate = (str(qa) or "")[:10]
    pairs[(tdate, qdate)] += 1
    if not qdate:
        unknown += 1
    elif tdate == qdate:
        same += 1
    else:
        diff += 1
print(f"  observations for run 20260831_010309: {len(rows)}")
print(f"    thesis_id date == quote_as_of date : {same}")
print(f"    thesis_id date != quote_as_of date : {diff}")
print(f"    quote_as_of absent                 : {unknown}")
print("  (thesis_id date, quote_as_of date) pairs:")
for (a, b), v in pairs.most_common(8):
    print(f"    {a!r} / {b!r}: {v}")

print("\n  distinct thesis_id for a single ticker across dates (FLYW example):")
for r in cur.execute(
        "SELECT DISTINCT thesis_id, run_id FROM option_thesis_events "
        "WHERE ticker = 'FLYW' ORDER BY thesis_id"):
    print(f"    {r}")

print("\n  tickers holding more than one thesis_id (same side, different date):")
dup = cur.execute(
    "SELECT ticker, COUNT(DISTINCT thesis_id) c FROM option_thesis_events "
    "GROUP BY ticker HAVING c > 1 ORDER BY c DESC").fetchall()
print(f"    count = {len(dup)}; top: {dup[:10]}")

con.close()
