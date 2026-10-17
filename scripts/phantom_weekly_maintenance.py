"""No-paid-call maintenance: plan exact gaps, repair stored rows, drain IV queue."""
from __future__ import annotations
import argparse,csv,json,re,sqlite3,sys,shutil
from datetime import datetime,timedelta,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0,str(ROOT))
from scripts.phantom_maintenance import (ensure_schema,complete_greeks_and_queue_iv,
    drain_pending,refresh_pair_health,session_health)
from avshunter.shared.xnys_calendar import session_state,xnys_session_on_or_before

def load_roster(path):
    with Path(path).open(encoding='utf-8-sig',newline='') as f:
        rows=csv.DictReader(f)
        # Identity strings NAN and SYM are not missing-value sentinels.
        return sorted({str(r.get('ticker') or r.get('symbol') or '').strip().upper() for r in rows
          if re.fullmatch(r'[A-Za-z][A-Za-z0-9.\-]{0,9}',str(r.get('ticker') or r.get('symbol') or '').strip())})

def latest_friday():
    last=session_state(datetime.now(timezone.utc))[2]
    friday=last-timedelta(days=(last.weekday()-4)%7)
    return xnys_session_on_or_before(friday).isoformat()

def plan_session(c,day,tickers):
    has_audit=c.execute("SELECT 1 FROM sqlite_master WHERE name='backfill_audit'").fetchone()
    no_data={r[0] for r in c.execute("SELECT ticker FROM backfill_audit WHERE quote_date=? AND status='NO_DATA'",(day,))} if has_audit else set()
    present=[]; absent=[]; known_no_data=[]
    for ticker in tickers:
        if c.execute('SELECT 1 FROM chain_snapshots WHERE ticker=? AND quote_date=? LIMIT 1',(ticker,day)).fetchone():
            present.append(ticker)
        elif ticker in no_data:
            known_no_data.append(ticker)
        else:
            absent.append(ticker)
    return {'session':day,'expected_tickers':len(tickers),'with_chains':len(present),
      'audited_no_data':len(known_no_data),'missing_pairs':len(absent),'missing_tickers':absent,
      'present_tickers':present,'population_reconciled':len(present)+len(known_no_data)+len(absent)==len(tickers)}

def provenance_health(c,day,tickers):
    """Indexed latest-session counts; never scan other dates or decode raw JSON."""
    counts=dict(rows=0,blank_source=0,blank_quality=0,missing_or_invalid_underlying=0)
    columns={r[1] for r in c.execute('PRAGMA table_info(chain_snapshots)')}
    source='greeks_source' if 'greeks_source' in columns else 'NULL'
    quality='greeks_quality' if 'greeks_quality' in columns else 'NULL'
    for ticker in tickers:
        row=c.execute(f'''SELECT COUNT(*),
            COALESCE(SUM(COALESCE(TRIM({source}),'')=''),0),
            COALESCE(SUM(COALESCE(TRIM({quality}),'')=''),0),
            COALESCE(SUM(underlying_price IS NULL OR underlying_price<=0),0)
            FROM chain_snapshots WHERE ticker=? AND quote_date=?''',(ticker,day)).fetchone()
        counts={k:counts[k]+int(v) for k,v in zip(counts,row)}
    return {'session':day,**counts,'missing_label_columns':sorted({'greeks_source','greeks_quality'}-columns),
        'labels_complete':source!='NULL' and quality!='NULL' and counts['blank_source']==counts['blank_quality']==0}

def repair_stored_pairs(db,day,tickers):
    """One-time bootstrap for existing pairs; future writers maintain receipts."""
    with sqlite3.connect(db,timeout=60) as c:
        ensure_schema(c)
        for ticker in tickers:
            cur=c.execute('''SELECT * FROM chain_snapshots WHERE ticker=? AND quote_date=?
                AND (iv IS NULL OR delta IS NULL OR gamma IS NULL OR theta IS NULL OR vega IS NULL)''',(ticker,day))
            names=[d[0] for d in cur.description]
            while True:
                batch=cur.fetchmany(1000)
                if not batch:
                    break
                if shutil.disk_usage(Path(db).parent).free < 15*1024**3:
                    raise RuntimeError('Weekly repair stopped at 15 GiB reserve')
                # Stored numbers are not newly observed vendor Greeks.
                incoming=[{k:v for k,v in dict(zip(names,r)).items() if k not in {'iv','delta','gamma','theta','vega'}} for r in batch]
                complete_greeks_and_queue_iv(c,incoming)
            refresh_pair_health(c,ticker,day)
            if not c.execute('SELECT 1 FROM iv_surface_history WHERE ticker=? AND quote_date=? LIMIT 1',(ticker,day)).fetchone():
                c.execute("INSERT OR IGNORE INTO phantom_maintenance_pairs(ticker,quote_date,status,updated_at_utc) VALUES(?,?,'PENDING_IV',?)",(ticker,day,datetime.now(timezone.utc).isoformat()))
            c.commit()

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--db-path',type=Path,default=ROOT/'data/phantom/phantom_history.db')
    p.add_argument('--iv-cache-path',type=Path,default=ROOT/'data/cache/iv_history_cache.db')
    p.add_argument('--universe-path',type=Path,default=ROOT/'data/universe/polygon_liquid_universe.csv')
    p.add_argument('--sessions',nargs='+')
    p.add_argument('--report',type=Path,required=True)
    p.add_argument('--execute-local',action='store_true',help='Local stored-data repairs only. Never makes paid calls.')
    p.add_argument('--max-local-pairs',type=int,default=5000,help='Bound IV drain work; pending work stays visible.')
    p.add_argument('--max-label-rows',type=int,default=20000,help='Bound latest-session provenance label work, without scanning historical sessions.')
    args=p.parse_args(argv)
    tickers=load_roster(args.universe_path)
    days=args.sessions or [latest_friday()]
    from datetime import date
    from avshunter.shared.xnys_calendar import is_xnys_session
    for day in days:
        if not is_xnys_session(date.fromisoformat(day)):
            p.error('Not an XNYS session: '+day)
    with sqlite3.connect(args.db_path.as_uri()+'?mode=ro',uri=True,timeout=60) as c:
        sessions=[plan_session(c,d,tickers) for d in days]
        provenance_before=[provenance_health(c,d,tickers) for d in days]
    result={'provider_calls':0,'mode':'LOCAL_EXECUTE' if args.execute_local else 'READ_ONLY_PLAN',
      'sessions':sessions,'roster_count':len(tickers),'local_reports':[],'open_interest_policy':
      'Historical date D OI is settled from previous XNYS session; quote/volume are as of D close. Not same-day OI.'}
    result['provenance_before']=provenance_before
    if args.execute_local:
        for session in sessions:
            repair_stored_pairs(args.db_path,session['session'],session['present_tickers'])
        try:
            from .phantom_provenance_labels import repair_sessions
        except ImportError:
            from phantom_provenance_labels import repair_sessions
        result['provenance_labels']=repair_sessions(args.db_path,days,tickers,max_rows=args.max_label_rows)
        remaining=args.max_local_pairs
        while remaining>0:
            report=drain_pending(args.db_path,args.iv_cache_path,max_pairs=min(500,remaining))
            result['local_reports'].append(report)
            if not report.get('pairs'):
                break
            remaining-=report['pairs']
    result['health']=[session_health(args.db_path,d,tickers) for d in days]
    with sqlite3.connect(args.db_path.as_uri()+'?mode=ro',uri=True,timeout=60) as c:
        result['provenance_after']=[provenance_health(c,d,tickers) for d in days]
    args.report.parent.mkdir(parents=True,exist_ok=True)
    args.report.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps({'mode':result['mode'],'provider_calls':0,'missing_pairs':sum(r['missing_pairs'] for r in sessions),'report':str(args.report)}))
    return 0

if __name__=='__main__':
    raise SystemExit(main())
