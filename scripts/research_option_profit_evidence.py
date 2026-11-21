"""Saved-only shadow model. Read-only Phantom; new output outside saved runs.

No production hook is installed and no promotions can be enabled by this script.
Optional historical input reads HISTORICAL_TICKETS only, never Lane B records.
"""
from __future__ import annotations
import argparse,csv,hashlib,json,sqlite3,sys,time
from collections import Counter,defaultdict
from datetime import date,datetime,timedelta,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from contracts.option_profit_evidence import (VERSION,HORIZONS,LEVELS,contract,instant,
    build_windows,evaluate,MIN_TRAIN,MIN_VALIDATION)
from avshunter.shared.xnys_calendar import session_bounds
from domain.option_valuation import valuation_policy

def guard(event,args):
    if event in ('socket.connect','socket.getaddrinfo','urllib.Request','http.client.connect'):
        raise RuntimeError('NETWORK_FORBIDDEN')
    if event=='sqlite3.connect' and ('mode=ro' not in str(args[0]) or not str(args[0]).startswith('file:')):
        raise RuntimeError('READ_ONLY_DATABASE_REQUIRED')

def file_hash(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()

def db_state(db):
    result={}
    for p in (db,Path(str(db)+'-wal')):
        if not p.exists():result[str(p)]=None;continue
        s=p.stat()
        with p.open('rb') as f:header=hashlib.sha256(f.read(65536)).hexdigest()
        result[str(p)]={'bytes':s.st_size,'mtime_ns':s.st_mtime_ns,'header_sha256':header}
    return result

def identities(source,historical=None):
    index={};sources=Counter();invalid=[]
    csv.field_size_limit(64*1024*1024)
    with source.open(encoding='utf-8-sig',newline='') as f:
        for row in csv.DictReader(f):
            t=str(row.get('ticker') or '').strip();symbol=next((row[k] for k in
                ('contract_symbol','contract_occ_symbol','option_symbol') if row.get(k)),None)
            if not symbol:invalid.append({'ticker':t,'reason':'NO_SELECTED_EXACT_CONTRACT'});continue
            index.setdefault((t,symbol),[]).append({'source':'SAVED_PIPELINE_ROW','run_id':row.get('run_id'),
                'thesis_id':row.get('thesis_id'),'verdict':row.get('options_verdict')})
            sources['saved_pipeline_rows']+=1
    if historical:
        records=json.loads(historical.read_text(encoding='utf-8'))
        for r in records:
            if r.get('cohort')!='HISTORICAL_TICKETS':continue
            index.setdefault((r['ticker'],r['symbol']),[]).append({'source':'ARCHIVED_HISTORICAL_TICKET',
                'id':r['id'],'decision':r['decision']})
            sources['historical_tickets']+=1
    return index,dict(sources),invalid

def read_history(conn,ticker,symbol,start,as_of,cutoff):
    # The narrow ticker/date index fetches every chain row before testing OCC.
    # The existing PK can filter OCC in the index before fetching quote values.
    pk=[r[2] for r in conn.execute('PRAGMA index_info(sqlite_autoindex_chain_snapshots_1)')]
    index=' INDEXED BY sqlite_autoindex_chain_snapshots_1' if pk==['ticker','quote_date','option_symbol'] else ''
    rows=conn.execute('SELECT quote_date,bid,ask,bid_size,ask_size,updated_ts,created_at_utc '
        'FROM chain_snapshots'+index+' WHERE ticker=? AND quote_date>=? AND quote_date<=? AND option_symbol=? '
        'ORDER BY quote_date',(ticker,start.isoformat(),as_of.isoformat(),symbol)).fetchall()
    history={};reasons=Counter()
    for day,bid,ask,bs,az,ts,created in rows:
        reason=None;available=instant(created)
        try:
            quoted=datetime.fromtimestamp(int(ts),timezone.utc)
            close=session_bounds(date.fromisoformat(day))[1]
            if abs((quoted-close).total_seconds())>1800:reason='NOT_NEAR_SESSION_CLOSE'
        except (ValueError,TypeError,OSError,OverflowError):reason='INVALID_QUOTE_TIMESTAMP'
        if available is None:reason='RECEIPT_AVAILABILITY_UNASSESSED'
        elif available>cutoff:reason='RECEIPT_AFTER_RESEARCH_CUTOFF'
        if day in history:reason='DUPLICATE_SESSION_EXACT_CONTRACT'
        if reason:history[day]=None;reasons[reason]+=1
        else:history[day]={'bid':bid,'ask':ask,'bid_size':bs,'ask_size':az,
            'available_at':max(available,quoted).isoformat()}
    return history,{'saved_exact_rows':len(rows),'quarantine_counts':dict(reasons),
        'quote_rows_sha256':hashlib.sha256(json.dumps(rows,allow_nan=False,default=str).encode()).hexdigest()}

def run(source,database,output,*,as_of,cutoff,historical=None,lookback_days=120):
    if output.exists():raise FileExistsError('Immutable output exists; choose a new revision')
    if output.resolve().is_relative_to(ROOT):raise ValueError('Research output must be outside the production repository')
    index,source_counts,missing=identities(source,historical);policy=valuation_policy()
    source_paths=[source,ROOT/'config/governed_constants_v1.json',Path(__file__),
        ROOT/'contracts/option_profit_evidence.py']+([historical] if historical else [])
    before_hash={str(p):file_hash(p) for p in source_paths};before_db=db_state(database)
    records=[];excluded=[];aggregate=defaultdict(Counter);started=time.monotonic()
    pairs=sorted(index);reader=None
    try:
        for i,(ticker,symbol) in enumerate(pairs):
            if i%100==0:
                if reader:reader.close()
                reader=sqlite3.connect(database.resolve().as_uri()+'?mode=ro',uri=True,timeout=3)
                reader.execute('PRAGMA query_only=ON')
            c=contract(symbol)
            if not c or c['root']!=ticker:
                excluded.append({'ticker':ticker,'symbol':symbol,'reason':'UNVERIFIED_CONTRACT_ROOT_OR_MAPPING'});continue
            history,receipt=read_history(reader,ticker,symbol,as_of-timedelta(days=lookback_days),as_of,cutoff)
            for horizon in HORIZONS:
                for level in LEVELS:
                    windows=build_windows(symbol,history,as_of=as_of,horizon=horizon,threshold=level,
                        open_fee=policy['fee_usd_per_contract_open'],close_fee=policy['fee_usd_per_contract_close'])
                    result=evaluate(windows)
                    records.append({'ticker':ticker,'contract_symbol':symbol,'source_identities':index[(ticker,symbol)],
                        'horizon':horizon,'threshold':level,'receipt':receipt,'analysis':result,'windows':windows})
                    a=aggregate[f'{round(level*100)}_H{horizon}']
                    a.update(result['counts']);a['contracts']+=1;a['complete_windows']+=result['complete_n']
                    a['hits']+=result['hit_n'];a['failures']+=result['failure_n']
                    a['unassessed_or_censored']+=result['unassessed_or_censored_n']
                    a['out_of_sample_predictions']+=result['validation']['out_of_sample_n']
                    a['contracts_without_saved_quotes']+=int(not history)
            if (i+1)%100==0:print('Read exact contracts',i+1,'/',len(pairs),'seconds',round(time.monotonic()-started,1),flush=True)
    finally:
        if reader:reader.close()
    after_hash={str(p):file_hash(p) for p in source_paths};after_db=db_state(database)
    if before_hash!=after_hash or before_db!=after_db:raise ValueError('SOURCE_CHANGED_DURING_RESEARCH')
    report={'version':VERSION,'status':'SHADOW_COMPLETE_PROMOTIONS_BLOCKED','authority':'OFFLINE_SHADOW_ONLY',
        'promotion_enabled':False,'as_of_session':as_of.isoformat(),'research_cutoff_utc':cutoff.isoformat(),
        'source_counts':source_counts,'unique_contract_identities':len(pairs),'scored_contracts':len(pairs)-len(excluded),
        'missing_selected_contracts':missing,'mapping_exclusions':excluded,
        'summary':{k:dict(v) for k,v in aggregate.items()},'records':records,
        'fees':{k:policy[k] for k in ('fee_usd_per_contract_open','fee_usd_per_contract_close','fee_basis')},
        'frozen_validation':{'min_prior_nonoverlapping_exact_event_windows':MIN_TRAIN,
            'min_chronological_out_of_sample_windows':MIN_VALIDATION,'beta_prior':[1,1],
            'baseline_probability':.5,'lookback_calendar_days':lookback_days,
            'training_availability':'FULL_WINDOW_END_AND_RECEIPT_BEFORE_PREDICTION',
            'default_enable':False},
        'source_hashes_unchanged':before_hash,'database_before':before_db,'database_after':after_db,
        'providers':0,'pipeline_runs':0,'database_writes':0,'lane_b_changes':0,
        'limitations':['Daily close snapshot event, not intraday profit first passage or fill proof',
            'Fee assumptions exclude regulatory/exercise fees; not verified actual commissions',
            'Missing/late/backfilled paths can be informative and do not become failures',
            'DTE/moneyness and market regimes change even within an exact contract; not a validated row-conditional forecast',
            'No cross-contract/horizon/profit-level pooling and no delta-to-profit-probability substitution',
            'Counts across overlapping horizons are separate experiments, not independent trades',
            'No independently calibrated comparable market probability; no claimed Bayesian market edge',
            'No Lane B entry/stop/scale/roll/expiry policy reconstructed'],
        'elapsed_seconds':round(time.monotonic()-started,3)}
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('x',encoding='utf-8') as f:json.dump(report,f,separators=(',',':'),allow_nan=False)
    print(json.dumps({k:report[k] for k in ('status','source_counts','unique_contract_identities','scored_contracts','summary','elapsed_seconds')},indent=2))
    return report

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('source','database','output'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--historical',type=Path);p.add_argument('--as-of',required=True)
    p.add_argument('--cutoff-utc',required=True);a=p.parse_args()
    cutoff=instant(a.cutoff_utc)
    if cutoff is None or date.fromisoformat(a.as_of)>cutoff.date():p.error('Valid as-of and explicit UTC cutoff required')
    sys.addaudithook(guard)
    run(a.source,a.database,a.output,as_of=date.fromisoformat(a.as_of),cutoff=cutoff,historical=a.historical)

if __name__=='__main__':main()
