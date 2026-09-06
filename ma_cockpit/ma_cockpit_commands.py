"""
AVSHUNTER M&A Cockpit v1.0 â€” Command Router
"""
import time
from ma_cockpit_engine import (
    call_api, session, get_run_dir, extract_section, parse_csv,
    build_full_scan_prompt, build_deal_prompt, build_activist_prompt,
    build_arb_prompt, build_sector_prompt, build_corporate_event_prompt,
    build_triage_prompt
)
from ma_cockpit_outputs import write_all_outputs, _extract_section, _write_csv, TICKER_CSV_FIELDS

MENU = """
â•”â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•—
â•‘        AVSHUNTER M&A COCKPIT v1.0 â€” COMMAND MENU                â•‘
â• â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•£
â•‘  /scan              Full M&A and corporate event scan            â•‘
â•‘  /deal "text"       Analyse a specific deal or event             â•‘
â•‘  /triage "text"     Triage any corporate event headline          â•‘
â•‘  /activist          Activist campaign scan                       â•‘
â•‘  /arb               Merger arbitrage spread scan                 â•‘
â•‘  /sector TEXT       Sector M&A consolidation scan                â•‘
â•‘  /events            Corporate event scan (non-M&A)               â•‘
â•‘  /validate FILE     Validate a CSV against the schema            â•‘
â•‘  /status            Show current session summary                 â•‘
â•‘  /reset             Clear session, keep rules active             â•‘
â•‘  /menu              Show this menu                               â•‘
â•‘  /exit              Close cockpit                                â•‘
â•šâ•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•"""

def _safe_name(v):
    from pathlib import Path
    if v is None: return None
    if isinstance(v,(str,Path)): return Path(v).name
    if isinstance(v,dict):
        p=v.get("path")
        return Path(p).name if p else None
    return str(v)

def _print_results(results:dict, response:str=""):
    from ma_cockpit_engine import extract_verdict
    print()
    for key,label in [("ticker_csv","ma_candidates"),("handoff_csv","ma_handoff")]:
        if key in results:
            n=_safe_name(results[key]); r=results[key].get("rows","?") if isinstance(results[key],dict) else "?"
            if n: print(f"  âœ… {n:<52} ({r} rows)")
    for key in ("full_html","trader_html"):
        if key in results:
            n=_safe_name(results[key])
            if n: print(f"  âœ… {n}")
    if "master" in results:
        n=results["master"].get("added",0)
        print(f"  âœ… ma_catalyst_master.csv                    (+{n} rows)")
    print()
    if response:
        verdict=extract_verdict(response)
        if verdict!="PENDING": print(f"  M&A VERDICT:  {verdict}")
    print(f"  EXECUTION PERMISSION: NONE_MA_COCKPIT_ONLY")

def _print_section(response:str, tags:list):
    for tag in tags:
        content=_extract_section(response,tag)
        if content:
            print(f"\n{'â”€'*62}")
            print(f"  {tag.replace('_',' ')}")
            print('â”€'*62)
            for line in content.split('\n')[:50]:
                print(f"  {line}")

def cmd_scan(focus:str=None):
    f=f" [{focus}]" if focus else ""
    print(f"\n  Running full M&A + corporate event scan{f}...")
    print("  Searching deals, filings, activist campaigns, corporate events...")
    t0=time.time()
    response=call_api(build_full_scan_prompt(focus), web_search=True)
    run_dir,ts=get_run_dir()
    results=write_all_outputs(response,session,run_dir,ts)
    print(f"\n  Scan complete ({int(time.time()-t0)}s)")
    _print_results(results,response)
    _print_section(response,["MA_EXECUTIVE_SUMMARY","MA_PIPELINE_CANDIDATES"])
    return response

def cmd_deal(deal:str):
    print(f"\n  Analysing deal/event: {deal[:60]}...")
    t0=time.time()
    response=call_api(build_deal_prompt(deal), web_search=True)
    run_dir,ts=get_run_dir()
    results=write_all_outputs(response,session,run_dir,ts,prefix="deal")
    print(f"\n  Deal analysis complete ({int(time.time()-t0)}s)")
    _print_results(results,response)
    _print_section(response,["MA_EXECUTIVE_SUMMARY","MA_BENEFICIARY_MAP","MA_OPTIONS_ROUTING"])
    return response

def cmd_triage(event:str):
    print(f"\n  Triaging event: {event[:60]}...")
    t0=time.time()
    response=call_api(build_triage_prompt(event), web_search=True)
    run_dir,ts=get_run_dir()
    results=write_all_outputs(response,session,run_dir,ts,prefix="triage")
    print(f"\n  Triage complete ({int(time.time()-t0)}s)")
    _print_results(results,response)
    _print_section(response,["MA_EXECUTIVE_SUMMARY","MA_BENEFICIARY_MAP"])
    return response

def cmd_activist():
    print("\n  Running activist campaign scan...")
    t0=time.time()
    response=call_api(build_activist_prompt(), web_search=True)
    run_dir,ts=get_run_dir()
    results=write_all_outputs(response,session,run_dir,ts,prefix="activist")
    print(f"\n  Activist scan complete ({int(time.time()-t0)}s)")
    _print_results(results,response)
    _print_section(response,["MA_EXECUTIVE_SUMMARY","MA_PIPELINE_CANDIDATES"])
    return response

def cmd_arb():
    print("\n  Running merger arbitrage scan...")
    t0=time.time()
    response=call_api(build_arb_prompt(), web_search=True)
    run_dir,ts=get_run_dir()
    results=write_all_outputs(response,session,run_dir,ts,prefix="arb")
    print(f"\n  Arb scan complete ({int(time.time()-t0)}s)")
    _print_results(results,response)
    _print_section(response,["MA_EXECUTIVE_SUMMARY","MA_PIPELINE_CANDIDATES"])
    return response

def cmd_sector(sector:str):
    print(f"\n  Running sector M&A scan: {sector.upper()}...")
    t0=time.time()
    response=call_api(build_sector_prompt(sector), web_search=True)
    run_dir,ts=get_run_dir()
    results=write_all_outputs(response,session,run_dir,ts,prefix=f"sector_{sector.lower()[:8]}")
    print(f"\n  Sector scan complete ({int(time.time()-t0)}s)")
    _print_results(results,response)
    _print_section(response,["MA_EXECUTIVE_SUMMARY","MA_BENEFICIARY_MAP"])
    return response

def cmd_events():
    print("\n  Running corporate event scan...")
    t0=time.time()
    response=call_api(build_corporate_event_prompt(), web_search=True)
    run_dir,ts=get_run_dir()
    results=write_all_outputs(response,session,run_dir,ts,prefix="events")
    print(f"\n  Corporate events scan complete ({int(time.time()-t0)}s)")
    _print_results(results,response)
    _print_section(response,["MA_EXECUTIVE_SUMMARY","MA_PIPELINE_CANDIDATES"])
    return response

def cmd_validate(filepath:str):
    from pathlib import Path
    import json
    try:
        from ma_csv_schema import validate_ma_manual_review_csv
        report=validate_ma_manual_review_csv(filepath)
        print(f"\n  Validation: {'âœ… VALID' if report.valid else 'âŒ INVALID'}")
        print(f"  Rows: {report.row_count}")
        if report.errors:
            print(f"  Errors ({len(report.errors)}):")
            for e in report.errors[:10]: print(f"    âœ— {e}")
        if report.warnings:
            print(f"  Warnings ({len(report.warnings)}):")
            for w in report.warnings[:5]: print(f"    âš  {w}")
    except Exception as e:
        print(f"  âš  Validation error: {e}")

def cmd_status():
    s=session.summary()
    print(f"""
  â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
  M&A COCKPIT SESSION STATUS
  â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
  Date:             {session.session_date}
  M&A Verdict:      {s["desk_verdict"]}
  Total Candidates: {s["total"]}
  P1 Priority:      {s["p1"]}
  P2 Priority:      {s["p2"]}
  GO Verdicts:      {s["go"]}
  â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€""")

def cmd_reset():
    session.reset()
    print("\n  âœ… Session cleared. v1.0 rules preserved. Ready.\n")

def route_command(raw:str):
    raw=raw.strip()
    if not raw.startswith("/"): return None
    parts=raw.split(None,1)
    cmd=parts[0].lower()
    arg=parts[1].strip('"').strip("'") if len(parts)>1 else ""

    if   cmd=="/menu":     print(MENU)
    elif cmd=="/scan":     return cmd_scan(arg if arg else None)
    elif cmd=="/deal":
        if arg: return cmd_deal(arg)
        else: print('  Usage: /deal "Company A acquires Company B"')
    elif cmd=="/triage":
        if arg: return cmd_triage(arg)
        else: print('  Usage: /triage "Elon Musk buys Twitter"')
    elif cmd=="/activist": return cmd_activist()
    elif cmd=="/arb":      return cmd_arb()
    elif cmd=="/sector":
        if arg: return cmd_sector(arg)
        else: print("  Usage: /sector TECHNOLOGY")
    elif cmd=="/events":   return cmd_events()
    elif cmd=="/validate":
        if arg: cmd_validate(arg)
        else: print("  Usage: /validate path/to/file.csv")
    elif cmd=="/status":   cmd_status()
    elif cmd=="/reset":    cmd_reset()
    elif cmd in("/exit","/quit"): return "EXIT"
    else: print(f"  Unknown command: {cmd}  (type /menu for help)")
    return None

