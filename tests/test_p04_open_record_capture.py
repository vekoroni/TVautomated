"""P0-4 slice 1: an open ticket keeps a daily mark until it exits; one adapter rule; marks say what they are.

ACK approved 18 Sep 2026 (Enhancements/phase0/P0-4_CAPTURE_OPEN_RECORDS_DESIGN.md).

Measured root causes:
- RC1: chains reach the store only for that evening's candidates; a ticker that drops out loses its daily mark
  while a ticket on it is still open (16/17 Sep: ~1,350 tickers stored against ~2,780 on 14/15 Sep).
- RC2: the MarketData adapter always sent `date`, which the provider rejects for the current session ("date is for
  historical queries only"): the evening GEX refresh failed on 14, 16 and 17 Sep.
- RC3: marks are exact-date already, but outcomes did not record which quote date they used and nothing listed the
  tickets waiting on a mark.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest

from canonical_data.benchmark_option_chain import CanonicalBenchmarkOptionChainStore
from canonical_data.marketdata_option_chain import MarketDataOptionChainAdapter

SESSION = date(2026, 9, 18)
UPDATED = int(datetime(2026, 9, 18, 19, 59, tzinfo=timezone.utc).timestamp())
EXPIRY_TS = int(datetime(2026, 11, 20, 0, 0, tzinfo=timezone.utc).timestamp())


def _payload(ticker: str, strike_center: float = 100.0) -> dict:
    symbols, sides, strikes = [], [], []
    for offset in range(5):
        strike = int(strike_center - 2 + offset)
        encoded = f"{strike * 1000:08d}"
        symbols += [f"{ticker}261120C{encoded}", f"{ticker}261120P{encoded}"]
        sides += ["call", "put"]
        strikes += [float(strike), float(strike)]
    n = len(symbols)
    return {"s": "ok", "optionSymbol": symbols, "side": sides, "strike": strikes, "expiration": [EXPIRY_TS] * n,
            "dte": [63] * n, "updated": [UPDATED] * n, "bid": [4.0] * n, "ask": [4.2] * n, "mid": [4.1] * n,
            "bidSize": [10] * n, "askSize": [12] * n, "last": [4.05] * n, "openInterest": [100] * n,
            "volume": [20] * n, "inTheMoney": [False] * n, "intrinsicValue": [0.0] * n,
            "extrinsicValue": [4.1] * n, "underlyingPrice": [strike_center] * n, "iv": [0.3] * n,
            "delta": [0.5 if s == "call" else -0.5 for s in sides], "gamma": [0.02] * n, "theta": [-0.05] * n,
            "vega": [0.1] * n, "contractMultiplier": [100] * n}


class _Transport:
    def __init__(self):
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append(kwargs["params"])
        return SimpleNamespace(status_code=200, ok=True, text="", json=lambda: _payload("SPY"))


# --- RC2: one adapter rule --------------------------------------------------------------------------------------

def test_characterisation_past_session_request_carries_its_date():
    transport = _Transport()
    MarketDataOptionChainAdapter(api_token="t", transport=transport, today=lambda: date(2026, 9, 19)).fetch(
        "SPY", session_date=SESSION, dte_max=60)
    assert transport.calls[0]["date"] == "2026-09-18"


def test_same_session_request_carries_no_date():
    """The provider rejects `date` for the current session; after the close the plain request is today's chain."""
    transport = _Transport()
    MarketDataOptionChainAdapter(api_token="t", transport=transport, today=lambda: SESSION).fetch(
        "SPY", session_date=SESSION, dte_max=60)
    assert "date" not in transport.calls[0]
    assert transport.calls[0]["from"] == "2026-09-19"


def test_future_session_request_is_refused():
    adapter = MarketDataOptionChainAdapter(api_token="t", transport=_Transport(), today=lambda: SESSION)
    with pytest.raises(ValueError, match="future"):
        adapter.fetch("SPY", session_date=date(2026, 9, 21), dte_max=60)


def test_chain_not_from_the_requested_session_is_refused(tmp_path: Path):
    store = CanonicalBenchmarkOptionChainStore(registry_path=tmp_path / "c.sqlite", payload_root=tmp_path / "p",
                                               run_id="RUN-1", purpose="OPEN_RECORD_MARK")
    with pytest.raises(ValueError, match="session"):
        store.get(ticker="ABC", session_date=date(2026, 9, 17), dte_max=90, fetch=lambda t: _payload(t))


# --- RC1: open records ----------------------------------------------------------------------------------------------

@dataclass
class _Event:
    event_id: str
    payload: dict
    previous_event_id: str | None = None
    ticker: str = ""


@dataclass
class _Ledger:
    presentations: list = field(default_factory=list)
    outcomes: list = field(default_factory=list)

    def events_by_type(self, kind):
        return tuple(self.presentations if kind == "PRESENTATION_DECISION" else self.outcomes)


def _presentation(event_id, ticker, symbol, last_usable, issue="2026-09-15", expiry="2026-11-20", presented=True):
    return _Event(event_id, {"decision_stage": "SIGNAL_TICKET", "presented": presented, "ticker": ticker,
                             "contract_symbol": symbol, "issue_session": issue, "expiry": expiry,
                             "last_usable_session": last_usable})


def test_open_records_are_issued_tickets_without_a_closed_outcome_and_still_usable():
    from avshunter.c12_outcome.signal_ledger import open_records
    ledger = _Ledger(
        presentations=[
            _presentation("P1", "ABC", "ABC261120C00100000", "2026-11-17"),              # open
            _presentation("P2", "DEF", "DEF261120C00050000", "2026-11-17"),              # closed below
            _presentation("P3", "GHI", "GHI260918C00020000", "2026-09-16"),              # past last usable
            _presentation("P4", "JKL", "JKL261120C00010000", "2026-11-17", presented=False),  # not issued
            _presentation("P5", "MNO", "MNO261120C00030000", "2026-11-17", issue="2026-09-21"),  # issued later
        ],
        outcomes=[_Event("O2", {"decision_stage": "SIGNAL_TICKET", "state": "CLOSED"}, previous_event_id="P2")])
    records = open_records(ledger, SESSION)
    assert [(r.ticker, r.contract_symbol) for r in records] == [("ABC", "ABC261120C00100000")]
    assert records[0].expiry == date(2026, 11, 20)


def test_open_ticket_keeps_its_daily_mark_after_dropping_out_of_the_candidates(tmp_path: Path):
    """RC1 end to end: the evening stored no chain for ABC; the capture step fetches it, projects it, and the exact
    contract is readable for the session."""
    from avshunter.c12_outcome.signal_ledger import OpenRecord
    from orchestrator.completed_session_gex import capture_open_record_chains
    fetched = []

    def fetch(ticker, dte_max):
        fetched.append((ticker, dte_max))
        return _payload(ticker)

    record = OpenRecord(ticker="ABC", contract_symbol="ABC261120C00100000", expiry=date(2026, 11, 20),
                        last_usable_session=date(2026, 11, 17), presentation_event_id="P1")
    result = capture_open_record_chains(repository_root=tmp_path, run_id="RUN-1", session_date=SESSION,
                                        records=[record], fetch_chain=fetch, max_requests=10)
    assert result["status"] == "COMPLETE", result
    assert result["captured"] == ["ABC"] and fetched[0][0] == "ABC"
    assert fetched[0][1] >= (date(2026, 11, 20) - SESSION).days        # the window reaches the ticket's expiry
    with sqlite3.connect(tmp_path / "data" / "phantom" / "phantom_history.db") as connection:
        row = connection.execute("SELECT bid FROM chain_snapshots WHERE ticker='ABC' AND quote_date=? AND "
                                 "option_symbol='ABC261120C00100000'", (SESSION.isoformat(),)).fetchone()
    assert row is not None and row[0] == 4.0


def test_contract_already_stored_for_the_session_is_not_fetched_again(tmp_path: Path):
    from avshunter.c12_outcome.signal_ledger import OpenRecord
    from orchestrator.completed_session_gex import capture_open_record_chains
    record = OpenRecord("ABC", "ABC261120C00100000", date(2026, 11, 20), date(2026, 11, 17), "P1")
    first = capture_open_record_chains(repository_root=tmp_path, run_id="RUN-1", session_date=SESSION,
                                       records=[record], fetch_chain=lambda t, d: _payload(t), max_requests=10)
    calls = []
    second = capture_open_record_chains(repository_root=tmp_path, run_id="RUN-2", session_date=SESSION,
                                        records=[record], fetch_chain=lambda t, d: calls.append(t) or _payload(t),
                                        max_requests=10)
    assert first["captured"] == ["ABC"]
    assert second["already_present"] == ["ABC"] and calls == []


def test_request_budget_stops_fetching_and_is_reported(tmp_path: Path):
    from avshunter.c12_outcome.signal_ledger import OpenRecord
    from orchestrator.completed_session_gex import capture_open_record_chains
    records = [OpenRecord(t, f"{t}261120C00100000", date(2026, 11, 20), date(2026, 11, 17), f"P{t}")
               for t in ("ABC", "DEF", "GHI")]
    result = capture_open_record_chains(repository_root=tmp_path, run_id="RUN-1", session_date=SESSION,
                                        records=records, fetch_chain=lambda t, d: _payload(t), max_requests=2)
    assert len(result["captured"]) == 2 and result["over_budget"] == ["GHI"]
    assert result["requests_used"] == 2


def test_capture_failure_is_reported_not_raised(tmp_path: Path):
    from avshunter.c12_outcome.signal_ledger import OpenRecord
    from orchestrator.completed_session_gex import capture_open_record_chains

    def broken(ticker, dte_max):
        raise RuntimeError("provider unavailable")

    record = OpenRecord("ABC", "ABC261120C00100000", date(2026, 11, 20), date(2026, 11, 17), "P1")
    result = capture_open_record_chains(repository_root=tmp_path, run_id="RUN-1", session_date=SESSION,
                                        records=[record], fetch_chain=broken, max_requests=10)
    assert result["status"] == "PARTIAL"
    assert result["failed"] == {"ABC": "RuntimeError: provider unavailable"}


# --- RC3: marks say what they are ------------------------------------------------------------------------------

def test_outcome_records_the_quote_date_of_its_mark():
    from avshunter.c12_outcome import signal_ledger as sl
    from avshunter.c12_outcome import signals as sig
    presentation = SimpleNamespace(run_id="R", ticker="ABC", thesis_id="T", event_id="P1")
    outcome = sig.SignalOutcome(sig.CLOSED, date(2026, 9, 25), "HOLD_COMPLETE", 4.2, 5.0, 0.19, 80.0)
    ticket = SimpleNamespace(hold_sessions=20, signal_version="SIG-V1", ticket_id="X")
    event = sl.outcome_event(presentation=presentation, outcome=outcome, ticket=ticket, sessions_held=5,
                             now=datetime(2026, 9, 25, 22, tzinfo=timezone.utc), config_snapshot_id="S")
    assert event.payload["mark_quote_date"] == "2026-09-25"
    assert event.payload["mark_basis"] == "EXACT_SESSION"


# --- evening stage wiring --------------------------------------------------------------------------------------

def test_evening_stage_writes_coverage_and_never_raises(tmp_path: Path, monkeypatch):
    import json
    import intelligent_orchestrator as orchestrator
    monkeypatch.setattr(orchestrator.cfg, "RUNS_DIR", tmp_path / "runs")
    seen = {}

    def capture(**kwargs):
        seen.update(kwargs)
        return {"status": "COMPLETE", "captured": ["ABC"], "requests_used": 1}

    summary = orchestrator.run_open_record_capture_stage(
        "RUN-1", SESSION, load_records=lambda session: ["REC"], capture=capture, max_requests=7)
    assert summary["status"] == "COMPLETE" and seen["records"] == ["REC"] and seen["max_requests"] == 7
    written = json.loads((tmp_path / "runs" / "RUN-1" / "capture" / "open_record_coverage_RUN-1.json")
                         .read_text(encoding="utf-8"))
    assert written["captured"] == ["ABC"]

    def broken(**kwargs):
        raise RuntimeError("boom")

    failed = orchestrator.run_open_record_capture_stage(
        "RUN-2", SESSION, load_records=lambda session: [], capture=broken, max_requests=7)
    assert failed["status"] == "FAILED" and "boom" in failed["reason"]
