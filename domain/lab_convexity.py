"""Saved-snapshot payoff research; never changes decisions or grants execution.

Screening thresholds are descriptive UI choices, NOT validated trading rules.
Only the explicit offline publisher calls the pure saved-input pricing model.
"""
from datetime import date
import math
import re

VERSION = "lab_convexity_v1"
POLICY = {"waiting_min_target_return": 0.75, "max_spread_pct_mid": 15.0,
          "min_open_interest": 500, "min_target_runway_after_trigger": 0.5,
          "delay_multiplier": 2, "iv_multiplier": 0.8}


def number(value):
    if isinstance(value, bool):
        return None
    try:
        value = float(value)
        return value if math.isfinite(value) else None
    except (TypeError, ValueError):
        return None


def _truth(value):
    return value is True or str(value).strip().lower() == "true"


def _token(value):
    return str(value or "").strip().upper()


def _stress(row):
    """Reproduce the saved baseline before offering comparable new stresses."""
    from domain.option_valuation import option_value, valuation_policy
    required = ("contract_bid", "contract_ask", "contract_iv", "scenario_exit_sessions",
                "scenario_target_exit_spot", "valuation_rate_annual",
                "valuation_dividend_yield_annual", "valuation_entry_cost_usd_per_share")
    values = {k: number(row.get(k)) for k in required}
    result = {"state": "UNAVAILABLE", "reason": "SAVED_VALUATION_INPUTS_INCOMPLETE",
              "delay_return": None, "iv_return": None, "combined_return": None}
    if any(v is None for v in values.values()):
        return result
    symbol = str(row.get("contract_symbol") or "")
    match = re.fullmatch(r"(.+?)(\d{6})([CP])(\d{8})", symbol)
    side = _token(row.get("direction"))
    if (not match or match[3] != ("C" if side == "CALL" else "P")
            or row.get("anticipated_contract_symbol") != symbol):
        return {**result, "reason": "CONTRACT_LINEAGE_MISMATCH"}
    try:
        expiry = date.fromisoformat(str(row["expiry"])[:10])
        asof = date.fromisoformat(str(row["anticipated_valued_at_utc"])[:10])
        symbol_expiry = date(2000+int(match[2][:2]), int(match[2][2:4]), int(match[2][4:6]))
    except (KeyError, ValueError):
        return {**result, "reason": "VALUATION_CLOCK_INCOMPLETE"}
    if expiry != symbol_expiry or side not in {"CALL", "PUT"}:
        return {**result, "reason": "CONTRACT_LINEAGE_MISMATCH"}
    bid, ask, iv = (values[k] for k in ("contract_bid", "contract_ask", "contract_iv"))
    entry = values["valuation_entry_cost_usd_per_share"]
    if not 0 < bid <= ask or iv <= 0 or entry <= 0 or values["scenario_exit_sessions"] <= 0:
        return {**result, "reason": "INVALID_SAVED_QUOTE_OR_HORIZON"}
    model = row.get("valuation_model")
    if model not in {"AMERICAN_CRR", "BSM_EUROPEAN"}:
        return {**result, "reason": "MODEL_NOT_SUPPORTED"}
    # Same governed conversion used by the original producer, explicitly disclosed.
    from domain.anticipated_move import _constants
    per_session = _constants()["anticipated_move"]["calendar_days_per_session"]
    pol = valuation_policy()
    expected_entry = ask + pol["fee_usd_per_contract_open"] / 100
    if abs(entry - expected_entry) > 0.0002:
        return {**result, "reason": "SAVED_COST_BASIS_MISMATCH"}
    half_spread = (ask-bid)/2
    days = (expiry-asof).days
    t = values["scenario_exit_sessions"]
    strike = int(match[4])/1000

    def price(sessions, vol):
        remaining = days-sessions*per_session
        if remaining < 0:
            return None
        v = option_value(side, values["scenario_target_exit_spot"], strike, remaining/365, vol,
                         rate=values["valuation_rate_annual"],
                         dividend_yield=values["valuation_dividend_yield_annual"],
                         style="AMERICAN" if model == "AMERICAN_CRR" else "EUROPEAN")["value"]
        net = max(v-half_spread-pol["fee_usd_per_contract_close"]/100, 0)
        return round(net/entry-1, 4)

    base = price(t, iv)
    saved = number(row.get("scenario_target_return_on_premium"))
    if base is None or saved is None or abs(base-saved) > 0.0002:
        return {**result, "reason": "SAVED_BASELINE_NOT_REPRODUCED"}
    delay = price(t*POLICY["delay_multiplier"], iv)
    return {"state": "COMPLETE" if delay is not None else "PARTIAL_DELAY_BEYOND_EXPIRY",
            "reason": None if delay is not None else "DELAY_EXCEEDS_SAVED_EXPIRY",
            "delay_sessions": t*POLICY["delay_multiplier"], "delay_return": delay,
            "iv_original": iv, "iv_stressed": iv*POLICY["iv_multiplier"],
            "iv_return": price(t, iv*POLICY["iv_multiplier"]),
            "combined_return": price(t*POLICY["delay_multiplier"], iv*POLICY["iv_multiplier"]),
            "baseline_reproduced": True, "calendar_days_per_session": per_session}


def build_watchlist(rows):
    """Create research-only comparisons from the exact published source population."""
    groups = {"waiting": [], "entry_ready": [], "review_only": []}
    exclusions = []
    for ordinal, row in enumerate(rows):
        target_return = number(row.get("scenario_target_return_on_premium"))
        verdict = _token(row.get("lab_verdict"))
        ready = _token(row.get("thesis__readiness"))
        is_entry = verdict in {"GO", "GO_LIMIT", "GO_LMT", "GO_WITH_LIMIT"}
        if not is_entry and (target_return is None or target_return < POLICY["waiting_min_target_return"]):
            continue
        reasons = []
        bid, ask = number(row.get("contract_bid")), number(row.get("contract_ask"))
        spread = (ask-bid)/((ask+bid)/2)*100 if bid is not None and ask is not None and 0 < bid <= ask else None
        side = _token(row.get("direction"))
        sign = 1 if side == "CALL" else -1
        spot = number(row.get("live_price"))
        if spot is None or spot <= 0:
            spot = number(row.get("signal_price"))
        target = number(row.get("scenario_target_exit_spot"))
        inval = number(row.get("invalidation_price"))
        trigger = number(row.get("thesis_trigger_level"))
        if side not in {"CALL", "PUT"} or _token(row.get("direction_governance_status")) != "CONFIRMED":
            reasons.append("DIRECTION_NOT_CONFIRMED")
        if _token(row.get("direction_conflict_status")) not in {"NO_CONFLICT"}:
            reasons.append("DIRECTION_CONFLICT_OR_UNKNOWN")
        if verdict in {"BLOCK", "BLOCKED", "CONTRACT_REPAIR"} or ready.startswith("CLOSED"):
            reasons.append("BLOCKED_REPAIR_OR_CLOSED")
        if str(row.get("thesis__event_failed_at") or "").strip():
            reasons.append("THESIS_EVENT_FAILED")
        if _token(row.get("execution_viability_state")) != "EXECUTABLE_QUOTE":
            reasons.append("QUOTE_NOT_EXECUTABLE")
        if row.get("anticipated_time_fit") != "CONTRACT_OUTLASTS_Q80":
            reasons.append("EXPIRY_BEFORE_Q80_OR_UNKNOWN")
        if (spot is None or target is None or inval is None or sign*(target-spot) <= 0
                or sign*(spot-inval) <= 0 or number(row.get("scenario_invalidation_return_on_premium")) is None):
            reasons.append("TARGET_OR_INVALIDATION_INCOMPLETE")
        runway = (target-trigger)/(target-spot) if all(v is not None for v in (spot,target,trigger)) and target != spot else None
        if ready == "WAIT_TRIGGER":
            if runway is None or runway < POLICY["min_target_runway_after_trigger"]:
                reasons.append("TRIGGER_CONSUMES_MOST_MODELLED_MOVE_OR_UNKNOWN")
            if spread is None or spread > POLICY["max_spread_pct_mid"]:
                reasons.append("RESEARCH_SPREAD_LIMIT")
            if (number(row.get("contract_oi")) or 0) < POLICY["min_open_interest"]:
                reasons.append("RESEARCH_OPEN_INTEREST_LIMIT")
        elif ready != "READY_FOR_HUMAN_REVIEW":
            reasons.append("READINESS_NOT_SUPPORTED")
        if is_entry and row.get("geometry_justification") != "JUSTIFIED":
            reasons.append("ENTRY_GEOMETRY_NOT_JUSTIFIED")
        if is_entry and (_token(row.get("morning_execution_lane")) != "MORNING_VALIDATED"
                         or _token(row.get("morning_execution_permission")) not in
                         {"GO", "GO_LIMIT", "GO_LMT", "GO_WITH_LIMIT"}):
            reasons.append("CURRENT_ENTRY_PERMISSION_NOT_CONFIRMED")
        if reasons:
            exclusions.append({"ticker": row.get("ticker"), "source_row_ordinal": ordinal,
                               "target_return": target_return, "reasons": reasons})
            continue
        stress = _stress(row)
        if not stress.get("baseline_reproduced"):
            exclusions.append({"ticker": row.get("ticker"), "source_row_ordinal": ordinal,
                               "target_return": target_return, "reasons": [stress["reason"]]})
            continue
        group = "waiting" if ready == "WAIT_TRIGGER" else "entry_ready" if is_entry else "review_only"
        keep = ("ticker direction contract_symbol thesis_id trade_lane_candidate_id lab_rank lab_verdict "
                "final_action execution_authorized execution_can_grant_capital final_capital_permission "
                "morning_entry_action morning_execution_permission thesis__readiness thesis__readiness_reason "
                "thesis__trigger_age_sessions thesis_event thesis_trigger_level invalidation_price "
                "early_warning_invalidation_level contract_bid contract_ask contract_oi contract_volume "
                "selected_quote_timestamp_utc anticipated_valued_at_utc anticipated_evidence_status "
                "geometry_justification geometry_reason execution_lock_reason earnings_disclosure "
                "valuation_cost_basis").split()
        item = {k: row.get(k) for k in keep}
        item.update(source_row_ordinal=ordinal, group=group, target_spot=target, stock_reference=spot,
                    target_return=target_return, target_sessions=number(row.get("scenario_exit_sessions")),
                    invalidation_return=number(row.get("scenario_invalidation_return_on_premium")),
                    stall_return=number(row.get("scenario_stall_return_on_premium")),
                    entry_per_contract=round(number(row.get("valuation_entry_cost_usd_per_share"))*100, 2),
                    trigger_runway_fraction=runway, spread_pct_mid=spread, stress=stress,
                    automatic_execution_authorized=False,
                    source_execution_authorized=_truth(row.get("execution_authorized")))
        groups[group].append(item)
    for group in groups.values():
        group.sort(key=lambda d: (-(d["stress"]["combined_return"] if d["stress"]["combined_return"] is not None else -999),
                                  -(d["target_return"] if d["target_return"] is not None else -999), str(d["ticker"])))
    return {"schema": VERSION, "authority": "RESEARCH_DISPLAY_ONLY", "policy": POLICY,
            "population": len(rows), "groups": groups, "exclusions": exclusions,
            "counts": {k: len(v) for k,v in groups.items()},
            "disclosures": [
                "Screening thresholds are unvalidated research filters, not trading or capital rules.",
                "All prices are saved references. Confirmation may change premium, IV and remaining runway.",
                "Entry-ready means the saved published gate allows human review/sizing, not automatic execution.",
                "Waiting candidates have no confirmed trigger and no measured live-entry probability edge.",
                "Delay holds the median target fixed at twice the sessions. IV stress multiplies saved IV by 0.8.",
                "Target/invalidation/stall values use the median horizon. Invalidation loss is not a guaranteed stop fill.",
                "All long options can lose the whole premium. Scenarios are not EV or probabilities.",
                "Missing or nonreproducible stresses are explicit; no providers, fallback prices or pipeline are used."]}
