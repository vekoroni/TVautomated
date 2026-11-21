"""Offline cost controls: fake clients only, isolated ledgers, no real builds."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from types import SimpleNamespace

import pytest
from contracts import macro_api_cost as cost
from contracts import macro_build_budget as builds
from contracts.macro_prompt_projection import compact_context, columnar_records, deduplicate, research_view

ROOT = Path(__file__).resolve().parents[1]
# The governed daily cap is read from configuration, never repeated as a literal (ACK 21 Nov 2026: USD 4).
CAP_USD = json.loads((ROOT/'config'/'macro_api_cost_v1.json').read_text(encoding='utf-8'))['daily_cap_usd']
NOW = datetime(2026, 11, 19, 15, tzinfo=timezone.utc)
REQUEST = {'model': 'claude-sonnet-4-6', 'max_tokens': 16000,
           'system': 'contract', 'messages': [{'role': 'user', 'content': 'evidence'}]}


@pytest.fixture
def root(tmp_path):
    (tmp_path/'config').mkdir()
    (tmp_path/'data/macro/delivery').mkdir(parents=True)
    for name in ('macro_api_cost_v1.json', 'macro_build_schedule_v1.json'):
        (tmp_path/'config'/name).write_bytes((ROOT/'config'/name).read_bytes())
    return tmp_path


def response(**usage):
    return SimpleNamespace(usage={'input_tokens': 1000, 'output_tokens': 2000, **usage},
                           model='claude-sonnet-4-6', id='fake-response', stop_reason='end_turn')


def test_records_usage_including_cache_and_settles_reservation(root):
    token = cost.reserve_request(root, 'MACRO_SYNTHESIS', REQUEST, now=NOW)
    cost.record_response(root, token, response(cache_creation_input_tokens=100, cache_read_input_tokens=100))
    status = cost.usage_status(root, '2026-11-19')
    assert status['accounted_usd'] == pytest.approx(.03363)
    assert status['requests'][0]['receipt']['usage']['output_tokens'] == 2000
    assert status['requests'][0]['status'] == 'COMPLETE'


def test_atomic_concurrent_reservations_cannot_overcommit(root):
    def reserve(_):
        try:
            return cost.reserve_request(root, 'MACRO_SYNTHESIS', REQUEST, now=NOW)
        except cost.ApiCostLimit:
            return None
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(reserve, range(18)))
    state = cost.usage_status(root, '2026-11-19')
    assert 0 < sum(v is not None for v in results) < 18
    assert state['accounted_usd'] <= CAP_USD


def test_missing_usage_and_timeouts_keep_maximum_not_zero(root, monkeypatch):
    token = cost.reserve_request(root, 'MACRO_SYNTHESIS', REQUEST, now=NOW)
    before = cost.usage_status(root, '2026-11-19')['accounted_usd']
    with pytest.raises(cost.ApiCostLimit, match='usage missing'):
        cost.record_response(root, token, SimpleNamespace(model=REQUEST['model']))
    assert cost.usage_status(root, '2026-11-19')['accounted_usd'] == before
    calls = []
    class Client:
        messages = None
        def count_tokens(self, **kw):
            return SimpleNamespace(input_tokens=1000)
        def with_options(self, **kw):
            assert kw == {'max_retries': 0}
            self.messages = self
            return self
        def create(self, **kw):
            calls.append(kw)
            raise TimeoutError('ambiguous')
    original = cost.reserve_request
    monkeypatch.setattr(cost, 'reserve_request', lambda *a, **kw: original(*a, **kw, now=NOW))
    with pytest.raises(TimeoutError):
        cost.budgeted_message(root, 'MACRO_SYNTHESIS', REQUEST, Client, authorize=False)
    status = cost.usage_status(root, '2026-11-19')
    assert len(calls) == 1 and status['requests'][-1]['status'] == 'UNCERTAIN_RESERVED'
    assert status['accounted_usd'] > before


def test_credit_rejection_releases_dollars_but_preserves_receipt(root, monkeypatch):
    class Rejected(Exception):
        status_code = 400
    class Client:
        def count_tokens(self, **kw):
            return SimpleNamespace(input_tokens=1000)
        def with_options(self, **kw):
            self.messages = self
            return self
        def create(self, **kw):
            raise Rejected('credit')
    original = cost.reserve_request
    monkeypatch.setattr(cost, 'reserve_request', lambda *a, **kw: original(*a, **kw, now=NOW))
    with pytest.raises(Rejected):
        cost.budgeted_message(root, 'MACRO_SYNTHESIS', REQUEST, Client, authorize=False)
    state = cost.usage_status(root, '2026-11-19')
    assert state['accounted_usd'] == 0 and state['requests'][0]['status'] == 'REJECTED'


def test_et_reset_and_input_output_model_bounds(root):
    for changes in ({'model': 'unpriced-opus'}, {'max_tokens': 16001},
                    {'messages': [{'role': 'user', 'content': 'x'*750001}]}, {'tools': []}):
        with pytest.raises(cost.ApiCostLimit):
            cost.reserve_request(root, 'MACRO_SYNTHESIS', {**REQUEST, **changes}, now=NOW)
    for _ in range(30):
        try:
            cost.reserve_request(root, 'MACRO_SYNTHESIS', REQUEST, now=NOW)
        except cost.ApiCostLimit:
            break
    with pytest.raises(cost.ApiCostLimit, match='DOLLAR_CAP'):
        cost.reserve_request(root, 'MACRO_SYNTHESIS', REQUEST, now=NOW)
    # 04:59 UTC is still the previous ET date; 05:00 starts a new ledger day.
    late = datetime(2026,11,20,4,59,tzinfo=timezone.utc)
    with pytest.raises(cost.ApiCostLimit):
        cost.reserve_request(root, 'MACRO_SYNTHESIS', REQUEST, now=late)
    assert cost.reserve_request(root, 'MACRO_SYNTHESIS', REQUEST,
                                now=datetime(2026,11,20,5,tzinfo=timezone.utc))


def test_four_build_cap_survives_and_dollar_refusal_does_not_buy_slot(root, monkeypatch):
    monkeypatch.setenv('AVSH_BUILD_REASON', 'POST_CLOSE')
    for i in range(4):
        token = builds.reserve(root, reason='POST_CLOSE', key=str(i), now=NOW)
        monkeypatch.setenv('AVSH_FULL_BUILD_ID', token)
        builds.authorize_stage(root, 'MACRO_SYNTHESIS', now=NOW)
    with pytest.raises(ValueError, match='DAILY_FULL_BUILD_LIMIT'):
        builds.reserve(root, reason='POST_CLOSE', key='fifth', now=NOW)
    called = []
    monkeypatch.setattr(cost, 'reserve_request', lambda *a, **kw: (_ for _ in ()).throw(cost.ApiCostLimit('cap')))
    monkeypatch.setattr(cost, 'usage_status', lambda *a: {'legacy_usage_unknown': False, 'accounted_usd': CAP_USD})
    monkeypatch.setattr(builds, 'authorize_stage', lambda *a: called.append(a))
    with pytest.raises(cost.ApiCostLimit):
        cost.budgeted_message(root, 'MACRO_SYNTHESIS', REQUEST, lambda: pytest.fail('No provider'))
    assert called == []


def test_legacy_same_day_unknown_spend_blocks_without_rewriting_history(root, monkeypatch):
    token = builds.reserve(root, reason='POST_CLOSE', key='legacy',
                           now=datetime(2026,11,18,14,tzinfo=timezone.utc))
    monkeypatch.setenv('AVSH_FULL_BUILD_ID', token)
    builds.authorize_stage(root, 'MACRO_SYNTHESIS', now=datetime(2026,11,18,14,tzinfo=timezone.utc))
    raw = (root/'data/macro/delivery/full_build_attempts.sqlite').read_bytes()
    with pytest.raises(cost.ApiCostLimit, match='UNTRACKED_PRIOR_SPEND'):
        cost.reserve_request(root, 'MACRO_SYNTHESIS', REQUEST, now=datetime(2026,11,18,23,tzinfo=timezone.utc))
    assert (root/'data/macro/delivery/full_build_attempts.sqlite').read_bytes() == raw


def test_all_events_and_current_fields_survive_projection():
    events = [{'event_id': str(i), 'actual': None, 'forecast': -2, 'release_time': 'original-clock',
               'status': 'MISSING', 'sources': ['archived citation'], 'definition': 'long background'} for i in range(40)]
    view = research_view('events', {'events': events, 'counter_case': 'material risk'})
    assert len(view['events']) == 40
    assert [r['event_id'] for r in view['events']] == [str(i) for i in range(40)]
    assert all(r['actual'] is None and r['forecast'] == -2 and r['release_time'] == 'original-clock' for r in view['events'])
    assert 'sources' in view['events'][0]['_projection']['omitted_fields']
    assert view['counter_case'] == 'material risk'


def test_lossless_columnar_encoding_and_backward_refs():
    rows = [{'ticker': 'QQQ', 'value': i, 'missing': None} for i in range(5)]
    packed = columnar_records(rows)
    assert [dict(zip(packed['columns'], r)) for r in packed['rows']] == rows
    shared = {'risk': 'retained!'*100}
    packed = deduplicate({'first': shared, 'again': shared})
    assert packed['first'] == shared and packed['again'] == {'$ref': '#/first'}


def test_board_reuses_published_clock_without_provider():
    from macro_board.day_story import reused_macro_narrative
    out = reused_macro_narrative({'intel': {'packet': {'notes': 'original research'},
                                          'synthesis': {'packet_built_at': 'original-clock'}}})
    assert out['overview'] == 'original research' and out['additional_api_calls'] == 0
    assert out['synthesis']['packet_built_at'] == 'original-clock'


def test_pricing_is_frozen_at_reservation_and_usage_bound_failure_blocks_more(root):
    token = cost.reserve_request(root, 'MACRO_SYNTHESIS', REQUEST, now=NOW)
    path = root/'config/macro_api_cost_v1.json'
    p = json.loads(path.read_text())
    p['models']['claude-sonnet-4-6']['output_per_million_usd'] = 0
    path.write_text(json.dumps(p))
    cost.record_response(root, token, response())
    assert cost.usage_status(root, '2026-11-19')['accounted_usd'] == .033
    token = cost.reserve_request(root, 'MACRO_SYNTHESIS', REQUEST, now=NOW)
    with pytest.raises(cost.ApiCostLimit, match='bound exceeded'):
        cost.record_response(root, token, response(input_tokens=10000000))
    with pytest.raises(cost.ApiCostLimit, match='BOUND_BREACHED'):
        cost.reserve_request(root, 'MACRO_SYNTHESIS', REQUEST, now=NOW)


def test_read_only_status_does_not_create_ledger(root):
    assert cost.usage_status(root, '2026-11-19')['remaining_usd'] == CAP_USD
    assert not (root/'data/macro/delivery/api_usage.sqlite').exists()


def test_installed_sdk_optional_cache_counters_are_not_unknown_usage(root):
    from anthropic.types import Usage
    token = cost.reserve_request(root, 'MACRO_SYNTHESIS', REQUEST, now=NOW)
    reply = response()
    reply.usage = Usage(input_tokens=1000, output_tokens=2000)
    cost.record_response(root, token, reply)
    state = cost.usage_status(root, '2026-11-19')
    assert state['requests'][0]['status'] == 'COMPLETE'
    assert state['accounted_usd'] == .033


def test_saved_policy_keeps_four_builds_and_reuses_macro():
    p = json.loads((ROOT/'config/macro_build_schedule_v1.json').read_text())
    assert p['max_full_builds_per_et_day'] == 4
    cfg = json.loads((ROOT/'macro_board/config/macro_board_config_v1.json').read_text())['day_story']['ai_narrative']
    assert cfg['mode'] == 'REUSE_PUBLISHED_MACRO' and cfg['enabled'] is False
    assert cfg['call_on_build_kinds'] == []


def test_free_count_avoids_over_reserving_four_large_requests(root, monkeypatch):
    original = cost.reserve_request
    monkeypatch.setattr(cost, 'reserve_request', lambda *a, **kw: original(*a, **kw, now=NOW))
    calls = {'count': 0, 'paid': 0}
    class Client:
        def with_options(self, **kw):
            assert kw == {'max_retries': 0}
            self.messages = self
            return self
        def count_tokens(self, **kw):
            calls['count'] += 1
            assert kw['timeout'] == 15
            return SimpleNamespace(input_tokens=100000)
        def create(self, **kw):
            calls['paid'] += 1
            return response(input_tokens=100000, output_tokens=8000)
    large = {**REQUEST, 'messages': [{'role': 'user', 'content': 'x'*600000}]}
    for _ in range(4):
        cost.budgeted_message(root, 'MACRO_SYNTHESIS', large, Client, authorize=False)
    state = cost.usage_status(root, '2026-11-19')
    assert calls == {'count': 4, 'paid': 4}
    assert state['accounted_usd'] == pytest.approx(1.68)
    assert state['requests'][0]['receipt']['provider_input_token_estimate'] == 100000


def test_new_event_field_names_are_preserved_and_sparse_tables_are_lossless():
    row = {'event_id': 'NEW', 'actual_qualitative': None, 'release_timestamp_utc': 'original',
           'revised_previous_value': -4, 'new_material_field': 'must survive', 'sources': ['archived']}
    result = research_view('events', {'events': [row]})['events'][0]
    assert {k: result[k] for k in row if k != 'sources'} == {k: v for k,v in row.items() if k != 'sources'}
    records = [{'very_long_first_column_name': i, 'very_long_second_column_name': None,
                **({'optional_new_field_name': False} if i % 2 else {})} for i in range(10)]
    packed = columnar_records(records)
    assert packed['_encoding'] == 'indexed_records'
    assert [{packed['columns'][int(k)]: v for k,v in r.items()} for r in packed['rows']] == records
