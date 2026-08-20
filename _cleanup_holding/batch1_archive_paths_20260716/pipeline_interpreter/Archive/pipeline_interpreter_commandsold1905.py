"""
AVSHUNTER Pipeline Interpreter v1.0 â€” Command Router
"""
import time
from pathlib import Path
from pipeline_interpreter_engine import (
    call_api, session, SESSION, get_run_dir, parse_brief_csv,
    read_pipeline_csv, read_options_file, find_pipeline_files,
    build_interpret_prompt, build_single_ticker_prompt,
    build_morning_validation_prompt, build_chart_prompt,
    scan_ma_inputs_for_ticker, scan_ma_pipeline_outputs,
    scan_all_ma_inputs, get_ma_inputs_status, build_triage_prompt,
    MA_INPUTS, MA_CHARTS, MA_OPTIONS, MA_SCREENSHOTS, MA_PIPELINE, MA_MACRO, MA_NEWS,
    EXECUTION_PERMISSION
)
from ma_inputs_sync import sync_to_ma_inputs, show_status as sync_show_status, MA_PIPELINE_OUT
from pipeline_interpreter_outputs import write_all_outputs, write_triage_outputs, _extract_section
try:
    from interpreter_qa import check_triage_qa, check_ticker_qa, print_qa_report, append_qa_log
    _QA_AVAILABLE = True
except ImportError:
    _QA_AVAILABLE = False


MENU = """
â•”â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•—
â•‘     AVSHUNTER PIPELINE INTERPRETER v1.0 â€” COMMAND MENU          â•‘
â• â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•£
â•‘  /triage [FILE]               Fast priority scan â€” rank all candidates  â•‘
â•‘  /interpret FILE [FILE2...]   Interpret pipeline CSV file(s)     â•‘
â•‘  /morning FILE                Morning validation pass            â•‘
â•‘  /ticker TICKER FILE          Deep dive single ticker            â•‘
â•‘  /chart TICKER IMG [IMG2...]  Chart image analysis (vision)      â•‘
â•‘  /auto                        Auto-detect pipeline files         â•‘
â•‘  /load FILE                   Load a pipeline CSV into session   â•‘
â•‘  /options FILE                Add options data file              â•‘
â•‘  /sync                        Sync AVSHUNTER outputs to MA_Inputs     â•‘
â•‘  /macro FILE                  Load macro intelligence JSON/file       â•‘
â•‘  /news FILE [TICKER]          Load News Terminal CSV/output           â•‘
â•‘  /inputs                      Show MA_Inputs folder status          â•‘
â•‘  /status                      Show session summary               â•‘
â•‘  /reset                       Clear session                      â•‘
â•‘  /menu                        Show this menu                     â•‘
â•‘  /exit                        Close interpreter                  â•‘
â•šâ•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•"""

# Loaded data store
_loaded_pipeline = {}   # name -> rows
_loaded_options  = {}   # name -> content

def _safe_name(v):
    from pathlib import Path
    if v is None: return None
    if isinstance(v,(str,Path)): return Path(v).name
    if isinstance(v,dict): p=v.get("path"); return Path(p).name if p else None
    return str(v)


def _print_all_ma_input_csvs():
    """Print every CSV physically present before recognised-file classification."""
    csv_files = sorted(
        MA_INPUTS.rglob("*.csv"),
        key=lambda p: str(p.relative_to(MA_INPUTS)).lower(),
    ) if MA_INPUTS.exists() else []

    print("  All CSV files physically present:")
    if not csv_files:
        print("    (none)")
        return

    for idx, path in enumerate(csv_files, 1):
        print(f"    {idx:>3}. {path.relative_to(MA_INPUTS)}")
def _print_results(results:dict, response:str=""):
    print()
    if "brief_csv" in results:
        n=_safe_name(results["brief_csv"]); r=results["brief_csv"].get("rows","?") if isinstance(results["brief_csv"],dict) else "?"
        if n: print(f"  âœ… {n:<52} ({r} rows)")
    if "html" in results:
        n=_safe_name(results["html"])
        if n: print(f"  âœ… {n}")
    print()
    # Print verdicts
    s=session.summary()
    if s["go"]:      print(f"  GO:      {', '.join(s['go'])}")
    if s["armed"]:   print(f"  ARMED:   {', '.join(s['armed'])}")
    if s["wait"]:    print(f"  WAIT:    {', '.join(s['wait'])}")
    if s["blocked"]: print(f"  BLOCKED: {', '.join(s['blocked'])}")
    print(f"\n  {EXECUTION_PERMISSION}")

def cmd_triage(file_path:str=None):
    """
    Fast triage pass â€” rank and prioritise the whole candidate list.
    No deep dive. One API call. Produces ranked HTML + CSV.
    Run this BEFORE /ticker to know who gets the deep dive today.
    """
    global _loaded_pipeline

    print("\n  Running triage priority scan...")

    # Load pipeline data
    rows = []
    source_name = ""

    ma_summary = scan_all_ma_inputs()
    all_csvs = ma_summary.get("all_csv_files", [])
    recognised = ma_summary.get("recognised_csv_files", {})
    recognised_count = sum(len(v) for v in recognised.values())
    other_csvs = ma_summary.get("other_csv_files", [])
    missing = ma_summary.get("missing_expected_pipeline_files", [])

    if all_csvs:
        print(f"  MA_Inputs CSV inventory: {len(all_csvs)} present | {recognised_count} recognised | {len(other_csvs)} other/manual")
        for idx, p in enumerate(all_csvs, 1):
            try:
                rel = Path(p).relative_to(MA_INPUTS)
            except ValueError:
                rel = Path(p).name
            print(f"    {idx:>3}. {rel}")
    else:
        print("  MA_Inputs CSV inventory: 0 present")

    if missing:
        print("  Missing expected pipeline CSVs: " + ", ".join(missing))
    else:
        print("  Missing expected pipeline CSVs: none")

    if file_path:
        rows = read_pipeline_csv(file_path)
        source_name = Path(file_path).name
    elif _loaded_pipeline:
        # Use already-loaded pipeline data
        for name, r in _loaded_pipeline.items():
            rows.extend(r)
            source_name = name
            break
    else:
        # Auto-scan MA_Inputs
        found = scan_ma_pipeline_outputs()
        if found:
            # Use the file closest to manual execution first.
            best = (
                found.get("morning_validated")
                or found.get("morning_candidates")
                or found.get("top_trades")
                or found.get("morning_validation")
                or found.get("execution")
                or found.get("eil")
                or found.get("superbrain")
                or list(found.values())[0]
            )
            rows = read_pipeline_csv(best)
            source_name = Path(best).name
            print(f"  âœ… Auto-loaded: {source_name}")

    if not rows:
        print("  âš  No pipeline data found.")
        print(f"  Drop pipeline CSV into: {MA_PIPELINE}")
        print("  Or: /triage PATH/TO/pipeline.csv")
        return

    # Fix A -- lock source CSV into SESSION for /ticker auto-load
    from datetime import datetime as _dt
    if file_path:
        SESSION["last_pipeline_csv"] = str(file_path)
    elif found:
        _best = (
            found.get("morning_validated") or found.get("morning_candidates")
            or found.get("top_trades") or found.get("execution")
            or found.get("eil") or list(found.values())[0]
        )
        SESSION["last_pipeline_csv"] = str(_best)
    SESSION["last_triage_run"] = _dt.now().isoformat()
    if SESSION.get("last_pipeline_csv"):
        print(f"  [SESSION] CSV locked: {Path(SESSION['last_pipeline_csv']).name}")
        print(f"  [SESSION] /ticker <TICKER> ready")

    print(f"  Candidates: {len(rows)} rows from {source_name}")
    # B2 FIX: Filter BLOCKED tickers from triage session
    # These should not have reached morning_candidates but filter defensively
    if rows and "eil_v3_verdict" in rows[0]:
        _blocked_in_triage = sum(
            1 for r in rows if str(r.get("eil_v3_verdict", "")).upper() == "BLOCKED"
        )
        if _blocked_in_triage > 0:
            print(f"  ⚠  B2 GUARD: {_blocked_in_triage} BLOCKED tickers excluded from triage ranking")
            rows = [r for r in rows if str(r.get("eil_v3_verdict", "")).upper() != "BLOCKED"]

    # Get MA_Inputs availability for completeness scoring
    chart_tickers = set(ma_summary.get("chart_files", {}).keys())
    opt_tickers   = set(ma_summary.get("options_files", {}).keys())
    if chart_tickers or opt_tickers:
        print(f"  MA_Inputs data: charts for {sorted(chart_tickers)}, options for {sorted(opt_tickers)}")

    t0 = time.time()
    prompt = build_triage_prompt(rows, ma_summary)
    response = call_api(prompt)  # No web search â€” pure pipeline analysis

    run_dir, ts = get_run_dir()
    results = write_triage_outputs(response, run_dir, ts)

    elapsed = int(time.time() - t0)
    print(f"\n  Triage complete ({elapsed}s)")
    print()

    # Print results
    tc = results.get("triage_csv", {})
    th = results.get("triage_html", {})
    n = tc.get("rows", 0) if isinstance(tc, dict) else "?"
    tc_name = _safe_name(tc)
    th_name = _safe_name(th)
    if tc_name: print(f"  âœ… {tc_name:<52} ({n} ranked)")
    if th_name: print(f"  âœ… {th_name}")
    print()

    # Print execution order to console
    from pipeline_interpreter_outputs import _extract_section as _es
    order = _es(response, "TRIAGE_EXECUTION_ORDER")
    summary = _es(response, "TRIAGE_SUMMARY")

    if summary:
        print(f"{'â”€'*60}")
        print("  SESSION PICTURE")
        print('â”€'*60)
        for line in summary.split('\n')[:15]:
            if line.strip(): print(f"  {line}")

    if order:
        print(f"\n{'â”€'*60}")
        print("  TODAY'S EXECUTION ORDER")
        print('â”€'*60)
        for line in order.split('\n')[:12]:
            if line.strip(): print(f"  {line}")
        print()

    print(f"  Next step: run /ticker for each DEEP_DIVE_NOW ticker")
    print(f"  {EXECUTION_PERMISSION}")

    # QA check after triage
    if _QA_AVAILABLE:
        try:
            _qa = check_triage_qa(
                pipeline_csv   = SESSION.get("pipeline_csv") or SESSION.get("last_pipeline_csv"),
                macro_json     = SESSION.get("macro_json") or "",
                candidates_csv = SESSION.get("catalyst_csv"),
            )
            if _qa.get("checks", {}).get("pipeline_csv", {}).get("status") != "FAIL":
                print_qa_report(_qa)
                append_qa_log(_qa)
        except Exception as _qe:
            print(f"  [QA] Skipped: {_qe}")

    return response


def cmd_interpret(file_paths:list):
    global _loaded_pipeline
    print(f"\n  Loading {len(file_paths)} pipeline file(s)...")
    pipeline_data={}
    tickers=[]
    for fp in file_paths:
        rows=read_pipeline_csv(fp)
        if rows:
            name=Path(fp).stem
            pipeline_data[name]=rows
            # Extract tickers
            for row in rows:
                t=row.get("ticker") or row.get("underlying") or row.get("symbol","")
                if t and t not in tickers: tickers.append(t.strip())
    if not pipeline_data:
        print("  âš  No pipeline data loaded."); return

    print(f"  Tickers found: {', '.join(tickers[:20])}")

    # Auto-load options data from MA_Inputs for detected tickers
    ma_options_loaded = 0
    for ticker in tickers[:20]:
        ma_files = scan_ma_inputs_for_ticker(ticker)
        for opt_path in ma_files["options"]:
            opt_name = Path(opt_path).stem
            if opt_name not in _loaded_options:
                content = read_options_file(opt_path)
                _loaded_options[opt_name] = content
                ma_options_loaded += 1
    if ma_options_loaded > 0:
        print(f"  âœ… Auto-loaded {ma_options_loaded} options file(s) from MA_Inputs")

    print(f"  Running Dr. Magnus Vale + Soul of the Chart analysis...")
    t0=time.time()

    prompt=build_interpret_prompt(pipeline_data, _loaded_options if _loaded_options else None,
                                   focus_tickers=tickers[:15])
    response=call_api(prompt)
    run_dir,ts=get_run_dir()
    results=write_all_outputs(response,session,run_dir,ts,tickers=tickers)
    print(f"\n  Interpretation complete ({int(time.time()-t0)}s)")
    _print_results(results,response)
    return response

def cmd_morning(file_path:str):
    print(f"\n  Running morning validation pass...")
    rows=read_pipeline_csv(file_path)
    if not rows: print("  âš  No data loaded."); return
    tickers=[r.get("ticker","") for r in rows if r.get("ticker","")]

    # Load macro context if available
    macro_ctx=None
    macro_paths=[
        r"C:\Users\ACKVerissimo\AVSHUNTER-Intelligence\dropbox\macro\macro_intelligence_latest.json",
        Path.home()/"AVSHUNTER-Intelligence"/"dropbox"/"macro"/"macro_intelligence_latest.json"
    ]
    for mp in macro_paths:
        if Path(mp).exists():
            macro_ctx=read_options_file(str(mp))[:1500]
            print(f"  âœ… Macro context loaded")
            break

    t0=time.time()
    prompt=build_morning_validation_prompt(rows,macro_ctx)
    response=call_api(prompt)
    run_dir,ts=get_run_dir()
    results=write_all_outputs(response,session,run_dir,ts,tickers=tickers,prefix="morning")
    print(f"\n  Morning validation complete ({int(time.time()-t0)}s)")
    _print_results(results,response)
    return response

def cmd_ticker(ticker:str, file_path:str=None):
    print(f"\n  Running deep dive: {ticker}...")
    # Fix A -- auto-load CSV from SESSION if no file_path given
    if not file_path:
        file_path = SESSION.get("last_pipeline_csv")
        if not file_path:
            print("  [ERROR] No CSV loaded. Run /triage first or: /ticker TICKER FILE")
            return
        print(f"  [AUTO] {Path(file_path).name}")
    rows=read_pipeline_csv(file_path)
    row=next((r for r in rows if r.get("ticker","").upper()==ticker.upper()),None)
    if not row:
        # Try other field names
        row=next((r for r in rows if ticker.upper() in str(r.get("underlying","")).upper()),None)
    if not row:
        print(f"  âš  Ticker {ticker} not found in {Path(file_path).name}")
        if rows: print(f"  Available: {[r.get('ticker','?') for r in rows[:10]]}")
        return

    # Fix C -- never block analysis on execution_permission value
    _NON_LIVE = {"NONE_NEWS_TERMINAL_ONLY", "WATCHLIST_ONLY", "PIPELINE_BLOCKED"}
    _perm = row.get("execution_permission", "UNKNOWN")
    if _perm in _NON_LIVE:
        print(f"  [NOTE] execution_permission={_perm} -- analysis proceeds")

    # Auto-load from MA_Inputs for this ticker
    ma_files = scan_ma_inputs_for_ticker(ticker)
    ticker_options = dict(_loaded_options)  # start with already-loaded
    for opt_path in ma_files["options"]:
        opt_name = Path(opt_path).stem
        if opt_name not in ticker_options:
            ticker_options[opt_name] = read_options_file(opt_path)
            print(f"  âœ… Auto-loaded: {Path(opt_path).name}")

    # Combine charts: MA_Inputs charts + already-loaded
    ticker_charts = ma_files["charts"] + ma_files["screenshots"]
    if ticker_charts:
        print(f"  âœ… Found {len(ticker_charts)} chart(s) in MA_Inputs for {ticker}")

    t0=time.time()

    # If we have charts, use chart-aware API call
    if ticker_charts:
        prompt=build_chart_prompt(ticker=ticker, chart_descriptions=[],
                                   pipeline_row=row,
                                   options_data=ticker_options if ticker_options else None)
        response=call_api(prompt, images=ticker_charts)
    else:
        prompt=build_single_ticker_prompt(ticker,row,ticker_options if ticker_options else None)
        response=call_api(prompt)
    run_dir,ts=get_run_dir()
    results=write_all_outputs(response,session,run_dir,ts,tickers=[ticker],
                               prefix=f"ticker_{ticker.lower()}")
    print(f"\n  Deep dive complete ({int(time.time()-t0)}s)")
    _print_results(results,response)
    return response

def cmd_auto():
    global _loaded_pipeline
    print("\n  Auto-detecting pipeline files...")

    # Auto-sync from AVSHUNTER outputs first
    print("  Syncing from AVSHUNTER output folders...")
    sync_to_ma_inputs(max_age_hours=24, verbose=False)

    # Scan MA_Inputs/pipeline_outputs first
    found = scan_ma_pipeline_outputs()
    if found:
        print(f"  âœ… Found {len(found)} file(s) in MA_Inputs/pipeline_outputs/")
    else:
        # Fallback to standard locations
        found = find_pipeline_files()

    if not found:
        print("  âš  No pipeline files found.")
        print(f"  Drop pipeline CSVs into: {MA_PIPELINE}")
        print("  Or use /interpret PATH/TO/FILE.csv to specify manually.")
        return
    print(f"  Found {len(found)} file(s):")
    for name,path in found.items():
        print(f"    {name}: {path}")

    pipeline_data={}; tickers=[]
    for name,path in found.items():
        rows=read_pipeline_csv(path)
        if rows:
            pipeline_data[name]=rows
            for r in rows:
                t=r.get("ticker") or r.get("underlying","")
                if t and t not in tickers: tickers.append(t.strip())

    if not pipeline_data: print("  âš  No data loaded."); return
    print(f"\n  Tickers: {', '.join(tickers[:20])}")
    print(f"  Running interpretation...")
    t0=time.time()
    prompt=build_interpret_prompt(pipeline_data,_loaded_options or None,tickers[:15])
    response=call_api(prompt)
    run_dir,ts=get_run_dir()
    results=write_all_outputs(response,session,run_dir,ts,tickers=tickers)
    print(f"\n  Auto-interpretation complete ({int(time.time()-t0)}s)")
    _print_results(results,response)
    return response

def cmd_load(file_path:str):
    global _loaded_pipeline
    rows=read_pipeline_csv(file_path)
    if rows:
        name=Path(file_path).stem
        _loaded_pipeline[name]=rows
        print(f"  âœ… Loaded {len(rows)} rows as '{name}'")
    else:
        print(f"  âš  Could not load {file_path}")

def cmd_options(file_path:str):
    global _loaded_options
    content=read_options_file(file_path)
    name=Path(file_path).stem
    _loaded_options[name]=content
    print(f"  âœ… Options data loaded: {name} ({len(content)} chars)")

def cmd_chart(ticker:str, image_paths:list, chart_types:list=None):
    """Analyse chart image(s) for a ticker through Dr. Magnus Vale + Soul of the Chart."""
    global _loaded_pipeline, _loaded_options

    print(f"\n  Running chart analysis: {ticker}")
    print(f"  Images: {[Path(p).name for p in image_paths]}")

    # Auto-scan MA_Inputs for this ticker if no images provided or paths invalid
    ma_files = scan_ma_inputs_for_ticker(ticker)
    ma_charts = ma_files["charts"] + ma_files["screenshots"]

    # Validate provided paths
    valid_images = []
    for p in image_paths:
        if Path(p).exists():
            valid_images.append(p)
        else:
            print(f"  âš  Image not found: {p}")

    # Supplement with MA_Inputs charts not already in the list
    for mc in ma_charts:
        if mc not in valid_images:
            valid_images.append(mc)
            print(f"  âœ… Auto-loaded from MA_Inputs: {Path(mc).name}")

    if not valid_images:
        print(f"  âš  No chart images found.")
        print(f"  Drop chart screenshots into: {MA_CHARTS} or {MA_SCREENSHOTS}")
        print(f"  Name them: {ticker}_daily.png, {ticker}_intraday.png, etc.")
        return

    # Also auto-load options data for this ticker from MA_Inputs
    for opt_path in ma_files["options"]:
        opt_name = Path(opt_path).stem
        if opt_name not in _loaded_options:
            _loaded_options[opt_name] = read_options_file(opt_path)
            print(f"  âœ… Auto-loaded options: {Path(opt_path).name}")

    # Try to find pipeline row for this ticker
    pipeline_row = None
    for name, rows in _loaded_pipeline.items():
        row = next((r for r in rows
                    if r.get("ticker","").upper() == ticker.upper()
                    or r.get("underlying","").upper() == ticker.upper()), None)
        if row:
            pipeline_row = row
            print(f"  âœ… Pipeline row found in {name}")
            break

    if not pipeline_row:
        print(f"  â„¹ No pipeline row loaded for {ticker}.")
        print(f"  Use /load FILE to load pipeline data first for richer analysis.")

    # Determine chart types from filenames if not provided
    if not chart_types:
        chart_types = []
        for p in valid_images:
            name = Path(p).stem.lower()
            if "daily" in name: chart_types.append("daily")
            elif "weekly" in name: chart_types.append("weekly")
            elif "intraday" in name or "1h" in name or "15m" in name:
                chart_types.append("intraday")
            elif "chain" in name: chart_types.append("options_chain")
            elif "gex" in name: chart_types.append("GEX")
            elif "oi" in name: chart_types.append("open_interest")
            else: chart_types.append(Path(p).stem)

    t0 = __import__("time").time()
    prompt = build_chart_prompt(
        ticker=ticker,
        chart_descriptions=[],
        pipeline_row=pipeline_row,
        options_data=_loaded_options if _loaded_options else None,
        chart_types=chart_types
    )

    # Call API with images
    response = call_api(prompt, images=valid_images)
    run_dir, ts = get_run_dir()

    from pipeline_interpreter_outputs import write_all_outputs
    results = write_all_outputs(
        response, session, run_dir, ts,
        tickers=[ticker],
        prefix=f"chart_{ticker.lower()}"
    )

    print(f"\n  Chart analysis complete ({int(__import__('time').time()-t0)}s)")
    _print_results(results, response)

    # Print key sections to console
    from pipeline_interpreter_outputs import _extract_section
    for section in ["SOUL OF THE CHART â€” BEHAVIOURAL VERDICT",
                    "EXECUTION PRESCRIPTION", "KILL SWITCH", "FINAL VERDICT"]:
        content = _extract_section(response, section)
        if not content:
            # Search for it in the response text
            lines = response.split("\n")
            for i, line in enumerate(lines):
                if section.upper() in line.upper():
                    snippet = "\n".join(lines[i:i+8])
                    print(f"\n  {section}:\n  {snippet[:400]}")
                    break
        else:
            print(f"\n  {section}:\n  {content[:400]}")

    return response


def cmd_macro(file_path:str):
    """Load a macro intelligence file into MA_Inputs/macro/."""
    import shutil
    p = Path(file_path.strip('"').strip("'"))
    if not p.exists():
        print(f"  âš  File not found: {p}"); return
    dest = MA_MACRO / p.name
    shutil.copy2(p, dest)
    print(f"  âœ… Macro file loaded: {p.name}")
    print(f"  Location: {dest}")
    print(f"  Will be auto-read on next /ticker or /interpret run.")

def cmd_news(file_path:str, ticker:str=None):
    """Load a News Terminal output file into MA_Inputs/news_terminal/."""
    import shutil
    p = Path(file_path.strip('"').strip("'"))
    if not p.exists():
        print(f"  âš  File not found: {p}"); return
    dest = MA_NEWS / p.name
    shutil.copy2(p, dest)
    print(f"  âœ… News Terminal file loaded: {p.name}")
    if ticker:
        print(f"  Will filter for ticker: {ticker}")
    print(f"  Location: {dest}")
    print(f"  Will be auto-read on next /ticker or /interpret run.")


def cmd_sync(source_path:str=None, hours:int=24):
    """Sync AVSHUNTER output files into MA_Inputs automatically."""
    print(f"\n  Syncing AVSHUNTER outputs to MA_Inputs...")
    if source_path:
        print(f"  Source: {source_path}")
    result = sync_to_ma_inputs(
        source_dir=source_path if source_path else None,
        max_age_hours=hours,
        verbose=True
    )
    total = sum(v for k,v in result.items() if k not in ("skipped","errors"))
    print(f"\n  Total files synced: {total}")
    if total > 0:
        print(f"  MA_Inputs is ready. Run /auto or /triage to proceed.")
    else:
        print(f"  Nothing new to sync.")
        print(f"  If files exist but weren't picked up:")
        print(f"    1. Check AVSHUNTER_OUTPUT_DIRS in ma_inputs_sync.py")
        print(f"    2. Use /sync PATH to specify your output folder directly")
        print(f"    3. Or drop files manually into MA_Inputs\\pipeline_outputs\\")


def cmd_inputs():
    """Show status of MA_Inputs folder."""
    print(f"\n  MA_Inputs folder: {MA_INPUTS}")
    print()
    _print_all_ma_input_csvs()
    print()
    print(get_ma_inputs_status())
    print()
    print(f"  Subfolders:")
    print(f"    charts              -> {MA_CHARTS}")
    print(f"    options_data        -> {MA_OPTIONS}")
    print(f"    screenshots         -> {MA_SCREENSHOTS}")
    print(f"    pipeline_outputs    -> {MA_PIPELINE}")
    print(f"    macro               -> {MA_MACRO}")
    print(f"    news_terminal       -> {MA_NEWS}")

    # Show macro and news status
    macro_files = list(MA_MACRO.glob("*.*")) if MA_MACRO.exists() else []
    news_files  = list(MA_NEWS.glob("*.*")) if MA_NEWS.exists() else []
    print()
    if macro_files:
        latest_macro = max(macro_files, key=lambda f: f.stat().st_mtime)
        print(f"  âœ… Macro loaded:        {latest_macro.name}")
    else:
        print(f"  âš   Macro:              No file â€” use /macro FILE to load")
    if news_files:
        latest_news = max(news_files, key=lambda f: f.stat().st_mtime)
        print(f"  âœ… News Terminal loaded: {latest_news.name}")
    else:
        print(f"  âš   News Terminal:      No file â€” use /news FILE to load")
    print()
    print(f"  Drop files or use /macro and /news commands to load context.")


def cmd_status():
    s=session.summary()
    print(f"""
  â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
  PIPELINE INTERPRETER SESSION STATUS
  â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
  Date:             {session.session_date}
  Total Candidates: {s["total"]}
  GO:               {', '.join(s["go"]) if s["go"] else 'â€”'}
  ARMED:            {', '.join(s["armed"]) if s["armed"] else 'â€”'}
  WAIT/PROBE:       {len(s["wait"])} tickers
  BLOCKED:          {len(s["blocked"])} tickers
  Loaded Pipeline:  {list(_loaded_pipeline.keys()) or 'None'}
  Loaded Options:   {list(_loaded_options.keys()) or 'None'}
  â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€""")

def cmd_reset():
    global _loaded_pipeline, _loaded_options
    session.reset()
    _loaded_pipeline={}; _loaded_options={}
    print("\n  âœ… Session cleared. Rules preserved. Ready.\n")

def route_command(raw:str):
    raw=raw.strip()
    if not raw.startswith("/"): return None
    parts=raw.split(None,1)
    cmd=parts[0].lower()
    arg=parts[1].strip() if len(parts)>1 else ""

    if   cmd=="/menu":    print(MENU)
    elif cmd=="/triage":
        file = arg.strip('"').strip("'") if arg else None
        return cmd_triage(file)
    elif cmd=="/interpret":
        if arg:
            files=[f.strip().strip('"').strip("'") for f in arg.replace(","," ").split() if f.strip()]
            return cmd_interpret(files)
        else: print('  Usage: /interpret PATH/TO/pipeline.csv [PATH/TO/options.csv]')
    elif cmd=="/morning":
        if arg: return cmd_morning(arg.strip('"').strip("'"))
        else: print('  Usage: /morning PATH/TO/top_trades.csv')
    elif cmd=="/ticker":
        import shlex as _shlex
        try:
            tokens = _shlex.split(arg)
        except ValueError:
            tokens = arg.split(None, 1)
        if len(tokens) == 0:
            print('  Usage: /ticker TICKER  (uses session CSV)  or  /ticker TICKER PATH/TO/file.csv')
        elif len(tokens) == 1:
            return cmd_ticker(tokens[0].upper())
        else:
            return cmd_ticker(tokens[0].upper(), tokens[1].strip('"').strip("'"))
    elif cmd=="/chart":
        tokens = arg.split()
        if len(tokens) >= 2:
            ticker = tokens[0].upper()
            image_paths = [t.strip('"').strip("'") for t in tokens[1:]]
            return cmd_chart(ticker, image_paths)
        else:
            print('  Usage: /chart MET daily_chart.png [intraday_chart.png ...]')
            print('  You can pass multiple images: daily + intraday + options chain')
    elif cmd=="/auto":    return cmd_auto()
    elif cmd=="/load":
        if arg: cmd_load(arg.strip('"').strip("'"))
        else: print('  Usage: /load PATH/TO/file.csv')
    elif cmd=="/options":
        if arg: cmd_options(arg.strip('"').strip("'"))
        else: print('  Usage: /options PATH/TO/options_data.csv')
    elif cmd=="/macro":
        if arg: cmd_macro(arg)
        else: print('  Usage: /macro PATH/TO/macro_intelligence_latest.json')
    elif cmd=="/news":
        tokens = arg.split(None,1)
        if tokens:
            ticker_filter = tokens[1].strip() if len(tokens)>1 else None
            cmd_news(tokens[0], ticker_filter)
        else: print('  Usage: /news PATH/TO/news_terminal.csv [TICKER]')
    elif cmd=="/sync":
        parts2 = arg.split(None,1)
        path = parts2[0].strip('"').strip("'") if parts2 else None
        hours = int(parts2[1]) if len(parts2)>1 else 24
        cmd_sync(path, hours)
    elif cmd=="/inputs":  cmd_inputs()
    elif cmd=="/status":  cmd_status()
    elif cmd=="/reset":   cmd_reset()
    elif cmd in("/exit","/quit"): return "EXIT"
    else: print(f"  Unknown command: {cmd}  (type /menu for help)")
    return None
