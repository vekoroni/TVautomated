from __future__ import annotations

from dataclasses import asdict
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from worker3.adapters.jobs import JobStore
from worker3.adapters.lab_reports import AnalystReports
from worker3.domain import ContractError, Section, canonical
from worker3.integration import AvshunterSourceBridge, Worker3Coordinator
from worker3.integration.activation import ControlledProviderRuntime
from worker3.integration.lab_mount import install_worker3_lab_projection
from worker3.v2.assessment import SCHEMA
from tests.test_worker3_avshunter_source_bridge import RUN_ID, SourceFixture


REPO = Path(__file__).resolve().parents[1]
INTEGRATION_POLICY = REPO / "contracts" / "worker3_integration_v1.json"
DISABLED_RELEASE = REPO / "contracts" / "worker3_provider_release_v1.json"


class FakeTransport:
    def __init__(self, context, *, authority="ADVISORY_ONLY"):
        self.context = context
        self.authority = authority
        self.calls = []
        self.receipts = []

    def create(self, request, *, timeout_seconds):
        self.calls.append((request, timeout_seconds))
        self.receipts.append({
            "request_hash": "f" * 64,
            "http_status": 200,
            "input_tokens": 100,
            "output_tokens": 50,
            "elapsed_ms": 25,
            "credential_source": "test_fixture",
            "credential_fingerprint": "12345678",
        })
        job = self.context.job
        payload = {
            "schema_version": SCHEMA,
            "job_key": job.job_key,
            "identity": asdict(job.bundle.identity),
            "evidence_hash": job.bundle.evidence_hash,
            "context_hash": self.context.context_hash,
            "authority": self.authority,
            "claims": [],
            "sections": [{
                "section": section.value,
                "summary": "Evidence review pending.",
                "claim_ids": [],
            } for section in Section],
            "numeric_facts": [],
        }
        return {
            "id": "request-fixture",
            "model": job.model,
            "stop_reason": "end_turn",
            "content": [{"type": "text", "text": canonical(payload)}],
        }


class FakeApp:
    def __init__(self):
        self.routes = []

    def route(self, path, methods):
        def decorator(function):
            self.routes.append((path, tuple(methods), function))
            return function
        return decorator


class Worker3ActivationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.fixture = SourceFixture(self.root / "source")
        self.db = self.root / "jobs.sqlite"
        self.reports_path = self.root / "reports.sqlite"
        self.store = JobStore(self.db, budget_microusd=1_000_000)
        self.reports = AnalystReports(self.reports_path)
        self.coordinator = Worker3Coordinator(
            AvshunterSourceBridge(self.fixture.root), self.store, INTEGRATION_POLICY
        )
        self.release_path = self._release(enabled=True)

    def tearDown(self):
        self.reports.close()
        self.store.close()
        self.temp.cleanup()

    def _release(self, *, enabled, models=None, max_jobs=10,
                 max_calls=10, max_total=1_000_000):
        value = json.loads(DISABLED_RELEASE.read_text(encoding="utf-8"))
        value["enabled"] = enabled
        value["status"] = "CONTROLLED_ACTIVE" if enabled else "INSTALLED_DISABLED"
        value["allowed_models"] = list(models or (["fixture-model"] if enabled else []))
        value["max_jobs_per_activation"] = max_jobs
        value["max_calls_per_process"] = max_calls
        value["max_total_microusd"] = max_total
        value["input_microusd_per_million_tokens"] = 3_000_000 if enabled else 0
        value["output_microusd_per_million_tokens"] = 15_000_000 if enabled else 0
        path = self.root / ("active_release.json" if enabled else "disabled_release.json")
        path.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")
        return path

    def _prepared(self, *, ticker="AAA", model="fixture-model"):
        result = self.coordinator.prepare_run(
            RUN_ID, provider="ANTHROPIC", model=model, now=1000.0,
            tickers=(ticker,), call_ceiling_microusd=100_000,
        )
        return result.entries[0].job_id

    def _runtime(self, release=None):
        return ControlledProviderRuntime(
            self.coordinator, self.store, self.reports, release or self.release_path
        )

    def test_disabled_release_cannot_activate(self):
        runtime = self._runtime(self._release(enabled=False))
        with self.assertRaisesRegex(ContractError, "disabled"):
            runtime.activate((self._prepared(),), operator_approval_id="approval", now=1001.0)

    def test_activation_is_audited_and_idempotent(self):
        job_id = self._prepared()
        runtime = self._runtime()
        first = runtime.activate((job_id,), operator_approval_id="approval-1", now=1001.0)
        second = runtime.activate((job_id,), operator_approval_id="approval-1", now=1002.0)
        self.assertEqual(first, second)
        self.assertEqual(self.store.job_record(job_id)["status"], "QUEUED")
        record = self.store.activation_record(job_id)
        self.assertEqual(record["operator_approval_id"], "approval-1")

    def test_missing_approval_or_unapproved_model_blocks_activation(self):
        job_id = self._prepared()
        with self.assertRaises(ContractError):
            self._runtime().activate((job_id,), operator_approval_id="", now=1001.0)
        other = self._prepared(ticker="BBB", model="other-model")
        with self.assertRaisesRegex(ContractError, "not release-approved"):
            self._runtime().activate((other,), operator_approval_id="approval", now=1001.0)

    def test_activation_job_count_is_bounded(self):
        release = self._release(enabled=True, max_jobs=1)
        prepared = self.coordinator.prepare_run(
            RUN_ID, provider="ANTHROPIC", model="fixture-model", now=1000.0,
            tickers=("AAA", "BBB"), call_ceiling_microusd=100_000,
        )
        ids = tuple(entry.job_id for entry in prepared.entries)
        with self.assertRaisesRegex(ContractError, "job count"):
            self._runtime(release).activate(ids, operator_approval_id="approval", now=1001.0)

    def test_separate_activation_batches_share_one_release_ceiling(self):
        release = self._release(enabled=True, max_total=100_000)
        prepared = self.coordinator.prepare_run(
            RUN_ID, provider="ANTHROPIC", model="fixture-model", now=1000.0,
            tickers=("AAA", "BBB"), call_ceiling_microusd=100_000,
        )
        first, second = (entry.job_id for entry in prepared.entries)
        runtime = self._runtime(release)
        runtime.activate((first,), operator_approval_id="approval", now=1001.0)
        with self.assertRaisesRegex(ContractError, "cumulative activation"):
            runtime.activate((second,), operator_approval_id="approval", now=1002.0)
        self.assertEqual(self.store.job_record(second)["status"], "PREPARED")

    def test_validated_response_is_durable_semantic_reviewed_and_projected(self):
        job_id = self._prepared()
        runtime = self._runtime()
        runtime.activate((job_id,), operator_approval_id="approval", now=1001.0)
        context = self.coordinator.restore_context(job_id, ("QUEUED",))
        transport = FakeTransport(context)
        result = runtime.execute(job_id, transport=transport, clock=lambda: 1790000000.0)
        self.assertTrue(result["provider_called"])
        self.assertEqual(result["semantic_status"], "BLOCKED")
        self.assertEqual(result["cost_microusd"], 1050)
        self.assertEqual(self.store.job_record(job_id)["status"], "REVIEW_REQUIRED")
        view = self.reports.get(RUN_ID, "AAA", result["assessment_id"])
        self.assertEqual(view["status"], "BLOCKED_DRAFT")
        self.assertFalse(view["execution_permission"])
        self.assertEqual(view["authority"], "ADVISORY_ONLY")
        self.assertEqual(self.store.accounting()["reported_cost_microusd"], 1050)
        replay = runtime.execute(job_id, transport=transport, clock=lambda: 1790000001.0)
        self.assertFalse(replay["provider_called"])
        self.assertEqual(len(transport.calls), 1)

    def test_invalid_authority_response_is_held_uncertain(self):
        job_id = self._prepared()
        runtime = self._runtime()
        runtime.activate((job_id,), operator_approval_id="approval", now=1001.0)
        context = self.coordinator.restore_context(job_id, ("QUEUED",))
        with self.assertRaisesRegex(ContractError, "controlled validation"):
            runtime.execute(
                job_id, transport=FakeTransport(context, authority="BUY_NOW"),
                clock=lambda: 1790000000.0,
            )
        self.assertEqual(self.store.job_record(job_id)["status"], "UNCERTAIN")

    def test_failed_post_dispatch_attempt_consumes_process_call_cap(self):
        release = self._release(enabled=True, max_calls=1)
        prepared = self.coordinator.prepare_run(
            RUN_ID, provider="ANTHROPIC", model="fixture-model", now=1000.0,
            tickers=("AAA", "BBB"), call_ceiling_microusd=100_000,
        )
        first, second = (entry.job_id for entry in prepared.entries)
        runtime = self._runtime(release)
        runtime.activate((first, second), operator_approval_id="approval", now=1001.0)
        first_context = self.coordinator.restore_context(first, ("QUEUED",))
        with self.assertRaises(ContractError):
            runtime.execute(
                first, transport=FakeTransport(first_context, authority="BUY_NOW"),
                clock=lambda: 1790000000.0,
            )
        second_context = self.coordinator.restore_context(second, ("QUEUED",))
        with self.assertRaisesRegex(ContractError, "call limit exhausted"):
            runtime.execute(
                second, transport=FakeTransport(second_context),
                clock=lambda: 1790000001.0,
            )
        self.assertEqual(self.store.job_record(second)["status"], "QUEUED")

    def test_release_rejects_ambiguous_lab_projection_flag(self):
        value = json.loads(DISABLED_RELEASE.read_text(encoding="utf-8"))
        value["lab_projection_enabled"] = "false"
        path = self.root / "invalid_release.json"
        path.write_text(json.dumps(value), encoding="utf-8")
        with self.assertRaisesRegex(ContractError, "projection flag"):
            self._runtime(path)

    def test_projection_failure_reuses_durable_response_without_second_call(self):
        job_id = self._prepared()
        runtime = self._runtime()
        runtime.activate((job_id,), operator_approval_id="approval", now=1001.0)
        context = self.coordinator.restore_context(job_id, ("QUEUED",))
        transport = FakeTransport(context)
        with patch.object(self.reports, "save_draft", side_effect=RuntimeError("disk")):
            with self.assertRaises(RuntimeError):
                runtime.execute(job_id, transport=transport, clock=lambda: 1790000000.0)
        replay = runtime.execute(job_id, transport=transport, clock=lambda: 1790000001.0)
        self.assertFalse(replay["provider_called"])
        self.assertEqual(len(transport.calls), 1)

    def test_release_change_after_runtime_initialization_fails_closed(self):
        job_id = self._prepared()
        runtime = self._runtime()
        value = json.loads(self.release_path.read_text(encoding="utf-8"))
        value["max_jobs_per_activation"] = 9
        self.release_path.write_text(json.dumps(value), encoding="utf-8")
        with self.assertRaisesRegex(ContractError, "changed after"):
            runtime.activate((job_id,), operator_approval_id="approval", now=1001.0)

    def test_lab_mount_is_absent_when_disabled_and_advisory_when_enabled(self):
        app = FakeApp()
        self.assertIsNone(install_worker3_lab_projection(
            app, self.fixture.root, self._release(enabled=False)
        ))
        self.assertEqual(app.routes, [])
        reports = install_worker3_lab_projection(
            app, self.fixture.root, self.release_path
        )
        try:
            self.assertEqual(len(app.routes), 2)
        finally:
            reports.close()

    def test_production_lab_startup_honours_disabled_release(self):
        lab_path = REPO / "intelligence-lab" / "intelligence_lab.py"
        spec = importlib.util.spec_from_file_location(
            "worker3_disabled_release_lab_test", lab_path
        )
        module = importlib.util.module_from_spec(spec)
        self.assertIsNotNone(spec.loader)
        from worker3.integration.activation import load_provider_release
        disabled = load_provider_release(self._release(enabled=False))
        with patch("worker3.integration.lab_mount.load_provider_release", return_value=disabled), patch("worker3.integration.browser_launch.install_worker3_browser", return_value=None):
            spec.loader.exec_module(module)
        self.assertIsNone(module.WORKER3_ANALYST_REPORTS)
        self.assertFalse(any(
            "worker3/report" in str(rule) for rule in module.app.url_map.iter_rules()
        ))


if __name__ == "__main__":
    unittest.main()
