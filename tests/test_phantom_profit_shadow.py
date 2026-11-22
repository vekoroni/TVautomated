from copy import deepcopy
from datetime import date,datetime,timedelta,timezone
from pathlib import Path
import gzip,json,sqlite3,hashlib
import pytest
from avshunter.shared.xnys_calendar import session_bounds
from contracts.option_profit_evidence import sessions_after,outcome
from contracts.option_profit_cohorts import decorate,maturity_coverage,forecast
from contracts import phantom_profit_shadow as sh
from scripts.recover_phantom_profit_saved import raw_recovery

ROOT=Path(__file__).resolve().parents[1]
ORIGIN=date(2026,11,2)
SYMBOL='ABC270319C00100000'

def q(day=ORIGIN,bid=.9,ask=1,regular=False):
    t=session_bounds(day)[0]+timedelta(minutes=15) if regular else session_bounds(day)[1]
    return dict(bid=bid,ask=ask,bid_size=10,ask_size=10,underlying_price=100,
        provider_at=t.isoformat(),available_at=(t+timedelta(seconds=1)).isoformat(),underlying_at=t.isoformat())

def publish(tmp_path,monkeypatch,regular=False,replay=False,pool_paths=None):
    quote=q(regular=regular);recorded=datetime.fromisoformat(quote['available_at'])+timedelta(seconds=1)
    monkeypatch.setattr(sh,'now',lambda:recorded)
    s=sh.ShadowSession(ROOT,'test',store=tmp_path,pool_paths=pool_paths or [])
    ref=s.publish(dict(ticker='ABC',contract_symbol=SYMBOL),quote,
        phase='MORNING' if regular else 'EVENING',snapshot_id='candidate',replay_only=replay)
    return s,sh.read_packet(ref['path']),ref

def test_six_events_and_reference_never_executable(tmp_path,monkeypatch):
    s,p,ref=publish(tmp_path,monkeypatch)
    assert {(r['threshold'],r['horizon']) for r in p['rows']}=={(t,h) for t in (.2,.3) for h in (5,10,20)}
    assert all(r['entry_usable'] and not r['execution_validation_eligible'] and r['probability'] is None for r in p['rows'])
    assert all('REFERENCE_CLOSE_NOT_EXECUTABLE_ENTRY' in r['reasons'] for r in p['rows'])
    raw=Path(ref['path']).read_bytes()
    s.publish(dict(ticker='ABC',contract_symbol=SYMBOL),q(),phase='EVENING',snapshot_id='candidate')
    assert Path(ref['path']).read_bytes()==raw

@pytest.mark.parametrize('mutation,reason',[
    ({'provider_at':'2026-11-02T14:30:00+00:00'},'STALE_OR_OUT_OF_SESSION_ENTRY'),
    ({'underlying_at':None},'ENTRY_SPOT_TIME_ALIGNMENT_UNVERIFIED'),
    ({'option_symbol':'XYZ270319C00100000'},'EXACT_CONTRACT_MISMATCH'),
    ({'available_at':'2027-01-01T00:00:00+00:00'},'QUOTE_AVAILABILITY_UNVERIFIED')])
def test_bad_entry_clocks_fail_closed(tmp_path,monkeypatch,mutation,reason):
    s,p,_=publish(tmp_path,monkeypatch,regular=True)
    ref=s.publish(dict(ticker='ABC',contract_symbol=SYMBOL),{**q(regular=True),**mutation},phase='MORNING',snapshot_id='bad')
    assert all(not r['entry_usable'] and r['probability'] is None and reason in r['reasons'] for r in sh.read_packet(ref['path'])['rows'])

def history(row,bid=1.4):
    return {str(d):q(d,bid,bid+.1) for d in [ORIGIN]+sessions_after(ORIGIN,row['horizon'])}

@pytest.mark.parametrize('regular,first',[(False,1),(True,0)])
def test_maturation_first_hit_and_full_window(tmp_path,monkeypatch,regular,first):
    _,p,_=publish(tmp_path,monkeypatch,regular)
    r=p['rows'][0];days=sessions_after(ORIGIN,5);assessed=session_bounds(days[-1])[1]+timedelta(minutes=1)
    h=history(r)
    pending=sh.mature_forecast(r,h,as_of=days[0],assessed_at=assessed)
    assert pending['known_hit'] and pending['label'] is None and not pending['fit_eligible']
    result=sh.mature_forecast(r,h,as_of=days[-1],assessed_at=assessed)
    assert result['label']==1 and result['first_hit_session']==first and result['net_dollars']==pytest.approx(38.8)
    assert result['out_of_sample_eligible'] is False # no prior matched forecast

@pytest.mark.parametrize('bid,expected',[(.7,'FAILURE_NO_THRESHOLD'),(0,'FAILURE_NO_THRESHOLD'),(1.4,'HIT')])
def test_failures_costs_and_zero_bid_not_fills(tmp_path,monkeypatch,bid,expected):
    _,p,_=publish(tmp_path,monkeypatch);r=p['rows'][0];last=sessions_after(ORIGIN,5)[-1]
    out=sh.mature_forecast(r,history(r,bid),as_of=last,assessed_at=session_bounds(last)[1]+timedelta(minutes=1))
    assert out['state']==expected and out['fit_eligible']
    if bid==0:assert out['net_return'] is None and out['terminal_zero_bid']
    if bid==.7:assert out['net_dollars']==pytest.approx(-31.2)

def test_gaps_late_receipts_expiry_and_missing_entry_not_losses(tmp_path,monkeypatch):
    _,p,_=publish(tmp_path,monkeypatch);r=p['rows'][0];days=sessions_after(ORIGIN,5);h=history(r)
    assessed=session_bounds(days[-1])[1]+timedelta(minutes=1)
    del h[str(days[2])]
    out=sh.mature_forecast(r,h,as_of=days[-1],assessed_at=assessed)
    assert out['state']=='UNASSESSED_PATH_GAPS' and out['label'] is None
    h=history(r);h[str(days[2])]['available_at']='2027-01-01T00:00:00+00:00'
    assert sh.mature_forecast(r,h,as_of=days[-1],assessed_at=assessed)['label'] is None
    r={**r,'contract_symbol':'ABC261106C00100000'}
    assert sh.mature_forecast(r,h,as_of=days[-1],assessed_at=assessed)['state']=='EXPIRY_TRUNCATED'

def test_maturity_denominator_does_not_count_pending_or_expired_as_missing():
    rows=[dict(fit_eligible=True,window_end='2026-11-10',assessment_session='2026-11-20'),
          dict(fit_eligible=False,window_end='2026-11-10',assessment_session='2026-11-20'),
          dict(fit_eligible=False,window_end='2026-12-01',assessment_session='2026-11-20'),
          dict(fit_eligible=False,window_end='2026-11-10',expiry_truncated=True)]
    result=maturity_coverage(rows)
    assert result['mature_unknown_fraction']==.5 and result['not_matured_n']==1 and result['expiry_truncated_n']==1

def training_rows(clock='CLOSE_BENCHMARK'):
    rows=[]
    for i in range(5):
        day=sessions_after(date(2026,7,1),50)[i*10]
        for j in range(6):
            ticker=chr(65+j)*2;symbol=ticker+'270319C00100000';hist={str(d):q(d,1.5 if j%2 else .8,1.6) for d in sessions_after(day,5)}
            hist[str(day)]=q(day)
            r=outcome(symbol,day,hist,as_of=date(2026,10,30),horizon=5,threshold=.2,open_fee=1.1,close_fee=.1)
            r['entry_clock']=clock
            r=decorate(r,ticker,hist[str(day)],training_available_at='2026-10-31T00:00:00+00:00')
            rows.append(r)
    return rows

def test_pool_available_now_not_backdated_and_no_replay(tmp_path):
    rows=training_rows();recorded='2026-11-01T00:00:00+00:00'
    rows[0]['replay_only']=True
    ref=sh.write_packet(tmp_path,'TRAINING_POOL',dict(recorded_at_utc=recorded,rows=rows))
    assert not sh.load_pool([ref['path']],datetime(2026,10,31,tzinfo=timezone.utc))[0]
    pool,_,_=sh.load_pool([ref['path']],datetime(2026,11,2,tzinfo=timezone.utc))
    assert len(pool)==29 and all(r['training_available_at']==recorded for r in pool)

def test_matching_forecasts_are_frozen_and_entry_clocks_never_pooled(tmp_path,monkeypatch):
    pool=sh.write_packet(tmp_path/'training_pools','TRAINING_POOL',dict(recorded_at_utc='2026-11-01T00:00:00+00:00',rows=training_rows()))
    _,p,ref=publish(tmp_path,monkeypatch,pool_paths=[pool['path']])
    assert p['rows'][0]['probability']==.5 and p['rows'][0]['training']['n']==30
    frozen=Path(ref['path']).read_bytes()
    _,regular,_=publish(tmp_path/'intraday',monkeypatch,True,pool_paths=[pool['path']])
    assert all(r['probability'] is None for r in regular['rows'])
    rp=sh.write_packet(tmp_path/'intraday_pool','TRAINING_POOL',dict(recorded_at_utc='2026-11-01T00:00:00+00:00',rows=training_rows('REGULAR_FIRST_30_MIN')))
    _,regular,_=publish(tmp_path/'intraday2',monkeypatch,True,pool_paths=[rp['path']])
    assert regular['rows'][0]['probability']==.5 and regular['rows'][0]['execution_validation_eligible']
    assert Path(ref['path']).read_bytes()==frozen

def test_packet_tampering_and_identity():
    assert sh.identity_ok('BRK.B','BRKB270319C00100000')
    assert not sh.identity_ok('BH.A','BHA270319C00100000')

def test_immutable_hash_tamper(tmp_path):
    ref=sh.write_packet(tmp_path,'TRAINING_POOL',dict(recorded_at_utc='2026-11-01T00:00:00+00:00',rows=[]))
    p=Path(ref['path']);p.write_text(p.read_text().replace('TRAINING_POOL','BAD'))
    with pytest.raises(ValueError):sh.read_packet(p)

def test_raw_recovery_hash_identity_and_preserve_existing(tmp_path):
    db=sqlite3.connect(':memory:');db.execute('CREATE TABLE chain_snapshots (ticker,quote_date,option_symbol)')
    db.execute('INSERT INTO chain_snapshots VALUES (?,?,?)',('ABC',str(ORIGIN),SYMBOL))
    body={'http':200,'data':{'s':'ok','optionSymbol':[SYMBOL],'updated':[session_bounds(ORIGIN)[1].timestamp()],
        'bid':[.9],'ask':[1.0],'bidSize':[10],'askSize':[10],'underlyingPrice':[100]}}
    raw=tmp_path/'raw.gz';raw.write_bytes(gzip.compress(json.dumps(body).encode()))
    j=tmp_path/'journal.jsonl';receipt=dict(status='RECEIVED',key='x',ticker='ABC',day=str(ORIGIN),raw=str(raw),raw_sha256=hashlib.sha256(raw.read_bytes()).hexdigest())
    j.write_text(json.dumps(receipt)+'\n')
    wanted={('ABC',str(ORIGIN),SYMBOL)};recorded=datetime(2026,11,21,tzinfo=timezone.utc)
    overlay,a=raw_recovery(db,wanted,[j],recorded=recorded)
    assert not overlay and a['existing_rows_preserved']==1
    db.execute('DELETE FROM chain_snapshots') # fixture only
    overlay,a=raw_recovery(db,wanted,[j],recorded=recorded)
    assert len(overlay)==1 and next(iter(overlay.values()))['quote']['available_at']==recorded.isoformat()
    receipt['raw_sha256']='bad';j.write_text(json.dumps(receipt))
    overlay,a=raw_recovery(db,wanted,[j],recorded=recorded)
    assert not overlay and a['archive_errors']
    db.close()

def test_maturation_ro_bounded_and_replay_never_training(tmp_path,monkeypatch):
    _,p,_=publish(tmp_path,monkeypatch,replay=True)
    db=tmp_path/'db.sqlite';conn=sqlite3.connect(db)
    conn.execute('CREATE TABLE chain_snapshots (ticker,quote_date,option_symbol,bid,ask,bid_size,ask_size,updated_ts,created_at_utc)')
    for d in sessions_after(ORIGIN,20):
        quote=q(d,1.4,1.5)
        conn.execute('INSERT INTO chain_snapshots VALUES (?,?,?,?,?,?,?,?,?)',('ABC',str(d),SYMBOL,1.4,1.5,10,10,session_bounds(d)[1].timestamp(),quote['available_at']))
    conn.commit();conn.close();before=hashlib.sha256(db.read_bytes()).hexdigest()
    monkeypatch.setattr(sh,'now',lambda:datetime(2026,12,15,tzinfo=timezone.utc))
    cfg={**sh.config(ROOT),'max_maturation_cells':1}
    report=sh.mature_pending(tmp_path,db,cfg)
    assert report['processed']==1 and report['remaining_cells']==5 and report['training_pool'] is None
    assert before==hashlib.sha256(db.read_bytes()).hexdigest()

def test_wiring_targets_actual_owners_not_lane_b():
    evening=(ROOT/'scripts/phantom_engine.py').read_text(encoding='utf-8')
    morning=(ROOT/'morning_gate.py').read_text(encoding='utf-8')
    assert evening.index('profit_shadow = evening_cycle')<evening.index('db.batch_write_phantom_scores(run_id')
    assert "quote_from_morning(result, live_data)" in morning
    assert 'strategy_layer' not in Path(sh.__file__).read_text()

def test_runtime_batching_avoids_one_file_per_candidate_and_pending_starvation(tmp_path,monkeypatch):
    s,p,_=publish(tmp_path,monkeypatch)
    for i in range(3):
        s.publish(dict(ticker='ABC',contract_symbol=SYMBOL),q(),phase='EVENING',snapshot_id=str(i),persist=False)
    ref=s.flush()
    assert len(sh.read_packet(ref['path'])['rows'])==18 and s.flush() is None
    db=tmp_path/'empty.sqlite';c=sqlite3.connect(db)
    c.execute('CREATE TABLE chain_snapshots (ticker,quote_date,option_symbol,bid,ask,bid_size,ask_size,updated_ts,created_at_utc)');c.close()
    cfg={**sh.config(ROOT),'max_maturation_cells':1}
    report=sh.mature_pending(tmp_path,db,cfg)
    assert report['pending_maturity_cells']==24 and report['remaining_cells']==0 and report['processed']==0

def test_old_closing_quotes_do_not_become_current_reference_forecasts(tmp_path,monkeypatch):
    s,_,_=publish(tmp_path,monkeypatch)
    monkeypatch.setattr(sh,'now',lambda:datetime(2026,11,3,22,tzinfo=timezone.utc))
    ref=s.publish(dict(ticker='ABC',contract_symbol=SYMBOL),q(),phase='EVENING',snapshot_id='stale')
    assert all('STALE_REFERENCE_SESSION' in r['reasons'] and not r['entry_usable'] for r in sh.read_packet(ref['path'])['rows'])

def test_actual_evening_cycle_helper_with_saved_capture_only(tmp_path,monkeypatch):
    from contracts import phantom_prospective_evidence as cap
    quote=q();recorded=datetime.fromisoformat(quote['available_at'])+timedelta(seconds=1)
    monkeypatch.setattr(sh,'now',lambda:recorded)
    run=tmp_path/'r';candidate=dict(candidate_id='frozen',ticker='ABC',contract_symbol=SYMBOL,
        quote={**quote,'updated_ts':datetime.fromisoformat(quote['provider_at']).timestamp(),'created_at_utc':quote['available_at']})
    before=deepcopy(candidate)
    receipt=cap._write(run,dict(schema=cap.SCHEMA,kind='CANDIDATES',run_id='r',recorded_at_utc=recorded.isoformat(),
        capture_purpose='OFFLINE_REPLAY_NOT_ACTUAL_PUBLICATION',rows=[candidate]))
    db=tmp_path/'cycle.sqlite';c=sqlite3.connect(db);c.execute('CREATE TABLE unused (x)');c.close()
    result=sh.evening_cycle(ROOT,'r',receipt,store=tmp_path/'store',database=db)
    assert result['status']=='COMPLETE_SHADOW_CAPTURE' and result['captured_candidates']==1
    packet=sh.read_packet(result['forecast_packet']['path'])
    assert packet['replay_only'] and packet['rows'][0]['entry_usable'] and candidate==before

def test_unchanged_gaps_do_not_starve_other_due_contracts(tmp_path,monkeypatch):
    publish(tmp_path,monkeypatch,replay=True)
    db=tmp_path/'gaps.sqlite';c=sqlite3.connect(db)
    c.execute('CREATE TABLE chain_snapshots (ticker,quote_date,option_symbol,bid,ask,bid_size,ask_size,updated_ts,created_at_utc)');c.close()
    monkeypatch.setattr(sh,'now',lambda:datetime(2026,12,15,tzinfo=timezone.utc))
    cfg={**sh.config(ROOT),'max_maturation_cells':1}
    a=sh.mature_pending(tmp_path,db,cfg)
    monkeypatch.setattr(sh,'now',lambda:datetime(2026,12,16,tzinfo=timezone.utc))
    b=sh.mature_pending(tmp_path,db,cfg)
    ar=sh.read_packet(a['outcomes']['path'])['rows'][0]
    br=sh.read_packet(b['outcomes']['path'])['rows'][0]
    assert ar['state']==br['state']=='UNASSESSED_PATH_GAPS'
    assert ar['forecast_id']!=br['forecast_id']

def test_release_default_ledger_is_private_not_in_shared_database_folder():
    session=sh.ShadowSession(ROOT,'packaging-check')
    assert session.store==ROOT/'runtime/phantom_profit_shadow'
    assert not session.store.is_relative_to(ROOT/'data')
