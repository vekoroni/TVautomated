"""Configuration registry value objects (pure)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum
import hashlib
import json
import re
from typing import Any, Mapping

SCHEMA_VERSION = "avs-config-registry-v1"

UNITS = frozenset({
    "sessions", "calendar_days", "fraction", "percent", "usd", "usd_per_share",
    "usd_per_contract", "sigma", "contracts", "shares", "credits", "seconds",
    "count", "none",
})

KEY_PATTERN = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z0-9_]+)+$")
APPROVAL_PATTERN = re.compile(r"^[A-Z]+-\d{8}-[A-Za-z0-9-]+$")

REQUIRED_FIELDS = (
    "config_key", "version", "value", "value_type", "unit", "effective_from",
    "validation_state", "business_owner", "approval_id", "rationale",
    "evidence_ref", "provenance", "recorded_at_utc",
)


class ConfigError(ValueError):
    """Raised for any invalid, unresolvable or unauthorised configuration use."""


class ValueType(str, Enum):
    NUMBER = "NUMBER"
    INTEGER = "INTEGER"
    STRING = "STRING"
    BOOLEAN = "BOOLEAN"
    LIST = "LIST"
    OBJECT = "OBJECT"


class ValidationState(str, Enum):
    PROVISIONAL = "PROVISIONAL"
    VALIDATED = "VALIDATED"
    RETIRED = "RETIRED"


class AuthorityState(str, Enum):
    IMPLEMENTED_FOR_REPLICATION = "IMPLEMENTED_FOR_REPLICATION"
    NOT_YET_VALIDATED_FOR_PRODUCTION_AUTHORITY = "NOT_YET_VALIDATED_FOR_PRODUCTION_AUTHORITY"
    SHADOW = "SHADOW"
    AUTHORITATIVE = "AUTHORITATIVE"


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _matches_type(value: Any, value_type: ValueType) -> bool:
    if value_type is ValueType.BOOLEAN:
        return isinstance(value, bool)
    if value_type is ValueType.INTEGER:
        return isinstance(value, int) and not isinstance(value, bool)
    if value_type is ValueType.NUMBER:
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if value_type is ValueType.STRING:
        return isinstance(value, str)
    if value_type is ValueType.LIST:
        return isinstance(value, list)
    return isinstance(value, dict)


@dataclass(frozen=True, slots=True)
class ConfigEntry:
    config_key: str
    version: int
    value: Any
    value_type: ValueType
    unit: str
    effective_from: date
    validation_state: ValidationState
    business_owner: str
    approval_id: str
    rationale: str
    evidence_ref: str | None
    provenance: str
    recorded_at_utc: str

    @property
    def lock_id(self) -> str:
        return f"{self.config_key}@{self.version}"

    def content_hash(self) -> str:
        payload = {
            "config_key": self.config_key,
            "version": self.version,
            "value": self.value,
            "value_type": self.value_type.value,
            "unit": self.unit,
            "effective_from": self.effective_from.isoformat(),
            "validation_state": self.validation_state.value,
            "business_owner": self.business_owner,
            "approval_id": self.approval_id,
            "rationale": self.rationale,
            "evidence_ref": self.evidence_ref,
            "provenance": self.provenance,
            "recorded_at_utc": self.recorded_at_utc,
        }
        return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "ConfigEntry":
        missing = [name for name in REQUIRED_FIELDS if name not in raw]
        if missing:
            raise ConfigError(f"configuration entry missing fields {missing}: {dict(raw)}")
        key = str(raw["config_key"])
        if not KEY_PATTERN.match(key):
            raise ConfigError(f"invalid config_key {key!r}")
        version = raw["version"]
        if not isinstance(version, int) or isinstance(version, bool) or version < 1:
            raise ConfigError(f"{key}: version must be a positive integer")
        try:
            value_type = ValueType(str(raw["value_type"]))
            state = ValidationState(str(raw["validation_state"]))
            effective_from = date.fromisoformat(str(raw["effective_from"]))
        except ValueError as error:
            raise ConfigError(f"{key}@{version}: {error}") from error
        if not _matches_type(raw["value"], value_type):
            raise ConfigError(f"{key}@{version}: value does not match value_type {value_type.value}")
        unit = str(raw["unit"])
        if unit not in UNITS:
            raise ConfigError(f"{key}@{version}: unit {unit!r} not in vocabulary")
        approval_id = str(raw["approval_id"] or "")
        if not APPROVAL_PATTERN.match(approval_id):
            raise ConfigError(f"{key}@{version}: approval_id {approval_id!r} is not valid")
        for name in ("business_owner", "rationale", "provenance", "recorded_at_utc"):
            if not str(raw[name] or "").strip():
                raise ConfigError(f"{key}@{version}: {name} must not be empty")
        provenance = str(raw["provenance"])
        if provenance != "NEW" and not provenance.startswith("MIGRATED_FROM:"):
            raise ConfigError(f"{key}@{version}: provenance must be NEW or MIGRATED_FROM:<source>")
        evidence_ref = raw["evidence_ref"]
        if state is ValidationState.VALIDATED and not str(evidence_ref or "").strip():
            raise ConfigError(f"{key}@{version}: VALIDATED requires evidence_ref")
        return cls(
            config_key=key,
            version=version,
            value=raw["value"],
            value_type=value_type,
            unit=unit,
            effective_from=effective_from,
            validation_state=state,
            business_owner=str(raw["business_owner"]),
            approval_id=approval_id,
            rationale=str(raw["rationale"]),
            evidence_ref=None if evidence_ref in (None, "") else str(evidence_ref),
            provenance=provenance,
            recorded_at_utc=str(raw["recorded_at_utc"]),
        )


@dataclass(frozen=True, slots=True)
class ConfigValue:
    config_key: str
    version: int
    value: Any
    unit: str
    validation_state: ValidationState
