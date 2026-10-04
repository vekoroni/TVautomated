"""Point-in-time C5 description from frozen pre-option Discovery observations.

The packet is deliberately not a probability model or option valuation. A
missing governed fact remains missing; option-stage targets and contracts are
never read to repair a ticker thesis.
"""

from __future__ import annotations

import math
import json
from datetime import date, datetime, timezone
from typing import Mapping, Sequence

from domain.ticker_forecast import ForecastDirection, ForecastState, TickerForecast


PACKET_VERSION = "ticker_forecast_descriptive_v1"


# Structural target sources C5 accepts, by name (audit finding 5, 1 Oct 2026): a prior-range
# extreme is a structural level and is no longer relabelled as WYCKOFF upstream.
STRUCTURAL_TARGET_SOURCES = frozenset({"WYCKOFF", "PRIOR_RANGE_EXTREME"})


def _positive(value: object) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and number > 0 else None


def _candidate_geometry_json(source: Mapping[str, object]) -> str | None:
    """Both structural candidates as published by Discovery (display only)."""
    if not any(str(key).startswith(("bull_", "bear_")) for key in source):
        return None
    geometry = {}
    for side in ("BULL", "BEAR"):
        prefix = side.lower()
        geometry[side] = {
            "geometry_status": str(source.get(f"{prefix}_geometry_status") or "").strip() or None,
            "invalidation": _positive(source.get(f"{prefix}_invalidation")),
            "target_state": str(source.get(f"{prefix}_target_state") or "").strip() or None,
            "target": _positive(source.get(f"{prefix}_target")),
        }
    return json.dumps(geometry, sort_keys=True, separators=(",", ":"))


def build_descriptive_packet(
    run_id: str,
    evidence_session: str,
    as_of_utc: str,
    discovery_rows: Sequence[Mapping[str, object]],
    *,
    discovery_sha256: str,
    vanguard_rows: Sequence[Mapping[str, object]] = (),
    vanguard_rejections: Sequence[Mapping[str, object]] = (),
    vanguard_sha256: str | None = None,
) -> dict:
    """Describe every Discovery row without an option-dependent fallback."""
    if not run_id:
        raise ValueError("run_id is required")
    date.fromisoformat(evidence_session)
    try:
        cut = datetime.fromisoformat(as_of_utc.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("as_of_utc must be an ISO timestamp") from error
    if cut.tzinfo is None:
        raise ValueError("as_of_utc must be timezone-aware")
    if cut.astimezone(timezone.utc).date() < date.fromisoformat(evidence_session):
        raise ValueError("as_of_utc precedes evidence_session")
    if len(discovery_sha256) != 64 or any(ch not in "0123456789abcdef" for ch in discovery_sha256.lower()):
        raise ValueError("discovery_sha256 must be a SHA-256 digest")
    if vanguard_sha256 is not None and (
        len(vanguard_sha256) != 64
        or any(ch not in "0123456789abcdef" for ch in vanguard_sha256.lower())
    ):
        raise ValueError("vanguard_sha256 must be a SHA-256 digest")
    if vanguard_rows and not vanguard_sha256:
        raise ValueError("Vanguard rows require source hash")
    vanguard: dict[str, Mapping[str, object]] = {}
    for row in vanguard_rows:
        key = str(row.get("ticker") or "").strip().upper()
        if not key or key in vanguard:
            raise ValueError("Vanguard ticker missing or duplicate")
        vanguard[key] = row
    rejected: dict[str, str] = {}
    for row in vanguard_rejections:
        key = str(row.get("ticker") or "").strip().upper()
        if not key or key in rejected or key in vanguard:
            raise ValueError("Vanguard rejection identity missing, duplicate or conflicting")
        rejected[key] = str(row.get("reason_code") or "UNKNOWN")

    if vanguard_sha256 is not None:
        discovery_ids = [str(row.get("ticker") or "").strip().upper() for row in discovery_rows]
        if len(set(discovery_ids)) != len(discovery_ids) or set(discovery_ids) != set(vanguard) | set(rejected):
            raise ValueError("Vanguard pass/reject identities do not partition Discovery")

    seen: set[str] = set()
    output: list[dict] = []
    for source in discovery_rows:
        ticker = str(source.get("ticker") or "").strip().upper()
        if not ticker:
            raise ValueError("Discovery ticker is missing")
        if ticker in seen:
            raise ValueError(f"duplicate ticker: {ticker}")
        seen.add(ticker)
        base = {
            "ticker": ticker,
            "forecast_version": "ticker_forecast_v2",
            "forecast_state": ForecastState.DATA_INSUFFICIENT.value,
            "forecast_direction": None,
            "forecast_reference_spot": None,
            "forecast_target_spot": None,
            "forecast_invalidation_spot": None,
            "forecast_thesis_id": None,
            "forecast_reason": None,
            "c4_reliability_state": "NOT_ESTIMABLE",
            "c8_valuation_state": "NOT_VALUED_STATISTICAL_SUPPORT",
            "forecast_authority": "ADVISORY_ONLY",
            "forecast_source": "DISCOVERY_PREOPTION",
            "forecast_vanguard_state": (
                "PRESENT" if ticker in vanguard else
                "REJECTED" if ticker in rejected else "UNAVAILABLE"
            ),
            "forecast_vanguard_reason": rejected.get(ticker),
            "forecast_auction_state": None,
            "forecast_auction_control": None,
            "forecast_legacy_statistical_context": None,
            "forecast_structure_stage": str(source.get("wyckoff_mode_phase_key") or "").strip() or None,
            "forecast_compression_state": str(source.get("crabel_state") or "").strip().upper() or None,
            "forecast_evidence_state": "UNRESOLVED",
            "forecast_scenarios_json": None,
            "forecast_countercase": None,
            # DIR-002 DWN-04: Thesis status, trade-plan completeness and both
            # candidate geometries travel with the descriptive claim.
            "forecast_thesis_status": str(source.get("thesis__direction_status") or "").strip() or None,
            "forecast_trade_plan_state": None,
            "forecast_candidate_geometry_json": _candidate_geometry_json(source),
            "forecast_legacy_statistical_basis": None,
        }
        thesis_side = str(source.get("thesis__side") or "").strip().upper()
        vg = vanguard.get(ticker)
        if vg is not None:
            # L1 profile context is not measured buyer/seller control. L2's
            # historical EV is legacy context, not calibrated C4 evidence.
            auction = str(vg.get("layer1__auction_state") or "").strip().upper()
            control = str(vg.get("layer1__control__controller") or "").strip().upper()
            base["forecast_auction_state"] = auction or None
            if auction not in {"", "PROFILE_CONTEXT_ONLY", "UNKNOWN"} and control in {"BUYERS", "SELLERS"}:
                base["forecast_auction_control"] = control
            legacy_quality = str(vg.get("layer2__edge_quality") or "").strip().upper() or None
            if thesis_side == "BEAR":
                # Legacy edge quality is upside-only; never context for BEAR.
                base["forecast_legacy_statistical_basis"] = "NOT_APPLICABLE_BULL_ONLY_LEGACY"
            else:
                base["forecast_legacy_statistical_context"] = legacy_quality
                base["forecast_legacy_statistical_basis"] = "BULL_ONLY_LEGACY" if legacy_quality else None
        reason = None
        if str(source.get("direction_authority") or "").strip() != "DISCOVERY_GOVERNED":
            reason = "DIRECTION_NOT_GOVERNED"
        elif str(source.get("is_stale") or "").strip().lower() in {"true", "1", "yes"}:
            reason = "STALE_BAR"
        elif str(source.get("bar_data_asof") or "").strip() != evidence_session:
            reason = "BAR_SESSION_MISMATCH"
        legacy_direction = {
            "CALL": ForecastDirection.BULL,
            "PUT": ForecastDirection.BEAR,
        }.get(str(source.get("direction") or "").strip().upper())
        if thesis_side:
            # Fresh runs: the Thesis owns the side; legacy fields must agree.
            direction = {"BULL": ForecastDirection.BULL, "BEAR": ForecastDirection.BEAR}.get(thesis_side)
            if reason is None and thesis_side not in {"BULL", "BEAR", "UNASSIGNED"}:
                reason = "THESIS_SIDE_INVALID"
            elif reason is None and direction != legacy_direction:
                reason = "DIRECTION_FIELD_CONFLICT"
            elif reason is None and thesis_side == "UNASSIGNED":
                unassigned = str(source.get("thesis__unassigned_reason") or "").strip().upper()
                reason = f"THESIS_UNASSIGNED:{unassigned or 'REASON_MISSING'}"
        else:
            direction = legacy_direction
        if reason is None and direction is None:
            reason = "DIRECTION_NOT_DIRECTIONAL"
        spot = _positive(source.get("stock_price"))
        if reason is None and spot is None:
            reason = "REFERENCE_SPOT_MISSING"
        if reason is not None:
            base["forecast_reason"] = reason
            output.append(base)
            continue
        assert direction is not None and spot is not None
        target_source = str(source.get("structural_target_source") or "").strip()
        stop_source = str(source.get("governed_invalidation_source") or "").strip()
        declared_target_state = str(source.get("target_state") or "").strip().upper()
        target = (_positive(source.get("structural_target"))
                  if target_source in STRUCTURAL_TARGET_SOURCES and declared_target_state != "NONE" else None)
        stop = (_positive(source.get("governed_invalidation_spot"))
                if stop_source in {"WYCKOFF_VALIDATION", "BEHAVIOURAL_STRUCTURE"} else None)
        if ((direction is ForecastDirection.BULL and
             ((target is not None and target <= spot) or (stop is not None and stop >= spot)))
            or (direction is ForecastDirection.BEAR and
                ((target is not None and target >= spot) or (stop is not None and stop <= spot)))):
            base["forecast_reason"] = "INVALID_GEOMETRY"
            output.append(base)
            continue
        thesis_id = f"{run_id}:{ticker}:{evidence_session}:DISCOVERY"
        forecast = TickerForecast(
            run_id=run_id, thesis_id=thesis_id, ticker=ticker,
            evidence_session=evidence_session, as_of_utc=as_of_utc,
            direction=direction, forecast_state=ForecastState.DESCRIPTIVE_ONLY,
            reference_spot=spot, target_spot=target, invalidation_spot=stop,
            supporting_evidence=("DISCOVERY_SNAPSHOT",),
        )
        base["forecast_trade_plan_state"] = (
            "COMPLETE_GEOMETRY" if stop is not None else "INCOMPLETE_GEOMETRY"
        )
        base.update({
            "forecast_state": forecast.forecast_state.value,
            "forecast_direction": forecast.direction.value,
            "forecast_reference_spot": forecast.reference_spot,
            "forecast_target_spot": forecast.target_spot,
            "forecast_invalidation_spot": forecast.invalidation_spot,
            "forecast_thesis_id": forecast.thesis_id,
            "forecast_reason": (
                "TARGET_NOT_SOURCED_PREOPTION" if target is None
                else "STOP_NOT_SOURCED_PREOPTION" if stop is None
                else "SOURCED_PREOPTION_GEOMETRY"
            ),
        })
        opposing_control = (
            (direction is ForecastDirection.BULL and base["forecast_auction_control"] == "SELLERS")
            or (direction is ForecastDirection.BEAR and base["forecast_auction_control"] == "BUYERS")
        )
        base["forecast_evidence_state"] = "OPPOSING_AUCTION_EVIDENCE" if opposing_control else "DESCRIPTIVE_DIRECTIONAL"
        base["forecast_countercase"] = (
            "Measured auction control opposes the Discovery direction; await independent confirmation."
            if opposing_control else
            "The structure can fail or remain in range; no calibrated time-to-move is available."
        )
        side = "upward" if direction is ForecastDirection.BULL else "downward"
        base["forecast_scenarios_json"] = json.dumps([
            {"path": "CONFIRMATION", "condition": "trigger acceptance",
             "trigger_spot": _positive(source.get("wyckoff_entry_trigger")),
             "consequence": f"{side} development", "probability": None},
            {"path": "DELAY", "condition": "range persists or compression remains unresolved",
             "consequence": "ticker thesis may develop without a suitable near-dated option",
             "probability": None},
            {"path": "FAILURE", "condition": "structural invalidation or contrary control",
             "invalidation_spot": stop, "consequence": "reassess or invalidate thesis",
             "probability": None},
        ], sort_keys=True, separators=(",", ":"))
        output.append(base)
    return {
        "packet_version": PACKET_VERSION,
        "run_id": run_id,
        "evidence_session": evidence_session,
        "as_of_utc": as_of_utc,
        "source_discovery_sha256": discovery_sha256.lower(),
        "source_vanguard_sha256": vanguard_sha256.lower() if vanguard_sha256 else None,
        "vanguard_present_count": len(vanguard),
        "vanguard_rejected_count": len(rejected),
        "row_count": len(output),
        "authority": "ADVISORY_ONLY",
        "rows": output,
    }
