"""Saved fixtures only; no providers, pipeline, live writes or Lane B."""
from pathlib import Path
from copy import deepcopy
from datetime import datetime,timezone
import csv,json,math,sqlite3,sys,inspect
import pytest
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
import phantom_engine as engine
from contracts.phantom_advisory_policy import composite,legacy_composite,ceiling,SCORE_VERSION
from contracts import phantom_prospective_evidence as cap

RUN='20261120_220000'
NOW=datetime(2026,11,21,21,tzinfo=timezone.utc)

@pytest.mark.parametrize('regime',['NORMAL','TRANSITIONAL'])
def test_reachable_scale_without_changing_weights_or_available_weight_denominator(regime):
    w=engine._weights({'regime':regime});allhigh={k:100 for k in w}
    assert 67<ceiling(w)<68 and composite(allhigh,w)==pytest.approx(100)
    assert composite({k:0 for k in w},w)==0
    missing={**allhigh,'bayes':None}
    assert composite(missing,w)==pytest.approx(100*legacy_composite(missing,w)/ceiling(w))
    assert composite(missing,w)<100
    scores=[composite({k:n for k in w},w) for n in range(101)]
    assert scores==sorted(scores)
    assert {'HIGH','CONVICTION'}<={engine._decision(s) for s in scores}

@pytest.mark.parametrize('bad',[None,float('nan'),float('inf'),-1,101,True])
def test_bad_component_cannot_be_valid_evidence(bad):
    from contracts.phantom_advisory_policy import qualified_score
    assert qualified_score(bad) is None

def strongest(monkeypatch,bayes=100):
    monkeypatch.setattr(engine,'compute_iv_surface',lambda *a:dict(iv_entropy_score=100,iv_evidence_available=True))
    monkeypatch.setattr(engine,'compute_gamma_trajectory',lambda *a:dict(gamma_score=100,gamma_trajectory_signed=100))
    monkeypatch.setattr(engine,'compute_bayesian_edge',lambda *a:dict(bayesian_score=bayes,bayesian_edge_pp=20))
    monkeypatch.setattr(engine,'compute_info_flow',lambda *a:dict(info_flow_score=100))
    monkeypatch.setattr(engine,'compute_criticality',lambda *a:dict(criticality_score=100,criticality_order_parameter=1))

@pytest.mark.parametrize('veto',[False,True])
def test_even_full_evidence_maximum_score_cannot_promote_or_add_ois_bonus(monkeypatch,veto):
    strongest(monkeypatch)
    row=dict(ticker='NAN',direction='CALL',options_score=62,options_verdict='WATCH',
        contract_dte=30,contract_strike=100,catalyst_inside_dte=veto)
    frozen=deepcopy(row);p=engine.score_row(row,object(),RUN);out=engine.apply_payload(row,p)
    assert p['phantom_score']==100 and p['phantom_decision']=='CONVICTION'
    assert p['phantom_score_legacy']<70 and p['phantom_score_version']==SCORE_VERSION
    assert not p['phantom_promotions_enabled'] and not p['phantom_score_calibrated']
    assert p['phantom_promoted_verdict']=='NONE' and p['phantom_ois_adjustment']==0
    assert p['options_score_phantom_adjusted']==62 and row==frozen
    assert all(out[k]==v for k,v in row.items())
    assert p['phantom_hard_veto_respected']==veto

def fixture(tmp_path,monkeypatch):
    monkeypatch.setattr(cap,'_utc_now',lambda:NOW)
    root=tmp_path/'repo';run=root/'data/output/runs'/RUN;folder=run/'options';folder.mkdir(parents=True)
    source=folder/f'options_intelligence_{RUN}.csv'
    rows=[dict(ticker='NAN',contract_occ_symbol='NAN261218C00010000',thesis_id='TH1',options_verdict='WATCH'),
        dict(ticker='NAN',contract_occ_symbol='NAN261218C00010000',thesis_id='TH2',options_verdict='BLOCKED'),
        dict(ticker='SYM',contract_occ_symbol='',thesis_id='TH3',options_verdict='STAND_DOWN')]
    with source.open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    (run/'run_meta.json').write_text(json.dumps({'session_date':'2026-11-20','baseline_commit_hash':'test-only'}))
    db=tmp_path/'fixture.db';c=sqlite3.connect(db)
    c.execute('CREATE TABLE chain_snapshots('+','.join(cap.QUOTE_FIELDS)+',PRIMARY KEY(ticker,quote_date,option_symbol))')
    q=dict(ticker='NAN',quote_date='2026-11-20',option_symbol='NAN261218C00010000',side='call',strike=10,dte=28,
        bid=1,ask=1.1,bid_size=10,ask_size=10,underlying_price=10,updated_ts=int(datetime(2026,11,20,21,tzinfo=timezone.utc).timestamp()),
        created_at_utc='2026-11-20T21:01:00Z',source='SAVED_FIXTURE',iv=.3,delta=.5,gamma=.1,theta=-.1,vega=.2,
        greeks_source='TEST',greeks_quality='VENDOR_COMPLETE')
    c.execute('INSERT INTO chain_snapshots VALUES('+','.join('?' for _ in cap.QUOTE_FIELDS)+')',[q[k] for k in cap.QUOTE_FIELDS]);c.commit();c.close()
    return root,run,source,db,rows

def candidate(f):
    root,run,source,db,rows=f
    return cap.capture_candidates(run,source,rows,run_id=RUN,session='2026-11-20',database=db,score_version=SCORE_VERSION)

def payloads(rows):
    return [dict(run_id=RUN,ticker=r['ticker'],phantom_score=100,phantom_promoted_verdict='NONE',
        phantom_ois_adjustment=0,phantom_score_version=SCORE_VERSION) for r in rows]

def test_capture_preserves_all_rows_duplicate_tickers_raw_values_and_actual_clock(tmp_path,monkeypatch):
    f=fixture(tmp_path,monkeypatch);root,run,source,db,rows=f
    old=source.read_bytes();before=cap.db_fingerprint(db);first=candidate(f)
    packet=cap.read_packet(first['path'],run_id=RUN,kind='CANDIDATES')
    assert packet['recorded_at_utc']==NOW.isoformat() and packet['evidence_session']=='2026-11-20'
    assert packet['universe_count']==3 and len({r['candidate_id'] for r in packet['rows']})==3
    assert [r['ticker'] for r in packet['rows']]==['NAN','NAN','SYM']
    assert packet['rows'][0]['quote']['bid']==1 and packet['rows'][1]['entry_state']['options_verdict']=='BLOCKED'
    assert packet['rows'][2]['quote'] is None and 'NO_SELECTED_CONTRACT' in packet['rows'][2]['limitations']
    oldtime=Path(first['path']).stat().st_mtime_ns
    assert candidate(f)['path']==first['path'] and Path(first['path']).stat().st_mtime_ns==oldtime
    assert source.read_bytes()==old and cap.db_fingerprint(db)==before

def test_only_paired_publications_can_supply_future_model_availability(tmp_path,monkeypatch):
    f=fixture(tmp_path,monkeypatch);first=candidate(f)
    assert cap.availability_index([])=={}
    pub=cap.capture_predictions(f[1],first,payloads(f[-1]),run_id=RUN)
    index=cap.availability_index([pub['path']]);info=index[('NAN','NAN261218C00010000')]
    assert info['known_at']==NOW.isoformat() and info['earliest_entry_session']=='2026-11-23'
    assert len(index)==1  # missing contracts do not gain a guessed identity
    p=cap.read_packet(pub['path']);assert not p['promotion_enabled'] and len(p['rows'])==3

@pytest.mark.parametrize('change',['population','identity','promotion','bonus'])
def test_publication_rejects_unpaired_or_authority_bearing_predictions(tmp_path,monkeypatch,change):
    f=fixture(tmp_path,monkeypatch);first=candidate(f);p=payloads(f[-1])
    if change=='population':p.pop()
    elif change=='identity':p[0]['ticker']='OTHER'
    elif change=='promotion':p[0]['phantom_promoted_verdict']='EXECUTE'
    else:p[0]['phantom_ois_adjustment']=15
    with pytest.raises(ValueError):cap.capture_predictions(f[1],first,p,run_id=RUN)
    assert len(list((f[1]/'evidence/phantom_prospective').glob('predictions-*')))==0

@pytest.mark.parametrize('changed',['input','database'])
def test_source_change_between_capture_and_publication_is_not_claimed_as_same_snapshot(tmp_path,monkeypatch,changed):
    f=fixture(tmp_path,monkeypatch);first=candidate(f)
    if changed=='input':f[2].write_text('changed')
    else:
        c=sqlite3.connect(f[3]);c.execute('UPDATE chain_snapshots SET bid=.5');c.commit();c.close()
    with pytest.raises(ValueError):cap.capture_predictions(f[1],first,payloads(f[-1]),run_id=RUN)

@pytest.mark.parametrize('stamp,expected',[('2026-11-25T22:00:00+00:00','2026-11-27'),
    ('2026-11-27T18:00:00+00:00','2026-11-30'),('2026-11-27T17:59:00+00:00','2026-11-27'),
    ('2026-11-21T21:00:00+00:00','2026-11-23'),('2026-03-06T22:00:00+00:00','2026-03-09')])
def test_entry_session_never_backdates_after_close_weekend_holiday_early_close_dst(stamp,expected):
    assert cap.first_entry_session(datetime.fromisoformat(stamp))==expected

def test_tampered_hash_and_wrong_run_do_not_supply_knowledge(tmp_path,monkeypatch):
    f=fixture(tmp_path,monkeypatch);first=candidate(f)
    with pytest.raises(ValueError):cap.read_packet(first['path'],run_id='OTHER')
    p=Path(first['path']);data=json.loads(p.read_text());data['rows'].pop();p.write_text(json.dumps(data))
    with pytest.raises(ValueError):cap.read_packet(p)

def test_diagnostic_replay_packets_never_qualify_as_production_evidence(tmp_path,monkeypatch):
    f=fixture(tmp_path,monkeypatch)
    first=cap.capture_candidates(f[1],f[2],f[-1],run_id=RUN,session='2026-11-20',
        database=f[3],score_version=SCORE_VERSION,replay_only=True)
    pub=cap.capture_predictions(f[1],first,payloads(f[-1]),run_id=RUN)
    with pytest.raises(ValueError,match='Replay capture'):cap.availability_index([pub['path']])

@pytest.mark.parametrize('fail_capture',[False,True])
def test_fixture_stage_wires_capture_before_preload_and_records_failures_without_promotions(tmp_path,monkeypatch,fail_capture):
    f=fixture(tmp_path,monkeypatch);root,run,source,db,rows=f;events=[]
    class FakeDB:
        def __init__(self,**kw):pass
        def initialise(self):pass
        def ensure_scoring_index(self):return False
        def preload_tickers(self,*a,**kw):
            events.append('preload')
            assert fail_capture or list((run/'evidence/phantom_prospective').glob('candidates-*'))
        def batch_write_phantom_scores(self,*a):events.append('scores')
        def write_run_audit(self,*a):pass
    monkeypatch.setattr(engine,'PhantomDatabase',FakeDB)
    monkeypatch.setattr(engine,'score_row',lambda row,*a:dict(run_id=RUN,ticker=row['ticker'],phantom_score=100,
        phantom_promoted_verdict='NONE',phantom_ois_adjustment=0,phantom_hard_veto_respected=False))
    if fail_capture:
        def fail(*a,**kw):raise OSError('fixture capture guard')
        monkeypatch.setattr(engine,'capture_candidates',fail)
    before=source.read_bytes();fingerprint=cap.db_fingerprint(db)
    summary=engine.run_phantom(source,source.with_name('fixture_output.csv'),RUN,db,root)
    assert summary['promoted_count']==0 and not summary['promotions_enabled']
    assert summary['prospective_capture_state']==('INCOMPLETE' if fail_capture else 'CAPTURED')
    assert events==['preload','scores'] and source.read_bytes()==before and cap.db_fingerprint(db)==fingerprint
    if fail_capture:assert summary['prospective_candidate_capture']['status']=='FAILED'

def test_failed_publication_never_runs_the_profit_forecast_cycle(tmp_path,monkeypatch):
    from contracts import phantom_profit_shadow as shadow
    f=fixture(tmp_path,monkeypatch);root,run,source,db,rows=f
    class FakeDB:
        def __init__(self,**kw):pass
        def initialise(self):pass
        def ensure_scoring_index(self):return False
        def preload_tickers(self,*a,**kw):pass
        def batch_write_phantom_scores(self,*a):pass
        def write_run_audit(self,*a):pass
    monkeypatch.setattr(engine,'PhantomDatabase',FakeDB)
    monkeypatch.setattr(engine,'score_row',lambda row,*a:dict(run_id=RUN,ticker=row['ticker'],phantom_score=1,
        phantom_promoted_verdict='NONE',phantom_ois_adjustment=0,phantom_hard_veto_respected=False))
    def rejected(*a,**kw):raise ValueError('Selected quote rows changed')
    def forbidden(*a,**kw):raise AssertionError('Forecast must not bypass rejected publication')
    monkeypatch.setattr(engine,'capture_predictions',rejected)
    monkeypatch.setattr(shadow,'evening_cycle',forbidden)
    summary=engine.run_phantom(source,source.with_name('fixture_output.csv'),RUN,db,root)
    assert summary['prospective_prediction_capture']['status']=='FAILED'
    assert summary['option_profit_shadow']['status']=='BLOCKED_NO_VERIFIED_PUBLICATION'
