"""Deterministic direction governance for the AVSHUNTER long-option pipeline.

The module deliberately contains no predictive model.  It turns structural
direction and independently-produced evidence into an auditable record that
every downstream stage can validate.  Generated targets, selected contracts,
Discovery defaults and other direction-dependent outputs are never admitted as
resolution evidence.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

from domain.thesis_direction import (
    normalise_direction,
    resolve_structural_direction,
)


DIR_CALC_VERSION = "dir_v1.3.0"
RESOLUTION_POLICY_VERSION = "thesis_direction_v1.0.0"
LEGACY_DIR_CALC_VERSION = "dir_v1.2.0"
LEGACY_RESOLUTION_POLICY_VERSION = "strangle_resolution_v1.1.0"
GDR_SCHEMA_VERSION = "governed_direction_record_v1"

CALL = "CALL"
PUT = "PUT"
STRANGLE = "STRANGLE"
UNRESOLVED = "UNRESOLVED"
DIRECTED = {CALL, PUT}
NON_DIRECTIONAL = {STRANGLE, UNRESOLVED}

MIN_EVIDENCE_FAMILIES = 2
MIN_WINNING_SHARE = 0.60
MIN_DIRECTION_MARGIN = 0.20

EXCLUDED_DIRECTION_EVIDENCE = [
    "discovery_direction_preliminary",
    "footprint_direction",
    "generated_target",
    "selected_contract_side",
    "catalyst_direction_without_independent_provenance",
]


def _text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return "" if text.upper() in {"", "NAN", "NONE", "NULL", "N/A"} else text


def _upper(value: Any) -> str:
    return _text(value).upper()


def _number(value: Any) -> Optional[float]:
    try:
        result = float(value)
        return None if result != result else result
    except (TypeError, ValueError):
        return None


def _truthy(value: Any) -> bool:
    return _upper(value) in {"1", "TRUE", "YES", "Y", "ON"}


def normalise_side(value: Any) -> str:
    return normalise_direction(value, strangle_for_non_directional=True)


def structural_direction(precor_intent: Any, trend: Any) -> Tuple[str, str]:
    """Closed, fail-closed structural direction table."""
    return resolve_structural_direction(
        precor_intent,
        trend,
        strangle_for_non_directional=True,
    )


@dataclass(frozen=True)
class SideStructuralEvidence:
    """Per-side C3 observations; no instrument, macro or geometry authority."""

    event_confirmed: bool = False
    event_strength: Optional[float] = None
    control_score: Optional[float] = None
    intent_supported: bool = False
    mode_known: bool = False
    intent_transition: bool = False
    trend_aligned: bool = False
    trend_history_bars: Optional[int] = None
    observation_quality: Optional[float] = None
    event_as_of_session: str = ""
    control_as_of_session: str = ""
    intent_as_of_session: str = ""

    def __post_init__(self) -> None:
        for name in ("event_strength", "control_score", "observation_quality"):
            value = getattr(self, name)
            if value is not None and (not math.isfinite(value) or not 0 <= value <= 1):
                raise ValueError(f"{name} must be a measured 0–1 value or absent")
        if self.trend_history_bars is not None and self.trend_history_bars < 0:
            raise ValueError("trend_history_bars cannot be negative")


@dataclass(frozen=True)
class SideAssignmentPolicy:
    """Explicit, versioned parameters; no unrecorded production defaults."""

    version: str
    event_strength_min: float
    control_margin_min: float
    control_full_scale: float
    contested_margin: float
    min_observation_quality: float
    trend_min_bars: int

    def __post_init__(self) -> None:
        if not self.version:
            raise ValueError("A side-assignment policy version is required")
        for name in ("event_strength_min", "control_margin_min", "contested_margin", "min_observation_quality"):
            value = getattr(self, name)
            if value is None or not math.isfinite(value) or not 0 <= value <= 1:
                raise ValueError(f"Invalid side-assignment policy {name}")
        if self.control_full_scale is None or not math.isfinite(self.control_full_scale) or self.control_full_scale <= 0:
            raise ValueError("Invalid side-assignment control scale")
        if self.trend_min_bars is None or self.trend_min_bars < 1:
            raise ValueError("Invalid side-assignment trend history floor")


def assign_thesis_side(
    bull: SideStructuralEvidence,
    bear: SideStructuralEvidence,
    policy: SideAssignmentPolicy,
) -> Dict[str, Any]:
    """Assign a descriptive ticker side from structure, never from geometry or trend alone.

    The policy must be supplied by a versioned configuration owner. This pure
    boundary is not wired to production routing until its values and historical
    outcome behaviour meet DIR-002 R-2–R-5.
    """
    if not isinstance(bull, SideStructuralEvidence) or not isinstance(bear, SideStructuralEvidence):
        raise TypeError("Both per-side structural evidence vectors are required")
    if not isinstance(policy, SideAssignmentPolicy):
        raise TypeError("A versioned side-assignment policy is required")

    control_delta = None
    if bull.control_score is not None and bear.control_score is not None:
        control_delta = bull.control_score - bear.control_score

    def support(vector: SideStructuralEvidence, delta: Optional[float]) -> Tuple[List[str], Optional[float]]:
        observations: List[float] = []
        kinds: List[str] = []
        if vector.event_confirmed and vector.event_strength is not None and vector.event_strength >= policy.event_strength_min:
            kinds.append("EVENT")
            observations.append(vector.event_strength)
        if delta is not None and delta > policy.control_margin_min:
            kinds.append("CONTROL")
            observations.append(min(1.0, delta / policy.control_full_scale))
        if vector.intent_supported and vector.mode_known:
            kinds.append("INTENT")
            observations.append(1.0)
        return kinds, (sum(observations) / len(observations)) if observations else None

    bull_types, bull_strength = support(bull, control_delta)
    bear_types, bear_strength = support(bear, -control_delta if control_delta is not None else None)
    side = "UNASSIGNED"
    status = "NO_DIRECTIONAL_EVIDENCE"
    if bull_types and bear_types:
        quality_ok = (
            bull.observation_quality is not None
            and bear.observation_quality is not None
            and min(bull.observation_quality, bear.observation_quality) >= policy.min_observation_quality
        )
        difference = bull_strength - bear_strength
        if quality_ok and abs(difference) > policy.contested_margin:
            side = "BULL" if difference > 0 else "BEAR"
            status = "CONTESTED_DIRECTION"
        else:
            status = "CONFLICT_REVIEW"
    elif bull_types or bear_types:
        side = "BULL" if bull_types else "BEAR"
        status = "CONFIRMED_STRUCTURE" if len(bull_types or bear_types) >= 2 else "SINGLE_SOURCE_STRUCTURE"
    else:
        trend_available = (
            bull.trend_history_bars is not None
            and bear.trend_history_bars is not None
            and min(bull.trend_history_bars, bear.trend_history_bars) >= policy.trend_min_bars
        )
        if trend_available and bull.trend_aligned != bear.trend_aligned:
            status = "TREND_ONLY"
        elif trend_available and bull.intent_transition and bear.intent_transition:
            status = "TRANSITION_MIXED_TREND"
        elif not trend_available:
            status = "TREND_INSUFFICIENT_HISTORY"

    trend_side = ""
    if bull.trend_aligned != bear.trend_aligned:
        trend_side = "BULL" if bull.trend_aligned else "BEAR"
    basis = json.dumps(
        {
            "policy_version": policy.version,
            "bull_support_types": bull_types,
            "bear_support_types": bear_types,
            "bull_structure_strength": bull_strength,
            "bear_structure_strength": bear_strength,
            "bull_event_as_of_session": bull.event_as_of_session,
            "bear_event_as_of_session": bear.event_as_of_session,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return {
        "thesis__side": side,
        "thesis__direction_status": status,
        "thesis__direction_basis": basis,
        "thesis__unassigned_reason": status if side == "UNASSIGNED" else "",
        "thesis__side_assignment_policy_version": policy.version,
        "thesis__evidence_independence": "SINGLE_FAMILY_OHLC",
        "bull_support_types": bull_types,
        "bear_support_types": bear_types,
        "bull_structure_strength": bull_strength,
        "bear_structure_strength": bear_strength,
        "trend_context_side": trend_side,
    }


SIDE_ASSIGNMENT_POLICY_PATH = (
    Path(__file__).resolve().parents[1] / "config" / "dir002_side_assignment_v1.json"
)
_SIDE_ASSIGNMENT_KEYS = (
    "event_strength_min", "control_margin_min", "control_full_scale",
    "contested_margin", "min_observation_quality", "trend_min_bars",
)


def load_side_assignment_policy(path: Any = None) -> SideAssignmentPolicy:
    """Load the versioned DIR-002 assignment policy; any gap fails closed."""
    policy_path = Path(path) if path else SIDE_ASSIGNMENT_POLICY_PATH
    raw = json.loads(policy_path.read_text(encoding="utf-8"))
    if raw.get("version") != "side_assign_v1":
        raise ValueError("Unsupported side-assignment policy version")
    missing = [key for key in _SIDE_ASSIGNMENT_KEYS if raw.get(key) is None]
    if missing:
        raise ValueError(f"Side-assignment policy missing {missing}")
    return SideAssignmentPolicy(
        version=raw["version"],
        event_strength_min=float(raw["event_strength_min"]),
        control_margin_min=float(raw["control_margin_min"]),
        control_full_scale=float(raw["control_full_scale"]),
        contested_margin=float(raw["contested_margin"]),
        min_observation_quality=float(raw["min_observation_quality"]),
        trend_min_bars=int(raw["trend_min_bars"]),
    )


PRODUCTION_DIRECTION_SOURCES = {"beh001_v1", "legacy_rollback"}  # side_assign_v1 superseded by BEH-001


def side_assignment_runtime(path: Any = None) -> Dict[str, Any]:
    """Policy plus the run-level direction source (R-8 rollback control).

    ``side_assign_v1`` is the production default after cut-over; the legacy
    resolver is only reachable through the governed ``legacy_rollback`` value.
    """
    policy_path = Path(path) if path else SIDE_ASSIGNMENT_POLICY_PATH
    raw = json.loads(policy_path.read_text(encoding="utf-8"))
    source = raw.get("production_direction_source")
    if source not in PRODUCTION_DIRECTION_SOURCES:
        raise ValueError(f"Invalid production_direction_source: {source!r}")
    calibration = raw.get("calibration") or {}
    if not calibration.get("status"):
        raise ValueError("Side-assignment calibration status is required")
    return {
        "policy": load_side_assignment_policy(policy_path),
        "production_direction_source": source,
        "calibration_status": calibration["status"],
    }


def side_evidence_vectors(
    structure: Mapping[str, Any],
    intent: Mapping[str, Any],
) -> Tuple[SideStructuralEvidence, SideStructuralEvidence]:
    """Map C3 kernel observations to the two assignment vectors.

    Only per-side structure (event, control), symmetric Precor intent and the
    log-trend context enter. Unevaluated inputs are absent, never zero.
    """
    structure = structure or {}
    intent = intent or {}
    structure_ok = _upper(structure.get("status")) == "EVALUATED"
    intent_ok = _upper(intent.get("status")) == "EVALUATED"
    quality = (2.0 * structure_ok + 1.0 * intent_ok) / 3.0
    intent_value = _upper(intent.get("intent"))
    mode = _upper(intent.get("mode"))
    mode_known = intent_ok and mode in {"ACCUMULATION", "DISTRIBUTION"}
    history = _number(structure.get("trend_history_bars"))
    history_bars = int(history) if history is not None and math.isfinite(history) else None
    vectors = []
    for side, setup in (("bull", "BUY_SETUP"), ("bear", "SELL_SETUP")):
        block = structure.get(side) or {}
        event_type = _upper(block.get("event_type"))
        confirmed = structure_ok and event_type not in {"", "NONE", "NOT_EVALUATED"}
        strength = _number(block.get("event_strength")) if structure_ok else None
        control = _number(block.get("control_score")) if structure_ok else None
        vectors.append(SideStructuralEvidence(
            event_confirmed=bool(confirmed),
            event_strength=strength,
            control_score=control,
            # DEC-1: only an event-anchored setup is structural support.
            intent_supported=intent_ok and intent_value == setup
            and _upper(intent.get("intent_basis")) == "EVENT",
            mode_known=mode_known,
            intent_transition=intent_ok and intent_value == "TRANSITION",
            trend_aligned=bool(structure_ok and block.get("trend_aligned") is True),
            trend_history_bars=history_bars if structure_ok else None,
            observation_quality=quality,
            event_as_of_session=_text(block.get("event_session")) if confirmed else "",
        ))
    return vectors[0], vectors[1]


# Structural invalidation owners accepted by the handoff: the Wyckoff validator
# (DIR-002) and the BEH-001 behavioural engine. Never a convention (ATR, %).
STRUCTURAL_INVALIDATION_SOURCES = frozenset({"WYCKOFF_VALIDATION", "BEHAVIOURAL_STRUCTURE"})


def assess_thesis_geometry(
    *,
    thesis_side: str,
    reference_price: Any,
    invalidation_price: Any,
    invalidation_source: Any,
    target_price: Any,
    target_source: Any,
) -> Dict[str, Any]:
    """Assess structural geometry without re-deciding the ticker direction.

    This is a descriptive boundary, not an execution or option-trade gate.
    A missing or wrong-side invalidation prevents a complete geometry while
    retaining the separately established thesis side (DIR-002 §4.3–4.5).
    """
    side = _upper(thesis_side)
    if side not in {"BULL", "BEAR", "UNASSIGNED"}:
        raise ValueError(f"Invalid canonical thesis side: {thesis_side!r}")

    def positive_finite(value: Any) -> Optional[float]:
        parsed = _number(value)
        return parsed if parsed is not None and math.isfinite(parsed) and parsed > 0 else None

    reference = positive_finite(reference_price)
    invalidation = positive_finite(invalidation_price)
    target = positive_finite(target_price)
    invalidation_basis = _upper(invalidation_source)
    target_basis = _upper(target_source)

    result: Dict[str, Any] = {
        "thesis__side": side,
        "geometry_status": "NOT_ASSESSABLE",
        "geometry_complete": False,
        "invalidation_price": None,
        "invalidation_source": None,
        "invalidation_reason": "REFERENCE_MISSING" if reference is None else "SIDE_UNASSIGNED",
        "target_state": "NONE",
        "target_price": None,
        "target_source": None,
        "target_reason": "NO_STRUCTURAL_TARGET",
    }
    if reference is None or side == "UNASSIGNED":
        return result

    if target is not None and target_basis in {"WYCKOFF", "PRIOR_RANGE_EXTREME"}:
        if (side == "BULL" and target > reference) or (side == "BEAR" and target < reference):
            result["target_state"] = "LEVEL"
            result["target_price"] = target
            result["target_source"] = target_basis
            result["target_reason"] = "STRUCTURAL_LEVEL"
        else:
            result["target_reason"] = "WRONG_SIDE"
    elif target is not None:
        result["target_reason"] = "UNSOURCED"

    if invalidation is None:
        result["invalidation_reason"] = "MISSING"
    elif invalidation_basis not in STRUCTURAL_INVALIDATION_SOURCES:
        result["invalidation_reason"] = "UNSOURCED"
    elif (side == "BULL" and invalidation >= reference) or (
        side == "BEAR" and invalidation <= reference
    ):
        result["invalidation_reason"] = "WRONG_SIDE"
    else:
        result["invalidation_price"] = invalidation
        result["invalidation_source"] = invalidation_basis
        result["invalidation_reason"] = "STRUCTURAL_LEVEL"
        result["geometry_status"] = "COMPLETE"
        result["geometry_complete"] = True

    if not result["geometry_complete"]:
        result["geometry_status"] = "INCOMPLETE_GEOMETRY"
    return result


def candidate_geometry_shadow_fields(
    reference_price: Any,
    structural_candidates: Mapping[str, Any],
) -> Dict[str, Any]:
    """Adapt both structural candidates to namespaced, non-authoritative fields.

    No selected side, option side, macro observation or Vanguard statistic is
    accepted. The same readiness rule is applied to BULL and BEAR.
    """
    output: Dict[str, Any] = {}
    for side in ("BULL", "BEAR"):
        label = side.lower()
        geometry = assess_thesis_geometry(
            thesis_side=side,
            reference_price=reference_price,
            invalidation_price=structural_candidates.get(f"candidate_{label}_invalidation"),
            invalidation_source=structural_candidates.get("candidate_invalidation_source"),
            target_price=structural_candidates.get(f"candidate_{label}_target"),
            target_source=structural_candidates.get("candidate_target_source"),
        )
        output.update(
            {
                f"sym_{label}_geometry_status": geometry["geometry_status"],
                f"sym_{label}_invalidation": geometry["invalidation_price"],
                f"sym_{label}_invalidation_reason": geometry["invalidation_reason"],
                f"sym_{label}_target_state": geometry["target_state"],
                f"sym_{label}_target": geometry["target_price"],
                f"sym_{label}_target_reason": geometry["target_reason"],
            }
        )
    return output


def legacy_direction_adapter_v1(
    *,
    thesis_side: str,
    direction_status: str,
    direction_basis: str,
    unassigned_reason: Optional[str],
    geometry: Mapping[str, Any],
) -> Dict[str, Any]:
    """Derive legacy side and level fields from one Thesis-owned decision.

    This pure adapter is not a second direction resolver. DIR-002 §4.5 keeps
    the old vocabulary at consumers while canonical evidence is proven in
    shadow. It never turns a reference level into a trade barrier.
    """
    side = _upper(thesis_side)
    if side not in {"BULL", "BEAR", "UNASSIGNED"}:
        raise ValueError(f"Invalid canonical thesis side: {thesis_side!r}")
    if _upper(direction_status) == "TREND_ONLY" and side != "UNASSIGNED":
        raise ValueError("Trend-only evidence cannot assign a canonical side (DEC-1)")
    if side == "UNASSIGNED" and not _text(unassigned_reason):
        raise ValueError("Unassigned thesis requires an explicit reason")
    direction = (
        "CALL" if side == "BULL" else "PUT" if side == "BEAR" else
        "STRANGLE" if _upper(unassigned_reason) == "TRANSITION_MIXED_TREND" else "UNRESOLVED"
    )
    geometry_status = _upper(geometry.get("geometry_status")) if side != "UNASSIGNED" else "NOT_ASSESSABLE"
    stop_value = _number(geometry.get("invalidation_price"))
    valid_stop = (
        side != "UNASSIGNED"
        and geometry_status == "COMPLETE"
        and _upper(geometry.get("invalidation_source")) in STRUCTURAL_INVALIDATION_SOURCES
        and stop_value is not None and math.isfinite(stop_value) and stop_value > 0
    )
    invalidation = float(geometry["invalidation_price"]) if valid_stop else None
    stop_source = _upper(geometry.get("invalidation_source"))
    if side != "UNASSIGNED" and geometry_status == "COMPLETE" and not valid_stop:
        geometry_status = "INCOMPLETE_GEOMETRY"
    target_basis = _upper(geometry.get("target_source"))
    target_value = _number(geometry.get("target_price"))
    valid_target = (
        side != "UNASSIGNED"
        and _upper(geometry.get("target_state")) == "LEVEL"
        and target_basis in {"WYCKOFF", "PRIOR_RANGE_EXTREME"}
        and target_value is not None and math.isfinite(target_value) and target_value > 0
    )
    target = float(geometry["target_price"]) if valid_target else None
    return {
        "thesis__side": side,
        "thesis__direction_status": _text(direction_status),
        "thesis__direction_basis": _text(direction_basis),
        "thesis__unassigned_reason": _text(unassigned_reason) if side == "UNASSIGNED" else "",
        "direction": direction,
        "discovery_direction_preliminary": direction,
        "discovery_direction_status": _text(direction_status),
        "discovery_direction_basis": _text(direction_basis),
        "direction_authority": "DISCOVERY_GOVERNED",
        "geometry_status": geometry_status or "NOT_ASSESSABLE",
        "target_state": "LEVEL" if valid_target else "NONE",
        "stop_loss": invalidation,
        "structural_stop": invalidation,
        "structural_stop_source": stop_source if valid_stop else "MISSING_AUTHORITATIVE_INVALIDATION",
        "governed_invalidation_spot": invalidation,
        "governed_invalidation_source": stop_source if valid_stop else "MISSING_AUTHORITATIVE_INVALIDATION",
        "structural_target": target,
        # Audit finding 5 (1 Oct 2026): the target travels with the source that produced it.
        "structural_target_source": target_basis if valid_target else None,
    }


def preliminary_discovery_direction(fusion_direction: Any, wyckoff_direction: Any) -> str:
    """Return a preliminary hint without ever defaulting ambiguity to CALL."""
    for value in (fusion_direction, wyckoff_direction):
        side = normalise_side(value)
        if side in DIRECTED:
            return side
    return UNRESOLVED


def resolve_discovery_thesis_direction(
    fusion_direction: Any,
    wyckoff_direction: Any,
    precor_intent: Any,
    trend: Any,
) -> Tuple[str, str, str]:
    """Freeze the Discovery thesis direction from all structural evidence.

    An explicit Fusion/Wyckoff side is retained when the Precor table is
    non-directional.  A directional Precor result fills a previously unresolved
    preliminary hint.  Opposing directional results fail closed as UNRESOLVED;
    a later stage must not silently choose one side and inherit geometry built
    for the other.
    """
    preliminary = preliminary_discovery_direction(fusion_direction, wyckoff_direction)
    structural, structural_basis = structural_direction(precor_intent, trend)

    if preliminary in DIRECTED and structural in DIRECTED:
        if preliminary == structural:
            return (
                preliminary,
                "CONFIRMED",
                f"discovery_preliminary={preliminary}; {structural_basis}",
            )
        return (
            UNRESOLVED,
            "CONFLICT_REVIEW",
            f"discovery_preliminary={preliminary}; structural={structural}; {structural_basis}",
        )
    if preliminary in DIRECTED:
        return preliminary, "CONFIRMED_PRELIMINARY", f"discovery_preliminary={preliminary}"
    if structural in DIRECTED:
        return structural, "RESOLVED_STRUCTURAL", structural_basis
    if structural == STRANGLE:
        return STRANGLE, "NON_DIRECTIONAL", structural_basis
    return UNRESOLVED, "NOT_RESOLVED", structural_basis


@dataclass(frozen=True)
class DirectionEvidence:
    source: str
    family: str
    side: str
    weight: float
    as_of_utc: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return {
            "source": self.source,
            "family": self.family,
            "side": self.side,
            "weight": round(float(self.weight), 4),
            "direction_independent": True,
            "as_of_utc": self.as_of_utc,
        }


def _first_side(row: Mapping[str, Any], keys: Iterable[str]) -> str:
    for key in keys:
        side = normalise_side(row.get(key))
        if side in DIRECTED:
            return side
    return ""


def collect_resolution_evidence(row: Mapping[str, Any]) -> List[DirectionEvidence]:
    """Collect at most one vote per evidence family.

    All admitted sources are produced without using a selected option contract,
    a generated target, or the Discovery preliminary direction.  Multiple
    aliases of the same underlying model are deliberately de-duplicated.
    """
    evidence: List[DirectionEvidence] = []
    as_of = _text(
        row.get("as_of_utc")
        or row.get("scanner_timestamp_utc")
        or row.get("generated_at_utc")
    )

    actuarial = _first_side(
        row,
        (
            "vanguard_edge_direction",
            "layer2__edge_direction",
            "layer2__probability_direction",
            "edge_direction",
        ),
    )
    if actuarial:
        evidence.append(DirectionEvidence("VANGUARD_EDGE_DIRECTION", "ACTUARIAL", actuarial, 1.0, as_of))

    catalyst_quality = _upper(row.get("catalyst_data_quality"))
    catalyst_class = _upper(row.get("catalyst_trade_class"))
    catalyst_event_status = _upper(row.get("catalyst_event_status"))
    catalyst_admissible = (
        catalyst_class != "STRUCTURE_ONLY_NO_CATALYST"
        and (
            _truthy(row.get("catalyst_detected"))
            or catalyst_quality in {"CONFIRMED", "INFERRED"}
            or catalyst_event_status in {"CONFIRMED", "ACTIVE", "UPCOMING"}
        )
    )
    catalyst_independent = _truthy(row.get("catalyst_direction_independent"))
    catalyst_source = _upper(row.get("catalyst_direction_source"))
    catalyst_source_field = _upper(row.get("catalyst_direction_source_field"))
    catalyst_provenance_valid = bool(
        catalyst_independent
        and catalyst_source
        and catalyst_source_field in {
            "CATALYST_DIRECTION_BIAS",
            "TRADE_BIAS",
            "EXPECTED_IMPACT",
        }
    )
    catalyst = _first_side(row, ("catalyst_direction_bias", "catalyst_trade_bias"))
    if catalyst and catalyst_admissible and catalyst_provenance_valid:
        evidence.append(DirectionEvidence("CATALYST_DIRECTION_BIAS", "CATALYST", catalyst, 1.0, as_of))

    force = _number(row.get("directional_force"))
    if force is not None and abs(force) >= 5.0:
        force_side = CALL if force > 0 else PUT
        # Cap extreme values so one price-derived feature cannot dominate.
        force_weight = min(1.0, max(0.50, abs(force) / 20.0))
        evidence.append(DirectionEvidence("DIRECTIONAL_FORCE", "PRICE_FLOW", force_side, force_weight, as_of))

    relative_strength = _number(
        row.get("relative_strength_20d")
        or row.get("sector_relative_strength_20d")
        or row.get("rs_20d")
    )
    if relative_strength is not None and abs(relative_strength) >= 0.02:
        rs_side = CALL if relative_strength > 0 else PUT
        rs_weight = min(1.0, max(0.50, abs(relative_strength) / 0.10))
        evidence.append(DirectionEvidence("RELATIVE_STRENGTH_20D", "RELATIVE_STRENGTH", rs_side, rs_weight, as_of))

    # Stable ordering is required for reproducible hashes and replays.
    return sorted(evidence, key=lambda item: (item.family, item.source, item.side))


def _policy_hash() -> str:
    payload = {
        "version": LEGACY_RESOLUTION_POLICY_VERSION,
        "minimum_families": MIN_EVIDENCE_FAMILIES,
        "minimum_winning_share": MIN_WINNING_SHARE,
        "minimum_margin": MIN_DIRECTION_MARGIN,
        "families": ["ACTUARIAL", "CATALYST", "PRICE_FLOW", "RELATIVE_STRENGTH"],
        "catalyst_admission": {
            "exclude_trade_class": "STRUCTURE_ONLY_NO_CATALYST",
            "detected_or_quality": ["CONFIRMED", "INFERRED"],
            "event_status": ["CONFIRMED", "ACTIVE", "UPCOMING"],
            "requires_independent_provenance": True,
            "source_fields": [
                "CATALYST_DIRECTION_BIAS",
                "TRADE_BIAS",
                "EXPECTED_IMPACT",
            ],
        },
        "excluded": EXCLUDED_DIRECTION_EVIDENCE,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


def _fresh_policy_hash() -> str:
    """No post-Discovery family can reassign the structural thesis side."""
    payload = {
        "version": RESOLUTION_POLICY_VERSION,
        "authority": "DISCOVERY_GOVERNED",
        "resolution_families": [],
        "non_directional_resolution": False,
        "side_owner": "thesis__side",
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


def approved_direction_policy_tuples() -> frozenset[tuple[str, str, str]]:
    """Immutable, explicit registry for the current release and prior replay."""
    return frozenset({
        (DIR_CALC_VERSION, RESOLUTION_POLICY_VERSION, _fresh_policy_hash()),
        (LEGACY_DIR_CALC_VERSION, LEGACY_RESOLUTION_POLICY_VERSION, _policy_hash()),
    })


def direction_policy_uniformity(rows: Iterable[Mapping[str, Any]]) -> Tuple[bool, str]:
    """Accept either release for replay, but never mix releases within one run."""
    tuples = {
        (
            _text(row.get("dir_calc_version")),
            _text(row.get("direction_policy_version")),
            _text(row.get("direction_policy_sha256")),
        )
        for row in rows
    }
    if len(tuples) != 1:
        return False, "DIRECTION_POLICY_TUPLE_MIXED_OR_MISSING"
    if next(iter(tuples)) not in approved_direction_policy_tuples():
        return False, "DIRECTION_POLICY_TUPLE_UNAPPROVED"
    return True, "OK"


def resolve_governed_direction(
    *,
    ticker: Any,
    run_id: Any,
    discovery_direction: Any,
    governed_direction: Any,
    governed_basis: str,
    row: Mapping[str, Any],
    decided_at_utc: str = "",
    authority: str = "OPTIONS_INTELLIGENCE",
    allow_non_directional_resolution: bool = True,
) -> Dict[str, Any]:
    """Build a complete GDR and, when permitted, resolve a non-directional state."""
    governed = normalise_side(governed_direction)
    preliminary = normalise_side(discovery_direction)
    decided_at = decided_at_utc or datetime.now(timezone.utc).isoformat()
    thesis_side = _upper(row.get("thesis__side"))
    if thesis_side and thesis_side not in {"BULL", "BEAR", "UNASSIGNED"}:
        raise ValueError("THESIS_SIDE_INVALID")
    if thesis_side and _upper(authority) != "DISCOVERY_GOVERNED":
        raise ValueError("THESIS_AUTHORITY_INVALID")
    fresh_authority = _upper(authority) == "DISCOVERY_GOVERNED" and thesis_side in {
        "BULL", "BEAR", "UNASSIGNED"
    }
    if fresh_authority and thesis_side in {"BULL", "BEAR"}:
        expected_governed = CALL if thesis_side == "BULL" else PUT
        if governed != expected_governed:
            raise ValueError("DISCOVERY_THESIS_GOVERNED_SIDE_MISMATCH")
    if fresh_authority and thesis_side == "UNASSIGNED" and governed in DIRECTED:
        raise ValueError("UNASSIGNED_THESIS_CANNOT_GOVERN_A_DIRECTION")
    calc_version = DIR_CALC_VERSION if fresh_authority else LEGACY_DIR_CALC_VERSION
    policy_version = RESOLUTION_POLICY_VERSION if fresh_authority else LEGACY_RESOLUTION_POLICY_VERSION
    policy_hash = _fresh_policy_hash() if fresh_authority else _policy_hash()
    evidence = [] if fresh_authority else collect_resolution_evidence(row)
    call_score = sum(item.weight for item in evidence if item.side == CALL)
    put_score = sum(item.weight for item in evidence if item.side == PUT)
    total = call_score + put_score
    winning_side = CALL if call_score > put_score else PUT if put_score > call_score else ""
    winning_score = max(call_score, put_score)
    losing_score = min(call_score, put_score)
    winning_share = (winning_score / total) if total > 0 else 0.0
    margin = ((winning_score - losing_score) / total) if total > 0 else 0.0
    supporting_families = {
        item.family for item in evidence if item.side == winning_side
    }

    final_direction = governed
    resolution_path = "DIRECTION_CONFIRMED" if governed in DIRECTED else "UNRESOLVED"
    governance_status = "CONFIRMED" if governed in DIRECTED else "NOT_RESOLVED"
    resolution_chain: List[Dict[str, Any]] = []
    confidence = ""

    if not fresh_authority and allow_non_directional_resolution and governed in NON_DIRECTIONAL and (
        winning_side in DIRECTED
        and len(supporting_families) >= MIN_EVIDENCE_FAMILIES
        and winning_share >= MIN_WINNING_SHARE
        and margin >= MIN_DIRECTION_MARGIN
    ):
        final_direction = winning_side
        resolution_path = "DIRECTION_RESOLVED_PRECONTRACT"
        governance_status = "RESOLVED"
        confidence = "HIGH" if winning_share >= 0.75 and margin >= 0.50 else "MEDIUM"
        resolution_chain.append(
            {
                "stage": "OPTIONS_PRECONTRACT_RESOLUTION",
                "from": governed,
                "to": final_direction,
                "protocol": policy_version,
                "evidence": [item.as_dict() for item in evidence],
                "excluded_evidence": EXCLUDED_DIRECTION_EVIDENCE,
                "call_score": round(call_score, 4),
                "put_score": round(put_score, 4),
                "winning_share": round(winning_share, 4),
                "margin": round(margin, 4),
                "minimum_families": MIN_EVIDENCE_FAMILIES,
                "threshold": MIN_WINNING_SHARE,
                "minimum_margin": MIN_DIRECTION_MARGIN,
                "confidence": confidence,
                "reason": "Independent evidence families satisfied the governed resolution policy",
                "resolved_at_utc": decided_at,
            }
        )

    record: Dict[str, Any] = {
        "schema_version": GDR_SCHEMA_VERSION,
        "dir_key": {
            "ticker": _upper(ticker),
            "run_id": _text(run_id),
            "dir_calc_version": calc_version,
        },
        "preliminary": {
            "discovery_direction": preliminary,
        },
        "governed": {
            "direction": governed,
            "authority": authority,
            "basis": governed_basis,
            "decided_at_utc": decided_at,
        },
        "resolution_chain": resolution_chain,
        "final": {
            "direction": final_direction,
            "resolution_path": resolution_path,
        },
        "policy": {
            "version": policy_version,
            "sha256": policy_hash,
        },
    }
    canonical = json.dumps(record, sort_keys=True, separators=(",", ":"))
    record_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    return {
        "dir_calc_version": calc_version,
        "direction_policy_version": policy_version,
        "direction_policy_sha256": policy_hash,
        "discovery_direction_preliminary": preliminary,
        "governed_direction": governed,
        "governed_direction_authority": authority,
        "governed_direction_basis": governed_basis,
        "final_direction": final_direction,
        "direction_resolution_path": resolution_path,
        "direction_governance_status": governance_status,
        "direction_resolution_confidence": confidence,
        "direction_resolution_call_score": round(call_score, 4),
        "direction_resolution_put_score": round(put_score, 4),
        "direction_resolution_winning_share": round(winning_share, 4),
        "direction_resolution_margin": round(margin, 4),
        "direction_resolution_evidence_count": len(evidence),
        "direction_resolution_evidence_json": json.dumps(
            [item.as_dict() for item in evidence], sort_keys=True
        ),
        "direction_resolution_chain_json": json.dumps(resolution_chain, sort_keys=True),
        "direction_excluded_evidence_json": json.dumps(EXCLUDED_DIRECTION_EVIDENCE),
        "governed_direction_record_json": canonical,
        "governed_direction_record_sha256": record_hash,
    }


def parse_json_list(value: Any) -> List[Dict[str, Any]]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    text = _text(value)
    if not text:
        return []
    try:
        parsed = json.loads(text)
    except (TypeError, ValueError, json.JSONDecodeError):
        return []
    return [item for item in parsed if isinstance(item, dict)] if isinstance(parsed, list) else []


def validate_direction_record(row: Mapping[str, Any]) -> Tuple[bool, str]:
    """Validate final direction, provenance chain and dependent-side invariants."""
    governed = normalise_side(row.get("governed_direction"))
    final_direction = normalise_side(
        row.get("final_direction")
        or row.get("canonical_direction")
        or row.get("resolved_direction")
        or row.get("direction")
    )
    path = _upper(row.get("direction_resolution_path"))
    version = _text(row.get("dir_calc_version"))
    if version not in {DIR_CALC_VERSION, LEGACY_DIR_CALC_VERSION}:
        return False, f"DIRECTION_VERSION_INVALID:{version or 'MISSING'}"
    policy_version = _text(row.get("direction_policy_version"))
    policy_hash = _text(row.get("direction_policy_sha256"))
    if (version, policy_version, policy_hash) not in approved_direction_policy_tuples():
        return False, "DIRECTION_POLICY_TUPLE_UNAPPROVED"
    fresh_policy = version == DIR_CALC_VERSION

    record_text = _text(row.get("governed_direction_record_json"))
    record_hash = _text(row.get("governed_direction_record_sha256"))
    if not record_text or not record_hash:
        return False, "DIRECTION_RECORD_OR_HASH_MISSING"
    calculated_hash = hashlib.sha256(record_text.encode("utf-8")).hexdigest()
    if calculated_hash != record_hash:
        return False, "DIRECTION_RECORD_HASH_MISMATCH"
    try:
        record_object = json.loads(record_text)
    except (TypeError, ValueError, json.JSONDecodeError):
        return False, "DIRECTION_RECORD_JSON_INVALID"
    policy = record_object.get("policy") if isinstance(record_object, dict) else {}
    if not isinstance(policy, dict):
        return False, "DIRECTION_POLICY_RECORD_MISSING"
    if _text(row.get("direction_policy_version")) != policy_version:
        return False, "DIRECTION_POLICY_VERSION_INVALID"
    if _text(row.get("direction_policy_sha256")) != policy_hash:
        return False, "DIRECTION_POLICY_HASH_INVALID"
    if _text(policy.get("version")) != policy_version:
        return False, "DIRECTION_RECORD_POLICY_VERSION_INVALID"
    if _text(policy.get("sha256")) != policy_hash:
        return False, "DIRECTION_RECORD_POLICY_HASH_INVALID"
    if fresh_policy and _upper((record_object.get("governed") or {}).get("authority")) != "DISCOVERY_GOVERNED":
        return False, "DIRECTION_POLICY_AUTHORITY_INVALID"
    recovered = direction_fields_from_record_json(record_text)
    for field, actual in (
        ("dir_calc_version", version),
        ("governed_direction", governed),
        ("final_direction", final_direction),
        ("direction_resolution_path", path),
    ):
        expected = _upper(recovered.get(field))
        if expected != _upper(actual):
            return False, f"DIRECTION_RECORD_FLAT_FIELD_MISMATCH:{field}"
    if final_direction not in DIRECTED:
        return False, f"DIRECTION_NOT_EXECUTABLE:{final_direction or 'MISSING'}"
    if governed not in DIRECTED | NON_DIRECTIONAL:
        return False, f"GOVERNED_DIRECTION_INVALID:{governed or 'MISSING'}"

    chain = parse_json_list(row.get("direction_resolution_chain_json"))
    if fresh_policy and chain:
        return False, "DIRECTION_FRESH_POLICY_CHAIN_FORBIDDEN"
    if final_direction == governed:
        if chain:
            return False, "DIRECTION_CHAIN_PRESENT_WITHOUT_DIRECTION_CHANGE"
        if path != "DIRECTION_CONFIRMED":
            return False, f"DIRECTION_PATH_INVALID_FOR_CONFIRMED:{path or 'MISSING'}"
    else:
        if not chain:
            return False, "DIRECTION_CHANGED_WITHOUT_RESOLUTION_CHAIN"
        last = chain[-1]
        if normalise_side(last.get("to")) != final_direction:
            return False, "DIRECTION_CHAIN_FINAL_MISMATCH"
        if _upper(last.get("protocol")) != policy_version.upper():
            return False, "DIRECTION_PROTOCOL_INVALID"
        evidence = last.get("evidence")
        if not isinstance(evidence, list) or not evidence:
            return False, "DIRECTION_RESOLUTION_EVIDENCE_MISSING"
        families = set()
        for item in evidence:
            if not isinstance(item, dict) or item.get("direction_independent") is not True:
                return False, "DIRECTION_RESOLUTION_EVIDENCE_NOT_INDEPENDENT"
            if normalise_side(item.get("side")) == final_direction:
                families.add(_upper(item.get("family")))
        if len(families) < MIN_EVIDENCE_FAMILIES:
            return False, "DIRECTION_RESOLUTION_INSUFFICIENT_FAMILIES"
        if (_number(last.get("winning_share")) or 0.0) < MIN_WINNING_SHARE:
            return False, "DIRECTION_RESOLUTION_WINNING_SHARE_BELOW_POLICY"
        if (_number(last.get("margin")) or 0.0) < MIN_DIRECTION_MARGIN:
            return False, "DIRECTION_RESOLUTION_MARGIN_BELOW_POLICY"
        if path not in {"DIRECTION_RESOLVED_PRECONTRACT", "DIRECTION_OVERRIDDEN"}:
            return False, f"DIRECTION_PATH_INVALID_FOR_RESOLUTION:{path or 'MISSING'}"

    signal = _number(
        row.get("live_price")
        or row.get("underlying_price")
        or row.get("signal_price")
        or row.get("scanner_price")
    )
    target = _number(
        row.get("monetisability_structural_target_spot")
        or row.get("structural_target")
        or row.get("target_price")
        or row.get("exit_target_price")
    )
    invalidation = _number(
        row.get("invalidation_price")
        or row.get("invalidation_level")
        or row.get("exit_invalidation_price")
        or row.get("exit_stop_price")
    )
    if signal is not None and target is not None:
        if final_direction == CALL and target <= signal:
            return False, "CALL_TARGET_NOT_ABOVE_SIGNAL"
        if final_direction == PUT and target >= signal:
            return False, "PUT_TARGET_NOT_BELOW_SIGNAL"
    if signal is not None and invalidation is not None:
        if final_direction == CALL and invalidation >= signal:
            return False, "CALL_INVALIDATION_NOT_BELOW_SIGNAL"
        if final_direction == PUT and invalidation <= signal:
            return False, "PUT_INVALIDATION_NOT_ABOVE_SIGNAL"

    contract_side = normalise_side(
        row.get("selected_contract_side")
        or row.get("monetisability_direction")
    )
    if contract_side in DIRECTED and contract_side != final_direction:
        return False, f"SELECTED_CONTRACT_DIRECTION_MISMATCH:{contract_side}->{final_direction}"
    return True, "DIRECTION_INTEGRITY_CONFIRMED"


def direction_fields_from_record_json(value: Any) -> Dict[str, Any]:
    """Recover canonical flat fields from a serialized GDR when needed."""
    text = _text(value)
    if not text:
        return {}
    try:
        record = json.loads(text)
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    if not isinstance(record, dict):
        return {}
    governed = record.get("governed") if isinstance(record.get("governed"), dict) else {}
    final = record.get("final") if isinstance(record.get("final"), dict) else {}
    key = record.get("dir_key") if isinstance(record.get("dir_key"), dict) else {}
    policy = record.get("policy") if isinstance(record.get("policy"), dict) else {}
    return {
        "dir_calc_version": key.get("dir_calc_version", ""),
        "direction_policy_version": policy.get("version", ""),
        "direction_policy_sha256": policy.get("sha256", ""),
        "governed_direction": governed.get("direction", ""),
        "governed_direction_authority": governed.get("authority", ""),
        "governed_direction_basis": governed.get("basis", ""),
        "final_direction": final.get("direction", ""),
        "direction_resolution_path": final.get("resolution_path", ""),
        "direction_resolution_chain_json": json.dumps(record.get("resolution_chain") or [], sort_keys=True),
    }
