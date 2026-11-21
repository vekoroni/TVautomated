"""Print COMPLETE when today's (ET day) POST_CLOSE macro build has finished COMPLETE, else the latest status."""
import sqlite3, sys, datetime
from zoneinfo import ZoneInfo
db = r"C:\Users\ACKVerissimo\AVSHUNTER-Intelligence\data\macro\delivery\full_build_attempts.sqlite"
day = sys.argv[1] if len(sys.argv) > 1 else datetime.datetime.now(ZoneInfo("America/New_York")).date().isoformat()
c = sqlite3.connect(db, timeout=10)
rows = c.execute("select a.started, o.status from attempts a left join attempt_outcomes o on o.id=a.id "
                 "where a.day=? and a.reason='POST_CLOSE' order by a.started", (day,)).fetchall()
if any(s == "COMPLETE" for _, s in rows): print("COMPLETE")
elif rows: print("LATEST " + str(rows[-1][1] or "RUNNING") + " " + rows[-1][0])
else: print("NONE")
