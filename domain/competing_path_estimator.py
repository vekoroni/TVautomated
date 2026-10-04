"""Point-in-time C4 competing first-event baseline for underlying paths.

The caller owns version-equivalent episode construction. This module refuses
future-known features/labels and does not use option data. Count floors alone
do not certify a model; a later held-out calibration decision is required.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from random import Random
from typing import Sequence

from canonical_data.session_clock import is_xnys_session, xnys_sessions_between


@dataclass(frozen=True, slots=True)
class EpisodeOutcome:
    ticker: str
    sector: str
    direction: str
    decision_session: str
    decision_cutoff_utc: str
    feature_available_at_utc: str
    label_available_at_utc: str
    event: str
    event_session: int | None
    observed_sessions: int
    episode_version: str
    geometry_version: str


def _time(value: str) -> datetime:
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("all evidence clocks must carry a timezone")
    return result


def _incidence(rows: Sequence[EpisodeOutcome], horizon: int = 20) -> list[dict]:
    survival = 1.0
    target = stop = 0.0
    result = []
    for session in range(1, horizon + 1):
        at_risk = sum(1 for row in rows if row.observed_sessions >= session
                      and (row.event_session is None or row.event_session >= session))
        target_events = sum(1 for row in rows if row.event == "TARGET_FIRST" and row.event_session == session)
        stop_events = sum(1 for row in rows if row.event == "STOP_FIRST" and row.event_session == session)
        if at_risk:
            next_target = survival * target_events / at_risk
            next_stop = survival * stop_events / at_risk
            target += next_target
            stop += next_stop
            survival -= next_target + next_stop
        result.append({"session": session, "p_target_first": target,
                       "p_stop_first": stop, "p_event_free": survival,
                       "at_risk": at_risk, "target_events": target_events,
                       "stop_events": stop_events})
    return result


def _block_intervals(blocks: dict[int, list[EpisodeOutcome]], *, draws: int = 500) -> dict[str, dict]:
    """Resample complete 20-session market-date clusters, never ticker rows."""
    random = Random(20260927)
    keys = sorted(blocks)
    sampled: dict[int, dict[str, list[float]]] = {
        day: {"target_first": [], "stop_first": []} for day in (5, 10, 20)
    }
    for _ in range(draws):
        cohort = [row for key in random.choices(keys, k=len(keys)) for row in blocks[key]]
        curve = _incidence(cohort)
        for day in sampled:
            sampled[day]["target_first"].append(curve[day - 1]["p_target_first"])
            sampled[day]["stop_first"].append(curve[day - 1]["p_stop_first"])
    intervals = {}
    for day, causes in sampled.items():
        intervals[str(day)] = {}
        for cause, estimates in causes.items():
            estimates.sort()
            intervals[str(day)][cause] = {
                "lower_95": estimates[int(0.025 * (draws - 1))],
                "upper_95": estimates[int(0.975 * (draws - 1))],
            }
    return intervals


def fit_competing_path_baseline(
    observations: Sequence[EpisodeOutcome], *, training_cutoff_utc: str,
    expected_episode_version: str, expected_geometry_version: str,
) -> dict:
    """Return research incidence only when pre-registered support floors pass."""
    cut = _time(training_cutoff_utc)
    if not expected_episode_version or not expected_geometry_version:
        raise ValueError("version-equivalent episode and geometry are required")
    if not observations:
        return {"state": "NOT_ESTIMABLE", "reason": "NO_EPISODES", "incidence": None}
    ordered = sorted(observations, key=lambda item: (item.decision_session, item.ticker))
    first_date = date.fromisoformat(ordered[0].decision_session)
    if not is_xnys_session(first_date):
        raise ValueError("episode decision must be an XNYS session")
    eligible: list[EpisodeOutcome] = []
    excluded = {"FUTURE_FEATURE": 0, "FUTURE_LABEL": 0, "VERSION_MISMATCH": 0,
                "INCOMPLETE_PATH": 0, "OVERLAPPING_TICKER_START": 0}
    last_ticker_start: dict[str, date] = {}
    blocks: set[int] = set()
    block_members: dict[int, list[EpisodeOutcome]] = {}
    for item in ordered:
        current = date.fromisoformat(item.decision_session)
        if not is_xnys_session(current):
            raise ValueError("episode decision must be an XNYS session")
        decision_cut = _time(item.decision_cutoff_utc)
        if _time(item.feature_available_at_utc) > decision_cut:
            excluded["FUTURE_FEATURE"] += 1
            continue
        if _time(item.label_available_at_utc) > cut or decision_cut >= cut:
            excluded["FUTURE_LABEL"] += 1
            continue
        if (item.episode_version != expected_episode_version
                or item.geometry_version != expected_geometry_version):
            excluded["VERSION_MISMATCH"] += 1
            continue
        if (item.direction not in {"BULL", "BEAR"} or not item.ticker or not item.sector
                or item.event not in {"TARGET_FIRST", "STOP_FIRST", "NEITHER", "CENSORED"}
                or not 1 <= item.observed_sessions <= 20
                or (item.event in {"TARGET_FIRST", "STOP_FIRST"}
                    and (item.event_session is None or not 1 <= item.event_session <= item.observed_sessions))
                or (item.event in {"NEITHER", "CENSORED"} and item.event_session is not None)):
            excluded["INCOMPLETE_PATH"] += 1
            continue
        if item.event == "NEITHER" and item.observed_sessions != 20:
            excluded["INCOMPLETE_PATH"] += 1
            continue
        previous = last_ticker_start.get(item.ticker)
        if previous and xnys_sessions_between(previous, current) < 20:
            excluded["OVERLAPPING_TICKER_START"] += 1
            continue
        last_ticker_start[item.ticker] = current
        eligible.append(item)
        block_id = xnys_sessions_between(first_date, current) // 20
        blocks.add(block_id)
        block_members.setdefault(block_id, []).append(item)
    matured = [item for item in eligible if item.event != "CENSORED" or item.observed_sessions == 20]
    counts = {"eligible_starts": len(eligible), "matured_starts": len(matured),
              "independent_date_blocks": len(blocks),
              "tickers": len({item.ticker for item in eligible}),
              "sectors": len({item.sector for item in eligible})}
    support = (counts["independent_date_blocks"] >= 30 and counts["matured_starts"] >= 200
               and counts["tickers"] >= 20 and counts["sectors"] >= 4)
    intervals = _block_intervals(block_members) if support else None
    wide = bool(intervals and any(
        bounds["upper_95"] - bounds["lower_95"] > 0.40
        for causes in intervals.values() for bounds in causes.values()
    ))
    return {"state": ("POOLED_WIDE" if wide else "UNCALIBRATED_RESEARCH") if support else "NOT_ESTIMABLE",
            "reason": ("BLOCK_INTERVAL_TOO_WIDE" if wide else "HELD_OUT_CALIBRATION_REQUIRED")
            if support else "PRE_REGISTERED_SUPPORT_FLOOR_NOT_MET",
            "counts": counts, "excluded": excluded,
            "incidence": _incidence(eligible) if support else None,
            "block_bootstrap_95": intervals,
            "bootstrap_draws": 500 if support else 0,
            "training_cutoff_utc": training_cutoff_utc,
            "episode_version": expected_episode_version,
            "geometry_version": expected_geometry_version,
            "authority": "RESEARCH_ONLY"}
