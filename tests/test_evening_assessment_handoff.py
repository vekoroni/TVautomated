from copy import deepcopy
from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from domain.evening_assessment import assess_evening, attach_assessments, FIELDS
from domain.option_valuation import option_value, entry_cost_usd_per_share, exit_proceeds_usd_per_share

def candidate(**changes):
    r=dict(ticker='XYZ',run_id='TEST',pipeline_mode='EOD',thesis_id='xyz-thesis',
        trade_lane_candidate_id='xyz-setup',canonical_direction='CALL',direction='CALL',
        signal_price=100,anticipated_level_q50=115,invalidation_price=95,
        anticipated_sessions_q50=5,anticipated_sessions_q80=10,planned_hold_sessions=10,
        contract_symbol='XYZ270219C00100000',anticipated_contract_symbol='XYZ270219C00100000',
        contract_bid=3.8,contract_ask=4.,contract_iv=.3,contract_oi=1000,contract_volume=100,
        selected_quote_timestamp_utc='2026-11-20T21:00:00Z',
        anticipated_valued_at_utc='2026-11-20T21:00:00Z',bar_data_asof='2026-11-20',
        thesis__readiness='READY_FOR_HUMAN_REVIEW',thesis_structure_alignment='ALIGNED',
        direction_conflict_status='NO_CONFLICT',lab_verdict='MANUAL_REVIEW',lab_tradeable=False,
        final_action='MANUAL_REVIEW',lab_rank=99,contract_repair_required='TRUE',
        valuation_rate_annual=.04,valuation_rate_basis='TEST_RATE',
        valuation_dividend_yield_annual=.01,valuation_dividend_basis='TEST_DIVIDEND')
    r.update(changes);return r

def assessed(**changes):
    f=assess_evening(candidate(**changes),run_id='TEST')
    return f,json.loads(f['evening_assessment_json'])

@pytest.mark.parametrize('hold',[1,5,20])
def test_qualifies_without_morning_and_never_grants_authority(hold):
    f,p=assessed(planned_hold_sessions=hold,anticipated_sessions_q50=hold)
    assert f['evening_assessment_route']=='EVENING_QUALIFIED'
    assert p['authority']=='RESEARCH_ONLY_NO_ENTRY_PERMISSION'
    assert p['legacy_verdict']=='MANUAL_REVIEW'
    assert p['empirical_clock_state']=='UNASSESSED_NOT_PUBLISHED'

def test_long_hold_human_review_even_when_assumed_profit_is_fast():
    f,p=assessed(planned_hold_sessions=21,crossing_n_slow_pace_30=1)
    assert f['evening_assessment_route']=='HUMAN_REVIEW_LONGER_HORIZON'
    assert p['planned_trading_hold_sessions']==21

@pytest.mark.parametrize('patch,route,reason',[
    ({'planned_hold_sessions':None},'ASSESSMENT_INCOMPLETE','PLANNED_TRADING_HOLD'),
    ({'contract_ask':None},'ASSESSMENT_INCOMPLETE','QUOTE_OR_IV_MISSING'),
    ({'contract_bid':0},'CONTRACT_UNSUITABLE','NO_OBSERVED_EXECUTABLE_BID'),
    ({'contract_bid':1},'CONTRACT_UNSUITABLE','SPREAD_EXCEEDS'),
    ({'contract_oi':2},'CONTRACT_UNSUITABLE','OI_BELOW'),
    ({'contract_symbol':'XYZ261127C00100000','anticipated_contract_symbol':'XYZ261127C00100000'},'CONTRACT_UNSUITABLE','RUNWAY'),
    ({'anticipated_contract_symbol':'XYZ270219P00100000'},'ASSESSMENT_INCOMPLETE','CONTRACT_MISMATCH'),
    ({'anticipated_valued_at_utc':'2026-11-19T21:00:00Z'},'ASSESSMENT_INCOMPLETE','QUOTE_MISMATCH'),
    ({'selected_quote_timestamp_utc':'2026-11-19T21:00:00Z'},'ASSESSMENT_INCOMPLETE','QUOTE_SESSION_MISMATCH'),
    ({'lab_verdict':'BLOCKED'},'ASSESSMENT_INCOMPLETE','UPSTREAM_SAFETY_BLOCK'),
    ({'signal_price':94},'THESIS_INVALIDATED',''),
    ({'thesis__readiness':'WAIT_TRIGGER'},'WAITING_FOR_TRIGGER',''),
    ({'thesis__readiness':'CLOSED_OUTCOME_REACHED'},'OPPORTUNITY_CLOSED',''),
])
def test_named_failures(patch,route,reason):
    f,p=assessed(**patch)
    assert f['evening_assessment_route']==route
    assert reason in f['evening_assessment_reasons']

def test_payload_identity_and_no_source_mutation():
    r=candidate();old=deepcopy(r)
    rows,counts=attach_assessments([r],run_id='TEST')
    assert r==old and len(rows)==1 and counts=={'EVENING_QUALIFIED':1}
    for k in ('lab_verdict','lab_tradeable','final_action','lab_rank','contract_symbol'):
        assert rows[0][k]==old[k]
    changed=assess_evening(candidate(contract_ask=4.1),run_id='TEST')
    assert changed['evening_assessment_source_sha256']!=rows[0]['evening_assessment_source_sha256']

def test_same_engine_cost_formula_and_stress_not_double_charged():
    f,p=assessed();n=5
    base=next(r for r in p['scenarios'] if r['checkpoint_sessions']==n and r['scenario']=='TARGET_IF_REACHED')
    years=(date(2027,2,19)-date.fromisoformat(base['exit_date'])).days/365
    v=option_value('CALL',115,100,years,.3,rate=.04,dividend_yield=.01)['value']
    entry=entry_cost_usd_per_share(4.)
    proceeds=exit_proceeds_usd_per_share(v,bid=3.8,ask=4.)
    assert base['model_value_per_share']==pytest.approx(v)
    assert base['net_pnl_per_contract']==pytest.approx((proceeds-entry)*100)
    assert base['net_return_fraction']==pytest.approx(proceeds/entry-1)
    wide=next(r for r in p['scenarios'] if r['checkpoint_sessions']==n and r['scenario']=='TARGET_WIDE_EXIT')
    low=next(r for r in p['scenarios'] if r['checkpoint_sessions']==n and r['scenario']=='TARGET_IV_DOWN')
    assert wide['entry_cost_per_contract']==base['entry_cost_per_contract']
    assert wide['net_pnl_per_contract']<=base['net_pnl_per_contract']
    assert low['net_pnl_per_contract']<=base['net_pnl_per_contract']

def test_put_expiry_and_holiday_session_boundaries():
    f,p=assessed(canonical_direction='PUT',direction='PUT',anticipated_level_q50=85,
        invalidation_price=105,contract_symbol='XYZ261127P00100000',anticipated_contract_symbol='XYZ261127P00100000')
    assert p['expiry_sessions']==4
    assert any(r['state']=='BEYOND_EXPIRY' and 'model_value_per_share' not in r for r in p['scenarios'])
    assert next(r for r in p['scenarios'] if r['checkpoint_sessions']==1)['exit_date']=='2026-11-23'

def test_frozen_evening_carries_without_repricing_and_never_ticker_only(tmp_path):
    from contracts.evening_assessment_handoff import freeze_assessments,carry_frozen_assessments
    root=tmp_path/'TEST';root.mkdir();(root/'run_meta.json').write_text('{"status":"RUNNING"}')
    r=candidate();r.update(assess_evening(r,run_id='TEST'))
    freeze_assessments([r],root)
    before={p:p.read_bytes() for p in root.rglob('*') if p.is_file()}
    morning=candidate(pipeline_mode='MORNING',morning_data_state='AVAILABLE',contract_ask=8.)
    out,_=carry_frozen_assessments([morning],root)
    assert out[0]['contract_ask']==8
    assert out[0]['evening_assessment_json']==r['evening_assessment_json']
    assert assess_evening(out[0],run_id='TEST')['evening_assessment_json']==r['evening_assessment_json']
    assert {p:p.read_bytes() for p in before}==before
    assert carry_frozen_assessments([candidate(thesis_id='different')],root)[1]['unassessed_rows']==1

def test_completed_snapshot_never_gets_new_files(tmp_path):
    from contracts.evening_assessment_handoff import freeze_assessments
    from contracts.monetisation_clock import complete_evening_history
    root=tmp_path/'TEST';root.mkdir();(root/'run_meta.json').write_text('{"status":"COMPLETED"}')
    before=list(root.rglob('*'))
    assert freeze_assessments([candidate()],root)['state']=='PRESERVED_NON_RUNNING_SNAPSHOT'
    complete_evening_history([candidate()],root,tmp_path/'absent.db')
    assert list(root.rglob('*'))==before

def test_full_materializer_publication_api_and_lossless_handoff(tmp_path):
    from contracts.lab_control import build_final_opportunity_book
    from contracts.lab_review_projection import publish_review_projection,read_review_rows,read_review_card,read_review_evidence,FAMILIES
    source=candidate();before=deepcopy(source)
    book=build_final_opportunity_book('TEST',[source],{'pipeline_mode':'EOD'})
    assert source==before
    assert book[0]['evening_assessment_version']
    original={k:book[0][k] for k in ('lab_verdict','lab_tradeable','contract_symbol','lab_rank')}
    pub=publish_review_projection({'run_id':'TEST','candidate_count':1,'rows':book},tmp_path)
    home=read_review_rows(tmp_path,'TEST')['rows'][0]
    card=read_review_card(tmp_path,'TEST',home['row_key'])
    assert json.loads(card['fields']['evening_assessment_json'])['route']==home['evening_assessment_route']
    # Verify the lossless receiving-side shape without depending on the
    # separately developed manual-basket feature or touching Lane B.
    frozen=json.loads(json.dumps({'run_id':'TEST','revision':pub['revision'],
        'row_key':home['row_key'],'card':card,'evidence':{family:
            read_review_evidence(tmp_path,'TEST',home['row_key'],family,pub['revision']) for family in FAMILIES}}))
    assert frozen['card']['fields']['evening_assessment_json']==card['fields']['evening_assessment_json']
    for k,v in original.items():assert book[0][k]==v

def test_evening_measurement_needs_no_morning_file_and_preserves_database(tmp_path):
    from contracts.monetisation_clock import complete_evening_history
    root=tmp_path/'TEST';root.mkdir();(root/'run_meta.json').write_text('{"run_status":"IN_PROGRESS","session_date":"2026-11-20","evidence_cutoff_utc":"2026-11-21T22:29:19Z"}')
    db=tmp_path/'history.db'
    c=sqlite3.connect(db)
    c.execute('CREATE TABLE chain_snapshots(ticker TEXT,option_symbol TEXT,quote_date TEXT,bid REAL,ask REAL,bid_size REAL,ask_size REAL,updated_ts INTEGER,created_at_utc TEXT,PRIMARY KEY(ticker,quote_date,option_symbol))')
    c.execute('INSERT INTO chain_snapshots VALUES(?,?,?,?,?,?,?,?,?)',('XYZ','XYZ270219C00100000','2026-11-20',3.8,4.,10,10,
        int(datetime(2026,11,20,21,tzinfo=timezone.utc).timestamp()),'2026-11-21T08:00:00Z'))
    c.commit();c.close();before=db.read_bytes()
    r=candidate()
    rows,receipt=complete_evening_history([r],root,db)
    assert receipt['state']=='COMPLETE_DESCRIPTIVE_MEASUREMENT'
    assert not (root/'morning_validation').exists()
    assert db.read_bytes()==before
    assert rows[0]['monetisation_20_unassessed_n'] is not None
    packet=json.loads((root/'intelligence_lab/evening_monetisation_clock_TEST.json').read_text())
    assert packet['source_kind']=='evening'
    assert packet['records'][0]['source_receipt']['saved_exact_rows']==1
    assert 'RECEIPT_AFTER_DECISION_CUTOFF' not in packet['records'][0]['source_receipt']['quarantine_counts']
    from contracts.lab_review_sources import prepare_review_publication
    prepared,_,rec=prepare_review_publication({'run_id':'TEST','candidate_count':1,'rows':rows},root)
    assert rec['monetisation_clock']['matched_rows']==1
    assert prepared['rows'][0]['monetisation_clock_state']==rows[0]['monetisation_clock_state']
    changed=candidate(contract_symbol='XYZ270219C00105000')
    with pytest.raises(ValueError,match='SOURCE_CHANGED'):
        complete_evening_history([changed],root,db)

def test_iv_context_is_not_a_probability_or_cheapness_label():
    _,p=assessed(atm_iv=.4,iv_rank=20,iv_percentile=15,iv_history_state='SHORT_HISTORY')
    assert p['iv_intelligence']['selected_contract_iv']==.3
    assert p['iv_intelligence']['iv_history_state']=='SHORT_HISTORY'
    assert any(s['scenario']=='HALF_MOVE_IF_REACHED' for s in p['scenarios'])
    assert any(s['scenario']=='STALL_IV_DOWN' for s in p['scenarios'])
    assert any(s['scenario']=='TARGET_IV_UP' for s in p['scenarios'])
