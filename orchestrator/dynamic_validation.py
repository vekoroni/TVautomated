"""Session-aware, underlying-first validation of a frozen thesis.

The service owns validation ordering and immutable evidence identity.  It does
not select direction or contracts and delegates final action/capital to the
existing Execution Gate callback.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from domain.run_planning import RequestedAction, RunPlan, validation_event_identity
from domain.market_structure_evidence import profile_evidence_state_for_session
from domain.execution_authority import assert_no_unauthorised_capital
from domain.thesis_direction import (
    DirectionInvariantError,
    FrozenThesis,
    ValidationTransition,
    assert_direction_continuity,
    evaluate_validation_transition,
)
from canonical_data.session_clock import SessionState

@dataclass(frozen=True, slots=True)
class UnderlyingObservation:
    observation_id: str
    ticker: str
    price: float
    observed_at_utc: str
    dataset_id: str
    quality: str = "OBSERVED"

    def __post_init__(self) -> None:
        if float(self.price) <= 0:
            raise ValueError("underlying observation price must be positive")
        object.__setattr__(self, "ticker", self.ticker.strip().upper())


@dataclass(frozen=True, slots=True)
class ThesisValidationEvent:
    validation_event_id: str
    thesis_id: str
    ticker: str
    invocation_id: str
    evidence_cutoff_utc: str
    transition: str
    current_price: float | None
    gap_pct: float | None
    underlying_observation_id: str | None
    option_quote_observation_id: str | None
    developing_profile_evidence_id: str | None
    profile_evidence_state: str
    execution_gate_result: Mapping[str, Any]
    reason: str
    direction: str
    selected_contract: str
    data_status: str = "COMPLETE"
    authority: str = "VALIDATION_ONLY"
    can_reverse_direction: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ValidationBatchResult:
    events: tuple[ThesisValidationEvent, ...]
    input_count: int
    deferred_count: int
    exception_count: int
    failure_ratio: float
    systemic_failure: bool

    def __post_init__(self) -> None:
        if self.input_count < 0 or self.deferred_count < 0 or self.exception_count < 0:
            raise ValueError("validation population counts cannot be negative")
        if self.deferred_count > len(self.events):
            raise ValueError("deferred validation count exceeds published events")
        if len(self.events) + self.exception_count != self.input_count:
            raise ValueError(
                "validation population does not reconcile: "
                f"input={self.input_count} events={len(self.events)} "
                f"exceptions={self.exception_count}"
            )


UnderlyingResolver = Callable[[FrozenThesis, RunPlan], UnderlyingObservation]
OptionResolver = Callable[[FrozenThesis, UnderlyingObservation, RunPlan], Mapping[str, Any]]
ProfileResolver = Callable[[FrozenThesis, UnderlyingObservation, RunPlan, str], Mapping[str, Any]]
ExecutionGate = Callable[[FrozenThesis, UnderlyingObservation | None, Mapping[str, Any] | None, str, RunPlan], Mapping[str, Any]]


def _profile_state(session_state: str) -> str:
    return profile_evidence_state_for_session(SessionState(session_state)).value


def validate_thesis(
    plan: RunPlan,
    thesis: FrozenThesis,
    *,
    resolve_underlying: UnderlyingResolver,
    resolve_option_quote: OptionResolver,
    execution_gate: ExecutionGate,
    resolve_developing_profile: ProfileResolver | None = None,
) -> ThesisValidationEvent:
    """Validate one frozen thesis without acquiring data for a dead thesis."""
    if plan.resolved_action != RequestedAction.VALIDATE.value:
        raise ValueError("validate_thesis requires a resolved VALIDATE plan")
    if thesis.completed_session != plan.last_completed_session:
        raise ValueError("frozen thesis session does not match the run plan")

    profile_state = _profile_state(plan.session_state)
    try:
        underlying = resolve_underlying(thesis, plan)
    except Exception as error:
        transition = ValidationTransition.DATA_DEFERRED
        gate = execution_gate(thesis, None, None, transition.value, plan)
        assert_no_unauthorised_capital(gate)
        return ThesisValidationEvent(
            validation_event_id=hashlib.sha256(
                f"{thesis.thesis_id}|{plan.invocation_id}|DATA_DEFERRED".encode()
            ).hexdigest(),
            thesis_id=thesis.thesis_id, ticker=thesis.ticker,
            invocation_id=plan.invocation_id,
            evidence_cutoff_utc=plan.evidence_cutoff_utc,
            transition=transition.value, current_price=None, gap_pct=None,
            underlying_observation_id=None, option_quote_observation_id=None,
            developing_profile_evidence_id=None,
            profile_evidence_state=profile_state,
            execution_gate_result=dict(gate),
            reason=f"UNDERLYING_UNAVAILABLE:{type(error).__name__}",
            direction=thesis.direction, selected_contract=thesis.selected_contract,
            data_status="UNDERLYING_UNAVAILABLE",
        )
    if underlying.ticker != thesis.ticker:
        raise ValueError("underlying observation ticker does not match thesis")

    transition, reason = evaluate_validation_transition(thesis, float(underlying.price))
    gap_pct = (float(underlying.price) / float(thesis.completed_close) - 1.0) * 100.0
    quote: Mapping[str, Any] | None = None
    profile: Mapping[str, Any] | None = None
    terminal = transition in {
        ValidationTransition.THESIS_INVALIDATED,
        ValidationTransition.TARGET_ALREADY_REACHED,
        ValidationTransition.NOT_EVALUATED_NON_DIRECTIONAL,
    }
    data_statuses: list[str] = []
    if not terminal:
        try:
            quote = resolve_option_quote(thesis, underlying, plan)
            assert_direction_continuity(thesis.direction, quote, stage="OPTION_QUOTE")
        except DirectionInvariantError:
            raise
        except Exception as error:
            data_statuses.append(f"OPTION_QUOTE_UNAVAILABLE:{type(error).__name__}")
            reason += f"; option quote unavailable ({type(error).__name__})"
        if profile_state in {"DEVELOPING_SESSION", "PARTIAL_SESSION"} and resolve_developing_profile:
            try:
                profile = resolve_developing_profile(thesis, underlying, plan, profile_state)
            except Exception as error:
                data_statuses.append(f"PROFILE_UNAVAILABLE_ADVISORY:{type(error).__name__}")
                reason += f"; advisory profile unavailable ({type(error).__name__})"
                profile_state = "UNAVAILABLE_PROVIDER"

    gate = execution_gate(thesis, underlying, quote, transition.value, plan)
    assert_no_unauthorised_capital(gate)
    assert_direction_continuity(thesis.direction, gate, stage="EXECUTION_GATE")
    quote_id = str((quote or {}).get("observation_id") or "") or None
    profile_id = str((profile or {}).get("evidence_id") or "") or None
    event_id = validation_event_identity(
        thesis_id=thesis.thesis_id,
        evidence_cutoff_utc=datetime.fromisoformat(plan.evidence_cutoff_utc.replace("Z", "+00:00")),
        underlying_observation_id=underlying.observation_id,
        quote_observation_id=quote_id,
        developing_profile_evidence_id=profile_id,
    )
    return ThesisValidationEvent(
        validation_event_id=event_id, thesis_id=thesis.thesis_id,
        ticker=thesis.ticker, invocation_id=plan.invocation_id,
        evidence_cutoff_utc=plan.evidence_cutoff_utc,
        transition=transition.value, current_price=float(underlying.price),
        gap_pct=round(gap_pct, 6),
        underlying_observation_id=underlying.observation_id,
        option_quote_observation_id=quote_id,
        developing_profile_evidence_id=profile_id,
        profile_evidence_state=profile_state,
        execution_gate_result=dict(gate), reason=reason,
        direction=thesis.direction, selected_contract=thesis.selected_contract,
        data_status="|".join(data_statuses) if data_statuses else "COMPLETE",
    )


def validate_theses(
    plan: RunPlan,
    theses: tuple[FrozenThesis, ...],
    *,
    resolve_underlying: UnderlyingResolver,
    resolve_option_quote: OptionResolver,
    execution_gate: ExecutionGate,
    resolve_developing_profile: ProfileResolver | None = None,
    max_failure_ratio: float = 0.05,
) -> ValidationBatchResult:
    """Validate a frozen worklist with per-ticker isolation and outage signal."""
    if not 0.0 <= float(max_failure_ratio) <= 1.0:
        raise ValueError("max_failure_ratio must be in [0,1]")
    tickers = [item.ticker for item in theses]
    if len(tickers) != len(set(tickers)):
        raise ValueError("validation worklist contains duplicate tickers")
    authorised = set(plan.authorised_ticker_worklists.get("UNDERLYING_VALIDATION", ()))
    if authorised and set(tickers) != authorised:
        raise ValueError("validation thesis population differs from the frozen worklist")
    events: list[ThesisValidationEvent] = []
    exceptions = 0
    for frozen in theses:
        try:
            events.append(
                validate_thesis(
                    plan, frozen,
                    resolve_underlying=resolve_underlying,
                    resolve_option_quote=resolve_option_quote,
                    execution_gate=execution_gate,
                    resolve_developing_profile=resolve_developing_profile,
                )
            )
        except Exception:
            exceptions += 1
    deferred = sum(
        1 for event in events
        if event.transition == ValidationTransition.DATA_DEFERRED.value
        or "UNAVAILABLE" in event.data_status
    )
    failed = deferred + exceptions
    ratio = failed / len(theses) if theses else 0.0
    return ValidationBatchResult(
        events=tuple(events), input_count=len(theses), deferred_count=deferred,
        exception_count=exceptions, failure_ratio=round(ratio, 8),
        systemic_failure=bool(theses) and ratio > float(max_failure_ratio),
    )


def persist_validation_event(
    event: ThesisValidationEvent,
    destination: Path,
    *,
    ledger_path: Path | None = None,
    run_id: str | None = None,
) -> Path:
    """Atomically persist an immutable validation event."""
    encoded = json.dumps(event.to_dict(), indent=2, sort_keys=True).encode("utf-8")
    path = Path(destination)
    if path.exists():
        if path.read_bytes() != encoded:
            raise RuntimeError("validation event identity already has different content")
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
        temporary.write_bytes(encoded)
        os.replace(temporary, path)
    if ledger_path is not None:
        from canonical_data.decision_outcome_ledger import (
            DecisionOutcomeLedger,
            make_ledger_event,
        )

        ledger_event = make_ledger_event(
            event_type="VALIDATION",
            occurred_at_utc=event.evidence_cutoff_utc,
            run_id=run_id or event.invocation_id,
            ticker=event.ticker,
            thesis_id=event.thesis_id,
            validation_event_id=event.validation_event_id,
            payload=event.to_dict(),
        )
        DecisionOutcomeLedger(ledger_path).append(ledger_event)
    return path


def _row_text(row: Mapping[str, Any], *names: str) -> str:
    for name in names:
        value = row.get(name)
        if value is None:
            continue
        text = str(value).strip()
        if text and text.upper() not in {"NAN", "NONE", "NULL", "N/A"}:
            return text
    return ""


def _row_float(row: Mapping[str, Any], *names: str) -> float | None:
    for name in names:
        value = row.get(name)
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            continue
        if parsed == parsed:
            return parsed
    return None


def _row_bool(row: Mapping[str, Any], *names: str) -> bool:
    text = _row_text(row, *names).upper()
    return text in {"1", "TRUE", "YES", "Y", "ON"}


def _utc_instant(value: str) -> datetime:
    parsed = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Morning validation evidence cutoff must be timezone-aware")
    return parsed.astimezone(timezone.utc).replace(microsecond=0)


def validation_event_from_morning_row(
    row: Mapping[str, Any],
    *,
    run_id: str,
    fallback_evidence_cutoff_utc: str,
) -> ThesisValidationEvent:
    """Serialise the governed Morning result without re-fetching or re-deciding.

    Morning Gate already owns current-price acquisition, lifecycle evaluation
    and Execution Gate invocation.  This adapter only expresses that completed
    result through the dynamic validation contract consumed by the Lab,
    Interpreter and Decision/Outcome Ledger.
    """
    ticker = _row_text(row, "ticker").upper()
    thesis_id = _row_text(row, "thesis_id")
    direction = _row_text(
        row, "governed_direction", "final_direction", "canonical_direction", "direction"
    ).upper()
    selected_contract = _row_text(
        row,
        "selected_contract_symbol",
        "morning_selected_contract_symbol",
        "current_contract_symbol",
        "contract_symbol",
        "recommended_contract",
    ).upper().removeprefix("O:")
    if not ticker or not thesis_id:
        raise ValueError("Morning validation row requires ticker and thesis_id")

    cutoff_text = _row_text(
        row,
        "current_quote_timestamp_utc",
        "selected_quote_timestamp_utc",
        "morning_quote_timestamp_utc",
        "live_contract_quote_timestamp",
        "live_contract_provider_updated",
        "underlying_quote_updated",
    ) or fallback_evidence_cutoff_utc
    cutoff = _utc_instant(cutoff_text)
    cutoff_text = cutoff.isoformat().replace("+00:00", "Z")

    current_price = _row_float(row, "live_price", "current_price", "morning_price")
    if current_price is not None and current_price <= 0:
        current_price = None
    completed_close = _row_float(
        row, "completed_close", "eod_close", "signal_price", "underlying_price"
    )
    gap_pct = (
        round((current_price / completed_close - 1.0) * 100.0, 6)
        if current_price is not None and completed_close is not None and completed_close > 0
        else None
    )

    morning_state = _row_text(row, "morning_transition_state", "thesis_state").upper()
    if direction not in {"CALL", "PUT"}:
        transition = ValidationTransition.NOT_EVALUATED_NON_DIRECTIONAL.value
    elif current_price is None:
        transition = ValidationTransition.DATA_DEFERRED.value
    elif morning_state == "THESIS_INVALIDATED":
        transition = ValidationTransition.THESIS_INVALIDATED.value
    elif morning_state == "MOVE_ALREADY_REALIZED":
        transition = ValidationTransition.ENTRY_RUNWAY_EXHAUSTED.value
    elif morning_state in {
        "CONTRACT_REPRICE_REQUIRED",
        "LIQUIDITY_STILL_PENDING",
        "WAIT_FOR_PULLBACK",
        "GAP_CONFIRMATION_EXTENDED",
        "EOD_PENDING_MORNING_REQUOTE",
    }:
        transition = ValidationTransition.PENDING_TRIGGER.value
    elif morning_state in {
        "EXECUTABLE_NOW",
        "GAP_CONFIRMATION_WITH_RUNWAY",
        "THESIS_CONFIRMED",
        "ACTIVE",
    }:
        transition = ValidationTransition.THESIS_CONFIRMED.value
    else:
        transition = ValidationTransition.DATA_DEFERRED.value

    underlying_source_id = _row_text(
        row,
        "underlying_observation_id",
        "underlying_quote_observation_id",
        "underlying_quote_dataset_id",
        "underlying_dataset_id",
    )
    if not underlying_source_id:
        underlying_source_id = "morning_underlying_" + hashlib.sha256(
            f"{ticker}|{cutoff_text}|{current_price}".encode("utf-8")
        ).hexdigest()[:24]
    quote_id = _row_text(
        row,
        "selected_quote_snapshot_id",
        "current_quote_snapshot_id",
        "morning_quote_snapshot_id",
        "selected_quote_dataset_id",
        "current_quote_dataset_id",
        "msi_exact_quote_dataset_id",
    ) or None
    profile_id = _row_text(
        row, "developing_profile_evidence_id", "ms_profile_evidence_id"
    ) or None
    profile_state = _row_text(
        row, "ms_profile_evidence_state", "profile_evidence_state"
    ).upper() or "NOT_REQUESTED"
    action = _row_text(row, "final_action", "morning_entry_action", "verdict").upper()
    data_status = (
        "UNDERLYING_UNAVAILABLE"
        if current_price is None
        else _row_text(row, "morning_data_status", "data_status").upper() or "COMPLETE"
    )
    event_id = validation_event_identity(
        thesis_id=thesis_id,
        evidence_cutoff_utc=cutoff,
        underlying_observation_id=underlying_source_id,
        quote_observation_id=quote_id,
        developing_profile_evidence_id=profile_id,
    )
    return ThesisValidationEvent(
        validation_event_id=event_id,
        thesis_id=thesis_id,
        ticker=ticker,
        invocation_id=str(run_id),
        evidence_cutoff_utc=cutoff_text,
        transition=transition,
        current_price=current_price,
        gap_pct=gap_pct,
        underlying_observation_id=underlying_source_id,
        option_quote_observation_id=quote_id,
        developing_profile_evidence_id=profile_id,
        profile_evidence_state=profile_state,
        execution_gate_result={
            "action": action,
            "final_action": action,
            "capital_permission": _row_text(
                row, "final_capital_permission", "capital_permission", "execution_permission"
            ).upper(),
            "morning_execution_permission": _row_text(
                row, "morning_execution_permission"
            ).upper(),
            "executable_now": _row_bool(row, "executable_now"),
            "morning_transition_state": morning_state,
            "authority": "EXECUTION_GATE",
        },
        reason=(
            _row_text(row, "liquidity_lifecycle_reason", "morning_reason", "flag_reason")
            or f"MORNING_GATE_RECORDED:{morning_state or 'UNCLASSIFIED'}"
        ),
        direction=direction,
        selected_contract=selected_contract,
        data_status=data_status,
    )


def persist_morning_validation_events(
    rows: Iterable[Mapping[str, Any]],
    *,
    run_id: str,
    destination_dir: Path,
    fallback_evidence_cutoff_utc: str,
) -> dict[str, Any]:
    """Complete missing Morning validation lineage using immutable event files."""
    destination = Path(destination_dir)
    latest_existing: dict[str, str] = {}
    if destination.is_dir():
        for path in sorted(destination.glob("*.json")):
            payload = json.loads(path.read_text(encoding="utf-8-sig"))
            thesis_id = _row_text(payload, "thesis_id")
            cutoff = _row_text(payload, "evidence_cutoff_utc")
            if thesis_id and cutoff > latest_existing.get(thesis_id, ""):
                latest_existing[thesis_id] = cutoff

    written = reused = skipped = 0
    event_ids: list[str] = []
    for row in rows:
        if not _row_text(row, "ticker") or not _row_text(row, "thesis_id"):
            skipped += 1
            continue
        event = validation_event_from_morning_row(
            row,
            run_id=run_id,
            fallback_evidence_cutoff_utc=fallback_evidence_cutoff_utc,
        )
        if latest_existing.get(event.thesis_id, "") >= event.evidence_cutoff_utc:
            reused += 1
            continue
        path = destination / f"{event.validation_event_id}.json"
        existed = path.is_file()
        persist_validation_event(event, path)
        written += 0 if existed else 1
        reused += 1 if existed else 0
        latest_existing[event.thesis_id] = event.evidence_cutoff_utc
        event_ids.append(event.validation_event_id)
    return {
        "status": "PASS",
        "authority": "VALIDATION_ONLY",
        "input_rows": written + reused + skipped,
        "written": written,
        "reused": reused,
        "skipped_missing_governed_identity": skipped,
        "event_ids": event_ids,
        "destination": str(destination),
    }

