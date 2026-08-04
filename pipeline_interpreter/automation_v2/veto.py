"""Deterministic sovereign permission lattice.

Provider analysis may preserve or reduce permission, but never promote it.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Mapping

from .models import CAPITAL_DENIED, EXECUTION_NONE
from .numeric_validation import finite_decimal, invalid_or_negative


NEGATIVE_RR = "NEGATIVE_RR"
EVIDENCE_INVALID = "EVIDENCE_INVALID"
UPSTREAM_DENIED = "UPSTREAM_DENIED"
LIVE_CONFIRMATION_REQUIRED = "LIVE_CONFIRMATION_REQUIRED"


@dataclass(frozen=True, slots=True)
class SovereignPolicy:
    block_on_invalid_evidence: bool = True
    require_live_confirmation: bool = True


@dataclass(frozen=True, slots=True)
class SovereignDecision:
    veto_codes: tuple[str, ...]
    effective_verdict: str
    eil_action: str
    execution_permission: str = EXECUTION_NONE
    capital_permission: str = CAPITAL_DENIED

    @property
    def blocked(self) -> bool:
        return bool(self.veto_codes)


def _first_value(row: Mapping[str, Any], names: tuple[str, ...]) -> Any:
    lower = {str(key).lower(): value for key, value in row.items()}
    for name in names:
        value = lower.get(name.lower())
        if value not in (None, ""):
            return value
    return None


def parse_rr(row: Mapping[str, Any]) -> Decimal | None:
    raw = _first_value(
        row,
        (
            "option_rr",
            "option_r_r",
            "rr",
            "r_r",
            "r:r",
            "risk_reward",
            "risk_reward_ratio",
        ),
    )
    if raw is None:
        return None
    cleaned = str(raw).strip().upper().replace("R", "").replace("X", "")
    cleaned = cleaned.replace(":", "").replace(",", "")
    return finite_decimal(cleaned)


def evaluate_sovereign_veto(
    *,
    pipeline_row: Mapping[str, Any],
    evidence_findings: tuple[str, ...] = (),
    live_validation: Mapping[str, Any] | None = None,
    policy: SovereignPolicy | None = None,
) -> SovereignDecision:
    policy = policy or SovereignPolicy()
    codes: list[str] = []

    raw_rr = _first_value(
        pipeline_row,
        (
            "option_rr", "option_r_r", "rr", "r_r", "r:r",
            "risk_reward", "risk_reward_ratio",
        ),
    )
    rr = parse_rr(pipeline_row)
    if raw_rr is None or invalid_or_negative(rr):
        codes.append(NEGATIVE_RR)

    upstream_permission = str(
        _first_value(
            pipeline_row,
            (
                "execution_permission",
                "capital_permission",
                "morning_permission",
            ),
        )
        or ""
    ).upper()
    if any(token in upstream_permission for token in ("DENIED", "BLOCK", "STOP")):
        codes.append(UPSTREAM_DENIED)

    if policy.block_on_invalid_evidence and evidence_findings:
        codes.append(EVIDENCE_INVALID)

    live_validation = live_validation or {}
    live_state = str(
        _first_value(
            live_validation,
            ("permission", "execution_permission", "status", "verdict"),
        )
        or ""
    ).upper()
    live_confirmed = live_state in {"GO", "CONFIRMED", "APPROVED", "LIVE_CONFIRMED"}
    if policy.require_live_confirmation and not live_confirmed:
        codes.append(LIVE_CONFIRMATION_REQUIRED)

    unique_codes = tuple(dict.fromkeys(codes))
    return SovereignDecision(
        veto_codes=unique_codes,
        effective_verdict="STOP" if unique_codes else "WAIT",
        eil_action="STOP",
    )


def apply_sovereign_overlay(
    proposed_verdict: str, decision: SovereignDecision
) -> SovereignDecision:
    """Apply a one-way safety overlay to a provider's proposed verdict."""
    proposal = (proposed_verdict or "WAIT").strip().upper()
    if decision.blocked:
        return decision
    if proposal in {"STOP", "BLOCK", "BLOCKED", "WAIT", "NO_TRADE"}:
        return SovereignDecision(
            veto_codes=decision.veto_codes,
            effective_verdict="STOP" if proposal in {"STOP", "BLOCK", "BLOCKED"} else "WAIT",
            eil_action="STOP",
        )
    # The Interpreter is advisory: even a provider GO remains WAIT and cannot execute.
    return SovereignDecision(
        veto_codes=decision.veto_codes,
        effective_verdict="WAIT",
        eil_action="STOP",
    )
