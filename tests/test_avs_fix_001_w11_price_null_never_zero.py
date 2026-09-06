"""AVS-FIX-001 W1.1 (QT-D04) — a missing price is null, never 0.0.

Run 20260905_151448 published `structural_target == 0.0` on 19 Lab rows: the
13 CALL tickers the quant tester listed, plus 6 PUT rows the same defect
produced. The value came from `eod_candidate_engine._normalise_current_contract`, which
defaulted an unresolvable target to 0.0, and survived into the Lab because
`lab_control.first()` treats the string "0.0" as a present value.

A fabricated zero is worse than a null: `target > entry`, `target != 0`, and
every ratio against it evaluate silently rather than failing closed.

Three directions throughout, per binding rule 7.
"""

from __future__ import annotations

import unittest

import pandas as pd

import eod_candidate_engine as eod
import handoff_contract_audit as hca
from contracts.lab_control import _is_missing_price, first_price

#: The 13 CALL tickers QT-D04 recorded on run 20260905_151448.
QT_D04_CALL_TICKERS = [
    "AEE", "AVA", "BEPC", "CPRI", "GIII", "LZB", "MD",
    "NI", "NSSC", "OGE", "TSSI", "VNT", "XRAY",
]
#: The PUT rows the same defect produced on the same run.
QT_D04_PUT_TICKERS = ["CWEN", "EXK", "G", "MASS", "STAG", "WTRG"]


def _lab_frame(tickers, direction, target):
    return pd.DataFrame([
        {
            "ticker": ticker,
            "final_direction": direction,
            "canonical_direction": direction,
            "structural_target": target,
            "target_price": target,
            "invalidation_price": 10.0,
            "underlying_price": 100.0,
        }
        for ticker in tickers
    ])


def _price_zero_records(frame):
    records = hca._semantic_contract_audit({"lab": frame}, {"lab": "fixture.csv"})
    return [r for r in records if r.get("status") == "PRICE_FIELD_ZERO_AS_MISSING"]


class AuditRuleFiresOnFabricatedZero(unittest.TestCase):
    def test_call_rows_with_zero_target_are_flagged(self) -> None:
        records = _price_zero_records(_lab_frame(QT_D04_CALL_TICKERS, "CALL", 0.0))
        fields = {r["recommendation"].split(" is a price")[0] for r in records}
        self.assertIn("structural_target", fields)
        for record in records:
            self.assertEqual(record["severity"], "FAIL")
            self.assertEqual(record["filled_rows"], len(QT_D04_CALL_TICKERS))

    def test_put_rows_with_zero_target_are_flagged(self) -> None:
        records = _price_zero_records(_lab_frame(QT_D04_PUT_TICKERS, "PUT", 0.0))
        fields = {r["recommendation"].split(" is a price")[0] for r in records}
        self.assertIn("structural_target", fields)
        for record in records:
            self.assertEqual(record["filled_rows"], len(QT_D04_PUT_TICKERS))

    def test_other_direction_rows_are_unaffected(self) -> None:
        """RG-07: OTHER rows stand down; a null target on them is correct and
        must not be reported as a fabricated zero."""
        for direction in ("STRANGLE", "UNRESOLVED", None):
            with self.subTest(direction=direction):
                frame = _lab_frame(["ZZZA", "ZZZB"], direction, None)
                self.assertEqual(_price_zero_records(frame), [])

    def test_a_real_target_is_not_flagged(self) -> None:
        self.assertEqual(
            _price_zero_records(_lab_frame(QT_D04_CALL_TICKERS, "CALL", 112.5)), []
        )

    def test_the_rule_fails_on_the_unremediated_fixture_and_passes_on_the_fix(self) -> None:
        """The §7 definition of done: it must fail before and pass after."""
        self.assertNotEqual(_price_zero_records(_lab_frame(["AEE"], "CALL", 0.0)), [])
        self.assertEqual(_price_zero_records(_lab_frame(["AEE"], "CALL", None)), [])


class ZeroBidException(unittest.TestCase):
    """A 0.0 bid is a real market state when nobody is bidding."""

    @staticmethod
    def _frame(bid, bid_size):
        return pd.DataFrame([{
            "ticker": "AAPL", "final_direction": "CALL",
            "contract_bid": bid, "contract_bid_size": bid_size,
        }])

    def test_zero_bid_with_zero_size_is_legitimate(self) -> None:
        self.assertEqual(_price_zero_records(self._frame(0.0, 0)), [])

    def test_zero_bid_with_a_live_size_is_a_defect(self) -> None:
        records = _price_zero_records(self._frame(0.0, 12))
        self.assertTrue(records)
        self.assertIn("contract_bid", records[0]["recommendation"])

    def test_zero_ask_has_no_such_exception(self) -> None:
        frame = pd.DataFrame([{
            "ticker": "AAPL", "final_direction": "CALL",
            "contract_ask": 0.0, "contract_ask_size": 0,
        }])
        records = _price_zero_records(frame)
        self.assertTrue(records)
        self.assertIn("contract_ask", records[0]["recommendation"])


class ProducerWritesNullNotZero(unittest.TestCase):
    def test_unresolvable_target_becomes_null_and_names_its_absence(self) -> None:
        for direction in ("CALL", "PUT", "STRANGLE"):
            with self.subTest(direction=direction):
                row = {"ticker": "AEE", "canonical_direction": direction}
                eod._normalise_current_contract(row)
                self.assertIsNone(eod._optional_flt(row, "target_price"))
                self.assertNotEqual(row.get("target_price"), 0.0)
                self.assertEqual(row["target_state"], "UNRESOLVED")
                self.assertEqual(
                    row["target_unresolved_reason"], "STRUCTURAL_TARGET_UNRESOLVED"
                )

    def test_a_resolvable_target_is_carried_and_marked_available(self) -> None:
        row = {"ticker": "AEE", "canonical_direction": "CALL", "structural_target": 112.5}
        eod._normalise_current_contract(row)
        self.assertEqual(eod._optional_flt(row, "target_price"), 112.5)
        self.assertEqual(row["target_state"], "AVAILABLE")

    def test_a_zero_upstream_target_is_not_adopted(self) -> None:
        row = {"ticker": "AEE", "canonical_direction": "CALL", "structural_target": 0.0}
        eod._normalise_current_contract(row)
        self.assertIsNone(eod._optional_flt(row, "target_price"))
        self.assertEqual(row["target_state"], "UNRESOLVED")


class LabFirstPriceTreatsZeroAsAbsent(unittest.TestCase):
    def test_is_missing_price(self) -> None:
        for value in (0.0, 0, "0", "0.0", "", None, "nan", "NULL"):
            with self.subTest(value=value):
                self.assertTrue(_is_missing_price(value))
        for value in (112.5, "112.5", -3.0):
            with self.subTest(value=value):
                self.assertFalse(_is_missing_price(value))

    def test_first_price_skips_a_fabricated_zero_and_finds_the_real_value(self) -> None:
        signal = {"structural_target": 0.0, "opt__structural_target": 112.5}
        self.assertEqual(
            first_price(signal, "structural_target", "opt__structural_target"), 112.5
        )

    def test_first_price_returns_the_default_when_every_candidate_is_zero(self) -> None:
        signal = {"structural_target": 0.0, "target_price": 0.0}
        self.assertEqual(first_price(signal, "structural_target", "target_price"), "")


if __name__ == "__main__":
    unittest.main()
