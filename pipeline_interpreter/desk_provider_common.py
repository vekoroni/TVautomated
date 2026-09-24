"""Provider-neutral contracts shared by every Interpreter Desk transport.

Any transport (OpenAI Responses, Anthropic Messages, or a future one) raises
these same exception types and is validated against these same schemas, so
``interactive_desk.py``'s failure classification and report/answer validation
never have to know which model vendor produced a result. Nothing here talks
to a network, stores credentials, or grants execution/capital authority.
"""

from __future__ import annotations

import re
from typing import Any


class ProviderUnavailable(RuntimeError):
    pass


class ProviderRequestRejected(ProviderUnavailable):
    """The provider returned a definite HTTP rejection, not a lost response."""

    def __init__(self, http_status: int, *, request_id: str | None = None, provider: str = "Provider",
                 detail: str | None = None):
        self.http_status = http_status
        self.request_id = request_id if request_id and re.fullmatch(r"[A-Za-z0-9_-]{1,128}", request_id) else None
        # Free-text detail from the provider's own error body. Never a credential
        # or evidence field — just the provider's rejection reason (e.g. bad
        # request shape) — so it's safe to persist and show to the operator.
        self.detail = detail.strip()[:500] if isinstance(detail, str) and detail.strip() else None
        message = f"{provider} HTTP {http_status}; no automatic retry"
        if self.detail:
            message = f"{message} — {self.detail}"
        super().__init__(message)


class ProviderOutcomeUnknown(ProviderUnavailable):
    """A request may have reached the provider, but no terminal response is known."""


_REPLY_REASON_CODES = frozenset({
    # after the paid call: the reply could not be used
    "NO_STRUCTURED_TOOL_CALL", "MULTIPLE_STRUCTURED_TOOL_CALLS", "SDK_ERROR",
    # before the paid call: the transport stopped itself and sent nothing
    "SDK_MISSING", "COST_CEILING_EXCEEDED", "EVIDENCE_REFS_INVALID",
})
_REPLY_TOKEN = re.compile(r"[A-Za-z0-9_]{1,40}")
_REPLY_MAX_BLOCK_TYPES = 32


class ProviderReplyUnusable(ProviderUnavailable):
    """The provider answered, but the reply carried no single usable structured result.

    Approved by ACK 24 Sep 2026: the case is named in typed, bounded fields (a
    reason code from a fixed set, the API's own stop reason token, the ordered
    content block types) so a receipt can say which case occurred. The message
    is fixed; provider prose, evidence and credentials never travel here.
    """

    def __init__(self, reason_code: str, *, stop_reason: Any = None, block_types: Any = None):
        self.reason_code = reason_code if reason_code in _REPLY_REASON_CODES else "UNCLASSIFIED"
        self.stop_reason = (stop_reason if isinstance(stop_reason, str) and _REPLY_TOKEN.fullmatch(stop_reason)
                            else "UNRECOGNISED")
        self.block_types = [b for b in (block_types or []) if isinstance(b, str) and _REPLY_TOKEN.fullmatch(b)
                            ][:_REPLY_MAX_BLOCK_TYPES] if isinstance(block_types, (list, tuple)) else []
        super().__init__(f"Provider reply unusable: {self.reason_code} (stop_reason={self.stop_reason}); "
                         "no automatic retry")


_REPORT_KEYS = ["macro", "gamma", "liquidity", "thesis", "chart", "options_flow", "risk", "verdict"]


def _object(properties: dict[str, Any]) -> dict[str, Any]:
    return {"type": "object", "properties": properties, "required": list(properties),
            "additionalProperties": False}


def _report_schema(chain_keys: Any) -> dict[str, Any]:
    return _object({
        "executive_summary": {"type": "string"},
        "evidence_chain_review": {"type": "array", "items": _object({
            "key": {"type": "string", "enum": list(chain_keys)},
            "status": {"type": "string"},
            "text": {"type": "string"},
            "evidence_class": {"type": "string", "enum": ["OBSERVED", "DERIVED", "INFERRED", "UNKNOWN"]},
            "evidence_refs": {"type": "array", "items": {"type": "string"}},
        })},
        "counter_case": _object({
            "links": {"type": "array", "items": {"type": "string", "enum": list(chain_keys)}},
            "text": {"type": "string"},
            "evidence_refs": {"type": "array", "items": {"type": "string"}},
        }),
        "sections": {"type": "array", "items": _object({
            "key": {"type": "string", "enum": _REPORT_KEYS},
            "text": {"type": "string"},
            "evidence_class": {"type": "string", "enum": ["OBSERVED", "DERIVED", "INFERRED", "UNKNOWN"]},
            "evidence_refs": {"type": "array", "items": {"type": "string"}},
        })},
        "external_events": {"type": "array", "items": _object({
            "url": {"type": "string"}, "asof_utc": {"type": "string"}, "summary": {"type": "string"},
        })},
        "unresolved": {"type": "array", "items": {"type": "string"}},
    })


_ANSWER_SCHEMA = _object({
    "answer": {"type": "string"},
    "evidence_class": {"type": "string", "enum": ["OBSERVED", "DERIVED", "INFERRED", "UNKNOWN"]},
    "evidence_refs": {"type": "array", "items": {"type": "string"}},
    "limitations": {"type": "array", "items": {"type": "string"}},
})


REPORT_INSTRUCTIONS_TEMPLATE = (
    "You are AVSHUNTER's advisory Pipeline Interpreter. Explain only the supplied "
    "governed evidence. Produce all eight analytical sections with specific levels, "
    "sequence of events, supporting and contradicting facts, uncertainty, and the "
    "next observation that would change the assessment. The chart section must "
    "derive its narrative from numeric structure/profile data, never screenshots. "
    "Produce exactly five evidence_chain_review items in sector, ticker, thesis, "
    "contract, morning order. Copy each link's status exactly from evidence.confluence; "
    "cite its evidence_ref and explain what is confirmed, opposed or unknown. "
    "Sector and ticker relative returns are pre-decision price observations, not "
    "literal fund inflows or proof of buyer identity. A frozen EOD quote is not a "
    "live executable quote. An absent catalyst means cause unverified, not no thesis. "
    "Never turn advisory confluence into execution permission. "
    "Provide a counter_case naming every confluence link whose status is opposed, "
    "missing, pending or otherwise not supportive, with the corresponding evidence refs. "
    "Use web search only "
    "for point-in-time earnings/news, with URL and event time; otherwise leave "
    "external_events empty. Distinguish observed facts, derivations, inference and "
    "unknowns. No screenshots. Do not change ticker, direction, contract, target, "
    "invalidation, action, size, capital permission or broker state. Hidden orders "
    "cannot be observed without depth/prints; qualify any location inference. "
    "Cite only the source identifiers supplied in evidence.evidence_refs: {evidence_refs}."
)

DEEP_REPORT_INSTRUCTIONS_TEMPLATE = (
    "You are AVSHUNTER's advisory Pipeline Interpreter, running a deeper single-ticker "
    "review. You have been given a wider governed evidence set than the standard report — "
    "including market-physics state (energy, force, entropy, regime-instability, phase-"
    "transition probabilities), McMillan advisory signals (IV/GEX entry quality, gamma-"
    "island-on-path, move-vs-theta margin, crowd-arrival state), and wall-break scoring "
    "(WBS grade and its component triggers), where present on this ticker. Use whatever of "
    "this extra evidence is present to sharpen and cross-check the same eight sections — do "
    "not add new sections or a separate narrative layer for a junior audience. Write for an "
    "experienced trader: plain, direct, specific numbers and levels. If a term genuinely "
    "needs unpacking, unpack it briefly inline rather than assuming background knowledge; "
    "do not pad the report with definitions the trader already knows. "
    "Produce all eight analytical sections with specific levels, sequence of events, "
    "supporting and contradicting facts, uncertainty, and the next observation that would "
    "change the assessment. The chart section must derive its narrative from numeric "
    "structure/profile data, never screenshots. "
    "Produce exactly five evidence_chain_review items in sector, ticker, thesis, "
    "contract, morning order. Copy each link's status exactly from evidence.confluence; "
    "cite its evidence_ref and explain what is confirmed, opposed or unknown. "
    "Sector and ticker relative returns are pre-decision price observations, not "
    "literal fund inflows or proof of buyer identity. A frozen EOD quote is not a "
    "live executable quote. An absent catalyst means cause unverified, not no thesis. "
    "Never turn advisory confluence into execution permission. "
    "Provide a counter_case naming every confluence link whose status is opposed, "
    "missing, pending or otherwise not supportive, with the corresponding evidence refs. "
    "Use web search only "
    "for point-in-time earnings/news, with URL and event time; otherwise leave "
    "external_events empty. Distinguish observed facts, derivations, inference and "
    "unknowns. No screenshots. Do not change ticker, direction, contract, target, "
    "invalidation, action, size, capital permission or broker state. Hidden orders "
    "cannot be observed without depth/prints; qualify any location inference. "
    "Cite only the source identifiers supplied in evidence.evidence_refs: {evidence_refs}."
)

ANSWER_INSTRUCTIONS = (
    "Answer the human's question about this one frozen AVSHUNTER advisory report. "
    "Use only supplied evidence and report; do not fetch new facts or mix tickers. "
    "Explicitly state uncertainty and unavailable order depth/trade prints. "
    "Do not grant trading, order, position-sizing or capital authority."
)
