"""Competing-risks estimators with session-block bootstrap (pure; numpy).

Event coding per prediction: (time, cause, weight) with cause TARGET, STOP or CENSOR.
AMBIGUOUS counts as STOP (P0-8 config ``outcome.ambiguous_policy``); TIMEOUT,
OPEN_CENSORED and DATA_GAP are censored at their observed sessions. Weights let the
matched base rate enter the same estimator as fractional events (P0-8 §5.4).

Events are reduced once to per-block count arrays; a bootstrap resample is a
multiplicity-weighted sum of those arrays, so resampling cost does not grow with rows.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

import numpy as np

from .model import OutcomeState, UnderlyingOutcome

TARGET, STOP, CENSOR = "TARGET", "STOP", "CENSOR"
CAUSES = (TARGET, STOP, CENSOR)
_T, _S, _C = range(len(CAUSES))


@dataclass(frozen=True, slots=True)
class EventRecord:
    time: int
    cause: str
    block: str   # independent unit (evidence session)
    weight: float = 1.0


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
    at_risk_start: float
    target: tuple[float, ...]     # cumulative incidence of target-first at sessions 1..sessions
    stop: tuple[float, ...]
    survival: tuple[float, ...]


def block_counts(events: Sequence[EventRecord], sessions: int) -> tuple[list[str], np.ndarray]:
    """Per-block weighted counts, shape (blocks, causes, sessions + 1); index 0 holds time 0."""
    blocks = sorted({event.block for event in events})
    position = {block: index for index, block in enumerate(blocks)}
    counts = np.zeros((len(blocks), len(CAUSES), sessions + 1), dtype=float)
    cause_index = {cause: index for index, cause in enumerate(CAUSES)}
    for event in events:
        time = min(max(event.time, 0), sessions)
        counts[position[event.block], cause_index[event.cause], time] += event.weight
    return blocks, counts


def _curves(counts: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Aalen-Johansen over aggregated counts shaped (..., causes, sessions + 1).

    Returns cumulative incidence of target, stop and overall survival at sessions 1..S,
    each shaped (..., S).
    """
    exits = counts.sum(axis=-2)                                   # (..., S+1)
    at_risk = np.flip(np.cumsum(np.flip(exits, axis=-1), axis=-1), axis=-1)[..., 1:]
    d_target = counts[..., _T, 1:]
    d_stop = counts[..., _S, 1:]
    with np.errstate(divide="ignore", invalid="ignore"):
        hazard_t = np.where(at_risk > 0, d_target / at_risk, 0.0)
        hazard_s = np.where(at_risk > 0, d_stop / at_risk, 0.0)
    survival_after = np.cumprod(1.0 - hazard_t - hazard_s, axis=-1)
    survival_before = np.concatenate([np.ones_like(survival_after[..., :1]), survival_after[..., :-1]], axis=-1)
    return (np.cumsum(survival_before * hazard_t, axis=-1),
            np.cumsum(survival_before * hazard_s, axis=-1),
            survival_after)


def aalen_johansen(events: Sequence[EventRecord], sessions: int) -> IncidenceCurve:
    _, counts = block_counts(events, sessions)
    total = counts.sum(axis=0) if len(counts) else np.zeros((len(CAUSES), sessions + 1))
    target, stop, survival = _curves(total)
    return IncidenceCurve(sessions, float(total.sum()), tuple(map(float, target)), tuple(map(float, stop)),
                          tuple(map(float, survival)))


@dataclass(frozen=True, slots=True)
class BootstrapInterval:
    blocks: int
    target_by_final_session: tuple[float, float, float]   # (low, point, high)
    stop_by_final_session: tuple[float, float, float]


def _multiplicities(blocks: int, resamples: int, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    draws = rng.integers(0, blocks, size=(resamples, blocks))
    return np.stack([np.bincount(row, minlength=blocks) for row in draws]).astype(float)


def _interval(samples: np.ndarray, point: float, lower_quantile: float, upper_quantile: float) -> tuple[float, float, float]:
    if samples.size == 0:
        return (float("nan"), point, float("nan"))
    low, high = np.quantile(samples, [lower_quantile, upper_quantile])
    return (float(low), point, float(high))


def block_bootstrap(
    events: Sequence[EventRecord],
    sessions: int,
    resamples: int,
    seed: int,
    lower_quantile: float,
    upper_quantile: float,
) -> BootstrapInterval:
    blocks, counts = block_counts(events, sessions)
    point = aalen_johansen(events, sessions)
    multiplicity = _multiplicities(len(blocks), resamples, seed)
    resampled = np.einsum("rb,bct->rct", multiplicity, counts)
    target, stop, _ = _curves(resampled)
    return BootstrapInterval(
        blocks=len(blocks),
        target_by_final_session=_interval(target[:, -1], point.target[-1], lower_quantile, upper_quantile),
        stop_by_final_session=_interval(stop[:, -1], point.stop[-1], lower_quantile, upper_quantile),
    )


@dataclass(frozen=True, slots=True)
class PairedInterval:
    """Observed predictions vs their matched base rate, resampled on the same session blocks."""
    blocks: int
    observed: BootstrapInterval
    base_target: float
    base_stop: float
    excess_target: tuple[float, float, float]   # observed minus base, (low, point, high)
    excess_stop: tuple[float, float, float]


def paired_block_bootstrap(
    observed: Sequence[EventRecord],
    base: Sequence[EventRecord],
    sessions: int,
    resamples: int,
    seed: int,
    lower_quantile: float,
    upper_quantile: float,
) -> PairedInterval:
    blocks = sorted({event.block for event in observed} | {event.block for event in base})
    position = {block: index for index, block in enumerate(blocks)}

    def aligned(events: Sequence[EventRecord]) -> np.ndarray:
        own_blocks, own_counts = block_counts(events, sessions)
        out = np.zeros((len(blocks), len(CAUSES), sessions + 1), dtype=float)
        for index, block in enumerate(own_blocks):
            out[position[block]] = own_counts[index]
        return out

    observed_counts, base_counts = aligned(observed), aligned(base)
    observed_point = aalen_johansen(observed, sessions)
    base_point = aalen_johansen(base, sessions)
    multiplicity = _multiplicities(len(blocks), resamples, seed)
    obs_t, obs_s, _ = _curves(np.einsum("rb,bct->rct", multiplicity, observed_counts))
    base_t, base_s, _ = _curves(np.einsum("rb,bct->rct", multiplicity, base_counts))
    observed_interval = BootstrapInterval(
        blocks=len({event.block for event in observed}),
        target_by_final_session=_interval(obs_t[:, -1], observed_point.target[-1], lower_quantile, upper_quantile),
        stop_by_final_session=_interval(obs_s[:, -1], observed_point.stop[-1], lower_quantile, upper_quantile),
    )
    return PairedInterval(
        blocks=len(blocks),
        observed=observed_interval,
        base_target=base_point.target[-1],
        base_stop=base_point.stop[-1],
        excess_target=_interval(obs_t[:, -1] - base_t[:, -1], observed_point.target[-1] - base_point.target[-1],
                                lower_quantile, upper_quantile),
        excess_stop=_interval(obs_s[:, -1] - base_s[:, -1], observed_point.stop[-1] - base_point.stop[-1],
                              lower_quantile, upper_quantile),
    )


def events_from(outcomes: Iterable[tuple[UnderlyingOutcome, str]]) -> list[EventRecord]:
    events = []
    for outcome, block in outcomes:
        event = to_event(outcome, block)
        if event is not None:
            events.append(event)
    return events


def base_rate_events(target_fractions: Sequence[float], stop_fractions: Sequence[float], observed: int,
                     block: str) -> list[EventRecord]:
    """Fractional events for one prediction's matched universe: resolutions at sessions 1..n, the rest censored at n."""
    events = []
    for session, (target, stop) in enumerate(zip(target_fractions, stop_fractions), start=1):
        if target:
            events.append(EventRecord(session, TARGET, block, float(target)))
        if stop:
            events.append(EventRecord(session, STOP, block, float(stop)))
    remainder = 1.0 - float(sum(target_fractions)) - float(sum(stop_fractions))
    if remainder > 0:
        events.append(EventRecord(observed, CENSOR, block, remainder))
    return events
