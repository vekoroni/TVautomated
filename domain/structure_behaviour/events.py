"""BEH-001 L6: behaviourally supported events with a life cycle (F4).

Every event starts as a candidate and is resolved from later bars at the same
cut: DETECTED (response not yet decisive), CONFIRMED, FAILED or UNRESOLVED.
Events are never filled in from a phase label. One rule per event, mirrored.
"""
from __future__ import annotations

import math
from typing import List, Mapping, Optional

from .behaviour import acceptance, assess_reaction, effort_result
from .control import ControlAssessment
from .sequences import SequenceResult

MIRROR_EVENT = {"SPRING": "UPTHRUST", "SOS": "SOW", "LPS": "LPSY", "BUYER_ABSORPTION": "SELLER_ABSORPTION"}


def _event(name, side, state, index, seq, **fields) -> dict:
    return {"event": name, "side": side, "state": state, "index": index,
            "label": seq.label(index) if index is not None else None, **fields}


def _boundary_tests(seq: SequenceResult, policy: Mapping) -> List[dict]:
    """Spring / Upthrust: penetrate an established level, recover, then respond."""
    cfg = policy["events"]
    frame = seq.frame
    end = seq.last_index
    ll, lh, lc, atr = (frame[c].to_numpy() for c in ("ll", "lh", "lc", "atr"))
    out = []
    rng = seq.trading_range
    supports, resistances = [], []
    if rng is not None:
        supports.append(("RANGE_SUPPORT", rng.support, rng.end_index))
        resistances.append(("RANGE_RESISTANCE", rng.resistance, rng.end_index))
    majors = seq.major_pivots or seq.minor_pivots
    lows = [p for p in majors if p.kind == "L"]
    highs = [p for p in majors if p.kind == "H"]
    if lows:
        supports.append(("PIVOT_LOW", lows[-1].price, lows[-1].confirmed_index))
    if highs:
        resistances.append(("PIVOT_HIGH", highs[-1].price, highs[-1].confirmed_index))
    for side, levels, name in (("BULL", supports, "SPRING"), ("BEAR", resistances, "UPTHRUST")):
        sign = 1.0 if side == "BULL" else -1.0
        seen = set()
        for source, level, known_from in levels:
            key = round(level, 6)
            if key in seen:
                continue
            seen.add(key)
            lv = math.log(level)
            for i in range(known_from + 1, end + 1):
                extreme = ll[i] if side == "BULL" else lh[i]
                if sign * (lv - extreme) < float(cfg["break_min_atr"]) * atr[i]:
                    continue
                window = range(i, min(end, i + int(cfg["reclaim_within_bars"])) + 1)
                recovered = [j for j in window if sign * (lc[j] - lv) > 0]
                if not recovered:
                    continue
                event_extreme = frame["low" if side == "BULL" else "high"].iloc[i: recovered[0] + 1]
                event_price = float(event_extreme.min() if side == "BULL" else event_extreme.max())
                # Response after the recovery decides the life cycle.
                failure = acceptance(seq, level=event_price, side="BELOW" if side == "BULL" else "ABOVE",
                                     from_index=recovered[0] + 1, policy=policy)
                span = frame.iloc[i: recovered[0] + 1]
                recovery_high = float(span["high"].max() if side == "BULL" else span["low"].min())
                follow = acceptance(seq, level=recovery_high, side="ABOVE" if side == "BULL" else "BELOW",
                                    from_index=recovered[0] + 1, policy=policy)
                back_in = acceptance(seq, level=level, side="BELOW" if side == "BULL" else "ABOVE",
                                     from_index=recovered[0] + 1, policy=policy)
                if failure["state"] in {"ACCEPTED", "ACCEPTED_PROVISIONAL"} or back_in["state"] in {"ACCEPTED", "ACCEPTED_PROVISIONAL"}:
                    state = "FAILED"
                elif follow["state"] in {"ACCEPTED", "ACCEPTED_PROVISIONAL"}:
                    state = "CONFIRMED"
                else:
                    state = "DETECTED" if end - recovered[0] <= 2 * int(cfg["reclaim_within_bars"]) else "UNRESOLVED"
                out.append(_event(name, side, state, i, seq, level=level, level_source=source,
                                  event_price=event_price, trigger_level=recovery_high,
                                  recovered_index=recovered[0]))
                break
    return out


def _thrust_events(seq: SequenceResult, control: ControlAssessment, policy: Mapping) -> List[dict]:
    """SOS/SOW then LPS/LPSY: effective retained progress, then an unrepaired reaction."""
    cfg = policy["events"]
    out = []
    if control.controller not in {"BUYERS", "SELLERS"}:
        return out
    side = "BULL" if control.controller == "BUYERS" else "BEAR"
    direction = "UP" if side == "BULL" else "DOWN"
    waves = seq.major_waves if control.degree == "MAJOR" else seq.minor_waves
    leg = seq.major_leg if control.degree == "MAJOR" else seq.current_leg
    thrusts = [w for w in waves if w.direction == direction
               and w.distance_atr >= float(cfg["effective_thrust_min_atr"])
               and (w.extension_atr is None or w.extension_atr > 0)]
    live = None
    if leg is not None and leg.direction == direction and leg.distance_atr >= float(cfg["effective_thrust_min_atr"]):
        live = leg
    if not thrusts and live is None:
        return out
    if thrusts:
        w = thrusts[-1]
        out.append(_event("SOW" if side == "BEAR" else "SOS", side,
                          "CONFIRMED" if w.extension_atr is not None and w.extension_atr > 0 else "DETECTED",
                          w.end.index, seq, thrust_origin=w.start.price, thrust_end=w.end.price,
                          distance_atr=round(w.distance_atr, 3)))
        # Reaction after the thrust: next confirmed opposing wave or the live opposing leg.
        reactions = [r for r in waves if r.start.index == w.end.index and r.direction != direction]
        reaction_extreme = reactions[0].end.price if reactions else (
            leg.extreme_price if leg is not None and leg.direction != direction and leg.start.index == w.end.index else None)
        if reaction_extreme is not None:
            assessed = assess_reaction(origin=w.start.price, thrust_end=w.end.price,
                                       reaction_extreme=reaction_extreme, thrust_direction=direction, policy=policy)
            resumed = acceptance(seq, level=w.end.price, side="BELOW" if side == "BEAR" else "ABOVE",
                                 from_index=(reactions[0].end.index if reactions else w.end.index + 1), policy=policy)
            if assessed["state"] == "FULL_REPAIR":
                state = "FAILED"
            elif resumed["state"] in {"ACCEPTED", "ACCEPTED_PROVISIONAL"}:
                state = "CONFIRMED"
            else:
                state = "DETECTED"
            out.append(_event("LPSY" if side == "BEAR" else "LPS", side, state,
                              reactions[0].end.index if reactions else seq.last_index, seq,
                              reaction_extreme=reaction_extreme, thrust_end=w.end.price,
                              thrust_origin=w.start.price, retracement=round(assessed["retracement"], 3),
                              depth=assessed["depth"], resumed=resumed["state"],
                              resumed_index=resumed["index"]))
    return out


def _absorption(seq: SequenceResult, control: ControlAssessment, policy: Mapping) -> List[dict]:
    """One side repeatedly achieves little while the other defends and presses."""
    out = []
    lows = [p for p in seq.minor_pivots if p.kind == "L"][-3:]
    highs = [p for p in seq.minor_pivots if p.kind == "H"][-3:]
    end = seq.last_index
    close = float(seq.frame["close"].iloc[end])
    atr = seq.atr(end)
    er = effort_result(seq, max(1, end - 10), end, policy)
    # Swing steps must clear the tolerance band; noise is not absorption (F7).
    tol = float(policy["acceptance"]["min_beyond_atr"]) * atr
    falling_highs = len(highs) >= 2 and all(
        math.log(a.price) - math.log(b.price) > tol for a, b in zip(highs, highs[1:]))
    rising_lows = len(lows) >= 2 and all(
        math.log(b.price) - math.log(a.price) > tol for a, b in zip(lows, lows[1:]))
    if falling_highs and len(lows) >= 1 and abs(math.log(close / lows[-1].price)) <= 1.5 * atr:
        out.append(_event("SELLER_ABSORPTION", "BEAR", "DETECTED", end, seq, boundary=lows[-1].price,
                          defending=highs[-1].price, effort_absorption=er["absorption"]))
    if rising_lows and len(highs) >= 1 and abs(math.log(highs[-1].price / close)) <= 1.5 * atr:
        out.append(_event("BUYER_ABSORPTION", "BULL", "DETECTED", end, seq, boundary=highs[-1].price,
                          defending=lows[-1].price, effort_absorption=er["absorption"]))
    return out


def _change_of_behaviour(seq: SequenceResult, policy: Mapping) -> List[dict]:
    """An abnormal counter-move against an established sequence of thrusts."""
    out = []
    waves = seq.minor_waves
    leg = seq.current_leg
    if len(waves) < 3 or leg is None:
        return out
    prior = waves[-1] if waves[-1].direction != leg.direction else waves[-2]
    ratio = float(policy["events"]["abnormal_counter_move_ratio"])
    same_dir = [w for w in waves if w.direction == prior.direction][-2:]
    established = len(same_dir) == 2 and all((w.extension_atr or 0) > 0 for w in same_dir)
    if established and leg.direction != prior.direction and leg.distance_atr >= ratio * prior.distance_atr \
            and leg.distance_atr > max(w.distance_atr for w in same_dir):
        side = "BULL" if leg.direction == "UP" else "BEAR"
        out.append(_event("CHANGE_OF_BEHAVIOUR", side, "DETECTED", seq.last_index, seq,
                          transfer_level=prior.start.price, counter_move_atr=round(leg.distance_atr, 3)))
    return out


def _supersede_failed_tests(events: List[dict]) -> List[dict]:
    """Rule FAILED_EVENT: once a Spring fails, a live Spring whose low is at or
    above the failed one is superseded (mirror for Upthrust/UTAD)."""
    for name, worse in (("SPRING", lambda live, failed: live >= failed),
                        ("UPTHRUST", lambda live, failed: live <= failed)):
        family = [e for e in events if e["event"] == name or (name == "UPTHRUST" and e["event"] == "UTAD")]
        failed = [e["event_price"] for e in family if e["state"] == "FAILED"]
        for e in family:
            if e["state"] in {"DETECTED", "CONFIRMED", "UNRESOLVED"} and any(worse(e["event_price"], f) for f in failed):
                e["state"] = "SUPERSEDED"
    return events


def detect_events(seq: SequenceResult, control: ControlAssessment, policy: Mapping) -> List[dict]:
    if seq.status != "EVALUATED":
        return []
    events = _supersede_failed_tests(_boundary_tests(seq, policy)) + _thrust_events(seq, control, policy)
    events += _absorption(seq, control, policy) + _change_of_behaviour(seq, policy)
    # UTAD needs a supported distribution context: a range plus seller control.
    for e in events:
        if e["event"] == "UPTHRUST" and seq.trading_range is not None and control.controller == "SELLERS":
            e["event"] = "UTAD"
    return events


def detect_local_events(seq: SequenceResult, control: ControlAssessment, policy: Mapping) -> List[dict]:
    """Local (minor-swing) structure: thrust/reaction events only (NESTED_STRUCTURE)."""
    if seq.status != "EVALUATED":
        return []
    return _thrust_events(seq, control, policy)
