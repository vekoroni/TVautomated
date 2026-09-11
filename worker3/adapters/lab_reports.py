"""Immutable analyst read model and read-only Lab route installer."""
import html
import json
import sqlite3
import threading

from ..domain import canonical, digest, instant, utc, ContractError
from ..semantic import review_assessment
from ..v2.assessment import validate_assessment
from ..report_html import document, render_detail, evidence_table, table
from ..report_detail import SECTION_GUIDANCE, quality


class AnalystReports:
    def __init__(self, path):
        self.lock=threading.RLock()
        self.db=sqlite3.connect(str(path),check_same_thread=False)
        self.db.execute("CREATE TABLE IF NOT EXISTS analyst_reports (id TEXT PRIMARY KEY, run_id TEXT NOT NULL, ticker TEXT NOT NULL, view_json TEXT NOT NULL)")
        self.db.commit()

    def close(self): self.db.close()

    def save_draft(self, context, response, *, generated_at):
        generated_at=utc(generated_at)
        if instant(generated_at)<instant(context.job.bundle.evidence_cutoff_utc):
            raise ContractError("report predates evidence")
        checked=validate_assessment(context,response)
        semantic=review_assessment(context,response)
        rendered=json.loads(checked.rendered_json)
        key=digest({"context_hash":context.context_hash,"payload":json.loads(checked.payload_json),
                    "generated_at":generated_at,"request_id":response.request_id})
        view={"schema_version":"worker3_lab_report_v1","assessment_id":key,
              "identity":rendered["identity"],"generated_at":generated_at,
              "evidence_cutoff":context.job.bundle.evidence_cutoff_utc,
              "context_hash":context.context_hash,"evidence_hash":context.job.bundle.evidence_hash,
              "status":"BLOCKED_DRAFT" if semantic.status=="BLOCKED" else "UNREVIEWED_DRAFT",
              "authority":"ADVISORY_ONLY","human_review_required":True,"execution_permission":False,
              "semantic_findings":list(semantic.findings),"sections":rendered["sections"],
              "claims":rendered["claims"],"system_evidence":rendered["system_evidence"],
              "prior_assessment_id":context.previous.assessment_id if context.previous else None}
        raw=canonical(view)
        with self.lock, self.db:
            existing=self.db.execute("SELECT view_json FROM analyst_reports WHERE id=?",(key,)).fetchone()
            if existing and existing[0]!=raw: raise ContractError("immutable analyst report conflict")
            self.db.execute("INSERT OR IGNORE INTO analyst_reports VALUES(?,?,?,?)",
                            (key,context.job.bundle.identity.run_id,context.job.bundle.identity.ticker,raw))
        return key

    def get(self, run_id, ticker, assessment_id):
        with self.lock:
            row=self.db.execute("SELECT view_json FROM analyst_reports WHERE id=? AND run_id=? AND ticker=?",
                                (assessment_id,run_id,ticker)).fetchone()
        return json.loads(row[0]) if row else None


def render_panel(view):
    """Escape all source/model content. No generated HTML or script execution."""
    esc=lambda value:html.escape(str(value),quote=True)
    identity=view["identity"]
    parts=['<section class="worker3-report" aria-label="Worker 3 advisory report">',
           '<h2>Trading analyst — '+esc(identity['ticker'])+'</h2>',
           '<p role="status">'+esc(view['status'])+' — ADVISORY ONLY. Human review required. No trading permission.</p>',
           '<dl><dt>Run</dt><dd>'+esc(identity['run_id'])+'</dd><dt>Evidence cutoff</dt><dd>'+esc(view['evidence_cutoff'])+'</dd>',
           '<dt>Report generated</dt><dd>'+esc(view['generated_at'])+'</dd><dt>Assessment</dt><dd>'+esc(view['assessment_id'])+'</dd></dl>']
    parts.append(table(('Identity field','Value'),[(k,identity.get(k)) for k in ('ticker','direction','contract_symbol','contract_id','trading_session','planned_hold_sessions','thesis_id')]))
    depth=quality(view)
    parts.append('<p class="note">Report depth: '+esc(depth['status'])+'. Accuracy is not certified; human review remains required.</p>')
    if view['semantic_findings']:
        parts.append('<h3>Review findings</h3><ul>'+''.join('<li>'+esc(x)+'</li>' for x in view['semantic_findings'])+'</ul>')
    parts.append('<nav>'+''.join('<a href="#'+esc(s['section'])+'">'+esc(SECTION_GUIDANCE[s['section']][0])+'</a>' for s in view['sections'])+'</nav>')
    claims={c['claim_id']:c for c in view['claims']}
    for section in view['sections']:
        parts.extend(['<article id="'+esc(section['section'])+'"><h3>'+esc(SECTION_GUIDANCE[section['section']][0])+'</h3><small>'+esc(section['section'])+'</small><p>'+esc(section['summary'])+'</p>'])
        for claim_id in section['claim_ids']:
            claim=claims[claim_id]
            parts.append('<p>'+esc(claim['claim_type'])+': '+esc(claim['text'])+'</p>')
            refs=claim['supporting_evidence_ids']+claim['contradicting_evidence_ids']
            parts.append('<details><summary>Evidence references</summary>'+evidence_table(view['system_evidence']['catalog'],refs)+'<pre>'+esc(canonical({r:view['system_evidence']['catalog'][r] for r in refs}))+'</pre></details>')
        parts.append('</article>')
    comparison=view['system_evidence'].get('comparison')
    parts.append('<h3>Refresh comparison</h3>')
    if comparison is None:
        parts.append('<p>Initial assessment — no prior comparison.</p>')
    else:
        parts.append('<p>Prior assessment: '+esc(view['prior_assessment_id'])+'</p><pre>'+esc(canonical(comparison))+'</pre>')
    parts.append(render_detail(view))
    parts.append('</section>')
    return ''.join(parts)


def register_lab_routes(app, reports):
    """Flask-compatible optional routes; no existing routes/permissions modified.

    The production app must explicitly install this with its approved report store.
    No latest-report inference or ticker-only fallback is permitted.
    """
    @app.route('/api/worker3/report/<run_id>/<ticker>/<assessment_id>', methods=['GET'])
    def worker3_report_json(run_id,ticker,assessment_id):
        view=reports.get(run_id,ticker,assessment_id)
        return (canonical(view) if view else '{"error":"REPORT_NOT_FOUND"}',200 if view else 404,
                {'Content-Type':'application/json','Cache-Control':'no-store'})

    @app.route('/worker3/report/<run_id>/<ticker>/<assessment_id>', methods=['GET'])
    def worker3_report_panel(run_id,ticker,assessment_id):
        view=reports.get(run_id,ticker,assessment_id)
        return (document('Worker 3 — '+ticker, '<p><a href="/worker3/batches">All batch results</a></p>'+render_panel(view)) if view else 'Report not found',200 if view else 404,
                {'Content-Type':'text/html; charset=utf-8','Cache-Control':'no-store',
                 'Content-Security-Policy':"default-src 'none'; style-src 'unsafe-inline'; frame-ancestors 'self'"})
