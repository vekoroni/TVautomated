import sqlite3, os, json
OUT = r"C:\Users\ACKVerissimo\AVSHUNTER-Intelligence\audit\td\AVS-TD-001"
DBS = ["control_plane.sqlite","decision_outcome_ledger.sqlite","historical_prices.sqlite","run_plans.sqlite","iv_history_cache.db","trade_journal.db"]
report = {}
for db in DBS:
    p = os.path.join(OUT, "db_copies", db)
    if not os.path.exists(p) or os.path.getsize(p) == 0:
        report[db] = {"status": "ABSENT_OR_EMPTY"}; print(db, "ABSENT_OR_EMPTY"); continue
    con = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
    cur = con.cursor()
    tables = [r[0] for r in cur.execute("select name from sqlite_master where type='table' order by name")]
    info = {}
    print(f"=== {db}: {len(tables)} tables ===")
    for t in tables:
        try:
            n = cur.execute(f'select count(*) from "{t}"').fetchone()[0]
        except Exception as e:
            n = f"ERR {e}"
        cols = [r[1] for r in cur.execute(f'pragma table_info("{t}")')]
        info[t] = {"rows": n, "cols": cols}
        print(f"  {t}: rows={n} cols({len(cols)})={cols[:40]}")
    report[db] = info
    con.close()
json.dump(report, open(os.path.join(OUT, "probes", "p02_db_schema.json"), "w"), indent=1, default=str)
