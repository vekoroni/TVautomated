"""Advisory freshness for CME equity/ZN/CL/GC weekday 17-18 ET maintenance.

Holiday/exceptional exchange closures are not inferred. Old bars remain stale.
Grace accounts for delayed source bars; it never makes pre-reopen bars fresh.
"""
from datetime import datetime,timedelta,timezone
from zoneinfo import ZoneInfo
import json
from pathlib import Path
CONFIG=json.loads((Path(__file__).resolve().parents[1]/'config/source_recovery_v1.json').read_text(encoding='utf-8'))['futures']

def classify_futures_quote(now, last, stale_after_minutes=60):
    et=now.astimezone(ZoneInfo('America/New_York'))
    opening=CONFIG['reopen_hour_et'];closing=CONFIG['maintenance_start_hour_et']
    reopen=et.replace(hour=opening,minute=0,second=0,microsecond=0)
    age=(now-last).total_seconds()/60
    out={'stale':age>stale_after_minutes,'state':'STALE' if age>stale_after_minutes else 'OK',
         'session_schedule':'CME_STANDARD_WEEK_HOLIDAYS_UNVERIFIED','next_refresh_utc':None}
    if age<0: return {**out,'stale':True,'state':'FUTURE_QUOTE'}
    if et.weekday()==5 or (et.weekday()==4 and et.hour>=closing) or (et.weekday()==6 and et.hour<opening):
        out.update(state='WEEKEND_CLOSED',stale=True)
    elif closing<=et.hour<opening:
        out.update(state='SESSION_BREAK',stale=True,next_refresh_utc=(reopen+timedelta(minutes=CONFIG['reopen_grace_minutes'])).astimezone(timezone.utc).isoformat().replace('+00:00','Z'))
    else:
        if et.hour<opening: reopen-=timedelta(days=1)
        if last.astimezone(timezone.utc)<reopen.astimezone(timezone.utc):
            deadline=reopen+timedelta(minutes=CONFIG['reopen_grace_minutes'])
            pending=et<deadline
            out.update(state='REOPEN_PENDING' if pending else 'STALE_AFTER_REOPEN',stale=True,
                       next_refresh_utc=deadline.astimezone(timezone.utc).isoformat().replace('+00:00','Z') if pending else None)
    return out
