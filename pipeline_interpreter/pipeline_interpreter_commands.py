
def cmd_inputs():
    from pathlib import Path
    base = Path(__file__).parent / "MA_Inputs"
    folders = ["pipeline_outputs","news_terminal","macro","charts","options_data"]
    print("\n  MA_Inputs status:")
    for f in folders:
        p = base / f
        files = [x for x in p.glob("*") if not x.name.startswith(".")] if p.exists() else []
        status = f"  {len(files)} file(s)" if files else "  EMPTY"
        print(f"  {f:<25} {status}")
        if files:
            newest = max(files, key=lambda x: x.stat().st_mtime)
            print(f"  {'':25} latest: {newest.name}")
    print()
"""
AVSHUNTER Pipeline Interpreter v1.0 Ã¢â‚¬â€ Command Router
"""
import time
from pathlib import Path
from pipeline_interpreter_engine import (
    call_api, session, SESSION, get_run_dir, parse_brief_csv,
    read_pipeline_csv, read_options_file, find_pipeline_files,
    build_interpret_prompt, build_single_ticker_prompt,
    build_morning_validation_prompt, build_chart_prompt,
    build_intraday_prompt, format_live_price_block,
    scan_ma_inputs_for_ticker, scan_ma_pipeline_outputs,
    scan_all_ma_inputs, get_ma_inputs_status, build_triage_prompt,
    MA_INPUTS, MA_CHARTS, MA_OPTIONS, MA_SCREENSHOTS, MA_PIPELINE, MA_MACRO, MA_NEWS, MA_LAB,
    EXECUTION_PERMISSION, MODEL_TRIAGE, MODEL_DEEP_DIVE, LIVE_PRICES, LIVE_DATA,
    fetch_all_live_data, format_live_data_for_prompt,
    fetch_live_contract_spread, fetch_peer_quotes,
    _LIVE_MARKET_AVAILABLE,
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
Ã¢â€¢â€Ã¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢â€”
Ã¢â€¢â€˜     AVSHUNTER PIPELINE INTERPRETER v1.0 Ã¢â‚¬â€ COMMAND MENU          Ã¢â€¢â€˜
Ã¢â€¢Â Ã¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢Â£
Ã¢â€¢â€˜  /triage [FILE]               Fast priority scan Ã¢â‚¬â€ rank all candidates  Ã¢â€¢â€˜
Ã¢â€¢â€˜  /interpret FILE [FILE2...]   Interpret pipeline CSV file(s)     Ã¢â€¢â€˜
Ã¢â€¢â€˜  /morning FILE                Morning validation pass            Ã¢â€¢â€˜
Ã¢â€¢â€˜  /ticker TICKER FILE          Deep dive single ticker            Ã¢â€¢â€˜
Ã¢â€¢â€˜  /intraday TICKER [IMG...]    15m/30m chart + live price analysis Ã¢â€¢â€˜
Ã¢â€¢â€˜  /live TICKER [contract]     Fetch live options vol/flow/spread  Ã¢â€¢â€˜
Ã¢â€¢â€˜  /price TICKER PRICE [chg%]  Register live price for analysis   Ã¢â€¢â€˜
Ã¢â€¢â€˜  /chart TICKER IMG [IMG2...]  Chart image analysis (vision)      Ã¢â€¢â€˜
Ã¢â€¢â€˜  /auto                        Auto-detect pipeline files         Ã¢â€¢â€˜
Ã¢â€¢â€˜  /load FILE                   Load a pipeline CSV into session   Ã¢â€¢â€˜
Ã¢â€¢â€˜  /options FILE                Add options data file              Ã¢â€¢â€˜
Ã¢â€¢â€˜  /sync                        Sync AVSHUNTER outputs to MA_Inputs     Ã¢â€¢â€˜
Ã¢â€¢â€˜  /macro FILE                  Load macro intelligence JSON/file       Ã¢â€¢â€˜
Ã¢â€¢â€˜  /news FILE [TICKER]          Load News Terminal CSV/output           Ã¢â€¢â€˜
Ã¢â€¢â€˜  /inputs                      Show MA_Inputs folder status          Ã¢â€¢â€˜
Ã¢â€¢â€˜  /status                      Show session summary               Ã¢â€¢â€˜
Ã¢â€¢â€˜  /reset                       Clear session                      Ã¢â€¢â€˜
Ã¢â€¢â€˜  /menu                        Show this menu                     Ã¢â€¢â€˜
Ã¢â€¢â€˜  /exit                        Close interpreter                  Ã¢â€¢â€˜
Ã¢â€¢Å¡Ã¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢Â"""

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
        if n: print(f"  Ã¢Å“â€¦ {n:<52} ({r} rows)")
    if "html" in results:
        n=_safe_name(results["html"])
        if n: print(f"  Ã¢Å“â€¦ {n}")
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
    Fast triage pass Ã¢â‚¬â€ rank and prioritise the whole candidate list.
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
                if not best:
                    _lv=found.get("lab_triage_view")
                    if _lv and _active_run_id in str(_lv):
                        best=_lv; print(f"  [MODE: MORNING] falling back to lab_triage_view run {_active_run_id}")
            else:
                _lv=found.get("lab_triage_view")
                if _lv and _active_run_id in str(_lv):
                    best=_lv; print(f"  [MODE: EOD] lab_triage_view run {_active_run_id}")
                if not best:
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
                        or found.get("lab_triage_view") or found.get("execution") or found.get("eil") or list(found.values())[0])
            else:
                best = (found.get("lab_triage_view") or found.get("morning_candidates") or found.get("morning_validated")
                        or found.get("execution") or found.get("eil") or list(found.values())[0])
            print(f"  [FALLBACK] No run_id match")
        if best:
            rows=read_pipeline_csv(best)
            source_name=Path(best).name
            print(f"  âœ… Auto-loaded: {source_name}")

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
            print(f"  âš   B2 GUARD: {_blocked_in_triage} BLOCKED tickers excluded from triage ranking")
            rows = [r for r in rows if str(r.get("eil_v3_verdict", "")).upper() != "BLOCKED"]

    # Get MA_Inputs availability for completeness scoring
    chart_tickers = set(ma_summary.get("chart_files", {}).keys())
    opt_tickers   = set(ma_summary.get("options_files", {}).keys())
    if chart_tickers or opt_tickers:
        print(f"  MA_Inputs data: charts for {sorted(chart_tickers)}, options for {sorted(opt_tickers)}")

    # â”€â”€ Component 9: Lab reconciliation pre-triage gate â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    from lab_reconciliation import (
        load_lab_export, reconcile_universes, check_run_id_alignment,
        build_lab_alignment_block,
    )
    lab_rows, lab_filename = load_lab_export(MA_LAB)
    run_id_check = None
    if lab_rows:
        pipeline_run_id = ""
        if rows:
            pipeline_run_id = str(rows[0].get("run_id", rows[0].get("Run_ID", ""))).strip()
        run_id_check = check_run_id_alignment(lab_rows, pipeline_run_id)
        if not run_id_check["match"]:
            print(f"  [LAB] STALE_LAB_DATA: Lab Run_ID {run_id_check['lab_run_id']} "
                  f"does not match pipeline Run_ID {run_id_check['pipeline_run_id']}")
            print(f"  [LAB] Lab export may be from a different session â€” reconciliation will proceed with warning.")
        interpreter_tickers = [str(r.get("ticker", "")).upper() for r in rows]
        reconciliation = reconcile_universes(lab_rows, interpreter_tickers)
        lab_block = build_lab_alignment_block(reconciliation, lab_filename, run_id_check)
        SESSION["lab_rows"]           = lab_rows
        SESSION["lab_reconciliation"] = reconciliation
        SESSION["lab_filename"]       = lab_filename
        SESSION["lab_run_id_check"]   = run_id_check
        print(f"  [LAB] Lab export: {lab_filename}")
        if "LAB_TRIAGE_VIEW_FALLBACK" in lab_filename:
            print(f"  [LAB] ⚠  WARNING: avshunter_signals_*.csv not found in pipeline_outputs/")
            print(f"  [LAB] ⚠  Falling back to lab_triage_view — CONFIRMED count is UNRELIABLE (same file as pipeline source)")
            print(f"  [LAB] ⚠  Place avshunter_signals_*.csv in pipeline_outputs/ to fix reconciliation")
        print(f"  [LAB] Confirmed: {reconciliation['confirmed_count']} | "
              f"Lab only: {reconciliation['lab_only_count']} | "
              f"Interpreter only: {reconciliation['interp_only_count']} <- review required")
        if reconciliation["interp_only"]:
            print(f"  [LAB] LAB_NOT_CONFIRMED tickers: {', '.join(reconciliation['interp_only'])}")
    else:
        lab_block = "LAB_ALIGNMENT: No lab export found in MA_Inputs/lab_export/"
        SESSION["lab_rows"]           = []
        SESSION["lab_reconciliation"] = {}
        SESSION["lab_filename"]       = ""
        print("  [LAB] No lab export â€” place avshunter_signals_*.csv in MA_Inputs/lab_export/")
    # â”€â”€ End lab reconciliation gate â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    # -- Entry timing engine - pre-trade probability layer
    from entry_timing_engine import load_garch_rows, build_pre_trade_probability_block
    from lab_reconciliation import get_lab_row as _get_lab_row_ete
    _garch_rows = load_garch_rows(MA_PIPELINE)
    _ete_blocks = []
    for _r in rows[:20]:
        _t = str(_r.get("ticker", "")).upper()
        if _t:
            _g = _garch_rows.get(_t, {})
            _lab_r = _get_lab_row_ete(SESSION.get("lab_rows", []), _t)
            _ete_blocks.append(build_pre_trade_probability_block(_t, _r, _g, _lab_r or {}, 0))
    _ete_summary = "\n".join(_ete_blocks)
    # -- End entry timing engine

    t0 = time.time()
    response = _build_battlefield_triage_response(rows, ma_summary, source_name)
    if response:
        print("  [BATTLEFIELD] Deterministic run-level triage built from prepared outputs")
    else:
        prompt = build_triage_prompt(rows, ma_summary, lab_alignment_block=lab_block, pre_trade_prob_block=_ete_summary)
        response = call_api(prompt, model=MODEL_TRIAGE)  # Sonnet 4.6 â€” fast triage

    run_dir, ts = get_run_dir()
    results = write_triage_outputs(
        response, run_dir, ts,
        lab_reconciliation = SESSION.get("lab_reconciliation"),
        lab_filename       = SESSION.get("lab_filename", ""),
        run_id_check       = SESSION.get("lab_run_id_check"),
        lab_rows           = SESSION.get("lab_rows", []) or None,
    )

    elapsed = int(time.time() - t0)
    print(f"\n  Triage complete ({elapsed}s)")
    print()

    # Print results
    tc = results.get("triage_csv", {})
    th = results.get("triage_html", {})
    n = tc.get("rows", 0) if isinstance(tc, dict) else "?"
    tc_name = _safe_name(tc)
    th_name = _safe_name(th)
    if tc_name: print(f"  Ã¢Å“â€¦ {tc_name:<52} ({n} ranked)")
    if th_name: print(f"  Ã¢Å“â€¦ {th_name}")
    print()

    # Print execution order to console
    from pipeline_interpreter_outputs import _extract_section as _es
    order = _es(response, "TRIAGE_EXECUTION_ORDER")
    summary = _es(response, "TRIAGE_SUMMARY")

    if summary:
        print(f"{'Ã¢â€â‚¬'*60}")
        print("  SESSION PICTURE")
        print('Ã¢â€â‚¬'*60)
        for line in summary.split('\n')[:15]:
            if line.strip(): print(f"  {line}")

    if order:
        print(f"\n{'Ã¢â€â‚¬'*60}")
        print("  TODAY'S EXECUTION ORDER")
        print('Ã¢â€â‚¬'*60)
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
        print("  Ã¢Å¡Â  No pipeline data loaded."); return

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
        print(f"  Ã¢Å“â€¦ Auto-loaded {ma_options_loaded} options file(s) from MA_Inputs")

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
    if not rows: print("  Ã¢Å¡Â  No data loaded."); return
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
            print(f"  Ã¢Å“â€¦ Macro context loaded")
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
        print(f"  âš  Ticker {ticker} not found in {Path(file_path).name}")
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
            print(f"  âœ… Auto-loaded: {Path(opt_path).name}")
    ticker_charts = ma_files["charts"] + ma_files["screenshots"]
    if ticker_charts:
        print(f"  âœ… Found {len(ticker_charts)} chart(s) in MA_Inputs for {ticker}")
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
        print(f"  âœ… Trader note loaded for {ticker}: '{_preview}'")
    # â”€â”€ Component 9: Lab context injection â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    from lab_reconciliation import (
        get_lab_row, validate_lab_field_alignment,
        build_lab_context_block, build_field_conflict_block,
    )
    _lab_rows = SESSION.get("lab_rows", [])
    lab_context_block  = ""
    lab_conflict_block = ""
    if not _lab_rows:
        print(f"  [LAB] {ticker}: LAB_NOT_LOADED â€” run /triage or /lab to load export")
    else:
        _lab_row       = get_lab_row(_lab_rows, ticker)
        _reconciliation = SESSION.get("lab_reconciliation", {})
        _is_confirmed  = ticker.upper() in [t.upper() for t in _reconciliation.get("confirmed", [])]
        lab_context_block  = build_lab_context_block(_lab_row, ticker)
        _conflicts         = validate_lab_field_alignment(_lab_row or {}, row, ticker) if _lab_row else []
        lab_conflict_block = build_field_conflict_block(_conflicts, ticker)
        if not _is_confirmed:
            print(f"  [LAB] {ticker}: LAB_NOT_CONFIRMED â€” not present in Lab export")
        elif _conflicts:
            _flag_count = sum(1 for c in _conflicts if c["severity"] == "FLAG")
            print(f"  [LAB] {ticker}: {len(_conflicts)} field conflict(s) ({_flag_count} FLAG-level)")
        else:
            print(f"  [LAB] {ticker}: Lab aligned â€” no field conflicts")
    # â”€â”€ End lab context injection â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    # -- Entry timing engine - single ticker
    from entry_timing_engine import load_garch_rows, build_pre_trade_probability_block
    _garch_rows_t = load_garch_rows(MA_PIPELINE)
    _garch_row_t  = _garch_rows_t.get(ticker.upper(), {})
    _lab_r_t      = get_lab_row(_lab_rows, ticker) if _lab_rows else {}
    _active_t     = SESSION.get("active_thesis_" + ticker.upper()) or {}
    _days_phase   = len(_active_t.get("state_chain", [])) if _active_t else 0
    _ete_block_t  = build_pre_trade_probability_block(ticker, row, _garch_row_t, _lab_r_t or {}, _days_phase)
    # -- End entry timing engine
    # -- Direction Conflict Resolver + Alternative Contract Selector
    _conflict  = {}
    _alt_trade = None
    try:
        from direction_conflict_resolver import resolve_direction
        from alternative_contract_selector import select_alternative_contract
        _conflict = resolve_direction(row)
        row["dcr_dominant_direction"] = _conflict.get("dominant_direction", "")
        row["dcr_pipeline_direction"] = _conflict.get("pipeline_direction", "")
        row["dcr_misdiagnosed"]       = _conflict.get("misdiagnosed", False)
        row["dcr_conflict_severity"]  = _conflict.get("conflict_severity", "")
        row["dcr_call_score"]         = _conflict.get("call_score", "")
        row["dcr_put_score"]          = _conflict.get("put_score", "")
        _diag_flag = "⚠ MISDIAGNOSIS" if _conflict.get("misdiagnosed") else ""
        print(f"  [DCR] {ticker}: dominant={_conflict.get('dominant_direction')} pipeline={_conflict.get('pipeline_direction')} severity={_conflict.get('conflict_severity','NONE')} {_diag_flag}".strip())
        if _conflict.get("misdiagnosed"):
            _live_price = float(row.get("live_price") or row.get("last_price") or 0)
            if _live_price > 0:
                _alt_trade = select_alternative_contract(row, _conflict["dominant_direction"], _live_price)
                row["alt_contract_symbol"] = _alt_trade.get("alt_contract_symbol", "")
                row["alt_direction"]       = _alt_trade.get("alt_direction", "")
                row["alt_strike"]          = _alt_trade.get("alt_strike", "")
                row["alt_contract_status"] = _alt_trade.get("alt_contract_status", "")
                print(f"  [ALT] {ticker}: {_alt_trade.get('alt_contract_symbol','')} status={_alt_trade.get('alt_contract_status','')}")
    except Exception as _dcr_err:
        print(f"  [DCR] skipped: {_dcr_err}")
    # -- End Direction Conflict Resolver
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
                                               ticker_note=_ticker_note,
                                               lab_context_block=lab_context_block,
                                               lab_conflict_block=lab_conflict_block,
                                               pre_trade_prob_block=_ete_block_t)
        response = call_api(prompt, use_web_search=_use_web_search)
    run_dir, ts = get_run_dir()
    results = write_all_outputs(response, session, run_dir, ts,
                                 tickers=[ticker], prefix=f"ticker_{ticker.lower()}")

    # -- Junior Briefing -- merged into ticker output
    try:
        from pipeline_interpreter_engine import build_story_prompt
        from pipeline_interpreter_outputs import write_all_outputs_with_junior
        _story_prompt = build_story_prompt(
            ticker=ticker,
            pipeline_row=row,
            options_data=ticker_options if ticker_options else None,
            update_type="FULL",
        )
        _story_response = call_api(_story_prompt, model=MODEL_DEEP_DIVE, max_tokens=12000)
        results = write_all_outputs_with_junior(
            main_response=response,
            story_response=_story_response,
            session=session,
            run_dir=run_dir,
            ts=ts,
            ticker=ticker,
            pre_trade_prob_block=_ete_block_t,
        )
        print("  ✅ Junior Briefing merged into ticker output")
        # -- Phantom 1: Write interpreter sidecar JSON for morning validator
        try:
            from pipeline_interpreter_outputs import write_interpreter_sidecar
            _run_id = SESSION.get("run_id") or ts
            _sidecar_path = write_interpreter_sidecar(
                ticker=ticker,
                run_id=_run_id,
                ts=ts,
                pre_trade_prob_block=_ete_block_t,
                story_response=_story_response,
            )
            if _sidecar_path:
                print(f"  ✅ Interpreter sidecar: {_sidecar_path.name}")
        except Exception as _se:
            print(f"  ⚠  Sidecar write skipped: {_se}")
            # Phantom 4: Save evening baseline if in EVENING session mode
        try:
            import json as _json4
            _ss_path = MA_INPUTS / "session_state.json"
            _sess_mode = ""
            if _ss_path.exists():
                _ss = _json4.loads(_ss_path.read_text(encoding="utf-8"))
                _sess_mode = _ss.get("session_mode", "")
            if _sess_mode == "EVENING" and _sidecar_path and _sidecar_path.exists():
                from thesis_registry import save_evening_baseline
                _sc_data = _json4.loads(_sidecar_path.read_text(encoding="utf-8"))
                _saved = save_evening_baseline(ticker, _sc_data)
                if _saved:
                    print(f"  ✅ Evening baseline saved for {ticker}")
        except Exception as _be:
            print(f"  ⚠  Baseline save skipped: {_be}")
    except Exception as _je:
        print(f"  ⚠  Junior Briefing merge skipped: {_je}")
    # -- End Junior Briefing merge

    print(f"\n  Deep dive complete ({int(time.time()-t0)}s)")
    _print_results(results, response)
    return response



def cmd_live(args: str = ""):
    """
    Fetch all four live data gaps for a ticker and store in LIVE_DATA session store.
    Automatically injected into /ticker and /intraday prompts.

    Usage:
      /live WFC                          â€” all four data points, auto-detect contract
      /live WFC WFC260618P00072500        â€” include specific contract for spread fetch
      /live WFC WFC260618P00072500 put    â€” filter options volume to puts only
      /live                              â€” show all fetched tickers in LIVE_DATA store

    Data fetched:
      1. Intraday options volume (replaces OI_ONLY pipeline flag)
      2. Institutional flow (unusual vol/OI ratio contracts)
      3. Live bid/ask spread (specific contract if supplied)
      4. Sector peer confirmation (JPM/BAC/C for WFC etc.)

    Requires Polygon API key in environment or pipeline_interpreter_engine.py defaults.
    """
    if not _LIVE_MARKET_AVAILABLE:
        print("  âš   live_market_reader.py not found in interpreter directory.")
        print("  Copy live_market_reader.py to the pipeline_interpreter folder.")
        return

    args = args.strip()

    # No args â€” show store status
    if not args:
        if not LIVE_DATA:
            print("  No live data fetched yet.")
            print("  Usage: /live TICKER [contract_ticker] [call|put]")
        else:
            print(f"  Live data store ({len(LIVE_DATA)} tickers):")
            for t, d in sorted(LIVE_DATA.items()):
                fetched = d.get("fetched_at", "?")
                ov = d.get("options_volume", {})
                pc = d.get("peer_confirmation", {})
                ls = d.get("live_spread", {})
                vol_flag = ov.get("put_volume_flag", "") or ""
                peer_v   = pc.get("alignment_verdict", "")[:35] if pc.get("status") == "OK" else ""
                spread_q = ls.get("spread_quality", "")[:20] if ls.get("status") == "OK" else "no contract"
                print(f"    {t:<8} [{fetched}]  {vol_flag[:40]}  {peer_v}  spread: {spread_q}")
        return

    tokens = args.split()
    ticker       = tokens[0].upper()
    contract     = tokens[1] if len(tokens) >= 2 and not tokens[1].lower() in ("call","put") else None
    direction    = next((t for t in tokens[1:] if t.lower() in ("call","put")), None)

    print(f"\n  Fetching live market data: {ticker}")
    if contract:
        print(f"  Contract: {contract}")
    if direction:
        print(f"  Direction filter: {direction}")

    data = fetch_all_live_data(
        ticker         = ticker,
        contract_ticker= contract,
        direction      = direction,
        write_to_ma_inputs=True,
    )

    # Store in session
    LIVE_DATA[ticker] = data

    # Print formatted summary
    print()
    summary = format_live_data_for_prompt(data)
    if summary:
        for line in summary.split("\n")[:35]:
            print(f"  {line}")

    print()
    print(f"  âœ… LIVE_DATA[{ticker}] stored â€” will be injected into /ticker {ticker} and /intraday {ticker}")
    print(f"  Run /ticker {ticker} or /intraday {ticker} to use in analysis.")


def cmd_price(args: str = ""):
    """
    Register a live price for a ticker so it flows into /ticker and /intraday.

    Usage:
      /price WFC 75.81
      /price WFC 75.81 -0.23          (price + change%)
      /price WFC 75.81 -0.23 75.56    (price + change% + VWAP)
      /price WFC 75.81 -0.23 75.56 4.1 0.38  (+ vol_ratio + spread)

    Shows all registered prices with /price (no args).
    Clears a ticker with /price WFC clear.
    """
    args = args.strip()

    # No args â€” show all registered prices
    if not args:
        if not LIVE_PRICES:
            print("  No live prices registered. Use: /price TICKER PRICE [change%] [vwap] [vol_ratio] [spread]")
        else:
            print(f"  Registered live prices ({len(LIVE_PRICES)} tickers):")
            for t, d in sorted(LIVE_PRICES.items()):
                chg  = f"  {d.get('change_pct','?')}%" if d.get('change_pct') else ""
                vwap = f"  VWAP={d.get('vwap','')}" if d.get('vwap') else ""
                ts   = d.get('timestamp', '')
                print(f"    {t:<8} ${d.get('price','?')}{chg}{vwap}  [{ts}]")
        return

    tokens = args.split()
    if len(tokens) < 1:
        print("  Usage: /price TICKER PRICE [change%] [vwap] [vol_ratio] [spread]")
        return

    ticker = tokens[0].upper()

    # Clear instruction
    if len(tokens) == 2 and tokens[1].lower() == "clear":
        if ticker in LIVE_PRICES:
            del LIVE_PRICES[ticker]
            print(f"  âœ… Live price for {ticker} cleared.")
        else:
            print(f"  {ticker} not in price store.")
        return

    if len(tokens) < 2:
        print(f"  Usage: /price {ticker} PRICE [change%] [vwap] [vol_ratio] [spread]")
        return

    from datetime import datetime as _dt
    try:
        price = float(tokens[1])
    except ValueError:
        print(f"  âš   Invalid price: {tokens[1]}")
        return

    entry = {
        "price":      price,
        "timestamp":  _dt.now().strftime("%H:%M ET"),
    }
    if len(tokens) >= 3:
        try:    entry["change_pct"] = float(tokens[2])
        except: pass
    if len(tokens) >= 4:
        try:    entry["vwap"] = float(tokens[3])
        except: pass
    if len(tokens) >= 5:
        try:    entry["vol_ratio"] = float(tokens[4])
        except: pass
    if len(tokens) >= 6:
        try:    entry["spread"] = tokens[5]
        except: pass

    LIVE_PRICES[ticker] = entry

    # Print confirmation
    chg  = f"  change={entry['change_pct']}%" if entry.get("change_pct") is not None else ""
    vwap = f"  VWAP={entry['vwap']}" if entry.get("vwap") else ""
    print(f"  âœ… Live price registered: {ticker} = ${price}{chg}{vwap}  [{entry['timestamp']}]")
    print(f"  Will be injected into /ticker {ticker} and /intraday {ticker} automatically.")


def cmd_intraday(args: str = ""):
    """
    Intraday chart analysis â€” 15m/30m charts + live price context.

    Usage:
      /intraday WFC                           (no charts â€” price-only update)
      /intraday WFC 15m_chart.png             (single chart)
      /intraday WFC chart1.png chart2.png     (multiple charts â€” e.g. 15m + 30m)

    Drops chart images into MA_Inputs/charts/ named TICKER_15m.png / TICKER_30m.png
    and they will be auto-detected. Or supply paths directly.

    Designed to be run at 09:45-10:30 ET after /triage has identified the shortlist.
    Requires /price TICKER PRICE to have been run first for best analysis.
    """
    tokens = args.split() if args.strip() else []

    if not tokens:
        print("  Usage: /intraday TICKER [chart1.png] [chart2.png ...]")
        print("  Example: /intraday WFC WFC_15m.png WFC_30m.png")
        print("  Tip: run /price WFC 75.81 first to register the live price.")
        return

    ticker = tokens[0].upper()

    # Collect explicit image paths
    explicit_images = []
    for tok in tokens[1:]:
        p = Path(tok.strip('"').strip("'"))
        if p.exists():
            explicit_images.append(str(p))
        else:
            print(f"  âš   Image not found: {tok} â€” skipping")

    # Auto-scan MA_Inputs/charts for intraday files for this ticker
    ma_files = scan_ma_inputs_for_ticker(ticker)
    intraday_keywords = {"15m", "30m", "5m", "intraday", "1h", "1hr"}
    ma_intraday = [
        f for f in (ma_files["charts"] + ma_files["screenshots"])
        if any(kw in Path(f).name.lower() for kw in intraday_keywords)
    ]

    # Merge explicit + auto-detected, deduplicate
    all_images = list(dict.fromkeys(explicit_images + ma_intraday))

    # Detect timeframes from filenames
    chart_timeframes = []
    for img in all_images:
        name = Path(img).name.lower()
        for tf in ["15m", "30m", "5m", "1h", "1hr", "intraday"]:
            if tf in name and tf not in chart_timeframes:
                chart_timeframes.append(tf)
    if not chart_timeframes:
        chart_timeframes = ["intraday"]

    # Get pipeline row from session CSV
    file_path = SESSION.get("last_pipeline_csv")
    if not file_path:
        print("  [ERROR] No CSV in session. Run /triage first.")
        return

    rows = read_pipeline_csv(file_path)
    row  = next((r for r in rows if r.get("ticker","").upper() == ticker), None)
    if not row:
        row = next((r for r in rows if ticker in str(r.get("underlying","")).upper()), None)
    if not row:
        print(f"  âš   {ticker} not found in session CSV. Analysis will use live price only.")
        row = {"ticker": ticker, "note": "Not found in pipeline CSV â€” live price analysis only"}

    # Load options data
    ticker_options = dict(_loaded_options)
    for opt_path in ma_files["options"]:
        opt_name = Path(opt_path).stem
        if opt_name not in ticker_options:
            ticker_options[opt_name] = read_options_file(opt_path)

    # Load trader note
    import json as _json
    _notes_path  = MA_INPUTS / "news_terminal" / "trader_notes.json"
    _ticker_note = ""
    if _notes_path.exists():
        try:
            _notes = _json.loads(_notes_path.read_text(encoding="utf-8"))
            _note_entry = _notes.get(ticker, {})
            _ticker_note = _note_entry.get("note","") if isinstance(_note_entry,dict) else str(_note_entry)
        except Exception:
            pass

    # Build live price block
    live_price_block = format_live_price_block(ticker, LIVE_PRICES)
    if not live_price_block:
        print(f"  âš   No live price registered for {ticker}.")
        print(f"  Run: /price {ticker} PRICE [change%] [vwap]")
        print(f"  Continuing with pipeline EOD price only.")

    # Report what we are feeding
    print(f"\n  Running intraday analysis: {ticker}")
    print(f"  Charts: {len(all_images)} image(s) â€” timeframes: {', '.join(chart_timeframes)}")
    if live_price_block:
        p = LIVE_PRICES[ticker]
        print(f"  Live price: ${p.get('price')}  [{p.get('timestamp','')}]")
    print()

    prompt = build_intraday_prompt(
        ticker          = ticker,
        pipeline_row    = row,
        live_price_block= live_price_block,
        options_data    = ticker_options if ticker_options else None,
        ticker_note     = _ticker_note,
        chart_timeframes= chart_timeframes,
    )

    t0 = time.time()
    if all_images:
        response = call_api(prompt, images=all_images, use_web_search=False,
                            model=MODEL_DEEP_DIVE)
    else:
        response = call_api(prompt, use_web_search=False, model=MODEL_DEEP_DIVE)

    run_dir, ts = get_run_dir()
    results = write_all_outputs(response, session, run_dir, ts,
                                tickers=[ticker],
                                prefix=f"intraday_{ticker.lower()}")
    print(f"\n  Intraday analysis complete ({int(time.time()-t0)}s)")
    _print_results(results, response)
    return response


def cmd_sync(source_path: str = None, max_age_hours: int = 24):
    """/sync -- copy AVSHUNTER pipeline outputs into MA_Inputs/pipeline_outputs/."""
    try:
        from ma_inputs_sync import sync_to_ma_inputs
        kwargs = dict(max_age_hours=max_age_hours, verbose=True, recursive=True)
        if source_path:
            kwargs["source_dir"] = source_path
        result = sync_to_ma_inputs(**kwargs)
        if isinstance(result, dict):
            copied = result.get("copied", result.get("synced", "?"))
            skipped = result.get("skipped", "?")
            print(f"  [SYNC] Complete: {copied} file(s) copied, {skipped} skipped")
        else:
            print(f"  [SYNC] Complete")
        print(f"  Run /triage to pick up updated files.")
    except ImportError:
        print("  [SYNC] ERROR: ma_inputs_sync.py not found in interpreter folder.")
    except Exception as e:
        print(f"  [SYNC] ERROR: {e}")


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
        print(f"  âš   Only captured one line. Type /brief alone, paste, then END")
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
        print("  âš   No text received."); return
    saved_path=save_pasted_brief(brief_text)
    lines_count=brief_text.count("\n")+1
    print(f"\n  âœ… Brief saved ({lines_count} lines)")
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
        print(f"  âš   No note entered for {ticker}."); return
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
    print(f"\n  âœ… Note saved for {ticker}: '{_preview}'")
    print(f"  Will be injected into /ticker {ticker} automatically.")


MENU = """
Ã¢â€¢â€Ã¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢â€”
Ã¢â€¢â€˜     AVSHUNTER PIPELINE INTERPRETER v1.0 Ã¢â‚¬â€ COMMAND MENU          Ã¢â€¢â€˜
Ã¢â€¢Â Ã¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢Â£
Ã¢â€¢â€˜  /triage [FILE]               Fast priority scan Ã¢â‚¬â€ rank all candidates  Ã¢â€¢â€˜
Ã¢â€¢â€˜  /interpret FILE [FILE2...]   Interpret pipeline CSV file(s)     Ã¢â€¢â€˜
Ã¢â€¢â€˜  /morning FILE                Morning validation pass            Ã¢â€¢â€˜
Ã¢â€¢â€˜  /ticker TICKER FILE          Deep dive single ticker            Ã¢â€¢â€˜
Ã¢â€¢â€˜  /chart TICKER IMG [IMG2...]  Chart image analysis (vision)      Ã¢â€¢â€˜
Ã¢â€¢â€˜  /auto                        Auto-detect pipeline files         Ã¢â€¢â€˜
Ã¢â€¢â€˜  /load FILE                   Load a pipeline CSV into session   Ã¢â€¢â€˜
Ã¢â€¢â€˜  /options FILE                Add options data file              Ã¢â€¢â€˜
â•‘  /brief                        Paste newsroom brief into session         â•‘
â•‘  /note TICKER [obs]             Add trader narrative for deep dive          â•‘
Ã¢â€¢â€˜  /sync                        Sync AVSHUNTER outputs to MA_Inputs     Ã¢â€¢â€˜
Ã¢â€¢â€˜  /macro FILE                  Load macro intelligence JSON/file       Ã¢â€¢â€˜
Ã¢â€¢â€˜  /news FILE [TICKER]          Load News Terminal CSV/output           Ã¢â€¢â€˜
Ã¢â€¢â€˜  /inputs                      Show MA_Inputs folder status          Ã¢â€¢â€˜
Ã¢â€¢â€˜  /lab [FILE]                    Load Lab export + reconcile universe     Ã¢â€¢â€˜
Ã¢â€¢â€˜  /story TICKER [--fresh]       Story of the Trade â€” junior briefing  Ã¢â€¢â€˜
Ã¢â€¢â€˜  /update TICKER [chart IMG...] Update story with new chart or options Ã¢â€¢â€˜
Ã¢â€¢â€˜  /status                      Show session summary               Ã¢â€¢â€˜
Ã¢â€¢â€˜  /reset                       Clear session                      Ã¢â€¢â€˜
Ã¢â€¢â€˜  /menu                        Show this menu                     Ã¢â€¢â€˜
Ã¢â€¢â€˜  /ete TICKER                  Entry timing probability report                       Ã¢â€¢â€˜
Ã¢â€¢â€˜  /exit                        Close interpreter                  Ã¢â€¢â€˜
Ã¢â€¢Å¡Ã¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢Â"""


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
    elif cmd=="/intraday":
        return cmd_intraday(arg.strip() if arg else "")
    elif cmd=="/live":
        cmd_live(arg.strip() if arg else "")
    elif cmd=="/price":
        cmd_price(arg.strip() if arg else "")
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
    elif cmd=="/lab":
        cmd_lab(arg.strip() if arg else "")
    elif cmd=="/story":
        return cmd_story(arg.strip() if arg else "")
    elif cmd=="/update":
        return cmd_update(arg.strip() if arg else "")
    elif cmd == "/ete":
        from entry_timing_engine import load_garch_rows, build_pre_trade_probability_block
        from lab_reconciliation import get_lab_row as _get_lab_row_ete2
        _tok = arg.strip().upper() if arg and arg.strip() else ""
        if not _tok:
            print("  Usage: /ete TICKER")
        else:
            _file = SESSION.get("last_pipeline_csv")
            _rows = read_pipeline_csv(_file) if _file else []
            _row  = next((r for r in _rows if r.get("ticker", "").upper() == _tok), {})
            _g    = load_garch_rows(MA_PIPELINE).get(_tok, {})
            _l    = _get_lab_row_ete2(SESSION.get("lab_rows", []), _tok)
            print("\n" + build_pre_trade_probability_block(_tok, _row, _g, _l or {}, 0))
    elif cmd in("/exit","/quit"): return "EXIT"
    else: print(f"  Unknown command: {cmd}  (type /menu for help)")
    return None


# â”€â”€ STORY OF THE TRADE â€” additions only, appended at bottom â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def cmd_story(args: str = ""):
    """
    /story TICKER [--fresh]
    Generate the full Story of the Trade for a ticker.
    --fresh forces FULL update even if a previous story exists.
    """
    import json as _json
    from pipeline_interpreter_engine import (
        build_story_prompt, get_latest_story_for_thesis, load_image,
    )
    from pipeline_interpreter_outputs import write_story_outputs
    import thesis_registry as _tr

    # 1. Parse ticker and --fresh flag
    tokens = args.split()
    if not tokens:
        print("  Usage: /story TICKER [--fresh]")
        return
    ticker   = tokens[0].upper()
    is_fresh = "--fresh" in tokens

    # 2. Get pipeline row from session CSV
    file_path = SESSION.get("last_pipeline_csv")
    if not file_path:
        print("  [ERROR] No CSV loaded. Run /triage first or /load FILE")
        return
    rows = read_pipeline_csv(file_path)
    row  = next((r for r in rows if r.get("ticker", "").upper() == ticker), None)
    if not row:
        print(f"  [ERROR] {ticker} not found in session CSV")
        return

    # 3. Gather MA_Inputs files for this ticker
    ma_files = scan_ma_inputs_for_ticker(ticker)
    ticker_options = dict(_loaded_options)
    for opt_path in ma_files["options"]:
        opt_name = Path(opt_path).stem
        if opt_name not in ticker_options:
            ticker_options[opt_name] = read_options_file(opt_path)
    ticker_charts = ma_files["charts"] + ma_files["screenshots"]

    # 4. Check thesis registry for existing active thesis
    active_thesis = _tr.get_active_thesis(ticker)
    update_type   = "FULL"
    previous_html = ""
    previous_ts   = ""
    thesis_id     = ""

    if active_thesis and not is_fresh:
        # Carry forward â€” load previous story HTML
        previous_html = get_latest_story_for_thesis(ticker)
        if previous_html:
            update_type = "OVERNIGHT"
            previous_ts = active_thesis.get("latest_story_ts", "")
            thesis_id   = active_thesis["thesis_id"]
            print(f"  [CARRY-FORWARD] Active thesis {thesis_id} â€” using OVERNIGHT update")
        else:
            update_type = "FULL"
    else:
        if is_fresh and active_thesis:
            _tr.close_thesis(ticker, active_thesis["thesis_id"], reason="trader_fresh_reset")
            print(f"  [FRESH] Previous thesis closed â€” starting new FULL story")

    # 5. Build story prompt
    import time as _time
    t0 = _time.time()
    prompt = build_story_prompt(
        ticker=ticker,
        pipeline_row=row,
        options_data=ticker_options if ticker_options else None,
        chart_images=ticker_charts if ticker_charts else None,
        previous_story_html=previous_html,
        update_type=update_type,
    )

    # 6. Call API
    response = call_api(prompt, images=ticker_charts if ticker_charts else None,
                        model=MODEL_DEEP_DIVE)
    run_dir, ts = get_run_dir()

    # 7. If no active thesis (FULL run), create one in the registry
    if update_type == "FULL":
        try:
            thesis_id = _tr.create_thesis(
                ticker=ticker,
                direction=str(row.get("direction", "UNKNOWN")),
                horizon=str(row.get("horizon", "")),
                strike_zone=str(row.get("preferred_contract", row.get("strike_zone", "0"))),
                pipeline_run_id=str(row.get("pipeline_run_id", "")),
                kill_switch_level=float(str(row.get("kill_switch_level", 0) or 0).replace("$", "")),
                probe_trigger=float(str(row.get("probe_trigger", 0) or 0).replace("$", "")),
                armed_trigger=float(str(row.get("armed_trigger", 0) or 0).replace("$", "")),
            )
            print(f"  [THESIS] Created: {thesis_id}")
        except Exception as _e:
            print(f"  [THESIS] Registry create error: {_e}")
            thesis_id = f"{ticker}_STORY_{ts}"

    # 8. Write outputs
    state_chain = active_thesis.get("state_chain", []) if active_thesis else []
    results = write_story_outputs(
        response=response,
        ticker=ticker,
        session=session,
        run_dir=run_dir,
        ts=ts,
        thesis_id=thesis_id,
        update_type=update_type,
        state_chain=state_chain,
        previous_ts=previous_ts,
    )

    # 9. Update thesis registry
    try:
        _tr.update_thesis(
            ticker=ticker,
            thesis_id=thesis_id,
            ts=ts,
            verdict=results.get("section_statuses", {}).get("section_8_verdict", "WATCH"),
            trade_state=str(row.get("triage_verdict", "WATCH")),
            trigger_proximity=str(row.get("trigger_proximity", "")),
            story_path=results.get("html_path", ""),
            latest_story_path=results.get("html_path", ""),
        )
    except Exception as _e:
        print(f"  [THESIS] Registry update error: {_e}")

    # 10. QA check
    if _QA_AVAILABLE:
        try:
            from interpreter_qa import check_story_qa
            qa = check_story_qa(ticker, results.get("html_path", ""))
            print(f"  [QA] Story: {qa.get('overall', 'UNKNOWN')} â€” "
                  f"{qa.get('pass_count', 0)}/{qa.get('total_checks', 0)} checks passed")
        except Exception:
            pass

    # 11. Summary
    print(f"\n  Story of the Trade complete ({int(_time.time()-t0)}s)")
    print(f"  update_type:  {update_type}")
    print(f"  thesis_id:    {thesis_id}")
    if results.get("html_path"):
        print(f"  HTML:         {Path(results['html_path']).name}")
    if results.get("csv_path"):
        print(f"  CSV:          {Path(results['csv_path']).name}")
    return response


def cmd_update(args: str = ""):
    """
    /update TICKER [chart IMG1 IMG2...] [options FILE]
    Update an existing story with new chart or options data.
    """
    import time as _time
    from pipeline_interpreter_engine import build_story_prompt, get_latest_story_for_thesis
    from pipeline_interpreter_outputs import write_story_outputs
    import thesis_registry as _tr

    tokens = args.split()
    if not tokens:
        print("  Usage: /update TICKER [chart IMG...] [options FILE]")
        print("  Example: /update WFC chart wfc_1030.png")
        print("  Example: /update WFC options wfc_options.csv")
        return
    ticker = tokens[0].upper()
    rest   = tokens[1:]

    # 1. Detect chart images and options files
    chart_images  = []
    options_files = []
    mode = None
    for tok in rest:
        if tok.lower() == "chart":
            mode = "chart"
        elif tok.lower() == "options":
            mode = "options"
        elif mode == "chart":
            chart_images.append(tok.strip('"').strip("'"))
        elif mode == "options":
            options_files.append(tok.strip('"').strip("'"))

    # 2. Determine update_type
    if chart_images and options_files:
        update_type = "FULL"
    elif chart_images:
        update_type = "CHART_UPDATE"
    elif options_files:
        update_type = "OPTIONS_UPDATE"
    else:
        print(f"  [ERROR] No chart or options files specified.")
        print("  Usage: /update TICKER chart IMG1 [IMG2...]")
        return

    # 3. Load previous story â€” try registry first (Option B), then scan outputs
    active_thesis = _tr.get_active_thesis(ticker)
    previous_html = ""
    previous_ts   = ""
    thesis_id     = ""

    if active_thesis:
        thesis_id   = active_thesis["thesis_id"]
        previous_ts = active_thesis.get("latest_story_ts", "")
        reg_path    = active_thesis.get("latest_story_path", "")
        if reg_path and Path(reg_path).exists():
            try:
                previous_html = Path(reg_path).read_text(encoding="utf-8")
                print(f"  [REGISTRY] Loaded previous story: {Path(reg_path).name}")
            except OSError:
                pass

    if not previous_html:
        previous_html = get_latest_story_for_thesis(ticker)
        if previous_html:
            print(f"  [SCAN] Loaded previous story from outputs/ scan")
        else:
            print(f"  [ERROR] No previous story found for {ticker}. Run /story {ticker} first.")
            return

    # 4. Get pipeline row from session
    file_path = SESSION.get("last_pipeline_csv")
    if not file_path:
        print("  [ERROR] No CSV loaded. Run /triage first or /load FILE")
        return
    rows = read_pipeline_csv(file_path)
    row  = next((r for r in rows if r.get("ticker", "").upper() == ticker), {})

    # 5. Load options data if provided
    ticker_options = {}
    for opt_f in options_files:
        if Path(opt_f).exists():
            ticker_options[Path(opt_f).stem] = read_options_file(opt_f)
            print(f"  [OPTIONS] Loaded: {Path(opt_f).name}")
        else:
            print(f"  [WARN] Options file not found: {opt_f}")

    # 6. Build prompt and call API
    t0 = _time.time()
    prompt = build_story_prompt(
        ticker=ticker,
        pipeline_row=row,
        options_data=ticker_options if ticker_options else None,
        previous_story_html=previous_html,
        update_type=update_type,
    )
    response = call_api(prompt, images=chart_images if chart_images else None,
                        model=MODEL_DEEP_DIVE)
    run_dir, ts = get_run_dir()

    # 7. Write versioned outputs (never overwrite)
    state_chain = active_thesis.get("state_chain", []) if active_thesis else []
    results = write_story_outputs(
        response=response,
        ticker=ticker,
        session=session,
        run_dir=run_dir,
        ts=ts,
        thesis_id=thesis_id,
        update_type=update_type,
        state_chain=state_chain,
        previous_ts=previous_ts,
    )

    # 8. Update thesis registry
    if thesis_id:
        try:
            _tr.update_thesis(
                ticker=ticker,
                thesis_id=thesis_id,
                ts=ts,
                verdict=results.get("section_statuses", {}).get("section_8_verdict", "WATCH"),
                trade_state=str(row.get("triage_verdict", "WATCH")),
                trigger_proximity=str(row.get("trigger_proximity", "")),
                story_path=results.get("html_path", ""),
                latest_story_path=results.get("html_path", ""),
            )
        except Exception as _e:
            print(f"  [THESIS] Registry update error: {_e}")

    # 9. Summary
    print(f"\n  Story update complete ({int(_time.time()-t0)}s)")
    print(f"  update_type:  {update_type}")
    print(f"  thesis_id:    {thesis_id}")
    _changed = {"CHART_UPDATE": "Sections 5+8", "OPTIONS_UPDATE": "Sections 6+8",
                "FULL": "All 8 sections"}.get(update_type, "Selected sections")
    print(f"  Regenerated:  {_changed}")
    if results.get("html_path"):
        print(f"  HTML:         {Path(results['html_path']).name}")
    return response


# â”€â”€ COMPONENT 9 â€” cmd_lab â€” appended at bottom â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def cmd_lab(args: str = ""):
    """
    /lab [FILE]
    Manually load a Lab export CSV and show reconciliation summary.
    If FILE not specified, scans MA_Inputs/lab_export/ for most recent file.
    Does not run a full triage -- reconciliation summary only.
    """
    from lab_reconciliation import (
        load_lab_export, reconcile_universes,
        check_run_id_alignment, build_lab_alignment_block,
    )

    path = args.strip().strip('"').strip("'") if args.strip() else None
    if path:
        lab_rows, lab_filename = load_lab_export(Path(path).parent)
    else:
        lab_rows, lab_filename = load_lab_export(MA_LAB)

    if not lab_rows:
        print("  [LAB] No lab export found.")
        print(f"  Place avshunter_signals_*.csv in {MA_LAB}")
        return

    # Build interpreter ticker list from session CSV if available
    interpreter_tickers = []
    _csv_path = SESSION.get("pipeline_csv") or SESSION.get("last_pipeline_csv")
    if _csv_path:
        try:
            rows = read_pipeline_csv(_csv_path)
            interpreter_tickers = [str(r.get("ticker", "")).upper() for r in rows]
        except Exception:
            pass

    pipeline_run_id = SESSION.get("pipeline_run_id", "")
    run_id_check    = check_run_id_alignment(lab_rows, pipeline_run_id)
    reconciliation  = reconcile_universes(lab_rows, interpreter_tickers)
    lab_block       = build_lab_alignment_block(reconciliation, lab_filename, run_id_check)

    print(f"\n{lab_block}")

    SESSION["lab_rows"]           = lab_rows
    SESSION["lab_reconciliation"] = reconciliation
    SESSION["lab_filename"]       = lab_filename

    print(f"\n  {len(lab_rows)} Lab tickers loaded into session.")
    print(f"  Run /triage to apply reconciliation, or /ticker TICKER to check Lab alignment.")
    if reconciliation.get("interp_only"):
        print(f"  LAB_NOT_CONFIRMED: {', '.join(reconciliation['interp_only'])}")

