"""Board-only Event ordering: saved source clocks, no synthesis or network."""
from copy import deepcopy
from types import SimpleNamespace

import pytest

from macro_board.build_board import build_intel


def event(identity, cutoff=None, **extra):
    return dict(event_id=identity, event_name=identity, information_cutoff_utc=cutoff, **extra)


def ordered(events, limit=None):
    source={'events':events, 'run_context':{'generated_utc':'2099-01-01T00:00:00Z'}}
    before=deepcopy(source)
    external={'event_payload':SimpleNamespace(status='FRESH', data=source)}
    result=build_intel(external, None, max_events=limit)['events']
    assert source==before, 'Ordering must not rewrite source dates or values'
    return result


def ids(result):
    return [row['event_id'] for row in result['events']]


def test_existing_callers_keep_eight_row_default_with_newest_first():
    rows=[event(str(i),f'2026-11-{i+1:02d}T12:00:00Z') for i in range(10)]
    external={'event_payload':SimpleNamespace(status='FRESH',data={'events':rows})}
    result=build_intel(external,None)['events']
    assert ids(result)==['9','8','7','6','5','4','3','2']


def test_latest_bowman_nested_cutoff_is_first_before_eight_row_limit():
    bowman=event('US_FED_BOWMAN_ECONOMIC_OUTLOOK_2026-11-10_203000Z',
                 market_perception={'observation_window':{
                     'event_reference_utc':'2026-11-10T20:30:00Z',
                     'information_cutoff_utc':'2026-11-10T21:34:00Z'}})
    old=[event(f'older-{i}', f'2026-10-{i+1:02d}T12:00:00Z') for i in range(10)]
    result=ordered(old+[bowman],8)
    assert ids(result)[0]==bowman['event_id']
    assert len(result['events'])==8
    assert result['coverage']['total_events']==11
    assert result['coverage']['omitted_historical_events']==3


def test_offsets_are_compared_as_instants_not_lexical_strings():
    earlier=event('earlier','2026-11-10T21:33:00Z')
    later=event('later',market_perception={'observation_window':{
        'information_cutoff_utc':'2026-11-10T22:34:00+01:00'}})
    assert ids(ordered([earlier,later]))==['later','earlier']


def test_explicit_top_level_source_cutoff_keeps_existing_precedence():
    source=event('source','2026-11-10T20:00:00Z',market_perception={
        'observation_window':{'information_cutoff_utc':'2026-11-10T22:00:00Z'}})
    other=event('other','2026-11-10T21:00:00Z')
    assert ids(ordered([source,other]))==['other','source']


@pytest.mark.parametrize('perception',[None,[], 'unknown', {'observation_window':None},
                                     {'observation_window':[]}, {'observation_window':'unknown'}])
def test_malformed_nested_window_keeps_valid_release_fallback(perception):
    source=event('fallback',market_perception=perception,release_time_utc='2026-11-10T21:00:00Z')
    older=event('older','2026-11-10T20:00:00Z')
    assert ids(ordered([older,source]))==['fallback','older']


@pytest.mark.parametrize('cutoff',[None,'not-a-date','2026-11-10T23:59:00'])
def test_missing_invalid_and_naive_times_are_not_promoted_by_receipt_or_identity(cutoff):
    unknown=event('2099-12-31-future-looking-id',market_perception={
        'observation_window':{'information_cutoff_utc':cutoff}})
    dated=event('dated','2026-11-10T21:00:00Z')
    assert ids(ordered([unknown,dated]))==['dated',unknown['event_id']]


def test_invalid_direct_clock_can_use_valid_nested_clock():
    nested=event('nested','invalid',market_perception={'observation_window':{
        'information_cutoff_utc':'2026-11-10T21:34:00Z'}})
    assert ids(ordered([event('older','2026-11-10T21:33:00Z'),nested]))==['nested','older']


def test_legacy_release_fields_and_unlimited_zero_and_tied_order_are_preserved():
    rows=[event('release', release_time_utc='2026-11-10T20:00:00Z'),
          event('original', original_report_release_time_utc='2026-11-10T21:00:00Z'),
          event('tied','2026-11-10T21:00:00Z'), event('unknown')]
    assert ids(ordered(rows))==['original','tied','release','unknown']
    assert ordered(rows,0)['events']==[]
