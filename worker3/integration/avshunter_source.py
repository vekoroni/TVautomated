"""Read-only bridge from a completed AVSHUNTER run to Worker 3 evidence.

The bridge never calls a data provider, changes a production database, grants
capital, or chooses a different ticker/direction/contract.  It verifies one
explicit run, its Intelligence Lab book, and canonical dataset payloads before
constructing immutable Worker 3 evidence bundles.  Bad ticker rows are isolated
as data exceptions; they do not abort other tickers in the worklist.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from contextlib import closing
import hashlib
import json
import math
from pathlib import Path
import re
import sqlite3
from typing import Any
from zoneinfo import ZoneInfo

from contracts.interpreter_handoff import is_successful_terminal_run_status

from ..adapters.artifacts import ArtifactRef, read_artifact
from ..adapters.native import (
    attach_native_document,
    lab_snapshot_from_document,
    read_lab_document,
)
from ..application import _constant, _pairs
from ..lab_contract import SUPPORTED_LAB_SCHEMAS
from ..domain import (
    canonical,
    ContractError,
    Direction,
    EvidenceBundle,
    Identity,
    Observation,
    digest,
    instant,
    utc,
)
from ..market_environment import (
    MarketEnvironmentSnapshot,
    build_trade_plan,
    project_market_environment,
)
from ..macro_ticker_context import (
    macro_ticker_context_diagnostics,
    project_macro_ticker_context,
)


_RUN_ID = re.compile(r"\d{8}_\d{6}")
_TICKER = re.compile(r"[A-Z0-9][A-Z0-9.\-]*")
_OCC = re.compile(r"^[A-Z0-9]{1,6}\d{6}([CP])\d{8}$")
_HOLD_ENDPOINT = {"1_5d": 5, "6_10d": 10, "11_20d": 20}
_ALLOWED_ACTIONS = {"BUILD_THESIS", "VALIDATE_THESIS"}
_SELECTED_QUOTE_SCHEMAS = {
    "LIVE_OPTION": "selected_option_quote_v1",
    "EXACT_OPTION_QUOTE": "exact_option_quote_v2",
}
# Current governed Lab books are approximately 100 MiB for a 1,400-ticker run.
# Keep a finite ceiling while allowing the production-sized single-read batch.
MAX_LAB_BOOK_BYTES = 256_000_000


def _sha256(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def _safe_scalar(value: Any) -> str | int | float | bool | None:
    if value is None:
        return None
    if type(value) is float and not math.isfinite(value):
        return None
    if type(value) in (str, int, float, bool):
        return value
    raise ContractError("source value is not an immutable JSON scalar")


def _read_json(path: Path) -> tuple[dict[str, Any], str]:
    if not path.is_file() or path.is_symlink():
        raise ContractError(f"required regular file unavailable: {path.name}")
    source_hash = _sha256(path)
    ref = ArtifactRef(path.name, source_hash, f"avshunter:{path.name}")
    return read_artifact(path.parent, ref, max_bytes=64_000_000).payload(), source_hash


def _max_timestamp(*values: str) -> str:
    parsed = [instant(value) for value in values]
    return max(parsed).astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _session_close_utc(session: str) -> str:
    local = datetime.combine(
        datetime.fromisoformat(session).date(),
        time(16, 0),
        tzinfo=ZoneInfo("America/New_York"),
    )
    return local.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _direction(value: Any) -> Direction:
    text = str(value or "").strip().upper()
    if text == "CALL":
        return Direction.CALL
    if text == "PUT":
        return Direction.PUT
    if text in {"STRANGLE", "NON_DIRECTIONAL", "UNRESOLVED"}:
        return Direction.NON_DIRECTIONAL
    raise ContractError(f"unsupported governed direction: {text or 'MISSING'}")


def _selected_contract(row: dict[str, Any], direction: Direction) -> tuple[str | None, str | None, str | None]:
    symbol = str(row.get("contract_symbol") or "").strip().upper()
    contract_id = str(row.get("selected_structure_id") or "").strip()
    if not symbol and not contract_id:
        return None, None, None
    if not symbol or not contract_id:
        raise ContractError("partial selected-contract identity")
    if direction is Direction.NON_DIRECTIONAL:
        raise ContractError("non-directional thesis cannot carry a selected long option")
    match = _OCC.fullmatch(symbol)
    if match is None:
        raise ContractError("selected contract is not a canonical OCC symbol")
    side = Direction.CALL if match.group(1) == "C" else Direction.PUT
    if side is not direction:
        raise ContractError("selected contract side contradicts governed direction")
    return contract_id, symbol, "avshunter_selected_structure_v1"


@dataclass(frozen=True, slots=True)
class RunEvidenceContext:
    run_id: str
    invocation_id: str
    trading_session: str
    market_evidence_cutoff_utc: str
    bundle_cutoff_utc: str
    resolved_action: str
    execution_authority_ceiling: str
    plan_hash: str
    run_dir: Path
    lab_book_path: Path
    run_meta_hash: str
    final_manifest_hash: str
    lab_book_hash: str


@dataclass(frozen=True, slots=True)
class PreparedTicker:
    ticker: str
    status: str
    bundle: EvidenceBundle | None
    reason: str | None


@dataclass(frozen=True, slots=True)
class PreparedRun:
    context: RunEvidenceContext
    entries: tuple[PreparedTicker, ...]
    market_environment_status: str = "UNAVAILABLE"
    market_environment_error: str | None = None
    macro_ticker_context_diagnostics: tuple[tuple[str, Any], ...] = ()

    def summary(self) -> dict[str, Any]:
        ready = sum(entry.status == "EVIDENCE_PREPARED" for entry in self.entries)
        diagnostics = dict(self.macro_ticker_context_diagnostics) or macro_ticker_context_diagnostics(
            (), requested=0
        )
        return {
            "schema_version": "worker3_avshunter_bridge_summary_v1",
            "run_id": self.context.run_id,
            "requested": len(self.entries),
            "evidence_prepared": ready,
            "data_exceptions": len(self.entries) - ready,
            "provider_requests": 0,
            "production_writes": 0,
            "authority": "ADVISORY_ONLY",
            "capital_permission": False,
            "market_environment_status": self.market_environment_status,
            "market_environment_error": self.market_environment_error,
            **diagnostics,
        }


@dataclass(frozen=True, slots=True)
class _MacroRunEvidence:
    packet: dict[str, Any] | None
    packet_hash: str | None
    environment: MarketEnvironmentSnapshot | None
    error: str | None


@dataclass(frozen=True, slots=True)
class _Dataset:
    values: dict[str, Any]
    payload: Any
    record_hash: str


class AvshunterSourceBridge:
    """Prepare Worker 3 evidence from an explicit, completed run."""

    def __init__(self, repository_root: str | Path):
        self.root = Path(repository_root).resolve(strict=True)
        self.runs_root = (self.root / "data" / "output" / "runs").resolve(strict=True)
        self.canonical_root = (self.root / "data" / "canonical").resolve(strict=True)
        self.registry_path = (self.canonical_root / "control_plane.sqlite").resolve(strict=True)

    def _run_dir(self, run_id: str) -> Path:
        if type(run_id) is not str or _RUN_ID.fullmatch(run_id) is None:
            raise ContractError("run_id must be an explicit YYYYMMDD_HHMMSS identifier")
        path = (self.runs_root / run_id).resolve(strict=True)
        if path.parent != self.runs_root or path.is_symlink():
            raise ContractError("run path escaped the approved run store")
        return path

    def load_context(self, run_id: str) -> tuple[RunEvidenceContext, dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
        run_dir = self._run_dir(run_id)
        meta, meta_hash = _read_json(run_dir / "run_meta.json")
        manifest, manifest_hash = _read_json(run_dir / "final_run_manifest.json")
        if meta.get("run_meta_schema_version") != "run_meta_v2":
            raise ContractError("unsupported run metadata schema")
        if meta.get("canonical_run_id") != run_id or manifest.get("run_id") != run_id:
            raise ContractError("run identity differs across governed artifacts")
        if not is_successful_terminal_run_status(meta.get("run_status")):
            raise ContractError(
                "Worker 3 requires a successful terminal AVSHUNTER run "
                "(COMPLETED or ACCEPTED)"
            )
        if manifest.get("pipeline_technical_health") != "PASS" or manifest.get("fatal_flags"):
            raise ContractError("run failed technical-health or fatal-flag governance")
        plan = meta.get("dynamic_plan")
        if type(plan) is not dict or plan.get("pipeline_run_id") != run_id:
            raise ContractError("governed dynamic plan missing or mismatched")
        action = str(plan.get("resolved_action") or "")
        if action not in _ALLOWED_ACTIONS:
            raise ContractError("run action is not eligible for Worker 3 analysis")
        session = str(plan.get("last_completed_session") or "")
        try:
            if date.fromisoformat(session).isoformat() != session:
                raise ValueError()
        except (TypeError, ValueError) as exc:
            raise ContractError("invalid completed trading session") from exc
        market_cutoff = utc(str(plan.get("evidence_cutoff_utc") or ""))
        invocation_id = str(plan.get("invocation_id") or "").strip()
        plan_hash = str(plan.get("plan_hash") or "")
        if not invocation_id or not re.fullmatch(r"[0-9a-f]{64}", plan_hash):
            raise ContractError("dynamic plan identity is incomplete")
        lab_path = run_dir / "intelligence_lab" / f"final_opportunity_book_{run_id}.json"
        lab_hash = _sha256(lab_path)
        lab_ref = ArtifactRef(
            str(lab_path.relative_to(run_dir)), lab_hash, f"avshunter:lab:{run_id}"
        )
        lab, repairs = read_lab_document(
            run_dir, lab_ref, max_bytes=MAX_LAB_BOOK_BYTES
        )
        if lab.get("lab_schema_version") not in SUPPORTED_LAB_SCHEMAS or lab.get("run_id") != run_id:
            raise ContractError("Intelligence Lab book schema/run mismatch")
        rows = lab.get("rows")
        if type(rows) is not list or lab.get("candidate_count") != len(rows):
            raise ContractError("Intelligence Lab candidate count does not reconcile")
        if lab.get("source_errors"):
            raise ContractError("Intelligence Lab book contains source errors")
        created = utc(str(lab.get("created_at_utc") or ""))
        status_updated = utc(str(meta.get("status_updated_at_utc") or ""))
        manifest_created = utc(str(manifest.get("created_at_utc") or ""))
        context = RunEvidenceContext(
            run_id=run_id,
            invocation_id=invocation_id,
            trading_session=session,
            market_evidence_cutoff_utc=market_cutoff,
            bundle_cutoff_utc=_max_timestamp(created, status_updated, manifest_created),
            resolved_action=action,
            execution_authority_ceiling=str(plan.get("execution_authority_ceiling") or ""),
            plan_hash=plan_hash,
            run_dir=run_dir,
            lab_book_path=lab_path,
            run_meta_hash=meta_hash,
            final_manifest_hash=manifest_hash,
            lab_book_hash=lab_hash,
        )
        return context, lab, rows, repairs

    def _connect_registry(self) -> sqlite3.Connection:
        uri = self.registry_path.as_uri() + "?mode=ro&immutable=1"
        connection = sqlite3.connect(uri, uri=True)
        connection.row_factory = sqlite3.Row
        return connection

    def _dataset(self, connection: sqlite3.Connection, dataset_id: str, *, ticker: str,
                 session: str, dataset_type: str,
                 allowed_completeness: tuple[str, ...] = ("COMPLETE",)) -> _Dataset:
        if not re.fullmatch(r"[0-9a-f]{64}", dataset_id or ""):
            raise ContractError(f"{dataset_type} dataset identity is absent or invalid")
        row = connection.execute(
            "SELECT * FROM dataset_registry WHERE dataset_id = ?", (dataset_id,)
        ).fetchone()
        if row is None:
            raise ContractError(f"{dataset_type} dataset is not registered")
        values = dict(row)
        if (
            values.get("dataset_type") != dataset_type
            or values.get("instrument_id") != ticker
            or values.get("session_date") != session
            or values.get("completeness_status") not in allowed_completeness
        ):
            raise ContractError(f"{dataset_type} registry identity/completeness mismatch")
        path = Path(str(values.get("storage_uri") or "")).resolve(strict=True)
        if not path.is_relative_to(self.canonical_root) or not path.is_file() or path.is_symlink():
            raise ContractError("canonical payload escaped the approved store")
        if _sha256(path) != values.get("content_hash"):
            raise ContractError(f"{dataset_type} canonical payload hash mismatch")
        try:
            payload = json.loads(
                path.read_text(encoding="utf-8"),
                object_pairs_hook=_pairs,
                parse_constant=_constant,
            )
        except (ValueError, UnicodeError) as exc:
            raise ContractError(f"{dataset_type} canonical payload is invalid JSON") from exc
        expected_root = list if dataset_type == "OPTION_CHAIN" else dict
        if type(payload) is not expected_root:
            raise ContractError(
                f"{dataset_type} canonical payload root must be "
                f"{'an array' if expected_root is list else 'an object'}"
            )
        return _Dataset(values, payload, digest(values))

    def _selected_quote_dataset(
        self,
        connection: sqlite3.Connection,
        dataset_id: str,
        *,
        ticker: str,
        context: RunEvidenceContext,
    ) -> _Dataset:
        """Resolve either the EOD quote or its same-run Morning successor."""

        if not re.fullmatch(r"[0-9a-f]{64}", dataset_id or ""):
            raise ContractError("selected quote dataset identity is absent or invalid")
        record = connection.execute(
            "SELECT * FROM dataset_registry WHERE dataset_id = ?", (dataset_id,)
        ).fetchone()
        if record is None:
            raise ContractError("selected quote dataset is not registered")
        values = dict(record)
        dataset_type = str(values.get("dataset_type") or "")
        expected_schema = _SELECTED_QUOTE_SCHEMAS.get(dataset_type)
        if expected_schema is None:
            raise ContractError("selected quote dataset type is unsupported")
        if values.get("schema_version") != expected_schema:
            raise ContractError("selected quote dataset schema is unsupported")

        quote_session = str(values.get("session_date") or "")
        if dataset_type == "LIVE_OPTION":
            if quote_session != context.trading_session:
                raise ContractError("EOD selected quote session differs from completed session")
        else:
            try:
                completed_session = date.fromisoformat(context.trading_session)
                observed_session = date.fromisoformat(quote_session)
                cutoff_session = instant(context.bundle_cutoff_utc).astimezone(
                    ZoneInfo("America/New_York")
                ).date()
            except (TypeError, ValueError) as exc:
                raise ContractError("Morning exact quote session is invalid") from exc
            if not completed_session <= observed_session <= cutoff_session:
                raise ContractError("Morning exact quote is outside the governed run window")
            if values.get("source_run_id") != context.run_id:
                raise ContractError("Morning exact quote belongs to another run")
            try:
                if instant(str(values.get("as_of") or "")) > instant(context.bundle_cutoff_utc):
                    raise ContractError("Morning exact quote postdates the frozen run cutoff")
            except (TypeError, ValueError) as exc:
                raise ContractError("Morning exact quote timestamp is invalid") from exc

        return self._dataset(
            connection,
            dataset_id,
            ticker=ticker,
            session=quote_session,
            dataset_type=dataset_type,
            allowed_completeness=("COMPLETE", "PARTIAL"),
        )

    @staticmethod
    def _normalise_selected_quote(
        quote: _Dataset,
        *,
        ticker: str,
        context: RunEvidenceContext,
        thesis_id: str,
    ) -> dict[str, Any]:
        """Map supported quote schemas into Worker 3's canonical vocabulary."""

        payload = quote.payload
        if not isinstance(payload, dict):
            raise ContractError("selected quote payload must be an object")
        if quote.values["dataset_type"] == "LIVE_OPTION":
            return dict(payload)
        if (
            str(payload.get("run_id") or "") != context.run_id
            or str(payload.get("underlying") or "").upper() != ticker
            or str(payload.get("thesis_id") or "") != thesis_id
        ):
            raise ContractError("Morning exact quote identity differs from governed thesis")
        return {
            "recommended_contract": payload.get("symbol"),
            "source_chain_dataset_id": None,
            "contract_quote_timestamp_utc": payload.get("quote_timestamp_utc"),
            "contract_bid": payload.get("bid"),
            "contract_ask": payload.get("ask"),
            "contract_mid": payload.get("mid"),
            "contract_delta": payload.get("delta"),
            "contract_gamma": payload.get("gamma"),
            "contract_theta": payload.get("theta"),
            "contract_vega": payload.get("vega"),
            "contract_iv": payload.get("implied_vol"),
            "contract_oi": payload.get("open_interest"),
            "contract_volume": payload.get("volume"),
            "contract_spread_pct": payload.get("spread_pct"),
            "contract_quote_quality": payload.get("quote_quality"),
        }

    def _market_profile(self, connection: sqlite3.Connection, *, ticker: str,
                        context: RunEvidenceContext) -> _Dataset | None:
        rows = connection.execute(
            """SELECT * FROM dataset_registry
               WHERE dataset_type = 'MARKET_STRUCTURE' AND instrument_id = ?
                 AND session_date = ? AND completeness_status = 'COMPLETE'
                 AND schema_version = 'market_profile_evidence_v1'
               ORDER BY CASE WHEN source_run_id = ? THEN 0 ELSE 1 END, registered_at DESC""",
            (ticker, context.trading_session, context.run_id),
        ).fetchall()
        if not rows:
            return None
        hashes = {dict(row).get("content_hash") for row in rows}
        if len(hashes) != 1:
            raise ContractError("completed market profile is ambiguous for ticker/session")
        return self._dataset(
            connection,
            dict(rows[0])["dataset_id"],
            ticker=ticker,
            session=context.trading_session,
            dataset_type="MARKET_STRUCTURE",
        )

    def _market_environment(self, context: RunEvidenceContext) -> _MacroRunEvidence:
        """Load and project the run-frozen advisory packet once per batch.

        Macro is non-authoritative. Absence or invalidity is disclosed to every
        bundle but cannot turn an otherwise valid ticker into a data exception.
        """
        path = context.run_dir / "interpreter" / "interpreter_macro_context.json"
        if not path.exists():
            return _MacroRunEvidence(
                None, None, None, "RUN_FROZEN_MACRO_PACKET_NOT_AVAILABLE"
            )
        try:
            packet, packet_hash = _read_json(path)
            if str(packet.get("session_date") or "") != context.trading_session:
                raise ContractError("macro packet trading session differs from run")
            environment = project_market_environment(
                packet=packet,
                packet_sha256=packet_hash,
                run_id=context.run_id,
                evidence_cutoff_utc=context.bundle_cutoff_utc,
            )
            return _MacroRunEvidence(packet, packet_hash, environment, None)
        except (ContractError, OSError, ValueError) as exc:
            return _MacroRunEvidence(
                None, None, None, f"RUN_FROZEN_MACRO_PACKET_INVALID:{exc}"
            )

    @staticmethod
    def _attach_worker_advisory(
        bundle: EvidenceBundle,
        *,
        context: RunEvidenceContext,
        macro_evidence: _MacroRunEvidence,
        lab_row: dict[str, Any],
    ) -> EvidenceBundle:
        observations = list(bundle.observations)
        environment = macro_evidence.environment
        environment_error = macro_evidence.error
        if environment is None:
            absence_hash = digest({
                "run_id": context.run_id,
                "source": "interpreter/interpreter_macro_context.json",
                "status": "UNAVAILABLE",
                "reason": environment_error,
            })
            observations.append(Observation(
                evidence_id=f"market_environment:{absence_hash}:status",
                field="market_environment",
                value=None,
                unit="structured_json",
                source_id="run_frozen_macro_packet",
                source_hash=absence_hash,
                observed_at=context.bundle_cutoff_utc,
                available_at=context.bundle_cutoff_utc,
                status="UNAVAILABLE",
                scope="CONTEXT",
                calculation_version="market_environment_v1",
            ))
            observations.append(Observation(
                evidence_id=f"market_environment:{absence_hash}:reason",
                field="market_environment_unavailable_reason",
                value=environment_error or "UNAVAILABLE",
                unit="reason_code",
                source_id="run_frozen_macro_packet",
                source_hash=absence_hash,
                observed_at=context.bundle_cutoff_utc,
                available_at=context.bundle_cutoff_utc,
                status="AVAILABLE",
                scope="CONTEXT",
                calculation_version="market_environment_v1",
            ))
        else:
            observations.append(Observation(
                evidence_id=f"market_environment:{environment.snapshot_hash}",
                field="market_environment",
                value=canonical(environment.to_payload()),
                unit="structured_json",
                source_id=f"run_frozen_macro_packet:{environment.source_packet_id}",
                source_hash=environment.source_packet_sha256,
                observed_at=environment.evidence_cutoff_utc,
                available_at=context.bundle_cutoff_utc,
                status="AVAILABLE",
                scope="CONTEXT",
                calculation_version="market_environment_v1",
            ))
        if (
            environment is not None
            and macro_evidence.packet is not None
            and macro_evidence.packet_hash is not None
        ):
            try:
                ticker_context = project_macro_ticker_context(
                    packet=macro_evidence.packet,
                    packet_sha256=macro_evidence.packet_hash,
                    market_environment=environment,
                    lab_row=lab_row,
                    run_id=context.run_id,
                    session_date=context.trading_session,
                    evidence_cutoff_utc=context.bundle_cutoff_utc,
                )
                observations.append(Observation(
                    evidence_id=f"macro_ticker_context:{ticker_context.context_hash}",
                    field="macro_ticker_context",
                    value=canonical(ticker_context.to_payload()),
                    unit="structured_json",
                    source_id=(
                        "run_frozen_macro_packet:"
                        + ticker_context.source_packet_id
                        + ":ticker_projection"
                    ),
                    source_hash=ticker_context.source_packet_sha256,
                    observed_at=context.bundle_cutoff_utc,
                    available_at=context.bundle_cutoff_utc,
                    status="AVAILABLE",
                    scope="TICKER",
                    ticker=bundle.identity.ticker,
                    calculation_version="macro_ticker_context_v1",
                ))
                ticker_context_error = None
            except (ContractError, ValueError) as exc:
                ticker_context_error = f"MACRO_TICKER_CONTEXT_INVALID:{exc}"
        else:
            ticker_context_error = environment_error or "MACRO_CONTEXT_UNAVAILABLE"
        if ticker_context_error is not None:
            absence_hash = digest({
                "run_id": context.run_id,
                "ticker": bundle.identity.ticker,
                "source": "interpreter/interpreter_macro_context.json",
                "status": "UNAVAILABLE",
                "reason": ticker_context_error,
            })
            observations.append(Observation(
                evidence_id=f"macro_ticker_context:{absence_hash}:status",
                field="macro_ticker_context",
                value=None,
                unit="structured_json",
                source_id="run_frozen_macro_packet:ticker_projection",
                source_hash=absence_hash,
                observed_at=context.bundle_cutoff_utc,
                available_at=context.bundle_cutoff_utc,
                status="UNAVAILABLE",
                scope="TICKER",
                ticker=bundle.identity.ticker,
                calculation_version="macro_ticker_context_v1",
            ))
            observations.append(Observation(
                evidence_id=f"macro_ticker_context:{absence_hash}:reason",
                field="macro_ticker_context_unavailable_reason",
                value=ticker_context_error,
                unit="reason_code",
                source_id="run_frozen_macro_packet:ticker_projection",
                source_hash=absence_hash,
                observed_at=context.bundle_cutoff_utc,
                available_at=context.bundle_cutoff_utc,
                status="AVAILABLE",
                scope="TICKER",
                ticker=bundle.identity.ticker,
                calculation_version="macro_ticker_context_v1",
            ))
        interim = EvidenceBundle(
            bundle.identity, bundle.evidence_cutoff_utc, tuple(observations),
            bundle.schema_version,
        )
        trade_plan = build_trade_plan(interim)
        observations.append(Observation(
            evidence_id=f"trade_plan:{trade_plan.plan_hash}",
            field="trade_plan",
            value=canonical(trade_plan.to_payload()),
            unit="structured_json",
            source_id=f"worker3_trade_plan:{bundle.identity.thesis_id}",
            source_hash=trade_plan.plan_hash,
            observed_at=context.bundle_cutoff_utc,
            available_at=context.bundle_cutoff_utc,
            status="AVAILABLE",
            scope="TICKER",
            ticker=bundle.identity.ticker,
            calculation_version="trade_plan_snapshot_v1",
        ))
        return EvidenceBundle(
            bundle.identity, bundle.evidence_cutoff_utc, tuple(observations),
            bundle.schema_version,
        )

    @staticmethod
    def _obs(*, evidence_id: str, field: str, value: Any, unit: str, source_id: str,
             source_hash: str, observed_at: str, available_at: str, ticker: str,
             scope: str = "TICKER", contract_id: str | None = None,
             calculation_version: str | None = None) -> Observation:
        scalar = _safe_scalar(value)
        return Observation(
            evidence_id=evidence_id,
            field=field,
            value=scalar,
            unit=unit,
            source_id=source_id,
            source_hash=source_hash,
            observed_at=observed_at,
            available_at=available_at,
            status="AVAILABLE" if scalar is not None else "UNAVAILABLE",
            scope=scope,
            ticker=ticker,
            contract_id=contract_id,
            calculation_version=calculation_version,
        )

    def _prepare_row(self, *, context: RunEvidenceContext, lab: dict[str, Any],
                     repairs: list[dict[str, Any]], row: dict[str, Any], row_index: int,
                     connection: sqlite3.Connection,
                     macro_evidence: _MacroRunEvidence) -> EvidenceBundle:
        ticker = str(row.get("ticker") or "").strip().upper()
        if _TICKER.fullmatch(ticker) is None:
            raise ContractError("invalid canonical ticker in Lab row")
        if row.get("run_id") != context.run_id or row.get("lab_schema_version") != lab["lab_schema_version"]:
            raise ContractError("mixed Lab row run/schema identity")
        direction = _direction(row.get("governed_direction"))
        hold = _HOLD_ENDPOINT.get(str(row.get("hold_window") or row.get("hold_period") or ""))
        if hold is None:
            raise ContractError("governed hold window is missing or unsupported")
        contract_id, symbol, selection_version = _selected_contract(row, direction)
        identity = Identity(
            run_id=context.run_id,
            invocation_id=context.invocation_id,
            trading_session=context.trading_session,
            ticker=ticker,
            thesis_id=str(row.get("thesis_id") or "").strip(),
            direction=direction,
            planned_hold_sessions=hold,
            contract_id=contract_id,
            contract_symbol=symbol,
            selection_version=selection_version,
        )
        lab_created = utc(str(lab["created_at_utc"]))
        session_close = _session_close_utc(context.trading_session)
        prefix = f"lab:{context.lab_book_hash}:{ticker}:"
        source_id = f"avshunter:lab:{context.run_id}"
        observations: list[Observation] = []
        lab_fields = (
            ("signal_price", "signal_price", "USD/share", session_close),
            ("structural_target", "structural_target", "USD/share", lab_created),
            ("invalidation_price", "invalidation_price", "USD/share", lab_created),
            ("trigger_primary", "trigger_primary", "state", lab_created),
            ("trigger_quality", "trigger_quality", "state", lab_created),
            ("trigger_score", "trigger_score", "score", lab_created),
            ("thesis_state", "thesis_state", "state", lab_created),
            ("liquidity_state", "liquidity_state", "state", lab_created),
            ("monetisability_state", "monetisability_state", "state", lab_created),
            ("monetisability_target_profit_pct", "target_profit_pct", "percent", lab_created),
        )
        # Interpreter report inputs, copied from the exact attested Lab row.
        # These remain Lab snapshot observations, not freshly fetched quotes.
        detail_fields = {
            "trigger_price": "USD/share", "trigger_data_state": "state",
            "gamma_flip": "USD/share", "call_wall": "USD/share", "put_wall": "USD/share",
            "gamma_island_level": "USD/share", "gamma_island_distance_pct": "percent",
            "runway_to_wall_pct": "percent", "theta_drag_pct": "percent", "vega_risk_pct": "percent",
            "wbs": "score", "wbs_data_state": "state", "wbs_grade": "state",
            "regime_drift_status": "state", "ivp_label": "state",
            "macro_regime": "state", "macro_data_quality": "state",
            "macro_plain_language_advisory": "text", "macro_as_of_utc": "source_timestamp",
            "macro_sector_alignment": "state",
        }
        lab_fields += tuple((name, name, unit, lab_created) for name, unit in detail_fields.items())
        for source_field, field, unit, observed in lab_fields:
            value = row.get(source_field)
            if source_field in detail_fields:
                if value == "" or isinstance(value, (dict, list)):
                    value = None
                if unit in ("USD/share", "percent", "score") and type(value) not in (int, float):
                    value = None
            observations.append(self._obs(
                evidence_id=prefix + field,
                field=field,
                value=value,
                unit=unit,
                source_id=source_id,
                source_hash=context.lab_book_hash,
                observed_at=observed,
                available_at=lab_created,
                ticker=ticker,
                calculation_version=lab["lab_schema_version"],
            ))
        chain = self._dataset(
            connection,
            str(row.get("option_chain_dataset_id") or ""),
            ticker=ticker,
            session=context.trading_session,
            dataset_type="OPTION_CHAIN",
        )
        observations.append(self._obs(
            evidence_id=prefix + "option_chain_dataset_id",
            field="option_chain_dataset_id",
            value=chain.values["dataset_id"],
            unit="identifier",
            source_id="canonical_registry:OPTION_CHAIN",
            source_hash=chain.record_hash,
            observed_at=str(chain.values["as_of"]),
            available_at=lab_created,
            ticker=ticker,
            calculation_version=str(chain.values["schema_version"]),
        ))
        if contract_id is not None:
            quote = self._selected_quote_dataset(
                connection,
                str(row.get("selected_quote_dataset_id") or ""),
                ticker=ticker,
                context=context,
            )
            payload = self._normalise_selected_quote(
                quote,
                ticker=ticker,
                context=context,
                thesis_id=identity.thesis_id,
            )
            if (
                str(payload.get("recommended_contract") or "").upper() != symbol
                or (
                    payload.get("source_chain_dataset_id") is not None
                    and payload.get("source_chain_dataset_id") != chain.values["dataset_id"]
                )
            ):
                raise ContractError("selected quote does not belong to governed contract/chain")
            side = "CALL" if _OCC.fullmatch(symbol).group(1) == "C" else "PUT"
            if side != direction.value:
                raise ContractError("canonical quote side contradicts governed direction")
            comparisons = {
                "contract_bid": "contract_bid",
                "contract_ask": "contract_ask",
                "contract_mid": "contract_mid",
                "contract_delta": "contract_delta",
                "contract_iv": "contract_iv",
                "contract_open_interest": "contract_oi",
                "contract_volume": "contract_volume",
            }
            for lab_field, payload_field in comparisons.items():
                left, right = _safe_scalar(row.get(lab_field)), _safe_scalar(payload.get(payload_field))
                if left is None or right is None:
                    continue
                if type(left) in (int, float) and type(right) in (int, float):
                    if not math.isclose(float(left), float(right), rel_tol=1e-9, abs_tol=1e-9):
                        raise ContractError(f"Lab/canonical selected quote mismatch: {lab_field}")
                elif left != right:
                    raise ContractError(f"Lab/canonical selected quote mismatch: {lab_field}")
            quote_time = utc(str(payload.get("contract_quote_timestamp_utc") or quote.values["as_of"]))
            observations.append(self._obs(
                evidence_id=f"quote:{quote.values['dataset_id']}:dataset_completeness",
                field="quote_dataset_completeness",
                value=quote.values["completeness_status"],
                unit="state",
                source_id=f"canonical_registry:{quote.values['dataset_id']}",
                source_hash=quote.record_hash,
                observed_at=quote_time,
                available_at=lab_created,
                ticker=ticker,
                scope="CONTRACT",
                contract_id=contract_id,
                calculation_version=str(quote.values["schema_version"]),
            ))
            contract_fields = (
                ("contract_bid", "bid", "USD/share"),
                ("contract_ask", "ask", "USD/share"),
                ("contract_mid", "mid", "USD/share"),
                ("contract_delta", "delta", "ratio"),
                ("contract_gamma", "gamma", "per_USD"),
                ("contract_theta", "theta_daily", "USD/share/day"),
                ("contract_vega", "vega", "USD/share/vol_point"),
                ("contract_iv", "implied_volatility", "annualized_decimal"),
                ("contract_oi", "open_interest", "contracts"),
                ("contract_volume", "volume", "contracts"),
                ("contract_spread_pct", "spread_pct", "ratio"),
                ("contract_quote_quality", "quote_quality", "state"),
            )
            for payload_field, field, unit in contract_fields:
                observations.append(self._obs(
                    evidence_id=f"quote:{quote.values['dataset_id']}:{field}",
                    field=field,
                    value=payload.get(payload_field),
                    unit=unit,
                    source_id=f"canonical_dataset:{quote.values['dataset_id']}",
                    source_hash=str(quote.values["content_hash"]),
                    observed_at=quote_time,
                    available_at=lab_created,
                    ticker=ticker,
                    scope="CONTRACT",
                    contract_id=contract_id,
                    calculation_version=str(quote.values["schema_version"]),
                ))
        profile = self._market_profile(connection, ticker=ticker, context=context)
        if profile is None:
            absence_hash = digest({
                "dataset_type": "MARKET_STRUCTURE",
                "ticker": ticker,
                "session": context.trading_session,
                "result": "NOT_REGISTERED",
            })
            observations.append(self._obs(
                evidence_id=prefix + "completed_profile_status",
                field="completed_profile_status",
                value=None,
                unit="state",
                source_id="canonical_registry_query:MARKET_STRUCTURE",
                source_hash=absence_hash,
                observed_at=lab_created,
                available_at=lab_created,
                ticker=ticker,
                calculation_version="market_profile_evidence_v1",
            ))
        else:
            profile_time = utc(str(profile.payload.get("observed_at_utc") or profile.values["as_of"]))
            for source_field, field, unit in (
                ("poc", "profile_poc", "USD/share"),
                ("value_area_high", "profile_value_area_high", "USD/share"),
                ("value_area_low", "profile_value_area_low", "USD/share"),
                ("profile_type", "profile_type", "state"),
                ("quality", "profile_quality", "state"),
                ("uncertainty_score", "profile_uncertainty_score", "ratio"),
                ("usable", "profile_usable", "boolean"),
            ):
                observations.append(self._obs(
                    evidence_id=f"profile:{profile.values['dataset_id']}:{field}",
                    field=field,
                    value=profile.payload.get(source_field),
                    unit=unit,
                    source_id=f"canonical_dataset:{profile.values['dataset_id']}",
                    source_hash=str(profile.values["content_hash"]),
                    observed_at=profile_time,
                    available_at=lab_created,
                    ticker=ticker,
                    calculation_version=str(profile.values["schema_version"]),
                ))
        bundle = EvidenceBundle(identity, context.bundle_cutoff_utc, tuple(observations))
        lab_ref = ArtifactRef(
            str(context.lab_book_path.relative_to(context.run_dir)),
            context.lab_book_hash,
            f"avshunter:lab:{context.run_id}",
        )
        selected_repairs = [
            repair for repair in repairs
            if repair["path"].startswith(f"/rows/{row_index}/")
            or not repair["path"].startswith("/rows/")
        ]
        snapshot = lab_snapshot_from_document(
            lab,
            repairs,
            lab_ref,
            run_id=context.run_id,
            ticker=ticker,
            captured_at=context.bundle_cutoff_utc,
        )
        # lab_snapshot_from_document performs its own exact selected-row filtering;
        # selected_repairs is evaluated here to make the single-row intent explicit.
        del selected_repairs
        bundle = attach_native_document(bundle, snapshot)
        return self._attach_worker_advisory(
            bundle,
            context=context,
            macro_evidence=macro_evidence,
            lab_row=row,
        )

    def prepare_run(self, run_id: str, *, tickers: tuple[str, ...] | None = None) -> PreparedRun:
        context, lab, rows, repairs = self.load_context(run_id)
        macro_evidence = self._market_environment(context)
        by_ticker: dict[str, tuple[int, dict[str, Any]]] = {}
        for index, row in enumerate(rows):
            if type(row) is not dict:
                raise ContractError("Lab row must be an object")
            ticker = str(row.get("ticker") or "").strip().upper()
            if ticker in by_ticker:
                raise ContractError(f"duplicate Intelligence Lab ticker: {ticker}")
            by_ticker[ticker] = (index, row)
        requested = tuple(by_ticker) if tickers is None else tickers
        if type(requested) is not tuple or not requested:
            raise ContractError("nonempty immutable Worker 3 worklist required")
        if len(set(requested)) != len(requested):
            raise ContractError("duplicate Worker 3 worklist ticker")
        if any(type(ticker) is not str or _TICKER.fullmatch(ticker) is None for ticker in requested):
            raise ContractError("worklist requires exact canonical uppercase tickers")
        entries: list[PreparedTicker] = []
        with closing(self._connect_registry()) as connection:
            for ticker in requested:
                selected = by_ticker.get(ticker)
                if selected is None:
                    entries.append(PreparedTicker(ticker, "DATA_EXCEPTION", None, "ticker absent from exact Lab book"))
                    continue
                index, row = selected
                try:
                    bundle = self._prepare_row(
                        context=context,
                        lab=lab,
                        repairs=repairs,
                        row=row,
                        row_index=index,
                        connection=connection,
                        macro_evidence=macro_evidence,
                    )
                    entries.append(PreparedTicker(ticker, "EVIDENCE_PREPARED", bundle, None))
                except (ContractError, OSError, sqlite3.Error) as exc:
                    entries.append(PreparedTicker(ticker, "DATA_EXCEPTION", None, str(exc)))
        context_payloads: list[dict[str, Any]] = []
        context_invalid = 0
        for entry in entries:
            if entry.status != "EVIDENCE_PREPARED" or entry.bundle is None:
                continue
            observation = next(
                (
                    item for item in entry.bundle.observations
                    if item.field == "macro_ticker_context"
                ),
                None,
            )
            payload: dict[str, Any] | None = None
            if observation is not None and observation.status == "AVAILABLE":
                try:
                    candidate = json.loads(str(observation.value))
                    if type(candidate) is dict:
                        payload = candidate
                except (TypeError, ValueError):
                    payload = None
            if payload is None:
                context_invalid += 1
            else:
                context_payloads.append(payload)
        diagnostics = macro_ticker_context_diagnostics(
            tuple(context_payloads),
            requested=len(context_payloads) + context_invalid,
            invalid=context_invalid,
        )
        return PreparedRun(
            context,
            tuple(entries),
            "AVAILABLE" if macro_evidence.environment is not None else "UNAVAILABLE",
            macro_evidence.error,
            tuple(diagnostics.items()),
        )
