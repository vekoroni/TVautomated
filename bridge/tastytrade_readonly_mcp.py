"""Narrow, read-only stdio MCP transport for tastytrade quote observations.

This adapter owns transport only. The broker-quote domain normalizer owns
identity, time and quality. No account, order or capital tool is reachable.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import json
import os
from pathlib import Path
from queue import Empty, Queue
import shutil
import subprocess
import threading
from typing import Any

from canonical_data.option_identity import parse_occ_symbol


class BrokerMcpError(RuntimeError):
    """The broker MCP transport or read response could not be trusted."""


class BrokerCredentialUnavailable(BrokerMcpError):
    """This process has not been given the approved OAuth environment."""


_QUOTE_TOOL = "tastytrade_get_quote"
# Read-only volatility/liquidity metrics for the standalone ETF macro board (ACK, 6 Oct 2026).
_METRICS_TOOL = "tastytrade_get_market_metrics"
_ALLOWED_TOOLS = frozenset({_QUOTE_TOOL, _METRICS_TOOL})
_PROVENANCE_META_FIELD = "tastytrade/provenance"
_CREDENTIAL_NAMES = (
    "TASTYTRADE_CLIENT_ID",
    "TASTYTRADE_CLIENT_SECRET",
    "TASTYTRADE_REFRESH_TOKEN",
)
_INSTRUMENT_TYPES = frozenset({"Equity", "Equity Option"})
_MAX_LINE_BYTES = 4 * 1024 * 1024


def to_tastytrade_option_symbol(value: str) -> str:
    """Convert compact OCC to the broker's six-character, space-padded root."""
    identity = parse_occ_symbol(value)
    if len(identity.root) > 6:
        raise ValueError("OCC root exceeds Tastytrade's six-character quote identity")
    return identity.root.ljust(6) + identity.symbol[len(identity.root):]


def _default_command(environment: Mapping[str, str]) -> list[str]:
    raw = environment.get("TASTYTRADE_MCP_SERVER_PATH", "").strip()
    if not raw:
        raw = str(Path.home() / "tastytrade-mcp" / "dist" / "index.js")
    server = Path(raw)
    if not server.is_file() or server.suffix.lower() != ".js":
        raise BrokerMcpError("Tastytrade MCP server JavaScript file is unavailable")
    node = environment.get("TASTYTRADE_NODE_PATH") or shutil.which("node")
    if not node:
        raise BrokerMcpError("Node.js executable is unavailable")
    return [str(node), str(server)]


class ReadOnlyTastytradeMcp:
    """One-shot read session; the only callable remote tools are get_quote and get_market_metrics."""

    def __init__(
        self, *, command: Sequence[str] | None = None,
        environment: Mapping[str, str] | None = None, timeout_seconds: float = 45.0,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        # An explicit environment is the complete Tastytrade credential scope,
        # not an addition to possibly unrelated inherited broker credentials.
        inherited = dict(os.environ)
        for name in list(inherited):
            if name.startswith("TASTYTRADE_"):
                inherited.pop(name)
        broker_values = (
            {k: v for k, v in os.environ.items() if k.startswith("TASTYTRADE_")}
            if environment is None else dict(environment)
        )
        inherited.update(broker_values)
        inherited.pop("TASTYTRADE_API_URL", None)
        inherited.pop("TASTYTRADE_ALLOW_UNKNOWN_API_HOST", None)
        inherited["TASTYTRADE_ENV"] = "production"
        inherited["TASTYTRADE_READ_ONLY"] = "1"
        self._environment = inherited
        self._command = list(command) if command is not None else _default_command(inherited)
        if not self._command or any(not isinstance(x, str) or not x for x in self._command):
            raise ValueError("MCP command is invalid")
        self._timeout_seconds = timeout_seconds
        self._process: subprocess.Popen[str] | None = None
        self._responses: Queue[dict[str, Any] | BaseException] = Queue()
        self._request_id = 0
        self._advertised_tools: set[str] = set()

    def __enter__(self) -> "ReadOnlyTastytradeMcp":
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        self._process = subprocess.Popen(
            self._command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, text=True, encoding="utf-8", bufsize=1,
            env=self._environment, creationflags=flags,
        )
        threading.Thread(target=self._read_stdout, daemon=True).start()
        try:
            result = self._request("initialize", {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "avshunter-readonly-quotes", "version": "1.0"},
            })
            if not isinstance(result, Mapping) or "protocolVersion" not in result:
                raise BrokerMcpError("MCP initialization response is invalid")
            self._send({"jsonrpc": "2.0", "method": "notifications/initialized"})
            listing = self._request("tools/list", {})
            if not isinstance(listing, Mapping) or not isinstance(listing.get("tools"), list):
                raise BrokerMcpError("MCP tool listing is invalid")
            self._advertised_tools = {
                tool["name"] for tool in listing["tools"]
                if isinstance(tool, Mapping) and isinstance(tool.get("name"), str)
            }
            if _QUOTE_TOOL not in self._advertised_tools:
                raise BrokerMcpError("tastytrade_get_quote is not advertised by the read-only server")
            return self
        except BaseException:
            self.close()
            raise

    def __exit__(self, _type: Any, _value: Any, _traceback: Any) -> None:
        self.close()

    def close(self) -> None:
        process = self._process
        self._process = None
        if process is None:
            return
        if process.stdin:
            try:
                process.stdin.close()
            except OSError:
                pass
        try:
            process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2)

    def _read_stdout(self) -> None:
        process = self._process
        assert process is not None and process.stdout is not None
        try:
            while True:
                line = process.stdout.readline(_MAX_LINE_BYTES + 1)
                if not line:
                    self._responses.put(BrokerMcpError("MCP server closed its output"))
                    return
                if len(line.encode("utf-8")) > _MAX_LINE_BYTES or not line.endswith("\n"):
                    self._responses.put(BrokerMcpError("MCP response exceeded size limit"))
                    return
                response = json.loads(line)
                if isinstance(response, dict) and "id" in response:
                    self._responses.put(response)
        except (OSError, ValueError, UnicodeError) as exc:
            self._responses.put(BrokerMcpError(f"MCP response framing failed: {type(exc).__name__}"))

    def _send(self, message: Mapping[str, Any]) -> None:
        process = self._process
        if process is None or process.stdin is None or process.poll() is not None:
            raise BrokerMcpError("MCP server is not running")
        try:
            process.stdin.write(json.dumps(message, separators=(",", ":")) + "\n")
            process.stdin.flush()
        except OSError as exc:
            raise BrokerMcpError("MCP request could not be sent") from exc

    def _request(self, method: str, params: Mapping[str, Any]) -> Any:
        self._request_id += 1
        request_id = self._request_id
        self._send({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})
        try:
            result = self._responses.get(timeout=self._timeout_seconds)
        except Empty as exc:
            raise BrokerMcpError("MCP response timed out") from exc
        if isinstance(result, BaseException):
            raise result
        if result.get("id") != request_id or result.get("jsonrpc") != "2.0":
            raise BrokerMcpError("MCP response identity does not match request")
        if "error" in result:
            raise BrokerMcpError(f"MCP {method} returned a protocol error")
        if "result" not in result:
            raise BrokerMcpError("MCP response lacks a result")
        return result["result"]

    def call_tool(self, name: str, arguments: Mapping[str, Any]) -> Mapping[str, Any] | list[Any]:
        if name not in _ALLOWED_TOOLS:
            raise ValueError(f"MCP tool {name!r} is not allowed")
        if name not in self._advertised_tools:
            raise BrokerMcpError(f"{name} is not advertised")
        result = self._request("tools/call", {"name": name, "arguments": dict(arguments)})
        if not isinstance(result, Mapping) or result.get("isError"):
            raise BrokerMcpError("broker read tool returned an error")
        content = result.get("content")
        # tastytrade-mcp (21 Sep 2026 build) appends its own provenance notice as a final text
        # block and marks it in _meta; that block is server-authored metadata, never data.
        meta = result.get("_meta")
        if (isinstance(content, list) and len(content) == 2 and isinstance(meta, Mapping)
                and isinstance(meta.get(_PROVENANCE_META_FIELD), Mapping)
                and isinstance(content[1], Mapping) and content[1].get("type") == "text"
                and str(content[1].get("text", "")).startswith("PROVENANCE")):
            content = content[:1]
        if (not isinstance(content, list) or len(content) != 1
                or not isinstance(content[0], Mapping) or content[0].get("type") != "text"):
            raise BrokerMcpError("broker read tool returned an unsupported payload")
        try:
            payload = json.loads(content[0]["text"])
        except (KeyError, TypeError, ValueError) as exc:
            raise BrokerMcpError("broker read tool returned invalid JSON") from exc
        if not isinstance(payload, (dict, list)):
            raise BrokerMcpError("broker read payload must be an object or array")
        return payload

    def quote(self, symbols: Sequence[str], instrument_type: str) -> Mapping[str, Any] | list[Any]:
        if instrument_type not in _INSTRUMENT_TYPES:
            raise ValueError("instrument type is unsupported")
        if not 1 <= len(symbols) <= 100:
            raise ValueError("quote request needs 1–100 symbols")
        if any(not isinstance(s, str) or not s or s.strip() != s for s in symbols):
            raise ValueError("quote symbols must be exact nonblank strings")
        broker_symbols = (
            [to_tastytrade_option_symbol(symbol) for symbol in symbols]
            if instrument_type == "Equity Option" else list(symbols)
        )
        if len(set(broker_symbols)) != len(broker_symbols):
            raise ValueError("duplicate quote symbols")
        missing = [name for name in _CREDENTIAL_NAMES if not self._environment.get(name)]
        if missing:
            raise BrokerCredentialUnavailable("missing broker OAuth environment: " + ", ".join(missing))
        return self.call_tool(_QUOTE_TOOL, {
            "symbols": broker_symbols, "instrument_type": instrument_type,
            "include_instrument": True,
        })

    def market_metrics(self, symbols: Sequence[str]) -> Mapping[str, Any] | list[Any]:
        """IV index/rank/percentile, HV, beta and per-expiry IV for underlying symbols (read-only)."""
        if not 1 <= len(symbols) <= 100:
            raise ValueError("market metrics request needs 1–100 symbols")
        if any(not isinstance(s, str) or not s or s.strip() != s for s in symbols):
            raise ValueError("metric symbols must be exact nonblank strings")
        if len(set(symbols)) != len(symbols):
            raise ValueError("duplicate metric symbols")
        missing = [name for name in _CREDENTIAL_NAMES if not self._environment.get(name)]
        if missing:
            raise BrokerCredentialUnavailable("missing broker OAuth environment: " + ", ".join(missing))
        return self.call_tool(_METRICS_TOOL, {"symbols": list(symbols)})
