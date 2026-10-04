"""Step 3b (ACK 4 Oct 2026): C12 scores each ticket at its own evidence hold; the fixed window is a comparison.

"score each ticket at its own anticipated hold ... keep the fixed 20 as a second column" (approved with step 3).
Business rules:
- A ticket's hold is the book's evidence hold (planned_hold_source DURATION_EVIDENCE_*); without evidence it is
  scored at the governed window and says so (hold_basis), never silently.
- The fixed governed window is recorded on every ticket as the comparison hold.
- The comparison outcome is written under its own decision stage, so existing reports, open-record lists and
  "already scored" checks never see it or double count.
- Tickets already in the ledger (without the new fields) still load.
"""
from __future__ import annotations

from datetime import date

from avshunter.c12_outcome import signal_ledger as ledger_io
from avshunter.c12_outcome import signals as sig

from test_c12_signals import ISSUE, bars, prepare, ticket


def test_ticket_hold_is_the_evidence_hold_when_the_book_has_one():
    reason, p = prepare(book=dict(planned_hold_sessions=13, planned_hold_source="DURATION_EVIDENCE_Q80:1d:n=900"))
    assert reason is None
    assert p.hold_sessions == 13 and p.hold_basis == "DURATION_EVIDENCE_Q80:1d:n=900"
    assert p.path_inputs["hold_sessions"] == 13


def test_ticket_without_evidence_is_scored_at_the_window_and_says_so():
    reason, p = prepare(book=dict(planned_hold_sessions=None, planned_hold_source="NO_EVIDENCE_HOLD|X"))
    assert reason is None and p.hold_sessions == 20 and p.hold_basis == "NO_EVIDENCE_HOLD_SCORED_AT_FIXED_WINDOW"


def test_every_ticket_records_the_fixed_window_as_its_comparison():
    t = ticket()
    assert t.comparison_hold_sessions == 20


def test_comparison_is_needed_only_when_the_holds_differ():
    assert sig.comparison_hold_needed(ticket(hold_sessions=13, comparison_hold_sessions=20)) is True
    assert sig.comparison_hold_needed(ticket(hold_sessions=20, comparison_hold_sessions=20)) is False
    assert sig.comparison_hold_needed(ticket(hold_sessions=13, comparison_hold_sessions=None)) is False


def test_comparison_exit_uses_the_fixed_window():
    t = ticket(hold_sessions=1, comparison_hold_sessions=3)
    flat = (100, 101, 99, 100)
    rows = bars(flat, flat, flat, flat)
    assert sig.plan_exit(t, rows, as_of=date(2026, 9, 23)).session == date(2026, 9, 21)
    assert sig.plan_exit(sig.comparison_ticket(t), rows, as_of=date(2026, 9, 23)).session == date(2026, 9, 23)


def test_comparison_outcomes_live_under_their_own_stage():
    assert ledger_io.COMPARISON_STAGE != ledger_io.DECISION_STAGE


def test_tickets_already_in_the_ledger_still_load():
    payload = {k: ledger_io._plain(v) for k, v in sig.asdict_ticket(ticket()).items()
               if k not in ("hold_basis", "comparison_hold_sessions")}
    loaded = ledger_io.ticket_from_payload(payload)
    assert loaded.comparison_hold_sessions is None and loaded.hold_basis == ""
    assert not sig.comparison_hold_needed(loaded)


class _Event:
    def __init__(self, event_id, payload, previous=None):
        self.event_id, self.payload, self.previous_event_id = event_id, payload, previous
        self.run_id, self.ticker, self.thesis_id, self.event_type = "r", "ABC", "TH-1", "PRESENTATION_DECISION"
        self.occurred_at_utc = "2026-09-18T13:00:00+00:00"


class _Ledger:
    def __init__(self, presentation):
        self.events = [presentation]

    def events_by_type(self, kind):
        return [e for e in self.events if e.event_type == kind]

    def append_many(self, events):
        events = list(events)
        self.events.extend(events)
        return len(events)


def test_score_signals_writes_the_comparison_outcome_beside_the_ticket(tmp_path):
    import sqlite3
    from types import SimpleNamespace
    from avshunter.c12_outcome import signal_service
    from test_c12_signals import SYMBOL, settings
    t = ticket(hold_sessions=1, comparison_hold_sessions=3)
    payload = {k: ledger_io._plain(v) for k, v in sig.asdict_ticket(t).items()}
    payload.update(decision_stage=ledger_io.DECISION_STAGE, presented=True)
    ledger = _Ledger(_Event("P1", payload))
    chain_db, price_db = tmp_path / "chains.db", tmp_path / "prices.sqlite"
    con = sqlite3.connect(chain_db)
    con.execute("CREATE TABLE chain_snapshots (ticker TEXT, quote_date TEXT, option_symbol TEXT, bid REAL, ask REAL)")
    con.executemany("INSERT INTO chain_snapshots VALUES ('ABC', ?, ?, ?, ?)",
                    [("2026-09-21", SYMBOL, 5.5, 5.8), ("2026-09-23", SYMBOL, 6.0, 6.3)])
    con.commit(); con.close()
    con = sqlite3.connect(price_db)
    con.execute("CREATE TABLE ohlcv_daily (ticker TEXT, trading_date TEXT, open REAL, high REAL, low REAL, close REAL, "
                "volume REAL, bar_status TEXT)")
    con.executemany("INSERT INTO ohlcv_daily VALUES ('ABC',?,100,101,99,100,1e6,'COMPLETE')",
                    [(d,) for d in ("2026-09-18", "2026-09-21", "2026-09-22", "2026-09-23")])
    con.commit(); con.close()
    snap = SimpleNamespace(snapshot_id="SNAP")
    out = signal_service.score_signals(ledger, date(2026, 9, 23), snap, datetime_now(), chain_db=chain_db,
                                       price_db=price_db, settings_override=settings())
    assert out["new_outcomes"] == 1 and out["new_comparison_outcomes"] == 1
    primary = ledger_io.signal_outcomes(ledger)
    comparison = ledger_io.comparison_outcomes(ledger)
    assert len(primary) == 1 and primary[0].payload["exit_session"] == "2026-09-21"
    assert len(comparison) == 1 and comparison[0].payload["exit_session"] == "2026-09-23"
    again = signal_service.score_signals(ledger, date(2026, 9, 23), snap, datetime_now(), chain_db=chain_db,
                                         price_db=price_db, settings_override=settings())
    assert again["new_outcomes"] == 0 and again["new_comparison_outcomes"] == 0


def datetime_now():
    from datetime import datetime, timezone
    return datetime(2026, 9, 24, 12, 0, tzinfo=timezone.utc)
