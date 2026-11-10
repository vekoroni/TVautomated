"""An explicit null producer placeholder is not permission to select a trade."""
import copy
import json
from pathlib import Path

import pytest

from contracts.us_money_index_contract import normalise_us_money_index_sidecar, USMoneyIndexValidationError


def packet(value=None, execution=False):
    path = Path(__file__).parent / 'fixtures/us_money_index_v2_text_flags_20261008.json'
    source = json.loads(path.read_text(encoding='utf-8'))
    source['options_monetisation']['rev63_financing_risk_and_options_monetisation'] = {
        'selected_contract': value, 'execution_approved': execution}
    return source


def test_null_placeholder_preserves_original_and_never_grants_authority():
    source = packet()
    before = copy.deepcopy(source)
    result = normalise_us_money_index_sidecar(source)
    assert source == before == result['source_payload']
    assert result['authority'] == 'ADVISORY_ONLY'
    assert result['execution_permission'] == 'NONE_INTELLIGENCE_ONLY'
    assert result['policy_activation'] == 'DISABLED_UNTIL_SEPARATELY_TESTED'
    assert any('absence only' in issue for issue in result['quality_issues'])


@pytest.mark.parametrize('value', ['', 'SPY261120P00600000', {}, [], False, 0])
def test_non_null_selection_stays_forbidden(value):
    with pytest.raises(USMoneyIndexValidationError, match='authority fields are forbidden'):
        normalise_us_money_index_sidecar(packet(value))


@pytest.mark.parametrize('execution', [None, True, 'false', 0])
def test_null_requires_explicit_false_execution(execution):
    with pytest.raises(USMoneyIndexValidationError, match='authority fields are forbidden'):
        normalise_us_money_index_sidecar(packet(execution=execution))


def test_other_authority_paths_remain_forbidden_even_if_null():
    source = packet()
    source['selected_contract'] = None
    with pytest.raises(USMoneyIndexValidationError, match='authority fields are forbidden'):
        normalise_us_money_index_sidecar(source)
