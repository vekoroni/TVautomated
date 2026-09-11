import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from worker3.adapters.jobs import JobStore
from worker3.adapters.claude_v2 import ClaudeV2Adapter
from worker3.integration import AvshunterSourceBridge, Worker3Coordinator
from worker3.v2.assessment import build_evidence, AssessmentContext, PreviousAssessment, _render
from worker3.semantic import review_assessment
from worker3.application import ProviderResponse
from worker3.domain import ContractError, canonical
from tests.test_worker3_avshunter_source_bridge import SourceFixture, RUN_ID
from tests.test_worker3_activation import FakeTransport, INTEGRATION_POLICY


class EvidenceCoverageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        fixture = SourceFixture(root / 'source')
        store = JobStore(root / 'jobs.sqlite', budget_microusd=1000000)
        self.addCleanup(store.close)
        coordinator = Worker3Coordinator(AvshunterSourceBridge(fixture.root), store, INTEGRATION_POLICY)
        prepared = coordinator.prepare_run(RUN_ID, provider='ANTHROPIC', model='fixture-model', now=1000,
                                           tickers=('AAA',), call_ceiling_microusd=100000)
        self.context = coordinator.restore_context(prepared.entries[0].job_id)

    def metadata(self, ctx):
        return next((ref, row) for ref, row in build_evidence(ctx)['catalog'].items()
                    if ref.startswith('context:comparison:'))

    def test_initial_comparison_availability_is_citable_but_not_a_numeric_slot(self):
        ref, row = self.metadata(self.context)
        self.assertEqual(row['detail']['status'], 'NO_PRIOR_ASSESSMENT_SUPPLIED')
        self.assertIsNone(row['detail']['previous_assessment_id'])
        self.assertEqual(row['status'], 'AVAILABLE')
        self.assertEqual((ref, row), self.metadata(self.context))
        with self.assertRaises(ContractError):
            _render('{{slot:' + ref + '}}', {ref}, {ref: row})

    def test_refresh_metadata_identifies_supplied_prior(self):
        ctx = self.context
        raw = FakeTransport(ctx).create({}, timeout_seconds=30)
        response = ProviderResponse(raw['content'][0]['text'], 'fixture', ctx.job.provider, ctx.job.model, 'COMPLETE')
        prior = PreviousAssessment(ctx, response, ctx.job.bundle.evidence_cutoff_utc)
        refreshed = AssessmentContext(replace(ctx.job, task_type='REFRESH_ASSESSMENT', previous_assessment_id=prior.assessment_id), ctx.scenarios, prior)
        ref, row = self.metadata(refreshed)
        self.assertEqual(row['detail']['status'], 'PRIOR_ASSESSMENT_SUPPLIED')
        self.assertEqual(row['detail']['previous_assessment_id'], prior.assessment_id)
        self.assertNotEqual(ref, self.metadata(ctx)[0])

    def test_schema_requires_nonempty_claim_and_section_citations(self):
        ctx = self.context
        request = ClaudeV2Adapter(FakeTransport(ctx), 2048, 500000, 30, ctx).request_for(ctx.job)
        props = request['output_config']['format']['schema']['properties']
        self.assertEqual(props['claims']['items']['properties']['supporting_evidence_ids']['minItems'], 1)
        self.assertEqual(props['sections']['items']['properties']['claim_ids']['minItems'], 2)
        ref, _ = self.metadata(ctx)
        self.assertIn(ref, props['claims']['items']['properties']['supporting_evidence_ids']['items']['enum'])

    def test_cited_comparison_claim_clears_only_changes_coverage(self):
        ctx = self.context
        raw = json.loads(FakeTransport(ctx).create({}, timeout_seconds=30)['content'][0]['text'])
        ref, _ = self.metadata(ctx)
        raw['claims'] = [{'claim_id': 'comparison', 'claim_type': 'OBSERVATION',
                         'text': 'No prior assessment was supplied; comparison is unavailable.',
                         'supporting_evidence_ids': [ref], 'contradicting_evidence_ids': []}]
        for section in raw['sections']:
            if section['section'] == 'CHANGES':
                section['claim_ids'] = ['comparison']
                section['summary'] = 'Comparison is unavailable without a supplied prior assessment.'
        response = ProviderResponse(canonical(raw), 'fixture', ctx.job.provider, ctx.job.model, 'COMPLETE')
        review = review_assessment(ctx, response)
        self.assertNotIn('section:CHANGES:UNCITED_SECTION_REVIEW', review.findings)
        self.assertIn('section:COMPANY:UNCITED_SECTION_REVIEW', review.findings)
        self.assertEqual(review.status, 'BLOCKED')
