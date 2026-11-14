"""Crossing scenario: on which session would this exact contract first show +20% / +30%, on an assumed path?

AVS-TRADE-001 design note v4 (ACK 14 Nov 2026, D-14.10). Pure: no providers, no clock of its own, no writes.

DISPLAY ONLY, NOT VALIDATED. This is a scenario, not the measured monetisation clock, not a forecast and not a
probability of profit. It never selects, ranks or gates, and it is never published under a name Lane B acts on.

The one question it answers, in both modes: what would a NEW entry at this quote need?

  path     level(j) = S + (L* - S) * min(1, sqrt(j / R))        j = 1, 2, ... session closes after the assessment
           S   quote spot             L*  frozen thesis target (never recomputed)
           R   remaining pace = arrival sessions - completed sessions since the frozen thesis origin
  grid     sampled once per session, at the close; j = 1 is the first close strictly after the assessment instant
  search   to J = min(R, U, cap), where U = sessions to expiry - exit buffer (the last session an exit can be worked)
  covers   a crossing at j covers when j + monitoring buffer <= U

The path is an assumption: the evidence gives the arrival time, not the route. It stops at the target, never passes
it, and never touches the invalidation level (invalidation is not modelled). Stopping the search at arrival is a
boundary of this experiment; it does not prove that no later crossing exists.

Reuses: the one pricer and the one cost formula (domain.option_valuation), the session calendar and the countdown
owner (domain.trade_timing). Thresholds, buffers, cap and stress sizes are governed configuration.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from functools import lru_cache
import json
import math
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

from avshunter.shared.xnys_calendar import is_xnys_session, session_bounds
from domain.option_valuation import (american_crr_values, european_bsm_value, exercise_style,
                                     net_return_on_premium_raw, resolve_dividend, resolve_rate, valuation_policy)
from domain.trade_timing import after_sessions, day, remaining_hold, sessions_between

CONSTANTS_PATH = Path(__file__).resolve().parents[1] / "config" / "governed_constants_v1.json"
MODES = ("EVENING_AT_EVIDENCE", "MORNING_FRESH_ENTRY")
PACES = ("MEDIAN", "SLOW")
VARIANTS = ("BASE", "IV_DOWN", "WIDE_EXIT")
HEADLINE = ("SLOW", 30, "BASE")
ASSESSED_NOT_COVERING = {"CROSSES_NOT_COVERING", "NO_CROSSING_BY_ARRIVAL", "NO_CROSSING_BY_USABLE_DEADLINE",
                         "NO_USABLE_WINDOW"}

#: The fields this module puts on a row. None of them is a name any gate, rank, selector or Lane B flag reads.
CROSSING_FIELDS = (
    "crossing_state", "crossing_basis", "crossing_authority", "crossing_mode", "crossing_config_version",
    "crossing_n_median_pace_20", "crossing_n_median_pace_30", "crossing_n_slow_pace_20", "crossing_n_slow_pace_30",
    "crossing_n_slow_pace_30_iv_down", "crossing_n_slow_pace_30_wide_exit",
    "crossing_covers_slow30_base", "crossing_records_json",
    "crossing_thesis_id", "crossing_contract_symbol", "crossing_thesis_origin_date", "crossing_origin_spot",
    "crossing_frozen_target_level", "crossing_assessment_instant_utc", "crossing_quote_timestamp_utc",
    "crossing_quote_spot", "crossing_elapsed_sessions", "crossing_grid_first_date",
    "crossing_sessions_to_expiry", "crossing_expiry_session_date", "crossing_usable_deadline_session",
    "crossing_usable_deadline_date", "crossing_monitor_deadline_session", "crossing_monitor_deadline_date",
    "crossing_search_cap", "crossing_search_limit", "crossing_search_end_session", "crossing_search_end_date",
    "crossing_rate_used", "crossing_rate_basis", "crossing_dividend_used", "crossing_dividend_basis",
    "crossing_iv_used", "crossing_iv_down_used", "crossing_exit_spread_multiple", "crossing_model_version",
    "crossing_invalidation_basis",
)


@lru_cache(maxsize=1)
def crossing_config() -> Dict[str, Any]:
    """The governed settings, validated once. A setting outside its stated range is refused, never clamped."""
    constants = json.loads(CONSTANTS_PATH.read_text(encoding="utf-8-sig"))
    cfg = dict(constants["contract_crossing_scenario"])
    cfg["iv_down_multiple"] = float(min(constants["contract_economics"]["iv_stress"]))
    return validate_config(cfg)


def validate_config(cfg: Mapping[str, Any]) -> Dict[str, Any]:
    out = dict(cfg)
    thresholds = [float(t) for t in out["thresholds"]]
    if not thresholds or min(thresholds) < float(out["threshold_floor"]) - 1e-12:
        raise ValueError("contract_crossing_scenario.thresholds must not be below threshold_floor")
    low, high = out["search_cap_sessions_range"]
    if not (int(low) <= int(out["search_cap_sessions"]) <= int(high)):
        raise ValueError("contract_crossing_scenario.search_cap_sessions is outside its range")
    low, high = out["exit_spread_stress_multiple_range"]
    multiple = float(out["exit_spread_stress_multiple"])
    if not math.isfinite(multiple) or not (float(low) <= multiple <= float(high)):
        raise ValueError("contract_crossing_scenario.exit_spread_stress_multiple is outside its range")
    for key in ("monitor_buffer_sessions", "exit_buffer_sessions"):
        if int(out[key]) < 0:
            raise ValueError(f"contract_crossing_scenario.{key} must not be negative")
    if not (0.0 < float(out["iv_down_multiple"]) <= 1.0):
        raise ValueError("the governed low IV stress must be above 0 and at most 1")
    out["thresholds"] = thresholds
    return out


def _num(value: Any) -> Optional[float]:
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _instant(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value if value.tzinfo is not None and value.utcoffset() is not None else None
    if value in (None, ""):
        return None
    try:
        instant = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return instant if instant.tzinfo is not None and instant.utcoffset() is not None else None


def _plain_date(value: Any) -> Optional[date]:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if value in (None, ""):
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def grid_first_date(assessment: datetime) -> date:
    """The first session close strictly after the assessment instant.

    Before the close on a session day that is today (the countdown owner does not count today's session as spent
    before its close); otherwise the next session.
    """
    today = day(assessment.isoformat())
    if is_xnys_session(today) and assessment < session_bounds(today)[1]:
        return today
    return after_sessions(today, 1)


def expiry_session(expiry: date) -> date:
    """The last XNYS session on or before the expiry date."""
    current = expiry
    while not is_xnys_session(current):
        current -= timedelta(days=1)
    return current


def _model_values(side: str, spots: Sequence[float], strike: float, years: Sequence[float], vol: float, *,
                  rate: float, dividend_yield: float, underlying: Any) -> List[float]:
    """One model value per grid session, from the one pricer. The only place this module prices."""
    if exercise_style(underlying) == "EUROPEAN":
        return [european_bsm_value(side, s, strike, max(t, 0.0), vol, rate=rate, dividend_yield=dividend_yield)
                for s, t in zip(spots, years)]
    values = american_crr_values(list(spots), strike, [max(t, 0.0) for t in years], rate, dividend_yield, vol,
                                 side == "CALL", steps=int(valuation_policy()["crr_steps"]))
    return [float(v) for v in values]


def _record(pace: str, threshold: int, variant: str, state: str, **extra: Any) -> Dict[str, Any]:
    base = {"pace": pace, "threshold_pct": threshold, "variant": variant, "state": state, "crossing_session": None,
            "crossing_date": None, "covers": None, "remaining_pace_sessions": None, "arrival_date": None,
            "search_end_session": None, "search_end_date": None, "search_limit": None}
    base.update(extra)
    return base


def headline_coverage(state: Optional[str]) -> str:
    """YES / NO / NOT_ASSESSED for the slow-pace +30% base record, by the written rule (design section 6)."""
    if state == "CROSSES_COVERING":
        return "YES"
    if state in ASSESSED_NOT_COVERING:
        return "NO"
    return "NOT_ASSESSED"


def blank_fields(state: str, *, mode: Any = None) -> Dict[str, Any]:
    out: Dict[str, Any] = {field: None for field in CROSSING_FIELDS}
    out.update(crossing_state=state, crossing_authority="DISPLAY_ONLY_NOT_VALIDATED",
               crossing_covers_slow30_base="NOT_ASSESSED", crossing_mode=mode,
               crossing_invalidation_basis="INVALIDATION_NOT_MODELLED")
    return out


def scenario_crossing(
    *,
    side: Any,
    mode: Any,
    thesis_id: Any,
    contract_symbol: Any,
    thesis_origin_date: Any,
    origin_spot: Any,
    frozen_target_level: Any,
    arrival_sessions_median: Any,
    arrival_sessions_slow: Any,
    assessment_instant_utc: Any,
    quote_timestamp_utc: Any,
    quote_spot: Any,
    strike: Any,
    expiry: Any,
    bid: Any,
    ask: Any,
    iv: Any,
    thesis_active: Any = None,
    underlying: Any = None,
    rate: Any = None,
    rate_basis: Any = None,
    dividend_yield: Any = None,
    dividend_basis: Any = None,
    config: Optional[Mapping[str, Any]] = None,
    paces: Sequence[str] = PACES,
    variants: Sequence[str] = VARIANTS,
) -> Dict[str, Any]:
    """The crossing scenario for one exact contract: 12 records (2 paces x 2 thresholds x 3 variants) and the
    headline fields. Every not-assessed case is a state with no number; nothing is ever turned into a zero.

    `paces` and `variants` narrow what is priced (the shadow candidates price the slow pace at base IV only, a
    published scope reduction); a combination left out is recorded NOT_COMPUTED_OUT_OF_SCOPE, never as a result."""
    cfg = validate_config(config) if config is not None else crossing_config()
    want_paces = tuple(p for p in PACES if p in set(paces))
    want_variants = tuple(v for v in VARIANTS if v in set(variants))
    thresholds = [int(round(t * 100)) for t in cfg["thresholds"]]
    out = blank_fields("NOT_ASSESSED", mode=str(mode or "").upper() or None)
    out.update(crossing_basis=cfg["path_basis"], crossing_config_version=cfg["version"],
               crossing_thesis_id=thesis_id, crossing_contract_symbol=contract_symbol,
               crossing_search_cap=int(cfg["search_cap_sessions"]),
               crossing_exit_spread_multiple=float(cfg["exit_spread_stress_multiple"]),
               crossing_quote_timestamp_utc=None if quote_timestamp_utc in (None, "") else str(quote_timestamp_utc))

    def finish(state: str, records: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        recs = records if records is not None else [
            _record(p, t, v, state) for p in PACES for t in thresholds for v in VARIANTS]
        by = {(r["pace"], r["threshold_pct"], r["variant"]): r for r in recs}
        head = by.get(HEADLINE)
        out["crossing_state"] = head["state"] if head else state
        out["crossing_covers_slow30_base"] = headline_coverage(out["crossing_state"])
        for pace, tag in (("MEDIAN", "median"), ("SLOW", "slow")):
            for t in thresholds:
                rec = by.get((pace, t, "BASE"))
                key = f"crossing_n_{tag}_pace_{t}"
                if key in out:
                    out[key] = rec["crossing_session"] if rec else None
        for variant, tag in (("IV_DOWN", "iv_down"), ("WIDE_EXIT", "wide_exit")):
            rec = by.get(("SLOW", 30, variant))
            out[f"crossing_n_slow_pace_30_{tag}"] = rec["crossing_session"] if rec else None
        if head:
            out.update(crossing_search_limit=head["search_limit"], crossing_search_end_session=head["search_end_session"],
                       crossing_search_end_date=head["search_end_date"])
            if head["crossing_session"] is not None and out["crossing_grid_first_date"]:
                first = date.fromisoformat(out["crossing_grid_first_date"])
                monitor = head["crossing_session"] + int(cfg["monitor_buffer_sessions"])
                out["crossing_monitor_deadline_session"] = monitor
                out["crossing_monitor_deadline_date"] = after_sessions(first, monitor - 1).isoformat()
        out["crossing_records_json"] = json.dumps(recs, sort_keys=True)
        return out

    # 1. anchors
    side_text = str(side or "").upper()
    mode_text = str(mode or "").upper()
    assessed = _instant(assessment_instant_utc)
    if mode_text not in MODES or assessed is None or side_text not in ("CALL", "PUT"):
        return finish("NOT_ASSESSED_CALLER_DID_NOT_SUPPLY_ANCHORS")
    out["crossing_assessment_instant_utc"] = assessed.isoformat()
    sign = 1.0 if side_text == "CALL" else -1.0
    # 2-3. thesis status: unknown is never assumed active
    if thesis_active is None:
        return finish("NOT_ASSESSED_THESIS_STATUS_UNKNOWN")
    if not bool(thesis_active):
        return finish("THESIS_NOT_ACTIVE")
    # 4. frozen origin: never replaced by today's date
    origin = _plain_date(thesis_origin_date)
    if origin is None:
        return finish("NOT_ASSESSED_NO_THESIS_ORIGIN")
    out["crossing_thesis_origin_date"] = origin.isoformat()
    clock = remaining_hold(0, origin.isoformat(), assessed.isoformat())
    if clock.get("hold_clock_state") == "REFERENCE_NOT_RECORDED_OR_INVALID":
        return finish("NOT_ASSESSED_NO_THESIS_ORIGIN")
    elapsed = int(clock["elapsed_hold_sessions"])
    out["crossing_elapsed_sessions"] = elapsed
    first = grid_first_date(assessed)
    out["crossing_grid_first_date"] = first.isoformat()
    # 5-6. spots and level
    spot, spot0, target = _num(quote_spot), _num(origin_spot), _num(frozen_target_level)
    if spot is None or spot <= 0 or spot0 is None or spot0 <= 0:
        return finish("NOT_ASSESSED_NO_SPOT")
    out.update(crossing_quote_spot=spot, crossing_origin_spot=spot0)
    if target is None or target <= 0:
        return finish("NOT_ASSESSED_NO_LEVEL")
    out["crossing_frozen_target_level"] = target
    # 7-8. geometry: wrong side is judged on the origin spot; a target the quote has passed is "reached"
    if sign * (target - spot0) <= 0:
        return finish("TARGET_ON_WRONG_SIDE")
    if sign * (spot - target) >= 0:
        return finish("TARGET_ALREADY_REACHED_AT_QUOTE")

    # contract inputs (states 11-13), evaluated per pace after the pace states
    strike_v, iv_v, expiry_d = _num(strike), _num(iv), _plain_date(expiry)
    bid_v, ask_v = _num(bid), _num(ask)
    contract_state: Optional[str] = None
    if strike_v is None or strike_v <= 0 or iv_v is None or iv_v <= 0 or expiry_d is None:
        contract_state = "NOT_ASSESSED_NO_STRIKE_IV_OR_EXPIRY"
    elif (ask is not None and ask != "" and ask_v is None) or (bid is not None and bid != "" and bid_v is None):
        contract_state = "NOT_ASSESSED_INVALID_QUOTE"                       # non-finite
    elif ask_v is None or ask_v <= 0:
        contract_state = "NOT_ASSESSED_INVALID_QUOTE"
    elif bid_v is not None and (bid_v < 0 or bid_v > ask_v):
        contract_state = "NOT_ASSESSED_INVALID_QUOTE"
    elif bid_v is None or bid_v == 0:
        contract_state = "NOT_ASSESSED_EXIT_COST_UNKNOWN"

    usable = sessions_to_expiry = None
    if expiry_d is not None:
        last = expiry_session(expiry_d)
        sessions_to_expiry = (sessions_between(first, last) + 1) if last >= first else 0
        usable = sessions_to_expiry - int(cfg["exit_buffer_sessions"])
        out.update(crossing_sessions_to_expiry=sessions_to_expiry, crossing_expiry_session_date=last.isoformat(),
                   crossing_usable_deadline_session=usable,
                   crossing_usable_deadline_date=after_sessions(first, usable - 1).isoformat() if usable >= 1 else None)

    rate_used, rate_label = resolve_rate(rate, rate_basis)
    q_used, q_label = resolve_dividend(dividend_yield, dividend_basis)
    iv_down = iv_v * float(cfg["iv_down_multiple"]) if iv_v else None
    out.update(crossing_rate_used=rate_used, crossing_rate_basis=rate_label, crossing_dividend_used=q_used,
               crossing_dividend_basis=q_label, crossing_iv_used=iv_v, crossing_iv_down_used=iv_down,
               crossing_model_version=valuation_policy().get("version"))

    cap = int(cfg["search_cap_sessions"])
    monitor = int(cfg["monitor_buffer_sessions"])
    multiple = float(cfg["exit_spread_stress_multiple"])
    records: List[Dict[str, Any]] = []
    for pace, arrival in (("MEDIAN", arrival_sessions_median), ("SLOW", arrival_sessions_slow)):
        total = _num(arrival)

        def all_states(state: str, **extra: Any) -> None:
            records.extend(_record(pace, t, v, state, **extra) for t in thresholds for v in VARIANTS)

        if pace not in want_paces:
            all_states("NOT_COMPUTED_OUT_OF_SCOPE")
            continue
        # 9-10. pace
        if total is None or total < 1:
            all_states("NOT_ASSESSED_NO_ARRIVAL_TIME")
            continue
        remaining = int(math.ceil(total)) - elapsed
        if remaining <= 0:
            all_states("PACE_EXHAUSTED", remaining_pace_sessions=remaining)
            continue
        arrival_date = after_sessions(first, remaining - 1).isoformat()
        common = {"remaining_pace_sessions": remaining, "arrival_date": arrival_date}
        # 11-13. contract
        if contract_state is not None:
            all_states(contract_state, **common)
            continue
        # 14. usable window
        if usable is None or usable <= 0:
            all_states("NO_USABLE_WINDOW", **common)
            continue
        # the boundary actually searched; ties resolve arrival, then usable deadline, then cap
        end = min(remaining, usable, cap)
        limit = "ARRIVAL" if end == remaining else "USABLE_DEADLINE" if end == usable else "CONFIG_CAP"
        end_date = after_sessions(first, end - 1)
        common.update(search_end_session=end, search_end_date=end_date.isoformat(), search_limit=limit)
        offsets = list(range(1, end + 1))
        dates = [after_sessions(first, j - 1) for j in offsets]
        spots = [spot + (target - spot) * min(1.0, math.sqrt(j / remaining)) for j in offsets]
        years = [max((expiry_d - d).days, 0) / 365.0 for d in dates]
        # Sessions are priced in order, in blocks, and pricing stops once every threshold of every variant that
        # shares those model values has its first crossing. The crossing found is the same as a full scan would
        # find; only sessions after the last needed crossing are left unpriced.
        hits: Dict[tuple, Optional[int]] = {}
        failed: Dict[str, Optional[int]] = {}
        for label, vol in (("BASE", iv_v), ("IV_DOWN", iv_down)):
            sharing = [v for v in ("BASE", "WIDE_EXIT") if v in want_variants] if label == "BASE" else (
                ["IV_DOWN"] if "IV_DOWN" in want_variants else [])
            if not sharing:
                continue
            for v in sharing:
                failed[v] = None
                for t in thresholds:
                    hits[(v, t)] = None
            block = max(1, int(cfg.get("pricing_block_sessions", 20)))
            for start in range(0, end, block):
                js = offsets[start:start + block]
                try:
                    values = _model_values(side_text, spots[start:start + block], strike_v, years[start:start + block],
                                           vol, rate=rate_used, dividend_yield=q_used, underlying=underlying)
                except (OverflowError, FloatingPointError, ValueError, ZeroDivisionError):
                    for v in sharing:
                        failed[v] = failed[v] or js[0]
                    break
                for j, value in zip(js, values):
                    for v in sharing:
                        if failed[v] is not None:
                            continue
                        raw = (net_return_on_premium_raw(value, bid=bid_v, ask=ask_v,
                                                         exit_spread_multiple=multiple if v == "WIDE_EXIT" else 1.0)
                               if math.isfinite(value) else None)
                        if raw is None:
                            failed[v] = j
                            continue
                        for t in thresholds:
                            if hits[(v, t)] is None and raw >= t / 100.0:      # unrounded comparison
                                hits[(v, t)] = j
                if all(failed[v] is not None or all(hits[(v, t)] is not None for t in thresholds) for v in sharing):
                    break
        for variant in VARIANTS:
            if variant not in want_variants:
                records.extend(_record(pace, t, variant, "NOT_COMPUTED_OUT_OF_SCOPE", **common) for t in thresholds)
                continue
            failed_at = failed.get(variant)
            for t in thresholds:
                hit = hits.get((variant, t))
                if hit is not None:
                    covers = hit + monitor <= usable
                    records.append(_record(pace, t, variant, "CROSSES_COVERING" if covers else "CROSSES_NOT_COVERING",
                                           crossing_session=hit, crossing_date=dates[hit - 1].isoformat(),
                                           covers=covers, **common))
                elif failed_at is not None:
                    records.append(_record(pace, t, variant, "NOT_ASSESSED_PRICING_NUMERIC_FAILURE", **common))
                else:
                    state = {"ARRIVAL": "NO_CROSSING_BY_ARRIVAL", "USABLE_DEADLINE": "NO_CROSSING_BY_USABLE_DEADLINE",
                             "CONFIG_CAP": "SEARCH_TRUNCATED_AT_CONFIG_CAP"}[limit]
                    records.append(_record(pace, t, variant, state,
                                           covers=False if state != "SEARCH_TRUNCATED_AT_CONFIG_CAP" else None, **common))
    return finish("NOT_ASSESSED", records)
