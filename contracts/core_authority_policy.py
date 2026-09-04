"""Cross-stage authority invariants for the macro-agnostic core.

External macro remains useful context for sector rotation and human review, but
it cannot modify candidate membership, direction, horizon, contract selection
or capital permission.  Thesis identity fields are immutable once populated.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Mapping


CORE_AUTHORITY_POLICY_VERSION = "core-authority-policy-v1"
CORE_QUANT_REGIME = "TRANSITIONAL"
MACRO_AUTHORITY = "ADVISORY_ONLY"

FROZEN_THESIS_FIELDS = (
    "governed_direction",
    "canonical_direction",
    "planned_hold_sessions",
    "target_spot",
    "invalidation_spot",
)


def neutral_vanguard_macro_payload() -> dict[str, Any]:
    """Return a deterministic non-narrative placeholder for legacy schemas."""
    return {
        "vix": 20.0,
        "vix_history": [],
        "spy_price": 0.0,
        "spy_trend": "SIDEWAYS",
        "sector_etf_price": 0.0,
        "sector_relative_strength": 0.0,
        "macro_authority": MACRO_AUTHORITY,
        "macro_core_effective_delta": 0.0,
    }


def macro_advisory_fields(payload: Mapping[str, Any] | None) -> dict[str, Any]:
    source = dict(payload or {})
    return {
        "macro_advisory_payload": source,
        "macro_capital_authority": MACRO_AUTHORITY,
        "macro_candidate_authority": "NONE",
        "macro_direction_authority": "NONE",
        "macro_contract_authority": "NONE",
        "macro_core_effective_delta": 0.0,
        "core_authority_policy_version": CORE_AUTHORITY_POLICY_VERSION,
    }


def _present(value: Any) -> bool:
    return value is not None and str(value).strip().upper() not in {
        "", "NAN", "NONE", "NULL", "N/A",
    }


def _equal(left: Any, right: Any) -> bool:
    try:
        left_number = float(left)
        right_number = float(right)
        if math.isfinite(left_number) and math.isfinite(right_number):
            return abs(left_number - right_number) <= 1e-9
    except (TypeError, ValueError):
        pass
    return str(left).strip().upper() == str(right).strip().upper()


def assert_frozen_thesis_fields(
    before: Mapping[str, Any],
    after: Mapping[str, Any],
    *,
    fields: tuple[str, ...] = FROZEN_THESIS_FIELDS,
) -> None:
    """Reject a downstream mutation of an already-populated thesis field."""
    changes: list[str] = []
    for field in fields:
        original = before.get(field)
        current = after.get(field)
        if not _present(original):
            continue
        if not _equal(original, current):
            changes.append(f"{field}:{original!r}->{current!r}")
    if changes:
        raise ValueError("FROZEN_THESIS_MUTATION:" + "|".join(changes))


@dataclass(frozen=True, slots=True)
class AuthoritySnapshot:
    governed_direction: Any = None
    canonical_direction: Any = None
    planned_hold_sessions: Any = None
    target_spot: Any = None
    invalidation_spot: Any = None

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> "AuthoritySnapshot":
        return cls(**{field: row.get(field) for field in FROZEN_THESIS_FIELDS})

    def validate(self, row: Mapping[str, Any]) -> None:
        assert_frozen_thesis_fields(
            {field: getattr(self, field) for field in FROZEN_THESIS_FIELDS}, row
        )
