from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[1]
VANGUARD_RUNTIME = Path(r"C:\Users\ACKVerissimo\vanguard")
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
# The external Vanguard runtime supplies actuarial_cache_builder, but must not
# precede AVSHUNTER: both repositories contain a top-level ``scripts`` package
# and poisoning that namespace makes collection order change test outcomes.
if str(VANGUARD_RUNTIME) not in sys.path:
    sys.path.append(str(VANGUARD_RUNTIME))

import actuarial_cache_builder as cache_builder


def synthetic_rows() -> pd.DataFrame:
    rows = []
    for index in range(40):
        rows.append({
            "vol_regime": "NORMAL",
            "trend_direction": "UP",
            "structure_quality": "STRONG",
            "adx_bucket": "MODERATE",
            "wyckoff_phase_bucket": "MARKUP",
            "trend_maturity": "MIDDLE",
            "atr_pct_bucket": "MID",
            "outcome_5d_return": 0.01,
            "outcome_10d_return": 0.02 if index < 35 else None,
            "outcome_20d_return": 0.03 if index < 30 else None,
            "outcome_hit_5pct_up_5d": 0.0,
            "outcome_hit_7pct_up_10d": 0.0,
            "outcome_hit_10pct_up": 0.0,
            "outcome_max_drawdown_5d": -0.01,
            "outcome_max_drawdown_10d": -0.02 if index < 35 else None,
            "outcome_max_drawdown_20d": -0.03 if index < 30 else None,
            "outcome_days_to_10pct": None,
        })
    return pd.DataFrame(rows)


class ActuarialCacheV7ContractTests(unittest.TestCase):
    def setUp(self) -> None:
        cache_builder.STATE_COLS = list(cache_builder.FULL_STATE_COLS)

    def test_live_only_dimensions_are_not_fabricated(self) -> None:
        dimensions = cache_builder.configure_state_dimensions(synthetic_rows().columns)
        self.assertNotIn("macro_regime", dimensions)
        self.assertNotIn("catalyst_proximity", dimensions)
        self.assertIn("atr_pct_bucket", dimensions)

    def test_missing_core_dimension_fails_closed(self) -> None:
        frame = synthetic_rows().drop(columns=["adx_bucket"])
        with self.assertRaisesRegex(ValueError, "adx_bucket"):
            cache_builder.configure_state_dimensions(frame.columns)

    def test_horizon_samples_use_independent_maturity(self) -> None:
        frame = synthetic_rows()
        cache_builder.configure_state_dimensions(frame.columns)
        cache = cache_builder.aggregate_states(cache_builder.build_state_key(frame))
        row = cache.iloc[0]
        self.assertEqual(int(row["sample_size_5d"]), 40)
        self.assertEqual(int(row["sample_size_10d"]), 35)
        self.assertEqual(int(row["sample_size_20d"]), 30)
        self.assertEqual(int(row["sample_size"]), 30)
        self.assertEqual(float(row["win_rate_20d"]), 1.0)

    def test_reduced_historical_key_accepts_live_overlays(self) -> None:
        frame = synthetic_rows()
        cache_builder.configure_state_dimensions(frame.columns)
        cache = cache_builder.aggregate_states(cache_builder.build_state_key(frame))
        live = dict(frame.iloc[0])
        live.update({"macro_regime": "RISK_OFF", "catalyst_proximity": "HIGH"})
        result = cache_builder.lookup_state(live, cache)
        self.assertFalse(result.no_match)
        self.assertEqual(result.sample_size, 30)

    def test_governed_similarity_handles_coupled_sideways_taxonomy_gap(self) -> None:
        frame = synthetic_rows()
        frame["trend_direction"] = "SIDEWAYS"
        frame["structure_quality"] = "NEUTRAL"
        frame["wyckoff_phase_bucket"] = "ACCUMULATION"
        frame["trend_maturity"] = "SIDEWAYS_BUILDING"
        cache_builder.configure_state_dimensions(frame.columns)
        cache = cache_builder.aggregate_states(cache_builder.build_state_key(frame))

        live = dict(frame.iloc[0])
        live["wyckoff_phase_bucket"] = "MARKUP"
        live["trend_maturity"] = "SIDEWAYS_RANGING"
        result = cache_builder.lookup_state(live, cache)

        self.assertFalse(result.no_match)
        self.assertTrue(result.valid)
        self.assertEqual(result.fallback_depth, 2)
        self.assertEqual(
            set(result.fallback_dims_dropped),
            {"wyckoff_phase_bucket", "trend_maturity"},
        )
        self.assertLess(result.penalty_multiplier, 1.0)

    def test_governed_similarity_never_crosses_direction(self) -> None:
        frame = synthetic_rows()
        cache_builder.configure_state_dimensions(frame.columns)
        cache = cache_builder.aggregate_states(cache_builder.build_state_key(frame))

        live = dict(frame.iloc[0])
        live["trend_direction"] = "DOWN"
        result = cache_builder.lookup_state(live, cache)

        self.assertTrue(result.no_match)
        self.assertEqual(result.matched_key, "")

    def test_incremental_request_is_coerced_to_full_rebuild(self) -> None:
        frame = synthetic_rows()
        emitted = {}

        with mock.patch.object(
            cache_builder, "load_db", return_value=frame
        ) as load_db, mock.patch.object(
            cache_builder, "save_cache"
        ), mock.patch.object(
            cache_builder, "emit_pipeline_status", side_effect=lambda ok, stats: emitted.update(stats)
        ), mock.patch.object(
            cache_builder, "save_last_run"
        ), mock.patch.object(
            cache_builder, "merge_into_cache"
        ) as merge:
            self.assertTrue(cache_builder.build(incremental=True))

        load_db.assert_called_once_with(incremental=False)
        merge.assert_not_called()
        self.assertEqual(emitted["mode"], "full_rebuild")


if __name__ == "__main__":
    unittest.main()
