"""BEH-001 L4: who controls the campaign, how well, and what would transfer it.

Control is inferred from progress and retained ground across swings plus the
live leg (rule CONTROL_FROM_PROGRESS, F2). One mirrored rule; no participant
identity is inferred.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Mapping, Optional, Tuple

from .behaviour import acceptance, assess_reaction, compare_thrusts
from .sequences import CurrentLeg, Pivot, SequenceResult


@dataclass(frozen=True)
class ControlAssessment:
    status: str
    controller: str                      # BUYERS / SELLERS / TWO-SIDED / CONTROL SHIFTING / NOT_EVALUATED
    quality: str = "UNMEASURED"          # STRENGTHENING / WEAKENING / UNCHANGED / UNMEASURED
    degree: str = "MAJOR"
    origin: Optional[Pivot] = None
    start_label: Optional[str] = None
    duration_bars: Optional[int] = None
    thrust_count: int = 0
    thrust_atr: Tuple[float, ...] = ()
    sot: str = "UNMEASURED"
    last_reaction: Optional[dict] = None
    transfer_level: Optional[float] = None
    transfer_condition: str = ""
    evidence: Tuple[str, ...] = field(default_factory=tuple)


def _log(p: float) -> float:
    return math.log(p)


def _side_view(pivots, leg: Optional[CurrentLeg], side: str):
    """Express the question in SELLERS orientation: 'own' extremes are lows."""
    own_kind, other_kind = ("L", "H") if side == "SELLERS" else ("H", "L")
    sign = 1.0 if side == "SELLERS" else -1.0          # sign*(log) is 'lower' for sellers
    own = [p for p in pivots if p.kind == own_kind]
    other = [p for p in pivots if p.kind == other_kind]
    leg_own_extreme = None
    if leg is not None and leg.direction == ("DOWN" if side == "SELLERS" else "UP"):
        leg_own_extreme = leg.extreme_price
    return own, other, sign, leg_own_extreme


def _assess_side(seq: SequenceResult, pivots, leg, side: str, tol: float, policy) -> Optional[dict]:
    own, other, sign, leg_extreme = _side_view(pivots, leg, side)
    if len(other) < 2 or not own:
        return None
    lower_other = sign * (_log(other[-1].price) - _log(other[-2].price)) < -tol   # lower high (sellers)
    lower_own = len(own) >= 2 and sign * (_log(own[-1].price) - _log(own[-2].price)) < -tol
    evidence = []
    if lower_own:
        # Retention: a new extreme that price has since been accepted back
        # beyond (the broken prior extreme reclaimed) is a failed push, not
        # progress (refinement 2).
        reclaimed = acceptance(seq, level=own[-2].price, side="ABOVE" if side == "SELLERS" else "BELOW",
                               from_index=own[-1].index + 1, policy=policy)
        if reclaimed["state"] in {"ACCEPTED", "ACCEPTED_PROVISIONAL"}:
            lower_own = False
            evidence.append("EXTREME_NOT_RETAINED")
    if leg_extreme is not None and sign * (_log(leg_extreme) - _log(own[-1].price)) < -tol:
        lower_own = True
        evidence.append("CURRENT_LEG")
    # The controller's last thrust: from the latest 'other' pivot that precedes
    # the latest own extreme (or the live leg) to that extreme.
    thrust_end_price = leg_extreme if "CURRENT_LEG" in evidence else own[-1].price
    origins = [p for p in other if p.index < (leg.extreme_index if "CURRENT_LEG" in evidence else own[-1].index)]
    if not origins:
        return None
    origin = origins[-1]
    # Reaction since the thrust end: a later 'other' pivot or the live opposing leg.
    reaction_extreme = None
    if "CURRENT_LEG" not in evidence:
        later_other = [p for p in other if p.index > own[-1].index]
        if later_other:
            reaction_extreme = later_other[-1].price
        elif leg is not None and leg.direction != ("DOWN" if side == "SELLERS" else "UP"):
            reaction_extreme = leg.extreme_price
    reaction = None
    if reaction_extreme is not None:
        reaction = assess_reaction(origin=origin.price, thrust_end=thrust_end_price,
                                   reaction_extreme=reaction_extreme,
                                   thrust_direction="DOWN" if side == "SELLERS" else "UP", policy=policy)
    repaired = reaction is not None and reaction["state"] == "FULL_REPAIR"
    holds = lower_other and lower_own and not repaired
    return {"holds": holds, "lower_other": lower_other, "lower_own": lower_own, "repaired": repaired,
            "origin": origin, "reaction": reaction, "evidence": tuple(evidence), "other": other}


def assess_control(seq: SequenceResult, policy: Mapping, degree: str | None = None) -> ControlAssessment:
    """Campaign control (major swings) or, with degree="MINOR", local control."""
    if seq.status != "EVALUATED":
        return ControlAssessment(seq.status, "NOT_EVALUATED")
    min_pivots = int(policy["range"]["min_pivots"])
    use_major = len(seq.major_pivots) >= min_pivots if degree is None else degree == "MAJOR"
    pivots = seq.major_pivots if use_major else seq.minor_pivots
    leg = seq.major_leg if use_major else seq.current_leg
    degree = "MAJOR" if use_major else "MINOR"
    tol = float(policy["acceptance"]["min_beyond_atr"]) * seq.atr(seq.last_index)
    sellers = _assess_side(seq, pivots, leg, "SELLERS", tol, policy)
    buyers = _assess_side(seq, pivots, leg, "BUYERS", tol, policy)
    s_hold = bool(sellers and sellers["holds"])
    b_hold = bool(buyers and buyers["holds"])
    if s_hold and not b_hold:
        side, view = "SELLERS", sellers
    elif b_hold and not s_hold:
        side, view = "BUYERS", buyers
    else:
        rng = seq.trading_range if use_major else seq.local_range
        balanced = rng is not None and rng.price_inside
        controller = "TWO-SIDED" if balanced and not (s_hold or b_hold) else "CONTROL SHIFTING"
        return ControlAssessment("EVALUATED", controller, degree=degree,
                                 evidence=("RANGE_BALANCED",) if balanced else ("MIXED_PROGRESS",))
    # Control origin: walk back while successive 'other' pivots keep stepping in favour.
    other = view["other"]
    sign = 1.0 if side == "SELLERS" else -1.0
    start = len(other) - 1
    while start > 0 and sign * (_log(other[start].price) - _log(other[start - 1].price)) < 0:
        start -= 1
    origin = other[start]
    thrusts = tuple(w.distance_atr for w in (seq.major_waves if use_major else seq.minor_waves)
                    if w.start.index >= origin.index and w.direction == ("DOWN" if side == "SELLERS" else "UP"))
    if leg is not None and leg.direction == ("DOWN" if side == "SELLERS" else "UP") and "CURRENT_LEG" in view["evidence"]:
        thrusts = thrusts + (leg.distance_atr,)
    sot = compare_thrusts(thrusts[-2], thrusts[-1], policy) if len(thrusts) >= 2 else "UNMEASURED"
    quality = {"LENGTHENING": "STRENGTHENING", "SHORTENING": "WEAKENING"}.get(sot, sot)
    reaction = view["reaction"]
    if reaction is not None and reaction["depth"] == "DEEP" and quality != "WEAKENING":
        quality = "WEAKENING"
    transfer = view["origin"].price
    verb = "above" if side == "SELLERS" else "below"
    other_side = "buyers" if side == "SELLERS" else "sellers"
    return ControlAssessment(
        "EVALUATED", side, quality, degree, origin, origin.label, seq.last_index - origin.index,
        len(thrusts), thrusts, sot, reaction, transfer,
        f"{other_side} accept {verb} {transfer:.4g} (origin of the last thrust) and defend it",
        view["evidence"],
    )
