"""Point-in-time Actuarial feature evidence for governed outcome learning."""

from __future__ import annotations

import math
from typing import Any, Mapping


ACTUARIAL_FEATURE_OBSERVATION_VERSION = "actuarial-feature-observation-v1"

ACTUARIAL_FEATURE_ALIASES: dict[str, tuple[str, ...]] = {
    "original_state_key": ("layer2__original_state_key", "actuarial_original_state_key"),
    "matched_state_key": ("layer2__matched_state_key", "actuarial_matched_state_key"),
    "match_method": ("layer2__state_match_method", "actuarial_match_method"),
    "match_quality": ("layer2__state_match_quality", "actuarial_match_quality"),
    "match_similarity": ("layer2__state_match_similarity",),
    "sample_size": ("layer2__sample_size", "actuarial_sample_size"),
    "sample_confidence_bucket": ("layer2__sample_confidence_bucket",),
    "confidence_penalty": ("layer2__confidence_penalty",),
    "confidence_weight": ("layer2__confidence_weight",),
    "preferred_horizon": ("layer2__preferred_horizon", "actuarial_preferred_horizon"),
    "vol_regime": ("layer2__vol_regime", "actuarial_vol_regime"),
    "trend_direction": ("layer2__trend_direction", "actuarial_trend_direction"),
    "structure_quality": ("layer2__structure_quality", "actuarial_structure_quality"),
    "trend_maturity": ("layer2__trend_maturity", "actuarial_trend_maturity"),
    "raw_prob_up_5d": ("layer2__raw_prob_up_5d",),
    "raw_prob_up_10d": ("layer2__raw_prob_up_10d",),
    "raw_prob_up_20d": ("layer2__raw_prob_up_20d",),
    "raw_prob_down_5d": ("layer2__raw_prob_down_5d",),
    "raw_prob_down_10d": ("layer2__raw_prob_down_10d",),
    "raw_prob_down_20d": ("layer2__raw_prob_down_20d",),
    "raw_prob_target_hit": ("layer2__raw_prob_target_hit",),
    "raw_prob_stop_hit": ("layer2__raw_prob_stop_hit",),
    "raw_expected_return": ("layer2__raw_expected_return",),
    "raw_expected_drawdown": ("layer2__raw_expected_drawdown",),
    "raw_expected_time_to_target": ("layer2__raw_expected_time_to_target",),
    "baseline_probability": ("layer2__baseline_probability",),
    "adjusted_prob_target_hit": ("layer2__adjusted_prob_target_hit",),
    "adjusted_expected_return": ("layer2__adjusted_expected_return",),
    "probability_edge": ("layer2__probability_edge",),
    "probability_verdict": ("layer2__probability_verdict",),
}


def _clean(value: Any) -> Any:
    if value is None:
        return None
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    text = str(value).strip().upper()
    if text in {"", "NAN", "NONE", "NULL"}:
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def actuarial_feature_observation_from_row(
    row: Mapping[str, Any],
) -> dict[str, Any]:
    features: dict[str, Any] = {}
    source_fields: dict[str, str] = {}
    for canonical, aliases in ACTUARIAL_FEATURE_ALIASES.items():
        for alias in aliases:
            value = _clean(row.get(alias))
            if value is not None:
                features[canonical] = value
                source_fields[canonical] = alias
                break
    return {
        "schema_version": ACTUARIAL_FEATURE_OBSERVATION_VERSION,
        "state": "CAPTURED" if features else "UNAVAILABLE",
        "features": features,
        "source_fields": source_fields,
        "calculation_version": _clean(
            row.get("actuarial_calculation_version")
            or row.get("calculation_version")
        ),
        "schema_fingerprint": _clean(row.get("actuarial_schema_fingerprint")),
        "authority": "OBSERVATION_ONLY",
        "can_change_direction": False,
        "can_grant_execution": False,
        "can_allocate_capital": False,
    }


__all__ = [
    "ACTUARIAL_FEATURE_ALIASES",
    "ACTUARIAL_FEATURE_OBSERVATION_VERSION",
    "actuarial_feature_observation_from_row",
]
