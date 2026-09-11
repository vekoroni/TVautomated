"""Conservative deterministic text checks, NOT a general semantic truth engine."""
from dataclasses import dataclass
import json
import re

from .application import CheckedDraft, ProviderResponse, validate_response
from .domain import ContractError, EvidenceBundle, WorkerJob, canonical


TOKEN = re.compile(r"\{\{evidence:([^{}]+)\}\}")
AUTHORITY = re.compile(r"\b(buy[_ ]now|sell[_ ]now|enter now|capital permission|guaranteed profit|reverse direction)\b", re.I)


def authority_language(text):
    """Allow only explicit denial forms; still scan the rest of the sentence.

    Avoid a broad negation window: 'no doubt, capital permission granted'
    and mixed denial/approval sentences must remain flagged.
    """
    denied = re.sub(r"\bno capital permission (?:exists|is granted)\b", "", text, flags=re.I)
    denied = re.sub(r"\bcapital permission (?:is denied|is not granted|remains denied)\b", "", denied, flags=re.I)
    return AUTHORITY.search(denied)



@dataclass(frozen=True, slots=True)
class NarrativeIssue:
    location: str
    code: str


@dataclass(frozen=True, slots=True)
class NarrativeReview:
    issues: tuple[NarrativeIssue, ...]
    semantic_review_required: bool = True
    publication_ready: bool = False


def render_numeric_template(text: str, bundle: EvidenceBundle, allowed_refs: tuple[str, ...]) -> str:
    """Plain text only: every digit-bearing number must come from an explicit token.

    Not HTML sanitisation. Raw numbers, dates and identifiers with digits are
    deliberately unsupported in this restricted template form.
    """
    if type(text) is not str or type(allowed_refs) is not tuple or any(type(r) is not str for r in allowed_refs):
        raise ContractError("template and immutable reference scope required")
    index = {obs.evidence_id: obs for obs in bundle.observations}
    scrubbed = TOKEN.sub("", text)
    if "{{" in scrubbed or "}}" in scrubbed or re.search(r"\d", scrubbed):
        raise ContractError("raw or malformed numeric template content")
    def substitute(match):
        ref = match.group(1)
        if ref not in allowed_refs or ref not in index:
            raise ContractError("template numeric reference outside supporting evidence")
        obs = index[ref]
        if obs.status != "AVAILABLE" or type(obs.value) not in (int, float):
            raise ContractError("template requires available numeric evidence")
        return f"{canonical(obs.value)} {obs.unit}"
    return TOKEN.sub(substitute, text)


def review_narrative(job: WorkerJob, draft: CheckedDraft) -> NarrativeReview:
    # Never trust a hand-constructed CheckedDraft or a mutable parsed payload.
    checked = validate_response(job, ProviderResponse(draft.payload_json, draft.request_id,
                                                     job.provider, job.model, "COMPLETE"))
    if checked.job_key != draft.job_key or checked.evidence_hash != draft.evidence_hash:
        raise ContractError("draft metadata mismatch")
    payload = json.loads(checked.payload_json)
    issues = []
    claims = {claim["claim_id"]: claim for claim in payload["claims"]}
    items = [(f"claim:{c['claim_id']}", c["text"], tuple(c["supporting_evidence_ids"]))
             for c in payload["claims"]]
    for section in payload["sections"]:
        location = f"section:{section['section']}"
        refs = tuple(sorted({ref for cid in section["claim_ids"]
                             for ref in claims[cid]["supporting_evidence_ids"]}))
        if not section["claim_ids"]:
            issues.append(NarrativeIssue(location, "UNCITED_SECTION_REVIEW"))
        items.append((location, section["summary"], refs))
    for location, text, refs in items:
        if authority_language(text):
            issues.append(NarrativeIssue(location, "AUTHORITY_LANGUAGE_REVIEW"))
        try:
            render_numeric_template(text, job.bundle, refs)
        except ContractError:
            issues.append(NarrativeIssue(location, "UNBOUND_OR_INVALID_NUMBER_REVIEW"))
    return NarrativeReview(tuple(issues))
