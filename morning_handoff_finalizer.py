"""Governed Morning Gate -> Execution Gate -> Lab -> Interpreter handoff.

This module deliberately performs no provider or API requests.  It consumes the
completed Morning Gate rows, materialises the downstream artifacts, verifies
their reconciliation, and copies the governed handoff files into MA_Inputs.
Both supported Morning entry points call this module so a Morning run cannot
report success while leaving the Intelligence Lab on the previous EOD view.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import logging
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional

from contracts.direction_governance import DIR_CALC_VERSION, validate_direction_record
from contracts.options_liquidity_execution_guard import (
    action_is_within_guard,
    evaluate_olm_execution_guard,
)
from contracts.interpreter_macro_context import (
    advisory_fields_for_row,
    materialize_interpreter_macro_context,
)

log = logging.getLogger("avshunter.morning_handoff")
REPO_ROOT = Path(__file__).resolve().parent
DEFAULT_RUNS_DIR = REPO_ROOT / "data" / "output" / "runs"
HANDOFF_VERSION = "morning-handoff-v2"
ACTIONABLE_LAB_VERDICTS = {"GO", "GO_LIMIT", "PROBE"}
EXECUTION_TO_LAB = {
    "BUY_NOW": "GO",
    "BUY_SMALL": "GO_LIMIT",
    "CONTRACT_REPAIR": "CONTRACT_REPAIR",
    "MANUAL_REVIEW": "MANUAL_REVIEW",
    "BLOCK": "BLOCKED",
    "SKIP": "BLOCKED",
}


class MorningHandoffError(RuntimeError):
    """Raised when the mandatory Morning downstream handoff is incomplete."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_csv(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise MorningHandoffError(f"Morning handoff input not found: {path}")
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = [dict(row) for row in csv.DictReader(handle)]
    if not rows:
        raise MorningHandoffError(f"Morning handoff input contains no rows: {path}")
    return rows


def _normalise_rows(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    normalised = [dict(row) for row in rows]
    if not normalised:
        raise MorningHandoffError("Morning handoff received no result rows")
    return normalised


def _count(rows: Iterable[Mapping[str, Any]], key: str) -> dict[str, int]:
    values = Counter(str(row.get(key, "") or "").strip() or "MISSING" for row in rows)
    return dict(sorted(values.items()))


def _contract_identity(row: Mapping[str, Any]) -> str:
    for key in (
        "selected_contract_symbol",
        "morning_selected_contract_symbol",
        "contract_symbol",
        "live_contract_symbol",
        "recommended_contract",
    ):
        value = str(row.get(key, "") or "").strip().upper().replace(" ", "")
        if value and value not in {"NAN", "NONE", "NULL", "N/A"}:
            return value.replace("O:", "")
    return ""


def _execution_lab_mismatches(
    gated_rows: Iterable[Mapping[str, Any]],
    lab_rows: Iterable[Mapping[str, Any]],
) -> list[str]:
    gated_rows = list(gated_rows)
    lab_rows = list(lab_rows)
    gated_by_ticker = {
        str(row.get("ticker", "") or "").strip().upper(): row for row in gated_rows
    }
    lab_by_ticker = {
        str(row.get("ticker", "") or "").strip().upper(): row for row in lab_rows
    }
    mismatches: list[str] = []
    if len(gated_by_ticker) != len(gated_rows):
        mismatches.append("DUPLICATE_OR_MISSING_TICKER_IN_EXECUTION_ROWS")
    if len(lab_by_ticker) != len(lab_rows):
        mismatches.append("DUPLICATE_OR_MISSING_TICKER_IN_LAB_ROWS")
    for ticker, gated in gated_by_ticker.items():
        lab = lab_by_ticker.get(ticker)
        if lab is None:
            mismatches.append(f"{ticker}:MISSING_FROM_LAB")
            continue
        action = str(gated.get("final_action", "") or "").strip().upper()
        expected = EXECUTION_TO_LAB.get(action)
        actual = str(lab.get("lab_verdict", "") or "").strip().upper()
        if expected is None:
            mismatches.append(f"{ticker}:UNKNOWN_EXECUTION_ACTION:{action or 'MISSING'}")
        elif actual != expected:
            mismatches.append(f"{ticker}:ACTION_{action}_EXPECTED_{expected}_GOT_{actual}")
        lab_action = str(lab.get("final_action", "") or "").strip().upper()
        if lab_action != action:
            mismatches.append(f"{ticker}:FINAL_ACTION_LOST:{action}->{lab_action or 'MISSING'}")
        gated_contract = _contract_identity(gated)
        lab_contract = _contract_identity(lab)
        if gated_contract and gated_contract != lab_contract:
            mismatches.append(
                f"{ticker}:CONTRACT_CHANGED:{gated_contract}->{lab_contract or 'MISSING'}"
            )
        for direction_field in (
            "dir_calc_version",
            "governed_direction",
            "final_direction",
            "direction_resolution_path",
            "direction_resolution_chain_json",
            "governed_direction_record_sha256",
        ):
            before = str(gated.get(direction_field, "") or "").strip()
            after = str(lab.get(direction_field, "") or "").strip()
            if before != after:
                mismatches.append(
                    f"{ticker}:DIRECTION_FIELD_CHANGED:{direction_field}:"
                    f"{before or 'MISSING'}->{after or 'MISSING'}"
                )
        for macro_field in (
            "macro_packet_id",
            "macro_packet_sha256",
            "macro_source_fingerprint",
            "macro_as_of_utc",
            "macro_freshness",
            "macro_data_quality",
            "macro_authority",
        ):
            before = str(gated.get(macro_field, "") or "").strip()
            after = str(lab.get(macro_field, "") or "").strip()
            if before != after:
                mismatches.append(
                    f"{ticker}:MACRO_ADVISORY_FIELD_CHANGED:{macro_field}:"
                    f"{before or 'MISSING'}->{after or 'MISSING'}"
                )
        if action in {"BUY_NOW", "BUY_SMALL"}:
            gated_valid, gated_reason = validate_direction_record(gated)
            lab_valid, lab_reason = validate_direction_record(lab)
            if not gated_valid:
                mismatches.append(
                    f"{ticker}:ACTIONABLE_EXECUTION_DIRECTION_INVALID:{gated_reason}"
                )
            if not lab_valid:
                mismatches.append(
                    f"{ticker}:ACTIONABLE_LAB_DIRECTION_INVALID:{lab_reason}"
                )
    for ticker in sorted(set(lab_by_ticker) - set(gated_by_ticker)):
        mismatches.append(f"{ticker}:UNEXPECTED_LAB_ROW")
    return mismatches


def _olm_execution_mismatches(
    gated_rows: Iterable[Mapping[str, Any]],
) -> list[str]:
    """Return lifecycle/action violations before any Lab artifact is written."""

    mismatches: list[str] = []
    for row in gated_rows:
        ticker = str(row.get("ticker", "") or "").strip().upper() or "UNKNOWN"
        decision = evaluate_olm_execution_guard(row, require_contract=True)
        action = str(row.get("final_action", "") or "").strip().upper()
        if not action_is_within_guard(action, decision):
            mismatches.append(
                f"{ticker}:OLM_ACTION_EXCEEDS_{decision.disposition}:"
                f"{action or 'MISSING'}:{decision.reason}"
            )
        emitted_disposition = str(
            row.get("olm_guard_disposition", "") or ""
        ).strip().upper()
        emitted_reason = str(row.get("olm_guard_reason", "") or "").strip().upper()
        if emitted_disposition != decision.disposition:
            mismatches.append(
                f"{ticker}:OLM_GUARD_DISPOSITION_DRIFT:"
                f"{emitted_disposition or 'MISSING'}->{decision.disposition}"
            )
        if emitted_reason != decision.reason.upper():
            mismatches.append(
                f"{ticker}:OLM_GUARD_REASON_DRIFT:"
                f"{emitted_reason or 'MISSING'}->{decision.reason}"
            )
    return mismatches


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )
    temporary.replace(path)


def _session_date_from_run(run_id: str) -> str:
    raw = str(run_id or "").strip()[:8]
    try:
        return datetime.strptime(raw, "%Y%m%d").date().isoformat()
    except ValueError:
        return datetime.now(timezone.utc).date().isoformat()


def _msi_identity_preflight(
    *,
    run_id: str,
    run_dir: Path,
    rows: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    """Validate every actionable identity before atomic materialisation.

    The materializer remains the final authority.  This preflight records all
    missing identities in one operator-readable report and never invents a
    thesis, trade idea, structure, contract, or quote snapshot identifier.
    """

    required = (
        "ticker",
        "thesis_id",
        "trade_idea_id",
        "selected_structure_id",
        "selected_contract_symbol",
        "selected_quote_snapshot_id",
    )
    failures: list[dict[str, Any]] = []
    checked = 0
    for raw in rows:
        row = dict(raw)
        checked += 1
        values = {
            "ticker": str(row.get("ticker") or "").strip().upper(),
            "thesis_id": str(row.get("thesis_id") or "").strip(),
            "trade_idea_id": str(row.get("trade_idea_id") or "").strip(),
            "selected_structure_id": str(
                row.get("selected_structure_id") or ""
            ).strip(),
            "selected_contract_symbol": _contract_identity(row),
            "selected_quote_snapshot_id": str(
                row.get("selected_quote_snapshot_id") or ""
            ).strip(),
        }
        missing = [field for field in required if not values[field]]
        observed_run_id = str(row.get("run_id") or run_id).strip()
        if observed_run_id != run_id:
            missing.append("run_id_mismatch")
        if missing:
            failures.append(
                {
                    "ticker": values["ticker"] or "UNKNOWN",
                    "missing": missing,
                    "observed_run_id": observed_run_id,
                }
            )

    report = {
        "schema_version": "msi_identity_preflight_v1",
        "run_id": run_id,
        "status": "PASS" if not failures else "FAIL",
        "checked_at_utc": _utc_now(),
        "actionable_rows": checked,
        "failed_rows": len(failures),
        "required_identity_fields": list(required),
        "failures": failures,
    }
    report_path = run_dir / "diagnostics" / "msi_identity_preflight.json"
    _atomic_json(report_path, report)
    report["report_path"] = str(report_path)
    return report


def _macro_reference(run_dir: Path, session_date: str) -> dict[str, Any] | None:
    packet_path = run_dir / "macro_quant_packet.json"
    if not packet_path.is_file():
        return None
    try:
        payload = json.loads(packet_path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, Mapping):
        return None
    as_of = str(
        payload.get("as_of_utc")
        or payload.get("generated_at_utc")
        or payload.get("created_at_utc")
        or ""
    ).strip()
    if not as_of:
        return None
    packet_hash = _sha256(packet_path)
    return {
        "packet_id": str(
            payload.get("packet_id")
            or payload.get("macro_packet_id")
            or f"MACRO:{packet_hash[:24]}"
        ),
        "path": str(packet_path.resolve()),
        "sha256": packet_hash,
        "as_of_utc": as_of,
        "session_date": str(payload.get("session_date") or session_date),
        "freshness": str(
            payload.get("macro_freshness_status")
            or payload.get("freshness")
            or "UNKNOWN"
        ).upper(),
        "quality": str(
            payload.get("macro_data_quality") or payload.get("quality") or "UNKNOWN"
        ).upper(),
        "macro_context_state": str(
            payload.get("macro_context_state")
            or payload.get("regime_state")
            or "NEUTRAL"
        ).upper(),
    }


def _publish_msi_handoff(
    *,
    run_id: str,
    run_dir: Path,
    lab_rows: Iterable[Mapping[str, Any]],
    completed_at_utc: str,
    macro_reference: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    from msi_runtime import active_flags
    from contracts.dynamic_session_contract import DynamicSessionFeatureFlags

    flags = active_flags()
    dynamic_flags = DynamicSessionFeatureFlags.from_environment()
    if flags.lab_v3_view != flags.interpreter_resolver:
        raise MorningHandoffError(
            "MSI_LAB_V3_VIEW and MSI_INTERPRETER_RESOLVER must activate together"
        )
    if not flags.lab_v3_view:
        return {"status": "DISABLED", "feature_flags": flags.to_dict()}

    if dynamic_flags.lab_dynamic_view != dynamic_flags.interpreter_dynamic_resolver:
        raise MorningHandoffError(
            "dynamic Lab and Interpreter resolver flags must activate together"
        )

    validation_events: list[dict[str, Any]] = []
    if dynamic_flags.lab_dynamic_view:
        candidates = sorted(
            list((run_dir / "validation").glob("*.json"))
            + list((run_dir / "morning_validation" / "validation_events").glob("*.json"))
        )
        for path in candidates:
            try:
                payload = json.loads(path.read_text(encoding="utf-8-sig"))
            except (OSError, json.JSONDecodeError) as error:
                raise MorningHandoffError(
                    f"dynamic validation event unreadable: {path}: {error}"
                ) from error
            if isinstance(payload, Mapping):
                validation_events.append(dict(payload))

    source_rows = [dict(row) for row in lab_rows]
    actionable = [
        dict(row)
        for row in source_rows
        if str(row.get("final_action") or "").strip().upper()
        in {"BUY_NOW", "BUY_SMALL"}
    ]
    if not actionable:
        status_path = run_dir / "interpreter" / "handoff_status.json"
        status = {
            "schema_version": "interpreter_handoff_status_v1",
            "run_id": run_id,
            "status": "NO_ACTIONABLE_SIGNALS",
            "completed_at_utc": completed_at_utc,
            "actionable_rows": 0,
        }
        _atomic_json(status_path, status)
        return {**status, "status_path": str(status_path)}

    meta_path = run_dir / "run_meta.json"
    try:
        run_meta = json.loads(meta_path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        run_meta = {}
    run_kind = str(run_meta.get("run_kind") or "PRODUCTION").upper()
    if run_kind != "PRODUCTION":
        raise MorningHandoffError(
            f"MSI production handoff cannot publish a {run_kind} run"
        )
    identity_preflight = _msi_identity_preflight(
        run_id=run_id,
        run_dir=run_dir,
        rows=actionable,
    )
    if identity_preflight["status"] != "PASS":
        examples = ";".join(
            f"{item['ticker']}:{','.join(item['missing'])}"
            for item in identity_preflight["failures"][:12]
        )
        raise MorningHandoffError(
            "MSI identity preflight failed before publication: "
            f"{examples}; report={identity_preflight['report_path']}"
        )
    session_date = _session_date_from_run(run_id)
    from contracts.interpreter_handoff_materializer import (
        materialize_interpreter_handoff,
    )
    from tools.msi_reconcile import reconcile_handoff

    result = materialize_interpreter_handoff(
        run_id=run_id,
        rows=actionable,
        run_root=run_dir,
        pipeline_mode="MORNING_VALIDATION",
        session_date=session_date,
        run_kind=run_kind,
        run_status="ACCEPTED",
        required_stage_status={
            "EOD": "PASS",
            "MORNING_GATE": "COMPLETED",
            "EXECUTION_GATE": "PASS",
            "LAB": "PASS",
        },
        morning_gate_completed_utc=completed_at_utc,
        macro_reference=macro_reference or _macro_reference(run_dir, session_date),
        validation_events=validation_events,
        require_validation_lineage=dynamic_flags.lab_dynamic_view,
    )
    independent = reconcile_handoff(result["handoff_manifest_path"])
    if independent.get("status") != "PASS":
        raise MorningHandoffError(
            "MSI independent reconciliation failed: "
            + ";".join(independent.get("mismatches") or [])
        )

    if dynamic_flags.decision_outcome_ledger:
        from canonical_data.decision_outcome_ledger import (
            DecisionOutcomeLedger,
            candidate_events_from_rows,
            make_ledger_event,
        )

        ledger_path = run_dir.parents[2] / "canonical" / "decision_outcome_ledger.sqlite"
        ledger = DecisionOutcomeLedger(ledger_path)
        ledger.append_many(candidate_events_from_rows(
            source_rows, run_id=run_id, occurred_at_utc=completed_at_utc,
        ))
        for event in validation_events:
            ledger.append(make_ledger_event(
                event_type="VALIDATION",
                occurred_at_utc=str(event.get("evidence_cutoff_utc") or completed_at_utc),
                run_id=run_id,
                ticker=str(event.get("ticker") or ""),
                thesis_id=str(event.get("thesis_id") or ""),
                validation_event_id=str(event.get("validation_event_id") or ""),
                payload=event,
            ))
        result["decision_outcome_ledger"] = {
            "path": str(ledger_path),
            "candidate_events": len(source_rows),
            "validation_events": len(validation_events),
            "append_only": True,
        }

    structured_flag_names = (
        "v2_capture", "cds_resolver", "minute_bars", "structure",
        "lab_v3_view", "macro_advisory", "interpreter_resolver",
    )
    governed_full_flag_run = bool(
        run_meta.get("msi_config_hash") and isinstance(run_meta.get("msi_feature_flags"), Mapping)
    )
    if governed_full_flag_run and all(getattr(flags, name) for name in structured_flag_names):
        from tools.msi_production_readiness import assess_run
        production_readiness = assess_run(
            run_id, runs_dir=run_dir.parent, flags=flags,
        )
        readiness_path = run_dir / "diagnostics" / "msi_production_readiness.json"
        _atomic_json(readiness_path, production_readiness)
        production_readiness["report_path"] = str(readiness_path)
        if production_readiness.get("status") != "PASS":
            raise MorningHandoffError(
                "MSI production readiness failed: "
                + ";".join(production_readiness.get("errors") or [])
            )
    else:
        production_readiness = {
            "status": "SKIPPED_NON_GOVERNED_OR_PARTIAL_TEST_FLAGS",
            "feature_flags": flags.to_dict(),
        }

    if meta_path.is_file():
        run_meta["run_status"] = "ACCEPTED"
        run_meta["pipeline_mode"] = "MORNING_VALIDATION"
        run_meta["operator_accepted_by"] = "MORNING_HANDOFF_FINALIZER"
        run_meta["operator_accepted_at_utc"] = completed_at_utc
        run_meta["msi_handoff_manifest_path"] = result["handoff_manifest_path"]
        _atomic_json(meta_path, run_meta)
    return {
        **result,
        "feature_flags": flags.to_dict(),
        "identity_preflight": identity_preflight,
        "independent_reconciliation": independent,
        "production_readiness": production_readiness,
    }


def _sync_and_verify(paths: Iterable[Path]) -> list[dict[str, Any]]:
    # The repository contains both pipeline_interpreter.py and a same-named
    # directory.  When the module has already been imported, normal dotted
    # import cannot reach the directory.  Load the sync implementation by its
    # governed file path as a deterministic fallback.
    try:
        from pipeline_interpreter.ma_inputs_sync import MA_PIPELINE_OUT, sync_file
    except (ImportError, ModuleNotFoundError):
        sync_path = REPO_ROOT / "pipeline_interpreter" / "ma_inputs_sync.py"
        spec = importlib.util.spec_from_file_location(
            "avshunter_morning_ma_inputs_sync",
            sync_path,
        )
        if spec is None or spec.loader is None:
            raise MorningHandoffError(f"Cannot load Interpreter sync module: {sync_path}")
        sync_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(sync_module)
        MA_PIPELINE_OUT = sync_module.MA_PIPELINE_OUT
        sync_file = sync_module.sync_file

    results: list[dict[str, Any]] = []
    for source in paths:
        source = Path(source)
        if not source.exists():
            raise MorningHandoffError(f"Required handoff artifact is missing: {source}")
        if not sync_file(source, verbose=True, force=True):
            raise MorningHandoffError(f"Interpreter sync rejected required artifact: {source}")
        destination = Path(MA_PIPELINE_OUT) / source.name
        if not destination.exists():
            raise MorningHandoffError(f"Interpreter destination was not created: {destination}")
        source_hash = _sha256(source)
        destination_hash = _sha256(destination)
        if source_hash != destination_hash:
            raise MorningHandoffError(
                f"Interpreter copy hash mismatch: {source} -> {destination}"
            )
        results.append(
            {
                "source": str(source),
                "destination": str(destination),
                "sha256": source_hash,
                "verified": True,
            }
        )
    return results


def sync_verified_morning_handoff(summary: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Publish an already-materialised handoff after its integrity gate passes.

    Keeping this step separate allows the Morning entry point to materialise the
    Lab book, compare it with the governed Morning rows, and only then expose the
    artifacts to the Pipeline Interpreter.
    """
    execution_summary = dict(summary.get("execution_gate_summary", {}) or {})
    required_paths = [
        Path(str(summary.get("source_path") or "")),
        Path(str(execution_summary.get("gated_csv") or "")),
        Path(str(summary.get("lab_triage_path") or "")),
        Path(str(summary.get("lab_csv_path") or "")),
    ]
    if any(not str(path) or str(path) == "." for path in required_paths):
        raise MorningHandoffError("Cannot sync an incomplete Morning handoff summary")

    sync_results = _sync_and_verify(required_paths)
    summary_path = Path(str(summary.get("summary_path") or ""))
    if summary_path and str(summary_path) != ".":
        updated = dict(summary)
        updated["interpreter_sync"] = sync_results
        updated["interpreter_sync_status"] = "PASS"
        updated["interpreter_synced_at_utc"] = _utc_now()
        _atomic_json(summary_path, updated)
    return sync_results


def finalize_morning_handoff(
    run_id: str,
    results: Optional[Iterable[Mapping[str, Any]]] = None,
    *,
    runs_dir: Path | str = DEFAULT_RUNS_DIR,
    sync_interpreter: bool = True,
) -> dict[str, Any]:
    """Materialise and verify every downstream artifact for one Morning run.

    Passing ``results`` is used by the live Morning entry points.  Omitting it
    replays the already-written Morning CSV and is therefore safe for offline
    recovery: no market-data code is imported or called by this module.
    """

    run_id = str(run_id or "").strip()
    if not run_id:
        raise MorningHandoffError("run_id is required")

    run_dir = Path(runs_dir) / run_id
    morning_dir = run_dir / "morning_validation"
    morning_path = morning_dir / f"morning_validated_trades_{run_id}.csv"
    source_rows = _normalise_rows(results) if results is not None else _read_csv(morning_path)
    session_date = _session_date_from_run(run_id)

    from execution_gate import run_execution_gate
    from contracts.lab_control import (
        write_final_opportunity_book,
        write_final_run_manifest,
    )

    gated_rows, gate_summary = run_execution_gate(
        signals=source_rows,
        run_id=run_id,
        output_dir=run_dir / "trades",
    )
    if len(gated_rows) != len(source_rows):
        raise MorningHandoffError(
            f"Execution Gate reconciliation failed: input={len(source_rows)} "
            f"output={len(gated_rows)}"
        )

    olm_mismatches = _olm_execution_mismatches(gated_rows)
    if olm_mismatches:
        preview = "; ".join(olm_mismatches[:12])
        raise MorningHandoffError(
            "OLM Execution Gate invariant failed before Lab publication: "
            f"{preview}"
        )

    # Snapshot the latest valid canonical macro sources at the Morning boundary.
    # Only advisory fields are added; execution authority fields are never read
    # from or mutated by this packet.
    macro_materialization = materialize_interpreter_macro_context(
        run_dir=run_dir,
        session_date=session_date,
        macro_dir=REPO_ROOT / "dropbox" / "macro",
    )
    macro_packet = dict(macro_materialization["packet"])
    macro_reference = dict(macro_materialization["reference"])
    for row in gated_rows:
        before_authority = {
            key: row.get(key)
            for key in (
                "governed_direction", "selected_contract_symbol", "thesis_state",
                "olm_guard_disposition", "final_action", "capital_permission",
                "execution_permission", "position_size_pct",
            )
        }
        row.update(
            advisory_fields_for_row(
                macro_packet,
                row,
                packet_sha256=str(macro_reference.get("sha256") or ""),
            )
        )
        after_authority = {key: row.get(key) for key in before_authority}
        if before_authority != after_authority:
            raise MorningHandoffError("Macro advisory mutated governed authority fields")

    manifest = write_final_run_manifest(
        run_id,
        Path(runs_dir),
        pipeline_mode="MORNING_VALIDATION",
    )
    lab_book = write_final_opportunity_book(
        run_id,
        gated_rows,
        manifest,
        Path(runs_dir),
        sync_interpreter=False,
    )
    lab_rows = list(lab_book.get("rows") or [])
    if len(lab_rows) != len(source_rows):
        raise MorningHandoffError(
            f"Intelligence Lab reconciliation failed: input={len(source_rows)} "
            f"lab={len(lab_rows)}"
        )

    authority_mismatches = _execution_lab_mismatches(gated_rows, lab_rows)
    direction_versions = {
        str(row.get("dir_calc_version", "") or "").strip()
        for row in gated_rows
    }
    if direction_versions != {DIR_CALC_VERSION}:
        authority_mismatches.append(
            "RUN:DIRECTION_VERSION_SET_INVALID:"
            + ",".join(sorted(value or "MISSING" for value in direction_versions))
        )
    if authority_mismatches:
        preview = "; ".join(authority_mismatches[:12])
        raise MorningHandoffError(
            "Execution Gate -> Intelligence Lab authority reconciliation failed: "
            f"{preview}"
        )

    source_go = sum(
        1
        for row in source_rows
        if str(row.get("morning_execution_permission", "")).upper()
        in ACTIONABLE_LAB_VERDICTS
    )
    lab_actionable = sum(
        1
        for row in lab_rows
        if str(row.get("lab_verdict", "")).upper() in ACTIONABLE_LAB_VERDICTS
    )
    if source_go and not lab_actionable:
        raise MorningHandoffError(
            f"Morning authority was lost in the Lab handoff: source_actionable={source_go}, "
            "lab_actionable=0"
        )

    gated_path = Path(str(gate_summary.get("gated_csv") or ""))
    triage_path = Path(str(lab_book.get("triage_csv_path") or ""))
    final_book_path = Path(str(lab_book.get("csv_path") or ""))
    required_paths = [morning_path, gated_path, triage_path, final_book_path]
    completed_at_utc = _utc_now()
    msi_handoff = _publish_msi_handoff(
        run_id=run_id,
        run_dir=run_dir,
        lab_rows=lab_rows,
        completed_at_utc=completed_at_utc,
        macro_reference=macro_reference,
    )
    sync_results = _sync_and_verify(required_paths) if sync_interpreter else []

    summary = {
        "schema_version": HANDOFF_VERSION,
        "run_id": run_id,
        "completed_at_utc": completed_at_utc,
        "status": "PASS",
        "api_requests": 0,
        "source_path": str(morning_path),
        "source_rows": len(source_rows),
        "execution_rows": len(gated_rows),
        "lab_rows": len(lab_rows),
        "source_verdict_counts": _count(source_rows, "verdict"),
        "source_permission_counts": _count(source_rows, "morning_execution_permission"),
        "execution_action_counts": _count(gated_rows, "final_action"),
        "lab_verdict_counts": _count(lab_rows, "lab_verdict"),
        "source_actionable": source_go,
        "lab_actionable": lab_actionable,
        "execution_gate_summary": gate_summary,
        "lab_csv_path": str(final_book_path),
        "lab_triage_path": str(triage_path),
        "interpreter_sync": sync_results,
        "msi_handoff": msi_handoff,
        "macro_advisory": {
            "packet_id": macro_reference.get("packet_id"),
            "packet_path": macro_materialization.get("packet_path"),
            "sha256": macro_reference.get("sha256"),
            "source_fingerprint": macro_reference.get("source_fingerprint"),
            "freshness": macro_reference.get("freshness"),
            "quality": macro_reference.get("quality"),
            "authority": "ADVISORY_ONLY",
        },
        "reconciliation": {
            "source_equals_execution": len(source_rows) == len(gated_rows),
            "source_equals_lab": len(source_rows) == len(lab_rows),
            "morning_authority_preserved": not source_go or lab_actionable > 0,
            "execution_lab_exact_match": not authority_mismatches,
            "execution_lab_mismatch_count": len(authority_mismatches),
            "direction_version": DIR_CALC_VERSION,
            "direction_version_uniform": direction_versions == {DIR_CALC_VERSION},
        },
    }
    summary_path = morning_dir / f"morning_handoff_summary_{run_id}.json"
    summary["summary_path"] = str(summary_path)
    _atomic_json(summary_path, summary)
    log.info(
        "Morning handoff PASS: run=%s rows=%d source_actionable=%d lab_actionable=%d",
        run_id,
        len(source_rows),
        source_go,
        lab_actionable,
    )
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Recover/finalise a completed AVSHUNTER Morning run without API calls"
    )
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--runs-dir", default=str(DEFAULT_RUNS_DIR))
    parser.add_argument("--no-interpreter-sync", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
    try:
        summary = finalize_morning_handoff(
            args.run_id,
            runs_dir=Path(args.runs_dir),
            sync_interpreter=not args.no_interpreter_sync,
        )
    except Exception as error:
        log.exception("Morning handoff failed: %s", error)
        return 1
    print(json.dumps(summary, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
