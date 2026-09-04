"""Structured, append-only and non-authoritative Interpreter assessments."""

from __future__ import annotations

import json
import os
import re
import uuid
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Mapping


ASSESSMENT_SCHEMA_VERSION = "interpreter_assessment_v1"
INTERPRETER_AUTHORITY_STATEMENT = (
    "ADVISORY_ONLY — this assessment cannot change governed direction, selected "
    "contract, lifecycle, final action or capital permission."
)


class AssessmentStatus(str, Enum):
    VALID = "VALID"
    REJECTED_SCHEMA = "REJECTED_SCHEMA"
    REJECTED_GOVERNANCE_CONFLICT = "REJECTED_GOVERNANCE_CONFLICT"
    REJECTED_STALE_BUNDLE = "REJECTED_STALE_BUNDLE"


class AssessmentValidationError(ValueError):
    pass


MODEL_FIELDS = frozenset({
    "strengthening_weakening", "agreement_conflict", "manual_checks",
    "data_gaps", "plain_language_reason",
})
COPIED_AUTHORITY_FIELDS = (
    "governed_direction", "selected_contract_symbol", "thesis_state",
    "final_action", "capital_permission", "ms_direction_relationship",
)

# Macro/news packets are useful context but never execution evidence.  Their
# staleness must remain visible without invalidating an otherwise current
# ticker assessment.  Only the domains used to describe the governed ticker,
# selected contract and observed market structure participate in this gate.
ASSESSMENT_CRITICAL_FRESHNESS_DOMAINS = frozenset({
    "exact_option_quote", "option_quote", "selected_contract_quote",
    "underlying_quote", "underlying_price", "market_structure",
})


def _text(value: Any) -> str:
    return str(value or "").strip()


def _canonical_contract(value: Any) -> str:
    return _text(value).upper().replace("O:", "").replace(" ", "")


def _bundle_authority(bundle: Mapping[str, Any]) -> dict[str, str]:
    governed = dict(bundle.get("governed_record") or {})
    return {
        "governed_direction": _text(
            governed.get("governed_direction") or governed.get("final_direction")
        ).upper(),
        "selected_contract_symbol": _canonical_contract(
            bundle.get("selected_contract_symbol")
            or governed.get("selected_contract_symbol")
            or governed.get("contract_symbol")
        ),
        "thesis_state": _text(governed.get("thesis_state")).upper(),
        "final_action": _text(governed.get("final_action")).upper(),
        "capital_permission": _text(governed.get("capital_permission")).upper(),
        "ms_direction_relationship": _text(
            (bundle.get("market_structure") or {}).get("ms_direction_relationship")
            or governed.get("ms_direction_relationship")
        ).upper(),
    }


def _narrative_conflicts(reason: str, authority: Mapping[str, str]) -> list[str]:
    """Detect explicit authority substitutions, not ordinary discussion words."""
    text = reason.upper()
    findings: list[str] = []
    expected_direction = authority.get("governed_direction", "")
    if re.search(r"\b(DIRECTION|TRADE DIRECTION)\s*[:=]\s*(CALL|PUT)\b", text):
        claimed = re.search(r"\b(?:DIRECTION|TRADE DIRECTION)\s*[:=]\s*(CALL|PUT)\b", text)
        if claimed and expected_direction and claimed.group(1) not in expected_direction:
            findings.append("NARRATIVE_DIRECTION_OVERRIDE")
    expected_contract = authority.get("selected_contract_symbol", "")
    match = re.search(r"\b(?:SELECTED CONTRACT|CONTRACT)\s*[:=]\s*([A-Z0-9.]+)\b", text)
    if match and expected_contract and _canonical_contract(match.group(1)) != expected_contract:
        findings.append("NARRATIVE_CONTRACT_OVERRIDE")
    if re.search(r"\b(?:CAPITAL|EXECUTION)\s+(?:IS\s+)?(?:APPROVED|AUTHORI[ZS]ED|PERMITTED)\b", text):
        findings.append("NARRATIVE_CAPITAL_GRANT")
    return findings


def build_assessment(
    *,
    bundle: Mapping[str, Any],
    model_output: Mapping[str, Any],
    model_id: str,
    prompt_version: str,
    prompt_hash: str,
    temperature: float = 0.0,
) -> dict[str, Any]:
    unknown = set(model_output) - MODEL_FIELDS
    status = AssessmentStatus.VALID
    findings: list[str] = []
    if unknown:
        status = AssessmentStatus.REJECTED_SCHEMA
        findings.append("MODEL_FIELDS_NOT_ALLOWED:" + ",".join(sorted(unknown)))
    for field in MODEL_FIELDS:
        if field not in model_output:
            status = AssessmentStatus.REJECTED_SCHEMA
            findings.append(f"MODEL_FIELD_MISSING:{field}")
    freshness = dict(bundle.get("freshness_map") or {})
    critical_freshness = {
        str(domain).lower(): value
        for domain, value in freshness.items()
        if str(domain).lower() in ASSESSMENT_CRITICAL_FRESHNESS_DOMAINS
    }
    if any(
        str(value).upper() in {"STALE", "MISSING", "INVALID"}
        for value in critical_freshness.values()
    ):
        status = AssessmentStatus.REJECTED_STALE_BUNDLE
        findings.append("BUNDLE_NOT_CURRENT_FOR_ASSESSMENT")
    authority = _bundle_authority(bundle)
    conflicts = _narrative_conflicts(
        _text(model_output.get("plain_language_reason")), authority
    )
    if conflicts:
        status = AssessmentStatus.REJECTED_GOVERNANCE_CONFLICT
        findings.extend(conflicts)
    if float(temperature) != 0.0:
        status = AssessmentStatus.REJECTED_SCHEMA
        findings.append("TEMPERATURE_MUST_BE_ZERO")
    assessment = {
        "schema_version": ASSESSMENT_SCHEMA_VERSION,
        "assessment_status": status.value,
        "assessment_id": str(uuid.uuid4()),
        "bundle_id": _text(bundle.get("bundle_id")),
        "run_id": _text(bundle.get("run_id")),
        "ticker": _text(bundle.get("ticker")).upper(),
        "trade_idea_id": _text(bundle.get("trade_idea_id")),
        "model_id": _text(model_id),
        "prompt_version": _text(prompt_version),
        "prompt_hash": _text(prompt_hash).lower(),
        "temperature": 0.0,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        **authority,
        "strengthening_weakening": model_output.get("strengthening_weakening"),
        "agreement_conflict": model_output.get("agreement_conflict"),
        "manual_checks": model_output.get("manual_checks"),
        "data_gaps": model_output.get("data_gaps"),
        "plain_language_reason": model_output.get("plain_language_reason"),
        "authority_statement": INTERPRETER_AUTHORITY_STATEMENT,
        "validation_findings": findings,
    }
    return validate_assessment(assessment, bundle=bundle)


def validate_assessment(
    assessment: Mapping[str, Any], *, bundle: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    value = dict(assessment)
    if value.get("schema_version") != ASSESSMENT_SCHEMA_VERSION:
        raise AssessmentValidationError("ASSESSMENT_SCHEMA_UNSUPPORTED")
    for field in (
        "assessment_id", "assessment_status", "bundle_id", "run_id", "ticker",
        "trade_idea_id", "model_id", "prompt_version", "prompt_hash", "created_utc",
    ):
        if not _text(value.get(field)):
            raise AssessmentValidationError(f"ASSESSMENT_MISSING_{field.upper()}")
    try:
        uuid.UUID(value["assessment_id"])
        uuid.UUID(value["bundle_id"])
        datetime.fromisoformat(value["created_utc"].replace("Z", "+00:00"))
    except ValueError as error:
        raise AssessmentValidationError("ASSESSMENT_ID_OR_TIME_INVALID") from error
    if value.get("temperature") != 0.0:
        raise AssessmentValidationError("ASSESSMENT_TEMPERATURE_NOT_ZERO")
    if value.get("authority_statement") != INTERPRETER_AUTHORITY_STATEMENT:
        raise AssessmentValidationError("ASSESSMENT_AUTHORITY_STATEMENT_INVALID")
    if value.get("assessment_status") not in {item.value for item in AssessmentStatus}:
        raise AssessmentValidationError("ASSESSMENT_STATUS_INVALID")
    if bundle is not None:
        for field in ("bundle_id", "run_id", "ticker", "trade_idea_id"):
            if _text(value.get(field)).upper() != _text(bundle.get(field)).upper():
                raise AssessmentValidationError(f"ASSESSMENT_BUNDLE_MISMATCH:{field}")
        authority = _bundle_authority(bundle)
        for field in COPIED_AUTHORITY_FIELDS:
            if _text(value.get(field)).upper() != _text(authority.get(field)).upper():
                raise AssessmentValidationError(f"ASSESSMENT_AUTHORITY_MISMATCH:{field}")
    return value


def append_assessment(path: Path | str, assessment: Mapping[str, Any]) -> Path:
    """Preserve valid and rejected attempts; consumers display only VALID rows."""
    value = validate_assessment(assessment)
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    return target


def latest_valid_assessment(
    path: Path | str, *, run_id: str, ticker: str, bundle_id: str
) -> dict[str, Any] | None:
    target = Path(path)
    if not target.is_file():
        return None
    matches = []
    with target.open("r", encoding="utf-8-sig") as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                value = validate_assessment(json.loads(line))
            except (json.JSONDecodeError, AssessmentValidationError):
                continue
            if (
                value["assessment_status"] == AssessmentStatus.VALID.value
                and value["run_id"] == run_id
                and value["ticker"] == ticker.upper()
                and value["bundle_id"] == bundle_id
            ):
                matches.append(value)
    return max(matches, key=lambda item: item["created_utc"]) if matches else None


__all__ = [
    "ASSESSMENT_CRITICAL_FRESHNESS_DOMAINS", "ASSESSMENT_SCHEMA_VERSION",
    "AssessmentStatus", "AssessmentValidationError",
    "INTERPRETER_AUTHORITY_STATEMENT", "append_assessment", "build_assessment",
    "latest_valid_assessment", "validate_assessment",
]
