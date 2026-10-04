"""One-shot Anthropic Messages transport for advisory Interpreter reports.

Same governed contract as ``openai_desk_provider.py`` — same bounded digest
input, same forced structured schema, same cost ceiling, same exception
types — only the model vendor differs. Credentials and model are explicit
runtime inputs read from the environment; this module never loads, stores,
or logs a credential, and never fetches ungoverned evidence: the model sees
only the same digest the Lab already assembled (no screenshots, no new
provider fetches, no broker or execution tools).

Drop-in for ``OpenAIResponsesProvider``: same public surface (``ready``,
``model_id``, ``estimate_report_bound``, ``report``, ``answer``), so
``interactive_desk.py`` can use either transport unmodified.
"""

from __future__ import annotations

import json
import math
import os
from typing import Any, Mapping

from anthropic_runtime_config import workspace_id as configured_workspace_id
from pipeline_interpreter.confluence_evidence import CHAIN_KEYS
from pipeline_interpreter.desk_provider_common import (
    ANSWER_INSTRUCTIONS,
    DEEP_REPORT_INSTRUCTIONS_TEMPLATE,
    REPORT_INSTRUCTIONS_TEMPLATE,
    ProviderOutcomeUnknown,
    ProviderReplyUnusable,
    ProviderRequestRejected,
    ProviderUnavailable,
    _ANSWER_SCHEMA,
    _REPORT_KEYS,
    _report_schema,
)

_REPORT_SCHEMA = _report_schema(CHAIN_KEYS)

# One non-streaming attempt may legitimately run several minutes for a report with
# web search and an 8,000-token output (24 Sep 2026: a 120 s literal timed out three
# times on one COP click). Configuration, not a literal; the SDK's own single-request
# ceiling is the default.
DEFAULT_TIMEOUT_SECONDS = 600

_REPORT_TOOL_NAME = "avshunter_interpreter_report_v1"
_DEEP_REPORT_TOOL_NAME = "avshunter_interpreter_deep_report_v1"
_ANSWER_TOOL_NAME = "avshunter_interpreter_answer_v1"


class AnthropicDeskProvider:
    def __init__(
        self, *, api_key: str | None, model_id: str | None, timeout: int = DEFAULT_TIMEOUT_SECONDS,
        input_usd_per_million: float | None = None,
        output_usd_per_million: float | None = None,
        web_search_usd_per_call: float | None = None,
        max_ticker_usd: float | None = None,
    ):
        self._api_key = api_key or ""
        self.model_id = model_id or "UNCONFIGURED"
        # The Lab may run in its own venv. Surface a missing SDK in /control
        # before the user commits a report attempt; _call still records the
        # typed SDK_MISSING outcome if the environment changes after startup.
        try:
            import anthropic  # noqa: F401
            self.sdk_available = True
        except ImportError:
            self.sdk_available = False
        self.timeout = timeout
        self.input_usd_per_million = input_usd_per_million
        self.output_usd_per_million = output_usd_per_million
        self.web_search_usd_per_call = web_search_usd_per_call
        self.max_ticker_usd = max_ticker_usd
        prices = (input_usd_per_million, output_usd_per_million,
                  web_search_usd_per_call, max_ticker_usd)
        # Anthropic requires ``anthropic-workspace-id`` for keys that are not
        # workspace-scoped. The workspace identity has one owner
        # (anthropic_runtime_config, pinned 7 Sep 2026); it is resolved here so
        # an unconfigured workspace makes the provider not-ready before any
        # paid request, never a provider-side HTTP 400 after one.
        try:
            self._workspace_id: str | None = configured_workspace_id()
        except RuntimeError:
            self._workspace_id = None
        self.ready = bool(self._api_key and model_id and self._workspace_id and all(
            isinstance(v, (int, float)) and math.isfinite(v) and v > 0 for v in prices
        ))

    @classmethod
    def from_environment(cls) -> "AnthropicDeskProvider":
        """Reads a separate env namespace from the OpenAI provider so the two
        transports can be configured — and priced — independently, and so
        switching AVSHUNTER_INTERPRETER_PROVIDER never silently reuses the
        wrong vendor's pricing.
        """
        def configured(name: str) -> float | None:
            try:
                return float(os.environ[name])
            except (KeyError, ValueError):
                return None
        timeout = configured("AVSHUNTER_INTERPRETER_ANTHROPIC_TIMEOUT_SECONDS")
        return cls(api_key=os.environ.get("ANTHROPIC_API_KEY"),
                   model_id=os.environ.get("AVSHUNTER_INTERPRETER_ANTHROPIC_MODEL"),
                   timeout=int(timeout) if timeout and timeout > 0 else DEFAULT_TIMEOUT_SECONDS,
                   input_usd_per_million=configured("AVSHUNTER_INTERPRETER_ANTHROPIC_INPUT_USD_PER_MILLION"),
                   output_usd_per_million=configured("AVSHUNTER_INTERPRETER_ANTHROPIC_OUTPUT_USD_PER_MILLION"),
                   web_search_usd_per_call=configured("AVSHUNTER_INTERPRETER_ANTHROPIC_WEB_SEARCH_USD_PER_CALL"),
                   max_ticker_usd=configured("AVSHUNTER_INTERPRETER_ANTHROPIC_MAX_TICKER_USD"))

    def estimate_report_bound(self, input_chars: int) -> float | None:
        """Conservative configured estimate, not a provider billing guarantee."""
        if not self.ready:
            return None
        input_ceiling = input_chars + 5000 + 2 * 10000
        return round((input_ceiling * self.input_usd_per_million
                      + 8000 * self.output_usd_per_million) / 1_000_000
                     + 2 * self.web_search_usd_per_call, 6)

    def _require_budget(self, input_chars: int) -> None:
        bound = self.estimate_report_bound(input_chars)
        if bound is None:
            raise ProviderUnavailable(
                "Configure ANTHROPIC_API_KEY, AVSHUNTER_INTERPRETER_ANTHROPIC_MODEL, the Anthropic "
                "workspace (ANTHROPIC_WORKSPACE_ID or config/anthropic_runtime.json), verified "
                "model/tool pricing and per-ticker spend ceiling locally."
            )
        if bound > self.max_ticker_usd:
            # Typed so the receipt says the ceiling stopped it and nothing was sent.
            raise ProviderReplyUnusable("COST_CEILING_EXCEEDED")

    def _call(self, *, instructions: str, input_value: Mapping[str, Any], schema: dict,
              tool_name: str, web_search: bool, max_tokens: int) -> tuple[dict, set[str], dict]:
        if not self.ready:
            raise ProviderUnavailable(
                "Set ANTHROPIC_API_KEY and AVSHUNTER_INTERPRETER_ANTHROPIC_MODEL locally and "
                "configure the Anthropic workspace (ANTHROPIC_WORKSPACE_ID or "
                "config/anthropic_runtime.json); do not paste credentials into chat."
            )
        try:
            import anthropic
        except ImportError as exc:
            # The serving interpreter lacks the SDK (seen 24 Sep 2026 when the Lab was
            # started from intelligence-lab/venv): named, and nothing is sent.
            raise ProviderReplyUnusable("SDK_MISSING") from exc

        # max_retries=0: the SDK would otherwise re-send a timed-out request twice,
        # silently, each a separate paid attempt. One click is one attempt; the Desk's
        # finality rule owns what happens after an unknown outcome.
        client = anthropic.Anthropic(
            api_key=self._api_key, timeout=self.timeout, max_retries=0,
            default_headers={"anthropic-workspace-id": self._workspace_id},
        )
        structured_tool = {
            "name": tool_name,
            "description": "Return the governed advisory result as structured data. "
                            "Call this exactly once, as the final action, to finish.",
            "input_schema": schema,
        }
        if web_search:
            tools: list[dict] = [
                {"type": "web_search_20250305", "name": "web_search", "max_uses": 2},
                structured_tool,
            ]
            # Auto, not forced: the model must be free to search before it
            # finishes, but the instructions require it to end by calling
            # the structured tool exactly once.
            tool_choice: dict = {"type": "auto"}
        else:
            tools = [structured_tool]
            tool_choice = {"type": "tool", "name": tool_name}

        try:
            resp = client.messages.create(
                model=self.model_id,
                max_tokens=max_tokens,
                system=instructions,
                messages=[{"role": "user",
                           "content": json.dumps(input_value, ensure_ascii=False, allow_nan=False)}],
                tools=tools,
                tool_choice=tool_choice,
            )
        except anthropic.APIStatusError as exc:
            request_id = getattr(exc, "request_id", None)
            detail = None
            body = getattr(exc, "body", None)
            if isinstance(body, dict):
                inner = body.get("error")
                if isinstance(inner, dict):
                    detail = inner.get("message")
            if not detail:
                detail = str(exc)[:300]
            raise ProviderRequestRejected(
                exc.status_code, request_id=request_id, provider="Anthropic Messages", detail=detail
            ) from exc
        except (anthropic.APIConnectionError, TimeoutError, OSError) as exc:
            raise ProviderOutcomeUnknown("Anthropic Messages outcome unknown; no automatic retry") from exc
        except anthropic.APIError as exc:
            raise ProviderReplyUnusable("SDK_ERROR") from exc

        sources: set[str] = set()
        value = None
        stop_reason = getattr(resp, "stop_reason", None)
        block_types = [getattr(block, "type", None) for block in resp.content]
        for block in resp.content:
            btype = getattr(block, "type", None)
            if btype == "tool_use" and getattr(block, "name", None) == tool_name:
                if value is not None:
                    raise ProviderReplyUnusable("MULTIPLE_STRUCTURED_TOOL_CALLS",
                                                stop_reason=stop_reason, block_types=block_types)
                value = block.input
            elif btype == "web_search_tool_result":
                for item in (getattr(block, "content", None) or []):
                    url = item.get("url") if isinstance(item, dict) else getattr(item, "url", None)
                    if url:
                        sources.add(url)
        if not isinstance(value, dict):
            # A paused server-tool turn, an exhausted output budget or a prose-only
            # answer all land here; the stop reason and block types name which.
            raise ProviderReplyUnusable("NO_STRUCTURED_TOOL_CALL",
                                        stop_reason=stop_reason, block_types=block_types)

        usage_obj = getattr(resp, "usage", None)
        usage = {}
        if usage_obj is not None:
            usage = {"input_tokens": getattr(usage_obj, "input_tokens", None),
                     "output_tokens": getattr(usage_obj, "output_tokens", None)}
        return value, sources, usage

    def report(self, digest: Mapping[str, Any]) -> dict[str, Any]:
        self._require_budget(len(json.dumps(digest, ensure_ascii=False, default=str)))
        evidence_refs = digest.get("evidence_refs")
        allowed_refs = {"EOD_BOOK", "MORNING_HANDOFF", "PIT_PRICE_BARS"}
        if (not isinstance(evidence_refs, list) or not evidence_refs
                or any(ref not in allowed_refs for ref in evidence_refs)):
            raise ProviderReplyUnusable("EVIDENCE_REFS_INVALID")
        value, sources, usage = self._call(
            instructions=REPORT_INSTRUCTIONS_TEMPLATE.format(evidence_refs=", ".join(evidence_refs)),
            input_value={"evidence": digest, "required_sections": _REPORT_KEYS},
            schema=_REPORT_SCHEMA, tool_name=_REPORT_TOOL_NAME, web_search=True,
            max_tokens=8000,
        )
        value["_verified_web_urls"] = sorted(sources)
        value["_provider_usage"] = usage
        return value

    def deep_report(self, digest: Mapping[str, Any]) -> dict[str, Any]:
        """Same schema and validation as report(), wider digest, one call.

        No second (junior-briefing) call, no screenshots — the caller widens
        ``digest`` before this is invoked; this method itself only changes
        the instructions and the tool name so the result can't collide with
        a standard report's persisted file for the same ticker.
        """
        self._require_budget(len(json.dumps(digest, ensure_ascii=False, default=str)))
        evidence_refs = digest.get("evidence_refs")
        allowed_refs = {"EOD_BOOK", "MORNING_HANDOFF", "PIT_PRICE_BARS"}
        if (not isinstance(evidence_refs, list) or not evidence_refs
                or any(ref not in allowed_refs for ref in evidence_refs)):
            raise ProviderReplyUnusable("EVIDENCE_REFS_INVALID")
        value, sources, usage = self._call(
            instructions=DEEP_REPORT_INSTRUCTIONS_TEMPLATE.format(evidence_refs=", ".join(evidence_refs)),
            input_value={"evidence": digest, "required_sections": _REPORT_KEYS},
            schema=_REPORT_SCHEMA, tool_name=_DEEP_REPORT_TOOL_NAME, web_search=True,
            max_tokens=8000,
        )
        value["_verified_web_urls"] = sorted(sources)
        value["_provider_usage"] = usage
        return value

    def answer(self, digest: Mapping[str, Any], report: Mapping[str, Any], question: str) -> dict[str, Any]:
        self._require_budget(len(json.dumps(digest, ensure_ascii=False, default=str))
                             + len(json.dumps(report.get("sections") or [], ensure_ascii=False, default=str))
                             + len(question))
        value, _sources, usage = self._call(
            instructions=ANSWER_INSTRUCTIONS,
            input_value={"evidence": digest, "report": {
                "ticker": report.get("ticker"), "phase": report.get("phase"),
                "executive_summary": report.get("executive_summary"),
                "sections": report.get("sections"), "unresolved": report.get("unresolved"),
            }, "question": question},
            schema=_ANSWER_SCHEMA, tool_name=_ANSWER_TOOL_NAME, web_search=False,
            max_tokens=1400,
        )
        value["_provider_usage"] = usage
        return value
