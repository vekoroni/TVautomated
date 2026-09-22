"""Post-dispatch failures retain evidence for offline diagnosis, never retry."""

import json
import unittest

from worker3.application import ProviderResponse
from worker3.domain import ContractError
from worker3.v2.assessment import validate_assessment
from tests import test_worker3_activation as activation_tests


class ValidationQuarantineTests(unittest.TestCase):
    setUp = activation_tests.Worker3ActivationTests.setUp
    tearDown = activation_tests.Worker3ActivationTests.tearDown
    _release = activation_tests.Worker3ActivationTests._release
    _prepared = activation_tests.Worker3ActivationTests._prepared
    _runtime = activation_tests.Worker3ActivationTests._runtime

    def _execute_invalid(self, transport):
        job_id = self._prepared()
        runtime = self._runtime()
        runtime.activate((job_id,), operator_approval_id="approved", now=1001.0)
        with self.assertRaisesRegex(ContractError, "controlled validation"):
            runtime.execute(job_id, transport=transport(job_id), clock=lambda: 1790000000.0)
        self.assertEqual(self.store.job_record(job_id)["status"], "UNCERTAIN")
        return job_id, runtime

    def test_rejected_authority_is_private_and_replayable_without_provider_call(self):
        transports = []

        def make_transport(job_id):
            context = self.coordinator.restore_context(job_id, ("QUEUED",))
            result = activation_tests.FakeTransport(context, authority="BUY_NOW")
            transports.append(result)
            return result

        job_id, runtime = self._execute_invalid(make_transport)
        failure = self.store.rejected_response_record(job_id)
        self.assertEqual(failure["failure_stage"], "STRUCTURAL_VALIDATION")
        self.assertEqual(failure["failure_code"], "assessment cannot claim trading authority")
        self.assertEqual(failure["provider_response"]["completion_status"], "COMPLETE")
        self.assertEqual(len(failure["response_hash"]), 64)
        self.assertEqual(self.store.completed_result(job_id), None)
        receipt = json.loads(self.store.db.execute(
            "SELECT receipt FROM charges WHERE job_id=?", (job_id,),
        ).fetchone()[0])
        self.assertEqual(receipt["runtime_failure_stage"], "STRUCTURAL_VALIDATION")
        self.assertEqual(receipt["validation_failure_code"], failure["failure_code"])
        restored = self.coordinator.restore_context(job_id, ("UNCERTAIN",))
        with self.assertRaisesRegex(ContractError, "cannot claim trading authority"):
            validate_assessment(restored, ProviderResponse(**failure["provider_response"]))
        with self.assertRaisesRegex(ContractError, "not claimable"):
            runtime.execute(job_id, transport=transports[0], clock=lambda: 1790000001.0)
        self.assertEqual(len(transports[0].calls), 1)

    def test_raw_digit_narrative_is_quarantined_not_silently_repaired(self):
        def make_transport(job_id):
            context = self.coordinator.restore_context(job_id, ("QUEUED",))
            transport = activation_tests.FakeTransport(context)
            original = transport.create

            def invalid(request, *, timeout_seconds):
                envelope = original(request, timeout_seconds=timeout_seconds)
                payload = json.loads(envelope["content"][0]["text"])
                payload["sections"][0]["summary"] = "Unbound figure 20."
                envelope["content"][0]["text"] = json.dumps(payload)
                return envelope

            transport.create = invalid
            return transport

        job_id, _ = self._execute_invalid(make_transport)
        failure = self.store.rejected_response_record(job_id)
        self.assertEqual(failure["failure_stage"], "STRUCTURAL_VALIDATION")
        self.assertIn("bound slots", failure["failure_code"])
        self.assertIn("Unbound figure 20", failure["provider_response"]["json_text"])

    def test_invalid_envelope_records_stage_without_inventing_response(self):
        def make_transport(job_id):
            context = self.coordinator.restore_context(job_id, ("QUEUED",))
            transport = activation_tests.FakeTransport(context)
            transport.create = lambda request, *, timeout_seconds: {"id": "incomplete"}
            return transport

        job_id, _ = self._execute_invalid(make_transport)
        failure = self.store.rejected_response_record(job_id)
        self.assertEqual(failure["failure_stage"], "PROVIDER_RESPONSE")
        self.assertIsNone(failure["provider_response"])

    def test_valid_response_has_no_rejection_record(self):
        job_id = self._prepared()
        runtime = self._runtime()
        runtime.activate((job_id,), operator_approval_id="approved", now=1001.0)
        context = self.coordinator.restore_context(job_id, ("QUEUED",))
        result = runtime.execute(job_id, transport=activation_tests.FakeTransport(context),
                                 clock=lambda: 1790000000.0)
        self.assertFalse(result["semantic_status"] == "REJECTED")
        self.assertIsNone(self.store.rejected_response_record(job_id))


if __name__ == "__main__":
    unittest.main()
