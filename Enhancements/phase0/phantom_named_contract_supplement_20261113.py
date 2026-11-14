"""ACK-approved missing entry quotes only; original shared cap, insert-only."""
from __future__ import annotations
import argparse,gzip,hashlib,json,os,re,sqlite3,sys
from collections import defaultdict
from contextlib import closing
from datetime import date,datetime
from pathlib import Path
from zoneinfo import ZoneInfo
HERE=Path(__file__).resolve().parent
if str(HERE) not in sys.path:sys.path.insert(0,str(HERE))
import guarded_phantom_backfill as g
ROOT=g.ROOT
JOB='PHANTOM_NAMED_SUPPLEMENT_20261113'
ENTRY_DAYS={'2026-10-14','2026-10-19','2026-10-20','2026-10-22','2026-11-11'}
APPROVED_TARGETS_SHA256='52c920bfb1ba206deee5b60d9fc35d9368fef7c5777aeffd5c77b44f0b4e468d'
ALLOWED_DAYS=ENTRY_DAYS|set(g.DAYS)
BASE=HERE/'backfill_receipts'/g.JOB
FOLDER=BASE/JOB
DB=ROOT/'data/phantom/phantom_history.db'
CACHE=ROOT/'data/cache/iv_history_cache.db'
RESEARCH=ROOT/'dropbox/macro/coaching/model/outcomes/decision_events.sqlite'

def check_target(t,scope=None):
    if scope is not None:return scope.check_target(t)
    if t['day'] not in ENTRY_DAYS:raise ValueError('Unapproved entry day; 12 November deferred')
    match=re.fullmatch(r'([A-Z0-9.]+)(\d{6})([CP])(\d{8})',t['symbol'])
    if not match:raise ValueError('Malformed exact OCC')
    g.check_identity(t['ticker'],match[1],t['symbol'])
    expiry=datetime.strptime(match[2],'%y%m%d').date();dte=(expiry-date.fromisoformat(t['day'])).days
    if not (dte>60 or (t['ticker'],t['day'],t['symbol'])==('ARKG','2026-10-20','ARKG261120P00046000')):raise ValueError('Outside approved scope')
    return match,expiry,dte

def worklist():
    entries=[]
    with closing(g.ro(RESEARCH)) as c:
        for ticker,day,symbol in c.execute("SELECT e.ticker,e.decision_session,e.contract_scored FROM decision_events e JOIN option_entry x USING(event_id) WHERE COALESCE(e.contract_scored,'')<>'' AND x.ref_quote_date IS NULL AND e.decision_session<>'2026-11-12' ORDER BY 2,1,3"):
            t={'ticker':ticker,'day':day,'symbol':symbol};check_target(t);entries.append(t)
    return {'job':JOB,'entry_count':len(entries),'targets':list({tuple(t.values()):t for t in entries}.values()),'created':g.now(),'cap':g.CAP}

def quote_key(t,scope=None):
    check_target(t,scope)
    return g.digest(g.encoded(['MARKETDATA_OPTION_QUOTE_V1',t['ticker'],t['day'],t['symbol'],{'date':t['day']}]))

def normalize_quote(data,t,scope=None):
    match,expiry,dte=check_target(t,scope)
    if data.get('optionSymbol')!=[t['symbol']]:raise g.MappingFailure('Returned OCC differs from named contract: '+t['symbol'])
    for name,value in data.items():
        if isinstance(value,list) and len(value)!=1:raise RuntimeError('UNEQUAL_QUOTE_ARRAYS: '+name)
    for name in ('underlying','expiration','side','strike'):
        if name in data and not isinstance(data[name],list):raise RuntimeError('INVALID_IDENTITY_ARRAY: '+name)
    if 'underlying' in data:g.check_identity(t['ticker'],data['underlying'][0],t['symbol'])
    if not isinstance(data.get('updated'),list) or len(data['updated'])!=1:raise RuntimeError('QUOTE_DATE_UNAVAILABLE')
    if str(datetime.fromtimestamp(data['updated'][0],ZoneInfo('America/New_York')).date())!=t['day']:raise RuntimeError('QUOTE_DATE_MISMATCH')
    side='call' if match[3]=='C' else 'put';strike=int(match[4])/1000
    if data.get('side',[side])[0]!=side or float(data.get('strike',[strike])[0])!=strike:raise RuntimeError('OCC_STATIC_IDENTITY_MISMATCH')
    if data.get('expiration',[None])[0] is not None and datetime.fromtimestamp(data['expiration'][0],ZoneInfo('America/New_York')).date()!=expiry:raise RuntimeError('OCC_EXPIRATION_MISMATCH')
    norm=dict(data,side=[side],strike=[strike],dte=[dte],underlying=data.get('underlying',[match[1]]))
    from scripts.phantom_database import normalize_marketdata_chain
    rows=normalize_marketdata_chain(norm,t['ticker'],t['day'])
    if len(rows)!=1:raise RuntimeError('Quote normalization conservation failed')
    row=rows[0];row['source']='MARKETDATA_OPTIONS_QUOTES'
    raw={k:v[0] for k,v in data.items() if isinstance(v,list)}
    raw.update(backfill_job=JOB if scope is None else scope.job,canonical_ticker=t['ticker'],request_key=quote_key(t,scope),endpoint='options/quotes',request_date=t['day'],occ_expiry_date=str(expiry),dte_policy='OCC_EXPIRY_MINUS_QUOTE_DATE_CALENDAR_DAYS',static_identity_policy='EXACT_OCC_DECODE_NOT_PRICE_IMPUTATION')
    row['raw_json']=json.dumps(raw,allow_nan=False)
    return row

def fetch_quote(session,budget,t,scope=None):
    key=quote_key(t,scope);record,fresh=budget.reserve(key,t['ticker'],t['day'],0)
    if fresh:
        record.update(endpoint='options/quotes',option_symbol=t['symbol'],scope_job=JOB if scope is None else scope.job,params={'date':t['day']});budget.persist(record)
        response=session.get('https://api.marketdata.app/v1/options/quotes/'+t['symbol']+'/',params={'date':t['day']},timeout=(15,60),allow_redirects=False)
        try:data=response.json()
        except ValueError:data={'s':'error','errmsg':'NON_JSON_RESPONSE'}
        payload={'http':response.status_code,'headers':{k:v for k,v in response.headers.items() if k.lower().startswith('x-api-ratelimit-')},'data':data}
        raw=gzip.compress(g.encoded(payload));dest=budget.folder/(key+'.json.gz')
        with dest.open('xb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
        record.update(status='RECEIVED',raw=str(dest),raw_sha256=g.digest(raw),finished=g.now(),provider_consumed=response.headers.get('X-Api-Ratelimit-Consumed'));budget.persist(record)
    return g.checked_payload(g.read_receipt(record),record)

def saved_matches(targets,budget,scope=None):
    wanted={(t['ticker'],t['day'],t['symbol']):t for t in targets};found={};seen=set()
    wanted_pairs={k[:2] for k in wanted}
    for journal in [budget.journal,*sorted(g.EXTERNAL.glob('*BUDGET.jsonl'))]:
        latest={}
        for line in journal.read_text(encoding='utf-8-sig').splitlines():
            r=json.loads(line)
            if (r.get('ticker'),r.get('day')) in wanted_pairs:latest[r['key']]=r
        for r in latest.values():
            if r.get('status')!='RECEIVED':raise RuntimeError('UNCERTAIN_MATCHING_SAVED_REQUEST')
            if not r.get('raw') or r['raw'] in seen:continue
            seen.add(r['raw']);payload=g.read_receipt(r)
            if payload.get('http') not in (200,203):continue
            data=payload.get('data',{});symbols=data.get('optionSymbol',[])
            for key,t in wanted.items():
                if key[:2]!=(r.get('ticker'),r.get('day')) or t['symbol'] not in symbols:continue
                i=symbols.index(t['symbol']);selected={k:([v[i]] if isinstance(v,list) and len(v)==len(symbols) else v) for k,v in data.items()}
                normalize_quote(selected,t,scope)
                if key in found and found[key]['data']!=selected:raise RuntimeError('CONFLICTING_SAVED_QUOTES')
                found[key]={'data':selected,'raw':r['raw'],'raw_sha256':r.get('raw_sha256'),'journal':str(journal)}
    return found

def existing_hash(db,ticker,day,exclude,table='chain_snapshots'):
    if table not in ('chain_snapshots','options_greeks_history'):raise ValueError('Unexpected table')
    symbol='option_symbol' if table=='chain_snapshots' else 'contract_symbol';datecol='quote_date' if table=='chain_snapshots' else 'snapshot_date';h=hashlib.sha256()
    with closing(g.ro(db)) as c:
        cur=c.execute(f'SELECT * FROM {table} WHERE ticker=? AND {datecol}=? ORDER BY {symbol}',(ticker,day));idx=[d[0] for d in cur.description].index(symbol)
        for row in cur:
            if row[idx] not in exclude:h.update(g.encoded(row));h.update(b'\n')
    return h.hexdigest()

def insert_exact(db,rows,scope=None):
    if not rows:return 0
    if len({(r['ticker'],r['quote_date']) for r in rows})!=1:raise ValueError('One pair per transaction')
    for r in rows:check_target({'ticker':r['ticker'],'day':r['quote_date'],'symbol':r['option_symbol']},scope)
    from scripts.phantom_maintenance import complete_greeks_and_queue_iv
    with closing(sqlite3.connect(db,timeout=30)) as c:
        new=[r for r in rows if not c.execute('SELECT 1 FROM chain_snapshots WHERE ticker=? AND quote_date=? AND option_symbol=?',(r['ticker'],r['quote_date'],r['option_symbol'])).fetchone()]
        if not new:return 0
        g.install_chain_guard(c,[(r['ticker'],r['quote_date'],r['option_symbol']) for r in new])
        c.execute("CREATE TEMP TRIGGER preserve_computed BEFORE UPDATE ON main.options_greeks_history BEGIN SELECT RAISE(ABORT,'EXISTING_COMPUTED_ROW_UPDATE_PROHIBITED'); END")
        c.execute('BEGIN IMMEDIATE')
        try:
            cols=list(new[0]);c.executemany('INSERT INTO chain_snapshots('+','.join(cols)+') VALUES('+','.join('?' for _ in cols)+')',[[r[k] for k in cols] for r in new]);complete_greeks_and_queue_iv(c,new)
            for r in new:
                key=(r['ticker'],r['quote_date'],r['option_symbol'])
                c.execute("UPDATE chain_snapshots SET greeks_source='UNAVAILABLE_UNASSESSED' WHERE ticker=? AND quote_date=? AND option_symbol=? AND COALESCE(TRIM(greeks_source),'')=''",key)
                if c.execute("SELECT COALESCE(TRIM(greeks_quality),'') FROM chain_snapshots WHERE ticker=? AND quote_date=? AND option_symbol=?",key).fetchone()[0]=='':raise RuntimeError('Unlabelled new row')
            c.commit()
        except Exception:c.rollback();raise
    return len(new)

def derive_preserving(db,cache,ticker,day):
    import pandas as pd
    from scripts.finalize_phantom_weekly_snapshot import CHAIN_SELECT,_surface_and_atm
    with closing(g.ro(db)) as c:
        c.row_factory=sqlite3.Row;rows=[dict(r) for r in c.execute(CHAIN_SELECT+' WHERE ticker=? AND quote_date=?',(ticker,day))]
    surface,atm=_surface_and_atm(pd.DataFrame(rows),day,g.now());expected=None if atm.empty else float(atm.iloc[0]['iv']);conflict=None
    with closing(sqlite3.connect(cache,timeout=30)) as c:
        old=c.execute('SELECT atm_iv FROM iv_history WHERE ticker=? AND sample_date=?',(ticker,day)).fetchone()
        if old and old[0]!=expected:conflict={'existing_atm_iv':old[0],'supplement_aggregate_atm_iv':expected,'status':'EXISTING_IV_CACHE_PRESERVED'}
        if expected is not None:
            c.execute("INSERT OR IGNORE INTO iv_history(ticker,sample_date,atm_iv,source,updated_at) VALUES(?,?,?,'phantom_history',?)",(ticker,day,expected,g.now()));c.execute('INSERT OR IGNORE INTO iv_cache_meta(ticker,last_full_build,last_refresh) VALUES(?,NULL,?)',(ticker,day))
        c.commit()
    with closing(sqlite3.connect(db,timeout=30)) as c:
        c.executemany('''INSERT OR IGNORE INTO iv_surface_history(ticker,quote_date,dte_bucket,side,contract_count,atm_iv,median_iv,iv_entropy,skew_25d,put_call_iv_spread,median_spread_pct,total_open_interest,total_volume,created_at_utc) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',surface)
        state='COMPLETE' if expected is not None else 'IV_UNAVAILABLE'
        c.execute("UPDATE phantom_maintenance_pairs SET status=?,updated_at_utc=?,last_error=?,attempts=attempts+1 WHERE ticker=? AND quote_date=? AND status='PENDING_IV'",(state,g.now(),json.dumps(conflict) if conflict else (None if expected is not None else 'NO_VALID_ATM_INPUT'),ticker,day));c.commit()
    return {'ticker':ticker,'day':day,'state':state,'cache_preservation_flag':conflict}

def preservation_snapshot(db,cache,targets):
    pairs=defaultdict(set)
    for t in targets:pairs[(t['ticker'],t['day'])].add(t['symbol'])
    output={'pairs':{},'counts':g.all_date_counts(db,sorted({t['ticker'] for t in targets}))}
    with closing(g.ro(cache)) as ivc,closing(g.ro(db)) as c:
        for (ticker,day),symbols in pairs.items():
            output['pairs'][ticker+'|'+day]={'chain_hash':existing_hash(db,ticker,day,symbols),'computed_hash':existing_hash(db,ticker,day,symbols,'options_greeks_history'),'cache_rows':[list(r) for r in ivc.execute('SELECT * FROM iv_history WHERE ticker=? AND sample_date=?',(ticker,day))],'surface_rows':[list(r) for r in c.execute('SELECT * FROM iv_surface_history WHERE ticker=? AND quote_date=? ORDER BY dte_bucket,side',(ticker,day))]}
    return output

def run(execute=False,scope=None):
    g.disk_guard(DB);g.writer_guard()
    folder=FOLDER if scope is None else BASE/scope.job
    job=JOB if scope is None else scope.job
    manifest=json.loads((folder/'MANIFEST.json').read_text()) if (folder/'MANIFEST.json').exists() else (worklist() if scope is None else scope.manifest);targets=manifest['targets']
    expected_count,expected_hash=(44,APPROVED_TARGETS_SHA256) if scope is None else (scope.count,scope.target_hash)
    if len(targets)!=expected_count or g.digest(g.encoded(targets))!=expected_hash:
        raise RuntimeError('APPROVED_TARGET_WORKLIST_CHANGED; no provider calls')
    for t in targets:check_target(t,scope)
    budget=g.Budget(BASE,g.CAP,allowed_days=ALLOWED_DAYS if scope is None else scope.allowed_days)
    if any(r['status']!='RECEIVED' for r in budget.records.values()):raise RuntimeError('UNCERTAIN_PRIOR_RESERVATIONS')
    saved=saved_matches(targets,budget,scope)
    print(json.dumps({'mode':'execute' if execute else 'plan','named_entries':manifest['entry_count'],'unique_keys':len(targets),'saved_matches':len(saved),'cumulative_reserved':len(budget.records),'cap':g.CAP,'target_hash':g.digest(g.encoded(targets)),'sessions':sorted({t['day'] for t in targets})}),flush=True)
    if not execute:return 0
    folder.mkdir(exist_ok=True,parents=True);state={'status':'PREFLIGHT','job':job,'pid':os.getpid(),'started':g.now(),'cap':g.CAP,'pipeline_run':False}
    def progress(**values):state.update(values,updated=g.now());g.save(folder/'JOB.json',state)
    try:
        import msvcrt,requests
        from dotenv import dotenv_values
        with (g.EXTERNAL/'PHANTOM_APPROVED_20261017.lock').open('a+b') as lock:
            lock.seek(0);msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
            if not (folder/'MANIFEST.json').exists():g.save(folder/'MANIFEST.json',manifest)
            before_path=folder/'BEFORE.json';before=json.loads(before_path.read_text()) if before_path.exists() else preservation_snapshot(DB,CACHE,targets)
            if not before_path.exists():g.save(before_path,before)
            prior=g.read_pairs(folder/'RESULTS.jsonl');done={(p['ticker'],p['day'],p['symbol']) for p in prior};quarantine=g.global_quarantine(g.EXTERNAL)
            for p in g.read_pairs(BASE/'PAIRS.jsonl')+prior:
                if p.get('status')=='SKIPPED_MAPPING':quarantine[p['ticker']]=p['reason']
            session=requests.Session();token=os.environ.get('MARKETDATA_API_KEY') or dotenv_values(ROOT/'.env').get('MARKETDATA_API_KEY')
            if not token:raise RuntimeError('MarketData credential unavailable')
            session.headers['Authorization']='Token '+token;progress(status='RUNNING')
            for t in targets:
                key=(t['ticker'],t['day'],t['symbol'])
                if key in done:continue
                g.disk_guard(DB);g.writer_guard();result=dict(t)
                with closing(g.ro(DB)) as c:present=c.execute('SELECT raw_json FROM chain_snapshots WHERE ticker=? AND quote_date=? AND option_symbol=?',key).fetchone()
                if present:
                    if json.loads(present[0] or '{}').get('backfill_job')!=job:raise RuntimeError('New external exact capture appeared; preserved')
                    result.update(status='OK',recovered_local_commit=True)
                elif t['ticker'] in quarantine:result.update(status='SKIPPED_MAPPING',reason=quarantine[t['ticker']])
                else:
                    try:
                        data=saved[key]['data'] if key in saved else fetch_quote(session,budget,t,scope)
                        if data.get('s')=='no_data':result.update(status='NO_DATA')
                        else:insert_exact(DB,[normalize_quote(data,t,scope)],scope);result.update(status='OK',saved_response_reused=key in saved)
                    except g.MappingFailure as error:quarantine[t['ticker']]=str(error);result.update(status='SKIPPED_MAPPING',reason=str(error))
                g.append_pair(folder/'RESULTS.jsonl',result);prior.append(result);done.add(key);progress(completed=len(prior),current=t,cumulative_reserved=len(budget.records));print(json.dumps(result),flush=True)
            local=[derive_preserving(DB,CACHE,ticker,day) for ticker,day in sorted({(p['ticker'],p['day']) for p in prior if p['status']=='OK'})];g.save(folder/'LOCAL.json',local)
            after=preservation_snapshot(DB,CACHE,targets);inserted={(p['ticker'],p['day'],p['symbol']) for p in prior if p['status']=='OK'}
            for key,old in before['pairs'].items():
                cur=after['pairs'][key]
                if old['chain_hash']!=cur['chain_hash'] or old['computed_hash']!=cur['computed_hash']:raise RuntimeError('Existing chain/computed row changed')
                if any(r not in cur['cache_rows'] for r in old['cache_rows']):raise RuntimeError('Existing cache row changed')
                if any(r not in cur['surface_rows'] for r in old['surface_rows']):raise RuntimeError('Existing surface row changed')
            for ticker,byday in before['counts'].items():
                for day in set(byday)|set(after['counts'][ticker]):
                    if after['counts'][ticker].get(day,0)!=byday.get(day,0)+sum(k[:2]==(ticker,day) for k in inserted):raise RuntimeError('Population preservation failed')
            quality={'written_rows':0,'incomplete_without_quality':0,'blank_source':0,'null_greek_rows':0,'pending_iv_pairs':0}
            with closing(g.ro(DB)) as c:
                for key in inserted:
                    r=c.execute('SELECT iv,delta,gamma,theta,vega,greeks_quality,greeks_source FROM chain_snapshots WHERE ticker=? AND quote_date=? AND option_symbol=?',key).fetchone()
                    if not r:raise RuntimeError('Inserted exact contract disappeared')
                    missing=any(x is None for x in r[:5]);quality['written_rows']+=1;quality['null_greek_rows']+=missing;quality['incomplete_without_quality']+=missing and not bool(r[5]);quality['blank_source']+=not bool(r[6])
                for ticker,day in {(k[0],k[1]) for k in inserted}:quality['pending_iv_pairs']+=c.execute("SELECT COUNT(*) FROM phantom_maintenance_pairs WHERE ticker=? AND quote_date=? AND status='PENDING_IV'",(ticker,day)).fetchone()[0]
            if quality['incomplete_without_quality'] or quality['blank_source'] or quality['pending_iv_pairs']:raise RuntimeError('Incomplete exact-key finalization')
            g.save(folder/'AFTER.json',after);exclusions=[p for p in prior if p['status']!='OK']
            progress(status='COMPLETE_WITH_EXCLUSIONS' if exclusions else 'COMPLETE',final_quality=quality,existing_rows_unchanged=True,other_date_counts_unchanged=True,exclusions=exclusions,local=local,cumulative_reserved=len(budget.records),provider_consumed_known=sum(float(r.get('provider_consumed') or 0) for r in budget.records.values()),finished=g.now());return 0
    except Exception as error:
        progress(status='STOPPED',error=type(error).__name__+': '+str(error),finished=g.now());print(json.dumps(state),flush=True);return 1

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--execute',action='store_true');raise SystemExit(run(parser.parse_args().execute))
