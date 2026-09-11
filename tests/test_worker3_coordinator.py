from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from worker3.adapters.jobs import JobStore
from worker3.domain import ContractError
from worker3.integration import AvshunterSourceBridge, Worker3Coordinator
from worker3.v2.assessment import PROMPT
from tests.test_worker3_avshunter_source_bridge import RUN_ID, SourceFixture


REPO = Path(__file__).resolve().parents[1]
POLICY = REPO / "contracts" / "worker3_integration_v1.json"


class Worker3CoordinatorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.fixture = SourceFixture(self.root / "source")
        self.db_path = self.root / "jobs.sqlite"
        self.store = JobStore(self.db_path, budget_microusd=1_000_000)
        self.coordinator = Worker3Coordinator(
            AvshunterSourceBridge(self.fixture.root), self.store, POLICY
        )

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def prepare(self, **kwargs):
        return self.coordinator.prepare_run(
            RUN_ID,
            provider=kwargs.pop("provider", "ANTHROPIC"),
            model=kwargs.pop("model", "fixture-model"),
            now=kwargs.pop("now", 1000.0),
            call_ceiling_microusd=kwargs.pop("call_ceiling_microusd", 100_000),
            **kwargs,
        )

    def test_prepares_call_and_put_as_durable_unclaimable_jobs(self):
        result = self.prepare()
        self.assertEqual([entry.status for entry in result.entries], ["JOB_PREPARED", "JOB_PREPARED"])
        self.assertEqual(result.summary()["jobs_prepared"], 2)
        self.assertFalse(result.summary()["provider_dispatch_enabled"])
        self.assertEqual(self.store.claim(now=1001.0), None)
        self.assertEqual({row["status"] for row in self.store.progress(RUN_ID)}, {"PREPARED"})

    def test_source_exception_is_durable_and_creates_no_job(self):
        self.fixture.rows[1]["selected_quote_dataset_id"] = ""
        self.fixture.write_run()
        result = self.prepare()
        self.assertEqual([entry.status for entry in result.entries], ["JOB_PREPARED", "DATA_EXCEPTION"])
        self.assertIsNone(result.entries[1].job_id)
        self.assertEqual(len(self.store.progress(RUN_ID)), 1)
        exception = next(row for row in self.store.intake_progress(RUN_ID) if row["ticker"] == "BBB")
        self.assertEqual(exception["reason_code"], "SOURCE_DATA_EXCEPTION")

    def test_repeat_is_idempotent_for_jobs_and_intakes(self):
        first = self.prepare(now=1000.0)
        second = self.prepare(now=2000.0)
        self.assertEqual([entry.job_id for entry in first.entries], [entry.job_id for entry in second.entries])
        self.assertEqual([entry.intake_id for entry in first.entries], [entry.intake_id for entry in second.entries])
        self.assertEqual(len(self.store.progress(RUN_ID)), 2)
        self.assertEqual(len(self.store.intake_progress(RUN_ID)), 2)

    def test_restart_restores_exact_job_and_evidence_identity(self):
        result = self.prepare()
        job_id = result.entries[0].job_id
        expected = self.coordinator.restore_context(job_id)
        self.store.close()
        self.store = JobStore(self.db_path, budget_microusd=1_000_000)
        self.coordinator = Worker3Coordinator(
            AvshunterSourceBridge(self.fixture.root), self.store, POLICY
        )
        restored = self.coordinator.restore_context(job_id)
        self.assertEqual(restored.context_hash, expected.context_hash)
        self.assertEqual(restored.job.job_key, expected.job.job_key)
        self.assertEqual(restored.job.bundle.evidence_hash, expected.job.bundle.evidence_hash)

    def test_provider_model_prompt_and_authority_are_persisted(self):
        result = self.prepare(provider="OPENAI", model="fixture-openai")
        record = self.store.job_record(result.entries[0].job_id)
        payload = record["payload"]
        self.assertEqual(payload["authority"], "ADVISORY_ONLY")
        self.assertFalse(payload["capital_permission"])
        self.assertEqual(payload["dispatch_state"], "DISABLED_BY_POLICY")
        self.assertEqual(payload["worker_job"]["provider"], "OPENAI")
        self.assertEqual(payload["worker_job"]["model"], "fixture-openai")
        self.assertEqual(payload["worker_job"]["prompt_version"], PROMPT)

    def test_changed_model_produces_distinct_job_identity(self):
        first = self.prepare(model="model-a")
        second = self.prepare(model="model-b", now=1001.0)
        self.assertNotEqual(first.entries[0].job_id, second.entries[0].job_id)

    def test_tampered_persisted_payload_fails_closed(self):
        result = self.prepare()
        job_id = result.entries[0].job_id
        record = self.store.job_record(job_id)
        payload = record["payload"]
        payload["authority"] = "BUY_NOW"
        self.store.db.execute(
            "UPDATE jobs SET payload=? WHERE id=?",
            (json.dumps(payload, sort_keys=True, separators=(",", ":")), job_id),
        )
        with self.assertRaisesRegex(ContractError, "PREPARE_ONLY policy"):
            self.coordinator.restore_context(job_id)

    def test_policy_cannot_enable_provider_dispatch(self):
        policy = json.loads(POLICY.read_text(encoding="utf-8"))
        policy["provider_dispatch_enabled"] = True
        changed = self.root / "changed_policy.json"
        changed.write_text(json.dumps(policy), encoding="utf-8")
        with self.assertRaisesRegex(ContractError, "PREPARE_ONLY authority"):
            Worker3Coordinator(
                AvshunterSourceBridge(self.fixture.root), self.store, changed
            )

    def test_no_charge_or_unknown_reservation_before_activation(self):
        self.prepare()
        self.assertEqual(
            self.store.accounting(),
            {
                "reported_cost_microusd": 0,
                "unknown_cost_reservation_microusd": 0,
                "unknown_calls": 0,
            },
        )


if __name__ == "__main__":
    unittest.main()
