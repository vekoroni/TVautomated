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
from news_macro_readers import save_pasted_brief
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



def _build_battlefield_triage_response(rows: list, ma_summary: dict, source_name: str = "") -> str:
    """Build deterministic morning battlefield triage from prepared run outputs.

    Morning validator is the live gate. Other prepared outputs are consumed as
    context, but cannot override direction, permission, or repair/block status.
    """
    import csv as _csv
    import io as _io
    import json as _json

    try:
        sm = MA_INPUTS / "session_state.json"
        mode = "EOD"
        if sm.exists():
            mode = str(_json.loads(sm.read_text(encoding="utf-8")).get("session_mode", "eod")).upper()
    except Exception:
        mode = "EOD"
    if mode != "MORNING":
        return ""

    found = scan_ma_pipeline_outputs()
    morning_rows = rows if rows and "live_validation_state" in rows[0] else []
    if not morning_rows and found.get("morning_validated"):
        morning_rows = read_pipeline_csv(found["morning_validated"])
    if not morning_rows or "live_validation_state" not in morning_rows[0]:
        return ""

    def _load_keyed(key: str) -> dict:
        path = found.get(key)
        if not path:
            return {}
        try:
            data = read_pipeline_csv(path)
        except Exception:
            return {}
        out = {}
        for r in data:
            t = str(r.get("ticker", "") or r.get("underlying", "")).strip().upper()
            if t and t not in out:
                out[t] = r
        return out

    layers = {
        "morning_candidates": _load_keyed("morning_candidates"),
        "eil": _load_keyed("eil"),
        "execution": _load_keyed("execution"),
        "superbrain": _load_keyed("superbrain"),
        "garch": _load_keyed("garch_forecasts"),
    }

    chart_tickers = set()
    option_tickers = set()
    if isinstance((ma_summary or {}).get("chart_files"), dict):
        chart_tickers = {str(k).upper() for k in ma_summary["chart_files"].keys()}
    if isinstance((ma_summary or {}).get("options_files"), dict):
        option_tickers = {str(k).upper() for k in ma_summary["options_files"].keys()}

    def clean(v):
        return str(v if v is not None else "").strip()

    def upper(v):
        return clean(v).upper()

    def num(v):
        try:
            return float(v if v not in (None, "") else 0)
        except Exception:
            return 0.0

    def first(*vals):
        for v in vals:
            s = clean(v)
            if s:
                return s
        return ""

    def layer(ticker, key):
        return layers.get(key, {}).get(ticker, {})

    def direction(ticker, r):
        mc = layer(ticker, "morning_candidates")
        ex = layer(ticker, "execution")
        for val in (
            r.get("canonical_direction"),
            r.get("resolved_direction"),
            r.get("footprint_direction"),
            r.get("direction"),
            r.get("evening_direction"),
            r.get("primary_direction"),
            mc.get("canonical_direction"),
            mc.get("resolved_direction"),
            mc.get("footprint_direction"),
            mc.get("direction"),
            mc.get("primary_direction"),
            ex.get("canonical_direction"),
            ex.get("resolved_direction"),
            ex.get("footprint_direction"),
            ex.get("direction"),
            r.get("selected_contract_side"),
            mc.get("selected_contract_side"),
            ex.get("intent"),
        ):
            u = upper(val)
            if u in {"CALL", "PUT", "LONG_CALL", "LONG_PUT"}:
                return u.replace("LONG_", "")
            if u == "BUY_SETUP":
                return "CALL"
            if u == "SELL_SETUP":
                return "PUT"
        return "UNKNOWN"

    actionable = {"PROBE", "ARMED", "GO", "GO_LIMIT", "EXECUTE", "EXECUTE_WITH_CAUTION"}

    def classify(r):
        state = upper(r.get("live_validation_state"))
        perm = upper(r.get("morning_execution_permission"))
        contract = upper(r.get("contract_tradability_state"))
        if state in {"REJECTED", "BLOCKED"} or perm == "BLOCKED":
            return "SKIP_TODAY", "Morning validator rejected or blocked thesis", 4
        if perm == "CONTRACT_REPAIR" or contract == "REPAIR_REQUIRED":
            return "REVIEW_LATER", "Contract repair required before any entry", 2
        if state == "CONFIRMED" and perm in actionable:
            return "DEEP_DIVE_NOW", "Morning validator confirmed thesis and granted action review", 0
        if state == "WAIT_RETEST" or perm == "WAIT":
            return "REVIEW_LATER", "Waiting for live confirmation; not execution-ready", 2
        return "WATCH_ONLY", "No live execution permission from morning validator", 3

    def score(ticker, r):
        mc = layer(ticker, "morning_candidates")
        return num(first(r.get("validation_score"), r.get("pse_score"), mc.get("pse_score"), mc.get("composite_score"), 0))

    def reason_context(ticker, r):
        mc = layer(ticker, "morning_candidates")
        eil = layer(ticker, "eil")
        exe = layer(ticker, "execution")
        sb = layer(ticker, "superbrain")
        garch = layer(ticker, "garch")
        parts = [
            f"state={first(r.get('live_validation_state'), 'NA')}",
            f"perm={first(r.get('morning_execution_permission'), 'NA')}",
            f"score={first(r.get('validation_score'), r.get('pse_score'), mc.get('pse_score'), '0')}",
            f"contract={first(r.get('contract_tradability_state'), 'NA')}",
        ]
        iv = first(r.get("morning_iv_rank_state"), r.get("iv_gex_entry_quality_label"), mc.get("iv_gex_entry_quality_label"))
        if iv:
            parts.append(f"IV={iv}")
        eil_v = first(eil.get("eil_v3_verdict"), eil.get("eil_label"), eil.get("final_verdict"), exe.get("eil_v3_verdict"), exe.get("final_verdict"))
        if eil_v:
            parts.append(f"EIL={eil_v}")
        sb_v = first(sb.get("superbrain_verdict"), sb.get("final_verdict"), sb.get("verdict"))
        if sb_v:
            parts.append(f"SB={sb_v}")
        l3 = first(garch.get("l3_iv_tailwind_score"), r.get("l3_iv_tailwind_score"), mc.get("l3_iv_tailwind_score"))
        if l3:
            parts.append(f"L3_IV_tailwind={l3}")
        if ticker in chart_tickers:
            parts.append("charts_ready")
        if ticker in option_tickers:
            parts.append("options_ready")
        wr = first(r.get("rejection_reason"), r.get("wait_reason"))
        if wr:
            parts.append(wr[:140])
        return "; ".join(parts)

    keyed = []
    seen = set()
    for r in morning_rows:
        t = upper(r.get("ticker"))
        if t and t not in seen:
            keyed.append((t, r))
            seen.add(t)

    keyed.sort(key=lambda item: (classify(item[1])[2], -score(item[0], item[1]), item[0]))

    fields = [
        "rank", "ticker", "direction", "pipeline_score", "dte", "horizon",
        "live_validation_state", "validation_score", "earnings_flag",
        "ma_inputs_ready", "triage_verdict", "triage_reason",
    ]
    buf = _io.StringIO()
    writer = _csv.DictWriter(buf, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    groups = {"DEEP_DIVE_NOW": [], "DEEP_DIVE_NEXT": [], "REVIEW_LATER": [], "WATCH_ONLY": [], "SKIP_TODAY": []}

    for rank, (ticker, r) in enumerate(keyed, 1):
        verdict, base_reason, _ = classify(r)
        groups.setdefault(verdict, []).append(ticker)
        mc = layer(ticker, "morning_candidates")
        ma_ready = "YES" if ticker in chart_tickers and ticker in option_tickers else ("PARTIAL" if ticker in chart_tickers or ticker in option_tickers else "NO")
        writer.writerow({
            "rank": rank,
            "ticker": ticker,
            "direction": direction(ticker, r),
            "pipeline_score": first(r.get("validation_score"), r.get("pse_score"), mc.get("pse_score")),
            "dte": first(r.get("dte"), mc.get("dte"), "UNKNOWN"),
            "horizon": first(r.get("horizon_bucket"), mc.get("horizon_bucket"), r.get("horizon"), "UNKNOWN"),
            "live_validation_state": first(r.get("live_validation_state"), "UNKNOWN"),
            "validation_score": first(r.get("validation_score"), ""),
            "earnings_flag": first(r.get("earnings_flag"), r.get("earnings_in_window"), mc.get("earnings_flag")),
            "ma_inputs_ready": ma_ready,
            "triage_verdict": verdict,
            "triage_reason": f"{base_reason}; {reason_context(ticker, r)}",
        })

    def fmt(xs):
        return ", ".join(xs) if xs else "None"

    consumed = ", ".join([k for k, v in found.items() if v])
    summary = f"""**DEEP_DIVE_NOW:** {fmt(groups.get('DEEP_DIVE_NOW', []))}
**DEEP_DIVE_NEXT:** {fmt(groups.get('DEEP_DIVE_NEXT', []))}
**REVIEW_LATER:** {fmt(groups.get('REVIEW_LATER', []))}
**WATCH_ONLY:** {fmt(groups.get('WATCH_ONLY', []))}
**SKIP_TODAY:** {fmt(groups.get('SKIP_TODAY', []))}
---
### Session Picture
Battlefield triage consumed the prepared run outputs by ticker: {consumed}.

This is the continuation layer: it ranks the battlefield using whole-run context, while the morning validator remains the live gate for direction, permission, and execution readiness. Chart and options files improve review completeness only; they cannot promote a repair, wait, blocked, or rejected ticker.

Confirmed/action-review names: {len(groups.get('DEEP_DIVE_NOW', []))}. Repair/wait names stay in review. Rejected or blocked names are skipped today."""

    order_lines = [
        f"/ticker {ticker} ??? confirmed by morning validator; use full battlefield context for final human review."
        for ticker in groups.get("DEEP_DIVE_NOW", [])[:10]
    ]
    if not order_lines:
        order_lines = ["No validator-confirmed execution-review candidates. Stand down and monitor repair/wait queue."]
    order = "\n".join(order_lines) + "\n\nEXECUTION PERMISSION: NONE_PIPELINE_INTERPRETER_ONLY"

    return f"""[TRIAGE_RANKED_TABLE]
{buf.getvalue().strip()}
[/TRIAGE_RANKED_TABLE]

[TRIAGE_SUMMARY]
{summary}
[/TRIAGE_SUMMARY]

[TRIAGE_EXECUTION_ORDER]
{order}
[/TRIAGE_EXECUTION_ORDER]
"""


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
        import json as _json
        _active_run_id=None; _session_mode="EOD"
        _sm=MA_INPUTS/"session_state.json"
        if _sm.exists():
            try:
                _d=_json.loads(_sm.read_text(encoding="utf-8"))
                _active_run_id=_d.get("run_id","").strip()
                _session_mode=_d.get("session_mode","eod").upper()
            except Exception: pass
        found=scan_ma_pipeline_outputs()
        best=None
        if _active_run_id and found:
            if _session_mode=="MORNING":
                _mv=found.get("morning_validated")
                if _mv and _active_run_id in str(_mv):
                    best=_mv; print(f"  [MODE: MORNING] morning_validated_trades run {_active_run_id}")
                if not best:
                    _mc=found.get("morning_candidates")
                    if _mc and _active_run_id in str(_mc):
                        best=_mc; print(f"  [MODE: MORNING] falling back to morning_candidates run {_active_run_id}")
            else:
                _mc=found.get("morning_candidates")
                if _mc and _active_run_id in str(_mc):
                    best=_mc; print(f"  [MODE: EOD] morning_candidates run {_active_run_id}")
                if not best:
                    _mv=found.get("morning_validated")
                    if _mv and _active_run_id in str(_mv):
                        best=_mv; print(f"  [MODE: EOD] falling back to morning_validated run {_active_run_id}")
        if not best and _active_run_id and found:
            for _k,_p in found.items():
                if _active_run_id in str(_p):
                    best=_p; print(f"  [FALLBACK] {Path(_p).name}"); break
        if not best and found:
            if _session_mode == "MORNING":
                best = (found.get("morning_validated") or found.get("morning_candidates")
                        or found.get("execution") or found.get("eil") or list(found.values())[0])
            else:
                best = (found.get("morning_candidates") or found.get("morning_validated")
                        or found.get("execution") or found.get("eil") or list(found.values())[0])
            print(f"  [FALLBACK] No run_id match")
        if best:
            rows=read_pipeline_csv(best)
            source_name=Path(best).name
            print(f"  ✅ Auto-loaded: {source_name}")

    # Fix A -- lock source CSV into SESSION for /ticker auto-load
    from datetime import datetime as _dt
    if file_path:
        SESSION["last_pipeline_csv"] = str(file_path)
    elif best:
        SESSION["last_pipeline_csv"] = str(best)
    elif found:
        SESSION["last_pipeline_csv"] = str(list(found.values())[0])
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
    response = _build_battlefield_triage_response(rows, ma_summary, source_name)
    if response:
        print("  [BATTLEFIELD] Deterministic run-level triage built from prepared outputs")
    else:
        prompt = build_triage_prompt(rows, ma_summary)
        response = call_api(prompt)  # pure pipeline analysis

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
    if not file_path:
        file_path = SESSION.get("last_pipeline_csv")
        if not file_path:
            print("  [ERROR] No CSV loaded. Run /triage first or: /ticker TICKER FILE")
            return
        print(f"  [AUTO] {Path(file_path).name}")
    rows = read_pipeline_csv(file_path)
    row  = next((r for r in rows if r.get("ticker","").upper()==ticker.upper()), None)
    if not row:
        row = next((r for r in rows if ticker.upper() in str(r.get("underlying","")).upper()), None)
    if not row:
        print(f"  ⚠ Ticker {ticker} not found in {Path(file_path).name}")
        if rows: print(f"  Available: {[r.get('ticker','?') for r in rows[:10]]}")
        return
    _NON_LIVE = {"NONE_NEWS_TERMINAL_ONLY","WATCHLIST_ONLY","PIPELINE_BLOCKED"}
    _perm = row.get("execution_permission","UNKNOWN")
    if _perm in _NON_LIVE:
        print(f"  [NOTE] execution_permission={_perm} -- analysis proceeds")
    ma_files = scan_ma_inputs_for_ticker(ticker)
    ticker_options = dict(_loaded_options)
    for opt_path in ma_files["options"]:
        opt_name = Path(opt_path).stem
        if opt_name not in ticker_options:
            ticker_options[opt_name] = read_options_file(opt_path)
            print(f"  ✅ Auto-loaded: {Path(opt_path).name}")
    ticker_charts = ma_files["charts"] + ma_files["screenshots"]
    if ticker_charts:
        print(f"  ✅ Found {len(ticker_charts)} chart(s) in MA_Inputs for {ticker}")
    # Load trader note
    import json as _json
    _notes_path  = MA_INPUTS / "news_terminal" / "trader_notes.json"
    _ticker_note = ""
    if _notes_path.exists():
        try:
            _notes = _json.loads(_notes_path.read_text(encoding="utf-8"))
            _note_entry = _notes.get(ticker.upper(), {})
            _ticker_note = _note_entry.get("note","") if isinstance(_note_entry,dict) else str(_note_entry)
        except Exception:
            pass
    if _ticker_note:
        _preview = _ticker_note[:60] + ("..." if len(_ticker_note)>60 else "")
        print(f"  ✅ Trader note loaded for {ticker}: '{_preview}'")
    _use_web_search = True
    t0 = time.time()
    if ticker_charts:
        prompt   = build_chart_prompt(ticker=ticker, chart_descriptions=[],
                                       pipeline_row=row,
                                       options_data=ticker_options if ticker_options else None,
                                       ticker_note=_ticker_note)
        response = call_api(prompt, images=ticker_charts, use_web_search=_use_web_search)
    else:
        prompt   = build_single_ticker_prompt(ticker, row,
                                               ticker_options if ticker_options else None,
                                               ticker_note=_ticker_note)
        response = call_api(prompt, use_web_search=_use_web_search)
    run_dir, ts = get_run_dir()
    results = write_all_outputs(response, session, run_dir, ts,
                                 tickers=[ticker], prefix=f"ticker_{ticker.lower()}")
    print(f"\n  Deep dive complete ({int(time.time()-t0)}s)")
    _print_results(results, response)
    return response



def cmd_reset():
    """Clear in-memory interpreter state without changing the prepared run marker."""
    global _loaded_pipeline, _loaded_options
    _loaded_pipeline.clear()
    _loaded_options.clear()
    session.reset()
    for key in ("pipeline_csv", "last_pipeline_csv", "last_triage_run"):
        SESSION[key] = None
    print("  Session cleared. Prepared MA_Inputs files are unchanged.")


def cmd_brief(text:str=""):
    """Paste newsroom brief. /brief then paste, type END to finish."""
    if text.strip():
        print(f"  ⚠  Only captured one line. Type /brief alone, paste, then END")
        lines=[text.strip()]
    else:
        lines=[]
    print("  Paste the full newsroom brief below.")
    print("  Type END on a new line when finished.\n")
    consecutive_blanks=0
    try:
        while True:
            line=input()
            if line.strip().upper()=="END": break
            if line.strip()=="":
                consecutive_blanks+=1
                if consecutive_blanks>=2: break
                lines.append(line)
            else:
                consecutive_blanks=0
                lines.append(line)
    except (EOFError,KeyboardInterrupt): pass
    brief_text="\n".join(lines).strip()
    if not brief_text:
        print("  ⚠  No text received."); return
    saved_path=save_pasted_brief(brief_text)
    lines_count=brief_text.count("\n")+1
    print(f"\n  ✅ Brief saved ({lines_count} lines)")
    print(f"  Newsroom context included in /triage and /ticker automatically.")
    print(f"  Run /triage now.")


def cmd_note(args:str=""):
    """Add trader narrative note. /note TICKER [observation]"""
    import json as _json
    args=args.strip()
    if args.lower().startswith('/note '): args=args[6:].strip()
    if not args:
        print("  Usage: /note TICKER [observation]"); return
    parts=args.split(None,1)
    ticker=parts[0].upper().strip()
    remainder=parts[1].strip() if len(parts)>1 else ""
    if not remainder:
        print(f"  Trader note for {ticker}.")
        print(f"  Type your observation. Type END on a new line when finished.\n")
        lines=[]; consecutive_blanks=0
        try:
            while True:
                line=input()
                if line.strip().upper()=="END": break
                if line.strip()=="":
                    consecutive_blanks+=1
                    if consecutive_blanks>=2: break
                    lines.append(line)
                else:
                    consecutive_blanks=0; lines.append(line)
        except (EOFError,KeyboardInterrupt): pass
        note_text="\n".join(lines).strip()
    else:
        note_text=remainder
    if not note_text:
        print(f"  ⚠  No note entered for {ticker}."); return
    notes_path=MA_INPUTS/"news_terminal"/"trader_notes.json"
    notes_path.parent.mkdir(parents=True,exist_ok=True)
    notes={}
    if notes_path.exists():
        try: notes=_json.loads(notes_path.read_text(encoding="utf-8"))
        except Exception: notes={}
    from datetime import datetime as _dt
    notes[ticker]={"note":note_text,"timestamp":_dt.now().isoformat()}
    notes_path.write_text(_json.dumps(notes,indent=2),encoding="utf-8")
    SESSION[f"note_{ticker}"]=note_text
    _preview=note_text[:80]+("..." if len(note_text)>80 else "")
    print(f"\n  ✅ Note saved for {ticker}: '{_preview}'")
    print(f"  Will be injected into /ticker {ticker} automatically.")


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
║  /brief                        Paste newsroom brief into session         ║
║  /note TICKER [obs]             Add trader narrative for deep dive          ║
â•‘  /sync                        Sync AVSHUNTER outputs to MA_Inputs     â•‘
â•‘  /macro FILE                  Load macro intelligence JSON/file       â•‘
â•‘  /news FILE [TICKER]          Load News Terminal CSV/output           â•‘
â•‘  /inputs                      Show MA_Inputs folder status          â•‘
â•‘  /status                      Show session summary               â•‘
â•‘  /reset                       Clear session                      â•‘
â•‘  /menu                        Show this menu                     â•‘
â•‘  /exit                        Close interpreter                  â•‘
â•šâ•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•"""


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
    elif cmd=="/brief":
        cmd_brief(arg.strip() if arg else "")
    elif cmd=="/note":
        cmd_note(arg.strip() if arg else "")
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
