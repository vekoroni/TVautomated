"""Transport contract; all HTTP is faked and no credentials leave the test."""

from __future__ import annotations

import io
import json
from urllib.error import HTTPError, URLError

import pytest


def test_missing_key_or_model_blocks_before_network(monkeypatch):
    from pipeline_interpreter import openai_desk_provider as module

    monkeypatch.setattr(module, "urlopen", lambda *a, **k: pytest.fail("network called"))
    provider = module.OpenAIResponsesProvider(api_key=None, model_id=None)
    assert provider.ready is False
    with pytest.raises(module.ProviderUnavailable, match="Configure OPENAI_API_KEY"):
        provider.report({"ticker": "AAA", "evidence_refs": ["EOD_BOOK"]})


def test_report_uses_bounded_structured_response_and_verified_web_sources(monkeypatch):
    from pipeline_interpreter import openai_desk_provider as module

    calls = []
    response = {
        "status": "completed", "usage": {"input_tokens": 123, "output_tokens": 456},
        "output": [
            {"type": "web_search_call", "action": {"sources": [{"url": "https://example.com/earnings"}]}},
            {"type": "message", "content": [{"type": "output_text", "text": json.dumps({
                "executive_summary": "Thesis supported", "sections": [],
                "external_events": [{"url": "https://example.com/earnings", "asof_utc": "2026-09-21T20:00:00Z", "summary": "Earnings"}],
                "unresolved": [],
            })}]},
        ],
    }
    def fake_open(request, *, timeout):
        calls.append(json.loads(request.data))
        assert request.get_header("Authorization") == "Bearer fake-key"
        return io.BytesIO(json.dumps(response).encode("utf-8"))
    monkeypatch.setattr(module, "urlopen", fake_open)
    provider = module.OpenAIResponsesProvider(
        api_key="fake-key", model_id="test-model",
        input_usd_per_million=1, output_usd_per_million=1,
        web_search_usd_per_call=0.001, max_ticker_usd=1,
    )
    result = provider.report({"run_id": "20260922_000106", "ticker": "AAA", "evidence_refs": ["EOD_BOOK"]})
    assert calls[0]["model"] == "test-model"
    assert calls[0]["store"] is False
    assert calls[0]["max_output_tokens"] == 8000
    assert calls[0]["text"]["format"]["type"] == "json_schema"
    assert calls[0]["tools"] == [{"type": "web_search"}]
    assert calls[0]["max_tool_calls"] == 2
    assert result["_verified_web_urls"] == ["https://example.com/earnings"]
    assert result["_provider_usage"]["input_tokens"] == 123


def test_missing_governed_pricing_blocks_paid_request(monkeypatch):
    from pipeline_interpreter import openai_desk_provider as module

    monkeypatch.setattr(module, "urlopen", lambda *a, **k: pytest.fail("network called"))
    provider = module.OpenAIResponsesProvider(api_key="fake-key", model_id="test-model")
    assert provider.ready is False
    with pytest.raises(module.ProviderUnavailable, match="verified model/tool pricing"):
        provider.report({"ticker": "AAA", "evidence_refs": ["EOD_BOOK"]})


def test_configured_cost_ceiling_blocks_before_network(monkeypatch):
    from pipeline_interpreter import openai_desk_provider as module

    monkeypatch.setattr(module, "urlopen", lambda *a, **k: pytest.fail("network called"))
    provider = module.OpenAIResponsesProvider(
        api_key="fake-key", model_id="test-model",
        input_usd_per_million=100, output_usd_per_million=100,
        web_search_usd_per_call=1, max_ticker_usd=0.01,
    )
    assert provider.estimate_report_bound(1000) > provider.max_ticker_usd
    with pytest.raises(module.ProviderUnavailable, match="exceeds per-ticker ceiling"):
        provider.report({"ticker": "AAA", "evidence_refs": ["EOD_BOOK"]})


def test_http_rejection_has_bounded_status_and_request_id(monkeypatch):
    from pipeline_interpreter import openai_desk_provider as module

    def rejected(request, *, timeout):
        raise HTTPError(request.full_url, 400, "private provider detail",
                        {"x-request-id": "req_fixture"}, io.BytesIO(b"private provider body"))

    monkeypatch.setattr(module, "urlopen", rejected)
    provider = module.OpenAIResponsesProvider(
        api_key="fake-key", model_id="test-model",
        input_usd_per_million=1, output_usd_per_million=1,
        web_search_usd_per_call=0.001, max_ticker_usd=1,
    )
    with pytest.raises(module.ProviderRequestRejected) as raised:
        provider.report({"ticker": "AAA", "evidence_refs": ["EOD_BOOK"]})
    assert raised.value.http_status == 400
    assert raised.value.request_id == "req_fixture"
    assert "private" not in str(raised.value)


def test_transport_loss_remains_uncertain(monkeypatch):
    from pipeline_interpreter import openai_desk_provider as module

    def disconnected(request, *, timeout):
        raise URLError("private network detail")

    monkeypatch.setattr(module, "urlopen", disconnected)
    provider = module.OpenAIResponsesProvider(
        api_key="fake-key", model_id="test-model",
        input_usd_per_million=1, output_usd_per_million=1,
        web_search_usd_per_call=0.001, max_ticker_usd=1,
    )
    with pytest.raises(module.ProviderOutcomeUnknown) as raised:
        provider.report({"ticker": "AAA", "evidence_refs": ["EOD_BOOK"]})
    assert "private" not in str(raised.value)
