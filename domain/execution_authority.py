"""Pure execution-eligibility and capital-authority policy.

``BUY_NOW`` and ``BUY_SMALL`` are trader workflow recommendations.  They do
not place an order, size an account or grant capital authority.  This module
owns that distinction and the ordering of execution ceilings; adapters own
quotes, persistence and UI vocabulary.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping


EXECUTION_AUTHORITY_POLICY_VERSION = "execution-authority-v1"


class ExecutionAction(str, Enum):
    BUY_NOW = "BUY_NOW"
    BUY_SMALL = "BUY_SMALL"
    MANUAL_REVIEW = "MANUAL_REVIEW"
    CONTRACT_REPAIR = "CONTRACT_REPAIR"
    BLOCK = "BLOCK"
    SKIP = "SKIP"


class ExecutionEligibility(str, Enum):
    ELIGIBLE_NOW = "ELIGIBLE_NOW"
    ELIGIBLE_LIMITED = "ELIGIBLE_LIMITED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    CONTRACT_REPAIR_REQUIRED = "CONTRACT_REPAIR_REQUIRED"
    NOT_ELIGIBLE = "NOT_ELIGIBLE"


class CapitalPermission(str, Enum):
    HUMAN_APPROVAL_REQUIRED = "HUMAN_APPROVAL_REQUIRED"
    REVIEW_ONLY = "REVIEW_ONLY"
    NO = "NO"


_ACTION_POLICY = {
    ExecutionAction.BUY_NOW: (
        ExecutionEligibility.ELIGIBLE_NOW,
        CapitalPermission.HUMAN_APPROVAL_REQUIRED,
    ),
    ExecutionAction.BUY_SMALL: (
        ExecutionEligibility.ELIGIBLE_LIMITED,
        CapitalPermission.HUMAN_APPROVAL_REQUIRED,
    ),
    ExecutionAction.MANUAL_REVIEW: (
        ExecutionEligibility.REVIEW_REQUIRED,
        CapitalPermission.REVIEW_ONLY,
    ),
    ExecutionAction.CONTRACT_REPAIR: (
        ExecutionEligibility.CONTRACT_REPAIR_REQUIRED,
        CapitalPermission.REVIEW_ONLY,
    ),
    ExecutionAction.BLOCK: (
        ExecutionEligibility.NOT_ELIGIBLE,
        CapitalPermission.NO,
    ),
    ExecutionAction.SKIP: (
        ExecutionEligibility.NOT_ELIGIBLE,
        CapitalPermission.NO,
    ),
}


_ALLOWED_BY_CEILING = {
    ExecutionAction.BUY_NOW: frozenset(ExecutionAction),
    ExecutionAction.BUY_SMALL: frozenset({
        ExecutionAction.BUY_SMALL,
        ExecutionAction.MANUAL_REVIEW,
        ExecutionAction.CONTRACT_REPAIR,
        ExecutionAction.BLOCK,
        ExecutionAction.SKIP,
    }),
    ExecutionAction.MANUAL_REVIEW: frozenset({
        ExecutionAction.MANUAL_REVIEW,
        ExecutionAction.CONTRACT_REPAIR,
        ExecutionAction.BLOCK,
        ExecutionAction.SKIP,
    }),
    ExecutionAction.CONTRACT_REPAIR: frozenset({
        ExecutionAction.CONTRACT_REPAIR,
        ExecutionAction.BLOCK,
        ExecutionAction.SKIP,
    }),
    ExecutionAction.BLOCK: frozenset({ExecutionAction.BLOCK, ExecutionAction.SKIP}),
    ExecutionAction.SKIP: frozenset({ExecutionAction.SKIP}),
}


_ADVISORY_AUTHORITY_FIELDS = (
    "macro_capital_authority",
    "ev3_capital_authority",
    "ms_authority",
    "ms_profile_authority",
)
_ADVISORY_BOOLEAN_FIELDS = (
    "ms_can_grant_capital",
    "ms_profile_can_grant_capital",
    "maturation_execution_authority",
)


def _upper(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip().upper()
    return "" if text in {"", "NAN", "NONE", "NULL", "N/A"} else text


def _truth(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return _upper(value) in {"1", "TRUE", "YES", "Y", "ON"}


@dataclass(frozen=True, slots=True)
class ExecutionAuthorityDecision:
    action: str
    reason: str
    eligibility: str
    final_capital_permission: str
    human_approval_required: bool
    execution_authorized: bool = False
    can_grant_capital: bool = False
    policy_version: str = EXECUTION_AUTHORITY_POLICY_VERSION

    def as_fields(self) -> dict[str, Any]:
        return {
            "final_action": self.action,
            "gate_reason": self.reason,
            "execution_eligibility_state": self.eligibility,
            "execution_authority_ceiling": self.action,
            "execution_authority_source": "FINAL_EXECUTION_GATE",
            "execution_authority_policy_version": self.policy_version,
            "final_capital_permission": self.final_capital_permission,
            "execution_requires_human_approval": self.human_approval_required,
            "execution_authorized": self.execution_authorized,
            "execution_can_grant_capital": self.can_grant_capital,
        }


def action_is_within_execution_ceiling(
    action: ExecutionAction | str,
    ceiling: ExecutionAction | str,
) -> bool:
    try:
        proposed = ExecutionAction(_upper(action))
        maximum = ExecutionAction(_upper(ceiling))
    except ValueError:
        return False
    return proposed in _ALLOWED_BY_CEILING[maximum]


def advisory_authority_violations(payload: Mapping[str, Any]) -> tuple[str, ...]:
    """Identify an advisory subsystem attempting to grant capital."""

    violations: list[str] = []
    for field in _ADVISORY_AUTHORITY_FIELDS:
        value = _upper(payload.get(field))
        if value and value not in {"ADVISORY_ONLY", "NONE"}:
            violations.append(f"{field}={value}")
    for field in _ADVISORY_BOOLEAN_FIELDS:
        if _truth(payload.get(field)):
            violations.append(f"{field}=TRUE")
    return tuple(violations)


def decide_execution_authority(
    action: ExecutionAction | str,
    reason: str,
    *,
    evidence: Mapping[str, Any] | None = None,
) -> ExecutionAuthorityDecision:
    """Convert a recommendation into a governed, human-authorised decision."""

    try:
        resolved = ExecutionAction(_upper(action))
    except ValueError as error:
        raise ValueError(f"unknown execution action: {action}") from error
    violations = advisory_authority_violations(evidence or {})
    resolved_reason = str(reason or "UNSPECIFIED")
    if violations:
        resolved = ExecutionAction.BLOCK
        resolved_reason = "ADVISORY_AUTHORITY_VIOLATION:" + "|".join(violations)
    eligibility, permission = _ACTION_POLICY[resolved]
    return ExecutionAuthorityDecision(
        action=resolved.value,
        reason=resolved_reason,
        eligibility=eligibility.value,
        final_capital_permission=permission.value,
        human_approval_required=resolved in {
            ExecutionAction.BUY_NOW,
            ExecutionAction.BUY_SMALL,
        },
    )


def govern_execution_result(
    payload: Mapping[str, Any],
    *,
    action: ExecutionAction | str,
    reason: str,
) -> dict[str, Any]:
    governed = dict(payload)
    governed.update(
        decide_execution_authority(action, reason, evidence=governed).as_fields()
    )
    return governed


def execution_authority_contract_violations(
    payload: Mapping[str, Any],
) -> tuple[str, ...]:
    """Validate a stamped final-gate baton without re-adjudicating the trade.

    Legacy rows without a policy version remain readable.  Once the v1 baton
    is present, downstream consumers must fail closed on any contradiction.
    """

    if not _upper(payload.get("execution_authority_policy_version")):
        return ()
    action = _upper(payload.get("final_action"))
    try:
        expected = decide_execution_authority(
            action, str(payload.get("gate_reason") or "UNSPECIFIED"),
            evidence=payload,
        )
    except ValueError:
        return (f"final_action={action or 'MISSING'}",)
    expected_fields = expected.as_fields()
    checks = (
        "execution_eligibility_state",
        "execution_authority_ceiling",
        "execution_authority_source",
        "execution_authority_policy_version",
        "final_capital_permission",
        "execution_requires_human_approval",
        "execution_authorized",
        "execution_can_grant_capital",
    )
    violations: list[str] = []
    for field in checks:
        actual = payload.get(field)
        wanted = expected_fields[field]
        if isinstance(wanted, bool):
            matches = _truth(actual) is wanted
        else:
            matches = _upper(actual) == _upper(wanted)
        if not matches:
            violations.append(f"{field}={actual!r}:EXPECTED={wanted!r}")
    return tuple(violations)


def morning_validation_authority_fields(verdict: str) -> dict[str, Any]:
    """Return the non-capital authority contract for Morning validation."""

    state = _upper(verdict)
    permission = (
        CapitalPermission.HUMAN_APPROVAL_REQUIRED
        if state == "GO"
        else CapitalPermission.REVIEW_ONLY
        if state == "FLAG"
        else CapitalPermission.NO
    )
    return {
        "morning_authority_state": (
            "MORNING_VALIDATED" if state == "GO"
            else "MORNING_REVIEW_REQUIRED" if state == "FLAG"
            else "MORNING_NOT_ELIGIBLE"
        ),
        "morning_can_grant_capital": False,
        "final_capital_permission": permission.value,
        "execution_authorized": False,
        "execution_authority_policy_version": EXECUTION_AUTHORITY_POLICY_VERSION,
    }


def assert_no_unauthorised_capital(payload: Mapping[str, Any]) -> None:
    """Reject intermediate callbacks that attempt to bypass human authority."""

    if _truth(payload.get("execution_authorized")):
        raise ValueError("UNAUTHORISED_CAPITAL_GRANT:execution_authorized")
    if _truth(payload.get("execution_can_grant_capital")):
        raise ValueError("UNAUTHORISED_CAPITAL_GRANT:execution_can_grant_capital")
    violations = advisory_authority_violations(payload)
    if violations:
        raise ValueError("ADVISORY_AUTHORITY_VIOLATION:" + "|".join(violations))
