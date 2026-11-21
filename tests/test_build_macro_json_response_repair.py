"""Single-request synthesis regressions, with isolated fake provider usage."""
import json
from pathlib import Path
from types import SimpleNamespace
import pytest
import build_macro_json as builder
from contracts import macro_api_cost as cost

@pytest.fixture
def client(tmp_path, monkeypatch):
    (tmp_path/'config').mkdir()
    (tmp_path/'config/macro_api_cost_v1.json').write_bytes((builder.BASE_DIR/'config/macro_api_cost_v1.json').read_bytes())
    monkeypatch.setattr(builder, 'BASE_DIR', tmp_path)
    original = cost.budgeted_message
    monkeypatch.setattr(cost, 'budgeted_message', lambda root, stage, request, factory: original(root, stage, request, factory, authorize=False))
    class Client:
        text = '{"regime_state":"TRANSITIONAL"}'
        stop = 'end_turn'
        calls = []
        def with_options(self, **kwargs):
            assert kwargs == {'max_retries': 0}
            self.messages = self
            return self
        def create(self, **kwargs):
            self.calls.append(kwargs)
            return SimpleNamespace(content=[SimpleNamespace(text=self.text)], stop_reason=self.stop,
                                   usage={'input_tokens': 500, 'output_tokens': 1000}, model='claude-sonnet-4-6')
        def count_tokens(self, **kwargs):
            assert 'max_tokens' not in kwargs
            return SimpleNamespace(input_tokens=500)
    c = Client()
    monkeypatch.setattr(builder, '_anthropic_client', lambda: c)
    return c

def test_transport_fences_and_trailing_text_are_removed():
    assert builder._parse_macro_response('Here is the object:\n```json\n{"regime_state":"NEUTRAL"}\n```\nDone.')["regime_state"] == 'NEUTRAL'

def test_one_request_contains_evidence_once_and_full_contract(client):
    assert builder.call_macro_api('UNIQUE_EVIDENCE')['regime_state'] == 'TRANSITIONAL'
    assert len(client.calls) == 1
    request = client.calls[0]
    text = json.dumps(request)
    assert text.count('UNIQUE_EVIDENCE') == 1
    assert 'BLOCK 9' in text and 'sector_rotation' in text and 'horizon_routing' in text
    assert request['max_tokens'] >= 16000

@pytest.mark.parametrize('text', ['{"regime_state": nope}', '[]'])
def test_invalid_json_fails_without_paid_rewrite(client, text):
    client.text = text
    with pytest.raises(RuntimeError, match='no automatic paid repair'):
        builder.call_macro_api('fixture')
    assert len(client.calls) == 1

def test_output_cutoff_does_not_trigger_repair(client):
    client.text = '{"cut_off":'
    client.stop = 'max_tokens'
    with pytest.raises(RuntimeError, match='truncated at the output limit'):
        builder.call_macro_api('fixture')
    assert len(client.calls) == 1

def test_dry_run_never_calls_provider_or_reserves_budget(monkeypatch):
    monkeypatch.setattr(builder, '_anthropic_client', lambda: pytest.fail('No API'))
    monkeypatch.setattr(cost, 'reserve_request', lambda *a, **kw: pytest.fail('No reservation'))
    assert builder.call_macro_api('fixture', dry_run=True) == {}
