"""
Step 6 test: lab context injection in cmd_ticker().
Tests both the no-lab (LAB_NOT_LOADED) and with-lab paths without live API calls.
"""
import sys, io, contextlib, types
sys.path.insert(0, ".")

# ── Patch API before any import of commands ───────────────────────────────────
import pipeline_interpreter_engine as _eng
_FAKE_RESPONSE = (
    "[TRADE_NARRATIVE_WFC]\nTest narrative\n[/TRADE_NARRATIVE_WFC]\n"
    "[TRADE_BRIEF_CSV]\nticker,direction,final_verdict,trade_state,horizon,dte,"
    "trigger_level,kill_switch_level,preferred_contract,premium,rr,iv_context,"
    "ivp,earnings_in_window,earnings_action,max_pain_risk,"
    "sector_confirmation_required,first_hour_rule,probe_permitted,"
    "initial_adverse_tolerance,capital_permission,narrative_summary,"
    "execution_permission\n"
    "WFC,LONG_PUT,PROBE,WATCH,11-20,45,75.00,77.50,WFC260618P00075000,"
    "1.20,2.5,ELEVATED,55,NO,N/A,LOW,NO,YES,YES,0.50,"
    "CAPITAL_DENIED_PENDING_LIVE_CONFIRMATION,Test summary,"
    "NONE_PIPELINE_INTERPRETER_ONLY\n"
    "[/TRADE_BRIEF_CSV]\n"
)
_eng.call_api = lambda *a, **kw: _FAKE_RESPONSE

import pipeline_interpreter_commands as _cmd
from pipeline_interpreter_commands import SESSION

# Give SESSION a valid pipeline CSV path so cmd_ticker can load rows
import csv, tempfile, os
from pathlib import Path

# Write a minimal synthetic pipeline CSV
_tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, newline="",
                                   encoding="utf-8")
_writer = csv.DictWriter(_tmp, fieldnames=["ticker","direction","eil_v3_verdict",
    "kill_switch_level","probe_trigger","armed_trigger","execution_permission",
    "horizon","preferred_contract","ivp","premium"])
_writer.writeheader()
_writer.writerow({"ticker":"WFC","direction":"LONG_PUT","eil_v3_verdict":"ARMED",
    "kill_switch_level":"77.50","probe_trigger":"75.00","armed_trigger":"74.00",
    "execution_permission":"NONE_PIPELINE_INTERPRETER_ONLY","horizon":"11-20",
    "preferred_contract":"WFC260618P00075000","ivp":"55","premium":"1.20"})
_tmp.close()
SESSION["last_pipeline_csv"] = _tmp.name

errors = []

# ══════════════════════════════════════════════════════════════════════════════
# TEST A — No lab file loaded (SESSION["lab_rows"] is empty / absent)
# ══════════════════════════════════════════════════════════════════════════════
SESSION.pop("lab_rows", None)
SESSION.pop("lab_reconciliation", None)

buf = io.StringIO()
crashed = False
try:
    with contextlib.redirect_stdout(buf):
        _cmd.cmd_ticker("WFC")
except Exception as e:
    crashed = True
    buf.write(f"CRASH: {type(e).__name__}: {e}\n")

out_a = buf.getvalue()
print("=== TEST A: No lab loaded ===")
for line in out_a.split("\n"):
    if line.strip(): print(" ", line)
print()

assert not crashed,                              "TEST A crashed — FAIL"
assert "LAB_NOT_LOADED" in out_a,               "LAB_NOT_LOADED not printed — FAIL"
assert "[LAB]" in out_a,                        "[LAB] prefix missing — FAIL"
assert "Deep dive complete" in out_a,           "Deep dive did not complete — FAIL"
assert "LAB_CONTEXT" not in out_a,              "Lab context block leaked into prompt output — FAIL"
print("TEST A — No lab loaded:         PASS")
print("  LAB_NOT_LOADED printed:       YES")
print("  No crash:                     YES")
print("  Deep dive completed:          YES")
print()

# ══════════════════════════════════════════════════════════════════════════════
# TEST B — Lab loaded, ticker CONFIRMED, no field conflicts
# ══════════════════════════════════════════════════════════════════════════════
SESSION["lab_rows"] = [
    {"Ticker":"WFC","Run_ID":"20260521_212948",
     "Direction":"LONG_PUT","Verdict":"ARMED","IVP":"55","Strike":"75",
     "EV":"0.72","WBS_Grade":"A","Priority_Rank":"3","Premium_Mid":"1.20"},
]
SESSION["lab_reconciliation"] = {
    "confirmed": ["WFC"], "lab_only": [], "interp_only": [],
    "confirmed_count": 1, "lab_only_count": 0, "interp_only_count": 0,
}
SESSION["lab_filename"] = "avshunter_signals_20260521_212948_test.csv"

# Capture what gets passed into build_single_ticker_prompt
_captured_lab_ctx = []
_captured_lab_conf = []
_orig_bstp = _eng.build_single_ticker_prompt
def _mock_bstp(*a, **kw):
    _captured_lab_ctx.append(kw.get("lab_context_block", "NOT_PASSED"))
    _captured_lab_conf.append(kw.get("lab_conflict_block", "NOT_PASSED"))
    return _orig_bstp(*a, **kw)
_eng.build_single_ticker_prompt = _mock_bstp

buf2 = io.StringIO()
crashed2 = False
try:
    with contextlib.redirect_stdout(buf2):
        _cmd.cmd_ticker("WFC")
except Exception as e:
    crashed2 = True
    buf2.write(f"CRASH: {type(e).__name__}: {e}\n")

_eng.build_single_ticker_prompt = _orig_bstp  # restore
out_b = buf2.getvalue()
print("=== TEST B: Lab loaded, WFC confirmed, no conflicts ===")
for line in out_b.split("\n"):
    if line.strip(): print(" ", line)
print()

assert not crashed2,                            "TEST B crashed — FAIL"
assert "Lab aligned" in out_b,                  "Lab aligned message missing — FAIL"
assert "LAB_NOT_CONFIRMED" not in out_b,        "False LAB_NOT_CONFIRMED — FAIL"
assert _captured_lab_ctx,                       "lab_context_block not passed to prompt builder"
assert "LAB_CONTEXT_WFC" in _captured_lab_ctx[0], \
    f"Lab context wrong: {_captured_lab_ctx[0][:80]}"
assert "NONE" in _captured_lab_conf[0],         f"Conflict block wrong: {_captured_lab_conf[0][:80]}"
print("TEST B — Confirmed, no conflicts:  PASS")
print(f"  lab_context_block passed:      YES ({_captured_lab_ctx[0][:40]}...)")
print(f"  lab_conflict_block passed:     YES ({_captured_lab_conf[0][:40]})")
print()

# ══════════════════════════════════════════════════════════════════════════════
# TEST C — Lab loaded, ticker NOT confirmed (interp_only)
# ══════════════════════════════════════════════════════════════════════════════
SESSION["lab_rows"] = [
    {"Ticker":"SPY","Run_ID":"20260521_212948","Direction":"LONG_CALL"},
]
SESSION["lab_reconciliation"] = {
    "confirmed": ["SPY"], "lab_only": [], "interp_only": ["WFC"],
    "confirmed_count": 1, "lab_only_count": 0, "interp_only_count": 1,
}

buf3 = io.StringIO()
crashed3 = False
try:
    with contextlib.redirect_stdout(buf3):
        _cmd.cmd_ticker("WFC")
except Exception as e:
    crashed3 = True
    buf3.write(f"CRASH: {type(e).__name__}: {e}\n")

out_c = buf3.getvalue()
print("=== TEST C: WFC not in Lab (interp_only) ===")
for line in out_c.split("\n"):
    if line.strip(): print(" ", line)
print()

assert not crashed3,                            "TEST C crashed — FAIL"
assert "LAB_NOT_CONFIRMED" in out_c,            "LAB_NOT_CONFIRMED missing — FAIL"
assert "Deep dive complete" in out_c,           "Deep dive did not complete — FAIL"
print("TEST C — LAB_NOT_CONFIRMED:        PASS")
print()

# ══════════════════════════════════════════════════════════════════════════════
# TEST D — Lab loaded, ticker confirmed, FLAG-level conflict
# ══════════════════════════════════════════════════════════════════════════════
SESSION["lab_rows"] = [
    {"Ticker":"WFC","Run_ID":"20260521_212948",
     "Direction":"LONG_CALL",          # conflicts with pipeline LONG_PUT → FLAG
     "Verdict":"ARMED","IVP":"55","Strike":"75",
     "EV":"0.72","WBS_Grade":"A","Priority_Rank":"3","Premium_Mid":"1.20"},
]
SESSION["lab_reconciliation"] = {
    "confirmed": ["WFC"], "lab_only": [], "interp_only": [],
    "confirmed_count": 1, "lab_only_count": 0, "interp_only_count": 0,
}

buf4 = io.StringIO()
crashed4 = False
try:
    with contextlib.redirect_stdout(buf4):
        _cmd.cmd_ticker("WFC")
except Exception as e:
    crashed4 = True
    buf4.write(f"CRASH: {type(e).__name__}: {e}\n")

out_d = buf4.getvalue()
print("=== TEST D: Direction FLAG conflict (LONG_CALL vs LONG_PUT) ===")
for line in out_d.split("\n"):
    if line.strip(): print(" ", line)
print()

assert not crashed4,                            "TEST D crashed — FAIL"
assert "conflict" in out_d.lower(),             "Conflict count not reported — FAIL"
assert "FLAG" in out_d,                         "FLAG severity not reported — FAIL"
assert "Deep dive complete" in out_d,           "Deep dive did not complete — FAIL"
print("TEST D — FLAG conflict reported:   PASS")
print()

# Cleanup
os.unlink(_tmp.name)

print("=" * 60)
print("ALL STEP 6 TESTS PASS")
print("/ticker graceful degradation: PASS (LAB_NOT_LOADED when no lab)")
print("/ticker lab confirmed:        PASS (context + conflict blocks injected)")
print("/ticker lab not confirmed:    PASS (LAB_NOT_CONFIRMED shown, no crash)")
print("/ticker FLAG conflict:        PASS (conflict count + FLAG reported)")
