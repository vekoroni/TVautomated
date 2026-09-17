"""First-passage evaluation with right-censoring and realistic fills (pure).

Rules (P0-8 §5.1-5.2, spec AM-1):
- sessions are the XNYS sessions after the evidence session, up to min(as-of, window);
- target touched when the session's extreme crosses the target (only for LEVEL targets);
- invalidation touched when the opposite extreme crosses it; the fill is the worse of the
  level and the session open (gap risk);
- both touched in one session -> AMBIGUOUS at that session;
- a missing bar inside the observed span -> DATA_GAP, censored before it;
- no touch through the full window -> TIMEOUT at the last session's close;
- otherwise OPEN_CENSORED at the number of sessions observed.
"""

from __future__ import annotations

from datetime import date
from typing import Mapping, Sequence

from .model import Bar, Geometry, OutcomeState, TargetState, UnderlyingOutcome


def _not_scorable(geometry: Geometry) -> UnderlyingOutcome:
    reasons = []
    if geometry.direction is None:
        reasons.append(f"direction {geometry.direction_text!r}")
    if geometry.reference_price is None:
        reasons.append("reference price missing")
    reasons.append(f"invalidation {geometry.invalidation_state.value}")
    return UnderlyingOutcome(OutcomeState.NOT_SCORABLE, 0, None, None, None, None, None, None, None,
                             reason="; ".join(reasons))


def evaluate_passage(
    geometry: Geometry,
    window_sessions: Sequence[date],
    bars: Mapping[date, Bar],
    window_length: int,
) -> UnderlyingOutcome:
    """Evaluate one prediction.

    ``window_sessions``: XNYS sessions 1..n after the evidence session that are observable
    as of the scoring date (n <= window_length). ``bars`` must contain only bars up to the
    scoring date.
    """
    if not geometry.scorable:
        return _not_scorable(geometry)
    direction, reference, stop = geometry.direction, geometry.reference_price, geometry.invalidation_price
    target = geometry.target_price if geometry.target_state is TargetState.LEVEL else None
    sign = direction.sign
    risk = abs(reference - stop)

    best_move = None
    worst_move = None

    def result(state, observed, resolution, session, exit_price, reason=""):
        ret = None if exit_price is None else sign * (exit_price - reference) / reference
        r_mult = None if exit_price is None else sign * (exit_price - reference) / risk
        return UnderlyingOutcome(state, observed, resolution, session, exit_price, ret, r_mult,
                                 best_move, worst_move, reason)

    for index, session in enumerate(window_sessions, start=1):
        bar = bars.get(session)
        if bar is None:
            return result(OutcomeState.DATA_GAP, index - 1, None, None, None, f"no bar for session {session.isoformat()}")
        favourable = bar.high if sign > 0 else bar.low
        adverse = bar.low if sign > 0 else bar.high
        move_best = sign * (favourable - reference) / reference
        move_worst = sign * (adverse - reference) / reference
        best_move = move_best if best_move is None else max(best_move, move_best)
        worst_move = move_worst if worst_move is None else min(worst_move, move_worst)

        stop_hit = sign * (adverse - stop) <= 0
        target_hit = target is not None and sign * (favourable - target) >= 0
        if stop_hit:
            fill = min(stop, bar.open) if sign > 0 else max(stop, bar.open)
        if stop_hit and target_hit:
            return result(OutcomeState.AMBIGUOUS, index, index, session, fill, "target and invalidation in the same session")
        if stop_hit:
            return result(OutcomeState.STOP_FIRST, index, index, session, fill)
        if target_hit:
            return result(OutcomeState.TARGET_FIRST, index, index, session, target)

    observed = len(window_sessions)
    if observed >= window_length and observed:
        last = window_sessions[-1]
        return result(OutcomeState.TIMEOUT, observed, observed, last, bars[last].close)
    return result(OutcomeState.OPEN_CENSORED, observed, None, None, None)
