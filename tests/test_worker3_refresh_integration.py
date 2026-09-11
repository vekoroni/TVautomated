from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
import tempfile
import unittest

from worker3.adapters.jobs import JobStore
from worker3.adapters.lab_reports import AnalystReports
from worker3.domain import ContractError
from worker3.integration import AvshunterSourceBridge, Worker3Coordinator
from worker3.integration.activation import ControlledProviderRuntime
from tests.test_worker3_activation import FakeTransport, INTEGRATION_POLICY
from tests.test_worker3_avshunter_source_bridge import RUN_ID, SourceFixture


REPO = Path(__file__).resolve().parents[1]
RELEASE = REPO / "contracts" / "worker3_provider_release_v1.json"


class Worker3RefreshIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.fixture = SourceFixture(self.root / "source")
        self.db_path = self.root / "jobs.sqlite"
        self.reports_path = self.root / "reports.sqlite"
        self.store = JobStore(self.db_path, budget_microusd=5_000_000)
        self.reports = AnalystReports(self.reports_path)
        self.addCleanup(self._close)
        self.coordinator = Worker3Coordinator(
            AvshunterSourceBridge(self.fixture.root), self.store, INTEGRATION_POLICY
        )
        release = json.loads(RELEASE.read_text(encoding="utf-8"))
        release.update(
            enabled=True,
            status="CONTROLLED_ACTIVE",
            allowed_models=["fixture-model"],
            max_jobs_per_activation=10,
            max_calls_per_process=10,
            max_total_microusd=5_000_000,
            max_call_microusd=1_000_000,
            input_microusd_per_million_tokens=3_000_000,
            output_microusd_per_million_tokens=15_000_000,
        )
        self.release_path = self.root / "release.json"
        self.release_path.write_text(json.dumps(release), encoding="utf-8")

    def _close(self):
        if self.reports is not None:
            self.reports.close()
            self.reports = None
        if self.store is not None:
            self.store.close()
            self.store = None

    def _execute_initial(self):
        prepared = self.coordinator.prepare_run(
            RUN_ID, provider="ANTHROPIC", model="fixture-model", now=1000.0,
            tickers=("AAA",), call_ceiling_microusd=100_000,
        )
        job_id = prepared.entries[0].job_id
        runtime = ControlledProviderRuntime(
            self.coordinator, self.store, self.reports, self.release_path
        )
        runtime.activate((job_id,), operator_approval_id="initial", now=1001.0)
        context = self.coordinator.restore_context(job_id, ("QUEUED",))
        cutoff = datetime.fromisoformat(
            context.job.bundle.evidence_cutoff_utc.replace("Z", "+00:00")
        ).timestamp()
        result = runtime.execute(
            job_id, transport=FakeTransport(context), clock=lambda: cutoff
        )
        return job_id, result["assessment_id"]

    def _advance_current_evidence(self):
        self.fixture.rows[0]["signal_price"] = 10.75
        self.fixture.write_run()
        path = self.fixture.run / "run_meta.json"
        meta = json.loads(path.read_text(encoding="utf-8"))
        meta["dynamic_plan"]["evidence_cutoff_utc"] = "2026-09-07T13:45:00Z"
        path.write_text(
            json.dumps(meta, sort_keys=True, separators=(",", ":")),
            encoding="utf-8",
        )

    def test_projected_assessment_is_indexed_and_reconstructable(self):
        job_id, assessment_id = self._execute_initial()
        index = self.store.assessment_record(assessment_id)
        self.assertEqual(index["job_id"], job_id)
        prior = self.coordinator.restore_previous_assessment(assessment_id)
        self.assertEqual(prior.assessment_id, assessment_id)
        self.assertEqual(prior.context.job.bundle.identity.ticker, "AAA")

    def test_pre_index_assessment_is_backfilled_without_provider_call(self):
        job_id, assessment_id = self._execute_initial()
        self.store.db.execute(
            "DELETE FROM assessment_index WHERE assessment_id=?", (assessment_id,)
        )
        self.assertIsNone(self.store.assessment_record(assessment_id))
        prior = self.coordinator.restore_previous_assessment(assessment_id)
        self.assertEqual(prior.assessment_id, assessment_id)
        self.assertEqual(self.store.assessment_record(assessment_id)["job_id"], job_id)

    def test_refresh_is_restart_safe_and_idempotent(self):
        _, assessment_id = self._execute_initial()
        self._advance_current_evidence()
        prepared = self.coordinator.prepare_run(
            RUN_ID, provider="ANTHROPIC", model="fixture-model", now=2000.0,
            tickers=("AAA",), previous_assessment_ids={"AAA": assessment_id},
            call_ceiling_microusd=100_000,
        )
        refresh_id = prepared.entries[0].job_id
        context = self.coordinator.restore_context(refresh_id)
        self.assertEqual(context.job.task_type, "REFRESH_ASSESSMENT")
        self.assertEqual(context.previous.assessment_id, assessment_id)
        self.assertNotEqual(
            context.previous.context.job.bundle.evidence_hash,
            context.job.bundle.evidence_hash,
        )

        self.store.close()
        self.store = JobStore(self.db_path, budget_microusd=5_000_000)
        self.coordinator = Worker3Coordinator(
            AvshunterSourceBridge(self.fixture.root), self.store, INTEGRATION_POLICY
        )
        restored = self.coordinator.restore_context(refresh_id)
        self.assertEqual(restored.context_hash, context.context_hash)
        self.assertEqual(restored.previous.assessment_id, assessment_id)

        runtime = ControlledProviderRuntime(
            self.coordinator, self.store, self.reports, self.release_path
        )
        runtime.activate((refresh_id,), operator_approval_id="refresh", now=2001.0)
        transport = FakeTransport(restored)
        result = runtime.execute(
            refresh_id, transport=transport,
            clock=lambda: datetime.fromisoformat(
                "2026-09-07T13:45:00+00:00"
            ).timestamp(),
        )
        replay = runtime.execute(
            refresh_id, transport=transport,
            clock=lambda: datetime.fromisoformat(
                "2026-09-07T13:46:00+00:00"
            ).timestamp(),
        )
        self.assertTrue(result["provider_called"])
        self.assertFalse(replay["provider_called"])
        self.assertEqual(result["assessment_id"], replay["assessment_id"])
        self.assertEqual(len(transport.calls), 1)
        view = self.reports.get(RUN_ID, "AAA", result["assessment_id"])
        self.assertEqual(view["prior_assessment_id"], assessment_id)
        self.assertIsNotNone(view["system_evidence"]["comparison"])

    def test_cross_ticker_prior_is_isolated_as_data_exception(self):
        _, assessment_id = self._execute_initial()
        prepared = self.coordinator.prepare_run(
            RUN_ID, provider="ANTHROPIC", model="fixture-model", now=2000.0,
            tickers=("BBB",), previous_assessment_ids={"BBB": assessment_id},
            call_ceiling_microusd=100_000,
        )
        self.assertEqual(prepared.entries[0].status, "DATA_EXCEPTION")
        self.assertIn("another ticker", prepared.entries[0].reason)

    def test_refresh_requires_exact_explicit_prior_map(self):
        with self.assertRaisesRegex(ContractError, "worklist"):
            self.coordinator.prepare_run(
                RUN_ID, provider="ANTHROPIC", model="fixture-model", now=2000.0,
                tickers=("AAA", "BBB"),
                previous_assessment_ids={"AAA": "a" * 64},
            )


if __name__ == "__main__":
    unittest.main()
