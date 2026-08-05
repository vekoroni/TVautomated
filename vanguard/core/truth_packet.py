from __future__ import annotations

import hashlib
import json
import warnings
from typing import Any, Dict, Optional

from .actuarial_registry import expected_schema_fingerprint, schema_version, strict_mode
from .schema_contract_v6 import (
    SOURCE_DISCOVERY_FALLBACK,
    SOURCE_MISSING,
    SOURCE_V6_DB,
    TRUTH_DISCOVERY_FALLBACK,
    TRUTH_INVALID,
    TRUTH_MISSING,
    TRUTH_VALID,
    TRUTH_VALID_FALLBACK,
)


class TruthPacketError(RuntimeError):
    """Raised when actuarial truth metadata is internally inconsistent."""


def classify_truth_status(block: Dict[str, Any]) -> str:
    source = str(block.get("actuarial_source") or block.get("source") or "").upper()
    no_match = bool(block.get("no_match"))
    if source == SOURCE_DISCOVERY_FALLBACK:
        return TRUTH_DISCOVERY_FALLBACK
    if source == SOURCE_MISSING or no_match or not block.get("available", True):
        return TRUTH_MISSING
    if source == SOURCE_V6_DB:
        try:
            if int(block.get("fallback_depth") or 0) > 0:
                return TRUTH_VALID_FALLBACK
        except Exception:
            pass
        return TRUTH_VALID
    return TRUTH_INVALID


def build_truth_packet_id(block: Dict[str, Any]) -> str:
    payload = {
        "source": block.get("actuarial_source"),
        "schema_version": block.get("schema_version"),
        "schema_fingerprint": block.get("schema_fingerprint"),
        "state_key": block.get("state_key"),
        "matched_key": block.get("matched_key"),
        "fallback_depth": block.get("fallback_depth"),
        "sample_size": block.get("sample_size"),
        "valid": block.get("valid"),
        "no_match": block.get("no_match"),
    }
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return "tp_v6_" + hashlib.sha256(blob).hexdigest()[:24]


def apply_truth_packet(block: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(block)
    out["truth_packet_status"] = classify_truth_status(out)
    out["truth_packet_id"] = build_truth_packet_id(out)
    return out


def validate_truth_packet(
    block: Dict[str, Any],
    *,
    strict: Optional[bool] = None,
) -> bool:
    strict = strict_mode() if strict is None else strict
    source = str(block.get("actuarial_source") or "").upper()
    problems = []

    if source == SOURCE_V6_DB:
        expected_version = schema_version()
        expected_fingerprint = expected_schema_fingerprint()
        if block.get("schema_version") != expected_version:
            problems.append(
                f"truth packet schema_version mismatch: expected {expected_version}, got {block.get('schema_version')}"
            )
        if block.get("schema_fingerprint") != expected_fingerprint:
            problems.append(
                "truth packet schema_fingerprint mismatch: "
                f"expected {expected_fingerprint}, got {block.get('schema_fingerprint')}"
            )

    expected_status = classify_truth_status(block)
    if block.get("truth_packet_status") and block.get("truth_packet_status") != expected_status:
        problems.append(
            f"truth packet status mismatch: expected {expected_status}, got {block.get('truth_packet_status')}"
        )

    if block.get("truth_packet_id"):
        expected_id = build_truth_packet_id(block)
        if block.get("truth_packet_id") != expected_id:
            problems.append("truth packet id mismatch")

    if problems and strict:
        raise TruthPacketError("; ".join(problems))
    for message in problems:
        warnings.warn(message, RuntimeWarning, stacklevel=2)
    return not problems
