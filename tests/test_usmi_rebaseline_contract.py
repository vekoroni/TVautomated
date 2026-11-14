"""The new partial baseline must not invent a score or weaken the old contract."""
import copy
import json
from pathlib import Path
import pytest
from contracts.us_money_index_contract import validate_us_money_index_packet, attach_us_money_index
from contracts.interpreter_macro_context import materialize_interpreter_macro_context


def baseline():
    source=json.loads((Path(__file__).parent/'fixtures/us_money_index_v2_text_flags_20261008.json').read_bytes())
    source.update(contract_version='avshunter_us_money_index_v2_1', authority='ADVISORY_ONLY',
                  automatic_execution=False, manual_review_required=True)
    source['baseline_lineage']={
        'baseline_id':'USMI_REBASELINE_20261110_V1', 'status':'NEW_BASELINE_HISTORY_INCOMPLETE',
        'prior_canonical_revision_reported':73, 'prior_canonical_bytes_recovered':False,
        'revision_semantics':'DELIVERY_SEQUENCE_NOT_RECOVERED_HISTORY',
        'source_chat':'6ae19fab-20f0-83ed-a8e2-34dbfb1993d8','source_message':'fixture-only'}
    source['current_state'].update(state_confidence=None,risk_off_transmission_score=None,
        regime_change_since_monday=None,monetisation_change_since_monday=None,risk_off_transition=None)
    source['risk_off_transmission_score']={'current_score':None,'components':{},
        'assessment_status':'UNASSESSED_METHODOLOGY_NOT_RECOVERED'}
    source['data_quality']['overall']='PARTIAL_UNVERIFIED_REBASELINE'
    source['options_monetisation']['long_call_priority']=[]
    source['options_monetisation']['long_put_priority']=[]
    return source


def test_unknowns_are_lossless_non_executable_and_non_calculative():
    source=baseline(); before=copy.deepcopy(source)
    result=validate_us_money_index_packet(source)
    assert result['valid'],result['errors']
    packet=result['packet']
    assert packet['source_payload']==source==before
    assert packet['state']['risk_off_transmission_score'] is None
    assert packet['state']['state_confidence'] is None
    assert packet['state']['risk_off_transition'] is None
    assert 'risk_off_transmission_score' not in packet['metrics']
    assert packet['sector_routing']=={'CALL':{},'PUT':{}}
    assert packet['quality_status']=='PARTIAL_UNVERIFIED'
    assert packet['policy_activation']=='DISABLED_UNTIL_SEPARATELY_TESTED'
    assert packet['execution_permission']=='NONE_INTELLIGENCE_ONLY'


@pytest.mark.parametrize('mutation',[
    lambda p:p['current_state'].update(state_confidence=0.8),
    lambda p:p['current_state'].update(risk_off_transmission_score=81),
    lambda p:p['risk_off_transmission_score'].update(current_score=81),
    lambda p:p['risk_off_transmission_score'].update(components={'made_up':{'score':81}}),
    lambda p:p.update(automatic_execution=True),
    lambda p:p.update(execution_permission='ENABLED'),
    lambda p:p.update(selected_contract=None),
    lambda p:p['baseline_lineage'].update(prior_canonical_bytes_recovered=True),
    lambda p:p['data_quality'].update(overall='VERIFIED'),
    lambda p:p['baseline_lineage'].update(source_chat='different-producer'),
])
def test_unsafe_rebaseline_is_rejected(mutation):
    p=baseline();mutation(p)
    assert not validate_us_money_index_packet(p)['valid']


def test_old_v2_does_not_gain_nullable_score_exception():
    p=baseline();p['contract_version']='avshunter_us_money_index_v2_0'
    assert not validate_us_money_index_packet(p)['valid']


def test_native_nested_safety_requires_complete_explicit_block_without_conflicts():
    p=baseline()
    for key in ('automatic_execution','manual_review_required','authority','execution_permission'):
        p['current_state'][key]=p.pop(key)
    assert validate_us_money_index_packet(p)['valid']
    p['automatic_execution']=True
    assert not validate_us_money_index_packet(p)['valid']
    p.pop('automatic_execution')
    p['current_state'].pop('manual_review_required')
    assert not validate_us_money_index_packet(p)['valid']


def test_saved_pipeline_interpreter_consumes_unknowns_without_live_run(tmp_path):
    p=validate_us_money_index_packet(baseline())['packet']
    macro=attach_us_money_index({},p)
    run=tmp_path/'run';run.mkdir()
    (run/'macro_snapshot.json').write_text(json.dumps(macro),encoding='utf-8')
    result=materialize_interpreter_macro_context(run_dir=run,session_date='2026-11-10',
        macro_dir=tmp_path/'macro',prefer_run_snapshot=True)['packet']
    assert result['us_money_index']['state']['risk_off_transmission_score'] is None
    assert result['us_money_index']['policy_activation']=='DISABLED_UNTIL_SEPARATELY_TESTED'


def test_etf_board_preserves_partial_baseline_and_unknown_score():
    from types import SimpleNamespace
    from macro_board.build_board import build_intel
    p=baseline()
    intel=build_intel({'us_money_index':SimpleNamespace(status='FRESH',data=p)},None)
    assert intel['usmi']['score'] is None
    assert intel['usmi']['confidence'] is None
    assert intel['usmi']['baseline_lineage']==p['baseline_lineage']
    assert intel['usmi']['data_quality']['overall']=='PARTIAL_UNVERIFIED_REBASELINE'


def test_new_dated_observations_keep_intraday_and_lagged_meanings():
    from macro_board.build_board import _dated
    p=baseline()
    p['cross_asset']['equities']['current_global_session']={
        'sp500':{'level':7508.27,'day_change_pct':-0.55},'snapshot_at_utc':'2026-11-10T19:45:00Z'}
    p['cross_asset']['credit']={'hy_oas_pct':3.34,'observation_date':'2026-11-09'}
    rows=_dated(p)
    assert any('not close' in r['metric'] and r['observed']=='2026-11-10T19:45:00Z' for r in rows)
    assert any(r['metric']=='HY OAS %' and r['observed'].startswith('2026-11-09') for r in rows)
