"""Materialise the immutable MSI Lab-to-Interpreter production handoff.

This module is deliberately data-only: it does not fetch market data, select a
contract, calculate direction, or grant capital.  It serialises already
governed Morning/Lab rows and publishes the atomic Interpreter baton only when
every row has complete, matching identity.
"""

from __future__ import annotations

import csv
import json
import os
import tempfile
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from contracts.interpreter_handoff import (
    AUTHORITY_MAP_VERSION,
    BOOK_SCHEMA_VERSION,
    BUNDLE_SCHEMA_VERSION,
    HandoffValidationError,
    artifact_record,
    canonical_json,
    publish_handoff_manifest,
    sha256_file,
    utc_now,
    validate_evidence_bundle,
)
from canonical_data.bundle_freshness import derive_bundle_freshness
from contracts.quote_change_evidence import (
    compare_exact_option_quotes,
    quote_change_overlay_fields,
    quote_snapshot_from_row,
)


MATERIALIZER_VERSION = "msi-handoff-materializer-v1.2"
RECONCILIATION_SCHEMA_VERSION = "msi_reconciliation_v1"
BOOK_MANIFEST_SCHEMA_VERSION = "lab_signal_book_v3_manifest_v1"


def _text(value: Any) -> str:
    text = str(value or "").strip()
    return "" if text.upper() in {"NAN", "NONE", "NULL", "N/A"} else text


def _upper(value: Any) -> str:
    return _text(value).upper()


def _canonical_contract(row: Mapping[str, Any]) -> str:
    raw = (
        row.get("selected_contract_symbol")
        or row.get("morning_selected_contract_symbol")
        or row.get("contract_symbol")
    )
    value = _upper(raw).replace("O:", "").replace(" ", "")
    if not value:
        symbols = row.get("selected_contract_symbols")
        if isinstance(symbols, str):
            try:
                symbols = json.loads(symbols)
            except json.JSONDecodeError:
                symbols = [symbols]
        if isinstance(symbols, (list, tuple)) and len(symbols) == 1:
            value = _upper(symbols[0]).replace("O:", "").replace(" ", "")
    return value


def _first(row: Mapping[str, Any], *names: str) -> Any:
    for name in names:
        value = row.get(name)
        if _text(value):
            return value
    return ""


def _atomic_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    os.close(fd)
    temporary = Path(temporary_name)
    try:
        temporary.write_text(value, encoding="utf-8")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _atomic_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    identity = [
        "lab_schema_version",
        "run_id",
        "pipeline_mode",
        "ticker",
        "thesis_id",
        "trade_idea_id",
        "selected_structure_id",
        "selected_contract_symbol",
        "selected_quote_snapshot_id",
        "bundle_id",
    ]
    fields = identity + sorted({key for row in rows for key in row} - set(identity))
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    os.close(fd)
    temporary = Path(temporary_name)
    try:
        with temporary.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _identity(row: Mapping[str, Any], run_id: str, pipeline_mode: str) -> dict[str, str]:
    identity = {
        "run_id": _text(row.get("run_id")) or run_id,
        "pipeline_mode": _upper(row.get("pipeline_mode")) or pipeline_mode,
        "ticker": _upper(row.get("ticker")),
        "thesis_id": _text(row.get("thesis_id")),
        "trade_idea_id": _text(row.get("trade_idea_id")),
        "selected_structure_id": _text(row.get("selected_structure_id")),
        "selected_contract_symbol": _canonical_contract(row),
        "selected_quote_snapshot_id": _text(row.get("selected_quote_snapshot_id")),
    }
    if identity["run_id"] != run_id:
        raise HandoffValidationError(
            f"MATERIALIZER_RUN_ID_MISMATCH:{identity['run_id']}:{run_id}"
        )
    missing = [name for name, value in identity.items() if not value]
    if missing:
        raise HandoffValidationError(
            f"MATERIALIZER_MISSING_IDENTITY:{identity['ticker'] or 'UNKNOWN'}:"
            + ",".join(missing)
        )
    return identity


def _authority_map() -> dict[str, str]:
    return {
        "governed_direction": "DIRECTION_GOVERNANCE",
        "selected_contract_symbol": "MORNING_GATE_SELECTED_CONTRACT",
        "thesis_state": "OPTIONS_LIQUIDITY_LIFECYCLE",
        "olm_guard_disposition": "OLM_EXECUTION_GUARD",
        "model_final_action": "MORNING_EXECUTION_GATE",
        "final_action": "MORNING_HANDOFF_QUOTE_GOVERNANCE",
        "execution_quote_status": "MORNING_HANDOFF_QUOTE_GOVERNANCE",
        "capital_permission": "MORNING_EXECUTION_GATE",
        "validation_transition": "DYNAMIC_VALIDATION_GATE",
        "validation_event_id": "DYNAMIC_VALIDATION_GATE",
        "frozen_thesis": "COMPLETED_THESIS",
        "current_validation": "DYNAMIC_VALIDATION_GATE",
        "macro_quant_packet": "ADVISORY_ONLY",
        "interpreter_assessment": "ADVISORY_ONLY",
    }


def _status_banner(validation: Mapping[str, Any] | None) -> str:
    if not validation:
        return "THESIS PREPARED — CURRENT VALIDATION NOT RUN"
    transition = _upper(validation.get("transition"))
    profile_state = _upper(validation.get("profile_evidence_state"))
    gate = validation.get("execution_gate_result")
    gate = dict(gate) if isinstance(gate, Mapping) else {}
    action = _upper(gate.get("action") or gate.get("final_action"))
    if transition == "THESIS_INVALIDATED":
        return "THESIS INVALIDATED BY CURRENT PRICE"
    if transition in {"TARGET_ALREADY_REACHED", "ENTRY_RUNWAY_EXHAUSTED"}:
        return "THESIS VALID — ENTRY RUNWAY EXHAUSTED"
    if transition == "DATA_DEFERRED":
        return "DATA DEFERRED — CURRENT SESSION NOT YET OBSERVABLE"
    if transition == "THESIS_CONFIRMED" and action in {"BUY_NOW", "BUY_SMALL", "ELIGIBLE"}:
        return "THESIS CONFIRMED — EXECUTION VIABILITY PASSED"
    if profile_state == "DEVELOPING_SESSION":
        return "RTH DEVELOPING PROFILE — ADVISORY"
    if profile_state == "PENDING_MARKET_OPEN":
        return "PREMARKET VALIDATED — OPTION REQUOTE MAY BE REQUIRED"
    return "THESIS VALIDATED — REVIEW EXECUTION GATE"


def _frozen_axis(row: Mapping[str, Any], identity: Mapping[str, str]) -> dict[str, Any]:
    return {
        "thesis_id": identity["thesis_id"],
        "completed_session": _first(
            row, "evidence_session_date", "completed_session", "thesis_session_date"
        ),
        "direction": _upper(row.get("governed_direction") or row.get("direction")),
        "horizon": _first(
            row, "planned_hold_sessions", "expected_holding_window", "horizon_bucket"
        ),
        "completed_close": _first(
            row, "completed_close", "eod_close", "signal_price", "underlying_price"
        ),
        "target": _first(row, "target_spot", "target_price", "structural_target"),
        "invalidation": _first(
            row, "invalidation_spot", "invalidation_price", "structural_invalidation"
        ),
        "selected_contract": identity["selected_contract_symbol"],
        "completed_profile_evidence_id": _first(
            row, "completed_profile_evidence_id", "market_profile_evidence_id"
        ),
    }


def _normalise_validation_event(
    event: Mapping[str, Any] | Any | None,
    *,
    identity: Mapping[str, str],
) -> dict[str, Any] | None:
    if event is None:
        return None
    if hasattr(event, "to_dict"):
        event = event.to_dict()
    if not isinstance(event, Mapping):
        raise HandoffValidationError("VALIDATION_EVENT_INVALID")
    value = dict(event)
    checks = {
        "ticker": identity["ticker"],
        "thesis_id": identity["thesis_id"],
        "direction": identity.get("governed_direction", ""),
        "selected_contract": identity["selected_contract_symbol"],
    }
    for field, expected in checks.items():
        actual = (
            _upper(value.get(field)).replace("O:", "").replace(" ", "")
            if field == "selected_contract"
            else _upper(value.get(field))
        )
        comparison = (
            _upper(expected).replace("O:", "").replace(" ", "")
            if field == "selected_contract"
            else _upper(expected)
        )
        if comparison and actual != comparison:
            raise HandoffValidationError(
                f"VALIDATION_EVENT_IDENTITY_MISMATCH:{field}"
            )
    if not _text(value.get("validation_event_id")):
        raise HandoffValidationError("VALIDATION_EVENT_ID_MISSING")
    return value


def _freshness_map(row: Mapping[str, Any]) -> dict[str, str]:
    return derive_bundle_freshness(row)


def _apply_execution_quote_governance(
    row: Mapping[str, Any], *, session_date: str
) -> dict[str, Any]:
    """Separate swing-trade thesis validity from entry-price freshness."""
    governed = dict(row)
    governed["model_final_action"] = _upper(governed.get("final_action"))
    governed["contract_size_quality"] = (
        _upper(governed.get("contract_size_quality")) or "MISSING"
    )
    timestamp = _text(_first(
        governed,
        "current_quote_timestamp_utc",
        "selected_quote_timestamp_utc",
        "live_contract_quote_timestamp",
        "live_contract_provider_updated",
    ))
    try:
        observed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        if observed.tzinfo is None:
            raise ValueError("timezone required")
        quote_date = observed.astimezone(timezone.utc).date()
        governed_session = date.fromisoformat(str(session_date)[:10])
    except (TypeError, ValueError):
        quote_date = None
        governed_session = None
    if quote_date is None or governed_session is None:
        governed["execution_quote_status"] = "MANUAL_REQUOTE_REQUIRED"
    elif quote_date < governed_session:
        governed["execution_quote_status"] = "PRIOR_SESSION_MANUAL_REQUOTE"
    else:
        governed["execution_quote_status"] = "SAME_SESSION_INDICATIVE"
    if governed["execution_quote_status"] != "SAME_SESSION_INDICATIVE":
        governed["final_action"] = "MANUAL_REQUOTE_REQUIRED"
        governed["morning_entry_action"] = "MANUAL_REQUOTE_REQUIRED"
        governed["morning_execution_permission"] = "HUMAN_REQUOTE_REQUIRED"
        governed["execution_permission"] = "HUMAN_APPROVAL_REQUIRED"
        governed["final_capital_permission"] = "HUMAN_APPROVAL_REQUIRED"
    governed["execution_quote_timestamp_utc"] = timestamp
    governed["execution_quote_human_confirmation_required"] = True
    return governed


def _bundle(
    row: Mapping[str, Any],
    *,
    identity: Mapping[str, str],
    macro_reference: Mapping[str, Any] | None,
    session_date: str,
    validation_event: Mapping[str, Any] | Any | None = None,
) -> dict[str, Any]:
    governed = _apply_execution_quote_governance(row, session_date=session_date)
    governed.update(identity)
    validation = _normalise_validation_event(
        validation_event,
        identity={
            **identity,
            "governed_direction": _upper(
                row.get("governed_direction") or row.get("direction")
            ),
        },
    )
    frozen_axis = _frozen_axis(row, identity)
    if validation:
        governed.update({
            "validation_event_id": validation.get("validation_event_id"),
            "validation_transition": validation.get("transition"),
            "validation_reason": validation.get("reason"),
            "validation_evidence_cutoff_utc": validation.get("evidence_cutoff_utc"),
            "validation_current_price": validation.get("current_price"),
            "validation_gap_pct": validation.get("gap_pct"),
            "validation_data_status": validation.get("data_status"),
            "validation_profile_evidence_state": validation.get("profile_evidence_state"),
        })
    governed["lab_status_banner"] = _status_banner(validation)
    morning_quote = quote_snapshot_from_row(governed, role="MORNING")
    current_quote = quote_snapshot_from_row(governed, role="CURRENT")
    quote_change = compare_exact_option_quotes(
        ticker=identity["ticker"],
        thesis_id=identity["thesis_id"],
        trade_idea_id=identity["trade_idea_id"],
        selected_structure_id=identity["selected_structure_id"],
        morning=morning_quote,
        current=current_quote,
    )
    governed.update(quote_change_overlay_fields(quote_change))
    bundle_id = str(
        uuid.uuid5(
            uuid.NAMESPACE_URL,
            canonical_json(
                {
                    **identity,
                    "validation_event_id": _text(
                        (validation or {}).get("validation_event_id")
                    ),
                    "authority_map_version": AUTHORITY_MAP_VERSION,
                }
            ),
        )
    )
    governed["bundle_id"] = bundle_id
    bundle = {
        "bundle_schema_version": BUNDLE_SCHEMA_VERSION,
        "authority_map_version": AUTHORITY_MAP_VERSION,
        "bundle_id": bundle_id,
        "bundle_created_utc": utc_now(),
        **identity,
        "authority_map": _authority_map(),
        "freshness_map": _freshness_map(governed),
        "governed_record": governed,
        "market_structure": {
            key: value
            for key, value in row.items()
            if key.startswith("ms_") or key.startswith("market_structure_")
        },
        "frozen_thesis": frozen_axis,
        "current_validation": validation or {},
        "quote_change_evidence": quote_change,
    }
    if macro_reference:
        expected_packet_id = _text(macro_reference.get("packet_id"))
        expected_hash = _text(macro_reference.get("sha256")).lower()
        row_packet_id = _text(row.get("macro_packet_id"))
        row_hash = _text(row.get("macro_packet_sha256")).lower()
        if row_packet_id and row_packet_id != expected_packet_id:
            raise HandoffValidationError("MACRO_PACKET_ID_LAB_BUNDLE_MISMATCH")
        if row_hash and row_hash != expected_hash:
            raise HandoffValidationError("MACRO_PACKET_HASH_LAB_BUNDLE_MISMATCH")
        bundle["macro_quant_packet"] = dict(macro_reference)
    return validate_evidence_bundle(bundle)


def _normalise_macro_reference(
    run_root: Path, reference: Mapping[str, Any] | None
) -> dict[str, Any] | None:
    if not reference:
        return None
    value = dict(reference)
    raw_path = _text(value.get("path"))
    if raw_path:
        path = Path(raw_path)
        if not path.is_absolute():
            path = run_root / path
        path = path.resolve()
        try:
            path.relative_to(run_root.resolve())
        except ValueError as error:
            raise HandoffValidationError("MACRO_REFERENCE_OUTSIDE_RUN") from error
        if not path.is_file():
            raise HandoffValidationError("MACRO_REFERENCE_MISSING")
        value["path"] = str(path)
        actual_hash = sha256_file(path)
        supplied_hash = _text(value.get("sha256")).lower()
        if supplied_hash and supplied_hash != actual_hash:
            raise HandoffValidationError("MACRO_REFERENCE_HASH_MISMATCH")
        value["sha256"] = actual_hash
    return value


def materialize_interpreter_handoff(
    *,
    run_id: str,
    rows: Iterable[Mapping[str, Any]],
    run_root: Path | str,
    pipeline_mode: str,
    session_date: str,
    run_kind: str,
    run_status: str,
    required_stage_status: Mapping[str, Any],
    morning_gate_completed_utc: str,
    macro_reference: Mapping[str, Any] | None = None,
    validation_events: Mapping[str, Any] | Iterable[Any] | None = None,
    require_validation_lineage: bool = False,
    producer_version: str = MATERIALIZER_VERSION,
) -> dict[str, Any]:
    """Write, reconcile and atomically publish one accepted handoff.

    The caller must pass only the governed rows intended for Interpreter use.
    Rows lacking an exact long CALL/PUT contract identity fail the whole
    publication; they are never silently dropped or repaired here.
    """

    root = Path(run_root).resolve()
    if root.name != run_id:
        raise HandoffValidationError(f"MATERIALIZER_RUN_ROOT_MISMATCH:{root.name}:{run_id}")
    mode = _upper(pipeline_mode)
    source_rows = [dict(row) for row in rows]
    if not source_rows:
        raise HandoffValidationError("MATERIALIZER_EMPTY_ROW_SET")
    macro = _normalise_macro_reference(root, macro_reference)
    validation_by_thesis: dict[str, Any] = {}
    if isinstance(validation_events, Mapping):
        validation_values = (
            (validation_events,)
            if "thesis_id" in validation_events
            else validation_events.values()
        )
    else:
        validation_values = validation_events or ()
    for raw_event in validation_values:
        value = raw_event.to_dict() if hasattr(raw_event, "to_dict") else raw_event
        if not isinstance(value, Mapping):
            raise HandoffValidationError("VALIDATION_EVENT_INVALID")
        thesis_key = _text(value.get("thesis_id"))
        if not thesis_key:
            raise HandoffValidationError("VALIDATION_EVENT_THESIS_ID_MISSING")
        prior = validation_by_thesis.get(thesis_key)
        prior_value = (
            prior.to_dict() if hasattr(prior, "to_dict") else prior
        )
        if prior is None or _text(value.get("evidence_cutoff_utc")) > _text(
            (prior_value or {}).get("evidence_cutoff_utc")
        ):
            validation_by_thesis[thesis_key] = raw_event

    book_rows: list[dict[str, Any]] = []
    bundles: list[dict[str, Any]] = []
    seen_tickers: set[str] = set()
    for row in source_rows:
        identity = _identity(row, run_id, mode)
        ticker = identity["ticker"]
        if ticker in seen_tickers:
            raise HandoffValidationError(f"MATERIALIZER_DUPLICATE_TICKER:{ticker}")
        seen_tickers.add(ticker)
        validation_event = validation_by_thesis.get(identity["thesis_id"])
        if require_validation_lineage and validation_event is None:
            raise HandoffValidationError(
                f"MATERIALIZER_MISSING_VALIDATION_EVENT:{ticker}:{identity['thesis_id']}"
            )
        bundle = _bundle(
            row,
            identity=identity,
            macro_reference=macro,
            session_date=session_date,
            validation_event=validation_event,
        )
        # The v3 book and bundle are two serialisations of the same governed
        # record.  Computed quote evidence must never exist only in the bundle.
        book_row = dict(bundle["governed_record"])
        book_row.update(identity)
        book_row["lab_schema_version"] = BOOK_SCHEMA_VERSION
        book_row["bundle_id"] = bundle["bundle_id"]
        book_rows.append(book_row)
        bundles.append(bundle)

    lab_dir = root / "intelligence_lab"
    interpreter_dir = root / "interpreter"
    diagnostics_dir = root / "diagnostics"
    book_path = lab_dir / "lab_signal_book_v3.csv"
    book_manifest_path = lab_dir / "lab_signal_book_v3.manifest.json"
    bundles_path = interpreter_dir / "interpreter_evidence_bundle_v1.jsonl"
    reconciliation_path = diagnostics_dir / "msi_reconciliation.json"

    _atomic_csv(book_path, book_rows)
    book_manifest = {
        "schema_version": BOOK_MANIFEST_SCHEMA_VERSION,
        "book_schema_version": BOOK_SCHEMA_VERSION,
        "run_id": run_id,
        "pipeline_mode": mode,
        "created_at_utc": utc_now(),
        "row_count": len(book_rows),
        "ticker_count": len(seen_tickers),
        "book_sha256": sha256_file(book_path),
        "authority_map_version": AUTHORITY_MAP_VERSION,
        "validation_lineage_required": bool(require_validation_lineage),
        "validation_event_count": sum(
            1 for bundle in bundles if bundle.get("current_validation")
        ),
    }
    _atomic_text(book_manifest_path, json.dumps(book_manifest, indent=2, sort_keys=True))
    _atomic_text(
        bundles_path,
        "".join(canonical_json(bundle) + "\n" for bundle in bundles),
    )

    reconciliation = {
        "schema_version": RECONCILIATION_SCHEMA_VERSION,
        "status": "PASS",
        "run_id": run_id,
        "created_at_utc": utc_now(),
        "input_rows": len(source_rows),
        "book_rows": len(book_rows),
        "bundle_rows": len(bundles),
        "unique_tickers": len(seen_tickers),
        "missing_bundles": 0,
        "identity_mismatches": 0,
        "validation_event_rows": sum(
            1 for bundle in bundles if bundle.get("current_validation")
        ),
        "book_sha256": sha256_file(book_path),
        "bundle_sha256": sha256_file(bundles_path),
    }
    _atomic_text(reconciliation_path, json.dumps(reconciliation, indent=2, sort_keys=True))

    artifacts = [
        artifact_record("LAB_BOOK", book_path, BOOK_SCHEMA_VERSION),
        artifact_record("LAB_BOOK_MANIFEST", book_manifest_path, BOOK_MANIFEST_SCHEMA_VERSION),
        artifact_record("INTERPRETER_BUNDLES", bundles_path, BUNDLE_SCHEMA_VERSION),
        artifact_record("RECONCILIATION_REPORT", reconciliation_path, RECONCILIATION_SCHEMA_VERSION),
    ]
    handoff_path = interpreter_dir / "handoff_manifest.json"
    publish_handoff_manifest(
        handoff_path,
        run_id=run_id,
        pipeline_mode=mode,
        session_date=session_date,
        run_kind=run_kind,
        run_status=run_status,
        required_stage_status=required_stage_status,
        morning_gate_completed_utc=morning_gate_completed_utc,
        artifacts=artifacts,
        ticker_count=len(seen_tickers),
        bundle_count=len(bundles),
        reconciliation_status="PASS",
        producer_version=producer_version,
    )
    return {
        "run_id": run_id,
        "status": "PASS",
        "row_count": len(book_rows),
        "ticker_count": len(seen_tickers),
        "book_path": str(book_path),
        "book_manifest_path": str(book_manifest_path),
        "bundle_path": str(bundles_path),
        "reconciliation_path": str(reconciliation_path),
        "handoff_manifest_path": str(handoff_path),
    }


__all__ = [
    "BOOK_MANIFEST_SCHEMA_VERSION",
    "MATERIALIZER_VERSION",
    "RECONCILIATION_SCHEMA_VERSION",
    "materialize_interpreter_handoff",
]
