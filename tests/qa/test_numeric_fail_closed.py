from __future__ import annotations

import unittest

from pipeline_interpreter.automation_v2.lab_batch import _negative_rr
from pipeline_interpreter.automation_v2.market_structure import _present
from pipeline_interpreter.automation_v2.numeric_validation import finite_decimal
from pipeline_interpreter.automation_v2.veto import evaluate_sovereign_veto


class NumericFailClosedTests(unittest.TestCase):
    def test_rr_rejects_missing_malformed_and_non_finite_values(self):
        for value in (None, "", "garbage", "nan", "NaN", "inf", "-inf"):
            with self.subTest(value=value):
                self.assertIsNone(finite_decimal(value))
                row = {} if value is None else {"rr_predicted": value}
                self.assertTrue(_negative_rr(row))

    def test_rr_accepts_finite_zero_and_positive_values(self):
        for value in ("0", "0.0", "2.5", 3):
            with self.subTest(value=value):
                self.assertIsNotNone(finite_decimal(value))
                self.assertFalse(_negative_rr({"rr_predicted": value}))

    def test_sovereign_veto_rejects_all_invalid_rr_values_without_crashing(self):
        for value in (None, "", "garbage", "nan", "inf", "-inf"):
            with self.subTest(value=value):
                row = {} if value is None else {"rr": value}
                decision = evaluate_sovereign_veto(
                    pipeline_row=row, live_validation={"permission": "GO"}
                )
                self.assertIn("NEGATIVE_RR", decision.veto_codes)
                self.assertEqual(decision.effective_verdict, "STOP")

    def test_market_structure_rejects_non_finite_values(self):
        for value in (float("nan"), float("inf"), "NaN", "-Infinity"):
            with self.subTest(value=value):
                self.assertFalse(_present(value))


if __name__ == "__main__":
    unittest.main()
