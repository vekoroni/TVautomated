"""
AVSHUNTER Pipeline Interpreter v1.0 â€” Core Engine
Reads pipeline CSV outputs and produces Dr. Magnus Vale trade narratives
"""
import os, csv, json, re, io, base64, mimetypes
import sys as _sys
from pathlib import Path
from datetime import datetime
_sys.path.insert(0, str(Path(__file__).parent))
from news_macro_readers import (
    read_macro_context, read_news_terminal_output,
    read_enrichment_delta, read_all_news_macro_context, save_pasted_brief,
)
try:
    from live_market_reader import (
        fetch_all_live_data, format_live_data_for_prompt,
        fetch_live_contract_spread, fetch_peer_quotes,
    )
    _LIVE_MARKET_AVAILABLE = True
except ImportError:
    _LIVE_MARKET_AVAILABLE = False
    def fetch_all_live_data(*a, **kw): return {}
    def format_live_data_for_prompt(*a, **kw): return ""
    def fetch_live_contract_spread(*a, **kw): return {}
    def fetch_peer_quotes(*a, **kw): return {}

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

# Model selection — v1.1 update
# Triage (/triage): Sonnet 4.6 — fast, cost-efficient, handles 65+ row ranking well
# Deep dive (/ticker, /chart): Opus 4.6 — full reasoning power for chess move trees and thesis analysis
MODEL_TRIAGE    = "claude-sonnet-4-6"
MODEL_DEEP_DIVE = "claude-opus-4-6"
MODEL           = MODEL_DEEP_DIVE  # default fallback — preserves backward compatibility
MAX_TOKENS      = 8000

BASE_DIR      = Path(__file__).parent
SYSTEM_PROMPT = BASE_DIR / "pipeline_interpreter_system_prompt.txt"
OUTPUTS_DIR   = BASE_DIR / "outputs"
MA_INPUTS     = BASE_DIR / "MA_Inputs"
MA_CHARTS     = MA_INPUTS / "charts"
MA_OPTIONS    = MA_INPUTS / "options_data"
MA_SCREENSHOTS= MA_INPUTS / "screenshots"
MA_PIPELINE   = MA_INPUTS / "pipeline_outputs"
MA_MACRO      = MA_INPUTS / "macro"
MA_NEWS       = MA_INPUTS / "news_terminal" 

# Ensure all folders exist
for _d in [OUTPUTS_DIR, MA_INPUTS, MA_CHARTS, MA_OPTIONS, MA_SCREENSHOTS, MA_PIPELINE, MA_MACRO, MA_NEWS]:
    _d.mkdir(parents=True, exist_ok=True)

EXECUTION_PERMISSION = "NONE_PIPELINE_INTERPRETER_ONLY"
CAPITAL_PERMISSION   = "CAPITAL_DENIED_PENDING_LIVE_CONFIRMATION"

# UX1 FIX: Translate capital-lock system codes to human review prompts
# Applied in the display layer only — underlying field values are unchanged
_DISPLAY_LABEL_MAP = {
    "NO_LIVE_CAPITAL_EOD":          "PENDING HUMAN REVIEW",
    "PSE_IGNORED_MANUAL_SIZING":    "MANUAL SIZING MODE",
    "ADVISORY_ONLY":                "MANUAL SIZING MODE",
    "MANUAL_SIZE_REQUIRED":         "MANUAL SIZE REQUIRED",
    "HUMAN_REVIEW_REQUIRED":        "PENDING HUMAN REVIEW",
    "NO_LIVE_CAPITAL":              "PENDING HUMAN REVIEW",
    "POSITION_SIZING_RETIRED_ADVISORY_ONLY": "MANUAL SIZING MODE",
}

def _translate_display_labels(val: str) -> str:
    """Translate internal capital-lock codes to operator-facing review prompts."""
    return _DISPLAY_LABEL_MAP.get(str(val).strip(), val)

# Shared session state dict used by session check and command handlers
SESSION: dict = {
    "pipeline_csv": None,
    "macro_json":   None,
    "catalyst_csv": None,
    "last_pipeline_csv": None,
    "last_triage_run":   None,
}

# Live price store — populated by /price command, injected into /ticker and /intraday
# Format: { "WFC": {"price": 75.81, "change_pct": -0.23, "timestamp": "09:47"}, ... }
LIVE_PRICES: dict = {}

# Live market data store — populated by /live command or auto-fetch in morning session
# Format: { "WFC": { options_volume: {...}, institutional_flow: {...}, ... } }
LIVE_DATA: dict = {}
PIPELINE_FILE_KEYWORDS = {
    "lab_triage_view":     ["lab_triage_view"],
    "morning_validated":   ["morning_validated_trades", "morning_validated"],
    "morning_candidates":  ["morning_candidates"],
    "top_trades":          ["top_trades", "avshunter_top"],
    "morning_validation":  ["morning_validation", "morning_val"],
    "execution":           ["execution_v3_5", "execution"],
    "eil":                 ["eil", "execution_intelligence"],
    "superbrain":          ["superbrain", "super_brain"],
    "pse":                 ["pse", "position_sizing"],
    "master_dashboard":    ["master_dashboard", "master_dash"],
    "catalyst_truth":      ["catalyst_truth"],
    "execute_tickers":     ["execute_tickers"],
    "garch_forecasts":     ["garch_forecasts"],
    "horizon_1_5d":        ["horizon_1_5d"],
    "horizon_6_10d":       ["horizon_6_10d"],
    "horizon_11_20d":      ["horizon_11_20d"],
    "options_intelligence": ["options_intelligence"],
    "vanguard_signals":    ["vanguard_signals"],
}

EXPECTED_PIPELINE_FILE_KEYS = [
    "lab_triage_view",
    "catalyst_truth",
    "eil",
    "execute_tickers",
    "execution",
    "garch_forecasts",
    "horizon_1_5d",
    "horizon_6_10d",
    "horizon_11_20d",
    "morning_candidates",
    "morning_validated",
    "options_intelligence",
    "superbrain",
    "vanguard_signals",
]

TRIAGE_CSV_FIELDS = [
    "ticker","direction","score","dte","horizon","earnings_in_window",
    "earnings_date","ma_ready","triage_verdict","triage_rank","urgency_flag",
    "catalyst_freshness","trigger_proximity","why","upgrade_condition",
    "execution_permission"
]

# â”€â”€ SESSION â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
class InterpreterSession:
    def __init__(self): self.reset()
    def reset(self):
        self.candidates=[]; self.narratives={}; self.verdicts={}
        self.session_date=datetime.now().strftime("%Y-%m-%d"); self.run_count=0
        self.triage_deep_dive=[]; self.triage_rows=[]
    def add_verdict(self, ticker:str, verdict:str, state:str):
        self.verdicts[ticker]={"verdict":verdict,"state":state}
    def summary(self):
        go    =[t for t,v in self.verdicts.items() if v["verdict"]=="GO"]
        armed =[t for t,v in self.verdicts.items() if v["verdict"]=="ARMED"]
        wait  =[t for t,v in self.verdicts.items() if v["verdict"] in ("WAIT","PROBE")]
        blocked=[t for t,v in self.verdicts.items() if v["verdict"] in ("BLOCKED","MISDIAGNOSED")]
        return {"total":len(self.verdicts),"go":go,"armed":armed,
                "wait":wait,"blocked":blocked}

session = InterpreterSession()
_loaded_options: dict = {}

def _print_results(results: dict, response: str) -> None:
    for key, val in results.items():
        if isinstance(val, dict) and 'path' in val:
            rows = val.get('rows', '')
            rows_str = f"({rows} ranked)" if rows else ""
            print(f"  \u2705 {Path(val['path']).name:<50} {rows_str}")



# â”€â”€ SYSTEM PROMPT â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
def load_system_prompt() -> str:
    if SYSTEM_PROMPT.exists(): return SYSTEM_PROMPT.read_text(encoding="utf-8")
    raise FileNotFoundError(f"Not found: {SYSTEM_PROMPT}")

# â”€â”€ API â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
def load_image(path:str) -> dict:
    """Load image file and return Anthropic image content block."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Image not found: {path}")
    mime, _ = mimetypes.guess_type(str(p))
    if not mime or not mime.startswith("image/"):
        # Try by extension
        ext = p.suffix.lower()
        mime = {"png":"image/png","jpg":"image/jpeg","jpeg":"image/jpeg",
                "gif":"image/gif","webp":"image/webp"}.get(ext.lstrip("."), "image/png")
    with open(p, "rb") as f:
        data = base64.standard_b64encode(f.read()).decode("utf-8")
    return {"type":"image","source":{"type":"base64","media_type":mime,"data":data}}

def call_api(user_prompt:str, images:list=None, use_web_search:bool=False,
             model:str=None, max_tokens:int=None) -> str:
    """Call Claude API.
    images        = list of file paths to include as vision input.
    use_web_search = enables live ticker news search.
    model         = override model; defaults to MODEL_DEEP_DIVE.
                    Pass MODEL_TRIAGE for /triage calls (faster, cheaper).
    """
    try: import anthropic
    except ImportError: raise ImportError("pip install anthropic --break-system-packages")
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    _model = model or MODEL_DEEP_DIVE
    _max_tokens  = max_tokens or MAX_TOKENS
    print(f"  [API] model={_model}")

    # Build message content
    if images:
        msg_content = []
        for img_path in images:
            try:
                msg_content.append(load_image(img_path))
                print(f"  ✅ Image loaded: {Path(img_path).name}")
            except Exception as e:
                print(f"  ⚠ Could not load image {img_path}: {e}")
        msg_content.append({"type":"text","text":user_prompt})
    else:
        msg_content = user_prompt

    # Build API kwargs
    kwargs = dict(
        model=_model,
        max_tokens=_max_tokens,
        system=load_system_prompt(),
        messages=[{"role":"user","content":msg_content}],
    )

    # Enable web search tool for live ticker news if requested
    if use_web_search:
        kwargs["tools"] = [{"type": "web_search_20250305", "name": "web_search"}]
        print(f"  🔍 Web search enabled — fetching latest news...")

    resp = client.messages.create(**kwargs)

    # Extract text blocks — handles tool_use and tool_result gracefully
    text_parts = []
    for b in resp.content:
        if hasattr(b, "type") and b.type == "text":
            text_parts.append(b.text)
    return "\n".join(text_parts)


# â”€â”€ FILE READERS â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
def read_pipeline_csv(path:str) -> list:
    """Read any pipeline CSV and return list of dicts."""
    rows=[]
    try:
        with open(path,"r",encoding="utf-8-sig") as f:
            reader=csv.DictReader(f)
            for row in reader:
                rows.append(dict(row))
        print(f"  âœ… Loaded {len(rows)} rows from {Path(path).name}")
    except Exception as e:
        print(f"  âš  Could not read {path}: {e}")
    return rows

def read_options_file(path:str) -> str:
    """Read options data file as text."""
    try:
        p=Path(path)
        if p.suffix.lower()==".csv":
            with open(p,"r",encoding="utf-8-sig") as f:
                return f.read()
        elif p.suffix.lower()==".json":
            with open(p,"r",encoding="utf-8") as f:
                return json.dumps(json.load(f),indent=2)
        else:
            return p.read_text(encoding="utf-8")
    except Exception as e:
        return f"[Could not read {path}: {e}]"

def find_pipeline_files(directory:str=None) -> dict:
    """Auto-detect pipeline output files in a directory."""
    search_dirs=[
        Path(directory) if directory else None,
        Path(r"C:\Users\ACKVerissimo\AVSHUNTER-Intelligence\AVSHUNTER_outputs"),
        Path(r"C:\Users\ACKVerissimo\AVSHUNTER-Intelligence\outputs"),
        Path.home() / "AVSHUNTER-Intelligence" / "outputs",
    ]
    keywords = PIPELINE_FILE_KEYWORDS

    found={}
    for d in search_dirs:
        if d and d.exists():
            for f in d.rglob("*.csv"):
                name=f.name.lower()
                for key,kws in keywords.items():
                    if any(kw in name for kw in kws) and key not in found:
                        found[key]=str(f)
            if found: break
    return found

# â”€â”€ PROMPT BUILDERS â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
def run_session_check():
    import json as _json
    TODAY = datetime.now().strftime("%Y%m%d")
    active_run_id = None; session_mode = "UNKNOWN"
    sm_path = MA_INPUTS / "session_state.json"
    if sm_path.exists():
        try:
            sm = _json.loads(sm_path.read_text(encoding="utf-8"))
            active_run_id = sm.get("run_id","").strip()
            session_mode  = sm.get("session_mode","UNKNOWN").upper()
        except Exception: pass
    if session_mode=="MORNING" and active_run_id:
        primary = f"morning_validated_trades_{active_run_id}.csv"
        fallback= f"morning_candidates_{active_run_id}.csv"; fb_label="EOD CANDIDATES"
    elif active_run_id:
        primary = f"morning_candidates_{active_run_id}.csv"
        fallback= f"morning_validated_trades_{active_run_id}.csv"; fb_label="morning_validated"
    else:
        primary = f"morning_candidates_{TODAY}_*.csv"
        fallback= f"morning_validated_trades_{TODAY}_*.csv"; fb_label="morning_validated"
    print("\n" + "="*60)
    print("  SESSION CHECK -- ENGINE COMMUNICATION STATUS")
    if active_run_id: print(f"  Run ID: {active_run_id}  |  Mode: {session_mode}")
    print("="*60)
    all_ok = True
    if MA_PIPELINE.exists():
        files = sorted(MA_PIPELINE.glob(primary), key=lambda f:f.stat().st_mtime, reverse=True)
        if not files: files = sorted(MA_PIPELINE.glob(fallback), key=lambda f:f.stat().st_mtime, reverse=True)
        if not files:
            any_f = sorted(list(MA_PIPELINE.glob("morning_candidates_*.csv"))+list(MA_PIPELINE.glob("morning_validated_trades_*.csv")),key=lambda f:f.stat().st_mtime,reverse=True)
            files = any_f
        if files:
            run_ok = active_run_id and active_run_id in files[0].name
            status = "OK" if run_ok else "!! STALE"
            if not run_ok: all_ok=False
            print(f"  Pipeline output        {status}  {files[0].name}")
            SESSION["pipeline_csv"] = str(files[0])
        else:
            print(f"  Pipeline output        X NOT FOUND"); SESSION["pipeline_csv"]=None; all_ok=False
    else:
        print(f"  Pipeline output        X DIR NOT FOUND"); SESSION["pipeline_csv"]=None; all_ok=False
    if MA_MACRO.exists():
        mf = sorted(MA_MACRO.glob("macro_intelligence_latest.json"),key=lambda f:f.stat().st_mtime,reverse=True)
        if mf:
            age_h = (datetime.now().timestamp()-mf[0].stat().st_mtime)/3600
            print(f"  Macro JSON             {'OK' if age_h<14 else '!! STALE'}  {mf[0].name}  ({age_h:.1f}h)")
            SESSION["macro_json"]=str(mf[0])
            if age_h>=14: all_ok=False
        else: print(f"  Macro JSON             X NOT FOUND"); SESSION["macro_json"]=None; all_ok=False
        df = sorted(MA_MACRO.glob("avshunter_macro_enrichment_delta.json"),key=lambda f:f.stat().st_mtime,reverse=True)
        if df:
            age_h2=(datetime.now().timestamp()-df[0].stat().st_mtime)/3600
            print(f"  Enrichment delta       OK  {df[0].name}  ({age_h2:.1f}h)")
    bf = MA_INPUTS/"news_terminal"/"newsroom_brief_latest.txt"
    if bf.exists():
        age_h3=(datetime.now().timestamp()-bf.stat().st_mtime)/3600
        print(f"  Newsroom brief         {'OK' if age_h3<14 else '!! OLD'}  {bf.name}")
    else: print(f"  Newsroom brief         --  not pasted (run /brief)")
    SESSION["catalyst_csv"]=None
    print("="*60)
    mode_label="MORNING EXECUTION REVIEW" if session_mode=="MORNING" else "EOD PREP"
    print(f"  STATUS: {'READY' if all_ok else 'WARNING'}  -- {mode_label}")
    print("="*60+"\n")
    if SESSION.get("pipeline_csv") and not SESSION.get("last_pipeline_csv"):
        SESSION["last_pipeline_csv"]=SESSION["pipeline_csv"]


def _date(): return datetime.now().strftime("%A %d %B %Y")

# Key fields to include â€” drop verbose/redundant columns to save tokens
_PRIORITY_FIELDS = [
    "ticker","underlying","direction","intent","phase","regime",
    "score","vanguard_score","superbrain_score","eil_verdict","pse_score","wbs_score",
    "confidence","priority","route","suggested_avshunter_review","upload_priority",
    "anis_total_score","fips_score","dbs","triage_verdict","final_verdict",
    "strike","expiry","dte","premium","delta","gamma","theta",
    "iv_percentile","ivp","rr","r_r","max_pain","actuarial_notes",
    "iv_gex_entry_quality_label","gamma_island_label","gamma_island_level",
    "gamma_island_distance_pct","move_theta_margin_label","crowd_arrival_state",
    "iv_gex_entry_quality_narrative","move_theta_narrative","crowd_arrival_narrative",
    "key_catalyst","key_risk","invalidation","execution_notes",
    "narrative","event_category","directional_bias","forward_impact_thesis",
    "why_analyse","why_run_through_pipeline","manual_check_required",
]

def _select_fields(rows:list) -> list:
    """Pick priority fields that exist in the data, fall back to all if none match."""
    if not rows: return []
    available = list(rows[0].keys())
    selected = [f for f in _PRIORITY_FIELDS if f in available]
    if not selected:
        selected = available[:20]  # fallback: first 20 columns
    return selected

def _format_rows(rows:list, max_rows:int=15) -> str:
    """Format pipeline rows as compact text for the prompt. Limits tokens."""
    if not rows: return "No data."
    fields = _select_fields(rows)
    lines = [",".join(fields)]
    for r in rows[:max_rows]:
        row_vals = []
        for f in fields:
            val = _translate_display_labels(str(r.get(f,"")).strip())
            # Truncate long values
            if len(val) > 80:
                val = val[:77] + "..."
            row_vals.append(val)
        lines.append(",".join(row_vals))
    if len(rows) > max_rows:
        lines.append(f"... ({len(rows)-max_rows} more rows â€” showing top {max_rows} only)")
    return "\n".join(lines)

def _format_ma_inputs(ma_inputs: dict) -> str:
    if not ma_inputs:
        return ""
    lines = ["MA_INPUTS AVAILABLE:"]
    for key, val in ma_inputs.items():
        if val:
            lines.append(f"  {key}: {val}" if not isinstance(val, list) 
                         else f"  {key}: {len(val)} file(s)")
    return "\n".join(lines)


def build_interpret_prompt(pipeline_data:dict, options_data:dict=None,
                            focus_tickers:list=None, session_context:str=None) -> str:
    date_str = _date()
    focus_str = f"\nFocus tickers: {', '.join(focus_tickers)}" if focus_tickers else ""
    ctx_str = f"\nSession context: {session_context}" if session_context else ""

    sections=[]
    for name, rows in pipeline_data.items():
        if rows:
            sections.append(f"=== {name.upper()} ({len(rows)} rows) ===\n{_format_rows(rows)}")

    opt_sections=[]
    if options_data:
        for name, content in options_data.items():
            if content and len(content.strip())>10:
                # Truncate large files
                truncated = content[:800]+"...[truncated]" if len(content)>800 else content
                opt_sections.append(f"=== OPTIONS: {name.upper()} ===\n{truncated}")

    pipeline_text = "\n\n".join(sections) if sections else "No pipeline data provided."
    options_text  = "\n\n".join(opt_sections) if opt_sections else "No options data provided."

    # Load macro and news context
    macro_text = read_macro_context(ma_macro_dir=MA_MACRO)
    news_text  = read_news_terminal_output(ma_news_dir=MA_NEWS)

    return f"""Run Pipeline Interpreter full analysis. Date: {date_str}{focus_str}{ctx_str}

PIPELINE OUTPUT DATA:
{pipeline_text}

OPTIONS INTELLIGENCE DATA:
{options_text}

MACRO + ENRICHMENT DELTA + NEWS:
{combined_context}

INSTRUCTIONS:
For each candidate in the pipeline data, apply the complete Dr. Magnus Vale + Soul of the Chart framework.

Produce for each ticker:
1. Dr. Magnus Vale Diagnosis â€” true market condition vs pipeline score
2. Evidence Quality â€” rigorously separate CONFIRMED / ASSUMPTION / MISSING from the data provided
3. Trapped Participants â€” who is trapped, where, what forces them to act
4. Chess Move Tree â€” next 3-5 forced moves with specific price levels where available
5. Soul of the Chart â€” behavioural ownership map, strong vs weak hands, what the chart is trying to make traders believe
6. Bullish Case vs Bearish Case â€” honest argument for both sides
7. Behavioural Verdict â€” which side has better evidence
8. Execution Prescription â€” exact trigger level, exact kill switch, first-hour rule
9. Kill Switch â€” single condition that invalidates immediately
10. Monetisation â€” how it pays if correct, preferred contract, timeline, R:R
11. Final Verdict: GO / ARMED / PROBE / WAIT / BLOCKED / MISDIAGNOSED

Apply the 1-5 day business rule rigorously:
- Would entering at current conditions risk immediate red? YES/NO
- If YES â†’ WAIT or BLOCKED regardless of pipeline score

End with [SESSION_SUMMARY] covering the full pipeline picture.
End with [TRADE_BRIEF_CSV] â€” one row per ticker.

execution_permission=NONE_PIPELINE_INTERPRETER_ONLY
capital_permission=CAPITAL_DENIED_PENDING_LIVE_CONFIRMATION"""

def build_single_ticker_prompt(ticker:str, pipeline_row:dict,
                                options_data:dict=None, context:str=None,
                                ticker_note:str="",
                                lab_context_block:str="",
                                lab_conflict_block:str="",
                                pre_trade_prob_block:str="") -> str:
    date_str=_date()
    row_text="\n".join(f"{k}: {_translate_display_labels(str(v))}" for k,v in pipeline_row.items() if v)
    opt_text=""
    if options_data:
        for name,content in options_data.items():
            if content:
                opt_text+=f"\n{name.upper()}:\n{content[:600]}\n"

    ctx_str=f"\nAdditional context: {context}" if context else ""

    # Trader narrative block
    _trader_note_block = ""
    if ticker_note and ticker_note.strip():
        _trader_note_block = f"TICKER_NARRATIVE: {ticker}\n{ticker_note.strip()}\nEND_TICKER_NARRATIVE\n\n"

    # Load macro and news terminal context
    combined_context = read_all_news_macro_context(ticker=ticker if "ticker" in dir() else None, ma_macro_dir=MA_MACRO, ma_news_dir=MA_NEWS)

    # Inject live price if registered via /price command
    _live_price_block = format_live_price_block(ticker, LIVE_PRICES)
    _live_price_section = f"\nLIVE PRICE:\n{_live_price_block}\n" if _live_price_block else ""

    # Lab context injection (Component 9) — empty string by default, no effect on existing callers
    _lab = ""
    if lab_context_block:  _lab += f"\n{lab_context_block}\n"
    if lab_conflict_block: _lab += f"\n{lab_conflict_block}\n"
    if pre_trade_prob_block: _lab += f"\n{pre_trade_prob_block}\n"

    return f"""Run Pipeline Interpreter â single ticker deep dive: {ticker}
{_trader_note_block}Date: {date_str}{ctx_str}

PIPELINE ROW:
{row_text}
{_live_price_section}
OPTIONS DATA:
{opt_text if opt_text else 'Not provided.'}
{_lab}
MACRO + ENRICHMENT DELTA + NEWS:
{combined_context}

WEB SEARCH INSTRUCTION:
You have access to a live web search tool. Before producing any section of this analysis,
search for the latest news on this ticker using these specific queries:
1. "{ticker} latest news today"
2. "{ticker} stock news"
3. "{ticker} stock catalyst news"

Search purpose: Find any narrative that poses a RISK or ENHANCEMENT to the pipeline thesis.
The pipeline direction is FIXED and authoritative. Do not use search results to change direction.
Use search results only to:
  - Confirm the thesis has no news-based headwind (ENHANCEMENT)
  - Flag any recent news that creates friction against the thesis (RISK)
  - Identify any upcoming catalyst within the DTE window (CATALYST ALERT)
  - Find any earnings date, FDA date, or binary event (EVENT RISK)

Report findings under NEWS NARRATIVE OVERLAY as:
  SEARCH_RESULT: [what you found]
  THESIS_IMPACT: RISK / ENHANCEMENT / NEUTRAL / CATALYST_ALERT / EVENT_RISK
  IMPACT_DETAIL: [one sentence on how this affects the pipeline thesis]

If no relevant news found: state SEARCH_RESULT: NO_MATERIAL_NEWS_FOUND

Apply the COMPLETE Dr. Magnus Vale + Soul of the Chart framework.
Be maximally sceptical. Challenge every assumption in the pipeline row.
Use McMillan advisory fields as context for entry quality, theta margin, and crowd timing.
Do not treat McMillan advisory flags as automatic blocks.
Produce the full narrative including three-level explanation (Beginner/Intermediate/Professional).
State the Final Verdict clearly: GO / ARMED / PROBE / WAIT / BLOCKED / MISDIAGNOSED
Apply the 1-5 day business rule: would entering now risk immediate red?

execution_permission=NONE_PIPELINE_INTERPRETER_ONLY"""

def build_triage_prompt(pipeline_rows:list, ma_inputs_summary:dict=None,
                        session_mode:str="EOD",
                        lab_alignment_block:str="",
                        pre_trade_prob_block:str="") -> str:
    import json as _json
    date_str = _date()
    hour = datetime.now().hour
    # Read session mode
    _sm = MA_INPUTS/"session_state.json"
    if _sm.exists():
        try:
            _d=_json.loads(_sm.read_text(encoding="utf-8"))
            session_mode=_d.get("session_mode","eod").upper()
        except Exception: pass
    combined_context = read_all_news_macro_context(ma_macro_dir=MA_MACRO, ma_news_dir=MA_NEWS)

    # v1.1 — Pre-filter to OIS>=50 tickers before formatting for Claude.
    # Prevents the 40-row cap from discarding high-quality signals in favour
    # of low-OIS noise. Falls back to all rows if fewer than 10 pass the filter.
    _OIS_FIELDS = ["ois_score", "scs_score", "composite_score", "pipeline_score"]
    def _ois_val(row):
        for _f in _OIS_FIELDS:
            _v = row.get(_f, "")
            try:
                return float(_v)
            except (TypeError, ValueError):
                continue
        return 0.0

    ois_filtered = [r for r in pipeline_rows if _ois_val(r) >= 50]
    rows_to_triage = ois_filtered if len(ois_filtered) >= 10 else pipeline_rows
    if ois_filtered:
        print(f"  [TRIAGE] OIS>=50 filter: {len(ois_filtered)} tickers → passing to Claude (was {len(pipeline_rows)} total)")
    rows_text   = _format_rows(rows_to_triage, max_rows=65)  # raised from 40 to 65
    inputs_text = _format_ma_inputs(ma_inputs_summary) if ma_inputs_summary else ""

    # Sector-grouped candidate summary -- injected above the flat table
    def _get_sector_key(row):
        for _f in ["gics_sector", "sector_name", "sector", "gics_sector_name"]:
            _v = str(row.get(_f, "")).strip()
            if _v:
                return _v.upper()
        return "UNKNOWN"

    def _get_scs_val(row):
        for _f in ["scs_score", "priority_score", "composite"]:
            try:
                return float(row.get(_f, 0) or 0)
            except (TypeError, ValueError):
                continue
        return 0.0

    def _get_fld(row, *fields, default=""):
        for _f in fields:
            _v = str(row.get(_f, "")).strip()
            if _v:
                return _v
        return default

    _run_id = "UNKNOWN"
    _macro_regime = "UNKNOWN"
    if _sm.exists():
        try:
            _d3 = _json.loads(_sm.read_text(encoding="utf-8"))
            _run_id = _d3.get("run_id", "UNKNOWN")
            for _mf in ["macro_regime_now", "current_regime", "morning_macro_regime_state"]:
                _mr = _d3.get(_mf, "")
                if _mr:
                    _macro_regime = _mr
                    break
        except Exception:
            pass
    if _macro_regime == "UNKNOWN":
        _mj_path = MA_MACRO / "macro_intelligence_latest.json"
        if _mj_path.exists():
            try:
                _mj = _json.loads(_mj_path.read_text(encoding="utf-8"))
                for _mf in ["macro_regime_now", "current_regime", "morning_macro_regime_state"]:
                    _mr = _mj.get(_mf, "")
                    if _mr:
                        _macro_regime = _mr
                        break
            except Exception:
                pass

    _go_n = _flag_n = _block_n = 0
    for _r in rows_to_triage:
        _vv = _get_fld(_r, "verdict", "execution_permission", "morning_execution_permission").upper()
        if "GO" in _vv and "FLAG" not in _vv and "BLOCK" not in _vv:
            _go_n += 1
        elif "FLAG" in _vv:
            _flag_n += 1
        elif "BLOCK" in _vv:
            _block_n += 1

    from collections import defaultdict as _dd
    _sec_groups = _dd(list)
    for _r in rows_to_triage:
        _sec_groups[_get_sector_key(_r)].append(_r)
    for _sec in _sec_groups:
        _sec_groups[_sec].sort(key=_get_scs_val, reverse=True)

    _sg_lines = [
        f"RUN ID: {_run_id}",
        f"MACRO REGIME: {_macro_regime}",
        f"TOTALS -- GO: {_go_n} | FLAG: {_flag_n} | BLOCK: {_block_n}",
        "INSTRUCTION: The trader will manually decide which sectors to engage based on their macro view. Do not recommend trades. Rank each sector by quality of its GO candidates and flag any sector where all candidates are FLAG or BLOCK.",
        "",
    ]
    for _sn in sorted(_sec_groups.keys()):
        _srows = _sec_groups[_sn]
        _sg_lines.append(f"=== {_sn} -- {len(_srows)} tickers ===")
        for _r in _srows:
            _t  = _get_fld(_r, "ticker", default="?")
            _ti = _get_fld(_r, "structural_tier", "tier", "tier_label", default="")
            _di = _get_fld(_r, "evening_direction", "direction", "canonical_direction", default="")
            _sc = _get_scs_val(_r)
            _ve = _get_fld(_r, "verdict", "execution_permission", "morning_execution_permission", default="")
            _rr = _get_fld(_r, "rr", "rr_predicted", "evening_rr_predicted", default="")
            _ev = _get_fld(_r, "ev_predicted", "ev2_ev_conf_adj", "eil_ev_net", "evening_ev_predicted", default="")
            _wb = _get_fld(_r, "wbs_grade", default="")
            _st = _get_fld(_r, "setup_type", default="")
            _sg_lines.append(
                f"{_t}  {_ti}  {_di}  SCS={_sc:.1f}  VERDICT={_ve}  RR={_rr}  EV={_ev}  WBS={_wb}  {_st}".rstrip()
            )
        _sec_go_tickers = [
            _get_fld(_r, "ticker", default="?") for _r in _srows
            if "GO" in _get_fld(_r, "verdict", "execution_permission", "morning_execution_permission", default="").upper()
            and "FLAG" not in _get_fld(_r, "verdict", "execution_permission", "morning_execution_permission", default="").upper()
            and "BLOCK" not in _get_fld(_r, "verdict", "execution_permission", "morning_execution_permission", default="").upper()
        ]
        if _sec_go_tickers:
            _sg_lines.append(f"Note: {_sn} has {len(_sec_go_tickers)} GO candidates -- check macro alignment before entry.")
        _sg_lines.append("")
    sector_grouped_text = "\n".join(_sg_lines)

    # Build validation summary for MORNING mode
    validation_summary = ""
    if session_mode == "MORNING" and pipeline_rows:
        try:
            import pandas as _pd
            _df=_pd.DataFrame(pipeline_rows)
            if "live_validation_state" in _df.columns and "ticker" in _df.columns:
                confirmed=_df[_df["live_validation_state"]=="CONFIRMED"]["ticker"].tolist()
                wait_ret =_df[_df["live_validation_state"]=="WAIT_RETEST"]["ticker"].tolist()
                rejected =_df[_df["live_validation_state"]=="REJECTED"]["ticker"].tolist()
                eod_only =[]; 
                if "live_capital_permission" in _df.columns:
                    eod_only=_df[_df["live_capital_permission"]=="EOD_CANDIDATE_ONLY"]["ticker"].tolist()
                validation_summary = f"""
MORNING VALIDATION — PRIMARY RANKING SIGNALS:
CONFIRMED (thesis VALID): {confirmed}
WAIT_RETEST (PENDING): {wait_ret}
REJECTED (BROKEN): {rejected}
EOD_CANDIDATE_ONLY (actionable): {eod_only}
RULES: CONFIRMED+EOD_ONLY=DEEP_DIVE_NOW | CONFIRMED+NO=DEEP_DIVE_NEXT | WAIT=REVIEW_LATER | REJECTED=SKIP
"""
        except Exception: pass
    if session_mode=="MORNING":
        mode_instr=f"SESSION MODE: MORNING EXECUTION REVIEW\nUse live_validation_state and morning_execution_permission as MASTER ranking signals.\nNever promote a ticker because chart files exist if morning validation says WAIT, CONTRACT_REPAIR, BLOCKED, or REJECTED.\nIf live_validation_state is missing, mark SKIP_TODAY and request the morning_validated_trades CSV.\n{validation_summary}\nDate: {date_str}"
    else:
        mode_instr=f"SESSION MODE: EOD PREP\nUse structural signals. horizon_bucket is the TRADE THESIS horizon — not DTE.\nA 30 DTE contract for a 6_10d horizon is a 6-10 day trade.\nDate: {date_str}"
    # Lab alignment injection (Component 9) — empty string by default, no effect on existing callers
    lab_section = f"\n{lab_alignment_block}\n" if lab_alignment_block else ""
    pre_trade_section = f"\n{pre_trade_prob_block}\n" if pre_trade_prob_block else ""

    return f"""Run AVSHUNTER Pipeline Triage. {mode_instr}

SECTOR-GROUPED CANDIDATES:
{sector_grouped_text}

PIPELINE CANDIDATES (FULL TABLE):
{rows_text}
{inputs_text}

MACRO + ENRICHMENT DELTA + NEWS:
{combined_context}
{lab_section}{pre_trade_section}
OUTPUT EXACTLY THREE TAGGED SECTIONS:

[TRIAGE_RANKED_TABLE]
CSV: rank,ticker,direction,pipeline_score,dte,horizon,live_validation_state,validation_score,earnings_flag,ma_inputs_ready,triage_verdict,triage_reason
triage_verdict: DEEP_DIVE_NOW | DEEP_DIVE_NEXT | REVIEW_LATER | WATCH_ONLY | SKIP_TODAY
horizon: use horizon_bucket not raw DTE
Output ONLY the CSV. No preamble. No code fences.
[/TRIAGE_RANKED_TABLE]

[TRIAGE_SUMMARY]
**DEEP_DIVE_NOW:** [tickers]
**DEEP_DIVE_NEXT:** [tickers]
**REVIEW_LATER:** [tickers]
**WATCH_ONLY:** [tickers]
**SKIP_TODAY:** [tickers]
---
### Session Picture
2-3 paragraphs. In MORNING mode state CONFIRMED vs REJECTED counts and what it means.
In EOD mode state horizon_bucket distribution and urgency.
[/TRIAGE_SUMMARY]

[TRIAGE_EXECUTION_ORDER]
Exact /ticker commands in priority order. One sentence rationale each.
End with: EXECUTION PERMISSION: NONE_PIPELINE_INTERPRETER_ONLY
[/TRIAGE_EXECUTION_ORDER]
"""


def build_chart_prompt(ticker:str, chart_descriptions:list,
                       pipeline_row:dict=None, options_data:dict=None,
                       chart_types:list=None, ticker_note:str="") -> str:
    """Build prompt for chart image analysis â€” feeds into Dr. Magnus Vale + Soul of the Chart."""
    date_str = _date()
    chart_type_str = ""
    if chart_types:
        chart_type_str = "\nChart types provided: " + ", ".join(chart_types)

    # Trader narrative block
    _trader_note_block = ""
    if ticker_note and ticker_note.strip():
        _trader_note_block = f"TICKER_NARRATIVE: {ticker}\n{ticker_note.strip()}\nEND_TICKER_NARRATIVE\n\n"

    row_text = ""
    if pipeline_row:
        row_text = "\nPIPELINE ROW FOR THIS TICKER:\n"
        row_text += "\n".join(f"{k}: {_translate_display_labels(str(v))}" for k,v in pipeline_row.items() if v)

    opt_text = ""
    if options_data:
        for name, content in options_data.items():
            if content:
                opt_text += f"\n{name.upper()}:\n{content[:500]}\n"

    chart_desc = ""
    if chart_descriptions:
        chart_desc = "\nCHART DESCRIPTIONS PROVIDED BY USER:\n" + "\n".join(chart_descriptions)

    # Load macro and news context
    combined_context = read_all_news_macro_context(ticker=ticker if "ticker" in dir() else None, ma_macro_dir=MA_MACRO, ma_news_dir=MA_NEWS)

    # Inject live price if registered via /price command
    _live_price_block = format_live_price_block(ticker, LIVE_PRICES)
    _live_price_section = f"\nLIVE PRICE:\n{_live_price_block}\n" if _live_price_block else ""


    return f"""Run Pipeline Interpreter â€” CHART ANALYSIS for {ticker}.
{_trader_note_block}Date: {date_str}{chart_type_str}{chart_desc}

MACRO + ENRICHMENT DELTA + NEWS:
{combined_context}
{_live_price_section}
The chart image(s) above show {ticker}. Read them as a behavioural auction map.

{row_text}

OPTIONS DATA:
{opt_text if opt_text else "Not provided."}

WEB SEARCH INSTRUCTION:
You have access to a live web search tool. Before producing any section of this analysis,
search for the latest news on this ticker using these specific queries:
1. "{ticker} latest news today"
2. "{ticker} stock news"
3. "{ticker} stock catalyst news"

Search purpose: Find any narrative that poses a RISK or ENHANCEMENT to the pipeline thesis.
The pipeline direction is FIXED and authoritative. Do not use search results to change direction.
Use search results only to:
  - Confirm the thesis has no news-based headwind (ENHANCEMENT)
  - Flag any recent news that creates friction against the thesis (RISK)
  - Identify any upcoming catalyst within the DTE window (CATALYST ALERT)
  - Find any earnings date, FDA date, or binary event (EVENT RISK)

Report findings under NEWS NARRATIVE OVERLAY as:
  SEARCH_RESULT: [what you found]
  THESIS_IMPACT: RISK / ENHANCEMENT / NEUTRAL / CATALYST_ALERT / EVENT_RISK
  IMPACT_DETAIL: [one sentence on how this affects the pipeline thesis]

If no relevant news found: state SEARCH_RESULT: NO_MATERIAL_NEWS_FOUND

Apply the COMPLETE Soul of the Chart framework to what you see in the chart(s):

VISUAL CHART READ:
1. What phase is this chart in? (accumulation / distribution / re-accumulation /
   re-distribution / mark-up / mark-down / transition)
2. Where are the key levels? (support, resistance, supply zones, demand zones)
3. Who has control â€” strong hands or weak hands? What is the evidence?
4. Is there absorption of supply or rejection of demand? Where?
5. What is the chart trying to make traders believe? What is actually happening?
6. Where are trapped participants? Longs trapped above? Shorts trapped below?
7. What forced-action levels are visible?
8. Wyckoff sequencing â€” only if the chart clearly supports it
9. What does volume (if visible) tell us about conviction?
10. What does the options data tell us when overlaid on the chart structure?

Then apply Dr. Magnus Vale:
- Does the visual chart confirm or CONTRADICT the pipeline score?
- If the chart contradicts the pipeline â€” state MISDIAGNOSED
- Chess Move Tree: next 3-5 forced moves based on WHAT YOU SEE
- Execution Prescription: trigger level from the chart (exact price if visible)
- Kill Switch: exact level from the chart

Then state the complete FINAL VERDICT:
GO / ARMED / PROBE / WAIT / BLOCKED / MISDIAGNOSED

Apply the correct horizon rules based on DTE in the pipeline row.

execution_permission=NONE_PIPELINE_INTERPRETER_ONLY"""


def build_morning_validation_prompt(candidates:list, macro_context:str=None) -> str:
    date_str=_date()
    macro_str=f"\nMacro context:\n{macro_context}" if macro_context else ""
    rows_text=_format_rows(candidates,max_rows=20)

    return f"""Run Pipeline Interpreter â€” MORNING VALIDATION. Date: {date_str}{macro_str}

TOP PIPELINE CANDIDATES:
{rows_text}

This is the pre-market morning validation pass.

For each candidate:
1. Is the thesis from last night still live given current macro?
2. What must the first hour of tape show to confirm or deny the thesis?
3. What is the exact trigger level for today?
4. What is the exact kill switch for today?
5. Final verdict for today: GO / ARMED / PROBE / WAIT / BLOCKED

Produce:
- Opening brief (3-4 sentences on the full picture)
- Per-ticker morning verdict
- Today's execution watchlist (ARMED or better only)
- Capital preservation reminders
- [TRADE_BRIEF_CSV]

execution_permission=NONE_PIPELINE_INTERPRETER_ONLY"""

# â”€â”€ PARSERS â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
def extract_section(response:str, tag:str) -> str:
    m=re.search(rf'\[{tag}\](.*?)(?=\[[A-Z_]+\]|$)', response, re.DOTALL|re.IGNORECASE)
    return m.group(1).strip() if m else ""

def extract_verdict(response:str, ticker:str) -> str:
    verdicts=["GO","ARMED","PROBE","WAIT","BLOCKED","MISDIAGNOSED"]
    # Look near the ticker mention
    idx=response.find(ticker)
    if idx>0:
        window=response[idx:idx+3000]
        for v in verdicts:
            if f"FINAL VERDICT" in window and v in window:
                return v
    # Fallback: scan full response
    for v in verdicts:
        if f"FINAL VERDICT" in response and v in response:
            return v
    return "WAIT"

def parse_brief_csv(text:str) -> list:
    if not text.strip(): return []
    try:
        clean=re.sub(r'```[a-z]*','',text).replace('```','').strip()
        rows=list(csv.DictReader(io.StringIO(clean)))
        for r in rows:
            r["execution_permission"] = EXECUTION_PERMISSION
            # Fix v1.1: was a syntax error (tuple key assignment)
            for _field in [
                "live_validation_state",
                "thesis_validity_state",
                "validation_score",
                "capital_permission",
            ]:
                r[_field] = CAPITAL_PERMISSION
        return rows
    except Exception as e:
        print(f"  âš  CSV parse: {e}"); return []

# â”€â”€ MA_INPUTS SCANNER â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
def scan_ma_inputs_for_ticker(ticker:str) -> dict:
    """
    Scan MA_Inputs folder for all files matching a ticker.
    Returns dict with chart_paths, options_paths, screenshot_paths.
    """
    ticker_upper = ticker.upper()
    result = {"charts": [], "options": [], "screenshots": [], "pipeline": []}

    IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
    CSV_EXTS   = {".csv"}

    # Charts folder
    if MA_CHARTS.exists():
        for f in sorted(MA_CHARTS.iterdir()):
            if f.suffix.lower() in IMAGE_EXTS:
                if ticker_upper in f.name.upper():
                    result["charts"].append(str(f))

    # Options data folder
    if MA_OPTIONS.exists():
        for f in sorted(MA_OPTIONS.iterdir()):
            if f.suffix.lower() in CSV_EXTS:
                if ticker_upper in f.name.upper():
                    result["options"].append(str(f))

    # Screenshots folder
    if MA_SCREENSHOTS.exists():
        for f in sorted(MA_SCREENSHOTS.iterdir()):
            if f.suffix.lower() in IMAGE_EXTS:
                if ticker_upper in f.name.upper():
                    result["screenshots"].append(str(f))

    return result

def scan_ma_pipeline_outputs() -> dict:
    """
    Scan MA_Inputs/pipeline_outputs for the latest pipeline CSV files.
    Returns dict matching find_pipeline_files() format.
    """
    found = {}
    keywords = PIPELINE_FILE_KEYWORDS


    if MA_INPUTS.exists():
        # Get all CSVs sorted newest first so root/manual drops are visible too.
        csvs = sorted(MA_INPUTS.rglob("*.csv"),
                      key=lambda f: f.stat().st_mtime, reverse=True)
        for f in csvs:
            name = f.name.lower()
            for key, kws in keywords.items():
                if any(kw in name for kw in kws) and key not in found:
                    found[key] = str(f)

    return found


def classify_ma_input_csvs() -> dict:
    """Classify every CSV under MA_Inputs as recognised pipeline or other/manual."""
    csvs = sorted(
        MA_INPUTS.rglob("*.csv"),
        key=lambda p: str(p.relative_to(MA_INPUTS)).lower(),
    ) if MA_INPUTS.exists() else []

    recognised = {}
    recognised_paths = set()
    for f in csvs:
        name = f.name.lower()
        for key, kws in PIPELINE_FILE_KEYWORDS.items():
            if any(kw in name for kw in kws):
                recognised.setdefault(key, []).append(str(f))
                recognised_paths.add(str(f))
                break

    missing = [key for key in EXPECTED_PIPELINE_FILE_KEYS if key not in recognised]
    other = [str(f) for f in csvs if str(f) not in recognised_paths]
    return {
        "all_csv_files": [str(f) for f in csvs],
        "recognised_csv_files": recognised,
        "other_csv_files": other,
        "missing_expected_pipeline_files": missing,
    }

def scan_all_ma_inputs() -> dict:
    """
    Full scan of MA_Inputs folder.
    Returns summary of what's available.
    """
    csv_classification = classify_ma_input_csvs()
    summary = {
        "pipeline_files": scan_ma_pipeline_outputs(),
        "chart_files":    {},
        "options_files":  {},
        "screenshot_files": {},
        "all_csv_files": csv_classification["all_csv_files"],
        "recognised_csv_files": csv_classification["recognised_csv_files"],
        "other_csv_files": csv_classification["other_csv_files"],
        "missing_expected_pipeline_files": csv_classification["missing_expected_pipeline_files"],
    }

    IMAGE_EXTS = {".png",".jpg",".jpeg",".gif",".webp"}
    CSV_EXTS   = {".csv"}

    # Group by ticker
    def group_by_ticker(folder, exts):
        groups = {}
        if folder.exists():
            for f in sorted(folder.iterdir()):
                if f.suffix.lower() in exts:
                    # Extract ticker from filename (first part before _)
                    ticker = f.name.split("_")[0].upper()
                    if ticker not in groups:
                        groups[ticker] = []
                    groups[ticker].append(str(f))
        return groups

    summary["chart_files"]      = group_by_ticker(MA_CHARTS, IMAGE_EXTS)
    summary["options_files"]    = group_by_ticker(MA_OPTIONS, CSV_EXTS)
    summary["screenshot_files"] = group_by_ticker(MA_SCREENSHOTS, IMAGE_EXTS)

    return summary

def get_ma_inputs_status() -> str:
    """Return a human-readable status of what's in MA_Inputs."""
    summary = scan_all_ma_inputs()
    lines = ["MA_Inputs folder status:"]

    pf = summary["pipeline_files"]
    lines.append(f"  Pipeline files: {len(pf)}")
    for k, v in pf.items():
        lines.append(f"    {k}: {Path(v).name}")

    recognised = summary.get("recognised_csv_files", {})
    recognised_count = sum(len(v) for v in recognised.values())
    lines.append(f"  Recognised CSV files: {recognised_count}")
    for k in sorted(recognised):
        names = ", ".join(Path(v).name for v in recognised[k])
        lines.append(f"    {k}: {names}")

    other = summary.get("other_csv_files", [])
    lines.append(f"  Other/manual CSV files: {len(other)}")
    for v in other:
        lines.append(f"    {Path(v).relative_to(MA_INPUTS)}")

    missing = summary.get("missing_expected_pipeline_files", [])
    if missing:
        lines.append("  Missing expected pipeline CSVs:")
        for key in missing:
            lines.append(f"    {key}")
    else:
        lines.append("  Missing expected pipeline CSVs: none")

    cf = summary["chart_files"]
    lines.append(f"  Chart files: {sum(len(v) for v in cf.values())} "
                 f"({len(cf)} tickers: {', '.join(sorted(cf.keys()))})")

    of = summary["options_files"]
    lines.append(f"  Options data: {sum(len(v) for v in of.values())} "
                 f"({len(of)} tickers: {', '.join(sorted(of.keys()))})")

    sf = summary["screenshot_files"]
    lines.append(f"  Screenshots: {sum(len(v) for v in sf.values())} "
                 f"({len(sf)} tickers: {', '.join(sorted(sf.keys()))})")

    all_tickers = sorted(set(list(cf.keys()) + list(of.keys()) + list(sf.keys())))
    if all_tickers:
        lines.append(f"  All tickers with data: {', '.join(all_tickers)}")
    else:
        lines.append("  No ticker-specific files found yet.")

    return "\n".join(lines)


# ── LIVE PRICE HELPERS ─────────────────────────────────────────────────────

def format_live_price_block(ticker: str, live_prices: dict) -> str:
    """
    Format the live price context block for injection into prompts.
    Returns empty string if no price registered for this ticker.
    """
    entry = live_prices.get(ticker.upper(), {})
    if not entry:
        return ""
    price     = entry.get("price", "")
    chg       = entry.get("change_pct", "")
    ts        = entry.get("timestamp", "")
    vwap      = entry.get("vwap", "")
    vol_ratio = entry.get("vol_ratio", "")
    spread    = entry.get("spread", "")
    lines = [f"LIVE PRICE DATA (registered {ts}):"]
    lines.append(f"  price:       {price}")
    if chg:      lines.append(f"  change_pct:  {chg}%")
    if vwap:     lines.append(f"  vwap:        {vwap}  (price {'above' if float(str(price) or 0) >= float(str(vwap) or 0) else 'below'} VWAP)")
    if vol_ratio:lines.append(f"  vol_ratio:   {vol_ratio}x average")
    if spread:   lines.append(f"  live_spread: {spread}  (verify before entry)")
    lines.append("  NOTE: Live price supersedes EOD pipeline price for trigger/invalidation assessment.")
    return "\n".join(lines)


def build_intraday_prompt(
    ticker: str,
    pipeline_row: dict,
    live_price_block: str = "",
    options_data: dict = None,
    ticker_note: str = "",
    chart_timeframes: list = None,
) -> str:
    """
    Build the intraday chart + live price analysis prompt.
    Called by cmd_intraday — feeds Dr. Magnus Vale chart read
    with 15/30m timeframe focus and live price context.

    chart_timeframes: list of strings describing uploaded charts,
    e.g. ["15m", "30m"] — used to direct the chart read.
    """
    date_str   = _date()
    timeframes = chart_timeframes or ["15m", "30m"]
    tf_str     = " + ".join(timeframes)

    row_text = "\n".join(
        f"{k}: {_translate_display_labels(str(v))}"
        for k, v in pipeline_row.items() if v
    )

    opt_text = ""
    if options_data:
        for name, content in options_data.items():
            if content:
                opt_text += f"\n{name.upper()}:\n{content[:500]}\n"

    _trader_note_block = ""
    if ticker_note and ticker_note.strip():
        _trader_note_block = (
            f"TICKER_NARRATIVE: {ticker}\n"
            f"{ticker_note.strip()}\n"
            f"END_TICKER_NARRATIVE\n\n"
        )

    combined_context = read_all_news_macro_context(
        ticker=ticker, ma_macro_dir=MA_MACRO, ma_news_dir=MA_NEWS
    )

    live_price_section = (
        f"\n{live_price_block}\n" if live_price_block
        else "\nLIVE PRICE: Not registered. Use /price TICKER PRICE to add.\n"
    )

    # Inject live market data (options volume, institutional flow, spread, peers)
    _live_mkt = LIVE_DATA.get(ticker.upper(), {})
    _live_mkt_block = format_live_data_for_prompt(_live_mkt) if _live_mkt else ""
    live_market_section = f"\n{_live_mkt_block}\n" if _live_mkt_block else ""

    return f"""Run Pipeline Interpreter — INTRADAY CHART ANALYSIS: {ticker}
{_trader_note_block}Date: {date_str}
Chart timeframes provided: {tf_str}

PIPELINE ROW (EOD thesis — treat as the prepared thesis context):
{row_text}
{live_price_section}{live_market_section}
OPTIONS DATA:
{opt_text if opt_text else 'Not provided.'}

MACRO + ENRICHMENT DELTA + NEWS:
{combined_context}

INTRADAY CHART READ INSTRUCTIONS:
The chart image(s) above show {ticker} on {tf_str} timeframes.
This is the LIVE CONFIRMATION layer — your job is to assess whether the
prepared EOD thesis is being confirmed, rejected, or is still forming.

Apply the Soul of the Chart intraday framework:

1. VWAP POSITION
   - Is price above or below VWAP right now?
   - Is VWAP acting as support (bullish thesis) or resistance (bearish thesis)?
   - How many times has price tested VWAP? Rejection or acceptance?

2. OPENING RANGE ASSESSMENT
   - Where did price open relative to yesterday's close and VWAP?
   - Has the opening range been broken? In which direction?
   - Is the break sustained or immediately faded?

3. TRIGGER PROXIMITY
   - How close is current price to the prepared trigger level from the pipeline?
   - Is price approaching from the correct side?
   - Is momentum building toward the trigger or fading?

4. INTRADAY VOLUME SIGNATURE
   - Is volume expanding on moves toward the trigger (confirming)?
   - Is volume declining on moves away (healthy pullback) or expanding (reversal)?
   - RVOL context — is today's session attracting institutional attention?

5. SHORT-TERM EMA STRUCTURE (on 15m/30m)
   - EMA9 vs EMA21 on intraday: aligned with thesis direction?
   - Any EMA crossover in progress?
   - Price relative to intraday VWAP and EMAs simultaneously

6. INTRADAY TRAPPED PARTICIPANTS
   - Who got trapped in the first 30 minutes?
   - Where are their stops clustered?
   - Will those stops fuel the thesis move or cause a whipsaw?

7. THESIS CONFIRMATION SCORE
   Rate the intraday evidence on a 0-10 scale:
   - 8-10: Thesis CONFIRMED intraday — consider PROBE entry
   - 5-7:  Thesis FORMING — watch but do not enter yet
   - 0-4:  Thesis NOT CONFIRMED — WAIT, do not enter

8. UPDATED EXECUTION PRESCRIPTION
   Based on what you see in the intraday charts AND the live price:
   - Is the trigger still valid or has it been breached/negated?
   - Exact entry condition for the NEXT 30-60 minutes
   - Updated kill switch based on intraday structure
   - If contract spread was previously flagged WIDE: is it acceptable now?

9. FIRST HOUR RULE CHECK
   For 1-5d horizon: Has the first hour confirmed direction?
   For 6-10d / 11-20d: Is the intraday structure consistent with thesis?

INTRADAY VERDICT (replaces morning validator output for this ticker):
INTRADAY_CONFIRMED  — thesis live, trigger valid, entry conditions met
INTRADAY_FORMING    — thesis intact but not yet triggered, watch
INTRADAY_WAIT       — thesis unclear, do not enter this session
INTRADAY_REJECTED   — intraday structure contradicts thesis, stand down

State the INTRADAY VERDICT clearly and give the single most important
price level to watch in the next 60 minutes.

execution_permission=NONE_PIPELINE_INTERPRETER_ONLY"""


def get_timestamp(): return datetime.now().strftime("%Y%m%d_%H%M")
def get_run_dir():
    ts=get_timestamp()
    d=OUTPUTS_DIR/ts; d.mkdir(parents=True,exist_ok=True)
    return d, ts


# ── STORY OF THE TRADE — additions only, appended at bottom ──────────────────

def build_story_prompt(
    ticker: str,
    pipeline_row: dict,
    live_price_block: str = "",
    options_data: dict = None,
    chart_images: list = None,
    ticker_note: str = "",
    previous_story_html: str = "",
    update_type: str = "FULL",  # FULL|CHART_UPDATE|OPTIONS_UPDATE|MACRO_UPDATE|OVERNIGHT
) -> str:
    """
    Build the Story of the Trade prompt for /story and /update commands.
    Mirrors build_intraday_prompt() context-gathering pattern.
    """
    date_str = _date()

    row_text = "\n".join(
        f"{k}: {_translate_display_labels(str(v))}"
        for k, v in pipeline_row.items() if v
    )

    opt_text = ""
    if options_data:
        for name, content in options_data.items():
            if content:
                opt_text += f"\n{name.upper()}:\n{content[:500]}\n"

    # Trader note: prefer explicit arg, fall back to trader_notes.json
    _trader_note_block = ""
    if ticker_note and ticker_note.strip():
        _trader_note_block = (
            f"TICKER_NARRATIVE: {ticker}\n"
            f"{ticker_note.strip()}\n"
            f"END_TICKER_NARRATIVE\n\n"
        )
    else:
        _notes_path = MA_INPUTS / "news_terminal" / "trader_notes.json"
        if _notes_path.exists():
            try:
                _notes = json.loads(_notes_path.read_text(encoding="utf-8"))
                _note_entry = _notes.get(ticker.upper(), {})
                _loaded_note = (
                    _note_entry.get("note", "")
                    if isinstance(_note_entry, dict)
                    else str(_note_entry)
                )
                if _loaded_note:
                    _trader_note_block = (
                        f"TICKER_NARRATIVE: {ticker}\n"
                        f"{_loaded_note.strip()}\n"
                        f"END_TICKER_NARRATIVE\n\n"
                    )
            except Exception:
                pass

    combined_context = read_all_news_macro_context(
        ticker=ticker, ma_macro_dir=MA_MACRO, ma_news_dir=MA_NEWS
    )

    _lpb = live_price_block or format_live_price_block(ticker, LIVE_PRICES)
    live_price_section = (
        f"\n{_lpb}\n" if _lpb
        else "\nLIVE PRICE: Not registered. Use /price TICKER PRICE to add.\n"
    )

    _live_mkt = LIVE_DATA.get(ticker.upper(), {})
    _live_mkt_block = format_live_data_for_prompt(_live_mkt) if _live_mkt else ""
    live_market_section = f"\n{_live_mkt_block}\n" if _live_mkt_block else ""

    # Previous story context — only included for update types
    previous_story_section = ""
    if previous_story_html:
        _update_instructions = {
            "FULL":           "Regenerate all 8 sections.",
            "CHART_UPDATE":   "Regenerate sections 5 (Chart) and 8 (Verdict) only. Carry forward sections 1,2,3,4,6,7 verbatim with CARRIED_FORWARD_FROM marker.",
            "OPTIONS_UPDATE": "Regenerate sections 6 (Options) and 8 (Verdict) only. Carry forward sections 1,2,3,4,5,7 verbatim with CARRIED_FORWARD_FROM marker.",
            "MACRO_UPDATE":   "Regenerate section 1 (Macro) and 8 (Verdict) only. Carry forward sections 2,3,4,5,6,7 verbatim with CARRIED_FORWARD_FROM marker.",
            "OVERNIGHT":      "Regenerate sections 1 (Macro), 5 (Chart), and 8 (Verdict). Carry forward sections 2,3,4,6,7 verbatim with CARRIED_FORWARD_FROM marker.",
        }
        _instruction = _update_instructions.get(update_type, "Regenerate all 8 sections.")
        previous_story_section = (
            f"\nPREVIOUS_STORY_CONTEXT:\n"
            f"update_type: {update_type}\n"
            f"Instruction: {_instruction}\n"
            f"When carrying forward a section output:\n"
            f"  [SECTION_N_NAME]\n"
            f"  [CARRIED_FORWARD_FROM: {{previous_ts}}]\n"
            f"  {{previous section content verbatim}}\n\n"
            f"--- PREVIOUS STORY HTML ---\n"
            f"{previous_story_html[:8000]}\n"
            f"--- END PREVIOUS STORY ---\n"
        )

    return (
        f"OUTPUT FORMAT: Produce ONLY a [JUNIOR_BRIEFING_{ticker.upper()}] block.\n"
        f"Do NOT produce [TRADE_NARRATIVE_{ticker.upper()}]. No preamble. No conclusion.\n"
        f"Start your response with [JUNIOR_BRIEFING_{ticker.upper()}] and nothing before it.\n\n"
        f"Run Pipeline Interpreter — STORY OF THE TRADE: {ticker}\n"
        f"update_type: {update_type}\n"
        f"{_trader_note_block}"
        f"Date: {date_str}\n\n"
        f"PIPELINE ROW (EOD thesis — primary data source for all 8 sections):\n"
        f"{row_text}\n"
        f"{live_price_section}"
        f"{live_market_section}"
        f"\nOPTIONS DATA:\n"
        f"{opt_text if opt_text else 'Not provided.'}\n\n"
        f"MACRO + ENRICHMENT DELTA + NEWS:\n"
        f"{combined_context}\n"
        f"{previous_story_section}\n"
        f"STORY OF THE TRADE INSTRUCTIONS:\n"
        f"Produce a [JUNIOR_BRIEFING_{ticker.upper()}] block containing all 8 sections\n"
        f"as defined in the JUNIOR TRADER LAYER system prompt section.\n\n"
        f"Each section must:\n"
        f"- Open with STATUS: {{one of the permitted badge values}}\n"
        f"- Explain all concepts in plain English; define every technical term on first use\n"
        f"- End with INTERDEP: explaining the connection to adjacent sections\n\n"
        f"Section 2 must explain gamma flip -> gamma island -> wall break structure as a cascade.\n"
        f"Section 3 must label every level: KILL_ZONE / RESISTANCE / VWAP_BATTLEGROUND /\n"
        f"  ENTRY_TRIGGER / GAMMA_FLIP / SWING_EXTREME / WALL_TARGET\n"
        f"Section 5 must contain a checkpoint table: Checkpoint | Required for thesis | Status\n"
        f"Section 8 must contain WHAT_MAKES_US_ENTER and WHAT_MAKES_US_ABANDON sub-boxes.\n\n"
        f"execution_permission=NONE_PIPELINE_INTERPRETER_ONLY"
    )


def build_overnight_delta(
    ticker: str,
    pipeline_row: dict,
    previous_story_state: dict,  # from thesis_registry state_chain[-1]
    macro_context: str = "",
    news_context: str = "",
) -> str:
    """
    Produce a compact overnight delta block for triage injection.
    Checks overnight gap vs kill_switch_level and probe_trigger.
    Returns OVERNIGHT_DELTA_{ticker} block as a string.
    """
    prev_verdict    = previous_story_state.get("verdict", "UNKNOWN")
    prev_ts         = previous_story_state.get("ts", "UNKNOWN")
    kill_switch     = float(pipeline_row.get("kill_switch_level", 0) or 0)
    probe_trigger   = float(pipeline_row.get("probe_trigger", 0) or 0)
    armed_trigger   = float(pipeline_row.get("armed_trigger", 0) or 0)
    last_price      = pipeline_row.get("last_price", "") or pipeline_row.get("price", "")

    # Gap assessment
    try:
        price_float = float(str(last_price).replace("$", "").replace(",", ""))
    except (ValueError, TypeError):
        price_float = 0.0

    if price_float > 0 and kill_switch > 0:
        gap_vs_ks = ((price_float - kill_switch) / kill_switch) * 100
        ks_status = (
            f"BREACHED (${price_float:.2f} >= kill switch ${kill_switch:.2f})"
            if price_float >= kill_switch
            else f"SAFE (${kill_switch:.2f} not breached, {abs(gap_vs_ks):.1f}% away)"
        )
    else:
        ks_status = "UNKNOWN (price or kill_switch not in pipeline row)"

    if price_float > 0 and probe_trigger > 0:
        gap_vs_probe = ((price_float - probe_trigger) / probe_trigger) * 100
        trigger_status = (
            f"TRIGGERED_OVERNIGHT (price ${price_float:.2f} at/through probe trigger ${probe_trigger:.2f})"
            if abs(gap_vs_probe) <= 0.5
            else f"AWAY (probe trigger ${probe_trigger:.2f}, {gap_vs_probe:+.1f}% gap)"
        )
    else:
        trigger_status = "UNKNOWN"

    # Macro shift — look for significant keywords in macro_context
    macro_shift = "NO_SIGNIFICANT_CHANGE"
    if macro_context:
        _macro_lower = macro_context.lower()
        _shift_keywords = ["regime change", "spike", "crash", "fed", "cpi", "fomc",
                           "rate cut", "rate hike", "reversal", "surprise"]
        if any(kw in _macro_lower for kw in _shift_keywords):
            macro_shift = "CHANGE_DETECTED — review macro context before /story"

    # News flags for this ticker
    news_flags = "NONE"
    if news_context and ticker.upper() in news_context.upper():
        news_flags = "TICKER_MENTIONED — review newsroom brief"

    # Carry-forward action
    direction = pipeline_row.get("direction", "").upper()
    carry_action = "CONTINUE_MONITORING"
    if "BREACHED" in ks_status:
        carry_action = "CLOSE_THESIS — kill switch breached overnight"
    elif "TRIGGERED" in trigger_status:
        carry_action = "ALERT — trigger tested overnight, reassess at open"

    return (
        f"OVERNIGHT_DELTA_{ticker.upper()}:\n"
        f"  previous_verdict:       {prev_verdict}\n"
        f"  previous_ts:            {prev_ts}\n"
        f"  overnight_price:        ${price_float:.2f}\n"
        f"  direction:              {direction}\n"
        f"  kill_switch_status:     {ks_status}\n"
        f"  trigger_status:         {trigger_status}\n"
        f"  armed_trigger:          ${armed_trigger:.2f}\n"
        f"  macro_shift:            {macro_shift}\n"
        f"  news_flags:             {news_flags}\n"
        f"  carry_forward_action:   {carry_action}\n"
    )


def get_latest_story_for_thesis(ticker: str, outputs_dir: Path = None) -> str:
    """
    Scan outputs/ for the most recent story_{ticker}_*.html by mtime.
    Returns file contents as a string, or empty string if none found.
    Called by /update command — Option B cross-session retrieval.
    """
    search_dir = outputs_dir or OUTPUTS_DIR
    if not search_dir.exists():
        return ""
    pattern = f"story_{ticker.upper()}_*.html"
    candidates = list(search_dir.rglob(pattern))
    if not candidates:
        return ""
    latest = max(candidates, key=lambda p: p.stat().st_mtime)
    try:
        return latest.read_text(encoding="utf-8")
    except OSError:
        return ""


# ── COMPONENT 9 — Intelligence Lab Reconciliation — additions at bottom ───────

# Lab export folder path constant
MA_LAB = MA_INPUTS / "lab_export"

# Create lab_export folder on startup alongside all other MA_Inputs subfolders
MA_LAB.mkdir(parents=True, exist_ok=True)

# Register lab export pattern in file-keyword lookup so scan functions detect it
PIPELINE_FILE_KEYWORDS["lab_export"] = ["avshunter_signals"]
