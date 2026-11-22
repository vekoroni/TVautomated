from copy import deepcopy
from datetime import datetime,timezone
import gzip,json,math
import pytest
from domain.evening_target_roles import annotate_payload,target_metadata,scenario_metadata
from domain.evening_assessment import assess_evening
from contracts.contract_comparison_inventory import FIELDS,normalize_quote,normalize_inventory
from contracts.contract_rejection import classify_chain
from scripts.publish_saved_contract_comparison import publish_saved_inventory
from tests.test_evening_assessment_handoff import candidate

def quote(**kw):
    r=dict(option_symbol='NAN261218C00100000',side='call',strike=100.,dte=28.,
        bid=0.,ask=2.,iv=0.,open_interest=0,volume=0,updated_ts=1795208400)
    r.update(kw);return r

def test_names_do_not_change_target_scenario_numbers_or_source():
    row=candidate(anticipated_level_q50=111.62,anticipated_level=137.47)
    r=deepcopy(row);packet=json.loads(assess_evening(row,run_id='TEST')['evening_assessment_json'])
    assert row==r and packet['target']==111.62
    assert packet['targets']['first_target']['price']==111.62
    assert packet['targets']['full_target']['price']==137.47
    assert packet['targets']['full_target']['valuation_state']=='REFERENCE_ONLY_NOT_REPRICED'
    assert packet['targets']['full_target']['arrival_clock_field'] is None
    assert all(s['spot']==111.62 and s['target_source_field']=='anticipated_level_q50'
        for s in packet['scenarios'] if s['scenario'].startswith('TARGET_'))
    assert all(s['spot']==pytest.approx(105.81) for s in packet['scenarios'] if s['scenario']=='HALF_MOVE_IF_REACHED')
    assert row['lab_verdict']=='MANUAL_REVIEW' and row['lab_rank']==99

def test_saved_annotation_preserves_all_previous_values_and_hash_binds_full_target():
    old={'target':111.62,'source_sha256':'old','scenarios':[{'scenario':'TARGET_IF_REACHED','spot':111.62,'net_pnl_per_contract':31.2}]}
    before=deepcopy(old);row={'anticipated_level_q50':111.62,'anticipated_level':137.47}
    new=annotate_payload(old,row)
    assert old==before and new['target']==old['target']
    assert new['scenarios'][0]['net_pnl_per_contract']==31.2
    assert new['target_naming_parent_source_sha256']=='old'
    assert new['source_sha256']!=annotate_payload(old,{**row,'anticipated_level':138.})['source_sha256']
    with pytest.raises(ValueError,match='SOURCE_LEVEL_MISMATCH'):annotate_payload(old,{**row,'anticipated_level_q50':112})

@pytest.mark.parametrize('value',[None,0,-1,float('nan'),float('inf'),True])
def test_missing_full_target_stays_unassessed(value):
    t=target_metadata({'anticipated_level_q50':100,'anticipated_level':value})
    assert t['targets']['full_target']['price'] is None
    assert t['targets']['full_target']['state']=='UNASSESSED_MISSING_OR_INVALID'

def test_future_morning_does_not_relabel_frozen_packet():
    r=candidate(pipeline_mode='MORNING',evening_assessment_json='{"version":"legacy-frozen"}')
    assert assess_evening(r,run_id='TEST')['evening_assessment_json']==r['evening_assessment_json']

def test_legacy_zero_target_sentinel_is_not_a_canonical_zero_dollar_target():
    old={'target':0,'source_sha256':'old','scenarios':[]}
    new=annotate_payload(old,{'anticipated_level_q50':0,'anticipated_level':120})
    assert new['target']==0 and old['target']==0
    assert new['targets']['first_target']['price'] is None
    assert new['targets']['first_target']['state']=='UNASSESSED_MISSING_OR_INVALID'

def test_inventory_maps_exact_identity_without_manufacturing_quotes():
    raw=quote();before=deepcopy(raw);n=normalize_quote(raw)
    assert raw==before and n['raw_observation']==raw
    assert set(FIELDS)<=n.keys()
    assert n['symbol']=='NAN261218C00100000' and n['right']=='CALL' and n['expiry']=='2026-12-18'
    assert n['quote_timestamp_utc']=='2026-11-20T21:00:00+00:00'
    assert n['iv'] is None and n['field_reasons']['iv']=='NONPOSITIVE_RECORDED_IV'
    assert n['raw_observation']['iv']==0 and n['bid']==0
    assert n['gate_failed'] is None and n['gate_evidence_state']=='NOT_RECORDED_IN_SAVED_SCOPE'
    assert n['mid'] is None and n['spread_pct'] is None and n['delta'] is None
    assert n['field_basis']['expiry']=='EXACT_OCC_ENCODING'

@pytest.mark.parametrize('iv',[0,-.1,None,float('nan'),float('inf'),False,'invalid'])
def test_invalid_iv_is_unavailable_and_input_unchanged(iv):
    q=quote(iv=iv);n=normalize_quote(q)
    assert n['iv'] is None and n['iv_state']=='UNAVAILABLE'
    assert n['bid']==0
    if isinstance(iv,float) and math.isnan(iv):assert math.isnan(q['iv'])
    else:assert q['iv']==iv

def test_positive_iv_and_zero_bid_are_distinct():
    n=normalize_quote(quote(iv=.32))
    assert n['iv']==.32 and n['iv_state']=='AVAILABLE_SAVED_VALUE'
    assert n['quote_state']=='NO_OBSERVED_EXECUTABLE_BID'
    assert n['open_interest']==n['volume']==0

@pytest.mark.parametrize('patch',[{'side':'put'},{'strike':99},{'expiry':'2026-12-19'}])
def test_identity_conflict_never_becomes_clean_quote(patch):
    n=normalize_quote(quote(**patch))
    assert n['quote_state']=='INVALID_OR_IDENTITY_CONFLICT'

def test_unzoned_time_and_invalid_expiry_not_guessed():
    n=normalize_quote(quote(quote_timestamp_utc='2026-11-20T21:00:00',expiry='bad'))
    assert n['quote_timestamp_utc'] is None and n['expiry'] is None
    assert n['raw_observation']['expiry']=='bad'

def test_gate_counts_legacy_records_and_selection_remain_separate():
    r=dict(symbol='NAN261218C00100000',right='C',dte=28,delta=.5,bid=2,ask=2.1,iv=0,
        mark=2.05,spread_pct=.05,quote_quality='TWO_SIDED',strike=100)
    result=classify_chain([r],direction='CALL',dte_min=1,dte_max=60,delta_min=.2,delta_max=.7,spread_limit=.2)
    assert result['gate_counts']['ACCEPTED']==1
    assert result['contracts_tested'][0]['iv']==0 # Existing raw legacy record is retained.
    n=result['available_contracts_both_sides']['CALL']['contracts'][0]
    assert n['iv'] is None and n['raw_observation']['iv']==0 and n['gate_evidence_state']=='CLASSIFIED_PASS'
    assert result['available_contracts_both_sides']['PUT']['total_contracts']==0

def test_adapter_preserves_raw_file_and_every_quote_and_refuses_overwrite(tmp_path):
    record={'ticker':'NAN','session':'2026-11-20','available_contracts_both_sides':{
        'CALL':{'state':'AVAILABLE','contracts':[quote(),quote(iv=.3,bid=1.)]},'PUT':{'contracts':[]}}}
    source=tmp_path/'raw.jsonl';source.write_text(json.dumps(record)+'\n');before=source.read_bytes()
    dest=tmp_path/'view.jsonl.gz';receipt=publish_saved_inventory(source,dest)
    with gzip.open(dest,'rt') as stream:view=json.load(stream)
    assert receipt['counts']['quotes']==2 and receipt['counts']['raw_zero_iv']==1
    assert source.read_bytes()==before and view['provider_chain_completeness']=='NOT_ESTABLISHED'
    assert view['available_contracts_both_sides']['CALL']['contracts'][0]['raw_observation']==quote()
    with pytest.raises(ValueError,match='CREATE_ONLY'):publish_saved_inventory(source,dest)
