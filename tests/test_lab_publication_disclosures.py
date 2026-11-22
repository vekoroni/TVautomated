from copy import deepcopy
import json
import pytest
from contracts.lab_publication_disclosures import FIELDS,SCORE_FIELDS,publication_disclosures
from contracts.required_research_monitor import MONITOR_FIELDS
from contracts.lab_control import build_final_opportunity_book,FINAL_BOOK_FIELDS
from contracts.lab_review_projection import publish_review_projection,read_review_rows,read_review_card
from test_evening_assessment_handoff import candidate

def saved_packet():
    return dict(required_monitoring=False,monitoring_reason='',monitoring_execution_authority='NONE',
        thesis_reassessment_status='REASSESSMENT_REQUIRED',thesis_reassessment_reason='SAVED_EVENT',
        thesis_reassessment_event_time_utc='2026-11-21T00:55:00Z',thesis_reassessment_source_url='saved://source',
        ranking_score_source='LEGACY_FALLBACK',ranking_score_100=None,ranking_score_eod_50=0.0)

def test_ten_fields_are_saved_without_overwrite_or_current_policy_mix():
    row={'ticker':'CAPR',**saved_packet(),'options_research_score':99}
    before=deepcopy(row);out=publication_disclosures(row,as_of='2026-11-25')
    assert row==before and out==saved_packet() and len(FIELDS)==10

@pytest.mark.parametrize('group',[MONITOR_FIELDS,SCORE_FIELDS])
def test_partial_saved_packet_remains_unassessed_not_mixed_with_current_defaults(group):
    row={'ticker':'CAPR',group[0]:None,'options_research_score':77}
    out=publication_disclosures(row,as_of='2026-11-25')
    assert all(out[k] is None for k in group)

def test_new_disclosures_are_dated_and_do_not_grant_permission():
    row={'ticker':'CAPR','options_score':6,'options_research_score':77,'lab_verdict':'BLOCKED'}
    old=deepcopy(row)
    before=publication_disclosures(row,as_of='2026-11-20T21:00:00Z')
    after=publication_disclosures(row,as_of='2026-11-23T21:00:00Z')
    assert before['thesis_reassessment_status']=='' and before['required_monitoring'] is False
    assert after['thesis_reassessment_status']=='REASSESSMENT_REQUIRED' and after['required_monitoring'] is True
    assert after['monitoring_execution_authority']=='NONE'
    assert after['ranking_score_100']==77 and after['ranking_score_eod_50']==38.5
    assert row==old

def test_materializer_preserves_saved_fields_and_original_trading_outputs():
    source=candidate(ticker='CAPR',**saved_packet());old=deepcopy(source)
    result=build_final_opportunity_book('TEST',[source],{'pipeline_mode':'EOD','evidence_cutoff_utc':'2026-11-25T21:00:00Z'})[0]
    assert source==old
    assert set(FIELDS)<=set(FINAL_BOOK_FIELDS)
    for k,v in saved_packet().items():assert result[k]==v,(k,result[k],v)
    assert result['contract_symbol']==source['contract_symbol']
    assert result['lab_verdict']=='MANUAL_REVIEW'

def test_fresh_materializer_uses_run_decision_clock_not_wall_clock():
    source=candidate(ticker='CAPR',options_score=6,options_research_score=77)
    early=build_final_opportunity_book('TEST',[source],{'pipeline_mode':'EOD','evidence_cutoff_utc':'2026-11-20T21:00:00Z'})[0]
    late=build_final_opportunity_book('TEST',[source],{'pipeline_mode':'EOD','evidence_cutoff_utc':'2026-11-23T21:00:00Z'})[0]
    assert early['thesis_reassessment_status']==''
    assert late['thesis_reassessment_status']=='REASSESSMENT_REQUIRED'
    assert late['ranking_score_100']==77 and late['ranking_score_eod_50']==38.5
    for k in ('lab_verdict','lab_rank','priority_rank','contract_symbol','final_action'):
        assert early[k]==late[k]

def test_projection_exposes_all_ten_fields_in_home_and_card_without_changes(tmp_path):
    r=candidate(**saved_packet());book={'run_id':'TEST','candidate_count':1,'rows':[r]};old=deepcopy(book)
    pub=publish_review_projection(book,tmp_path)
    home=read_review_rows(tmp_path,'TEST',revision=pub['revision'])['rows'][0]
    card=read_review_card(tmp_path,'TEST',home['row_key'],pub['revision'])
    for k,v in saved_packet().items():assert home[k]==v and card['fields'][k]==v
    assert book==old

def test_absent_saved_fields_are_not_fabricated_at_projection_time(tmp_path):
    r=candidate(ticker='CAPR')
    pub=publish_review_projection({'run_id':'TEST','candidate_count':1,'rows':[r]},tmp_path)
    home=read_review_rows(tmp_path,'TEST',revision=pub['revision'])['rows'][0]
    assert all(home[f] is None for f in FIELDS)
    # Policy overlay is visibly separate and confers no entry authority.
    assert home['current_monitoring']['authority']=='DISPLAY_ONLY_CURRENT_NOTICE'

def test_old_generation_stays_readable_and_unchanged(tmp_path,monkeypatch):
    import contracts.lab_review_projection as p
    monkeypatch.setattr(p,'HOME_FIELDS',tuple(f for f in p.HOME_FIELDS if f not in FIELDS))
    monkeypatch.setattr(p,'CARD_FIELDS',tuple(f for f in p.CARD_FIELDS if f not in FIELDS))
    pub=p.publish_review_projection({'run_id':'TEST','candidate_count':1,'rows':[candidate()]},tmp_path)
    folder=tmp_path/'TEST/intelligence_lab/review_projection'
    before={f:f.read_bytes() for f in folder.iterdir() if f.is_file()}
    monkeypatch.undo()
    home=p.read_review_rows(tmp_path,'TEST',revision=pub['revision'])['rows'][0]
    p.read_review_card(tmp_path,'TEST',home['row_key'],pub['revision'])
    assert {f:f.read_bytes() for f in before}==before
