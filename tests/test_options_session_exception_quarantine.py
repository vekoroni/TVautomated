from __future__ import annotations

from datetime import date
import unittest

import pandas as pd

import scripts.avshunter_options_intelligence as options_intelligence
from scripts.avshunter_options_intelligence import (
    OPTIONS_SESSION_EXCEPTION_COLUMNS,
    _resolve_options_session_scope,
)


class OptionsSessionExceptionQuarantineTests(unittest.TestCase):
    def test_single_stale_ticker_is_quarantined_without_changing_run_session(self) -> None:
        eligible = pd.DataFrame([
            {
                "ticker": "AAA",
                "bar_data_asof": "2026-08-31",
                "data_source": "POLYGON",
                "is_stale": False,
            },
            {
                "ticker": "BBB",
                "bar_data_asof": "2026-08-31",
                "data_source": "CANONICAL_HISTORY",
                "is_stale": False,
            },
            {
                "ticker": "NKE",
                "bar_data_asof": "2026-08-28",
                "data_source": "STALE_CACHE",
                "is_stale": True,
            },
        ])

        session, source, exceptions = _resolve_options_session_scope(eligible)

        self.assertEqual(session, date(2026, 8, 31))
        self.assertEqual(source, "bar_data_asof")
        self.assertEqual(list(exceptions.columns), OPTIONS_SESSION_EXCEPTION_COLUMNS)
        self.assertEqual(len(exceptions), 1)
        record = exceptions.iloc[0].to_dict()
        self.assertEqual(record["ticker"], "NKE")
        self.assertEqual(record["expected_session"], "2026-08-31")
        self.assertEqual(record["actual_session"], "2026-08-28")
        self.assertEqual(record["exception_reason"], "UNDERLYING_SESSION_MISMATCH")
        self.assertEqual(
            record["exception_action"],
            "QUARANTINE_MONITOR_ONLY_NO_OPTIONS_ACQUISITION",
        )

    def test_stale_source_is_quarantined_even_when_boolean_flag_is_absent(self) -> None:
        eligible = pd.DataFrame([
            {
                "ticker": "AAA",
                "data_as_of": "2026-08-31",
                "bar_data_source": "POLYGON",
            },
            {
                "ticker": "BBB",
                "data_as_of": "2026-08-31",
                "bar_data_source": "STALE_CACHE",
            },
        ])

        session, source, exceptions = _resolve_options_session_scope(eligible)

        self.assertEqual(session, date(2026, 8, 31))
        self.assertEqual(source, "data_as_of")
        self.assertEqual(exceptions["ticker"].tolist(), ["BBB"])
        self.assertEqual(
            exceptions["exception_reason"].tolist(), ["UNDERLYING_DATA_STALE"]
        )

    def test_missing_session_is_quarantined_when_fresh_session_exists(self) -> None:
        eligible = pd.DataFrame([
            {"ticker": "AAA", "bar_data_asof": "2026-08-31", "is_stale": False},
            {"ticker": "BBB", "bar_data_asof": None, "is_stale": True},
        ])

        session, _, exceptions = _resolve_options_session_scope(eligible)

        self.assertEqual(session, date(2026, 8, 31))
        self.assertEqual(exceptions["ticker"].tolist(), ["BBB"])
        self.assertEqual(
            exceptions["exception_reason"].tolist(),
            ["UNDERLYING_SESSION_UNAVAILABLE"],
        )

    def test_genuine_ambiguity_among_fresh_rows_still_fails_closed(self) -> None:
        eligible = pd.DataFrame([
            {"ticker": "AAA", "bar_data_asof": "2026-08-28", "is_stale": False},
            {"ticker": "BBB", "bar_data_asof": "2026-08-31", "is_stale": False},
        ])

        with self.assertRaisesRegex(ValueError, "ambiguous"):
            _resolve_options_session_scope(eligible)

    def test_all_stale_population_cannot_invent_a_governed_session(self) -> None:
        eligible = pd.DataFrame([
            {
                "ticker": "AAA",
                "bar_data_asof": "2026-08-28",
                "data_source": "STALE_CACHE",
                "is_stale": True,
            }
        ])

        with self.assertRaisesRegex(ValueError, "unavailable"):
            _resolve_options_session_scope(eligible)

    def test_quarantined_row_cannot_mutate_options_lifecycle(self) -> None:
        original_store = options_intelligence._CDS_LIQUIDITY_STORE
        options_intelligence._CDS_LIQUIDITY_STORE = object()
        try:
            result = {
                "ticker": "NKE",
                "options_session_exception": True,
                "options_direction": "CALL",
                "thesis_id": "must-not-be-persisted",
            }
            options_intelligence._persist_options_lifecycle_result(
                result, "20260901_064425"
            )
        finally:
            options_intelligence._CDS_LIQUIDITY_STORE = original_store

        self.assertEqual(
            result["liquidity_persistence_status"],
            "SKIPPED_SESSION_DATA_EXCEPTION",
        )


if __name__ == "__main__":
    unittest.main()
