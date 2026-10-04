"""BEH-001 L8: actionable behavioural signal candidates (design §5-§6).

A candidate is a testable proposition: direction, the event behind it, the
trigger that activates it, the expected sequence, what ends it, and the next
anticipated logic. Detection, activation and approval are separate; approval
is downstream. Compression never creates a direction (F6).
"""
from __future__ import annotations

import json
import math
from typing import List, Mapping, Optional

from .behaviour import acceptance
from .compression import describe
from .control import ControlAssessment
from .sequences import SequenceResult

DURATION_UNESTIMATED = ("UNESTIMATED: no causally available duration estimator for this timeframe yet "
                        "(rule DURATION); never hard-coded")
OPPOSITE = {"BULL": "BEAR", "BEAR": "BULL"}


def _measured(level: float, length_log: float, up: bool) -> float:
    """Project a log distance from a level in the candidate direction."""
    return level * math.exp(length_log) if up else level * math.exp(-length_log)


def _next_pivot(seq: SequenceResult, beyond: float, up: bool):
    """Nearest confirmed swing extreme beyond a level, in the candidate direction."""
    pivots = list(seq.minor_pivots) + list(seq.major_pivots)
    if up:
        found = [p.price for p in pivots if p.kind == "H" and p.price > beyond]
        return (min(found), "PRIOR_SWING_HIGH") if found else None
    found = [p.price for p in pivots if p.kind == "L" and p.price < beyond]
    return (max(found), "PRIOR_SWING_LOW") if found else None


def _range_boundary(seq: SequenceResult, scope: str, beyond: float, up: bool):
    """Opposite boundary of the scope's trading range, if it lies beyond the level."""
    ranges = [seq.local_range, seq.trading_range] if scope == "LOCAL" else [seq.trading_range, seq.local_range]
    for r in ranges:
        if r is None:
            continue
        if up and r.resistance > beyond:
            return r.resistance, "RANGE_RESISTANCE: opposite boundary of the trading range"
        if not up and r.support < beyond:
            return r.support, "RANGE_SUPPORT: opposite boundary of the trading range"
    return None


def _pivot_outcome(seq: SequenceResult, beyond: Optional[float], up: bool):
    if beyond is None:
        return None
    found = _next_pivot(seq, beyond, up)
    return None if found is None else (found[0], f"{found[1]}: nearest confirmed swing beyond the trigger")


def _outcome_reached_index(seq: SequenceResult, policy: Mapping, outcome: float, up: bool, start: int):
    """First bar ending a run of closes at or beyond the outcome level, or None."""
    need = int(policy["outcome"]["reached_closes"])
    lc = seq.frame["lc"].to_numpy()
    level = math.log(outcome)
    run = 0
    for i in range(max(0, start), len(lc)):
        run = run + 1 if ((lc[i] >= level) if up else (lc[i] <= level)) else 0
        if run >= need:
            return i
    return None


def _state(seq: SequenceResult, policy: Mapping, **kw) -> str:
    return _state_detail(seq, policy, **kw)[0]


def _state_detail(seq: SequenceResult, policy: Mapping, *, direction: Optional[str], trigger: float,
                  invalidation: float, from_index: int, outcome: Optional[float] = None):
    """DETECTED until the trigger is accepted; FAILED once invalidation is accepted;
    OUTCOME_REACHED when the outcome level is reached after activation and before failure."""
    if direction not in {"BULL", "BEAR"}:
        return "MONITOR", None
    up = direction == "BULL"
    failed = acceptance(seq, level=invalidation, side="BELOW" if up else "ABOVE", from_index=from_index, policy=policy)
    activated = acceptance(seq, level=trigger, side="ABOVE" if up else "BELOW", from_index=from_index, policy=policy)
    failed_ok = failed["state"] in {"ACCEPTED", "ACCEPTED_PROVISIONAL"}
    activated_ok = activated["state"] in {"ACCEPTED", "ACCEPTED_PROVISIONAL"}
    if activated_ok and outcome is not None:
        reached = _outcome_reached_index(seq, policy, outcome, up, activated["index"])
        if reached is not None and (not failed_ok or failed["index"] < activated["index"] or failed["index"] > reached):
            return "OUTCOME_REACHED", reached
    if failed_ok and (activated["index"] is None or failed["index"] >= activated["index"]):
        return "FAILED", None
    if activated_ok:
        return "ACTIVATED", None
    return "DETECTED", None


def disambiguate_ids(out: List[dict]) -> None:
    """Two events of one type on one bar testing different levels are different
    propositions: colliding IDs gain the trigger level; unique IDs are unchanged."""
    counts: dict = {}
    for c in out:
        counts[c["Candidate_ID"]] = counts.get(c["Candidate_ID"], 0) + 1
    for c in out:
        if counts[c["Candidate_ID"]] > 1:
            level = c.get("Trigger_Level")
            c["Candidate_ID"] = f"{c['Candidate_ID']}|L{level:.6g}" if level is not None else c["Candidate_ID"]
    # One event detected twice on one bar is one proposition: publish it once.
    seen: set = set()
    unique: List[dict] = []
    for c in out:
        if c["Candidate_ID"] in seen:
            continue
        seen.add(c["Candidate_ID"])
        unique.append(c)
    out[:] = unique


def build_candidates(**kw) -> List[dict]:
    """Candidates for one timeframe and scope. Reaching an outcome ends a stage, not the
    ticker: a later candidate (event after the reached bar) names the most recent
    reached candidate as its parent unless a failure already supplied one."""
    out = _build_candidates(**kw)
    disambiguate_ids(out)
    reached = sorted((c["_reached_index"], c["Candidate_ID"]) for c in out if c["_reached_index"] is not None)
    for c in out:
        if c["Parent_Candidate_ID"] is None:
            prior = [cid for index, cid in reached if index < c["_from_index"] and cid != c["Candidate_ID"]]
            if prior:
                c["Parent_Candidate_ID"] = prior[-1]
    for c in out:
        c.pop("_reached_index")
        c.pop("_from_index")
    return out


def _build_candidates(*, ticker: str, timeframe: str, role: str, seq: SequenceResult,
                     control: ControlAssessment, phase: dict, events: List[dict],
                     compression: dict, maturity: str, policy: Mapping,
                     scope: str = "CAMPAIGN", include_context: bool = True) -> List[dict]:
    end = seq.last_index
    as_of = seq.label(end)
    controller_side = {"BUYERS": "BULL", "SELLERS": "BEAR"}.get(control.controller)
    base = {
        "Ticker": ticker, "Timeframe": timeframe, "Timeframe_Role": role, "As_Of": as_of,
        "Structure_Scope": scope,
        "Wyckoff_Phase": phase["phase"], "Phase_Confidence": phase["confidence"],
        "Phase_Transition": phase["transition"], "Local_Phase": phase.get("local_phase"),
        "Structural_Context": phase["context"],
        "Controller": control.controller, "Control_Quality": control.quality,
        "SOT_State": f"controller thrusts {control.sot.lower()}; thrusts={len(control.thrust_atr)} "
                     f"({', '.join(f'{x:.2f}' for x in control.thrust_atr[-3:])} ATR)",
        "Crabel_Compression": describe(compression), "Movement_Maturity": maturity,
        "Control_Origin": None if control.origin is None else f"{control.origin.kind} {control.origin.price:.4g} @ {control.origin.label}",
        "Control_Start": control.start_label, "Control_Duration": control.duration_bars,
        "Control_Transfer_Condition": control.transfer_condition or "No directional controller to transfer",
        "Movement_Start": control.start_label, "Movement_Duration": control.duration_bars,
        "Expected_Duration": DURATION_UNESTIMATED, "Direction_Status": "HYPOTHESIS_NOT_OUTCOME",
    }
    out: List[dict] = []

    def add(signal_type: str, direction: Optional[str], event: str, trigger_level: Optional[float],
            invalidation_level: Optional[float], trigger: str, invalidation: str, expected: str,
            next_logic: str, from_index: int, evidence: List[dict], warnings: List[str],
            outcome=None, parent: Optional[str] = None) -> None:
        state, reached = (("MONITOR", None) if direction is None or trigger_level is None or invalidation_level is None
                          else _state_detail(seq, policy, direction=direction, trigger=trigger_level,
                                             invalidation=invalidation_level, from_index=from_index,
                                             outcome=outcome[0] if outcome else None))
        if state == "OUTCOME_REACHED":
            next_logic = (f"Outcome {outcome[0]:.4g} reached at {seq.label(reached)}: this stage is complete, the "
                          f"ticker is not. Next stage is read from the new structure: continuation beyond "
                          f"{outcome[0]:.4g}, a test back toward it, or a range forming at it")
        if direction and controller_side and direction != controller_side:
            warnings = warnings + [f"COUNTER_CAMPAIGN: {direction} candidate against {control.controller} control"]
        if maturity in {"MATURE", "LATE", "EXHAUSTING"} and direction == controller_side:
            warnings = warnings + [f"MATURE_MOVE: trigger may be fresh but the move is {maturity}"]
        if compression["state"] == "CONTRACTING" and direction and direction != controller_side and controller_side:
            warnings = warnings + ["Contraction does not imply a reversal; buyers/sellers have not demonstrated a defended change"]
        out.append({
            **base,
            "Candidate_ID": f"{ticker}|{timeframe}|{scope}|{signal_type}|{seq.label(from_index)}",
            "Signal_Type": signal_type, "Signal_State": state, "Direction": direction,
            "Wyckoff_Event": event, "Trigger": trigger, "Trigger_Level": trigger_level,
            "Invalidation": invalidation, "Invalidation_Level": invalidation_level,
            "Expected_Behaviour": expected, "Next_Anticipated_Logic": next_logic,
            # RQ-1: the expected behaviour as a measurable structural level.
            "Outcome_Level": (outcome[0] if outcome and direction in {"BULL", "BEAR"} and state != "MONITOR" else None),
            "Outcome_Definition": (outcome[1] if outcome and direction in {"BULL", "BEAR"} and state != "MONITOR"
                                   else "NONE: monitoring observation" if direction is None or state == "MONITOR"
                                   else "NONE: no structural outcome level"),
            # RQ-2 / RQ-3: lineage and age since the event bar.
            "Parent_Candidate_ID": parent, "Age_Bars": int(end - from_index),
            "Outcome_Reached_As_Of": None if reached is None else seq.label(reached),
            "_reached_index": reached, "_from_index": from_index,
            "Warning": "; ".join(warnings) if warnings else "",
            "Evidence": json.dumps(evidence, sort_keys=True, default=str),
        })

    for e in events:
        side = e["side"]
        up = side == "BULL"
        if e["event"] in {"LPSY", "LPS"} and e["state"] != "FAILED":
            shallow = e.get("depth") == "SHALLOW"
            name = ("Trend Continuation after Shallow Test" if shallow else
                    "SOW -> LPSY continuation" if not up else "SOS -> LPS continuation")
            add(name, side, f"{'SOS' if up else 'SOW'} then {e['event']} (reaction retraced "
                f"{e['retracement']:.0%}, did not regain the thrust origin {e['thrust_origin']:.4g})",
                e["thrust_end"], e["reaction_extreme"],
                f"acceptance {'above' if up else 'below'} {e['thrust_end']:.4g} (thrust extreme)",
                f"acceptance {'below' if up else 'above'} {e['reaction_extreme']:.4g} (the {e['event']} extreme)",
                f"{'Buyers' if up else 'Sellers'} resume and extend beyond {e['thrust_end']:.4g}, keeping the reaction area defended",
                f"Failed {e['event']} -> local range / testing; campaign reversal needs acceptance "
                f"{'below' if up else 'above'} {control.transfer_level:.4g} plus defence",
                e["index"],
                [{"status": "OBSERVED", "what": f"{'SOS' if up else 'SOW'} thrust to {e['thrust_end']:.4g}"},
                 {"status": "OBSERVED", "what": f"reaction to {e['reaction_extreme']:.4g}, {e['depth'].lower()}"},
                 {"status": "INFERRED", "what": f"{e['event']} candidate: reaction failed to repair"}], [],
                outcome=(_measured(e["reaction_extreme"], abs(math.log(e["thrust_origin"] / e["thrust_end"])), up),
                         "MEASURED_MOVE: prior thrust length projected from the reaction extreme"))
        elif e["event"] in {"SPRING", "UPTHRUST", "UTAD"} and e["state"] != "SUPERSEDED":
            label = {"SPRING": "Spring", "UPTHRUST": "Upthrust", "UTAD": "UTAD"}[e["event"]]
            if e["state"] == "FAILED":
                cont = OPPOSITE[side]
                name = "Failed Spring Continuation" if e["event"] == "SPRING" else "Failed Upthrust Continuation"
                add(name, cont, f"Failed {label} (lost {e['level']:.4g} and could not restore it)",
                    e["level"], e["trigger_level"],
                    f"acceptance {'below' if cont == 'BEAR' else 'above'} {e['level']:.4g} (lost structure)",
                    f"sustained recovery {'above' if cont == 'BEAR' else 'below'} {e['trigger_level']:.4g}",
                    f"{'Downward' if cont == 'BEAR' else 'Upward'} continuation after the failed {label.lower()}",
                    f"Recovery of the lost structure -> re-read the {label.lower()} on the new structure",
                    e["index"], [{"status": "OBSERVED", "what": f"{label} at {e['event_price']:.4g} failed"}], [],
                    outcome=(_pivot_outcome(seq, e["level"], cont == "BULL") or
                             (_measured(e["level"], abs(math.log(e["trigger_level"] / e["level"])), cont == "BULL"),
                              "MEASURED_MOVE: failed recovery length projected beyond the lost level")),
                    parent=f"{ticker}|{timeframe}|{scope}|"
                           f"{'Spring Candidate' if e['event'] == 'SPRING' else 'UTAD Test' if e['event'] == 'UTAD' else 'Upthrust Candidate'}"
                           f"|{seq.label(e['index'])}")
            else:
                name = ("Spring Candidate" if e["event"] == "SPRING" else
                        "UTAD Test" if e["event"] == "UTAD" else "Upthrust Candidate")
                add(name, side, f"{label} of {e['level_source'].lower()} {e['level']:.4g}"
                    f" ({e['state'].lower()})", e["trigger_level"], e["event_price"],
                    f"acceptance {'above' if up else 'below'} {e['trigger_level']:.4g} (local response)",
                    f"acceptance {'below' if up else 'above'} the event extreme {e['event_price']:.4g}",
                    f"Price defends the recovered area and moves away from the {'low' if up else 'high'}",
                    f"Failed {label.lower()} -> {'BEAR' if up else 'BULL'} continuation",
                    e["index"],
                    [{"status": "OBSERVED", "what": f"penetrated {e['level']:.4g} to {e['event_price']:.4g} and recovered"},
                     {"status": "UNRESOLVED" if e["state"] == "DETECTED" else "OBSERVED",
                      "what": f"subsequent response: {e['state']}"}], [],
                    outcome=_range_boundary(seq, scope, e["trigger_level"], up) or
                    _pivot_outcome(seq, e["trigger_level"], up))
        elif e["event"] in {"SELLER_ABSORPTION", "BUYER_ABSORPTION"}:
            name = "Seller Absorption Breakdown" if not up else "Buyer Absorption Breakout"
            add(name, side, e["event"].replace("_", " ").title(), e["boundary"], e["defending"],
                f"expansion and acceptance {'above' if up else 'below'} {e['boundary']:.4g}",
                f"acceptance {'below' if up else 'above'} {e['defending']:.4g} (defending structure lost)",
                "The expansion retains progress beyond the pressured boundary",
                "Two-sided range if neither side retains the break", e["index"],
                [{"status": "OBSERVED", "what": f"{'higher lows' if up else 'lower recovery highs'} pressing {e['boundary']:.4g}"},
                 {"status": "INFERRED", "what": f"effort/result absorption={e['effort_absorption']}"}], [],
                outcome=(_measured(e["boundary"], abs(math.log(e["boundary"] / e["defending"])), up),
                         "MEASURED_MOVE: boundary-to-defending width projected beyond the boundary"))
        elif e["event"] == "CHANGE_OF_BEHAVIOUR":
            add("Change-of-Behaviour Reversal", side, "Abnormal counter-move against established thrusts",
                e["transfer_level"], float(seq.current_leg.start.price),
                f"acceptance {'above' if up else 'below'} {e['transfer_level']:.4g} (control-transfer level)",
                f"acceptance {'below' if up else 'above'} {seq.current_leg.start.price:.4g} (old controller restored)",
                "The new controller defends gained territory and extends progress",
                "Old campaign continues", e["index"],
                [{"status": "OBSERVED", "what": f"counter-move {e['counter_move_atr']:.2f} ATR"}], [],
                outcome=(_measured(e["transfer_level"],
                                   abs(math.log(e["transfer_level"] / float(seq.current_leg.start.price))), up),
                         "MEASURED_MOVE: transfer-to-leg-start distance projected beyond the transfer level"))

    if not include_context:
        return out
    # Compression and hinge: context only; a direction needs a directional controller.
    if compression["state"] == "CONTRACTING":
        consistent = (controller_side == "BEAR" and compression["location"] in {"BELOW_FALLING_CEILING", "AT_SUPPORT"}) or \
                     (controller_side == "BULL" and compression["location"] in {"ABOVE_RISING_FLOOR", "AT_RESISTANCE"})
        direction = controller_side if consistent else None
        up = direction == "BULL"
        trig = compression["box_high"] if up else compression["box_low"]
        inv = compression["box_low"] if up else compression["box_high"]
        add("Crabel Compression Breakout", direction, "Contraction at a meaningful location" if direction else
            "Contraction without a supported directional reading",
            trig if direction else None, inv if direction else None,
            f"expansion and acceptance {'above' if up else 'below'} {trig:.4g}" if direction else "monitor both box edges",
            f"rapid return into the box, or acceptance {'below' if up else 'above'} {inv:.4g}" if direction else "n/a",
            "Expansion produces retained directional movement" if direction else "Wait for a side to retain an expansion",
            "Monitoring observation" if direction else "Monitoring observation",
            end, [{"status": "OBSERVED", "what": describe(compression)}], [],
            outcome=_pivot_outcome(seq, trig, up) if direction else None)
    highs = [p for p in seq.minor_pivots if p.kind == "H"][-2:]
    lows = [p for p in seq.minor_pivots if p.kind == "L"][-2:]
    if len(highs) == 2 and len(lows) == 2 and highs[1].price < highs[0].price and lows[1].price > lows[0].price:
        direction = controller_side
        up = direction == "BULL"
        add("Hinge / Apex Expansion", direction, "Converging swings",
            (highs[1].price if up else lows[1].price) if direction else None,
            (lows[1].price if up else highs[1].price) if direction else None,
            f"expansion and acceptance {'above' if up else 'below'} the apex boundary" if direction else "monitor both boundaries",
            "failed expansion / renewed overlap" if direction else "n/a",
            "Price leaves the hinge and retains progress" if direction else "Wait for a side",
            "Monitoring observation", end,
            [{"status": "OBSERVED", "what": f"lower highs {highs[0].price:.4g}->{highs[1].price:.4g}, "
                                              f"higher lows {lows[0].price:.4g}->{lows[1].price:.4g}"}], [],
            outcome=_pivot_outcome(seq, highs[0].price if up else lows[0].price, up) if direction else None)
    if maturity in {"LATE", "EXHAUSTING"} and controller_side:
        add("Mature Trend Exhaustion", None, "Thrusts losing effectiveness", None, None,
            f"warning only; directional only after control transfer ({control.transfer_condition})",
            "effective resumption of the original trend", "Watch for a change of behaviour",
            "Change-of-Behaviour Reversal candidate if control transfers", end,
            [{"status": "OBSERVED", "what": f"controller thrusts {control.sot.lower()}"}], [])
    return out
