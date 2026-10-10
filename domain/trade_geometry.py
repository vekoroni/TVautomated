"""Trade geometry from the planned executable entry (output-trust item 3, D2-3; ACK decision 1, 9 Oct 2026).

Root cause it answers: the governing setup's failure level is often a weekly/monthly campaign level (lane A median
8.8 daily ATR away) while the target is the next outcome level (4.7 ATR); that reward/risk was never shown or tested.

One owner for: the planned entry (the session price for a ready thesis, the thesis trigger for a waiting one), reward
and risk in price and daily ATR(14), the early-warning risk view, the break-even hit rate risk / (risk + reward), and
the setup's measured hit rate (the lower panel, its n and a Wilson interval) set against it. The governing setup's own
target and invalidation are used as given - never moved. Justification is about the underlying levels only; the option
is valued separately (D5-1).

States: JUSTIFIED, GEOMETRY_NOT_JUSTIFIED (measured below break-even), INVALID_GEOMETRY (order broken, risk or reward
not positive - never an infinite ratio), NOT_MEASURED (no measured hit rate: labelled, not blocked), NOT_ASSESSABLE
(side, entry, target, invalidation or ATR missing). The two failing states cannot be GO (trigger_layer); every row
stays visible and ranked. Note: the hit rates were measured from each setup's activation/detection, not from this
entry; the reason says so.
"""
from __future__ import annotations

import math
from statistics import NormalDist
from typing import Any, Dict, Mapping, Optional

from domain.structure_behaviour.trade_lane import load_lanes

TRADE_GEOMETRY_FIELDS = (
    "geometry_justification", "geometry_reason", "geometry_entry_basis", "geometry_entry_price",
    "geometry_target_price", "geometry_invalidation_price", "geometry_early_warning_price", "geometry_atr_daily",
    "geometry_reward_price", "geometry_risk_price", "geometry_reward_atr", "geometry_risk_atr",
    "geometry_early_warning_risk_atr", "geometry_breakeven_hit_rate", "geometry_measured_hit_rate",
    "geometry_hit_panel", "geometry_hit_n", "geometry_hit_low", "geometry_hit_high",
)
NOT_GO_STATES = frozenset({"GEOMETRY_NOT_JUSTIFIED", "INVALID_GEOMETRY"})
_SIDES = {"BULL": 1, "CALL": 1, "BEAR": -1, "PUT": -1}


def _num(value: Any) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _wilson(rate: float, n: int, confidence: float) -> tuple[float, float]:
    z = NormalDist().inv_cdf(0.5 + confidence / 2.0)
    denom = 1.0 + z * z / n
    centre = (rate + z * z / (2 * n)) / denom
    half = z * math.sqrt(rate * (1 - rate) / n + z * z / (4 * n * n)) / denom
    return round(centre - half, 4), round(centre + half, 4)


def assess_trade_geometry(*, side: Any, readiness: Any, session_price: Any, trigger_level: Any, target: Any,
                          invalidation: Any, early_warning: Any, atr_daily: Any, lane: Mapping[str, Any],
                          policy: Mapping[str, Any] | None = None) -> Dict[str, Any]:
    out: Dict[str, Any] = {f: None for f in TRADE_GEOMETRY_FIELDS}
    sign = _SIDES.get(str(side or "").strip().upper())
    waiting = str(readiness or "").strip().upper() == "WAIT_TRIGGER"
    out["geometry_entry_basis"] = "THESIS_TRIGGER" if waiting else "SESSION_PRICE"
    entry = _num(trigger_level) if waiting else _num(session_price)
    tgt, inv, warn, atr = _num(target), _num(invalidation), _num(early_warning), _num(atr_daily)
    out.update(geometry_entry_price=entry, geometry_target_price=tgt, geometry_invalidation_price=inv,
               geometry_early_warning_price=warn, geometry_atr_daily=atr)
    missing = [name for name, v in (("side", sign), ("entry", entry), ("target", tgt), ("invalidation", inv),
                                    ("atr", atr if atr and atr > 0 else None)) if v is None]
    if missing:
        out.update(geometry_justification="NOT_ASSESSABLE", geometry_reason=f"missing {', '.join(missing)}")
        return out
    reward, risk = round((tgt - entry) * sign, 4), round((entry - inv) * sign, 4)
    out.update(geometry_reward_price=reward, geometry_risk_price=risk,
               geometry_reward_atr=round(reward / atr, 2), geometry_risk_atr=round(risk / atr, 2))
    if warn is not None:
        out["geometry_early_warning_risk_atr"] = round((entry - warn) * sign / atr, 2)
    if reward <= 0 or risk <= 0:
        out.update(geometry_justification="INVALID_GEOMETRY",
                   geometry_reason=f"order broken from the {out['geometry_entry_basis'].lower()}: "
                                   f"reward {reward}, risk {risk}")
        return out
    breakeven = round(risk / (risk + reward), 4)
    out["geometry_breakeven_hit_rate"] = breakeven
    panels = [(p, _num(lane.get(f"trade_lane_hit_{k}")), _num(lane.get(f"trade_lane_hit_n_{k}")))
              for p, k in (("ORIGINAL", "original"), ("HOLDOUT", "holdout"))]
    panels = [(p, h, n) for p, h, n in panels if h is not None]
    if not panels:
        out.update(geometry_justification="NOT_MEASURED",
                   geometry_reason="no measured hit rate for this setup (lane C); break-even shown for judgement")
        return out
    policy = policy or load_lanes()["geometry_justification"]
    panel, hit, n = min(panels, key=lambda x: x[1])
    out.update(geometry_measured_hit_rate=hit, geometry_hit_panel=panel,
               geometry_hit_n=int(n) if n is not None else None)
    inside = ""
    if n:
        low, high = _wilson(hit, int(n), float(policy["interval_confidence"]))
        out.update(geometry_hit_low=low, geometry_hit_high=high)
        inside = "; break-even inside the interval" if low <= breakeven <= high else ""
    state = "JUSTIFIED" if hit >= breakeven else "GEOMETRY_NOT_JUSTIFIED"
    out.update(geometry_justification=state,
               geometry_reason=f"measured {hit:.1%} ({panel.lower()}) vs break-even {breakeven:.1%}{inside}; "
                               "hit rate measured from the setup's activation/detection, not this entry")
    return out
