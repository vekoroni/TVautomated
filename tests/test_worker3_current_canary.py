from pathlib import Path
import json
import shutil
import tempfile
import unittest
from unittest.mock import patch

from worker3.domain import ContractError
from worker3.integration.avshunter_source import AvshunterSourceBridge
from worker3.integration.current_canary import (latest_completed, select_candidate, offline_audit,
    count_frozen_request, counted_cost_ceiling, MODEL)
from worker3.integration.runner import main as prepare_main
from tests.test_worker3_avshunter_source_bridge import SourceFixture, RUN_ID
from tests import test_worker3_activation as activation_tests
from tests.test_worker3_activation import FakeTransport


class CurrentCanaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.fixture = SourceFixture(self.root)
        contracts = self.root / "contracts"
        contracts.mkdir()
        for name in ("worker3_integration_v1.json", "worker3_provider_release_v1.json"):
            shutil.copyfile(Path(__file__).resolve().parents[1] / "contracts" / name, contracts / name)

    def test_latest_ignores_alias_and_records_incomplete(self):
        newer = self.root / "data/output/runs/20260907_120000"
        newer.mkdir()
        (newer / "run_meta.json").write_text(json.dumps({"run_status": "RUNNING"}))
        run, skipped = latest_completed(AvshunterSourceBridge(self.root))
        self.assertEqual(run, RUN_ID)
        self.assertEqual(len(skipped), 1)

    def test_newest_completed_governance_failure_does_not_fall_back(self):
        newer = self.root / "data/output/runs/20260907_120000"
        newer.mkdir()
        (newer / "run_meta.json").write_text(json.dumps({"run_status": "COMPLETED"}))
        with self.assertRaises((ContractError, FileNotFoundError)):
            latest_completed(AvshunterSourceBridge(self.root))

    def test_exact_selection_never_falls_back_from_data_exception(self):
        source = AvshunterSourceBridge(self.root).prepare_run(RUN_ID)
        self.assertEqual(select_candidate(source, direction="PUT").ticker, "BBB")
        with self.assertRaisesRegex(ContractError, "no ticker fallback"):
            select_candidate(source, ticker="MISSING")

    def test_offline_harness_real_process_replay_and_exceptions(self):
        self.fixture.rows.append({**self.fixture.rows[0], "ticker": "BROKEN", "thesis_id": ""})
        self.fixture.write_run()
        audit = offline_audit(self.root)
        self.assertEqual(audit["summary"]["jobs_prepared"], 2)
        self.assertEqual(audit["summary"]["data_exceptions"], 1)
        self.assertEqual(audit["directions"], {"CALL": 1, "PUT": 1})
        self.assertEqual(len(audit["cases"]), 5)
        for case in audit["cases"]:
            self.assertEqual(case["provider_attempts"], 1)
            if case["mode"] in ("envelope", "authority"):
                self.assertEqual(case["state"], "UNCERTAIN")
            else:
                self.assertTrue(case["accepted"])
                self.assertFalse(case["restart_replay"]["provider_called"])
                self.assertEqual(case["routes"]["wrong_identity_404s"], 6)

    def test_operator_cli_passes_only_exact_ticker(self):
        with patch("worker3.integration.runner.JobStore") as store, \
             patch("worker3.integration.runner.Worker3Coordinator") as coordinator, \
             patch("worker3.integration.runner.AvshunterSourceBridge"), \
             patch("pathlib.Path.mkdir"), patch("builtins.print"):
            coordinator.return_value.prepare_run.return_value.summary.return_value = {"jobs_prepared": 1}
            self.assertEqual(prepare_main(["--run-id", RUN_ID, "--ticker", "AAA", "--provider", "ANTHROPIC",
                             "--model", "fixture-model", "--budget-microusd", "100000",
                             "--call-ceiling-microusd", "100000"]), 0)
            self.assertEqual(coordinator.return_value.prepare_run.call_args.kwargs["tickers"], ("AAA",))

    def test_count_preflight_exact_hash_budget_and_no_generation(self):
        from unittest.mock import Mock
        request = {"model": MODEL, "max_tokens": 8192, "system": "test", "messages": []}
        connection = Mock()
        connection.getresponse.return_value.status = 200
        connection.getresponse.return_value.read.return_value = b'{"input_tokens": 80000}'
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "fixture-only", "ANTHROPIC_WORKSPACE_ID": ""}):
            receipt = count_frozen_request(request, connection_factory=lambda *a, **k: connection)
        self.assertEqual(connection.request.call_count, 1)
        self.assertEqual(connection.request.call_args.args[1], "/v1/messages/count_tokens")
        self.assertLess(counted_cost_ceiling(request, receipt), 500000)
        with self.assertRaisesRegex(ContractError, "changed"):
            counted_cost_ceiling({**request, "system": "changed"}, receipt)
        with self.assertRaisesRegex(ContractError, "cost exceeds"):
            counted_cost_ceiling(request, {**receipt, "input_tokens": 200000})

    def test_count_preflight_http_failure_does_not_retry(self):
        from unittest.mock import Mock
        connection = Mock()
        connection.getresponse.return_value.status = 500
        request = {"model": MODEL, "max_tokens": 8192, "system": "test", "messages": []}
        receipt = {}
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "fixture-only", "ANTHROPIC_WORKSPACE_ID": ""}):
            with self.assertRaisesRegex(ContractError, "no retry"):
                count_frozen_request(request, connection_factory=lambda *a, **k: connection, receipt=receipt)
        self.assertEqual(connection.request.call_count, 1)
        self.assertEqual(receipt["http_status"], 500)
        connection.close.assert_called_once()


class ControlledBoundaryRegressions(unittest.TestCase):
    setUp = activation_tests.Worker3ActivationTests.setUp
    tearDown = activation_tests.Worker3ActivationTests.tearDown
    _release = activation_tests.Worker3ActivationTests._release
    _prepared = activation_tests.Worker3ActivationTests._prepared
    _runtime = activation_tests.Worker3ActivationTests._runtime

    def test_malformed_envelope_consumes_last_call(self):
        job_id = self._prepared()
        runtime = self._runtime(self._release(enabled=True, max_calls=1))
        runtime.activate((job_id,), operator_approval_id="approval", now=1001)
        transport = FakeTransport(self.coordinator.restore_context(job_id, ("QUEUED",)))
        with patch.object(transport, "create", return_value={"id": "malformed"}) as create:
            with self.assertRaisesRegex(ContractError, "controlled validation"):
                runtime.execute(job_id, transport=transport, clock=lambda: 1790000000)
            self.assertEqual(create.call_count, 1)
        self.assertEqual(runtime.calls, 1)
        self.assertEqual(self.store.job_record(job_id)["status"], "UNCERTAIN")

    def test_one_call_projection_failure_replays_at_exhausted_cap(self):
        job_id = self._prepared()
        runtime = self._runtime(self._release(enabled=True, max_calls=1))
        runtime.activate((job_id,), operator_approval_id="approval", now=1001)
        transport = FakeTransport(self.coordinator.restore_context(job_id, ("QUEUED",)))
        with patch.object(self.reports, "save_draft", side_effect=RuntimeError("disk")):
            with self.assertRaises(RuntimeError):
                runtime.execute(job_id, transport=transport, clock=lambda: 1790000000)
        replay = runtime.execute(job_id, transport=transport, clock=lambda: 1790000001)
        self.assertFalse(replay["provider_called"])
        self.assertEqual(len(transport.calls), 1)


if __name__ == "__main__":
    unittest.main()
