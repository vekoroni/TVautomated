"""The anticipated move: replaces stop-based R:R (ACK 3 Oct 2026; design AVS_ANTICIPATED_MOVE_DESIGN_20261003).

One owner, pure. Display only in this build step: no gate, score or rank reads these fields until the replay
validation (design §7) and ACK's D-C ranking switch.

- Magnitude (§3): the trade-side BEH-001 candidate's structural Outcome_Level, capped at the volatility-reachable
  level k*sigma*sqrt(t_q80/252) (D-D); no structural level -> volatility only. Nothing is derived from a stop.
- Time (§4): the candidate's duration evidence (q50/q80 own-timeframe bars -> sessions, governed table).
  Thin evidence -> hold UNESTIMATED; the reach uses the governed window, labelled (D-A a).
- Payoff (§5): coverage = anticipated move / breakeven move; value multiples from the repository's
  Black-Scholes valuer (r = q = 0, contract IV held). Stress (disclosed, not scored): the slower q80 path,
  and IV x governed iv_stress low when earnings fall inside q80.
- The invalidation is the thesis exit shown on the card; it is deliberately not an input.
- No behavioural event on the trade's side -> NO_TRADE_SIDE_EVENT: symmetric volatility is not an expectation.
"""
from __future__ import annotations

from datetime import date, datetime
import json
import math
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

from contracts.selected_contract_economics import _black_scholes_value

CONSTANTS_PATH = Path(__file__).resolve().parents[1] / "config" / "governed_constants_v1.json"
ANTICIPATED_MOVE_FIELDS = (
    "anticipated_move_state", "anticipated_level", "anticipated_level_basis", "anticipated_move_pct",
    "anticipated_structural_level", "anticipated_structural_definition", "anticipated_reachable_level",
    "anticipated_sessions_q50", "anticipated_sessions_q80", "anticipated_hold_sessions", "anticipated_time_basis",
    "anticipated_p_outcome_by_limit", "anticipated_p_invalidation_by_limit", "anticipated_evidence_n",
    "anticipated_evidence_status", "anticipated_breakeven_move_pct", "anticipated_move_coverage",
    "anticipated_value_multiple_q50", "anticipated_value_multiple_q80", "anticipated_value_multiple_earnings_stress",
    "anticipated_stress_basis", "anticipated_time_fit", "anticipated_pays_state", "anticipated_authority",
    "anticipated_version",
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
    if vol is not None and vol > 0 and reach_sessions:
        k = float(econ["sigma_multiple"])
        out["anticipated_reachable_level"] = round(s0 * (1.0 + sign * k * vol * math.sqrt(reach_sessions / 252.0)), 4)
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
    out["anticipated_move_pct"] = round(sign * (level - s0) / s0 * 100.0, 4)
    out["anticipated_move_state"] = "ESTIMATED" if estimated else "ESTIMATED_TIME_UNESTIMATED"

    # Payoff (§5).
    c = contract or {}
    strike, ask, iv = _num(c.get("strike")), _num(c.get("ask")), _num(c.get("iv"))
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

    def multiple(sessions: Optional[int], vol_used: float) -> Optional[float]:
        # Real-data finding (3 Oct 2026): never value the move at a time the contract does not live to.
        if not sessions or sessions > contract_sessions:
            return None
        years = max(days_to_expiry - sessions * per_session, 0.0) / 365.0
        value = _black_scholes_value(side, level, strike, years, vol_used)
        return None if value is None else round(value / ask, 4)

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
    # D-B (ACK 3 Oct 2026, amended): does the move pay = contract value at the median anticipated time vs premium.
    q50_multiple = out["anticipated_value_multiple_q50"]
    if q50_multiple is not None:
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
