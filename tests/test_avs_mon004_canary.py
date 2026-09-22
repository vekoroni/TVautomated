"""Safety and arithmetic tests for the read-only outcome activation canary."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from canonical_data.historical_prices import DEFAULT_ADJUSTMENT
from tools.avs_mon004_canary import connect_read_only, isolated_index_probe, run_canary


class OutcomeCanaryTests(unittest.TestCase):
    def test_index_probe_uses_only_temporary_key_store(self) -> None:
        result = isolated_index_probe([
            ("family-a", "2026-09-01T20:00:00+00:00"),
            ("family-b", "2026-09-02T20:00:00+00:00"),
        ])
        self.assertEqual(result["keys_copied"], 2)
        self.assertGreaterEqual(result["index_growth_bytes"], 0)
        self.assertGreaterEqual(result["index_build_wal_bytes_before_checkpoint"], 0)

    def test_live_probe_is_read_only_and_reconciles_exact_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            control_path = root / "control.sqlite"
            price_path = root / "prices.sqlite"
            phantom_path = root / "phantom.sqlite"
            with closing(sqlite3.connect(control_path)) as control:
                control.executescript("""
                    CREATE TABLE doi_contract_families(
                        family_id TEXT PRIMARY KEY, run_id TEXT,
                        evidence_cutoff_utc TEXT, ticker TEXT,
                        governed_direction TEXT);
                    CREATE TABLE doi_contract_assessments(
                        assessment_id TEXT PRIMARY KEY, family_id TEXT,
                        contract_symbol TEXT, evidence_cutoff_utc TEXT,
                        observation_id TEXT);
                    CREATE TABLE option_contract_observations(
                        observation_id TEXT PRIMARY KEY, contract_symbol TEXT,
                        ticker TEXT, source_dataset_id TEXT,
                        quote_as_of TEXT, observed_at TEXT, bid REAL, ask REAL);
                    CREATE TABLE dataset_registry(dataset_id TEXT PRIMARY KEY,
                        session_date TEXT);
                    CREATE TABLE doi_outcome_labels(label_id TEXT PRIMARY KEY);
                """)
                control.execute("INSERT INTO doi_contract_families VALUES (?,?,?,?,?)",
                                ("family-a", "RUN-A", "2026-09-01T20:00:00+00:00",
                                 "ABC", "CALL"))
                control.execute("INSERT INTO doi_contract_assessments VALUES (?,?,?,?,?)",
                                ("assessment-a", "family-a", "ABC261016C00100000",
                                 "2026-09-01T20:00:00+00:00", "origin"))
                control.executemany("INSERT INTO dataset_registry VALUES (?,?)", [
                    ("dataset-origin", "2026-09-01"),
                    ("dataset-future", "2026-09-02"),
                ])
                control.executemany(
                    "INSERT INTO option_contract_observations VALUES (?,?,?,?,?,?,?,?)", [
                        ("origin", "ABC261016C00100000", "ABC", "dataset-origin",
                         "2026-09-01T20:00:00+00:00", "2026-09-01T20:01:00+00:00", 1, 1.2),
                        ("future", "ABC261016C00100000", "ABC", "dataset-future",
                         "2026-09-02T20:00:00+00:00", "2026-09-02T20:01:00+00:00", 2, 2.2),
                    ],
                )
                control.commit()
            with closing(sqlite3.connect(price_path)) as prices:
                prices.execute("""CREATE TABLE ohlcv_daily(
                    ticker TEXT, trading_date TEXT, bar_status TEXT,
                    adjustment_convention TEXT, observed_at TEXT)""")
                prices.executemany("INSERT INTO ohlcv_daily VALUES (?,?,?,?,?)", [
                    ("ABC", "2026-09-02", "COMPLETE", DEFAULT_ADJUSTMENT,
                     "2026-09-02T20:10:00+00:00"),
                    ("ABC", "2026-09-03", "COMPLETE", DEFAULT_ADJUSTMENT,
                     "2026-09-03T20:10:00+00:00"),
                ])
                prices.commit()
            with closing(sqlite3.connect(phantom_path)) as phantom:
                phantom.execute("""CREATE TABLE chain_snapshots(
                    ticker TEXT, quote_date TEXT, option_symbol TEXT,
                    bid REAL, ask REAL,
                    PRIMARY KEY(ticker,quote_date,option_symbol))""")
                phantom.execute("INSERT INTO chain_snapshots VALUES (?,?,?,?,?)",
                                ("ABC", "2026-09-02", "ABC261016C00100000", 2, 2.2))
                phantom.commit()
            before = control_path.read_bytes()
            result = run_canary(control_path, price_path, phantom_path)
            self.assertEqual(control_path.read_bytes(), before)
            self.assertEqual(result["quote_coverage"]["sample_count"], 1)
            self.assertEqual(result["quote_coverage"]["by_horizon"]["1"]
                             ["full_exact_two_sided_path"], 1)
            self.assertEqual(result["quote_coverage"]["by_horizon"]["5"]
                             ["underlying_not_mature"], 1)
            self.assertEqual(result["quote_coverage"]["phantom_by_horizon"]["1"]
                             ["full_exact_two_sided_path"], 1)
            with closing(connect_read_only(control_path)) as read_only:
                with self.assertRaises(sqlite3.OperationalError):
                    read_only.execute("CREATE TABLE forbidden(x)")


if __name__ == "__main__":
    unittest.main()
