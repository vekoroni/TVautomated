#!/usr/bin/env python3
"""
AVSHUNTER Phase 4 handoff truth packet.

The packet is the production baton: receive, validate, enrich, preserve,
and pass forward committed fields without silent downgrade.
"""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Mapping, Optional


FIELD_STATUSES = {"CONFIRMED", "PARTIAL", "INFERRED", "MISSING", "STALE", "CONFLICTED", "INVALID"}
PACKET_STATUSES = {"VALID", "PARTIAL", "DEGRADED", "BLOCKED", "CONFLICTED"}
MISSING_TOKENS = {"", "NONE", "UNKNOWN", "MISSING", "N/A", "NAN", "NULL"}

PRIORITY_LIVE_EXECUTION = 100
PRIORITY_DOWNSTREAM_VALIDATION = 90
PRIORITY_VANGUARD_ACTUARIAL = 80
PRIORITY_OPTIONS_INTELLIGENCE = 75
PRIORITY_EIL_PSE = 70
PRIORITY_MACRO_QUANT = 65
PRIORITY_DISCOVERY = 60
PRIORITY_PACKAGE_EXISTING = 50
PRIORITY_INFERRED = 40
PRIORITY_FALLBACK = 10

SOVEREIGN_GATES = {
    "PSE_FATAL_BLOCK",
    "EXECUTION_INVALID",
    "MACRO_CONFLICTED",
    "LIVE_VALIDATION_MISSING",
    "MISSING_TRIGGER_FULL_EXECUTE",
    "EVENING_LIVE_VALIDATION_CLAIM",
}

TRUTH_PACKET_META_FIELDS = [
    "truth_packet_status",
    "truth_packet_conflict_count",
    "truth_packet_warning_count",
    "truth_packet_error_count",
    "handoff_integrity_status",
    "handoff_integrity_notes",
    "verdict_coherence_status",
    "verdict_coherence_notes",
]

SCANNER_FIELD_NAMES = [
    "scanner_source",
    "scanner_run_id",
    "scanner_timestamp_utc",
    "scanner_signal_type",
    "scanner_score",
    "scanner_reason_codes",
    "scanner_pattern_tags",
    "scanner_sector",
    "scanner_price",
    "scanner_volume",
    "scanner_rvol",
    "scanner_watchlist_lane",
    "scanner_data_quality",
    "scanner_confidence",
    "scanner_age_hrs",
    "scanner_decision",
    # Existing production aliases from avshunter_universe_scanner.py / VMS.
    "vms_score",
    "vms_decision",
    "vol_spread",
    "iv_rank",
    "iv_rank_source",
    "iv_rank_confidence",
    "iv_current",
    "rv",
    "hv_30d",
    "term_slope",
    "skew",
    "pipeline_tag",
]

PHYSICS_FIELD_NAMES = [
    "physics_state_id",
    "market_energy_score",
    "compression_energy",
    "directional_force",
    "force_alignment_score",
    "trend_inertia",
    "volatility_pressure",
    "entropy_score",
    "regime_instability_score",
    "phase_transition_probability",
    "shock_sensitivity",
    "liquidity_friction_score",
    "hidden_state_label",
    "state_transition_label",
    "future_state_5d",
    "future_state_10d",
    "future_state_20d",
    "transition_success_5d",
    "transition_success_10d",
    "transition_success_20d",
    "physics_data_quality",
    "physics_defaulted_fields",
    "physics_degraded_reason",
]

TRUTH_PACKET_FIELD_GROUPS = {
    "identity": ["ticker", "direction", "run_id", "run_mode", "asof_date", "source_universe"],
    "scanner": SCANNER_FIELD_NAMES,
    "physics": PHYSICS_FIELD_NAMES,
    "macro": [
        "macro_regime_label", "regime_drift_status", "macro_freshness_status",
        "macro_age_hours", "macro_confidence", "macro_data_quality",
        "risk_on_off_score", "macro_conviction_score", "net_liquidity_score",
        "liquidity_pulse", "vix_regime_label", "vix_regime_score",
        "vix_contango", "vix_structure_label", "vol_mode", "rates_impulse",
        "usd_state", "credit_state", "credit_risk_score", "gex_regime_score",
        "dealer_gamma_state", "sector_rotation_state", "leading_sectors",
        "lagging_sectors", "preferred_sectors", "avoid_sectors",
        "ticker_sector_alignment", "ticker_sector_alignment_score",
        "macro_preferred_horizon", "primary_bucket", "equity_drawer_active",
        "bucket_clarity_scores", "macro_execution_caution",
    ],
    "discovery": [
        "discovery_score", "composite_score", "signal_type", "momentum_tier",
        "lane_tag", "reasons_top3", "predictability_score", "bmps", "flow_score",
    ],
    "vanguard": [
        "state_v2", "state_hash", "behaviour_state_key", "behaviour_state_hash",
        "actuarial_match_type", "actuarial_ev_weight",
        "future_momentum_bucket", "preferred_horizon",
        "layer2__preferred_horizon", "layer2__state_match_method",
        "layer2__state_match_stage", "layer2__state_match_dimensions",
        "layer2__state_match_quality", "layer2__state_match_is_exact",
        "layer2__sample_confidence_bucket", "actuarial_hit_rate",
        "actuarial_ev", "actuarial_sample_size", "layer2__sample_size",
    ],
    "options": [
        "option_symbol", "recommended_contract", "option_direction",
        "options_direction", "expiration", "expiry", "dte", "delta",
        "contract_delta", "iv", "iv_percentile", "spread_pct_mid",
        "contract_spread_pct", "breakeven", "breakeven_pct",
        "breakeven_pass_live", "runway_to_wall_pct", "gamma_flip_distance",
        "gamma_flip_gap_pct", "dealer_gamma_state", "option_expected_value",
        "ev_adjusted", "option_rr", "rr_options", "premium_mid", "premium",
        "pcr_vol", "dw_pcr_vol", "pcr_vol_status", "pcr_vol_missing_reason",
        "direction_conflict_status", "direction_conflict_reason",
    ],
    "eil_pse": [
        "eil_v3_verdict", "eil_composite_score", "eil_liquidity_score",
        "eil_gex_score", "pse_execution_mode", "pse_block_reason",
        "pse_score", "trigger_primary", "trigger_quality", "trigger_codes",
    ],
    "mcmillan": [
        "iv_gex_entry_quality", "iv_gex_entry_quality_label",
        "iv_gex_entry_quality_narrative", "gamma_island_on_path",
        "gamma_island_label", "gamma_island_level", "gamma_island_distance_pct",
        "gamma_island_source", "gamma_island_note",
        "move_theta_ratio", "move_theta_margin_label", "move_theta_narrative",
        "crowd_arrival_state", "crowd_arrival_score",
        "crowd_arrival_components", "crowd_arrival_narrative",
    ],
    "catalyst": [
        "catalyst_engine_version", "catalyst_detected", "catalyst_type",
        "catalyst_date", "days_to_catalyst", "catalyst_inside_dte",
        "catalyst_truth_score", "catalyst_binary_score",
        "catalyst_direction_bias", "catalyst_source_count",
        "catalyst_data_quality", "catalyst_trade_class",
        "event_convexity_score", "cheap_convexity_flag",
        "catalyst_liquidity_ok", "catalyst_alignment_label",
        "catalyst_reason_codes", "catalyst_source_fields",
        "catalyst_manual_upload", "catalyst_requires_live_confirmation",
        "catalyst_event_status", "catalyst_source_tier",
        "catalyst_source_url", "catalyst_ticker_role",
        "catalyst_expected_impact", "catalyst_failure_risk",
    ],
    "eod_monetisation": [
        "eod_candidate_status", "eod_candidate_reason", "eod_dropoff_reason",
        "eod_candidate_permission", "candidate_size", "sizing_policy",
        "live_capital_permission", "eod_live_capital_permission",
        "monetisation_fit_score", "monetisation_fit_label",
        "primary_direction", "direction_reroute_status",
        "direction_decision_reason", "direction_call_score",
        "direction_put_score", "selected_contract_side",
    ],
    "contract_repair": [
        "contract_quality_score", "contract_repair_status",
        "contract_repair_attempted", "contract_repair_required", "contract_repair_reason",
        "contract_spread_pct_eod", "contract_oi", "contract_volume",
        "contract_delta",
    ],
    "morning_validation": [
        "live_validation_state", "morning_execution_permission",
        "morning_execution_route", "execution_permission", "validation_score",
        "morning_execution_lane", "morning_entry_action",
        "morning_unlock_condition", "thesis_validity_state",
        "entry_timing_state", "contract_tradability_state",
        "direction_alignment_status",
        "validation_confidence", "rejection_reason", "wait_reason",
        "upgrade_downgrade_reason", "contract_liquidity_confirmed",
        "spread_confirmed", "breakeven_confirmed", "direction_confirmed",
    ],
    "execution": [
        "thesis_decision", "execution_mode", "verdict_coherence_status",
        "verdict_coherence_notes", "handoff_integrity_status",
        "handoff_integrity_notes", "is_live_execution_validated",
        "final_rank", "final_score", "final_notes", "fd_verdict",
    ],
}

TRUTH_PACKET_CARRY_FIELDS = list(dict.fromkeys(
    field_name
    for group_fields in TRUTH_PACKET_FIELD_GROUPS.values()
    for field_name in group_fields
))


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def is_missing_value(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, float):
        return math.isnan(value)
    if hasattr(value, "item"):
        try:
            return is_missing_value(value.item())
        except Exception:
            pass
    if isinstance(value, str):
        return value.strip().upper() in MISSING_TOKENS
    return False


def normalise_status(status: str) -> str:
    value = str(status or "CONFIRMED").strip().upper()
    return value if value in FIELD_STATUSES else "CONFIRMED"


def _safe_confidence(value: Any) -> float:
    try:
        v = float(value)
    except (TypeError, ValueError):
        v = 1.0
    if math.isnan(v):
        v = 0.0
    return max(0.0, min(1.0, v))


def _json_safe(value: Any) -> Any:
    if hasattr(value, "item"):
        try:
            return _json_safe(value.item())
        except Exception:
            pass
    if isinstance(value, float) and math.isnan(value):
        return None
    if isinstance(value, (dict, list, tuple)):
        return json.loads(json.dumps(value, default=str, ensure_ascii=False))
    return value


def _csv_safe(value: Any) -> Any:
    value = _json_safe(value)
    if isinstance(value, (dict, list)):
        return json.dumps(value, sort_keys=True, ensure_ascii=False)
    return value


def _status_rank(status: str) -> int:
    return {
        "CONFIRMED": 6,
        "PARTIAL": 5,
        "INFERRED": 4,
        "STALE": 3,
        "CONFLICTED": 2,
        "INVALID": 1,
        "MISSING": 0,
    }.get(normalise_status(status), 0)


@dataclass
class HandoffField:
    name: str
    value: Any
    status: str = "CONFIRMED"
    source: str = "UNKNOWN"
    updated_at_utc: Optional[str] = None
    confidence: float = 1.0
    priority: int = PRIORITY_PACKAGE_EXISTING
    notes: Optional[str] = None

    def __post_init__(self) -> None:
        self.status = normalise_status(self.status)
        self.confidence = _safe_confidence(self.confidence)
        self.priority = int(self.priority or PRIORITY_PACKAGE_EXISTING)
        if self.updated_at_utc is None:
            self.updated_at_utc = utc_now_iso()

    def to_json_dict(self) -> Dict[str, Any]:
        out = asdict(self)
        out["value"] = _json_safe(out["value"])
        return out


def make_field(
    name: str,
    value: Any,
    source: str,
    status: str = "CONFIRMED",
    confidence: float = 1.0,
    priority: int = PRIORITY_PACKAGE_EXISTING,
    notes: Optional[str] = None,
) -> HandoffField:
    return HandoffField(
        name=name,
        value=value,
        status=status,
        source=source,
        updated_at_utc=utc_now_iso(),
        confidence=confidence,
        priority=priority,
        notes=notes,
    )


@dataclass
class HandoffTruthPacket:
    run_id: str = ""
    ticker: Optional[str] = None
    direction: Optional[str] = None
    run_mode: str = "UNKNOWN"
    created_at_utc: str = field(default_factory=utc_now_iso)
    updated_at_utc: str = field(default_factory=utc_now_iso)
    packet_status: str = "VALID"
    fields: Dict[str, HandoffField] = field(default_factory=dict)
    conflicts: List[Dict[str, Any]] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    def add_field(
        self,
        name: str,
        value: Any,
        source: str,
        status: str = "CONFIRMED",
        confidence: float = 1.0,
        priority: int = PRIORITY_PACKAGE_EXISTING,
        notes: Optional[str] = None,
    ) -> None:
        new = make_field(name, value, source, status, confidence, priority, notes)
        current = self.fields.get(name)
        self.updated_at_utc = utc_now_iso()

        if current is None:
            self.fields[name] = new
            return

        if is_missing_value(new.value):
            return
        if is_missing_value(current.value):
            self.fields[name] = new
            return
        if current.value == new.value:
            if new.priority > current.priority or _status_rank(new.status) > _status_rank(current.status):
                self.fields[name] = new
            return

        current_confirmed = current.status == "CONFIRMED"
        new_weaker_or_stale = new.status in {"INFERRED", "MISSING", "STALE", "INVALID", "CONFLICTED"}
        if current_confirmed and new_weaker_or_stale:
            return

        if new.status == "CONFIRMED" and current.status == "CONFIRMED" and abs(new.priority - current.priority) <= 10:
            self.conflicts.append({
                "field": name,
                "old_value": _json_safe(current.value),
                "new_value": _json_safe(new.value),
                "old_source": current.source,
                "new_source": new.source,
                "reason": "confirmed_value_conflict_preserved_original",
                "timestamp": utc_now_iso(),
            })
            self.packet_status = "CONFLICTED"
            return

        if new.priority > current.priority and _status_rank(new.status) >= _status_rank(current.status):
            self.conflicts.append({
                "field": name,
                "old_value": _json_safe(current.value),
                "new_value": _json_safe(new.value),
                "old_source": current.source,
                "new_source": new.source,
                "reason": "higher_priority_override",
                "timestamp": utc_now_iso(),
            })
            self.fields[name] = new
            return

        if new.priority > current.priority:
            self.fields[name] = new

    def get(self, name: str, default: Any = None) -> Any:
        field_obj = self.fields.get(name)
        return field_obj.value if field_obj is not None else default

    def merge(self, other_packet: "HandoffTruthPacket") -> "HandoffTruthPacket":
        for field_obj in other_packet.fields.values():
            self.add_field(
                field_obj.name,
                field_obj.value,
                field_obj.source,
                field_obj.status,
                field_obj.confidence,
                field_obj.priority,
                field_obj.notes,
            )
        self.conflicts.extend(other_packet.conflicts)
        self.warnings.extend(other_packet.warnings)
        self.errors.extend(other_packet.errors)
        self.finalise()
        return self

    def validate_required(self, required_fields: Iterable[str]) -> Dict[str, List[str]]:
        missing = []
        invalid = []
        conflicted = []
        conflict_fields = {str(c.get("field")) for c in self.conflicts}
        for name in required_fields:
            field_obj = self.fields.get(name)
            if field_obj is None or is_missing_value(field_obj.value):
                missing.append(name)
            elif field_obj.status == "INVALID":
                invalid.append(name)
            elif field_obj.status == "CONFLICTED" or name in conflict_fields:
                conflicted.append(name)
        return {"missing": missing, "invalid": invalid, "conflicted": conflicted}

    def apply_sovereign_gate(self, gate_name: str, gate_status: str, reason: str, source: str) -> None:
        gate = str(gate_name or "").strip().upper()
        status = str(gate_status or "").strip().upper()
        msg = f"{gate}:{status}:{reason}"
        if gate in SOVEREIGN_GATES and status in {"BLOCKED", "FATAL_BLOCK", "INVALID", "MISSING", "CONFLICTED"}:
            self.errors.append(msg)
            self.packet_status = "BLOCKED" if gate in {"EIL_BLOCKED", "PSE_FATAL_BLOCK", "EXECUTION_INVALID"} else "DEGRADED"
        else:
            self.warnings.append(msg)
        self.add_field("last_sovereign_gate", gate, source, status="CONFIRMED", priority=PRIORITY_DOWNSTREAM_VALIDATION)
        self.add_field("last_sovereign_gate_reason", reason, source, status="CONFIRMED", priority=PRIORITY_DOWNSTREAM_VALIDATION)

    def finalise(self) -> "HandoffTruthPacket":
        if self.errors:
            self.packet_status = "BLOCKED" if any("FATAL_BLOCK" in e or "BLOCKED" in e for e in self.errors) else "DEGRADED"
        elif self.conflicts:
            self.packet_status = "CONFLICTED"
        elif self.warnings:
            self.packet_status = "PARTIAL"
        else:
            self.packet_status = "VALID"
        return self

    def to_flat_dict(self, prefix_optional: bool = False) -> Dict[str, Any]:
        prefix = "truth__" if prefix_optional else ""
        self.finalise()
        out = {
            "truth_packet_status": self.packet_status,
            "truth_packet_conflict_count": len(self.conflicts),
            "truth_packet_warning_count": len(self.warnings),
            "truth_packet_error_count": len(self.errors),
            "handoff_integrity_status": "CONFLICTED" if self.conflicts else "OK",
            "handoff_integrity_notes": " | ".join(self.warnings + self.errors),
            "verdict_coherence_status": "BLOCKED" if self.errors else "OK",
            "verdict_coherence_notes": " | ".join(self.errors),
        }
        for name, field_obj in self.fields.items():
            if not prefix_optional and name in TRUTH_PACKET_META_FIELDS:
                continue
            out[f"{prefix}{name}"] = _csv_safe(field_obj.value)
        return out

    def to_json_dict(self) -> Dict[str, Any]:
        self.finalise()
        return {
            "run_id": self.run_id,
            "ticker": self.ticker,
            "direction": self.direction,
            "run_mode": self.run_mode,
            "created_at_utc": self.created_at_utc,
            "updated_at_utc": self.updated_at_utc,
            "packet_status": self.packet_status,
            "fields": {name: f.to_json_dict() for name, f in self.fields.items()},
            "conflicts": _json_safe(self.conflicts),
            "warnings": list(self.warnings),
            "errors": list(self.errors),
        }

    @classmethod
    def from_row(
        cls,
        row: Mapping[str, Any],
        source: str,
        priority: int = PRIORITY_PACKAGE_EXISTING,
        run_id: str = "",
        run_mode: str = "UNKNOWN",
    ) -> "HandoffTruthPacket":
        pkt = cls(
            run_id=str(row.get("run_id") or run_id or ""),
            ticker=str(row.get("ticker") or "").strip().upper() or None,
            direction=str(row.get("direction") or row.get("options_direction") or "").strip() or None,
            run_mode=run_mode,
        )
        for name in TRUTH_PACKET_CARRY_FIELDS:
            if name in row:
                status = "MISSING" if is_missing_value(row.get(name)) else "CONFIRMED"
                pkt.add_field(name, row.get(name), source, status=status, priority=priority)
        pkt._apply_row_coherence(row, source)
        pkt.finalise()
        return pkt

    def _apply_row_coherence(self, row: Mapping[str, Any], source: str) -> None:
        eil = str(row.get("eil_v3_verdict") or "").upper()
        thesis = str(row.get("thesis_decision") or row.get("fd_verdict") or "").upper()
        exec_mode = str(row.get("execution_mode") or row.get("pse_execution_mode") or "").upper()
        trigger = str(row.get("trigger_primary") or "").strip().upper()
        pse_mode = str(row.get("pse_execution_mode") or "").upper()
        live_validated = str(row.get("is_live_execution_validated") or "").upper() in {"TRUE", "1", "YES"}

        if eil in {"BLOCKED", "BLOCK"}:
            # DOI authority contract: EIL is preserved as evidence but may not
            # invalidate or suppress the governed ticker thesis.
            self.warnings.append("EIL_ADVISORY_BLOCKED: retained for human review")
        if pse_mode == "FATAL_BLOCK" and exec_mode in {"FULL_EXECUTE", "REDUCED_EXECUTE", "LIVE_EXECUTE"}:
            self.apply_sovereign_gate("PSE_FATAL_BLOCK", "FATAL_BLOCK", "PSE FATAL_BLOCK cannot execute", source)
        if exec_mode == "FULL_EXECUTE" and trigger in {"", "NONE", "NAN", "UNKNOWN", "MISSING"}:
            self.apply_sovereign_gate("MISSING_TRIGGER_FULL_EXECUTE", "BLOCKED", "Missing trigger cannot FULL_EXECUTE", source)
        if self.run_mode == "EVENING" and live_validated:
            self.apply_sovereign_gate("EVENING_LIVE_VALIDATION_CLAIM", "INVALID", "Evening run cannot claim live validation", source)
        if str(row.get("macro_data_quality") or "").upper() == "CONFLICTED":
            self.apply_sovereign_gate("MACRO_CONFLICTED", "CONFLICTED", "Macro data quality conflicted", source)
        prior_handoff = str(row.get("handoff_integrity_status") or "").strip().upper()
        if prior_handoff in {"BLOCKED", "CONFLICTED", "FAILED", "INVALID"}:
            self.apply_sovereign_gate(
                "EXECUTION_INVALID",
                "INVALID",
                f"Upstream handoff_integrity_status={prior_handoff}",
                source,
            )
        prior_verdict = str(row.get("verdict_coherence_status") or "").strip().upper()
        if prior_verdict in {"BLOCKED", "CONFLICTED", "FAILED", "INVALID"}:
            self.apply_sovereign_gate(
                "EXECUTION_INVALID",
                "INVALID",
                f"Upstream verdict_coherence_status={prior_verdict}",
                source,
            )
        if str(row.get("equity_drawer_active") or "").upper() in {"TRUE", "1", "YES"}:
            self.warnings.append("EQUITY_DRAWER_ACTIVE_REQUIRES_STRONG_CONFIRMATION")


def build_truth_packet_from_row(
    row: Mapping[str, Any],
    source: str,
    priority: int = PRIORITY_PACKAGE_EXISTING,
    run_id: str = "",
    run_mode: str = "UNKNOWN",
) -> HandoffTruthPacket:
    return HandoffTruthPacket.from_row(row, source=source, priority=priority, run_id=run_id, run_mode=run_mode)


def enrich_row_with_truth_packet(
    row: Mapping[str, Any],
    source: str,
    priority: int = PRIORITY_PACKAGE_EXISTING,
    run_id: str = "",
    run_mode: str = "UNKNOWN",
) -> Dict[str, Any]:
    out = dict(row)
    packet = build_truth_packet_from_row(out, source=source, priority=priority, run_id=run_id, run_mode=run_mode)
    out.update(packet.to_flat_dict())
    return out


def enrich_dataframe_with_truth_packets(
    df: Any,
    source: str,
    priority: int = PRIORITY_PACKAGE_EXISTING,
    run_id: str = "",
    run_mode: str = "UNKNOWN",
) -> Any:
    if df is None or not hasattr(df, "iterrows"):
        return df
    rows = [
        enrich_row_with_truth_packet(row.to_dict(), source=source, priority=priority, run_id=run_id, run_mode=run_mode)
        for _, row in df.iterrows()
    ]
    try:
        import pandas as pd
        return pd.DataFrame(rows)
    except Exception:
        return rows


def packet_json_from_row(
    row: Mapping[str, Any],
    source: str,
    priority: int = PRIORITY_PACKAGE_EXISTING,
    run_id: str = "",
    run_mode: str = "UNKNOWN",
) -> Dict[str, Any]:
    return build_truth_packet_from_row(row, source=source, priority=priority, run_id=run_id, run_mode=run_mode).to_json_dict()
