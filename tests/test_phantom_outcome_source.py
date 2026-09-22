"""Point-in-time and provenance tests for the Phantom outcome source."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from datetime import date, datetime, timezone
from pathlib import Path

from canonical_data.phantom_outcome_source import (
    PhantomOutcomeProvenanceError, PhantomOutcomeSourceReader,
)
from domain.data_projection import PHANTOM_OPTION_CHAIN_PROJECTION


UTC = timezone.utc


class PhantomOutcomeSourceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.control = self.root / "control.sqlite"
        self.phantom = self.root / "phantom.sqlite"
        self.symbol = "ABC261016C00100000"
        self.dataset_id = "dataset-1"
        self.payload = {
            "ticker": "ABC", "quote_date": "2026-09-02",
            "option_symbol": self.symbol,
            "updated_ts": int(datetime(2026, 9, 2, 20, tzinfo=UTC).timestamp()),
            "created_at_utc": "2026-09-02T20:01:00+00:00",
            "source": "MARKETDATA", "bid": 2.0, "ask": 2.2,
            "volume": 10, "open_interest": 20, "iv": 0.4,
        }
        self.row_json = json.dumps(self.payload, sort_keys=True, separators=(",", ":"))
        self.row_hash = hashlib.sha256(self.row_json.encode()).hexdigest()
        with closing(sqlite3.connect(self.control)) as db:
            db.execute("""CREATE TABLE dataset_registry(
                dataset_id TEXT PRIMARY KEY,dataset_type TEXT,instrument_id TEXT,
                session_date TEXT,provider TEXT,completeness_status TEXT,
                content_hash TEXT,observed_at TEXT,registered_at TEXT)""")
            db.execute("INSERT INTO dataset_registry VALUES (?,?,?,?,?,?,?,?,?)",
                       (self.dataset_id, "OPTION_CHAIN", "ABC", "2026-09-02",
                        "MARKETDATA", "COMPLETE", "file-hash",
                        "2026-09-02T20:01:00+00:00",
                        "2026-09-02T20:02:00+00:00"))
            db.commit()
        with closing(sqlite3.connect(self.phantom)) as db:
            db.executescript("""
                CREATE TABLE canonical_option_chain_revisions(
                    dataset_id TEXT,event_id TEXT,ticker TEXT,quote_date TEXT,
                    option_symbol TEXT,row_content_hash TEXT,row_json TEXT,
                    source_run_id TEXT,dataset_as_of_utc TEXT,
                    projected_at_utc TEXT,
                    PRIMARY KEY(dataset_id,option_symbol));
                CREATE INDEX idx_revisions ON canonical_option_chain_revisions(
                    ticker,quote_date,option_symbol);
                CREATE TABLE canonical_projection_receipts(
                    event_id TEXT PRIMARY KEY,projection_name TEXT,
                    dataset_id TEXT,ticker TEXT,session_date TEXT,
                    content_hash TEXT,rows_projected INTEGER,projected_at_utc TEXT);
            """)
            db.execute("INSERT INTO canonical_option_chain_revisions VALUES (?,?,?,?,?,?,?,?,?,?)",
                       (self.dataset_id, "event-1", "ABC", "2026-09-02",
                        self.symbol, self.row_hash, self.row_json, "RUN-1",
                        "2026-09-02T20:00:00+00:00",
                        "2026-09-02T20:03:00+00:00"))
            db.execute("INSERT INTO canonical_projection_receipts VALUES (?,?,?,?,?,?,?,?)",
                       ("event-1", PHANTOM_OPTION_CHAIN_PROJECTION, self.dataset_id,
                        "ABC", "2026-09-02", "file-hash", 1,
                        "2026-09-02T20:03:00+00:00"))
            db.commit()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _read(self, cutoff: datetime | None = None):
        return PhantomOutcomeSourceReader(self.control, self.phantom).read_sessions(
            ticker="ABC", contract_symbol=self.symbol,
            sessions=(date(2026, 9, 2),),
            assessment_cutoff_utc=datetime(2026, 9, 1, 20, tzinfo=UTC),
            evaluation_cutoff_utc=cutoff or datetime(2026, 9, 3, tzinfo=UTC),
        )

    def test_verified_revision_retains_quote_and_availability_time(self) -> None:
        items = self._read()
        self.assertEqual(len(items), 1)
        item = items[0]
        self.assertEqual(item.observation.dataset_id, self.dataset_id)
        self.assertEqual(item.observation.quote_at_utc,
                         datetime(2026, 9, 2, 20, tzinfo=UTC))
        self.assertEqual(item.observation.available_at_utc,
                         datetime(2026, 9, 2, 20, 3, tzinfo=UTC))
        self.assertTrue(item.observation.observation_id.startswith("PHANTOM_REV:"))
        self.assertEqual(item.row_content_hash, self.row_hash)

    def test_later_projection_is_not_visible_early(self) -> None:
        self.assertEqual(self._read(datetime(2026, 9, 2, 20, 2, tzinfo=UTC)), ())

    def test_corrupt_revision_hash_fails_closed(self) -> None:
        with closing(sqlite3.connect(self.phantom)) as db:
            db.execute("UPDATE canonical_option_chain_revisions SET row_content_hash='BAD'")
            db.commit()
        with self.assertRaises(PhantomOutcomeProvenanceError):
            self._read()

    def test_wrong_registry_identity_fails_closed(self) -> None:
        with closing(sqlite3.connect(self.control)) as db:
            db.execute("UPDATE dataset_registry SET instrument_id='XYZ'")
            db.commit()
        with self.assertRaises(PhantomOutcomeProvenanceError):
            self._read()

    def test_exact_symbol_only(self) -> None:
        self.assertEqual(PhantomOutcomeSourceReader(self.control, self.phantom).read_sessions(
            ticker="ABC", contract_symbol="ABC261016P00100000",
            sessions=(date(2026, 9, 2),),
            assessment_cutoff_utc=datetime(2026, 9, 1, 20, tzinfo=UTC),
            evaluation_cutoff_utc=datetime(2026, 9, 3, tzinfo=UTC),
        ), ())

    def test_unversioned_chain_snapshot_is_not_promoted(self) -> None:
        with closing(sqlite3.connect(self.phantom)) as db:
            db.execute("DELETE FROM canonical_option_chain_revisions")
            db.execute("""CREATE TABLE chain_snapshots(
                ticker TEXT,quote_date TEXT,option_symbol TEXT,bid REAL,ask REAL)""")
            db.execute("INSERT INTO chain_snapshots VALUES (?,?,?,?,?)",
                       ("ABC", "2026-09-02", self.symbol, 2.0, 2.2))
            db.commit()
        self.assertEqual(self._read(), ())


if __name__ == "__main__":
    unittest.main()
