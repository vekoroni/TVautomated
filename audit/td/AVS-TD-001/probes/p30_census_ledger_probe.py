import sqlite3, json, collections, os
OUT = r"C:\Users\ACKVerissimo\AVSHUNTER-Intelligence\audit\td\AVS-TD-001"
con = sqlite3.connect(f"file:{os.path.join(OUT,'db_copies','decision_outcome_ledger.sqlite')}?mode=ro", uri=True)
cur = con.cursor()
print("event types:", cur.execute("select event_type, count(*), min(occurred_at_utc), max(occurred_at_utc) from ledger_events group by 1 order by 2 desc").fetchall())
print("schema versions:", cur.execute("select schema_version, event_type, count(*) from ledger_events group by 1,2").fetchall())
print("runs:", cur.execute("select run_id, count(*) from ledger_events group by 1 order by 1").fetchall())
keys = collections.defaultdict(collections.Counter)
samples = {}
for et, pj in cur.execute("select event_type, payload_json from ledger_events"):
    try:
        d = json.loads(pj)
    except Exception:
        continue
    for k in d.keys():
        keys[et][k] += 1
    samples.setdefault(et, d)
for et in keys:
    print("\n==", et, "payload keys:", dict(keys[et]))
    s = json.dumps(samples[et])[:1500]
    print("sample:", s)
