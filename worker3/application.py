"""Provider port and structural validation; semantic acceptance is a later gate."""
from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from typing import Protocol

from .domain import ClaimType, ContractError, Section, WorkerJob, canonical, nonempty


@dataclass(frozen=True, slots=True)
class ProviderResponse:
    json_text: str
    request_id: str
    provider: str
    model: str
    completion_status: str


class AssessmentProvider(Protocol):
    def generate(self, job: WorkerJob) -> ProviderResponse: ...


@dataclass(frozen=True, slots=True)
class CheckedDraft:
    job_key: str
    evidence_hash: str
    request_id: str
    payload_json: str
    semantic_review_required: bool = True
    publication_ready: bool = False


def _keys(value, expected):
    if type(value) is not dict or set(value) != set(expected):
        raise ContractError(f"object requires exactly {sorted(expected)}")


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ContractError("duplicate JSON key")
        result[key] = value
    return result


def _constant(value):
    raise ContractError(f"non-finite JSON value: {value}")


def _refs(value, known, *, required=False):
    if type(value) is not list or any(type(x) is not str for x in value):
        raise ContractError("references must be a string array")
    if len(set(value)) != len(value) or (required and not value):
        raise ContractError("duplicate or missing references")
    if any(x not in known for x in value):
        raise ContractError("unknown reference")


def validate_response(job: WorkerJob, response: ProviderResponse) -> CheckedDraft:
    if not isinstance(response, ProviderResponse):
        raise ContractError("provider response required")
    if response.completion_status != "COMPLETE":
        raise ContractError("incomplete/truncated provider response")
    if (response.provider, response.model) != (job.provider, job.model):
        raise ContractError("provider/model mismatch")
    nonempty(response.request_id, "provider request id")
    if not isinstance(response.json_text, str) or len(response.json_text) > 200_000:
        raise ContractError("response missing or exceeds bounded size")
    try:
        payload = json.loads(response.json_text, object_pairs_hook=_pairs,
                             parse_constant=_constant)
    except (ValueError, RecursionError) as exc:
        raise ContractError("invalid strict JSON") from exc
    try:
        canonical(payload)  # Also rejects exponent overflow such as 1e999.
    except (ValueError, TypeError, RecursionError) as exc:
        raise ContractError("non-finite or unsupported payload") from exc
    _keys(payload, ("schema_version", "job_key", "identity", "evidence_hash", "authority",
                    "claims", "sections", "numeric_facts"))
    if payload["schema_version"] != "trading_assessment_draft_v1":
        raise ContractError("unsupported assessment schema")
    if payload["authority"] != "ADVISORY_ONLY":
        raise ContractError("assessment cannot claim trading authority")
    expected_identity = asdict(job.bundle.identity)
    _keys(payload["identity"], expected_identity)
    # Strict JSON equality prevents True from being accepted as hold_sessions=1.
    if canonical(payload["identity"]) != canonical(expected_identity):
        raise ContractError("assessment identity mismatch")
    if payload["evidence_hash"] != job.bundle.evidence_hash or payload["job_key"] != job.job_key:
        raise ContractError("assessment belongs to different evidence/job")
    observations = {o.evidence_id: o for o in job.bundle.observations}
    available = {key for key, obs in observations.items() if obs.status == "AVAILABLE"}
    if type(payload["claims"]) is not list:
        raise ContractError("claims must be an array")
    claim_ids = set()
    for claim in payload["claims"]:
        _keys(claim, ("claim_id", "claim_type", "text", "supporting_evidence_ids",
                      "contradicting_evidence_ids"))
        nonempty(claim["claim_id"], "claim id")
        nonempty(claim["text"], "claim text")
        if claim["claim_id"] in claim_ids:
            raise ContractError("duplicate claim id")
        claim_ids.add(claim["claim_id"])
        if type(claim["claim_type"]) is not str or claim["claim_type"] not in {x.value for x in ClaimType}:
            raise ContractError("unknown claim type")
        _refs(claim["supporting_evidence_ids"], available, required=True)
        _refs(claim["contradicting_evidence_ids"], available)
        if set(claim["supporting_evidence_ids"]) & set(claim["contradicting_evidence_ids"]):
            raise ContractError("same observation cannot support and contradict a claim")
    if type(payload["sections"]) is not list or len(payload["sections"]) != len(Section):
        raise ContractError("all eight sections required")
    section_ids = set()
    used_claims = set()
    for section in payload["sections"]:
        _keys(section, ("section", "summary", "claim_ids"))
        if type(section["section"]) is not str or section["section"] not in {x.value for x in Section}:
            raise ContractError("unknown section")
        if section["section"] in section_ids:
            raise ContractError("duplicate section")
        section_ids.add(section["section"])
        nonempty(section["summary"], "section summary")
        _refs(section["claim_ids"], claim_ids)
        used_claims.update(section["claim_ids"])
    if used_claims != claim_ids:
        raise ContractError("unreferenced claims")
    if type(payload["numeric_facts"]) is not list:
        raise ContractError("numeric facts must be an array")
    fact_ids = set()
    for fact in payload["numeric_facts"]:
        _keys(fact, ("evidence_id", "value", "unit"))
        if type(fact["evidence_id"]) is not str or fact["evidence_id"] not in available:
            raise ContractError("unknown/unavailable fact reference")
        if fact["evidence_id"] in fact_ids:
            raise ContractError("duplicate numeric fact")
        fact_ids.add(fact["evidence_id"])
        obs = observations[fact["evidence_id"]]
        if type(obs.value) not in (int, float):
            raise ContractError("numeric fact requires numeric source (not boolean)")
        if canonical(fact["value"]) != canonical(obs.value) or fact["unit"] != obs.unit:
            raise ContractError("numeric value/unit differs from source")
    try:
        clean = canonical(payload)
    except (ValueError, TypeError) as exc:
        raise ContractError("non-finite or unsupported payload") from exc
    return CheckedDraft(job.job_key, job.bundle.evidence_hash, response.request_id, clean)


def assess(job: WorkerJob, provider: AssessmentProvider) -> CheckedDraft:
    """No retries, IO, publication or SDK here; failures propagate to future coordinator."""
    return validate_response(job, provider.generate(job))
