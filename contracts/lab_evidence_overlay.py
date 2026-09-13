"""Allow-listed, non-authoritative Intelligence Lab MSI overlays."""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping


OVERLAY_SCHEMA_VERSION = "lab_evidence_overlay_v1"

CURRENT_QUOTE_FIELDS = {
    "current_contract_bid", "current_contract_ask", "current_contract_mid",
    "current_contract_spread_pct", "contract_bid_change", "contract_ask_change",
    "contract_mid_change", "contract_bid_change_pct", "contract_ask_change_pct",
    "contract_mid_change_pct", "contract_spread_change_pp", "contract_bid_size",
    "contract_ask_size", "contract_bid_size_change", "contract_ask_size_change",
    "contract_size_quality", "current_quote_snapshot_id", "quote_timestamp_utc",
    "quote_age_seconds", "quote_freshness", "quote_age_affects_thesis",
    "quote_source", "comparison_status", "change_status",
    "current_spread_fraction_mid", "current_spread_pct_of_mid",
}
UNDERLYING_FIELDS = {
    "underlying_last", "underlying_nbbo_bid", "underlying_nbbo_ask",
    "underlying_nbbo_mid", "underlying_nbbo_bid_size", "underlying_nbbo_ask_size",
    "underlying_nbbo_timestamp_utc", "underlying_vwap_canonical",
    "underlying_vwap_relationship", "overnight_gap_pct", "remaining_runway_pct",
    "session_state", "last_completed_bar_utc",
}
STRUCTURE_FIELDS = {
    "ms_profile_type", "ms_lifecycle", "ms_direction_relationship",
    "ms_first_distribution_low", "ms_first_distribution_high",
    "ms_second_distribution_low", "ms_second_distribution_high",
    "ms_developing_poc", "ms_final_poc", "ms_separation_low",
    "ms_separation_high", "ms_repair_pct", "ms_acceptance_minutes",
    "ms_acceptance_closes", "ms_vwap_hold_minutes", "ms_quality_class",
    "ms_reason_code", "ms_evidence_id", "ms_parameter_set_version",
    "screenshot_confirmation_status", "screenshot_screen_type",
    "screenshot_capture_time_utc", "screenshot_quality",
    "screenshot_authority",
}
ASSESSMENT_FIELDS = {
    "interpreter_assessment_id", "interpreter_created_utc",
    "interpreter_strengthening_weakening", "interpreter_agreement_conflict",
    "interpreter_manual_checks", "interpreter_data_gaps",
    "interpreter_plain_language_reason", "interpreter_authority_statement",
    "interpreter_assessment_status",
}
OVERLAY_ALLOWED_FIELDS = frozenset(
    CURRENT_QUOTE_FIELDS | UNDERLYING_FIELDS | STRUCTURE_FIELDS | ASSESSMENT_FIELDS
)

PROTECTED_AUTHORITY_FIELDS = frozenset({
    "run_id", "ticker", "pipeline_mode", "thesis_id", "trade_idea_id",
    "selected_structure_id", "selected_contract_symbol", "selected_contract_symbols",
    "selected_quote_snapshot_id", "governed_direction", "final_direction",
    "direction", "dir_calc_version", "governed_direction_record_sha256",
    "thesis_state", "liquidity_state", "morning_transition_state",
    "olm_guard_disposition", "olm_guard_reason", "final_action",
    "capital_permission", "morning_execution_permission", "lab_verdict",
    "lab_tradeable", "position_size_display",
})


class OverlayValidationError(ValueError):
    pass


def _text(value: Any) -> str:
    return str(value or "").strip()


def _parse_timestamp(value: Any, field: str) -> None:
    try:
        datetime.fromisoformat(_text(value).replace("Z", "+00:00"))
    except ValueError as error:
        raise OverlayValidationError(f"INVALID_{field.upper()}") from error


def validate_overlay(value: Mapping[str, Any]) -> dict[str, Any]:
    overlay = dict(value)
    if overlay.get("schema_version") != OVERLAY_SCHEMA_VERSION:
        raise OverlayValidationError("OVERLAY_SCHEMA_UNSUPPORTED")
    for field in ("overlay_id", "run_id", "ticker", "bundle_id", "created_utc"):
        if not _text(overlay.get(field)):
            raise OverlayValidationError(f"OVERLAY_MISSING_{field.upper()}")
    try:
        uuid.UUID(_text(overlay["overlay_id"]))
        uuid.UUID(_text(overlay["bundle_id"]))
    except ValueError as error:
        raise OverlayValidationError("OVERLAY_ID_NOT_UUID") from error
    _parse_timestamp(overlay["created_utc"], "created_utc")
    fields = overlay.get("fields")
    if not isinstance(fields, Mapping):
        raise OverlayValidationError("OVERLAY_FIELDS_INVALID")
    unknown = set(fields) - OVERLAY_ALLOWED_FIELDS
    protected = set(fields) & PROTECTED_AUTHORITY_FIELDS
    if protected:
        raise OverlayValidationError("OVERLAY_AUTHORITY_FIELD:" + ",".join(sorted(protected)))
    if unknown:
        raise OverlayValidationError("OVERLAY_FIELD_NOT_ALLOWED:" + ",".join(sorted(unknown)))
    overlay["ticker"] = _text(overlay["ticker"]).upper()
    overlay["fields"] = dict(fields)
    return overlay


def build_overlay(
    *,
    run_id: str,
    ticker: str,
    bundle_id: str,
    fields: Mapping[str, Any],
    source: str,
) -> dict[str, Any]:
    return validate_overlay({
        "schema_version": OVERLAY_SCHEMA_VERSION,
        "overlay_id": str(uuid.uuid4()),
        "run_id": run_id,
        "ticker": ticker,
        "bundle_id": bundle_id,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "source": source,
        "fields": dict(fields),
    })


def append_overlay(path: Path | str, overlay: Mapping[str, Any]) -> Path:
    record = validate_overlay(overlay)
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    return target


def load_overlays(path: Path | str) -> list[dict[str, Any]]:
    target = Path(path)
    if not target.is_file():
        return []
    records: list[dict[str, Any]] = []
    with target.open("r", encoding="utf-8-sig") as handle:
        for number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                records.append(validate_overlay(json.loads(line)))
            except (json.JSONDecodeError, OverlayValidationError) as error:
                raise OverlayValidationError(f"INVALID_OVERLAY_LINE:{number}:{error}") from error
    return records


def apply_latest_compatible_overlays(
    rows: Iterable[Mapping[str, Any]],
    overlays: Iterable[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Apply only compatible observation fields; book authority always wins."""

    validated = [validate_overlay(item) for item in overlays]
    latest: dict[tuple[str, str, str], dict[str, Any]] = {}
    for item in validated:
        key = (item["run_id"], item["ticker"], item["bundle_id"])
        previous = latest.get(key)
        if previous is None or item["created_utc"] > previous["created_utc"]:
            latest[key] = item
    by_run_ticker: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for item in latest.values():
        by_run_ticker.setdefault((item["run_id"], item["ticker"]), []).append(item)

    output: list[dict[str, Any]] = []
    for raw in rows:
        row = dict(raw)
        key = (_text(row.get("run_id")), _text(row.get("ticker")).upper())
        compatible = by_run_ticker.get(key, [])
        expected_bundle = _text(row.get("bundle_id"))
        # An overlay without exact bundle continuity is not compatible.  Never
        # fall back to run+ticker because contract identity can change within a
        # run while the ticker remains the same.
        if not expected_bundle:
            compatible = []
        else:
            compatible = [item for item in compatible if item["bundle_id"] == expected_bundle]
        if compatible:
            chosen = max(compatible, key=lambda item: item["created_utc"])
            for field, value in chosen["fields"].items():
                if field in OVERLAY_ALLOWED_FIELDS:
                    row[field] = value
            row["applied_overlay_id"] = chosen["overlay_id"]
            row["applied_overlay_bundle_id"] = chosen["bundle_id"]
        output.append(row)
    return output


__all__ = [
    "ASSESSMENT_FIELDS", "CURRENT_QUOTE_FIELDS", "OVERLAY_ALLOWED_FIELDS",
    "OVERLAY_SCHEMA_VERSION", "OverlayValidationError", "PROTECTED_AUTHORITY_FIELDS",
    "STRUCTURE_FIELDS", "UNDERLYING_FIELDS", "append_overlay",
    "apply_latest_compatible_overlays", "build_overlay", "load_overlays",
    "validate_overlay",
]
