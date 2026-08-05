from __future__ import annotations

import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

from .actuarial_registry import (
    canonical_cache_path,
    expected_schema_fingerprint,
    load_registry,
    schema_version,
    strict_mode,
)
from .schema_contract_v6 import CACHE_METADATA_FIELDS, SOURCE_V6_DB


class CacheIntegrityError(RuntimeError):
    """Raised when actuarial cache metadata does not match the v6 registry."""


@dataclass
class CacheValidationResult:
    path: str = ""
    schema_version: str = ""
    schema_fingerprint: str = ""
    rows: int = 0
    missing_metadata_fields: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.missing_metadata_fields and not self.warnings

    def to_dict(self) -> Dict[str, object]:
        return {
            "path": self.path,
            "schema_version": self.schema_version,
            "schema_fingerprint": self.schema_fingerprint,
            "rows": self.rows,
            "missing_metadata_fields": self.missing_metadata_fields,
            "warnings": self.warnings,
            "ok": self.ok,
        }


def _single_value(df: pd.DataFrame, column: str) -> str:
    if column not in df.columns:
        return ""
    values = [str(v) for v in df[column].dropna().unique().tolist() if str(v).strip()]
    return values[0] if values else ""


def annotate_cache_frame(df: pd.DataFrame, schema_meta) -> pd.DataFrame:
    out = df.copy()
    out["schema_version"] = schema_meta.schema_version
    out["schema_fingerprint"] = schema_meta.schema_fingerprint
    out["actuarial_source"] = SOURCE_V6_DB
    out["truth_packet_status"] = "VALID"
    return out


def validate_cache_frame(
    df: pd.DataFrame,
    *,
    path: Optional[Path] = None,
    strict: Optional[bool] = None,
) -> CacheValidationResult:
    registry = load_registry()
    strict = strict_mode() if strict is None else strict
    expected_version = schema_version(registry)
    expected_fingerprint = expected_schema_fingerprint(registry)

    missing = [name for name in CACHE_METADATA_FIELDS if name not in df.columns]
    actual_version = _single_value(df, "schema_version")
    actual_fingerprint = _single_value(df, "schema_fingerprint")

    warnings_out: List[str] = []
    if missing:
        warnings_out.append(f"cache missing metadata fields: {', '.join(missing)}")
    if actual_version and actual_version != expected_version:
        warnings_out.append(
            f"cache schema_version mismatch: expected {expected_version}, got {actual_version}"
        )
    if actual_fingerprint and expected_fingerprint and actual_fingerprint != expected_fingerprint:
        warnings_out.append(
            "cache schema_fingerprint mismatch: "
            f"expected {expected_fingerprint}, got {actual_fingerprint}"
        )

    result = CacheValidationResult(
        path=str(path or ""),
        schema_version=actual_version,
        schema_fingerprint=actual_fingerprint,
        rows=len(df),
        missing_metadata_fields=missing,
        warnings=warnings_out,
    )

    if warnings_out and strict:
        raise CacheIntegrityError("; ".join(warnings_out))
    for message in warnings_out:
        warnings.warn(message, RuntimeWarning, stacklevel=2)
    return result


def load_validated_cache(path: Optional[Path] = None, *, strict: Optional[bool] = None) -> tuple[pd.DataFrame, CacheValidationResult]:
    cache_path = Path(path) if path is not None else canonical_cache_path()
    if not cache_path.exists():
        raise FileNotFoundError(f"Actuarial cache not found: {cache_path}")
    df = pd.read_parquet(cache_path)
    return df, validate_cache_frame(df, path=cache_path, strict=strict)
