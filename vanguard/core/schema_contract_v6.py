from __future__ import annotations

import os
from typing import Dict, Tuple


SCHEMA_VERSION = "actuarial_v6"
STRICT_ENV = "AVSHUNTER_STRICT_ACTUARIAL_V6"

SOURCE_V6_DB = "V6_DB"
SOURCE_DISCOVERY_FALLBACK = "DISCOVERY_FALLBACK"
SOURCE_MISSING = "MISSING"

TRUTH_VALID = "VALID"
TRUTH_VALID_FALLBACK = "VALID_FALLBACK"
TRUTH_DISCOVERY_FALLBACK = "DISCOVERY_FALLBACK"
TRUTH_MISSING = "MISSING"
TRUTH_INVALID = "INVALID"

REQUIRED_CANONICAL_FIELDS = (
    "state_v2",
    "state_hash",
    "momentum_bucket",
    "location_bucket",
    "future_momentum_bucket",
    "wyckoff_phase_bucket",
    "phase_v2",
    "trend_direction",
    "structure_quality",
    "vol_regime",
    "atr_percentile",
    "dist_from_high",
    "dist_from_low",
    "return_5d",
    "return_10d",
    "return_20d",
    "max_drawdown_20d",
    "hit_10pct_20d",
    "bucket_schema_version",
)

REQUIRED_FIELD_ALIASES: Dict[str, Tuple[str, ...]] = {
    "return_5d": ("return_5d", "outcome_5d_return"),
    "return_10d": ("return_10d", "outcome_10d_return"),
    "return_20d": ("return_20d", "outcome_20d_return"),
    "max_drawdown_20d": ("max_drawdown_20d", "outcome_max_drawdown_20d"),
    "hit_10pct_20d": ("hit_10pct_20d", "outcome_hit_10pct_up"),
}

HORIZON_FUTURE_FIELDS = (
    "future_momentum_bucket",
    "preferred_horizon",
    "horizon_bucket",
    "future_path_label",
    "return_5d",
    "return_10d",
    "return_20d",
    "max_drawdown_20d",
    "time_to_target_bucket",
)

CACHE_METADATA_FIELDS = (
    "schema_version",
    "schema_fingerprint",
    "actuarial_source",
    "truth_packet_status",
)


def strict_mode() -> bool:
    return os.environ.get(STRICT_ENV, "").strip().lower() in {"1", "true", "yes", "on"}


def aliases_for(field: str) -> Tuple[str, ...]:
    return REQUIRED_FIELD_ALIASES.get(field, (field,))
