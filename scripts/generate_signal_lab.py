"""
generate_signal_lab.py
======================
Generates avshunter_intelligence_lab_YYYYMMDD.html from tonight's pipeline outputs.
Run automatically by intelligent_orchestrator.py --evening (Phase 8 - Report)
or manually:

    python scripts/generate_signal_lab.py
    python scripts/generate_signal_lab.py --run-id 20260215_182828

Output: data/output/avshunter_intelligence_lab_YYYYMMDD.html
        Open in any browser — no server, no Python, no internet required.
"""

import os
import sys
import json
import glob
import argparse
import pandas as pd
from datetime import datetime
from pathlib import Path

# ── Paths ──────────────────────────────────────────────────────────────────
BASE_DIR   = Path(__file__).resolve().parent.parent
OUTPUT_DIR = BASE_DIR / "data" / "output"
RUNS_DIR   = OUTPUT_DIR / "runs"

def find_latest_run_id():
    runs = sorted(glob.glob(str(RUNS_DIR / "2*")), reverse=True)
    if runs:
        return Path(runs[0]).name
    return None

def find_latest_csv(pattern):
    files = sorted(glob.glob(str(OUTPUT_DIR / pattern)), reverse=True)
    return files[0] if files else None

def load_data(run_id=None):
    if run_id is None:
        run_id = find_latest_run_id()
    if run_id is None:
        print("ERROR: No run ID found. Run the evening pipeline first.")
        sys.exit(1)

    print(f"Loading run: {run_id}")

    # Discovery candidates
    dc_path = find_latest_csv(f"discovery_candidates_ultimate_{run_id}*.csv")
    if not dc_path:
        dc_path = find_latest_csv("discovery_candidates_ultimate_*.csv")
    if not dc_path:
        print("ERROR: discovery_candidates_ultimate_*.csv not found")
        sys.exit(1)

    # Vanguard signals
    vs_path = str(RUNS_DIR / run_id / "vanguard" / "vanguard_signals.csv")
    if not os.path.exists(vs_path):
        vs_path = find_latest_csv("vanguard_signals*.csv")
    if not vs_path or not os.path.exists(vs_path):
        print("WARNING: vanguard_signals.csv not found — using Discovery only")
        vs_path = None

    dc = pd.read_csv(dc_path)
    print(f"  Discovery: {len(dc)} signals from {dc_path}")

    if vs_path:
        vs = pd.read_csv(vs_path)
        print(f"  Vanguard:  {len(vs)} signals from {vs_path}")
    else:
        vs = pd.DataFrame(columns=['ticker'])

    return dc, vs, run_id

def merge_and_clean(dc, vs):
    vs_cols = [c for c in [
        'ticker','verdict','layer2__expected_value_20d','layer2__win_rate_20d',
        'layer2__edge_quality','layer2__n_observations','layer2__vol_regime',
        'layer2__trend_direction','layer2__trend_maturity','layer2__kelly_fraction',
        'layer1__control','layer1__auction_state'
    ] if c in vs.columns]

    if vs_cols:
        merged = dc.merge(vs[vs_cols], on='ticker', how='left')
    else:
        merged = dc.copy()

    keep = [c for c in [
        'ticker','tier','tier_label','stock_price','entry_price','stop_loss',
        'phase','wyckoff_score','crabel_score','composite_score','win_probability',
        'control_state','crabel_pattern','crabel_state','precor_phase','precor_intent',
        'vwap_bias','volume_ratio','compression_ratio','days_in_range','days_to_trigger',
        'conditions_met','phase_strength','active_regime','signal_type','entry_size','stop_pct',
        'verdict','layer2__expected_value_20d','layer2__win_rate_20d','layer2__edge_quality',
        'layer2__n_observations','layer2__trend_direction','layer2__kelly_fraction','layer1__control'
    ] if c in merged.columns]

    df = merged[keep].copy()
    for col in df.select_dtypes(include='float').columns:
        df[col] = df[col].round(3)
    df = df.fillna('N/A')
    for col in df.columns:
        df[col] = df[col].replace('nan', 'N/A')

    return df

def build_stats(df):
    return {
        'total':   len(df),
        'trade':   int((df.get('verdict','') == 'TRADE').sum()) if 'verdict' in df.columns else 0,
        'tier0':   int((df['tier'] == 0).sum()),
        'tier1':   int((df['tier'] == 1).sum()),
        'tier2':   int((df['tier'] == 2).sum()),
        'phase_c': int((df['phase'] == 'C').sum()) if 'phase' in df.columns else 0,
        'phase_d': int((df['phase'] == 'D').sum()) if 'phase' in df.columns else 0,
        'strong':  int((df.get('layer2__edge_quality','') == 'STRONG').sum()),
        'crabel':  int(df.get('crabel_pattern','').apply(lambda x: x not in ['N/A','nan','']).sum()),
    }

def generate_html(df, run_id, stats):
    data_json = json.dumps(df.to_dict(orient='records'), default=str)
    date_str  = datetime.now().strftime('%d %b %Y')

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AVSHUNTER — Signal Intelligence Lab · {date_str}</title>
<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Mono:wght@400;700&family=Syne:wght@400;600;700;800&display=swap');
:root{{--bg:#05080d;--surface:#0a0f18;--surface2:#0f1520;--border:#1a2535;--accent:#00e5ff;--accent2:#ff6b2b;--green:#00ff88;--warn:#ffc107;--red:#ff3d57;--text:#c8d8e8;--muted:#4a6080;--strong:#ffffff}}
*{{margin:0;padding:0;box-sizing:border-box}}
body{{background:var(--bg);color:var(--text);font-family:'Space Mono',monospace;font-size:13px;height:100vh;overflow:hidden;display:flex;flex-direction:column}}
body::before{{content:'';position:fixed;inset:0;background:radial-gradient(ellipse 80% 50% at 50% -20%,rgba(0,229,255,.06),transparent);pointer-events:none}}
header{{background:var(--surface);border-bottom:1px solid var(--border);padding:0 20px;height:54px;display:flex;align-items:center;gap:20px;flex-shrink:0}}
.logo{{font-family:'Syne',sans-serif;font-size:20px;font-weight:800;letter-spacing:4px;background:linear-gradient(90deg,var(--accent),var(--accent2));-webkit-background-clip:text;-webkit-text-fill-color:transparent}}
.hstats{{display:flex;gap:24px;margin-left:auto}}
.hs{{text-align:right}}
.hs-n{{font-size:16px;font-weight:700;color:var(--accent);font-family:'Syne',sans-serif}}
.hs-l{{font-size:9px;color:var(--muted);letter-spacing:1px;text-transform:uppercase}}
.nlp-zone{{background:var(--surface);border-bottom:1px solid var(--border);padding:12px 20px;flex-shrink:0}}
.nlp-row{{display:flex;gap:8px;align-items:center}}
.nlp-in{{flex:1;background:var(--bg);border:1px solid var(--border);border-radius:4px;padding:9px 14px;color:var(--text);font-family:'Space Mono',monospace;font-size:12px;outline:none;transition:border .2s}}
.nlp-in:focus{{border-color:var(--accent)}}
.nlp-in::placeholder{{color:var(--muted)}}
.btn{{background:var(--accent);border:none;border-radius:4px;padding:9px 16px;color:#000;font-family:'Space Mono',monospace;font-size:11px;font-weight:700;cursor:pointer;letter-spacing:1px;transition:opacity .2s}}
.btn:hover{{opacity:.8}}
.btn-ghost{{background:transparent;border:1px solid var(--border);color:var(--muted)}}
.btn-ghost:hover{{border-color:var(--accent);color:var(--accent);background:transparent}}
.presets{{display:flex;gap:6px;margin-top:8px;flex-wrap:wrap}}
.preset{{background:var(--surface2);border:1px solid var(--border);border-radius:20px;padding:3px 10px;font-size:10px;color:var(--muted);cursor:pointer;transition:all .15s;letter-spacing:.5px}}
.preset:hover{{border-color:var(--accent);color:var(--accent)}}
.edu{{background:linear-gradient(135deg,rgba(0,229,255,.04),rgba(255,107,43,.04));border:1px solid rgba(0,229,255,.15);border-radius:6px;margin:10px 20px;padding:14px 16px;display:none;max-height:200px;overflow-y:auto}}
.edu.on{{display:block}}
.edu-head{{font-size:10px;letter-spacing:2px;color:var(--accent);margin-bottom:8px;text-transform:uppercase}}
.edu-body{{font-size:12px;line-height:1.75;color:var(--text)}}
.edu-body b{{color:var(--accent2)}}
.edu-body .c{{color:var(--accent);font-weight:700}}
.layout{{display:flex;flex:1;overflow:hidden}}
.sidebar{{width:210px;background:var(--surface);border-right:1px solid var(--border);padding:14px 12px;overflow-y:auto;flex-shrink:0}}
.fg{{margin-bottom:18px}}
.ft{{font-size:9px;text-transform:uppercase;letter-spacing:2px;color:var(--muted);margin-bottom:7px}}
.chips{{display:flex;flex-wrap:wrap;gap:4px}}
.chip{{padding:3px 9px;border-radius:3px;font-size:10px;cursor:pointer;border:1px solid var(--border);color:var(--muted);transition:all .15s}}
.chip:hover{{border-color:var(--accent);color:var(--accent)}}
.chip.on{{background:var(--accent);border-color:var(--accent);color:#000;font-weight:700}}
.sldr{{margin-top:5px}}
.sldr label{{font-size:10px;color:var(--muted);display:flex;justify-content:space-between}}
.sldr label span{{color:var(--accent)}}
.sldr input[type=range]{{width:100%;margin-top:4px;accent-color:var(--accent)}}
.tarea{{flex:1;display:flex;flex-direction:column;overflow:hidden}}
.thead-bar{{background:var(--surface);border-bottom:1px solid var(--border);padding:8px 14px;display:flex;align-items:center;gap:12px;flex-shrink:0}}
.rcount{{font-size:12px;color:var(--accent);font-weight:700}}
.sort-sel{{background:var(--surface2);border:1px solid var(--border);border-radius:3px;padding:4px 8px;color:var(--text);font-size:11px;font-family:'Space Mono',monospace;outline:none;cursor:pointer}}
.twrap{{flex:1;overflow-y:auto}}
table{{width:100%;border-collapse:collapse}}
thead th{{background:var(--surface);padding:7px 9px;text-align:left;font-size:9px;text-transform:uppercase;letter-spacing:1.5px;color:var(--muted);border-bottom:1px solid var(--border);position:sticky;top:0;z-index:5;white-space:nowrap;cursor:pointer}}
thead th:hover{{color:var(--accent)}}
tbody tr{{border-bottom:1px solid rgba(26,37,53,.5);cursor:pointer;transition:background .1s}}
tbody tr:hover{{background:var(--surface)}}
tbody tr.sel{{background:rgba(0,229,255,.07)!important;border-left:2px solid var(--accent)}}
td{{padding:6px 9px;font-size:11px;white-space:nowrap}}
.badge{{display:inline-block;padding:2px 7px;border-radius:2px;font-size:9px;font-weight:700;letter-spacing:1px}}
.t0{{background:rgba(255,107,43,.15);color:var(--accent2);border:1px solid rgba(255,107,43,.4)}}
.t1{{background:rgba(0,229,255,.15);color:var(--accent);border:1px solid rgba(0,229,255,.4)}}
.t2{{background:rgba(74,96,128,.15);color:var(--muted);border:1px solid rgba(74,96,128,.3)}}
.pC{{background:rgba(0,255,136,.12);color:var(--green)}}
.pD{{background:rgba(0,229,255,.12);color:var(--accent)}}
.pB{{background:rgba(255,193,7,.12);color:var(--warn)}}
.pA{{background:rgba(74,96,128,.12);color:var(--muted)}}
.vTRADE{{color:var(--green);font-weight:700}}
.vDISCOVERY{{color:var(--accent)}}
.eSTRONG{{color:var(--green);font-weight:700}}
.eMODERATE{{color:var(--warn)}}
.eWEAK{{color:var(--muted)}}
.bar-wrap{{display:flex;align-items:center;gap:5px}}
.bar{{height:3px;border-radius:2px;background:linear-gradient(90deg,var(--accent),var(--accent2))}}
.detail{{width:300px;background:var(--surface);border-left:1px solid var(--border);overflow-y:auto;flex-shrink:0}}
.d-empty{{display:flex;flex-direction:column;align-items:center;justify-content:center;height:100%;color:var(--muted);text-align:center;padding:20px;font-size:11px;line-height:1.8}}
.d-empty-icon{{font-size:32px;margin-bottom:10px;opacity:.25}}
.d-body{{padding:16px}}
.d-ticker{{font-family:'Syne',sans-serif;font-size:32px;font-weight:800;color:var(--strong);letter-spacing:2px}}
.d-sub{{font-size:9px;color:var(--muted);letter-spacing:1px;margin-bottom:14px;text-transform:uppercase}}
.ds{{background:var(--surface2);border:1px solid var(--border);border-radius:5px;padding:11px;margin-bottom:11px}}
.dst{{font-size:9px;text-transform:uppercase;letter-spacing:1.5px;color:var(--muted);margin-bottom:8px}}
.dr{{display:flex;justify-content:space-between;align-items:center;margin-bottom:5px}}
.dl{{font-size:10px;color:var(--muted)}}
.dv{{font-size:11px;color:var(--text);font-weight:700}}
.dv.pos{{color:var(--green)}}.dv.neg{{color:var(--red)}}.dv.hl{{color:var(--accent)}}
.ev-bar{{background:var(--bg);border-radius:3px;height:5px;margin-top:6px;overflow:hidden}}
.ev-fill{{height:100%;border-radius:3px;transition:width .4s}}
.tc{{background:var(--surface2);border:1px solid var(--border);border-radius:4px;padding:9px 10px;margin-bottom:7px;font-size:11px;line-height:1.65;color:var(--text)}}
.tc-head{{font-size:9px;text-transform:uppercase;letter-spacing:1px;margin-bottom:5px}}
.tc.good{{border-color:rgba(0,255,136,.2)}}.tc.good .tc-head{{color:var(--green)}}
.tc.warn{{border-color:rgba(255,193,7,.2)}}.tc.warn .tc-head{{color:var(--warn)}}
.tc.bad{{border-color:rgba(255,61,87,.2)}}.tc.bad .tc-head{{color:var(--red)}}
::-webkit-scrollbar{{width:4px;height:4px}}
::-webkit-scrollbar-track{{background:transparent}}
::-webkit-scrollbar-thumb{{background:var(--border);border-radius:2px}}
</style>
</head>
<body>
<header>
  <div class="logo">AVSHUNTER</div>
  <div style="font-size:9px;color:var(--muted);letter-spacing:2px">SIGNAL INTELLIGENCE LAB · {date_str.upper()} · RUN {run_id}</div>
  <div class="hstats">
    <div class="hs"><div class="hs-n">{stats['total']:,}</div><div class="hs-l">Universe</div></div>
    <div class="hs"><div class="hs-n" style="color:var(--green)">{stats['trade']}</div><div class="hs-l">TRADE</div></div>
    <div class="hs"><div class="hs-n">{stats['tier1']}</div><div class="hs-l">Tier 1</div></div>
    <div class="hs"><div class="hs-n" id="h-filtered" style="color:var(--warn)">—</div><div class="hs-l">Filtered</div></div>
  </div>
</header>

<div class="nlp-zone">
  <div class="nlp-row">
    <input class="nlp-in" id="q" placeholder="Ask: show me Phase C TRADE signals with NR7 compression... or: explain wyckoff spring entry..." onkeydown="if(event.key==='Enter')runQ()">
    <button class="btn" onclick="runQ()">ANALYSE</button>
    <button class="btn btn-ghost" onclick="reset()">RESET</button>
  </div>
  <div class="presets">
    <div class="preset" onclick="q('best TRADE signals Phase C')">🎯 TRADE + Phase C</div>
    <div class="preset" onclick="q('Crabel NR7 compression')">📦 NR7 Compression</div>
    <div class="preset" onclick="q('strong edge quality STRONG')">💎 Strong Edge</div>
    <div class="preset" onclick="q('Phase D breakout Tier 1')">🚀 Phase D</div>
    <div class="preset" onclick="q('Tier 0 early position')">⏰ Early Entries</div>
    <div class="preset" onclick="q('buyers in control TRADE')">🐂 Buyers In Control</div>
    <div class="preset" onclick="q('what is wyckoff phase C spring')">📚 Teach: Phase C</div>
    <div class="preset" onclick="q('explain crabel NR7 compression edge')">📚 Teach: Crabel</div>
    <div class="preset" onclick="q('how does vanguard actuarial ev work')">📚 Teach: Actuarial EV</div>
    <div class="preset" onclick="q('how to read compression ratio coil')">📚 Teach: Compression</div>
    <div class="preset" onclick="q('explain control state buyer seller equilibrium')">📚 Teach: Control</div>
  </div>
</div>

<div class="edu" id="edu">
  <div class="edu-head" id="edu-h"></div>
  <div class="edu-body" id="edu-b"></div>
</div>

<div class="layout">
  <div class="sidebar">
    <div class="fg"><div class="ft">Tier</div><div class="chips">
      <div class="chip on" data-f="tier" data-v="all" onclick="fc(this)">ALL</div>
      <div class="chip" data-f="tier" data-v="0" onclick="fc(this)">T0 Early</div>
      <div class="chip" data-f="tier" data-v="1" onclick="fc(this)">T1 Confirmed</div>
      <div class="chip" data-f="tier" data-v="2" onclick="fc(this)">T2 Observe</div>
    </div></div>
    <div class="fg"><div class="ft">Wyckoff Phase</div><div class="chips">
      <div class="chip on" data-f="phase" data-v="all" onclick="fc(this)">ALL</div>
      <div class="chip" data-f="phase" data-v="C" onclick="fc(this)">C Spring</div>
      <div class="chip" data-f="phase" data-v="D" onclick="fc(this)">D Markup</div>
      <div class="chip" data-f="phase" data-v="B" onclick="fc(this)">B Range</div>
      <div class="chip" data-f="phase" data-v="A" onclick="fc(this)">A Stop</div>
    </div></div>
    <div class="fg"><div class="ft">Vanguard Verdict</div><div class="chips">
      <div class="chip on" data-f="verdict" data-v="all" onclick="fc(this)">ALL</div>
      <div class="chip" data-f="verdict" data-v="TRADE" onclick="fc(this)">TRADE</div>
      <div class="chip" data-f="verdict" data-v="DISCOVERY" onclick="fc(this)">DISCOVERY</div>
    </div></div>
    <div class="fg"><div class="ft">Edge Quality</div><div class="chips">
      <div class="chip on" data-f="eq" data-v="all" onclick="fc(this)">ALL</div>
      <div class="chip" data-f="eq" data-v="STRONG" onclick="fc(this)">STRONG</div>
      <div class="chip" data-f="eq" data-v="MODERATE" onclick="fc(this)">MODERATE</div>
      <div class="chip" data-f="eq" data-v="WEAK" onclick="fc(this)">WEAK</div>
    </div></div>
    <div class="fg"><div class="ft">Control State</div><div class="chips">
      <div class="chip on" data-f="ctrl" data-v="all" onclick="fc(this)">ALL</div>
      <div class="chip" data-f="ctrl" data-v="BUYER" onclick="fc(this)">BUYERS</div>
      <div class="chip" data-f="ctrl" data-v="EQUILIBRIUM" onclick="fc(this)">EQUIL</div>
      <div class="chip" data-f="ctrl" data-v="SELLER" onclick="fc(this)">SELLERS</div>
      <div class="chip" data-f="ctrl" data-v="SHIFTING" onclick="fc(this)">SHIFTING</div>
    </div></div>
    <div class="fg"><div class="ft">Crabel Pattern</div><div class="chips">
      <div class="chip on" data-f="crbl" data-v="all" onclick="fc(this)">ALL</div>
      <div class="chip" data-f="crbl" data-v="NR7" onclick="fc(this)">NR7</div>
      <div class="chip" data-f="crbl" data-v="ID" onclick="fc(this)">ID</div>
      <div class="chip" data-f="crbl" data-v="Extreme" onclick="fc(this)">Extreme</div>
      <div class="chip" data-f="crbl" data-v="Moderate" onclick="fc(this)">Moderate</div>
      <div class="chip" data-f="crbl" data-v="NONE" onclick="fc(this)">None</div>
    </div></div>
    <div class="fg"><div class="ft">VWAP Bias</div><div class="chips">
      <div class="chip on" data-f="vwap" data-v="all" onclick="fc(this)">ALL</div>
      <div class="chip" data-f="vwap" data-v="ABOVE" onclick="fc(this)">ABOVE</div>
      <div class="chip" data-f="vwap" data-v="BELOW" onclick="fc(this)">BELOW</div>
    </div></div>
    <div class="fg"><div class="ft">Min Composite Score</div><div class="sldr">
      <label>Score &ge; <span id="sv">60</span></label>
      <input type="range" min="50" max="85" value="60" step="0.5" oninput="document.getElementById('sv').textContent=this.value;applyF()">
    </div></div>
    <div class="fg"><div class="ft">Min Win Probability</div><div class="sldr">
      <label>Win Prob &ge; <span id="wp">50</span>%</label>
      <input type="range" min="0" max="80" value="50" step="1" oninput="document.getElementById('wp').textContent=this.value;applyF()">
    </div></div>
    <div class="fg"><div class="ft">Min EV 20d</div><div class="sldr">
      <label>EV &ge; <span id="ev">0</span>%</label>
      <input type="range" min="0" max="4" value="0" step="0.5" oninput="document.getElementById('ev').textContent=this.value;applyF()">
    </div></div>
  </div>

  <div class="tarea">
    <div class="thead-bar">
      <div class="rcount" id="rc">— signals</div>
      <div style="margin-left:auto;display:flex;gap:8px;align-items:center">
        <span style="font-size:10px;color:var(--muted)">SORT</span>
        <select class="sort-sel" onchange="sortBy(this.value)">
          <option value="composite_score">Composite Score</option>
          <option value="layer2__expected_value_20d">EV 20d</option>
          <option value="layer2__win_rate_20d">Win Rate</option>
          <option value="wyckoff_score">Wyckoff Score</option>
          <option value="win_probability">Win Probability</option>
          <option value="compression_ratio">Compression Ratio</option>
          <option value="days_to_trigger">Days to Trigger</option>
        </select>
      </div>
    </div>
    <div class="twrap">
      <table>
        <thead><tr>
          <th>TICKER</th><th>TIER</th><th>PHASE</th><th>SCORE</th>
          <th>CRABEL</th><th>CONTROL</th><th>VWAP</th>
          <th>VERDICT</th><th>EDGE</th><th>EV 20D</th>
          <th>WIN%</th><th>N OBS</th><th>ENTRY</th><th>STOP</th><th>RISK%</th>
        </tr></thead>
        <tbody id="tb"></tbody>
      </table>
    </div>
  </div>

  <div class="detail" id="detail">
    <div class="d-empty" id="de">
      <div class="d-empty-icon">⚡</div>
      <div>Click any signal<br>for full analysis<br>+ edge education</div>
    </div>
    <div class="d-body" id="db" style="display:none"></div>
  </div>
</div>

<script>
const SIGNALS={data_json};
let filt=[],sel=null,sortF='composite_score';
const F={{tier:'all',phase:'all',verdict:'all',eq:'all',ctrl:'all',crbl:'all',vwap:'all'}};

function fc(el){{
  const f=el.dataset.f,v=el.dataset.v;F[f]=v;
  document.querySelectorAll(`.chip[data-f="${{f}}"]`).forEach(c=>c.classList.remove('on'));
  el.classList.add('on');applyF();
}}

function applyF(){{
  const r=document.querySelectorAll('input[type=range]');
  const minS=parseFloat(r[0]?.value||60),minW=parseFloat(r[1]?.value||50),minEV=parseFloat(r[2]?.value||0);
  filt=SIGNALS.filter(s=>{{
    if(F.tier!=='all'&&String(s.tier)!==F.tier)return false;
    if(F.phase!=='all'&&s.phase!==F.phase)return false;
    if(F.verdict!=='all'&&s.verdict!==F.verdict)return false;
    if(F.eq!=='all'&&s.layer2__edge_quality!==F.eq)return false;
    if(F.ctrl!=='all'&&!String(s.control_state).includes(F.ctrl))return false;
    if(F.crbl!=='all'){{
      if(F.crbl==='NONE'){{if(s.crabel_pattern&&s.crabel_pattern!=='N/A'&&s.crabel_pattern!=='nan')return false;}}
      else{{if(!String(s.crabel_pattern).includes(F.crbl))return false;}}
    }}
    if(F.vwap!=='all'&&s.vwap_bias!==F.vwap)return false;
    if((s.composite_score||0)<minS)return false;
    if((s.win_probability||0)<minW)return false;
    if(((s.layer2__expected_value_20d||0)*100)<minEV)return false;
    return true;
  }});
  filt.sort((a,b)=>(b[sortF]||0)-(a[sortF]||0));
  render();
  document.getElementById('rc').textContent=filt.length+' signals';
  document.getElementById('h-filtered').textContent=filt.length;
}}

function sortBy(f){{sortF=f;applyF();}}

function render(){{
  const rows=filt.slice(0,300);
  document.getElementById('tb').innerHTML=rows.map(s=>{{
    const ev=((s.layer2__expected_value_20d||0)*100).toFixed(2);
    const wr=((s.layer2__win_rate_20d||0)*100).toFixed(0);
    const nobs=s.layer2__n_observations&&s.layer2__n_observations!=='N/A'?(+s.layer2__n_observations/1000).toFixed(0)+'K':'—';
    const sw=Math.max(0,Math.min(50,((s.composite_score-50)/35)*50));
    const cp=String(s.crabel_pattern||'');
    const cd=cp==='N/A'||cp==='nan'||!cp?'—':cp.split('+')[0];
    const cs=String(s.control_state||'').replace('_IN_CONTROL','').replace(/_/g,' ');
    const risk=s.stop_pct&&s.stop_pct!=='N/A'?`${{(+s.stop_pct).toFixed(1)}}%`:'—';
    const entry=s.entry_price&&s.entry_price!=='N/A'?`$${{(+s.entry_price).toFixed(2)}}`:'—';
    const stop=s.stop_loss&&s.stop_loss!=='N/A'&&+s.stop_loss>0?`$${{(+s.stop_loss).toFixed(2)}}`:'—';
    const ctrlCol=s.control_state?.includes('BUYER')?'var(--green)':s.control_state?.includes('SELLER')?'var(--red)':'var(--muted)';
    const evCol=+ev>=3?'var(--green)':+ev>=1.5?'var(--warn)':'var(--muted)';
    const wrCol=+wr>=40?'var(--green)':+wr>=35?'var(--warn)':'var(--muted)';
    return `<tr onclick="pick('${{s.ticker}}')" id="r-${{s.ticker}}">
      <td style="color:var(--strong);font-weight:700">${{s.ticker}}</td>
      <td><span class="badge t${{s.tier}}">T${{s.tier}}</span></td>
      <td><span class="badge p${{s.phase}}">${{s.phase}}</span></td>
      <td><div class="bar-wrap"><div class="bar" style="width:${{sw}}px"></div><span>${{(+s.composite_score).toFixed(1)}}</span></div></td>
      <td style="color:${{cp.includes('NR7')||cp.includes('ID')?'var(--accent2)':'var(--muted)'}}">${{cd}}</td>
      <td style="font-size:10px;color:${{ctrlCol}}">${{cs}}</td>
      <td style="color:${{s.vwap_bias==='ABOVE'?'var(--green)':'var(--muted)'}};font-size:10px">${{s.vwap_bias||'—'}}</td>
      <td><span class="v${{s.verdict||'NONE'}}">${{s.verdict||'—'}}</span></td>
      <td><span class="e${{s.layer2__edge_quality||'NONE'}}">${{s.layer2__edge_quality||'—'}}</span></td>
      <td style="color:${{evCol}}">${{ev}}%</td>
      <td style="color:${{wrCol}}">${{wr}}%</td>
      <td style="color:var(--muted)">${{nobs}}</td>
      <td>${{entry}}</td><td style="color:var(--red)">${{stop}}</td><td style="color:var(--muted)">${{risk}}</td>
    </tr>`;
  }}).join('');
}}

function pick(t){{
  sel=t;const s=SIGNALS.find(x=>x.ticker===t);if(!s)return;
  document.querySelectorAll('tbody tr').forEach(r=>r.classList.remove('sel'));
  const row=document.getElementById(`r-${{t}}`);
  if(row){{row.classList.add('sel');row.scrollIntoView({{block:'nearest'}});}}
  document.getElementById('de').style.display='none';
  document.getElementById('db').style.display='block';
  renderDetail(s);
}}

function renderDetail(s){{
  const ev=((s.layer2__expected_value_20d||0)*100).toFixed(2);
  const wr=((s.layer2__win_rate_20d||0)*100).toFixed(1);
  const nobs=s.layer2__n_observations&&s.layer2__n_observations!=='N/A'?(+s.layer2__n_observations).toLocaleString():'N/A';
  const kelly=s.layer2__kelly_fraction&&s.layer2__kelly_fraction!=='N/A'?((+s.layer2__kelly_fraction)*100).toFixed(1)+'%':'N/A';
  const risk=s.entry_price&&s.stop_loss&&+s.stop_loss>0?(((+s.entry_price-+s.stop_loss)/+s.entry_price)*100).toFixed(2)+'%':'N/A';
  const cards=buildCards(s);
  document.getElementById('db').innerHTML=`
    <div class="d-ticker">${{s.ticker}}</div>
    <div class="d-sub">${{s.tier_label||''}} · PHASE ${{s.phase}} · ${{s.layer2__vol_regime||'—'}}</div>
    <div class="ds"><div class="dst">Discovery Scoring</div>
      <div class="dr"><span class="dl">Composite Score</span><span class="dv hl">${{(+s.composite_score).toFixed(1)}}</span></div>
      <div class="dr"><span class="dl">Wyckoff Score</span><span class="dv">${{(+s.wyckoff_score||0).toFixed(1)}}</span></div>
      <div class="dr"><span class="dl">Win Probability</span><span class="dv ${{+s.win_probability>=55?'pos':''}}">${{(+s.win_probability||0).toFixed(1)}}%</span></div>
      <div class="dr"><span class="dl">Conditions Met</span><span class="dv">${{s.conditions_met||'—'}}</span></div>
      <div class="dr"><span class="dl">Compression Ratio</span><span class="dv ${{+s.compression_ratio<0.65?'pos':''}}">${{(+s.compression_ratio||0).toFixed(3)}}</span></div>
      <div class="dr"><span class="dl">Days in Range</span><span class="dv">${{s.days_in_range||'—'}}</span></div>
      <div class="dr"><span class="dl">Days to Trigger</span><span class="dv">${{s.days_to_trigger||'—'}}</span></div>
    </div>
    <div class="ds"><div class="dst">Pattern Intelligence</div>
      <div class="dr"><span class="dl">Phase</span><span class="dv hl">Phase ${{s.phase}}</span></div>
      <div class="dr"><span class="dl">Crabel Pattern</span><span class="dv ${{s.crabel_pattern&&s.crabel_pattern!=='N/A'?'pos':''}}">${{s.crabel_pattern||'—'}}</span></div>
      <div class="dr"><span class="dl">Control State</span><span class="dv ${{s.control_state?.includes('BUYER')?'pos':s.control_state?.includes('SELLER')?'neg':''}}">${{s.control_state||'—'}}</span></div>
      <div class="dr"><span class="dl">VWAP Bias</span><span class="dv ${{s.vwap_bias==='ABOVE'?'pos':''}}">${{s.vwap_bias||'—'}}</span></div>
      <div class="dr"><span class="dl">Volume Ratio</span><span class="dv ${{+s.volume_ratio>=1.2?'pos':''}}">${{(+s.volume_ratio||0).toFixed(2)}}x</span></div>
      <div class="dr"><span class="dl">Trend Direction</span><span class="dv">${{s.layer2__trend_direction||'—'}}</span></div>
    </div>
    <div class="ds"><div class="dst">Actuarial (${{nobs}} obs)</div>
      <div class="dr"><span class="dl">Verdict</span><span class="dv v${{s.verdict}}">${{s.verdict||'—'}}</span></div>
      <div class="dr"><span class="dl">Edge Quality</span><span class="dv e${{s.layer2__edge_quality}}">${{s.layer2__edge_quality||'—'}}</span></div>
      <div class="dr"><span class="dl">EV 20d</span><span class="dv ${{+ev>=3?'pos':+ev>=1.5?'':'neg'}}">${{ev}}%</span></div>
      <div class="dr"><span class="dl">Win Rate</span><span class="dv ${{+wr>=40?'pos':''}}">${{wr}}%</span></div>
      <div class="dr"><span class="dl">Kelly Fraction</span><span class="dv">${{kelly}}</span></div>
      <div class="ev-bar"><div class="ev-fill" style="width:${{Math.min(100,+ev/5*100)}}%;background:${{+ev>=3?'var(--green)':+ev>=1.5?'var(--warn)':'var(--muted)'}}"></div></div>
    </div>
    <div class="ds"><div class="dst">Trade Parameters</div>
      <div class="dr"><span class="dl">Entry</span><span class="dv hl">$${{(+s.entry_price||0).toFixed(2)}}</span></div>
      <div class="dr"><span class="dl">Stop</span><span class="dv neg">${{+s.stop_loss>0?'$'+(+s.stop_loss).toFixed(2):'—'}}</span></div>
      <div class="dr"><span class="dl">Risk %</span><span class="dv">${{risk}}</span></div>
      <div class="dr"><span class="dl">Position Size</span><span class="dv">${{s.tier==0?'33%':s.tier==1?'100%':'WATCH'}}</span></div>
    </div>
    <div class="dst" style="padding:2px 0 8px">Edge Education</div>${{cards}}`;
}}

function buildCards(s){{
  const ev=(s.layer2__expected_value_20d||0)*100,wr=(s.layer2__win_rate_20d||0)*100;
  const nobs=+(s.layer2__n_observations)||0;
  const out=[];
  const ph=s.phase;
  if(ph==='C')out.push({{t:'good',h:'✓ Phase C — The Spring Entry',b:'<b>Highest-probability entry</b> in the Wyckoff cycle. Smart money engineers a shakeout below support to absorb final sellers at lowest prices, then price snaps back. Your stop is at the spring low. The upside target (top of range) is typically 3-5x the risk.'}});
  else if(ph==='D')out.push({{t:'good',h:'✓ Phase D — Markup Confirmed',b:'Accumulation complete. <b>Buying confirmed institutional absorption.</b> SOS bars and LPS pullbacks confirm. Less risk than Phase C but higher entry price. Best entries: NR4 compression pullbacks within Phase D.'}});
  else if(ph==='B')out.push({{t:'warn',h:'⚡ Phase B — Cause Building',b:'Still in the <b>trading range</b>. Accumulation in progress. Watch for compression_ratio dropping below 0.65 — signals Phase C shakeout approaching. Tier 0 entry valid at 33% size.'}});
  else out.push({{t:'warn',h:'⚡ Phase A — Early Stop',b:'Prior downtrend stopping. <b>Highest reward, lowest certainty.</b> Only valid as Tier 0 at 33% sizing. Needs Phase B and C to form before adding.'}});
  
  const cp=String(s.crabel_pattern||'');
  if(cp.includes('NR7'))out.push({{t:'good',h:'✓ NR7+LowVol — Fully Coiled',b:'<b>Narrowest 7-bar range + volume dry-up.</b> Double compression. Crabel: resolves directionally in 1-3 sessions. Combined with Phase C = highest conviction setup in the system. Trigger: if open > NR7 high → long.'}});
  else if(cp.includes('ID'))out.push({{t:'good',h:'✓ Inside Day — Volatility Compressed',b:'Range fits inside prior bar. <b>Market in stasis.</b> Next directional bar will be impulsive. Watch open range breakout.'}});
  else if(cp.includes('Extreme'))out.push({{t:'warn',h:'⚡ Extreme Compression',b:'Large move imminent. <b>Direction not declared.</b> Enter only on open-range breakout confirmation.'}});
  else out.push({{t:'warn',h:'— No Crabel Pattern',b:'<b>No compression catalyst.</b> Timing is uncertain — rely on Wyckoff phase. May require 5-15 days before setup activates.'}});
  
  if(ev>=3&&wr>=40)out.push({{t:'good',h:'✓ STRONG Actuarial Edge',b:`<b>${{nobs.toLocaleString()}} historical observations</b> confirm EV ${{ev.toFixed(2)}}% at ${{wr.toFixed(0)}}% win rate over 20 days. Note: 20d window understates 5-10d Wyckoff payoff — real edge likely 6-8%.`}});
  else if(ev>=1.5)out.push({{t:'warn',h:'⚡ MODERATE Edge (20d Window)',b:`EV ${{ev.toFixed(2)}}% from ${{nobs.toLocaleString()}} obs. <b>20-day window understates Wyckoff/Crabel setups</b> — a stock gaining 7% in 5 days then giving back 4% by day 20 records as EV 3%. Actual edge at optimal hold window is likely higher.`}});
  else out.push({{t:'bad',h:'✗ Weak Statistical Edge',b:`EV ${{ev.toFixed(2)}}% below threshold. <b>Rely on Discovery scoring, not actuarial,</b> for conviction. Wait for setup to strengthen.`}});
  
  const ctrl=String(s.control_state||'');
  if(ctrl.includes('BUYER'))out.push({{t:'good',h:'✓ Buyers In Control — Clean Entry',b:'Price accepting value <b>above VWAP</b>. Buyers winning each auction. Cleanest long confirmation — enter on any minor pullback.'}});
  else if(ctrl.includes('SHIFTING'))out.push({{t:'good',h:'✓ Control Shifting — Explosive Setup',b:'<b>Sellers exhausted, buyers taking over.</b> Most explosive setups emerge here. Aggressive sizing justified on first LPS after shift.'}});
  else if(ctrl.includes('EQUIL'))out.push({{t:'warn',h:'⚡ Equilibrium — Declare at Open',b:'Neither side dominant. <b>Use Crabel open-range breakout as trigger.</b> Open above NR7 high → buy. Open below support → stand aside.'}});
  else out.push({{t:'bad',h:'✗ Sellers In Control — Wait',b:'<b>Do not fight sellers.</b> Wait for control to shift. The spring may not be complete yet.'}});
  
  return out.map(c=>`<div class="tc ${{c.t}}"><div class="tc-head">${{c.h}}</div>${{c.b}}</div>`).join('');
}}

const RULES=[
  {{kw:['phase c','spring','shakeout'],f:()=>{{F.phase='C';activateChip('phase','C');}},edu:{{h:'🎯 WYCKOFF PHASE C — THE SPRING',t:'Phase C is the <b>highest-probability entry point</b> in the accumulation structure. Smart money engineers a shakeout below support to absorb the final sellers.<br><br><b>Without a chart, find it by:</b> phase=C, compression_ratio &lt; 0.70, conditions_met &ge; 3/5, tier=1.<br><br><b>The edge:</b> 249,037 historical observations confirm Phase C + NORMAL vol = 4.45% EV at 44% win rate. Sub-50% win rate but winners are 3-4x the size of losers — asymmetric payoff is the Wyckoff edge.'}}}},
  {{kw:['phase d','markup','breakout'],f:()=>{{F.phase='D';activateChip('phase','D');}},edu:{{h:'🚀 WYCKOFF PHASE D — MARKUP',t:'Phase D = accumulation complete. Institutions have finished loading. <b>Signs of Strength (SOS)</b> bars appear — wide range up on expanding volume, price holding above old resistance.<br><br><b>Entry:</b> Last Point of Support (LPS) pullbacks that hold above old resistance. Combine with NR4/NR7 compression for optimal timing.'}}}},
  {{kw:['crabel','nr7','id','compression','narrow range'],f:()=>{{F.crbl='NR7';activateChip('crbl','NR7');}},edu:{{h:'📦 CRABEL NR7 — VOLATILITY COILING',t:'Tom Crabel: <b>volatility is mean-reverting</b>. After extreme compression, expansion follows — almost inevitably.<br><br><b>NR7:</b> Narrowest range of last 7 bars. <b>NR7+LowVol:</b> NR7 + below-average volume = double compression.<br><br><b>How to trade it:</b> On the next session open, if price trades above the NR7 bar high → buy. Below the NR7 bar low → stand aside. The open range is the trigger — not a blind entry.'}}}},
  {{kw:['strong','edge quality','best edge'],f:()=>{{F.eq='STRONG';activateChip('eq','STRONG');}},edu:{{h:'💎 EDGE QUALITY — ACTUARIAL THRESHOLDS',t:'Edge quality = the verdict from 1.28M historical observations.<br><br><b>STRONG:</b> EV &ge; 3% AND Win Rate &ge; 40% over 20 days (249K+ obs)<br><b>MODERATE:</b> EV &ge; 1.5%<br><b>WEAK:</b> EV positive but marginal<br><br><b>The 20-day window caveat:</b> All EV is measured at day 20. Wyckoff springs that pay off in 5 days are understated. STRONG at 20 days = likely exceptional at 5-10 days.'}}}},
  {{kw:['trade','best signals','confirmed trade'],f:()=>{{F.verdict='TRADE';activateChip('verdict','TRADE');F.tier='1';activateChip('tier','1');}},edu:{{h:'⚡ TRADE SIGNAL — WHAT IT MEANS',t:'TRADE requires ALL simultaneously: EV &ge; 3%, Win Rate &ge; 40%, Edge Quality = STRONG, Tier &ge; 1.<br><br><b>Tonight: 65 TRADE signals from 2,020 universe = 3.2% hit rate.</b> Deliberately narrow — only fires when multiple independent evidence sources converge.<br><br><b>Perfect convergence:</b> TRADE + Phase C/D + NR7/ID + BUYERS or SHIFTING + VWAP ABOVE. All five = highest conviction setup.'}}}},
  {{kw:['buyer','buyers','control'],f:()=>{{F.ctrl='BUYER';activateChip('ctrl','BUYER');}},edu:{{h:'🐂 CONTROL STATE — AUCTION THEORY',t:'Control state = who is winning the price auction.<br><br><b>BUYERS_IN_CONTROL:</b> Price above VWAP, higher lows forming. Clean long entry.<br><b>EQUILIBRIUM:</b> Market undecided. Use Crabel open-range breakout as trigger.<br><b>CONTROL_SHIFTING:</b> Most explosive — sellers exhausted, buyers taking over. Best asymmetric payoff.<br><b>SELLERS_IN_CONTROL:</b> Wait.'}}}},
  {{kw:['tier 0','early'],f:()=>{{F.tier='0';activateChip('tier','0');}},edu:{{h:'⏰ TIER 0 — EARLY POSITION STRATEGY',t:'Tier 0 = 5-15 days before the Tier 1 trigger fires. <b>Lowest price, highest uncertainty.</b><br><br><b>Why enter early:</b> Entry typically 3-8% below Tier 1 trigger. Blended average improves your cost basis.<br><br><b>Quality filters:</b> compression_ratio &lt; 0.70, days_to_trigger &le; 7, conditions_met &ge; 3/5, phase B or C.<br><br><b>Size:</b> 33% only. Add 67% when Tier 1 fires.'}}}},
  {{kw:['how does ev','expected value','actuarial','vanguard'],f:()=>{{}},edu:{{h:'📊 HOW EV WORKS — THE STATISTICAL EDGE',t:'EV = (Win Rate × Avg Winner) + (Loss Rate × Avg Loser)<br><br>Tonight example: (44% × 10.1%) + (56% × -2.7%) = 4.45% - 1.51% = <b>2.94% net EV per trade</b><br><br><b>Why sub-50% win rate still profits:</b> You are wrong more often than right. But when right you make 10%, when wrong you lose 2.7%. Asymmetry is the entire Wyckoff edge — entry at the spring where upside (top of range) is 3-5x the downside (stop below spring low).<br><br><b>Database:</b> 1.28M observations across 3 years. Not a backtest — historical fact.'}}}},
  {{kw:['compression ratio','coil','compressed'],f:()=>{{}},edu:{{h:'📐 COMPRESSION RATIO — READING THE COIL',t:'Compression ratio = how tightly price is contracted vs normal range.<br><br><b>&lt; 0.55:</b> Extreme. NR7 territory. Move imminent.<br><b>0.55-0.70:</b> Strong. Tier 0/1 sweet spot.<br><b>0.70-0.90:</b> Moderate. Valid, less urgency.<br><b>&gt; 0.90:</b> Expanding. Not a compression trade.<br><br>Lower = more coiled. ASTS tonight: compression_ratio 0.55 + NR7 = maximally coiled.'}}}},
  {{kw:['control state','explain control','buyer seller'],f:()=>{{}},edu:{{h:'🎯 CONTROL STATE EXPLAINED',t:'Auction market theory: at every price, buyers and sellers run an auction. Whoever accepts value = controls that level.<br><br><b>BUYERS_IN_CONTROL:</b> Accepting above VWAP. Clean long entry.<br><b>EQUILIBRIUM:</b> Oscillating VWAP. Needs compression catalyst for direction.<br><b>CONTROL_SHIFTING:</b> Transition state. Most explosive setups here.<br><b>SELLERS_IN_CONTROL:</b> Do not long. Wait for shift.<br><br>Tonight: 458 Tier 1 signals in EQUILIBRIUM. Market undecided — the Crabel NR7 open-range breakout is the declaration trigger.'}}}},
];

function runQ(){{
  const input=document.getElementById('q').value.toLowerCase();
  if(!input.trim())return;
  Object.keys(F).forEach(k=>F[k]='all');
  document.querySelectorAll('.chip').forEach(c=>c.classList.remove('on'));
  document.querySelectorAll('.chip[data-v="all"]').forEach(c=>c.classList.add('on'));
  let edu=null;
  for(const r of RULES){{
    if(r.kw.some(k=>input.includes(k))){{r.f();if(r.edu)edu=r.edu;}}
  }}
  const sm=input.match(/score\\s*(?:above|>|over|>=)?\\s*(\\d+)/);
  if(sm){{document.querySelectorAll('input[type=range]')[0].value=sm[1];document.getElementById('sv').textContent=sm[1];}}
  const wm=input.match(/win.*?(\\d+)\\s*%/);
  if(wm){{document.querySelectorAll('input[type=range]')[1].value=wm[1];document.getElementById('wp').textContent=wm[1];}}
  const em=input.match(/ev.*?(\\d+\\.?\\d*)\\s*%/);
  if(em){{document.querySelectorAll('input[type=range]')[2].value=em[1];document.getElementById('ev').textContent=em[1];}}
  if(edu){{document.getElementById('edu-h').textContent=edu.h;document.getElementById('edu-b').innerHTML=edu.t;document.getElementById('edu').classList.add('on');}}
  else document.getElementById('edu').classList.remove('on');
  applyF();
}}

function q(txt){{document.getElementById('q').value=txt;runQ();}}

function activateChip(f,v){{
  document.querySelectorAll(`.chip[data-f="${{f}}"]`).forEach(c=>c.classList.remove('on'));
  const t=document.querySelector(`.chip[data-f="${{f}}"][data-v="${{v}}"]`);
  if(t)t.classList.add('on');
}}

function reset(){{
  Object.keys(F).forEach(k=>F[k]='all');
  document.querySelectorAll('.chip').forEach(c=>c.classList.remove('on'));
  document.querySelectorAll('.chip[data-v="all"]').forEach(c=>c.classList.add('on'));
  const r=document.querySelectorAll('input[type=range]');
  r[0].value=60;r[1].value=50;r[2].value=0;
  document.getElementById('sv').textContent=60;document.getElementById('wp').textContent=50;document.getElementById('ev').textContent=0;
  document.getElementById('q').value='';document.getElementById('edu').classList.remove('on');
  applyF();
}}
applyF();
</script>
</body>
</html>"""
    return html

def main():
    parser = argparse.ArgumentParser(description='Generate AVSHUNTER Signal Intelligence Lab')
    parser.add_argument('--run-id', help='Specific run ID (default: latest)')
    args = parser.parse_args()

    dc, vs, run_id = load_data(args.run_id)
    df = merge_and_clean(dc, vs)
    stats = build_stats(df)

    print(f"\nStats: {stats}")

    html = generate_html(df, run_id, stats)

    date_str = datetime.now().strftime('%Y%m%d')
    out_path = OUTPUT_DIR / f"avshunter_intelligence_lab_{date_str}.html"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(html)

    size_mb = os.path.getsize(out_path) / 1024 / 1024
    print(f"\n✓ Generated: {out_path}")
    print(f"  Size:      {size_mb:.1f} MB")
    print(f"  Signals:   {stats['total']:,}")
    print(f"  TRADE:     {stats['trade']}")
    print(f"\nOpen in browser: file:///{out_path}")

if __name__ == '__main__':
    main()
