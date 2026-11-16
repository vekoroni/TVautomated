"""Saved snapshot compatibility/display tests. No pricing or provider requests."""
from copy import deepcopy
import json
import pytest
from contracts.lab_snapshot_disclosure import scope_snapshot


@pytest.mark.parametrize('trusted',[False,True])
@pytest.mark.parametrize('matching_clock',[False,True])
def test_saved_reference_requires_exact_thesis_contract_and_valuation_clock(tmp_path,trusted,matching_clock):
    import csv
    from contracts.lab_review_sources import prepare_review_publication
    row=dks(); row.update(run_id='RUN',thesis_id='TH',trade_idea_id='ID',validation_event_id='EV')
    for key in ('selected_quote_source','monetisability_timevalue_as_of_session'):
        row.pop(key)
    root=tmp_path/'RUN'; folder=root/'morning_validation';folder.mkdir(parents=True)
    saved={**row,'selected_quote_source':'MARKETDATA','monetisability_timevalue_as_of_session':'2026-11-13'}
    if not matching_clock: saved['anticipated_valued_at_utc']='2026-11-16T15:00:00Z'
    with (folder/'morning_validated_trades_RUN.csv').open('w',newline='',encoding='utf-8') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(saved));writer.writeheader();writer.writerow(saved)
    book={'run_id':'RUN','candidate_count':1,'rows':[row],'created_at_utc':'2026-11-16T15:20:00Z'}
    original=deepcopy(book)
    receipt={'status':'PASS','authority':'VALIDATION_ONLY','input_rows':1,'lab_projection_issues':[]}
    prepared,_,_=prepare_review_publication(book,root,validation_receipt=receipt if trusted else None)
    assert book==original
    output=scope_snapshot(prepared['rows'][0]);d=output['snapshot_disclosure']
    assert (d['quote']['configured_delay_seconds']==900)==matching_clock
    assert (d['historical_timevalue']['as_of_session']=='2026-11-13')==matching_clock
    assert output['scenario_target_return_on_premium']==-.1411
    assert output['lab_verdict']=='MANUAL_REVIEW'


def dks():
    return dict(ticker='DKS',contract_symbol='DKS261204P00150000',expiry='2026-12-04',
        contract_ask=12.4,contract_bid=9.5,contract_iv=.6685,lab_verdict='MANUAL_REVIEW',lab_rank=9,
        anticipated_contract_symbol='DKS261204P00150000',anticipated_contract_basis='MORNING_CONTRACT_RECOMPUTED:DKS261204P00150000',
        anticipated_valued_at_utc='2026-11-16T14:57:52Z',anticipated_value_multiple_q50=.8589,
        scenario_target_return_on_premium=-.1411,scenario_exit_sessions=3,scenario_exit_date='2026-11-19',
        scenario_state='NOT_ASSESSED',scenario_reason='DOI_SCENARIOS_ABSENT',
        valuation_model='AMERICAN_CRR',valuation_version='option_valuation_v1',
        valuation_cost_basis='ASK_PLUS_FEES_AND_EXIT_SPREAD',valuation_entry_cost_usd_per_share=12.411,
        valuation_rate_annual=.0432,valuation_rate_basis='SAVED',valuation_dividend_yield_annual=.0343,
        valuation_dividend_basis='SAVED',planned_hold_sessions=3,
        planned_hold_source='VOLATILITY_TIME_TO_LEVEL_CALIBRATED_Q80',
        anticipated_evidence_status='NO_COMPARABLE_EVIDENCE',anticipated_sessions_q50=None,
        ev3_status='REJECTED',ev3_reason_detail='horizon=NO_EVIDENCE_HOLD, planned_hold_sessions=None',
        selected_quote_source='MARKETDATA',selected_quote_timestamp_utc='2026-11-16T14:57:52Z',
        quote_freshness='FRESH',execution_viability_quote_age_state='WITHIN_FEED_WINDOW',
        execution_viability_quote_age_minutes=27.5,execution_viability_quote_age_seconds=748.17,
        monetisability_evaluation_phase='EOD_CLOSE',monetisability_contract_symbol='DKS261204P00150000',
        monetisability_timevalue_value_per_share=12.700833,monetisability_timevalue_profit_pct=15.4621,
        monetisability_timevalue_as_of_session='2026-11-13',monetisability_timevalue_expiry_date='2026-12-11',
        monetisability_timevalue_iv_used=.6267,monetisability_state_timevalue='LIMITED')


def test_incompatible_dks_reference_is_archived_not_overlaid_or_repriced():
    row=dks();original=deepcopy(row);out=scope_snapshot(row);d=out['snapshot_disclosure']
    assert row==original
    assert out['lab_verdict']==row['lab_verdict'] and out['lab_rank']==row['lab_rank']
    assert out['scenario_target_return_on_premium']==-.1411
    assert out['anticipated_value_multiple_q50']==.8589
    assert out['monetisability_timevalue_profit_pct'] is None
    assert out['monetisability_state_timevalue']=='HISTORICAL_REFERENCE_ONLY'
    reference=out['reference_snapshots']['historical_timevalue']
    assert reference['fields']['monetisability_timevalue_profit_pct']==15.4621
    assert set(reference['mismatch_reasons'])=={'AS_OF_SESSION_MISMATCH','EXPIRY_MISMATCH','IV_MISMATCH','ENTRY_ASK_MISMATCH','EOD_REFERENCE_PHASE'}
    assert d['current_scenario']['state']=='MORNING_REFERENCE'
    assert d['doi_scenario']['state']=='NOT_ASSESSED'
    assert d['historical_timevalue']['expiry']=='2026-12-11'
    assert scope_snapshot(out)==out, 'Repeated display publication must not erase archived evidence'


def test_fmc_legacy_iv_and_price_do_not_override_current_loss():
    row=dks();row.update(ticker='FMC',contract_symbol='FMC270115P00095000',expiry='2027-01-15',
        contract_ask=90.1,contract_iv=3.4362,anticipated_contract_symbol='FMC270115P00095000',
        anticipated_contract_basis='MORNING_REPRICED:FMC270115P00095000',
        anticipated_value_multiple_q50=.9909,scenario_target_return_on_premium=-.0091,
        monetisability_timevalue_value_per_share=90.595457,monetisability_timevalue_profit_pct=-.6629,
        monetisability_timevalue_expiry_date='2027-01-15',monetisability_timevalue_iv_used=4.4329)
    out=scope_snapshot(row)
    assert out['scenario_target_return_on_premium']==-.0091
    assert out['monetisability_timevalue_value_per_share'] is None
    assert out['reference_snapshots']['historical_timevalue']['fields']['monetisability_timevalue_iv_used']==4.4329


def test_compatible_saved_timevalue_is_kept_without_claiming_live_or_expected_return():
    row=dks();row.update(monetisability_evaluation_phase='MORNING_REFERENCE',
        monetisability_timevalue_as_of_session='2026-11-16',monetisability_timevalue_expiry_date='2026-12-04',
        monetisability_timevalue_iv_used=.6685,monetisability_timevalue_value_per_share=12.4,
        monetisability_timevalue_profit_pct=0)
    out=scope_snapshot(row)
    assert out['monetisability_timevalue_profit_pct']==0
    assert out['snapshot_disclosure']['historical_timevalue']['state']=='MATCHING_SAVED_INPUTS'
    assert not out['snapshot_disclosure']['quote']['entry_quote_verified']


def test_quotes_disclose_raw_and_effective_age_without_a_live_countdown():
    row=dks();out=scope_snapshot(row);q=out['snapshot_disclosure']['quote']
    assert q['state']=='SAVED_QUOTE_REFERENCE_NOT_LIVE'
    assert q['configured_delay_seconds']==900 and q['configured_effective_window_seconds']==900
    assert q['saved_raw_age_minutes']==27.5 and q['saved_effective_age_seconds']==748.17
    assert q['saved_assessment_state']=='WITHIN_FEED_WINDOW'
    row['execution_viability_quote_age_seconds']=0
    assert scope_snapshot(row)['snapshot_disclosure']['quote']['saved_effective_age_seconds']==0
    row['selected_quote_source']='UNKNOWN';row['selected_quote_timestamp_utc']=None
    q=scope_snapshot(row)['snapshot_disclosure']['quote']
    assert q['configured_delay_seconds'] is None
    assert q['state']=='QUOTE_OBSERVATION_TIME_NOT_RECORDED'


def test_fallback_timing_and_missing_evidence_are_not_renamed_historical_n():
    t=scope_snapshot(dks())['snapshot_disclosure']['timing']
    assert t['hold_basis']=='VOLATILITY_PLANNING_FALLBACK'
    assert t['arrival_state']=='NO_HISTORICAL_ARRIVAL_ESTIMATE'
    assert t['ev3_status']=='REJECTED'
    assert t['evidence_n'] is None


def test_projection_publishes_scoped_metadata_without_changing_verdict_or_source(tmp_path,monkeypatch):
    import requests
    monkeypatch.setattr(requests.sessions.Session,'request',lambda *a,**k:pytest.fail('No providers'))
    from contracts.lab_review_projection import publish_review_projection,read_review_rows,read_review_card,read_review_evidence
    row=dks();book=dict(run_id='TEST',candidate_count=1,rows=[row]);frozen=deepcopy(book)
    manifest=publish_review_projection(book,tmp_path)
    home=read_review_rows(tmp_path,'TEST')['rows'][0]
    card=read_review_card(tmp_path,'TEST',home['row_key'])
    assert book==frozen
    assert card['fields']['lab_verdict']=='MANUAL_REVIEW'
    audit=read_review_evidence(tmp_path,'TEST',home['row_key'],'audit',manifest['revision'])['fields']
    assert audit['monetisability_timevalue_profit_pct'] is None
    assert audit['reference_snapshots']['historical_timevalue']['fields']['monetisability_timevalue_profit_pct']==15.4621
    assert card['snapshot_disclosure']==home['snapshot_disclosure']
    assert card['snapshot_disclosure']['historical_timevalue']['return_pct']==15.4621
