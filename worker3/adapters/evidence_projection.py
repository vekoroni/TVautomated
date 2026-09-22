"""Bounded provider view of immutable v2 evidence.

The local evidence catalog and its context hash remain complete. Only the
provider-facing copy of a Lab native document is projected: its two nested
lineage/payload blobs are not narrative fields and can dwarf the selected
ticker row. Their identities and sizes remain explicit in the request.
"""
from __future__ import annotations

from hashlib import sha256
import json

from ..domain import ContractError, canonical


_LAB_FIELD = "native_document_lab_signal_book"
_NESTED_FIELDS = ("source_payload_json", "field_provenance_json")


def project_provider_evidence(evidence: dict) -> dict:
    """Return a provider view without mutating or re-hashing local evidence."""
    catalog = evidence["catalog"]
    projected_catalog = None
    for ref, item in catalog.items():
        observation = item.get("observation")
        if not isinstance(observation, dict) or observation.get("field") != _LAB_FIELD:
            continue
        raw = observation.get("value")
        if item.get("unit") != "structured_json" or not isinstance(raw, str) or item.get("value") != raw:
            raise ContractError("Lab native evidence cannot be projected safely")
        try:
            document = json.loads(raw)
            source = document["source_document"]
            row = source["row"]
            if not isinstance(document, dict) or not isinstance(source, dict) or not isinstance(row, dict):
                raise TypeError("Lab native document is not an object")
        except (ValueError, KeyError, TypeError) as exc:
            raise ContractError("invalid Lab native evidence projection input") from exc
        omitted = {}
        for field in _NESTED_FIELDS:
            if field in row:
                value = row[field]
                if not isinstance(value, str):
                    raise ContractError("Lab nested source field has changed type")
                omitted[field] = {"sha256": sha256(value.encode("utf-8")).hexdigest(),
                                  "bytes": len(value.encode("utf-8"))}
        if not omitted:
            continue
        selected_row = {key: value for key, value in row.items() if key not in omitted}
        selected_source = {**source, "row": selected_row}
        selected_document = {**document, "source_document": selected_source}
        projected_observation = {**observation, "value": canonical(selected_document)}
        projected_item = {key: value for key, value in item.items() if key != "value"}
        projected_item["observation"] = projected_observation
        projected_item["provider_projection"] = {
            "kind": "SELECTED_LAB_ROW_WITH_NESTED_SOURCE_EXCLUSIONS",
            "full_value_sha256": sha256(raw.encode("utf-8")).hexdigest(),
            "full_value_bytes": len(raw.encode("utf-8")),
            "omitted_nested_fields": omitted,
            "omitted_field_policy": "Not supplied to the model; do not infer their contents. "
                                    "Complete immutable evidence remains in the local Worker job.",
        }
        if projected_catalog is None:
            projected_catalog = dict(catalog)
        projected_catalog[ref] = projected_item
    if projected_catalog is None:
        return evidence
    return {**evidence, "catalog": projected_catalog,
            "provider_view": "SELECTED_LAB_ROW_PROJECTION_V1; local context hash covers complete evidence"}
