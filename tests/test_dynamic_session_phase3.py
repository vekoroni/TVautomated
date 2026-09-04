from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
import tempfile
import unittest

import pandas as pd

from canonical_data import (
    CanonicalFeatureFlags,
    CanonicalMinuteBarResolver,
    CanonicalRegistry,
    DatasetType,
    LifecycleManager,
    LifecycleState,
    assess_intraday_quality,
    expected_intraday_timestamps,
    intraday_schema_version,
    missing_intraday_ranges,
    parse_marketdata_stock_candles,
    session_bounds,
)


SESSION = date(2026, 8, 31)


def bars(start: datetime, end: datetime, interval: int = 5) -> pd.DataFrame:
    timestamps = pd.date_range(start, end, freq=f"{interval}min")
    return pd.DataFrame({
        "timestamp_utc": timestamps,
        "open": 100.0,
        "high": 101.0,
        "low": 99.0,
        "close": 100.5,
        "volume": 1_000,
    })


class FramePreservingAdapterTests(unittest.TestCase):
    def test_marketdata_parallel_arrays_preserve_every_candle_and_time_domain(self):
        start, _ = session_bounds(SESSION)
        stamps = pd.date_range(start, periods=78, freq="5min")
        payload = {
            "s": "ok",
            "t": [int(value.timestamp()) for value in stamps],
            "o": [100 + index / 100 for index in range(78)],
            "h": [101 + index / 100 for index in range(78)],
            "l": [99 + index / 100 for index in range(78)],
            "c": [100.5 + index / 100 for index in range(78)],
            "v": [1_000 + index for index in range(78)],
            "updated": int((start + pd.Timedelta(hours=7)).timestamp()),
        }
        acquired = datetime(2026, 8, 31, 21, 0, tzinfo=timezone.utc)
        frame = parse_marketdata_stock_candles(
            payload, ticker="aapl", session_date=SESSION, interval_minutes=5,
            acquired_at_utc=acquired,
        )
        self.assertEqual(len(frame), 78)
        self.assertEqual(frame["timestamp_utc"].nunique(), 78)
        self.assertEqual(set(frame["interval_minutes"]), {5})
        self.assertEqual(set(frame["provider"]), {"MARKETDATA"})
        self.assertEqual(set(frame["session_date"]), {"2026-08-31"})
        self.assertTrue((frame["provider_observed_at_utc"] != frame["acquired_at_utc"]).all())

    def test_marketdata_mismatched_arrays_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "parallel-array"):
            parse_marketdata_stock_candles(
                {"s": "ok", "t": [1, 2], "o": [1], "h": [2, 2], "l": [1, 1], "c": [1, 1], "v": [1, 1]},
                ticker="AAPL", session_date=SESSION, interval_minutes=5,
            )


class CoverageAndPlanningTests(unittest.TestCase):
    def test_regular_and_early_close_counts_are_calendar_derived(self):
        regular_open, regular_close = session_bounds(SESSION)
        self.assertEqual(len(expected_intraday_timestamps(session_date=SESSION, start_utc=regular_open, end_utc=regular_close, interval_minutes=5)), 78)
        self.assertEqual(len(expected_intraday_timestamps(session_date=SESSION, start_utc=regular_open, end_utc=regular_close, interval_minutes=15)), 26)
        self.assertEqual(len(expected_intraday_timestamps(session_date=SESSION, start_utc=regular_open, end_utc=regular_close, interval_minutes=30)), 13)
        early = date(2026, 11, 27)
        early_open, early_close = session_bounds(early)
        self.assertEqual(len(expected_intraday_timestamps(session_date=early, start_utc=early_open, end_utc=early_close, interval_minutes=5)), 42)

    def test_quality_exposes_duplicates_gaps_and_out_of_scope_rows(self):
        start = datetime(2026, 8, 31, 13, 30, tzinfo=timezone.utc)
        expected = pd.date_range(start, periods=4, freq="5min")
        frame = bars(start, start + pd.Timedelta(minutes=15))
        frame = pd.concat([frame.iloc[[0]], frame.iloc[[0]], frame.iloc[[2]], bars(start + pd.Timedelta(hours=1), start + pd.Timedelta(hours=1))], ignore_index=True)
        quality = assess_intraday_quality(frame, expected, interval_minutes=5)
        self.assertEqual(quality.duplicate_count, 2)
        self.assertEqual(quality.missing_count, 2)
        self.assertEqual(quality.unexpected_count, 1)
        self.assertEqual(quality.completeness_status, "INVALID_DUPLICATES")

    def test_missing_ranges_coalesce_contiguous_only_and_respect_request_limit(self):
        start = pd.Timestamp("2026-08-31T13:30:00Z")
        expected = pd.date_range(start, periods=8, freq="5min")
        available = {expected[0], expected[3], expected[7]}
        ranges = missing_intraday_ranges(expected, available, interval_minutes=5, max_intervals_per_request=2)
        self.assertEqual(ranges, (
            (expected[1].to_pydatetime(), expected[2].to_pydatetime()),
            (expected[4].to_pydatetime(), expected[5].to_pydatetime()),
            (expected[6].to_pydatetime(), expected[6].to_pydatetime()),
        ))

    def test_interval_has_distinct_canonical_schema(self):
        self.assertEqual(intraday_schema_version(1), "underlying_intraday_bar_v1")
        self.assertEqual(intraday_schema_version(5), "underlying_intraday_bar_v2_5min")
        self.assertNotEqual(intraday_schema_version(5), intraday_schema_version(15))


class CanonicalResolverPhase3Tests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        registry = CanonicalRegistry(self.root / "control.sqlite"); registry.initialise()
        registry.register_run("R3", "DYNAMIC", SESSION)
        lifecycle = LifecycleManager(registry)
        for ticker in ("AAPL", "FAIL", "DROP"):
            event = lifecycle.register("R3", ticker, allowed_capabilities=(DatasetType.INTRADAY_BAR,))
            event = lifecycle.transition("R3", ticker, LifecycleState.ACTIVE_CORE, stage="PACKAGES", reason_code="TEST",
                                         expected_version=event.version, allowed_capabilities=(DatasetType.INTRADAY_BAR,))
            lifecycle.transition("R3", ticker, LifecycleState.ACTIVE_MORNING, stage="MARKET_STRUCTURE", reason_code="TEST",
                                 expected_version=event.version, allowed_capabilities=(DatasetType.INTRADAY_BAR,))
        lifecycle.create_worklist("R3", "MARKET_STRUCTURE", DatasetType.INTRADAY_BAR, ("AAPL", "FAIL"))
        self.flags = CanonicalFeatureFlags(enabled=True, write_through=True, stage_gating_enforced=True,
                                           offline_replay=False, ohlcv_mode="ACTIVE")
        self.start = datetime(2026, 8, 31, 13, 30, tzinfo=timezone.utc)
        self.end = self.start + pd.Timedelta(minutes=20)

    def tearDown(self):
        self.temporary.cleanup()

    def resolver(self, cutoff: datetime | None = None, invocation: str = "R3-I1") -> CanonicalMinuteBarResolver:
        return CanonicalMinuteBarResolver(
            registry_path=self.root / "control.sqlite", payload_root=self.root / "payloads",
            run_id="R3", invocation_id=invocation, evidence_cutoff_utc=cutoff, flags=self.flags,
        )

    def test_exact_cache_reuse_makes_zero_second_provider_calls(self):
        calls = []
        def fetch(ticker, start, end):
            calls.append((ticker, start, end)); return bars(start, end)
        first = self.resolver().resolve(ticker="AAPL", session_date=SESSION, start_utc=self.start, end_utc=self.end,
                                        fetch_missing=fetch, provider="MARKETDATA", interval_minutes=5,
                                        adjustment_convention="SPLIT_ADJUSTED")
        second = self.resolver().resolve(ticker="AAPL", session_date=SESSION, start_utc=self.start, end_utc=self.end,
                                         fetch_missing=fetch, provider="MARKETDATA", interval_minutes=5,
                                         adjustment_convention="SPLIT_ADJUSTED")
        self.assertEqual(first.physical_fetches, 1)
        self.assertEqual(second.physical_fetches, 0)
        self.assertEqual(len(calls), 1)
        self.assertEqual(first.quality.completeness_status, "COMPLETE")
        self.assertTrue({"dataset_id", "content_hash", "completeness_status"} <= set(first.frame.columns))
        self.assertTrue({"dataset_id", "content_hash", "completeness_status"} <= set(second.frame.columns))

    def test_developing_cutoff_defers_future_without_requesting_it(self):
        calls = []
        cutoff = self.start + pd.Timedelta(minutes=10)
        result = self.resolver(cutoff=cutoff).resolve(
            ticker="AAPL", session_date=SESSION, start_utc=self.start, end_utc=self.end,
            fetch_missing=lambda ticker, start, end: (calls.append((start, end)) or bars(start, end)),
            provider="MARKETDATA", interval_minutes=5, adjustment_convention="SPLIT_ADJUSTED",
        )
        self.assertEqual(result.request_plan.observable_count, 3)
        self.assertEqual(result.request_plan.deferred_count, 2)
        self.assertEqual(calls[0][1], cutoff)
        self.assertEqual(len(result.frame), 3)

    def test_partial_cache_fetches_only_newly_observable_range(self):
        calls = []
        first_cutoff = self.start + pd.Timedelta(minutes=10)
        fetch = lambda ticker, start, end: (calls.append((start, end)) or bars(start, end))
        self.resolver(cutoff=first_cutoff, invocation="R3-I1").resolve(
            ticker="AAPL", session_date=SESSION, start_utc=self.start, end_utc=self.end,
            fetch_missing=fetch, provider="MARKETDATA", interval_minutes=5, adjustment_convention="SPLIT_ADJUSTED",
        )
        result = self.resolver(cutoff=self.end, invocation="R3-I2").resolve(
            ticker="AAPL", session_date=SESSION, start_utc=self.start, end_utc=self.end,
            fetch_missing=fetch, provider="MARKETDATA", interval_minutes=5, adjustment_convention="SPLIT_ADJUSTED",
        )
        self.assertEqual(calls[1], (self.start + pd.Timedelta(minutes=15), self.end))
        self.assertEqual(result.physical_fetches, 1)
        self.assertEqual(len(result.frame), 5)

    def test_batch_blocks_inactive_and_isolates_provider_failure(self):
        calls = []
        def fetch(ticker, start, end):
            calls.append(ticker)
            if ticker == "FAIL":
                raise RuntimeError("provider unavailable")
            return bars(start, end)
        result = self.resolver().resolve_many(
            tickers=("AAPL", "FAIL", "DROP"), session_date=SESSION,
            start_utc=self.start, end_utc=self.end, fetch_missing_for_ticker=fetch,
            provider="MARKETDATA", interval_minutes=5, adjustment_convention="SPLIT_ADJUSTED",
        )
        self.assertEqual(result.succeeded, ("AAPL",))
        self.assertEqual(result.failed, ("FAIL",))
        self.assertEqual(result.blocked, ("DROP",))
        self.assertNotIn("DROP", calls)
        self.assertEqual(sorted(calls), ["AAPL", "FAIL"])


if __name__ == "__main__":
    unittest.main()
