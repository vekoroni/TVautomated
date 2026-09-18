"""Signal tickets in the Decision and Outcome Ledger (ACK 18 Sep 2026; one owner per fact, R2).

The ledger (``canonical_data.decision_outcome_ledger``, rules in ``domain.decision_outcome``) already owns decisions
and outcomes for every thesis. Tickets are recorded there rather than in a parallel store:

  issued ticket          PRESENTATION_DECISION  human_response NOT_YET_RECORDED, presented True, rank
  every other candidate  PRESENTATION_DECISION  human_response NOT_PRESENTED, presented False, reason (and rank)
  ticket outcome         OUTCOME                is_counterfactual True, chained to the presentation

Each presentation is chained to the thesis's latest morning EXECUTION_DECISION (else CANDIDATE_DECISION), as the
ledger's causal rules require. A candidate with no thesis identity or no decision to chain to cannot be recorded, so
it is never issued (every issued ticket must be measurable).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable, Mapping

from . import signals as sig

DECISION_STAGE = "SIGNAL_TICKET"
NOT_YET_RECORDED, NOT_PRESENTED = "NOT_YET_RECORDED", "NOT_PRESENTED"
DEFAULT_LEDGER = Path(__file__).resolve().parents[2] / "data" / "canonical" / "decision_outcome_ledger.sqlite"


def open_ledger(path: Path = DEFAULT_LEDGER, *, read_only: bool = False):
    from canonical_data.decision_outcome_ledger import DecisionOutcomeLedger
    return DecisionOutcomeLedger(path, read_only=read_only)


def chain_anchor(ledger, thesis_id: str):
    """The event a presentation may follow: the latest execution decision, else the latest candidate decision."""
    return ledger.latest_event(thesis_id, "EXECUTION_DECISION") or ledger.latest_event(thesis_id, "CANDIDATE_DECISION")


def _plain(value: Any) -> Any:
    return value.isoformat() if isinstance(value, (date, datetime)) else value


def presentation_event(*, anchor, run_id: str, now: datetime, signal_version: str, issue_session: date,
                       config_snapshot_id: str, ticket: sig.SignalTicket | None = None, ticker: str | None = None,
                       reason: str | None = None, rank: int | None = None):
    from canonical_data.decision_outcome_ledger import make_ledger_event
    if ticket is not None:
        payload = {k: _plain(v) for k, v in asdict(ticket).items()}
        payload.update(preferred_assessment_id=ticket.ticket_id, human_response=NOT_YET_RECORDED, presented=True,
                       reason=None)
        ticker = ticket.ticker
    else:
        payload = {"preferred_assessment_id": f"{signal_version}|{run_id}|{issue_session.isoformat()}|{ticker}",
                   "human_response": NOT_PRESENTED, "presented": False, "reason": reason, "rank": rank,
                   "issue_session": issue_session.isoformat(), "signal_version": signal_version}
    payload.update(decision_stage=DECISION_STAGE, config_snapshot_id=config_snapshot_id)
    return make_ledger_event(event_type="PRESENTATION_DECISION", occurred_at_utc=now.isoformat(), run_id=run_id,
                             ticker=ticker, thesis_id=anchor.thesis_id, previous_event_id=anchor.event_id,
                             payload=payload)


def issued_presentations(ledger, as_of: date) -> list:
    return [e for e in ledger.events_by_type("PRESENTATION_DECISION")
            if e.payload.get("decision_stage") == DECISION_STAGE and e.payload.get("presented") is True
            and str(e.payload.get("issue_session") or "9999") <= as_of.isoformat()]


def signal_outcomes(ledger) -> list:
    return [e for e in ledger.events_by_type("OUTCOME") if e.payload.get("decision_stage") == DECISION_STAGE]


@dataclass(frozen=True, slots=True)
class OpenRecord:
    """An issued option ticket that still needs a daily mark (P0-4)."""
    ticker: str
    contract_symbol: str
    expiry: date
    last_usable_session: date
    presentation_event_id: str


def open_records(ledger, session: date) -> list[OpenRecord]:
    """Issued option tickets with no CLOSED outcome that are still inside their contract's usable life on
    ``session``; each needs that session's exact quote to be scored (P0-4, ACK 18 Sep 2026)."""
    closed = {e.previous_event_id for e in signal_outcomes(ledger) if e.payload.get("state") == sig.CLOSED}
    out = []
    for e in issued_presentations(ledger, session):
        p = e.payload
        symbol, expiry, usable = p.get("contract_symbol"), p.get("expiry"), p.get("last_usable_session")
        if e.event_id in closed or not symbol or not expiry or not usable:
            continue
        usable_day = date.fromisoformat(str(usable)[:10])
        if usable_day < session:
            continue
        out.append(OpenRecord(ticker=str(p.get("ticker") or e.ticker).upper(), contract_symbol=str(symbol).upper(),
                              expiry=date.fromisoformat(str(expiry)[:10]), last_usable_session=usable_day,
                              presentation_event_id=e.event_id))
    return sorted(out, key=lambda r: (r.ticker, r.contract_symbol))


def ticket_from_payload(payload: Mapping[str, Any]) -> sig.SignalTicket:
    names = sig.SignalTicket.__dataclass_fields__.keys()
    data = {k: payload.get(k) for k in names}
    for key in ("evidence_session", "issue_session", "expiry", "last_usable_session"):
        data[key] = date.fromisoformat(data[key]) if data[key] else None
    data["h9r_gap_up_event"] = bool(data["h9r_gap_up_event"])
    return sig.SignalTicket(**data)


def outcome_event(*, presentation, outcome: sig.SignalOutcome, ticket: sig.SignalTicket, sessions_held: int | None,
                  now: datetime, config_snapshot_id: str):
    from canonical_data.decision_outcome_ledger import make_ledger_event
    payload = {"decision_stage": DECISION_STAGE, "trade_id": None, "is_counterfactual": True,
               "horizon_sessions": ticket.hold_sessions, "outcome_horizon_sessions": sessions_held,
               "signal_version": ticket.signal_version, "ticket_id": ticket.ticket_id, "state": outcome.state,
               "exit_session": _plain(outcome.exit_session), "exit_reason": outcome.exit_reason,
               "entry_price": outcome.entry_price, "exit_price": outcome.exit_price,
               "return_on_capital": outcome.return_on_capital, "pnl_per_unit": outcome.pnl_per_unit,
               "reason": outcome.reason, "config_snapshot_id": config_snapshot_id,
               # Marks are exact-session point lookups, never nearest-date substitutes (P0-4, RC3).
               "mark_quote_date": _plain(outcome.exit_session), "mark_basis": "EXACT_SESSION"}
    return make_ledger_event(event_type="OUTCOME", occurred_at_utc=now.isoformat(), run_id=presentation.run_id,
                             ticker=presentation.ticker, thesis_id=presentation.thesis_id,
                             previous_event_id=presentation.event_id, payload=payload)
