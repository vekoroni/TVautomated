"""Application service that matures ledger candidates from canonical prices."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
import math
from typing import Any, Callable, Iterable, Mapping

from domain.decision_outcome import evaluate_outcome_path

from .decision_outcome_ledger import (
    DecisionOutcomeLedger,
    LedgerEvent,
    outcome_observation_event_from_candidate,
    outcome_event_from_candidate,
)


DEFAULT_OUTCOME_HORIZONS = (1, 2, 3, 5, 10, 20)


@dataclass(frozen=True, slots=True)
class OutcomeMaturationSummary:
    candidate_events: int
    eligible_candidates: int
    outcomes_evaluated: int
    outcomes_appended: int
    outcomes_already_present: int
    deferred_horizons: int
    ineligible_candidates: int
    data_exceptions: int
    data_exception_horizons: int
    expected_candidate_horizons: int
    outcome_observations_appended: int
    outcome_observations_already_present: int
    accounted_candidate_horizons: int
    population_reconciled: bool
    authority: str = "OBSERVATION_ONLY"
    can_grant_capital: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _number(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) and parsed > 0 else None


def _bars_as_records(value: Any) -> list[dict[str, Any]]:
    if hasattr(value, "to_dict"):
        try:
            value = value.to_dict("records")
        except TypeError:
            pass
    return [dict(item) for item in (value or ())]


def mature_candidate_outcomes(
    ledger: DecisionOutcomeLedger,
    *,
    read_completed_history: Callable[[str, str], Iterable[Mapping[str, Any]]],
    as_of_utc: str,
    horizons: Iterable[int] = DEFAULT_OUTCOME_HORIZONS,
) -> OutcomeMaturationSummary:
    """Append governed milestone outcomes without provider calls."""

    horizon_set = tuple(sorted({int(item) for item in horizons}))
    if not horizon_set or horizon_set[0] <= 0:
        raise ValueError("outcome horizons must be positive")
    datetime.fromisoformat(str(as_of_utc).replace("Z", "+00:00"))

    candidates = tuple(
        event
        for event in ledger.events_by_type("CANDIDATE_DECISION")
        if str(event.payload.get("decision_stage") or "").upper() == "EOD_THESIS"
    )
    existing = {
        (event.previous_event_id, int(event.payload.get("horizon_sessions") or 0))
        for event in ledger.events_by_type("OUTCOME")
        if event.previous_event_id and event.payload.get("is_counterfactual") is True
    }
    histories: dict[tuple[str, str], list[dict[str, Any]]] = {}
    evaluated = appended = already = deferred = ineligible = exceptions = eligible = 0
    observations_appended = observations_already = 0

    def record_observation(
        candidate: LedgerEvent, horizon: int, status: str, reason: str,
    ) -> None:
        nonlocal observations_appended, observations_already
        observation = outcome_observation_event_from_candidate(
            candidate,
            horizon_sessions=horizon,
            data_status=status,
            reason=reason,
            occurred_at_utc=as_of_utc,
        )
        if ledger.append(observation):
            observations_appended += 1
        else:
            observations_already += 1

    for candidate in candidates:
        payload = candidate.payload
        direction = str(payload.get("direction") or "").strip().upper()
        completed_session = str(payload.get("completed_session") or "").strip()[:10]
        reference = _number(payload.get("reference_price"))
        target = _number(payload.get("target_price"))
        invalidation = _number(payload.get("invalidation_price"))
        missing: list[str] = []
        if direction not in {"CALL", "PUT"}:
            missing.append("DIRECTION_UNAVAILABLE")
        if not completed_session:
            missing.append("COMPLETED_SESSION_UNAVAILABLE")
        if reference is None:
            missing.append("REFERENCE_PRICE_UNAVAILABLE")
        if target is None:
            missing.append("TARGET_PRICE_UNAVAILABLE")
        if invalidation is None:
            missing.append("INVALIDATION_PRICE_UNAVAILABLE")
        if missing:
            ineligible += 1
            for horizon in horizon_set:
                record_observation(
                    candidate, horizon, "DATA_EXCEPTION", "|".join(missing)
                )
            continue
        eligible += 1
        history_key = (candidate.ticker, completed_session)
        if history_key not in histories:
            try:
                raw_bars = _bars_as_records(
                    read_completed_history(candidate.ticker, completed_session)
                )
                histories[history_key] = [
                    bar
                    for bar in raw_bars
                    if str(bar.get("date") or "")[:10] > completed_session
                ]
            except Exception as error:
                exceptions += 1
                histories[history_key] = []
                for horizon in horizon_set:
                    if (candidate.event_id, horizon) not in existing:
                        record_observation(
                            candidate,
                            horizon,
                            "DATA_EXCEPTION",
                            f"PRICE_HISTORY_READ_FAILED:{type(error).__name__.upper()}",
                        )
                continue
        bars = histories[history_key]
        for horizon in horizon_set:
            outcome_key = (candidate.event_id, horizon)
            if outcome_key in existing:
                already += 1
                continue
            evaluation = evaluate_outcome_path(
                direction=direction,
                reference_price=reference,
                future_bars=bars,
                horizon_sessions=horizon,
                target_price=target,
                invalidation_price=invalidation,
            )
            if evaluation.data_status != "OBSERVED_COMPLETED_SESSIONS":
                deferred += 1
                record_observation(
                    candidate,
                    horizon,
                    "DEFERRED_NOT_YET_OBSERVABLE",
                    "UNDERLYING_HORIZON_NOT_MATURE",
                )
                continue
            evaluated += 1
            horizon_bar = bars[horizon - 1]
            horizon_date = str(horizon_bar.get("date") or "").strip()[:10]
            occurred = (
                f"{horizon_date}T23:59:59Z" if horizon_date else str(as_of_utc)
            )
            event = outcome_event_from_candidate(
                candidate, evaluation, occurred_at_utc=occurred
            )
            if ledger.append(event):
                appended += 1
            else:
                already += 1
            existing.add(outcome_key)

    expected_candidate_horizons = len(candidates) * len(horizon_set)
    accounted_candidate_horizons = (
        evaluated + already + deferred
        + ineligible * len(horizon_set)
        + exceptions * len(horizon_set)
    )
    return OutcomeMaturationSummary(
        candidate_events=len(candidates),
        eligible_candidates=eligible,
        outcomes_evaluated=evaluated,
        outcomes_appended=appended,
        outcomes_already_present=already,
        deferred_horizons=deferred,
        ineligible_candidates=ineligible,
        data_exceptions=exceptions,
        data_exception_horizons=(ineligible + exceptions) * len(horizon_set),
        expected_candidate_horizons=expected_candidate_horizons,
        outcome_observations_appended=observations_appended,
        outcome_observations_already_present=observations_already,
        accounted_candidate_horizons=accounted_candidate_horizons,
        population_reconciled=(
            accounted_candidate_horizons == expected_candidate_horizons
        ),
    )


__all__ = [
    "DEFAULT_OUTCOME_HORIZONS",
    "OutcomeMaturationSummary",
    "mature_candidate_outcomes",
]
