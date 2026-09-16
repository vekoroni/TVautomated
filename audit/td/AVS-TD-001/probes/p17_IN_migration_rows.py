"""p17 I4: list schema_migration_log and schema_metadata rows from the control_plane copy (read-only)."""
import sqlite3, json
DB = r"C:\Users\ACKVerissimo\AVSHUNTER-Intelligence\audit\td\AVS-TD-001\db_copies\control_plane.sqlite"
con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
out = {}
for t in ("schema_migration_log", "schema_metadata"):
    cur = con.execute(f"SELECT * FROM {t}")
    cols = [c[0] for c in cur.description]
    out[t] = {"columns": cols, "rows": [dict(zip(cols, r)) for r in cur.fetchall()]}
json.dump(out, open(r"C:\Users\ACKVerissimo\AVSHUNTER-Intelligence\audit\td\AVS-TD-001\probes\p17_IN_migration_rows.json", "w"), indent=1, default=str)
print(json.dumps(out, indent=1, default=str))
