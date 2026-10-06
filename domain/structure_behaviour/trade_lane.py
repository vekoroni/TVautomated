"""Trade lanes for BEH-001 setups (ACK, 4 Oct 2026).

A: trade now - the setup's timeframe, type and state reached the outcome level before invalidation at least
   half the time on both the original and the held-out panel.
B: early entry - a detected Spring / SOS->LPS / Buyer Absorption whose level is near (within 2 daily ATR) and
   whose invalidation is far (at least 2 ATR): 74% / 76% reach the level first (ACK: "reduce the number to
   1 in 3"); confirmed downstream only when the option's value multiple covers the failures (>= 1 / hit rate).
C: awaiting trigger / human judgement - any other live setup, including timeframes without tested evidence.
NO_LIVE_SETUP: nothing to trade or watch; Discovery drops the ticker for this run (it re-enters next run).
INTRADAY_ONLY_UNTESTED: live setups only on timeframes without tested evidence; dropped for the run (ACK 5 Oct 2026).
The table lives in config/beh001_lanes_v1.json with its evidence.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional

LANES_PATH = Path(__file__).resolve().parents[2] / "config" / "beh001_lanes_v1.json"
# Fields Discovery publishes per ticker and the book carries (with the intake labels set beside them).
TRADE_LANE_FIELDS = ("trade_lane", "trade_lane_basis", "trade_lane_setup", "trade_lane_hit_original",
                     "trade_lane_hit_holdout", "trade_lane_version", "trade_lane_required_multiple", "trade_lane_side",
                     "intake_flags", "price_band")
_ORDER = {"A": 0, "B": 1, "C": 2}


def load_lanes(path: Path | str | None = None) -> Mapping[str, Any]:
    table = json.loads(Path(path or LANES_PATH).read_text(encoding="utf-8"))
    if table.get("version") != "beh001_lanes_v1":
        raise ValueError("Unsupported lane table version")
    return table


def _match(entries: Iterable[Mapping], state: str, kind: str) -> Optional[Mapping]:
    return next((e for e in entries or [] if e["state"] == state and e["type"] == kind), None)


def _num(value: Any) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number else None


def _geometry(candidate: Mapping, price: Any, atr_daily: Any, rule: Mapping) -> Optional[bool]:
    """Level within the rule's ATR distance and invalidation at least its ATR distance away; None if unknown."""
    px, atr_, level, inval = (_num(price), _num(atr_daily), _num(candidate.get("Outcome_Level")),
                              _num(candidate.get("Invalidation_Level")))
    if None in (px, atr_, level, inval) or atr_ <= 0:
        return None
    return (abs(level - px) / atr_ < float(rule["max_level_distance_atr"])
            and abs(px - inval) / atr_ >= float(rule["min_invalidation_distance_atr"]))


def candidate_lane(candidate: Mapping, table: Mapping, price: Any = None,
                   atr_daily: Any = None) -> Optional[Dict[str, Any]]:
    """Lane of one setup, or None when it is not live."""
    state = str(candidate.get("Signal_State") or "").upper()
    if state not in table["live_states"]:
        return None
    tf, kind = str(candidate.get("Timeframe") or ""), str(candidate.get("Signal_Type") or "")
    hit = _match(table["lane_a_trade_now"].get(tf), state, kind)
    if hit:
        return {"lane": "A", "basis": "TRADE_NOW_MEASURED", "hit": hit["hit"]}
    lane_b = table["lane_b_early_entry"]
    hit = _match(lane_b.get(tf), state, kind)
    if hit:
        fits = _geometry(candidate, price, atr_daily, lane_b["geometry"])
        if fits:
            return {"lane": "B", "basis": "EARLY_ENTRY_MEASURED", "hit": hit["hit"]}
        basis = "EARLY_ENTRY_GEOMETRY_UNKNOWN" if fits is None else "EARLY_ENTRY_GEOMETRY_NOT_MET"
        return {"lane": "C", "basis": basis, "hit": None}
    basis = "NO_TESTED_EVIDENCE" if tf in table["untested_timeframes"] else "BELOW_LINE_OR_UNMEASURED"
    return {"lane": "C", "basis": basis, "hit": None}


_SIDES = {"BULL": "BULL", "CALL": "BULL", "BEAR": "BEAR", "PUT": "BEAR"}


def _side(value: Any) -> Optional[str]:
    return _SIDES.get(str(value or "").strip().upper())


def ticker_lane(candidates: Iterable[Mapping], table: Mapping | None = None, *, price: Any = None,
                atr_daily: Any = None, side: Any = None) -> Dict[str, Any]:
    """The ticker's lane from its live setups on the trade's side (A before B before C), and the setup that set it.

    side: the trade side Discovery assigned (BULL/BEAR or CALL/PUT). Fix A (ACK 5 Oct 2026): only setups on that
    side set the lane - run 20261005_072245 took 174 of 506 lane A/B rows from opposite-side setups. With no
    assigned side the ticker is lane C (NO_TRADE_SIDE); with live setups only on the other side it is lane C
    (NO_LIVE_SETUP_ON_TRADE_SIDE). side=None keeps the side-blind reading (callers that pass no side).
    price / atr_daily: the session close and 14-day daily ATR, used for the lane B geometry.
    """
    table = table or load_lanes()
    candidates = list(candidates or [])
    if side is None:
        return _best_lane(candidates, table, price, atr_daily)
    trade_side = _side(side)
    every = _best_lane(candidates, table, price, atr_daily)
    if trade_side is None:
        if every["trade_lane"] in _ORDER:
            every.update(trade_lane="C", trade_lane_basis="NO_TRADE_SIDE", trade_lane_hit_original=None,
                         trade_lane_hit_holdout=None)
        return {**every, "trade_lane_side": None}
    own = _best_lane([c for c in candidates if _side(c.get("Direction")) == trade_side], table, price, atr_daily)
    if own["trade_lane"] == "NO_LIVE_SETUP" and every["trade_lane"] in _ORDER:
        own.update(trade_lane="C", trade_lane_basis="NO_LIVE_SETUP_ON_TRADE_SIDE")
    return {**own, "trade_lane_side": trade_side}


def _best_lane(candidates: Iterable[Mapping], table: Mapping, price: Any, atr_daily: Any) -> Dict[str, Any]:
    untested = set(table["untested_timeframes"])
    best = None
    for c in candidates or []:
        lane = candidate_lane(c, table, price, atr_daily)
        if not lane:
            continue
        tested = str(c.get("Timeframe") or "") not in untested
        # A before B before C; among equals, a setup on a tested timeframe sets the lane.
        key = (_ORDER[lane["lane"]], 0 if tested else 1)
        if best is None or key < best["key"]:
            best = {**lane, "candidate": c, "key": key}
    if best is None:
        return {"trade_lane": "NO_LIVE_SETUP", "trade_lane_basis": "NO_LIVE_SETUP", "trade_lane_setup": None,
                "trade_lane_hit_original": None, "trade_lane_hit_holdout": None, "trade_lane_version": table["version"]}
    if best["key"][1] == 1:
        # ACK 5 Oct 2026 (change 1): only intraday setups, none tested yet - held out of the downstream line until
        # step 4 tests the timeframe (removing it from untested_timeframes re-admits these tickers).
        c = best["candidate"]
        return {"trade_lane": "INTRADAY_ONLY_UNTESTED", "trade_lane_basis": "INTRADAY_ONLY_UNTESTED",
                "trade_lane_setup": f'{c.get("Timeframe")}|{c.get("Signal_Type")}|{c.get("Signal_State")}',
                "trade_lane_hit_original": None, "trade_lane_hit_holdout": None, "trade_lane_version": table["version"]}
    c, hit = best["candidate"], best["hit"] or [None, None]
    return {"trade_lane": best["lane"], "trade_lane_basis": best["basis"],
            "trade_lane_setup": f'{c.get("Timeframe")}|{c.get("Signal_Type")}|{c.get("Signal_State")}',
            "trade_lane_hit_original": hit[0], "trade_lane_hit_holdout": hit[1],
            "trade_lane_version": table["version"]}


def confirm_early_entry(lane_fields: Mapping, value_multiple_q50: Any, *,
                        final_direction: Any = None) -> Dict[str, Any]:
    """Lane B holds only when the option's value multiple at the anticipated time covers the failures.

    Fix A: a lane A/B set on one side never travels to a trade on the other side (LANE_SIDE_CHANGED).
    """
    out = dict(lane_fields)
    lane_side, final_side = _side(lane_fields.get("trade_lane_side")), _side(final_direction)
    if out.get("trade_lane") in ("A", "B") and lane_side and final_side and lane_side != final_side:
        out.update(trade_lane="C", trade_lane_basis="LANE_SIDE_CHANGED")
        return out
    if out.get("trade_lane") != "B":
        return out
    hits = [h for h in (_num(lane_fields.get("trade_lane_hit_original")),
                        _num(lane_fields.get("trade_lane_hit_holdout"))) if h]
    multiple = _num(value_multiple_q50)
    need = 1.0 / min(hits) if hits else None
    out["trade_lane_required_multiple"] = round(need, 2) if need else None
    if multiple is None or need is None:
        out.update(trade_lane="C", trade_lane_basis="EARLY_ENTRY_PAYOFF_UNKNOWN")
    elif multiple < need:
        out.update(trade_lane="C", trade_lane_basis="EARLY_ENTRY_PAYOFF_TOO_SMALL")
    return out
