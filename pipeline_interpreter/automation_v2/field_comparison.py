"""Field-level comparison between legacy and shadow trade briefs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


DEFAULT_COMPARISON_FIELDS = (
    "ticker",
    "direction",
    "trade_state",
    "horizon",
    "dte",
    "trigger_level",
    "kill_switch_level",
    "preferred_contract",
    "premium",
    "rr",
    "iv_context",
    "ivp",
    "earnings_in_window",
    "earnings_action",
    "max_pain_risk",
    "sector_confirmation_required",
    "first_hour_rule",
    "probe_permitted",
    "initial_adverse_tolerance",
    "narrative_summary",
)


@dataclass(frozen=True, slots=True)
class FieldDifference:
    field: str
    legacy: str
    shadow: str


@dataclass(frozen=True, slots=True)
class FieldComparison:
    ticker: str
    compared_fields: int
    matching_fields: int
    match_rate: float
    differences: tuple[FieldDifference, ...]
    sovereign_fields_excluded: tuple[str, ...] = (
        "final_verdict",
        "execution_permission",
        "capital_permission",
        "eil_action",
    )


def _normal(value: Any) -> str:
    return " ".join(str(value or "").strip().upper().split())


def compare_trade_briefs(
    legacy: Mapping[str, Any],
    shadow: Mapping[str, Any],
    fields: tuple[str, ...] = DEFAULT_COMPARISON_FIELDS,
) -> FieldComparison:
    ticker = _normal(shadow.get("ticker") or legacy.get("ticker"))
    differences = []
    matching = 0
    for field in fields:
        legacy_value = _normal(legacy.get(field))
        shadow_value = _normal(shadow.get(field))
        if legacy_value == shadow_value:
            matching += 1
        else:
            differences.append(
                FieldDifference(field, legacy_value, shadow_value)
            )
    total = len(fields)
    return FieldComparison(
        ticker=ticker,
        compared_fields=total,
        matching_fields=matching,
        match_rate=matching / total if total else 1.0,
        differences=tuple(differences),
    )
