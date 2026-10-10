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
                     # S2-1 (ACK 6 Oct 2026): the governing setup, the levels it excluded, the daily event kept as
                     # supporting evidence, and the I-c invalidation (governing decides, daily is an early warning).
                     "trade_lane_candidate_id", "trade_lane_levels_passed",
                     "daily_event", "daily_event_state", "daily_event_candidate_id", "daily_event_outcome_level",
                     "thesis_invalidation_setup_id", "early_warning_invalidation_level", "early_warning_setup_id",
                     "intake_flags", "price_band",
                     # Output-trust item 3 (9 Oct 2026): the records behind each hit rate (original, held out).
                     "trade_lane_hit_n_original", "trade_lane_hit_n_holdout",
                     # Output-trust item 10.1 (ACK 10 Oct 2026): the governing setup's own rate within the planned
                     # hold (config/setup_rates_v1.json, display only until ACK switches the lane / geometry rates).
                     "setup_rate_within_hold", "setup_rate_ci_low", "setup_rate_ci_high", "setup_rate_n",
                     "setup_rate_shrunk", "setup_hold_bars", "setup_calibration_slope", "setup_calibration_intercept",
                     # Output-trust item 10.2 (ACK 10 Oct 2026): the setup's forward calibration state, from the
                     # latest C12 forward report (domain/forward_calibration.py) - display only.
                     "setup_forward_state", "setup_forward_text")
SETUP_RATES_PATH = Path(__file__).resolve().parents[2] / "config" / "setup_rates_v1.json"
FORWARD_REPORT_PATH = Path(__file__).resolve().parents[2] / "data" / "canonical" / "forward_calibration_latest.json"
_FORWARD: Dict[str, Any] = {}
_SETUP_RATES: Dict[str, Any] = {}


def setup_rate_fields(candidate: Optional[Mapping]) -> Dict[str, Any]:
    """The governing setup's replay rate within its planned hold (held-out panel), its n, interval, shrunk rate and
    the replay calibration - display only. A setup the table does not hold gets nulls (never a pooled stand-in)."""
    out = {f: None for f in ("setup_rate_within_hold", "setup_rate_ci_low", "setup_rate_ci_high", "setup_rate_n",
                             "setup_rate_shrunk", "setup_hold_bars", "setup_calibration_slope",
                             "setup_calibration_intercept", "setup_forward_state", "setup_forward_text")}
    if not candidate:
        return out
    if not _SETUP_RATES and SETUP_RATES_PATH.exists():
        table = json.loads(SETUP_RATES_PATH.read_text(encoding="utf-8"))
        _SETUP_RATES["calibration"] = table.get("calibration") or {}
        _SETUP_RATES["by_key"] = {(s["timeframe"], s["state"], s["signal_type"], s["direction"]): s
                                  for s in table.get("setups") or []}
    key = (str(candidate.get("Timeframe") or ""), str(candidate.get("Signal_State") or "").upper(),
           str(candidate.get("Signal_Type") or ""), str(candidate.get("Direction") or "").upper())
    s = (_SETUP_RATES.get("by_key") or {}).get(key)
    if not s or not s.get("n_holdout"):
        return out
    ci = s.get("ci_holdout") or [None, None]
    cal = _SETUP_RATES.get("calibration") or {}
    out.update(setup_rate_within_hold=s.get("rate_holdout"), setup_rate_ci_low=ci[0], setup_rate_ci_high=ci[1],
               setup_rate_n=s.get("n_holdout"), setup_rate_shrunk=s.get("rate_shrunk"), setup_hold_bars=s.get("hold_bars"),
               setup_calibration_slope=cal.get("slope"), setup_calibration_intercept=cal.get("intercept"))
    out.update(_forward_fields(f"{key[0]}|{key[2]}|{key[1]}|{key[3]}"))
    return out


def _forward_fields(setup_key: str) -> Dict[str, Any]:
    from domain.forward_calibration import forward_label
    if "report" not in _FORWARD:
        try:
            _FORWARD["report"] = json.loads(FORWARD_REPORT_PATH.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            _FORWARD["report"] = None
    report = _FORWARD["report"]
    if not report:
        return {"setup_forward_state": "NOT_MEASURED", "setup_forward_text": "forward: not measured (no forward report)"}
    own = (report.get("setups") or {}).get(setup_key)
    return {"setup_forward_state": (own or {}).get("state") or "UNCALIBRATED_FORWARD",
            "setup_forward_text": forward_label(own, report.get("policy") or {})}
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
        return {"lane": "A", "basis": "TRADE_NOW_MEASURED", "hit": hit["hit"], "n": hit.get("n")}
    lane_b = table["lane_b_early_entry"]
    hit = _match(lane_b.get(tf), state, kind)
    if hit:
        fits = _geometry(candidate, price, atr_daily, lane_b["geometry"])
        if fits:
            return {"lane": "B", "basis": "EARLY_ENTRY_MEASURED", "hit": hit["hit"], "n": hit.get("n")}
        basis = "EARLY_ENTRY_GEOMETRY_UNKNOWN" if fits is None else "EARLY_ENTRY_GEOMETRY_NOT_MET"
        return {"lane": "C", "basis": basis, "hit": None}
    basis = "NO_TESTED_EVIDENCE" if tf in table["untested_timeframes"] else "BELOW_LINE_OR_UNMEASURED"
    return {"lane": "C", "basis": basis, "hit": None}


_SIDES = {"BULL": "BULL", "CALL": "BULL", "BEAR": "BEAR", "PUT": "BEAR"}


def _side(value: Any) -> Optional[str]:
    return _SIDES.get(str(value or "").strip().upper())


def ticker_lane(candidates: Iterable[Mapping], table: Mapping | None = None, *, price: Any = None,
                atr_daily: Any = None, side: Any = None) -> Dict[str, Any]:
    """The ticker's lane fields from the governing setup (see select_governing)."""
    return select_governing(candidates, table, price=price, atr_daily=atr_daily, side=side)[0]


def select_governing(candidates: Iterable[Mapping], table: Mapping | None = None, *, price: Any = None,
                     atr_daily: Any = None, side: Any = None,
                     adopted_ids: Optional[Iterable[str]] = None) -> tuple[Dict[str, Any], Optional[Mapping]]:
    """The governing setup: the one live setup that sets the lane AND supplies the move, time and invalidation.

    S2-1 (ACK 6 Oct 2026): Discovery used to pick a setup four times with four rules (daily primary, lane, a
    1d-first thesis event, a range target); 32 of 51 GOs on run 20261006_060401 were valued on a 1d event that was
    not their lane setup. One selection now serves them all:
    - trade-side live setups only. Fix A (ACK 5 Oct 2026): with no assigned side the ticker is lane C
      (NO_TRADE_SIDE); with live setups only on the other side it is lane C (NO_LIVE_SETUP_ON_TRADE_SIDE).
      side=None keeps the side-blind reading (callers that pass no side);
    - a setup whose outcome level is not ahead of the price on its own side is excluded (LEVEL_ALREADY_PASSED):
      the move has happened. A candidate stays DETECTED until its trigger is accepted, so a passed level can still
      look live (signals._state_detail); with every trade-side level passed the basis says so;
    - lane A before B before C; a tested timeframe before an untested one; then ACTIVATED before DETECTED, the
      higher holdout hit rate, more duration evidence, the nearer level, the newer event; the Candidate_ID only last.
    price / atr_daily: the session close and 14-day daily ATR (lane B geometry and the passed-level test).
    adopted_ids: G2-06 (verification 20261008_220129) - when the thesis decisions are known, only an ADOPTED thesis
    can govern; a refused candidate (levels on the wrong side) never supplies the trigger, target or invalidation.
    None keeps the legacy reading for callers without thesis decisions.
    Returns (lane fields, governing candidate or None).
    """
    table = table or load_lanes()
    candidates = list(candidates or [])
    if side is None:
        return _best_lane(candidates, table, price, atr_daily)
    trade_side = _side(side)
    every, _ = _best_lane(candidates, table, price, atr_daily)
    if trade_side is None:
        if every["trade_lane"] in _ORDER:
            every.update(trade_lane="C", trade_lane_basis="NO_TRADE_SIDE", trade_lane_hit_original=None,
                         trade_lane_hit_holdout=None, trade_lane_hit_n_original=None, trade_lane_hit_n_holdout=None,
                         trade_lane_candidate_id=None)
        return {**every, "trade_lane_side": None}, None
    # The side-blind reading above stays on every candidate (survival and the lane-C basis are unchanged); only the
    # trade-side governing choice is restricted to adopted theses when they are known.
    adopted = None if adopted_ids is None else set(adopted_ids)
    own, governing = _best_lane([c for c in candidates if _side(c.get("Direction")) == trade_side
                                 and (adopted is None or c.get("Candidate_ID") in adopted)], table, price,
                                atr_daily)
    if own["trade_lane"] == "NO_LIVE_SETUP" and every["trade_lane"] in _ORDER:
        basis = ("ALL_TRADE_SIDE_LEVELS_PASSED" if own["trade_lane_basis"] == "ALL_LEVELS_PASSED"
                 else "NO_LIVE_SETUP_ON_TRADE_SIDE")
        own.update(trade_lane="C", trade_lane_basis=basis)
    return {**own, "trade_lane_side": trade_side}, governing


def _level_passed(candidate: Mapping, price: Any) -> bool:
    """The outcome level is not ahead of the price on the candidate's own side (the move has already happened)."""
    level, px, side = _num(candidate.get("Outcome_Level")), _num(price), _side(candidate.get("Direction"))
    if level is None or px is None or side is None:
        return False
    return (level - px) * (1 if side == "BULL" else -1) <= 0


def _best_lane(candidates: Iterable[Mapping], table: Mapping, price: Any,
               atr_daily: Any) -> tuple[Dict[str, Any], Optional[Mapping]]:
    untested = set(table["untested_timeframes"])
    best, passed = None, 0
    for c in candidates or []:
        lane = candidate_lane(c, table, price, atr_daily)
        if not lane:
            continue
        if _level_passed(c, price):
            passed += 1
            continue
        level, px = _num(c.get("Outcome_Level")), _num(price)
        hit = lane.get("hit") or [None, None]
        key = (_ORDER[lane["lane"]], 0 if str(c.get("Timeframe") or "") not in untested else 1,
               0 if str(c.get("Signal_State") or "").upper() == "ACTIVATED" else 1,
               -(_num(hit[1]) or 0.0), -(_num(c.get("Duration_Level_N")) or 0.0),
               abs(level - px) if level is not None and px is not None else float("inf"),
               _num(c.get("Age_Bars")) if _num(c.get("Age_Bars")) is not None else float("inf"),
               str(c.get("Candidate_ID") or ""))
        if best is None or key < best["key"]:
            best = {**lane, "candidate": c, "key": key}
    common = {"trade_lane_version": table["version"], "trade_lane_levels_passed": passed,
              "trade_lane_hit_n_original": None, "trade_lane_hit_n_holdout": None, **setup_rate_fields(None)}
    if best is None:
        return {"trade_lane": "NO_LIVE_SETUP", "trade_lane_basis": "ALL_LEVELS_PASSED" if passed else "NO_LIVE_SETUP",
                "trade_lane_setup": None,
                "trade_lane_hit_original": None, "trade_lane_hit_holdout": None, "trade_lane_candidate_id": None,
                **common}, None
    c = best["candidate"]
    setup = f'{c.get("Timeframe")}|{c.get("Signal_Type")}|{c.get("Signal_State")}'
    if best["key"][1] == 1:
        # ACK 5 Oct 2026 (change 1): only intraday setups, none tested yet - held out of the downstream line until
        # step 4 tests the timeframe (removing it from untested_timeframes re-admits these tickers).
        return {"trade_lane": "INTRADAY_ONLY_UNTESTED", "trade_lane_basis": "INTRADAY_ONLY_UNTESTED",
                "trade_lane_setup": setup, "trade_lane_hit_original": None, "trade_lane_hit_holdout": None,
                "trade_lane_candidate_id": c.get("Candidate_ID"), **common}, None
    hit = best["hit"] or [None, None]
    n = best.get("n") or [None, None]
    return {"trade_lane": best["lane"], "trade_lane_basis": best["basis"], "trade_lane_setup": setup,
            "trade_lane_hit_original": hit[0], "trade_lane_hit_holdout": hit[1],
            "trade_lane_candidate_id": c.get("Candidate_ID"), **common,
            "trade_lane_hit_n_original": n[0], "trade_lane_hit_n_holdout": n[1], **setup_rate_fields(c)}, c


def governed_invalidation(governing: Optional[Mapping], daily_primary: Optional[Mapping]) -> Dict[str, Any]:
    """I-c (ACK 6 Oct 2026): the governing setup's own invalidation decides "thesis wrong"; the daily primary's
    level, when it is a different setup, is an early warning (supporting, never gating). No governing setup leaves
    the invalidation missing - it is never borrowed from another setup."""
    level = _num((governing or {}).get("Invalidation_Level"))
    warn = None
    if daily_primary is not None and governing is not None \
            and daily_primary.get("Candidate_ID") != governing.get("Candidate_ID"):
        warn = daily_primary
    return {"governed_invalidation_level": level,
            "thesis_invalidation_setup_id": (governing or {}).get("Candidate_ID") if governing else None,
            "early_warning_invalidation_level": _num(warn.get("Invalidation_Level")) if warn else None,
            "early_warning_setup_id": warn.get("Candidate_ID") if warn else None}


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
