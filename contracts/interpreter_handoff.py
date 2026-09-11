"""Governed, atomic Lab-to-Interpreter handoff contracts for MSI v1.1.

This module contains no market-data or model calls.  It validates immutable
files produced by the pipeline and publishes a single manifest baton only
after every referenced artefact and per-ticker bundle has been verified.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import tempfile
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


HANDOFF_SCHEMA_VERSION = "interpreter_handoff_manifest_v1"
BUNDLE_SCHEMA_VERSION = "interpreter_evidence_bundle_v1"
BOOK_SCHEMA_VERSION = "lab_signal_book_v3"
AUTHORITY_MAP_VERSION = "msi-authority-v1.1"


class RunKind(str, Enum):
    PRODUCTION = "PRODUCTION"
    TEST = "TEST"
    REPLAY = "REPLAY"
    REPAIR = "REPAIR"
    RESEARCH = "RESEARCH"


class RunStatus(str, Enum):
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    ABORTED = "ABORTED"
    ACCEPTED = "ACCEPTED"


SUCCESSFUL_TERMINAL_RUN_STATUSES = frozenset({
    RunStatus.COMPLETED,
    RunStatus.ACCEPTED,
})


def is_successful_terminal_run_status(value: Any) -> bool:
    """Return whether a run is immutable enough for downstream evidence use.

    ``COMPLETED`` is the successful terminal state produced by the pipeline
    before production acceptance. ``ACCEPTED`` is the stronger terminal state
    applied after the governed Lab/Interpreter handoff has reconciled. Both are
    eligible evidence sources; in-progress, aborted and unknown states are not.
    Consumers must still validate technical health, fatal flags and artifact
    identity independently.
    """

    if isinstance(value, RunStatus):
        status = value
    else:
        try:
            status = RunStatus(str(value or "").strip().upper())
        except ValueError:
            return False
    return status in SUCCESSFUL_TERMINAL_RUN_STATUSES


class HandoffStatus(str, Enum):
    READY = "READY"
    BLOCKED_MISSING_STAGE = "BLOCKED_MISSING_STAGE"
    BLOCKED_IDENTITY = "BLOCKED_IDENTITY"
    BLOCKED_HASH = "BLOCKED_HASH"
    BLOCKED_RECONCILIATION = "BLOCKED_RECONCILIATION"


class HandoffValidationError(ValueError):
    """A handoff cannot be trusted for production interpretation."""


REQUIRED_BUNDLE_IDENTITY = (
    "run_id",
    "pipeline_mode",
    "ticker",
    "thesis_id",
    "trade_idea_id",
    "selected_structure_id",
    "selected_contract_symbol",
    "selected_quote_snapshot_id",
    "bundle_id",
    "bundle_created_utc",
    "bundle_schema_version",
    "authority_map_version",
)

REQUIRED_ARTIFACT_ROLES = {
    "LAB_BOOK",
    "LAB_BOOK_MANIFEST",
    "INTERPRETER_BUNDLES",
    "RECONCILIATION_REPORT",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path | str) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _text(value: Any) -> str:
    text = str(value or "").strip()
    return "" if text.upper() in {"NAN", "NONE", "NULL", "N/A"} else text


def _canonical_occ(value: Any) -> str:
    return _text(value).upper().replace("O:", "").replace(" ", "")


def _require_timestamp(value: Any, field: str) -> None:
    raw = _text(value)
    if not raw:
        raise HandoffValidationError(f"MISSING_{field.upper()}")
    try:
        datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as error:
        raise HandoffValidationError(f"INVALID_{field.upper()}:{raw}") from error


def validate_evidence_bundle(bundle: Mapping[str, Any]) -> dict[str, Any]:
    value = dict(bundle)
    missing = [field for field in REQUIRED_BUNDLE_IDENTITY if not _text(value.get(field))]
    if missing:
        raise HandoffValidationError("BUNDLE_MISSING_IDENTITY:" + ",".join(missing))
    if value["bundle_schema_version"] != BUNDLE_SCHEMA_VERSION:
        raise HandoffValidationError("BUNDLE_SCHEMA_UNSUPPORTED")
    if value["authority_map_version"] != AUTHORITY_MAP_VERSION:
        raise HandoffValidationError("AUTHORITY_MAP_UNSUPPORTED")
    validation = value.get("current_validation")
    if validation:
        if not isinstance(validation, Mapping):
            raise HandoffValidationError("BUNDLE_VALIDATION_EVENT_INVALID")
        validation_id = _text(validation.get("validation_event_id"))
        governed_id = _text(
            (value.get("governed_record") or {}).get("validation_event_id")
        )
        if not validation_id or validation_id != governed_id:
            raise HandoffValidationError("BUNDLE_VALIDATION_EVENT_ID_MISMATCH")
        for field in ("ticker", "thesis_id"):
            if _text(validation.get(field)).upper() != _text(value.get(field)).upper():
                raise HandoffValidationError(
                    f"BUNDLE_VALIDATION_EVENT_IDENTITY_MISMATCH:{field}"
                )
    try:
        uuid.UUID(_text(value["bundle_id"]))
    except ValueError as error:
        raise HandoffValidationError("BUNDLE_ID_NOT_UUID") from error
    _require_timestamp(value["bundle_created_utc"], "bundle_created_utc")
    value["ticker"] = _text(value["ticker"]).upper()
    value["selected_contract_symbol"] = _canonical_occ(
        value["selected_contract_symbol"]
    )
    if not value["selected_contract_symbol"]:
        raise HandoffValidationError("BUNDLE_SELECTED_CONTRACT_MISSING")
    if not isinstance(value.get("authority_map"), Mapping):
        raise HandoffValidationError("BUNDLE_AUTHORITY_MAP_MISSING")
    if not isinstance(value.get("freshness_map"), Mapping):
        raise HandoffValidationError("BUNDLE_FRESHNESS_MAP_MISSING")
    governed = value.get("governed_record")
    if not isinstance(governed, Mapping):
        raise HandoffValidationError("BUNDLE_GOVERNED_RECORD_MISSING")
    for field in (
        "run_id",
        "ticker",
        "thesis_id",
        "trade_idea_id",
        "selected_structure_id",
        "selected_quote_snapshot_id",
    ):
        if _text(governed.get(field)).upper() != _text(value.get(field)).upper():
            raise HandoffValidationError(f"BUNDLE_GOVERNED_IDENTITY_MISMATCH:{field}")
    governed_contract = _canonical_occ(
        governed.get("selected_contract_symbol")
        or governed.get("contract_symbol")
        or governed.get("morning_selected_contract_symbol")
    )
    if governed_contract != value["selected_contract_symbol"]:
        raise HandoffValidationError("BUNDLE_GOVERNED_IDENTITY_MISMATCH:selected_contract_symbol")
    doi_state = _text(governed.get("doi_projection_state")).upper()
    if doi_state:
        if _text(governed.get("doi_authority")).upper() != "ADVISORY_ONLY":
            raise HandoffValidationError("BUNDLE_DOI_AUTHORITY_INVALID")
        # `_text` deliberately treats the token NONE as missing for ordinary
        # identity fields; here NONE is the required authority value.
        if str(governed.get("doi_decision_authority") or "").strip().upper() != "NONE":
            raise HandoffValidationError("BUNDLE_DOI_DECISION_AUTHORITY_INVALID")
        if _text(governed.get("doi_execution_authority")).upper() != "HUMAN_ONLY":
            raise HandoffValidationError("BUNDLE_DOI_EXECUTION_AUTHORITY_INVALID")
        if doi_state in {"CALIBRATED", "DETERMINISTIC_UNCALIBRATED"}:
            for field in ("doi_family_id", "doi_ranking_id", "doi_evidence_cutoff_utc"):
                if not _text(governed.get(field)):
                    raise HandoffValidationError(f"BUNDLE_DOI_LINEAGE_MISSING:{field}")
    return value


def load_bundle_jsonl(path: Path | str) -> list[dict[str, Any]]:
    bundles: list[dict[str, Any]] = []
    identities: set[tuple[str, str, str]] = set()
    with Path(path).open("r", encoding="utf-8-sig") as handle:
        for number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                bundle = validate_evidence_bundle(json.loads(line))
            except (json.JSONDecodeError, HandoffValidationError) as error:
                raise HandoffValidationError(f"INVALID_BUNDLE_LINE:{number}:{error}") from error
            identity = (bundle["run_id"], bundle["ticker"], bundle["bundle_id"])
            if identity in identities:
                raise HandoffValidationError(f"DUPLICATE_BUNDLE_IDENTITY:{number}")
            identities.add(identity)
            bundles.append(bundle)
    if not bundles:
        raise HandoffValidationError("BUNDLE_FILE_EMPTY")
    return bundles


def read_book_rows(path: Path | str) -> list[dict[str, Any]]:
    book = Path(path)
    if book.suffix.lower() == ".csv":
        with book.open("r", encoding="utf-8-sig", newline="") as handle:
            return [dict(row) for row in csv.DictReader(handle)]
    payload = json.loads(book.read_text(encoding="utf-8-sig"))
    rows = payload.get("rows") if isinstance(payload, Mapping) else payload
    if not isinstance(rows, list):
        raise HandoffValidationError("LAB_BOOK_ROWS_INVALID")
    return [dict(row) for row in rows if isinstance(row, Mapping)]


def _validate_book_bundle_identity(
    row: Mapping[str, Any], bundle: Mapping[str, Any]
) -> None:
    for field in (
        "run_id", "ticker", "thesis_id", "trade_idea_id",
        "selected_structure_id", "selected_quote_snapshot_id",
    ):
        if _text(row.get(field)).upper() != _text(bundle.get(field)).upper():
            raise HandoffValidationError(f"HANDOFF_BOOK_BUNDLE_IDENTITY_MISMATCH:{field}")
    row_contract = _canonical_occ(
        row.get("selected_contract_symbol")
        or row.get("contract_symbol")
        or row.get("morning_selected_contract_symbol")
    )
    if row_contract != _canonical_occ(bundle.get("selected_contract_symbol")):
        raise HandoffValidationError(
            "HANDOFF_BOOK_BUNDLE_IDENTITY_MISMATCH:selected_contract_symbol"
        )
    validation = bundle.get("current_validation") or {}
    if validation and _text(row.get("validation_event_id")) != _text(
        validation.get("validation_event_id")
    ):
        raise HandoffValidationError(
            "HANDOFF_BOOK_BUNDLE_VALIDATION_ID_MISMATCH"
        )
    governed = dict(bundle.get("governed_record") or {})
    for field in (
        "governed_direction", "thesis_state", "olm_guard_disposition",
        "final_action", "capital_permission",
    ):
        if _text(row.get(field)).upper() != _text(governed.get(field)).upper():
            raise HandoffValidationError(f"HANDOFF_BOOK_BUNDLE_AUTHORITY_MISMATCH:{field}")


def _safe_artifact_path(manifest_path: Path, raw: Any) -> Path:
    candidate = Path(_text(raw))
    if not candidate.is_absolute():
        candidate = (manifest_path.parent / candidate).resolve()
    else:
        candidate = candidate.resolve()
    run_root = manifest_path.parent.parent.resolve()
    try:
        candidate.relative_to(run_root)
    except ValueError as error:
        raise HandoffValidationError(f"ARTIFACT_OUTSIDE_RUN:{candidate}") from error
    return candidate


@dataclass(frozen=True, slots=True)
class ValidatedHandoff:
    manifest_path: Path
    manifest: dict[str, Any]
    artifacts: dict[str, Path]
    bundles: tuple[dict[str, Any], ...]
    book_rows: tuple[dict[str, Any], ...]


def validate_handoff_manifest(
    manifest_path: Path | str,
    *,
    require_accepted: bool = True,
) -> ValidatedHandoff:
    path = Path(manifest_path).resolve()
    try:
        manifest = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as error:
        raise HandoffValidationError(f"HANDOFF_MANIFEST_UNREADABLE:{path}") from error
    if manifest.get("schema_version") != HANDOFF_SCHEMA_VERSION:
        raise HandoffValidationError("HANDOFF_SCHEMA_UNSUPPORTED")
    if manifest.get("handoff_status") != HandoffStatus.READY.value:
        raise HandoffValidationError("HANDOFF_NOT_READY")
    if require_accepted:
        if manifest.get("run_kind") != RunKind.PRODUCTION.value:
            raise HandoffValidationError("HANDOFF_NOT_PRODUCTION")
        if manifest.get("run_status") != RunStatus.ACCEPTED.value:
            raise HandoffValidationError("HANDOFF_RUN_NOT_ACCEPTED")
    for field in ("run_id", "pipeline_mode", "session_date", "published_at_utc"):
        if not _text(manifest.get(field)):
            raise HandoffValidationError(f"HANDOFF_MISSING_{field.upper()}")
    _require_timestamp(manifest["published_at_utc"], "published_at_utc")
    records = manifest.get("artifacts")
    if not isinstance(records, Sequence) or isinstance(records, (str, bytes)):
        raise HandoffValidationError("HANDOFF_ARTIFACTS_INVALID")
    artifacts: dict[str, Path] = {}
    for record in records:
        if not isinstance(record, Mapping):
            raise HandoffValidationError("HANDOFF_ARTIFACT_RECORD_INVALID")
        role = _text(record.get("role")).upper()
        artifact = _safe_artifact_path(path, record.get("path"))
        if role in artifacts:
            raise HandoffValidationError(f"HANDOFF_DUPLICATE_ARTIFACT_ROLE:{role}")
        if not artifact.is_file():
            raise HandoffValidationError(f"HANDOFF_ARTIFACT_MISSING:{role}")
        if sha256_file(artifact) != _text(record.get("sha256")).lower():
            raise HandoffValidationError(f"HANDOFF_ARTIFACT_HASH_MISMATCH:{role}")
        artifacts[role] = artifact
    missing_roles = REQUIRED_ARTIFACT_ROLES - set(artifacts)
    if missing_roles:
        raise HandoffValidationError(
            "HANDOFF_REQUIRED_ARTIFACT_MISSING:" + ",".join(sorted(missing_roles))
        )
    bundles = load_bundle_jsonl(artifacts["INTERPRETER_BUNDLES"])
    rows = read_book_rows(artifacts["LAB_BOOK"])
    run_id = _text(manifest["run_id"])
    if any(bundle["run_id"] != run_id for bundle in bundles):
        raise HandoffValidationError("HANDOFF_BUNDLE_RUN_MISMATCH")
    bundle_tickers = {bundle["ticker"] for bundle in bundles}
    row_tickers = {_text(row.get("ticker")).upper() for row in rows if _text(row.get("ticker"))}
    if len(row_tickers) != len(rows):
        raise HandoffValidationError("HANDOFF_BOOK_DUPLICATE_OR_MISSING_TICKER")
    if bundle_tickers != row_tickers:
        raise HandoffValidationError("HANDOFF_BOOK_BUNDLE_TICKER_MISMATCH")
    row_by_ticker = {_text(row.get("ticker")).upper(): row for row in rows}
    for bundle in bundles:
        _validate_book_bundle_identity(row_by_ticker[bundle["ticker"]], bundle)
    if int(manifest.get("ticker_count", -1)) != len(row_tickers):
        raise HandoffValidationError("HANDOFF_TICKER_COUNT_MISMATCH")
    if int(manifest.get("bundle_count", -1)) != len(bundles):
        raise HandoffValidationError("HANDOFF_BUNDLE_COUNT_MISMATCH")
    if int(manifest.get("missing_bundle_count", -1)) != 0:
        raise HandoffValidationError("HANDOFF_MISSING_BUNDLES")
    return ValidatedHandoff(path, manifest, artifacts, tuple(bundles), tuple(rows))


def artifact_record(role: str, path: Path | str, schema_version: str) -> dict[str, Any]:
    artifact = Path(path).resolve()
    if not artifact.is_file():
        raise HandoffValidationError(f"ARTIFACT_MISSING:{role}:{artifact}")
    return {
        "role": role.upper(),
        "path": str(artifact),
        "schema_version": schema_version,
        "size_bytes": artifact.stat().st_size,
        "sha256": sha256_file(artifact),
    }


def publish_handoff_manifest(
    target: Path | str,
    *,
    run_id: str,
    pipeline_mode: str,
    session_date: str,
    run_kind: RunKind | str,
    run_status: RunStatus | str,
    required_stage_status: Mapping[str, Any],
    morning_gate_completed_utc: str,
    artifacts: Iterable[Mapping[str, Any]],
    ticker_count: int,
    bundle_count: int,
    reconciliation_status: str,
    producer_version: str,
) -> Path:
    """Atomically publish the production baton after full self-validation."""

    destination = Path(target).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    kind = run_kind.value if isinstance(run_kind, RunKind) else str(run_kind).upper()
    status = run_status.value if isinstance(run_status, RunStatus) else str(run_status).upper()
    if kind != RunKind.PRODUCTION.value or status != RunStatus.ACCEPTED.value:
        raise HandoffValidationError("ONLY_ACCEPTED_PRODUCTION_HANDOFF_MAY_PUBLISH")
    if reconciliation_status != "PASS":
        raise HandoffValidationError("HANDOFF_RECONCILIATION_NOT_PASS")
    if any(str(value).upper() not in {"PASS", "COMPLETED", "ACCEPTED"} for value in required_stage_status.values()):
        raise HandoffValidationError("HANDOFF_REQUIRED_STAGE_NOT_COMPLETE")
    _require_timestamp(morning_gate_completed_utc, "morning_gate_completed_utc")
    records = [dict(record) for record in artifacts]
    payload = {
        "schema_version": HANDOFF_SCHEMA_VERSION,
        "handoff_status": HandoffStatus.READY.value,
        "run_id": _text(run_id),
        "pipeline_mode": _text(pipeline_mode).upper(),
        "session_date": _text(session_date),
        "run_kind": kind,
        "run_status": status,
        "required_stage_status": dict(required_stage_status),
        "morning_gate_completed_utc": morning_gate_completed_utc,
        "ticker_count": int(ticker_count),
        "bundle_count": int(bundle_count),
        "missing_bundle_count": max(0, int(ticker_count) - int(bundle_count)),
        "reconciliation_status": reconciliation_status,
        "producer_version": _text(producer_version),
        "published_at_utc": utc_now(),
        "artifacts": records,
    }
    fd, temp_name = tempfile.mkstemp(prefix=f".{destination.name}.", dir=destination.parent)
    os.close(fd)
    temporary = Path(temp_name)
    try:
        temporary.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        validate_handoff_manifest(temporary)
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    return destination


__all__ = [
    "AUTHORITY_MAP_VERSION",
    "BOOK_SCHEMA_VERSION",
    "BUNDLE_SCHEMA_VERSION",
    "HANDOFF_SCHEMA_VERSION",
    "HandoffStatus",
    "HandoffValidationError",
    "RunKind",
    "RunStatus",
    "ValidatedHandoff",
    "artifact_record",
    "canonical_json",
    "load_bundle_jsonl",
    "publish_handoff_manifest",
    "read_book_rows",
    "sha256_file",
    "validate_evidence_bundle",
    "validate_handoff_manifest",
]
