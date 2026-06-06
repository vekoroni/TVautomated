# ============================================================
# AVSHUNTER — actuarial_enrichment_pass.py
# Version   : v1.6.0
# Built     : 2026-05-03
# Session   : May 2026 pipeline build
# SHA256    : a7f3d2e891bc450c
# Changes   : FIX-ACB-02: macro_regime alias "regime" added; catalyst_proximity
#             normalised to NONE (cache has no FAR/WITHIN values); duplicate
#             _derive_atr_pct_bucket removed; depth-0 exact match now achievable
# ============================================================
#!/usr/bin/env python3
"""
actuarial_enrichment_pass.py
=============================
AVSHUNTER — Post-Vanguard Actuarial Enrichment Pass
Version : 1.5.0

WHY THIS EXISTS
---------------
build_packages_from_discovery.py runs BEFORE Vanguard. At that point the
STATE_COLS required for actuarial lookup are not available.
Result: every package gets state_key with empty dimensions — no_match=True.
EDE then correctly blocks every signal with LOW_EDGE (score=0.000).

FIX v1.4 (2026-04-28)
----------------------
ROOT CAUSE 4 (final): _derive_adx_bucket() returned HIGH/MEDIUM/LOW but the
actuarial cache uses STRONG/MODERATE/WEAK. Every generated key had a non-matching
adx_bucket label. Fixed by changing labels to STRONG/MODERATE/WEAK with thresholds
adx>=25=STRONG, adx>=15=MODERATE, else=WEAK. Also normalises legacy HIGH/MEDIUM/LOW
values if a pre-existing adx_bucket field is found.

With this fix the compound fallback (depth=2, drop macro_regime + wyckoff_phase_bucket)
will match NORMAL|SIDEWAYS|WEAK|MODERATE and NORMAL|SIDEWAYS|NEUTRAL|MODERATE etc.
against cache rows 135-146 which have 189k-326k observations each.

FIX v1.3 (2026-04-28)
----------------------
ROOT CAUSE 3 (final): The actuarial_cache_builder.py STATE_COLS is a 6-field
schema: vol_regime | trend_direction | structure_quality | adx_bucket |
wyckoff_phase_bucket | macro_regime. The cache was BUILT with these 6 fields.

v1.1 and v1.2 used a 4-field schema with trend_maturity (layer2__trend_maturity)
as field 3. trend_maturity does NOT exist as a cache dimension — it is a Vanguard
L2 column but was never part of STATE_COLS. The 2 missing fields produced ||| in
the key → no_match on every signal.

Fix: _VANGUARD_STATE_MAP restored to the correct 6-field schema exactly matching
STATE_COLS in actuarial_cache_builder.py. adx_bucket restored via _derive_adx_bucket().
wyckoff_phase_bucket and macro_regime read directly from the vanguard enriched CSV.
The fallback chain (drop macro first, then wyckoff) now operates correctly.

FIX v1.2 (2026-04-28)
----------------------
ROOT CAUSE 2: _load_vanguard_index searched the vanguard/ folder only.
vanguard_signals_enriched_{run_id}.csv is written by options_intelligence
into the options/ folder. Script fell through to vanguard_signals.csv
(no layer2__ cols) → still produced NORMAL|SIDEWAYS|NEUTRAL|||.
Fix: options/ folder added as first search candidate.

FIX v1.1 (2026-04-28)
----------------------
ROOT CAUSE: _VANGUARD_STATE_MAP used the WRONG 5-field schema. The actuarial
cache builder stores states as a 4-field key:

    vol_regime | trend_direction | trend_maturity | structure_quality

Confirmed from layer2__debug_signature in vanguard_signals_enriched CSV:
    NORMAL|SIDEWAYS|SIDEWAYS_BUILDING|NEUTRAL  (1,086 signals)
    NORMAL|SIDEWAYS|SIDEWAYS_BUILDING|WEAK     (  220 signals)
    NORMAL|SIDEWAYS|SIDEWAYS_RANGING|NEUTRAL   (  121 signals)
    NORMAL|SIDEWAYS|SIDEWAYS_RANGING|WEAK      (   58 signals)

The old script was building:
    NORMAL|SIDEWAYS|NEUTRAL|||  ← 3 fields + 2 empty → NO_MATCH on every signal

The fix: _VANGUARD_STATE_MAP now reads layer2__trend_maturity as field 3 and
layer2__structure_quality as field 4, matching the cache exactly. The old
wyckoff_phase, macro_regime, and adx_bucket dimensions are removed — they
are NOT part of the actuarial cache key.

THE FIX
-------
This script runs AFTER run_vanguard_from_packages.py completes.
It reads vanguard_signals_enriched_{run_id}.csv which contains all six
dimensions, performs the actuarial lookup, and patches pkg["actuarial"]
in every package JSON on disk.

PIPELINE POSITION
-----------------
    run_vanguard_from_packages.py     ← layer2__ cols now written
            ↓
    actuarial_enrichment_pass.py      ← THIS SCRIPT (Phase 8.5)
            ↓
    run_options_intelligence.py
            ↓
    superbrain
            ↓
    EIL
            ↓
    EDE  ← now receives real win_rate_10d, efficiency_10d, penalty_multiplier

DEPLOY
------
    C:\\Users\\ACKVerissimo\\AVSHUNTER-Intelligence\\scripts\\actuarial_enrichment_pass.py

ORCHESTRATOR CALL
-----------------
    from scripts.actuarial_enrichment_pass import run_actuarial_enrichment_pass
    result = run_actuarial_enrichment_pass(run_id=run_id, base_dir=cfg.BASE_DIR)
"""

from __future__ import annotations

import csv
import json
import logging
import sys
import argparse
import pandas as pd
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

log = logging.getLogger("actuarial_enrichment_pass")

# ─────────────────────────────────────────────────────────────────────────────
# PATHS
# ─────────────────────────────────────────────────────────────────────────────
HERE    = Path(__file__).resolve()
SCRIPTS = HERE.parent
REPO    = SCRIPTS.parent   # AVSHUNTER-Intelligence\
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from vanguard.core.actuarial_registry import (
    canonical_db_path,
    expected_schema_fingerprint,
    load_registry,
    schema_version as registry_schema_version,
    strict_mode as registry_strict_mode,
)
from vanguard.core.cache_integrity import validate_cache_frame
from vanguard.core.schema_contract_v6 import (
    HORIZON_FUTURE_FIELDS,
    SOURCE_MISSING,
    SOURCE_V6_DB,
)
from vanguard.core.truth_packet import apply_truth_packet, validate_truth_packet
from scripts.behaviour_state_builder import (
    build_behaviour_state_hash,
    build_behaviour_state_key,
    derive_catalyst_overlay,
    is_precise_behaviour_state_key,
    resolve_match_type,
)

# Actuarial layer lives in the separate vanguard\ directory
VANGUARD_DIR     = Path(r"C:\Users\ACKVerissimo\vanguard")
ACTUARIAL_CACHE  = VANGUARD_DIR / "data" / "actuarial_cache.parquet"
BEHAVIOUR_CACHE  = VANGUARD_DIR / "data" / "behaviour_cache.parquet"
ACTUARIAL_SCRIPT = VANGUARD_DIR / "actuarial_cache_builder.py"


# ─────────────────────────────────────────────────────────────────────────────
# LOAD ACTUARIAL MODULE
# ─────────────────────────────────────────────────────────────────────────────
_CACHE_DF        = None
_LOOKUP_FN       = None
_ACTUARIAL_READY = False
_ACTUARIAL_ERROR = ""
_SCHEMA_VERSION = ""
_SCHEMA_FINGERPRINT = ""
_CANONICAL_DB_PATH = ""
_CACHE_VALIDATION = None
_BEHAVIOUR_CACHE_HASHES = set()
_BEHAVIOUR_CACHE_ERROR = ""

# QA-FIX-1: cache schema metadata, populated at load time.
# _STATE_COLS mirrors actuarial_cache_builder.STATE_COLS for audit logging.
# _FORCE_CATALYST_NONE is set dynamically: True while cache has no real
# catalyst buckets; False once backfill adds FAR/WITHIN values.
_STATE_COLS: List[str] = []

PHASE2_LAYER2_FIELDS = [
    "layer2__state_match_method",
    "layer2__state_match_stage",
    "layer2__state_match_dimensions",
    "layer2__state_match_quality",
    "layer2__state_match_similarity",
    "layer2__state_match_is_exact",
    "layer2__sample_size",
    "layer2__sample_confidence_bucket",
    "layer2__confidence_penalty",
    "layer2__confidence_weight",
    "layer2__preferred_horizon",
    "layer2__matched_state_key",
    "layer2__original_state_key",
    "behaviour_state_key",
    "behaviour_state_hash",
    "actuarial_match_type",
    "actuarial_ev_weight",
    "catalyst_overlay",
    "layer2__fallback_reason",
    "layer2__raw_prob_up_5d",
    "layer2__raw_prob_up_10d",
    "layer2__raw_prob_up_20d",
    "layer2__raw_prob_down_5d",
    "layer2__raw_prob_down_10d",
    "layer2__raw_prob_down_20d",
    "layer2__raw_prob_target_hit",
    "layer2__raw_prob_stop_hit",
    "layer2__raw_expected_return",
    "layer2__raw_expected_drawdown",
    "layer2__raw_expected_time_to_target",
    "layer2__baseline_probability",
    "layer2__adjusted_prob_target_hit",
    "layer2__adjusted_expected_return",
    "layer2__probability_edge",
    "layer2__probability_verdict",
]
_FORCE_CATALYST_NONE   = True


def _preflight_fingerprint_check(db_path: str, registry: dict) -> bool:
    """
    Pre-flight check: confirm cache fingerprint matches registry before loading.
    Raises RuntimeWarning if mismatch. Hard raises ValueError if strict mode is on.

    NOTE: The registry fingerprint is a schema version tag stored as a metadata
    column inside actuarial_cache.parquet — not a hash of the raw DB file bytes.
    This function reads only the schema_fingerprint column (fast, single-column
    parquet read) so the mismatch is caught once at startup rather than per-ticker.
    """
    import warnings
    try:
        import pandas as _pd
        _cache = ACTUARIAL_CACHE
        if not _cache.exists():
            return True  # cache not yet built — skip, full validation will catch it
        _df = _pd.read_parquet(_cache, columns=["schema_fingerprint"])
        actual = str(_df["schema_fingerprint"].iloc[0]).strip() if len(_df) > 0 else ""
    except Exception:
        return True  # non-fatal — validate_cache_frame handles this on full load

    expected = str(
        (registry.get("canonical_database") or {}).get("expected_schema_fingerprint", "")
    )
    if not actual or not expected or actual == expected:
        return True

    msg = (
        f"Pre-flight fingerprint mismatch: "
        f"expected {expected}, got {actual}. "
        f"Update actuarial_registry.json or restore approved DB."
    )
    if registry_strict_mode() or registry.get("strict_actuarial_mode", False):
        raise ValueError(msg)
    warnings.warn(msg, RuntimeWarning)
    return False


def _load_actuarial() -> bool:
    global _CACHE_DF, _LOOKUP_FN, _ACTUARIAL_READY, _ACTUARIAL_ERROR
    global _STATE_COLS, _FORCE_CATALYST_NONE
    global _SCHEMA_VERSION, _SCHEMA_FINGERPRINT, _CANONICAL_DB_PATH, _CACHE_VALIDATION
    global _BEHAVIOUR_CACHE_HASHES, _BEHAVIOUR_CACHE_ERROR

    if _ACTUARIAL_READY:
        return True

    vanguard_str = str(VANGUARD_DIR)
    if vanguard_str not in sys.path:
        sys.path.insert(0, vanguard_str)

    try:
        import actuarial_cache_builder as _acb

        # QA-FIX-1: use getattr so a missing function produces a clean error
        # instead of AttributeError after a successful import.
        load_cache   = getattr(_acb, "load_cache",   None)
        lookup_state = getattr(_acb, "lookup_state", None)

        if load_cache is None or lookup_state is None:
            _ACTUARIAL_ERROR = "actuarial_cache_builder missing load_cache or lookup_state"
            log.warning(_ACTUARIAL_ERROR)
            return False

        # Pre-flight fingerprint check — fires once at startup before full cache load.
        # Catches registry/cache mismatch immediately rather than per-ticker (3,400+ times).
        _preflight_fingerprint_check(str(canonical_db_path(require_exists=False)), load_registry())

        _CACHE_DF = load_cache()
        if _CACHE_DF is None or len(_CACHE_DF) == 0:
            _ACTUARIAL_ERROR = "Cache empty — run actuarial_cache_builder.py first"
            return False

        _CACHE_VALIDATION = validate_cache_frame(_CACHE_DF, path=ACTUARIAL_CACHE)
        _SCHEMA_VERSION = _CACHE_VALIDATION.schema_version or registry_schema_version()
        _SCHEMA_FINGERPRINT = (
            _CACHE_VALIDATION.schema_fingerprint or expected_schema_fingerprint()
        )
        _CANONICAL_DB_PATH = str(canonical_db_path(require_exists=False))

        _LOOKUP_FN  = lookup_state
        _STATE_COLS = list(getattr(_acb, "STATE_COLS", []))

        # QA-FIX-1: only force catalyst_proximity=NONE when the loaded cache
        # genuinely has no usable catalyst categories. Some cache builds store
        # STATE_COLS only inside state_key, not as physical columns, so inspect
        # both shapes before deciding.
        _FORCE_CATALYST_NONE = True
        try:
            _cat_vals = []
            if "catalyst_proximity" in getattr(_CACHE_DF, "columns", []):
                _cat_vals = (
                    _CACHE_DF["catalyst_proximity"]
                    .dropna().astype(str).str.upper().str.strip()
                    .unique().tolist()
                )
            elif "state_key" in getattr(_CACHE_DF, "columns", []) and "catalyst_proximity" in _STATE_COLS:
                _cat_idx = _STATE_COLS.index("catalyst_proximity")
                _cat_vals = sorted({
                    str(parts[_cat_idx]).upper().strip()
                    for parts in _CACHE_DF["state_key"].dropna().astype(str).str.split("|")
                    if len(parts) > _cat_idx
                })
            _non_none = [v for v in _cat_vals if v not in ("", "NONE", "NAN", "NULL", "DATA_WEAK")]
            _FORCE_CATALYST_NONE = len(_non_none) == 0
        except Exception:
            _FORCE_CATALYST_NONE = True

        _BEHAVIOUR_CACHE_HASHES = set()
        _BEHAVIOUR_CACHE_ERROR = ""
        try:
            if BEHAVIOUR_CACHE.exists():
                _behaviour_df = pd.read_parquet(BEHAVIOUR_CACHE)
                if "behaviour_state_hash" in _behaviour_df.columns:
                    _BEHAVIOUR_CACHE_HASHES = set(
                        _behaviour_df["behaviour_state_hash"].dropna().astype(str).str.strip()
                    )
                    log.info(
                        "Behaviour-state cache loaded - %d hashes from %s",
                        len(_BEHAVIOUR_CACHE_HASHES),
                        BEHAVIOUR_CACHE,
                    )
                else:
                    _BEHAVIOUR_CACHE_ERROR = "behaviour_cache.parquet missing behaviour_state_hash"
                    log.warning(_BEHAVIOUR_CACHE_ERROR)
            else:
                log.info("Behaviour-state cache not present - broad actuarial matches remain discounted")
        except Exception as _behaviour_err:
            _BEHAVIOUR_CACHE_ERROR = str(_behaviour_err)
            log.warning("Behaviour-state cache load failed: %s", _BEHAVIOUR_CACHE_ERROR)

        _ACTUARIAL_READY = True
        log.info("Actuarial cache loaded — %d states", len(_CACHE_DF))
        if _STATE_COLS:
            log.info("Actuarial cache STATE_COLS: %s", " | ".join(_STATE_COLS))
        log.info(
            "Actuarial v6 schema: version=%s fingerprint=%s",
            _SCHEMA_VERSION,
            _SCHEMA_FINGERPRINT,
        )
        log.info(
            "Catalyst proximity handling: %s",
            "FORCED_NONE (cache has no real catalyst buckets)"
            if _FORCE_CATALYST_NONE else
            "USE_VANGUARD_VALUE (cache has real catalyst data)",
        )
        return True

    except ImportError as e:
        _ACTUARIAL_ERROR = f"actuarial_cache_builder not importable: {e}"
        log.warning(_ACTUARIAL_ERROR)
        return False
    except Exception as e:
        _ACTUARIAL_ERROR = str(e)
        log.warning("Actuarial cache load failed: %s", e)
        return False


# ─────────────────────────────────────────────────────────────────────────────
# STATE DIMENSION DERIVATION FROM VANGUARD ROW
# ─────────────────────────────────────────────────────────────────────────────

# v1.1: Exact column names confirmed from vanguard_signals_enriched CSV analysis.
# Actuarial cache key is 4 fields: layer2__debug_signature confirms format:
#   layer2__vol_regime | layer2__trend_direction | layer2__trend_maturity | layer2__structure_quality
# Example: NORMAL|SIDEWAYS|SIDEWAYS_BUILDING|NEUTRAL
# Old 5-field schema (wyckoff_phase, macro_regime, adx_bucket) is REMOVED.

# ── v1.5 FIX: State key must match actuarial_cache_builder.py STATE_COLS exactly ─
# ACB-01 extended STATE_COLS from 6 to 9 fields (May 2026).
# actuarial_cache_builder.py STATE_COLS (9 fields, this order):
#   vol_regime | trend_direction | structure_quality | adx_bucket |
#   wyckoff_phase_bucket | macro_regime |
#   trend_maturity | catalyst_proximity | atr_pct_bucket
#
# The cache was REBUILT with all 9 fields. lookup_state() joins them in this
# order. We must pass all 9 so lookup_state() produces a matchable key.
# Fields 7-9 are the new ACB-01 additions; without them the key ends with
# "||| which never matches any cache entry.
#
# FALLBACK_DROP_SEQUENCE drops catalyst_proximity first, then atr_pct_bucket,
# then trend_maturity before touching the core 6 — so partial data is handled.
_VANGUARD_STATE_MAP = {
    "vol_regime": [
        "layer2__vol_regime",        # NORMAL | EXPANSION | COMPRESSION
        "vol_regime",
    ],
    "trend_direction": [
        "layer2__trend_direction",   # SIDEWAYS | UP | DOWN
        "dominant_trend",
        "trend_direction",
    ],
    "structure_quality": [
        "layer2__structure_quality", # NEUTRAL | WEAK | STRONG
        "structure_quality",
    ],
    "adx_bucket": [
        # adx_bucket is derived from adx_14 — handled by _derive_adx_bucket()
        # This entry is a placeholder; adx_bucket is always set via
        # _derive_adx_bucket() in _derive_state_from_vanguard_row().
        "__adx_derived__",           # sentinel — never matched, derived separately
    ],
    "wyckoff_phase_bucket": [
        "wyckoff_phase_bucket",      # ACCUMULATION | MARKUP | DISTRIBUTION | MARKDOWN
        "current_phase",
        "phase",
    ],
    "macro_regime": [
        "macro_regime",              # TRANSITIONAL | RISK_ON | RISK_OFF
        "active_regime",
        "regime_state",
        "regime",                    # FIX-ACB-02: vanguard_signals writes "regime" not "macro_regime"
    ],
    # ── ACB-01: Three new dimensions added to STATE_COLS (May 2026) ──────────
    # These were the source of the trailing ||| that caused all state misses.
    "trend_maturity": [
        "trend_maturity",            # EARLY | MIDDLE | LATE | EXHAUSTED |
        "layer2__trend_maturity",    # SIDEWAYS_BUILDING | SIDEWAYS_RANGING
        "trend_mat",
    ],
    "catalyst_proximity": [
        # QA-FIX-2: real column aliases. When _FORCE_CATALYST_NONE=True (cache
        # has no real catalyst buckets), _derive_state_from_vanguard_row() forces
        # NONE regardless of what these aliases resolve to. Once the DB is
        # backfilled, _FORCE_CATALYST_NONE becomes False and the real value is used.
        "catalyst_proximity",
        "earnings_proximity",
        "days_to_earnings_bucket",
        "event_proximity",
    ],
    "atr_pct_bucket": [
        # atr_pct_bucket derived from atr_pct — handled by _derive_atr_pct_bucket()
        "__atr_pct_derived__",       # sentinel — never matched, derived separately
    ],
}


def _derive_adx_bucket(row: Dict[str, Any]) -> str:
    """
    Derive adx_bucket from raw adx_14 value.

    v1.4 FIX: Labels must match actuarial_cache_builder.py exactly.
    Cache uses STRONG|MODERATE|WEAK — NOT HIGH|MEDIUM|LOW.
    Thresholds confirmed from cache STATE_COLS documentation:
        adx_14 >= 25 → STRONG   (strong trend)
        adx_14 >= 15 → MODERATE (moderate trend)
        adx_14 <  15 → WEAK     (weak/no trend)

    Falls back to any pre-existing adx_bucket field if already bucketed.
    """
    # Check for pre-existing bucket first (already in cache label format)
    for k in ("adx_bucket", "adx_tier", "adx_band"):
        v = str(row.get(k) or "").strip().upper()
        if v and v not in ("", "NAN", "NONE"):
            # Normalise any legacy HIGH/MEDIUM/LOW labels
            if v == "HIGH":   return "STRONG"
            if v == "MEDIUM": return "MODERATE"
            if v == "LOW":    return "WEAK"
            return v

    # Derive from raw adx_14 using STRONG/MODERATE/WEAK labels
    for k in ("adx_14", "adx", "ADX_14"):
        v = row.get(k)
        if v is not None:
            try:
                adx = float(v)
                if adx >= 25:
                    return "STRONG"
                elif adx >= 15:
                    return "MODERATE"
                else:
                    return "WEAK"
            except (TypeError, ValueError):
                pass
    return ""


def _derive_atr_pct_bucket(row: Dict[str, Any]) -> str:
    """
    Derive atr_pct_bucket from raw atr_pct value.

    ACB-01 thresholds (matching actuarial_cache_builder.py exactly):
        atr_pct >= 4.0  → HIGH   (volatile, wide-ranging)
        atr_pct >= 2.0  → MID    (moderate volatility)
        atr_pct <  2.0  → LOW    (compressed, tight-ranging)

    QA-FIX-3: Preserve valid zero values. The old `a or b or c` chain treated
    numeric 0 as missing and incorrectly returned MID instead of LOW.
    A ticker with atr_pct=0 is a genuine low-volatility state.
    """
    raw = None
    for key in ("atr_pct", "atr_14_pct", "atr_pct_raw"):
        if key in row and row.get(key) not in (None, "", "nan", "NaN", "N/A", "NONE"):
            raw = row.get(key)
            break

    try:
        v = float(str(raw).strip())
        if v >= 4.0:
            return "HIGH"
        if v >= 2.0:
            return "MID"
        return "LOW"
    except (ValueError, TypeError, AttributeError):
        return "MID"   # fallback — neutral bucket when field genuinely absent


def _derive_state_from_vanguard_row(row: Dict[str, Any]) -> Dict[str, str]:
    """
    Extract all 9 STATE_COLS from a vanguard enriched row, matching
    actuarial_cache_builder.py STATE_COLS exactly (ACB-01, May 2026):

        vol_regime | trend_direction | structure_quality | adx_bucket |
        wyckoff_phase_bucket | macro_regime |
        trend_maturity | catalyst_proximity | atr_pct_bucket

    Fields 7-9 (trend_maturity, catalyst_proximity, atr_pct_bucket) were
    added in ACB-01. Without them the key ends with ||| and misses every
    cache entry — this was the root cause of the mass no_match warnings.

    adx_bucket derived from raw adx_14 via _derive_adx_bucket().
    atr_pct_bucket derived from raw atr_pct via _derive_atr_pct_bucket().
    All other fields read directly from layer2__ or discovery columns.
    """
    state: Dict[str, str] = {}

    for state_col, aliases in _VANGUARD_STATE_MAP.items():
        if aliases[0] in ("__adx_derived__", "__atr_pct_derived__"):
            # Derived fields — skip alias lookup, populated below
            state[state_col] = ""
            continue
        if state_col == "catalyst_proximity" and _FORCE_CATALYST_NONE:
            # QA-FIX-2: Force NONE only when cache metadata confirms catalyst
            # categories are unavailable. Once the cache has real catalyst
            # buckets, _FORCE_CATALYST_NONE becomes False and the real
            # Vanguard row value is used — no code change required.
            state[state_col] = "NONE"
            continue
        val = ""
        for alias in aliases:
            v = str(row.get(alias) or "").strip()
            if v and v.lower() not in ("nan", "none", ""):
                val = v.upper()
                break
        state[state_col] = val

    # Derive adx_bucket and atr_pct_bucket from raw numeric columns
    state["adx_bucket"]     = _derive_adx_bucket(row)
    state["atr_pct_bucket"] = _derive_atr_pct_bucket(row)

    return state


# ─────────────────────────────────────────────────────────────────────────────
# ACTUARIAL LOOKUP → PACKAGE PATCH DICT
# ─────────────────────────────────────────────────────────────────────────────

def _result_get(result: Any, key: str, default: Any = None) -> Any:
    """
    QA-FIX-4: Read lookup_state() result safely whether it is a
    dataclass/NamedTuple (attribute access) or a dict (key access).
    Protects the enrichment pass from actuarial_cache_builder API drift
    — if the cache builder switches from a dataclass to a plain dict
    return, this function handles both without crashing.
    """
    if isinstance(result, dict):
        return result.get(key, default)
    return getattr(result, key, default)


_HORIZON_FIELD_ALIASES = {
    "future_path_label": (
        "future_path_label",
        "layer2__future_path_label",
        "layer2__outcomes__future_path_label",
        "outcome_category",
        "layer2__outcome_category",
        "layer2__outcomes__outcome_category",
    ),
}


def _has_committed_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip().lower() not in {"", "nan", "none", "null", "n/a"}
    return True


def _aliases_for_horizon_field(field: str) -> Tuple[str, ...]:
    return _HORIZON_FIELD_ALIASES.get(
        field,
        (
            field,
            f"layer2__{field}",
            f"layer2__outcomes__{field}",
            f"outcomes__{field}",
        ),
    )


def _preserve_horizon_future_fields(
    block: Dict[str, Any],
    *,
    vanguard_row: Optional[Dict[str, Any]],
    existing_actuarial: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Retain vital horizon/future fields captured upstream.

    Phase 1 is a governance lock, not an EV rewrite. If a future/horizon field
    is already present on the existing package actuarial block or arrives from
    the Vanguard row, carry it forward instead of letting the package write
    forget it.
    """
    out = dict(block)
    sources = [existing_actuarial or {}, vanguard_row or {}]

    for field in HORIZON_FUTURE_FIELDS:
        if _has_committed_value(out.get(field)):
            continue
        for source in sources:
            for alias in _aliases_for_horizon_field(field):
                if alias in source and _has_committed_value(source.get(alias)):
                    out[field] = source.get(alias)
                    break
            if _has_committed_value(out.get(field)):
                break

    return out


def _preserve_phase2_baton_fields(
    block: Dict[str, Any],
    *,
    vanguard_row: Optional[Dict[str, Any]],
    existing_actuarial: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Carry Phase 2 layer2__ baton keys into pkg["actuarial"]."""
    def _has_phase2_value(value: Any) -> bool:
        if value is None:
            return False
        if isinstance(value, str):
            return value.strip().lower() not in {"", "nan", "null", "n/a"}
        return True

    out = dict(block)
    existing = existing_actuarial or {}
    baton: Dict[str, Any] = dict(existing.get("phase2_baton") or {})

    for field in PHASE2_LAYER2_FIELDS:
        value = None
        if vanguard_row and _has_phase2_value(vanguard_row.get(field)):
            value = vanguard_row.get(field)
        elif _has_phase2_value(existing.get(field)):
            value = existing.get(field)
        elif _has_phase2_value(baton.get(field)):
            value = baton.get(field)

        if _has_phase2_value(value):
            out[field] = value
            baton[field] = value

    missing = [field for field in PHASE2_LAYER2_FIELDS if not _has_phase2_value(out.get(field))]
    out["phase2_baton"] = baton
    out["phase2_baton_status"] = "VALID" if not missing else "MISSING_FIELDS"
    out["phase2_baton_missing_fields"] = missing
    return out


def _build_actuarial_block(state: Dict[str, str]) -> Dict[str, Any]:
    """
    Perform actuarial cache lookup and return the full actuarial block
    ready to be written into pkg["actuarial"].

    QA-FIX-4: Uses _result_get() throughout — safe for both dataclass
    and dict return shapes from lookup_state().
    """
    if not _ACTUARIAL_READY or _CACHE_DF is None or _LOOKUP_FN is None:
        return apply_truth_packet({
            "available": False,
            "actuarial_source": SOURCE_MISSING,
            "schema_version": _SCHEMA_VERSION,
            "schema_fingerprint": _SCHEMA_FINGERPRINT,
            "canonical_database_path": _CANONICAL_DB_PATH,
            "reason": _ACTUARIAL_ERROR or "Cache not loaded",
            "actuarial_live_blend_weight": 0.0,
            "actuarial_live_data_quality": "NONE",
            "actuarial_live_overlay_applied": False,
        })

    try:
        result = _LOOKUP_FN(state, _CACHE_DF)
        no_match = bool(_result_get(result, "no_match", True))
        block = {
            "available":             True,
            "actuarial_source":      SOURCE_MISSING if no_match else SOURCE_V6_DB,
            "schema_version":        _SCHEMA_VERSION,
            "schema_fingerprint":    _SCHEMA_FINGERPRINT,
            "canonical_database_path": _CANONICAL_DB_PATH,
            "state_key":             _result_get(result, "state_key",             ""),
            "matched_key":           _result_get(result, "matched_key",           ""),
            "fallback_depth":        _result_get(result, "fallback_depth",        0),
            "fallback_dims_dropped": _result_get(result, "fallback_dims_dropped", []),
            "sample_size":           _result_get(result, "sample_size",           0),
            "valid":                 _result_get(result, "valid",                 False),
            "no_match":              no_match,
            "penalty_multiplier":    _result_get(result, "penalty_multiplier",    1.0),
            "expected_move_5d":      _result_get(result, "expected_move_5d",      0.0),
            "expected_move_10d":     _result_get(result, "expected_move_10d",     0.0),
            "expected_move_20d":     _result_get(result, "expected_move_20d",     0.0),
            "win_rate_5d":           _result_get(result, "win_rate_5d",           0.0),
            "win_rate_10d":          _result_get(result, "win_rate_10d",          0.0),
            "win_rate_20d":          _result_get(result, "win_rate_20d",          0.0),
            "risk_10d":              _result_get(result, "risk_10d",              0.0),
            "efficiency_10d":        _result_get(result, "efficiency_10d",        0.0),
            "vol_10d":               _result_get(result, "vol_10d",               0.0),
            "avg_days_to_10pct":     _result_get(result, "avg_days_to_10pct",     None),
            "state_used":            state,
            "cache_built_at":        _result_get(result, "cache_built_at",        ""),
            "cache_state_cols":      _STATE_COLS,     # QA-FIX-4: audit field
            "actuarial_live_blend_weight": 0.0,
            "actuarial_live_data_quality": "NONE",
            "actuarial_live_overlay_applied": False,
            "enriched_by":           "actuarial_enrichment_pass",
            "enriched_at":           datetime.now(timezone.utc).isoformat(),
        }
        block = apply_truth_packet(block)
        validate_truth_packet(block)
        return block
    except Exception as e:
        log.debug("Actuarial lookup failed for state %s: %s", state, e)
        block = {
            "available":       False,
            "actuarial_source": SOURCE_MISSING,
            "schema_version": _SCHEMA_VERSION,
            "schema_fingerprint": _SCHEMA_FINGERPRINT,
            "canonical_database_path": _CANONICAL_DB_PATH,
            "reason":          f"lookup_error: {e}",
            "state_used":      state,
            "actuarial_live_blend_weight": 0.0,
            "actuarial_live_data_quality": "NONE",
            "actuarial_live_overlay_applied": False,
            "cache_state_cols": _STATE_COLS,
        }
        return apply_truth_packet(block)


# ─────────────────────────────────────────────────────────────────────────────
# VANGUARD CSV LOADER
# ─────────────────────────────────────────────────────────────────────────────

def _load_vanguard_index(run_dir: Path, run_id: str) -> Dict[str, Dict[str, Any]]:
    """
    Load vanguard_signals_enriched_{run_id}.csv into a ticker-keyed dict.
    Falls back to vanguard_signals.csv if enriched version not found.
    """
    # v1.2: vanguard_signals_enriched is written by options_intelligence into
    # the options/ folder, not the vanguard/ folder. Search order:
    #   1. optionsanguard_signals_enriched_{run_id}.csv  ← actual location
    #   2. vanguardanguard_signals_enriched_{run_id}.csv ← legacy location
    #   3. optionsanguard_signals_enriched.csv           ← unnested fallback
    #   4. vanguardanguard_signals_enriched.csv          ← legacy fallback
    #   5. vanguardanguard_signals.csv                   ← last resort (NO layer2__ cols)
    candidates = [
        run_dir / "options" / f"vanguard_signals_enriched_{run_id}.csv",
        run_dir / "vanguard" / f"vanguard_signals_enriched_{run_id}.csv",
        run_dir / "options" / "vanguard_signals_enriched.csv",
        run_dir / "vanguard" / "vanguard_signals_enriched.csv",
        run_dir / "vanguard" / "vanguard_signals.csv",
    ]

    for path in candidates:
        if path.exists() and path.stat().st_size > 500:
            index: Dict[str, Dict[str, Any]] = {}
            try:
                with path.open("r", encoding="utf-8-sig", newline="") as f:
                    for row in csv.DictReader(f):
                        t = str(row.get("ticker") or "").strip().upper()
                        if t:
                            index[t] = {
                                k: v.strip() if isinstance(v, str) else v
                                for k, v in row.items()
                            }
                if index:
                    log.info(
                        "Vanguard index loaded: %s (%d tickers)",
                        path.name, len(index),
                    )
                    return index
            except Exception as e:
                log.warning("Failed to load %s: %s", path.name, e)

    log.warning("No vanguard signals CSV found for run %s", run_id)
    return {}


# ─────────────────────────────────────────────────────────────────────────────
# PACKAGE PATCHER
# ─────────────────────────────────────────────────────────────────────────────

def _patch_package(
    pkg_path: Path,
    vanguard_row: Optional[Dict[str, Any]],
) -> Tuple[str, str]:
    """
    Read one package JSON, derive actuarial state from vanguard row,
    perform lookup, write patched pkg["actuarial"] back to disk.

    Returns (ticker, outcome) where outcome is one of:
        EXACT_MATCH | FALLBACK_MATCH | NO_MATCH | NO_VANGUARD_ROW | ERROR
    """
    try:
        with pkg_path.open("r", encoding="utf-8") as f:
            pkg = json.load(f)
    except Exception as e:
        return (pkg_path.stem.replace(".package", ""), f"ERROR_READ:{e}")

    ticker = str(pkg.get("ticker") or "").upper()

    if vanguard_row is None:
        # No vanguard data for this ticker — preserve existing actuarial block
        # but stamp enrichment_pass_attempted so we know it was checked
        act = pkg.get("actuarial") or {}
        if not isinstance(act, dict):
            act = {}
        if isinstance(act, dict):
            act.setdefault("actuarial_source", SOURCE_MISSING)
            act.setdefault("schema_version", _SCHEMA_VERSION)
            act.setdefault("schema_fingerprint", _SCHEMA_FINGERPRINT)
            act.setdefault("canonical_database_path", _CANONICAL_DB_PATH)
            if act.get("truth_packet_id"):
                validate_truth_packet(act)
            act = apply_truth_packet(act)
            validate_truth_packet(act)
        act["enrichment_pass_attempted"] = True
        act["enrichment_pass_result"]    = "NO_VANGUARD_ROW"
        pkg["actuarial"] = act
        try:
            with pkg_path.open("w", encoding="utf-8") as f:
                json.dump(pkg, f, indent=2, ensure_ascii=False)
        except Exception:
            pass
        return (ticker, "NO_VANGUARD_ROW")

    # Derive state from vanguard row
    state = _derive_state_from_vanguard_row(vanguard_row)

    # ACB-01 v1.5: Validate all 9 STATE_COLS — log if any dimension empty
    _state_key_preview = "|".join(state.get(d, "") for d in [
        "vol_regime", "trend_direction", "structure_quality",
        "adx_bucket", "wyckoff_phase_bucket", "macro_regime",
        "trend_maturity", "catalyst_proximity", "atr_pct_bucket",
    ])
    if any(v == "" for v in state.values()):
        log.debug(
            "Incomplete state key for %s: %s (empty dims: %s)",
            ticker, _state_key_preview,
            [k for k, v in state.items() if v == ""],
        )
    else:
        log.debug("State key for %s: %s", ticker, _state_key_preview)

    # Sprint A/B: precise behaviour-state identity rides beside broad actuarial state.
    behaviour_state_key = build_behaviour_state_key(vanguard_row)
    behaviour_state_hash = build_behaviour_state_hash(behaviour_state_key)
    catalyst_overlay = derive_catalyst_overlay(vanguard_row)

    # Perform actuarial lookup
    actuarial_block = _build_actuarial_block(state)

    broad_hit = bool(actuarial_block.get("available")) and not bool(actuarial_block.get("no_match"))
    # Behaviour cache is optional; when absent, broad actuarial matches remain
    # explicitly discounted instead of pretending precision exists.
    behaviour_hit = bool(
        behaviour_state_hash
        and is_precise_behaviour_state_key(behaviour_state_key)
        and behaviour_state_hash in _BEHAVIOUR_CACHE_HASHES
    )
    actuarial_match_type, actuarial_ev_weight = resolve_match_type(broad_hit, behaviour_hit)
    actuarial_block.update({
        "behaviour_state_key": behaviour_state_key,
        "behaviour_state_hash": behaviour_state_hash,
        "catalyst_overlay": catalyst_overlay,
        "actuarial_match_type": actuarial_match_type,
        "actuarial_ev_weight": actuarial_ev_weight,
    })

    # Retain existing useful fields by default; the fresh lookup owns core
    # match metrics and v6 truth metadata.
    existing_act = pkg.get("actuarial") or {}
    if isinstance(existing_act, dict):
        merged_act = dict(existing_act)
        merged_act.update(actuarial_block)
        actuarial_block = merged_act
        actuarial_block = _preserve_horizon_future_fields(
            actuarial_block,
            vanguard_row=vanguard_row,
            existing_actuarial=existing_act,
        )
        actuarial_block = _preserve_phase2_baton_fields(
            actuarial_block,
            vanguard_row=vanguard_row,
            existing_actuarial=existing_act,
        )
        validate_truth_packet(actuarial_block)

    pkg["actuarial"] = actuarial_block

    # Determine outcome for reporting
    if not actuarial_block.get("available"):
        outcome = "LOOKUP_FAILED"
    elif actuarial_block.get("no_match"):
        outcome = "NO_MATCH"
    elif actuarial_block.get("fallback_depth", 0) > 0:
        outcome = "FALLBACK_MATCH"
    else:
        outcome = "EXACT_MATCH"

    try:
        with pkg_path.open("w", encoding="utf-8") as f:
            json.dump(pkg, f, indent=2, ensure_ascii=False)
    except Exception as e:
        return (ticker, f"ERROR_WRITE:{e}")

    return (ticker, outcome)


# ─────────────────────────────────────────────────────────────────────────────
# MAIN ENRICHMENT PASS
# ─────────────────────────────────────────────────────────────────────────────

def run_actuarial_enrichment_pass(
    run_id: str,
    base_dir: Path,
) -> Dict[str, Any]:
    """
    Called by intelligent_orchestrator.py Phase 8.5 — after Vanguard,
    before Options Intelligence.

    Reads  : data/output/runs/{run_id}/vanguard/vanguard_signals_enriched_{run_id}.csv
    Patches: data/output/runs/{run_id}/packages/*.package.json
    Returns: summary dict the orchestrator can log/gate on
    """
    run_dir  = base_dir / "data" / "output" / "runs" / run_id
    pkg_dir  = run_dir / "packages"
    index_path = pkg_dir / "index.json"

    if not pkg_dir.exists():
        return {"success": False, "reason": f"packages dir not found: {pkg_dir}"}

    if not index_path.exists():
        return {"success": False, "reason": f"index.json not found: {index_path}"}

    # Load actuarial cache
    if not _load_actuarial():
        return {
            "success": False,
            "reason": f"Actuarial cache unavailable: {_ACTUARIAL_ERROR}",
        }

    # Load vanguard signals index
    vanguard_index = _load_vanguard_index(run_dir, run_id)
    if not vanguard_index:
        return {
            "success": False,
            "reason": "Vanguard signals CSV not found — run Vanguard first",
        }

    # Load package index for the list of built packages
    with index_path.open("r", encoding="utf-8") as f:
        index = json.load(f)

    packages = [p for p in index.get("packages", []) if p.get("status") == "BUILT"]

    if not packages:
        return {"success": False, "reason": "No BUILT packages in index.json"}

    # Process each package
    outcomes: Dict[str, int] = {
        "EXACT_MATCH":    0,
        "FALLBACK_MATCH": 0,
        "NO_MATCH":       0,
        "NO_VANGUARD_ROW":0,
        "LOOKUP_FAILED":  0,
        "ERROR_READ":     0,
        "ERROR_WRITE":    0,
    }

    # QA-FIX-5: track real patched count vs theoretical package count.
    # Old code reported len(packages) even when package files were missing.
    patched_count        = 0
    missing_package_files = 0

    for rec in packages:
        ticker    = str(rec.get("ticker") or "").upper()
        pkg_path  = rec.get("package_path")

        if not pkg_path:
            continue

        p = Path(pkg_path)
        if not p.is_absolute():
            p = (base_dir / p).resolve()

        if not p.exists():
            log.debug("Package not found: %s", p)
            missing_package_files += 1
            continue

        vg_row = vanguard_index.get(ticker)
        _, outcome = _patch_package(p, vg_row)
        patched_count += 1

        # Prefix-safe bucket — _patch_package may return ERROR_READ:<msg>
        matched_key = next(
            (k for k in outcomes if outcome.startswith(k)), "LOOKUP_FAILED"
        )
        outcomes[matched_key] = outcomes.get(matched_key, 0) + 1

    # Update index.json with enrichment pass summary
    _usable    = outcomes["EXACT_MATCH"] + outcomes["FALLBACK_MATCH"]
    _match_rate = _usable / patched_count if patched_count else 0.0

    index["actuarial_enrichment_pass"] = {
        "run_at":                datetime.now(timezone.utc).isoformat(),
        "vanguard_tickers":      len(vanguard_index),
        "packages_expected":     len(packages),
        "packages_patched":      patched_count,
        "missing_package_files": missing_package_files,
        "outcomes":              outcomes,
        "usable_matches":        _usable,
        "match_rate":            round(_match_rate, 4),
        "cache_states":          len(_CACHE_DF) if _CACHE_DF is not None else 0,
        "cache_state_cols":      _STATE_COLS,
        "schema_version":        _SCHEMA_VERSION,
        "schema_fingerprint":    _SCHEMA_FINGERPRINT,
        "canonical_database_path": _CANONICAL_DB_PATH,
        "cache_validation":      _CACHE_VALIDATION.to_dict() if _CACHE_VALIDATION else None,
        "force_catalyst_none":   _FORCE_CATALYST_NONE,
    }
    with index_path.open("w", encoding="utf-8") as f:
        json.dump(index, f, indent=2, ensure_ascii=False)

    log.info(
        "Actuarial enrichment pass complete — "
        "patched=%d/%d exact=%d fallback=%d no_match=%d no_vanguard=%d match_rate=%.1f%%",
        patched_count,
        len(packages),
        outcomes["EXACT_MATCH"],
        outcomes["FALLBACK_MATCH"],
        outcomes["NO_MATCH"],
        outcomes["NO_VANGUARD_ROW"],
        _match_rate * 100,
    )

    return {
        "success":               True,
        "packages_expected":     len(packages),
        "packages_patched":      patched_count,
        "missing_package_files": missing_package_files,
        "outcomes":              outcomes,
        "usable_matches":        _usable,
        "match_rate":            round(_match_rate, 4),
        "cache_states":          len(_CACHE_DF) if _CACHE_DF is not None else 0,
        "cache_state_cols":      _STATE_COLS,
        "schema_version":        _SCHEMA_VERSION,
        "schema_fingerprint":    _SCHEMA_FINGERPRINT,
        "canonical_database_path": _CANONICAL_DB_PATH,
        "force_catalyst_none":   _FORCE_CATALYST_NONE,
    }


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def _setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [ACTUARIAL_PASS] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[logging.StreamHandler(sys.stdout)],
    )


def main() -> int:
    _setup_logging()
    ap = argparse.ArgumentParser(
        description="AVSHUNTER Post-Vanguard Actuarial Enrichment Pass"
    )
    ap.add_argument("--run-id",   required=True, help="Run ID e.g. 20260424_090026")
    ap.add_argument("--base-dir", default=str(REPO), help="AVSHUNTER-Intelligence root dir")
    args = ap.parse_args()

    result = run_actuarial_enrichment_pass(
        run_id   = args.run_id,
        base_dir = Path(args.base_dir).resolve(),
    )

    if not result.get("success"):
        log.error("FAILED: %s", result.get("reason"))
        return 1

    o = result["outcomes"]
    print(f"\n=== ACTUARIAL ENRICHMENT PASS COMPLETE ===")
    print(f"  Packages expected : {result.get('packages_expected', result.get('packages_patched', 0))}")
    print(f"  Packages patched  : {result['packages_patched']}")
    print(f"  Missing packages  : {result.get('missing_package_files', 0)}")
    print(f"  Cache states      : {result['cache_states']}")
    print(f"  Cache STATE_COLS  : {' | '.join(result.get('cache_state_cols', []))}")
    print(f"  Force catalyst    : {result.get('force_catalyst_none', True)}")
    print(f"  Exact match       : {o['EXACT_MATCH']}")
    print(f"  Fallback match    : {o['FALLBACK_MATCH']}")
    print(f"  No match          : {o['NO_MATCH']}")
    print(f"  No vanguard row   : {o['NO_VANGUARD_ROW']}")
    print(f"  Match rate        : {result.get('match_rate', 0.0) * 100:.1f}%")
    return 0


if __name__ == "__main__":
    sys.exit(main())
