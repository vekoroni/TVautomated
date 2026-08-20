"""
AVSHUNTER M&A Cockpit v1.0 — Output Writers
CSV (full schema), HTML brief, master calendar
"""
import csv, json, re, io
from datetime import datetime
from pathlib import Path

EXECUTION_PERMISSION = "NONE_MA_COCKPIT_ONLY"
CAPITAL_GRADE        = "NO"

# Full schema matching ma_csv_schema.py REQUIRED_COLUMNS
TICKER_CSV_FIELDS = [
    "review_date","event_id","event_date","source_name","source_tier","source_url",
    "headline","event_type","deal_status","target_company","target_ticker",
    "acquirer_company","acquirer_ticker","sector","industry","deal_value",
    "premium_to_last_close","consideration_type","cash_stock_mix","rumour_flag",
    "confirmed_flag","denied_flag","second_source_count","strategic_logic_score",
    "regulatory_plausibility_score","source_quality_score","price_confirmation_score",
    "options_confirmation_score","sector_consolidation_score","affected_ticker",
    "affected_company","affected_role","beneficiary_type","expected_impact_direction",
    "expected_impact_strength","dbs","pipeline_candidate_flag","pipeline_priority",
    "pipeline_reason","ma_tps","ma_rcs","ma_pasp_state","ma_street_state",
    "ma_trade_bias","ma_verdict","ma_confidence","long_call_candidate","long_put_candidate",
    "options_liquidity_status","spread_pct_mid","preferred_dte_min","preferred_dte_max",
    "preferred_delta_min","preferred_delta_max","confirmed_facts","assumptions",
    "missing_inputs","failure_flags","manual_reviewer_notes","run_through_avshunter",
    "avshunter_route","created_by","last_updated","execution_permission","capital_grade"
]

HANDOFF_CSV_FIELDS = [
    "event_date","event_time","narrative","event_type","deal_status","source_name",
    "source_tier","source_url","affected_ticker","affected_company","sector",
    "affected_role","beneficiary_type","expected_impact_direction","expected_impact_strength",
    "dbs","cems","pipeline_priority","ma_trade_bias","ma_verdict","ma_confidence",
    "avshunter_route","long_call_candidate","long_put_candidate","options_liquidity_status",
    "strategic_motive","deal_value","premium_to_last_close","regulatory_risk",
    "financing_risk","timeline_horizon","confirmed_facts","assumptions","missing_inputs",
    "failure_flags","manual_reviewer_notes","execution_permission","capital_grade"
]

def _extract_section(response:str, tag:str) -> str:
    m = re.search(rf'\[{tag}\](.*?)(?=\[[A-Z_]+\]|$)', response, re.DOTALL|re.IGNORECASE)
    return m.group(1).strip() if m else ""

def _clean_csv(text:str) -> str:
    text = re.sub(r'```[a-z]*','',text).replace('```','').strip()
    text = re.sub(r'(NONE_MA_COCKPIT_ONLY(?:,NO)?)\s+([A-Z]{1,8},\d{4})',r'\1\n\2',text)
    text = re.sub(r'(NO,MA_COCKPIT_v1\.0[^\n]*)\s+(\d{4}-\d{2}-\d{2},)',r'\1\n\2',text)
    lines=[l for l in text.splitlines() if l.strip() and l.strip()!='---']
    return '\n'.join(lines)

def _parse_csv(text:str) -> list:
    if not text.strip(): return []
    try:
        rows=list(csv.DictReader(io.StringIO(_clean_csv(text))))
        for r in rows:
            r["execution_permission"]=EXECUTION_PERMISSION
            r["capital_grade"]=CAPITAL_GRADE
            if not r.get("created_by"): r["created_by"]="MA_COCKPIT_v1.0"
            if not r.get("last_updated"): r["last_updated"]=datetime.now().strftime("%Y-%m-%d %H:%M")
        return rows
    except Exception as e:
        print(f"  ⚠ CSV parse: {e}"); return []

def _write_csv(rows:list, path:Path, fields:list) -> int:
    if not rows: return 0
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path,"w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction="ignore")
        w.writeheader()
        for r in rows:
            r["execution_permission"]=EXECUTION_PERMISSION
            r["capital_grade"]=CAPITAL_GRADE
            w.writerow(r)
    return len(rows)

def _deduplicate_master(rows:list, master:Path) -> int:
    existing=set()
    if master.exists():
        with open(master,"r",encoding="utf-8") as f:
            for r in csv.DictReader(f):
                key=f"{r.get('affected_ticker','')}-{r.get('event_date','')}-{str(r.get('headline',''))[:30]}"
                existing.add(key)
    added=0; write_hdr=not master.exists()
    master.parent.mkdir(parents=True, exist_ok=True)
    with open(master,"a",newline="",encoding="utf-8") as f:
        writer=None
        for r in rows:
            key=f"{r.get('affected_ticker','')}-{r.get('event_date','')}-{str(r.get('headline',''))[:30]}"
            if key not in existing:
                if writer is None:
                    writer=csv.DictWriter(f,fieldnames=list(r.keys()),extrasaction="ignore")
                    if write_hdr: writer.writeheader()
                r["execution_permission"]=EXECUTION_PERMISSION; r["capital_grade"]=CAPITAL_GRADE
                writer.writerow(r); existing.add(key); added+=1
    return added

def _verdict_color(v:str) -> str:
    if "PIPELINE_NOW" in v or "CONFIRMED" in v: return "#00c853"
    if "WATCHLIST" in v or "HIGH_PROB" in v: return "#f59e0b"
    if "ACTIVIST" in v: return "#0080ff"
    if "RUMOUR" in v or "BLOCK" in v: return "#ef4444"
    return "#64748b"

def _priority_badge(p:str) -> str:
    styles={"P1":"color:#00c853;background:#003300;border:1px solid #00c85355;",
            "P2":"color:#f59e0b;background:#1a1200;border:1px solid #f59e0b55;",
            "P3":"color:#64748b;background:#0f1520;border:1px solid #64748b55;",
            "WATCH_ONLY":"color:#334155;background:#0a0a0a;border:1px solid #33415555;",
            "DO_NOT_RUN":"color:#ef4444;background:#1a0000;border:1px solid #ef444455;"}
    s=styles.get(p,"color:#64748b;background:#0a0a0a;")
    return f'<span style="font-family:var(--mono);font-size:10px;font-weight:700;padding:3px 8px;border-radius:3px;{s}">{p}</span>'

def _role_color(r:str) -> str:
    return {"TARGET":"#00c853","ACQUIRER":"#ef4444","PEER":"#f59e0b",
            "ACTIVIST_TARGET":"#0080ff","MERGER_ARB":"#a855f7",
            "BREAKUP_CANDIDATE":"#f59e0b","SUPPLIER":"#94a3b8",
            "COMPETITOR":"#ef4444","SECTOR_SYMPATHY":"#64748b"}.get(r,"#64748b")

def _verdict_badge(v:str) -> str:
    c={"GO":"#00c853","ARMED_HALF":"#f59e0b","WAIT":"#64748b","BLOCKED":"#ef4444"}.get(v,"#64748b")
    return f'<span style="font-family:var(--mono);font-size:10px;font-weight:700;color:{c};background:{c}22;border:1px solid {c}44;padding:3px 8px;border-radius:3px;">{v}</span>'

def _dbs_color(score:str) -> str:
    try:
        n=int(float(score))
        return "#00c853" if n>=70 else ("#f59e0b" if n>=50 else "#ef4444")
    except: return "#64748b"

def _csv_to_table(csv_text:str) -> str:
    if not csv_text.strip(): return "<p>No candidates.</p>"
    try:
        rows=list(csv.DictReader(io.StringIO(_clean_csv(csv_text))))
        if not rows: return "<p>No rows parsed.</p>"
        cols=["affected_ticker","affected_company","sector","affected_role","beneficiary_type",
              "expected_impact_direction","dbs","pipeline_priority","ma_trade_bias",
              "ma_verdict","avshunter_route","long_call_candidate","long_put_candidate",
              "options_liquidity_status","headline"]
        avail=list(rows[0].keys())
        show=[c for c in cols if c in avail]
        hdr=''.join(f'<th>{c.replace("_"," ").title()}</th>' for c in show)
        body=''
        for row in rows:
            cells=''
            for col in show:
                val=str(row.get(col,'')).strip()
                style=''
                if col=='affected_ticker':
                    style='font-weight:700;font-family:var(--mono);font-size:14px;color:#e2e8f0;white-space:nowrap;'
                elif col=='affected_role':
                    style=f'color:{_role_color(val)};font-weight:600;font-size:12px;'
                elif col=='pipeline_priority':
                    cells+=f'<td>{_priority_badge(val)}</td>'; continue
                elif col=='ma_verdict':
                    cells+=f'<td>{_verdict_badge(val)}</td>'; continue
                elif col=='dbs':
                    style=f'color:{_dbs_color(val)};font-weight:700;font-family:var(--mono);text-align:center;'
                elif col in('long_call_candidate','long_put_candidate'):
                    c='#00c853' if val.upper()=='TRUE' else '#334155'
                    style=f'color:{c};font-weight:600;text-align:center;'
                elif col=='headline':
                    style='font-size:12px;color:#94a3b8;max-width:220px;'
                elif col in('ma_trade_bias','expected_impact_direction'):
                    c='#00c853' if 'BULL' in val or 'CALL' in val else ('#ef4444' if 'BEAR' in val or 'PUT' in val else '#f59e0b')
                    style=f'color:{c};font-weight:600;font-size:12px;'
                cells+=f'<td style="{style}">{val}</td>'
            body+=f'<tr>{cells}</tr>'
        return f'<div style="overflow-x:auto"><table class="data-tbl"><thead><tr>{hdr}</tr></thead><tbody>{body}</tbody></table></div>'
    except Exception as e:
        return f"<p>Table error: {e}</p>"

def _md_to_html(text:str) -> str:
    if not text: return "<p>No data.</p>"
    text=text.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")
    text=re.sub(r'^### (.+)$',r'<h3>\1</h3>',text,flags=re.MULTILINE)
    text=re.sub(r'^## (.+)$',r'<h2>\1</h2>',text,flags=re.MULTILINE)
    text=re.sub(r'^# (.+)$',r'<h2>\1</h2>',text,flags=re.MULTILINE)
    text=re.sub(r'\*\*(.+?)\*\*',r'<strong>\1</strong>',text)
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
                result.append(f'<table class="data-tbl">{hdr}{bdy}</table>')
                trows=[]; in_table=False
            result.append(line)
    if in_table and trows:
        hdr='<tr>'+''.join(f'<th>{c}</th>' for c in trows[0])+'</tr>'
        bdy=''.join('<tr>'+''.join(f'<td>{c}</td>' for c in r)+'</tr>' for r in trows[1:])
        result.append(f'<table class="data-tbl">{hdr}{bdy}</table>')
    text='\n'.join(result); parts=[]
    for para in re.split(r'\n{2,}',text):
        para=para.strip()
        if not para: continue
        if para.startswith('<h') or para.startswith('<table'): parts.append(para)
        elif re.match(r'^[-*] ',para):
            items=re.split(r'\n[-*] ',para); items=[i.lstrip('-* ') for i in items if i.strip()]
            parts.append('<ul>'+''.join(f'<li>{i}</li>' for i in items)+'</ul>')
        else: parts.append(f'<p>{para.replace(chr(10)," ")}</p>')
    return '\n'.join(parts)

def build_html(response:str, session, ts:str, mode:str="full") -> str:
    from ma_cockpit_engine import extract_verdict
    date_str=datetime.now().strftime("%A %d %B %Y")
    time_str=datetime.now().strftime("%H:%M ET")
    desk_verdict=session.desk_verdict or "PENDING"
    vc=_verdict_color(desk_verdict)
    s=session.summary()

    exec_sum   =_extract_section(response,"MA_EXECUTIVE_SUMMARY")
    deals      =_extract_section(response,"MA_DEALS_DETECTED")
    corp_events=_extract_section(response,"MA_CORPORATE_EVENTS")
    trans      =_extract_section(response,"MA_TRANSMISSION")
    ben_map    =_extract_section(response,"MA_BENEFICIARY_MAP")
    routing    =_extract_section(response,"MA_OPTIONS_ROUTING")
    pipeline   =_extract_section(response,"MA_PIPELINE_CANDIDATES")
    caution    =_extract_section(response,"MA_FAILURE_CAUTION_LIST")
    validation =_extract_section(response,"MA_VALIDATION_CHECKLIST")
    conf_table =_extract_section(response,"MA_CONFIRMED_ASSUMPTION_MISSING")
    desk_v     =_extract_section(response,"MA_DESK_VERDICT")
    ticker_csv =_extract_section(response,"TICKER_CSV_DATA")

    cand_table=_csv_to_table(ticker_csv) if ticker_csv else ""
    brand="AVSHUNTER M&A COCKPIT v1.0" if mode=="full" else "AVSHUNTER M&A INTELLIGENCE"

    def sec(title,body,icon="▶",border_color=None):
        if not body or not body.strip(): return ""
        bc=f"border-left:3px solid {border_color};" if border_color else ""
        return f'<div class="section" style="{bc}"><div class="sec-hdr">{icon} {title}</div><div class="sec-body brief-content">{_md_to_html(body)}</div></div>'

    sections  = sec("Executive Summary",exec_sum,"◈","#a855f7")
    sections += sec("Deals Detected",deals,"▶","#00c853")
    sections += sec("Corporate Events",corp_events,"▶","#0080ff")
    sections += sec("Transmission & Sector Impact",trans)
    sections += sec("Beneficiary Map",ben_map,"◈","#f59e0b")

    if cand_table:
        sections += f'<div class="section" style="border-left:3px solid #a855f7"><div class="sec-hdr">◈ M&amp;A Pipeline Candidates</div><div class="sec-body">{cand_table}</div></div>'

    sections += sec("Options Routing",routing)
    sections += sec("Pipeline Candidate List",pipeline)

    if mode=="full":
        sections += sec("Failure & Caution List",caution,"⚠","#ef4444")
        sections += sec("Manual Validation Checklist",validation)
        sections += sec("Confirmed / Assumption / Missing",conf_table)
        sections += sec("Desk Verdict",desk_v)

    return f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>AVSHUNTER M&A Cockpit — {date_str}</title>
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@300;400;500;600&display=swap');
:root{{--bg:#09090d;--bg2:#0f1018;--bg3:#161820;--border:#1e2030;--accent:#a855f7;--green:#22c55e;--red:#ef4444;--amber:#f59e0b;--blue:#3b82f6;--text:#e2e8f0;--text2:#94a3b8;--text3:#64748b;--mono:'IBM Plex Mono',monospace;--sans:'IBM Plex Sans',sans-serif;}}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:var(--bg);color:var(--text);font-family:var(--sans);font-size:14px;line-height:1.7}}
.hdr{{background:var(--bg2);border-bottom:2px solid var(--accent);padding:24px 36px;display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:16px}}
.brand{{font-family:var(--mono);font-size:10px;color:var(--accent);letter-spacing:.15em;text-transform:uppercase;margin-bottom:6px}}
.title{{font-family:var(--mono);font-size:22px;font-weight:600;color:var(--text)}}
.meta{{font-family:var(--mono);font-size:11px;color:var(--text3);margin-top:6px}}
.badges{{display:flex;flex-direction:column;align-items:flex-end;gap:8px}}
.vbadge{{font-family:var(--mono);font-size:10px;font-weight:700;letter-spacing:.08em;padding:5px 12px;border-radius:3px;background:{vc}22;color:{vc};border:1px solid {vc}55}}
.banner{{background:#140a1a;border-bottom:1px solid #3b1a5a;padding:8px 36px;font-family:var(--mono);font-size:11px;color:#c084fc;letter-spacing:.08em;text-align:center}}
.stats{{display:flex;gap:12px;flex-wrap:wrap;padding:16px 36px;background:var(--bg2);border-bottom:1px solid var(--border)}}
.stat{{background:var(--bg);border:1px solid var(--border);border-radius:4px;padding:10px 16px;min-width:120px}}
.slbl{{font-family:var(--mono);font-size:9px;color:var(--text3);letter-spacing:.12em;text-transform:uppercase;margin-bottom:5px}}
.sval{{font-family:var(--mono);font-size:13px;font-weight:600;color:var(--accent)}}
.content{{max-width:1320px;margin:0 auto;padding:24px 36px}}
.section{{margin-bottom:20px;background:var(--bg2);border:1px solid var(--border);border-radius:6px;overflow:hidden}}
.sec-hdr{{background:var(--bg3);border-bottom:1px solid var(--border);padding:11px 20px;font-family:var(--mono);font-size:11px;font-weight:600;color:var(--accent);letter-spacing:.1em;text-transform:uppercase}}
.sec-body{{padding:20px 24px}}
.brief-content p{{margin-bottom:10px;color:var(--text2);line-height:1.75}}
.brief-content h2,.brief-content h3{{font-family:var(--mono);color:var(--accent);margin:18px 0 8px;font-size:12px;letter-spacing:.1em;text-transform:uppercase;border-bottom:1px solid var(--border);padding-bottom:5px}}
.brief-content table{{width:100%;border-collapse:collapse;margin:12px 0;font-family:var(--mono);font-size:12px}}
.brief-content th{{background:var(--bg3);color:var(--text3);padding:7px 12px;text-align:left;border:1px solid var(--border);font-size:10px;letter-spacing:.06em;text-transform:uppercase}}
.brief-content td{{padding:7px 12px;border:1px solid var(--border);color:var(--text);vertical-align:top}}
.brief-content tr:nth-child(even) td{{background:var(--bg3)}}
.brief-content ul{{margin:8px 0 12px 20px;color:var(--text2)}}
.brief-content li{{margin-bottom:5px}}
.brief-content strong{{color:var(--text);font-weight:600}}
.data-tbl{{width:100%;border-collapse:collapse;font-family:var(--mono);font-size:12px}}
.data-tbl th{{background:var(--bg3);color:var(--text3);padding:8px 12px;text-align:left;border:1px solid var(--border);font-size:10px;letter-spacing:.08em;text-transform:uppercase;white-space:nowrap}}
.data-tbl td{{padding:8px 12px;border:1px solid var(--border);vertical-align:top;line-height:1.5}}
.data-tbl tr:hover td{{background:var(--bg3)}}
.footer{{border-top:1px solid var(--border);padding:14px 36px;background:var(--bg2);display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px;margin-top:8px}}
.ftr-l{{font-family:var(--mono);font-size:10px;color:#c084fc;font-weight:600}}
.ftr-r{{font-family:var(--mono);font-size:10px;color:var(--text3)}}
</style></head><body>
<div class="hdr">
  <div><div class="brand">{brand}</div>
  <div class="title">M&amp;A Intelligence Brief</div>
  <div class="meta">{date_str} &nbsp;|&nbsp; {time_str} &nbsp;|&nbsp; Run: {ts}</div></div>
  <div class="badges"><div class="vbadge">{desk_verdict.replace("_"," ")}</div></div>
</div>
<div class="banner">⚠&nbsp; EXECUTION PERMISSION: {EXECUTION_PERMISSION} &nbsp;—&nbsp; ANALYSIS ONLY &nbsp;—&nbsp; CAPITAL GRADE: {CAPITAL_GRADE}</div>
<div class="stats">
  <div class="stat"><div class="slbl">Desk Verdict</div><div class="sval" style="font-size:9px;color:{vc}">{desk_verdict.replace("_"," ")}</div></div>
  <div class="stat"><div class="slbl">Total Candidates</div><div class="sval">{s["total"]}</div></div>
  <div class="stat"><div class="slbl">P1 Priority</div><div class="sval" style="color:var(--green)">{s["p1"]}</div></div>
  <div class="stat"><div class="slbl">P2 Priority</div><div class="sval" style="color:var(--amber)">{s["p2"]}</div></div>
  <div class="stat"><div class="slbl">GO Verdicts</div><div class="sval" style="color:var(--green)">{s["go"]}</div></div>
  <div class="stat"><div class="slbl">Run</div><div class="sval" style="font-size:11px">{ts}</div></div>
</div>
<div class="content">{sections}</div>
<div class="footer">
  <div class="ftr-l">⚠ {EXECUTION_PERMISSION} | CAPITAL GRADE: {CAPITAL_GRADE}</div>
  <div class="ftr-r">AVSHUNTER M&A Cockpit v1.0 | Generated {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</div>
</div></body></html>"""

_MA_INTEGRATION_COLS = [
    "ticker", "catalyst_type", "catalyst_status", "catalyst_date",
    "event_window_start", "event_window_end", "catalyst_direction_bias",
    "catalyst_source_confidence", "catalyst_binary_score", "source_tier",
    "source_url", "ticker_role", "event_status", "tradability_route",
    "failure_risk", "missing_data", "execution_permission", "capital_grade",
    "date_quality", "source_count", "already_priced_risk",
    "needs_manual_confirmation", "company", "sector", "key_catalyst",
    "transmission_channel", "expected_impact", "confirmation_signals",
    "invalidation_signals", "anis_score", "fips_score", "manual_validation_notes"
]


def write_ma_candidates_flat(response: str, ts: str) -> "Path | None":
    """Write ma_candidates_YYYYMMDD.csv to flat ma_cockpit/outputs/ (32-col integration schema)."""
    from pathlib import Path as _Path
    base_dir = _Path(__file__).parent
    flat_dir = base_dir / "outputs"
    flat_dir.mkdir(parents=True, exist_ok=True)
    date_str = ts[:8]
    out = flat_dir / f"ma_candidates_{date_str}.csv"

    raw = _extract_section(response, "MA_CANDIDATES_CSV_DATA")
    if not raw:
        return None
    clean = _clean_csv(raw)
    try:
        rows = list(csv.DictReader(io.StringIO(clean)))
    except Exception as e:
        print(f"  ⚠ MA candidates flat CSV parse: {e}")
        return None
    if not rows:
        return None

    for row in rows:
        row["execution_permission"] = "NONE_NEWS_TERMINAL_ONLY"
        row["capital_grade"] = "NO"
        for col in _MA_INTEGRATION_COLS:
            row.setdefault(col, "")

    with open(out, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=_MA_INTEGRATION_COLS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    print(f"  [MA FLAT CSV]  {out.name} ({len(rows)} rows)")
    return out


def write_all_outputs(response:str, session, run_dir:Path, ts:str, prefix:str="") -> dict:
    from ma_cockpit_engine import MASTER_CSV, extract_verdict
    results={}
    pfx=f"{prefix}_" if prefix else ""

    # Save raw response
    (run_dir/f"raw_response_{ts}.txt").write_text(response,encoding="utf-8")

    # Parse CSVs
    ticker_raw  =_extract_section(response,"TICKER_CSV_DATA")
    handoff_raw =_extract_section(response,"HANDOFF_CSV_DATA")
    ticker_rows =_parse_csv(ticker_raw)
    handoff_rows=_parse_csv(handoff_raw)

    # Update session
    session.add_candidates(ticker_rows)
    session.desk_verdict=extract_verdict(response)
    session.last_ticker_csv=ticker_rows
    session.last_handoff_csv=handoff_rows

    # Write ticker CSV (full schema)
    tp=run_dir/f"{pfx}ma_candidates_{ts}.csv"
    n=_write_csv(ticker_rows,tp,TICKER_CSV_FIELDS)
    results["ticker_csv"]={"path":tp,"rows":n}
    if n==0: print(f"  ⚠ No ticker rows extracted — check raw_response_{ts}.txt")

    # Write handoff CSV
    hp=run_dir/f"{pfx}ma_handoff_{ts}.csv"
    results["handoff_csv"]={"path":hp,"rows":_write_csv(handoff_rows,hp,HANDOFF_CSV_FIELDS)}

    # Update master
    added=_deduplicate_master(ticker_rows+handoff_rows,MASTER_CSV)
    results["master"]={"added":added}

    # Write HTML briefs
    full_html=build_html(response,session,ts,mode="full")
    fp=run_dir/f"{pfx}ma_brief_{ts}_full.html"
    fp.write_text(full_html,encoding="utf-8"); results["full_html"]={"path":fp}

    trader_html=build_html(response,session,ts,mode="trader")
    tp2=run_dir/f"{pfx}ma_brief_{ts}_trader.html"
    tp2.write_text(trader_html,encoding="utf-8"); results["trader_html"]={"path":tp2}

    # Integration output — flat ma_cockpit/outputs/ma_candidates_YYYYMMDD.csv (32-col schema)
    flat_path = write_ma_candidates_flat(response, ts)
    if flat_path:
        results["ma_candidates_flat"] = {"path": flat_path}

    return results
