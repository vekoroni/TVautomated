"""Immutable-value EOD review bundle contract for the Pipeline Interpreter.

The bundle is advisory and deliberately separate from the contract-required
Morning handoff. The caller must supply the hash of a *frozen* EOD completion
manifest; this pure builder does not establish terminal run completion or write
files. Those checks belong to the publication adapter.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Mapping, Sequence


SCHEMA_VERSION = "interpreter_eod_review_v1"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class EODReviewBundleError(ValueError):
    """The EOD review input cannot be bound to trustworthy evidence."""


def _digest(value: Any) -> str:
    try:
        payload = json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError) as exc:
        raise EODReviewBundleError("EOD review content is not canonical JSON") from exc
    return hashlib.sha256(payload).hexdigest()


def _hash(value: object, name: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise EODReviewBundleError(f"{name} must be a lowercase SHA-256 digest")
    return value


def _text(value: object) -> str | None:
    if value is None:
        return None
    result = str(value).strip()
    return result or None


def build_eod_review_bundle(
    *,
    run_id: str,
    source_manifest_sha256: str,
    row: Mapping[str, Any],
    evidence_refs: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Build a deterministic, non-authoritative view of one EOD Lab row.

    This captures identity and key thesis fields while binding to a full
    canonical row hash. Additional fields can be read through the separately
    verified source reference; they are never guessed or silently zero-filled.
    """

    if not isinstance(run_id, str) or not run_id.strip():
        raise EODReviewBundleError("run_id is required")
    if not isinstance(row, Mapping) or row.get("run_id") != run_id:
        raise EODReviewBundleError("EOD row/run identity mismatch")
    ticker = _text(row.get("ticker"))
    if not ticker:
        raise EODReviewBundleError("EOD row ticker is required")
    manifest_hash = _hash(source_manifest_sha256, "source_manifest_sha256")
    source_row_sha256 = _digest(dict(row))
    if isinstance(evidence_refs, (str, bytes)) or not evidence_refs:
        raise EODReviewBundleError("at least one governed evidence reference is required")
    refs: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in evidence_refs:
        if not isinstance(raw, Mapping):
            raise EODReviewBundleError("evidence reference must be a mapping")
        dataset_id = _text(raw.get("dataset_id"))
        if not dataset_id or dataset_id in seen:
            raise EODReviewBundleError("evidence dataset identity missing or duplicated")
        seen.add(dataset_id)
        ref: dict[str, Any] = {
            "dataset_id": dataset_id,
            "sha256": _hash(raw.get("sha256"), "evidence sha256"),
        }
        if raw.get("asof_utc") is not None:
            ref["asof_utc"] = _text(raw.get("asof_utc"))
        refs.append(ref)

    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "authority": "ADVISORY_ONLY",
        "pipeline_mode": "EOD",
        "run_id": run_id,
        "ticker": ticker.upper(),
        "thesis_id": _text(row.get("thesis_id")),
        "direction": _text(row.get("canonical_direction") or row.get("direction")),
        "source_action": _text(row.get("final_action")),
        "selected_contract_symbol": _text(
            row.get("selected_contract_symbol") or row.get("contract_symbol")
        ),
        "target_price": row.get("target_price"),
        "invalidation_spot": row.get("invalidation_spot"),
        "planned_hold_sessions": row.get("planned_hold_sessions"),
        "source_manifest_sha256": manifest_hash,
        "source_row_sha256": source_row_sha256,
        "evidence_refs": refs,
    }
    payload["bundle_id"] = _digest(payload)
    return payload
