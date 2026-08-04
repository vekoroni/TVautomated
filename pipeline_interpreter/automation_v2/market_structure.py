"""Deterministic market-structure projection from authoritative pipeline inputs."""

from __future__ import annotations

from decimal import Decimal
from math import isfinite
from numbers import Real
from typing import Any, Mapping

from .models import TickerRunRequest


MARKET_STRUCTURE_FIELDS = (
    "call_wall", "put_wall", "gamma_flip", "max_pain", "gex_regime",
    "gex_score", "gamma_island_on_path", "gamma_island_level", "wbs_score",
    "wbs_grade", "wbs_wall_price", "wbs_wall_distance_pct",
    "wbs_entry_guidance", "wbs_stop_guidance", "trigger_primary",
    "trigger_quality", "trigger_score", "trigger_codes", "trigger_go_eligible",
    "trigger_confirmation_state",
)

ALIASES: dict[str, tuple[str, ...]] = {
    "call_wall": ("call_wall", "gex_call_wall"),
    "put_wall": ("put_wall", "gex_put_wall"),
    "gamma_flip": ("gamma_flip", "gex_gamma_flip"),
    "max_pain": ("max_pain", "max_pain_level"),
    "gex_regime": ("gex_regime", "dealer_gamma_state", "gamma_regime"),
    "gex_score": ("gex_score", "eil_gex_score", "gex_regime_score"),
    "gamma_island_on_path": ("gamma_island_on_path", "gamma_island"),
    "gamma_island_level": ("gamma_island_level", "gamma_island_target"),
    "wbs_score": ("wbs_score", "wall_break_score"),
    "wbs_grade": ("wbs_grade", "wall_break_grade"),
    "wbs_wall_price": ("wbs_wall_price", "wall_price", "nearest_wall"),
    "wbs_wall_distance_pct": (
        "wbs_wall_distance_pct", "wbs_wall_dist_pct", "wall_dist_pct",
        "distance_to_wall",
    ),
    "wbs_entry_guidance": ("wbs_entry_guidance", "wall_break_entry_guidance"),
    "wbs_stop_guidance": ("wbs_stop_guidance", "wall_break_stop_guidance"),
    "trigger_primary": (
        "trigger_primary", "primary_trigger", "entry_trigger", "trigger_type",
    ),
    "trigger_quality": ("trigger_quality", "trigger_grade"),
    "trigger_score": ("trigger_score", "eil_trigger_score"),
    "trigger_codes": ("trigger_codes", "trigger_code", "trigger_flags"),
    "trigger_go_eligible": ("trigger_go_eligible", "go_eligible"),
    "trigger_confirmation_state": (
        "trigger_confirmation_state", "trigger_status", "trigger_state",
    ),
}


def _present(value: Any) -> bool:
    if value is None or str(value).strip() == "":
        return False
    if isinstance(value, bool):
        return True
    if isinstance(value, Decimal):
        return value.is_finite()
    if isinstance(value, Real):
        return isfinite(value)
    return str(value).strip().lower() not in {
        "nan", "+nan", "-nan", "inf", "+inf", "-inf",
        "infinity", "+infinity", "-infinity",
    }


def project_market_structure(request: TickerRunRequest) -> dict[str, Any]:
    """Resolve fields using explicit source precedence: live > lab > pipeline."""
    sources: tuple[Mapping[str, Any], ...] = (
        request.live_validation, request.lab_context, request.pipeline_row,
    )
    projected: dict[str, Any] = {}
    for target, aliases in ALIASES.items():
        projected[target] = ""
        for source in sources:
            for alias in aliases:
                value = source.get(alias)
                if _present(value):
                    projected[target] = value
                    break
            if _present(projected[target]):
                break
    if not _present(projected["trigger_confirmation_state"]):
        eligible = str(projected["trigger_go_eligible"]).strip().lower()
        projected["trigger_confirmation_state"] = (
            "CONFIRMED" if eligible in {"1", "true", "yes", "go"} else "NOT_CONFIRMED"
        )
    return projected


def enrich_trade_brief(
    trade_brief: Mapping[str, Any], request: TickerRunRequest
) -> dict[str, Any]:
    enriched = dict(trade_brief)
    enriched.update(project_market_structure(request))
    return enriched
