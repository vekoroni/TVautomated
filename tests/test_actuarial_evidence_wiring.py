"""No providers/pipeline. Contract controls are not model calibration tests."""
import ast
from copy import deepcopy
import hashlib,json,sys
from pathlib import Path
import pandas as pd
import pytest
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
from contracts.actuarial_evidence import (FIELDS,bind_evidence,evidence_fields,wire_frame,
    cache_outcomes,prepare_phantom_handoff,preferred_options_input,comparison)
from contracts.enrichment_ledger import write_enrichment_ledger
from phantom_bayesian import compute_bayesian_edge

RUN='20261119_230000';DAY='2026-11-19'
def cohort(**kw):
    c=dict(cohort_id='BROAD_STATE',event_id='UNDERLYING_RETURN_GT_ZERO',side='UP',
        horizon=10,clock='DAILY_BARS',rate=.6,rate_unit='FRACTION',n=100,wins=60,losses=40,
        maturity_basis='NON_NULL_HORIZON_OUTCOMES',observation_cutoff_session=DAY)
    c.update(kw);return c
def record(**kw):
    p=dict(available=True,valid=True,no_match=False,deferred=False,enriched_by='actuarial_enrichment_pass',
        enrichment_pass_result='EXACT_MATCH',behaviour_state_hash='STATE_A',matched_key='BROAD_STATE',
        sample_size=9000,**{'layer2__sample_size':3000},outcome_evidence=[cohort()])
    p.update(kw)
    return dict(run_id=RUN,ticker='NAN',stage='actuarial',calculation_version='TEST_V1',input_sha256='a'*64,payload=p)
def candidate(**kw):
    r=dict(run_id=RUN,ticker='NAN',behaviour_state_hash='STATE_A',contract_delta=.5,
           contract_dte=10,options_direction='CALL',options_score=60,options_verdict='WATCH')
    r.update(kw);return r
def wired(r=None,rec=None):
    r=r or candidate();e=bind_evidence(r,rec or record(),RUN,DAY,ledger_sha='b'*64)
    return {**r,**evidence_fields(e)}
def market(**kw):
    m=dict(event_id='UNDERLYING_RETURN_GT_ZERO',side='UP',horizon=10,clock='DAILY_BARS',
           probability=.4,measure='CALIBRATED_EVENT_PROBABILITY',calibration_version='TEST_ONLY_NOT_DEPLOYED',
           observation_cutoff_session=DAY)
    m.update(kw);return m

def test_default_delta_is_never_a_10_bar_underlying_probability():
    p=compute_bayesian_edge(wired())
    assert p['bayesian_score'] is None and not p['bayesian_evidence_available']
    assert 'OUTCOME_MISMATCH' in p['bayesian_evidence_reasons']
    assert 'MARKET_PROBABILITY_UNVERIFIED' in p['bayesian_evidence_reasons']

@pytest.mark.parametrize('change,reason',[
    ({'horizon':20},'HORIZON_OR_CLOCK_MISMATCH'),
    ({'clock':'CALENDAR_DAYS'},'HORIZON_OR_CLOCK_MISMATCH'),
    ({'side':'DOWN'},'SIDE_MISMATCH'),
    ({'event_id':'OPTION_EXPIRES_ITM'},'OUTCOME_MISMATCH'),
    ({'measure':'ABS_DELTA_PROXY'},'MARKET_PROBABILITY_UNVERIFIED'),
    ({'probability':60},'INVALID_MARKET_PROBABILITY'),
    ({'observation_cutoff_session':'2026-11-20'},'EVIDENCE_CUTOFF_MISMATCH')])
def test_comparison_requires_same_event_side_clock_horizon(change,reason):
    p=compute_bayesian_edge(wired(),market_evidence=market(**change))
    assert p['bayesian_score'] is None and reason in p['bayesian_evidence_reasons']

def test_fully_comparable_contract_positive_control_and_zero_wins():
    p=compute_bayesian_edge(wired(),market_evidence=market())
    assert p['bayesian_evidence_available']
    assert p['posterior_win_prob']==pytest.approx((.48*40+60)/140,abs=.0001)
    r=record(outcome_evidence=[cohort(rate=0,wins=0,losses=100)])
    p=compute_bayesian_edge(wired(rec=r),market_evidence=market())
    assert p['bayesian_evidence_available'] and p['posterior_win_prob']==pytest.approx(.48*40/140,abs=.0001)

@pytest.mark.parametrize('change,reason',[
    ({'n':9000},'COUNT_MISMATCH'),({'wins':None},'MISSING_SUCCESS_FAILURE_COUNTS'),
    ({'wins':60.5},'MISSING_SUCCESS_FAILURE_COUNTS'),({'rate':60},'INVALID_RATE_OR_UNIT'),
    ({'rate':.5},'RATE_COUNT_MISMATCH'),({'observation_cutoff_session':'2026-11-20'},'FUTURE_OBSERVATIONS'),
    ({'observation_cutoff_session':None},'OBSERVATION_CUTOFF_UNVERIFIED')])
def test_bad_or_unmatured_counts_do_not_fall_back_to_generic_fields(change,reason):
    r=wired(rec=record(outcome_evidence=[cohort(**change)]))
    r.update(actuarial_sample_count=9000,actuarial_win_rate_10d=.99)
    p=compute_bayesian_edge(r,market_evidence=market())
    assert p['bayesian_score'] is None and reason in p['bayesian_evidence_reasons']

@pytest.mark.parametrize('change,reason',[
    ({'deferred':True},'SOURCE_DEFERRED_OR_STATUS_UNVERIFIED'),
    ({'valid':False},'SOURCE_NOT_VALIDATED'),
    ({'enrichment_pass_result':'NO_VANGUARD_ROW'},'SOURCE_COMPLETION_UNVERIFIED')])
def test_legacy_lifecycle_contradictions_remain_visible(change,reason):
    p=compute_bayesian_edge(wired(rec=record(**change)),market_evidence=market())
    assert p['bayesian_score'] is None and reason in p['bayesian_evidence_reasons']

def test_generic_20d_count_and_layer2_count_never_become_10d_denominator():
    rec=record();rec['payload'].pop('outcome_evidence');rec['payload']['win_rate_10d']=.61
    r=wired(rec=rec);e=json.loads(r['actuarial_evidence_json']);c=e['cohorts'][1]
    assert c['rate']==.61 and c['n'] is None and c['wins'] is None
    assert e['reported_generic_sample_size']==9000 and e['reported_layer2_sample_size']==3000

def test_matched_cache_horizon_count_is_used_without_rounding_wins():
    cache=pd.DataFrame([dict(state_key='BROAD_STATE',sample_size=9000,sample_size_10d=9100,
        win_rate_10d=.6,win_rate_20d=.5,sample_size_20d=9000)])
    result=dict(matched_key='BROAD_STATE',win_rate_10d=.6,win_rate_20d=.5,sample_size=9000)
    evidence=cache_outcomes(result,cache)
    assert evidence[1]['n']==9100 and evidence[2]['n']==9000
    assert evidence[1]['wins'] is None and evidence[1]['losses'] is None
    result['win_rate_10d']=.7
    assert cache_outcomes(result,cache)[1]['n'] is None

def tree(tmp_path):
    root=tmp_path/RUN;(root/'options').mkdir(parents=True)
    (root/'run_meta.json').write_text(json.dumps({'session_date':DAY}))
    source=root/'options'/f'options_intelligence_{RUN}.csv'
    pd.DataFrame([candidate(),candidate(ticker='SYM')]).to_csv(source,index=False)
    rec=record();write_enrichment_ledger(root,RUN,'actuarial',[rec,{**rec,'ticker':'SYM'}])
    return root,source

def test_publication_is_immutable_reusable_and_survives_phantom_bypass(tmp_path):
    root,source=tree(tmp_path);raw=source.read_bytes()
    dest,receipt=prepare_phantom_handoff(root,source)
    out=pd.read_csv(dest,keep_default_na=False)
    assert list(out.ticker)==['NAN','SYM']
    assert source.read_bytes()==raw and out.options_verdict.tolist()==['WATCH','WATCH']
    assert set(FIELDS)<=set(out.columns) and receipt['rows']==2
    assert preferred_options_input(root)==dest
    assert prepare_phantom_handoff(root,source)[1]['status']=='REUSED_VALIDATED'
    phantom=root/'options'/f'options_intelligence_phantom_{RUN}.csv';phantom.write_bytes(b'preserved')
    assert preferred_options_input(root)==phantom
    phantom.unlink() # fixture only
    (root/'run_meta.json').write_text(json.dumps({'session_date':'2026-11-20'}))
    assert preferred_options_input(root)==source
    with pytest.raises(FileExistsError):prepare_phantom_handoff(root,source)

def test_wrong_run_state_missing_and_conflicting_records_are_not_ticker_joins(tmp_path):
    root,source=tree(tmp_path)
    frame=pd.read_csv(source,keep_default_na=False);frame.loc[0,'behaviour_state_hash']='STATE_B'
    out,receipt=wire_frame(frame,root,DAY)
    assert out.iloc[0].actuarial_evidence_binding=='CONFLICTED'
    # A second different cohort cannot silently win by append order.
    write_enrichment_ledger(root,RUN,'actuarial',[record(behaviour_state_hash='STATE_C')],append=True)
    out,_=wire_frame(frame,root,DAY)
    assert 'RECORD_IDENTITY_CONFLICT' in out.iloc[0].actuarial_evidence_reasons
    wrong=record();wrong['run_id']='OTHER'
    path=root/'enrichment'/f'actuarial_{RUN}.jsonl';path.write_text(json.dumps(wrong)+'\n')
    assert wire_frame(frame,root,DAY)[1]['ledger_state']=='RUN_MISMATCH'

def test_phantom_gate_cannot_promote_incompatible_evidence_even_at_forced_high_score(monkeypatch):
    import phantom_engine as engine
    class DB:
        def latest_chain_rows(self,t):return []
    monkeypatch.setattr(engine,'compute_iv_surface',lambda *a:{'iv_entropy_score':100,'iv_evidence_available':True})
    monkeypatch.setattr(engine,'compute_gamma_trajectory',lambda *a:{'gamma_score':100,'gamma_trajectory_signed':100,'gamma_evidence_available':True})
    monkeypatch.setattr(engine,'compute_info_flow',lambda *a:{'info_flow_score':100})
    monkeypatch.setattr(engine,'compute_criticality',lambda *a:{'criticality_score':100,'criticality_order_parameter':1})
    monkeypatch.setattr(engine,'_composite',lambda *a:100)
    row=wired();p=engine.score_row(row,DB(),RUN)
    assert p['phantom_promoted_verdict']=='NONE' and p['phantom_ois_adjustment']==0
    assert engine.apply_payload(row,p)['options_verdict']=='WATCH'

def test_stage_order_and_consumer_wiring_are_explicit_without_running_pipeline():
    text=(ROOT/'intelligent_orchestrator.py').read_text(encoding='utf-8-sig')
    body=text[text.index('# ── PHASE 8.5: Actuarial Enrichment Pass'):]
    assert body.index('run_actuarial_enrichment_pass(')<body.index('prepare_phantom_handoff(')<body.index('"phantom_engine.py"')
    assert 'preferred_options_input' in text


def test_producer_records_exact_cache_counts_and_input_hash_without_inventing_wins(monkeypatch,tmp_path):
    from scripts import actuarial_enrichment_pass as producer
    cache=pd.DataFrame([dict(state_key='BROAD_STATE',sample_size_10d=110,win_rate_10d=.6)])
    for name,value in {'_ACTUARIAL_READY':True,'_CACHE_DF':cache,'_CACHE_OUTCOME_INDEX':None,
                       '_LOOKUP_FN':lambda *a:dict(matched_key='BROAD_STATE',win_rate_10d=.6,
                           valid=True,no_match=False,sample_size=90),
                       'apply_truth_packet':lambda b:b,'validate_truth_packet':lambda b:None}.items():
        monkeypatch.setattr(producer,name,value)
    block=producer._build_actuarial_block({'regime':'TEST'})
    assert block['deferred'] is False and block['reason']=='LOOKUP_COMPLETE'
    assert block['outcome_evidence'][1]['n']==110
    assert block['outcome_evidence'][1]['wins'] is None
    assert block['evidence_input_sha256']
    root=tmp_path/RUN;path=root/'packages'/'NAN.package.json';path.parent.mkdir(parents=True)
    producer._record_actuarial_fact(path,{'run_id':RUN},'NAN',block)
    saved=json.loads((root/'enrichment'/f'actuarial_{RUN}.jsonl').read_text())
    assert saved['input_sha256']==block['evidence_input_sha256']


def test_new_fields_survive_handoff_book_and_review_projection(tmp_path):
    from contracts.handoff_contract import enrich_row_with_truth_packet
    from contracts.lab_control import opportunity_book_row
    from contracts.lab_review_projection import publish_review_projection,read_review_rows,read_review_card
    row=wired()
    handoff=enrich_row_with_truth_packet(row,source='TEST',run_id=RUN)
    assert all(handoff[k]==row[k] for k in FIELDS)
    bookrow=opportunity_book_row(row,RUN,1)
    assert all(bookrow[k]==row[k] for k in FIELDS)
    receipt=publish_review_projection({'run_id':RUN,'candidate_count':1,'rows':[bookrow]},tmp_path)
    index=read_review_rows(tmp_path,RUN,revision=receipt['revision'])
    card=read_review_card(tmp_path,RUN,index['rows'][0]['row_key'],receipt['revision'])
    assert {k:card['fields'][k] for k in FIELDS}=={k:row[k] for k in FIELDS}
