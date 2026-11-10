"""The new partial baseline must not invent a score or weaken the old contract."""
import copy
import json
from pathlib import Path
import pytest
from contracts.us_money_index_contract import validate_us_money_index_packet, attach_us_money_index


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
