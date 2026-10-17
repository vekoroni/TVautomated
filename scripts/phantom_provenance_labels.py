"""Bounded, reversible label-only correction. No provider calls or Greek solving."""
from __future__ import annotations
import argparse,hashlib,json,math,shutil,sqlite3,time
from datetime import datetime,timezone
from pathlib import Path

GREEKS=('iv','delta','gamma','theta','vega')
KEY=('ticker','quote_date','option_symbol')
NUMERIC=('expiration_ts','strike','dte','updated_ts','bid','ask','mid','last',
         'open_interest','volume','underlying_price',*GREEKS)
RUN='PROVENANCE_LABELS_20261017_V1'

def now():return datetime.now(timezone.utc).isoformat()
def finite(v):
    try:return v is not None and math.isfinite(float(v))
    except (ValueError,TypeError):return False
def blank(v):return not str(v or '').strip()
def numeric_hash(row):
    return hashlib.sha256(json.dumps([float(row[k]) if finite(row.get(k)) else row.get(k) for k in NUMERIC],allow_nan=True).encode()).hexdigest()

def labels(row,history=None):
    """Never infer vendor from provider name alone or claim an untried solve failed."""
    source=row.get('greeks_source');quality=row.get('greeks_quality')
    issue=None if finite(row.get('underlying_price')) and float(row['underlying_price'])>0 else 'MISSING_OR_INVALID_NOT_FILLED'
    if not blank(source) and not blank(quality):
        return source,quality,issue
    present=[g for g in GREEKS if finite(row.get(g))]
    missing=len(present)<5
    try:raw=json.loads(row.get('raw_json') or '{}')
    except (TypeError,ValueError):raw={}
    if not isinstance(raw,dict):raw={}
    hints=' '.join(str(raw.get(k) or '') for k in ('greeks_source',*[g+'_source' for g in GREEKS],'implied_vol_source')).upper()
    computed_hint=any(t in hints for t in ('COMPUTED','BSM','SOLVED','BLACK_SCHOLES'))
    vendor=str(row.get('source') or '').upper() in ('MARKETDATA','MARKETDATA.APP','MARKETDATA_OPTIONS_QUOTES','MARKETDATA_CACHED')
    matches=bool(present) and vendor and not computed_hint and all(
        finite(raw.get(g,raw.get('implied_vol') if g=='iv' else None)) and
        math.isclose(float(row[g]),float(raw.get(g,raw.get('implied_vol') if g=='iv' else None)),rel_tol=1e-10,abs_tol=1e-12) for g in present)
    if blank(source):
        if matches:source='MARKETDATA_VENDOR'
        elif not present:source='UNAVAILABLE_NO_NUMERIC_GREEKS'
        elif computed_hint:source='COMPUTED_SOURCE_UNVERIFIED'
        else:source='EXISTING_UNVERIFIED'
    if blank(quality):
        if missing:
            status=str((history or {}).get('quality_status') or '')
            quality=('HISTORY_'+status+('_CHAIN_INCOMPLETE' if status.startswith('OK') else '') if status else 'INCOMPLETE_UNASSESSED_NO_SOLVER_RECORD')
        elif matches:quality='VENDOR_COMPLETE'
        elif 'COMPUTED' in str(source):quality='COMPLETE_COMPUTED_EXISTING'
        else:quality='COMPLETE_EXISTING_PROVENANCE_UNVERIFIED'
    return source,quality,issue

def ensure_schema(c):
    c.execute('''CREATE TABLE IF NOT EXISTS phantom_provenance_label_runs(
        run_id TEXT PRIMARY KEY,last_rowid INTEGER NOT NULL,counts_json TEXT,status TEXT,updated_at_utc TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS phantom_provenance_label_audit(
        run_id TEXT NOT NULL,row_id INTEGER NOT NULL,ticker TEXT,quote_date TEXT,option_symbol TEXT,
        old_source TEXT,old_quality TEXT,new_source TEXT,new_quality TEXT,numeric_sha256 TEXT,
        underlying_issue TEXT,created_at_utc TEXT,PRIMARY KEY(run_id,row_id))''')

def apply_batch(c, rows,run_id=RUN):
    """Caller owns transaction. No commit or numeric update inside this helper."""
    audit=[];updates=[];original={};counts={'scanned':len(rows),'labelled':0,'vendor_labelled':0,'quality_labelled':0,'underlying_flagged':0}
    for row in rows:
        history=None
        if any(not finite(row.get(g)) for g in GREEKS) and blank(row.get('greeks_quality')):
            cur=c.execute('SELECT quality_status FROM options_greeks_history WHERE ticker=? AND snapshot_date=? AND contract_symbol=?',tuple(row[k] for k in KEY))
            found=cur.fetchone();history={'quality_status':found[0]} if found else None
        source,quality,issue=labels(row,history)
        changed=source!=row.get('greeks_source') or quality!=row.get('greeks_quality')
        if not changed and not issue:continue
        prior=c.execute('SELECT 1 FROM phantom_provenance_label_audit WHERE run_id=? AND row_id=?',(run_id,row['_rowid'])).fetchone()
        if prior:continue
        digest=numeric_hash(row);original[row['_rowid']]=digest
        audit.append((run_id,row['_rowid'],*[row[k] for k in KEY],row.get('greeks_source'),row.get('greeks_quality'),source,quality,digest,issue,now()))
        if changed:updates.append((source,quality,row['_rowid'],*[row[k] for k in KEY],row.get('greeks_source'),row.get('greeks_quality')))
        counts['labelled']+=bool(changed)
        counts['vendor_labelled']+=source=='MARKETDATA_VENDOR' and source!=row.get('greeks_source')
        counts['quality_labelled']+=quality!=row.get('greeks_quality')
        counts['underlying_flagged']+=bool(issue)
    c.executemany('INSERT INTO phantom_provenance_label_audit VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',audit)
    before=c.total_changes
    c.executemany('''UPDATE chain_snapshots SET greeks_source=?,greeks_quality=?
      WHERE rowid=? AND ticker=? AND quote_date=? AND option_symbol=?
      AND greeks_source IS ? AND greeks_quality IS ?''',updates)
    if c.total_changes-before!=len(updates):raise RuntimeError('Concurrent label change: batch must roll back')
    if original:
        keys=list(original);marks=','.join('?' for _ in keys)
        cur=c.execute('SELECT rowid AS _rowid,* FROM chain_snapshots WHERE rowid IN ('+marks+')',keys)
        names=[d[0] for d in cur.description];checked=0
        for values in cur:
            row=dict(zip(names,values));checked+=1
            if numeric_hash(row)!=original[row['_rowid']]:raise RuntimeError('Numeric preservation failed: rollback required')
        if checked!=len(original):raise RuntimeError('Row conservation failed')
    return counts

def correct(db,*,execute=False,max_rows=2000,batch_size=1000,run_id=RUN,min_free_gib=15):
    db=Path(db).resolve()
    mode='' if execute else '?mode=ro'
    c=sqlite3.connect(str(db) if execute else db.as_uri()+mode,uri=not execute,timeout=30)
    if not execute:c.execute('PRAGMA query_only=ON')
    columns={r[1] for r in c.execute('PRAGMA table_info(chain_snapshots)')}
    if not set((*KEY,*GREEKS,'greeks_source','greeks_quality','raw_json')).issubset(columns):raise RuntimeError('Unexpected chain schema')
    if execute:
        ensure_schema(c);c.commit()
    exists=c.execute("SELECT 1 FROM sqlite_master WHERE name='phantom_provenance_label_runs'").fetchone()
    checkpoint=c.execute('SELECT last_rowid,counts_json FROM phantom_provenance_label_runs WHERE run_id=?',(run_id,)).fetchone() if exists else None
    after=checkpoint[0] if checkpoint else 0
    totals=json.loads(checkpoint[1]) if checkpoint else {'scanned':0,'labelled':0,'vendor_labelled':0,'quality_labelled':0,'underlying_flagged':0}
    this_run=0;finished=False
    while this_run<max_rows:
        if shutil.disk_usage(db.parent).free<min_free_gib*1024**3:raise RuntimeError('STOP_DISK_RESERVE')
        cur=c.execute('SELECT rowid AS _rowid,* FROM chain_snapshots WHERE rowid>? ORDER BY rowid LIMIT ?',(after,min(batch_size,max_rows-this_run)))
        names=[d[0] for d in cur.description];rows=[dict(zip(names,r)) for r in cur.fetchall()]
        if not rows:finished=True;break
        if execute:
            try:
                c.execute('BEGIN IMMEDIATE')
                # Read again under writer lock so preimages/labels/receipts share one snapshot.
                ids=[r['_rowid'] for r in rows];marks=','.join('?' for _ in ids)
                cur=c.execute('SELECT rowid AS _rowid,* FROM chain_snapshots WHERE rowid IN ('+marks+') ORDER BY rowid',ids)
                names=[d[0] for d in cur.description];locked=[dict(zip(names,r)) for r in cur.fetchall()]
                if len(locked)!=len(rows):raise RuntimeError('Concurrent row deletion')
                counts=apply_batch(c,locked,run_id)
                after=rows[-1]['_rowid'];newtotals={k:totals[k]+counts[k] for k in totals}
                c.execute('INSERT OR REPLACE INTO phantom_provenance_label_runs VALUES(?,?,?,?,?)',(run_id,after,json.dumps(newtotals),'RUNNING',now()))
                c.commit();totals=newtotals
            except Exception:
                c.rollback();raise
        else:
            counts={'scanned':len(rows),'labelled':0,'vendor_labelled':0,'quality_labelled':0,'underlying_flagged':0}
            for row in rows:
                source,quality,issue=labels(row)
                counts['labelled']+=source!=row.get('greeks_source') or quality!=row.get('greeks_quality')
                counts['vendor_labelled']+=source=='MARKETDATA_VENDOR' and source!=row.get('greeks_source')
                counts['quality_labelled']+=quality!=row.get('greeks_quality');counts['underlying_flagged']+=bool(issue)
            totals={k:totals[k]+counts[k] for k in totals};after=rows[-1]['_rowid']
        this_run+=len(rows)
        if this_run%10000==0:print(json.dumps({'status':'RUNNING','last_rowid':after,**totals}),flush=True)
    status='COMPLETE' if finished else 'BATCH_LIMIT'
    if execute:
        c.execute('UPDATE phantom_provenance_label_runs SET status=?,updated_at_utc=? WHERE run_id=?',(status,now(),run_id));c.commit()
    c.close()
    return {'status':status,'execute':execute,'run_id':run_id,'last_rowid':after,**totals,'numeric_changes':0,'provider_calls':0,'finished':now()}

def repair_sessions(db,days,tickers,*,max_rows=20000):
    """Bounded latest-session check on indexed ticker/date pairs, not all history."""
    totals={'scanned':0,'labelled':0,'vendor_labelled':0,'quality_labelled':0,'underlying_flagged':0}
    run_id='WEEKLY_LABELS_'+now()
    with sqlite3.connect(db,timeout=30) as c:
        ensure_schema(c);c.commit()
        c.execute('''CREATE TABLE IF NOT EXISTS phantom_provenance_session_queue(
            session TEXT PRIMARY KEY,status TEXT NOT NULL,updated_at_utc TEXT NOT NULL)''')
        for day in days:
            c.execute('INSERT OR REPLACE INTO phantom_provenance_session_queue VALUES(?,?,?)',(day,'PENDING',now()))
        c.commit()
        pending_days=[r[0] for r in c.execute("SELECT session FROM phantom_provenance_session_queue WHERE status='PENDING' ORDER BY session")]
        for day in pending_days:
            for ticker in tickers:
                after=0
                while totals['scanned']<max_rows:
                    if shutil.disk_usage(Path(db).parent).free<15*1024**3:raise RuntimeError('STOP_DISK_RESERVE')
                    cur=c.execute('''SELECT rowid AS _rowid,* FROM chain_snapshots
                      WHERE ticker=? AND quote_date=? AND rowid>? AND
                      (COALESCE(TRIM(greeks_source),'')='' OR COALESCE(TRIM(greeks_quality),'')=''
                       OR underlying_price IS NULL OR underlying_price<=0)
                      ORDER BY rowid LIMIT ?''',(ticker,day,after,min(1000,max_rows-totals['scanned'])))
                    names=[d[0] for d in cur.description];rows=[dict(zip(names,r)) for r in cur.fetchall()]
                    if not rows:break
                    try:
                        c.execute('BEGIN IMMEDIATE')
                        counts=apply_batch(c,rows,run_id);c.commit()
                    except Exception:c.rollback();raise
                    totals={k:totals[k]+counts[k] for k in totals};after=rows[-1]['_rowid']
                if totals['scanned']>=max_rows:
                    return {'status':'BATCH_LIMIT_REMAINDER_UNASSESSED',**totals,'pending_sessions':[r[0] for r in c.execute("SELECT session FROM phantom_provenance_session_queue WHERE status='PENDING' ORDER BY session")],'provider_calls':0,'numeric_changes':0}
            c.execute("UPDATE phantom_provenance_session_queue SET status='COMPLETE',updated_at_utc=? WHERE session=?",(now(),day));c.commit()
    return {'status':'COMPLETE_SESSION_CHECK',**totals,'pending_sessions':[],'provider_calls':0,'numeric_changes':0}

def main():
    p=argparse.ArgumentParser();p.add_argument('--db',type=Path,required=True);p.add_argument('--execute',action='store_true')
    p.add_argument('--max-rows',type=int,default=2000);p.add_argument('--batch-size',type=int,default=1000);p.add_argument('--report',type=Path,required=True)
    a=p.parse_args()
    if not 1<=a.batch_size<=1000 or a.max_rows<1:p.error('Invalid bounded batch size')
    try:r=correct(a.db,execute=a.execute,max_rows=a.max_rows,batch_size=a.batch_size)
    except Exception as exc:
        r={'status':'STOPPED','error':str(exc),'finished':now(),'provider_calls':0}
        a.report.write_text(json.dumps(r,indent=2));print(json.dumps(r),flush=True);return 1
    a.report.write_text(json.dumps(r,indent=2));print(json.dumps(r),flush=True);return 0

if __name__=='__main__':raise SystemExit(main())
