"""Adversarial request-size checks for complete local, bounded provider evidence."""
import json
from pathlib import Path
import tempfile
import unittest

from worker3.adapters.claude_v2 import ClaudeV2Adapter
from worker3.adapters.jobs import JobStore
from worker3.domain import (ContractError, Direction, EvidenceBundle, Identity,
                            Observation, WorkerJob, canonical, digest)
from worker3.integration import AvshunterSourceBridge, Worker3Coordinator
from worker3.v2.assessment import AssessmentContext, PROMPT, build_evidence
from tests.test_worker3_activation import INTEGRATION_POLICY
from tests.test_worker3_avshunter_source_bridge import SourceFixture, RUN_ID


STAMP = "2026-09-21T14:00:00Z"


def _context(*, nested=True, unrelated=False):
    identity = Identity("20260920_203115", "test-invocation", "2026-09-18",
                        "AAA", "thesis-1", Direction.CALL, 5)
    row = {"ticker": "AAA", "thesis_id": "thesis-1", "governed_direction": "CALL",
           "trigger_primary": "PRICE_CONFIRMATION", "source_note": "Observe only; advisory."}
    if nested:
        row["source_payload_json"] = canonical({"history": "source-detail-" * 33000})
        row["field_provenance_json"] = canonical({"lineage": "field-lineage-" * 11000})
    doc = {"schema_version": "worker3_native_document_v1", "source_document": {"row": row}}
    observations = [Observation("lab-native", "native_document_lab_signal_book",
                                canonical(doc), "structured_json", "lab:source", "a" * 64,
                                STAMP, STAMP, ticker="AAA")]
    observations.append(Observation("price", "signal_price", 20.0, "USD", "price:source",
                                    "b" * 64, STAMP, STAMP, ticker="AAA"))
    if unrelated:
        observations.append(Observation("unrelated", "unrelated_document", "x" * 600000,
                                        "structured_json", "other:source", "c" * 64,
                                        STAMP, STAMP, ticker="AAA"))
    job = WorkerJob(EvidenceBundle(identity, STAMP, tuple(observations)),
                    "ANTHROPIC", "fixture-model", PROMPT)
    return AssessmentContext(job)


class NoTransport:
    def create(self, *_args, **_kwargs):
        raise AssertionError("provider must not be called during request construction")


class LargeEvidenceTests(unittest.TestCase):
    def test_large_lab_row_prepares_through_real_source_bridge(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fixture = SourceFixture(root)
            fixture.rows[0]["source_payload_json"] = canonical({"history": "source-detail-" * 33000})
            fixture.rows[0]["field_provenance_json"] = canonical({"lineage": "field-lineage-" * 11000})
            fixture.write_run()
            store = JobStore(root / "jobs.sqlite", budget_microusd=1_000_000)
            try:
                coordinator = Worker3Coordinator(AvshunterSourceBridge(root), store,
                                                 INTEGRATION_POLICY)
                prepared = coordinator.prepare_run(
                    RUN_ID, provider="ANTHROPIC", model="fixture-model", now=1000,
                    tickers=("AAA",), call_ceiling_microusd=100000,
                    max_input_bytes=500000, max_output_tokens=8192)
                self.assertEqual(prepared.entries[0].status, "JOB_PREPARED")
                context = coordinator.restore_context(prepared.entries[0].job_id)
                request = ClaudeV2Adapter(NoTransport(), 8192, 500000, 30,
                                          context).request_for(context.job)
                self.assertLessEqual(len(canonical(request).encode("utf-8")), 500000)
            finally:
                store.close()

    def test_native_nested_payload_is_projected_without_changing_local_truth(self):
        context = _context()
        full = build_evidence(context)
        full_hash = digest(full)
        adapter = ClaudeV2Adapter(NoTransport(), 8192, 500000, 300, context)
        request = adapter.request_for(context.job)
        self.assertLessEqual(len(canonical(request).encode("utf-8")), 500000)
        self.assertEqual(request, adapter.request_for(context.job))
        packet = json.loads(request["messages"][0]["content"])
        projected = packet["untrusted_bound_evidence"]
        ref = next(ref for ref, item in full["catalog"].items()
                   if item.get("observation", {}).get("field") == "native_document_lab_signal_book")
        original = full["catalog"][ref]
        wire = projected["catalog"][ref]
        manifest = wire["provider_projection"]
        self.assertEqual(manifest["full_value_sha256"], digest(json.loads(original["value"])))
        self.assertEqual(set(manifest["omitted_nested_fields"]),
                         {"source_payload_json", "field_provenance_json"})
        self.assertNotIn("value", wire)  # No second copy of the structured source.
        wire_row = json.loads(wire["observation"]["value"])["source_document"]["row"]
        self.assertEqual(wire_row["trigger_primary"], "PRICE_CONFIRMATION")
        self.assertNotIn("source_payload_json", wire_row)
        self.assertEqual(digest(build_evidence(context)), full_hash)
        self.assertEqual(packet["output_contract"]["context_hash"], context.context_hash)
        price_ref = next(k for k, v in full["catalog"].items()
                         if v.get("observation", {}).get("field") == "signal_price")
        self.assertEqual(projected["catalog"][price_ref], full["catalog"][price_ref])

    def test_unrelated_oversized_evidence_still_fails_closed(self):
        context = _context(unrelated=True)
        with self.assertRaisesRegex(ContractError, "exceeds byte limit"):
            ClaudeV2Adapter(NoTransport(), 8192, 500000, 300, context).request_for(context.job)

    def test_no_nested_fields_leaves_existing_wire_contract_unchanged(self):
        context = _context(nested=False)
        request = ClaudeV2Adapter(NoTransport(), 8192, 500000, 300, context).request_for(context.job)
        packet = json.loads(request["messages"][0]["content"])
        self.assertEqual(packet["untrusted_bound_evidence"], build_evidence(context))


if __name__ == "__main__":
    unittest.main()
