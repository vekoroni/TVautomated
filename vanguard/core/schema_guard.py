from __future__ import annotations

import hashlib
import json
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Optional

import pandas as pd

from .actuarial_registry import (
    canonical_db_path,
    expected_schema_fingerprint,
    load_registry,
    schema_version,
    strict_mode,
    validate_production_db_path,
)
from .schema_contract_v6 import REQUIRED_CANONICAL_FIELDS, aliases_for


FINGERPRINT_ALGORITHM = "sha256:parquet_schema_arrow_v1"


class SchemaContractError(RuntimeError):
    """Raised when the v6 actuarial schema contract is violated."""


@dataclass
class SchemaValidationResult:
    path: str
    schema_version: str
    schema_fingerprint: str
    fingerprint_algorithm: str = FINGERPRINT_ALGORITHM
    required_fields: List[str] = field(default_factory=list)
    resolved_fields: Dict[str, str] = field(default_factory=dict)
    missing_fields: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.missing_fields

    def to_dict(self) -> Dict[str, object]:
        return {
            "path": self.path,
            "schema_version": self.schema_version,
            "schema_fingerprint": self.schema_fingerprint,
            "fingerprint_algorithm": self.fingerprint_algorithm,
            "required_fields": self.required_fields,
            "resolved_fields": self.resolved_fields,
            "missing_fields": self.missing_fields,
            "warnings": self.warnings,
            "ok": self.ok,
        }


def _fingerprint_payload_from_arrow_schema(path: Path) -> Mapping[str, object]:
    import pyarrow.parquet as pq

    schema = pq.ParquetFile(path).schema_arrow
    return {
        "algorithm": FINGERPRINT_ALGORITHM,
        "fields": [
            {"name": name, "type": str(schema.field(name).type)}
            for name in schema.names
        ],
    }


def fingerprint_schema_from_path(path: Path) -> str:
    payload = _fingerprint_payload_from_arrow_schema(Path(path))
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def columns_from_parquet(path: Path) -> List[str]:
    import pyarrow.parquet as pq

    return list(pq.ParquetFile(path).schema_arrow.names)


def _resolve_required_fields(
    columns: Iterable[str], contract_version: str
) -> tuple[Dict[str, str], List[str], List[str]]:
    available = set(columns)
    resolved: Dict[str, str] = {}
    missing: List[str] = []
    notes: List[str] = []

    for field_name in REQUIRED_CANONICAL_FIELDS:
        physical = next((candidate for candidate in aliases_for(field_name) if candidate in available), None)
        if physical is None:
            missing.append(field_name)
            continue
        resolved[field_name] = physical
        if physical != field_name:
            notes.append(
                f"{field_name} resolved via explicit {contract_version} "
                f"compatibility mapping to {physical}"
            )

    return resolved, missing, notes


def validate_actuarial_database(
    path: Optional[Path] = None,
    *,
    strict: Optional[bool] = None,
) -> SchemaValidationResult:
    registry = load_registry()
    strict = strict_mode() if strict is None else strict
    db_path = Path(path) if path is not None else canonical_db_path(registry, require_exists=True)
    validate_production_db_path(db_path, registry=registry, strict=strict)

    if not db_path.exists():
        raise FileNotFoundError(f"Canonical actuarial database not found: {db_path}")

    columns = columns_from_parquet(db_path)
    fingerprint = fingerprint_schema_from_path(db_path)
    expected = expected_schema_fingerprint(registry)
    active_schema_version = schema_version(registry)
    resolved, missing, notes = _resolve_required_fields(columns, active_schema_version)

    warnings_out = list(notes)
    if expected and fingerprint != expected:
        warnings_out.append(
            f"schema fingerprint mismatch: expected {expected}, got {fingerprint}"
        )

    result = SchemaValidationResult(
        path=str(db_path),
        schema_version=active_schema_version,
        schema_fingerprint=fingerprint,
        required_fields=list(REQUIRED_CANONICAL_FIELDS),
        resolved_fields=resolved,
        missing_fields=missing,
        warnings=warnings_out,
    )

    fatal = []
    if missing:
        fatal.append(f"missing required canonical schema fields: {', '.join(missing)}")
    if expected and fingerprint != expected:
        fatal.append(
            f"schema fingerprint mismatch: expected {expected}, got {fingerprint}"
        )

    if fatal and strict:
        raise SchemaContractError("; ".join(fatal))
    # Compatibility aliases are expected by the governed field register and
    # remain in result.warnings for audit provenance. Only actual contract
    # failures should emit RuntimeWarning noise during every pipeline run.
    for message in fatal:
        warnings.warn(message, RuntimeWarning, stacklevel=2)

    return result


def load_validated_actuarial_dataframe(
    path: Optional[Path] = None,
    *,
    strict: Optional[bool] = None,
) -> tuple[pd.DataFrame, SchemaValidationResult]:
    result = validate_actuarial_database(path=path, strict=strict)
    return pd.read_parquet(result.path), result
