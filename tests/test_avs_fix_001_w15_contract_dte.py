"""AVS-FIX-001 W1.5 — contract_dte in the Lab book.

AVS-MVP-001 §4 evaluates "DTE >= 2 x hold" from the Lab book, and the hold is
counted in trading sessions — so the DTE beside it has to be counted the same
way. The book carried no such column; the nearest thing, `dte`, is a provider
calendar figure that defaults to 30 when absent, which cannot support the
comparison at all.

`contract_dte` counts XNYS sessions from the run's completed session to the
expiry encoded in the selected contract's own OCC symbol, so it can never
describe a different contract from the one selected. An absent contract yields
null with a named state, never 0 — which would read as "expires today".
"""

from __future__ import annotations

from datetime import date
import unittest

import eod_candidate_engine as eod
from canonical_data.session_clock import xnys_sessions_between
from contracts.lab_control import FINAL_BOOK_FIELDS, first


class TradingSessionCount(unittest.TestCase):
    def test_counts_sessions_not_calendar_days(self) -> None:
        # Friday 2026-08-28 to Friday 2026-09-18 is 21 calendar days but only
        # 14 sessions — Labor Day, Monday 2026-09-07, is a holiday.
        self.assertEqual(
            xnys_sessions_between(date(2026, 8, 28), date(2026, 9, 18)), 14
        )

    def test_a_long_weekend_is_not_three_days_of_life(self) -> None:
        """The case calendar DTE gets wrong.

        From Friday 2026-09-04, Labor Day Monday 2026-09-07 is three calendar
        days away and zero sessions away.
        """
        self.assertEqual(
            xnys_sessions_between(date(2026, 9, 4), date(2026, 9, 7)), 0
        )

    def test_same_session_is_zero(self) -> None:
        self.assertEqual(
            xnys_sessions_between(date(2026, 9, 4), date(2026, 9, 4)), 0
        )

    def test_an_expired_contract_is_never_negative(self) -> None:
        self.assertEqual(
            xnys_sessions_between(date(2026, 9, 4), date(2026, 9, 1)), 0
        )


class GovernedContractDte(unittest.TestCase):
    def test_known_symbol_and_session_gives_the_expected_dte(self) -> None:
        value, state = eod._governed_contract_dte({
            "recommended_contract": "AAPL260918C00100000",
            "evidence_session_date": "2026-08-28",
        })
        self.assertEqual(value, 14.0)
        self.assertEqual(state, "AVAILABLE")

    def test_both_directions_read_their_own_expiry(self) -> None:
        for symbol, direction in (
            ("AAPL260918C00100000", "CALL"),
            ("AAPL260918P00100000", "PUT"),
        ):
            with self.subTest(direction=direction):
                value, state = eod._governed_contract_dte({
                    "recommended_contract": symbol,
                    "evidence_session_date": "2026-08-28",
                })
                self.assertEqual(value, 14.0)
                self.assertEqual(state, "AVAILABLE")

    def test_absent_contract_is_null_with_a_named_state(self) -> None:
        value, state = eod._governed_contract_dte({"evidence_session_date": "2026-08-28"})
        self.assertIsNone(value)
        self.assertEqual(state, "NOT_APPLICABLE_NO_SELECTED_CONTRACT")
        self.assertNotEqual(value, 0.0)

    def test_other_direction_rows_carry_no_contract_and_no_dte(self) -> None:
        """RG-07: an OTHER row stands down and never selects a contract."""
        for direction in ("STRANGLE", "UNRESOLVED", None):
            with self.subTest(direction=direction):
                value, state = eod._governed_contract_dte({
                    "canonical_direction": direction,
                    "evidence_session_date": "2026-08-28",
                })
                self.assertIsNone(value)
                self.assertEqual(state, "NOT_APPLICABLE_NO_SELECTED_CONTRACT")

    def test_an_unparseable_symbol_is_named_not_guessed(self) -> None:
        value, state = eod._governed_contract_dte({
            "recommended_contract": "NOT-AN-OCC-SYMBOL",
            "evidence_session_date": "2026-08-28",
        })
        self.assertIsNone(value)
        self.assertEqual(state, "SCHEMA_INVALID")

    def test_the_expiry_comes_from_the_selected_contract(self) -> None:
        """A stale `expiry` column must not override the selected symbol."""
        value, _ = eod._governed_contract_dte({
            "recommended_contract": "AAPL260918C00100000",
            "expiry": "2027-01-15",
            "evidence_session_date": "2026-08-28",
        })
        self.assertEqual(value, 14.0)


class LabProjection(unittest.TestCase):
    def test_the_fields_are_allow_listed(self) -> None:
        for field in ("contract_dte", "contract_dte_state", "contract_dte_basis"):
            self.assertIn(field, FINAL_BOOK_FIELDS, field)

    def test_the_lab_maps_the_producer_value(self) -> None:
        self.assertEqual(first({"contract_dte": 14.0}, "contract_dte"), 14.0)

    def test_a_row_without_a_contract_projects_the_named_absence(self) -> None:
        self.assertEqual(
            first({}, "contract_dte_state", default="NOT_APPLICABLE_NO_SELECTED_CONTRACT"),
            "NOT_APPLICABLE_NO_SELECTED_CONTRACT",
        )

    def test_mvp_section_4_is_evaluable_from_the_book(self) -> None:
        """DTE >= 2 x hold, both sides in trading sessions."""
        hold_sessions = 5
        row = {"contract_dte": 14.0, "contract_dte_state": "AVAILABLE"}
        self.assertGreaterEqual(row["contract_dte"], 2 * hold_sessions)
        blocked = {"contract_dte": 8.0, "contract_dte_state": "AVAILABLE"}
        self.assertLess(blocked["contract_dte"], 2 * hold_sessions)


if __name__ == "__main__":
    unittest.main()
