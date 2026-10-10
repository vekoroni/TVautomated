"""The anticipated move: replaces stop-based R:R (ACK 3 Oct 2026; design AVS_ANTICIPATED_MOVE_DESIGN_20261003).

One owner, pure. Display only in this build step: no gate, score or rank reads these fields until the replay
validation (design §7) and ACK's D-C ranking switch.

- Magnitude (§3): the trade-side BEH-001 candidate's structural Outcome_Level, capped at the volatility-reachable
  level k*sigma*sqrt(t_q80/252) (D-D); no structural level -> volatility only. Nothing is derived from a stop.
- Time (§4): the candidate's duration evidence (q50/q80 own-timeframe bars -> sessions, governed table).
  Thin evidence -> hold UNESTIMATED; the reach uses the governed window, labelled (D-A a).
- Payoff (§5): coverage = anticipated move / breakeven move. Output-trust item 4 (ACK decision 2, 9 Oct 2026): value
  from the ONE engine (domain.option_valuation: EV3's American CRR, BSM for European index options; rate and dividend
  yield with their basis), net of spread and fees, contract IV held. Scenarios at the median time, as return on
  premium: target reached, invalidation reached, stall, and a lower-IV target case when earnings fall inside the hold.
  The value multiples (rank, lane B) and the pays state are 1 + the net return of the same engine. Stress (disclosed,
  not scored): the slower q80 path, and IV x governed iv_stress low when earnings fall inside q80.
- The invalidation is the thesis exit shown on the card; it is deliberately not an input.
- No behavioural event on the trade's side -> NO_TRADE_SIDE_EVENT: symmetric volatility is not an expectation.
"""
from __future__ import annotations

from datetime import date, datetime
import json
import math
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

from domain.option_valuation import (VALUATION_FIELDS, cost_basis, entry_cost_usd_per_share, resolve_dividend,
                                     resolve_rate, return_on_premium, scenario_value, valuation_policy)

CONSTANTS_PATH = Path(__file__).resolve().parents[1] / "config" / "governed_constants_v1.json"
ANTICIPATED_MOVE_FIELDS = (
    "anticipated_move_state", "anticipated_level", "anticipated_level_basis", "anticipated_move_pct",
    "anticipated_level_q50",
    "anticipated_structural_level", "anticipated_structural_definition", "anticipated_reachable_level",
    "anticipated_sessions_q50", "anticipated_sessions_q80", "anticipated_hold_sessions", "anticipated_time_basis",
    "anticipated_p_outcome_by_limit", "anticipated_p_invalidation_by_limit", "anticipated_evidence_n",
    "anticipated_evidence_status", "anticipated_breakeven_move_pct", "anticipated_move_coverage",
    "anticipated_value_multiple_q50", "anticipated_value_multiple_q80", "anticipated_value_multiple_earnings_stress",
    "anticipated_stress_basis", "anticipated_time_fit", "anticipated_pays_state", "anticipated_authority",
    "anticipated_version",
    # L5 (ACK 7 Oct 2026): the contract the value was computed for (set by the EOD engine and the Morning swap
    # recompute; the Lab's economics identity). It travels with the other anticipated fields into the book.
    "anticipated_contract_symbol",
    # Output-trust item 4: the one engine's model, inputs with their basis, and the labelled scenarios.
    *VALUATION_FIELDS,
    # M-G2-01 (ACK 10 Oct 2026): which quote valued the contract and when, and the frozen Evening reference beside
    # a Morning repricing (set by the EOD engine and the Morning recompute; never overwritten).
    "anticipated_contract_basis", "anticipated_valued_at_utc", "eod_anticipated_value_multiple_q50",
    "eod_anticipated_pays_state", "eod_scenario_target_return_on_premium", "eod_anticipated_valued_at_utc",
)
_ESTIMATED = {"IN_SAMPLE_REPLAY_NOT_VALIDATED", "VALIDATED"}


def _num(value: Any) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _date(value: Any) -> Optional[date]:
    if value in (None, ""):
        return None
    try:
        return datetime.fromisoformat(str(value)[:10]).date()
    except ValueError:
        return None


def _constants() -> Dict[str, Any]:
    return json.loads(CONSTANTS_PATH.read_text(encoding="utf-8-sig"))


def anticipated_move_fields(
    *,
    direction: Any,
    spot: Any,
    outcome_level: Any,
    outcome_definition: Any,
    timeframe: Any,
    duration: Optional[Mapping[str, Any]],
    vol_annual: Any,
    contract: Optional[Mapping[str, Any]],
    governed_window_sessions: Any,
    earnings: Optional[Mapping[str, Any]] = None,
    trade_side_event: bool = True,
    invalidation_level: Any = None,
    rate: Any = None,
    rate_basis: Any = None,
    dividend_yield: Any = None,
    dividend_basis: Any = None,
) -> Dict[str, Any]:
    constants = _constants()
    cfg = constants["anticipated_move"]
    econ = constants["contract_economics"]
    out: Dict[str, Any] = {field: None for field in ANTICIPATED_MOVE_FIELDS}
    out.update(anticipated_authority="DISPLAY_ONLY", anticipated_version=cfg["version"],
               anticipated_pays_state="NOT_COMPUTED")
    side = str(direction or "").upper()
    if side not in {"CALL", "PUT"}:
        out["anticipated_move_state"] = "NOT_APPLICABLE_NON_DIRECTIONAL"
        return out
    sign = 1.0 if side == "CALL" else -1.0
    if not trade_side_event:
        # Real-data finding (3 Oct 2026): volatility reach is symmetric and is not a directional expectation.
        # With no behavioural event on the trade's side there is no anticipated move - stated, not invented.
        out["anticipated_move_state"] = "NO_TRADE_SIDE_EVENT"
        return out
    s0 = _num(spot)
    if s0 is None or s0 <= 0:
        out["anticipated_move_state"] = "UNESTIMATED_NO_SPOT"
        return out

    # Time (§4): duration evidence in own-timeframe bars -> sessions.
    dur = duration or {}
    per_bar = _num((cfg["sessions_per_bar"]).get(str(timeframe or "")))
    q50, q80 = _num(dur.get("q50_bars")), _num(dur.get("q80_bars"))
    estimated = str(dur.get("status") or "") in _ESTIMATED and per_bar is not None and q50 is not None and q80 is not None
    window = _num(governed_window_sessions)
    out.update(anticipated_evidence_n=dur.get("n"), anticipated_evidence_status=dur.get("status") or "UNESTIMATED")
    if estimated:
        s50, s80 = max(1, round(q50 * per_bar)), max(1, round(q80 * per_bar))
        out.update(anticipated_sessions_q50=s50, anticipated_sessions_q80=s80, anticipated_hold_sessions=s50,
                   anticipated_time_basis=f"DURATION_EVIDENCE:{timeframe}:{dur.get('test')}:n={dur.get('n')}",
                   anticipated_p_outcome_by_limit=_num(dur.get("p_event")),
                   anticipated_p_invalidation_by_limit=_num(dur.get("p_invalidation")))
        reach_sessions = s80
    else:
        out["anticipated_time_basis"] = "GOVERNED_WINDOW_NO_DURATION_EVIDENCE"
        reach_sessions = int(window) if window else None

    # Magnitude (§3).
    structural = _num(outcome_level)
    if structural is not None and sign * (structural - s0) <= 0:
        structural = None                                   # a level on the wrong side is not a target
    out.update(anticipated_structural_level=structural,
               anticipated_structural_definition=(outcome_definition or None) if structural is not None else None)
    vol = _num(vol_annual)
    k = float(econ["sigma_multiple"])

    def reach_by(sessions: Any) -> Optional[float]:
        if vol is None or vol <= 0 or not sessions:
            return None
        return round(s0 * (1.0 + sign * k * vol * math.sqrt(float(sessions) / 252.0)), 4)

    def level_by(sessions: Any) -> Optional[float]:
        """Fix B (ACK 5 Oct 2026): the level reachable by that time - structural, capped at that time's reach."""
        cap = reach_by(sessions)
        if structural is not None and cap is not None:
            return round(structural if abs(structural - s0) <= abs(cap - s0) else cap, 4)
        return cap if cap is not None else (round(structural, 4) if structural is not None else None)

    out["anticipated_reachable_level"] = reach_by(reach_sessions)
    reach = out["anticipated_reachable_level"]
    if structural is not None and reach is not None:
        nearer = structural if abs(structural - s0) <= abs(reach - s0) else reach
        out["anticipated_level"] = round(nearer, 4)
        out["anticipated_level_basis"] = "STRUCTURAL" if nearer == structural else "VOLATILITY_CAPPED"
    elif reach is not None:
        out.update(anticipated_level=reach, anticipated_level_basis="VOLATILITY_ONLY")
    elif structural is not None:
        out.update(anticipated_level=round(structural, 4), anticipated_level_basis="STRUCTURAL_REACH_UNKNOWN")
    if out["anticipated_level"] is None:
        out["anticipated_move_state"] = "UNESTIMATED_NO_LEVEL"
        return out
    level = out["anticipated_level"]
    out["anticipated_level_q50"] = level_by(out["anticipated_sessions_q50"] or reach_sessions)
    out["anticipated_move_pct"] = round(sign * (level - s0) / s0 * 100.0, 4)
    out["anticipated_move_state"] = "ESTIMATED" if estimated else "ESTIMATED_TIME_UNESTIMATED"

    # Payoff (§5).
    c = contract or {}
    strike, ask, iv, bid = _num(c.get("strike")), _num(c.get("ask")), _num(c.get("iv")), _num(c.get("bid"))
    if bid is not None and (bid < 0 or (ask is not None and bid > ask)):
        bid = None                                          # an inconsistent quote is not a spread
    expiry, as_of = _date(c.get("expiry")), _date(c.get("as_of"))
    if strike is None or ask is None or ask <= 0:
        return out
    breakeven = strike + ask if side == "CALL" else strike - ask
    be_move = sign * (breakeven - s0) / s0 * 100.0
    out["anticipated_breakeven_move_pct"] = round(be_move, 4)
    if be_move > 0:
        out["anticipated_move_coverage"] = round(out["anticipated_move_pct"] / be_move, 4)
    if iv is None or iv <= 0 or expiry is None or as_of is None:
        return out
    days_to_expiry = (expiry - as_of).days
    per_session = float(cfg["calendar_days_per_session"])

    contract_sessions = days_to_expiry / per_session
    rate_used, rate_label = resolve_rate(rate, rate_basis)
    q_used, q_label = resolve_dividend(dividend_yield, dividend_basis)
    out.update(valuation_rate_annual=rate_used, valuation_rate_basis=rate_label,
               valuation_dividend_yield_annual=q_used, valuation_dividend_basis=q_label,
               valuation_cost_basis=cost_basis(bid), valuation_version=valuation_policy()["version"],
               valuation_entry_cost_usd_per_share=round(entry_cost_usd_per_share(ask), 4))

    def net_return(sessions: Optional[int], at: Optional[float], vol_used: float) -> Optional[float]:
        # Real-data finding (3 Oct 2026): never value the move at a time the contract does not live to.
        if not sessions or sessions > contract_sessions or at is None:
            return None
        years = max(days_to_expiry - sessions * per_session, 0.0) / 365.0
        priced = scenario_value({**c, "strike": strike}, side, at, years, vol_used, rate=rate_used,
                                dividend_yield=q_used)
        out["valuation_model"] = priced["model"]
        return return_on_premium(priced["value"], bid=bid, ask=ask)

    def multiple(sessions: Optional[int], vol_used: float) -> Optional[float]:
        # Fix B (ACK 5 Oct 2026): value at the level reachable by that time, never a later horizon's reach.
        net = net_return(sessions, level_by(sessions) if sessions else None, vol_used)
        return None if net is None else round(1.0 + net, 4)

    t50 = out["anticipated_sessions_q50"] or reach_sessions
    t80 = out["anticipated_sessions_q80"] or reach_sessions
    out["anticipated_time_fit"] = ("CONTRACT_EXPIRES_BEFORE_MEDIAN_TIME" if t50 and t50 > contract_sessions
                                   else "CONTRACT_EXPIRES_BEFORE_Q80" if t80 and t80 > contract_sessions
                                   else "CONTRACT_OUTLASTS_Q80")
    out["anticipated_value_multiple_q50"] = multiple(t50, iv)
    out["anticipated_value_multiple_q80"] = multiple(t80, iv)
    low = float(min(econ.get("iv_stress") or [1.0]))
    stress = [f"q80 path ({t80} sessions)"]
    e = earnings or {}
    to_event = _num(e.get("earnings_sessions_to_event"))
    if str(e.get("earnings_state") or "").upper() == "SCHEDULED" and to_event is not None and t80 and to_event <= t80:
        out["anticipated_value_multiple_earnings_stress"] = multiple(t80, iv * low)
        stress.append(f"earnings in {int(to_event)} sessions: IV x {low:g} (governed iv_stress) at q80")
    out["anticipated_stress_basis"] = "; ".join(stress)
    # Output-trust item 4: the labelled scenarios at the median time, return on premium after spread and fees.
    inval = _num(invalidation_level)
    if inval is not None and sign * (s0 - inval) <= 0:
        inval = None                                        # an invalidation on the wrong side is not a scenario
    target_at = level_by(t50) if t50 else None
    out.update(scenario_exit_sessions=t50, scenario_target_exit_spot=target_at, scenario_invalidation_exit_spot=inval,
               scenario_iv_basis=f"IV_HELD at contract IV {iv:.4f}",
               scenario_target_return_on_premium=net_return(t50, target_at, iv),
               scenario_invalidation_return_on_premium=net_return(t50, inval, iv),
               scenario_stall_return_on_premium=net_return(t50, s0, iv))
    if str(e.get("earnings_state") or "").upper() == "SCHEDULED" and to_event is not None and t50 and to_event <= t50:
        out["scenario_target_earnings_iv_return_on_premium"] = net_return(t50, target_at, iv * low)
        out["scenario_iv_basis"] += f"; earnings case IV x {low:g} (governed iv_stress)"
    # D-B (ACK 3 Oct 2026, amended): does the move pay = contract value at the median anticipated time vs premium.
    q50_multiple = out["anticipated_value_multiple_q50"]
    if out["anticipated_level_basis"] == "VOLATILITY_ONLY":
        # Fix B: with no structural target on the trade side the level is a volatility reach, not an expectation.
        out["anticipated_pays_state"] = "NOT_ASSESSED_VOLATILITY_ONLY"
    elif q50_multiple is not None:
        out["anticipated_pays_state"] = "PAYS" if q50_multiple >= 1.0 else "DOES_NOT_PAY_AT_ANTICIPATED_TIME"
    return out


def evidence_runway(*, timeframe: Any, alignment: Any, status: Any, q50_bars: Any, q80_bars: Any,
                    n: Any = None) -> Dict[str, Any]:
    """Contract runway from the level evidence (ACK 3 Oct 2026 step 4b; extended 4 Oct 2026 to weekly/monthly).

    Trade-side events with level evidence on a tested timeframe (1d / 1w / 1mo) size the runway from q80
    (sessions). Untested timeframes and events without evidence get no evidence runway; the basis says why. The median
    move time is published for any timeframe (display). A runway is a floor, never a ceiling.
    """
    per_bar = _num(_constants()["anticipated_move"]["sessions_per_bar"].get(str(timeframe or "")))
    q50, q80 = _num(q50_bars), _num(q80_bars)
    estimated = str(status or "") in _ESTIMATED and per_bar is not None and q50 is not None and q80 is not None
    aligned = str(alignment or "").upper() == "ALIGNED"
    out = {"evidence_runway_sessions": None, "evidence_move_sessions": None, "evidence_runway_basis": None}
    if aligned and estimated:
        out["evidence_move_sessions"] = max(1, round(q50 * per_bar))
    if not aligned:
        out["evidence_runway_basis"] = "GOVERNED_WINDOW_NO_TRADE_SIDE_EVENT"
    elif not estimated:
        out["evidence_runway_basis"] = "GOVERNED_WINDOW_NO_LEVEL_EVIDENCE"
    elif str(timeframe) not in _constants()["anticipated_move"]["runway_tested_timeframes"]:
        out["evidence_runway_basis"] = f"NO_TESTED_EVIDENCE_TIMEFRAME:{timeframe}"
    else:
        # ACK 4 Oct 2026: daily, weekly and monthly events size the runway from their own q80 (held-out timing).
        out["evidence_runway_sessions"] = max(1, round(q80 * per_bar))
        out["evidence_runway_basis"] = f"DURATION_EVIDENCE_Q80:{timeframe}:n={n}"
    return out


def runway_fallback(*, evidence: Optional[Mapping[str, Any]], timeframe: Any, signal_type: Any, direction: Any,
                    state: Any, outcome_level: Any, spot: Any, vol_annual: Any, test: Any = None) -> Dict[str, Any]:
    """Contract runway when the governing setup has no evidence of its own (ACK 7 Oct 2026: "build C with B fallback").

    C - pooled evidence: the longest q80 of the setup's broader group (domain.structure_behaviour.duration), in XNYS
        sessions, on a tested timeframe.
    B - volatility, calibrated: the sessions a k-sigma move needs to reach the setup's level at current volatility,
        t = 252 x (|level / spot - 1| / (k x vol))^2 (k = contract_economics.sigma_multiple), x the timeframe's q80
        multiplier learned on recorded outcomes (config runway_volatility_calibration). Not the setup's own evidence;
        labelled so.
    Neither (no level on the trade side, or no volatility): no estimate - never the fixed 20-session window.
    A runway is a floor, never a ceiling.
    """
    from domain.structure_behaviour.duration import LEVEL_TESTS, pooled_level_q80
    constants = _constants()
    cfg = constants["anticipated_move"]
    side = {"CALL": "BULL", "PUT": "BEAR", "BULL": "BULL", "BEAR": "BEAR"}.get(str(direction or "").upper())
    level_test = test or LEVEL_TESTS.get(str(state or "").upper())
    if str(timeframe or "") in cfg["runway_tested_timeframes"] and side and level_test:
        q80, basis, _n = pooled_level_q80(evidence, timeframe=timeframe, signal_type=signal_type, direction=side,
                                          test=level_test)
        per_bar = _num(cfg["sessions_per_bar"].get(str(timeframe)))
        if q80 is not None and per_bar is not None:
            return {"runway_sessions": max(1, round(float(q80) * per_bar)), "runway_basis": basis,
                    "runway_is_evidence": True}
    level, s0, vol = _num(outcome_level), _num(spot), _num(vol_annual)
    k = _num(constants["contract_economics"]["sigma_multiple"])
    # Calibrated B (ACK 7 Oct 2026): the k-sigma time is a fast-move time (it covered 30% of real level hits); x the
    # timeframe's q80 multiplier learned on recorded outcomes it is a q80 runway (83-86% on the held-out panel).
    # A timeframe without a calibrated multiplier gets no B estimate.
    multiplier = _num((constants.get("runway_volatility_calibration") or {}).get("q80_multiplier", {})
                      .get(str(timeframe or "")))
    if side and level is not None and s0 and s0 > 0 and vol and vol > 0 and k and k > 0 and multiplier:
        move = (level / s0 - 1.0) * (1.0 if side == "BULL" else -1.0)
        if move > 0:
            fast = max(1, math.ceil(252.0 * (move / (k * vol)) ** 2))
            return {"runway_sessions": math.ceil(fast * multiplier),
                    "runway_basis": (f"VOLATILITY_TIME_TO_LEVEL_CALIBRATED_Q80:k={k:g}|vol={vol:.4f}|move={move:.4f}"
                                     f"|x{multiplier:g}"),
                    "runway_is_evidence": False}
    return {"runway_sessions": None, "runway_basis": "NO_RUNWAY_ESTIMATE", "runway_is_evidence": False}
