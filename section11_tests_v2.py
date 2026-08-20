"""Section 11 — Component 9 full test checklist v2."""
import sys, io, contextlib, csv, os, re, tempfile
from pathlib import Path
sys.path.insert(0, ".")

import pipeline_interpreter_engine as _eng
import pipeline_interpreter_commands as _cmd
from pipeline_interpreter_commands import SESSION, MA_LAB

SAMPLE  = MA_LAB / "avshunter_signals_20260521_212948_2026-05-22_1213.csv"
OUTPUTS = Path("outputs")

_TRIAGE_FAKE = (
    "[TRIAGE_RANKED_TABLE]\n"
    "rank,ticker,direction,pipeline_score,dte,horizon,live_validation_state,"
    "validation_score,earnings_flag,ma_inputs_ready,triage_verdict,triage_reason\n"
    "1,WMT,LONG_PUT,85,28,6-10,,80,NO,YES,DEEP_DIVE_NOW,Lab confirmed\n"
    "2,AAPL,LONG_CALL,70,30,1-5,,65,NO,YES,REVIEW_LATER,Not in lab\n"
    "3,CALM,LONG_PUT,75,45,11-20,,72,NO,PARTIAL,DEEP_DIVE_NEXT,Lab confirmed\n"
    "[/TRIAGE_RANKED_TABLE]\n"
    "[TRIAGE_SUMMARY]\nTest session.\n[/TRIAGE_SUMMARY]\n"
    "[TRIAGE_EXECUTION_ORDER]\n/ticker WMT\n"
    "EXECUTION PERMISSION: NONE_PIPELINE_INTERPRETER_ONLY\n[/TRIAGE_EXECUTION_ORDER]\n"
)
_TICKER_FAKE = (
    "[TRADE_BRIEF_CSV]\nticker,direction,final_verdict,trade_state,horizon,dte,"
    "trigger_level,kill_switch_level,preferred_contract,premium,rr,iv_context,"
    "ivp,earnings_in_window,earnings_action,max_pain_risk,sector_confirmation_required,"
    "first_hour_rule,probe_permitted,initial_adverse_tolerance,capital_permission,"
    "narrative_summary,execution_permission\n"
    "WMT,LONG_PUT,PROBE,WATCH,6-10,28,116.00,120.00,WMT260618P00115000,"
    "1.08,6.4,FAIR,40,NO,N/A,LOW,NO,YES,YES,0.40,"
    "CAPITAL_DENIED_PENDING_LIVE_CONFIRMATION,Test,"
    "NONE_PIPELINE_INTERPRETER_ONLY\n[/TRADE_BRIEF_CSV]\n"
)

_current_fake = [_TRIAGE_FAKE]
_eng.call_api = lambda *a, **kw: _current_fake[0]
_cmd.call_api = lambda *a, **kw: _current_fake[0]
_cmd._build_battlefield_triage_response = lambda *a, **kw: None

def _run(fn, *a, **kw):
    buf = io.StringIO(); crashed = False; exc = None
    try:
        with contextlib.redirect_stdout(buf): fn(*a, **kw)
    except Exception as e:
        crashed = True; exc = e; buf.write(f"CRASH: {e}\n")
    return buf.getvalue(), crashed, exc

def _latest_html(pat="triage_*.html"):
    files = sorted(OUTPUTS.rglob(pat), key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0].read_text(encoding="utf-8") if files else ""

def _clear_lab(): 
    for k in ("lab_rows","lab_reconciliation","lab_filename","lab_run_id_check"): SESSION.pop(k,None)

def _pipeline_csv(*tickers, **overrides):
    """Write a pipeline CSV with the given tickers and return its path."""
    fields = ["ticker","direction","eil_v3_verdict","kill_switch_level","probe_trigger",
              "armed_trigger","execution_permission","horizon","preferred_contract",
              "ivp","premium","triage_rank","ev_score","wbs_grade","preferred_strike"]
    tmp = tempfile.NamedTemporaryFile(mode="w",suffix=".csv",delete=False,newline="",encoding="utf-8")
    w = csv.DictWriter(tmp, fieldnames=fields); w.writeheader()
    for t in tickers:
        row = {"ticker":t,"direction":"LONG_PUT","eil_v3_verdict":"ARMED",
               "kill_switch_level":"120","probe_trigger":"116","armed_trigger":"115",
               "execution_permission":"NONE_PIPELINE_INTERPRETER_ONLY","horizon":"6-10",
               "preferred_contract":f"{t}260618P00100000","ivp":"40","premium":"1.00",
               "triage_rank":"1","ev_score":"0.5","wbs_grade":"PROBABLE","preferred_strike":"100"}
        row.update({k:v for k,v in overrides.items()})
        w.writerow(row)
    tmp.close()
    return tmp.name

RESULTS = {}

# ═══════════════════════════════════════════════════════════
print("=" * 65)
print("SECTION 11.1 — Import Tests")
print("=" * 65)
import_tests = [
    ("lab_reconciliation.reconcile_universes",    lambda: __import__("lab_reconciliation").reconcile_universes),
    ("lab_reconciliation.load_lab_export",        lambda: __import__("lab_reconciliation").load_lab_export),
    ("lab_reconciliation.validate_lab_field_alignment", lambda: __import__("lab_reconciliation").validate_lab_field_alignment),
    ("lab_reconciliation.build_lab_alignment_block",    lambda: __import__("lab_reconciliation").build_lab_alignment_block),
    ("pipeline_interpreter_engine.MA_LAB",        lambda: _eng.MA_LAB),
    ("interpreter_qa.check_lab_reconciliation_qa",lambda: __import__("interpreter_qa").check_lab_reconciliation_qa),
]
all_11_1 = True
for desc, fn in import_tests:
    try:
        r = fn(); val = str(r)[:55] if not callable(r) else "callable"
        print(f"  PASS  {desc}  [{val}]")
    except Exception as e:
        all_11_1 = False; print(f"  FAIL  {desc}  -> {e}")
RESULTS["11.1"] = "PASS" if all_11_1 else "FAIL"
print()

# ═══════════════════════════════════════════════════════════
print("=" * 65)
print("SECTION 11.2 — Reconciliation Logic Tests")
print("=" * 65)

# 11.2.a  /lab loads 101 tickers
_clear_lab()
out_lab, crash_lab, _ = _run(_cmd.cmd_lab)
assert not crash_lab, f"11.2.a crashed"
assert len(SESSION.get("lab_rows",[])) == 101, f"11.2.a: {len(SESSION.get('lab_rows',[]))} rows"
print(f"  PASS  11.2.a  /lab loads 101 tickers")

# 11.2.b  Run_ID in /lab output
assert "20260521_212948" in out_lab, "11.2.b: Run_ID missing"
print(f"  PASS  11.2.b  Run_ID 20260521_212948 shown in /lab output")

# 11.2.c-f  /triage with proper pipeline CSV containing WMT, AAPL, CALM
# WMT and CALM are in the lab sample; AAPL is not → interp_only
_current_fake[0] = _TRIAGE_FAKE
pipe_csv = _pipeline_csv("WMT","AAPL","CALM")
try:
    out_triage, crash_triage, _ = _run(_cmd.cmd_triage, pipe_csv)
    assert not crash_triage, f"11.2.c crashed"
    html = _latest_html("triage_*.html")
    assert html, "11.2.c: no HTML"

    # 11.2.c
    assert "Intelligence Lab Reconciliation" in html, "11.2.c: LAB card missing"
    print(f"  PASS  11.2.c  /triage HTML contains LAB_ALIGNMENT card")

    # 11.2.d  counts
    rec = SESSION.get("lab_reconciliation",{})
    lab_set   = {r["Ticker"] for r in SESSION["lab_rows"]}
    interp_set = {"WMT","AAPL","CALM"}
    exp_conf  = sorted(interp_set & lab_set)
    exp_interp= sorted(interp_set - lab_set)
    print(f"  INFO  Lab has {len(lab_set)} tickers | pipeline has WMT,AAPL,CALM")
    print(f"  INFO  Expected confirmed: {exp_conf}  interp_only: {exp_interp}")
    assert rec.get("confirmed_count") == len(exp_conf), \
        f"11.2.d: confirmed {rec.get('confirmed_count')} vs expected {len(exp_conf)}"
    assert rec.get("interp_only_count") == len(exp_interp), \
        f"11.2.d: interp_only {rec.get('interp_only_count')} vs expected {len(exp_interp)}"
    print(f"  PASS  11.2.d  confirmed={rec['confirmed_count']}  "
          f"lab_only={rec['lab_only_count']}  interp_only={rec['interp_only_count']}")

    # 11.2.e  LAB_NOT_CONFIRMED badge
    assert "LAB_NOT_CONFIRMED" in html, "11.2.e: badge missing"
    for t in exp_interp:
        assert t in html, f"11.2.e: {t} not in HTML"
    print(f"  PASS  11.2.e  interp_only {exp_interp} carry LAB_NOT_CONFIRMED badge")

    # 11.2.f  Run_ID / filename in HTML
    assert "20260521_212948" in html or "avshunter_signals" in html, "11.2.f: Run_ID missing"
    print(f"  PASS  11.2.f  Run_ID / lab filename present in HTML card")
finally:
    try: os.unlink(pipe_csv)
    except: pass

RESULTS["11.2"] = "PASS"
print()

# ═══════════════════════════════════════════════════════════
print("=" * 65)
print("SECTION 11.3 — Field Conflict Tests")
print("=" * 65)

_orig_scan = _cmd.scan_ma_inputs_for_ticker
_cmd.scan_ma_inputs_for_ticker = lambda t: {"charts":[],"screenshots":[],"options":[],"pipeline":[]}
_orig_bstp = _cmd.build_single_ticker_prompt
_current_fake[0] = _TICKER_FAKE

pipe_wmt = _pipeline_csv("WMT")
SESSION["last_pipeline_csv"] = pipe_wmt

# Ensure lab_rows loaded with original sample
if not SESSION.get("lab_rows"):
    _run(_cmd.cmd_lab)
SESSION["lab_reconciliation"] = {
    "confirmed":["WMT","CALM"],"lab_only":[],"interp_only":["AAPL"],
    "confirmed_count":2,"lab_only_count":99,"interp_only_count":1,
}

# 11.3.a  confirmed ticker → Lab context block injected
_cap = {"ctx":None,"conf":None}
def _mock(*a,**kw):
    _cap["ctx"]  = kw.get("lab_context_block","NOT_PASSED")
    _cap["conf"] = kw.get("lab_conflict_block","NOT_PASSED")
    return _orig_bstp(*a,**kw)
_cmd.build_single_ticker_prompt = _mock
out_wmt, crash_wmt, _ = _run(_cmd.cmd_ticker, "WMT")
_cmd.build_single_ticker_prompt = _orig_bstp

assert not crash_wmt, f"11.3.a crashed"
assert "[LAB]" in out_wmt, "11.3.a: [LAB] prefix missing"
assert ("Lab aligned" in out_wmt or "conflict" in out_wmt.lower()), "11.3.a: lab status line missing"
assert _cap["ctx"] and "LAB_CONTEXT_WMT" in _cap["ctx"], \
    f"11.3.a: lab_context_block wrong: {_cap['ctx']}"
assert _cap["conf"] and "LAB_FIELD_CONFLICTS_WMT" in _cap["conf"], \
    f"11.3.a: lab_conflict_block wrong: {_cap['conf']}"
print(f"  PASS  11.3.a  Confirmed ticker WMT: Lab context + conflict blocks injected")
print(f"         lab_context_block  -> {_cap['ctx'][:50]}...")
print(f"         lab_conflict_block -> {_cap['conf'][:55]}")

# 11.3.b  interp_only ticker → LAB_NOT_CONFIRMED
SESSION["lab_reconciliation"]["confirmed"]         = ["CALM"]
SESSION["lab_reconciliation"]["interp_only"]       = ["WMT","AAPL"]
SESSION["lab_reconciliation"]["confirmed_count"]   = 1
SESSION["lab_reconciliation"]["interp_only_count"] = 2
out_interp, crash_interp, _ = _run(_cmd.cmd_ticker, "WMT")
assert not crash_interp, "11.3.b crashed"
assert "LAB_NOT_CONFIRMED" in out_interp, f"11.3.b: missing:\n{out_interp}"
assert "Deep dive complete" in out_interp, "11.3.b: did not complete"
print(f"  PASS  11.3.b  Interp-only WMT: LAB_NOT_CONFIRMED shown, deep dive completes")
# Restore
SESSION["lab_reconciliation"]["confirmed"]         = ["WMT","CALM"]
SESSION["lab_reconciliation"]["interp_only"]       = ["AAPL"]
SESSION["lab_reconciliation"]["confirmed_count"]   = 2
SESSION["lab_reconciliation"]["interp_only_count"] = 1

# 11.3.c  Edit CSV Direction CALL (flip from PUT) → FLAG conflict
with open(SAMPLE, encoding="utf-8-sig", newline="") as f:
    reader = csv.DictReader(f)
    fieldnames = reader.fieldnames
    all_rows = list(reader)

orig_dir = next(r["Direction"] for r in all_rows if r["Ticker"]=="WMT")
assert orig_dir == "PUT", f"WMT Direction expected PUT, got {orig_dir}"

modified = MA_LAB / "avshunter_signals_CONFLICT_test.csv"
for r in all_rows:
    if r["Ticker"] == "WMT": r["Direction"] = "CALL"
with open(modified,"w",encoding="utf-8",newline="") as f:
    w = csv.DictWriter(f,fieldnames=fieldnames); w.writeheader(); w.writerows(all_rows)

orig_hidden = MA_LAB / "_ORIG_hidden.csv"
SAMPLE.rename(orig_hidden)

try:
    _clear_lab()
    _run(_cmd.cmd_lab)
    SESSION["lab_reconciliation"] = {
        "confirmed":["WMT","CALM"],"lab_only":[],"interp_only":["AAPL"],
        "confirmed_count":2,"lab_only_count":99,"interp_only_count":1,
    }

    _cap2 = {"ctx":None,"conf":None}
    def _mock2(*a,**kw):
        _cap2["ctx"]  = kw.get("lab_context_block","NOT_PASSED")
        _cap2["conf"] = kw.get("lab_conflict_block","NOT_PASSED")
        return _orig_bstp(*a,**kw)
    _cmd.build_single_ticker_prompt = _mock2
    out_flag, crash_flag, _ = _run(_cmd.cmd_ticker, "WMT")
    _cmd.build_single_ticker_prompt = _orig_bstp

    assert not crash_flag, f"11.3.c crashed"
    assert "conflict" in out_flag.lower(), f"11.3.c: no conflict in output"
    assert "FLAG" in out_flag, f"11.3.c: FLAG not reported"
    conf_blk = _cap2["conf"] or ""
    assert "Direction" in conf_blk, f"11.3.c: Direction not in conflict block: {conf_blk[:100]}"
    assert "FLAG" in conf_blk,      f"11.3.c: FLAG not in block: {conf_blk[:100]}"
    assert "CALL" in conf_blk,      f"11.3.c: CALL not in block: {conf_blk[:100]}"
    lab_line = [l for l in out_flag.split("\n") if "[LAB]" in l]
    print(f"  PASS  11.3.c  Direction FLAG conflict (CALL vs LONG_PUT) detected")
    print(f"         [LAB] line: {lab_line[0].strip() if lab_line else '(captured)'}")
    print(f"         conflict block: {conf_blk[:75]}...")
    print(f"  INFO  Restoring original sample CSV...")
finally:
    orig_hidden.rename(SAMPLE)
    modified.unlink(missing_ok=True)
    print(f"  INFO  Original sample CSV restored OK")

_cmd.scan_ma_inputs_for_ticker = _orig_scan
try: os.unlink(pipe_wmt)
except: pass

RESULTS["11.3"] = "PASS"
print()

# ═══════════════════════════════════════════════════════════
print("=" * 65)
print("SECTION 11.4 — Regression Tests")
print("=" * 65)
_current_fake[0] = _TRIAGE_FAKE

# 11.4.a  /triage WITHOUT lab file → WARN, completes
orig_a = MA_LAB / "_ORIG_11_4_a.csv"
SAMPLE.rename(orig_a)
_clear_lab()
try:
    out_t_nolab, crash_t_nolab, _ = _run(_cmd.cmd_triage)
    assert not crash_t_nolab, "11.4.a crashed"
    assert "No lab export" in out_t_nolab, "11.4.a: WARN missing"
    assert "Triage complete" in out_t_nolab, "11.4.a: triage did not complete"
    html_nolab = _latest_html("triage_*.html")
    assert "LAB_NOT_LOADED" in html_nolab, "11.4.a: LAB_NOT_LOADED missing from HTML"
    print(f"  PASS  11.4.a  /triage without lab file: WARN shown, completes normally")
    print(f"                HTML contains LAB_NOT_LOADED card")
finally:
    orig_a.rename(SAMPLE)

# 11.4.b  /ticker WITHOUT lab loaded → LAB_NOT_LOADED
_clear_lab()
_cmd.scan_ma_inputs_for_ticker = lambda t: {"charts":[],"screenshots":[],"options":[],"pipeline":[]}
pipe_b = _pipeline_csv("WMT")
SESSION["last_pipeline_csv"] = pipe_b
_current_fake[0] = _TICKER_FAKE
out_t_nolab2, crash_t_nolab2, _ = _run(_cmd.cmd_ticker, "WMT")
_cmd.scan_ma_inputs_for_ticker = _orig_scan
try: os.unlink(pipe_b)
except: pass

assert not crash_t_nolab2,               "11.4.b crashed"
assert "LAB_NOT_LOADED" in out_t_nolab2, "11.4.b: LAB_NOT_LOADED missing"
assert "Deep dive complete" in out_t_nolab2, "11.4.b: did not complete"
print(f"  PASS  11.4.b  /ticker without lab: LAB_NOT_LOADED shown, output unchanged")

# 11.4.c  /lab with no file → WARN, no crash
orig_c = MA_LAB / "_ORIG_11_4_c.csv"
SAMPLE.rename(orig_c)
_clear_lab()
try:
    out_lab_nofile, crash_lab_nofile, _ = _run(_cmd.cmd_lab)
    assert not crash_lab_nofile,                "11.4.c crashed"
    assert "No lab export found" in out_lab_nofile, "11.4.c: WARN missing"
    assert "avshunter_signals" in out_lab_nofile,   "11.4.c: file hint missing"
    print(f"  PASS  11.4.c  /lab with no file: helpful WARN, no crash")
finally:
    orig_c.rename(SAMPLE)

# 11.4.d  All existing functions intact
from pipeline_interpreter_commands import (
    cmd_triage, cmd_ticker, cmd_intraday, cmd_brief, cmd_note, route_command, MENU
)
from pipeline_interpreter_outputs import write_all_outputs, write_triage_outputs, build_html
from interpreter_qa import REQUIRED_SECTIONS, check_triage_qa, check_ticker_qa

import inspect
sig = inspect.signature(_out.build_triage_html)
sig2 = inspect.signature(_out.write_triage_outputs)
assert "lab_reconciliation" in sig.parameters,  "build_triage_html missing lab param"
assert "lab_reconciliation" in sig2.parameters, "write_triage_outputs missing lab param"
assert sig.parameters["lab_reconciliation"].default is None, "lab param default wrong"
assert REQUIRED_SECTIONS[0] == "MARKET PREDICTION AND FAILURE POINT"
assert len(REQUIRED_SECTIONS) == 17
assert callable(check_triage_qa) and callable(check_ticker_qa)
assert "/lab" in MENU,    "/lab missing from MENU"
assert "/triage" in MENU, "/triage missing from MENU"
assert "/ticker" in MENU, "/ticker missing from MENU"
print(f"  PASS  11.4.d  All existing functions, constants, and MENU entries intact")
print(f"                REQUIRED_SECTIONS: {len(REQUIRED_SECTIONS)} (unchanged)")
print(f"                Lab params have default=None (backward compatible)")

RESULTS["11.4"] = "PASS"
print()

# ═══════════════════════════════════════════════════════════
print("=" * 65)
print("SECTION 11 — FINAL SUMMARY")
print("=" * 65)
all_pass = all(v == "PASS" for v in sorted(RESULTS.items()))
for section, result in sorted(RESULTS.items()):
    print(f"  {result}  Section {section}")
print()
if all(v == "PASS" for v in RESULTS.values()):
    print("ALL SECTION 11 TESTS PASS")
    print("Component 9 build verified complete.")
else:
    failed = [s for s,r in RESULTS.items() if r != "PASS"]
    print(f"FAIL — sections still failing: {failed}")
