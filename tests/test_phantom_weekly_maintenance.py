from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pandas as pd


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from finalize_phantom_weekly_snapshot import dte_bucket, entropy, nearest_iv


class PhantomWeeklyMaintenanceTests(unittest.TestCase):
    def test_dte_buckets_have_stable_boundaries(self) -> None:
        self.assertEqual(dte_bucket(7), "0_7")
        self.assertEqual(dte_bucket(8), "8_30")
        self.assertEqual(dte_bucket(30), "8_30")
        self.assertEqual(dte_bucket(31), "31_60")
        self.assertEqual(dte_bucket(60), "31_60")
        self.assertEqual(dte_bucket(61), "61_PLUS")

    def test_nearest_iv_prefers_target_delta(self) -> None:
        frame = pd.DataFrame({
            "iv": [0.20, 0.25, 0.30],
            "delta": [0.10, 0.49, 0.80],
            "strike": [90, 100, 110],
            "underlying_price": [100, 100, 100],
        })
        self.assertEqual(nearest_iv(frame, 0.50), 0.25)

    def test_nearest_iv_falls_back_to_atm_strike(self) -> None:
        frame = pd.DataFrame({
            "iv": [0.20, 0.25, 0.30],
            "delta": [None, None, None],
            "strike": [90, 101, 110],
            "underlying_price": [100, 100, 100],
        })
        self.assertEqual(nearest_iv(frame, 0.50), 0.25)

    def test_entropy_rejects_invalid_values(self) -> None:
        value = entropy(pd.Series([0.2, 0.3, None, -1.0]))
        self.assertGreater(value, 0.0)
        self.assertTrue(pd.notna(value))


if __name__ == "__main__":
    unittest.main()
