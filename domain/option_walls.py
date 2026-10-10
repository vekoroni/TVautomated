"""Option walls: concentration, separated from dealer influence and observed price response (output-trust item 7).

Design: Enhancements/phase7/ITEM7_WALLS_DESIGN_20261010.md (ACK's call-wall review, 10 Oct 2026). Root cause it
replaces: compute_oi_walls took the largest raw open interest anywhere in a 1-110 day chain (SMCI 8 Oct: a $3 Jan-2027
put, OI 58,551, gamma 0.0001, with spot 42.77).

Definition: a wall candidate is a material concentration of gamma-weighted open interest within one instrument, one
expiry basket and a relevant price region. Its support or resistance role is unverified until price behaviour
supports it. Method GAMMA_OI_CONCENTRATION_V1 (our own; never presented as a provider's wall).

Three conclusions are kept apart: options concentration (wall_*), estimated dealer influence (gamma flip, labelled
sign assumption) and observed price response (wall_*_price_status). Display and context only in this build; which
readers may use a wall as a price level is ACK's decision (design section 8).
"""
from __future__ import annotations

import json
import math
from datetime import date, timedelta
from typing import Any, Dict, List, Mapping, Optional

import pandas as pd

from canonical_data.session_clock import advance_xnys_sessions, is_xnys_session, xnys_sessions_between

METHOD = "GAMMA_OI_CONCENTRATION_V1"
SIDES = (("call", "C"), ("put", "P"))
BASKET_PREFIX = {"THROUGH_EXIT": "hold", "AFTER_EXIT": "post"}
WALL_FIELDS = (
    "wall_method", "wall_instrument", "wall_spot_used", "wall_chain_asof_utc", "wall_oi_clearing_date",
    "wall_multiplier_basis", "wall_excluded_contracts", "wall_trade_session", "wall_exit_date", "wall_cutoff_date",
    "wall_dealer_sign", "wall_price_basis", "wall_map_json",
    *[f"wall_{b}_{s}_{k}" for b in ("hold", "post") for s in ("call", "put")
      for k in ("peak", "low", "high", "share", "state", "price_status", "price_note")],
    "gamma_flip_confidence_state", "dealer_sign_assumption",
    "wall_hold_call_level_confirmed", "wall_hold_put_level_confirmed",
)
# Price evidence that confirms the zone's role on its side (call zones above price act as resistance, put zones below
# as support): repeated rejection, or a crossing whose retest held with follow-through (role reversed and confirmed).
CONFIRMED_LEVEL_STATUSES = {"call": {"OBSERVED_RESISTANCE", "CONTINUATION_SUPPORTED"},
                            "put": {"OBSERVED_SUPPORT", "CONTINUATION_SUPPORTED"}}
GOVERNED_WALL_FIELDS = ("call_wall", "put_wall", "call_wall_state", "put_wall_state", "call_wall_level_confirmed",
                        "put_wall_level_confirmed", "wall_basis", "legacy_oi_call_wall", "legacy_oi_put_wall",
                        "legacy_oi_call_wall_state", "legacy_oi_put_wall_state")


def governed_walls(assessment: Mapping[str, Any], legacy: Mapping[str, Any]) -> Dict[str, Any]:
    """Item 7 readers (ACK 10 Oct 2026, design section 8): call_wall / put_wall become the hold basket's qualified
    zone peak (missing, with its state, when none qualifies); the raw-OI walls stay under legacy_oi_* names. max pain
    and the raw per-side OI maxima are unchanged legacy context."""
    out = dict(legacy or {})
    for side in ("call", "put"):
        out[f"legacy_oi_{side}_wall"] = (legacy or {}).get(f"{side}_wall")
        out[f"legacy_oi_{side}_wall_state"] = (legacy or {}).get(f"{side}_wall_state")
        out[f"{side}_wall"] = assessment.get(f"wall_hold_{side}_peak")
        out[f"{side}_wall_state"] = assessment.get(f"wall_hold_{side}_state") or "NOT_ASSESSED"
        out[f"{side}_wall_level_confirmed"] = bool(assessment.get(f"wall_hold_{side}_level_confirmed"))
    out["wall_basis"] = f"{assessment.get('wall_method') or METHOD}:THROUGH_EXIT"
    return out


def level_wall(row: Mapping[str, Any], side: str) -> Optional[float]:
    """A wall a reader may use as a price level: only when price confirmed its role. Rows from before item 7 (no
    wall_method) keep their legacy reading."""
    value = _num(row.get(f"{side}_wall"))
    if not row.get("wall_method"):
        return value
    confirmed = row.get(f"{side}_wall_level_confirmed")
    confirmed = confirmed is True or str(confirmed).strip().upper() in {"TRUE", "1", "YES"}
    return value if confirmed else None


def _policy(overrides: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    from pathlib import Path
    path = Path(__file__).resolve().parents[1] / "config" / "governed_constants_v1.json"
    policy = dict(json.loads(path.read_text(encoding="utf-8-sig"))["option_walls"])
    policy.update(overrides or {})
    return policy


def _num(value: Any) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _date(value: Any) -> Optional[date]:
    try:
        return pd.Timestamp(value).date()
    except (TypeError, ValueError):
        return None


def gamma_flip_confidence_state(flip: Any, confidence: Any, policy: Optional[Mapping[str, Any]] = None) -> str:
    """D5-3: a flip below the governed confidence is shown as indicative only, never used as a level."""
    if _num(flip) is None:
        return "NO_FLIP"
    conf = _num(confidence) or 0.0
    return "CONFIDENT" if conf >= float((policy or _policy())["gamma_flip_min_confidence"]) else "LOW_CONFIDENCE"


# ------------------------------------------------------------------ observed price response
def _atr(bars: pd.DataFrame, n: int = 14) -> Optional[float]:
    if bars is None or len(bars) < 2:
        return None
    prev = bars["close"].shift(1)
    tr = pd.concat([bars["high"] - bars["low"], (bars["high"] - prev).abs(), (bars["low"] - prev).abs()], axis=1).max(axis=1)
    value = tr.tail(n).mean()
    return float(value) if value == value and value > 0 else None


def price_response_status(bars: Optional[pd.DataFrame], *, low: float, high: float,
                          policy: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    """How price behaved around a zone, from completed daily bars (the "Soul of the Chart" questions).

    Statuses: UNTESTED_CONCENTRATION, SINGLE_REJECTION, OBSERVED_SUPPORT / OBSERVED_RESISTANCE (repeated rejection,
    with the trend of rejection strength), BREACHED_ACCEPTANCE_ASSESSING (crossed once; no retest, or a retest without
    follow-through yet), CONTINUATION_SUPPORTED (crossed once, retest held, then follow-through),
    FAILED_BREAK_ASSESSING (crossed beyond once and came back), CONTESTED_LEVEL (traded through 3+ times),
    AT_LEVEL (closing inside the zone now). Crossing a level is never read as the positions being closed.
    """
    pol = policy or _policy()
    if bars is None or len(bars) < 5:
        return {"status": "NO_PRICE_HISTORY", "rejections": 0, "note": "no completed daily bars"}
    b = bars.tail(int(pol["price_lookback_sessions"])).reset_index(drop=True)
    atr = _atr(b) or 0.0
    tol = float(pol["touch_tolerance_atr"]) * atr
    lo, hi = float(low) - tol, float(high) + tol

    def side(close: float) -> str:
        return "ABOVE" if close > hi else "BELOW" if close < lo else "INSIDE"

    sides = [side(c) for c in b["close"]]
    now = sides[-1]
    if now == "INSIDE":
        return {"status": "AT_LEVEL", "rejections": 0, "note": "closing inside the zone now"}
    outside = [s for s in sides if s != "INSIDE"]
    origin = outside[0]
    touches = [i for i in range(len(b)) if b.at[i, "high"] >= lo and b.at[i, "low"] <= hi]
    vol_med = float(b["volume"].tail(20).median() or 0)
    absorption = any(b.at[i, "volume"] >= 1.5 * vol_med and abs(b.at[i, "close"] - b.at[i, "open"]) <= 0.3 * atr
                     for i in touches) if vol_med > 0 and atr > 0 else False
    flag = " · absorption possible (high volume, little progress)" if absorption else ""
    # Crossings between the two sides (inside-zone closes ignored). Repeated crossing is contested ground, not
    # support or resistance evidence (live 8 Oct acceptance: near-spot levels are often traded through).
    crossings = sum(1 for x, y in zip(outside, outside[1:]) if x != y)
    if crossings >= 3:
        return {"status": "CONTESTED_LEVEL", "rejections": 0,
                "note": f"traded through {crossings} times in {len(b)} sessions - no support or resistance evidence{flag}"}
    if crossings == 1:
        cross = max(i for i, s in enumerate(sides) if s not in (now, "INSIDE"))
        retests = [i for i in touches if i > cross and sides[i] == now]
        if retests:
            last = retests[-1]
            sign = 1 if now == "ABOVE" else -1
            if (b.at[len(b) - 1, "close"] - b.at[last, "close"]) * sign > 0 and len(b) - 1 > last:
                return {"status": "CONTINUATION_SUPPORTED", "rejections": len(retests),
                        "note": f"crossed to the {now.lower()} side; retest held {len(retests)}x, then follow-through{flag}"}
            return {"status": "BREACHED_ACCEPTANCE_ASSESSING", "rejections": len(retests),
                    "note": f"crossed to the {now.lower()} side; retest held, follow-through pending{flag}"}
        return {"status": "BREACHED_ACCEPTANCE_ASSESSING", "rejections": 0,
                "note": f"crossed to the {now.lower()} side; no retest yet{flag}"}
    if crossings == 2:
        return {"status": "FAILED_BREAK_ASSESSING", "rejections": 0,
                "note": f"closed beyond the zone once, then back on the {now.lower()} side{flag}"}
    rejections = [i for i in touches if sides[i] == now]
    if not rejections:
        return {"status": "UNTESTED_CONCENTRATION", "rejections": 0, "note": f"not touched in {len(b)} sessions"}
    role = "OBSERVED_RESISTANCE" if now == "BELOW" else "OBSERVED_SUPPORT"
    if len(rejections) == 1:
        return {"status": "SINGLE_REJECTION", "rejections": 1, "note": f"one rejection ({role.split('_')[1].lower()} "
                                                                         f"not yet repeated){flag}"}
    depth = [(lo - b.at[i, "close"]) if now == "BELOW" else (b.at[i, "close"] - hi) for i in rejections]
    trend = ("weakening" if depth[-1] < 0.7 * depth[0] else "strengthening" if depth[-1] > 1.3 * depth[0]
             else "steady")
    return {"status": role, "rejections": len(rejections), "note": f"{len(rejections)} rejections, {trend}{flag}"}


# ------------------------------------------------------------------ concentration
def _zones(conc: pd.Series, candidates: List[float], total: float, pol: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """Peak-led zones: a peak strike grows to adjacent candidate strikes holding >= a governed share of the peak."""
    strikes = sorted(candidates)
    used: set = set()
    zones: List[Dict[str, Any]] = []
    while len(zones) < int(pol["zones_per_side"]):
        free = [k for k in strikes if k not in used and conc.get(k, 0.0) > 0]
        if not free:
            break
        peak = max(free, key=lambda k: conc[k])
        idx = strikes.index(peak)
        lo_i = hi_i = idx
        floor = float(pol["zone_neighbour_fraction"]) * conc[peak]
        while lo_i - 1 >= 0 and strikes[lo_i - 1] not in used and conc.get(strikes[lo_i - 1], 0.0) >= floor:
            lo_i -= 1
        while hi_i + 1 < len(strikes) and strikes[hi_i + 1] not in used and conc.get(strikes[hi_i + 1], 0.0) >= floor:
            hi_i += 1
        members = strikes[lo_i:hi_i + 1]
        used.update(members)
        value = float(sum(conc.get(k, 0.0) for k in members))
        zones.append({"peak": float(peak), "low": float(members[0]), "high": float(members[-1]),
                      "share": round(value / total, 4) if total > 0 else 0.0,
                      "dollar_gamma_1pct": round(value, 2)})
    # the most significant concentration first: rank zones by their share of the side's basket
    return sorted(zones, key=lambda z: z["share"], reverse=True)


def assess_option_walls(chain: pd.DataFrame, *, ticker: str, spot: Any, trade_session: date, hold_sessions: Any,
                        atm_iv: Any = None, bars: Optional[pd.DataFrame] = None, chain_asof_utc: Any = None,
                        policy_overrides: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    pol = _policy(policy_overrides)
    out: Dict[str, Any] = {f: None for f in WALL_FIELDS}
    root = str(ticker or "").strip().upper()
    s0 = _num(spot)
    out.update(wall_method=METHOD, wall_instrument=root, wall_spot_used=s0, wall_chain_asof_utc=chain_asof_utc,
               wall_dealer_sign="NOT_ESTIMATED_CONCENTRATION_IS_UNSIGNED",
               dealer_sign_assumption="ASSUMED_CUSTOMER_LONG_PUTS_SHORT_CALLS_UNVERIFIED",
               wall_trade_session=trade_session.isoformat() if trade_session else None)
    df = chain.copy() if chain is not None else pd.DataFrame()
    if df.empty or s0 is None or s0 <= 0:
        reason = "NO_CHAIN_DATA" if df.empty else "SPOT_UNAVAILABLE"
        for b in BASKET_PREFIX.values():
            for s, _ in SIDES:
                out[f"wall_{b}_{s}_state"] = reason
        out["wall_map_json"] = json.dumps({"state": reason})
        return out
    # 1. instrument and contract validity
    own = df["underlying"].astype(str).str.upper().eq(root) if "underlying" in df else pd.Series(True, index=df.index)
    out["wall_excluded_contracts"] = int((~own).sum())
    df = df[own].copy()
    mult = pd.to_numeric(df.get("contract_multiplier"), errors="coerce") if "contract_multiplier" in df else None
    if mult is None or mult.isna().all():
        df["_m"] = 100.0
        out["wall_multiplier_basis"] = "MULTIPLIER_ASSUMED_100_NOT_PROVIDED"
    else:
        df["_m"] = mult.fillna(100.0)
        out["wall_multiplier_basis"] = "PROVIDER_MULTIPLIER" + ("_SOME_ASSUMED_100" if mult.isna().any() else "")
    # Open interest is published after clearing: a chain observed on session D carries the positions of the session
    # before D (never today's volume). The chain's session is its as-of date, else the session before the trade.
    try:
        from canonical_data.session_clock import previous_xnys_session
        chain_session = _date(str(chain_asof_utc)[:10]) if chain_asof_utc else previous_xnys_session(trade_session)
        out["wall_oi_clearing_date"] = previous_xnys_session(chain_session).isoformat()
    except Exception:                                             # noqa: BLE001 - stated, never invented
        out["wall_oi_clearing_date"] = None
    # 2. baskets by actual dates
    df["_exp"] = df["expiration_date"].map(_date)
    hold = _num(hold_sessions)
    exit_date = advance_xnys_sessions(trade_session, int(hold)) if hold and hold > 0 and is_xnys_session(trade_session) else None
    cutoff = trade_session + timedelta(days=int(pol["longer_cutoff_calendar_days"]))
    out.update(wall_exit_date=exit_date.isoformat() if exit_date else None, wall_cutoff_date=cutoff.isoformat())
    masks = {"TODAY": df["_exp"].eq(trade_session)}
    if exit_date:
        masks["THROUGH_EXIT"] = (df["_exp"] > trade_session) & (df["_exp"] <= exit_date)
        masks["AFTER_EXIT"] = (df["_exp"] > exit_date) & (df["_exp"] <= cutoff)
    else:
        masks["AFTER_EXIT"] = (df["_exp"] > trade_session) & (df["_exp"] <= cutoff)
    masks["COMBINED"] = (df["_exp"] >= trade_session) & (df["_exp"] <= cutoff)
    # 3. measure: gamma x OI x multiplier, dollar gamma for a 1% move
    df["_conc"] = (pd.to_numeric(df["gamma"], errors="coerce").fillna(0.0)
                   * pd.to_numeric(df["open_interest"], errors="coerce").fillna(0.0) * df["_m"] * s0 * s0 * 0.01)
    iv = _num(atm_iv)
    if iv is None:
        near = df[(pd.to_numeric(df["strike"], errors="coerce") - s0).abs() <= 0.05 * s0]
        iv = _num(pd.to_numeric(near.get("implied_vol"), errors="coerce").median()) if not near.empty else None
    out["wall_price_basis"] = f"DAILY_BARS:{int(pol['price_lookback_sessions'])}_SESSIONS:TOL_{pol['touch_tolerance_atr']}_ATR"
    baskets: Dict[str, Any] = {}
    for name, mask in masks.items():
        sub = df[mask]
        end = max(sub["_exp"]) if not sub.empty else None
        sessions = max(xnys_sessions_between(trade_session, end), 1) if end else None
        band = (float(pol["relevance_k"]) * iv * math.sqrt(sessions / 252.0) * s0) if (iv and sessions) else None
        entry: Dict[str, Any] = {"expiries": sorted({d.isoformat() for d in sub["_exp"] if d}),
                                 "relevance_band": round(band, 4) if band else None}
        for side, right in SIDES:
            rows = sub[sub["right"].astype(str).str.upper().str[0] == right]
            conc = rows.groupby(pd.to_numeric(rows["strike"], errors="coerce"))["_conc"].sum()
            total = float(conc.sum())
            above = side == "call"
            cand = [float(k) for k in conc.index if (k > s0 if above else k < s0)
                    and (band is None or abs(k - s0) <= band)]
            zones = _zones(conc, cand, total, pol) if total > 0 else []
            entry[f"{side}_zones"] = zones
            entry[f"{side}_total_dollar_gamma_1pct"] = round(total, 2)
            if sub.empty:
                state, wall = "NO_EXPIRIES_IN_BASKET", None
            elif total <= 0:
                state, wall = "NO_GAMMA_OI", None
            elif not cand:
                state, wall = "NO_STRIKES_IN_RELEVANT_RANGE", None
            else:
                wall = next((z for z in zones if z["share"] >= float(pol["materiality_share_min"])), None)
                state = "QUALIFIED" if wall else "NO_QUALIFIED_WALL"
            entry[f"{side}_state"] = state
            entry[f"{side}_wall"] = wall
        baskets[name] = entry
    # 4. flat fields for the hold and post-exit baskets, with the observed price response
    for name, prefix in BASKET_PREFIX.items():
        entry = baskets.get(name)
        for side, _ in SIDES:
            key = f"wall_{prefix}_{side}_"
            if entry is None:
                out[key + "state"] = "NO_PLANNED_EXIT"
                continue
            wall = entry[f"{side}_wall"]
            out[key + "state"] = entry[f"{side}_state"]
            if wall:
                response = price_response_status(bars, low=wall["low"], high=wall["high"], policy=pol)
                wall["price_status"], wall["price_note"] = response["status"], response["note"]
                out.update({key + "peak": wall["peak"], key + "low": wall["low"], key + "high": wall["high"],
                            key + "share": wall["share"], key + "price_status": response["status"],
                            key + "price_note": response["note"]})
                if prefix == "hold":
                    out[key + "level_confirmed"] = response["status"] in CONFIRMED_LEVEL_STATUSES[side]
    out["wall_map_json"] = json.dumps({"method": METHOD, "spot": s0, "atm_iv_used": iv, "baskets": baskets},
                                      default=str)
    return out
