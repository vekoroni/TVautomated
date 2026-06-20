"""
AVSHUNTER Pipeline Interpreter v1.0 — Output Writers
Trade narrative HTML + brief CSV
"""
import csv, json, re, io
from datetime import datetime
from pathlib import Path

EXECUTION_PERMISSION = "NONE_PIPELINE_INTERPRETER_ONLY"
CAPITAL_PERMISSION   = "CAPITAL_DENIED_PENDING_LIVE_CONFIRMATION"

BRIEF_CSV_FIELDS = [
    "ticker","direction","final_verdict","trade_state","horizon","dte",
    "trigger_level","kill_switch_level","preferred_contract","premium","rr",
    "iv_context","ivp","earnings_in_window","earnings_action",
    "max_pain_risk","sector_confirmation_required","first_hour_rule",
    "probe_permitted","initial_adverse_tolerance","capital_permission",
    "narrative_summary","execution_permission"
]

def _extract_section(response:str, tag:str) -> str:
    m=re.search(rf'\[{tag}\](.*?)(?=\[[A-Z_]+\]|$)', response, re.DOTALL|re.IGNORECASE)
    return m.group(1).strip() if m else ""

def _extract_ticker_narrative(response:str, ticker:str) -> str:
    m=re.search(rf'\[TRADE_NARRATIVE_{ticker}\](.*?)(?=\[TRADE_NARRATIVE_|\[SESSION_|$)',
                response, re.DOTALL|re.IGNORECASE)
    return m.group(1).strip() if m else ""

def _clean_csv(text:str) -> str:
    text=re.sub(r'```[a-z]*','',text).replace('```','').strip()
    lines=[l for l in text.splitlines() if l.strip() and l.strip()!='---']
    return '\n'.join(lines)

def _parse_csv(text:str) -> list:
    if not text.strip(): return []
    try:
        rows=list(csv.DictReader(io.StringIO(_clean_csv(text))))
        for r in rows:
            r["execution_permission"]=EXECUTION_PERMISSION
            r["capital_permission"]=CAPITAL_PERMISSION
        return rows
    except Exception as e:
        print(f"  ⚠ CSV: {e}"); return []

def _write_csv(rows:list, path:Path, fields:list) -> int:
    if not rows: return 0
    path.parent.mkdir(parents=True,exist_ok=True)
    with open(path,"w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction="ignore")
        w.writeheader()
        for r in rows:
            r["execution_permission"]=EXECUTION_PERMISSION
            r["capital_permission"]=CAPITAL_PERMISSION
            w.writerow(r)
    return len(rows)

def _verdict_style(v:str) -> tuple:
    styles={
        # Pipeline verdicts (machine layer)
        "GO":                  ("#00ff88","#003300","#00ff8822"),
        "ARMED":               ("#00d4aa","#002a22","#00d4aa22"),
        "PROBE":               ("#f59e0b","#1a1200","#f59e0b22"),
        "WAIT":                ("#64748b","#0f1520","#64748b22"),
        "BLOCKED":             ("#ef4444","#1a0000","#ef444422"),
        "MISDIAGNOSED":        ("#a855f7","#1a0a2a","#a855f722"),
        # Interpreter verdicts (human layer — v2)
        "PROBE_NOW":           ("#00ff88","#003300","#00ff8822"),
        "PROBE_WATCH":         ("#f59e0b","#1a1200","#f59e0b22"),
        "MONITOR":             ("#38bdf8","#001a26","#38bdf822"),
        "CROWD_TRADE":         ("#e879f9","#1a0026","#e879f922"),
        "PASS_THESIS_INVALID": ("#ef4444","#1a0000","#ef444422"),
    }
    return styles.get(v,("#64748b","#0f1520","#64748b22"))

def _md_to_html(text:str) -> str:
    if not text: return "<p>No data.</p>"
    text=text.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")
    text=re.sub(r'^### (.+)$',r'<h4>\1</h4>',text,flags=re.MULTILINE)
    text=re.sub(r'^## (.+)$',r'<h3>\1</h3>',text,flags=re.MULTILINE)
    text=re.sub(r'^# (.+)$',r'<h3>\1</h3>',text,flags=re.MULTILINE)
    text=re.sub(r'\*\*(.+?)\*\*',r'<strong>\1</strong>',text)
    text=re.sub(r'`(.+?)`',r'<code>\1</code>',text)
    lines=text.split('\n'); result=[]; in_table=False; trows=[]
    for line in lines:
        s=line.strip()
        if s.startswith('|') and '|' in s[1:]:
            if not in_table: in_table=True; trows=[]
            if re.match(r'^\|[\s\-|]+\|$',s): continue
            trows.append([c.strip() for c in s.split('|')[1:-1]])
        else:
            if in_table and trows:
                hdr='<tr>'+''.join(f'<th>{c}</th>' for c in trows[0])+'</tr>'
                bdy=''.join('<tr>'+''.join(f'<td>{c}</td>' for c in r)+'</tr>' for r in trows[1:])
                result.append(f'<table class="ntbl">{hdr}{bdy}</table>'); trows=[]; in_table=False
            result.append(line)
    if in_table and trows:
        hdr='<tr>'+''.join(f'<th>{c}</th>' for c in trows[0])+'</tr>'
        bdy=''.join('<tr>'+''.join(f'<td>{c}</td>' for c in r)+'</tr>' for r in trows[1:])
        result.append(f'<table class="ntbl">{hdr}{bdy}</table>')
    text='\n'.join(result); parts=[]
    for para in re.split(r'\n{2,}',text):
        para=para.strip()
        if not para: continue
        if para.startswith('<h') or para.startswith('<table'): parts.append(para)
        elif re.match(r'^[-*] ',para):
            items=re.split(r'\n[-*] ',para)
            items=[i.lstrip('-* ') for i in items if i.strip()]
            parts.append('<ul>'+''.join(f'<li>{i}</li>' for i in items)+'</ul>')
        else: parts.append(f'<p>{para.replace(chr(10)," ")}</p>')
    return '\n'.join(parts)

def _build_ticker_card(ticker:str, narrative:str, verdict:str) -> str:
    fg,bg,glow=_verdict_style(verdict)
    if not narrative: return ""

    def sub_sec(tag, label, icon="▸"):
        content=_extract_section(narrative, tag) or _extract_section(narrative, tag.replace("_"," "))
        # Also try partial match
        if not content:
            for line in narrative.split('\n'):
                if tag.replace('_',' ').upper() in line.upper() or tag in line.upper():
                    idx=narrative.find(line)
                    next_header=re.search(r'\n[A-Z][A-Z\s/—]+\n',narrative[idx+len(line):])
                    end=idx+len(line)+(next_header.start() if next_header else 2000)
                    content=narrative[idx+len(line):end].strip()
                    break
        if not content: return ""
        return f'<div class="sub-sec"><div class="sub-hdr">{icon} {label}</div><div class="sub-body">{_md_to_html(content)}</div></div>'

    # Extract key subsections from the narrative text directly
    sections_html = _md_to_html(narrative)

    return f"""<div class="ticker-card" id="card-{ticker}">
  <div class="card-header">
    <div class="card-left">
      <div class="ticker-name">{ticker}</div>
      <div class="card-sub">Dr. Magnus Vale + Soul of the Chart Analysis</div>
    </div>
    <div class="verdict-badge" style="color:{fg};background:{bg};border:1px solid {fg}44;box-shadow:0 0 20px {glow}">
      {verdict}
    </div>
  </div>
  <div class="card-body">
    <div class="narrative-content">{sections_html}</div>
  </div>
</div>"""

def _build_summary_bar(session_summary:str, session) -> str:
    s=session.summary()
    go_list=', '.join(s['go']) if s['go'] else '—'
    armed_list=', '.join(s['armed']) if s['armed'] else '—'
    wait_list=', '.join(s['wait']) if s['wait'] else '—'
    blocked_list=', '.join(s['blocked']) if s['blocked'] else '—'
    return f"""<div class="summary-bar">
  <div class="sum-item go"><div class="sum-lbl">GO</div><div class="sum-val">{len(s['go'])}</div><div class="sum-tickers">{go_list}</div></div>
  <div class="sum-item armed"><div class="sum-lbl">ARMED</div><div class="sum-val">{len(s['armed'])}</div><div class="sum-tickers">{armed_list}</div></div>
  <div class="sum-item wait"><div class="sum-lbl">WAIT / PROBE</div><div class="sum-val">{len(s['wait'])}</div><div class="sum-tickers">{wait_list}</div></div>
  <div class="sum-item blocked"><div class="sum-lbl">BLOCKED</div><div class="sum-val">{len(s['blocked'])}</div><div class="sum-tickers">{blocked_list}</div></div>
</div>"""

def build_html(response:str, session, ts:str, tickers:list=None) -> str:
    date_str=datetime.now().strftime("%A %d %B %Y")
    time_str=datetime.now().strftime("%H:%M ET")

    session_summary=_extract_section(response,"SESSION_SUMMARY")
    brief_csv_raw  =_extract_section(response,"TRADE_BRIEF_CSV")
    brief_rows     =_parse_csv(brief_csv_raw)

    # Update session verdicts
    for row in brief_rows:
        t=row.get("ticker","")
        v=row.get("final_verdict","WAIT")
        st=row.get("trade_state","WATCH")
        if t: session.add_verdict(t,v,st)

    sum_bar=_build_summary_bar(session_summary,session)

    # Build ticker nav
    detected_tickers=tickers or list(session.verdicts.keys())
    nav_html=""
    for t in detected_tickers:
        v=session.verdicts.get(t,{}).get("verdict","WAIT")
        fg,bg,_=_verdict_style(v)
        nav_html+=f'<a class="nav-ticker" href="#card-{t}" style="color:{fg};border-color:{fg}44">{t}<span class="nav-v">{v}</span></a>'

    # Build ticker cards
    cards_html=""
    if detected_tickers:
        for t in detected_tickers:
            narrative=_extract_ticker_narrative(response,t)
            if not narrative:
                # Try to find the ticker section in the full response
                idx=response.find(t)
                if idx>0:
                    narrative=response[idx:idx+4000]
            v=session.verdicts.get(t,{}).get("verdict","WAIT")
            cards_html+=_build_ticker_card(t,narrative,v)
    else:
        # No tickers detected — render full response
        cards_html=f'<div class="ticker-card"><div class="card-body"><div class="narrative-content">{_md_to_html(response)}</div></div></div>'

    # Build brief CSV table
    csv_table=""
    if brief_rows:
        cols=["ticker","direction","final_verdict","trade_state","trigger_level",
              "kill_switch_level","preferred_contract","dte","rr","capital_permission"]
        avail=[c for c in cols if c in (brief_rows[0].keys() if brief_rows else [])]
        hdr=''.join(f'<th>{c.replace("_"," ").title()}</th>' for c in avail)
        body=""
        for row in brief_rows:
            cells=""
            for col in avail:
                val=str(row.get(col,"")).strip()
                style=""
                if col=="ticker": style="font-weight:700;font-family:var(--mono);font-size:14px;color:#e2e8f0;"
                elif col=="final_verdict":
                    fg,bg,_=_verdict_style(val)
                    style=f"color:{fg};background:{bg};font-weight:700;font-family:var(--mono);font-size:11px;padding:2px 8px;border-radius:3px;"
                elif col=="capital_permission": style="font-size:10px;color:#ef4444;font-family:var(--mono);"
                elif col in("rr","dte"): style="font-family:var(--mono);color:#00d4aa;"
                cells+=f'<td style="{style}">{val}</td>'
            body+=f'<tr>{cells}</tr>'
        csv_table=f'<div style="overflow-x:auto"><table class="ntbl brief-tbl"><thead><tr>{hdr}</tr></thead><tbody>{body}</tbody></table></div>'

    return f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>AVSHUNTER Pipeline Interpreter — {date_str}</title>
<style>
@import url('https://fonts.googleapis.com/css2?family=Courier+Prime:wght@400;700&family=DM+Sans:wght@300;400;500;600&display=swap');
:root{{
  --bg:#060810;--bg2:#0b0d16;--bg3:#101420;--bg4:#161b28;
  --border:#1c2235;--border2:#252d42;
  --green:#00ff88;--amber:#f59e0b;--red:#ef4444;--blue:#3b82f6;--purple:#a855f7;--cyan:#00d4aa;
  --text:#dde4f0;--text2:#8895b0;--text3:#4a5568;
  --mono:'Courier Prime',monospace;--sans:'DM Sans',sans-serif;
}}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:var(--bg);color:var(--text);font-family:var(--sans);font-size:14px;line-height:1.75;min-height:100vh}}

/* HEADER */
.hdr{{
  background:linear-gradient(180deg,#0b0f1e 0%,#060810 100%);
  border-bottom:1px solid var(--border2);
  padding:28px 40px;display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:20px;
  position:relative;overflow:hidden;
}}
.hdr::before{{content:'';position:absolute;top:0;left:0;right:0;height:2px;
  background:linear-gradient(90deg,transparent,var(--cyan),var(--green),transparent);}}
.hdr-brand{{font-family:var(--mono);font-size:10px;color:var(--cyan);letter-spacing:.2em;text-transform:uppercase;margin-bottom:8px;}}
.hdr-title{{font-family:var(--mono);font-size:24px;font-weight:700;color:var(--text);letter-spacing:-.02em;}}
.hdr-title span{{color:var(--green);}}
.hdr-meta{{font-family:var(--mono);font-size:11px;color:var(--text3);margin-top:8px;line-height:1.8;}}
.hdr-right{{display:flex;flex-direction:column;align-items:flex-end;gap:10px;}}
.permission-tag{{
  font-family:var(--mono);font-size:10px;font-weight:700;letter-spacing:.08em;
  padding:6px 14px;border-radius:3px;
  background:#1a0000;color:#ff5555;border:1px solid #440000;
}}

/* BANNER */
.banner{{
  background:#0a0c14;border-bottom:1px solid #1c2235;
  padding:10px 40px;font-family:var(--mono);font-size:11px;
  color:#ef4444;letter-spacing:.1em;text-align:center;
  display:flex;justify-content:center;align-items:center;gap:12px;
}}

/* SUMMARY BAR */
.summary-bar{{
  display:flex;gap:1px;background:var(--border);
  border-bottom:1px solid var(--border2);
}}
.sum-item{{flex:1;padding:16px 20px;background:var(--bg2);}}
.sum-item.go .sum-val{{color:var(--green);}}
.sum-item.armed .sum-val{{color:var(--cyan);}}
.sum-item.wait .sum-val{{color:var(--amber);}}
.sum-item.blocked .sum-val{{color:var(--red);}}
.sum-lbl{{font-family:var(--mono);font-size:9px;color:var(--text3);letter-spacing:.15em;text-transform:uppercase;margin-bottom:4px;}}
.sum-val{{font-family:var(--mono);font-size:28px;font-weight:700;line-height:1;margin-bottom:4px;}}
.sum-tickers{{font-family:var(--mono);font-size:11px;color:var(--text2);}}

/* NAV */
.ticker-nav{{
  padding:16px 40px;background:var(--bg2);border-bottom:1px solid var(--border);
  display:flex;gap:8px;flex-wrap:wrap;align-items:center;
}}
.nav-label{{font-family:var(--mono);font-size:10px;color:var(--text3);letter-spacing:.12em;text-transform:uppercase;margin-right:8px;}}
.nav-ticker{{
  font-family:var(--mono);font-size:11px;font-weight:700;
  padding:5px 12px;border-radius:3px;border:1px solid;
  text-decoration:none;display:flex;align-items:center;gap:8px;
  transition:opacity .15s;background:transparent;
}}
.nav-ticker:hover{{opacity:.75;}}
.nav-v{{font-size:9px;opacity:.8;}}

/* CONTENT */
.content{{max-width:1280px;margin:0 auto;padding:32px 40px;}}

/* TICKER CARDS */
.ticker-card{{
  background:var(--bg2);border:1px solid var(--border2);
  border-radius:8px;margin-bottom:24px;overflow:hidden;
  position:relative;
}}
.ticker-card::before{{
  content:'';position:absolute;top:0;left:0;bottom:0;width:3px;
  background:var(--green);
}}
.card-header{{
  background:var(--bg3);border-bottom:1px solid var(--border);
  padding:18px 24px;display:flex;justify-content:space-between;align-items:center;
}}
.card-left{{}}
.ticker-name{{font-family:var(--mono);font-size:22px;font-weight:700;color:var(--text);letter-spacing:.05em;}}
.card-sub{{font-family:var(--mono);font-size:10px;color:var(--text3);letter-spacing:.12em;text-transform:uppercase;margin-top:4px;}}
.verdict-badge{{
  font-family:var(--mono);font-size:13px;font-weight:700;
  letter-spacing:.1em;padding:8px 20px;border-radius:4px;
}}
.card-body{{padding:24px;}}

/* NARRATIVE CONTENT */
.narrative-content p{{color:var(--text2);margin-bottom:12px;line-height:1.8;}}
.narrative-content h3{{
  font-family:var(--mono);font-size:11px;font-weight:700;color:var(--cyan);
  letter-spacing:.15em;text-transform:uppercase;
  margin:28px 0 12px;padding-bottom:8px;
  border-bottom:1px solid var(--border2);
}}
.narrative-content h4{{
  font-family:var(--mono);font-size:11px;color:var(--amber);
  letter-spacing:.1em;text-transform:uppercase;margin:18px 0 8px;
}}
.narrative-content strong{{color:var(--text);font-weight:600;}}
.narrative-content code{{
  font-family:var(--mono);font-size:12px;color:var(--green);
  background:#001a08;padding:2px 6px;border-radius:3px;
}}
.narrative-content ul{{margin:8px 0 14px 20px;color:var(--text2);}}
.narrative-content li{{margin-bottom:6px;line-height:1.7;}}
.ntbl{{width:100%;border-collapse:collapse;font-family:var(--mono);font-size:12px;margin:14px 0;}}
.ntbl th{{background:var(--bg4);color:var(--text3);padding:8px 14px;
  text-align:left;border:1px solid var(--border);font-size:10px;
  letter-spacing:.08em;text-transform:uppercase;}}
.ntbl td{{padding:8px 14px;border:1px solid var(--border);color:var(--text);vertical-align:top;}}
.ntbl tr:hover td{{background:var(--bg4);}}
.brief-tbl th,.brief-tbl td{{white-space:nowrap;}}

/* SESSION SUMMARY */
.session-card{{
  background:var(--bg2);border:1px solid var(--border2);
  border-radius:8px;margin-bottom:24px;overflow:hidden;
}}
.session-hdr{{
  background:linear-gradient(90deg,#0a1020,#0f1830);
  border-bottom:1px solid var(--border);padding:14px 24px;
  font-family:var(--mono);font-size:11px;font-weight:700;
  color:var(--cyan);letter-spacing:.12em;text-transform:uppercase;
}}
.session-body{{padding:24px;}}

/* BRIEF TABLE SECTION */
.brief-section{{
  background:var(--bg2);border:1px solid var(--border2);
  border-radius:8px;margin-bottom:24px;overflow:hidden;
}}
.brief-hdr{{
  background:var(--bg3);border-bottom:1px solid var(--border);
  padding:14px 24px;font-family:var(--mono);font-size:11px;font-weight:700;
  color:var(--amber);letter-spacing:.12em;text-transform:uppercase;
}}
.brief-body{{padding:20px 24px;overflow-x:auto;}}

/* FOOTER */
.footer{{
  border-top:1px solid var(--border);padding:16px 40px;
  background:var(--bg2);margin-top:8px;
  display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px;
}}
.ftr-l{{font-family:var(--mono);font-size:10px;color:#ff5555;font-weight:700;}}
.ftr-r{{font-family:var(--mono);font-size:10px;color:var(--text3);}}
</style></head><body>

<div class="hdr">
  <div>
    <div class="hdr-brand">AVSHUNTER Intelligence Layer</div>
    <div class="hdr-title">Pipeline <span>Interpreter</span></div>
    <div class="hdr-title" style="font-size:13px;color:var(--text2);margin-top:4px;">Dr. Magnus Vale + Soul of the Chart</div>
    <div class="hdr-meta">{date_str} &nbsp;|&nbsp; {time_str} &nbsp;|&nbsp; Run: {ts}</div>
  </div>
  <div class="hdr-right">
    <div class="permission-tag">⚠ {EXECUTION_PERMISSION}</div>
    <div class="permission-tag" style="color:#f59e0b;background:#1a1200;border-color:#44330099;">{CAPITAL_PERMISSION}</div>
  </div>
</div>
<div class="banner">
  ⚠ &nbsp; THE MACHINE DISCOVERS — THE NARRATIVE DIAGNOSES — THE MARKET PERMITS — THE TRADER EXECUTES
  &nbsp; | &nbsp; NO EXECUTION PERMISSION IS GRANTED BY THIS DOCUMENT
</div>
{sum_bar}
<div class="ticker-nav">
  <span class="nav-label">Jump to:</span>
  {nav_html if nav_html else '<span style="color:var(--text3);font-family:var(--mono);font-size:11px;">No tickers detected</span>'}
</div>
<div class="content">

  <div class="session-card">
    <div class="session-hdr">◈ Session Summary & Full Picture</div>
    <div class="session-body narrative-content">{_md_to_html(session_summary) if session_summary else _md_to_html(response[:3000])}</div>
  </div>

  {cards_html}

  {'<div class="brief-section"><div class="brief-hdr">◈ Trade Brief — All Candidates</div><div class="brief-body">'+csv_table+'</div></div>' if csv_table else ''}

</div>
<div class="footer">
  <div class="ftr-l">⚠ {EXECUTION_PERMISSION} &nbsp;|&nbsp; {CAPITAL_PERMISSION}</div>
  <div class="ftr-r">AVSHUNTER Pipeline Interpreter v1.0 &nbsp;|&nbsp; Generated {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</div>
</div>
</body></html>"""


# ── TRIAGE OUTPUT FUNCTIONS ───────────────────────────────────────────────────
TRIAGE_CSV_FIELDS = [
    "ticker","direction","score","dte","horizon","earnings_in_window",
    "earnings_date","ma_ready","triage_verdict","triage_rank","urgency_flag",
    "catalyst_freshness","trigger_proximity","why","upgrade_condition",
    "execution_permission"
]

def _parse_triage_csv(text:str) -> list:
    if not text.strip(): return []
    try:
        clean = _clean_csv(text)
        return list(csv.DictReader(io.StringIO(clean)))
    except Exception as e:
        print(f"  ⚠ Triage CSV parse: {e}"); return []

def _triage_verdict_style(v:str) -> tuple:
    styles = {
        "DEEP_DIVE_NOW":  ("#00ff88","#003300","#00ff8844"),
        "DEEP_DIVE_NEXT": ("#00d4aa","#002a22","#00d4aa44"),
        "REVIEW_LATER":   ("#f59e0b","#1a1200","#f59e0b44"),
        "WATCH_ONLY":     ("#64748b","#0f1520","#64748b44"),
        "SKIP_TODAY":     ("#334155","#0a0a0a","#33415544"),
    }
    return styles.get(v, ("#64748b","#0f1520","#64748b44"))

def build_triage_html(response:str, ts:str,
                       lab_reconciliation:dict=None, lab_filename:str="",
                       run_id_check:dict=None, lab_rows:list=None) -> str:
    date_str = datetime.now().strftime("%A %d %B %Y")
    time_str = datetime.now().strftime("%H:%M ET")

    ranked_raw  = _extract_section(response, "TRIAGE_RANKED_TABLE")
    summary_raw = _extract_section(response, "TRIAGE_SUMMARY")
    order_raw   = _extract_section(response, "TRIAGE_EXECUTION_ORDER")

    ranked_rows = _parse_triage_csv(ranked_raw)

    # ── LAB_ALIGNMENT card (Component 9) ─────────────────────────────────────
    _confirmed_set   = set(t.upper() for t in (lab_reconciliation or {}).get("confirmed",   []))
    _interp_only_set = set(t.upper() for t in (lab_reconciliation or {}).get("interp_only", []))
    _lab_only_set    = set(t.upper() for t in (lab_reconciliation or {}).get("lab_only",    []))

    def _lab_badge(text, fg, bg):
        return (f'<span style="font-family:var(--mono);font-size:11px;font-weight:700;'
                f'padding:3px 10px;border-radius:3px;color:{fg};background:{bg};'
                f'border:1px solid {fg}44;display:inline-block">{text}</span>')

    if lab_reconciliation is None:
        # No lab file loaded this session
        _lab_card_html = f"""<div class="t-section" style="margin-bottom:20px">
          <div class="t-hdr">◈ Intelligence Lab Reconciliation</div>
          <div class="t-body">
            <div style="display:flex;align-items:center;gap:14px;padding:8px 0">
              {_lab_badge("LAB_NOT_LOADED", "#64748b", "#0f1520")}
              <span style="color:var(--text3);font-size:12px">
                No lab export found — place <code style="color:var(--cyan)">avshunter_signals_*.csv</code>
                in <code style="color:var(--cyan)">MA_Inputs/lab_export/</code> and run /lab or /triage
              </span>
            </div>
          </div>
        </div>"""
    else:
        confirmed_n   = lab_reconciliation.get("confirmed_count",   0)
        lab_only_n    = lab_reconciliation.get("lab_only_count",    0)
        interp_only_n = lab_reconciliation.get("interp_only_count", 0)
        interp_list   = lab_reconciliation.get("interp_only", [])
        _fn = lab_filename or "lab export"

        # Run_ID mismatch banner
        _stale_banner = ""
        if run_id_check and not run_id_check.get("match", True):
            _stale_banner = (
                f'<div style="background:#1a1200;border:1px solid #f59e0b44;border-radius:4px;'
                f'padding:7px 14px;margin-bottom:12px;font-family:var(--mono);font-size:11px;'
                f'color:#f59e0b">'
                f'&#9888; STALE_LAB_DATA — Lab Run_ID <strong>{run_id_check.get("lab_run_id","?")}</strong>'
                f' does not match pipeline Run_ID <strong>{run_id_check.get("pipeline_run_id","?")}</strong>'
                f' — lab export may be from a different session'
                f'</div>'
            )

        # Interp-only ticker list
        _interp_list_html = ""
        if interp_list:
            _interp_list_html = (
                '&nbsp; <span style="font-size:11px;color:#ef4444;font-family:var(--mono)">'
                + " &middot; ".join(interp_list[:30])
                + ("…" if len(interp_list) > 30 else "")
                + '</span>'
            )

        _lab_card_html = f"""<div class="t-section" style="margin-bottom:20px">
          <div class="t-hdr">◈ Intelligence Lab Reconciliation — {_fn}</div>
          <div class="t-body">
            {_stale_banner}
            <div style="display:grid;gap:10px">
              <div style="display:flex;align-items:center;gap:14px">
                {_lab_badge("CONFIRMED", "#00ff88", "#003300")}
                <span style="color:var(--text2);font-size:13px">
                  <strong style="color:var(--green)">{confirmed_n}</strong>
                  tickers validated in both Lab and Interpreter — no action required
                </span>
              </div>
              <div style="display:flex;align-items:center;gap:14px">
                {_lab_badge("LAB ONLY", "#f59e0b", "#1a1200")}
                <span style="color:var(--text2);font-size:13px">
                  <strong style="color:#f59e0b">{lab_only_n}</strong>
                  tickers ranked by Lab but not surfaced by Interpreter — manual review
                </span>
              </div>
              <div style="display:flex;align-items:center;gap:14px;flex-wrap:wrap">
                {_lab_badge("LAB_NOT_CONFIRMED", "#ef4444", "#1a0000")}
                <span style="color:var(--text2);font-size:13px">
                  <strong style="color:#ef4444">{interp_only_n}</strong>
                  tickers in Interpreter not in Lab — REVIEW REQUIRED
                </span>
                {_interp_list_html}
              </div>
            </div>
          </div>
        </div>"""

    def _lab_status_for(ticker_upper):
        """Return (label, fg, bg) for the LAB STATUS cell."""
        if lab_reconciliation is None:
            return ("LAB_NOT_LOADED", "#4a5568", "#0f1520")
        if ticker_upper in _interp_only_set:
            return ("LAB_NOT_CONFIRMED", "#ef4444", "#1a0000")
        if ticker_upper in _confirmed_set:
            # Check field conflicts if lab_rows provided
            if lab_rows:
                try:
                    from lab_reconciliation import get_lab_row, validate_lab_field_alignment
                    _lr = get_lab_row(lab_rows, ticker_upper)
                    if _lr:
                        _conflicts = validate_lab_field_alignment(_lr, {}, ticker_upper)
                        if _conflicts:
                            return ("CONFIRMED_CONFLICTS", "#f59e0b", "#1a1200")
                except Exception:
                    pass
            return ("CONFIRMED", "#00ff88", "#003300")
        return ("LAB_NOT_LOADED", "#4a5568", "#0f1520")

    # Build ranked table
    triage_table = ""
    if ranked_rows:
        # Sort by sector alphabetically, then by scs_score descending within sector
        def _triage_sort_key(row):
            sec = (row.get("gics_sector") or row.get("sector_name") or
                   row.get("sector") or row.get("gics_sector_name") or "UNKNOWN").upper()
            try:
                scs = -float(row.get("scs_score") or row.get("priority_score") or row.get("composite") or 0)
            except (TypeError, ValueError):
                scs = 0.0
            return (sec, scs)
        sorted_rows = sorted(ranked_rows, key=_triage_sort_key)

        rows_html = ""
        _cur_sector = None
        _total_cols = 13
        for row in sorted_rows:
            sector_raw = (
                str(row.get("gics_sector","") or row.get("sector_name","") or
                    row.get("sector","") or row.get("gics_sector_name","")).strip()
            )
            sector_display = sector_raw if sector_raw else "UNKNOWN"
            sector_key = sector_display.upper()
            if sector_key != _cur_sector:
                _cur_sector = sector_key
                rows_html += (
                    f'<tr><td colspan="{_total_cols}" style="background:#1a1a2e;color:#7ec8e3;'
                    f'font-weight:bold;padding:6px 10px;letter-spacing:0.05em;'
                    f'font-family:var(--mono);font-size:11px">{sector_display} (sector group)</td></tr>'
                )

            v   = str(row.get("triage_verdict","")).strip()
            fg, bg, glow = _triage_verdict_style(v)
            rank = str(row.get("rank","")).strip()
            ticker = str(row.get("ticker","")).strip()
            direction = str(row.get("direction","")).strip()
            score = str(row.get("pipeline_score","")).strip()
            dte   = str(row.get("dte","")).strip()
            horizon = str(row.get("horizon","")).strip()
            earnings = str(row.get("earnings_flag","")).strip()
            ready = str(row.get("ma_inputs_ready","")).strip()
            reason = str(row.get("triage_reason","")).strip()

            pipeline_verdict = str(
                row.get("verdict","") or row.get("execution_permission","") or
                row.get("morning_execution_permission","")
            ).strip()
            pv_upper = pipeline_verdict.upper()
            if pv_upper == "GO":
                vd_style = "background:#1a4a1a;color:white;font-weight:bold"
            elif pv_upper == "FLAG":
                vd_style = "background:#4a3a00;color:#ffcc00;font-weight:bold"
            elif pv_upper == "BLOCK":
                vd_style = "background:#4a0000;color:#ff6666;font-weight:bold"
            else:
                vd_style = "color:#64748b"

            dir_col = "#00c853" if "CALL" in direction else ("#ef4444" if "PUT" in direction else "#64748b")
            earn_col = "#ef4444" if earnings in ("TODAY","IN_WINDOW") else "#64748b"
            ready_col = "#00c853" if ready=="YES" else ("#f59e0b" if ready=="PARTIAL" else "#ef4444")

            try:
                score_n = float(score)
                score_col = "#00c853" if score_n>=80 else ("#f59e0b" if score_n>=65 else "#ef4444")
            except: score_col = "#64748b"

            _ls_label, _ls_fg, _ls_bg = _lab_status_for(ticker.upper())
            rows_html += f'''<tr>
              <td style="font-family:var(--mono);color:#64748b;text-align:center">{rank}</td>
              <td style="font-family:var(--mono);font-weight:700;font-size:15px;color:#e2e8f0">{ticker}</td>
              <td style="font-family:var(--mono);font-size:11px;color:#94a3b8;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">{sector_display if sector_raw else '&mdash;'}</td>
              <td style="color:{dir_col};font-weight:600;font-size:12px">{direction}</td>
              <td style="color:{score_col};font-family:var(--mono);font-weight:700;text-align:center">{score}</td>
              <td style="font-family:var(--mono);font-size:11px;padding:4px 8px;{vd_style}">{pipeline_verdict or '&mdash;'}</td>
              <td style="font-family:var(--mono);color:#94a3b8;text-align:center">{dte}d</td>
              <td style="font-family:var(--mono);font-size:11px;color:#64748b">{horizon}</td>
              <td style="color:{earn_col};font-family:var(--mono);font-size:11px">{earnings}</td>
              <td style="color:{ready_col};font-family:var(--mono);font-size:11px;text-align:center">{ready}</td>
              <td><span style="font-family:var(--mono);font-size:11px;font-weight:700;padding:3px 10px;border-radius:3px;color:{fg};background:{bg};border:1px solid {fg}44">{v}</span></td>
              <td><span style="font-family:var(--mono);font-size:10px;font-weight:700;padding:2px 8px;border-radius:3px;color:{_ls_fg};background:{_ls_bg};border:1px solid {_ls_fg}44;white-space:nowrap">{_ls_label}</span></td>
              <td style="font-size:12px;color:#94a3b8;max-width:260px">{reason}</td>
            </tr>'''

        triage_table = f'''<div class="t-section">
          <div class="t-hdr">◈ Priority Ranking — All Candidates</div>
          <div class="t-body" style="overflow-x:auto">
            <table class="t-tbl">
              <thead><tr>
                <th>#</th><th>Ticker</th><th>Sector</th><th>Direction</th><th>Score</th>
                <th>Verdict</th><th>DTE</th><th>Horizon</th><th>Earnings</th>
                <th>Data Ready</th><th>Triage Verdict</th><th>Lab Status</th><th>Why</th>
              </tr></thead>
              <tbody>{rows_html}</tbody>
            </table>
          </div>
        </div>'''

    # Build execution order section
    order_html = ""
    if order_raw:
        order_html = f"""<div class="t-section" style="border-left:3px solid #00ff88">
          <div class="t-hdr" style="color:#00ff88">▶ Today's Execution Order</div>
          <div class="t-body narrative-content">{_md_to_html(order_raw)}</div>
        </div>"""

    # Build summary groups from ranked rows
    groups = {"DEEP_DIVE_NOW":[],"DEEP_DIVE_NEXT":[],"REVIEW_LATER":[],"WATCH_ONLY":[],"SKIP_TODAY":[]}
    for row in ranked_rows:
        v = str(row.get("triage_verdict","")).strip()
        t = str(row.get("ticker","")).strip()
        if v in groups and t: groups[v].append(t)

    groups_html = ""
    group_labels = [
        ("DEEP_DIVE_NOW",  "#00ff88", "Deep Dive Now"),
        ("DEEP_DIVE_NEXT", "#00d4aa", "Deep Dive Next"),
        ("REVIEW_LATER",   "#f59e0b", "Review Later"),
        ("WATCH_ONLY",     "#64748b", "Watch Only"),
        ("SKIP_TODAY",     "#334155", "Skip Today"),
    ]
    for key, color, label in group_labels:
        tickers = groups.get(key, [])
        if tickers:
            ticker_badges = "".join(
                f'<span style="font-family:var(--mono);font-size:12px;font-weight:700;'
                f'padding:4px 12px;border-radius:3px;margin:3px;display:inline-block;'
                f'color:{color};background:{color}22;border:1px solid {color}44">{t}</span>'
                for t in tickers
            )
            groups_html += f"""<div class="group-row">
              <div class="group-lbl" style="color:{color}">{label}</div>
              <div class="group-tickers">{ticker_badges}</div>
            </div>"""

    return f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>AVSHUNTER Triage — {date_str}</title>
<style>
@import url('https://fonts.googleapis.com/css2?family=Courier+Prime:wght@400;700&family=DM+Sans:wght@300;400;500;600&display=swap');
:root{{
  --bg:#060810;--bg2:#0b0d16;--bg3:#101420;--bg4:#161b28;
  --border:#1c2235;--border2:#252d42;
  --green:#00ff88;--cyan:#00d4aa;--amber:#f59e0b;--red:#ef4444;
  --text:#dde4f0;--text2:#8895b0;--text3:#4a5568;
  --mono:'Courier Prime',monospace;--sans:'DM Sans',sans-serif;
}}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:var(--bg);color:var(--text);font-family:var(--sans);font-size:14px;line-height:1.75}}
.hdr{{background:var(--bg2);border-bottom:2px solid var(--green);padding:24px 36px;
  display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:16px;
  position:relative;overflow:hidden;}}
.hdr::before{{content:'';position:absolute;top:0;left:0;right:0;height:2px;
  background:linear-gradient(90deg,transparent,var(--green),var(--cyan),transparent);}}
.hdr-brand{{font-family:var(--mono);font-size:10px;color:var(--green);letter-spacing:.2em;text-transform:uppercase;margin-bottom:6px}}
.hdr-title{{font-family:var(--mono);font-size:24px;font-weight:700;color:var(--text)}}
.hdr-title span{{color:var(--green)}}
.hdr-meta{{font-family:var(--mono);font-size:11px;color:var(--text3);margin-top:6px}}
.hdr-tag{{font-family:var(--mono);font-size:10px;font-weight:700;padding:6px 14px;
  border-radius:3px;background:#1a0000;color:#ff5555;border:1px solid #440000;}}
.banner{{background:#020b04;border-bottom:1px solid #0a3018;padding:8px 36px;
  font-family:var(--mono);font-size:11px;color:var(--green);letter-spacing:.1em;text-align:center}}
.content{{max-width:1320px;margin:0 auto;padding:24px 36px}}
.t-section{{background:var(--bg2);border:1px solid var(--border2);border-radius:6px;
  margin-bottom:20px;overflow:hidden}}
.t-hdr{{background:var(--bg3);border-bottom:1px solid var(--border);padding:12px 20px;
  font-family:var(--mono);font-size:11px;font-weight:700;color:var(--cyan);
  letter-spacing:.12em;text-transform:uppercase}}
.t-body{{padding:20px 24px}}
.t-tbl{{width:100%;border-collapse:collapse;font-size:13px}}
.t-tbl th{{background:var(--bg4);color:var(--text3);padding:9px 14px;text-align:left;
  border:1px solid var(--border);font-family:var(--mono);font-size:10px;
  letter-spacing:.08em;text-transform:uppercase;white-space:nowrap}}
.t-tbl td{{padding:9px 14px;border:1px solid var(--border);vertical-align:middle}}
.t-tbl tr:hover td{{background:var(--bg3)}}
.groups{{background:var(--bg2);border:1px solid var(--border2);border-radius:6px;
  padding:20px 24px;margin-bottom:20px}}
.group-row{{display:flex;align-items:center;gap:16px;padding:10px 0;
  border-bottom:1px solid var(--border);}}
.group-row:last-child{{border-bottom:none}}
.group-lbl{{font-family:var(--mono);font-size:11px;font-weight:700;
  letter-spacing:.1em;min-width:140px;text-transform:uppercase}}
.group-tickers{{display:flex;flex-wrap:wrap;gap:4px}}
.narrative-content p{{color:var(--text2);margin-bottom:10px}}
.narrative-content h3,.narrative-content h4{{font-family:var(--mono);color:var(--cyan);
  margin:14px 0 8px;font-size:11px;letter-spacing:.1em;text-transform:uppercase}}
.narrative-content ul{{margin:6px 0 10px 18px;color:var(--text2)}}
.narrative-content li{{margin-bottom:4px}}
.narrative-content strong{{color:var(--text)}}
.footer{{border-top:1px solid var(--border);padding:14px 36px;background:var(--bg2);
  display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px;margin-top:8px}}
.ftr-l{{font-family:var(--mono);font-size:10px;color:#ff5555;font-weight:700}}
.ftr-r{{font-family:var(--mono);font-size:10px;color:var(--text3)}}
</style></head><body>
<div class="hdr">
  <div>
    <div class="hdr-brand">AVSHUNTER Pipeline Interpreter</div>
    <div class="hdr-title">Triage <span>Priority Scan</span></div>
    <div class="hdr-meta">{date_str} &nbsp;|&nbsp; {time_str} &nbsp;|&nbsp; Run: {ts}</div>
  </div>
  <div class="hdr-tag">⚠ NONE_PIPELINE_INTERPRETER_ONLY</div>
</div>
<div class="banner">
  STAGE 1: TRIAGE &nbsp;→&nbsp; STAGE 2: DEEP DIVE (one ticker at a time)
  &nbsp;|&nbsp; SELECT FROM THIS LIST BEFORE RUNNING /ticker
</div>
<div class="content">
  {_lab_card_html}
  <div class="groups">
    <div class="t-hdr" style="background:transparent;border:none;padding:0 0 12px 0">
      ◈ Priority Groups
    </div>
    {groups_html if groups_html else "<p style='color:var(--text3)'>No candidates ranked.</p>"}
  </div>
  {triage_table}
  {order_html}
  {'<div class="t-section"><div class="t-hdr">◈ Session Picture</div><div class="t-body narrative-content">' + _md_to_html(summary_raw) + '</div></div>' if summary_raw else ""}
</div>
<div class="footer">
  <div class="ftr-l">⚠ NONE_PIPELINE_INTERPRETER_ONLY | CAPITAL_DENIED_PENDING_LIVE_CONFIRMATION</div>
  <div class="ftr-r">AVSHUNTER Pipeline Interpreter v1.0 — Triage | {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</div>
</div>
</body></html>"""

def write_triage_outputs(response:str, run_dir:Path, ts:str,
                          lab_reconciliation:dict=None, lab_filename:str="",
                          run_id_check:dict=None, lab_rows:list=None) -> dict:
    results = {}

    # Raw response
    (run_dir / f"raw_triage_{ts}.txt").write_text(response, encoding="utf-8")

    # Parse triage CSV
    ranked_raw  = _extract_section(response, "TRIAGE_RANKED_TABLE")
    ranked_rows = _parse_triage_csv(ranked_raw)

    # Write triage CSV
    cp = run_dir / f"triage_{ts}.csv"
    if ranked_rows:
        cp.parent.mkdir(parents=True, exist_ok=True)
        with open(cp, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=TRIAGE_CSV_FIELDS, extrasaction="ignore")
            w.writeheader()
            w.writerows(ranked_rows)
        results["triage_csv"] = {"path": cp, "rows": len(ranked_rows)}
    else:
        print(f"  ⚠ No triage rows parsed — check raw_triage_{ts}.txt")
        results["triage_csv"] = {"path": cp, "rows": 0}

    # Write triage HTML — pass lab data for LAB_ALIGNMENT card and LAB STATUS column
    html = build_triage_html(response, ts,
                              lab_reconciliation=lab_reconciliation,
                              lab_filename=lab_filename,
                              run_id_check=run_id_check,
                              lab_rows=lab_rows)
    hp = run_dir / f"triage_{ts}.html"
    hp.write_text(html, encoding="utf-8")
    results["triage_html"] = {"path": hp}

    return results


def write_all_outputs(response: str, session, run_dir, ts: str,
                      tickers: list = None, prefix: str = "") -> dict:
    """
    Master output writer — called by /interpret, /ticker, /morning, /chart commands.
    Writes: raw response, brief CSV, HTML narrative.
    Returns dict of results.
    """
    from pathlib import Path
    results = {}
    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    pfx = f"{prefix}_" if prefix else ""

    # Save raw response for debugging
    raw_path = run_dir / f"raw_response_{ts}.txt"
    raw_path.write_text(response, encoding="utf-8")

    # Parse brief CSV from response
    brief_raw = _extract_section(response, "TRADE_BRIEF_CSV")
    brief_rows = _parse_csv(brief_raw) if brief_raw else []

    # Update session verdicts from CSV
    for row in brief_rows:
        t = row.get("ticker", "")
        v = row.get("final_verdict", "WAIT")
        st = row.get("trade_state", "WATCH")
        if t and hasattr(session, "add_verdict"):
            session.add_verdict(t, v, st)

    session.last_ticker_csv = brief_rows

    # Write brief CSV
    BRIEF_FIELDS = [
        "ticker", "direction", "final_verdict", "trade_state", "horizon", "dte",
        "trigger_level", "kill_switch_level", "preferred_contract", "premium", "rr",
        "iv_context", "ivp", "earnings_in_window", "earnings_action",
        "max_pain_risk", "sector_confirmation_required", "first_hour_rule",
        "probe_permitted", "initial_adverse_tolerance", "capital_permission",
        "narrative_summary", "execution_permission"
    ]
    bp = run_dir / f"{pfx}trade_brief_{ts}.csv"
    n = _write_csv(brief_rows, bp, BRIEF_FIELDS)
    results["brief_csv"] = {"path": bp, "rows": n}
    if n == 0:
        print(f"  ⚠ No brief CSV rows — check raw_response_{ts}.txt")

    # Build and write HTML narrative
    try:
        html = build_html(response, session, ts, tickers=tickers)
        hp = run_dir / f"{pfx}interpreter_{ts}.html"
        hp.write_text(html, encoding="utf-8")
        results["html"] = {"path": hp}
    except Exception as e:
        print(f"  ⚠ HTML build error: {e}")

    return results


# ── STORY OF THE TRADE — additions only, appended at bottom ──────────────────

# Badge colour map for the 8 story sections
_STORY_BADGE_STYLES: dict = {
    # Section 1 — Macro
    "HEADWIND":         ("#f59e0b", "#1a1200"),
    "TAILWIND":         ("#00ff88", "#003300"),
    # Section 2 — Gamma
    "AMPLIFYING":       ("#3b82f6", "#071524"),
    "DAMPENING":        ("#8895b0", "#0f1520"),
    # Section 4 — Thesis
    "ARMED":            ("#00ff88", "#003300"),
    "GO":               ("#00ff88", "#003300"),
    "PROBE":            ("#3b82f6", "#071524"),
    "WAIT":             ("#f59e0b", "#1a1200"),
    # Section 5 — Chart
    "CONFIRMED":        ("#00ff88", "#003300"),
    "FORMING":          ("#f59e0b", "#1a1200"),
    "UNDER PRESSURE":   ("#ef4444", "#1a0000"),
    "REJECTED":         ("#ef4444", "#1a0000"),
    # Section 6 — Options
    "CONFIRMS":         ("#00ff88", "#003300"),
    "CONFLICTS":        ("#ef4444", "#1a0000"),
    # Section 7 — Risk
    "LOW":              ("#00ff88", "#003300"),
    "MODERATE":         ("#f59e0b", "#1a1200"),
    "HIGH":             ("#ef4444", "#1a0000"),
    "EXTREME":          ("#ef4444", "#1a0000"),
    # Section 8 — Verdict
    "DO NOT ENTER":     ("#f59e0b", "#1a1200"),
    "WATCH":            ("#8895b0", "#0f1520"),
    "ENTER":            ("#00ff88", "#003300"),
    "EXIT":             ("#ef4444", "#1a0000"),
    # Fallback / neutral
    "NEUTRAL":          ("#8895b0", "#0f1520"),
}

_SECTION_LABELS: list = [
    ("SECTION_1_MACRO",      "1", "Macro — the weather conditions"),
    ("SECTION_2_GAMMA",      "2", "Market Makers &amp; Gamma — the battlefield"),
    ("SECTION_3_LIQUIDITY",  "3", "Liquidity Zones — the tripwires"),
    ("SECTION_4_THESIS",     "4", "Thesis — the plan"),
    ("SECTION_5_CHART",      "5", "Chart — live confirmation status"),
    ("SECTION_6_OPTIONS",    "6", "Options Flow — institutional vote"),
    ("SECTION_7_RISK",       "7", "Risk — the honest scorecard"),
    ("SECTION_8_VERDICT",    "8", "Verdict — what to do right now"),
]


def _extract_junior_section(response: str, section_tag: str, ticker: str) -> str:
    """
    Extract a single [SECTION_N_X] block from inside a [JUNIOR_BRIEFING_{TICKER}] block.
    Falls back to a global search if the briefing wrapper isn't found.
    """
    briefing_match = re.search(
        rf'\[JUNIOR_BRIEFING_{re.escape(ticker.upper())}\](.*?)(?=\[JUNIOR_BRIEFING_|\Z)',
        response, re.DOTALL | re.IGNORECASE
    )
    search_text = briefing_match.group(1) if briefing_match else response

    m = re.search(
        rf'\[{re.escape(section_tag)}\](.*?)(?=\[SECTION_\d|\Z)',
        search_text, re.DOTALL | re.IGNORECASE
    )
    return m.group(1).strip() if m else ""


def _extract_status(section_text: str) -> str:
    """Extract STATUS: value from a section block."""
    m = re.search(r'STATUS:\s*(.+)', section_text, re.IGNORECASE)
    return m.group(1).strip().upper() if m else "NEUTRAL"


def _story_badge_html(status: str) -> str:
    fg, bg = _STORY_BADGE_STYLES.get(status, ("#8895b0", "#0f1520"))
    return (
        f'<span style="display:inline-block;padding:3px 12px;border-radius:4px;'
        f'font-family:var(--mono,monospace);font-size:12px;font-weight:700;'
        f'letter-spacing:1px;color:{fg};background:{bg};border:1px solid {fg}44">'
        f'{status}</span>'
    )


def render_state_chain(state_chain: list) -> str:
    """
    Render a horizontal timeline of all thesis state nodes.
    Each node is clickable and links to the story file from that timestamp.
    Called at the top of every story HTML.
    """
    if not state_chain:
        return '<div class="state-chain"><em style="color:#4a5568">No prior states — first run.</em></div>'

    nodes_html = ""
    for i, node in enumerate(state_chain):
        ts       = node.get("ts", "")
        verdict  = node.get("verdict", "—")
        path     = node.get("story_path", "")
        is_last  = (i == len(state_chain) - 1)
        fg, bg   = _STORY_BADGE_STYLES.get(verdict, ("#8895b0", "#0f1520"))
        label    = f'<a href="{path}" style="color:{fg};text-decoration:none">{ts}</a>' if path else ts
        border   = f"2px solid {fg}" if is_last else f"1px solid {fg}44"
        nodes_html += (
            f'<div style="display:inline-block;padding:6px 14px;border-radius:6px;'
            f'background:{bg};border:{border};margin:0 4px;text-align:center">'
            f'<div style="font-family:var(--mono,monospace);font-size:10px;color:{fg};'
            f'font-weight:700">{verdict}</div>'
            f'<div style="font-size:10px;color:#8895b0;margin-top:2px">{label}</div>'
            f'</div>'
        )
        if not is_last:
            nodes_html += '<span style="color:#4a5568;font-size:18px;vertical-align:middle">&#8594;</span>'

    return (
        f'<div class="state-chain" style="overflow-x:auto;white-space:nowrap;'
        f'padding:12px 0;border-bottom:1px solid #1c2235;margin-bottom:18px">'
        f'<div style="font-size:11px;color:#4a5568;font-family:var(--mono,monospace);'
        f'margin-bottom:8px">THESIS STATE CHAIN</div>'
        f'{nodes_html}'
        f'</div>'
    )


def build_story_html(
    response: str,
    ticker: str,
    ts: str,
    thesis_id: str = "",
    update_type: str = "FULL",
    state_chain: list = None,
    previous_ts: str = "",
) -> str:
    """
    Build the Story of the Trade HTML document.
    Uses the same dark palette as the existing interpreter HTML.
    Eight section cards with status badges, plain-English content, and INTERDEP footers.
    """
    date_str = datetime.now().strftime("%A %d %B %Y")
    time_str = datetime.now().strftime("%H:%M ET")

    # Update banner (only for non-FULL runs)
    update_banner = ""
    if update_type != "FULL" and previous_ts:
        _banner_labels = {
            "CHART_UPDATE":   ("Chart updated", "Sections 5 + 8 regenerated", "#3b82f6"),
            "OPTIONS_UPDATE": ("Options updated", "Sections 6 + 8 regenerated", "#a855f7"),
            "MACRO_UPDATE":   ("Macro shift detected", "Sections 1 + 8 regenerated", "#f59e0b"),
            "OVERNIGHT":      ("Overnight carry-forward", "Sections 1, 5 + 8 regenerated", "#00d4aa"),
        }
        title, subtitle, colour = _banner_labels.get(
            update_type, (update_type, "Partial regeneration", "#8895b0")
        )
        update_banner = (
            f'<div style="background:{colour}18;border:1px solid {colour}44;'
            f'border-radius:6px;padding:10px 16px;margin:0 0 18px 0;'
            f'font-family:var(--mono,monospace);font-size:12px">'
            f'<strong style="color:{colour}">{title}</strong>'
            f'<span style="color:#8895b0;margin-left:12px">{subtitle} — '
            f'based on previous story from {previous_ts}</span>'
            f'</div>'
        )

    # Progress pill bar
    pill_bar = '<div style="display:flex;gap:6px;flex-wrap:wrap;margin:0 0 20px 0">'
    for tag, num, label in _SECTION_LABELS:
        pill_bar += (
            f'<a href="#{tag}" style="text-decoration:none;padding:5px 12px;border-radius:20px;'
            f'background:#101420;border:1px solid #1c2235;font-size:11px;color:#8895b0;'
            f'font-family:var(--mono,monospace)">{num} {label.split("—")[0].strip()}</a>'
        )
    pill_bar += '</div>'

    # Build the eight section cards
    section_cards = ""
    for tag, num, label in _SECTION_LABELS:
        content = _extract_junior_section(response, tag, ticker)
        if not content:
            content = f"Section not found in API response. Check raw_response_{ts}.txt"

        status = _extract_status(content)
        badge  = _story_badge_html(status)

        # Separate INTERDEP line for styled footer
        interdep_match = re.search(r'INTERDEP:\s*(.+?)(?:\n|$)', content, re.IGNORECASE | re.DOTALL)
        interdep_html  = ""
        if interdep_match:
            interdep_text = interdep_match.group(1).strip()
            content = content[:interdep_match.start()].strip()
            interdep_html = (
                f'<div style="border-top:1px solid #1c2235;margin-top:16px;padding-top:10px;'
                f'font-size:11px;color:#4a5568;font-family:var(--mono,monospace)">'
                f'INTERDEP: {interdep_text}'
                f'</div>'
            )

        carried = "[CARRIED_FORWARD_FROM:" in content
        carried_banner = ""
        if carried:
            m_cf = re.search(r'\[CARRIED_FORWARD_FROM:\s*([^\]]+)\]', content)
            cf_ts = m_cf.group(1).strip() if m_cf else "previous session"
            carried_banner = (
                f'<div style="font-size:10px;color:#f59e0b;font-family:var(--mono,monospace);'
                f'margin-bottom:8px">&#8635; CARRIED FORWARD FROM {cf_ts}</div>'
            )
            content = re.sub(r'\[CARRIED_FORWARD_FROM:[^\]]*\]', '', content).strip()

        section_cards += (
            f'<div id="{tag}" style="background:#0b0d16;border:1px solid #1c2235;'
            f'border-radius:8px;margin-bottom:16px;overflow:hidden">'
            f'<div style="padding:14px 18px;border-bottom:1px solid #1c2235;'
            f'display:flex;justify-content:space-between;align-items:center">'
            f'<div style="font-family:var(--mono,monospace);font-size:13px;'
            f'color:#dde4f0;font-weight:600">{num}. {label}</div>'
            f'{badge}'
            f'</div>'
            f'<div style="padding:16px 18px">'
            f'{carried_banner}'
            f'{_md_to_html(content)}'
            f'{interdep_html}'
            f'</div>'
            f'</div>'
        )

    # Verdict badge from section 8
    verdict_content = _extract_junior_section(response, "SECTION_8_VERDICT", ticker)
    verdict_status  = _extract_status(verdict_content) if verdict_content else "WATCH"
    vfg, vbg = _STORY_BADGE_STYLES.get(verdict_status, ("#8895b0", "#0f1520"))

    state_chain_html = render_state_chain(state_chain or [])

    return f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>AVSHUNTER Story — {ticker} — {ts}</title>
<style>
@import url('https://fonts.googleapis.com/css2?family=Courier+Prime:wght@400;700&family=DM+Sans:wght@300;400;500;600&display=swap');
:root{{
  --bg:#060810;--bg2:#0b0d16;--bg3:#101420;--bg4:#161b28;
  --border:#1c2235;--border2:#252d42;
  --green:#00ff88;--amber:#f59e0b;--red:#ef4444;--blue:#3b82f6;--purple:#a855f7;--cyan:#00d4aa;
  --text:#dde4f0;--text2:#8895b0;--text3:#4a5568;
  --mono:'Courier Prime',monospace;--sans:'DM Sans',sans-serif;
}}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:var(--bg);color:var(--text);font-family:var(--sans);font-size:14px;line-height:1.7;min-height:100vh}}
.header{{background:var(--bg2);border-bottom:2px solid var(--border2);padding:18px 24px;display:flex;justify-content:space-between;align-items:center}}
.brand{{font-family:var(--mono);font-size:11px;color:var(--text3);letter-spacing:3px;text-transform:uppercase}}
.ticker-name{{font-family:var(--mono);font-size:26px;font-weight:700;color:var(--text);letter-spacing:2px}}
.story-label{{font-size:11px;color:var(--text3);font-family:var(--mono);letter-spacing:2px;margin-top:2px}}
.verdict-badge{{font-family:var(--mono);font-size:13px;font-weight:700;letter-spacing:2px;padding:8px 18px;border-radius:5px}}
.main{{max-width:960px;margin:0 auto;padding:24px}}
.permission-watermark{{background:#1a0000;border:1px solid #ef444433;border-radius:4px;padding:6px 14px;font-family:var(--mono);font-size:10px;color:#ef4444;letter-spacing:2px;text-align:center;margin-bottom:18px}}
.narrative-content h3{{color:var(--cyan);font-family:var(--mono);font-size:13px;margin:12px 0 6px;letter-spacing:1px}}
.narrative-content h4{{color:var(--text);font-size:13px;margin:10px 0 4px}}
.narrative-content p{{color:var(--text2);margin:6px 0;line-height:1.7}}
.narrative-content ul,.narrative-content ol{{padding-left:20px;color:var(--text2)}}
.narrative-content li{{margin:3px 0}}
.narrative-content strong{{color:var(--text)}}
.narrative-content code{{background:var(--bg3);color:var(--green);padding:1px 5px;border-radius:3px;font-size:12px}}
.narrative-content table{{width:100%;border-collapse:collapse;margin:12px 0;font-size:12px}}
.narrative-content th{{background:var(--bg3);color:var(--text2);padding:6px 10px;text-align:left;border:1px solid var(--border)}}
.narrative-content td{{padding:6px 10px;border:1px solid var(--border);color:var(--text2)}}
.footer{{background:var(--bg2);border-top:2px solid var(--border2);padding:14px 24px;text-align:center;font-family:var(--mono);font-size:10px;color:var(--text3);letter-spacing:2px;margin-top:32px}}
</style></head>
<body>
<div class="header">
  <div>
    <div class="brand">AVSHUNTER &mdash; STORY OF THE TRADE</div>
    <div class="ticker-name">{ticker.upper()}</div>
    <div class="story-label">Junior Briefing &mdash; {update_type} &mdash; {ts} &mdash; {date_str} {time_str}</div>
    {f'<div style="font-size:10px;color:#4a5568;font-family:var(--mono);margin-top:4px">thesis_id: {thesis_id}</div>' if thesis_id else ''}
  </div>
  <div class="verdict-badge" style="color:{vfg};background:{vbg};border:1px solid {vfg}44;box-shadow:0 0 20px {vbg}">
    {verdict_status}
  </div>
</div>
<div class="main">
  <div class="permission-watermark">EXECUTION PERMISSION: NONE &mdash; PIPELINE INTERPRETER READ-ONLY &mdash; NO CAPITAL AUTHORITY</div>
  {state_chain_html}
  {update_banner}
  {pill_bar}
  {section_cards}
</div>
<div class="footer">EXECUTION PERMISSION: NONE_PIPELINE_INTERPRETER_ONLY &mdash; CAPITAL_DENIED_PENDING_LIVE_CONFIRMATION &mdash; {ts}</div>
</body></html>"""


def write_story_outputs(
    response: str,
    ticker: str,
    session,
    run_dir: Path,
    ts: str,
    thesis_id: str = "",
    update_type: str = "FULL",
    state_chain: list = None,
    previous_ts: str = "",
) -> dict:
    """
    Parse [JUNIOR_BRIEFING_{TICKER}] from response.
    Write story HTML and story brief CSV.
    Returns dict with html_path, csv_path, and per-section status values.
    Never overwrites — always writes a new timestamped file.
    """
    results: dict = {}
    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)

    # Determine file suffix for update types
    _suffix_map = {
        "CHART_UPDATE":   "_chart_update",
        "OPTIONS_UPDATE": "_options_update",
        "MACRO_UPDATE":   "_macro_update",
        "OVERNIGHT":      "_overnight",
    }
    _suffix = _suffix_map.get(update_type, "")
    _tid    = f"_{thesis_id}" if thesis_id else ""

    # Write HTML
    try:
        html = build_story_html(
            response=response,
            ticker=ticker,
            ts=ts,
            thesis_id=thesis_id,
            update_type=update_type,
            state_chain=state_chain or [],
            previous_ts=previous_ts,
        )
        hp = run_dir / f"story_{ticker.upper()}{_tid}_{ts}{_suffix}.html"
        hp.write_text(html, encoding="utf-8")
        results["html_path"] = str(hp)
        print(f"  ✅ Story HTML: {hp.name}")
    except Exception as e:
        print(f"  ⚠  Story HTML build error: {e}")
        results["html_path"] = ""

    # Extract per-section status values for brief CSV
    section_statuses: dict = {}
    for tag, _num, _label in _SECTION_LABELS:
        content = _extract_junior_section(response, tag, ticker)
        section_statuses[tag.lower()] = _extract_status(content) if content else "MISSING"

    # Extract key pipeline fields from the response (best-effort from section 4 / section 7)
    _extract_val = lambda key: re.search(rf'{key}[:\s]+([^\n]+)', response, re.IGNORECASE)

    def _get(key):
        m = _extract_val(key)
        return m.group(1).strip() if m else ""

    # Build story brief CSV row
    brief_row = {
        "ticker":                  ticker.upper(),
        "thesis_id":               thesis_id,
        "ts":                      ts,
        "update_type":             update_type,
        "section_1_status":        section_statuses.get("section_1_macro", ""),
        "section_2_status":        section_statuses.get("section_2_gamma", ""),
        "section_3_status":        section_statuses.get("section_3_liquidity", ""),
        "section_4_status":        section_statuses.get("section_4_thesis", ""),
        "section_5_status":        section_statuses.get("section_5_chart", ""),
        "section_6_status":        section_statuses.get("section_6_options", ""),
        "section_7_status":        section_statuses.get("section_7_risk", ""),
        "section_8_verdict":       section_statuses.get("section_8_verdict", ""),
        "kill_switch_level":       _get("kill_switch_level"),
        "probe_trigger":           _get("probe_trigger"),
        "armed_trigger":           _get("armed_trigger"),
        "kill_switch_proximity_pct": _get("kill_switch_proximity"),
        "theta_daily":             _get("theta_daily"),
        "ivp":                     _get("ivp"),
        "carry_forward_sections":  (
            "1,2,3,4,6,7" if update_type == "CHART_UPDATE" else
            "1,2,3,4,5,7" if update_type == "OPTIONS_UPDATE" else
            "2,3,4,5,6,7" if update_type == "MACRO_UPDATE" else
            "2,3,4,6,7"   if update_type == "OVERNIGHT" else ""
        ),
        "execution_permission":    EXECUTION_PERMISSION,
        "capital_permission":      CAPITAL_PERMISSION,
    }

    STORY_BRIEF_FIELDS = [
        "ticker", "thesis_id", "ts", "update_type",
        "section_1_status", "section_2_status", "section_3_status", "section_4_status",
        "section_5_status", "section_6_status", "section_7_status", "section_8_verdict",
        "kill_switch_level", "probe_trigger", "armed_trigger",
        "kill_switch_proximity_pct", "theta_daily", "ivp",
        "carry_forward_sections", "execution_permission", "capital_permission",
    ]

    try:
        cp = run_dir / f"story_brief_{ticker.upper()}_{ts}{_suffix}.csv"
        _write_csv([brief_row], cp, STORY_BRIEF_FIELDS)
        results["csv_path"] = str(cp)
        print(f"  ✅ Story brief CSV: {cp.name}")
    except Exception as e:
        print(f"  ⚠  Story brief CSV error: {e}")
        results["csv_path"] = ""

    results["section_statuses"] = section_statuses
    return results


def write_all_outputs_with_junior(
    main_response: str,
    story_response: str,
    session,
    run_dir,
    ts: str,
    ticker: str,
    pre_trade_prob_block: str = "",
) -> dict:
    from pathlib import Path as _Path
    results = {}
    run_dir = _Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)

    (run_dir / f"raw_response_{ts}.txt").write_text(main_response, encoding="utf-8")
    (run_dir / f"raw_story_{ts}.txt").write_text(story_response, encoding="utf-8")

    brief_raw  = _extract_section(main_response, "TRADE_BRIEF_CSV")
    brief_rows = _parse_csv(brief_raw) if brief_raw else []
    for _row in brief_rows:
        _t  = _row.get("ticker", "")
        _v  = _row.get("final_verdict", "WAIT")
        _st = _row.get("trade_state", "WATCH")
        if _t and hasattr(session, "add_verdict"):
            session.add_verdict(_t, _v, _st)
    session.last_ticker_csv = brief_rows

    _BRIEF_FIELDS = [
        "ticker", "direction", "final_verdict", "trade_state", "horizon", "dte",
        "trigger_level", "kill_switch_level", "preferred_contract", "premium", "rr",
        "iv_context", "ivp", "earnings_in_window", "earnings_action",
        "max_pain_risk", "sector_confirmation_required", "first_hour_rule",
        "probe_permitted", "initial_adverse_tolerance", "capital_permission",
        "narrative_summary", "execution_permission",
    ]
    _bp = run_dir / f"ticker_{ticker.lower()}_trade_brief_{ts}.csv"
    _write_csv(brief_rows, _bp, _BRIEF_FIELDS)
    results["brief_csv"] = {"path": _bp, "rows": len(brief_rows)}

    main_html = build_html(main_response, session, ts, tickers=[ticker])

    # PRE-TRADE PROBABILITY ASSESSMENT card
    ete_block_html = ""
    if pre_trade_prob_block:
        _ete_esc = (
            pre_trade_prob_block
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )
        _card_hdr = (
            "<div style='background:#060f0c;border-bottom:1px solid #00d4aa44;"
            "padding:14px 20px;display:flex;justify-content:space-between;"
            "align-items:center'>"
            "<div style='font-family:monospace;font-size:13px;"
            "color:#00d4aa;font-weight:700;letter-spacing:2px'>"
            "PRE-TRADE PROBABILITY ASSESSMENT</div>"
            "<div style='font-size:10px;color:#4a5568;font-family:monospace'>"
            "INFORMATIONAL ONLY &#8212; NEVER BLOCKS VERDICT</div>"
            "</div>"
        )
        _card_body = (
            "<div style='padding:20px 24px'>"
            "<pre style='font-family:monospace;font-size:13px;color:#dde4f0;"
            "background:#060810;border:1px solid #1c2235;border-radius:6px;"
            "padding:16px 18px;overflow-x:auto;white-space:pre;line-height:1.6;"
            "margin:0'>" + _ete_esc + "</pre></div>"
        )
        ete_block_html = (
            "<div style='max-width:1280px;margin:0 auto;padding:0 40px 0'>"
            "<div style='background:#0b0d16;border:2px solid #00d4aa44;"
            "border-radius:8px;margin-top:24px;overflow:hidden'>"
            + _card_hdr + _card_body +
            "</div></div>"
        )

    try:
        junior_html = _build_junior_section_cards(story_response, ticker, ts)
    except Exception:
        junior_html = "<p style='color:#4a5568;font-family:monospace'>Junior briefing unavailable.</p>"

    _jr_hdr = (
        "<div style='background:#060f0c;border-bottom:1px solid #00d4aa44;"
        "padding:14px 20px;display:flex;justify-content:space-between;"
        "align-items:center'>"
        "<div style='font-family:monospace;font-size:13px;"
        "color:#00d4aa;font-weight:700;letter-spacing:2px'>JUNIOR TRADER BRIEFING</div>"
        "<div style='font-size:10px;color:#4a5568;font-family:monospace'>"
        "EXECUTION PERMISSION: NONE &#8212; READ ONLY</div>"
        "</div>"
    )
    junior_block = (
        "<div style='max-width:1280px;margin:0 auto;padding:0 40px 40px'>"
        "<div style='background:#0b0d16;border:2px solid #00d4aa44;"
        "border-radius:8px;margin-top:24px;overflow:hidden'>"
        + _jr_hdr +
        "<div style='padding:20px 24px'>" + junior_html + "</div>"
        "</div></div>"
    )

    unified_html = main_html.replace("</body>", ete_block_html + junior_block + "\n</body>")

    hp = run_dir / f"ticker_{ticker.lower()}_interpreter_{ts}.html"
    hp.write_text(unified_html, encoding="utf-8")
    results["html"] = {"path": hp}
    print(f"  \u2705 Unified HTML: {hp.name}")
    return results


def _build_junior_section_cards(story_response: str, ticker: str, ts: str) -> str:
    pill_bar = "<div style='display:flex;gap:6px;flex-wrap:wrap;margin:0 0 20px 0'>"
    for tag, num, label in _SECTION_LABELS:
        em = "\u2014"
        short = label.split(em)[0].strip() if em in label else label.split("&")[0].strip()
        pill_bar += (
            f"<a href='#{tag}_jr' style='text-decoration:none;padding:5px 12px;"
            f"border-radius:20px;background:#101420;border:1px solid #1c2235;"
            f"font-size:11px;color:#8895b0;font-family:monospace'>{num} {short}</a>"
        )
    pill_bar += "</div>"

    cards_html = ""
    for tag, num, label in _SECTION_LABELS:
        content = _extract_junior_section(story_response, tag, ticker)
        if not content:
            content = "Section not generated."
        status = _extract_status(content)
        badge  = _story_badge_html(status)
        interdep_match = re.search(r"INTERDEP:\s*(.+?)(?:\n|$)", content, re.IGNORECASE | re.DOTALL)
        interdep_html  = ""
        if interdep_match:
            interdep_text = interdep_match.group(1).strip()
            content = content[:interdep_match.start()].strip()
            interdep_html = (
                f"<div style='border-top:1px solid #1c2235;margin-top:16px;"
                f"padding-top:10px;font-size:11px;color:#4a5568;font-family:monospace'>"
                f"INTERDEP: {interdep_text}</div>"
            )
        cards_html += (
            f"<div id='{tag}_jr' style='background:#060810;border:1px solid #1c2235;"
            f"border-radius:8px;margin-bottom:14px;overflow:hidden'>"
            f"<div style='padding:12px 16px;border-bottom:1px solid #1c2235;"
            f"display:flex;justify-content:space-between;align-items:center'>"
            f"<div style='font-family:monospace;font-size:12px;"
            f"color:#dde4f0;font-weight:600'>{num}. {label}</div>"
            f"{badge}</div>"
            f"<div style='padding:14px 16px' class='narrative-content'>"
            f"{_md_to_html(content)}"
            f"{interdep_html}"
            f"</div></div>"
        )
    return pill_bar + cards_html


# ---------------------------------------------------------------------------
# Phantom 1 → Production: Interpreter Sidecar JSON
# ---------------------------------------------------------------------------

def write_interpreter_sidecar(
    ticker: str,
    run_id: str,
    ts: str,
    pre_trade_prob_block: str = "",
    story_response: str = "",
    entry_quality: dict = None,
    catalyst_override: str = None,
    pipeline_output_dir: Path = None,
) -> Path | None:
    """
    Write a structured interpreter feedback JSON to data/output/runs/{run_id}/interpreter/.
    This is the feedback channel from the interpreter back to the morning validator.

    All fields are nullable — if interpreter fails to generate, morning validator
    must still function using pipeline data alone (sidecar is additive only).

    Returns the path written, or None if write failed.
    """
    if not run_id or not ticker:
        return None

    # Resolve output dir: data/output/runs/{run_id}/interpreter/
    if pipeline_output_dir is None:
        # Fall back: look up from BASE_DIR if available
        try:
            _base = Path(__file__).resolve().parent.parent
            pipeline_output_dir = _base / "data" / "output" / "runs" / run_id / "interpreter"
        except Exception:
            return None

    try:
        out_dir = Path(pipeline_output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
    except Exception:
        return None

    # Parse ETE block into structured fields
    def _extract_ete_field(block: str, key: str) -> str:
        import re as _re
        m = _re.search(rf'{re.escape(key)}:\s*(.+)', block or "")
        return m.group(1).strip() if m else ""

    crowd_stage         = _extract_ete_field(pre_trade_prob_block, "crowd_stage")
    p_trigger_hit       = _extract_ete_field(pre_trade_prob_block, "p_trigger_hit")
    kill_switch_warning = _extract_ete_field(pre_trade_prob_block, "kill_switch_warning")
    garch_status        = _extract_ete_field(pre_trade_prob_block, "garch_status")
    edge_quality        = _extract_ete_field(pre_trade_prob_block, "edge_quality")

    # Parse junior section statuses
    section_statuses = {}
    for tag, num, label in _SECTION_LABELS:
        sec_content = _extract_junior_section(story_response, tag, ticker)
        section_statuses[tag] = {
            "present": bool(sec_content),
            "status":  _extract_status(sec_content) if sec_content else "MISSING",
        }

    junior_ok = all(v["present"] for v in section_statuses.values())

    payload = {
        "interpreter_version":    "1.1",
        "run_id":                 str(run_id),
        "ticker":                 str(ticker).upper(),
        "ts":                     str(ts),
        "generated_at":           datetime.now().isoformat(),
        # Pre-trade probability fields
        "crowd_stage":            crowd_stage or None,
        "p_trigger_hit":          p_trigger_hit or None,
        "kill_switch_warning":    kill_switch_warning or None,
        "garch_status":           garch_status or None,
        "edge_quality":           edge_quality or None,
        # Entry quality (Phantom 2)
        "entry_quality":          (entry_quality or {}).get("entry_quality"),
        "entry_zone_position":    (entry_quality or {}).get("zone_position"),
        "entry_distance_pct":     (entry_quality or {}).get("distance_to_nearest_pct"),
        # Catalyst override (Phantom 3)
        "catalyst_override":      catalyst_override or None,
        # Junior briefing integrity
        "junior_sections_present": junior_ok,
        "junior_section_statuses": section_statuses,
        # Execution permission — always locked
        "execution_permission":   "NONE_PIPELINE_INTERPRETER_ONLY",
        "capital_permission":     "CAPITAL_DENIED_PENDING_LIVE_CONFIRMATION",
    }

    out_path = out_dir / f"{run_id}_{ticker.upper()}_interpreter.json"
    try:
        out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return out_path
    except Exception:
        return None


def load_interpreter_sidecar(ticker: str, run_id: str, runs_base_dir: Path) -> dict | None:
    """
    Load interpreter sidecar JSON for a given ticker and run_id.
    Returns None if not found or unreadable — callers must handle None gracefully.
    """
    path = Path(runs_base_dir) / run_id / "interpreter" / f"{run_id}_{ticker.upper()}_interpreter.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None