"""Pure disclosure dependency tests; no EOD ranking-engine activation."""
import math
import pytest

from contracts.research_score_handoff import score_handoff


@pytest.mark.parametrize('raw', [0, '0', 20, 77, 100])
def test_valid_research_score_retains_provenance_and_scale(raw):
    row = {'options_research_score': raw, 'options_score': 6}
    before = dict(row)
    result = score_handoff(row)
    assert result['ranking_score_source'] == 'OPTIONS_RESEARCH'
    assert result['ranking_score_100'] == float(raw)
    assert result['ranking_score_eod_50'] == float(raw) / 2
    assert result['ranking_score_authority'] == 'RESEARCH_RANKING_ONLY'
    assert row == before


@pytest.mark.parametrize('raw', [-1, 101, math.inf, 'bad'])
def test_invalid_research_does_not_substitute_a_high_legacy_score(raw):
    result = score_handoff({'options_research_score': raw, 'options_score': 99})
    assert result['ranking_score_source'] == 'INVALID_OPTIONS_RESEARCH'
    assert result['ranking_score_100'] is None
    assert result['ranking_score_eod_50'] == 0


@pytest.mark.parametrize('raw', [None, '', 'nan', 'none'])
def test_absent_research_retains_explicit_legacy_lineage(raw):
    result = score_handoff({'options_research_score': raw, 'options_score': 7})
    assert result['ranking_score_source'] == 'LEGACY_FALLBACK'
    assert result['ranking_score_100'] is None
    assert result['ranking_score_eod_50'] == 7
