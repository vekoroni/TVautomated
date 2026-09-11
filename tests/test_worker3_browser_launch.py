import json
import shutil
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from flask import Flask
from worker3.domain import ContractError, digest, canonical
from worker3.integration.browser_launch import BrowserWorker, install_worker3_browser
from tests.test_worker3_avshunter_source_bridge import SourceFixture, RUN_ID

ROOT=Path(__file__).resolve().parents[1]
class BrowserLaunchTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        fixture=SourceFixture(self.root)
        for i,ticker in enumerate(('CCC','DDD','EEE'),6):
            chain=hex(i)[2:]*64;quote=hex(i+3)[2:]*64;symbol=ticker+'261016C00010000'
            fixture.rows.append(fixture.lab_row(ticker,'CALL',chain,quote,symbol));fixture._register_chain_quote(ticker,chain,quote,symbol)
        fixture.write_run();(self.root/'contracts').mkdir()
        shutil.copy(ROOT/'contracts/worker3_integration_v1.json',self.root/'contracts/worker3_integration_v1.json')
        release=json.loads((ROOT/'contracts/worker3_provider_release_v1.json').read_text())
        release.update(enabled=True,status='CONTROLLED_ACTIVE',allowed_models=['claude-sonnet-4-6'],max_jobs_per_activation=5,max_calls_per_process=5,max_total_microusd=5000000,max_call_microusd=1000000,max_output_tokens=8192,max_input_bytes=500000,timeout_seconds=300,input_microusd_per_million_tokens=3000000,output_microusd_per_million_tokens=15000000)
        (self.root/'contracts/worker3_provider_release_v1.json').write_text(json.dumps(release))
        self.calls=[];self.counts=[];self.inject_failure=False
        owner=self
        class Fake:
            def __init__(self,**kwargs):self.receipts=[]
            def create(self,packet,**kwargs):
                owner.calls.append(digest(packet))
                if owner.inject_failure: raise ContractError('Injected failure')
                body=json.loads(packet['messages'][0]['content']);out=body['output_contract'];ref=next(k for k,v in body['untrusted_bound_evidence']['catalog'].items() if v['status']=='AVAILABLE')
                out['claims']=[dict(claim_id='evidence',claim_type='OBSERVATION',text='Supplied evidence is available.',supporting_evidence_ids=[ref],contradicting_evidence_ids=[])]
                for section in out['sections']:section['claim_ids']=['evidence']
                self.receipts.append(dict(request_hash=digest(packet),http_status=200,input_tokens=100,output_tokens=10))
                return dict(id='fake-response',model=packet['model'],stop_reason='end_turn',content=[dict(type='text',text=canonical(out))])
        def counter(packet): self.counts.append(digest(packet));return dict(input_tokens=100,frozen_request_hash=digest(packet))
        self.worker=BrowserWorker(self.root,counter=counter,transport_factory=Fake)
    def wait(self,batch):
        deadline=time.monotonic()+60
        while time.monotonic()<deadline:
            result=self.worker.status(batch)
            if result['state']!='RUNNING' and batch not in self.worker.active:return result
            time.sleep(.02)
        self.fail('Batch did not finish')
    def test_five_selected_exactly_once_and_durable_results(self):
        p=self.worker.preview(RUN_ID,['AAA','BBB','CCC','DDD','EEE']);self.assertEqual(len(self.calls),0)
        self.worker.launch(p['batch_id']);r=self.wait(p['batch_id']);self.assertEqual(r['state'],'COMPLETE');self.assertEqual(len(self.calls),5);self.assertEqual(len(set(self.calls)),5)
        with self.assertRaises(ContractError):self.worker.launch(p['batch_id'])
        reopened=BrowserWorker(self.root);self.assertEqual(len(reopened.status(p['batch_id'])['results']),5)
    def test_invalid_selection_never_calls_provider(self):
        for tickers in ([],['AAA']*2,['AAA','BBB','CCC','DDD','EEE','FFF']):
            with self.assertRaises(ContractError):self.worker.preview(RUN_ID,tickers)
        self.assertEqual(self.calls,[]);self.assertEqual(self.counts,[])
    def test_missing_ticker_blocks_entire_selection_before_count(self):
        with self.assertRaises(ContractError):self.worker.preview(RUN_ID,['AAA','MISSING'])
        self.assertEqual(self.counts,[])
    def test_failure_stops_remaining_jobs_without_retry(self):
        p=self.worker.preview(RUN_ID,['AAA','BBB']);self.inject_failure=True;self.worker.launch(p['batch_id']);self.assertEqual(self.wait(p['batch_id'])['state'],'STOPPED');self.assertEqual(len(self.calls),1)
    def test_changed_release_blocks_launch(self):
        p=self.worker.preview(RUN_ID,['AAA']);path=self.root/'contracts/worker3_provider_release_v1.json';path.write_text(path.read_text()+'\n')
        with self.assertRaises(ContractError):self.worker.launch(p['batch_id'])
        self.assertEqual(self.calls,[])
    def test_overlapping_previews_cannot_repeat_paid_job(self):
        first=self.worker.preview(RUN_ID,['AAA']);second=self.worker.preview(RUN_ID,['AAA']);self.worker.launch(first['batch_id']);self.wait(first['batch_id']);self.worker.launch(second['batch_id']);self.assertEqual(self.wait(second['batch_id'])['state'],'STOPPED');self.assertEqual(len(self.calls),1)
    def test_restart_does_not_resume_interrupted_batch(self):
        p=self.worker.preview(RUN_ID,['AAA'])
        with self.worker.db() as db:db.execute("UPDATE batches SET state='RUNNING' WHERE id=?",(p['batch_id'],))
        self.assertEqual(BrowserWorker(self.root).status(p['batch_id'])['state'],'INTERRUPTED_REVIEW_REQUIRED');self.assertEqual(self.calls,[])
    def test_cross_origin_and_missing_token_rejected(self):
        app=Flask('browser-test');install_worker3_browser(app,self.root);client=app.test_client()
        self.assertEqual(client.get('/api/worker3/control',headers={'Origin':'https://evil.example'}).status_code,403)
        token=client.get('/api/worker3/control').get_json()['token']
        self.assertEqual(client.post('/api/worker3/launch',json={},headers={'Origin':'http://localhost'}).status_code,403)
        self.assertEqual(client.post('/api/worker3/launch',json={},headers={'Origin':'https://evil.example','X-Worker3-Token':token}).status_code,403)
        self.assertEqual(client.get('/api/worker3/control',environ_base={'REMOTE_ADDR':'192.0.2.1'}).status_code,403)
    def test_selection_above_remaining_budget_is_rejected(self):
        path=self.root/'contracts/worker3_provider_release_v1.json';release=json.loads(path.read_text());release['max_total_microusd']=4000000;path.write_text(json.dumps(release))
        with self.assertRaisesRegex(ContractError,'Insufficient'):
            self.worker.preview(RUN_ID,['AAA','BBB','CCC','DDD','EEE'])
        self.assertEqual(self.calls,[])

    def test_counted_request_mismatch_blocks_preview(self):
        self.worker.counter=lambda packet:dict(input_tokens=100,frozen_request_hash='wrong')
        with self.assertRaisesRegex(ContractError,'frozen request'):
            self.worker.preview(RUN_ID,['AAA'])
        self.assertEqual(self.calls,[])

    def test_preview_expiry_prevents_generation(self):
        p=self.worker.preview(RUN_ID,['AAA'])
        with self.worker.db() as db:db.execute('UPDATE batches SET created=0 WHERE id=?',(p['batch_id'],))
        with self.assertRaisesRegex(ContractError,'expired'):
            self.worker.launch(p['batch_id'])
        self.assertEqual(self.calls,[])
