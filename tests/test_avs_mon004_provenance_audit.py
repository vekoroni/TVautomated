"""Raw historical chain rows must never become governed outcome evidence."""

import sqlite3
import unittest
from datetime import date

from tools.avs_mon004_provenance_audit import (
    NO_QUOTE, NOT_ELIGIBLE, UNVERSIONED, VERIFIED, classify_session,
)


class ProvenanceClassificationTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.db.execute("""CREATE TABLE chain_snapshots(
            ticker TEXT, quote_date TEXT, option_symbol TEXT)""")
        self.db.execute("""CREATE TABLE canonical_option_chain_revisions(
            ticker TEXT, quote_date TEXT, option_symbol TEXT)""")
        self.args = dict(ticker="ABC", contract_symbol="ABC261016C00100000",
                         session=date(2026, 9, 2))

    def tearDown(self):
        self.db.close()

    def classify(self, verified=False):
        return classify_session(self.db, verified=verified, **self.args)

    def test_no_row_is_not_evidence(self):
        self.assertEqual(self.classify(), NO_QUOTE)

    def test_direct_backfill_remains_research_only(self):
        self.db.execute("INSERT INTO chain_snapshots VALUES (?,?,?)",
                        tuple(["ABC", "2026-09-02", self.args["contract_symbol"]]))
        self.assertEqual(self.classify(), UNVERSIONED)

    def test_revision_requires_reader_verification(self):
        self.db.execute("INSERT INTO canonical_option_chain_revisions VALUES (?,?,?)",
                        ("ABC", "2026-09-02", self.args["contract_symbol"]))
        self.assertEqual(self.classify(), NOT_ELIGIBLE)
        self.assertEqual(self.classify(verified=True), VERIFIED)

    def test_other_contract_cannot_satisfy_exact_identity(self):
        self.db.execute("INSERT INTO chain_snapshots VALUES (?,?,?)",
                        ("ABC", "2026-09-02", "ABC261016P00100000"))
        self.assertEqual(self.classify(), NO_QUOTE)


if __name__ == "__main__":
    unittest.main()
