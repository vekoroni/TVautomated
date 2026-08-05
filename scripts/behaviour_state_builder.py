#!/usr/bin/env python3
"""
AVSHUNTER Behaviour State Builder.

Production-intended additive helper:
- keep existing state_hash as the broad actuarial bucket
- add behaviour_state_key/hash as the finer monetisation state
- avoid raw free-text tags inside hashes
"""

from __future__ import annotations

import hashlib
from typing import Any, Iterable

import pandas as pd


BEHAVIOUR_DIMS = [
    "phase_v2",
    "momentum_bucket",
    "location_bucket",
    "trigger_state",
    "horizon_bucket",
    "direction",
    "catalyst_overlay",
]


def _is_blank(value: Any) -> bool:
    if value is None:
        return True
    try:
        if pd.isna(value):
            return True
    except Exception:
        pass
    text = str(value).strip()
    return text == "" or text.upper() in {"NAN", "NONE", "NULL", "NA"}


def _norm(value: Any, default: str = "UNK") -> str:
    if _is_blank(value):
        return default
    return str(value).upper().strip().replace(" ", "_").replace("-", "_")


def _first(row: Any, names: Iterable[str], default: str = "UNK") -> str:
    for name in names:
        try:
            value = row.get(name)
        except Exception:
            value = None
        if not _is_blank(value):
            return _norm(value, default=default)
    return default


def derive_horizon_bucket(value: Any) -> str:
    if _is_blank(value):
        return "UNK"
    text = str(value).upper().strip()
    if text in {"SHORT", "MED", "MEDIUM", "LONG"}:
        return "MED" if text == "MEDIUM" else text
    if text in {"1_5D", "1-5D", "1_5", "0_7D", "0-7D"}:
        return "SHORT"
    if text in {"6_10D", "6-10D", "6_10", "8_21D", "8-21D"}:
        return "MED"
    if text in {"11_20D", "11-20D", "11_20", "22_PLUS", "22+D"}:
        return "LONG"
    try:
        dte = int(float(text))
    except Exception:
        return "UNK"
    if 0 <= dte <= 7:
        return "SHORT"
    if 8 <= dte <= 21:
        return "MED"
    if dte >= 22:
        return "LONG"
    return "UNK"


def derive_catalyst_overlay(row: Any) -> str:
    existing = _first(row, ["catalyst_overlay", "catalyst_state_overlay"], default="")
    if existing in {"NONE", "NEAR", "ACTIVE", "POST", "UNK"}:
        return existing

    detected = _first(row, ["catalyst_detected", "has_catalyst"], default="FALSE")
    trade_class = _first(row, ["catalyst_trade_class"], default="")
    quality = _first(row, ["catalyst_data_quality"], default="")
    if detected not in {"TRUE", "1", "YES"} and "CATALYST" not in trade_class and quality in {"", "NO_CATALYST"}:
        return "NONE"

    dte = _first(row, ["catalyst_dte", "days_to_catalyst", "days_to_event", "days_to_trigger"], default="")
    if dte:
        try:
            days = int(float(dte))
            if days == 0:
                return "ACTIVE"
            if days < 0:
                return "POST"
            if days <= 7:
                return "NEAR"
        except Exception:
            pass

    if quality in {"DATED_REVIEW", "CONFIRMED", "HIGH"}:
        return "NEAR"
    if trade_class in {"EVENT_CONVEXITY_WATCH", "DATED_CATALYST_CONFIRMED"}:
        return "NEAR"
    if detected in {"TRUE", "1", "YES"}:
        return "NEAR"
    return "NONE"


def derive_direction(row: Any) -> str:
    side = _first(
        row,
        [
            "direction",
            "primary_direction",
            "direction_bias",
            "trade_bias",
            "selected_contract_side",
            "options_direction",
            "edge_direction",
            "trend_direction",
        ],
        default="UNK",
    )
    if side in {"CALL", "BUY", "BULL", "BULLISH", "LONG_CALL", "UP"}:
        return "BULLISH"
    if side in {"PUT", "SELL", "BEAR", "BEARISH", "LONG_PUT", "DOWN"}:
        return "BEARISH"
    if side in {"NEUTRAL", "SIDEWAYS"}:
        return "NEUTRAL"
    return side or "UNK"


def derive_trigger_state(row: Any) -> str:
    existing = _first(row, ["trigger_state"], default="")
    if existing in {"TRIGGER_EARLY_PROBE", "NO_TRIGGER"}:
        return existing
    if existing and existing not in {"UNK", "NONE"}:
        if any(token in existing for token in ("BREAK", "SQUEEZE", "COMPRESSION", "RANGE", "REVERSAL", "PULLBACK", "RETEST")):
            return "TRIGGER_EARLY_PROBE"
        return existing

    primary = _first(row, ["trigger_primary", "trigger_quality", "trigger_codes"], default="")
    if primary:
        if primary in {"NO_TRIGGER", "NONE"}:
            return "NO_TRIGGER"
        if any(token in primary for token in ("BREAK", "SQUEEZE", "COMPRESSION", "RANGE", "REVERSAL", "PULLBACK", "RETEST")):
            return "TRIGGER_EARLY_PROBE"

    phase = _first(row, ["phase_v2", "layer2__phase_v2"], default="")
    if phase == "EARLY_TRANSITION":
        return "TRIGGER_EARLY_PROBE"
    return "NO_TRIGGER"


def build_behaviour_state_key(row: Any) -> str:
    phase = _first(row, ["phase_v2", "layer2__phase_v2", "wyckoff_phase_bucket", "wyckoff_phase", "phase"])
    momentum = _first(row, ["momentum_bucket", "layer2__momentum_bucket", "momentum_tier"])
    location = _first(row, ["location_bucket", "layer2__location_bucket", "control_state"])
    trigger = derive_trigger_state(row)
    horizon = derive_horizon_bucket(_first(row, ["horizon_bucket", "expected_move_window", "target_dte", "dte"], default=""))
    direction = derive_direction(row)
    catalyst = derive_catalyst_overlay(row)
    return "|".join([phase, momentum, location, trigger, horizon, direction, catalyst])


def is_precise_behaviour_state_key(key: str) -> bool:
    """Return True only when all seven controlled behaviour dimensions are present."""
    parts = str(key or "").split("|")
    return len(parts) == len(BEHAVIOUR_DIMS) and all(p and p != "UNK" for p in parts)


def build_behaviour_state_hash(key: str) -> str:
    return hashlib.md5(str(key).encode("utf-8")).hexdigest()[:16]


def enrich_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["catalyst_overlay"] = out.apply(derive_catalyst_overlay, axis=1)
    out["behaviour_state_key"] = out.apply(build_behaviour_state_key, axis=1)
    out["behaviour_state_hash"] = out["behaviour_state_key"].apply(build_behaviour_state_hash)
    return out


def resolve_match_type(broad_hit: bool, behaviour_hit: bool) -> tuple[str, float]:
    if broad_hit and behaviour_hit:
        return "PRECISE_MATCH", 1.0
    if broad_hit and not behaviour_hit:
        return "BROAD_ONLY_MATCH", 0.75
    if not broad_hit and behaviour_hit:
        return "BEHAVIOUR_ONLY_MATCH", 0.50
    return "NO_ACTUARIAL_MATCH", 0.0
