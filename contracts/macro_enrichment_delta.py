#!/usr/bin/env python3
"""
Additive macro enrichment delta support.

The enrichment packet is a narrative/event overlay for an existing
macro_contract_v1_0 payload. It never replaces quantitative macro fields and
never changes ticker ingestion. Plain tickers can be matched later through the
macro exposure index stored under extras.
"""

from __future__ import annotations

import copy
import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional


ENRICHMENT_CONTRACT_VERSION = "macro_enrichment_delta_v1_0"
SUPPORTED_ENRICHMENT_CONTRACT_VERSIONS = {
    "macro_enrichment_delta_v1_0",
    "macro_enrichment_delta_v1_1",
    "macro_enrichment_delta_v1_2",
}
TARGET_MACRO_CONTRACT_VERSION = "macro_contract_v1_0"
PACKET_TYPE = "MACRO_ENRICHMENT_DELTA"
MERGE_MODE = "AUGMENT_ONLY_DO_NOT_REPLACE"

PROTECTED_MACRO_FIELDS = {
    "contract_version",
    "regime_state",
    "dir_bias",
    "trend_energy",
    "usd_state",
    "rates_impulse",
    "liquidity_pulse",
    "regime_drift_status",
    "macro_conviction",
    "vol_mode",
    "risk_on_off_switch",
    "sector_tilt",
    "net_liquidity_score",
    "vix_regime_score",
    "gex_regime_score",
    "macro_momentum_score",
    "regime_label",
    "regime_probability",
    "vix_spot",
    "macro_filter",
    "sector_lead",
    "sector_avoid",
    "size_multiplier",
    "trigger_required",
    "horizon_routing",
    "sector_rotation",
    "put_gate",
    "macro_quant_packet",
}

ALLOWED_TOP_LEVEL_KEYS = {
    "contract_version",
    "target_macro_contract_version",
    "packet_type",
    "merge_mode",
    "batch_id",
    "source",
    "as_of_utc",
    "report_date",
    "source_freshness",
    "ticker_handoff_policy",
    "protected_macro_fields_do_not_override",
    "merge_controls",
    "narrative_overlay",
    "theme_deltas",
    "event_guard_deltas",
    "macro_json_merge_block",
    "macro_exposure_index_build",
    "validation_rules",
    "audit",
    "binary_options_analysis_policy",
}

FORBIDDEN_TRUE_MERGE_CONTROLS = {
    "can_override_macro_filter",
    "can_change_size_multiplier",
    "can_change_trigger_required",
    "can_change_horizon_routing",
    "can_unblock_put_gate",
    "can_override_sector_lead_or_sector_avoid",
}

DELTA_PATTERNS = (
    "macro_enrichment_delta_latest.json",
    "macro_enrichment_delta*.json",
    "avshunter_macro_enrichment_delta*.json",
)


@dataclass
class ValidationResult:
    valid: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    protected_fields_attempted: List[str] = field(default_factory=list)
    conflict_flags: List[str] = field(default_factory=list)
    theme_relationships: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def load_macro_enrichment_delta(path: Path | str) -> Dict[str, Any]:
    delta_path = Path(path)
    with delta_path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise ValueError(f"Macro enrichment delta must be a JSON object: {delta_path}")
    return data


def find_macro_enrichment_delta(
    macro_path: Path | str,
    explicit_path: Optional[Path | str] = None,
) -> Optional[Path]:
    if explicit_path:
        candidate = Path(explicit_path)
        return candidate if candidate.is_absolute() else (Path.cwd() / candidate).resolve()

    macro_dir = Path(macro_path).resolve().parent
    candidates: List[Path] = []
    for pattern in DELTA_PATTERNS:
        candidates.extend([p for p in macro_dir.glob(pattern) if p.is_file()])

    unique = {str(p.resolve()): p for p in candidates}
    if not unique:
        return None

    ordered = sorted(unique.values(), key=lambda p: p.stat().st_mtime, reverse=True)
    return ordered[0]


def validate_macro_enrichment_delta(
    enrichment: Mapping[str, Any],
    base_macro: Mapping[str, Any],
) -> ValidationResult:
    errors: List[str] = []
    warnings: List[str] = []

    if not isinstance(enrichment, Mapping):
        return ValidationResult(False, errors=["enrichment must be a mapping"])
    if not isinstance(base_macro, Mapping):
        return ValidationResult(False, errors=["base_macro must be a mapping"])

    if enrichment.get("contract_version") not in SUPPORTED_ENRICHMENT_CONTRACT_VERSIONS:
        errors.append(
            "contract_version must be one of "
            f"{sorted(SUPPORTED_ENRICHMENT_CONTRACT_VERSIONS)}, got {enrichment.get('contract_version')!r}"
        )
    if enrichment.get("packet_type") != PACKET_TYPE:
        errors.append(f"packet_type must be {PACKET_TYPE}")
    if enrichment.get("merge_mode") != MERGE_MODE:
        errors.append(f"merge_mode must be {MERGE_MODE}")

    target = enrichment.get("target_macro_contract_version")
    base_contract = base_macro.get("contract_version")
    if target != TARGET_MACRO_CONTRACT_VERSION:
        errors.append(f"target_macro_contract_version must be {TARGET_MACRO_CONTRACT_VERSION}")
    if base_contract and target and base_contract != target:
        errors.append(f"delta targets {target}, but base macro contract is {base_contract}")

    unexpected = sorted(set(enrichment.keys()) - ALLOWED_TOP_LEVEL_KEYS)
    attempted = sorted(
        key
        for key in unexpected
        if key in PROTECTED_MACRO_FIELDS or key in {"macro", "macro_state", "overrides"}
    )

    overrides = enrichment.get("overrides")
    if isinstance(overrides, Mapping):
        attempted.extend(sorted(set(overrides.keys()) & PROTECTED_MACRO_FIELDS))

    if attempted:
        errors.append(
            "enrichment attempts to override protected macro field(s): "
            + ", ".join(sorted(set(attempted)))
        )

    controls = enrichment.get("merge_controls") or {}
    if isinstance(controls, Mapping):
        bad_controls = sorted(
            key for key in FORBIDDEN_TRUE_MERGE_CONTROLS if controls.get(key) is True
        )
        if bad_controls:
            errors.append("unsafe merge_controls enabled: " + ", ".join(bad_controls))
    else:
        warnings.append("merge_controls missing or invalid")

    ticker_policy = enrichment.get("ticker_handoff_policy") or {}
    if isinstance(ticker_policy, Mapping):
        allowed_cols = ticker_policy.get("allowed_candidate_columns")
        if allowed_cols not in (["ticker"], ("ticker",)):
            errors.append("ticker_handoff_policy must keep allowed_candidate_columns=['ticker']")
        if ticker_policy.get("do_not_add_candidate_metadata_to_ticker_file") is not True:
            errors.append("ticker_handoff_policy must forbid candidate metadata in ticker file")
    else:
        warnings.append("ticker_handoff_policy missing or invalid")

    if not isinstance(enrichment.get("theme_deltas", []), list):
        errors.append("theme_deltas must be a list")
    if not isinstance(enrichment.get("event_guard_deltas", []), list):
        errors.append("event_guard_deltas must be a list")

    conflict_flags = detect_enrichment_conflicts(base_macro, enrichment)
    relationships = detect_theme_relationships(base_macro, enrichment)

    return ValidationResult(
        valid=not errors,
        errors=errors,
        warnings=warnings,
        protected_fields_attempted=sorted(set(attempted)),
        conflict_flags=conflict_flags,
        theme_relationships=relationships,
    )


def merge_macro_enrichment_delta(
    base_macro: Mapping[str, Any],
    enrichment: Mapping[str, Any],
) -> Dict[str, Any]:
    validation = validate_macro_enrichment_delta(enrichment, base_macro)
    if not validation.valid:
        raise ValueError("; ".join(validation.errors))

    merged = copy.deepcopy(dict(base_macro))
    extras = merged.setdefault("extras", {})
    if not isinstance(extras, dict):
        raise ValueError("base macro extras must be a dict before enrichment can be attached")

    exposure_index = build_macro_exposure_index(enrichment)
    enriched_payload = copy.deepcopy(dict(enrichment))
    enriched_payload["macro_exposure_index"] = exposure_index
    enriched_payload["conflict_flags_added"] = validation.conflict_flags
    enriched_payload["theme_relationships"] = validation.theme_relationships
    enriched_payload["merge_decision"] = "MERGED_AUGMENT_ONLY"

    extras["macro_enrichment_delta"] = enriched_payload
    extras["macro_exposure_index"] = exposure_index
    extras["macro_enrichment_event_guards"] = copy.deepcopy(
        list(enrichment.get("event_guard_deltas", []))
    )
    extras["macro_enrichment_conflict_flags"] = validation.conflict_flags
    extras["macro_enrichment_theme_relationships"] = validation.theme_relationships
    extras["macro_enrichment_audit"] = build_macro_enrichment_audit(
        base_macro=base_macro,
        enrichment=enrichment,
        validation=validation,
        exposure_index=exposure_index,
    )
    extras["macro_decision_context"] = interpret_macro_decision_context(merged)

    extras["conflict_flags"] = _ordered_unique(
        _as_list(extras.get("conflict_flags")) + validation.conflict_flags
    )
    if "conflict_flags" in merged:
        merged["conflict_flags"] = _ordered_unique(
            _as_list(merged.get("conflict_flags")) + validation.conflict_flags
        )

    return merged


def build_macro_exposure_index(enrichment: Mapping[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    index: Dict[str, List[Dict[str, Any]]] = {}

    def _entry_for(base_entry: Dict[str, Any], role: str) -> Dict[str, Any]:
        entry = copy.deepcopy(base_entry)
        entry["role"] = role
        return entry

    for theme in enrichment.get("theme_deltas", []) or []:
        if not isinstance(theme, Mapping):
            continue
        theme_id = str(theme.get("theme_id") or "").strip()
        if not theme_id:
            continue

        base_entry = {
            "theme_id": theme_id,
            "directional_pressure": theme.get("directional_pressure"),
            "event_guards": list(theme.get("event_guards") or []),
            "confirmation_required": list(theme.get("confirmation_required") or []),
            "invalidation_conditions": list(theme.get("invalidation_conditions") or []),
            "merge_effect": copy.deepcopy(theme.get("merge_effect") or {}),
        }

        for ticker in _ticker_list(theme.get("beneficiary_universe")):
            _append_index_entry(index, ticker, _entry_for(base_entry, "BENEFICIARY"))

        for ticker in _ticker_list(theme.get("vulnerable_universe")):
            _append_index_entry(index, ticker, _entry_for(base_entry, "VULNERABLE"))

        context_values = []
        for key in ("context_universe", "context_only_universe", "contextual_universe"):
            context_values.extend(_ticker_list(theme.get(key)))
        for ticker in context_values:
            _append_index_entry(index, ticker, _entry_for(base_entry, "CONTEXT_ONLY"))

    hint = enrichment.get("macro_exposure_index_build")
    if isinstance(hint, Mapping):
        role_map = hint.get("ticker_role_map_hint")
        if isinstance(role_map, Mapping):
            for role, tickers in role_map.items():
                role_label = str(role or "").strip().upper()
                if role_label not in {"BENEFICIARY", "VULNERABLE", "CONTEXT_ONLY"}:
                    continue
                for ticker in _ticker_list(tickers):
                    entry = {
                        "theme_id": "MACRO_EXPOSURE_INDEX_HINT",
                        "directional_pressure": "CONTEXT",
                        "event_guards": [],
                        "confirmation_required": [],
                        "invalidation_conditions": [],
                        "merge_effect": {"source": "macro_exposure_index_build.ticker_role_map_hint"},
                        "role": role_label,
                    }
                    _append_index_entry(index, ticker, entry)

    return dict(sorted(index.items()))


def lookup_macro_exposure(macro_context: Mapping[str, Any], ticker: str) -> List[Dict[str, Any]]:
    symbol = str(ticker or "").strip().upper()
    if not symbol:
        return []

    extras = macro_context.get("extras") if isinstance(macro_context, Mapping) else {}
    if isinstance(extras, Mapping):
        index = extras.get("macro_exposure_index")
        if isinstance(index, Mapping):
            return copy.deepcopy(list(index.get(symbol, [])))
        delta = extras.get("macro_enrichment_delta")
        if isinstance(delta, Mapping):
            nested = delta.get("macro_exposure_index")
            if isinstance(nested, Mapping):
                return copy.deepcopy(list(nested.get(symbol, [])))

    top = macro_context.get("macro_exposure_index") if isinstance(macro_context, Mapping) else None
    if isinstance(top, Mapping):
        return copy.deepcopy(list(top.get(symbol, [])))
    return []


def _float_field(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _find_fung_hsieh_accuracy(macro_context: Mapping[str, Any]) -> Optional[float]:
    values: List[Any] = [
        macro_context.get("fung_hsieh_accuracy"),
        macro_context.get("fung_hsieh_model_accuracy"),
    ]
    macro_quant = macro_context.get("macro_quant_packet")
    if isinstance(macro_quant, Mapping):
        values.extend([
            macro_quant.get("fung_hsieh_accuracy"),
            macro_quant.get("fung_hsieh_model_accuracy"),
        ])

    for value in values:
        if value not in (None, ""):
            return _float_field(value)

    flags: List[str] = []
    extras = macro_context.get("extras") if isinstance(macro_context, Mapping) else {}
    if isinstance(extras, Mapping):
        flags.extend(str(v) for v in _as_list(extras.get("conflict_flags")))
        flags.extend(str(v) for v in _as_list(extras.get("macro_conflict_flags")))
    flags.extend(str(v) for v in _as_list(macro_context.get("conflict_flags")))

    for flag in flags:
        if "Fung-Hsieh" not in flag and "FUNG" not in flag.upper():
            continue
        match = re.search(r"0\.\d+", flag)
        if match:
            return _float_field(match.group(0))
    return None


def _sector_bias_for(macro_context: Mapping[str, Any], gics_sector: str = "") -> str:
    sector = str(gics_sector or "").strip().upper()
    if not sector:
        return "UNKNOWN"

    rotation = macro_context.get("sector_rotation")
    if not isinstance(rotation, Mapping):
        return "UNKNOWN"
    bias_map = rotation.get("sector_bias_map")
    if not isinstance(bias_map, Mapping):
        return "UNKNOWN"

    for key, value in bias_map.items():
        if str(key or "").strip().upper() == sector:
            return str(value or "UNKNOWN").strip().upper() or "UNKNOWN"
    return "UNKNOWN"


def interpret_macro_decision_context(
    macro_context: Mapping[str, Any],
    ticker: str = "",
    direction: str = "",
    gics_sector: str = "",
) -> Dict[str, Any]:
    """
    Commute raw macro facts into pipeline-safe decision context.

    This is deliberately stricter than the narrative enrichment. Macro may
    enhance, reduce size, or require confirmation; it may not invert direction
    solely because a call/put thesis is absent from the macro packet.
    """
    symbol = str(ticker or "").strip().upper()
    option_direction = str(direction or "").strip().upper()
    exposures = lookup_macro_exposure(macro_context, symbol) if symbol else []
    roles = set(_ordered_unique(entry.get("role") for entry in exposures))

    macro_quant = macro_context.get("macro_quant_packet")
    if not isinstance(macro_quant, Mapping):
        macro_quant = {}
    macro_confidence = _float_field(
        macro_context.get("macro_conviction", macro_quant.get("macro_confidence", 0.0))
    )
    # MACRO REDESIGN: FH accuracy re-scrape removed. Canonical signal is macro_filter.
    fung_hsieh_accuracy = None  # retained in output for schema compatibility only
    macro_filter = str(macro_context.get("macro_filter", "") or "").upper()
    trigger_required = bool(macro_context.get("trigger_required"))
    put_gate = macro_context.get("put_gate") if isinstance(macro_context.get("put_gate"), Mapping) else {}
    put_permission = str(put_gate.get("current_permission", "") or "").upper()
    sector_bias = _sector_bias_for(macro_context, gics_sector)

    no_go = "NO_GO" in macro_filter
    if no_go:
        direction_authority = "ABSTAIN"
        direction_vote = "ABSTAIN"
    elif macro_confidence < 0.70:
        direction_authority = "LIMITED"
    else:
        direction_authority = "ENABLED"

    if "BENEFICIARY" in roles and "VULNERABLE" not in roles:
        raw_vote = "CALL"
        applicability = "APPLICABLE"
    elif "VULNERABLE" in roles and "BENEFICIARY" not in roles:
        raw_vote = "PUT"
        applicability = "APPLICABLE"
    elif "CONTEXT_ONLY" in roles:
        raw_vote = "ABSTAIN"
        applicability = "CONTEXT_ONLY"
    elif sector_bias == "TAILWIND":
        raw_vote = "CALL"
        applicability = "APPLICABLE"
    elif sector_bias == "HEADWIND":
        raw_vote = "PUT"
        applicability = "APPLICABLE"
    elif sector_bias == "UNKNOWN":
        raw_vote = "ABSTAIN"
        applicability = "NOT_APPLICABLE"
    else:
        raw_vote = "ABSTAIN"
        applicability = "CONTEXT_ONLY"

    if direction_authority not in {"ABSTAIN"}:
        direction_vote = raw_vote if direction_authority != "DISABLED" else "ABSTAIN"
    confirmation_required: List[str] = []
    if direction_authority == "DISABLED":
        confirmation_required.append("STRUCTURE_FIRST_REQUIRED_MACRO_DIRECTION_DISABLED")
    # ABSTAIN = macro withholds direction vote; no confirmation required from trader
    elif direction_authority == "LIMITED":
        confirmation_required.append("LOCAL_CONFIRMATION_REQUIRED_LOW_MACRO_CONFIDENCE")
    if trigger_required:
        confirmation_required.append("BASE_MACRO_TRIGGER_REQUIRED")
    if option_direction == "PUT" and put_permission in {"BLOCKED", "RESTRICTED", "NO_GO"}:
        confirmation_required.append("PUT_GATE_DEFINED_RISK_OR_REPAIR_REQUIRED")

    if applicability == "NOT_APPLICABLE":
        alignment_state = "MACRO_NOT_APPLICABLE"
    elif not option_direction:
        alignment_state = "NO_DIRECTIONAL_MACRO_EDGE" if raw_vote == "ABSTAIN" else "MACRO_CONTEXT_AVAILABLE"
    elif option_direction == "PUT" and sector_bias == "TAILWIND":
        alignment_state = "PUT_ELEVATED_CONFIRMATION"
        confirmation_required.extend([
            "TAILWIND_SECTOR_REQUIRES_PHASE_D_OR_SELLER_CONTROL",
            "RELATIVE_SECTOR_UNDERPERFORMANCE_REQUIRED",
        ])
    elif option_direction == "CALL" and sector_bias == "HEADWIND":
        alignment_state = "CALL_ELEVATED_CONFIRMATION"
        confirmation_required.append("HEADWIND_SECTOR_REQUIRES_LOCAL_BULLISH_CONFIRMATION")
    elif raw_vote == "CALL" and option_direction == "CALL":
        alignment_state = "CALL_CONFIRMED" if direction_authority == "ENABLED" else "CALL_UNCONFIRMED_NEEDS_LOCAL_CONFIRMATION"
    elif raw_vote == "PUT" and option_direction == "PUT":
        alignment_state = "PUT_CONFIRMED" if direction_authority == "ENABLED" else "PUT_UNCONFIRMED_NEEDS_LOCAL_CONFIRMATION"
    elif raw_vote == "CALL" and option_direction == "PUT":
        alignment_state = "MACRO_CONFLICTS_PUT"
        confirmation_required.append("MACRO_CONFLICT_REQUIRES_LOCAL_BEARISH_CONFIRMATION")
    elif raw_vote == "PUT" and option_direction == "CALL":
        alignment_state = "MACRO_CONFLICTS_CALL"
        confirmation_required.append("MACRO_CONFLICT_REQUIRES_LOCAL_BULLISH_CONFIRMATION")
    else:
        alignment_state = "NO_DIRECTIONAL_MACRO_EDGE"

    trade_type = (
        "MACRO_DIRECTIONAL"
        if direction_authority == "ENABLED" and alignment_state in {"CALL_CONFIRMED", "PUT_CONFIRMED"}
        else "STRUCTURAL_SINGLE_STOCK"
    )

    reasons = []
    if no_go:
        reasons.append(
            "Macro filter is NO_GO (Fung-Hsieh sub-0.50): SIZE MODIFIER only — "
            "direction ABSTAINS. Ticker verdict unaffected."
        )
    if applicability == "NOT_APPLICABLE":
        reasons.append("Macro has no ticker/sector opinion; no direction vote is emitted.")
    if not reasons:
        reasons.append("Macro context interpreted as enhancer only; base gates preserved.")

    return {
        "macro_decision_contract_version": "macro_decision_context_v1",
        "ticker": symbol,
        "macro_alignment_state": alignment_state,
        "macro_applicability": applicability,
        "macro_direction_authority": direction_authority,
        "macro_direction_vote": direction_vote,
        "macro_raw_direction_hint": raw_vote,
        "macro_can_enhance_existing_direction": True,
        "macro_can_invert_direction": False,
        "structure_first_required": direction_authority in {"DISABLED", "ABSTAIN"} or applicability == "NOT_APPLICABLE",
        "trade_type_classification": trade_type,
        "macro_confidence": macro_confidence,
        "fung_hsieh_accuracy": fung_hsieh_accuracy,
        "macro_filter": macro_filter,
        "macro_trigger_required": trigger_required,
        "macro_size_cap": _float_field(macro_context.get("size_multiplier"), 1.0),
        "macro_put_gate_permission": put_permission,
        "macro_sector_bias": sector_bias,
        "macro_confirmation_required": _ordered_unique(confirmation_required),
        "macro_interpretation_reason": " ".join(reasons),
    }


def candidate_macro_enrichment_audit(macro_context: Mapping[str, Any], ticker: str) -> Dict[str, Any]:
    """Return flat, audit-friendly macro enrichment context for one plain ticker."""
    symbol = str(ticker or "").strip().upper()
    exposures = lookup_macro_exposure(macro_context, symbol)

    extras = macro_context.get("extras") if isinstance(macro_context, Mapping) else {}
    if not isinstance(extras, Mapping):
        extras = {}

    relationships = extras.get("macro_enrichment_theme_relationships")
    if not isinstance(relationships, Mapping):
        relationships = {}

    conflict_flags = _ordered_unique(
        _as_list(extras.get("macro_enrichment_conflict_flags"))
        + _as_list(extras.get("conflict_flags"))
        + _as_list(macro_context.get("conflict_flags") if isinstance(macro_context, Mapping) else [])
    )

    theme_ids = _ordered_unique(entry.get("theme_id") for entry in exposures)
    roles = _ordered_unique(entry.get("role") for entry in exposures)
    event_guards = _ordered_unique(
        guard
        for entry in exposures
        for guard in _as_list(entry.get("event_guards"))
    )
    confirmations = _ordered_unique(
        item
        for entry in exposures
        for item in _as_list(entry.get("confirmation_required"))
    )
    # Enforce do_not_unblock_put_gate: when any matched theme declares this flag,
    # stamp PUT_GATE_DELTA_LOCK so the EOD engine can gate PUT candidates even when
    # the base macro has no explicit put_gate.current_permission block.
    _put_gate_locked = any(
        isinstance(entry.get("merge_effect"), Mapping) and entry["merge_effect"].get("do_not_unblock_put_gate")
        for entry in exposures
    )
    if _put_gate_locked and "PUT_GATE_DELTA_LOCK" not in confirmations:
        confirmations = list(confirmations) + ["PUT_GATE_DELTA_LOCK"]
    directional_pressure = _ordered_unique(entry.get("directional_pressure") for entry in exposures)
    relationship_values = _ordered_unique(relationships.get(theme_id) for theme_id in theme_ids)

    if not exposures:
        pressure_label = "NO_ENRICHMENT_MATCH"
        pressure_score = 0.0
    elif conflict_flags or confirmations:
        pressure_label = "REQUIRES_CONFIRMATION"
        pressure_score = 0.0
    elif "BENEFICIARY" in roles and "VULNERABLE" not in roles:
        pressure_label = "BENEFICIARY_CONTEXT"
        pressure_score = 0.05
    elif "VULNERABLE" in roles and "BENEFICIARY" not in roles:
        pressure_label = "VULNERABLE_CONTEXT"
        pressure_score = -0.05
    else:
        pressure_label = "MIXED_CONTEXT"
        pressure_score = 0.0

    if exposures:
        audit_note = (
            f"Ticker {symbol} was plain-ingested. Macro exposure matched "
            f"{', '.join(theme_ids) or 'UNKNOWN'} as {', '.join(roles) or 'UNKNOWN'}. "
            "Base macro gates preserved; confirmation required before promotion."
        )
    else:
        audit_note = f"Ticker {symbol} was plain-ingested. No macro enrichment exposure match."

    decision_context = interpret_macro_decision_context(macro_context, symbol)

    return {
        "macro_enrichment_theme_count": len(exposures),
        "macro_enrichment_theme_ids": theme_ids,
        "macro_enrichment_roles": roles,
        "macro_enrichment_event_guards": event_guards,
        "macro_enrichment_confirmation_required": confirmations,
        "macro_enrichment_directional_pressure": directional_pressure,
        "macro_enrichment_conflict_flags": conflict_flags,
        "macro_enrichment_theme_relationships": relationship_values,
        "macro_enrichment_pressure_label": pressure_label,
        "macro_enrichment_pressure_score": pressure_score,
        "macro_enrichment_gate_preserved": True,
        "macro_enrichment_audit_note": audit_note,
        **decision_context,
    }


def build_macro_enrichment_audit(
    base_macro: Mapping[str, Any],
    enrichment: Mapping[str, Any],
    validation: ValidationResult,
    exposure_index: Mapping[str, List[Mapping[str, Any]]],
) -> Dict[str, Any]:
    protected_present = sorted(key for key in PROTECTED_MACRO_FIELDS if key in base_macro)
    theme_records = []
    for theme in enrichment.get("theme_deltas", []) or []:
        if not isinstance(theme, Mapping):
            continue
        theme_records.append(
            {
                "batch_id": enrichment.get("batch_id"),
                "source": enrichment.get("source"),
                "contract_version": enrichment.get("contract_version"),
                "theme_id": theme.get("theme_id"),
                "delta_type": theme.get("delta_type"),
                "event_guard_ids": list(theme.get("event_guards") or []),
                "merge_decision": "MERGED_AUGMENT_ONLY",
                "protected_fields_preserved": protected_present,
            }
        )

    entry_count = sum(len(entries) for entries in exposure_index.values())
    return {
        "batch_id": enrichment.get("batch_id"),
        "source": enrichment.get("source"),
        "contract_version": enrichment.get("contract_version"),
        "target_macro_contract_version": enrichment.get("target_macro_contract_version"),
        "merge_decision": "MERGED_AUGMENT_ONLY",
        "protected_fields_preserved": protected_present,
        "conflict_flags_added": validation.conflict_flags,
        "exposure_index_entries_created": entry_count,
        "exposure_index_tickers_created": len(exposure_index),
        "theme_relationships": validation.theme_relationships,
        "theme_audit": theme_records,
    }


def detect_enrichment_conflicts(
    base_macro: Mapping[str, Any],
    enrichment: Mapping[str, Any],
) -> List[str]:
    flags: List[str] = []
    avoid_text = _upper_blob(
        base_macro.get("sector_avoid"),
        base_macro.get("sector_tilt"),
        base_macro.get("sector_rotation"),
    )
    energy_is_avoided = "XLE" in avoid_text or "ENERGY" in avoid_text

    for theme in enrichment.get("theme_deltas", []) or []:
        if not isinstance(theme, Mapping):
            continue
        theme_id = str(theme.get("theme_id") or "").upper()
        theme_text = _upper_blob(
            theme_id,
            theme.get("theme_name"),
            theme.get("sectors_exposed"),
            theme.get("etf_read_through"),
            theme.get("delta_type"),
        )
        if energy_is_avoided and (
            "ENERGY_SHOCK" in theme_id or "XLE" in theme_text or "ENERGY" in theme_text
        ):
            flags.append("ENERGY_THEME_VS_BASE_XLE_AVOID")

    return _ordered_unique(flags)


def detect_theme_relationships(
    base_macro: Mapping[str, Any],
    enrichment: Mapping[str, Any],
) -> Dict[str, str]:
    relationships: Dict[str, str] = {}
    lead_text = _upper_blob(
        base_macro.get("sector_lead"),
        base_macro.get("sector_tilt"),
        base_macro.get("sector_rotation"),
    )
    tech_leadership = any(token in lead_text for token in ("XLK", "QQQ", "TECH", "INFORMATION TECHNOLOGY"))

    for theme in enrichment.get("theme_deltas", []) or []:
        if not isinstance(theme, Mapping):
            continue
        theme_id = str(theme.get("theme_id") or "").strip()
        if not theme_id:
            continue
        theme_text = _upper_blob(theme_id, theme.get("theme_name"), theme.get("sectors_exposed"))
        if tech_leadership and ("AI" in theme_text or "SEMICONDUCTOR" in theme_text):
            relationships[theme_id] = "STRENGTHENS_EXISTING_TECH_LEADERSHIP"
        elif "CONTEXT_ONLY" in _upper_blob(theme.get("delta_type")):
            relationships[theme_id] = "CONTEXT_ONLY_UNTIL_CONFIRMED"

    return relationships


def _append_index_entry(index: Dict[str, List[Dict[str, Any]]], ticker: str, entry: Dict[str, Any]) -> None:
    entries = index.setdefault(ticker, [])
    key = (entry.get("theme_id"), entry.get("role"))
    existing = {(item.get("theme_id"), item.get("role")) for item in entries}
    if key not in existing:
        entries.append(entry)


def _ticker_list(value: Any) -> List[str]:
    return [token.upper() for token in _as_list(value) if token]


def _as_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, tuple):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, set):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return []
        if raw.startswith("["):
            try:
                loaded = json.loads(raw)
                return _as_list(loaded)
            except Exception:
                pass
        return [part.strip() for part in raw.replace("|", ",").split(",") if part.strip()]
    return [str(value).strip()] if str(value).strip() else []


def _ordered_unique(values: Iterable[str]) -> List[str]:
    seen = set()
    out: List[str] = []
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
    return out


def _upper_blob(*values: Any) -> str:
    parts: List[str] = []

    def walk(value: Any) -> None:
        if value is None:
            return
        if isinstance(value, Mapping):
            for key, item in value.items():
                parts.append(str(key))
                walk(item)
            return
        if isinstance(value, (list, tuple, set)):
            for item in value:
                walk(item)
            return
        parts.append(str(value))

    for item in values:
        walk(item)
    return " ".join(parts).upper()
