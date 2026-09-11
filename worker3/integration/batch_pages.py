"""Read-only combined report pages; never launch, retry or mutate assessments."""
from flask import abort
from ..adapters.lab_reports import AnalystReports, render_panel
from ..domain import ContractError
from ..report_html import document, esc, table

HEADERS={'Cache-Control':'no-store','Content-Security-Policy':"default-src 'none'; style-src 'unsafe-inline'; frame-ancestors 'self'"}

def install_batch_pages(app, service, guard):
    @app.get('/worker3/batches')
    def worker3_batches_page():
        guard()
        with service.db() as db:
            ids=[r['id'] for r in db.execute("SELECT id FROM batches WHERE state != 'PREVIEW' ORDER BY created DESC LIMIT 50")]
        parts=['<h1>Worker 3 batch results</h1><p><a href="/">Return to Intelligence Lab</a></p>']
        for batch_id in ids:
            b=service.status(batch_id)
            parts.append('<article><h2><a href="'+esc(b['batch_url'])+'">'+esc(', '.join(b['tickers']))+'</a></h2><p>'+esc(b['state'])+' | '+str(b['completed_count'])+'/'+str(b['selected_count'])+' reports | Run '+esc(b['run_id'])+'</p></article>')
        if not ids:parts.append('<p>No launched batches.</p>')
        return document('Worker 3 batches',''.join(parts)),200,HEADERS

    @app.get('/worker3/batch/<batch_id>')
    def worker3_batch_page(batch_id):
        guard()
        try: b=service.status(batch_id)
        except ContractError:abort(404)
        parts=['<h1>Worker 3 batch report</h1><p><a href="/worker3/batches">All batches</a> | <a href="/">Intelligence Lab</a></p>',
               '<p>'+esc(b['state'])+' — '+str(b['completed_count'])+'/'+str(b['selected_count'])+' reports — Run '+esc(b['run_id'])+'</p>',
               '<p>Reported API cost: $'+format(b['cost_microusd']/1e6,'.6f')+'. This excludes other operating costs and any unresolved provider charge.</p>']
        if b['error']:parts.append('<p class="blocked">'+esc(b['error'])+'</p>')
        parts.append(table(('Selected ticker','Result'),[(e['ticker'],e['status']) for e in b['entries']]))
        reports=AnalystReports(service.data/'analyst_reports.sqlite')
        try:
            for e in b['entries']:
                r=e['result']
                if r:
                    parts.append('<p><a href="'+esc(r['report_url'])+'">Open '+esc(e['ticker'])+' separately</a></p>')
                    v=reports.get(b['run_id'],e['ticker'],r['assessment_id'])
                    if v:parts.append(render_panel(v).replace('id="','id="'+esc(e['ticker'])+'-').replace('href="#','href="#'+esc(e['ticker'])+'-'))
                    else:parts.append('<p>Stored report unavailable; inspect job state. No rerun performed.</p>')
        finally:reports.close()
        return document('Worker 3 batch',''.join(parts),b['state']=='RUNNING'),200,HEADERS
