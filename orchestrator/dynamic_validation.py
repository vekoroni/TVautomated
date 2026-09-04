"""Session-aware, underlying-first validation of a frozen thesis.

The service owns validation ordering and immutable evidence identity.  It does
not select direction or contracts and delegates final action/capital to the
existing Execution Gate callback.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Callable, Mapping

from canonical_data.run_plan import RequestedAction, RunPlan, validation_event_identity
from canonical_data.session_clock import SessionState


class ValidationTransition(str, Enum):
    THESIS_CONFIRMED = "THESIS_CONFIRMED"
    PENDING_TRIGGER = "PENDING_TRIGGER"
    ENTRY_RUNWAY_EXHAUSTED = "ENTRY_RUNWAY_EXHAUSTED"
    TARGET_ALREADY_REACHED = "TARGET_ALREADY_REACHED"
    THESIS_INVALIDATED = "THESIS_INVALIDATED"
    DATA_DEFERRED = "DATA_DEFERRED"
    NOT_EVALUATED_NON_DIRECTIONAL = "NOT_EVALUATED_NON_DIRECTIONAL"


@dataclass(frozen=True, slots=True)
class FrozenThesis:
    thesis_id: str
    ticker: str
    direction: str
    completed_session: str
    completed_close: float
    target: float
    invalidation: float
    selected_contract: str
    trigger: float | None = None
    maximum_entry: float | None = None
    completed_profile_evidence_id: str | None = None

    def __post_init__(self) -> None:
        direction = self.direction.strip().upper()
        if direction not in {"CALL", "PUT", "NON_DIRECTIONAL"}:
            raise ValueError("frozen thesis direction must be CALL, PUT or NON_DIRECTIONAL")
        for name in ("completed_close", "target", "invalidation"):
            if float(getattr(self, name)) <= 0:
                raise ValueError(f"{name} must be positive")
        if direction == "CALL" and not self.invalidation < self.completed_close < self.target:
            raise ValueError("CALL thesis geometry must be invalidation < close < target")
        if direction == "PUT" and not self.target < self.completed_close < self.invalidation:
            raise ValueError("PUT thesis geometry must be target < close < invalidation")
        object.__setattr__(self, "ticker", self.ticker.strip().upper())
        object.__setattr__(self, "direction", direction)


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


def _transition(thesis: FrozenThesis, price: float) -> tuple[ValidationTransition, str]:
    if thesis.direction == "NON_DIRECTIONAL":
        return ValidationTransition.NOT_EVALUATED_NON_DIRECTIONAL, "Directional validation is not applicable"
    if thesis.direction == "CALL":
        if price <= thesis.invalidation:
            return ValidationTransition.THESIS_INVALIDATED, "CALL invalidation breached"
        if price >= thesis.target:
            return ValidationTransition.TARGET_ALREADY_REACHED, "CALL target already reached"
        if thesis.maximum_entry is not None and price > thesis.maximum_entry:
            return ValidationTransition.ENTRY_RUNWAY_EXHAUSTED, "CALL maximum entry exceeded"
        if thesis.trigger is not None and price < thesis.trigger:
            return ValidationTransition.PENDING_TRIGGER, "CALL trigger not reached"
    else:
        if price >= thesis.invalidation:
            return ValidationTransition.THESIS_INVALIDATED, "PUT invalidation breached"
        if price <= thesis.target:
            return ValidationTransition.TARGET_ALREADY_REACHED, "PUT target already reached"
        if thesis.maximum_entry is not None and price < thesis.maximum_entry:
            return ValidationTransition.ENTRY_RUNWAY_EXHAUSTED, "PUT maximum entry exceeded"
        if thesis.trigger is not None and price > thesis.trigger:
            return ValidationTransition.PENDING_TRIGGER, "PUT trigger not reached"
    return ValidationTransition.THESIS_CONFIRMED, "Frozen thesis remains structurally valid"


def _profile_state(session_state: str) -> str:
    state = SessionState(session_state)
    if state is SessionState.PREMARKET:
        return "PENDING_MARKET_OPEN"
    if state is SessionState.REGULAR:
        return "DEVELOPING_SESSION"
    if state is SessionState.AFTER_HOURS:
        return "PARTIAL_SESSION"
    return "NOT_EVALUATED"


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

    transition, reason = _transition(thesis, float(underlying.price))
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
