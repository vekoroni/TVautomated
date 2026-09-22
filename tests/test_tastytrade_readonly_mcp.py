"""Contract tests for the narrowly allow-listed read-only broker bridge."""

import json
import sys

import pytest

from bridge.tastytrade_readonly_mcp import (
    BrokerCredentialUnavailable,
    BrokerMcpError,
    ReadOnlyTastytradeMcp,
    to_tastytrade_option_symbol,
)
from canonical_data.option_identity import normalise_occ_symbol


FAKE_SERVER = r'''
import json
import os
import sys

for line in sys.stdin:
    message = json.loads(line)
    method = message.get("method")
    if method == "notifications/initialized":
        continue
    if method == "initialize":
        result = {"protocolVersion": "2024-11-05", "capabilities": {"tools": {}},
                  "serverInfo": {"name": "fake-tastytrade", "version": "1"}}
    elif method == "tools/list":
        result = {"tools": [{"name": "tastytrade_get_quote"}]}
    elif method == "tools/call":
        name = message["params"]["name"]
        if name != "tastytrade_get_quote":
            result = {"isError": True, "content": [{"type": "text", "text": "forbidden"}]}
        else:
            args = message["params"]["arguments"]
            result = {"content": [{"type": "text", "text": json.dumps({"items": [
                {"symbol": args["symbols"][0], "instrument-type": args["instrument_type"],
                 "bid": "2.10", "ask": "2.25", "bid-size": "14", "ask-size": "12",
                 "updated-at": "2026-09-21T19:59:00Z",
                 "test-read-only": os.environ.get("TASTYTRADE_READ_ONLY"),
                 "test-environment": os.environ.get("TASTYTRADE_ENV"),
                 "test-api-url": os.environ.get("TASTYTRADE_API_URL")}
            ]})}]}
    else:
        result = {"isError": True, "content": [{"type": "text", "text": "unexpected"}]}
    sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": message["id"], "result": result}) + "\n")
    sys.stdout.flush()
'''


def fake_command(tmp_path):
    server = tmp_path / "fake_tastytrade_mcp.py"
    server.write_text(FAKE_SERVER, encoding="utf-8")
    return [sys.executable, str(server)]


def test_quote_never_calls_write_tools_and_forces_read_only(tmp_path):
    env = {"TASTYTRADE_CLIENT_ID": "dummy", "TASTYTRADE_CLIENT_SECRET": "dummy",
           "TASTYTRADE_REFRESH_TOKEN": "dummy", "TASTYTRADE_API_URL": "https://wrong.example"}
    with ReadOnlyTastytradeMcp(command=fake_command(tmp_path), environment=env) as broker:
        payload = broker.quote(["QBTS261120C00018000"], "Equity Option")
        assert payload["items"][0]["symbol"] == "QBTS  261120C00018000"
        assert normalise_occ_symbol(payload["items"][0]["symbol"]) == "QBTS261120C00018000"
        assert payload["items"][0]["test-read-only"] == "1"
        assert payload["items"][0]["test-environment"] == "production"
        assert payload["items"][0]["test-api-url"] is None
        with pytest.raises(ValueError, match="not allowed"):
            broker.call_tool("tastytrade_place_order", {})


def test_missing_credentials_fail_before_broker_call(tmp_path):
    with ReadOnlyTastytradeMcp(command=fake_command(tmp_path), environment={}) as broker:
        with pytest.raises(BrokerCredentialUnavailable, match="TASTYTRADE_CLIENT_ID"):
            broker.quote(["SPY"], "Equity")


def test_request_boundaries_and_exact_symbol_inputs(tmp_path):
    env = {"TASTYTRADE_CLIENT_ID": "dummy", "TASTYTRADE_CLIENT_SECRET": "dummy",
           "TASTYTRADE_REFRESH_TOKEN": "dummy"}
    with ReadOnlyTastytradeMcp(command=fake_command(tmp_path), environment=env) as broker:
        for symbols in ([], ["SPY"] * 2, ["SPY"] * 101, [" SPY"]):
            with pytest.raises(ValueError):
                broker.quote(symbols, "Equity")
        with pytest.raises(ValueError):
            broker.quote(["SPY"], "Unknown")


def test_compact_occ_conversion_never_rewrites_adjusted_root():
    assert to_tastytrade_option_symbol("QBTS261120C00018000") == "QBTS  261120C00018000"
    assert to_tastytrade_option_symbol("QBTS1261120C00018000") == "QBTS1 261120C00018000"
    with pytest.raises(ValueError, match="root"):
        to_tastytrade_option_symbol("ABCDEFG261120C00018000")


def test_unavailable_tool_is_explicit(tmp_path):
    server = tmp_path / "missing_tool.py"
    server.write_text(FAKE_SERVER.replace("tastytrade_get_quote\"}]", "not_the_quote_tool\"}]"), encoding="utf-8")
    with pytest.raises(BrokerMcpError, match="not advertised"):
        with ReadOnlyTastytradeMcp(command=[sys.executable, str(server)], environment={}):
            pass
