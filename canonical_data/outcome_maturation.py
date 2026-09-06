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
    outcome_event_from_candidate,
)


DEFAULT_OUTCOME_HORIZONS = (1, 5, 10, 20)


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
    """Append matured 1/5/10/20-session outcomes without provider calls."""

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

    for candidate in candidates:
        payload = candidate.payload
        direction = str(payload.get("direction") or "").strip().upper()
        completed_session = str(payload.get("completed_session") or "").strip()[:10]
        reference = _number(payload.get("reference_price"))
        if direction not in {"CALL", "PUT"} or not completed_session or reference is None:
            ineligible += 1
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
            except Exception:
                exceptions += 1
                histories[history_key] = []
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
                target_price=_number(payload.get("target_price")),
                invalidation_price=_number(payload.get("invalidation_price")),
            )
            if evaluation.data_status != "OBSERVED_COMPLETED_SESSIONS":
                deferred += 1
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

    return OutcomeMaturationSummary(
        candidate_events=len(candidates),
        eligible_candidates=eligible,
        outcomes_evaluated=evaluated,
        outcomes_appended=appended,
        outcomes_already_present=already,
        deferred_horizons=deferred,
        ineligible_candidates=ineligible,
        data_exceptions=exceptions,
    )


__all__ = [
    "DEFAULT_OUTCOME_HORIZONS",
    "OutcomeMaturationSummary",
    "mature_candidate_outcomes",
]
