"""One bound contract for current/prior observations, comparisons and scenarios."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
import json
import re

from ..application import ProviderResponse, _keys, _pairs, _constant, validate_response
from ..domain import ContractError, EvidenceBundle, Observation, WorkerJob, canonical, digest, instant, utc
from ..narrative import authority_language
from ..refresh import compare_evidence
from ..scenarios import evaluate_price_scenario


SCHEMA = "trading_assessment_draft_v2"
PROMPT = "worker3-bound-assessment-v2"
SLOT = re.compile(r"\{\{slot:([^{}]+)\}\}")


@dataclass(frozen=True, slots=True)
class ScenarioSpec:
    kind: str
    price_id: str
    level_id: str
    origin_id: str


@dataclass(frozen=True, slots=True)
class AssessmentContext:
    job: WorkerJob
    scenarios: tuple[ScenarioSpec, ...] = ()
    previous: PreviousAssessment | None = None

    def __post_init__(self):
        if not isinstance(self.job, WorkerJob) or self.job.prompt_version != PROMPT:
            raise ContractError("v2 job/prompt required")
        if type(self.scenarios) is not tuple or any(not isinstance(s, ScenarioSpec) for s in self.scenarios):
            raise ContractError("immutable scenario specs required")
        if len({canonical(asdict(s)) for s in self.scenarios}) != len(self.scenarios):
            raise ContractError("duplicate scenario spec")
        if self.job.task_type == "INITIAL_ASSESSMENT":
            if self.previous is not None:
                raise ContractError("initial assessment cannot have a predecessor")
        else:
            if not isinstance(self.previous, PreviousAssessment):
                raise ContractError("full validated prior v2 assessment required")
            if self.job.previous_assessment_id != self.previous.assessment_id:
                raise ContractError("prior assessment identity mismatch")
            if instant(self.previous.generated_at) > instant(self.job.bundle.evidence_cutoff_utc):
                raise ContractError("prior report unavailable at current cutoff")
            compare_evidence(self.previous.context.job.bundle, self.job.bundle)
        for spec in self.scenarios:
            evaluate_price_scenario(self.job.bundle, **asdict(spec))

    @property
    def context_hash(self):
        return digest(build_evidence(self))


@dataclass(frozen=True, slots=True)
class CheckedAssessment:
    payload_json: str
    rendered_json: str
    context_hash: str
    review_flags: tuple[str, ...]
    semantic_review_required: bool = True
    publication_ready: bool = False


@dataclass(frozen=True, slots=True)
class PreviousAssessment:
    context: AssessmentContext
    response: ProviderResponse
    generated_at: str
    _payload_json: str = field(init=False, repr=False)
    _assessment_id: str = field(init=False, repr=False)

    def __post_init__(self):
        checked = validate_assessment(self.context, self.response)
        object.__setattr__(self, "generated_at", utc(self.generated_at))
        if instant(self.generated_at) < instant(self.context.job.bundle.evidence_cutoff_utc):
            raise ContractError("report predates its evidence")
        object.__setattr__(self, "_payload_json", checked.payload_json)
        object.__setattr__(self, "_assessment_id", digest({"payload": json.loads(checked.payload_json),
                           "context_hash": checked.context_hash, "generated_at": self.generated_at,
                           "request_id": self.response.request_id}))

    @property
    def payload(self):
        return json.loads(self._payload_json)

    @property
    def assessment_id(self):
        return self._assessment_id


def build_evidence(context: AssessmentContext) -> dict:
    job = context.job
    catalog = {}
    def add_bundle(bundle, version):
        for obs in sorted(bundle.observations, key=lambda o: o.evidence_id):
            ref = f"{version}:{bundle.evidence_hash}:{obs.evidence_id}"
            catalog[ref] = {"kind": "OBSERVATION", "version": version,
                            "evidence_hash": bundle.evidence_hash, "observation": asdict(obs),
                            "identity": asdict(bundle.identity), "value": obs.value,
                            "unit": obs.unit, "status": obs.status}
    add_bundle(job.bundle, "current")
    comparison = None
    if context.previous:
        old = context.previous.context.job.bundle
        add_bundle(old, "prior")
        comparison = asdict(compare_evidence(old, job.bundle))
        for change in comparison["changes"]:
            ref = "change:" + digest({"before": old.evidence_hash, "after": job.bundle.evidence_hash,
                                       "scope": change["scope"], "field": change["field"]})
            catalog[ref] = {"kind": "CHANGE", "version": "comparison", "value": change["numeric_delta"],
                            "unit": next((o.unit for o in job.bundle.observations
                                          if (o.scope, o.field) == (change["scope"], change["field"])), "unknown"),
                            "status": "AVAILABLE" if change["numeric_delta"] is not None else "UNAVAILABLE",
                            "detail": change, "before_hash": old.evidence_hash,
                            "after_hash": job.bundle.evidence_hash}
    # Citable system provenance describes supplied context, never an assertion
    # that no earlier report exists outside this request.
    comparison_context = {
        "current_evidence_hash": job.bundle.evidence_hash,
        "previous_assessment_id": context.previous.assessment_id if context.previous else None,
        "status": "PRIOR_ASSESSMENT_SUPPLIED" if context.previous else "NO_PRIOR_ASSESSMENT_SUPPLIED",
        "reason": "Comparison uses the supplied prior assessment." if context.previous
                  else "Comparison is unavailable because no prior assessment was supplied.",
    }
    comparison_ref = "context:comparison:" + digest(comparison_context)
    catalog[comparison_ref] = {
        "kind": "CONTEXT", "version": "current", "status": "AVAILABLE",
        "value": canonical(comparison_context), "unit": "structured_json",
        "detail": comparison_context,
    }
    scenario_results = []
    for spec in sorted(context.scenarios, key=lambda s: canonical(asdict(s))):
        result = asdict(evaluate_price_scenario(job.bundle, **asdict(spec)))
        ref = "scenario:" + digest(result)
        catalog[ref] = {"kind": "SCENARIO", "version": "current", "value": result["state"],
                        "unit": "monitoring_state", "status": "AVAILABLE", "detail": result}
        scenario_results.append({"ref": ref, "result": result})
    return {"schema_version": "analyst_bound_evidence_v2", "job_key": job.job_key,
            "current_identity": asdict(job.bundle.identity), "current_evidence_hash": job.bundle.evidence_hash,
            "previous_assessment_id": context.previous.assessment_id if context.previous else None,
            "catalog": catalog, "comparison": comparison, "scenarios": scenario_results,
            "authority": "ADVISORY_ONLY"}


def _render(text: str, refs: set[str], catalog: dict) -> str:
    scrubbed = SLOT.sub("", text)
    if "{{" in scrubbed or "}}" in scrubbed or re.search(r"\d", scrubbed):
        raise ContractError("v2 narrative figures must use bound slots, not raw digits")
    def substitute(match):
        ref = match.group(1)
        if ref not in refs or ref not in catalog:
            raise ContractError("slot is not in the claim's supporting evidence")
        row = catalog[ref]
        if row["status"] != "AVAILABLE" or row["unit"] == "structured_json":
            raise ContractError("slot is unavailable or contains an unflattened context document")
        if row["kind"] == "SCENARIO":
            return f"{row['value']} [snapshot monitoring only; advisory]"
        if type(row["value"]) not in (int, float):
            raise ContractError("observation/change slots require numeric data")
        provenance = "COMPUTED CHANGE" if row["kind"] == "CHANGE" else row["version"].upper()
        if row["kind"] == "OBSERVATION":
            obs = row["observation"]
            provenance += f" as_of={obs['observed_at']}"
            if obs["scope"] == "CONTRACT":
                provenance += f" contract={obs['contract_id']}"
        return f"{canonical(row['value'])} {row['unit']} [{provenance}]"
    return SLOT.sub(substitute, text)


def validate_assessment(context: AssessmentContext, response: ProviderResponse) -> CheckedAssessment:
    if not isinstance(response, ProviderResponse) or type(response.json_text) is not str or len(response.json_text) > 200_000:
        raise ContractError("invalid/oversized v2 provider response")
    try:
        payload = json.loads(response.json_text, object_pairs_hook=_pairs, parse_constant=_constant)
        canonical(payload)
    except (ValueError, TypeError, RecursionError) as exc:
        raise ContractError("invalid strict v2 JSON") from exc
    _keys(payload, ("schema_version", "job_key", "identity", "evidence_hash", "context_hash",
                    "authority", "claims", "sections", "numeric_facts"))
    job = context.job
    bound = build_evidence(context)
    bound_hash = digest(bound)
    if payload["schema_version"] != SCHEMA or payload["context_hash"] != bound_hash:
        raise ContractError("v2 schema/context mismatch")
    if payload["job_key"] != job.job_key or payload["evidence_hash"] != job.bundle.evidence_hash:
        raise ContractError("v2 current evidence/job mismatch")
    # Reuse unchanged v1 strict identity/authority/claim/section checks over a
    # locally bound catalog. Never expose this internal projection as live data.
    cutoff = job.bundle.evidence_cutoff_utc
    observations = tuple(Observation(ref, ref, row["value"], row["unit"], "v2-catalog",
                                     bound_hash, cutoff, cutoff, status=row["status"], scope="CONTEXT")
                         for ref, row in sorted(bound["catalog"].items()))
    synthetic = replace(job, bundle=EvidenceBundle(job.bundle.identity, cutoff, observations))
    projected = dict(payload)
    projected.pop("context_hash")
    projected.update(schema_version="trading_assessment_draft_v1", job_key=synthetic.job_key,
                     evidence_hash=synthetic.bundle.evidence_hash)
    validate_response(synthetic, replace(response, json_text=canonical(projected)))
    catalog = bound["catalog"]
    rendered = json.loads(canonical(payload))
    claim_refs = {}
    flags = []
    for claim in rendered["claims"]:
        refs = set(claim["supporting_evidence_ids"])
        claim_refs[claim["claim_id"]] = refs
        if authority_language(claim["text"]):
            flags.append(f"claim:{claim['claim_id']}:AUTHORITY_LANGUAGE_REVIEW")
        claim["text"] = _render(claim["text"], refs, catalog)
    for section in rendered["sections"]:
        refs = set().union(*(claim_refs[cid] for cid in section["claim_ids"]))
        if not section["claim_ids"]:
            flags.append(f"section:{section['section']}:UNCITED_SECTION_REVIEW")
        if authority_language(section["summary"]):
            flags.append(f"section:{section['section']}:AUTHORITY_LANGUAGE_REVIEW")
        section["summary"] = _render(section["summary"], refs, catalog)
    rendered["system_evidence"] = bound
    return CheckedAssessment(canonical(payload), canonical(rendered), bound_hash, tuple(flags))
