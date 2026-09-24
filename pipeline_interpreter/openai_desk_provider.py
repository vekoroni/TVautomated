"""One-shot OpenAI Responses transport for advisory Interpreter reports.

Credentials and model are explicit runtime inputs. No broker tools, provider
conversation state, automatic retries, or capital authority are exposed.
"""

from __future__ import annotations

import json
import math
import os
from typing import Any, Mapping
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from pipeline_interpreter.confluence_evidence import CHAIN_KEYS
from pipeline_interpreter.desk_provider_common import (
    ANSWER_INSTRUCTIONS,
    DEEP_REPORT_INSTRUCTIONS_TEMPLATE,
    REPORT_INSTRUCTIONS_TEMPLATE,
    ProviderOutcomeUnknown,
    ProviderRequestRejected,
    ProviderUnavailable,
    _ANSWER_SCHEMA,
    _REPORT_KEYS,
    _report_schema,
)

_REPORT_SCHEMA = _report_schema(CHAIN_KEYS)


class OpenAIResponsesProvider:
    def __init__(
        self, *, api_key: str | None, model_id: str | None, timeout: int = 120,
        input_usd_per_million: float | None = None,
        output_usd_per_million: float | None = None,
        web_search_usd_per_call: float | None = None,
        max_ticker_usd: float | None = None,
    ):
        self._api_key = api_key or ""
        self.model_id = model_id or "UNCONFIGURED"
        self.timeout = timeout
        self.input_usd_per_million = input_usd_per_million
        self.output_usd_per_million = output_usd_per_million
        self.web_search_usd_per_call = web_search_usd_per_call
        self.max_ticker_usd = max_ticker_usd
        prices = (input_usd_per_million, output_usd_per_million,
                  web_search_usd_per_call, max_ticker_usd)
        self.ready = bool(self._api_key and model_id and all(
            isinstance(v, (int, float)) and math.isfinite(v) and v > 0 for v in prices
        ))

    @classmethod
    def from_environment(cls) -> "OpenAIResponsesProvider":
        def configured(name: str) -> float | None:
            try:
                return float(os.environ[name])
            except (KeyError, ValueError):
                return None
        return cls(api_key=os.environ.get("OPENAI_API_KEY"),
                   model_id=os.environ.get("AVSHUNTER_INTERPRETER_MODEL"),
                   input_usd_per_million=configured("AVSHUNTER_INTERPRETER_INPUT_USD_PER_MILLION"),
                   output_usd_per_million=configured("AVSHUNTER_INTERPRETER_OUTPUT_USD_PER_MILLION"),
                   web_search_usd_per_call=configured("AVSHUNTER_INTERPRETER_WEB_SEARCH_USD_PER_CALL"),
                   max_ticker_usd=configured("AVSHUNTER_INTERPRETER_MAX_TICKER_USD"))

    def estimate_report_bound(self, input_chars: int) -> float | None:
        """Conservative configured estimate, not a provider billing guarantee."""
        if not self.ready:
            return None
        # One token per input character plus fixed prompt and two bounded web
        # searches deliberately overestimates typical usage. Pricing is supplied
        # by the operator for the exact model, not embedded in source code.
        input_ceiling = input_chars + 5000 + 2 * 10000
        return round((input_ceiling * self.input_usd_per_million
                      + 8000 * self.output_usd_per_million) / 1_000_000
                     + 2 * self.web_search_usd_per_call, 6)

    def _require_budget(self, input_chars: int) -> None:
        bound = self.estimate_report_bound(input_chars)
        if bound is None:
            raise ProviderUnavailable(
                "Configure OPENAI_API_KEY, model, verified model/tool pricing and per-ticker spend ceiling locally."
            )
        if bound > self.max_ticker_usd:
            raise ProviderUnavailable(
                f"Configured conservative API estimate ${bound:.4f} exceeds per-ticker ceiling; no request sent."
            )

    def _response(self, *, instructions: str, input_value: Mapping[str, Any], schema: dict,
                  name: str, web_search: bool, max_output_tokens: int) -> tuple[dict, set[str], dict]:
        if not self.ready:
            raise ProviderUnavailable(
                "Set OPENAI_API_KEY and AVSHUNTER_INTERPRETER_MODEL locally; do not paste credentials into chat."
            )
        body: dict[str, Any] = {
            "model": self.model_id,
            "store": False,
            "max_output_tokens": max_output_tokens,
            "instructions": instructions,
            "input": json.dumps(input_value, ensure_ascii=False, allow_nan=False),
            "text": {"format": {"type": "json_schema", "name": name,
                                "strict": True, "schema": schema}},
        }
        if web_search:
            body["tools"] = [{"type": "web_search"}]
            body["include"] = ["web_search_call.action.sources"]
            body["max_tool_calls"] = 2
        request = Request(
            "https://api.openai.com/v1/responses",
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers={"Authorization": f"Bearer {self._api_key}",
                     "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout) as stream:
                response = json.load(stream)
        except HTTPError as exc:
            request_id = exc.headers.get("x-request-id") if exc.headers else None
            raise ProviderRequestRejected(exc.code, request_id=request_id, provider="OpenAI Responses") from exc
        except (URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            raise ProviderOutcomeUnknown("OpenAI Responses outcome unknown; no automatic retry") from exc
        if response.get("status") not in ("completed", None):
            if response.get("status") in ("queued", "in_progress"):
                raise ProviderOutcomeUnknown("OpenAI Responses has no terminal outcome; no automatic retry")
            raise ProviderUnavailable(f"OpenAI Responses incomplete: {response.get('status')}")
        messages = []
        sources: set[str] = set()
        for item in response.get("output") or []:
            if item.get("type") == "message":
                for part in item.get("content") or []:
                    if part.get("type") == "output_text":
                        messages.append(part.get("text") or "")
                    for annotation in part.get("annotations") or []:
                        if annotation.get("url"):
                            sources.add(annotation["url"])
            if item.get("type") == "web_search_call":
                for source in (item.get("action") or {}).get("sources") or []:
                    if source.get("url"):
                        sources.add(source["url"])
        if len(messages) != 1:
            raise ProviderUnavailable("OpenAI Responses returned no single structured message")
        try:
            value = json.loads(messages[0])
        except json.JSONDecodeError as exc:
            raise ProviderUnavailable("OpenAI Responses returned invalid structured JSON") from exc
        if not isinstance(value, dict):
            raise ProviderUnavailable("OpenAI Responses output is not an object")
        return value, sources, dict(response.get("usage") or {})

    def report(self, digest: Mapping[str, Any]) -> dict[str, Any]:
        self._require_budget(len(json.dumps(digest, ensure_ascii=False, default=str)))
        evidence_refs = digest.get("evidence_refs")
        allowed_refs = {"EOD_BOOK", "MORNING_HANDOFF", "PIT_PRICE_BARS"}
        if (not isinstance(evidence_refs, list) or not evidence_refs
                or any(ref not in allowed_refs for ref in evidence_refs)):
            raise ProviderUnavailable("report evidence source identifiers are invalid; no request sent")
        value, sources, usage = self._response(
            instructions=REPORT_INSTRUCTIONS_TEMPLATE.format(evidence_refs=", ".join(evidence_refs)),
            input_value={"evidence": digest, "required_sections": _REPORT_KEYS},
            schema=_REPORT_SCHEMA, name="avshunter_interpreter_report_v1", web_search=True,
            max_output_tokens=8000,
        )
        value["_verified_web_urls"] = sorted(sources)
        value["_provider_usage"] = usage
        return value

    def deep_report(self, digest: Mapping[str, Any]) -> dict[str, Any]:
        """Parity method for the OpenAI fallback path — same schema and
        validation as report(), wider digest, one call, distinct tool/schema
        name so a deep-dive result never collides with a standard report's
        persisted file for the same ticker.
        """
        self._require_budget(len(json.dumps(digest, ensure_ascii=False, default=str)))
        evidence_refs = digest.get("evidence_refs")
        allowed_refs = {"EOD_BOOK", "MORNING_HANDOFF", "PIT_PRICE_BARS"}
        if (not isinstance(evidence_refs, list) or not evidence_refs
                or any(ref not in allowed_refs for ref in evidence_refs)):
            raise ProviderUnavailable("report evidence source identifiers are invalid; no request sent")
        value, sources, usage = self._response(
            instructions=DEEP_REPORT_INSTRUCTIONS_TEMPLATE.format(evidence_refs=", ".join(evidence_refs)),
            input_value={"evidence": digest, "required_sections": _REPORT_KEYS},
            schema=_REPORT_SCHEMA, name="avshunter_interpreter_deep_report_v1", web_search=True,
            max_output_tokens=8000,
        )
        value["_verified_web_urls"] = sorted(sources)
        value["_provider_usage"] = usage
        return value

    def answer(self, digest: Mapping[str, Any], report: Mapping[str, Any], question: str) -> dict[str, Any]:
        self._require_budget(len(json.dumps(digest, ensure_ascii=False, default=str))
                             + len(json.dumps(report.get("sections") or [], ensure_ascii=False, default=str))
                             + len(question))
        value, _sources, usage = self._response(
            instructions=ANSWER_INSTRUCTIONS,
            input_value={"evidence": digest, "report": {
                "ticker": report.get("ticker"), "phase": report.get("phase"),
                "executive_summary": report.get("executive_summary"),
                "sections": report.get("sections"), "unresolved": report.get("unresolved"),
            }, "question": question},
            schema=_ANSWER_SCHEMA, name="avshunter_interpreter_answer_v1", web_search=False,
            max_output_tokens=1400,
        )
        value["_provider_usage"] = usage
        return value
