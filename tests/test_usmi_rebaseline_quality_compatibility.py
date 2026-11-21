"""Producer partial evidence labels cannot restore history or grant authority."""
from copy import deepcopy
import json
from pathlib import Path
import pytest
from contracts.us_money_index_contract import normalise_us_money_index_sidecar, USMoneyIndexValidationError


def packet():
    raw = json.loads((Path(__file__).parent / 'fixtures/macro_delivery_20261022/usmi.json').read_text(encoding='utf-8'))
    raw['contract_version'] = 'avshunter_us_money_index_v2_1'
    raw['baseline_lineage'] = {
        'baseline_id': 'USMI_REBASELINE_20261110_V1', 'status': 'NEW_BASELINE_HISTORY_INCOMPLETE',
        'prior_canonical_revision_reported': 73, 'prior_canonical_bytes_recovered': False,
        'revision_semantics': 'DELIVERY_SEQUENCE_NOT_RECOVERED_HISTORY',
        'source_chat': '6ae19fab-20f0-83ed-a8e2-34dbfb1993d8', 'source_message': 'saved-fixture'}
    raw.update(automatic_execution=False, manual_review_required=True,
               execution_permission='NONE_INTELLIGENCE_ONLY', authority='ADVISORY_ONLY')
    raw['current_state'].update(state_confidence=None, risk_off_transmission_score=None)
    raw['risk_off_transmission_score'] = {'current_score': None, 'components': {},
        'assessment_status': 'UNASSESSED_METHODOLOGY_NOT_RECOVERED'}
    raw['data_quality']['overall'] = 'PARTIAL_VERIFIED_REUTERS_16_50Z_CBOE_UNCONFIRMED_GEX_OPTIONS'
    return raw


def test_partial_producer_description_is_preserved_but_never_promoted():
    raw = packet(); frozen = deepcopy(raw)
    out = normalise_us_money_index_sidecar(raw)
    assert raw == frozen and out['source_payload'] == frozen
    assert out['quality_status'] == 'PARTIAL_UNVERIFIED'
    assert out['authority'] == 'ADVISORY_ONLY'
    assert out['execution_permission'] == 'NONE_INTELLIGENCE_ONLY'
    assert out['state']['state_confidence'] is None
    assert out['state']['risk_off_transmission_score'] is None
    assert any('PRODUCER_PARTIAL_QUALITY_DESCRIPTION_ONLY' in s for s in out['quality_issues'])
    assert 'NEW_BASELINE_HISTORY_INCOMPLETE' in out['quality_issues']


@pytest.mark.parametrize('label', ['VERIFIED', 'FULL_VERIFIED', 'HISTORY_RECOVERED', '', 'PARTIAL_VERIFIED_'])
def test_nonpartial_or_malformed_quality_still_fails(label):
    raw = packet(); raw['data_quality']['overall'] = label
    with pytest.raises(USMoneyIndexValidationError):
        normalise_us_money_index_sidecar(raw)


@pytest.mark.parametrize('section,key,value', [
    ('baseline_lineage', 'prior_canonical_bytes_recovered', True),
    ('baseline_lineage', 'status', 'HISTORY_RECOVERED'),
    ('baseline_lineage', 'baseline_id', 'UNKNOWN'),
    ('current_state', 'state_confidence', 0.9),
    ('current_state', 'risk_off_transmission_score', 42),
    ('risk_off_transmission_score', 'current_score', 42),
    ('risk_off_transmission_score', 'components', {'invented': 42}),
    ('current_state', 'automatic_execution', True),
])
def test_compatibility_does_not_relax_rebaseline_safety(section,key,value):
    raw = packet(); raw[section][key] = value
    with pytest.raises(USMoneyIndexValidationError):
        normalise_us_money_index_sidecar(raw)


def test_existing_rebaseline_label_and_unknown_null_flags_are_preserved():
    raw = packet(); raw['data_quality']['overall'] = 'PARTIAL_UNVERIFIED_REBASELINE'
    raw['current_state']['risk_off_transition'] = None
    out = normalise_us_money_index_sidecar(raw)
    assert out['quality_status'] == 'PARTIAL_UNVERIFIED'
    assert out['state']['risk_off_transition'] is None
