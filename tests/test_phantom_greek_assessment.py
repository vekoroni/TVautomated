"""Saved-data model/lineage/reader tests. No network, no live data."""
from pathlib import Path
from contextlib import closing
import hashlib,json,socket,sqlite3,sys
import pytest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'scripts'))
from scripts import phantom_greek_assessment as a
from domain.option_valuation import american_crr_value,european_bsm_value

@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def denied(*x,**kw):raise AssertionError('NO_NETWORK')
    monkeypatch.setattr(socket.socket,'connect',denied)
    monkeypatch.setattr(socket,'create_connection',denied)

def row(**kw):
    r=dict(ticker='NAN',quote_date='2026-11-27',option_symbol='NAN270115C00100000',side='call',
       strike=100.,dte=49.,bid=4.,mid=4.1,ask=4.2,underlying_price=100.,iv=None,delta=.5,gamma=.01,theta=-.02,vega=.1,
       updated_ts=None,greeks_source='MARKETDATA_VENDOR',greeks_quality='UNASSESSED_MIXED_PROTECTED_GREEKS')
    r.update(kw);return r

def test_inverse_uses_shared_american_engine_no_vendor_mutation():
    mid=american_crr_value(100,100,49/365,.045,0,.3,'CALL',steps=300)
    r=row(bid=mid-.1,mid=mid,ask=mid+.1);before=dict(r)
    result=a.assess_rows([r])[0]
    assert r==before
    assert result['status']=='MODEL_POINT_QUALIFIED',result
    assert abs(result['greeks']['iv']-.3)<1e-5
    assert abs(mid-european_bsm_value('CALL',100,100,49/365,.3,rate=.045,dividend_yield=0))<.02
    assert result['rate_basis']=='ASSUMED_FIXED_NOT_OBSERVED'
    assert result['promotion_eligible'] is False

def test_boundary_spread_is_interval_not_clamped_point():
    r=row(strike=29,underlying_price=36.28,dte=7,bid=5.7,mid=7.225,ask=8.75)
    out=a.assess_rows([r])[0]
    assert out['status']=='INTERVAL_ONLY'
    assert out['greeks'] is None and out['iv_interval']['upper']>0
    assert r['mid']==7.225 and r['iv'] is None

@pytest.mark.parametrize('changes,status',[
    ({'underlying_price':None},'EXCLUDED_MISSING_UNDERLYING'),
    ({'bid':0},'EXCLUDED_INVALID_QUOTE'),
    ({'ask':3.9},'EXCLUDED_INVALID_QUOTE'),
    ({'underlying_price':120},'EXCLUDED_SPREAD_BELOW_INTRINSIC'),
    ({'iv':.3,'greeks_quality':'VENDOR_COMPLETE'},'VENDOR_POINT_QUALIFIED'),
    ({'iv':6.,'greeks_quality':'VENDOR_COMPLETE'},'EXCLUDED_VENDOR_BENCHMARK_POLICY')])
def test_every_input_has_a_specific_result(changes,status):
    assert a.assess_rows([row(**changes)])[0]['status']==status

def setup_db(tmp_path):
    from scripts.phantom_database import PhantomDatabase
    p=tmp_path/'phantom.db';db=PhantomDatabase(p,ROOT);db.initialise()
    r=row();r.update(source='marketdata.app',open_interest=10,volume=2)
    # Raw insert, not the hook being tested; preserves the partial vendor set.
    with sqlite3.connect(p) as c:
        from scripts.phantom_maintenance import ensure_schema,refresh_pair_health
        ensure_schema(c)
        c.execute('INSERT INTO chain_snapshots('+','.join(r)+') VALUES('+','.join('?' for _ in r)+')',list(r.values()))
        refresh_pair_health(c,'NAN','2026-11-27')
    return db,p,r

def test_assessment_transaction_rollback_and_idempotence(tmp_path):
    _,p,r=setup_db(tmp_path)
    with sqlite3.connect(p) as c:
        a.ensure_schema(c);c.commit()
        assert a.assess_and_store(c,[r])['changed']==1
        c.rollback()
        assert c.execute('SELECT count(*) FROM phantom_greek_assessments').fetchone()[0]==0
        assert a.assess_and_store(c,[r])['changed']==1;c.commit()
        assert a.assess_and_store(c,[r])['changed']==0
        assert c.execute('SELECT count(*) FROM phantom_greek_assessment_audit').fetchone()[0]==1
        assert c.execute('SELECT iv,delta FROM chain_snapshots').fetchone()==(None,.5)

def test_health_surfaces_cache_and_scoring_read_same_assessment(tmp_path):
    from scripts.phantom_maintenance import session_health,drain_pending
    from scripts.phantom_option_quality import benchmark_record_eligible
    db,p,r=setup_db(tmp_path)
    result=a.assess_session(p,'2026-11-27',['NAN'],max_rows=1,min_free_gib=0)
    assert result['coverage']['unassessed_rows']==0
    assert result['affected_pairs']==[['NAN','2026-11-27']]
    health=session_health(p,'2026-11-27',['NAN'])
    assert health['known_needs_greeks_rows']==0 and health['known_incomplete_greek_rows']==1
    cache=tmp_path/'cache.db';drained=drain_pending(p,cache,min_free_gib=0)
    assert drained['reports'][0]['queue_complete']==1
    db.preload_tickers(['NAN'],as_of='2026-11-27')
    point=db.latest_chain_rows('NAN')[0]
    assert benchmark_record_eligible(point)
    assert point['raw_iv'] is None and point['raw_delta']==.5
    assert len(db.historical_iv_values('NAN'))==1
    with sqlite3.connect(cache) as c:assert c.execute('SELECT atm_iv FROM iv_history').fetchone()[0]==point['iv']
    with sqlite3.connect(p) as c:
        assert c.execute('SELECT iv,delta FROM chain_snapshots').fetchone()==(None,.5)
        assert a.session_assessment(c,'2026-11-27',['NAN'])['unassessed_rows']==0

def test_changed_input_invalidates_derived_view_and_health(tmp_path):
    db,p,r=setup_db(tmp_path)
    a.assess_session(p,'2026-11-27',['NAN'],max_rows=1,min_free_gib=0)
    with sqlite3.connect(p) as c:
        c.execute('UPDATE chain_snapshots SET ask=ask+.1')
        assert a.session_assessment(c,'2026-11-27',['NAN'])['unassessed_rows']==1
    assert db.latest_chain_rows('NAN','2026-11-27')==[]

def test_bound_reports_remainder_not_success(tmp_path):
    _,p,r=setup_db(tmp_path)
    result=a.assess_session(p,'2026-11-27',['NAN'],max_rows=0,min_free_gib=0)
    assert result['status']=='ASSESSMENT_BATCH_LIMIT_REMAINDER'
    assert result['coverage']['unassessed_rows']==1


def test_lab_overlay_separates_raw_missing_from_current_assessment(tmp_path):
    from contracts.lab_phantom_coverage import attach_phantom_coverage
    _,p,r=setup_db(tmp_path)
    a.assess_session(p,'2026-11-27',['NAN'],max_rows=1,min_free_gib=0)
    original={'run_id':'SAVED','revision':'unchanged','fields':{'ticker':'NAN','contract_symbol':r['option_symbol'],'lab_verdict':'MANUAL_REVIEW','lab_rank':5}}
    out=attach_phantom_coverage(original,p)
    assert out['fields']==original['fields'] and out['revision']=='unchanged'
    assert out['phantom_coverage_overlay']['unassessed_greek_rows']==0
    assert out['phantom_coverage_overlay']['incomplete_greek_rows']==1
    assert out['phantom_coverage_overlay']['exact_contract_state']=='ASSESSED_MODEL_POINT_ADVISORY'


def test_weekly_assessment_limit_is_not_reported_complete(tmp_path):
    from scripts.phantom_weekly_maintenance import main
    _,p,_=setup_db(tmp_path)
    with sqlite3.connect(p) as c:c.execute("UPDATE chain_snapshots SET iv=.3,greeks_quality='VENDOR_COMPLETE'")
    roster=tmp_path/'roster.csv';roster.write_text('ticker\nNAN\n')
    report=tmp_path/'weekly.json'
    assert main(['--db-path',str(p),'--iv-cache-path',str(tmp_path/'cache.db'),
        '--universe-path',str(roster),'--sessions','2026-11-27','--execute-local',
        '--max-assessment-rows','0','--report',str(report)])==0
    saved=json.loads(report.read_text())
    assert saved['status']=='NEEDS_LOCAL_FOLLOW_UP'
    assert saved['greek_assessments'][0]['coverage']['unassessed_rows']==1


def test_scoring_reader_skips_assessed_invalid_dte_without_crashing(tmp_path):
    db,p,_=setup_db(tmp_path)
    with sqlite3.connect(p) as c:c.execute('UPDATE chain_snapshots SET dte=NULL')
    a.assess_session(p,'2026-11-27',['NAN'],max_rows=1,min_free_gib=0)
    db.preload_tickers(['NAN'],as_of='2026-11-27')
    assert db.latest_chain_rows('NAN')==[] and db.historical_iv_values('NAN')==[]
