"""
Step 6 test v3 — patches on _cmd namespace (where cmd_ticker resolves names).
"""
import sys, io, contextlib, os, csv, tempfile
sys.path.insert(0, ".")

# Patch call_api on the engine first (before commands import)
import pipeline_interpreter_engine as _eng
_FAKE = (
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
_eng.call_api = lambda *a, **kw: _FAKE

import pipeline_interpreter_commands as _cmd
from pipeline_interpreter_commands import SESSION

# Patch on _cmd namespace — this is what cmd_ticker actually resolves
_orig_scan  = _cmd.scan_ma_inputs_for_ticker
_orig_bstp  = _cmd.build_single_ticker_prompt
_orig_api   = _cmd.call_api
_cmd.call_api = lambda *a, **kw: _FAKE   # also patch cmd namespace

# Force no-chart path so build_single_ticker_prompt is always used
_cmd.scan_ma_inputs_for_ticker = lambda t: {
    "charts":[], "screenshots":[], "options":[], "pipeline":[]
}

# Minimal pipeline CSV
_tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False,
                                   newline="", encoding="utf-8")
_fields = ["ticker","direction","eil_v3_verdict","kill_switch_level",
           "probe_trigger","armed_trigger","execution_permission",
           "horizon","preferred_contract","ivp","premium"]
with open(_tmp.name, "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=_fields)
    w.writeheader()
    w.writerow({"ticker":"WFC","direction":"LONG_PUT","eil_v3_verdict":"ARMED",
        "kill_switch_level":"77.50","probe_trigger":"75.00","armed_trigger":"74.00",
        "execution_permission":"NONE_PIPELINE_INTERPRETER_ONLY","horizon":"11-20",
        "preferred_contract":"WFC260618P00075000","ivp":"55","premium":"1.20"})
SESSION["last_pipeline_csv"] = _tmp.name

def _run(ticker="WFC"):
    buf = io.StringIO()
    crashed = False
    try:
        with contextlib.redirect_stdout(buf):
            _cmd.cmd_ticker(ticker)
    except Exception as e:
        crashed = True
        buf.write(f"CRASH: {type(e).__name__}: {e}\n")
    return buf.getvalue(), crashed

# ══ TEST A: no lab ════════════════════════════════════════════════════════════
SESSION.pop("lab_rows", None)
out_a, crash_a = _run()
assert not crash_a,                   f"A crashed:\n{out_a}"
assert "LAB_NOT_LOADED" in out_a,     f"A: LAB_NOT_LOADED missing\n{out_a}"
assert "Deep dive complete" in out_a, f"A: no completion\n{out_a}"
print("TEST A — No lab (LAB_NOT_LOADED): PASS")

# ══ TEST B: confirmed, no conflicts — capture lab params ══════════════════════
SESSION["lab_rows"] = [{"Ticker":"WFC","Run_ID":"20260521_212948",
    "Direction":"LONG_PUT","Verdict":"ARMED","IVP":"55","Strike":"75",
    "EV":"0.72","WBS_Grade":"A","Priority_Rank":"3","Premium_Mid":"1.20"}]
SESSION["lab_reconciliation"] = {"confirmed":["WFC"],"lab_only":[],
    "interp_only":[],"confirmed_count":1,"lab_only_count":0,"interp_only_count":0}

_cap = {"ctx": None, "conf": None}
def _mock_bstp(*a, **kw):
    _cap["ctx"]  = kw.get("lab_context_block",  "NOT_PASSED")
    _cap["conf"] = kw.get("lab_conflict_block", "NOT_PASSED")
    return _orig_bstp(*a, **kw)
_cmd.build_single_ticker_prompt = _mock_bstp

out_b, crash_b = _run()
_cmd.build_single_ticker_prompt = _orig_bstp   # restore

assert not crash_b,                       f"B crashed:\n{out_b}"
assert "Lab aligned" in out_b,            f"B: aligned msg missing\n{out_b}"
assert "LAB_NOT_CONFIRMED" not in out_b,  f"B: false LAB_NOT_CONFIRMED\n{out_b}"
assert _cap["ctx"] is not None,           "B: lab_context_block not captured (mock not hit)"
assert "LAB_CONTEXT_WFC" in _cap["ctx"],  f"B: ctx wrong: {_cap['ctx'][:80]}"
assert "NONE" in _cap["conf"],            f"B: conf wrong: {_cap['conf'][:80]}"
print("TEST B — Confirmed, no conflicts:")
print(f"  lab_context_block  → {_cap['ctx'][:50]}...")
print(f"  lab_conflict_block → {_cap['conf'][:50]}")
print("  PASS")

# ══ TEST C: LAB_NOT_CONFIRMED (interp_only) ══════════════════════════════════
SESSION["lab_rows"] = [{"Ticker":"SPY","Run_ID":"X","Direction":"LONG_CALL"}]
SESSION["lab_reconciliation"] = {"confirmed":["SPY"],"lab_only":[],
    "interp_only":["WFC"],"confirmed_count":1,"lab_only_count":0,"interp_only_count":1}
out_c, crash_c = _run()
assert not crash_c,                    f"C crashed:\n{out_c}"
assert "LAB_NOT_CONFIRMED" in out_c,   f"C: missing\n{out_c}"
assert "Deep dive complete" in out_c,  f"C: no completion\n{out_c}"
print("TEST C — LAB_NOT_CONFIRMED:        PASS")

# ══ TEST D: FLAG conflict (direction mismatch) ════════════════════════════════
SESSION["lab_rows"] = [{"Ticker":"WFC","Run_ID":"X",
    "Direction":"LONG_CALL","Verdict":"ARMED","IVP":"55",
    "Strike":"75","Premium_Mid":"1.20"}]
SESSION["lab_reconciliation"] = {"confirmed":["WFC"],"lab_only":[],
    "interp_only":[],"confirmed_count":1,"lab_only_count":0,"interp_only_count":0}
out_d, crash_d = _run()
assert not crash_d,                  f"D crashed:\n{out_d}"
assert "conflict" in out_d.lower(),  f"D: conflict msg missing\n{out_d}"
assert "FLAG" in out_d,              f"D: FLAG not reported\n{out_d}"
assert "Deep dive complete" in out_d,f"D: no completion\n{out_d}"
print("TEST D — FLAG conflict reported:   PASS")

# ══ Restore and cleanup ═══════════════════════════════════════════════════════
_cmd.scan_ma_inputs_for_ticker = _orig_scan
_cmd.call_api                  = _orig_api
os.unlink(_tmp.name)

print()
print("=" * 60)
print("ALL STEP 6 TESTS PASS")
print()
print("Summary:")
print("  A. LAB_NOT_LOADED — no lab in session: PASS (no crash, WARN printed)")
print("  B. Confirmed, no conflicts:             PASS (ctx + conflict blocks injected)")
print("  C. LAB_NOT_CONFIRMED (interp_only):     PASS (warning shown, ticker completes)")
print("  D. FLAG direction conflict:             PASS (flag count shown, no crash)")
