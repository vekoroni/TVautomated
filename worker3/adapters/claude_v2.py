"""Offline-tested v2 adapter; same injected transport and stop handling as v1."""
from dataclasses import asdict, dataclass

from .claude import ClaudeAdapter, POLICY
from .bound_output import output_schema
from ..domain import ContractError, Section, WorkerJob, canonical
from ..report_detail import guidance
from ..v2.assessment import AssessmentContext, PROMPT, SCHEMA, build_evidence, validate_assessment


@dataclass(frozen=True, slots=True)
class ClaudeV2Adapter(ClaudeAdapter):
    context: AssessmentContext

    def request_for(self, job: WorkerJob) -> dict:
        if job.job_key != self.context.job.job_key or job.provider != "ANTHROPIC" or job.prompt_version != PROMPT:
            raise ContractError("v2 adapter context/provider/prompt mismatch")
        evidence = build_evidence(self.context)
        output = {"schema_version": SCHEMA, "job_key": job.job_key,
                  "identity": asdict(job.bundle.identity), "evidence_hash": job.bundle.evidence_hash,
                  "context_hash": self.context.context_hash, "authority": "ADVISORY_ONLY",
                  "claims": [], "sections": [{"section": s.value, "summary": "Evidence review pending.",
                                               "claim_ids": []} for s in Section], "numeric_facts": []}
        instructions = {
            "claims": {"claim_id": "unique string", "claim_type": "OBSERVATION|INTERPRETATION|HYPOTHESIS",
                       "text": "prose with bound slots", "supporting_evidence_ids": ["catalog ref"],
                       "contradicting_evidence_ids": []},
            "numeric_facts": "Return an empty array []. Numeric figures are rendered from bound slots; do not duplicate them here.",
            "serialization": "Return exactly one bare JSON object. No Markdown fences, preamble, or trailing commentary.",
            "section_summaries": "Use qualitative prose only: no slots and no numerical figures. Put numerical detail in cited claims. Each section must list the claim_ids that support its summary.",
            "rules": "Use {{slot:catalog-ref}} for all figures/scenario states. No raw digits in prose. "
                     "Every slot reference must also appear verbatim in that same claim supporting_evidence_ids. "
                     "Choose at most two evidence references per claim before writing the prose; "
                     "omit any extra figure rather than adding an uncited slot. Preserve current/prior distinction. "
                     "Do not calculate deltas or scenario outcomes; use supplied system evidence. "
                     "For unavailable deltas explain the supplied reason without inventing a number. "
                     "All claims require citations and must be used by a section. No extra fields.",
            "section_coverage": {
                "rule": "Every section must cite at least one claim. Allocate one focused, "
                    "evidence-backed pair of claims per section before adding detail. Summaries must only "
                    "summarize those claims; do not introduce extra factual statements. "
                    "Never attach unrelated claims merely to fill claim_ids.",
                "documents": "COMPANY and CONTEXT may cite AVAILABLE structured_json source "
                    "documents for qualitative facts actually present in those documents. "
                    "Do not claim that catalysts, news or risks are absent simply because "
                    "the supplied evidence does not cover them.",
                "comparison": "For CHANGES cite the comparison context record below to explain "
                    "whether a prior assessment was supplied. No prior assessment supplied does "
                    "not prove that this is the first-ever report or that no earlier report exists.",
                "comparison_context_ref": next(ref for ref, row in evidence["catalog"].items()
                    if row["kind"] == "CONTEXT" and ref.startswith("context:comparison:")),
            },
            "response_budget": {
                "min_claims": 16, "target_claims": 16, "max_claims": 20, "max_words_per_claim": 90,
                "target_total_prose_words": 1200,
                "max_words_per_section_summary": 60,
                "max_supporting_refs_per_claim": 2,
                "completion_priority": "Return the entire output contract and all eight sections. "
                    "Provide at least two distinct substantive claims per section: evidence and "
                    "implication or limitation. Aim for a detailed explanation, not terse labels. "
                    "Avoid repeating claims across sections. Use the supplied evidence tables for "
                    "raw field inventories. Do not expand prose at the expense of "
                    "the identity, sections or closing JSON delimiters.",
            },
            "reference_rules": "Every citation and slot must use an EXACT KEY from "
                "untrusted_bound_evidence.catalog, including its current/prior prefix and "
                "bundle hash. Never use observation.evidence_id, a nested source ID, or a "
                "shortened lab:/native: ID instead of the full catalog key. "
                "Slots support AVAILABLE numeric observations/changes or SCENARIO states only. "
                "For OBSERVATION and CHANGE, inspect the catalog value JSON type: only an "
                "unquoted JSON number is eligible. A quoted numeric-looking string, boolean, "
                "null, object, or array is NOT numeric and must never be placed in a slot. "
                "SCENARIO kind is the only exception that permits a string-valued slot. "
                "Never put a structured_json document or a categorical observation in a slot. "
                "Describe categorical evidence in prose with its full catalog citation. "
                "Keep dates and digit-bearing identifiers in the supplied identity metadata; "
                "do not repeat them in prose. Do not spell out source numbers to avoid slots. "
                "Omit unsupported numerical detail instead of inventing or extracting an "
                "unbound number from a nested document.",
            "valid_numeric_claim_examples": [
                {"text": "The supplied value is {{slot:" + ref + "}}.",
                 "supporting_evidence_ids": [ref]}
                for ref, row in list((ref, row) for ref, row in evidence["catalog"].items()
                                    if row["status"] == "AVAILABLE"
                                    and row["unit"] != "structured_json"
                                    and type(row["value"]) in (int, float))[:2]
            ],
        }
        instructions["detailed_analysis"] = guidance(evidence["catalog"])
        packet = {"output_contract": output, "field_rules": instructions, "untrusted_bound_evidence": evidence,
                  "prior_report": self.context.previous.payload if self.context.previous else None,
                  "prior_report_validation": "STRUCTURAL_ONLY" if self.context.previous else "NOT_APPLICABLE"}
        request = {"model": job.model, "max_tokens": self.max_output_tokens,
                   "system": POLICY + "\nUse the v2 bound slots; distinguish historical figures from current figures. "
                   "The prior report is not certified truth. Scenario states are snapshot observations, not trade permission. "
                   "Follow the response_budget and reference_rules exactly. A complete concise "
                   "eight-section response is required; never exhaust the output on a long claims list. "
                   "Return bare JSON only, without Markdown code fences or surrounding prose. "
                   "Keep numeric_facts empty; use only eligible catalog slots for numerical prose.",
                   "messages": [{"role": "user", "content": canonical(packet)}]}
        request["output_config"] = {"format": {"type": "json_schema",
                                               "schema": output_schema(output, evidence["catalog"], detailed=True)}}
        if len(canonical(request).encode("utf-8")) > self.max_input_bytes:
            raise ContractError("v2 complete evidence exceeds byte limit; not truncated")
        return request

    def assess(self):
        return validate_assessment(self.context, self.generate(self.context.job))
