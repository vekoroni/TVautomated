"""
Step 6 test v2 — forces no-chart path so build_single_ticker_prompt is used.
"""
import sys, io, contextlib, os, csv, tempfile
sys.path.insert(0, ".")

import pipeline_interpreter_engine as _eng
_FAKE_RESPONSE = (
    "[TRADE_NARRATIVE_WFC]\nTest\n[/TRADE_NARRATIVE_WFC]\n"
    "[TRADE_BRIEF_CSV]\nticker,direction,final_verdict,trade_state,horizon,dte,"
    "trigger_level,kill_switch_level,preferred_contract,premium,rr,iv_context,"
    "ivp,earnings_in_window,earnings_action,max_pain_risk,"
    "sector_confirmation_required,first_hour_rule,probe_permitted,"
    "initial_adverse_tolerance,capital_permission,narrative_summary,"
    "execution_permission\n"
    "WFC,LONG_PUT,PROBE,WATCH,11-20,45,75.00,77.50,WFC260618P00075000,"
    "1.20,2.5,ELEVATED,55,NO,N/A,LOW,NO,YES,YES,0.50,"
    "CAPITAL_DENIED_PENDING_LIVE_CONFIRMATION,Test,"
    "NONE_PIPELINE_INTERPRETER_ONLY\n[/TRADE_BRIEF_CSV]\n"
)
_eng.call_api = lambda *a, **kw: _FAKE_RESPONSE

# Patch scan_ma_inputs_for_ticker to return NO charts — force build_single_ticker_prompt path
_orig_scan = _eng.scan_ma_inputs_for_ticker
_eng.scan_ma_inputs_for_ticker = lambda t: {"charts":[], "screenshots":[], "options":[], "pipeline":[]}

import pipeline_interpreter_commands as _cmd
from pipeline_interpreter_commands import SESSION

# Minimal synthetic pipeline CSV
_tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False,
                                   newline="", encoding="utf-8")
csv.DictWriter(_tmp, fieldnames=[
    "ticker","direction","eil_v3_verdict","kill_switch_level",
    "probe_trigger","armed_trigger","execution_permission",
    "horizon","preferred_contract","ivp","premium"
]).writeheader()  # need to write row too
_tmp.close()
# Reopen and write properly
with open(_tmp.name, "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=[
        "ticker","direction","eil_v3_verdict","kill_switch_level",
        "probe_trigger","armed_trigger","execution_permission",
        "horizon","preferred_contract","ivp","premium"])
    w.writeheader()
    w.writerow({"ticker":"WFC","direction":"LONG_PUT","eil_v3_verdict":"ARMED",
        "kill_switch_level":"77.50","probe_trigger":"75.00","armed_trigger":"74.00",
        "execution_permission":"NONE_PIPELINE_INTERPRETER_ONLY","horizon":"11-20",
        "preferred_contract":"WFC260618P00075000","ivp":"55","premium":"1.20"})
SESSION["last_pipeline_csv"] = _tmp.name

# ══ TEST A: no lab loaded ═════════════════════════════════════════════════════
SESSION.pop("lab_rows", None)
buf = io.StringIO()
crashed = False
try:
    with contextlib.redirect_stdout(buf):
        _cmd.cmd_ticker("WFC")
except Exception as e:
    crashed = True
out_a = buf.getvalue()
assert not crashed,                 "A crashed"
assert "LAB_NOT_LOADED" in out_a,  "A: LAB_NOT_LOADED missing"
assert "Deep dive complete" in out_a, "A: deep dive did not complete"
print("TEST A — No lab (LAB_NOT_LOADED): PASS")

# ══ TEST B: confirmed, no conflicts ══════════════════════════════════════════
SESSION["lab_rows"] = [{"Ticker":"WFC","Run_ID":"20260521_212948",
    "Direction":"LONG_PUT","Verdict":"ARMED","IVP":"55","Strike":"75",
    "EV":"0.72","WBS_Grade":"A","Priority_Rank":"3","Premium_Mid":"1.20"}]
SESSION["lab_reconciliation"] = {"confirmed":["WFC"],"lab_only":[],
    "interp_only":[],"confirmed_count":1,"lab_only_count":0,"interp_only_count":0}

_captured = {"ctx":[], "conf":[]}
_orig_bstp = _eng.build_single_ticker_prompt
def _mock(*a, **kw):
    _captured["ctx"].append(kw.get("lab_context_block","NOT_PASSED"))
    _captured["conf"].append(kw.get("lab_conflict_block","NOT_PASSED"))
    return _orig_bstp(*a, **kw)
_eng.build_single_ticker_prompt = _mock

buf2 = io.StringIO()
with contextlib.redirect_stdout(buf2):
    _cmd.cmd_ticker("WFC")
_eng.build_single_ticker_prompt = _orig_bstp
out_b = buf2.getvalue()

assert "Lab aligned" in out_b,               "B: aligned msg missing"
assert "LAB_NOT_CONFIRMED" not in out_b,     "B: false not-confirmed"
assert _captured["ctx"],                     "B: lab_context_block not passed"
assert "LAB_CONTEXT_WFC" in _captured["ctx"][0], \
    f"B: context block wrong: {_captured['ctx'][0][:60]}"
assert "NONE" in _captured["conf"][0],       f"B: conflict block wrong: {_captured['conf'][0]}"
print("TEST B — Confirmed, no conflicts:")
print(f"  lab_context_block  passed: YES  ({_captured['ctx'][0][:45]}...)")
print(f"  lab_conflict_block passed: YES  ({_captured['conf'][0][:45]})")
print("  PASS")

# ══ TEST C: LAB_NOT_CONFIRMED (interp_only) ══════════════════════════════════
SESSION["lab_rows"] = [{"Ticker":"SPY","Run_ID":"X","Direction":"LONG_CALL"}]
SESSION["lab_reconciliation"] = {"confirmed":["SPY"],"lab_only":[],
    "interp_only":["WFC"],"confirmed_count":1,"lab_only_count":0,"interp_only_count":1}
buf3 = io.StringIO()
with contextlib.redirect_stdout(buf3):
    _cmd.cmd_ticker("WFC")
out_c = buf3.getvalue()
assert "LAB_NOT_CONFIRMED" in out_c, "C: LAB_NOT_CONFIRMED missing"
assert "Deep dive complete" in out_c,"C: deep dive did not complete"
print("TEST C — LAB_NOT_CONFIRMED:        PASS")

# ══ TEST D: FLAG conflict ════════════════════════════════════════════════════
SESSION["lab_rows"] = [{"Ticker":"WFC","Run_ID":"X",
    "Direction":"LONG_CALL",   # conflicts with pipeline LONG_PUT => FLAG
    "Verdict":"ARMED","IVP":"55","Strike":"75","Premium_Mid":"1.20"}]
SESSION["lab_reconciliation"] = {"confirmed":["WFC"],"lab_only":[],
    "interp_only":[],"confirmed_count":1,"lab_only_count":0,"interp_only_count":0}
buf4 = io.StringIO()
with contextlib.redirect_stdout(buf4):
    _cmd.cmd_ticker("WFC")
out_d = buf4.getvalue()
assert "conflict" in out_d.lower(),  "D: conflict msg missing"
assert "FLAG" in out_d,              "D: FLAG not reported"
assert "Deep dive complete" in out_d,"D: deep dive did not complete"
print("TEST D — FLAG conflict reported:   PASS")

# ══ Restore and cleanup ═══════════════════════════════════════════════════════
_eng.scan_ma_inputs_for_ticker = _orig_scan
os.unlink(_tmp.name)

print()
print("=" * 60)
print("ALL STEP 6 TESTS PASS")
print()
print("Summary:")
print("  A. LAB_NOT_LOADED (no lab in session):   PASS — no crash, WARN printed")
print("  B. Confirmed, no conflicts:               PASS — context + conflict injected")
print("  C. LAB_NOT_CONFIRMED (interp_only):       PASS — warning shown, ticker runs")
print("  D. FLAG direction conflict:               PASS — flag count printed, no crash")
