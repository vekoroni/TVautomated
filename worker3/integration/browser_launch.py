"""Local-browser, explicit-preview batch launch. Durable latch; no auto-resume."""
import json
import secrets
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlsplit

from flask import abort, jsonify, request
from ..domain import ContractError, digest
from .batch_pages import install_batch_pages
from ..report_detail import PROFILE
from ..adapters.jobs import JobStore
from ..adapters.lab_reports import AnalystReports
from ..adapters.claude_v2 import ClaudeV2Adapter
from ..adapters.anthropic_http import AnthropicHTTP
from .activation import ControlledProviderRuntime, load_provider_release
from .coordinator import Worker3Coordinator
from .avshunter_source import AvshunterSourceBridge
from .current_canary import count_frozen_request


class BrowserWorker:
    def __init__(self, root, counter=count_frozen_request, transport_factory=AnthropicHTTP):
        self.root = Path(root)
        self.data = self.root / 'data/worker3'
        self.data.mkdir(parents=True, exist_ok=True)
        self.release_path = self.root / 'contracts/worker3_provider_release_v1.json'
        self.counter = counter
        self.transport_factory = transport_factory
        self.preview_lock = threading.Lock()
        self.active = set()
        self.lock = threading.Lock()
        with self.db() as db:
            db.execute('CREATE TABLE IF NOT EXISTS batches (id TEXT PRIMARY KEY, state TEXT NOT NULL, payload TEXT NOT NULL, results TEXT NOT NULL, error TEXT, created REAL NOT NULL)')

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.data / 'browser_batches.sqlite', timeout=30)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def runtime(self):
        release = load_provider_release(self.release_path)
        if not release.enabled or release.allowed_models != ('claude-sonnet-4-6',):
            raise ContractError('Worker 3 release is not enabled for the approved model')
        jobs = JobStore(self.data / 'worker3_jobs.sqlite', budget_microusd=release.max_total_microusd)
        reports = AnalystReports(self.data / 'analyst_reports.sqlite')
        coordinator = Worker3Coordinator(AvshunterSourceBridge(self.root), jobs, self.root / 'contracts/worker3_integration_v1.json')
        return jobs, reports, coordinator, ControlledProviderRuntime(coordinator, jobs, reports, self.release_path)

    def preview(self, run_id, tickers, previous_assessment_ids=None):
        if (not isinstance(run_id, str) or not run_id or not isinstance(tickers, list)
                or not 1 <= len(tickers) <= 5 or any(not isinstance(t, str) or not t for t in tickers)
                or len(set(tickers)) != len(tickers)):
            raise ContractError('Select one to five unique tickers from one run')
        if not self.preview_lock.acquire(blocking=False):
            raise ContractError('Another preview is in progress; wait for it to finish')
        try:
            jobs, reports, coordinator, runtime = self.runtime()
            try:
                release = runtime.release
                if len(tickers) > release.max_jobs_per_activation:
                    raise ContractError('Selection exceeds release job limit')
                prepared = coordinator.prepare_run(run_id, provider='ANTHROPIC', model=release.allowed_models[0],
                    tickers=tuple(tickers), now=time.time(), call_ceiling_microusd=release.max_call_microusd,
                    max_input_bytes=release.max_input_bytes, max_output_tokens=release.max_output_tokens,
                    timeout_seconds=release.timeout_seconds,
                    previous_assessment_ids=previous_assessment_ids)
                if len(prepared.entries) != len(tickers) or any(not e.job_id for e in prepared.entries):
                    raise ContractError('Selection contains missing or invalid evidence; no batch launched')
                entries = []
                for entry in prepared.entries:
                    record = jobs.job_record(entry.job_id)
                    if record['status'] != 'PREPARED':
                        raise ContractError('A selected job already ran or was activated; inspect its existing result')
                    ctx = coordinator.restore_context(entry.job_id)
                    adapter = ClaudeV2Adapter(type('NoCall', (), {'create': lambda *a, **k: None})(), release.max_output_tokens, release.max_input_bytes, release.timeout_seconds, ctx)
                    packet = adapter.request_for(ctx.job)
                    receipt = self.counter(packet)
                    if receipt.get('frozen_request_hash') != digest(packet):
                        raise ContractError('Token count does not match frozen request')
                    bound = ((receipt['input_tokens'] + 4096) * release.input_rate + release.max_output_tokens * release.output_rate + 999999) // 1000000
                    if bound > release.max_call_microusd:
                        raise ContractError('A selected request exceeds the per-ticker cost ceiling')
                    entries.append({'job_id':entry.job_id, 'ticker':ctx.job.bundle.identity.ticker,
                                    'previous_assessment_id':ctx.job.previous_assessment_id,
                                    'request_hash':digest(packet), 'cost_bound_microusd':bound})
                reserved = len(entries) * release.max_call_microusd
                accounting = jobs.accounting()
                available = release.max_total_microusd - accounting['reported_cost_microusd'] - accounting['unknown_cost_reservation_microusd']
                activated = jobs.db.execute('SELECT COALESCE(SUM(j.ceiling),0) FROM activations a JOIN jobs j ON j.id=a.job_id WHERE a.release_hash=?', (release.content_hash,)).fetchone()[0]
                if reserved > available or reserved + activated > release.max_total_microusd:
                    raise ContractError('Insufficient remaining release budget for this selection')
                payload = {'report_profile':PROFILE, 'run_id':run_id, 'entries':entries, 'release_hash':release.content_hash,
                           'reserved_microusd':reserved, 'cost_bound_microusd':sum(e['cost_bound_microusd'] for e in entries)}
                batch_id = secrets.token_urlsafe(24)
                with self.db() as db:
                    db.execute('INSERT INTO batches VALUES(?,?,?,?,?,?)', (batch_id,'PREVIEW',json.dumps(payload),'[]',None,time.time()))
                return {'batch_id':batch_id, **payload}
            finally:
                reports.close(); jobs.close()
        finally:
            self.preview_lock.release()

    def launch(self, batch_id):
        with self.db() as db:
            row = db.execute('SELECT * FROM batches WHERE id=?', (batch_id,)).fetchone()
            if row is None or row['state'] != 'PREVIEW' or time.time() - row['created'] > 900:
                raise ContractError('Preview expired or already launched; no retry performed')
            payload = json.loads(row['payload'])
            if payload.get('report_profile') != PROFILE:
                raise ContractError('Report requirements changed; create a new preview')
            if load_provider_release(self.release_path).content_hash != payload['release_hash']:
                raise ContractError('Release changed; create a new preview')
            changed = db.execute("UPDATE batches SET state='RUNNING' WHERE id=? AND state='PREVIEW'", (batch_id,)).rowcount
            if changed != 1:
                raise ContractError('Batch already launched')
        with self.lock:
            self.active.add(batch_id)
        threading.Thread(target=self.execute, args=(batch_id,payload), daemon=True).start()
        return {'batch_id':batch_id, 'state':'RUNNING'}

    def execute(self, batch_id, payload):
        results = []
        jobs = reports = None
        try:
            jobs, reports, coordinator, runtime = self.runtime()
            if runtime.release.content_hash != payload['release_hash']:
                raise ContractError('Release changed before dispatch')
            runtime.activate(tuple(e['job_id'] for e in payload['entries']), operator_approval_id='browser:'+batch_id, now=time.time())
            release = runtime.release
            transport = self.transport_factory(enabled=True,max_calls=len(payload['entries']),max_input_bytes=release.max_input_bytes,max_output_tokens=release.max_output_tokens)
            create = transport.create
            allowed = {e['request_hash'] for e in payload['entries']}
            def frozen_create(packet, **kwargs):
                key = digest(packet)
                if key not in allowed:
                    raise ContractError('Request changed or already dispatched')
                allowed.remove(key)
                return create(packet, **kwargs)
            transport.create = frozen_create
            for index, entry in enumerate(payload['entries']):
                result = runtime.execute(entry['job_id'],transport=transport,clock=time.time)
                result['ticker'] = entry['ticker']
                result['report_url'] = '/worker3/report/'+payload['run_id']+'/'+entry['ticker']+'/'+result['assessment_id']
                results.append(result)
                with self.db() as db:
                    db.execute('UPDATE batches SET results=? WHERE id=?', (json.dumps(results),batch_id))
                if result.get('semantic_status') == 'BLOCKED':
                    raise ContractError('Semantic review blocked '+entry['ticker']+'; '+str(len(payload['entries'])-index-1)+' remaining jobs were not sent')
            with self.db() as db:
                db.execute("UPDATE batches SET state='COMPLETE' WHERE id=?", (batch_id,))
        except Exception as exc:
            message = str(exc) if isinstance(exc, ContractError) else 'Batch failed; inspect durable job state before any further action'
            with self.db() as db:
                db.execute("UPDATE batches SET state='STOPPED', error=? WHERE id=?", (message,batch_id))
        finally:
            if reports is not None: reports.close()
            if jobs is not None: jobs.close()
            with self.lock: self.active.discard(batch_id)

    def status(self, batch_id):
        with self.db() as db:
            row = db.execute('SELECT * FROM batches WHERE id=?', (batch_id,)).fetchone()
        if row is None: raise ContractError('Unknown batch')
        state = row['state']
        with self.lock:
            if state == 'RUNNING' and batch_id not in self.active:
                state = 'INTERRUPTED_REVIEW_REQUIRED'
        payload=json.loads(row['payload'])
        results=json.loads(row['results'])
        by_ticker={r['ticker']:r for r in results}
        error=row['error']
        if len(results)==len(payload['entries']) and any(r.get('semantic_status')=='BLOCKED' for r in results):
            error='All selected tickers returned reports. Blocked drafts require review; no automatic rerun was performed.'
        entries=[{'ticker':e['ticker'], 'status':by_ticker[e['ticker']]['semantic_status'] if e['ticker'] in by_ticker else ('PENDING_OR_IN_PROGRESS' if state=='RUNNING' else 'NO_REPORT_REVIEW_JOB_STATE'),
                  'result':by_ticker.get(e['ticker'])} for e in payload['entries']]
        return {'entries':entries, 'completed_count':len(results), 'selected_count':len(entries),
                'cost_microusd':sum(r.get('cost_microusd',0) for r in results),
                'batch_url':'/worker3/batch/'+batch_id, 'batch_id':batch_id,'state':state,'run_id':payload['run_id'], 'tickers':[e['ticker'] for e in payload['entries']],
                'results':results,'error':error}


def install_worker3_browser(app, root):
    service = BrowserWorker(root)
    token = secrets.token_urlsafe(32)
    def guard(write=False):
        if request.remote_addr not in ('127.0.0.1','::1') or urlsplit(request.host_url).hostname not in ('localhost','127.0.0.1','::1'):
            abort(403)
        origin = request.headers.get('Origin')
        if origin and origin.rstrip('/') != request.host_url.rstrip('/'):
            abort(403)
        if write and (not request.is_json or request.headers.get('X-Worker3-Token') != token or not origin):
            abort(403)
    @app.get('/api/worker3/control')
    def worker3_control():
        guard(); release=load_provider_release(service.release_path)
        return jsonify(token=token,report_profile=PROFILE,enabled=release.enabled,max_tickers=min(5,release.max_jobs_per_activation),total_cap_microusd=release.max_total_microusd,per_ticker_cap_microusd=release.max_call_microusd)
    @app.post('/api/worker3/preview')
    def worker3_preview():
        guard(True); data=request.get_json()
        if not isinstance(data, dict): abort(400)
        try: return jsonify(service.preview(
            data.get('run_id'), data.get('tickers'),
            data.get('previous_assessment_ids'),
        ))
        except ContractError as exc: return jsonify(error=str(exc)),409
    @app.post('/api/worker3/launch')
    def worker3_launch():
        guard(True); data=request.get_json()
        if not isinstance(data, dict): abort(400)
        try: return jsonify(service.launch(data.get('batch_id')))
        except ContractError as exc: return jsonify(error=str(exc)),409
    @app.get('/api/worker3/batch/<batch_id>')
    def worker3_batch(batch_id):
        guard()
        try: return jsonify(service.status(batch_id))
        except ContractError as exc: return jsonify(error=str(exc)),404
    install_batch_pages(app, service, guard)
    return service
