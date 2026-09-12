from __future__ import annotations

import build_macro_json
import pytest
import anthropic_runtime_config


class _FakeClient:
    pass


def test_anthropic_client_uses_configured_workspace(monkeypatch):
    calls: list[dict] = []

    def factory(**kwargs):
        calls.append(kwargs)
        return _FakeClient()

    monkeypatch.setenv("ANTHROPIC_WORKSPACE_ID", "wrkspc_configured")
    monkeypatch.setattr(build_macro_json.anthropic, "Anthropic", factory)

    build_macro_json._anthropic_client()

    assert calls == [
        {"default_headers": {"anthropic-workspace-id": "wrkspc_configured"}}
    ]


def test_anthropic_client_fails_before_provider_call_when_workspace_is_missing(
    monkeypatch, tmp_path,
):
    calls: list[dict] = []

    def factory(**kwargs):
        calls.append(kwargs)
        return _FakeClient()

    monkeypatch.delenv("ANTHROPIC_WORKSPACE_ID", raising=False)
    monkeypatch.setattr(anthropic_runtime_config, "CONFIG_PATH", tmp_path / "missing.json")
    monkeypatch.setattr(build_macro_json.anthropic, "Anthropic", factory)

    with pytest.raises(RuntimeError, match="ANTHROPIC_WORKSPACE_ID is required"):
        build_macro_json._anthropic_client()

    assert calls == []
