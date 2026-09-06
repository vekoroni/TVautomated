"""AVS-FIX-001 W3.9 (RCA-003 §9, SD-002 §10) — outcome maturation runs nightly.

`canonical_data/outcome_maturation.py` existed and was already invoked in the
Evening path — but nested inside the decision-ledger APPEND block, so a failure
appending *this* run's candidates also skipped maturation of every candidate
from every previous run, which it does not depend on; and it skipped in silence
whenever the canonical price database was absent.

It is now its own non-critical stage with a published summary, so the operator
can tell a stage that ran and found nothing from a stage that never ran.

This is the item that makes calibration possible. Nothing reads the outcomes
yet, which is exactly why they have to start accumulating now.
"""

from __future__ import annotations

import json
import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import intelligent_orchestrator as orchestrator
from canonical_data.decision_outcome_ledger import DecisionOutcomeLedger, LedgerEvent
from canonical_data.outcome_maturation import (
    DEFAULT_OUTCOME_HORIZONS,
    mature_candidate_outcomes,
)

SESSION = "2026-08-28"


def candidate_event(ticker="AAPL", direction="CALL", reference=100.0,
                    target=110.0, invalidation=95.0, event_id="c1"):
    return LedgerEvent(
        event_id=event_id,
        event_type="CANDIDATE_DECISION",
        run_id="20260828_120000",
        ticker=ticker,
        thesis_id=f"t-{ticker}",
        occurred_at_utc="2026-08-28T21:00:00+00:00",
        payload={
            "decision_stage": "EOD_THESIS",
            "direction": direction,
            "completed_session": SESSION,
            "reference_price": reference,
            "target_price": target,
            "invalidation_price": invalidation,
            "thesis_id": f"t-{ticker}",
        },
    )


def price_history(count=25, start=100.0, step=1.0):
    """Completed sessions after SESSION, one bar per session."""
    bars = []
    for index in range(1, count + 1):
        close = start + step * index
        bars.append({
            "date": f"2026-09-{index:02d}" if index <= 30 else f"2026-10-{index - 30:02d}",
            "open": close, "high": close + 0.5, "low": close - 0.5, "close": close,
        })
    return bars


class MaturationOverAFixtureLedger(unittest.TestCase):
    def setUp(self) -> None:
        # ignore_cleanup_errors: the ledger keeps its SQLite connection open,
        # and Windows refuses to remove a file another handle holds.
        self._directory = TemporaryDirectory(ignore_cleanup_errors=True)
        self.root = Path(self._directory.name)
        self.ledger = DecisionOutcomeLedger(self.root / "ledger.sqlite")
        self.ledger.append(candidate_event())

    def tearDown(self) -> None:
        self._directory.cleanup()

    def _mature(self):
        return mature_candidate_outcomes(
            self.ledger,
            read_completed_history=lambda ticker, start: price_history(),
            as_of_utc=datetime.now(timezone.utc).isoformat(),
        )

    def test_decisions_mature_into_outcome_events_at_every_horizon(self) -> None:
        summary = self._mature()
        self.assertEqual(summary.eligible_candidates, 1)
        outcomes = list(self.ledger.events_by_type("OUTCOME"))
        horizons = sorted(
            int(event.payload.get("horizon_sessions") or 0) for event in outcomes
        )
        self.assertEqual(horizons, sorted(DEFAULT_OUTCOME_HORIZONS))

    def test_outcomes_link_back_to_their_candidate(self) -> None:
        self._mature()
        for event in self.ledger.events_by_type("OUTCOME"):
            self.assertEqual(event.previous_event_id, "c1")

    def test_the_rerun_is_idempotent(self) -> None:
        first = self._mature()
        before = len(list(self.ledger.events_by_type("OUTCOME")))
        second = self._mature()
        after = len(list(self.ledger.events_by_type("OUTCOME")))
        self.assertEqual(before, after, "a rerun appended duplicate outcomes")
        self.assertEqual(second.outcomes_appended, 0)
        self.assertEqual(second.outcomes_already_present, first.outcomes_appended)

    def test_the_ledger_stays_append_only(self) -> None:
        self._mature()
        candidates = list(self.ledger.events_by_type("CANDIDATE_DECISION"))
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].payload["reference_price"], 100.0)

    def test_all_three_directions(self) -> None:
        self.ledger.append(candidate_event(
            ticker="MSFT", direction="PUT", event_id="c2",
            target=90.0, invalidation=105.0,
        ))
        self.ledger.append(candidate_event(
            ticker="TSLA", direction="STRANGLE", event_id="c3",
        ))
        summary = self._mature()
        # CALL and PUT mature; the OTHER row is ineligible, never guessed at.
        self.assertEqual(summary.eligible_candidates, 2)
        self.assertGreaterEqual(summary.ineligible_candidates, 1)
        matured = {
            event.ticker for event in self.ledger.events_by_type("OUTCOME")
        }
        self.assertEqual(matured, {"AAPL", "MSFT"})

    def test_a_horizon_beyond_the_history_defers_rather_than_guessing(self) -> None:
        summary = mature_candidate_outcomes(
            self.ledger,
            read_completed_history=lambda ticker, start: price_history(count=2),
            as_of_utc=datetime.now(timezone.utc).isoformat(),
        )
        self.assertGreater(summary.deferred_horizons, 0)

    def test_maturation_grants_no_capital(self) -> None:
        summary = self._mature()
        self.assertEqual(summary.authority, "OBSERVATION_ONLY")
        self.assertIs(summary.can_grant_capital, False)
        for event in self.ledger.events_by_type("OUTCOME"):
            self.assertNotIn("final_action", event.payload)
            self.assertNotIn("capital_permission", event.payload)


class TheStageIsNonCritical(unittest.TestCase):
    """Every failure path degrades to a named status. None aborts a run."""

    def setUp(self) -> None:
        self._directory = TemporaryDirectory(ignore_cleanup_errors=True)
        self.root = Path(self._directory.name)
        (self.root / "runs" / "R1").mkdir(parents=True)

    def tearDown(self) -> None:
        self._directory.cleanup()

    def _run(self):
        with patch.object(orchestrator.cfg, "RUNS_DIR", self.root / "runs"):
            return orchestrator.run_outcome_maturation_stage("R1")

    def test_an_absent_price_database_is_deferred_not_silent(self) -> None:
        """The gap the old nesting hid: no prices meant no log line at all."""
        with patch(
            "contracts.dynamic_session_contract.DynamicSessionFeatureFlags.from_environment"
        ) as flags:
            flags.return_value.decision_outcome_ledger = True
            summary = self._run()
        self.assertEqual(summary["status"], "DEFERRED")
        self.assertEqual(summary["reason"], "CANONICAL_PRICE_HISTORY_UNAVAILABLE")

    def test_a_disabled_flag_is_skipped_and_says_so(self) -> None:
        with patch(
            "contracts.dynamic_session_contract.DynamicSessionFeatureFlags.from_environment"
        ) as flags:
            flags.return_value.decision_outcome_ledger = False
            summary = self._run()
        self.assertEqual(summary["status"], "SKIPPED")
        self.assertEqual(summary["reason"], "DECISION_LEDGER_FLAG_DISABLED")

    def test_an_unexpected_error_is_caught_and_named(self) -> None:
        with patch(
            "contracts.dynamic_session_contract.DynamicSessionFeatureFlags.from_environment",
            side_effect=RuntimeError("boom"),
        ):
            summary = self._run()
        self.assertEqual(summary["status"], "FAILED")
        self.assertIn("boom", summary["reason"])

    def test_the_summary_is_published_as_an_artefact(self) -> None:
        with patch(
            "contracts.dynamic_session_contract.DynamicSessionFeatureFlags.from_environment"
        ) as flags:
            flags.return_value.decision_outcome_ledger = False
            summary = self._run()
        artefact = Path(summary["artefact"])
        self.assertTrue(artefact.exists())
        payload = json.loads(artefact.read_text(encoding="utf-8"))
        self.assertEqual(payload["stage"], "OUTCOME_MATURATION")
        self.assertEqual(payload["authority"], "OBSERVATION_ONLY")
        self.assertIs(payload["can_grant_capital"], False)

    def test_every_outcome_declares_observation_only(self) -> None:
        for enabled in (True, False):
            with self.subTest(flag=enabled):
                with patch(
                    "contracts.dynamic_session_contract."
                    "DynamicSessionFeatureFlags.from_environment"
                ) as flags:
                    flags.return_value.decision_outcome_ledger = enabled
                    summary = self._run()
                self.assertEqual(summary["authority"], "OBSERVATION_ONLY")
                self.assertIs(summary["can_grant_capital"], False)


class TheStageIsWiredIntoTheEveningPath(unittest.TestCase):
    def test_the_evening_workflow_calls_it(self) -> None:
        import inspect

        source = inspect.getsource(orchestrator)
        self.assertIn("run_outcome_maturation_stage(canonical_run_id)", source)

    def test_it_is_not_nested_inside_the_ledger_append_block(self) -> None:
        """The defect this item fixed.

        A failure appending this run's candidates must not skip maturation of
        candidates from every previous run.
        """
        import inspect

        source = inspect.getsource(orchestrator.run_outcome_maturation_stage)
        self.assertIn("mature_candidate_outcomes", source)
        self.assertIn("OBSERVATION_ONLY", source)


if __name__ == "__main__":
    unittest.main()
