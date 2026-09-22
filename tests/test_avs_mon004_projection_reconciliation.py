"""Future-chain receipt and revision counts are an explicit acceptance gate."""

import unittest

from tools.avs_mon004_projection_reconciliation import classify_projection


class ProjectionClassificationTests(unittest.TestCase):
    def test_complete_matching_receipt_and_rows(self):
        self.assertEqual(classify_projection(
            dataset_hash="abc", delivery_state="COMPLETED",
            receipt_hash="abc", rows_projected=3, revision_count=3,
        ), "RECONCILED_RECEIPT_AND_ROW_COUNT")

    def test_missing_event_is_not_complete(self):
        self.assertEqual(classify_projection(
            dataset_hash="abc", delivery_state=None,
            receipt_hash=None, rows_projected=None, revision_count=0,
        ), "NO_PROJECTION_EVENT")

    def test_completed_outbox_without_receipt_is_not_complete(self):
        self.assertEqual(classify_projection(
            dataset_hash="abc", delivery_state="COMPLETED",
            receipt_hash=None, rows_projected=None, revision_count=3,
        ), "COMPLETED_WITHOUT_RECEIPT")

    def test_bad_hash_or_missing_revisions_fail(self):
        self.assertEqual(classify_projection(
            dataset_hash="abc", delivery_state="COMPLETED",
            receipt_hash="wrong", rows_projected=3, revision_count=3,
        ), "RECEIPT_HASH_MISMATCH")
        self.assertEqual(classify_projection(
            dataset_hash="abc", delivery_state="COMPLETED",
            receipt_hash="abc", rows_projected=3, revision_count=2,
        ), "REVISION_COUNT_MISMATCH")


if __name__ == "__main__":
    unittest.main()
