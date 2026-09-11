"""Conservative semantic lint; never a claim of exhaustive truth verification."""
from dataclasses import dataclass
import json
import re

from .domain import digest
from .v2.assessment import validate_assessment, build_evidence


@dataclass(frozen=True, slots=True)
class SemanticReview:
    status: str
    findings: tuple[str, ...]
    assessment_hash: str
    human_review_required: bool = True
    publication_ready: bool = False
    policy_version: str = "semantic_lint_v1"


def review_assessment(context, response):
    checked = validate_assessment(context, response)
    payload = json.loads(checked.payload_json)
    catalog = build_evidence(context)["catalog"]
    findings = list(checked.review_flags)
    all_text = [c["text"] for c in payload["claims"]] + [s["summary"] for s in payload["sections"]]
    for text in all_text:
        if re.search(r"\b(buy now|sell now|enter now|guaranteed|risk.free|capital approved|reverse (the )?direction)\b", text, re.I):
            findings.append("AUTHORITY_OR_GUARANTEE_LANGUAGE")
        if re.search(r"\b(no news|no risks?|no events?)\b", text, re.I):
            findings.append("UNSUPPORTED_ABSENCE_CLAIM")
        if re.search(r"\bphase\s+[abcde]\b|historical (win|success) rate", text, re.I):
            findings.append("UNIMPLEMENTED_PHASE_OR_HISTORICAL_SUCCESS_CLAIM")
    for claim in payload["claims"]:
        text = claim["text"]
        refs = claim["supporting_evidence_ids"]
        rows = [catalog[ref] for ref in refs]
        if re.search(r"absorption|exhaustion|buyers? (?:are )?in control|sellers? (?:are )?in control", text, re.I):
            reports = [r for r in rows if r.get("observation", {}).get("field") == "behaviour_report"]
            if not reports:
                findings.append("BEHAVIOUR_CLAIM_WITHOUT_BEHAVIOUR_EVIDENCE:" + claim["claim_id"])
            if claim["claim_type"] != "HYPOTHESIS":
                findings.append("BEHAVIOUR_PROXY_PRESENTED_AS_FACT:" + claim["claim_id"])
        if re.search(r"\b(current|now|today|latest)\b", text, re.I):
            if rows and all(r.get("version") == "prior" for r in rows):
                findings.append("PRIOR_EVIDENCE_PRESENTED_AS_CURRENT:" + claim["claim_id"])
        for row in rows:
            observation = row.get("observation", {})
            if observation.get("field") == "behaviour_report":
                report = json.loads(observation["value"])
                if report.get("status") != "ASSESSED":
                    findings.append("INSUFFICIENT_BEHAVIOUR_EVIDENCE:" + claim["claim_id"])
                if re.search(r"buyers? (?:are )?in control", text, re.I) and report.get("control") != "BUYER_CONTROL_PROXY":
                    findings.append("CONTROL_CONTRADICTS_COMPUTATION:" + claim["claim_id"])
                if re.search(r"sellers? (?:are )?in control", text, re.I) and report.get("control") != "SELLER_CONTROL_PROXY":
                    findings.append("CONTROL_CONTRADICTS_COMPUTATION:" + claim["claim_id"])
    findings = tuple(sorted(set(findings)))
    return SemanticReview("BLOCKED" if findings else "REQUIRES_HUMAN_REVIEW", findings, digest(payload))
