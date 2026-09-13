"""Derived opportunity tier for the Lab book.

AVS-FIX-001 W3.5, implementing AVS-THS-001 §4.

A tier describes **the quality and completeness of the evidence** for an
opportunity, so the Lab can order what it already has. It is derived, never
scored: every boundary traces to a governed column with a named authority, so
the tier is explainable and cannot quietly become a second gate.

**It grants nothing.** `derive_tier` is a pure function of one row and returns
two strings. It writes no permission field, reads `final_action` only to leave
it alone, and the Execution Gate remains the sole writer of capital authority.
A row can be TIER_1 and still be MANUAL_REVIEW; a row can be BLOCK here and
still carry whatever action the gate gave it. That is asserted by the authority
tests in tests/test_avs_fix_001_w35_opportunity_tier.py.

Tier 1 may legitimately be empty. That is information, not a fault.
"""

from __future__ import annotations

import math
from typing import Any, Mapping

from domain.quote_units import resolve_spread

TIER_POLICY_VERSION = "opportunity-tier-v1-ths001-s4"

TIER_1 = "TIER_1"
TIER_2 = "TIER_2"
TIER_3 = "TIER_3"
ARMED = "ARMED"
WATCH = "WATCH"
BLOCK = "BLOCK"

#: The Lab sorts by this order, then by underlying R:R within a tier.
TIER_SORT_ORDER = (TIER_1, TIER_2, TIER_3, ARMED, WATCH, BLOCK)

#: THS-001 §4 boundaries. Named here rather than inline so a change is a
#: reviewable edit to one place, and so the Lab can print the policy it used.
RR_TIER_1_MIN = 2.0
RR_TIER_2_MIN = 1.5
SPREAD_TIER_2_MAX = 0.25
DTE_HOLD_MULTIPLE = 2.0

_DIRECTED = {"CALL", "PUT"}
_MONETISABLE_STATES = {"MONETISABLE", "LIMITED"}


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and math.isnan(value):
        return ""
    return str(value).strip()


def _upper(value: Any) -> str:
    return _text(value).upper()


def _number(value: Any) -> float | None:
    try:
        if value is None:
            return None
        text = _text(value).replace("%", "")
        if not text:
            return None
        result = float(text)
        return None if math.isnan(result) or math.isinf(result) else result
    except (TypeError, ValueError):
        return None


def _first(row: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        value = row.get(key)
        if _text(value):
            return value
    return None


def _tier_spread_fraction(row: Mapping[str, Any]) -> float | None:
    """Adapt the frozen opportunity-tier-v1 `spread_pct` contract.

    Despite its name, v1 documented this field as a fraction.  Supplying the
    unit here makes that historical contract explicit; all new writers use
    spread_fraction_mid and never rely on this adapter.
    """
    canonical = resolve_spread(row)
    if canonical.spread_fraction_mid is not None:
        return canonical.spread_fraction_mid
    # Ambiguous legacy fields are intentionally not guessed.  Their producer
    # must disclose spread_unit or project a canonical spread field.
    return None


def _hard_veto(row: Mapping[str, Any]) -> str:
    """THS-001 §4's BLOCK list, unchanged. Returns the reason, or "".

    Order matters only for which reason is reported; any one of them blocks.
    """
    direction = _upper(_first(row, "canonical_direction", "governed_direction",
                              "final_direction", "direction"))
    if direction not in _DIRECTED:
        return "DIRECTION_NOT_RESOLVED"

    if not _text(_first(row, "governed_direction_record_sha256",
                        "direction_lineage_hash")):
        return "DIRECTION_LINEAGE_HASH_MISSING"

    invalidation_state = _upper(row.get("invalidation_state"))
    invalidation = _number(_first(row, "invalidation_price", "invalidation_spot"))
    if invalidation_state and invalidation_state != "AVAILABLE":
        return "GOVERNED_INVALIDATION_NOT_AVAILABLE"
    if invalidation is None or invalidation <= 0:
        return "GOVERNED_INVALIDATION_MISSING"

    target = _number(_first(row, "structural_target", "target_price", "target_spot"))
    if target is None or target <= 0:
        return "STRUCTURAL_TARGET_UNRESOLVED"

    # Correct side: a CALL target is above its invalidation, a PUT's below.
    if direction == "CALL" and target <= invalidation:
        return "TARGET_ON_WRONG_SIDE_OF_INVALIDATION"
    if direction == "PUT" and target >= invalidation:
        return "TARGET_ON_WRONG_SIDE_OF_INVALIDATION"

    viability = _upper(row.get("execution_viability_state"))
    if viability in {"PATHOLOGICAL_SPREAD", "NO_LIQUIDITY", "INVALID_QUOTE",
                     "EXPIRED_CONTRACT", "STALE_DATA"}:
        return f"EXECUTION_VIABILITY_{viability}"

    spread = _tier_spread_fraction(row)
    if spread is not None and spread > SPREAD_TIER_2_MAX:
        return "SPREAD_ABOVE_REVIEWABLE_CEILING"

    return ""


def _tier_2_weaknesses(row: Mapping[str, Any]) -> list[str]:
    """THS-001 §4's named Tier-2 shortfalls, each traced to a governed column.

    A criterion that cannot be evaluated because its column is absent is itself
    a weakness — `UNEVALUABLE_<criterion>` — never silence. TIER_1 means
    "everything the pipeline can verify is present and strong", so a missing
    column must not be able to promote a row by leaving a check unrun. On the
    pre-AVS-FIX-001 book of run 20260905_151448 this is not hypothetical:
    `trigger_state`, `contract_dte` and `monetisability_state_timevalue` were
    all absent, and without this rule 115 rows would have read TIER_1 against
    THS-001's own expectation of "tens, not hundreds".
    """
    weaknesses: list[str] = []

    rr = _number(_first(row, "rr_underlying", "rr_options", "rr_predicted",
                        "risk_reward_display"))
    if rr is None:
        weaknesses.append("UNEVALUABLE_RISK_REWARD")
    elif RR_TIER_2_MIN <= rr < RR_TIER_1_MIN:
        weaknesses.append(f"RR_{rr:.2f}_BELOW_2.0")

    intrinsic = _upper(row.get("monetisability_state"))
    timevalue = _upper(row.get("monetisability_state_timevalue"))
    if intrinsic == "LIMITED":
        weaknesses.append("MONETISABILITY_LIMITED_NOT_MONETISABLE")
    elif intrinsic != "MONETISABLE" and timevalue == "MONETISABLE":
        # W3.4's whole purpose: monetisable on time value alone is a named
        # weakness, not an exclusion.
        weaknesses.append("MONETISABLE_ON_TIMEVALUE_ONLY")
    elif not timevalue or timevalue == "NOT_EVALUATED":
        # THS-001 Tier 1 requires MONETISABLE under BOTH valuations.
        weaknesses.append("UNEVALUABLE_TIMEVALUE_MONETISABILITY")

    spread = _tier_spread_fraction(row)
    horizon_band = _number(row.get("horizon_spread_limit"))
    if horizon_band is None:
        horizon = _upper(_first(row, "time_horizon", "horizon_bucket"))
        horizon_band = 0.15 if horizon.startswith("1_5") else 0.25
    if spread is None:
        weaknesses.append("UNEVALUABLE_SPREAD")
    elif horizon_band < spread <= SPREAD_TIER_2_MAX:
        weaknesses.append(f"SPREAD_{spread:.2%}_ABOVE_HORIZON_BAND")

    trigger = _upper(_first(row, "trigger_state", "trigger_status", "eod_status"))
    if not trigger:
        weaknesses.append("UNEVALUABLE_TRIGGER_STATE")
    elif trigger not in {"TRIGGER_READY", "THESIS_READY"}:
        weaknesses.append(f"TRIGGER_{trigger}")

    dte = _number(row.get("contract_dte"))
    hold = _number(_first(row, "planned_hold_sessions", "hold_sessions", "hold_days"))
    if dte is None or hold is None or hold <= 0:
        weaknesses.append("UNEVALUABLE_DTE_VS_HOLD")
    else:
        required = DTE_HOLD_MULTIPLE * hold
        if dte < required:
            weaknesses.append(f"DTE_{dte:.0f}_BELOW_2X_HOLD_{required:.0f}")

    return weaknesses


def _armed_promoter(row: Mapping[str, Any]) -> str:
    """The named condition that would flip an ARMED row. "" if there is none.

    THS-001 §4 is explicit that ARMED without a named promoter is a bin, not a
    state. A row with no promoter is WATCH.
    """
    alternative = _text(row.get("best_alternative_symbol"))
    if alternative:
        spread = _number(row.get("best_alternative_spread_pct"))
        if spread is not None:
            return f"ALTERNATIVE_CONTRACT_AVAILABLE:{alternative}@{spread:.2%}"
        return f"ALTERNATIVE_CONTRACT_AVAILABLE:{alternative}"

    if _upper(row.get("contract_repair_status")) in {
        "CONTRACT_REPAIR_REQUIRED", "CONTRACT_REPAIR_AVAILABLE"
    }:
        return "CONTRACT_REPAIR_ROUTE_AVAILABLE"

    trigger = _upper(_first(row, "trigger_state", "trigger_status"))
    if trigger in {"REPAIR_AT_OPEN", "TRIGGER_PENDING", "AWAITING_TRIGGER"}:
        return f"TRIGGER_PENDING:{trigger}"

    iv_rank = _number(_first(row, "iv_rank", "iv_percentile", "ivp_252d"))
    if iv_rank is not None and iv_rank >= 75:
        return f"IV_RANK_{iv_rank:.0f}_ELEVATED_A_FALL_WOULD_REPRICE"

    return ""


def derive_tier(row: Mapping[str, Any]) -> tuple[str, str]:
    """Return (tier, tier_reason) for one governed row.

    ADVISORY. It grants no permission and removes none. `final_action` is never
    read for a decision and never written.
    """

    veto = _hard_veto(row)
    if veto:
        return BLOCK, veto

    intrinsic = _upper(row.get("monetisability_state"))
    timevalue = _upper(row.get("monetisability_state_timevalue"))
    viability = _upper(row.get("execution_viability_state"))
    monetisable = intrinsic in _MONETISABLE_STATES or timevalue in _MONETISABLE_STATES

    if not monetisable:
        # Not monetisable today. ARMED only with a named promoting condition;
        # otherwise WATCH.
        if intrinsic == "DATA_MISSING" or viability == "DATA_MISSING":
            promoter = _armed_promoter(row)
            if promoter:
                return ARMED, promoter
            return WATCH, "DATA_MISSING_AWAITING_RE_RESOLUTION"
        promoter = _armed_promoter(row)
        if promoter:
            return ARMED, promoter
        return WATCH, "EQUITY_VALID_OPTIONS_NOT_MONETISABLE_NO_PROMOTER"

    weaknesses = _tier_2_weaknesses(row)
    if not weaknesses:
        return TIER_1, "ALL_GOVERNED_EVIDENCE_PRESENT_AND_STRONG"
    if len(weaknesses) == 1:
        return TIER_2, weaknesses[0]
    return TIER_3, ";".join(weaknesses)


def tier_fields(row: Mapping[str, Any]) -> dict[str, Any]:
    """The two advisory columns, plus the policy version that produced them."""
    tier, reason = derive_tier(row)
    return {
        "opportunity_tier": tier,
        "opportunity_tier_reason": reason,
        "opportunity_tier_authority": "ADVISORY_ONLY",
        "opportunity_tier_policy_version": TIER_POLICY_VERSION,
    }


def tier_sort_key(row: Mapping[str, Any]) -> tuple[int, float]:
    """Lab ordering: tier first, then underlying R:R descending within a tier."""
    tier = _upper(row.get("opportunity_tier")) or derive_tier(row)[0]
    try:
        rank = TIER_SORT_ORDER.index(tier)
    except ValueError:
        rank = len(TIER_SORT_ORDER)
    rr = _number(_first(row, "rr_underlying", "rr_options", "rr_predicted"))
    return (rank, -(rr if rr is not None else 0.0))
