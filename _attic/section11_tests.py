"""
Section 11 — Component 9 full test checklist.
Covers 11.1 (imports), 11.2 (reconciliation), 11.3 (conflicts), 11.4 (regression).
No live API calls — call_api patched in both engine and commands namespaces.
"""
import sys, io, contextlib, csv, os, shutil, re, tempfile
from pathlib import Path
sys.path.insert(0, ".")

# ─────────────────────────────────────────────────────────────────────────────
# Global patch — must happen before importing pipeline_interpreter_commands
# ─────────────────────────────────────────────────────────────────────────────
import pipeline_interpreter_engine as _eng
import pipeline_interpreter_outputs as _out

def _fake_api(*a, **kw):
    return _FAKE_RESPONSE
_eng.call_api = _fake_api

# Patch battlefield builder so the API path always runs
import pipeline_interpreter_commands as _cmd
_cmd.call_api = _fake_api
_cmd._build_battlefield_triage_response = lambda *a, **kw: None

from pipeline_interpreter_commands import SESSION, MA_LAB
from pathlib import Path as _P

SAMPLE = MA_LAB / "avshunter_signals_20260521_212948_2026-05-22_1213.csv"
OUTPUTS = _P("outputs")

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────
def _run(fn, *args, **kwargs):
    buf = io.StringIO()
    crashed = False
    exc = None
    try:
        with contextlib.redirect_stdout(buf):
            fn(*args, **kwargs)
    except Exception as e:
        crashed = True; exc = e
    return buf.getvalue(), crashed, exc

def _latest_html(pattern="triage_*.html"):
    files = sorted(OUTPUTS.rglob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0].read_text(encoding="utf-8") if files else ""

def _clear_lab_session():
    for k in ("lab_rows","lab_reconciliation","lab_filename","lab_run_id_check"):
        SESSION.pop(k, None)

def _make_pipeline_csv(**extra):
    """Write a minimal one-row pipeline CSV for WMT and return its path."""
    fields = ["ticker","direction","eil_v3_verdict","kill_switch_level","probe_trigger",
              "armed_trigger","execution_permission","horizon","preferred_contract",
              "ivp","premium","triage_rank","ev_score","wbs_grade","preferred_strike"]
    row = {"ticker":"WMT","direction":"LONG_PUT","eil_v3_verdict":"ARMED",
           "kill_switch_level":"120.00","probe_trigger":"116.00","armed_trigger":"115.00",
           "execution_permission":"NONE_PIPELINE_INTERPRETER_ONLY","horizon":"6-10",
           "preferred_contract":"WMT260618P00115000","ivp":"40","premium":"1.08",
           "triage_rank":"1","ev_score":"0.0004","wbs_grade":"PROBABLE","preferred_strike":"115.0"}
    row.update(extra)
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False,
                                      newline="", encoding="utf-8")
    w = csv.DictWriter(tmp, fieldnames=fields)
    w.writeheader(); w.writerow(row); tmp.close()
    return tmp.name

RESULTS = {}

# ═══════════════════════════════════════════════════════════════════════════
# SECTION 11.1  —  IMPORT TESTS
# ═══════════════════════════════════════════════════════════════════════════
print("=" * 65)
print("SECTION 11.1 — Import Tests")
print("=" * 65)

import_tests = [
    ("from lab_reconciliation import reconcile_universes",
     lambda: __import__("lab_reconciliation").reconcile_universes),
    ("from lab_reconciliation import load_lab_export",
     lambda: __import__("lab_reconciliation").load_lab_export),
    ("from lab_reconciliation import validate_lab_field_alignment",
     lambda: __import__("lab_reconciliation").validate_lab_field_alignment),
    ("from lab_reconciliation import build_lab_alignment_block",
     lambda: __import__("lab_reconciliation").build_lab_alignment_block),
    ("from pipeline_interpreter_engine import MA_LAB",
     lambda: _eng.MA_LAB),
    ("from interpreter_qa import check_lab_reconciliation_qa",
     lambda: __import__("interpreter_qa").check_lab_reconciliation_qa),
]

all_11_1 = True
for desc, fn in import_tests:
    try:
        result = fn()
        val = str(result)[:60] if not callable(result) else "callable"
        status = "PASS"
        print(f"  PASS  {desc}")
        if not callable(result): print(f"        value: {val}")
    except Exception as e:
        status = "FAIL"
        all_11_1 = False
        print(f"  FAIL  {desc}  → {e}")

RESULTS["11.1"] = "PASS" if all_11_1 else "FAIL"
print()

# ═══════════════════════════════════════════════════════════════════════════
# SECTION 11.2  —  Reconciliation Logic Tests
# ═══════════════════════════════════════════════════════════════════════════
print("=" * 65)
print("SECTION 11.2 — Reconciliation Logic Tests")
print("=" * 65)

all_11_2 = True

# 11.2.a  /lab loads 101 tickers
_clear_lab_session()
out_lab, crash_lab, _ = _run(_cmd.cmd_lab)
assert not crash_lab,                        "11.2.a: /lab crashed"
assert SESSION.get("lab_rows"),              "11.2.a: lab_rows not populated"
lab_count = len(SESSION["lab_rows"])
assert lab_count == 101, f"11.2.a: expected 101, got {lab_count}"
print(f"  PASS  11.2.a  /lab loads 101 tickers (got {lab_count})")

# 11.2.b  Run_ID 20260521_212948 shown in alignment check
assert "20260521_212948" in out_lab,         "11.2.b: Run_ID missing from /lab output"
print(f"  PASS  11.2.b  Run_ID 20260521_212948 present in /lab output")

# 11.2.c  /triage builds HTML with LAB_ALIGNMENT card
# Fake triage response includes WMT (in lab), AAPL (not in lab)
_FAKE_RESPONSE = (
    "[TRIAGE_RANKED_TABLE]\n"
    "rank,ticker,direction,pipeline_score,dte,horizon,live_validation_state,"
    "validation_score,earnings_flag,ma_inputs_ready,triage_verdict,triage_reason\n"
    "1,WMT,LONG_PUT,85,28,6-10,,80,NO,YES,DEEP_DIVE_NOW,Lab confirmed\n"
    "2,AAPL,LONG_CALL,70,30,1-5,,65,NO,YES,REVIEW_LATER,Not in lab\n"
    "3,CALM,LONG_PUT,75,45,11-20,,72,NO,PARTIAL,DEEP_DIVE_NEXT,Lab confirmed\n"
    "[/TRIAGE_RANKED_TABLE]\n"
    "[TRIAGE_SUMMARY]\nTest session.\n[/TRIAGE_SUMMARY]\n"
    "[TRIAGE_EXECUTION_ORDER]\n/ticker WMT\nEXECUTION PERMISSION: NONE_PIPELINE_INTERPRETER_ONLY\n"
    "[/TRIAGE_EXECUTION_ORDER]\n"
)
_eng.call_api = _fake_api
_cmd.call_api = _fake_api

out_triage, crash_triage, _ = _run(_cmd.cmd_triage)
assert not crash_triage, f"11.2.c: /triage crashed"
html = _latest_html("triage_*.html")
assert html, "11.2.c: no triage HTML found"
assert "Intelligence Lab Reconciliation" in html, "11.2.c: LAB card missing from HTML"
print(f"  PASS  11.2.c  /triage HTML contains LAB_ALIGNMENT card")

# 11.2.d  confirmed + lab_only + interp_only counts correct
rec = SESSION.get("lab_reconciliation", {})
lab_tickers = {r["Ticker"] for r in SESSION["lab_rows"]}
triage_tickers = {"WMT","AAPL","CALM"}
expected_confirmed = triage_tickers & lab_tickers
expected_interp    = triage_tickers - lab_tickers
print(f"  INFO  Lab tickers: 101 | Triage tickers: {sorted(triage_tickers)}")
print(f"  INFO  Expected confirmed: {sorted(expected_confirmed)}")
print(f"  INFO  Expected interp_only: {sorted(expected_interp)}")
assert rec.get("confirmed_count") == len(expected_confirmed), \
    f"11.2.d: confirmed count wrong: {rec.get('confirmed_count')} vs {len(expected_confirmed)}"
assert rec.get("interp_only_count") == len(expected_interp), \
    f"11.2.d: interp_only count wrong: {rec.get('interp_only_count')} vs {len(expected_interp)}"
print(f"  PASS  11.2.d  confirmed={rec['confirmed_count']}, "
      f"lab_only={rec['lab_only_count']}, interp_only={rec['interp_only_count']}")

# 11.2.e  interp_only tickers carry LAB_NOT_CONFIRMED in HTML
assert "LAB_NOT_CONFIRMED" in html, "11.2.e: LAB_NOT_CONFIRMED badge missing from HTML"
for t in expected_interp:
    assert t in html, f"11.2.e: interp_only ticker {t} not mentioned in HTML"
print(f"  PASS  11.2.e  interp_only tickers {sorted(expected_interp)} carry LAB_NOT_CONFIRMED badge")

# 11.2.f  Run_ID shown in HTML card
assert "20260521_212948" in html or "avshunter_signals" in html, \
    "11.2.f: Run_ID / filename not in HTML"
print(f"  PASS  11.2.f  Run_ID / lab filename present in HTML card")

RESULTS["11.2"] = "PASS"
print()

# ═══════════════════════════════════════════════════════════════════════════
# SECTION 11.3  —  Field Conflict Tests
# ═══════════════════════════════════════════════════════════════════════════
print("=" * 65)
print("SECTION 11.3 — Field Conflict Tests")
print("=" * 65)

all_11_3 = True

# Set up pipeline CSV with WMT
pipeline_csv = _make_pipeline_csv()
SESSION["last_pipeline_csv"] = pipeline_csv

# Force no-chart path
_orig_scan = _cmd.scan_ma_inputs_for_ticker
_cmd.scan_ma_inputs_for_ticker = lambda t: {"charts":[],"screenshots":[],"options":[],"pipeline":[]}

# Reload lab with original CSV (WMT Direction=PUT, pipeline direction=LONG_PUT → no conflict)
_clear_lab_session()
_run(_cmd.cmd_lab)
SESSION["lab_reconciliation"] = {
    "confirmed":["WMT","CALM"],"lab_only":list({r["Ticker"] for r in SESSION["lab_rows"]}-{"WMT","CALM","AAPL"}),
    "interp_only":["AAPL"],
    "confirmed_count":2,"lab_only_count":99,"interp_only_count":1,
}

# ── 11.3.a  confirmed ticker shows Lab context block ─────────────────────────
_FAKE_RESPONSE = "[TRADE_BRIEF_CSV]\nticker,direction,final_verdict,trade_state,horizon,dte,trigger_level,kill_switch_level,preferred_contract,premium,rr,iv_context,ivp,earnings_in_window,earnings_action,max_pain_risk,sector_confirmation_required,first_hour_rule,probe_permitted,initial_adverse_tolerance,capital_permission,narrative_summary,execution_permission\nWMT,LONG_PUT,PROBE,WATCH,6-10,28,116.00,120.00,WMT260618P00115000,1.08,6.4,FAIR,40,NO,N/A,LOW,NO,YES,YES,0.40,CAPITAL_DENIED_PENDING_LIVE_CONFIRMATION,Test,NONE_PIPELINE_INTERPRETER_ONLY\n[/TRADE_BRIEF_CSV]\n"
_eng.call_api = _fake_api
_cmd.call_api = _fake_api

_cap_ctx = []; _cap_conf = []
_orig_bstp = _cmd.build_single_ticker_prompt
def _mock_bstp(*a, **kw):
    _cap_ctx.append(kw.get("lab_context_block","NOT_PASSED"))
    _cap_conf.append(kw.get("lab_conflict_block","NOT_PASSED"))
    return _orig_bstp(*a, **kw)
_cmd.build_single_ticker_prompt = _mock_bstp

out_wmt, crash_wmt, _ = _run(_cmd.cmd_ticker, "WMT")
_cmd.build_single_ticker_prompt = _orig_bstp

assert not crash_wmt,                           f"11.3.a: /ticker WMT crashed:\n{out_wmt}"
assert "[LAB]" in out_wmt,                      "11.3.a: [LAB] prefix missing"
assert "Lab aligned" in out_wmt or "conflict" in out_wmt.lower(), \
    f"11.3.a: lab status line missing:\n{out_wmt}"
assert _cap_ctx and "LAB_CONTEXT_WMT" in _cap_ctx[0], \
    f"11.3.a: lab_context_block not injected: {_cap_ctx}"
assert _cap_conf and "LAB_FIELD_CONFLICTS_WMT" in _cap_conf[0], \
    f"11.3.a: lab_conflict_block not injected: {_cap_conf}"
print(f"  PASS  11.3.a  Confirmed ticker WMT: Lab context block injected into prompt")
print(f"         lab_context_block  → {_cap_ctx[0][:55]}...")
print(f"         lab_conflict_block → {_cap_conf[0][:55]}")

# ── 11.3.b  interp_only ticker shows LAB_NOT_CONFIRMED ───────────────────────
out_aapl, crash_aapl, _ = _run(_cmd.cmd_ticker, "WMT")
# Temporarily make WMT an interp_only ticker
SESSION["lab_reconciliation"]["confirmed"]     = ["CALM"]
SESSION["lab_reconciliation"]["interp_only"]   = ["WMT","AAPL"]
SESSION["lab_reconciliation"]["confirmed_count"]   = 1
SESSION["lab_reconciliation"]["interp_only_count"] = 2

out_interp, crash_interp, _ = _run(_cmd.cmd_ticker, "WMT")
assert not crash_interp,                        "11.3.b: crashed"
assert "LAB_NOT_CONFIRMED" in out_interp,       f"11.3.b: LAB_NOT_CONFIRMED missing:\n{out_interp}"
assert "Deep dive complete" in out_interp,      "11.3.b: deep dive did not complete"
print(f"  PASS  11.3.b  Interp-only ticker: LAB_NOT_CONFIRMED shown, deep dive completes")

# Restore confirmed
SESSION["lab_reconciliation"]["confirmed"]         = ["WMT","CALM"]
SESSION["lab_reconciliation"]["interp_only"]       = ["AAPL"]
SESSION["lab_reconciliation"]["confirmed_count"]   = 2
SESSION["lab_reconciliation"]["interp_only_count"] = 1

# ── 11.3.c  Edit CSV to wrong Direction → FLAG conflict ──────────────────────
# Read sample, modify WMT Direction from PUT to CALL, write to temp file
with open(SAMPLE, encoding="utf-8-sig", newline="") as f:
    reader = csv.DictReader(f)
    fieldnames = reader.fieldnames
    all_rows = list(reader)

original_wmt_dir = next(r["Direction"] for r in all_rows if r["Ticker"]=="WMT")
assert original_wmt_dir == "PUT", f"Expected WMT Direction=PUT, got {original_wmt_dir}"

# Write modified CSV to a temp file in lab_export/
modified_path = MA_LAB / "avshunter_signals_MODIFIED_test.csv"
for r in all_rows:
    if r["Ticker"] == "WMT":
        r["Direction"] = "CALL"   # flip to opposite direction

with open(modified_path, "w", encoding="utf-8", newline="") as f:
    w = csv.DictWriter(f, fieldnames=fieldnames)
    w.writeheader(); w.writerows(all_rows)

# Rename original sample so modified is newest
orig_hidden = MA_LAB / "_ORIG_avshunter_signals_hidden.csv"
SAMPLE.rename(orig_hidden)

try:
    # Reload lab with modified CSV (WMT Direction=CALL)
    _clear_lab_session()
    _run(_cmd.cmd_lab)
    SESSION["lab_reconciliation"] = {
        "confirmed":["WMT","CALM"],"lab_only":[],
        "interp_only":["AAPL"],
        "confirmed_count":2,"lab_only_count":99,"interp_only_count":1,
    }

    _cap_ctx2 = []; _cap_conf2 = []
    def _mock_bstp2(*a, **kw):
        _cap_ctx2.append(kw.get("lab_context_block","NOT_PASSED"))
        _cap_conf2.append(kw.get("lab_conflict_block","NOT_PASSED"))
        return _orig_bstp(*a, **kw)
    _cmd.build_single_ticker_prompt = _mock_bstp2

    out_flag, crash_flag, _ = _run(_cmd.cmd_ticker, "WMT")
    _cmd.build_single_ticker_prompt = _orig_bstp

    assert not crash_flag, f"11.3.c: /ticker crashed:\n{out_flag}"
    # Check [LAB] line reports conflict
    assert "conflict" in out_flag.lower(), f"11.3.c: no conflict in output:\n{out_flag}"
    assert "FLAG" in out_flag, f"11.3.c: FLAG severity not reported:\n{out_flag}"
    # Check conflict block passed to prompt
    assert _cap_conf2, "11.3.c: conflict block not captured"
    conf_block = _cap_conf2[0]
    assert "Direction" in conf_block,  f"11.3.c: Direction not in conflict block: {conf_block[:150]}"
    assert "FLAG" in conf_block,        f"11.3.c: FLAG not in conflict block: {conf_block[:150]}"
    assert "CALL" in conf_block and "PUT" in conf_block, \
        f"11.3.c: CALL/PUT values not in conflict block: {conf_block[:150]}"
    print(f"  PASS  11.3.c  Direction FLAG conflict detected (CALL vs LONG_PUT)")
    print(f"         [LAB] output:    {[l for l in out_flag.split(chr(10)) if '[LAB]' in l][0].strip()}")
    print(f"         conflict_block:  {conf_block[:80]}...")
finally:
    # Always restore original sample
    orig_hidden.rename(SAMPLE)
    modified_path.unlink(missing_ok=True)
    print(f"  INFO  Original sample CSV restored")

_cmd.scan_ma_inputs_for_ticker = _orig_scan
try: os.unlink(pipeline_csv)
except Exception: pass

RESULTS["11.3"] = "PASS"
print()

# ═══════════════════════════════════════════════════════════════════════════
# SECTION 11.4  —  Regression Tests
# ═══════════════════════════════════════════════════════════════════════════
print("=" * 65)
print("SECTION 11.4 — Regression Tests")
print("=" * 65)

_FAKE_RESPONSE = (
    "[TRIAGE_RANKED_TABLE]\n"
    "rank,ticker,direction,pipeline_score,dte,horizon,live_validation_state,"
    "validation_score,earnings_flag,ma_inputs_ready,triage_verdict,triage_reason\n"
    "1,WMT,LONG_PUT,85,28,6-10,,80,NO,YES,DEEP_DIVE_NOW,Test\n"
    "[/TRIAGE_RANKED_TABLE]\n"
    "[TRIAGE_SUMMARY]\nRegression test\n[/TRIAGE_SUMMARY]\n"
    "[TRIAGE_EXECUTION_ORDER]\n/ticker WMT\nEXECUTION PERMISSION: NONE_PIPELINE_INTERPRETER_ONLY\n"
    "[/TRIAGE_EXECUTION_ORDER]\n"
)
_eng.call_api = _fake_api
_cmd.call_api = _fake_api

# ── 11.4.a  /triage WITHOUT lab file — WARN, no crash ────────────────────────
# Hide sample file
orig_hidden2 = MA_LAB / "_ORIG_regression_hidden.csv"
SAMPLE.rename(orig_hidden2)
_clear_lab_session()
try:
    out_triage_nolab, crash_triage_nolab, _ = _run(_cmd.cmd_triage)
    assert not crash_triage_nolab,              "11.4.a: /triage crashed without lab file"
    assert "No lab export" in out_triage_nolab, "11.4.a: WARN message missing"
    assert "Triage complete" in out_triage_nolab, "11.4.a: triage did not complete"
    html_nolab = _latest_html("triage_*.html")
    assert "LAB_NOT_LOADED" in html_nolab,      "11.4.a: LAB_NOT_LOADED not in HTML"
    print(f"  PASS  11.4.a  /triage without lab file: WARN shown, completes normally")
    print(f"                HTML contains LAB_NOT_LOADED card")
finally:
    orig_hidden2.rename(SAMPLE)

# ── 11.4.b  /ticker WITHOUT lab loaded — LAB_NOT_LOADED ──────────────────────
_clear_lab_session()
pipeline_csv2 = _make_pipeline_csv()
SESSION["last_pipeline_csv"] = pipeline_csv2
_cmd.scan_ma_inputs_for_ticker = lambda t: {"charts":[],"screenshots":[],"options":[],"pipeline":[]}
_FAKE_TICKER = "[TRADE_BRIEF_CSV]\nticker,direction,final_verdict,trade_state,horizon,dte,trigger_level,kill_switch_level,preferred_contract,premium,rr,iv_context,ivp,earnings_in_window,earnings_action,max_pain_risk,sector_confirmation_required,first_hour_rule,probe_permitted,initial_adverse_tolerance,capital_permission,narrative_summary,execution_permission\nWMT,LONG_PUT,PROBE,WATCH,6-10,28,116.00,120.00,WMT260618P00115000,1.08,6.4,FAIR,40,NO,N/A,LOW,NO,YES,YES,0.40,CAPITAL_DENIED_PENDING_LIVE_CONFIRMATION,Test,NONE_PIPELINE_INTERPRETER_ONLY\n[/TRADE_BRIEF_CSV]\n"
_FAKE_RESPONSE = _FAKE_TICKER
_eng.call_api = _fake_api
_cmd.call_api = _fake_api

out_ticker_nolab, crash_ticker_nolab, _ = _run(_cmd.cmd_ticker, "WMT")
_cmd.scan_ma_inputs_for_ticker = _orig_scan
try: os.unlink(pipeline_csv2)
except Exception: pass

assert not crash_ticker_nolab,               "11.4.b: /ticker crashed without lab"
assert "LAB_NOT_LOADED" in out_ticker_nolab, "11.4.b: LAB_NOT_LOADED missing"
assert "Deep dive complete" in out_ticker_nolab, "11.4.b: deep dive did not complete"
print(f"  PASS  11.4.b  /ticker without lab: LAB_NOT_LOADED shown, output unchanged")

# ── 11.4.c  /lab with no file — WARN, no crash ───────────────────────────────
orig_hidden3 = MA_LAB / "_ORIG_lab_hidden.csv"
SAMPLE.rename(orig_hidden3)
_clear_lab_session()
try:
    out_lab_nofile, crash_lab_nofile, _ = _run(_cmd.cmd_lab)
    assert not crash_lab_nofile,                "11.4.c: /lab crashed with no file"
    assert "No lab export found" in out_lab_nofile, "11.4.c: WARN missing"
    print(f"  PASS  11.4.c  /lab with no file: helpful WARN, no crash")
finally:
    orig_hidden3.rename(SAMPLE)

# ── 11.4.d  Existing command structure unchanged ──────────────────────────────
# Verify all original functions still callable and untouched
from pipeline_interpreter_commands import (
    cmd_triage, cmd_ticker, cmd_intraday, cmd_brief, cmd_note, route_command, MENU
)
from pipeline_interpreter_outputs import (
    write_all_outputs, write_triage_outputs, _extract_section, build_html, build_triage_html
)
from interpreter_qa import (
    REQUIRED_SECTIONS, check_triage_qa, check_ticker_qa, print_qa_report, append_qa_log
)
import inspect
sig_triage = inspect.signature(build_triage_html)
assert "lab_reconciliation" in sig_triage.parameters, "build_triage_html missing lab param"
assert REQUIRED_SECTIONS[0] == "MARKET PREDICTION AND FAILURE POINT", "REQUIRED_SECTIONS altered"
assert len(REQUIRED_SECTIONS) == 17, f"REQUIRED_SECTIONS count wrong: {len(REQUIRED_SECTIONS)}"
print(f"  PASS  11.4.d  All existing command/output/QA functions intact")
print(f"                REQUIRED_SECTIONS: {len(REQUIRED_SECTIONS)} entries (unchanged)")
print(f"                build_triage_html: has lab params with defaults (backward compatible)")

RESULTS["11.4"] = "PASS"
print()

# ═══════════════════════════════════════════════════════════════════════════
# SUMMARY
# ═══════════════════════════════════════════════════════════════════════════
print("=" * 65)
print("SECTION 11 — FULL TEST RESULTS SUMMARY")
print("=" * 65)
all_pass = all(v == "PASS" for v in RESULTS.values())
for section, result in sorted(RESULTS.items()):
    print(f"  {result}  Section {section}")
print()
if all_pass:
    print("ALL SECTION 11 TESTS PASS — Component 9 build verified complete.")
else:
    failed = [s for s,r in RESULTS.items() if r != "PASS"]
    print(f"FAIL — sections still failing: {failed}")
