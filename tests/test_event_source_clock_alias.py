from contracts.macro_feed_delivery import source_observation_time, _stamp
import pytest


def test_native_event_cutoff_alias_preserves_exact_source_time():
    packet={'run_context':{'information_cutoff':'2026-11-10T17:09:27Z'}}
    assert source_observation_time('events',packet)=='2026-11-10T17:09:27Z'
    assert packet['run_context']=={'information_cutoff':'2026-11-10T17:09:27Z'}


def test_explicit_utc_field_remains_primary():
    packet={'run_context':{'information_cutoff_utc':'2026-11-10T15:33:02Z','information_cutoff':'2026-11-10T17:09:27Z'}}
    assert source_observation_time('events',packet)=='2026-11-10T15:33:02Z'


def test_no_clock_is_not_replaced_with_receipt_time():
    assert source_observation_time('events',{'events':[]}) is None


def test_alias_without_timezone_still_fails_validation():
    with pytest.raises(ValueError):
        _stamp(source_observation_time('events',{'run_context':{'information_cutoff':'2026-11-10'}}))
