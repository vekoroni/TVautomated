"""Output-trust item 8 (D6-1 / G2-05; ACK approved 9-10 Oct 2026): a disposition record for every surfaced idea.

Root cause (Evening verification 20261008_220129, G2-05): the EOD decision append keys every event by thesis, so 508
book rows without a thesis identity (418 unresolved direction, 90 directed with no contract) were dropped from the
journal while still shown in the Lab. The Morning receipt also counted one skipped validation event without naming it.

Business rules:
- One record per run, ticker and stage (EOD / MORNING) for every row the book surfaces, traded or not.
- Frozen at decision time: setup, levels, contract (or the stated reason there is none), price and quote time, stated
  probabilities, value scenarios, the decision and why, and the model versions.
- Nothing invented: a missing thesis or contract identity is null with its state; missing fields are null.
- Append-only and idempotent: rewriting the same record is a no-op; different content under the same identity fails.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from canonical_data.decision_outcome_ledger import DecisionOutcomeLedger  # noqa: E402
from domain.ticker_disposition import DISPOSITION_FIELDS, disposition_record  # noqa: E402

DIRECTED = {"ticker": "SMCI", "direction": "CALL", "thesis_id": "SMCI:CALL:20261008",
            "thesis_event_candidate_id": "SMCI|1d|CAMPAIGN|SOS -> LPS continuation|2026-08-24", "thesis__readiness":
            "READY_FOR_HUMAN_REVIEW", "trade_lane": "A", "trade_lane_hit_holdout": 0.678, "contract_symbol":
            "SMCI261120C00045000", "signal_price": 42.77, "lab_verdict": "GO", "geometry_justification": "JUSTIFIED",
            "trade_lane_version": "beh001_lanes_v1", "valuation_version": "option_valuation_v1"}
UNRESOLVED = {"ticker": "ABC", "direction": "UNRESOLVED", "signal_price": 10.0, "lab_verdict": "MANUAL_REVIEW",
              "thesis__readiness": "NOT_ADOPTED"}
NO_CONTRACT = {"ticker": "XYZ", "direction": "PUT", "thesis_id": "XYZ:PUT:20261008", "signal_price": 20.0,
               "lab_verdict": "MANUAL_REVIEW", "contract_rejection_reason": "NO_CONTRACT_IN_DTE_WINDOW"}


def test_every_surfaced_row_gets_a_record_without_inventing_identity():
    d = disposition_record(DIRECTED, run_id="R1", stage="EOD", recorded_at_utc="2026-10-08T22:00:00Z")
    assert (d["run_id"], d["ticker"], d["stage"]) == ("R1", "SMCI", "EOD")
    assert d["thesis_id"] == "SMCI:CALL:20261008" and d["thesis_identity_state"] == "PRESENT"
    assert d["contract_identity_state"] == "PRESENT"
    assert d["snapshot"]["trade_lane_hit_holdout"] == 0.678 and d["snapshot"]["valuation_version"] == "option_valuation_v1"
    u = disposition_record(UNRESOLVED, run_id="R1", stage="EOD", recorded_at_utc="2026-10-08T22:00:00Z")
    assert u["thesis_id"] is None and u["thesis_identity_state"] == "NO_THESIS:UNRESOLVED_DIRECTION"
    assert u["contract_symbol"] is None and u["contract_identity_state"] == "NO_CONTRACT:NO_TRADE_SIDE"
    n = disposition_record(NO_CONTRACT, run_id="R1", stage="EOD", recorded_at_utc="2026-10-08T22:00:00Z")
    assert n["contract_identity_state"] == "NO_CONTRACT:NO_CONTRACT_IN_DTE_WINDOW"
    # live 8 Oct book: the reason is published as option_expression_state (no verified chain, unvalued candidates)
    book = disposition_record({**NO_CONTRACT, "contract_rejection_reason": None,
                               "option_expression_state": "NO_VERIFIED_CHAIN"}, run_id="R1", stage="EOD",
                              recorded_at_utc="x")
    assert book["contract_identity_state"] == "NO_CONTRACT:NO_VERIFIED_CHAIN"
    assert set(DISPOSITION_FIELDS) == set(d["snapshot"])                 # every frozen field present (null if missing)
    assert u["snapshot"]["contract_symbol"] is None


def test_a_book_row_key_is_never_presented_as_a_thesis_and_nan_is_a_ticker():
    # live 8 Oct: the book keys unresolved rows "AAP:UNRESOLVED:<run>" - a row key, not a thesis
    keyed = disposition_record({**UNRESOLVED, "thesis_id": "ABC:UNRESOLVED:R1"}, run_id="R1", stage="EOD",
                               recorded_at_utc="2026-10-08T22:00:00Z")
    assert keyed["thesis_id"] is None and keyed["book_row_key"] == "ABC:UNRESOLVED:R1"
    assert keyed["thesis_identity_state"] == "NO_THESIS:UNRESOLVED_DIRECTION"
    no_candidate = disposition_record(NO_CONTRACT, run_id="R1", stage="EOD", recorded_at_utc="2026-10-08T22:00:00Z")
    assert no_candidate["thesis_identity_state"].startswith("NO_THESIS:NO_GOVERNING_CANDIDATE")
    nan = disposition_record({**DIRECTED, "ticker": "NAN"}, run_id="R1", stage="EOD", recorded_at_utc="x")
    assert nan["ticker"] == "NAN"                                       # Nuveen's ticker, not a missing value


def test_the_journal_is_append_only_and_idempotent(tmp_path):
    ledger = DecisionOutcomeLedger(tmp_path / "ledger.sqlite")
    rows = [disposition_record(r, run_id="R1", stage="EOD", recorded_at_utc="2026-10-08T22:00:00Z")
            for r in (DIRECTED, UNRESOLVED, NO_CONTRACT)]
    assert ledger.append_dispositions(rows) == 3
    assert ledger.append_dispositions(rows) == 0                          # same content: no-op
    with pytest.raises(RuntimeError):
        ledger.append_dispositions([disposition_record({**DIRECTED, "lab_verdict": "BLOCKED"}, run_id="R1",
                                                       stage="EOD", recorded_at_utc="2026-10-08T23:00:00Z")])
    with sqlite3.connect(tmp_path / "ledger.sqlite") as con:
        with pytest.raises(sqlite3.DatabaseError):
            con.execute("DELETE FROM ticker_dispositions")
    assert {r["ticker"] for r in ledger.dispositions_for_run("R1")} == {"SMCI", "ABC", "XYZ"}


def test_the_eod_and_morning_stages_write_every_book_row():
    import inspect
    import intelligent_orchestrator
    import morning_handoff_finalizer
    eod = inspect.getsource(intelligent_orchestrator)
    assert 'disposition_record(_row, run_id=canonical_run_id, stage="EOD"' in eod
    mor = inspect.getsource(morning_handoff_finalizer)
    assert 'stage="MORNING"' in mor and "append_dispositions(" in mor


def test_a_skipped_validation_event_is_named():
    import inspect
    from orchestrator import dynamic_validation
    assert "skipped_missing_governed_identity_tickers" in inspect.getsource(dynamic_validation)
