"""Anthropic Desk transport contract; the SDK is faked and no credential or workspace id leaves the test.

Business rule (root cause approved by ACK, 24 Sep 2026): the Lab's Anthropic key is an
organisation key, so every request must carry the ``anthropic-workspace-id`` header. The
workspace identity has one owner, ``anthropic_runtime_config.workspace_id()`` (pinned on
7 Sep 2026 for unattended calls); the Desk provider reuses it and never guesses, discovers
or hard-codes a workspace. Without a configured workspace the provider is not ready and no
paid request is sent (decide before depend).
"""

from __future__ import annotations

import sys
import types

import pytest

import anthropic_runtime_config


class _Block:
    def __init__(self, **fields):
        self.__dict__.update(fields)


class _Usage:
    input_tokens = 11
    output_tokens = 22


def _fake_anthropic(create):
    """A stand-in for the anthropic SDK: captures client kwargs, routes messages.create."""
    module = types.ModuleType("anthropic")
    calls: list[dict] = []

    class APIError(Exception):
        pass

    class APIStatusError(APIError):
        def __init__(self, status_code, body=None, request_id=None):
            super().__init__(f"HTTP {status_code}")
            self.status_code, self.body, self.request_id = status_code, body, request_id

    class APIConnectionError(APIError):
        pass

    class Anthropic:
        def __init__(self, **kwargs):
            calls.append(kwargs)
            self.messages = types.SimpleNamespace(create=lambda **k: create(module, **k))

    module.Anthropic = Anthropic
    module.APIError, module.APIStatusError, module.APIConnectionError = APIError, APIStatusError, APIConnectionError
    return module, calls


def _provider(module):
    return module.AnthropicDeskProvider(
        api_key="fake-key", model_id="test-model",
        input_usd_per_million=1, output_usd_per_million=1,
        web_search_usd_per_call=0.001, max_ticker_usd=1,
    )


DIGEST = {"run_id": "20260924_085940", "ticker": "COP", "evidence_refs": ["EOD_BOOK"]}


def test_client_is_workspace_scoped_from_the_single_configuration_owner(monkeypatch):
    from pipeline_interpreter import anthropic_desk_provider as module

    monkeypatch.setenv("ANTHROPIC_WORKSPACE_ID", "wrkspc_configured")

    def create(_sdk, **kwargs):
        return types.SimpleNamespace(content=[_Block(
            type="tool_use", name=kwargs["tools"][-1]["name"],
            input={"executive_summary": "ok", "sections": [], "external_events": [], "unresolved": []},
        )], usage=_Usage())

    sdk, client_calls = _fake_anthropic(create)
    monkeypatch.setitem(sys.modules, "anthropic", sdk)

    provider = _provider(module)
    assert provider.ready is True
    result = provider.report(DIGEST)

    assert client_calls == [{"api_key": "fake-key", "timeout": module.DEFAULT_TIMEOUT_SECONDS, "max_retries": 0,
                             "default_headers": {"anthropic-workspace-id": "wrkspc_configured"}}]
    assert result["_provider_usage"] == {"input_tokens": 11, "output_tokens": 22}


def test_missing_workspace_blocks_before_any_paid_request(monkeypatch, tmp_path):
    from pipeline_interpreter import anthropic_desk_provider as module

    monkeypatch.delenv("ANTHROPIC_WORKSPACE_ID", raising=False)
    monkeypatch.setattr(anthropic_runtime_config, "CONFIG_PATH", tmp_path / "absent.json")
    sdk, client_calls = _fake_anthropic(lambda *_a, **_k: pytest.fail("provider called"))
    monkeypatch.setitem(sys.modules, "anthropic", sdk)

    provider = _provider(module)
    assert provider.ready is False
    with pytest.raises(module.ProviderUnavailable, match="workspace"):
        provider.report(DIGEST)
    assert client_calls == []


def test_workspace_id_never_appears_in_a_rejection(monkeypatch):
    from pipeline_interpreter import anthropic_desk_provider as module

    monkeypatch.setenv("ANTHROPIC_WORKSPACE_ID", "wrkspc_secretish")

    def create(sdk, **_kwargs):
        raise sdk.APIStatusError(400, body={"error": {"message": "bad request shape"}}, request_id="req_1")

    sdk, _calls = _fake_anthropic(create)
    monkeypatch.setitem(sys.modules, "anthropic", sdk)

    with pytest.raises(module.ProviderRequestRejected) as info:
        _provider(module).report(DIGEST)
    assert info.value.http_status == 400
    assert info.value.detail == "bad request shape"
    assert "wrkspc_" not in str(info.value)


# ---------------------------------------------------------------- typed reply diagnostics
# Approved by ACK 24 Sep 2026: when the reply carries no usable structured call, the
# transport says why in typed, bounded fields (reason code, the API's stop reason, the
# ordered content block types) so the receipt can name the case. Never provider prose.
def _reply(blocks, stop_reason):
    return types.SimpleNamespace(content=blocks, stop_reason=stop_reason, usage=_Usage())


def test_reply_without_a_structured_call_names_stop_reason_and_block_types(monkeypatch):
    from pipeline_interpreter import anthropic_desk_provider as module

    monkeypatch.setenv("ANTHROPIC_WORKSPACE_ID", "wrkspc_configured")
    blocks = [_Block(type="text", text="Searching..."), _Block(type="server_tool_use", name="web_search"),
              _Block(type="web_search_tool_result", content=[{"url": "https://example.com/a"}]),
              _Block(type="text", text="Here is my analysis in prose.")]
    sdk, _calls = _fake_anthropic(lambda *_a, **_k: _reply(blocks, "end_turn"))
    monkeypatch.setitem(sys.modules, "anthropic", sdk)

    with pytest.raises(module.ProviderReplyUnusable) as info:
        _provider(module).report(DIGEST)
    assert info.value.reason_code == "NO_STRUCTURED_TOOL_CALL"
    assert info.value.stop_reason == "end_turn"
    assert info.value.block_types == ["text", "server_tool_use", "web_search_tool_result", "text"]
    assert "Searching" not in str(info.value) and "analysis" not in str(info.value)   # no provider prose


def test_paused_or_truncated_turns_are_named_not_hidden(monkeypatch):
    from pipeline_interpreter import anthropic_desk_provider as module

    monkeypatch.setenv("ANTHROPIC_WORKSPACE_ID", "wrkspc_configured")
    for stop in ("pause_turn", "max_tokens"):
        sdk, _calls = _fake_anthropic(lambda *_a, **_k: _reply([_Block(type="server_tool_use", name="web_search")], stop))
        monkeypatch.setitem(sys.modules, "anthropic", sdk)
        with pytest.raises(module.ProviderReplyUnusable) as info:
            _provider(module).report(DIGEST)
        assert info.value.reason_code == "NO_STRUCTURED_TOOL_CALL" and info.value.stop_reason == stop


def test_two_structured_calls_are_a_named_reason(monkeypatch):
    from pipeline_interpreter import anthropic_desk_provider as module

    monkeypatch.setenv("ANTHROPIC_WORKSPACE_ID", "wrkspc_configured")
    call = {"executive_summary": "x", "sections": [], "external_events": [], "unresolved": []}
    blocks = [_Block(type="tool_use", name=module._REPORT_TOOL_NAME, input=call),
              _Block(type="tool_use", name=module._REPORT_TOOL_NAME, input=call)]
    sdk, _calls = _fake_anthropic(lambda *_a, **_k: _reply(blocks, "tool_use"))
    monkeypatch.setitem(sys.modules, "anthropic", sdk)

    with pytest.raises(module.ProviderReplyUnusable) as info:
        _provider(module).report(DIGEST)
    assert info.value.reason_code == "MULTIPLE_STRUCTURED_TOOL_CALLS"
    assert info.value.block_types == ["tool_use", "tool_use"]


def test_unexpected_stop_reasons_and_block_types_are_bounded(monkeypatch):
    from pipeline_interpreter import desk_provider_common as common

    exc = common.ProviderReplyUnusable("NO_STRUCTURED_TOOL_CALL", stop_reason="weird reason with spaces!" * 5,
                                       block_types=["text"] * 100 + ["bad type"])
    assert exc.stop_reason == "UNRECOGNISED"
    assert len(exc.block_types) <= 32 and "bad type" not in exc.block_types
    assert common.ProviderReplyUnusable("NOT_A_CODE").reason_code == "UNCLASSIFIED"


# ---------------------------------------------------------------- pre-dispatch failures are typed too
# 24 Sep 2026, 19:31 BST: the Lab was started from an interpreter without the anthropic SDK and
# the resulting controlled failure carried no reason. Missing is never neutral: every path that
# stops a report before or after the paid call names its case with a reason code.
def test_missing_sdk_is_a_named_reason_and_sends_nothing(monkeypatch):
    from pipeline_interpreter import anthropic_desk_provider as module

    monkeypatch.setenv("ANTHROPIC_WORKSPACE_ID", "wrkspc_configured")
    monkeypatch.setitem(sys.modules, "anthropic", None)          # import anthropic -> ImportError
    provider = _provider(module)
    assert provider.sdk_available is False
    with pytest.raises(module.ProviderReplyUnusable) as info:
        provider.report(DIGEST)
    assert info.value.reason_code == "SDK_MISSING"


def test_cost_ceiling_is_a_named_reason_and_sends_nothing(monkeypatch):
    from pipeline_interpreter import anthropic_desk_provider as module

    monkeypatch.setenv("ANTHROPIC_WORKSPACE_ID", "wrkspc_configured")
    sdk, calls = _fake_anthropic(lambda *_a, **_k: pytest.fail("provider called"))
    monkeypatch.setitem(sys.modules, "anthropic", sdk)
    provider = module.AnthropicDeskProvider(
        api_key="fake-key", model_id="test-model", input_usd_per_million=100, output_usd_per_million=100,
        web_search_usd_per_call=0.01, max_ticker_usd=0.5,
    )
    with pytest.raises(module.ProviderReplyUnusable) as info:
        provider.report(DIGEST)
    assert info.value.reason_code == "COST_CEILING_EXCEEDED" and calls == []


def test_invalid_evidence_refs_is_a_named_reason_and_sends_nothing(monkeypatch):
    from pipeline_interpreter import anthropic_desk_provider as module

    monkeypatch.setenv("ANTHROPIC_WORKSPACE_ID", "wrkspc_configured")
    sdk, calls = _fake_anthropic(lambda *_a, **_k: pytest.fail("provider called"))
    monkeypatch.setitem(sys.modules, "anthropic", sdk)
    with pytest.raises(module.ProviderReplyUnusable) as info:
        _provider(module).report({"ticker": "COP", "evidence_refs": ["SCREENSHOT"]})
    assert info.value.reason_code == "EVIDENCE_REFS_INVALID" and calls == []


# ---------------------------------------------------------------- one attempt, configured timeout
# Approved by ACK 24 Sep 2026: at 19:37-19:44 BST one COP click became three paid attempts because
# the SDK silently retried a 120 s client timeout twice. The transport sends exactly one attempt
# (SDK retries off) and its timeout is configuration, not a literal.
def test_client_sends_one_attempt_with_the_configured_timeout(monkeypatch):
    from pipeline_interpreter import anthropic_desk_provider as module

    monkeypatch.setenv("ANTHROPIC_WORKSPACE_ID", "wrkspc_configured")
    for name, value in (("ANTHROPIC_API_KEY", "fake-key"), ("AVSHUNTER_INTERPRETER_ANTHROPIC_MODEL", "test-model"),
                        ("AVSHUNTER_INTERPRETER_ANTHROPIC_INPUT_USD_PER_MILLION", "1"),
                        ("AVSHUNTER_INTERPRETER_ANTHROPIC_OUTPUT_USD_PER_MILLION", "1"),
                        ("AVSHUNTER_INTERPRETER_ANTHROPIC_WEB_SEARCH_USD_PER_CALL", "0.001"),
                        ("AVSHUNTER_INTERPRETER_ANTHROPIC_MAX_TICKER_USD", "1"),
                        ("AVSHUNTER_INTERPRETER_ANTHROPIC_TIMEOUT_SECONDS", "345")):
        monkeypatch.setenv(name, value)
    sdk, client_calls = _fake_anthropic(lambda *_a, **kwargs: types.SimpleNamespace(content=[_Block(
        type="tool_use", name=kwargs["tools"][-1]["name"],
        input={"executive_summary": "ok", "sections": [], "external_events": [], "unresolved": []})], usage=_Usage()))
    monkeypatch.setitem(sys.modules, "anthropic", sdk)

    module.AnthropicDeskProvider.from_environment().report(DIGEST)
    assert client_calls[0]["max_retries"] == 0
    assert client_calls[0]["timeout"] == 345


def test_timeout_default_is_the_documented_constant_and_bad_values_fall_back(monkeypatch):
    from pipeline_interpreter import anthropic_desk_provider as module

    assert module.DEFAULT_TIMEOUT_SECONDS == 600
    monkeypatch.delenv("AVSHUNTER_INTERPRETER_ANTHROPIC_TIMEOUT_SECONDS", raising=False)
    assert module.AnthropicDeskProvider.from_environment().timeout == 600
    monkeypatch.setenv("AVSHUNTER_INTERPRETER_ANTHROPIC_TIMEOUT_SECONDS", "not-a-number")
    assert module.AnthropicDeskProvider.from_environment().timeout == 600
    monkeypatch.setenv("AVSHUNTER_INTERPRETER_ANTHROPIC_TIMEOUT_SECONDS", "0")
    assert module.AnthropicDeskProvider.from_environment().timeout == 600
