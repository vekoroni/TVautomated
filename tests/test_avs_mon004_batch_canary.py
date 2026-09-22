"""The operational canary samples bounded, real assessment-bearing families."""

import sqlite3
import unittest

from tools.avs_mon004_batch_canary import select_families


class BatchCanarySelectionTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.db.row_factory = sqlite3.Row
        self.db.execute("""CREATE TABLE doi_contract_families(
            family_id TEXT,ticker TEXT,governed_direction TEXT,run_id TEXT,
            evidence_cutoff_utc TEXT)""")
        self.db.execute("CREATE TABLE doi_contract_assessments(family_id TEXT)")
        self.db.executemany("INSERT INTO doi_contract_families VALUES (?,?,?,?,?)", [
            ("c-late", "ABC", "CALL", "R", "2026-09-02T20:00:00+00:00"),
            ("c-early", "DEF", "CALL", "R", "2026-09-01T20:00:00+00:00"),
            ("p-early", "GHI", "PUT", "R", "2026-09-01T20:00:00+00:00"),
            ("p-empty", "JKL", "PUT", "R", "2026-09-01T19:00:00+00:00"),
        ])
        self.db.executemany("INSERT INTO doi_contract_assessments VALUES (?)", [
            ("c-late",), ("c-early",), ("p-early",),
        ])

    def tearDown(self):
        self.db.close()

    def test_balanced_and_assessment_bearing(self):
        rows = select_families(self.db, per_direction=1)
        self.assertEqual([row["family_id"] for row in rows],
                         ["c-early", "p-early"])

    def test_invalid_limit(self):
        with self.assertRaises(ValueError):
            select_families(self.db, per_direction=0)


if __name__ == "__main__":
    unittest.main()
