"""Escaped, read-only report presentation. No model-authored markup executes."""
import html
import json
from .report_detail import SECTION_GUIDANCE, coverage, quality

STYLE = '''body{margin:0;background:#0c1420;color:#e1e9f3;font:16px/1.6 system-ui,sans-serif}main{max-width:1150px;margin:auto;padding:28px}h1,h2,h3{line-height:1.25;color:#7ce0d1}article,.panel{background:#142132;border:1px solid #30455b;border-radius:10px;padding:20px;margin:20px 0}a{color:#79caff}table{width:100%;border-collapse:collapse;margin:15px 0;font-size:14px}td,th{text-align:left;vertical-align:top;padding:9px;border-bottom:1px solid #30455b;overflow-wrap:anywhere}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:12px}dt{font-weight:bold}dd{margin:0 0 8px}.note{color:#b5c4d6}.blocked{border-left:5px solid #ff8787}nav{display:flex;flex-wrap:wrap;gap:15px}summary{cursor:pointer}small{color:#b5c4d6}@media print{body{background:white;color:black}article,.panel{background:white;break-inside:avoid}h1,h2,h3{color:black}}'''

def esc(x): return html.escape(str(x),quote=True)

def document(title, body, refresh=False):
    return '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'+ ('<meta http-equiv="refresh" content="5">' if refresh else '')+'<title>'+esc(title)+'</title><style>'+STYLE+'</style></head><body><main>'+body+'</main></body></html>'

def display(value):
    if value is None or value=='':return 'Not supplied'
    if type(value) is float:return format(value,'.8g')
    if isinstance(value,(dict,list)):return json.dumps(value,ensure_ascii=False,indent=2)
    return str(value)

def table(headers, rows):
    return '<table><thead><tr>'+''.join('<th>'+esc(h)+'</th>' for h in headers)+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+esc(display(v))+'</td>' for v in row)+'</tr>' for row in rows)+'</tbody></table>'

def evidence_table(catalog, refs):
    rows=[]
    for ref in dict.fromkeys(refs):
        r=catalog[ref];o=r.get('observation',{})
        rows.append((o.get('field',r['kind']),r['status'],r['version'],
                     'Structured source document; see provenance' if r['unit']=='structured_json' else r['value'],
                     r['unit'],o.get('observed_at','System context'),o.get('source_id','Computed context')))
    return table(('Field','Availability','Version','Value','Unit','Source observation time','Source'),rows)

def render_detail(view):
    q=quality(view);catalog=view['system_evidence']['catalog']
    parts=['<section class="panel"><h3>Report depth and evidence coverage</h3><p>'+esc(q['status'])+'</p><p>'+esc(q['note'])+'</p>']
    if q['findings']:parts.append('<p>This saved narrative is brief. Evidence tables below add source detail; they do not regenerate or certify the narrative.</p>')
    parts.append(table(('Topic','Coverage','Missing typed fields'),[(c['topic'],c['status'],', '.join(c['missing_fields']) or 'None in this checklist') for c in coverage(catalog)]))
    parts.append('<p class="note">Partial means some listed fields are available, not that the topic is fully verified. The native source tables may contain additional snapshot context. A missing news field does not mean there was no news. Snapshot timestamps do not certify live market freshness.</p></section>')
    scalar=[r for r,v in catalog.items() if v.get('kind')=='OBSERVATION' and v.get('unit')!='structured_json']
    parts.append('<section class="panel"><h3>Bound evidence: values, availability and source times</h3>'+evidence_table(catalog,scalar)+'</section>')
    for ref,r in catalog.items():
        o=r.get('observation',{})
        if o.get('field')!='macro_ticker_context':continue
        parts.append(
            '<section class="panel"><h3>Governed ticker macro context</h3>'
            '<p><strong>ADVISORY_ONLY — DOES NOT CHANGE THE GOVERNED THESIS</strong></p>'
            '<p class="note">Frozen, ticker-conditioned macro evidence. It cannot change direction, contract, execution permission, capital permission or position size.</p>'
            '<p>Availability: '+esc(r.get('status','UNAVAILABLE'))+
            ' | Source: '+esc(o.get('source_id','Computed context'))+
            ' | Observed: '+esc(o.get('observed_at','System context'))+'</p>'
            '<pre>'+esc(display(r.get('value')))+'</pre></section>'
        )
    for ref,r in catalog.items():
        o=r.get('observation',{})
        if o.get('field')!='native_document_lab_signal_book':continue
        native=json.loads(o['value']);row=native['source_document']['row']
        groups={
         'Structure, trigger and invalidation':('trigger','target','invalidation','wyckoff','thesis','signal_price'),
         'Gamma, walls and drift':('gamma','wall','wbs','drift'),
         'Contract economics and liquidity':('contract','theta','vega','ivp','liquidity','monetisability','spread'),
         'Macro, sector and catalysts':('macro','sector','catalyst','news'),
        }
        parts.append('<section class="panel"><h3>Native Lab snapshot detail</h3><p class="note">Exact selected ticker row from the stored evidence. These source assertions have not been independently reconciled. File capture is not quote time. Blank fields remain unavailable; scenario profit is not an expected return.</p><p>Source: '+esc(o['source_id'])+' | Captured: '+esc(o['observed_at'])+'</p>')
        for title, prefixes in groups.items():
            values=[(k,v) for k,v in row.items() if any(p in k.lower() for p in prefixes) and not isinstance(v,(dict,list))]
            parts.append('<details open><summary>'+esc(title)+'</summary>'+table(('Source field','Recorded value'),values)+'</details>')
        parts.append('<details><summary>Full source and provenance</summary><pre>'+esc(json.dumps(native,ensure_ascii=False,indent=2))+'</pre></details></section>')
    return ''.join(parts)
