"""Expression marks: what the recorded option contract did (P0-8 §3.3, §5.3; pure).

Rules:
- entry at the recorded ``contract_ask`` (> 0); otherwise the chain ask for the same contract on the
  evidence session (> 0), the quote available when the book was built (ACK, 17 Sep 2026); otherwise
  ENTRY_NOT_VALUED. The entry source is always recorded;
- the planned exit session follows the underlying outcome: resolution session for TARGET_FIRST /
  STOP_FIRST / AMBIGUOUS, the final window session for TIMEOUT or an unscorable underlying;
- the contract is never held past its last usable session (expiry minus ``outcome.contract_exit_buffer``
  sessions); a contract whose last usable session is not after the evidence session is CONTRACT_INVALID;
- exit at that session's end-of-day bid from the chain store; a missing row is MARK_UNAVAILABLE
  (no nearest-date substitution);
- nothing is written while the exit session is still after the as-of session.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import re
from typing import Callable, Sequence

from .model import ContractState, OutcomeState

EXPRESSION_VERSION = "c12-expression-v1.1.0"

OCC_EXPIRY = re.compile(r"^[A-Z.]+(?P<yy>\d{2})(?P<mm>\d{2})(?P<dd>\d{2})[CP]\d{8}$")
CENTURY = 2000


def contract_expiry(symbol: str) -> date | None:
    match = OCC_EXPIRY.match(symbol or "")
    if not match:
        return None
    try:
        return date(CENTURY + int(match["yy"]), int(match["mm"]), int(match["dd"]))
    except ValueError:
        return None


def choose_entry(recorded_ask: float | None, evidence_chain_ask: float | None) -> tuple[float | None, str]:
    if recorded_ask is not None and recorded_ask > 0:
        return recorded_ask, "RECORDED_ASK"
    if evidence_chain_ask is not None and evidence_chain_ask > 0:
        return evidence_chain_ask, "CHAIN_ASK_EVIDENCE_SESSION"
    return None, "NONE"


@dataclass(frozen=True, slots=True)
class ExitPlan:
    session: date | None
    reason: str          # RESOLUTION | TIMEOUT | CONTRACT_LAST_USABLE | PENDING | NOT_HOLDABLE


def plan_exit(
    underlying_state: OutcomeState | None,
    resolution_session: int | None,
    window_sessions: Sequence[date],      # full window sessions 1..window after the evidence session
    last_usable_session: date,
    evidence_session: date,
    as_of: date,
) -> ExitPlan:
    if last_usable_session <= evidence_session:
        return ExitPlan(None, "NOT_HOLDABLE")
    planned, reason = None, "PENDING"
    if underlying_state in (OutcomeState.TARGET_FIRST, OutcomeState.STOP_FIRST, OutcomeState.AMBIGUOUS):
        planned, reason = window_sessions[resolution_session - 1], "RESOLUTION"
    elif underlying_state in (OutcomeState.TIMEOUT, OutcomeState.NOT_SCORABLE):
        planned, reason = window_sessions[-1], "TIMEOUT"
    if planned is None or last_usable_session < planned:
        planned, reason = last_usable_session, "CONTRACT_LAST_USABLE"
    if planned > as_of:
        return ExitPlan(None, "PENDING")
    return ExitPlan(planned, reason)


@dataclass(frozen=True, slots=True)
class ExpressionOutcome:
    state: str                   # MARKED | MARK_UNAVAILABLE | ENTRY_NOT_VALUED | CONTRACT_INVALID | PENDING
    exit_session: date | None
    exit_reason: str | None
    entry_ask: float | None
    exit_bid: float | None
    pnl_per_contract: float | None
    return_on_premium: float | None
    reason: str = ""
    entry_source: str = "NONE"


def mark_expression(
    contract_state: ContractState,
    contract_symbol: str | None,
    entry_ask: float | None,
    plan: ExitPlan,
    bid_lookup: Callable[[str, date], float | None],
    multiplier: float,
    evidence_chain_ask: float | None = None,
) -> ExpressionOutcome:
    if contract_state is not ContractState.VALID:
        return ExpressionOutcome("CONTRACT_INVALID", None, None, entry_ask, None, None, None, contract_state.value)
    if plan.reason == "NOT_HOLDABLE":
        return ExpressionOutcome("CONTRACT_INVALID", None, None, entry_ask, None, None, None,
                                 "contract expires within the exit buffer")
    if plan.session is None:
        return ExpressionOutcome("PENDING", None, plan.reason, entry_ask, None, None, None)
    entry_ask, entry_source = choose_entry(entry_ask, evidence_chain_ask)
    if entry_ask is None:
        return ExpressionOutcome("ENTRY_NOT_VALUED", plan.session, plan.reason, None, None, None, None,
                                 "recorded and evidence-session chain ask missing or not positive", entry_source)
    bid = bid_lookup(contract_symbol, plan.session)
    if bid is None:
        return ExpressionOutcome("MARK_UNAVAILABLE", plan.session, plan.reason, entry_ask, None, None, None,
                                 f"no chain row for {contract_symbol} on {plan.session.isoformat()}", entry_source)
    return ExpressionOutcome("MARKED", plan.session, plan.reason, entry_ask, bid,
                             (bid - entry_ask) * multiplier, bid / entry_ask - 1.0, "", entry_source)
