"""
AVSHUNTER News Terminal v1.3 â€” Command Router
Maps /commands to prompts, API calls and output writers
"""
from news_terminal_engine import (
    call_api, session, get_run_dir, extract_section,
    parse_csv_section, parse_json_section,
    build_brief_prompt, build_mna_prompt, build_sector_prompt,
    build_event_prompt, build_forward_prompt, build_watchlist_prompt,
    build_risk_prompt, build_sources_prompt, build_refine_prompt, build_map_prompt
)
from news_terminal_outputs import write_all_outputs, write_ticker_csv_only
from news_terminal_engine import session as _session

MENU = """
â•”â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•—
â•‘         AVSHUNTER NEWS TERMINAL v1.3 â€” COMMAND MENU             â•‘
â• â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•£
â•‘  /brief          Full global session intelligence brief          â•‘
â•‘  /event "text"   Analyse a specific news event                   â•‘
â•‘  /map            Beneficiaries, losers and companies             â•‘
â•‘  /forward        Forward-looking impact view with FIPS           â•‘
â•‘  /ticker-csv     Create curated ticker candidate CSV             â•‘
â•‘  /handoff-csv    Create full narrative/event handoff CSV         â•‘
â•‘  /watchlist      Watchlist-only candidates                       â•‘
â•‘  /mna            M&A, strategic reviews and activist signals     â•‘
â•‘  /sector TEXT    Sector narrative brief (e.g. /sector semis)     â•‘
â•‘  /risk           Stale, crowded, source, options, thesis risks   â•‘
â•‘  /sources        Confirmed / assumption / missing data           â•‘
â•‘  /refine         Reduce to highest-quality names only            â•‘
â•‘  /reset          Clear session, keep rules active                â•‘
â•‘  /status         Show current session summary                    â•‘
â•‘  /menu           Show this menu                                  â•‘
â•‘  /exit           Close terminal                                  â•‘
â•šâ•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•"""

def print_results(results: dict, raw_response: str = ""):
    """Print file write summary â€” handles any return structure."""
    from pathlib import Path
    print()
    def safe_name(v):
        if v is None: return None
        if isinstance(v, (str, Path)): return Path(v).name
        if isinstance(v, dict):
            p = v.get("path")
            return Path(p).name if p else None
        return str(v)
    def safe_rows(v):
        if isinstance(v, dict): return v.get("rows", "?")
        return "?"
    for key in ("ticker_csv",):
        if key in results:
            n = safe_name(results[key]); r = safe_rows(results[key])
            if n: print(f"  âœ… {n:<50} ({r} rows)")
    for key in ("handoff_csv",):
        if key in results:
            n = safe_name(results[key]); r = safe_rows(results[key])
            if n: print(f"  âœ… {n:<50} ({r} rows)")
    for key in ("macro_json",):
        if key in results:
            n = safe_name(results[key])
            if n: print(f"  âœ… {n}")
    for key in ("master_calendar", "master_new_rows"):
        if key in results:
            v = results[key]
            cnt = v.get("added", v) if isinstance(v, dict) else v
            print(f"  âœ… catalyst_calendar_master.csv  (+{cnt} rows)")
            break
    for key in ("full_html", "full_brief"):
        if key in results:
            n = safe_name(results[key])
            if n: print(f"  âœ… {n}")
            break
    for key in ("trader_html", "trader_brief"):
        if key in results:
            n = safe_name(results[key])
            if n: print(f"  âœ… {n}")
            break
    for key in ("summary_txt", "summary_text"):
        if key in results:
            n = safe_name(results[key])
            if n: print(f"  âœ… {n}")
            break
    print()
    from news_terminal_engine import extract_desk_verdict, extract_options_regime
    if raw_response:
        verdict = extract_desk_verdict(raw_response)
        regime = extract_options_regime(raw_response)
        if verdict != "PENDING": print(f"  DESK VERDICT:   {verdict}")
        if regime: print(f"  OPTIONS REGIME: {regime}")
        print()
    print(f"  EXECUTION PERMISSION: NONE_NEWS_TERMINAL_ONLY")

def print_text_response(response: str, sections: list):
    """Print relevant text sections to console."""
    from news_terminal_engine import extract_section
    for sec in sections:
        content = extract_section(response, sec)
        if content:
            print(f"\n{'â”€'*60}")
            print(f"  {sec.replace('_',' ')}")
            print('â”€'*60)
            for line in content.split('\n')[:40]:
                print(f"  {line}")

# â”€â”€ COMMAND HANDLERS â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
def cmd_brief():
    import time
    print("\n  Running global session brief...")
    print("  Searching live markets and news...")
    t0 = time.time()
    prompt = build_brief_prompt()
    response = call_api(prompt, include_web_search=True)
    run_dir, ts = get_run_dir()
    results = write_all_outputs(response, _session, run_dir, ts)
    elapsed = int(time.time() - t0)
    print(f"\n  Brief complete ({elapsed}s)")
    print_results(results, response)
    # Deploy integration outputs + run combiner
    deploy_news_terminal_outputs()
    _run_combiner()
    # Print summary to console
    exec_sum = extract_section(response, "EXECUTIVE_SUMMARY")
    if exec_sum:
        print(f"\n{'â”€'*60}")
        print("  EXECUTIVE SUMMARY")
        print('â”€'*60)
        for line in exec_sum.split('\n')[:8]:
            print(f"  {line}")
    return response

def cmd_mna():
    import time
    print("\n  Running M&A and strategic review scan...")
    print("  Searching SEC filings, M&A news, activist campaigns...")
    t0 = time.time()
    prompt = build_mna_prompt()
    response = call_api(prompt, include_web_search=True)
    run_dir, ts = get_run_dir()
    results = write_all_outputs(response, _session, run_dir, ts, prefix="mna")
    elapsed = int(time.time() - t0)
    print(f"\n  M&A scan complete ({elapsed}s)")
    print_results(results, response)
    print_text_response(response, ["MNA_EXECUTIVE_SUMMARY","MNA_DEALS_DETECTED"])
    return response

def cmd_sector(sector_name: str):
    import time
    print(f"\n  Running sector brief: {sector_name.upper()}...")
    t0 = time.time()
    prompt = build_sector_prompt(sector_name)
    response = call_api(prompt, include_web_search=True)
    run_dir, ts = get_run_dir()
    results = write_all_outputs(response, _session, run_dir, ts, prefix=f"sector_{sector_name.lower()[:8]}")
    elapsed = int(time.time() - t0)
    print(f"\n  Sector brief complete ({elapsed}s)")
    print_results(results, response)
    print_text_response(response, ["SECTOR_EXECUTIVE_SUMMARY","SECTOR_LEADERS_LOSERS"])
    return response

def cmd_event(event_description: str):
    import time
    print(f"\n  Analysing event: {event_description[:60]}...")
    t0 = time.time()
    prompt = build_event_prompt(event_description)
    response = call_api(prompt, include_web_search=True)
    run_dir, ts = get_run_dir()
    results = write_all_outputs(response, _session, run_dir, ts, prefix="event")
    elapsed = int(time.time() - t0)
    print(f"\n  Event analysis complete ({elapsed}s)")
    print_results(results, response)
    print_text_response(response, ["EVENT_SUMMARY","EVENT_TRANSMISSION","EVENT_BENEFICIARIES_LOSERS"])
    return response

def cmd_forward():
    import time
    print("\n  Building forward impact views with FIPS scoring...")
    t0 = time.time()
    prompt = build_forward_prompt()
    response = call_api(prompt, include_web_search=False)
    elapsed = int(time.time() - t0)
    print(f"\n  Forward view complete ({elapsed}s)")
    print_text_response(response, ["FORWARD_IMPACT_VIEW","FORWARD_FIPS_SCORES","FORWARD_CONFIRMATION_INVALIDATION"])
    return response

def cmd_map():
    import time
    print("\n  Mapping beneficiaries, losers and companies worth analysing...")
    t0 = time.time()
    prompt = build_map_prompt()
    response = call_api(prompt, include_web_search=False)
    elapsed = int(time.time() - t0)
    print(f"\n  Map complete ({elapsed}s)")
    print_text_response(response, ["MAP_BENEFICIARIES","MAP_LOSERS","MAP_COMPANIES_WORTH_ANALYSING"])
    return response

def cmd_watchlist():
    import time
    print("\n  Building watchlist-only candidates...")
    t0 = time.time()
    prompt = build_watchlist_prompt()
    response = call_api(prompt, include_web_search=False)
    run_dir, ts = get_run_dir()
    ticker_rows = parse_csv_section(extract_section(response, "TICKER_CSV_DATA"))
    results = write_ticker_csv_only(ticker_rows, run_dir, ts, prefix="watchlist")
    elapsed = int(time.time() - t0)
    print(f"\n  Watchlist complete ({elapsed}s)")
    print_results(results)
    print_text_response(response, ["WATCHLIST_CANDIDATES"])
    return response

def cmd_risk():
    import time
    print("\n  Analysing risk flags...")
    t0 = time.time()
    prompt = build_risk_prompt()
    response = call_api(prompt, include_web_search=False)
    elapsed = int(time.time() - t0)
    print(f"\n  Risk analysis complete ({elapsed}s)")
    print_text_response(response, ["RISK_STALE","RISK_CROWDED","RISK_SOURCE","RISK_OPTIONS","RISK_THESIS"])
    return response

def cmd_sources():
    import time
    print("\n  Retrieving confirmed data, assumptions and missing data...")
    t0 = time.time()
    prompt = build_sources_prompt()
    response = call_api(prompt, include_web_search=False)
    elapsed = int(time.time() - t0)
    print(f"\n  Sources complete ({elapsed}s)")
    print_text_response(response, ["SOURCES_CONFIRMED","SOURCES_ASSUMPTIONS","SOURCES_MISSING"])
    return response

def cmd_refine():
    import time
    print("\n  Refining to highest-quality candidates only...")
    t0 = time.time()
    prompt = build_refine_prompt()
    response = call_api(prompt, include_web_search=False)
    run_dir, ts = get_run_dir()
    ticker_rows = parse_csv_section(extract_section(response, "TICKER_CSV_DATA"))
    results = write_ticker_csv_only(ticker_rows, run_dir, ts, prefix="refined")
    elapsed = int(time.time() - t0)
    print(f"\n  Refine complete ({elapsed}s)")
    print_results(results)
    print_text_response(response, ["REFINED_CANDIDATES"])
    return response

def cmd_ticker_csv():
    import time
    print("\n  Creating curated ticker candidate CSV from current session...")
    if not session.candidates:
        print("  âš   No candidates in current session. Run /brief first.")
        return None
    t0 = time.time()
    run_dir, ts = get_run_dir()
    results = write_ticker_csv_only(session.candidates, run_dir, ts)
    elapsed = int(time.time() - t0)
    print(f"\n  Ticker CSV complete ({elapsed}s)")
    print_results(results)
    return None

def cmd_handoff_csv():
    import time
    print("\n  Creating full narrative/event handoff CSV from current session...")
    if not session.last_handoff_csv:
        print("  âš   No handoff data in current session. Run /brief or /event first.")
        return None
    t0 = time.time()
    from news_terminal_outputs import write_csv, HANDOFF_CSV_FIELDS
    run_dir, ts = get_run_dir()
    path = run_dir / f"handoff_{ts}.csv"
    n = write_csv(session.last_handoff_csv, path, HANDOFF_CSV_FIELDS)
    print(f"\n  âœ… {path.name} ({n} rows)")
    return None

def cmd_status():
    s = session.summary()
    print(f"""
  â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
  SESSION STATUS
  â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
  Date:           {session.session_date}
  Desk Verdict:   {s['desk_verdict']}
  Options Regime: {s['options_regime']}
  Narratives:     {s['narratives']}
  Candidates:     {s['total']} total  |  HIGH: {s['high']}  MED: {s['medium']}  LOW: {s['low']}
  Runs this session: {session.run_count}
  â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€""")

def deploy_news_terminal_outputs():
    """
    Copy news terminal macro outputs to all pipeline-readable locations.
    Called at the end of every news terminal run, after files are written.
    """
    import shutil
    from pathlib import Path as _Path
    from datetime import datetime as _dt

    BASE    = _Path(r"C:\Users\ACKVerissimo\AVSHUNTER-Intelligence")
    TODAY   = _dt.now().strftime("%Y%m%d")
    src_dir = BASE / "news_terminal" / "outputs"

    macro_targets = [
        BASE / "pipeline_interpreter" / "MA_Inputs" / "macro",
        BASE / "dropbox" / "macro",
    ]

    macro_files = [
        "macro_intelligence_latest.json",
        f"avshunter_macro_enrichment_delta_{TODAY}.json",
    ]

    for target in macro_targets:
        target.mkdir(parents=True, exist_ok=True)
        for fname in macro_files:
            src = src_dir / fname
            if src.exists():
                shutil.copy2(src, target / fname)
                print(f"  [DEPLOY] {fname} â†’ {target.name}")

    inputs_dir = BASE / "dropbox" / "inputs"
    inputs_dir.mkdir(parents=True, exist_ok=True)
    for fname in [f"premarket_candidates_{TODAY}.csv",
                  f"news_terminal_tickers_{TODAY}.txt"]:
        src = src_dir / fname
        if src.exists():
            shutil.copy2(src, inputs_dir / fname)
            print(f"  [DEPLOY] {fname} â†’ dropbox\\inputs")

    print("  [DEPLOY] Complete")


def _run_combiner():
    """Run build_premarket_candidates.py after outputs are written."""
    import subprocess, sys
    from pathlib import Path as _Path
    combiner = _Path(r"C:\Users\ACKVerissimo\AVSHUNTER-Intelligence\news_terminal\build_premarket_candidates.py")
    if combiner.exists():
        print("\n  Running combiner...")
        subprocess.run([sys.executable, str(combiner)], check=False)
    else:
        print(f"  âš  Combiner not found: {combiner}")


def cmd_reset():
    session.reset()
    print("\n  âœ… Session cleared. v1.3 rules and system prompt preserved.")
    print("  Ready for new analysis.\n")

def route_command(raw_input: str):
    """Parse and route a command string."""
    raw = raw_input.strip()
    if not raw.startswith("/"): return None

    parts = raw.split(None, 1)
    cmd = parts[0].lower()
    arg = parts[1].strip('"').strip("'") if len(parts) > 1 else ""

    if cmd == "/menu": print(MENU)
    elif cmd == "/brief": return cmd_brief()
    elif cmd == "/mna": return cmd_mna()
    elif cmd == "/sector":
        if arg: return cmd_sector(arg)
        else: print("  Usage: /sector SEMICONDUCTORS")
    elif cmd == "/event":
        if arg: return cmd_event(arg)
        else: print('  Usage: /event "Fed raises rates 25bps"')
    elif cmd == "/forward": return cmd_forward()
    elif cmd == "/map": return cmd_map()
    elif cmd == "/watchlist": return cmd_watchlist()
    elif cmd == "/risk": return cmd_risk()
    elif cmd == "/sources": return cmd_sources()
    elif cmd == "/refine": return cmd_refine()
    elif cmd == "/ticker-csv": return cmd_ticker_csv()
    elif cmd == "/handoff-csv": return cmd_handoff_csv()
    elif cmd == "/status": cmd_status()
    elif cmd == "/reset": cmd_reset()
    elif cmd in ("/exit", "/quit"): return "EXIT"
    else: print(f"  Unknown command: {cmd}  (type /menu for help)")
    return None

