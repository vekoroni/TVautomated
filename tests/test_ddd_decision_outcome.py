from __future__ import annotations

from pathlib import Path
import sqlite3

import pytest

from avshunter_trade_journal import get_db, log_entry, log_exit
from canonical_data.decision_outcome_ledger import (
    DecisionOutcomeLedger,
    candidate_events_from_rows,
    execution_events_from_rows,
    make_ledger_event,
    outcome_event_from_candidate,
    outcome_event_from_trade,
)
from canonical_data.outcome_maturation import mature_candidate_outcomes
from domain.decision_outcome import (
    LEDGER_AUTHORITY,
    LedgerInvariantError,
    evaluate_outcome_path,
    validate_event_link,
)
from morning_handoff_finalizer import _record_decision_outcome_ledger


RUN_ID = "DDD-PHASE8"
THESIS_ID = "THESIS:AAA:2026-09-04"
NOW = "2026-09-05T09:00:00Z"


def _row(ticker: str = "AAA", action: str = "BUY_SMALL") -> dict:
    return {
        "ticker": ticker,
        "run_id": RUN_ID,
        "pipeline_mode": "MORNING_VALIDATION",
        "thesis_id": THESIS_ID.replace("AAA", ticker),
        "trade_idea_id": f"IDEA:{ticker}",
        "governed_direction": "CALL",
        "selected_contract_symbol": f"{ticker}261016C00100000",
        "selected_quote_snapshot_id": f"QUOTE:{ticker}",
        "thesis_state": "ACTIVE",
        "final_action": action,
        "execution_eligibility_state": (
            "ELIGIBLE_LIMITED" if action == "BUY_SMALL" else "NOT_ELIGIBLE"
        ),
        "execution_authority_source": "FINAL_EXECUTION_GATE",
        "execution_authority_policy_version": "execution-authority-v1",
        "final_capital_permission": (
            "HUMAN_APPROVAL_REQUIRED" if action == "BUY_SMALL" else "NO"
        ),
        "execution_requires_human_approval": action == "BUY_SMALL",
        "execution_authorized": False,
    }


def test_domain_event_is_deterministic_and_observational() -> None:
    kwargs = dict(
        event_type="CANDIDATE_DECISION",
        occurred_at_utc=NOW,
        run_id=RUN_ID,
        ticker="aaa",
        thesis_id=THESIS_ID,
        payload={"final_action": "BUY_SMALL"},
    )
    first = make_ledger_event(**kwargs)
    second = make_ledger_event(**kwargs)
    assert first.event_id == second.event_id
    assert first.ticker == "AAA"
    assert first.payload["ledger_authority"] == LEDGER_AUTHORITY
    assert first.payload["ledger_can_grant_capital"] is False
    assert first.payload["ledger_can_reverse_direction"] is False


def test_non_finite_missing_evidence_is_recorded_as_null() -> None:
    event = make_ledger_event(
        event_type="CANDIDATE_DECISION",
        occurred_at_utc=NOW,
        run_id=RUN_ID,
        ticker="AAA",
        thesis_id=THESIS_ID,
        payload={"missing_quote": float("nan"), "nested": {"value": float("inf")}},
    )
    assert event.payload["missing_quote"] is None
    assert event.payload["nested"]["value"] is None


def test_restart_identity_is_stable_and_changed_content_fails_immutable(tmp_path: Path) -> None:
    first = make_ledger_event(
        event_type="CANDIDATE_DECISION", occurred_at_utc=NOW,
        run_id=RUN_ID, ticker="AAA", thesis_id=THESIS_ID,
        payload={"decision_stage": "EOD_THESIS", "final_action": "BLOCK"},
    )
    retry = make_ledger_event(
        event_type="CANDIDATE_DECISION", occurred_at_utc="2026-09-05T09:05:00Z",
        run_id=RUN_ID, ticker="AAA", thesis_id=THESIS_ID,
        payload={"decision_stage": "EOD_THESIS", "final_action": "BLOCK"},
    )
    changed = make_ledger_event(
        event_type="CANDIDATE_DECISION", occurred_at_utc="2026-09-05T09:05:00Z",
        run_id=RUN_ID, ticker="AAA", thesis_id=THESIS_ID,
        payload={"decision_stage": "EOD_THESIS", "final_action": "BUY_SMALL"},
    )
    assert first.event_id == retry.event_id == changed.event_id
    ledger = DecisionOutcomeLedger(tmp_path / "ledger.sqlite")
    assert ledger.append(first) is True
    assert ledger.append(retry) is False
    with pytest.raises(RuntimeError, match="different immutable content"):
        ledger.append(changed)


def test_domain_rejects_naive_time_and_authority_escalation() -> None:
    with pytest.raises(LedgerInvariantError, match="timezone-aware"):
        make_ledger_event(
            event_type="OUTCOME", occurred_at_utc="2026-09-05T09:00:00",
            run_id=RUN_ID, ticker="AAA", thesis_id=THESIS_ID, payload={},
        )
    with pytest.raises(LedgerInvariantError, match="ledger_can_grant_capital"):
        make_ledger_event(
            event_type="OUTCOME", occurred_at_utc=NOW, run_id=RUN_ID,
            ticker="AAA", thesis_id=THESIS_ID,
            payload={"ledger_can_grant_capital": True},
        )


def test_domain_validates_identity_time_and_transition_links() -> None:
    candidate = make_ledger_event(
        event_type="CANDIDATE_DECISION", occurred_at_utc=NOW,
        run_id=RUN_ID, ticker="AAA", thesis_id=THESIS_ID, payload={},
    )
    validation = make_ledger_event(
        event_type="VALIDATION", occurred_at_utc="2026-09-05T09:01:00Z",
        run_id=RUN_ID, ticker="AAA", thesis_id=THESIS_ID, payload={},
        previous_event_id=candidate.event_id,
    )
    validate_event_link(candidate, validation)
    bad = make_ledger_event(
        event_type="VALIDATION", occurred_at_utc="2026-09-05T08:59:00Z",
        run_id=RUN_ID, ticker="AAA", thesis_id=THESIS_ID, payload={},
        previous_event_id=candidate.event_id,
    )
    with pytest.raises(LedgerInvariantError, match="backwards"):
        validate_event_link(candidate, bad)


def test_sqlite_adapter_persists_complete_episode_and_is_append_only(tmp_path: Path) -> None:
    ledger = DecisionOutcomeLedger(tmp_path / "ledger.sqlite")
    candidate = make_ledger_event(
        event_type="CANDIDATE_DECISION", occurred_at_utc=NOW,
        run_id=RUN_ID, ticker="AAA", thesis_id=THESIS_ID, payload={},
    )
    validation = make_ledger_event(
        event_type="VALIDATION", occurred_at_utc="2026-09-05T09:01:00Z",
        run_id=RUN_ID, ticker="AAA", thesis_id=THESIS_ID,
        validation_event_id="VALIDATION-1", payload={"transition": "CONFIRMED"},
        previous_event_id=candidate.event_id,
    )
    execution = make_ledger_event(
        event_type="EXECUTION_DECISION", occurred_at_utc="2026-09-05T09:02:00Z",
        run_id=RUN_ID, ticker="AAA", thesis_id=THESIS_ID,
        validation_event_id="VALIDATION-1", payload={"final_action": "BUY_SMALL"},
        previous_event_id=validation.event_id,
    )
    entry = make_ledger_event(
        event_type="TRADE_ENTRY", occurred_at_utc="2026-09-05T09:03:00Z",
        run_id=RUN_ID, ticker="AAA", thesis_id=THESIS_ID,
        payload={"human_confirmed": True}, previous_event_id=execution.event_id,
    )
    outcome = outcome_event_from_trade(
        {
            "ticker": "AAA", "run_id": RUN_ID, "thesis_id": THESIS_ID,
            "trade_id": 1, "options_direction": "CALL", "pnl_usd": 50.0,
            "mfe": None, "mae": None, "outcome_class": "PROCESS_WIN",
        },
        occurred_at_utc="2026-09-06T09:03:00Z",
        previous_event_id=entry.event_id,
    )
    assert ledger.append_many((candidate, validation, execution, entry, outcome)) == 5
    assert ledger.append_many((candidate, validation, execution, entry, outcome)) == 0
    assert [item.event_type for item in ledger.events_for_thesis(THESIS_ID)] == [
        "CANDIDATE_DECISION", "VALIDATION", "EXECUTION_DECISION",
        "TRADE_ENTRY", "OUTCOME",
    ]
    assert ledger.event_counts(RUN_ID)["OUTCOME"] == 1
    assert outcome.payload["mfe"] is None
    assert outcome.payload["mae"] is None
    with sqlite3.connect(ledger.database_path) as connection:
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            connection.execute("DELETE FROM ledger_events")


def test_candidate_and_execution_factories_retain_go_and_rejection() -> None:
    rows = [_row("AAA", "BUY_SMALL"), _row("BBB", "BLOCK")]
    candidates = candidate_events_from_rows(
        rows, run_id=RUN_ID, occurred_at_utc=NOW, decision_stage="EOD_THESIS"
    )
    executions = execution_events_from_rows(
        rows, run_id=RUN_ID, occurred_at_utc=NOW
    )
    assert {event.payload["final_action"] for event in candidates} == {
        "BUY_SMALL", "BLOCK"
    }
    assert {event.payload["final_action"] for event in executions} == {
        "BUY_SMALL", "BLOCK"
    }
    assert all(event.payload["ledger_authority"] == "OBSERVATION_ONLY" for event in executions)


@pytest.mark.parametrize(
    ("direction", "target", "stop", "expected_return", "passage"),
    [
        ("CALL", 110.0, 95.0, 0.08, "TARGET_ONLY"),
        ("PUT", 90.0, 105.0, 0.08, "TARGET_ONLY"),
    ],
)
def test_outcome_path_is_symmetric_for_calls_and_puts(
    direction, target, stop, expected_return, passage
) -> None:
    bars = (
        [
            {"high": 106.0, "low": 98.0, "close": 104.0},
            {"high": 111.0, "low": 103.0, "close": 108.0},
        ]
        if direction == "CALL"
        else [
            {"high": 102.0, "low": 94.0, "close": 96.0},
            {"high": 97.0, "low": 89.0, "close": 92.0},
        ]
    )
    result = evaluate_outcome_path(
        direction=direction,
        reference_price=100.0,
        future_bars=bars,
        horizon_sessions=2,
        target_price=target,
        invalidation_price=stop,
    )
    assert result.directional_return == pytest.approx(expected_return)
    assert result.mfe == pytest.approx(0.11)
    assert result.mae == pytest.approx(-0.02)
    assert result.first_passage_state == passage


def test_outcome_path_defers_incomplete_horizon_and_does_not_invent_zero() -> None:
    result = evaluate_outcome_path(
        direction="CALL",
        reference_price=100.0,
        future_bars=[{"high": 102.0, "low": 99.0, "close": 101.0}],
        horizon_sessions=5,
    )
    assert result.data_status == "DEFERRED_NOT_YET_OBSERVABLE"
    assert result.directional_return is None
    assert result.mfe is None
    assert result.mae is None


def test_same_session_target_and_stop_is_explicitly_ambiguous() -> None:
    result = evaluate_outcome_path(
        direction="CALL",
        reference_price=100.0,
        future_bars=[{"high": 111.0, "low": 94.0, "close": 103.0}],
        horizon_sessions=1,
        target_price=110.0,
        invalidation_price=95.0,
    )
    assert result.first_passage_state == "AMBIGUOUS_SAME_SESSION"


def test_outcome_preserves_real_zero_and_rejects_non_finite_prices() -> None:
    event = outcome_event_from_trade(
        {
            "ticker": "AAA", "run_id": RUN_ID, "thesis_id": THESIS_ID,
            "pnl_r_multiple": 0.0, "rr_realised": 9.0,
            "days_held": 0, "hold_days": 9, "is_counterfactual": "false",
        },
        occurred_at_utc=NOW,
    )
    assert event.payload["pnl_r_multiple"] == 0.0
    assert event.payload["days_held"] == 0
    assert event.payload["is_counterfactual"] is False
    with pytest.raises(LedgerInvariantError, match="invalid OHLC"):
        evaluate_outcome_path(
            direction="CALL", reference_price=100.0,
            future_bars=[{"high": float("nan"), "low": 99.0, "close": 100.0}],
            horizon_sessions=1,
        )


def test_rejected_candidate_can_receive_comparable_counterfactual_outcome() -> None:
    candidate = candidate_events_from_rows(
        [_row("AAA", "BLOCK")],
        run_id=RUN_ID,
        occurred_at_utc=NOW,
        decision_stage="EOD_THESIS",
    )[0]
    evaluation = evaluate_outcome_path(
        direction="CALL",
        reference_price=100.0,
        future_bars=[{"high": 104.0, "low": 99.0, "close": 103.0}],
        horizon_sessions=1,
    )
    outcome = outcome_event_from_candidate(
        candidate, evaluation, occurred_at_utc="2026-09-06T09:00:00Z"
    )
    assert outcome.previous_event_id == candidate.event_id
    assert outcome.payload["is_counterfactual"] is True
    assert outcome.payload["original_final_action"] == "BLOCK"


def test_maturation_reuses_canonical_history_and_is_idempotent(tmp_path: Path) -> None:
    ledger = DecisionOutcomeLedger(tmp_path / "ledger.sqlite")
    row = {
        **_row("AAA", "BLOCK"),
        "completed_session": "2026-09-04",
        "completed_close": 100.0,
        "target_spot": 110.0,
        "invalidation_spot": 95.0,
    }
    candidate = candidate_events_from_rows(
        [row], run_id=RUN_ID, occurred_at_utc=NOW, decision_stage="EOD_THESIS"
    )[0]
    ledger.append(candidate)
    calls = []

    def read_history(ticker: str, start_date: str):
        calls.append((ticker, start_date))
        return [
            {"date": f"2026-09-{day:02d}", "high": 101.0 + index,
             "low": 99.0, "close": 100.0 + index}
            for index, day in enumerate((8, 9, 10, 11, 12), 1)
        ]

    first = mature_candidate_outcomes(
        ledger, read_completed_history=read_history,
        as_of_utc="2026-09-12T23:59:59Z",
    )
    # Stage 6 adds the 2- and 3-session learning milestones.
    assert first.outcomes_appended == 4
    assert first.deferred_horizons == 2
    assert calls == [("AAA", "2026-09-04")]
    outcomes = ledger.events_by_type("OUTCOME")
    assert {item.payload["horizon_sessions"] for item in outcomes} == {1, 2, 3, 5}
    assert all(item.payload["is_counterfactual"] is True for item in outcomes)

    calls.clear()
    second = mature_candidate_outcomes(
        ledger, read_completed_history=read_history,
        as_of_utc="2026-09-12T23:59:59Z",
    )
    assert second.outcomes_appended == 0
    assert second.outcomes_already_present == 4
    assert len(ledger.events_by_type("OUTCOME")) == 4


def test_morning_recorder_records_non_actionable_rows_and_missing_identity(tmp_path: Path) -> None:
    run_dir = tmp_path / "data" / "output" / "runs" / RUN_ID
    run_dir.mkdir(parents=True)
    summary = _record_decision_outcome_ledger(
        run_id=RUN_ID,
        run_dir=run_dir,
        rows=[_row("AAA", "BLOCK"), {"ticker": "MISSING", "final_action": "BLOCK"}],
        validation_events=[],
        occurred_at_utc=NOW,
    )
    assert summary["input_rows"] == 2
    assert summary["governed_rows"] == 1
    assert summary["missing_identity_count"] == 1
    assert summary["candidate_events"] == 1
    assert summary["execution_decision_events"] == 1
    assert summary["authority"] == "OBSERVATION_ONLY"


def test_morning_ledger_is_independent_of_msi_handoff_flags(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from morning_handoff_finalizer import _publish_msi_handoff

    monkeypatch.setenv("AVSHUNTER_DECISION_LEDGER_ENABLED", "1")
    monkeypatch.setenv("MSI_LAB_V3_VIEW", "0")
    monkeypatch.setenv("MSI_INTERPRETER_RESOLVER", "0")
    run_dir = tmp_path / "data" / "output" / "runs" / RUN_ID
    run_dir.mkdir(parents=True)
    result = _publish_msi_handoff(
        run_id=RUN_ID,
        run_dir=run_dir,
        lab_rows=[_row("AAA", "BLOCK")],
        completed_at_utc=NOW,
    )
    assert result["status"] == "DISABLED"
    assert result["decision_outcome_ledger"]["status"] == "PASS"
    assert result["decision_outcome_ledger"]["execution_decision_events"] == 1


def test_trade_journal_exit_writes_outcome_when_explicitly_enabled(tmp_path: Path) -> None:
    journal = tmp_path / "journal.sqlite"
    ledger_path = tmp_path / "ledger.sqlite"
    trade_id = log_entry(
        db_path=journal,
        runs_dir=tmp_path / "runs",
        ticker="AAA",
        run_id=RUN_ID,
        entry_premium=1.0,
        options_direction="CALL",
    )
    connection = get_db(journal)
    connection.execute("ALTER TABLE trades ADD COLUMN thesis_id TEXT")
    connection.execute(
        "UPDATE trades SET thesis_id=? WHERE trade_id=?", (THESIS_ID, trade_id)
    )
    connection.commit()
    connection.close()
    outcome = log_exit(
        db_path=journal,
        trade_id=trade_id,
        exit_premium=1.5,
        exit_reason="TEST_CLOSE",
        decision_ledger_path=ledger_path,
    )
    assert outcome["decision_ledger_authority"] == "OBSERVATION_ONLY"
    ledger_events = DecisionOutcomeLedger(ledger_path).events_for_thesis(THESIS_ID)
    assert len(ledger_events) == 1
    assert ledger_events[0].event_type == "OUTCOME"
    assert ledger_events[0].payload["pnl_usd"] == 50.0


def test_domain_module_has_no_infrastructure_dependency() -> None:
    source = (
        Path(__file__).parents[1] / "domain" / "decision_outcome.py"
    ).read_text(encoding="utf-8")
    for forbidden in (
        "import pandas", "import numpy", "canonical_data", "sqlite3",
        "requests", "Path(",
    ):
        assert forbidden not in source
