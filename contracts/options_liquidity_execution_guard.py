"""Fail-closed execution guard for the Options Liquidity Maturation layer.

The lifecycle calculator answers whether a thesis is still valid and whether
the exact selected contract is executable now. This module translates that
governed evidence into an execution ceiling. ``CONTINUE`` is deliberately not
an authorisation to trade: it only permits the existing Execution Gate to
apply its direction, contract, monetisability and quote controls.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


OLM_EXECUTION_GUARD_VERSION = "olm-execution-guard-v1"
SUPPORTED_LIFECYCLE_VERSIONS = frozenset({
    "OPTIONS-LIQUIDITY-LIFECYCLE-V1",
    "OPTIONS-LIQUIDITY-LIFECYCLE-V2",
})

CONTINUE_TRANSITIONS = frozenset({"EXECUTABLE_NOW", "GAP_CONFIRMATION_WITH_RUNWAY"})
REPAIR_TRANSITIONS = frozenset({"CONTRACT_REPRICE_REQUIRED"})
DEFER_TRANSITIONS = frozenset({
    "WAIT_FOR_PULLBACK",
    "GAP_CONFIRMATION_EXTENDED",
    "LIQUIDITY_STILL_PENDING",
    "EOD_PENDING_MORNING_REQUOTE",
    "LEGACY_LIFECYCLE_NOT_EVALUATED",
})

_CONTRACT_FIELDS = (
    "lifecycle_contract_version",
    "thesis_state",
    "liquidity_state",
    "morning_transition_state",
    "remaining_runway_state",
)


def _text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip().upper()
    return "" if text in {"", "NAN", "NONE", "NULL", "N/A"} else text


def _truth(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return _text(value) in {"TRUE", "1", "YES", "Y"}


@dataclass(frozen=True)
class GuardDecision:
    disposition: str
    reason: str
    state_consistent: bool
    execution_eligible: bool
    contract_present: bool
    guard_version: str = OLM_EXECUTION_GUARD_VERSION

    def as_fields(self) -> dict[str, Any]:
        return {
            "olm_guard_version": self.guard_version,
            "olm_guard_disposition": self.disposition,
            "olm_guard_reason": self.reason,
            "olm_guard_pass": self.execution_eligible,
            "olm_guard_state_consistent": self.state_consistent,
        }


def _decision(disposition: str, reason: str, *, consistent: bool,
              eligible: bool, present: bool) -> GuardDecision:
    return GuardDecision(
        disposition=disposition,
        reason=reason,
        state_consistent=consistent,
        execution_eligible=eligible,
        contract_present=present,
    )


def evaluate_olm_execution_guard(
    row: Mapping[str, Any],
    *,
    require_contract: bool = False,
) -> GuardDecision:
    """Return the OLM execution ceiling for one row.

    ``require_contract`` is enabled by the production batch gate. The default
    preserves direct legacy/research callers that pre-date OLM, while any row
    carrying OLM fields is governed regardless of this compatibility setting.
    """

    present = any(_text(row.get(field)) for field in _CONTRACT_FIELDS)
    if not present:
        if require_contract:
            return _decision(
                "MANUAL_REVIEW", "OLM_LIFECYCLE_REQUIRED",
                consistent=False, eligible=False, present=False,
            )
        return _decision(
            "CONTINUE", "LEGACY_DIRECT_CALL_NO_OLM_CONTRACT",
            consistent=True, eligible=True, present=False,
        )

    transition = _text(row.get("morning_transition_state"))
    thesis_state = _text(row.get("thesis_state"))
    runway_state = _text(row.get("remaining_runway_state"))
    liquidity_state = _text(row.get("liquidity_state"))
    lifecycle_version = _text(row.get("lifecycle_contract_version"))

    # Terminal evidence has absolute precedence over every contradictory field.
    if (transition == "THESIS_INVALIDATED"
            or thesis_state in {"INVALIDATED", "THESIS_INVALIDATED"}
            or runway_state == "THESIS_INVALIDATED"):
        return _decision(
            "BLOCK", "OLM_THESIS_INVALIDATED",
            consistent=transition == "THESIS_INVALIDATED",
            eligible=False, present=present,
        )
    if (transition == "MOVE_ALREADY_REALIZED"
            or thesis_state in {"TARGET_REALIZED", "MOVE_ALREADY_REALIZED"}
            or runway_state == "MOVE_ALREADY_REALIZED"):
        return _decision(
            "BLOCK", "OLM_MOVE_ALREADY_REALIZED",
            consistent=transition == "MOVE_ALREADY_REALIZED",
            eligible=False, present=present,
        )

    # A monitoring score claiming capital authority is contract corruption,
    # never a reason to continue or to size up.
    if _truth(row.get("maturation_execution_authority")):
        return _decision(
            "BLOCK", "OLM_MATURATION_AUTHORITY_VIOLATION",
            consistent=False, eligible=False, present=present,
        )

    if transition in REPAIR_TRANSITIONS:
        return _decision(
            "CONTRACT_REPAIR", f"OLM_{transition}",
            consistent=True, eligible=False, present=present,
        )
    if transition in DEFER_TRANSITIONS:
        return _decision(
            "MANUAL_REVIEW", f"OLM_{transition}",
            consistent=True, eligible=False, present=present,
        )
    if not transition:
        return _decision(
            "MANUAL_REVIEW", "OLM_TRANSITION_MISSING",
            consistent=False, eligible=False, present=present,
        )
    if transition not in CONTINUE_TRANSITIONS:
        return _decision(
            "BLOCK", f"OLM_TRANSITION_UNRECOGNISED:{transition}",
            consistent=False, eligible=False, present=present,
        )

    # Positive continuation requires one internally consistent, versioned,
    # current exact-contract assessment. No individual field can grant it.
    if lifecycle_version not in SUPPORTED_LIFECYCLE_VERSIONS:
        return _decision(
            "MANUAL_REVIEW",
            f"OLM_LIFECYCLE_VERSION_UNSUPPORTED:{lifecycle_version or 'MISSING'}",
            consistent=False, eligible=False, present=present,
        )
    if thesis_state != "ACTIVE":
        return _decision(
            "MANUAL_REVIEW",
            f"OLM_THESIS_STATE_NOT_ACTIVE:{thesis_state or 'MISSING'}",
            consistent=False, eligible=False, present=present,
        )
    if liquidity_state != "EXECUTABLE_NOW":
        return _decision(
            "MANUAL_REVIEW",
            f"OLM_LIQUIDITY_NOT_EXECUTABLE:{liquidity_state or 'MISSING'}",
            consistent=False, eligible=False, present=present,
        )
    if not _truth(row.get("executable_now")):
        return _decision(
            "MANUAL_REVIEW", "OLM_EXECUTABLE_FLAG_FALSE",
            consistent=False, eligible=False, present=present,
        )

    return _decision(
        "CONTINUE", f"OLM_{transition}",
        consistent=True, eligible=True, present=present,
    )


def action_is_within_guard(action: Any, decision: GuardDecision) -> bool:
    """Return whether an emitted action is equal to or safer than the ceiling."""

    action_text = _text(action)
    allowed = {
        "CONTINUE": {
            "BUY_NOW", "BUY_SMALL", "MANUAL_REVIEW", "CONTRACT_REPAIR", "BLOCK", "SKIP",
        },
        "MANUAL_REVIEW": {"MANUAL_REVIEW", "CONTRACT_REPAIR", "BLOCK", "SKIP"},
        "CONTRACT_REPAIR": {"CONTRACT_REPAIR", "BLOCK", "SKIP"},
        "BLOCK": {"BLOCK", "SKIP"},
    }
    return action_text in allowed.get(decision.disposition, set())
