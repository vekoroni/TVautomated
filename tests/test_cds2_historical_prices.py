"""Regression tests for CDS-2 historical price write-through behavior."""

from __future__ import annotations

from datetime import date, timedelta
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from canonical_data import (  # noqa: E402
    CanonicalDailyHistoryAdapter,
    HistoricalPriceDatabase,
    canonical_history_is_fresh,
    history_date_is_fresh,
    observe_shadow_history,
    read_canonical_history,
    write_through_fetched_history,
)
from scripts import backfill_timeseries_into_packages as backfill  # noqa: E402


def bars(close_two: float = 11.5) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"date": "2026-08-20", "open": 10.0, "high": 11.0, "low": 9.0, "close": 10.5, "volume": 1000.0},
            {"date": "2026-08-21", "open": 11.0, "high": 12.0, "low": 10.0, "close": close_two, "volume": 1200.0},
        ]
    )


def recent_bars(count: int = 2) -> pd.DataFrame:
    end = date.today() - timedelta(days=1)
    start = end - timedelta(days=count - 1)
    return pd.DataFrame([
        {
            "date": start + timedelta(days=index),
            "open": 10.0 + index,
            "high": 11.0 + index,
            "low": 9.0 + index,
            "close": 10.5 + index,
            "volume": 1000.0 + index,
        }
        for index in range(count)
    ])


class HistoricalPriceDatabaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temporary.name)
        self.path = self.temp_path / "historical_prices.sqlite"
        self.database = HistoricalPriceDatabase(self.path)
        self.database.initialise()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_initial_fetch_inserts_and_replay_does_not_duplicate(self) -> None:
        first = self.database.ingest(
            "bp", bars(), provider="polygon", source_kind="provider_fetch"
        )
        second = self.database.ingest(
            "BP", bars(), provider="POLYGON", source_kind="provider_fetch"
        )
        self.assertEqual(first.inserted_rows, 2)
        self.assertEqual(second.inserted_rows, 0)
        self.assertEqual(second.unchanged_rows, 2)
        self.assertEqual(self.database.coverage("BP").row_count, 2)
        self.assertEqual(self.database.revision_count("BP"), 0)

    def test_new_tail_is_appended_and_price_revision_is_audited(self) -> None:
        self.database.ingest(
            "BP", bars(), provider="POLYGON", source_kind="MIGRATION_PACKAGE"
        )
        revised = bars(close_two=5.75)
        revised.loc[1, ["open", "high", "low", "close"]] = [5.5, 6.0, 5.0, 5.75]
        revised.loc[len(revised)] = {
            "date": "2026-08-24", "open": 5.8, "high": 6.2,
            "low": 5.6, "close": 6.0, "volume": 1500,
        }
        result = self.database.ingest(
            "BP", revised, provider="POLYGON", source_kind="PROVIDER_FETCH"
        )
        self.assertEqual(result.inserted_rows, 1)
        self.assertEqual(result.revised_rows, 1)
        self.assertEqual(result.unchanged_rows, 1)
        self.assertEqual(self.database.revision_count("BP"), 1)
        output = self.database.read("BP")
        self.assertEqual(output["date"].dt.date.tolist()[-1], date(2026, 8, 24))
        self.assertEqual(output.loc[output["date"] == "2026-08-21", "close"].iloc[0], 5.75)

    def test_partial_session_is_stored_but_excluded_from_default_reads(self) -> None:
        self.database.ingest(
            "BP", bars(), provider="POLYGON", source_kind="LATEST_FETCH",
            partial_dates=("2026-08-21",),
        )
        self.assertEqual(len(self.database.read("BP")), 1)
        self.assertEqual(len(self.database.read("BP", completed_only=False)), 2)
        self.assertEqual(self.database.coverage("BP").partial_rows, 1)

    def test_schema_and_health_are_valid(self) -> None:
        self.database.ingest(
            "BP", bars(), provider="POLYGON", source_kind="PROVIDER_FETCH"
        )
        self.assertTrue(self.database.validate_schema()["valid"])
        health = self.database.health()
        self.assertEqual(health["integrity_check"], "ok")
        self.assertEqual(health["rows"], 2)
        self.assertEqual(health["tickers"], 1)

    def test_write_through_is_off_by_default_and_active_when_explicit(self) -> None:
        disabled_path = self.temp_path / "disabled.sqlite"
        self.assertIsNone(
            write_through_fetched_history(
                "BP", bars(), provider="POLYGON", source_kind="PROVIDER_FETCH",
                environment={"AVSHUNTER_HISTORICAL_PRICE_DB": str(disabled_path)},
            )
        )
        self.assertFalse(disabled_path.exists())

        environment = {
            "AVSHUNTER_CANONICAL_DATA_ENABLED": "1",
            "AVSHUNTER_CANONICAL_WRITE_THROUGH": "1",
            "AVSHUNTER_CDS2_OHLCV_MODE": "ACTIVE",
            "AVSHUNTER_HISTORICAL_PRICE_DB": str(self.path),
        }
        result = write_through_fetched_history(
            "BP", bars(), provider="POLYGON", source_kind="PROVIDER_FETCH",
            environment=environment,
        )
        self.assertEqual(result.inserted_rows, 2)
        canonical = read_canonical_history(
            "BP", bars=1, reference_date=date(2026, 8, 24), environment=environment
        )
        self.assertEqual(len(canonical), 1)
        self.assertEqual(canonical.attrs["data_source"], "CANONICAL_HISTORICAL_PRICE_DB")

    def test_active_read_rejects_stale_history_but_refresh_code_can_inspect_it(self) -> None:
        self.database.ingest(
            "BP", bars(), provider="POLYGON", source_kind="PROVIDER_FETCH"
        )
        environment = {
            "AVSHUNTER_CANONICAL_DATA_ENABLED": "1",
            "AVSHUNTER_CANONICAL_WRITE_THROUGH": "1",
            "AVSHUNTER_CDS2_OHLCV_MODE": "ACTIVE",
            "AVSHUNTER_HISTORICAL_PRICE_DB": str(self.path),
        }

        governed = read_canonical_history(
            "BP", reference_date=date(2026, 8, 27), environment=environment
        )
        raw_for_refresh = read_canonical_history(
            "BP",
            max_staleness_days=None,
            reference_date=date(2026, 8, 27),
            environment=environment,
        )

        self.assertIsNone(governed)
        self.assertIsNotNone(raw_for_refresh)
        self.assertFalse(
            canonical_history_is_fresh(
                raw_for_refresh, reference_date=date(2026, 8, 27)
            )
        )
        self.assertTrue(
            history_date_is_fresh(
                "2026-08-24", reference_date=date(2026, 8, 27)
            )
        )

    def test_stale_canonical_backfill_fetches_only_tail_then_reuses_full_database(self) -> None:
        stale_end = date.today() - timedelta(days=6)
        stale_history = recent_bars(120).copy()
        shift = stale_end - stale_history["date"].max()
        stale_history["date"] = stale_history["date"].map(lambda value: value + shift)
        self.database.ingest(
            "BP", stale_history, provider="POLYGON", source_kind="INITIAL"
        )
        packages = self.temp_path / "packages"
        packages.mkdir()
        package_path = packages / "BP.package.json"
        package_path.write_text(
            json.dumps({"ticker": "BP", "run_id": "STALE_REFRESH_TEST"}),
            encoding="utf-8",
        )
        fetched_start = stale_end + timedelta(days=1)
        fresh_end = date.today() - timedelta(days=1)
        fetched_rows = [
            {
                "date": (fetched_start + timedelta(days=index)).isoformat(),
                "open": 130.0 + index,
                "high": 131.0 + index,
                "low": 129.0 + index,
                "close": 130.5 + index,
                "volume": 2000.0 + index,
            }
            for index in range((fresh_end - fetched_start).days + 1)
        ]
        environment = {
            "AVSHUNTER_CANONICAL_DATA_ENABLED": "1",
            "AVSHUNTER_CANONICAL_WRITE_THROUGH": "1",
            "AVSHUNTER_CDS2_OHLCV_MODE": "ACTIVE",
            "AVSHUNTER_HISTORICAL_PRICE_DB": str(self.path),
        }

        with patch.dict(os.environ, environment, clear=False), patch.object(
            backfill,
            "polygon_fetch_ohlcv_daily",
            return_value=fetched_rows,
        ) as fetch:
            success, reason = backfill.backfill_package(
                package_path,
                min_bars=120,
                start="2018-01-01",
                allow_polygon=True,
                api_key="test-key",
            )

        self.assertTrue(success)
        self.assertEqual(reason, "POLYGON")
        self.assertEqual(fetch.call_args.kwargs["start"], fetched_start.isoformat())
        repaired = json.loads(package_path.read_text(encoding="utf-8"))
        self.assertEqual(repaired["bar_data_as_of"], fresh_end.isoformat())
        self.assertGreaterEqual(len(repaired["ohlcv_daily"]), 120)
        self.assertEqual(
            repaired["data_contract"]["canonical_freshness_status"],
            "REFRESHED_FROM_PROVIDER_TAIL",
        )

    def test_short_canonical_history_fetches_full_range_not_empty_tail(self) -> None:
        self.database.ingest(
            "ACDC", recent_bars(20), provider="POLYGON", source_kind="INITIAL"
        )
        packages = self.temp_path / "packages"
        packages.mkdir()
        package_path = packages / "ACDC.package.json"
        package_path.write_text(
            json.dumps({"ticker": "ACDC", "run_id": "SHORT_HISTORY_TEST"}),
            encoding="utf-8",
        )
        fetched = recent_bars(130).to_dict(orient="records")
        for row in fetched:
            row["date"] = row["date"].isoformat()
        environment = {
            "AVSHUNTER_CANONICAL_DATA_ENABLED": "1",
            "AVSHUNTER_CANONICAL_WRITE_THROUGH": "1",
            "AVSHUNTER_CDS2_OHLCV_MODE": "ACTIVE",
            "AVSHUNTER_HISTORICAL_PRICE_DB": str(self.path),
        }

        with patch.dict(os.environ, environment, clear=False), patch.object(
            backfill, "polygon_fetch_ohlcv_daily", return_value=fetched,
        ) as fetch:
            success, reason = backfill.backfill_package(
                package_path, min_bars=120, start="2021-01-01",
                allow_polygon=True, api_key="test-key",
            )

        self.assertTrue(success)
        self.assertEqual(reason, "POLYGON")
        self.assertEqual(fetch.call_args.kwargs["start"], "2021-01-01")
        repaired = json.loads(package_path.read_text(encoding="utf-8"))
        self.assertGreaterEqual(len(repaired["ohlcv_daily"]), 120)
        self.assertEqual(
            repaired["data_contract"]["canonical_freshness_status"],
            "REFRESHED_FROM_PROVIDER_FULL_HISTORY",
        )

    def test_shadow_observation_never_replaces_legacy_frame(self) -> None:
        self.database.ingest(
            "BP", bars(), provider="POLYGON", source_kind="PROVIDER_FETCH"
        )
        metrics = self.temp_path / "metrics.jsonl"
        environment = {
            "AVSHUNTER_CANONICAL_DATA_ENABLED": "1",
            "AVSHUNTER_CDS2_OHLCV_MODE": "SHADOW",
            "AVSHUNTER_HISTORICAL_PRICE_DB": str(self.path),
            "AVSHUNTER_CDS2_METRICS_PATH": str(metrics),
        }
        legacy = bars()
        returned = observe_shadow_history(
            "BP", legacy, consumer="TEST", environment=environment
        )
        self.assertIs(returned, legacy)
        self.assertIn('"status": "COMPARED"', metrics.read_text(encoding="utf-8"))

    def test_incremental_adapter_fetches_tail_once_then_reuses_database(self) -> None:
        self.database.ingest(
            "BP", bars(), provider="POLYGON", source_kind="INITIAL"
        )

        class FakeFetcher:
            def __init__(self):
                self.calls = []

            def fetch_daily_bars(self, ticker, from_date, to_date, adjusted=True):
                self.calls.append((ticker, from_date, to_date, adjusted))
                return pd.DataFrame([{
                    "date": to_date, "open": 12.0, "high": 13.0,
                    "low": 11.5, "close": 12.5, "volume": 1600.0,
                }])

        fetcher = FakeFetcher()
        adapter = CanonicalDailyHistoryAdapter(self.database, fetcher)
        first = adapter.ensure_range(
            "BP", date(2026, 8, 20), date(2026, 8, 24), allow_fetch=True
        )
        second = adapter.ensure_range(
            "BP", date(2026, 8, 20), date(2026, 8, 24), allow_fetch=True
        )
        self.assertEqual(first.physical_request_count, 1)
        self.assertEqual(first.missing_ranges, ())
        self.assertEqual(second.physical_request_count, 0)
        self.assertEqual(len(fetcher.calls), 1)

    def test_production_launchers_enable_write_through_and_active_reads(self) -> None:
        for launcher_name in ("run_evening.bat", "run_premarket.bat"):
            launcher = (ROOT / launcher_name).read_text(encoding="utf-8")
            self.assertIn("AVSHUNTER_CANONICAL_DATA_ENABLED=1", launcher)
            self.assertIn("AVSHUNTER_CANONICAL_WRITE_THROUGH=1", launcher)
            self.assertIn("AVSHUNTER_CDS2_OHLCV_MODE=ACTIVE", launcher)
            self.assertIn("data\\canonical\\historical_prices.sqlite", launcher)

    @unittest.skipUnless(os.name == "nt", "Windows batch launcher regression")
    def test_production_launchers_fall_back_to_a_usable_python_and_validate_flags(self) -> None:
        for launcher_name in ("run_evening.bat", "run_premarket.bat"):
            result = subprocess.run(
                [
                    "cmd.exe", "/d", "/c", str(ROOT / launcher_name),
                    "--cds-launcher-self-test",
                ],
                cwd=ROOT,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=90,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout)
            self.assertIn("CDS-2 startup flags: OK", result.stdout)
            self.assertIn("Python:", result.stdout)
            self.assertNotIn("[ERROR]", result.stdout)

    def test_direct_orchestrator_evening_command_activates_cds_runtime(self) -> None:
        environment = os.environ.copy()
        for name in (
            "AVSHUNTER_CANONICAL_DATA_ENABLED",
            "AVSHUNTER_CANONICAL_WRITE_THROUGH",
            "AVSHUNTER_CDS2_OHLCV_MODE",
            "AVSHUNTER_HISTORICAL_PRICE_DB",
            "AVSHUNTER_STAGE_GATING_ENFORCED",
        ):
            environment.pop(name, None)

        result = subprocess.run(
            [
                sys.executable,
                str(ROOT / "intelligent_orchestrator.py"),
                "--evening",
                "--cds-startup-self-test",
            ],
            cwd=ROOT,
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=90,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn(
            "CDS-2 orchestrator runtime: enabled=True write_through=True mode=ACTIVE",
            result.stdout,
        )
        self.assertIn("CDS-2 child-process inheritance self-test: PASS", result.stdout)
        self.assertIn("CDS-2 orchestrator startup self-test: PASS", result.stdout)
        self.assertIn("CDS-3 stage gating: ENFORCED", result.stdout)
        self.assertIn("data\\canonical\\historical_prices.sqlite", result.stdout)

    def test_backfill_direct_script_launch_can_import_canonical_data(self) -> None:
        self.database.ingest(
            "BP", recent_bars(), provider="POLYGON", source_kind="PROVIDER_FETCH"
        )
        packages = self.temp_path / "packages"
        packages.mkdir()
        package_path = packages / "BP.package.json"
        package_path.write_text(
            json.dumps({"ticker": "BP", "run_id": "CDS2_IMPORT_TEST"}),
            encoding="utf-8",
        )
        (packages / "index.json").write_text(
            json.dumps({
                "packages": [{
                    "ticker": "BP",
                    "status": "BUILT",
                    "package_path": str(package_path),
                }]
            }),
            encoding="utf-8",
        )

        environment = os.environ.copy()
        environment.pop("PYTHONPATH", None)
        environment.update({
            "AVSHUNTER_CANONICAL_DATA_ENABLED": "1",
            "AVSHUNTER_CANONICAL_WRITE_THROUGH": "1",
            "AVSHUNTER_CDS2_OHLCV_MODE": "ACTIVE",
            "AVSHUNTER_HISTORICAL_PRICE_DB": str(self.path),
        })
        result = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts" / "backfill_timeseries_into_packages.py"),
                "--packages-dir", str(packages),
                "--min-bars", "2",
            ],
            cwd=self.temp_path,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("CANONICAL_HISTORICAL_PRICE_DB: 1", result.stdout)
        repaired = json.loads(package_path.read_text(encoding="utf-8"))
        self.assertEqual(
            repaired["timeseries"]["source"], "CANONICAL_HISTORICAL_PRICE_DB"
        )
        self.assertTrue(repaired["data_contract"]["has_ohlcv_daily"])
        self.assertEqual(
            repaired["data_contract"]["actuarial_data_quality"], "OHLCV_OK"
        )
        self.assertNotIn("error", repaired["timeseries"])


if __name__ == "__main__":
    unittest.main()
