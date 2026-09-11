"""Long-response and uncertain-outcome regressions; never waits or calls a provider."""
import json
import unittest
from unittest.mock import Mock, patch

from worker3.adapters.anthropic_http import AnthropicHTTP
from worker3.adapters.jobs import JobStore
from worker3.domain import ContractError
from tests import test_worker3_activation as fixtures


class TimeoutRecoveryTests(unittest.TestCase):
    setUp = fixtures.Worker3ActivationTests.setUp
    tearDown = fixtures.Worker3ActivationTests.tearDown
    _release = fixtures.Worker3ActivationTests._release
    _runtime = fixtures.Worker3ActivationTests._runtime

    def prepare_long_job(self):
        value = json.loads(self.release_path.read_text())
        value.update(timeout_seconds=300, max_calls_per_process=1)
        self.release_path.write_text(json.dumps(value))
        prepared = self.coordinator.prepare_run(fixtures.RUN_ID, provider="ANTHROPIC",
            model="fixture-model", tickers=("AAA",), now=1000, timeout_seconds=300)
        job_id = prepared.entries[0].job_id
        runtime = self._runtime()
        runtime.activate((job_id,), operator_approval_id="offline", now=1001)
        return job_id, runtime

    def test_response_after_old_lease_limit_completes_and_replays(self):
        job_id, runtime = self.prepare_long_job()
        context = self.coordinator.restore_context(job_id, ("QUEUED",))
        transport = fixtures.FakeTransport(context)
        original = transport.create
        clock = [1790000000.0]

        def delayed(request, *, timeout_seconds):
            self.assertEqual(timeout_seconds, 300)
            clock[0] += 250  # A virtual late response; no sleep.
            return original(request, timeout_seconds=timeout_seconds)

        transport.create = delayed
        result = runtime.execute(job_id, transport=transport, clock=lambda: clock[0])
        self.assertTrue(result["provider_called"])
        self.assertEqual(self.store.job_record(job_id)["status"], "REVIEW_REQUIRED")
        self.assertFalse(runtime.execute(job_id, transport=transport,
                                        clock=lambda: clock[0])["provider_called"])
        self.assertEqual(len(transport.calls), 1)

    def test_timeout_diagnostics_survive_reopen_without_releasing_reservation(self):
        job_id, runtime = self.prepare_long_job()
        transport = AnthropicHTTP(enabled=True, max_input_bytes=500000)
        connection = Mock()
        connection.getresponse.side_effect = TimeoutError("private exception detail")
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "fixture-only",
                                      "ANTHROPIC_WORKSPACE_ID": "wrkspc_fixture"}), \
             patch("worker3.adapters.anthropic_http.http.client.HTTPSConnection", return_value=connection) as factory:
            with self.assertRaisesRegex(ContractError, "controlled validation"):
                runtime.execute(job_id, transport=transport, clock=lambda: 1790000000)
            factory.assert_called_once_with("api.anthropic.com", timeout=300)
            with self.assertRaises(ContractError):
                runtime.execute(job_id, transport=transport, clock=lambda: 1790000001)
        connection.request.assert_called_once()
        self.store.close()
        self.store = JobStore(self.db, budget_microusd=1_000_000)
        self.assertEqual(self.store.job_record(job_id)["status"], "UNCERTAIN")
        self.assertEqual(self.store.accounting()["unknown_cost_reservation_microusd"], 100000)
        receipt = json.loads(self.store.db.execute("SELECT receipt FROM charges").fetchone()[0])
        self.assertEqual(receipt["error_type"], "TIMEOUT")
        self.assertEqual(receipt["failure_stage"], "AWAITING_HEADERS")
        self.assertEqual(receipt["runtime_failure_stage"], "PROVIDER")
        self.assertNotIn("private exception detail", json.dumps(receipt))
        self.assertNotIn("fixture-only", json.dumps(receipt))

    def test_timeout_ceiling_still_fails_before_network(self):
        value = json.loads(self.release_path.read_text())
        value["timeout_seconds"] = 301
        self.release_path.write_text(json.dumps(value))
        with self.assertRaisesRegex(ContractError, "bounded"):
            self._runtime()
        with patch("worker3.adapters.anthropic_http.http.client.HTTPSConnection") as factory:
            with self.assertRaisesRegex(ContractError, "300 seconds"):
                AnthropicHTTP(enabled=True).create({}, timeout_seconds=301)
            factory.assert_not_called()


if __name__ == "__main__":
    unittest.main()
