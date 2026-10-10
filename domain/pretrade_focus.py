"""Advisory EOD focus for the next trading session.

Thesis completeness, selected-contract evidence, and current executability are
different facts.  This projection ranks review work; it neither removes a
candidate nor grants entry or capital authority.  A completed-session quote is
useful research evidence, never a live entry quote.
"""

from __future__ import annotations

import math
import json
from typing import Any, Mapping

from domain.volatility_budget import cumulative_expected_move_pct


POLICY_VERSION = "pretrade-focus-v1"
FOCUS_PRIMARY = "FOCUS_PRIMARY"
EVENING_THESIS_POLICY_VERSION = "evening-thesis-v1"
# An extreme target is sent to human review, never called invalid.  This is a
# conservative scenario-quality diagnostic, not a forecast probability.
TARGET_EXPECTED_MOVE_REVIEW_MULTIPLE = 3.0


def _cumulative_expected_move_pct(row: Mapping[str, Any], horizon: str) -> float | None:
    return cumulative_expected_move_pct(row, horizon)
EVENING_INPUT_FIELDS = (
    "pipeline_mode", "evening_thesis_bucket", "evening_thesis_reason",
    "evening_evidence_flags",
    "evening_next_condition", "canonical_direction", "direction",
    "signal_price", "invalidation_price", "invalidation_spot",
    "invalidation_state", "target_price", "target_price_source", "liquidity_thesis_state",
    "thesis_state", "selected_quote_dataset_id",
    "monetisability_quote_snapshot_id", "contract_symbol",
    "monetisability_contract_symbol", "contract_bid", "contract_ask",
    "selected_quote_timestamp_utc", "evidence_session_date",
    "direction_conflict_status", "direction_resolution_call_score",
    "direction_resolution_put_score", "direction_resolution_evidence_json",
    "monetisability_state",
    "contract_repair_required", "time_horizon",
    "expected_move_5d_fraction", "expected_move_10d_fraction",
    "expected_move_20d_fraction", "horizon_convention",
    "garch_expected_move_1_5d", "garch_expected_move_6_10d",
    "garch_expected_move_11_20d", "trigger_primary", "trigger_price",
    "wyckoff_execution_bias",
)
EVENING_EXPORT_FIELDS = (
    "evening_thesis_bucket", "evening_thesis_candidate",
    "evening_thesis_reason", "evening_evidence_flags", "evening_next_condition",
    "evening_thesis_authority", "evening_thesis_policy_version",
)
FOCUS_INPUT_FIELDS = (
    "direction", "canonical_direction", "invalidation_spot", "target_price",
    "signal_price", "invalidation_state", "target_state", "contract_symbol",
    "recommended_contract", "contract_bid", "contract_ask", "contract_dte",
    "dte", "selected_quote_timestamp_utc", "selected_quote_dataset_id",
    "monetisability_contract_symbol", "monetisability_quote_snapshot_id",
    "evidence_session_date", "monetisability_state",
    "direction_conflict_status", "trigger_go_eligible",
    "contract_repair_required", "contract_repair_status",
)
FOCUS_EXPORT_FIELDS = (
    "run_id", "ticker", "direction", "slate_rank", "structural_tier",
    "signal_price", "invalidation_spot", "target_price",
    "contract_symbol", "contract_bid", "contract_ask", "contract_dte",
    "selected_quote_timestamp_utc", "selected_quote_dataset_id",
    "monetisability_contract_symbol", "monetisability_quote_snapshot_id",
    "monetisability_state", "trigger_quality", "direction_conflict_status",
    "pretrade_thesis_state", "pretrade_contract_evidence_state",
    "pretrade_entry_quote_state", "pretrade_focus_lane",
    "pretrade_focus_priority", "pretrade_focus_candidate",
    "pretrade_focus_reason", "pretrade_focus_authority",
    "pretrade_focus_policy_version",
)


def _token(value: Any) -> str:
    if value is None:
        return ""
    result = str(value).strip()
    return "" if result.lower() in {"nan", "none", "null"} else result


def _number(value: Any) -> float | None:
    try:
        result = float(_token(value))
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _true(value: Any) -> bool:
    return _token(value).upper() in {"TRUE", "1", "YES"}


def project_pretrade_focus(row: Mapping[str, Any]) -> dict[str, Any]:
    """Return independent, non-authoritative EOD preparation fields.

    The primary focus lane requires a complete governed thesis, an observed
    exact-contract EOD quote, conservative EOD monetisability, a GO-eligible
    trigger, and no recorded direction conflict.  Other rows remain available
    in the full slate for development, repair, and human review.
    """
    side = _token(row.get("direction") or row.get("canonical_direction")).upper()
    invalidation = _number(row.get("invalidation_spot"))
    target = _number(row.get("target_price"))
    spot = _number(row.get("signal_price"))
    invalidation_state = _token(row.get("invalidation_state")).upper()
    target_state = _token(row.get("target_state")).upper()

    if side not in {"CALL", "PUT"}:
        thesis_state = "DIRECTION_REVIEW"
    elif invalidation_state != "AVAILABLE" or invalidation is None or invalidation <= 0:
        thesis_state = "INVALIDATION_REVIEW"
    elif target_state != "AVAILABLE" or target is None or target <= 0:
        thesis_state = "TARGET_REVIEW"
    elif spot is None or spot <= 0:
        thesis_state = "ENTRY_REFERENCE_REVIEW"
    elif not (
        (side == "CALL" and invalidation < spot < target)
        or (side == "PUT" and target < spot < invalidation)
    ):
        thesis_state = "THESIS_GEOMETRY_REVIEW"
    else:
        thesis_state = "READY_FOR_MORNING_THESIS_CHECK"

    symbol = _token(row.get("contract_symbol")) or _token(row.get("recommended_contract"))
    bid = _number(row.get("contract_bid"))
    ask = _number(row.get("contract_ask"))
    dte = _number(row.get("contract_dte"))
    if dte is None:
        dte = _number(row.get("dte"))
    quote_timestamp = _token(row.get("selected_quote_timestamp_utc"))
    quote_dataset_id = _token(row.get("selected_quote_dataset_id"))
    monetisation_symbol = _token(row.get("monetisability_contract_symbol"))
    monetisation_dataset_id = _token(row.get("monetisability_quote_snapshot_id"))
    if not symbol:
        contract_state = "CONTRACT_SELECTION_REVIEW"
    elif (
        bid is None or ask is None or not quote_timestamp or not quote_dataset_id
        or not monetisation_symbol or not monetisation_dataset_id
    ):
        contract_state = "EOD_QUOTE_EVIDENCE_REVIEW"
    elif (
        symbol != monetisation_symbol
        or quote_dataset_id != monetisation_dataset_id
    ):
        contract_state = "CONTRACT_EVIDENCE_CONFLICT_REVIEW"
    elif bid <= 0 or ask < bid or dte is None or dte <= 0:
        contract_state = "CONTRACT_GEOMETRY_REVIEW"
    else:
        contract_state = "COMPLETED_SESSION_QUOTE_OBSERVED"

    # L5 (ACK 7 Oct 2026): the focus lane follows the decision owner - the anticipated move's pays state - not
    # monetisability (intrinsic at expiry, AUDIT). A7: a prior-session quote is an aged quote, not a conflict;
    # only the exact-contract identity (symbol + quote dataset) is checked above.
    pays = _token(row.get("anticipated_pays_state")).upper()
    conflict = _token(row.get("direction_conflict_status")).upper()
    trigger = _true(row.get("trigger_go_eligible"))
    repair_required = _token(row.get("contract_repair_required")).upper()
    repair_status = _token(row.get("contract_repair_status")).upper()
    ready = thesis_state == "READY_FOR_MORNING_THESIS_CHECK"
    quote_observed = contract_state == "COMPLETED_SESSION_QUOTE_OBSERVED"
    if not ready:
        lane, priority = "THESIS_EVIDENCE_REVIEW", 8
    elif not quote_observed:
        lane, priority = "CONTRACT_EVIDENCE_REVIEW", 7
    elif pays == "PAYS" and trigger and conflict == "MITIGATED_REQUIRES_CONFIRMATION":
        lane, priority = "FOCUS_DIRECTION_CONFIRMATION", 2
    elif pays == "PAYS" and trigger and conflict != "NO_CONFLICT":
        lane, priority = "FOCUS_DIRECTION_EVIDENCE_REVIEW", 3
    elif pays == "PAYS" and trigger and repair_required == "TRUE":
        lane, priority = "FOCUS_CONTRACT_REPAIR", 5
    elif pays == "PAYS" and trigger and repair_required != "FALSE":
        lane, priority = "CONTRACT_REPAIR_EVIDENCE_REVIEW", 7
    elif pays == "PAYS" and trigger:
        lane, priority = FOCUS_PRIMARY, 1
    elif pays == "PAYS":
        lane, priority = "FOCUS_TRIGGER_DEVELOPING", 4
    elif pays == "DOES_NOT_PAY_AT_ANTICIPATED_TIME":
        lane, priority = "WATCH_MOVE_DOES_NOT_PAY", 6
    else:
        lane, priority = "OPTION_VALUE_REVIEW", 7

    return {
        "pretrade_thesis_state": thesis_state,
        "pretrade_contract_evidence_state": contract_state,
        "pretrade_entry_quote_state": "NOT_EVALUATED_AT_EOD",
        "pretrade_focus_lane": lane,
        "pretrade_focus_priority": priority,
        "pretrade_focus_candidate": lane == FOCUS_PRIMARY,
        "pretrade_focus_reason": (
            f"thesis={thesis_state}; contract={contract_state}; "
            f"pays={pays or 'MISSING'}; "
            f"contract_repair={repair_required or 'MISSING'}"
            f"/{repair_status or 'MISSING'}; "
            f"trigger={'GO' if trigger else 'PENDING'}; "
            f"direction_conflict={conflict or 'MISSING'}; "
            "entry quote and Morning thesis not yet validated"
        ),
        "pretrade_focus_authority": "ADVISORY_ONLY",
        "pretrade_focus_policy_version": POLICY_VERSION,
    }


def project_evening_thesis(row: Mapping[str, Any]) -> dict[str, Any]:
    """Reconcile EOD evidence into a *preparation* bucket, not trade authority.

    The Morning process owns the subsequent change check.  In particular it
    must not recalculate this frozen EOD conclusion from Morning observations.
    A developing or contradictory ticker stays visible with its next condition.
    """
    mode = _token(row.get("pipeline_mode")).upper()
    morning_observed = _token(row.get("morning_data_state")).upper() == "AVAILABLE"
    if morning_observed or mode not in {"EOD", "LIVE_EOD", "INTRADAY_EOD"}:
        frozen = _token(row.get("evening_thesis_bucket")) or "EOD_NOT_EVALUATED"
        return {
            "evening_thesis_bucket": frozen,
            "evening_thesis_candidate": frozen == "EOD_ACTION_SETUP_READY",
            "evening_thesis_reason": _token(row.get("evening_thesis_reason")) or "Frozen Evening decision unavailable",
            "evening_evidence_flags": _token(row.get("evening_evidence_flags")) or "NOT_EVALUATED",
            "evening_next_condition": _token(row.get("evening_next_condition")) or "Compare the Morning thesis with Evening evidence",
            "evening_thesis_authority": "ADVISORY_PENDING_MORNING_CHECK",
            "evening_thesis_policy_version": EVENING_THESIS_POLICY_VERSION,
        }

    side = _token(row.get("canonical_direction") or row.get("direction")).upper()
    spot = _number(row.get("signal_price"))
    stop = _number(row.get("invalidation_price"))
    if stop is None:
        stop = _number(row.get("invalidation_spot"))
    target = _number(row.get("target_price"))
    target_source = _token(row.get("target_price_source")).upper()
    terminal = _token(row.get("liquidity_thesis_state") or row.get("thesis_state")).upper()
    quote_id = _token(row.get("selected_quote_dataset_id"))
    economics_quote_id = _token(row.get("monetisability_quote_snapshot_id"))
    symbol = _token(row.get("contract_symbol"))
    economics_symbol = _token(row.get("monetisability_contract_symbol"))
    bid = _number(row.get("contract_bid"))
    ask = _number(row.get("contract_ask"))
    quote_time = _token(row.get("selected_quote_timestamp_utc"))
    session = _token(row.get("evidence_session_date"))
    flags: list[str] = []
    if target_source == "TARGET_3R":
        flags.append("TARGET_GENERATED_3R_SCENARIO")
    if _true(row.get("contract_repair_required")):
        flags.append("CONTRACT_REPAIR_REQUIRED")
    # L5 (ACK 7 Oct 2026): the evening thesis reads the pays state, not monetisability (AUDIT).
    pays = _token(row.get("anticipated_pays_state")).upper()
    if pays and pays != "PAYS":
        flags.append(f"OPTION_{pays}")
    if quote_id and economics_quote_id and quote_id != economics_quote_id:
        flags.append("QUOTE_ID_MISMATCH")
    horizon = _token(row.get("time_horizon")).upper()
    expected_move = _cumulative_expected_move_pct(row, horizon)
    target_move = abs(target / spot - 1.0) * 100.0 if target and spot else None
    if target_move is not None and expected_move and target_move > TARGET_EXPECTED_MOVE_REVIEW_MULTIPLE * expected_move:
        flags.append("TARGET_BEYOND_EXPECTED_MOVE_REVIEW_BAND")
    # Phase 5.3 (ACK 8 Oct 2026): price confirmation is the thesis's own accepted break / held retest on its own
    # trigger level (thesis__readiness, owned by Discovery's event step) - not a state category plus a spot cross.
    readiness = _token(row.get("thesis__readiness")).upper() or "NOT_RECORDED"
    trigger_price = _number(row.get("trigger_price"))
    trigger_confirmed = readiness == "READY_FOR_HUMAN_REVIEW"
    if not trigger_confirmed:
        flags.append("TRIGGER_NOT_PRICE_CONFIRMED")
    # XLU-D10 (ACK 2 Oct 2026): the trade is categorised by Phase and Event; the legacy
    # Wyckoff OBSERVE_ONLY bias is not a decision. Missing alignment is never neutral.
    structure = _token(row.get("thesis_structure_alignment")).upper() or "NOT_EVALUATED"
    category = _token(row.get("thesis_category")) or "MISSING"
    if structure != "ALIGNED":
        flags.append("NO_BEHAVIOURAL_EVENT_ON_TRADE_SIDE")

    def result(bucket: str, reason: str, next_condition: str) -> dict[str, Any]:
        return {
            "evening_thesis_bucket": bucket,
            "evening_thesis_candidate": bucket == "EOD_ACTION_SETUP_READY",
            "evening_thesis_reason": reason,
            "evening_evidence_flags": "|".join(flags) or "NONE",
            "evening_next_condition": next_condition,
            "evening_thesis_authority": "ADVISORY_PENDING_MORNING_CHECK",
            "evening_thesis_policy_version": EVENING_THESIS_POLICY_VERSION,
        }

    if terminal in {"THESIS_INVALIDATED", "INVALIDATED"}:
        return result("EOD_THESIS_INVALIDATED", "Governed thesis explicitly invalidated", "Rebuild a new thesis; do not revive this one by quote refresh")
    if side not in {"CALL", "PUT"} or not spot or not stop or not target or _token(row.get("invalidation_state")).upper() != "AVAILABLE":
        return result("EOD_EVIDENCE_REVIEW", "Direction, reference price, target or governed invalidation missing", "Resolve the missing thesis evidence")
    valid_geometry = (stop < spot < target) if side == "CALL" else (target < spot < stop)
    if not valid_geometry:
        return result("EOD_EVIDENCE_REVIEW", "Thesis geometry does not reconcile", "Recheck direction, target and invalidation; do not auto-flip direction")
    if (
        not symbol or not economics_symbol or symbol != economics_symbol
        or not quote_id or not economics_quote_id or quote_id != economics_quote_id
        or not quote_time or (session and not quote_time.startswith(session))
        or bid is None or bid <= 0 or ask is None or ask < bid
    ):
        return result("EOD_EVIDENCE_REVIEW", "Selected-contract quote and monetisability evidence do not reconcile", "Recover the exact completed-session contract observation")

    direction_conflict = _token(row.get("direction_conflict_status")).upper()
    aligned_score = _number(row.get("direction_resolution_call_score" if side == "CALL" else "direction_resolution_put_score")) or 0.0
    opposing_score = _number(row.get("direction_resolution_put_score" if side == "CALL" else "direction_resolution_call_score")) or 0.0
    raw_direction_evidence = _token(row.get("direction_resolution_evidence_json"))
    try:
        evidence = json.loads(raw_direction_evidence) if raw_direction_evidence else []
        if not isinstance(evidence, list):
            raise ValueError("direction evidence is not a list")
    except (ValueError, TypeError):
        return result("EOD_EVIDENCE_REVIEW", "Independent direction evidence cannot be parsed", "Repair the direction-evidence record")
    price_flow_sides = {
        _token(item.get("side")).upper()
        for item in evidence if isinstance(item, dict)
        and _token(item.get("family")).upper() == "PRICE_FLOW"
        and _token(item.get("direction_independent")).upper() in {"TRUE", "1", "YES"}
    }
    if direction_conflict not in {"", "NO_CONFLICT"} or opposing_score > aligned_score or any(s in {"CALL", "PUT"} and s != side for s in price_flow_sides):
        flags.append("OPPOSING_DIRECTION_EVIDENCE")
        other_side = "PUT" if side == "CALL" else "CALL"
        return result("EOD_DIRECTION_EVIDENCE_REVIEW", f"Governed {side} thesis has unresolved or opposing {other_side} evidence", "Investigate Vanguard's price/trend proxy alongside the other evidence; preserve the governed direction until explicitly revised")
    if side not in price_flow_sides:
        return result("EOD_DIRECTION_EVIDENCE_REVIEW", "Aligned Vanguard price/trend proxy evidence is missing", "Confirm the ticker direction with additional independently sourced evidence")

    if pays not in {"PAYS", "DOES_NOT_PAY_AT_ANTICIPATED_TIME"}:
        return result("EOD_EVIDENCE_REVIEW", "The option value at the anticipated move is not computed", "Complete the anticipated-move valuation for the contract")
    if _true(row.get("contract_repair_required")):
        return result("EOD_CONTRACT_WATCH", "Selected contract needs repair but ticker thesis remains", "Review the same-direction contract family")
    if pays != "PAYS":
        return result("EOD_CONTRACT_WATCH", "The anticipated move does not pay this contract; ticker thesis retained", "Choose a contract the move pays, or monitor the contract family")

    if target_source == "TARGET_3R":
        return result("EOD_TARGET_FEASIBILITY_REVIEW", "The target is a generated 3R scenario, not an independently supported price level", "Find a supported target before using target-based option profit as monetisability evidence")

    target_move = abs(target / spot - 1.0) * 100.0
    if expected_move is None or expected_move <= 0:
        return result("EOD_TARGET_FEASIBILITY_REVIEW", "Horizon-matched expected move is missing", "Source or compute the expected move for the stated horizon")
    if target_move > TARGET_EXPECTED_MOVE_REVIEW_MULTIPLE * expected_move:
        return result("EOD_TARGET_FEASIBILITY_REVIEW", f"Target move {target_move:.1f}% exceeds the supported {horizon} scenario", "Review target plausibility before using target-based option profit")

    structure_aligned = structure == "ALIGNED"
    if not trigger_confirmed or not structure_aligned or aligned_score <= 0:
        next_level = f"{side} acceptance beyond the thesis trigger {trigger_price:g}" if trigger_price is not None else "the thesis trigger level"
        return result("EOD_TRIGGER_WATCH", f"Thesis retained; thesis_readiness={readiness}, structure={category}", f"Watch for {next_level} and aligned independent evidence")

    # Output-trust item 3 (ACK decision 1, 9 Oct 2026): an activated thesis is ready only when its geometry from the
    # planned entry is justified by the setup's measured hit rate (or unmeasured, labelled). Unrecorded is not justified.
    geometry = _token(row.get("geometry_justification")).upper() or "NOT_RECORDED"
    if geometry in {"GEOMETRY_NOT_JUSTIFIED", "INVALID_GEOMETRY", "NOT_RECORDED"}:
        flags.append(f"GEOMETRY_{geometry}" if geometry == "NOT_RECORDED" else geometry)
        return result("EOD_GEOMETRY_REVIEW", f"Thesis activated; geometry {geometry} from the planned entry: "
                      f"{_token(row.get('geometry_reason')) or 'reason not recorded'}",
                      "Not GO: needs the setup's measured hit rate at or above break-even; target and invalidation are never moved")
    return result("EOD_ACTION_SETUP_READY", "Target, exact contract, direction evidence and observed trigger reconcile", "Morning checks thesis change and current entry conditions; human decides execution")
