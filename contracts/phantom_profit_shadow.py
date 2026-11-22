"""Local forecast/outcome ledger. No network, database writes or trade authority.

Closing-reference benchmarks and contemporaneous regular-session observations
are distinct events. A benchmark can train its own future benchmark; it cannot
establish executable entry or validate a different entry clock.
"""
from __future__ import annotations
from collections import Counter,defaultdict
from contextlib import closing
from datetime import datetime,date,timezone,timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
import json,os,sqlite3,tempfile,time
from contracts.option_profit_evidence import contract,number,instant,digest,valid_quote,sessions_after
from contracts.option_profit_cohorts import decorate,forecast,POLICY
from avshunter.shared.xnys_calendar import is_xnys_session,session_bounds

SCHEMA='phantom_profit_shadow_v1'
NY=ZoneInfo('America/New_York')
def now():return datetime.now(timezone.utc)
def config(repo):
    cfg=json.loads((Path(repo)/'config/phantom_profit_shadow_v1.json').read_text(encoding='utf-8-sig'))
    if cfg['promotions_enabled'] is not False or cfg['provider_calls']!=0:raise ValueError('Shadow authority invariant')
    return cfg

def write_packet(folder,kind,body):
    from contracts.phantom_prospective_evidence import blob
    payload={'schema':SCHEMA,'kind':kind,'promotions_enabled':False,**body}
    if payload['promotions_enabled'] is not False:raise ValueError('No promotion authority')
    sha=digest(payload);payload={**payload,'content_sha256':sha};raw=blob(payload)
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True);path=folder/(kind.lower()+'-'+sha+'.json')
    fd,name=tempfile.mkstemp(prefix='.shadow-',dir=folder);temp=Path(name)
    try:
        with os.fdopen(fd,'wb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
        try:os.link(temp,path)
        except FileExistsError:
            if path.read_bytes()!=raw:raise ValueError('Corrupt immutable shadow packet')
    finally:temp.unlink(missing_ok=True)
    return {'path':str(path.resolve()),'content_sha256':sha,'kind':kind,'rows':len(payload.get('rows',[]))}

def read_packet(path,kind=None):
    p=Path(path);body=json.loads(p.read_text(encoding='utf-8'));sha=body.get('content_sha256')
    if body.get('schema')!=SCHEMA or body.get('promotions_enabled') is not False or sha!=digest({k:v for k,v in body.items() if k!='content_sha256'}):raise ValueError('Invalid shadow packet')
    if kind and body['kind']!=kind:raise ValueError('Wrong shadow packet kind')
    if p.name!=body['kind'].lower()+'-'+sha+'.json':raise ValueError('Shadow packet filename mismatch')
    return body

def identity_ok(ticker,symbol):
    c=contract(symbol)
    # Explicitly checked identities approved 17 Oct; no inferred aliases.
    return bool(c and (c['root']==ticker or {'BF.B':'BFB','BRK.B':'BRKB','MOG.A':'MOGA'}.get(ticker)==c['root']))

def load_pool(paths,cutoff,max_rows=50000):
    byid={};references=[];conflicts=set()
    for path in sorted(map(Path,paths)):
        packet=read_packet(path,'TRAINING_POOL');built=instant(packet['recorded_at_utc'])
        if built is None or built>cutoff:continue
        references.append({'path':str(path.resolve()),'content_sha256':packet['content_sha256']})
        for raw in packet['rows']:
            r=dict(raw);available=instant(r.get('training_available_at'))
            if not r.get('fit_eligible') or not r.get('cohort_key') or r.get('label') not in (0,1) or available is None or available>cutoff:continue
            if r.get('replay_only'):continue
            quoted=instant(r.get('quote_available_at'))
            if quoted is None or quoted>cutoff:continue
            r['training_available_at']=max(available,built).isoformat()
            key=r['outcome_id']
            if key in byid and any(byid[key].get(k)!=r.get(k) for k in
                ('label','entry_state','first_hit_session','net_return','shared_event_key')):conflicts.add(key)
            else:byid.setdefault(key,r)
            if len(byid)>max_rows:raise ValueError('TRAINING_POOL_LIMIT_NEEDS_COMPACTION')
    return [v for k,v in byid.items() if k not in conflicts],references,sorted(conflicts)

def _clock(phase,q,recorded,cfg):
    quoted=instant(q.get('provider_at'));received=instant(q.get('available_at'))
    if not quoted or not received or max(quoted,received)>recorded:return 'UNASSESSED',['QUOTE_AVAILABILITY_UNVERIFIED']
    day=quoted.astimezone(NY).date()
    if not is_xnys_session(day):return 'UNASSESSED',['NON_SESSION_QUOTE']
    opening,closing=session_bounds(day)
    if phase=='EVENING':
        if abs((quoted-closing).total_seconds())>cfg['close_quote_tolerance_seconds']:return 'UNASSESSED',['NOT_CLOSE_SNAPSHOT']
        latest=recorded.astimezone(NY).date()
        while not is_xnys_session(latest) or recorded<session_bounds(latest)[1]:latest-=timedelta(days=1)
        if day!=latest:return 'UNASSESSED',['STALE_REFERENCE_SESSION']
        return 'CLOSE_BENCHMARK',['REFERENCE_CLOSE_NOT_EXECUTABLE_ENTRY']
    age=(recorded-quoted).total_seconds()
    spot=instant(q.get('underlying_at'))
    if not opening<=recorded<closing or not opening<=quoted<closing or age>cfg['max_intraday_quote_age_seconds']:
        return 'UNASSESSED',['STALE_OR_OUT_OF_SESSION_ENTRY']
    if spot is None or spot>recorded or abs((spot-quoted).total_seconds())>cfg['max_spot_quote_skew_seconds']:
        return 'UNASSESSED',['ENTRY_SPOT_TIME_ALIGNMENT_UNVERIFIED']
    minute=(quoted-opening).total_seconds()/60
    return ('REGULAR_FIRST_30_MIN' if minute<=30 else 'REGULAR_MORNING' if minute<150 else 'REGULAR_AFTERNOON'),[]

def quote_from_candidate(candidate):
    q=dict(candidate.get('quote') or {})
    try:q['provider_at']=datetime.fromtimestamp(float(q['updated_ts']),timezone.utc).isoformat()
    except (KeyError,TypeError,ValueError,OverflowError,OSError):q['provider_at']=None
    q['available_at']=q.get('created_at_utc');return q

def quote_from_morning(result,live):
    # Only the already-fetched exact quote; never fetch, repair or guess a leg.
    return {'bid':live.get('live_contract_bid'),'ask':live.get('live_contract_ask'),
        'bid_size':live.get('live_contract_bid_size'),'ask_size':live.get('live_contract_ask_size'),
        'underlying_price':live.get('live_price') or result.get('live_price'),
        'provider_at':live.get('quote_provider_timestamp_utc') or live.get('selected_quote_timestamp_utc') or live.get('live_contract_quote_timestamp'),
        'available_at':live.get('quote_fetch_timestamp_utc') or live.get('live_options_fetched_at'),
        'underlying_at':live.get('underlying_nbbo_timestamp_utc'),
        'option_symbol':live.get('live_contract_symbol') or result.get('contract_symbol')}

class ShadowSession:
    def __init__(self,repo,run_id,*,store=None,database=None,pool_paths=None):
        self.repo=Path(repo);self.run_id=run_id;self.cfg=config(repo)
        self.store=Path(store) if store else self.repo/'runtime/phantom_profit_shadow'
        self.database=Path(database) if database else self.repo/'data/phantom/phantom_history.db'
        self.started=time.monotonic();self.cells=0;self.buffer=[]
        paths=pool_paths if pool_paths is not None else sorted((self.store/'training_pools').glob('training_pool-*.json'))
        if len(paths)>self.cfg['max_packet_files']:raise ValueError('POOL_PACKET_LIMIT')
        self.pool,self.pool_refs,self.conflicts=load_pool(paths,now(),self.cfg['max_pool_rows'])
        self.by_event=defaultdict(list)
        for r in self.pool:self.by_event[r['shared_event_key']].append(r)
        from domain.option_valuation import valuation_policy
        self.fees=valuation_policy()

    def begin_publication(self):
        # Provider waiting is outside the bounded LOCAL computation budget.
        self.started=time.monotonic()

    def flush(self):
        if not self.buffer:return None
        last=self.buffer[-1]
        if len({(p['phase'],p['replay_only']) for p in self.buffer})!=1:raise ValueError('Mixed capture phases')
        ref=write_packet(self.store/'forecasts','FORECASTS',
            {**last,'rows':[r for p in self.buffer for r in p['rows']]})
        self.buffer.clear();return ref

    def publish(self,candidate,q,*,phase,snapshot_id,replay_only=False,persist=True):
        if self.cells+6>self.cfg['max_forecast_cells'] or time.monotonic()-self.started>self.cfg['max_local_seconds']:
            raise ValueError('SHADOW_BOUNDED_WORK_REMAINDER')
        recorded=now();clock,reasons=_clock(phase,q,recorded,self.cfg)
        ticker=str(candidate.get('ticker') or '');symbol=candidate.get('contract_symbol') or candidate.get('contract_occ_symbol')
        if q.get('option_symbol') and q['option_symbol']!=symbol:reasons+=['EXACT_CONTRACT_MISMATCH'];clock='UNASSESSED'
        if not identity_ok(ticker,symbol):reasons+=['UNVERIFIED_CONTRACT_IDENTITY'];clock='UNASSESSED'
        quoted=instant(q.get('provider_at'));origin=quoted.astimezone(NY).date() if quoted else recorded.astimezone(NY).date()
        rows=[]
        for h in self.cfg['horizons']:
            for threshold in self.cfg['profit_levels']:
                last=sessions_after(origin,h)[-1];c=contract(symbol)
                base={'contract_symbol':symbol,'origin':origin.isoformat(),'window_end':last.isoformat(),
                    'horizon':h,'clock':'XNYS_SESSIONS','threshold':threshold,'entry':'SAVED_ASK','exit':'SAVED_BID',
                    'multiplier':100,'open_fee':self.fees['fee_usd_per_contract_open'],
                    'close_fee':self.fees['fee_usd_per_contract_close'],'side':c['side'] if c else 'UNKNOWN',
                    'event_id':f'OPTION_NET_PROFIT_GE_{round(threshold*100)}_OBSERVED_CLOSE',
                    'entry_clock':clock,'event_key':digest([symbol,h,threshold,clock]),
                    'prediction_cutoff_utc':recorded.isoformat(),'entry_available_at':q.get('available_at'),
                    'fit_eligible':False,'label':None,'state':'FORECAST_FROZEN','expiry_truncated':bool(c and c['expiry']<last)}
                row=decorate(base,ticker,q,universe_known_at=recorded.isoformat(),training_available_at=None)
                f=forecast(row,self.by_event.get(row['shared_event_key'],[]))
                why=list(reasons)
                if f['reason']:why.append(f['reason'])
                if not valid_quote(q,True):why.append('UNUSABLE_ENTRY_QUOTE')
                if base['expiry_truncated']:why.append('INSUFFICIENT_EXPIRY_RUNWAY')
                usable=clock!='UNASSESSED' and valid_quote(q,True) and not base['expiry_truncated']
                reference=clock=='CLOSE_BENCHMARK'
                row.update(forecast_id=digest([snapshot_id,ticker,symbol,h,threshold,clock,recorded.isoformat(),q]),
                    candidate_snapshot_id=snapshot_id,recorded_at_utc=recorded.isoformat(),
                    entry_quote=dict(q),entry_usable=usable,
                    probability=f['probability'] if usable else None,
                    forecast_state='REFERENCE_BENCHMARK_ONLY' if reference else 'FROZEN' if usable and f['probability'] is not None else 'UNASSESSED',
                    training=f.get('training'),training_ids=f['training_ids'],baseline_probability=f.get('baseline_probability'),
                    reasons=why,execution_validation_eligible=usable and not reference and not replay_only,
                    outcome_id=digest([ticker,symbol,base['origin'],q,h,threshold,clock]))
                rows.append(row)
        self.cells+=len(rows)
        body={'run_id':self.run_id,'recorded_at_utc':recorded.isoformat(),
            'phase':phase,'replay_only':replay_only,'model_version':POLICY['version'],'policy_sha256':digest(POLICY),
            'configuration_sha256':digest(self.cfg),'pool_references':self.pool_refs,'training_conflicts':self.conflicts,
            'fee_basis':self.fees['fee_basis'],'fill_proof':False,'rows':rows}
        if persist:return write_packet(self.store/'forecasts','FORECASTS',body)
        self.buffer.append(body);return {'status':'BUFFERED','rows':len(rows)}

def saved_history(conn,ticker,symbol,days,cutoff,tolerance):
    history={};raw=[]
    for day in days:
        values=conn.execute('SELECT bid,ask,bid_size,ask_size,updated_ts,created_at_utc FROM chain_snapshots '
            'WHERE ticker=? AND quote_date=? AND option_symbol=?',(ticker,str(day),symbol)).fetchall()
        if len(values)!=1:history[str(day)]=None;continue
        bid,ask,bs,az,ts,created=values[0];raw.append([str(day),*values[0]])
        received=instant(created)
        try:quoted=datetime.fromtimestamp(float(ts),timezone.utc)
        except (ValueError,TypeError,OverflowError,OSError):quoted=None
        good=received is not None and received<=cutoff and quoted is not None and abs((quoted-session_bounds(day)[1]).total_seconds())<=tolerance
        history[str(day)]={'bid':bid,'ask':ask,'bid_size':bs,'ask_size':az,'available_at':received.isoformat(),
            'provider_at':quoted.isoformat()} if good else None
    return history,digest(raw)

def mature_forecast(row,history,*,as_of,assessed_at):
    r=dict(row);origin=date.fromisoformat(row['origin']);c=contract(row['contract_symbol'])
    r.update(assessment_session=as_of.isoformat(),assessed_at_utc=assessed_at.isoformat(),
        label=None,fit_eligible=False,state='PENDING',known_hit=False,first_hit_session=None,net_return=None,net_dollars=None)
    if not row['entry_usable'] or not c:r['state']='UNASSESSED_ENTRY';return r
    days=sessions_after(origin,row['horizon'])
    if c['expiry']<days[-1]:r['state']='EXPIRY_TRUNCATED';return r
    # Intraday entry can monetise at that same session's close (session 0).
    path=([origin] if row['entry_clock']!='CLOSE_BENCHMARK' else [])+days
    cost=float(row['entry_quote']['ask'])*100+row['open_fee'];gaps=[];available=[];terminal=None
    entry_time=instant(row['entry_quote'].get('provider_at'))
    if entry_time is None:r['state']='UNASSESSED_ENTRY';return r
    for day in path:
        if day>as_of:break
        q=history.get(str(day));n=0 if day==origin else days.index(day)+1
        if not valid_quote(q) or instant(q.get('provider_at')) is None or instant(q['provider_at'])<entry_time or instant(q.get('available_at')) is None or instant(q['available_at'])>assessed_at:
            gaps.append(str(day));continue
        available.append(instant(q['available_at']));terminal=q
        if float(q['bid'])>0:
            pnl=float(q['bid'])*100-row['close_fee']-cost;ret=pnl/cost
            if not r['known_hit'] and ret+1e-12>=row['threshold']:
                r.update(known_hit=True,first_hit_session=n,net_return=ret,net_dollars=pnl)
    r['missing_sessions']=gaps
    if days[-1]>as_of:r['state']='RIGHT_CENSORED';return r
    if gaps:r['state']='UNASSESSED_PATH_GAPS';return r
    r.update(state='HIT' if r['known_hit'] else 'FAILURE_NO_THRESHOLD',label=int(r['known_hit']),fit_eligible=True,
        quote_available_at=max(available).isoformat(),training_available_at=assessed_at.isoformat())
    if not r['known_hit'] and terminal and float(terminal['bid'])>0:
        pnl=float(terminal['bid'])*100-row['close_fee']-cost;r.update(net_dollars=pnl,net_return=pnl/cost)
    r['terminal_zero_bid']=bool(terminal and float(terminal['bid'])==0)
    r['out_of_sample_eligible']=bool(row['execution_validation_eligible'] and row['probability'] is not None)
    return r

def mature_pending(store,database,cfg,*,as_of=None):
    store=Path(store);assessed=now();as_of=as_of or assessed.astimezone(NY).date()
    # Never read an unfinished session close as a completed observation.
    if is_xnys_session(as_of) and assessed<session_bounds(as_of)[1]:
        from datetime import timedelta
        as_of-=timedelta(days=1)
    paths=sorted((store/'forecasts').glob('forecasts-*.json'))
    if len(paths)>cfg['max_packet_files']:raise ValueError('FORECAST_PACKET_LIMIT_REMAINDER')
    terminal=set();attempted={};old=list((store/'outcomes').glob('outcomes-*.json'))
    if len(old)>cfg['max_packet_files']:raise ValueError('OUTCOME_PACKET_LIMIT_REMAINDER')
    for path in old:
        for r in read_packet(path,'OUTCOMES')['rows']:
            if r.get('fit_eligible') or r.get('state') in ('UNASSESSED_ENTRY','EXPIRY_TRUNCATED'):terminal.add(r['forecast_id'])
            attempted[r['forecast_id']]=max(attempted.get(r['forecast_id'],''),r.get('assessed_at_utc',''))
    packets=[(p,read_packet(p,'FORECASTS')) for p in paths]
    packets.sort(key=lambda pair:(pair[1]['recorded_at_utc'],str(pair[0])))
    due=[]
    for _,packet in packets:
        for row in packet['rows']:
            if row['forecast_id'] in terminal:continue
            if row['window_end']>str(as_of) and row['entry_usable'] and not row.get('expiry_truncated'):
                continue
            due.append((packet,row))
    # Rotate unchanged path gaps behind never-assessed work. A bounded pass
    # must not perpetually spend its allowance on the same missing contracts.
    due.sort(key=lambda pair:(attempted.get(pair[1]['forecast_id'],''),pair[1]['window_end'],pair[1]['forecast_id']))
    rows=[];training=[];left=0;pending=0;started=time.monotonic()
    pending=sum(row['forecast_id'] not in terminal and row['window_end']>str(as_of)
        and row['entry_usable'] and not row.get('expiry_truncated') for _,packet in packets for row in packet['rows'])
    with closing(sqlite3.connect(Path(database).resolve().as_uri()+'?mode=ro',uri=True,timeout=3)) as conn:
        conn.execute('PRAGMA query_only=ON')
        for packet,row in due:
            if len(rows)>=cfg['max_maturation_cells'] or time.monotonic()-started>cfg['max_local_seconds']:
                left+=1;continue
            origin=date.fromisoformat(row['origin']);days=sessions_after(origin,row['horizon'])
            querydays=([origin] if row['entry_clock']!='CLOSE_BENCHMARK' else [])+days
            querydays=[d for d in querydays if d<=as_of and is_xnys_session(d)]
            h,sha=saved_history(conn,row['ticker'],row['contract_symbol'],querydays,assessed,cfg['close_quote_tolerance_seconds'])
            r=mature_forecast(row,h,as_of=as_of,assessed_at=assessed)
            r.update(source_forecast_packet=packet['content_sha256'],source_quotes_sha256=sha,replay_only=packet['replay_only'])
            rows.append(r)
            if r['fit_eligible'] and r.get('cohort_key') and not packet['replay_only']:training.append(r)
    outcome=write_packet(store/'outcomes','OUTCOMES',{'recorded_at_utc':assessed.isoformat(),'as_of_session':as_of.isoformat(),'rows':rows}) if rows else None
    pool=write_packet(store/'training_pools','TRAINING_POOL',{'recorded_at_utc':assessed.isoformat(),
        'basis':'OBSERVED_COMPLETED_WINDOWS_NOT_FILL_OR_MARKET_EDGE_PROOF','rows':training}) if training else None
    return {'status':'BOUNDED_REMAINDER' if left else 'COMPLETE_LOCAL_PASS','processed':len(rows),
        'remaining_cells':left,'pending_maturity_cells':pending,'states':dict(Counter(r['state'] for r in rows)),
        'outcomes':outcome,'training_pool':pool}


def evening_cycle(repo,run_id,capture,*,store=None,database=None):
    """Consume immutable captured inputs, not mutable trading rows."""
    from contracts.phantom_prospective_evidence import read_packet as read_candidates
    cfg=config(repo)
    if not cfg['enabled']:return {'status':'DISABLED','promotions_enabled':False}
    packet=read_candidates(capture['path'],run_id=run_id,kind='CANDIDATES')
    if packet['content_sha256']!=capture['content_sha256']:raise ValueError('Candidate reference mismatch')
    folder=Path(store) if store else Path(repo)/'runtime/phantom_profit_shadow'
    db=Path(database) if database else Path(repo)/'data/phantom/phantom_history.db'
    matured=mature_pending(folder,db,cfg)
    shadow=ShadowSession(repo,run_id,store=folder,database=db);shadow.begin_publication()
    refs=[];errors=[];left=0
    for ordinal,candidate in enumerate(packet['rows']):
        try:
            refs.append(shadow.publish(candidate,quote_from_candidate(candidate),phase='EVENING',
                snapshot_id=candidate['candidate_id'],replay_only=packet['capture_purpose']!='RUNTIME_PROSPECTIVE',persist=False))
        except ValueError as exc:
            if str(exc)=='SHADOW_BOUNDED_WORK_REMAINDER':left=len(packet['rows'])-ordinal;break
            errors.append({'candidate_id':candidate['candidate_id'],'reason':str(exc)})
    forecast_ref=shadow.flush()
    summary={'status':'INCOMPLETE' if left or errors or matured['remaining_cells'] else 'COMPLETE_SHADOW_CAPTURE',
        'recorded_at_utc':now().isoformat(),'run_id':run_id,'maturation':matured,'forecast_packet':forecast_ref,
        'captured_candidates':len(refs),
        'remaining_candidates':left,'errors':errors,'promotions_enabled':False,'providers':0,'database_writes':0}
    return {**summary,'receipt':write_packet(folder/'cycles','CYCLE',{**summary,'rows':[]})}
