from __future__ import annotations

from datetime import date
from pathlib import Path
import tempfile
import unittest

import pandas as pd

from canonical_data import (
    CanonicalFeatureFlags,
    CanonicalOptionChainService,
    CanonicalRegistry,
    DatasetType,
    LifecycleManager,
    LifecycleState,
    publish_options_worklist,
    resolve_completed_session_date,
)
from canonical_data.errors import FetchNotAuthorised


RUN_ID = "20260827_200000"
SESSION = date(2026, 8, 27)


def _chain(
    symbol: str = "TEST260918C00100000",
    quote_timestamp: str = "2026-08-27T20:00:00+00:00",
) -> pd.DataFrame:
    return pd.DataFrame(
        [{
            "underlying": "TEST", "symbol": symbol, "right": "C",
            "strike": 100.0, "dte": 22.0, "open_interest": 500,
            "bid": 4.9, "ask": 5.1, "mark": 5.0,
            "delta": 0.5, "gamma": 0.02,
            "quote_timestamp_utc": quote_timestamp,
        }]
    )


def _registry(root: Path, tickers=("TEST", "EQUITY")) -> CanonicalRegistry:
    registry = CanonicalRegistry(root / "control.sqlite")
    registry.initialise()
    registry.register_run(RUN_ID, "EVENING", SESSION)
    lifecycle = LifecycleManager(registry)
    for ticker in tickers:
        event = lifecycle.register(
            RUN_ID, ticker, allowed_capabilities=(DatasetType.DAILY_OHLCV,)
        )
        lifecycle.transition(
            RUN_ID, ticker, LifecycleState.ACTIVE_CORE,
            stage="PACKAGES", reason_code="PACKAGE_BUILT",
            expected_version=event.version,
            allowed_capabilities=(DatasetType.DAILY_OHLCV,),
        )
    return registry


def _flags() -> CanonicalFeatureFlags:
    return CanonicalFeatureFlags(
        enabled=True, write_through=True, stage_gating_enforced=True,
        offline_replay=False, ohlcv_mode="ACTIVE",
    )


def _offline_flags() -> CanonicalFeatureFlags:
    return CanonicalFeatureFlags(
        enabled=True, write_through=False, stage_gating_enforced=True,
        offline_replay=True, ohlcv_mode="ACTIVE",
    )


class CDS4OptionChainStoreTests(unittest.TestCase):
    def _service(self, root: Path) -> CanonicalOptionChainService:
        return CanonicalOptionChainService(
            registry_path=root / "control.sqlite",
            payload_root=root / "options",
            run_id=RUN_ID,
            session_date=SESSION,
            dte_max=110,
            min_open_interest=5,
            flags=_flags(),
        )

    def test_options_worklist_excludes_equity_only_and_reconciles(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            registry = _registry(Path(temporary))
            report = publish_options_worklist(
                registry, run_id=RUN_ID,
                input_tickers=("TEST", "EQUITY"), eligible_tickers=("TEST",),
            )
            self.assertTrue(report.reconciled)
            self.assertEqual(report.authorised_count, 1)
            self.assertEqual(report.excluded_count, 1)
            lifecycle = LifecycleManager(registry)
            self.assertEqual(
                lifecycle.stage_worklist_tickers(
                    RUN_ID, "OPTIONS", DatasetType.OPTION_CHAIN
                ),
                ("TEST",),
            )
            self.assertIs(
                lifecycle.latest(RUN_ID, "EQUITY").state,
                LifecycleState.ACTIVE_EQUITY_ONLY,
            )

    def test_marketdata_chain_writes_once_then_same_session_cache_hits(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            registry = _registry(root, tickers=("TEST",))
            publish_options_worklist(
                registry, run_id=RUN_ID,
                input_tickers=("TEST",), eligible_tickers=("TEST",),
            )
            service = self._service(root)
            calls = {"marketdata": 0}

            def marketdata(_: str) -> pd.DataFrame:
                calls["marketdata"] += 1
                return _chain()

            first = service.get("TEST", marketdata_fetch=marketdata)
            second = service.get("TEST", marketdata_fetch=marketdata)
            self.assertEqual(first.resolution, "PROVIDER_FETCH")
            self.assertIn(second.resolution, {"EXACT_HIT", "SUPERSET_HIT"})
            self.assertEqual(calls, {"marketdata": 1})
            self.assertEqual(service.ledger.physical_request_count(RUN_ID), 1)
            self.assertEqual(len(registry.list_dataset_records(DatasetType.OPTION_CHAIN)), 1)

            record = registry.list_dataset_records(DatasetType.OPTION_CHAIN)[0]
            self.assertEqual(record.session_date, SESSION)
            self.assertEqual(record.as_of.isoformat(), "2026-08-27T20:00:00+00:00")

    def test_marketdata_empty_stands_down_without_polygon_request(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            registry = _registry(root, tickers=("TEST",))
            publish_options_worklist(
                registry, run_id=RUN_ID,
                input_tickers=("TEST",), eligible_tickers=("TEST",),
            )
            service = self._service(root)
            calls = {"marketdata": 0}

            def marketdata(_: str) -> pd.DataFrame:
                calls["marketdata"] += 1
                return pd.DataFrame()

            result = service.get("TEST", marketdata_fetch=marketdata)
            self.assertEqual(result.provider, "MARKETDATA")
            self.assertEqual(result.resolution, "PROVIDER_EMPTY")
            self.assertEqual(calls, {"marketdata": 1})
            self.assertEqual(service.ledger.physical_request_count(RUN_ID), 1)

    def test_offline_replay_cache_miss_never_calls_provider(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            registry = _registry(root, tickers=("TEST",))
            publish_options_worklist(
                registry, run_id=RUN_ID,
                input_tickers=("TEST",), eligible_tickers=("TEST",),
            )
            service = CanonicalOptionChainService(
                registry_path=root / "control.sqlite",
                payload_root=root / "options",
                run_id=RUN_ID,
                session_date=SESSION,
                dte_max=110,
                min_open_interest=5,
                flags=_offline_flags(),
            )
            called = False

            def should_not_run(_: str) -> pd.DataFrame:
                nonlocal called
                called = True
                return _chain()

            result = service.get("TEST", marketdata_fetch=should_not_run)
            self.assertEqual(result.resolution, "OFFLINE_CACHE_MISS")
            self.assertEqual(result.provider, "CANONICAL")
            self.assertTrue(result.frame.empty)
            self.assertFalse(called)
            self.assertEqual(service.ledger.physical_request_count(RUN_ID), 0)

    def test_provider_payload_must_match_completed_session(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            registry = _registry(root, tickers=("TEST",))
            publish_options_worklist(
                registry, run_id=RUN_ID,
                input_tickers=("TEST",), eligible_tickers=("TEST",),
            )
            service = self._service(root)

            with self.assertRaisesRegex(ValueError, "quote/session mismatch"):
                service.get(
                    "TEST",
                    marketdata_fetch=lambda _: _chain(
                        quote_timestamp="2026-08-26T20:00:00+00:00"
                    ),
                )
            self.assertEqual(len(registry.list_dataset_records(DatasetType.OPTION_CHAIN)), 0)

    def test_provider_payload_requires_quote_timestamp_coverage(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            registry = _registry(root)
            publish_options_worklist(
                registry, run_id=RUN_ID,
                input_tickers=("TEST",), eligible_tickers=("TEST",),
            )
            service = self._service(root)
            sparse = _chain()
            sparse = pd.concat([sparse] * 5, ignore_index=True)
            sparse.loc[1:, "quote_timestamp_utc"] = None
            with self.assertRaisesRegex(ValueError, "timestamp coverage is insufficient"):
                service.get("TEST", marketdata_fetch=lambda _: sparse)
            self.assertEqual(len(registry.list_dataset_records(DatasetType.OPTION_CHAIN)), 0)

    def test_completed_session_comes_from_governed_bar_asof(self) -> None:
        self.assertEqual(
            resolve_completed_session_date(["2026-08-27", "2026-08-27"]),
            SESSION,
        )
        with self.assertRaisesRegex(ValueError, "ambiguous"):
            resolve_completed_session_date(["2026-08-27", "2026-08-28"])
        with self.assertRaisesRegex(ValueError, "unavailable"):
            resolve_completed_session_date([None, ""])

    def test_non_worklisted_ticker_is_blocked_before_callback(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            registry = _registry(root)
            publish_options_worklist(
                registry, run_id=RUN_ID,
                input_tickers=("TEST", "EQUITY"), eligible_tickers=("TEST",),
            )
            service = self._service(root)
            called = False

            def should_not_run(_: str) -> pd.DataFrame:
                nonlocal called
                called = True
                return _chain()

            with self.assertRaises(FetchNotAuthorised):
                service.get(
                    "EQUITY",
                    marketdata_fetch=should_not_run,
                )
            self.assertFalse(called)


if __name__ == "__main__":
    unittest.main()
