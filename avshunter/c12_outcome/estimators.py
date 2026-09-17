"""Competing-risks estimators with session-block bootstrap (pure; numpy).

Event coding per prediction: (time, cause) with cause TARGET, STOP or CENSOR.
AMBIGUOUS counts as STOP (P0-8 config ``outcome.ambiguous_policy``); TIMEOUT,
OPEN_CENSORED and DATA_GAP are censored at their observed sessions.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

import numpy as np

from .model import OutcomeState, UnderlyingOutcome

TARGET, STOP, CENSOR = "TARGET", "STOP", "CENSOR"


@dataclass(frozen=True, slots=True)
class EventRecord:
    time: int
    cause: str
    block: str   # independent unit (evidence session)


def to_event(outcome: UnderlyingOutcome, block: str) -> EventRecord | None:
    state = outcome.state
    if state is OutcomeState.NOT_SCORABLE:
        return None
    if state is OutcomeState.TARGET_FIRST:
        return EventRecord(outcome.resolution_session, TARGET, block)
    if state in (OutcomeState.STOP_FIRST, OutcomeState.AMBIGUOUS):
        return EventRecord(outcome.resolution_session, STOP, block)
    return EventRecord(outcome.sessions_observed, CENSOR, block)


@dataclass(frozen=True, slots=True)
class IncidenceCurve:
    sessions: int
    at_risk_start: int
    target: tuple[float, ...]     # cumulative incidence of target-first at sessions 1..sessions
    stop: tuple[float, ...]
    survival: tuple[float, ...]


def aalen_johansen(events: Sequence[EventRecord], sessions: int) -> IncidenceCurve:
    times = np.array([e.time for e in events], dtype=int)
    causes = np.array([e.cause for e in events])
    surv_prev = 1.0
    cif_t, cif_s = 0.0, 0.0
    target, stop, survival = [], [], []
    for t in range(1, sessions + 1):
        at_risk = int(np.sum(times >= t))
        d_target = int(np.sum((times == t) & (causes == TARGET)))
        d_stop = int(np.sum((times == t) & (causes == STOP)))
        if at_risk:
            cif_t += surv_prev * d_target / at_risk
            cif_s += surv_prev * d_stop / at_risk
            surv_prev *= 1.0 - (d_target + d_stop) / at_risk
        target.append(cif_t)
        stop.append(cif_s)
        survival.append(surv_prev)
    return IncidenceCurve(sessions, len(events), tuple(target), tuple(stop), tuple(survival))


@dataclass(frozen=True, slots=True)
class BootstrapInterval:
    blocks: int
    target_by_final_session: tuple[float, float, float]   # (low, point, high)
    stop_by_final_session: tuple[float, float, float]


def block_bootstrap(
    events: Sequence[EventRecord],
    sessions: int,
    resamples: int,
    seed: int,
    lower_quantile: float,
    upper_quantile: float,
) -> BootstrapInterval:
    by_block: dict[str, list[EventRecord]] = {}
    for event in events:
        by_block.setdefault(event.block, []).append(event)
    blocks = sorted(by_block)
    point = aalen_johansen(events, sessions)
    rng = np.random.default_rng(seed)
    targets, stops = [], []
    for _ in range(resamples):
        chosen = rng.choice(len(blocks), size=len(blocks), replace=True)
        sample = [event for index in chosen for event in by_block[blocks[index]]]
        curve = aalen_johansen(sample, sessions)
        targets.append(curve.target[-1])
        stops.append(curve.stop[-1])
    tq = np.quantile(targets, [lower_quantile, upper_quantile]) if targets else (np.nan, np.nan)
    sq = np.quantile(stops, [lower_quantile, upper_quantile]) if stops else (np.nan, np.nan)
    return BootstrapInterval(
        blocks=len(blocks),
        target_by_final_session=(float(tq[0]), point.target[-1], float(tq[1])),
        stop_by_final_session=(float(sq[0]), point.stop[-1], float(sq[1])),
    )


def events_from(outcomes: Iterable[tuple[UnderlyingOutcome, str]]) -> list[EventRecord]:
    events = []
    for outcome, block in outcomes:
        event = to_event(outcome, block)
        if event is not None:
            events.append(event)
    return events
