import json
from pathlib import Path
import tempfile
import unittest

from worker3.adapters.claude_v2 import ClaudeV2Adapter
from worker3.domain import ContractError, WorkerJob
from worker3.integration.avshunter_source import AvshunterSourceBridge
from worker3.integration.current_canary import NoTransport
from worker3.v2.assessment import AssessmentContext, PROMPT, build_evidence, _render
from tests import test_worker3_avshunter_source_bridge as fixtures


class ResponseGuidanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        fixture = fixtures.SourceFixture(Path(self.temp.name))
        entry = AvshunterSourceBridge(fixture.root).prepare_run(fixtures.RUN_ID, tickers=("AAA",)).entries[0]
        self.context = AssessmentContext(WorkerJob(entry.bundle, "ANTHROPIC", "fixture-model", PROMPT))
        self.request = ClaudeV2Adapter(NoTransport(), 8192, 500000, 300, self.context).request_for(self.context.job)
        self.packet = json.loads(self.request["messages"][0]["content"])

    def test_generated_slot_examples_pass_the_real_renderer(self):
        catalog = build_evidence(self.context)["catalog"]
        examples = self.packet["field_rules"]["valid_numeric_claim_examples"]
        self.assertEqual(len(examples), 2)
        for example in examples:
            rendered = _render(example["text"], set(example["supporting_evidence_ids"]), catalog)
            self.assertNotIn("{{slot:", rendered)
            self.assertIn("CURRENT", rendered)

    def test_guidance_preserves_complete_governed_evidence(self):
        self.assertEqual(self.packet["untrusted_bound_evidence"], build_evidence(self.context))
        self.assertEqual(len(self.packet["output_contract"]["sections"]), 8)

    def test_shortened_reference_and_raw_digits_remain_rejected(self):
        catalog = build_evidence(self.context)["catalog"]
        example = self.packet["field_rules"]["valid_numeric_claim_examples"][0]
        full = example["supporting_evidence_ids"][0]
        short = catalog[full]["observation"]["evidence_id"]
        with self.assertRaises(ContractError):
            _render(example["text"].replace(full, short), {short}, catalog)
        with self.assertRaisesRegex(ContractError, "raw digits"):
            _render("The price is 10.", {full}, catalog)


if __name__ == "__main__":
    unittest.main()
