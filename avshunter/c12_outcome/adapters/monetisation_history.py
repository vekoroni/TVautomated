"""Bounded exact-contract Phantom reads. Never requests, ingests or writes data."""
from __future__ import annotations
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import hashlib
import json
import sqlite3
from avshunter.shared.xnys_calendar import session_bounds

def instant(value):
    try:
        d=datetime.fromisoformat(str(value).replace('Z','+00:00'))
        return d.astimezone(timezone.utc) if d.tzinfo else None
    except (ValueError,TypeError):return None

class SavedMonetisationHistory:
    def __init__(self,database,*,lookback_days,close_tolerance_seconds):
        self.path=Path(database).resolve()
        self.lookback_days=lookback_days;self.tolerance=close_tolerance_seconds
        self.days={};self.conn=None

    def __enter__(self):
        self.conn=sqlite3.connect(self.path.as_uri()+'?mode=ro',uri=True,timeout=3)
        self.conn.execute('PRAGMA query_only=ON')
        return self

    def __exit__(self,*args):
        if self.conn:self.conn.close();self.conn=None

    def read(self,ticker,symbol,*,as_of,decision_cutoff):
        if decision_cutoff is None or decision_cutoff.tzinfo is None:
            raise ValueError('An explicit timezone-aware decision cutoff is required')
        key=(ticker,as_of)
        start=(as_of-timedelta(days=self.lookback_days)).isoformat()
        if key not in self.days:
            self.days[key]=[x[0] for x in self.conn.execute('SELECT DISTINCT quote_date FROM chain_snapshots '
                'WHERE ticker=? AND quote_date>=? AND quote_date<=? ORDER BY quote_date',
                (ticker,start,as_of.isoformat()))]
        days=self.days[key]
        history={};reasons={};raw=[];backfilled=0
        # Date-point PK lookups, not a whole-table/whole-history scan.
        for offset in range(0,len(days),200):
            batch=days[offset:offset+200]
            if not batch:continue
            query='SELECT quote_date,bid,ask,bid_size,ask_size,updated_ts,created_at_utc FROM chain_snapshots WHERE ticker=? AND quote_date IN ('+','.join('?' for _ in batch)+') AND option_symbol=? ORDER BY quote_date'
            raw.extend(self.conn.execute(query,(ticker,*batch,symbol)).fetchall())
        for day,bid,ask,bs,az,ts,created in raw:
            reason=None;available=instant(created)
            try:
                quoted=datetime.fromtimestamp(int(ts),timezone.utc)
                close=session_bounds(date.fromisoformat(day))[1]
                if abs((quoted-close).total_seconds())>self.tolerance:reason='NOT_NEAR_SESSION_CLOSE'
            except (ValueError,TypeError,OSError,OverflowError):reason='INVALID_QUOTE_TIMESTAMP'
            if available is None:reason='RECEIPT_AVAILABILITY_UNASSESSED'
            elif available>decision_cutoff:reason='RECEIPT_AFTER_DECISION_CUTOFF'
            if available and available.date()>date.fromisoformat(day):backfilled+=1
            history[day]=None if reason else {'bid':bid,'ask':ask,'bid_size':bs,'ask_size':az}
            if reason:reasons[reason]=reasons.get(reason,0)+1
        receipt={'ticker':ticker,'contract_symbol':symbol,'database':str(self.path),
            'quote_sessions_through':as_of.isoformat(),'receipt_available_by_utc':decision_cutoff.isoformat(),
            'lookback_start':start,'saved_exact_rows':len(raw),'quarantine_counts':reasons,
            'backfilled_quote_rows':backfilled,
            'quote_rows_sha256':hashlib.sha256(json.dumps(raw,separators=(',',':'),allow_nan=False).encode()).hexdigest(),
            'lookup':'EXACT_TICKER_SESSION_OCC_PK','entry_fill_proof':False}
        return history,receipt
