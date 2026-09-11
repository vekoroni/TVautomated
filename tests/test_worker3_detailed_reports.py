import copy
import json
import unittest
from dataclasses import replace
from flask import Flask
from worker3.narrative import authority_language
from worker3.report_detail import coverage as detail_coverage, guidance, quality
from worker3.report_html import render_detail
from worker3.adapters.lab_reports import AnalystReports, render_panel
from worker3.integration.browser_launch import install_worker3_browser
from worker3.application import ProviderResponse
from worker3.domain import canonical
from worker3.semantic import review_assessment
from worker3.v2.assessment import build_evidence
from tests import test_worker3_evidence_coverage as coverage_tests
from tests.test_worker3_activation import FakeTransport
from tests import test_worker3_browser_launch as browser_tests
from tests.test_worker3_avshunter_source_bridge import RUN_ID

class AuthorityDenialTests(unittest.TestCase):
    def test_denial_and_mixed_approval(self):
        for text in ('No capital permission exists.', 'Capital permission is denied.', 'No capital permission is granted.'):
            self.assertIsNone(authority_language(text))
        for text in ('No doubt, capital permission exists.', 'No capital permission exists, but buy now.', 'Capital permission granted.', 'No capital permission exists; capital permission granted.'):
            self.assertIsNotNone(authority_language(text))

class DetailedEvidenceTests(unittest.TestCase):
    setUp = coverage_tests.EvidenceCoverageTests.setUp
    metadata = coverage_tests.EvidenceCoverageTests.metadata
    def test_plan_and_missing_news(self):
        plan=guidance(build_evidence(self.context)['catalog']);self.assertEqual(len(plan['sections']),8)
        self.assertEqual(next(c for c in plan['evidence_coverage'] if c['topic']=='News and catalysts')['status'],'NOT_SUPPLIED_AS_TYPED_EVIDENCE')
    def test_macro_ticker_context_is_counted_as_typed_macro_coverage(self):
        catalog = {
            'ctx': {
                'version': 'current',
                'status': 'AVAILABLE',
                'observation': {'field': 'macro_ticker_context'},
            },
        }
        macro = next(row for row in detail_coverage(catalog) if row['topic'] == 'Macro context')
        self.assertEqual(macro['status'], 'PARTIAL')
        self.assertEqual(macro['refs'], ['ctx'])
        self.assertNotIn('macro_ticker_context', macro['missing_fields'])
    def test_macro_ticker_context_is_visible_and_explicitly_advisory(self):
        context_value = json.dumps({
            'authority': 'ADVISORY_ONLY',
            'ticker': 'AAA',
            'themes': ['OIL_SHOCK'],
        })
        view = {
            'claims': {},
            'sections': [],
            'system_evidence': {'catalog': {
                'ctx': {
                    'kind': 'OBSERVATION',
                    'unit': 'structured_json',
                    'value': context_value,
                    'version': 'current',
                    'status': 'AVAILABLE',
                    'observation': {
                        'field': 'macro_ticker_context',
                        'source_id': 'MACRO:fixture',
                        'observed_at': '2026-09-11T09:00:00Z',
                    },
                },
            }},
        }
        rendered = render_detail(view)
        self.assertIn('Governed ticker macro context', rendered)
        self.assertIn('ADVISORY_ONLY — DOES NOT CHANGE THE GOVERNED THESIS', rendered)
        self.assertIn('OIL_SHOCK', rendered)
    def test_chpt_denial_and_approval_through_validator(self):
        ctx=self.context;raw=json.loads(FakeTransport(ctx).create({},timeout_seconds=30)['content'][0]['text']);ref,_=self.metadata(ctx)
        raw['claims']=[dict(claim_id='a',claim_type='OBSERVATION',text='No prior assessment was supplied.',supporting_evidence_ids=[ref],contradicting_evidence_ids=[])]
        for s in raw['sections']:s.update(claim_ids=['a'],summary='No capital permission exists.')
        response=ProviderResponse(canonical(raw),'fixture',ctx.job.provider,ctx.job.model,'COMPLETE')
        self.assertEqual(review_assessment(ctx,response).status,'REQUIRES_HUMAN_REVIEW')
        raw['sections'][0]['summary']='Capital permission granted.'
        self.assertEqual(review_assessment(ctx,replace(response,json_text=canonical(raw))).status,'BLOCKED')
    def test_render_is_escaped_immutable_and_labels_brief(self):
        ctx=self.context;raw=FakeTransport(ctx).create({},timeout_seconds=30)
        response=ProviderResponse(raw['content'][0]['text'],'fixture',ctx.job.provider,ctx.job.model,'COMPLETE')
        reports=AnalystReports(':memory:')
        try:
            key=reports.save_draft(ctx,response,generated_at=ctx.job.bundle.evidence_cutoff_utc)
            view=reports.get(ctx.job.bundle.identity.run_id,ctx.job.bundle.identity.ticker,key)
            before=canonical(view);q=quality(view);html=render_panel(view)
            self.assertEqual(q['status'],'BRIEF_REPORT');self.assertFalse(q['publication_ready'])
            self.assertIn('Bound evidence',html);self.assertIn('Native Lab snapshot',html)
            self.assertEqual(canonical(view),before)
            evil=copy.deepcopy(view);evil['sections'][0]['summary']='<script>alert(1)</script>'
            self.assertNotIn('<script>',render_panel(evil));self.assertIn('&lt;script&gt;',render_panel(evil))
        finally:reports.close()

class BatchReportTests(unittest.TestCase):
    setUp = browser_tests.BrowserLaunchTests.setUp
    wait = browser_tests.BrowserLaunchTests.wait
    def test_combined_page_all_tickers_and_guard(self):
        p=self.worker.preview(RUN_ID,['AAA','BBB']);self.worker.launch(p['batch_id']);b=self.wait(p['batch_id'])
        self.assertEqual(b['completed_count'],2);self.assertEqual(b['selected_count'],2)
        app=Flask('combined');install_worker3_browser(app,self.root);client=app.test_client()
        page=client.get(b['batch_url']);self.assertEqual(page.status_code,200);text=page.get_data(as_text=True)
        self.assertIn('Trading analyst '+chr(8212)+' AAA',text);self.assertIn('Trading analyst '+chr(8212)+' BBB',text);self.assertIn('2/2 reports',text)
        self.assertEqual(len(self.calls),2);self.assertIn('AAA, BBB',client.get('/worker3/batches').get_data(as_text=True))
        self.assertEqual(client.get(b['batch_url'],headers={'Origin':'https://evil.example'}).status_code,403)
    def test_old_preview_is_rejected_before_paid_activation(self):
        p=self.worker.preview(RUN_ID,['AAA'])
        with self.worker.db() as db:
            row=db.execute('SELECT payload FROM batches WHERE id=?',(p['batch_id'],)).fetchone()
            payload=json.loads(row['payload']);payload.pop('report_profile')
            db.execute('UPDATE batches SET payload=? WHERE id=?',(json.dumps(payload),p['batch_id']))
        from worker3.domain import ContractError
        with self.assertRaisesRegex(ContractError,'requirements changed'):
            self.worker.launch(p['batch_id'])
        self.assertEqual(self.calls,[])
    def test_failure_keeps_all_tickers_visible(self):
        p=self.worker.preview(RUN_ID,['AAA','BBB']);self.inject_failure=True;self.worker.launch(p['batch_id']);b=self.wait(p['batch_id'])
        self.assertEqual(len(b['entries']),2);self.assertEqual(b['completed_count'],0)
        self.assertEqual(b['entries'][1]['status'],'NO_REPORT_REVIEW_JOB_STATE')

class TypedDetailTests(unittest.TestCase):
    def test_blank_numeric_text_and_zero_are_distinguished(self):
        import tempfile
        from pathlib import Path
        from tests.test_worker3_avshunter_source_bridge import SourceFixture
        from worker3.integration.avshunter_source import AvshunterSourceBridge
        with tempfile.TemporaryDirectory() as folder:
            f=SourceFixture(Path(folder))
            f.rows[0].update(gamma_flip=0.0, trigger_price='', call_wall='12.3')
            f.write_run()
            entry=AvshunterSourceBridge(f.root).prepare_run(RUN_ID,tickers=('AAA',)).entries[0]
            fields={o.field:o for o in entry.bundle.observations}
            self.assertEqual(fields['gamma_flip'].value,0.0)
            self.assertEqual(fields['gamma_flip'].status,'AVAILABLE')
            self.assertEqual(fields['trigger_price'].status,'UNAVAILABLE')
            self.assertEqual(fields['call_wall'].status,'UNAVAILABLE')
