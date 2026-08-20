"""
AVSHUNTER News Terminal v1.3 — Output Writers
CSV, JSON, HTML brief, newsletter
"""

import csv
import json
import re
from datetime import datetime
from pathlib import Path

EXECUTION_PERMISSION = "NONE_NEWS_TERMINAL_ONLY"
CAPITAL_GRADE = "NO"


def _get_paths():
    base = Path(__file__).parent
    outputs = base / "outputs"
    daily = outputs / "daily"
    catalyst_master = outputs / "catalyst_calendar_master.csv"
    return outputs, daily, catalyst_master


def write_ticker_csv(response, run_dir, ts):
    blocks = _extract_csv_blocks(response)
    if 'ticker_csv' not in blocks:
        return None
    out = run_dir / f"news_terminal_{ts}.csv"
    out.write_text(blocks['ticker_csv'], encoding="utf-8")
    _enforce_permissions(out)
    return out


def write_handoff_csv(response, run_dir, ts, prefix=""):
    blocks = _extract_csv_blocks(response)
    if 'handoff_csv' not in blocks:
        return None
    fname = f"handoff_{prefix}{ts}.csv" if prefix else f"handoff_{ts}.csv"
    out = run_dir / fname
    out.write_text(blocks['handoff_csv'], encoding="utf-8")
    _enforce_permissions(out)
    return out


def write_macro_json(response, run_dir, ts):
    data = _extract_json(response)
    if not data:
        data = _minimal_macro_json(response, ts)
    data["execution_permission"] = EXECUTION_PERMISSION
    data["capital_grade"] = CAPITAL_GRADE
    out = run_dir / f"macro_delta_{ts}.json"
    out.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return out


def write_full_brief(response, session, run_dir, ts):
    html = _build_html(response, session, ts, mode="full")
    out = run_dir / f"brief_{ts}_full.html"
    out.write_text(html, encoding="utf-8")
    return out


def write_trader_brief(response, session, run_dir, ts):
    html = _build_html(response, session, ts, mode="trader")
    out = run_dir / f"brief_{ts}_trader.html"
    out.write_text(html, encoding="utf-8")
    return out


def write_summary_text(response, session, run_dir, ts):
    text = _build_summary(response, session, ts)
    out = run_dir / f"brief_{ts}_summary.txt"
    out.write_text(text, encoding="utf-8")
    return out


def write_all_outputs(response, session, run_dir, ts, prefix=""):
    written = {}

    # Always save raw response for debugging
    raw_path = run_dir / f"raw_response_{ts}.txt"
    raw_path.write_text(response, encoding="utf-8")

    ticker_csv = write_ticker_csv(response, run_dir, ts)
    if ticker_csv:
        written['ticker_csv'] = ticker_csv
        written['master_new_rows'] = update_catalyst_master(ticker_csv)
    else:
        print("  ⚠ No ticker CSV extracted — check raw_response_{ts}.txt")

    handoff = write_handoff_csv(response, run_dir, ts, prefix=prefix)
    if handoff:
        written['handoff_csv'] = handoff
    else:
        print("  ⚠ No handoff CSV extracted")

    written['macro_json'] = write_macro_json(response, run_dir, ts)
    written['full_brief'] = write_full_brief(response, session, run_dir, ts)
    written['trader_brief'] = write_trader_brief(response, session, run_dir, ts)
    written['summary_text'] = write_summary_text(response, session, run_dir, ts)

    # Integration outputs — flat news_terminal/outputs/
    cat_path = write_catalyst_csv_v2(response, ts)
    if cat_path:
        written['catalyst_csv_v2'] = cat_path
    delta_path = write_macro_enrichment_delta(response, ts)
    if delta_path:
        written['macro_enrichment_delta'] = delta_path
    tickers_path = write_tickers_file(response, ts, cat_path)
    if tickers_path:
        written['tickers_file'] = tickers_path

    return written


def update_catalyst_master(ticker_csv_path):
    if not ticker_csv_path or not ticker_csv_path.exists():
        return 0
    outputs, _, catalyst_master = _get_paths()
    outputs.mkdir(parents=True, exist_ok=True)
    existing_keys = set()
    existing_rows = []
    fieldnames = []
    if catalyst_master.exists():
        with open(catalyst_master, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            fieldnames = reader.fieldnames or []
            for row in reader:
                key = (row.get('ticker',''), row.get('generated_date',''), row.get('narrative',''))
                existing_keys.add(key)
                existing_rows.append(row)
    new_rows = []
    with open(ticker_csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        if not fieldnames:
            fieldnames = reader.fieldnames or []
        for row in reader:
            key = (row.get('ticker',''), row.get('generated_date',''), row.get('narrative',''))
            if key not in existing_keys:
                new_rows.append(row)
                existing_keys.add(key)
    if not new_rows:
        return 0
    with open(catalyst_master, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(existing_rows + new_rows)
    return len(new_rows)


# ── Internal helpers ──────────────────────────────────────────────────────────

def _extract_section(response, tag):
    """Extract content between [TAG] and next [TAG] or end of string."""
    pattern = rf'\[{tag}\](.*?)(?=\[[A-Z_]+\]|$)'
    m = re.search(pattern, response, re.DOTALL | re.IGNORECASE)
    return m.group(1).strip() if m else ""

def _clean_csv_block(text):
    """Strip markdown fences, fix spacing issues, return clean CSV text."""
    # Strip markdown fences
    text = re.sub(r'```[a-z]*', '', text).replace('```', '').strip()

    # Fix: API sometimes outputs rows separated by space instead of newline
    # Detect by looking for pattern: "...NONE_NEWS_TERMINAL_ONLY TICKER," or "...NONE_NEWS_TERMINAL_ONLY NEWS_TERMINAL_TICKER"
    text = re.sub(
        r'(NONE_NEWS_TERMINAL_ONLY)\s+((?:TICKER|NEWS_TERMINAL_TICKER_CANDIDATE),)',
        r'\1\n\2',
        text
    )

    # Also fix header-to-first-row space separation
    # Pattern: last header column "execution_permission" followed by space then data
    text = re.sub(
        r'(execution_permission)\s+((?:NEWS_TERMINAL_TICKER_CANDIDATE|TICKER),)',
        r'\1\n\2',
        text
    )

    # Normalise line endings and strip blanks
    lines = [l for l in text.splitlines() if l.strip() and l.strip() != '---']
    return '\n'.join(lines)

def _extract_csv_blocks(response):
    results = {}

    # Strategy 1: [SECTION_TAG] markers (preferred)
    ticker_raw = _extract_section(response, "TICKER_CSV_DATA")
    if ticker_raw:
        results['ticker_csv'] = _clean_csv_block(ticker_raw)

    handoff_raw = _extract_section(response, "HANDOFF_CSV_DATA")
    if handoff_raw:
        results['handoff_csv'] = _clean_csv_block(handoff_raw)

    # Strategy 2: ```csv fences fallback
    if 'ticker_csv' not in results or 'handoff_csv' not in results:
        for match in re.finditer(r'```csv\n?(.*?)```', response, re.DOTALL):
            block = match.group(1).strip()
            lines = block.split('\n')
            if not lines:
                continue
            header = lines[0].lower()
            if 'ticker_csv' not in results and ('export_type' in header or 'pipeline_input_type' in header or 'ticker' in header):
                results['ticker_csv'] = block
            elif 'handoff_csv' not in results and 'event_date' in header:
                results['handoff_csv'] = block

    # Strategy 3: scan for CSV-looking blocks with known headers
    if 'ticker_csv' not in results:
        for match in re.finditer(r'(export_type,candidate_id.*?)(?=\n\n|\Z)', response, re.DOTALL):
            results['ticker_csv'] = match.group(1).strip()
            break
    if 'handoff_csv' not in results:
        for match in re.finditer(r'(event_date,event_time.*?)(?=\n\n|\Z)', response, re.DOTALL):
            results['handoff_csv'] = match.group(1).strip()
            break

    return results


def _extract_json(response):
    # Strategy 1: [MACRO_JSON_DATA] section tag
    raw = _extract_section(response, "MACRO_JSON_DATA")
    if raw:
        clean = re.sub(r'```[a-z]*', '', raw).replace('```', '').strip()
        try:
            return json.loads(clean)
        except json.JSONDecodeError:
            pass

    # Strategy 2: ```json fences
    for match in re.finditer(r'```json\n?(.*?)```', response, re.DOTALL):
        try:
            data = json.loads(match.group(1).strip())
            if any(k in data for k in ['global_session_date','asia_risk_tone','final_desk_verdict','desk_verdict']):
                return data
        except json.JSONDecodeError:
            continue

    # Strategy 3: bare JSON object with known keys
    for match in re.finditer(r'(\{[^{}]*"(?:global_session_date|asia_risk_tone|final_desk_verdict)"[^{}]*\})', response, re.DOTALL):
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            continue
    return None


def _minimal_macro_json(response, ts):
    desk_verdict = "MIXED_SESSION_WAIT_FOR_US_CONFIRMATION"
    for v in ["GLOBAL_RISK_ON_US_SUPPORTIVE","GLOBAL_RISK_OFF_US_DEFENSIVE",
              "CORPORATE_EVENT_PIPELINE_REVIEW","CATALYST_WATCH_ONLY",
              "CHINA_STIMULUS_CYCLICAL_SUPPORT","MIXED_SESSION_WAIT_FOR_US_CONFIRMATION"]:
        if v in response:
            desk_verdict = v
            break
    options_bias = "WAIT"
    for o in ["CALL_FAVOURED","PUT_FAVOURED","VOL_EXPANSION","VOL_CRUSH"]:
        if o in response:
            options_bias = o
            break
    return {
        "global_session_date": datetime.now().strftime("%Y-%m-%d"),
        "run_time": ts[-4:] if len(ts) >= 4 else ts,
        "run_session": "SCHEDULED",
        "final_desk_verdict": desk_verdict,
        "global_us_options_bias": options_bias,
        "manual_review_required": True,
        "missing_data": ["Full macro JSON not extracted — review brief manually"],
    }


def _enforce_permissions(path):
    try:
        content = path.read_text(encoding="utf-8")
        lines = content.split('\n')
        if not lines:
            return
        header = lines[0].split(',')
        ep_idx = next((i for i,h in enumerate(header) if 'execution_permission' in h.lower()), None)
        cg_idx = next((i for i,h in enumerate(header) if 'capital_grade' in h.lower()), None)
        if ep_idx is None:
            return
        fixed = [lines[0]]
        for line in lines[1:]:
            if not line.strip():
                continue
            parts = line.split(',')
            max_idx = max(x for x in [ep_idx, cg_idx] if x is not None)
            while len(parts) <= max_idx:
                parts.append('')
            parts[ep_idx] = EXECUTION_PERMISSION
            if cg_idx is not None:
                parts[cg_idx] = CAPITAL_GRADE
            fixed.append(','.join(parts))
        path.write_text('\n'.join(fixed), encoding="utf-8")
    except Exception:
        pass


def _verdict_color(verdict):
    if any(x in verdict for x in ['RISK_ON','SUPPORTIVE','STIMULUS']):
        return "#22c55e"
    if any(x in verdict for x in ['RISK_OFF','DEFENSIVE','PRESSURE']):
        return "#ef4444"
    return "#f59e0b"


def _md_to_html(text):
    text = text.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")
    text = re.sub(r'^### (.+)$', r'<h3>\1</h3>', text, flags=re.MULTILINE)
    text = re.sub(r'^## (.+)$', r'<h2>\1</h2>', text, flags=re.MULTILINE)
    text = re.sub(r'^# (.+)$', r'<h1>\1</h1>', text, flags=re.MULTILINE)
    text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
    lines = text.split('\n')
    result = []
    in_table = False
    table_rows = []
    for line in lines:
        s = line.strip()
        if s.startswith('|') and '|' in s[1:]:
            if not in_table:
                in_table = True
                table_rows = []
            if re.match(r'^\|[\s\-|]+\|$', s):
                continue
            cells = [c.strip() for c in s.split('|')[1:-1]]
            table_rows.append(cells)
        else:
            if in_table and table_rows:
                result.append(_render_table(table_rows))
                table_rows = []
                in_table = False
            result.append(line)
    if in_table and table_rows:
        result.append(_render_table(table_rows))
    text = '\n'.join(result)
    parts = []
    for para in re.split(r'\n{2,}', text):
        para = para.strip()
        if not para:
            continue
        if para.startswith('<h') or para.startswith('<table'):
            parts.append(para)
        elif re.match(r'^[-*] ', para):
            items = re.split(r'\n[-*] ', para)
            items = [i.lstrip('-* ') for i in items if i.strip()]
            parts.append('<ul>' + ''.join(f'<li>{i}</li>' for i in items) + '</ul>')
        else:
            parts.append(f'<p>{para.replace(chr(10), " ")}</p>')
    return '\n'.join(parts)


def _render_table(rows):
    if not rows:
        return ''
    html = '<table>\n<tr>' + ''.join(f'<th>{c}</th>' for c in rows[0]) + '</tr>\n'
    for row in rows[1:]:
        html += '<tr>' + ''.join(f'<td>{c}</td>' for c in row) + '</tr>\n'
    return html + '</table>'


def _extract_section(response, tag):
    pattern = rf'\[{tag}\](.*?)(?=\[[A-Z_]+\]|$)'
    m = re.search(pattern, response, re.DOTALL | re.IGNORECASE)
    return m.group(1).strip() if m else ""


def _csv_to_table(csv_text, max_cols=8):
    """Convert raw CSV text into an HTML table, showing only key columns."""
    if not csv_text.strip():
        return "<p>No data.</p>"
    try:
        import csv as _csv, io as _io
        clean = re.sub(r'```[a-z]*', '', csv_text).replace('```', '').strip()
        reader = list(_csv.DictReader(_io.StringIO(clean)))
        if not reader:
            return "<p>No rows.</p>"

        # Key columns to display in the HTML table
        priority_cols = [
            'ticker', 'company', 'sector', 'directional_bias', 'upload_priority',
            'anis_total_score', 'fips_score', 'confidence_score',
            'event_category', 'event_status', 'suggested_avshunter_review',
            'forward_impact_horizon', 'key_catalyst', 'key_risk', 'why_analyse'
        ]
        available = list(reader[0].keys())
        cols = [c for c in priority_cols if c in available]
        if not cols:
            cols = available[:max_cols]

        bias_colours = {
            'LONG_CALL_WATCH': ('#00c853', '#003300'),
            'LONG_PUT_WATCH': ('#ff3d3d', '#1a0000'),
            'WATCH_ONLY': ('#f59e0b', '#1a1200'),
            'CONTEXT_ONLY': ('#64748b', '#111'),
            'NO_ACTION': ('#334155', '#0a0a0a'),
        }
        priority_colours = {
            'HIGH': ('#00c853', '#003300'),
            'MEDIUM': ('#f59e0b', '#1a1200'),
            'LOW': ('#64748b', '#0a0a0a'),
        }

        hdr = ''.join(f'<th>{c.replace("_"," ").title()}</th>' for c in cols)
        rows_html = ''
        for row in reader:
            cells = ''
            for col in cols:
                val = str(row.get(col, '')).strip()
                style = ''
                if col == 'directional_bias' and val in bias_colours:
                    fg, bg = bias_colours[val]
                    style = f'color:{fg};background:{bg};font-weight:700;font-size:11px;padding:3px 6px;border-radius:3px;'
                elif col == 'upload_priority' and val in priority_colours:
                    fg, bg = priority_colours[val]
                    style = f'color:{fg};background:{bg};font-weight:700;font-size:11px;padding:3px 6px;border-radius:3px;'
                elif col in ('anis_total_score', 'fips_score', 'confidence_score'):
                    try:
                        n = int(val)
                        c = '#00c853' if n >= 75 else ('#f59e0b' if n >= 60 else '#ef4444')
                        style = f'color:{c};font-weight:700;font-family:var(--mono);'
                    except: pass
                elif col == 'ticker':
                    style = 'font-weight:700;font-family:var(--mono);font-size:14px;color:#e2e8f0;'
                elif col in ('why_analyse', 'key_catalyst', 'key_risk'):
                    style = 'font-size:12px;color:#94a3b8;max-width:240px;'
                cells += f'<td style="{style}">{val}</td>'
            rows_html += f'<tr>{cells}</tr>'
        return f'''<div style="overflow-x:auto"><table class="data-tbl">
<thead><tr>{hdr}</tr></thead>
<tbody>{rows_html}</tbody>
</table></div>'''
    except Exception as e:
        return f"<p>CSV parse error: {e}</p>"


def _build_html(response, session, ts, mode="full"):
    date_str = datetime.now().strftime("%A %d %B %Y")
    time_str = datetime.now().strftime("%H:%M ET")
    desk_verdict = session.desk_verdict or "PENDING"
    options_regime = session.options_regime or "—"
    dte = session.dte_preference or "—"
    vc = _verdict_color(desk_verdict)
    rc = "#ef4444" if "PUT" in options_regime else "#22c55e" if "CALL" in options_regime else "#f59e0b"

    # Extract individual sections cleanly
    exec_summary   = _extract_section(response, "EXECUTIVE_SUMMARY")
    global_session = _extract_section(response, "GLOBAL_SESSION")
    narratives     = _extract_section(response, "NARRATIVES")
    transmission   = _extract_section(response, "TRANSMISSION")
    index_impact   = _extract_section(response, "US_INDEX_IMPACT")
    sector_rot     = _extract_section(response, "SECTOR_ROTATION")
    options_imp    = _extract_section(response, "OPTIONS_IMPACT")
    ben_losers     = _extract_section(response, "BENEFICIARIES_LOSERS")
    companies      = _extract_section(response, "COMPANIES_WORTH_ANALYSING")
    handoff        = _extract_section(response, "AVSHUNTER_HANDOFF")
    validation     = _extract_section(response, "VALIDATION_CHECKLIST")
    conf_table     = _extract_section(response, "CONFIRMED_ASSUMPTION_MISSING")
    desk_v_text    = _extract_section(response, "DESK_VERDICT")
    ticker_csv_raw = _extract_section(response, "TICKER_CSV_DATA")
    handoff_csv_raw= _extract_section(response, "HANDOFF_CSV_DATA")

    # MNA sections
    if not exec_summary:
        exec_summary = _extract_section(response, "MNA_EXECUTIVE_SUMMARY") or                        _extract_section(response, "SECTOR_EXECUTIVE_SUMMARY") or                        _extract_section(response, "EVENT_SUMMARY")

    # Build candidate table from CSV data
    candidates_table = _csv_to_table(ticker_csv_raw) if ticker_csv_raw else ""

    if mode == "trader":
        brand  = "AVSHUNTER INTELLIGENCE BRIEF"
        footer = "For analysis purposes only. Not investment advice."
    else:
        brand  = "AVSHUNTER NEWS TERMINAL v1.3"
        footer = f"Execution Permission: {EXECUTION_PERMISSION} | Capital Grade: {CAPITAL_GRADE}"

    def sec(title, body, icon="▶"):
        if not body or not body.strip():
            return ""
        return f'''<div class="section">
          <div class="sec-hdr">{icon} {title}</div>
          <div class="sec-body brief-content">{_md_to_html(body)}</div>
        </div>'''

    # Build sections based on mode
    sections = sec("Executive Summary", exec_summary, "◈")
    sections += sec("Global Session Snapshot", global_session)
    sections += sec("Top Narratives", narratives)
    sections += sec("Macro Transmission", transmission)
    sections += sec("US Index Impact", index_impact)

    # Candidate table — rendered from CSV, not raw text
    if candidates_table:
        sections += f'''<div class="section">
          <div class="sec-hdr">◈ Companies Worth Watching</div>
          <div class="sec-body">{candidates_table}</div>
        </div>'''
    elif companies:
        sections += sec("Companies Worth Analysing", companies, "◈")

    sections += sec("Sector Rotation", sector_rot)
    sections += sec("Options Regime", options_imp)
    sections += sec("Beneficiaries & Losers", ben_losers)

    if mode == "full":
        sections += sec("AVSHUNTER Handoff", handoff)
        sections += sec("Manual Validation Checklist", validation)
        sections += sec("Confirmed / Assumption / Missing", conf_table)
        sections += sec("Desk Verdict", desk_v_text)

    return f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>AVSHUNTER News Terminal — {date_str}</title>
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@300;400;500;600&display=swap');
:root{{
  --bg:#0a0c0f;--bg2:#111318;--bg3:#1a1d24;--border:#2a2d36;
  --accent:#00d4aa;--accent2:#0080ff;--warn:#f59e0b;
  --danger:#ef4444;--success:#22c55e;
  --text:#e2e8f0;--text2:#94a3b8;--text3:#64748b;
  --mono:'IBM Plex Mono',monospace;--sans:'IBM Plex Sans',sans-serif;
}}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:var(--bg);color:var(--text);font-family:var(--sans);font-size:14px;line-height:1.7;min-height:100vh}}
.hdr{{background:var(--bg2);border-bottom:2px solid var(--accent);padding:24px 36px;display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:16px}}
.brand{{font-family:var(--mono);font-size:10px;color:var(--accent);letter-spacing:.15em;text-transform:uppercase;margin-bottom:6px}}
.title{{font-family:var(--mono);font-size:22px;font-weight:600;color:var(--text);letter-spacing:-.02em}}
.meta{{font-family:var(--mono);font-size:11px;color:var(--text3);margin-top:6px}}
.badges{{display:flex;flex-direction:column;align-items:flex-end;gap:8px}}
.vbadge,.rbadge{{font-family:var(--mono);font-size:10px;font-weight:600;letter-spacing:.08em;padding:5px 12px;border-radius:3px}}
.vbadge{{background:{vc}22;color:{vc};border:1px solid {vc}55}}
.rbadge{{background:{rc}22;color:{rc};border:1px solid {rc}55}}
.banner{{background:#1a0505;border-bottom:1px solid #440000;padding:8px 36px;font-family:var(--mono);font-size:11px;color:#ff5555;letter-spacing:.08em;text-align:center}}
.stats{{display:flex;gap:12px;flex-wrap:wrap;padding:20px 36px;background:var(--bg2);border-bottom:1px solid var(--border)}}
.stat{{background:var(--bg);border:1px solid var(--border);border-radius:4px;padding:10px 16px;min-width:130px}}
.slbl{{font-family:var(--mono);font-size:9px;color:var(--text3);letter-spacing:.12em;text-transform:uppercase;margin-bottom:5px}}
.sval{{font-family:var(--mono);font-size:13px;font-weight:600;color:var(--accent)}}
.content{{max-width:1280px;margin:0 auto;padding:28px 36px}}
.section{{margin-bottom:24px;background:var(--bg2);border:1px solid var(--border);border-radius:6px;overflow:hidden}}
.sec-hdr{{background:var(--bg3);border-bottom:1px solid var(--border);padding:11px 20px;font-family:var(--mono);font-size:11px;font-weight:600;color:var(--accent);letter-spacing:.1em;text-transform:uppercase}}
.sec-body{{padding:20px 24px}}
.brief-content p{{margin-bottom:10px;color:var(--text2);line-height:1.75}}
.brief-content h1,.brief-content h2,.brief-content h3{{font-family:var(--mono);color:var(--accent);margin:20px 0 10px;font-size:12px;letter-spacing:.1em;text-transform:uppercase;border-bottom:1px solid var(--border);padding-bottom:6px}}
.brief-content table{{width:100%;border-collapse:collapse;margin:14px 0;font-family:var(--mono);font-size:12px}}
.brief-content th{{background:var(--bg3);color:var(--text3);padding:7px 12px;text-align:left;border:1px solid var(--border);font-size:10px;letter-spacing:.06em;text-transform:uppercase}}
.brief-content td{{padding:7px 12px;border:1px solid var(--border);color:var(--text);vertical-align:top}}
.brief-content tr:nth-child(even) td{{background:var(--bg3)}}
.brief-content ul{{margin:8px 0 12px 20px;color:var(--text2)}}
.brief-content li{{margin-bottom:5px;line-height:1.6}}
.brief-content strong{{color:var(--text);font-weight:600}}
.data-tbl{{width:100%;border-collapse:collapse;font-family:var(--mono);font-size:12px}}
.data-tbl th{{background:var(--bg3);color:var(--text3);padding:8px 14px;text-align:left;border:1px solid var(--border);font-size:10px;letter-spacing:.08em;text-transform:uppercase;white-space:nowrap}}
.data-tbl td{{padding:8px 14px;border:1px solid var(--border);vertical-align:top;line-height:1.5}}
.data-tbl tr:hover td{{background:#1a1d24}}
.footer{{border-top:1px solid var(--border);padding:16px 36px;background:var(--bg2);display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px;margin-top:8px}}
.ftr-l{{font-family:var(--mono);font-size:10px;color:var(--danger);font-weight:600}}
.ftr-r{{font-family:var(--mono);font-size:10px;color:var(--text3)}}
</style></head><body>
<div class="hdr">
  <div>
    <div class="brand">{brand}</div>
    <div class="title">Daily Intelligence Brief</div>
    <div class="meta">{date_str} &nbsp;|&nbsp; {time_str} &nbsp;|&nbsp; Run: {ts}</div>
  </div>
  <div class="badges">
    <div class="vbadge">{desk_verdict.replace("_"," ")}</div>
    <div class="rbadge">{options_regime} &nbsp;|&nbsp; DTE {dte}</div>
  </div>
</div>
<div class="banner">⚠&nbsp; EXECUTION PERMISSION: {EXECUTION_PERMISSION} &nbsp;—&nbsp; ANALYSIS ONLY &nbsp;—&nbsp; CAPITAL GRADE: {CAPITAL_GRADE}</div>
<div class="stats">
  <div class="stat"><div class="slbl">Desk Verdict</div><div class="sval" style="font-size:9px;color:{vc}">{desk_verdict.replace("_"," ")}</div></div>
  <div class="stat"><div class="slbl">Options Regime</div><div class="sval" style="color:{rc}">{options_regime}</div></div>
  <div class="stat"><div class="slbl">DTE Preference</div><div class="sval">{dte}</div></div>
  <div class="stat"><div class="slbl">Candidates</div><div class="sval">{len(session.candidates)}</div></div>
  <div class="stat"><div class="slbl">Session</div><div class="sval" style="font-size:11px">{ts}</div></div>
</div>
<div class="content">
{sections}
</div>
<div class="footer">
  <div class="ftr-l">⚠ {footer}</div>
  <div class="ftr-r">AVSHUNTER News Terminal v1.3 &nbsp;|&nbsp; Generated {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</div>
</div>
</body></html>"""


def _build_summary(response, session, ts):
    date_str = datetime.now().strftime("%A %d %B %Y")
    desk_verdict = session.desk_verdict or "PENDING"
    options_regime = session.options_regime or "—"
    dte = session.dte_preference or "—"
    clean = re.sub(r'```.*?```', '', response, flags=re.DOTALL)
    clean = re.sub(r'#+\s', '', clean)
    clean = re.sub(r'\*\*(.+?)\*\*', r'\1', clean)
    clean = re.sub(r'\n{3,}', '\n\n', clean).strip()
    summary = clean[:1200] + "..." if len(clean) > 1200 else clean
    return f"""AVSHUNTER INTELLIGENCE — Daily Brief
{date_str} | {ts[-4:] if len(ts)>=4 else ts} ET
{'='*60}

DESK VERDICT: {desk_verdict}
OPTIONS REGIME: {options_regime} | DTE: {dte}
CANDIDATES: {len(session.candidates)}

{'='*60}
{summary}

{'='*60}
EXECUTION PERMISSION: {EXECUTION_PERMISSION}
CAPITAL GRADE: {CAPITAL_GRADE}
Analysis only. Not investment advice.
Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""

# ── STEP 2: INTEGRATION OUTPUTS (flat news_terminal/outputs/) ─────────────────

_CATALYST_OUTPUT_COLS = [
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


def write_catalyst_csv_v2(response: str, ts: str) -> "Path | None":
    """Write avshunter_catalyst_csv_YYYYMMDD.csv to flat news_terminal/outputs/."""
    import csv as _csv, io as _io
    outputs, _, _ = _get_paths()
    date_str = ts[:8]
    out = outputs / f"avshunter_catalyst_csv_{date_str}.csv"

    raw = _extract_section(response, "CATALYST_CSV_DATA")
    if not raw:
        return None
    clean = _clean_csv_block(raw)
    try:
        rows = list(_csv.DictReader(_io.StringIO(clean)))
    except Exception as e:
        print(f"  ⚠ Catalyst CSV parse: {e}")
        return None
    if not rows:
        return None

    for row in rows:
        row["execution_permission"] = EXECUTION_PERMISSION
        row["capital_grade"] = CAPITAL_GRADE
        for col in _CATALYST_OUTPUT_COLS:
            row.setdefault(col, "")

    with open(out, "w", newline="", encoding="utf-8") as f:
        writer = _csv.DictWriter(f, fieldnames=_CATALYST_OUTPUT_COLS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    print(f"  [CATALYST CSV] {out.name} ({len(rows)} rows)")
    return out


def write_macro_enrichment_delta(response: str, ts: str) -> "Path | None":
    """Write macro enrichment delta JSON to flat news_terminal/outputs/."""
    import json as _json
    outputs, _, _ = _get_paths()
    date_str = ts[:8]
    delta_out = outputs / f"avshunter_macro_enrichment_delta_{date_str}.json"
    latest_out = outputs / "macro_intelligence_latest.json"

    raw = _extract_section(response, "MACRO_ENRICHMENT_DELTA_DATA")
    if not raw:
        raw = _extract_section(response, "MACRO_JSON_DATA")
    if not raw:
        return None

    clean = re.sub(r'```[a-z]*', '', raw).replace('```', '').strip()
    try:
        data = _json.loads(clean)
    except _json.JSONDecodeError:
        return None

    data["execution_permission"] = EXECUTION_PERMISSION
    data["capital_grade"] = CAPITAL_GRADE
    text = _json.dumps(data, indent=2)
    delta_out.write_text(text, encoding="utf-8")
    latest_out.write_text(text, encoding="utf-8")
    print(f"  [MACRO DELTA]  {delta_out.name}")
    print(f"  [MACRO LATEST] macro_intelligence_latest.json")
    return delta_out


def write_tickers_file(response: str, ts: str, catalyst_path=None) -> "Path | None":
    """Write news_terminal_tickers_YYYYMMDD.txt to flat news_terminal/outputs/."""
    import csv as _csv, io as _io
    outputs, _, _ = _get_paths()
    date_str = ts[:8]
    out = outputs / f"news_terminal_tickers_{date_str}.txt"

    tickers = []

    raw = _extract_section(response, "TICKERS_LIST_DATA")
    if raw:
        for line in raw.strip().splitlines():
            t = line.strip().strip(",").strip()
            if t and t.replace(".", "").isalpha() and len(t) <= 6:
                tickers.append(t.upper())

    if catalyst_path and Path(catalyst_path).exists() and not tickers:
        try:
            with open(catalyst_path, "r", encoding="utf-8") as f:
                for row in _csv.DictReader(f):
                    t = row.get("ticker", "").strip()
                    if t and t not in tickers:
                        tickers.append(t)
        except Exception:
            pass

    if not tickers:
        old_raw = _extract_section(response, "TICKER_CSV_DATA")
        if old_raw:
            clean = _clean_csv_block(old_raw)
            try:
                for row in _csv.DictReader(_io.StringIO(clean)):
                    t = (row.get("ticker") or "").strip()
                    if t and t not in tickers:
                        tickers.append(t)
            except Exception:
                pass

    if not tickers:
        return None

    out.write_text("\n".join(sorted(set(tickers))), encoding="utf-8")
    print(f"  [TICKERS]      {len(tickers)} tickers → {out.name}")
    return out


# ── ALIAS for backward compatibility ─────────────────────────────────────────
def write_ticker_csv_only(rows: list, run_dir, ts: str, prefix: str = ""):
    """Alias — write ticker CSV from a pre-parsed row list."""
    from pathlib import Path
    from news_terminal_engine import TICKER_CSV_FIELDS
    pfx = f"{prefix}_" if prefix else ""
    path = Path(run_dir) / f"{pfx}ticker_candidates_{ts}.csv"
    n = _write_csv_rows(rows, path)
    return {"ticker_csv": {"path": path, "rows": n}}

def _write_csv_rows(rows: list, filepath) -> int:
    """Write pre-parsed rows to CSV."""
    if not rows:
        return 0
    from pathlib import Path
    import csv
    filepath = Path(filepath)
    filepath.parent.mkdir(parents=True, exist_ok=True)
    fields = list(rows[0].keys())
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            row["execution_permission"] = "NONE_NEWS_TERMINAL_ONLY"
            row["capital_grade"] = "NO"
            writer.writerow(row)
    return len(rows)
