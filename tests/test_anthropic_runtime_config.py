import json
import os
from pathlib import Path
import subprocess
import sys

import pytest
import anthropic_runtime_config as config
import build_macro_json


def test_repository_setting_works_in_fresh_process_from_other_directory(tmp_path):
    root = Path(config.__file__).parent
    environment = dict(os.environ)
    environment.pop("ANTHROPIC_WORKSPACE_ID", None)
    environment["PYTHONPATH"] = str(root)
    result = subprocess.check_output([sys.executable, "-B", "-c",
        "import anthropic_runtime_config as c; print(c.workspace_id())"],
        cwd=tmp_path, env=environment, text=True).strip()
    expected = json.loads(config.CONFIG_PATH.read_text())["workspace_id"]
    assert result == expected


def test_macro_uses_persisted_setting_without_environment(monkeypatch, tmp_path):
    path = tmp_path / "runtime.json"
    path.write_text(json.dumps({"workspace_id": "wrkspc_persisted"}))
    monkeypatch.setattr(config, "CONFIG_PATH", path)
    monkeypatch.delenv("ANTHROPIC_WORKSPACE_ID", raising=False)
    captured = []
    monkeypatch.setattr(build_macro_json.anthropic, "Anthropic", lambda **kwargs: captured.append(kwargs))
    build_macro_json._anthropic_client()
    assert captured == [{"default_headers": {"anthropic-workspace-id": "wrkspc_persisted"}}]


def test_explicit_environment_override(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "CONFIG_PATH", tmp_path / "absent.json")
    monkeypatch.setenv("ANTHROPIC_WORKSPACE_ID", "wrkspc_override")
    assert config.workspace_id() == "wrkspc_override"


@pytest.mark.parametrize("client", ["count", "generation"])
def test_worker3_sends_persisted_workspace(monkeypatch, tmp_path, client):
    from unittest.mock import Mock
    from worker3.adapters.anthropic_http import AnthropicHTTP
    from worker3.integration.current_canary import count_frozen_request, MODEL
    path = tmp_path / "runtime.json"
    path.write_text(json.dumps({"workspace_id": "wrkspc_persisted"}))
    monkeypatch.setattr(config, "CONFIG_PATH", path)
    monkeypatch.delenv("ANTHROPIC_WORKSPACE_ID", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fixture-only")
    connection = Mock()
    connection.getresponse.return_value.status = 200
    connection.getresponse.return_value.read.return_value = b'{"input_tokens": 100}'
    request = {"model": MODEL, "max_tokens": 1, "system": "fixture", "messages": []}
    if client == "count":
        count_frozen_request(request, connection_factory=lambda *a, **k: connection)
    else:
        monkeypatch.setattr("worker3.adapters.anthropic_http.http.client.HTTPSConnection", lambda *a, **k: connection)
        AnthropicHTTP(enabled=True).create(request, timeout_seconds=1)
    assert connection.request.call_args.kwargs["headers"]["anthropic-workspace-id"] == "wrkspc_persisted"
    assert connection.request.call_count == 1


@pytest.mark.parametrize("value", ["bad", "wrkspc_bad\nheader", None, 42])
def test_invalid_configuration_fails_closed(monkeypatch, tmp_path, value):
    path = tmp_path / "runtime.json"
    path.write_text(json.dumps({"workspace_id": value}))
    monkeypatch.setattr(config, "CONFIG_PATH", path)
    monkeypatch.delenv("ANTHROPIC_WORKSPACE_ID", raising=False)
    with pytest.raises(RuntimeError, match="valid wrkspc_"):
        config.workspace_id()
