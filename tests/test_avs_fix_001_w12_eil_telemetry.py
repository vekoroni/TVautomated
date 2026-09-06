"""AVS-FIX-001 W1.2 (QT-D06) — retired EIL telemetry cannot contradict a
governed stand-down. Clears AVS-MVP-001 §6 kill criterion 6.

Run 20260905_151448 published `eil_v3_verdict = EXECUTE_WITH_CAUTION` beside
`options_verdict = STAND_DOWN` on 187 rows (127 CALL, 60 PUT, 0 OTHER). TTEK,
the row the tester named, additionally carried `invalidation_state = MISSING`.

EIL v3 holds no authority. That is precisely why the column must not read
EXECUTE beside a governed refusal: a human reads it as a second opinion, and
the semantic audit reads it as a contradiction.
"""

from __future__ import annotations

import unittest

import pandas as pd

import execution_intelligence_runner as eir
import handoff_contract_audit as hca

suppress = eir._suppress_retired_eil_verdict_against_governed_stand_down


def _row(ticker, direction, eil, options_verdict, invalidation_state, **extra):
    row = {
        "ticker": ticker,
        "governed_direction": direction,
        "canonical_direction": direction,
        "eil_v3_verdict": eil,
        "options_verdict": options_verdict,
        "invalidation_state": invalidation_state,
    }
    row.update(extra)
    return row


class SuppressionAgainstGovernedRefusal(unittest.TestCase):
    def test_ttek_shape_is_suppressed(self) -> None:
        frame = pd.DataFrame([
            _row("TTEK", "CALL", "EXECUTE_WITH_CAUTION", "STAND_DOWN", "MISSING")
        ])
        out = suppress(frame)
        self.assertEqual(out.loc[0, "eil_v3_verdict"], "NOT_EVALUATED")
        self.assertEqual(
            out.loc[0, "eil_verdict_suppression_reason"],
            "GOVERNED_OPTIONS_VERDICT_STAND_DOWN;GOVERNED_INVALIDATION_NOT_AVAILABLE",
        )

    def test_all_three_directions(self) -> None:
        frame = pd.DataFrame([
            _row("AAA", "CALL", "EXECUTE", "STAND_DOWN", "AVAILABLE"),
            _row("BBB", "PUT", "EXECUTE_WITH_CAUTION", "STAND_DOWN", "AVAILABLE"),
            _row("CCC", "STRANGLE", "EXECUTE", "STAND_DOWN", "NOT_APPLICABLE"),
            _row("DDD", "UNRESOLVED", "EXECUTE", "STAND_DOWN", "NOT_APPLICABLE"),
            _row("EEE", None, "EXECUTE", "STAND_DOWN", "NOT_APPLICABLE"),
        ])
        out = suppress(frame)
        self.assertEqual(
            out["eil_v3_verdict"].tolist(), ["NOT_EVALUATED"] * 5,
            "a governed stand-down suppresses the retired verdict on every direction",
        )

    def test_stand_down_alone_suppresses(self) -> None:
        out = suppress(pd.DataFrame([
            _row("AAA", "CALL", "EXECUTE", "STAND_DOWN", "AVAILABLE")
        ]))
        self.assertEqual(out.loc[0, "eil_v3_verdict"], "NOT_EVALUATED")
        self.assertEqual(
            out.loc[0, "eil_verdict_suppression_reason"],
            "GOVERNED_OPTIONS_VERDICT_STAND_DOWN",
        )

    def test_missing_invalidation_alone_suppresses(self) -> None:
        out = suppress(pd.DataFrame([
            _row("AAA", "CALL", "EXECUTE", "PROCEED", "MISSING")
        ]))
        self.assertEqual(out.loc[0, "eil_v3_verdict"], "NOT_EVALUATED")
        self.assertEqual(
            out.loc[0, "eil_verdict_suppression_reason"],
            "GOVERNED_INVALIDATION_NOT_AVAILABLE",
        )

    def test_a_governed_proceed_keeps_its_execute_verdict(self) -> None:
        out = suppress(pd.DataFrame([
            _row("AAA", "CALL", "EXECUTE", "PROCEED", "AVAILABLE"),
            _row("BBB", "PUT", "EXECUTE_WITH_CAUTION", "PROCEED", "AVAILABLE"),
        ]))
        self.assertEqual(
            out["eil_v3_verdict"].tolist(), ["EXECUTE", "EXECUTE_WITH_CAUTION"]
        )
        self.assertEqual(out["eil_verdict_suppression_reason"].tolist(), ["", ""])

    def test_blocked_telemetry_is_preserved(self) -> None:
        """BLOCKED agrees with the stand-down and stays: it explains why."""
        out = suppress(pd.DataFrame([
            _row("AAA", "CALL", "BLOCKED", "STAND_DOWN", "MISSING"),
            _row("BBB", "PUT", "WATCHLIST", "STAND_DOWN", "AVAILABLE"),
        ]))
        self.assertEqual(out["eil_v3_verdict"].tolist(), ["BLOCKED", "WATCHLIST"])

    def test_every_verdict_column_is_covered(self) -> None:
        frame = pd.DataFrame([{
            "ticker": "AAA", "governed_direction": "CALL",
            "eil_v3_verdict": "EXECUTE",
            "eil_signal_verdict": "EXECUTE_WITH_CAUTION",
            "fd_verdict": "EXECUTE",
            "options_verdict": "STAND_DOWN",
            "invalidation_state": "AVAILABLE",
        }])
        out = suppress(frame)
        for column in ("eil_v3_verdict", "eil_signal_verdict", "fd_verdict"):
            self.assertEqual(out.loc[0, column], "NOT_EVALUATED", column)

    def test_absent_invalidation_column_does_not_manufacture_suppression(self) -> None:
        frame = pd.DataFrame([{
            "ticker": "AAA", "governed_direction": "CALL",
            "eil_v3_verdict": "EXECUTE", "options_verdict": "PROCEED",
        }])
        out = suppress(frame)
        self.assertEqual(out.loc[0, "eil_v3_verdict"], "EXECUTE")

    def test_empty_frame_is_returned_unchanged(self) -> None:
        empty = pd.DataFrame()
        self.assertTrue(suppress(empty).empty)

    def test_no_permission_field_is_written(self) -> None:
        """The suppression removes a claim; it grants and revokes nothing."""
        frame = pd.DataFrame([
            _row("AAA", "CALL", "EXECUTE", "STAND_DOWN", "AVAILABLE",
                 final_action="MANUAL_REVIEW", capital_permission="NO")
        ])
        out = suppress(frame)
        self.assertEqual(out.loc[0, "final_action"], "MANUAL_REVIEW")
        self.assertEqual(out.loc[0, "capital_permission"], "NO")


class SemanticAuditOnTtekShape(unittest.TestCase):
    """The audit rule must return 0 on the remediated TTEK shape."""

    @staticmethod
    def _audit(frame):
        records = hca._semantic_contract_audit(
            {"eil_enriched": frame}, {"eil_enriched": "fixture.csv"}
        )
        return [
            r for r in records
            if r.get("status") == "DIRECTIONAL_TRADE_PROMOTED_WITHOUT_GOVERNED_INVALIDATION"
        ]

    def _ttek(self, eil_verdict, final_action):
        return pd.DataFrame([{
            "ticker": "TTEK",
            "governed_direction": "CALL",
            "canonical_direction": "CALL",
            "eil_v3_verdict": eil_verdict,
            "options_verdict": "STAND_DOWN",
            "invalidation_state": "MISSING",
            "invalidation_spot": None,
            "final_action": final_action,
            "capital_permission": "NO",
        }])

    def test_promoted_without_invalidation_is_still_caught(self) -> None:
        """The protection itself is untouched: a real promotion still fails."""
        self.assertTrue(self._audit(self._ttek("EXECUTE_WITH_CAUTION", "BUY_NOW")))

    def test_suppressed_row_reports_zero(self) -> None:
        frame = suppress(self._ttek("EXECUTE_WITH_CAUTION", "MANUAL_REVIEW"))
        self.assertEqual(self._audit(frame), [])
        self.assertEqual(frame.loc[0, "eil_v3_verdict"], "NOT_EVALUATED")


if __name__ == "__main__":
    unittest.main()
