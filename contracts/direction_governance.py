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
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple


DIR_CALC_VERSION = "dir_v1.2.0"
RESOLUTION_POLICY_VERSION = "strangle_resolution_v1.1.0"
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
    text = _upper(value)
    if text in DIRECTED | NON_DIRECTIONAL:
        return text
    if any(token in text for token in ("PUT", "SELL", "BEAR", "SHORT")):
        return PUT
    if any(token in text for token in ("CALL", "BUY", "BULL", "LONG")):
        return CALL
    if text in {"STRADDLE", "NON_DIRECTIONAL", "MIXED", "TRANSITION"}:
        return STRANGLE
    return UNRESOLVED


def structural_direction(precor_intent: Any, trend: Any) -> Tuple[str, str]:
    """Closed, fail-closed structural direction table."""
    intent = _upper(precor_intent)
    trend_value = _upper(trend)
    if intent == "BUY_SETUP":
        return CALL, "precor_intent=BUY_SETUP"
    if intent == "SELL_SETUP":
        return PUT, "precor_intent=SELL_SETUP"
    if intent == "TRANSITION":
        if trend_value == "BULLISH":
            return CALL, "precor_intent=TRANSITION, trend=BULLISH"
        if trend_value == "BEARISH":
            return PUT, "precor_intent=TRANSITION, trend=BEARISH"
        return STRANGLE, f"precor_intent=TRANSITION, trend={trend_value or 'MIXED'}"
    if intent == "WAIT":
        return UNRESOLVED, "precor_intent=WAIT"
    return UNRESOLVED, f"precor_intent={intent or 'MISSING'}"


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
        "version": RESOLUTION_POLICY_VERSION,
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
    evidence = collect_resolution_evidence(row)
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

    if allow_non_directional_resolution and governed in NON_DIRECTIONAL and (
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
                "protocol": RESOLUTION_POLICY_VERSION,
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
            "dir_calc_version": DIR_CALC_VERSION,
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
            "version": RESOLUTION_POLICY_VERSION,
            "sha256": _policy_hash(),
        },
    }
    canonical = json.dumps(record, sort_keys=True, separators=(",", ":"))
    record_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    return {
        "dir_calc_version": DIR_CALC_VERSION,
        "direction_policy_version": RESOLUTION_POLICY_VERSION,
        "direction_policy_sha256": _policy_hash(),
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
    if version != DIR_CALC_VERSION:
        return False, f"DIRECTION_VERSION_INVALID:{version or 'MISSING'}"

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
    if _text(row.get("direction_policy_version")) != RESOLUTION_POLICY_VERSION:
        return False, "DIRECTION_POLICY_VERSION_INVALID"
    if _text(row.get("direction_policy_sha256")) != _policy_hash():
        return False, "DIRECTION_POLICY_HASH_INVALID"
    if _text(policy.get("version")) != RESOLUTION_POLICY_VERSION:
        return False, "DIRECTION_RECORD_POLICY_VERSION_INVALID"
    if _text(policy.get("sha256")) != _policy_hash():
        return False, "DIRECTION_RECORD_POLICY_HASH_INVALID"
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
        if _upper(last.get("protocol")) != RESOLUTION_POLICY_VERSION.upper():
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
