"""ACK 13 Nov 2026: two-session, insert-only PHANTOM repair; no pipeline.

Request validation/bounded pagination follows the exercised October guarded
adapter. Calculations remain owned by scripts.phantom_maintenance and the IV
snapshot owner. NO_DATA is final; no automatic HTTP retries or aliases guessed.
"""
from __future__ import annotations
import argparse,csv,gzip,hashlib,json,math,os,re,shutil,sqlite3,subprocess,sys,time
from contextlib import closing,contextmanager
from datetime import date,datetime,timedelta,timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
DAYS=('2026-10-20','2026-11-09')
CAP=30000
PAGE=1000
ALIASES={'BF.B':'BFB','BRK.B':'BRKB','MOG.A':'MOGA'}
EXTERNAL=Path(r'C:\Users\ACKVerissimo\Documents\Codex\2026-07-24\a')
JOB='PHANTOM_GUARDED_20261113_20OCT_09NOV'
# ACK 13 Nov: preserve this exact pre-existing sample and flag disagreement.
# This is not permission to suppress other cache conflicts or overwrite values.
APPROVED_CACHE_PRESERVATIONS={('VICI','2026-10-20'):.22746940176152292}
# Operational file-sharing retry only. No provider request is repeated.
SUMMARY_REPLACE_DELAYS_SECONDS=(.1,.2,.4,.8,1.6)

class MappingFailure(RuntimeError):pass

def now():return datetime.now(timezone.utc).isoformat()
def digest(value):return hashlib.sha256(value).hexdigest()
def encoded(value):return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def save(path,value):
    path=Path(path);temp=path.with_name(path.name+'.'+str(os.getpid())+'.tmp')
    with temp.open('wb') as f:f.write(encoded(value));f.flush();os.fsync(f.fileno())
    for attempt in range(len(SUMMARY_REPLACE_DELAYS_SECONDS)+1):
        try:
            os.replace(temp,path)
            return
        except OSError as error:
            # Windows readers/AV may briefly deny atomic replacement. Keep the
            # fsynced temp and old destination intact; never unlink either.
            if getattr(error,'winerror',None) not in (5,32,33) or attempt==len(SUMMARY_REPLACE_DELAYS_SECONDS):
                raise
            time.sleep(SUMMARY_REPLACE_DELAYS_SECONDS[attempt])

def checked_days(value):
    days=[x.strip() for x in value.split(',') if x.strip()]
    if sorted(days)!=sorted(DAYS) or len(days)!=2:raise ValueError('Only ACK-approved 20 October and 9 November; 12 November prohibited')
    return list(DAYS)

def roster(path):
    with Path(path).open(encoding='utf-8-sig',newline='') as f:
        reader=csv.DictReader(f);col=next(c for c in reader.fieldnames if c.lower() in ('ticker','symbol'))
        values={str(r.get(col) or '').strip().upper() for r in reader}
    return sorted(t for t in values if re.fullmatch(r'[A-Z][A-Z0-9.\-]{0,9}',t))

def params(day,offset):
    if day not in DAYS:raise ValueError('Request outside approved sessions')
    d=date.fromisoformat(day)
    return {'date':day,'from':str(d+timedelta(days=7)),'to':str(d+timedelta(days=60)),
        'strikeLimit':40,'range':'all','minOpenInterest':1,'nonstandard':'false','limit':PAGE,'offset':offset}

def request_key(ticker,day,offset):
    # Match the existing durable archives exactly, including JSON whitespace.
    return digest(json.dumps([ticker,params(day,offset)],sort_keys=True).encode())

class Budget:
    def __init__(self,folder,cap,allowed_days=None):
        self.folder=Path(folder);self.cap=cap;self.records={}
        self.allowed_days=set(DAYS if allowed_days is None else allowed_days)
        if '2026-11-12' in self.allowed_days:raise ValueError('12 November remains deferred')
        if cap<=0 or cap>CAP:raise ValueError('Invalid cumulative credit cap')
        self.path=self.folder/'BUDGET.json';self.journal=self.folder/'BUDGET.jsonl'
        summary=json.loads(self.path.read_text()) if self.path.exists() else None
        if summary and summary['cap']!=cap:raise RuntimeError('CAP_CHANGED')
        if self.journal.exists():
            for line in self.journal.read_text(encoding='utf-8').splitlines():
                r=json.loads(line)
                if r['day'] not in self.allowed_days:raise RuntimeError('Journal date outside scope')
                self.records[r['key']]=r
        if summary and summary['reserved']>len(self.records):raise RuntimeError('Budget journal missing reservations')
        if len(self.records)>cap:raise RuntimeError('CAP_ALREADY_EXCEEDED')
    def persist(self,r):
        self.folder.mkdir(parents=True,exist_ok=True)
        with self.journal.open('a',encoding='utf-8') as f:f.write(json.dumps(r)+'\n');f.flush();os.fsync(f.fileno())
        save(self.path,{'cap':self.cap,'reserved':len(self.records),'updated':now(),
            'provider_consumed_known':sum(float(x.get('provider_consumed') or 0) for x in self.records.values()),
            'unresolved_reservations':sum(x['status']!='RECEIVED' for x in self.records.values())})
    def reserve(self,key,ticker,day,offset):
        if day not in self.allowed_days:raise RuntimeError('Request date outside scope')
        old=self.records.get(key)
        if old:
            if old['status']!='RECEIVED':raise RuntimeError('UNCERTAIN prior paid request; no retry')
            return old,False
        if len(self.records)+1>self.cap:raise RuntimeError('CUMULATIVE_CREDIT_CAP_REACHED')
        r={'key':key,'ticker':ticker,'day':day,'offset':offset,'status':'RESERVED','started':now(),'reserved_credits':1}
        self.records[key]=r;self.persist(r)
        return r,True

def is_symbol_error(payload):
    msg=str(payload.get('data',{}).get('errmsg','')).lower()
    return payload.get('http') in (400,404) and (any(x in msg for x in
        ('invalid symbol','unknown symbol','symbol not found','invalid ticker','unknown ticker','ticker not found',
         'invalid option symbol','unknown option symbol','option symbol not found'))
        or ('symbol' in msg and 'does not exist' in msg))

def check_identity(ticker,actual,symbol):
    m=re.fullmatch(r'([A-Z0-9.]+)(\d{6})([CP])(\d{8})',str(symbol))
    allowed={ticker,ALIASES.get(ticker,ticker)}
    if actual not in allowed or not m or m[1] not in allowed:
        raise MappingFailure(f'Unverified identity: requested={ticker}, underlying={actual}, OCC={symbol}')

def validate(data,ticker,day,offset):
    symbols=data.get('optionSymbol')
    if not isinstance(symbols,list) or len(symbols)>PAGE or len(set(symbols))!=len(symbols):
        raise RuntimeError('Malformed/duplicate/oversized page')
    for field in ('underlying','expiration','side','strike','updated'):
        if not isinstance(data.get(field),list) or len(data[field])!=len(symbols):raise RuntimeError('Unequal identity/time arrays: '+field)
    p=params(day,offset)
    for i,symbol in enumerate(symbols):
        check_identity(ticker,data['underlying'][i],symbol)
        m=re.fullmatch(r'([A-Z0-9.]+)(\d{6})([CP])(\d{8})',symbol)
        expiry=datetime.fromtimestamp(data['expiration'][i],ZoneInfo('America/New_York')).date()
        updated=datetime.fromtimestamp(data['updated'][i],ZoneInfo('America/New_York')).date()
        if str(updated)!=day or not p['from']<=str(expiry)<=p['to'] or expiry.strftime('%y%m%d')!=m[2]:
            raise RuntimeError('Quote/expiry timestamp does not match requested session or OCC')
        if data['side'][i] != ('call' if m[3]=='C' else 'put') or round(float(data['strike'][i])*1000)!=int(m[4]):
            raise RuntimeError('OCC strike/side mismatch')
    return len(symbols)

def read_receipt(record):
    path=Path(record['raw'])
    raw=path.read_bytes()
    if record.get('raw_sha256') and digest(raw)!=record['raw_sha256']:raise RuntimeError('RAW_RECEIPT_HASH_MISMATCH')
    return json.loads(gzip.decompress(raw))

def checked_payload(payload,record):
    charge=record.get('provider_consumed')
    if charge is None or not math.isfinite(float(charge)) or not 0<=float(charge)<=1:
        raise RuntimeError('PROVIDER_CHARGE_MISSING_OR_EXCEEDS_BOUNDED_PAGE_RESERVATION')
    if is_symbol_error(payload):raise MappingFailure(str(payload['data'].get('errmsg','Symbol not found')))
    if payload['http'] not in (200,203,404) or payload.get('data',{}).get('s') not in ('ok','no_data'):
        raise RuntimeError('PROVIDER_SYSTEMIC_FAILURE_HTTP_'+str(payload['http']))
    return payload['data']

def get_page(session,budget,ticker,day,offset):
    key=request_key(ticker,day,offset);r,fresh=budget.reserve(key,ticker,day,offset)
    if fresh:
        # Exactly one request, never retry or redirect; one 1,000-row historical
        # page reserves one credit. Unexpected/missing billing evidence stops.
        response=session.get('https://api.marketdata.app/v1/options/chain/'+ticker+'/',
            params=params(day,offset),timeout=(15,60),allow_redirects=False)
        try:data=response.json();body={}
        except ValueError:data={'s':'error','errmsg':'NON_JSON_RESPONSE'};body={'body_text':response.text[:5000]}
        payload={'http':response.status_code,'headers':{k:v for k,v in response.headers.items()
            if k.lower().startswith('x-api-ratelimit-')},'data':data,**body}
        raw=gzip.compress(encoded(payload));path=budget.folder/(key+'.json.gz')
        with path.open('xb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
        r.update(status='RECEIVED',raw=str(path),raw_sha256=digest(raw),finished=now(),
            provider_consumed=response.headers.get('X-Api-Ratelimit-Consumed'))
        budget.persist(r)
    return checked_payload(read_receipt(r),r)

def install_chain_guard(c,keys):
    c.execute('CREATE TEMP TABLE IF NOT EXISTS approved_new_keys(ticker,quote_date,option_symbol,PRIMARY KEY(ticker,quote_date,option_symbol))')
    c.execute('DELETE FROM approved_new_keys')
    c.executemany('INSERT INTO approved_new_keys VALUES(?,?,?)',keys)
    c.executescript('''
      CREATE TEMP TRIGGER IF NOT EXISTS protect_chain_update BEFORE UPDATE ON main.chain_snapshots
      WHEN NOT EXISTS(SELECT 1 FROM approved_new_keys k WHERE k.ticker=OLD.ticker AND k.quote_date=OLD.quote_date AND k.option_symbol=OLD.option_symbol)
      BEGIN SELECT RAISE(ABORT,'PRE_EXISTING_CHAIN_UPDATE_PROHIBITED'); END;
      CREATE TEMP TRIGGER IF NOT EXISTS protect_chain_delete BEFORE DELETE ON main.chain_snapshots
      BEGIN SELECT RAISE(ABORT,'CAPTURED_CHAIN_DELETE_PROHIBITED'); END;
      CREATE TEMP TRIGGER IF NOT EXISTS protect_chain_insert BEFORE INSERT ON main.chain_snapshots
      WHEN NOT EXISTS(SELECT 1 FROM approved_new_keys k WHERE k.ticker=NEW.ticker AND k.quote_date=NEW.quote_date AND k.option_symbol=NEW.option_symbol)
      BEGIN SELECT RAISE(ABORT,'CHAIN_INSERT_OUTSIDE_APPROVED_KEYS'); END;''')

def ro(db):
    c=sqlite3.connect(Path(db).resolve().as_uri()+'?mode=ro',uri=True,timeout=30)
    c.execute('PRAGMA query_only=ON');return c

def scoped_no_data(c,days):
    result=set()
    # This small audit table is not the 82 GB chain table; chains are always
    # queried by ticker/date. Match scope, never retry final same-scope NO_DATA.
    for ticker,day,raw in c.execute("SELECT ticker,quote_date,params_json FROM backfill_audit WHERE quote_date IN (?,?) AND status='NO_DATA'",days):
        p=json.loads(raw);expected=params(day,0)
        if all(p.get(k)==expected[k] for k in ('date','from','to','strikeLimit','range','minOpenInterest')):
            result.add((ticker,day))
    return result

def make_plan(db,tickers):
    output=[]
    with closing(ro(db)) as c:
        no_data=scoped_no_data(c,DAYS)
        for day in DAYS:
            present={};missing=[];final_no_data=[]
            for ticker in tickers:
                n=c.execute('SELECT COUNT(*) FROM chain_snapshots WHERE ticker=? AND quote_date=?',(ticker,day)).fetchone()[0]
                if n:present[ticker]=n
                elif (ticker,day) in no_data:final_no_data.append(ticker)
                else:missing.append(ticker)
            output.append({'session':day,'universe':len(tickers),'present':present,'missing':missing,
                'final_no_data':final_no_data,'rows_before':sum(present.values())})
    return output

def import_saved(budget,external):
    imported=0
    for journal in sorted(Path(external).glob('*BUDGET.jsonl')):
        latest={}
        for line in journal.read_text(encoding='utf-8-sig').splitlines():
            r=json.loads(line)
            if r.get('day') in DAYS:latest[r['key']]=r
        for key,r in latest.items():
            if key!=request_key(r['ticker'],r['day'],r['offset']):raise RuntimeError('Prior receipt scope/key mismatch')
            if r['status']!='RECEIVED':raise RuntimeError('UNCERTAIN saved paid request; no repeat')
            payload=read_receipt(r)
            try:
                data=checked_payload(payload,r)
                if data['s']=='ok':validate(data,r['ticker'],r['day'],r['offset'])
            except MappingFailure:pass
            if key in budget.records:
                if read_receipt(budget.records[key])['data']!=payload['data']:raise RuntimeError('Conflicting saved response bodies')
                continue
            record,fresh=budget.reserve(key,r['ticker'],r['day'],r['offset'])
            source=Path(r['raw']);dest=budget.folder/(key+'.json.gz')
            with dest.open('xb') as f:f.write(source.read_bytes());f.flush();os.fsync(f.fileno())
            record.update(status='RECEIVED',raw=str(dest),raw_sha256=digest(dest.read_bytes()),
                provider_consumed=r.get('provider_consumed'),imported_from=str(journal))
            budget.persist(record);imported+=1
    return imported

def disk_guard(db):
    free=shutil.disk_usage(Path(db).parent).free
    if free<15*1024**3:raise RuntimeError('DISK_BELOW_15_GIB')
    return free

def writer_guard():
    command="Get-CimInstance Win32_Process | Where-Object {$_.ProcessId -notin @("+str(os.getpid())+','+str(os.getppid())+") -and $_.Name -match '^python(w)?\\.exe$' -and $_.CommandLine -match 'orchestrator|phantom|backfill|greek|maintenance'} | Select-Object ProcessId,CommandLine | ConvertTo-Json -Compress"
    result=subprocess.run(['powershell','-NoProfile','-NonInteractive','-Command',command],capture_output=True,text=True,check=True)
    if result.stdout.strip():raise RuntimeError('COMPETING_PIPELINE_OR_PHANTOM_WRITER: '+result.stdout[:500])

def global_quarantine(external):
    q={}
    for path in sorted(Path(external).glob('*MAPPING_FAILURES*.json')):
        payload=json.loads(path.read_text(encoding='utf-8-sig'))
        for r in payload.get('failures',[]):
            if r.get('ticker'):q[r['ticker']]=r.get('reason','Previously quarantined mapping')
    return q

def fetch_pair(session,budget,ticker,day):
    from scripts.phantom_database import normalize_marketdata_chain
    output=[];seen=set();offset=0
    while True:
        data=get_page(session,budget,ticker,day,offset)
        if data['s']=='no_data':break
        n=validate(data,ticker,day,offset)
        if seen.intersection(data['optionSymbol']):raise RuntimeError('Pagination overlap; offset ignored')
        seen.update(data['optionSymbol'])
        rows=normalize_marketdata_chain(data,ticker,day)
        if len(rows)!=n:raise RuntimeError('Normalized row conservation failed')
        for i,row in enumerate(rows):
            # Keep raw provider numeric agreement and canonical/provider lineage.
            raw={k:data[k][i] for k in data if isinstance(data[k],list) and len(data[k])==n}
            raw.update(canonical_ticker=ticker,provider_underlying=data['underlying'][i],
                backfill_job=JOB,request_key=request_key(ticker,day,offset),mapping_policy='EXACT_OR_EXPLICIT_VERIFIED_ALIAS')
            row['raw_json']=json.dumps(raw,allow_nan=False)
            row['underlying']=ticker
        output.extend(rows)
        if n<PAGE:break
        offset+=PAGE
    return output

def insert_pair(db,rows):
    if not rows:return 0
    from scripts.phantom_maintenance import complete_greeks_and_queue_iv
    pair={(r['ticker'],r['quote_date']) for r in rows}
    if len(pair)!=1 or next(iter(pair))[1] not in DAYS:raise RuntimeError('Insert scope invalid')
    ticker,day=next(iter(pair));keys=[(ticker,day,r['option_symbol']) for r in rows]
    if len(set(keys))!=len(keys):raise RuntimeError('Duplicate identities before insert')
    with closing(sqlite3.connect(db,timeout=30)) as c:
        install_chain_guard(c,keys)
        # Even auxiliary pre-existing computed records must not be overwritten.
        c.execute('''CREATE TEMP TRIGGER protect_existing_computed BEFORE UPDATE ON main.options_greeks_history
          BEGIN SELECT RAISE(ABORT,'EXISTING_COMPUTED_ROW_UPDATE_PROHIBITED'); END''')
        c.execute('BEGIN IMMEDIATE')
        try:
            if c.execute('SELECT 1 FROM chain_snapshots WHERE ticker=? AND quote_date=? LIMIT 1',(ticker,day)).fetchone():
                raise RuntimeError('Pair appeared after plan; existing captures preserved')
            fields=list(rows[0]);sql='INSERT INTO chain_snapshots('+','.join(fields)+') VALUES('+','.join('?' for _ in fields)+')'
            c.executemany(sql,[[r.get(k) for k in fields] for r in rows])
            complete_greeks_and_queue_iv(c,rows)
            # Failure/unavailable is explicit provenance, never a fabricated
            # vendor/computed numeric value. Only this transaction's new keys.
            c.execute("UPDATE chain_snapshots SET greeks_source='UNAVAILABLE_UNASSESSED' WHERE ticker=? AND quote_date=? AND COALESCE(TRIM(greeks_source),'')=''",(ticker,day))
            bad=c.execute("SELECT COUNT(*) FROM chain_snapshots WHERE ticker=? AND quote_date=? AND COALESCE(TRIM(greeks_quality),'')=''",(ticker,day)).fetchone()[0]
            if bad:raise RuntimeError('Unlabelled Greek quality after exact-key completion')
            c.commit()
        except Exception:c.rollback();raise
    return len(rows)

def derive_pair(db,cache,ticker,day):
    """Reuse IV calculation owner, but insert only; no global pending drain."""
    import pandas as pd
    from scripts.finalize_phantom_weekly_snapshot import CHAIN_SELECT,_surface_and_atm
    with closing(ro(db)) as c:
        c.row_factory=sqlite3.Row
        rows=[dict(r) for r in c.execute(CHAIN_SELECT+' WHERE ticker=? AND quote_date=?',(ticker,day))]
    if not rows:raise RuntimeError('Cannot derive an absent written pair')
    surface,atm=_surface_and_atm(pd.DataFrame(rows),day,now())
    expected=None if atm.empty else float(atm.iloc[0]['iv'])
    discrepancy=None
    with closing(sqlite3.connect(cache,timeout=30)) as c:
        existing=c.execute('SELECT atm_iv FROM iv_history WHERE ticker=? AND sample_date=?',(ticker,day)).fetchone()
        if existing and (expected is None or existing[0]!=expected):
            if expected is None or APPROVED_CACHE_PRESERVATIONS.get((ticker,day))!=existing[0]:
                raise RuntimeError('PRE_EXISTING_IV_CACHE_CONFLICT_PRESERVED')
            discrepancy={'status':'IV_CACHE_DISCREPANCY_PRESERVED','ticker':ticker,'session':day,
                'existing_atm_iv':existing[0],'derived_atm_iv':expected,
                'approval':'ACK 2026-11-13; existing cache preserved; derived surface remains separate'}
        if expected is not None:
            c.execute("INSERT OR IGNORE INTO iv_history(ticker,sample_date,atm_iv,source,updated_at) VALUES(?,?,?,'phantom_history',?)",(ticker,day,expected,now()))
            # Never move an existing metadata row backward to a historical date.
            c.execute('INSERT OR IGNORE INTO iv_cache_meta(ticker,last_full_build,last_refresh) VALUES(?,NULL,?)',(ticker,day))
        c.commit()
    with closing(sqlite3.connect(db,timeout=30)) as c:
        c.executemany('''INSERT OR IGNORE INTO iv_surface_history(ticker,quote_date,dte_bucket,side,contract_count,
          atm_iv,median_iv,iv_entropy,skew_25d,put_call_iv_spread,median_spread_pct,total_open_interest,total_volume,created_at_utc)
          VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',surface)
        c.execute('''UPDATE phantom_maintenance_pairs SET status=?,updated_at_utc=?,last_error=?,attempts=attempts+1
          WHERE ticker=? AND quote_date=? AND status='PENDING_IV' ''',
          ('COMPLETE' if expected is not None else 'IV_UNAVAILABLE',now(),
           json.dumps(discrepancy,sort_keys=True) if discrepancy else (None if expected is not None else 'NO_VALID_ATM_INPUT'),ticker,day))
        c.commit()
    return {'ticker':ticker,'session':day,'chain_rows':len(rows),'surface_rows':len(surface),
        'state':'COMPLETE' if expected is not None else 'IV_UNAVAILABLE'}

def all_date_counts(db,tickers):
    """Covering index only, ticker-scoped: counts outside this job must not move."""
    result={}
    with closing(ro(db)) as c:
        for i,ticker in enumerate(tickers):
            result[ticker]={d:n for d,n in c.execute('SELECT quote_date,COUNT(*) FROM chain_snapshots INDEXED BY idx_chain_ticker_date WHERE ticker=? GROUP BY quote_date',(ticker,))}
            if i and i%500==0:print('Count preservation scan',i,'/',len(tickers),flush=True)
    return result

def pair_hash(db,ticker,day):
    h=hashlib.sha256()
    with closing(ro(db)) as c:
        for row in c.execute('SELECT * FROM chain_snapshots WHERE ticker=? AND quote_date=? ORDER BY option_symbol',(ticker,day)):
            h.update(json.dumps(row,default=str,allow_nan=False).encode());h.update(b'\n')
    return h.hexdigest()

def write_audit(db,ticker,day,status,rows):
    p=params(day,0);key=digest(json.dumps([ticker,p,'complete_pair'],sort_keys=True).encode())
    with closing(sqlite3.connect(db,timeout=30)) as c:
        c.execute('''INSERT OR IGNORE INTO backfill_audit(query_key,ticker,quote_date,params_json,status,rows_written,
          estimated_credits,error,started_at_utc,finished_at_utc) VALUES(?,?,?,?,?,?,?,?,?,?)''',
          (key,ticker,day,json.dumps(p,sort_keys=True),status,rows,max(1,math.ceil(rows/PAGE)),'',now(),now()))
        c.commit()

def read_pairs(path):
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []

def append_pair(path,value):
    with path.open('a',encoding='utf-8') as f:f.write(json.dumps(value)+'\n');f.flush();os.fsync(f.fileno())

def verify_quality(db,cache,pairs):
    counts={'pairs':0,'rows':0,'missing':{g:0 for g in ('iv','delta','gamma','theta','vega')},
        'incomplete_without_quality':0,'blank_source':0,'blank_quality':0,'missing_underlying':0,
        'iv_complete':0,'iv_unavailable':0,'pending_iv':0,'quality_states':{},'iv_cache_discrepancies':[]}
    with closing(ro(db)) as c:
        for p in pairs:
            if p['status']!='OK':continue
            ticker,day=p['ticker'],p['session']
            rows=c.execute('SELECT iv,delta,gamma,theta,vega,greeks_source,greeks_quality,underlying_price FROM chain_snapshots WHERE ticker=? AND quote_date=?',(ticker,day)).fetchall()
            if len(rows)!=p['rows']:raise RuntimeError('Final written population mismatch')
            for r in rows:
                missing=False
                for i,g in enumerate(counts['missing']):
                    if r[i] is None:counts['missing'][g]+=1;missing=True
                counts['blank_source']+=not bool(str(r[5] or '').strip())
                counts['blank_quality']+=not bool(str(r[6] or '').strip())
                counts['incomplete_without_quality']+=missing and not bool(str(r[6] or '').strip())
                counts['missing_underlying']+=r[7] is None or r[7]<=0
                state=str(r[6]);counts['quality_states'][state]=counts['quality_states'].get(state,0)+1
            q=c.execute('SELECT status,last_error FROM phantom_maintenance_pairs WHERE ticker=? AND quote_date=?',(ticker,day)).fetchone()
            if q and q[1] and 'IV_CACHE_DISCREPANCY_PRESERVED' in q[1]:
                counts['iv_cache_discrepancies'].append(json.loads(q[1]))
            if not q or q[0] not in ('COMPLETE','IV_UNAVAILABLE'):counts['pending_iv']+=1
            else:counts['iv_complete' if q[0]=='COMPLETE' else 'iv_unavailable']+=1
            if pair_hash(db,ticker,day)!=p['chain_sha256']:raise RuntimeError('Written chain changed after its receipt')
            counts['pairs']+=1;counts['rows']+=len(rows)
    if counts['incomplete_without_quality'] or counts['pending_iv'] or counts['blank_source'] or counts['blank_quality']:
        raise RuntimeError('Final Greek/provenance/IV completeness failed: '+str(counts))
    return counts

def execute(args,plans,tickers,db,cache,folder):
    import requests
    from dotenv import dotenv_values
    folder.mkdir(parents=True,exist_ok=True)
    state_path=folder/'JOB.json';pair_path=folder/'PAIRS.jsonl'
    state={'status':'PREFLIGHT','pid':os.getpid(),'sessions':list(DAYS),'cap':args.credit_cap,
        'started':now(),'scope':'standard contracts; 7-60 DTE; strikeLimit 40; OI>=1',
        'pipeline_run':False,'provider':'MarketData only'}
    budget=Budget(folder,args.credit_cap)
    def progress(**fields):
        state.update(fields,updated=now(),reserved_credits=len(budget.records),
            provider_consumed_known=sum(float(r.get('provider_consumed') or 0) for r in budget.records.values()),
            disk_free_GiB=round(disk_guard(db)/1024**3,2))
        save(state_path,state)
    try:
        disk_guard(db);writer_guard()
        # Use the same OS-held lock as previous approved backfills; no stale-file deletion.
        import msvcrt
        with (EXTERNAL/'PHANTOM_APPROVED_20261017.lock').open('a+b') as lock:
            lock.seek(0)
            if not lock.read(1):lock.write(b'0');lock.flush()
            lock.seek(0);msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
            progress(status='PRESERVATION_BASELINE')
            before_path=folder/'BEFORE.json'
            if before_path.exists():before=json.loads(before_path.read_text())
            else:
                before={'counts':all_date_counts(db,tickers),'plans':plans,'existing_hashes':{
                    day+'|'+t:pair_hash(db,t,day) for item in plans for day in [item['session']] for t in item['present']}}
                save(before_path,before)
            plans=before['plans']  # Resume the original missing set, not a renewed scope.
            imported=import_saved(budget,EXTERNAL)
            # Validate every current receipt before another request, including imports.
            for key,r in budget.records.items():
                if key!=request_key(r['ticker'],r['day'],r['offset']) or r['status']!='RECEIVED':
                    raise RuntimeError('UNCERTAIN current receipt; no provider calls')
                try:
                    payload=checked_payload(read_receipt(r),r)
                    if payload['s']=='ok':validate(payload,r['ticker'],r['day'],r['offset'])
                except MappingFailure:pass
            quarantine=global_quarantine(EXTERNAL)
            prior=read_pairs(pair_path);done={(r['ticker'],r['session']) for r in prior}
            for p in prior:
                if p['status']=='SKIPPED_MAPPING':quarantine[p['ticker']]=p['reason']
            token=os.environ.get('MARKETDATA_API_KEY') or dotenv_values(ROOT/'.env').get('MARKETDATA_API_KEY')
            if not token:raise RuntimeError('MarketData credential unavailable')
            session=requests.Session();session.headers['Authorization']='Token '+token
            progress(status='RUNNING',initial_plans=plans,imported_responses=imported)
            for item in plans:
                day=item['session'];available='SPY' in item['present'] or any(
                    p['ticker']=='SPY' and p['session']==day and p['status']=='OK' for p in prior)
                for i,ticker in enumerate(sorted(item['missing'],key=lambda t:(t!='SPY',t!='AAPL',t))):
                    if (ticker,day) in done:continue
                    if i%25==0:writer_guard();progress(current_ticker=ticker,current_session=day)
                    disk_guard(db)
                    if ticker in quarantine:
                        result={'ticker':ticker,'session':day,'status':'SKIPPED_MAPPING','rows':0,'reason':quarantine[ticker]}
                    else:
                        # Re-check immediately before paid request. Existing pairs are never fetched.
                        with closing(ro(db)) as c:
                            existing=c.execute('SELECT raw_json FROM chain_snapshots WHERE ticker=? AND quote_date=?',(ticker,day)).fetchall()
                        if existing:
                            if all(json.loads(r[0] or '{}').get('backfill_job')==JOB for r in existing):
                                result={'ticker':ticker,'session':day,'status':'OK','rows':len(existing),
                                    'recovered_local_commit':True,'chain_sha256':pair_hash(db,ticker,day)}
                            else:raise RuntimeError('New external capture appeared after baseline; preserved, stop for reconciliation')
                        else:
                            try:rows=fetch_pair(session,budget,ticker,day)
                            except MappingFailure as error:
                                quarantine[ticker]=str(error)
                                result={'ticker':ticker,'session':day,'status':'SKIPPED_MAPPING','rows':0,'reason':str(error)}
                            else:
                                if not rows and ticker in ('SPY','AAPL') and not available:
                                    raise RuntimeError('SESSION_NOT_AVAILABLE_SENTINEL_'+day)
                                n=insert_pair(db,rows) if rows else 0
                                available=available or bool(n)
                                result={'ticker':ticker,'session':day,'status':'OK' if n else 'NO_DATA','rows':n}
                                if n:result['chain_sha256']=pair_hash(db,ticker,day)
                        if result['status'] in ('OK','NO_DATA'):write_audit(db,ticker,day,result['status'],result['rows'])
                    append_pair(pair_path,result);done.add((ticker,day));prior.append(result)
                    if result['status']=='OK':
                        local=derive_pair(db,cache,ticker,day)
                    if len(prior)%100==0:
                        progress(completed_pairs=len(prior),written_rows=sum(p['rows'] for p in prior))
                        print(json.dumps({'pairs_processed':len(prior),'reserved':len(budget.records),'session':day}),flush=True)
            # Local-only recovery of any committed pair whose IV acknowledgement was interrupted.
            progress(status='FINAL_LOCAL_VERIFICATION')
            for p in prior:
                if p['status']=='OK':
                    with closing(ro(db)) as c:q=c.execute('SELECT status FROM phantom_maintenance_pairs WHERE ticker=? AND quote_date=?',(p['ticker'],p['session'])).fetchone()
                    if not q or q[0] not in ('COMPLETE','IV_UNAVAILABLE'):derive_pair(db,cache,p['ticker'],p['session'])
            quality=verify_quality(db,cache,prior)
            after=all_date_counts(db,tickers)
            written={(p['ticker'],p['session']):p['rows'] for p in prior if p['status']=='OK'}
            for ticker,byday in before['counts'].items():
                for day in set(byday)|set(after[ticker]):
                    expected=byday.get(day,0)+written.get((ticker,day),0)
                    if after[ticker].get(day,0)!=expected:raise RuntimeError('Before/after count preservation failed: '+ticker+'/'+day)
            for key,h in before['existing_hashes'].items():
                day,ticker=key.split('|',1)
                if pair_hash(db,ticker,day)!=h:raise RuntimeError('Pre-existing pair hash changed')
            final_plan=make_plan(db,tickers);excluded={(p['ticker'],p['session']) for p in prior if p['status']=='SKIPPED_MAPPING'}
            for item in final_plan:
                unexpected=[t for t in item['missing'] if (t,item['session']) not in excluded]
                if unexpected:raise RuntimeError('Unexpected final missing tickers: '+str(unexpected))
            failures=[p for p in prior if p['status']=='SKIPPED_MAPPING']
            summary=[]
            for day in DAYS:
                rr=[p for p in prior if p['session']==day]
                requests_for_day=[r for r in budget.records.values() if r['day']==day]
                summary.append({'session':day,'requests':len(requests_for_day),'OK':sum(p['status']=='OK' for p in rr),
                    'NO_DATA':sum(p['status']=='NO_DATA' for p in rr),'ERROR':0,'mapping_exclusions':sum(p['status']=='SKIPPED_MAPPING' for p in rr),
                    'rows_written':sum(p['rows'] for p in rr),'reserved_credits':len(requests_for_day),
                    'provider_consumed_known':sum(float(r.get('provider_consumed') or 0) for r in requests_for_day)})
            save(folder/'AFTER_COUNTS.json',after)
            progress(status='COMPLETE_WITH_EXCLUSIONS' if failures else 'COMPLETE',sessions_summary=summary,
                mapping_failures=failures,final_quality=quality,final_plans=final_plan,
                existing_pair_hashes_unchanged=True,other_date_counts_unchanged=True,finished=now())
            return 0
    except Exception as error:
        state.update(status='STOPPED',error=type(error).__name__+': '+str(error),finished=now(),reserved_credits=len(budget.records))
        save(state_path,state);print(json.dumps({'status':'STOPPED','error':state['error'],'reserved':len(budget.records)}),flush=True)
        return 1

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=['plan','execute'])
    p.add_argument('--sessions',required=True);p.add_argument('--credit-cap',type=int,default=CAP)
    p.add_argument('--workers',type=int,default=1,help='Compatibility argument: serialized bounded requests only')
    args=p.parse_args(argv);checked_days(args.sessions)
    if not 0<args.credit_cap<=CAP:p.error('Cumulative cap must be <=30000')
    db=ROOT/'data/phantom/phantom_history.db';cache=ROOT/'data/cache/iv_history_cache.db'
    disk_guard(db);writer_guard()
    tickers=roster(ROOT/'data/universe/polygon_liquid_universe.csv')
    plans=make_plan(db,tickers)
    print(json.dumps({'mode':args.mode,'sessions':[{'session':r['session'],'universe':r['universe'],
        'present':len(r['present']),'missing':len(r['missing']),'final_no_data':len(r['final_no_data']),'rows_before':r['rows_before']} for r in plans],
        'cap':args.credit_cap,'workers':1,'provider_calls':0}),flush=True)
    if args.mode=='plan':return 0
    return execute(args,plans,tickers,db,cache,ROOT/'Enhancements/phase0/backfill_receipts'/JOB)

if __name__=='__main__':raise SystemExit(main())
