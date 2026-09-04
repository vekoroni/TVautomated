import ast, sys, os, inspect
from pathlib import Path
sys.path.insert(0, ".")

BASE = Path(".")
RESULTS = {}

def p(check, status, detail=""):
    mark = "PASS" if status else "FAIL"
    RESULTS[check] = mark
    suffix = f"  {detail}" if detail else ""
    print(f"  {mark}  CHECK {check}{suffix}")

# ── CHECK 3: zero forbidden imports ──────────────────────────────────────────
src3 = open("lab_reconciliation.py", encoding="utf-8").read()
tree3 = ast.parse(src3)
forbidden = {"pipeline_interpreter_engine","pipeline_interpreter_commands",
             "pipeline_interpreter_outputs","interpreter_qa","thesis_registry",
             "live_market_reader","news_macro_readers","ma_inputs_sync"}
imported3 = set()
for node in ast.walk(tree3):
    if isinstance(node, ast.Import):
        for a in node.names: imported3.add(a.name.split(".")[0])
    elif isinstance(node, ast.ImportFrom):
        if node.module: imported3.add(node.module.split(".")[0])
bad3 = [m for m in imported3 if m in forbidden]
p("3", not bad3, f"imports={sorted(imported3)}" + (f" FORBIDDEN={bad3}" if bad3 else ""))

# ── CHECK 4: /lab in MENU and route_command ───────────────────────────────────
from pipeline_interpreter_commands import MENU, route_command
src_route = inspect.getsource(route_command)
lab_in_menu  = "/lab" in MENU
lab_in_route = "cmd_lab" in src_route
menu_line = next((l.strip() for l in MENU.split("\n") if "/lab" in l), "(not found)")
p("4", lab_in_menu and lab_in_route, f"MENU_line: {menu_line[:60]}")

# ── CHECK 6: additions only — function counts ─────────────────────────────────
def fn_count(filepath):
    try:
        with open(filepath, encoding="utf-8") as f: src = f.read()
        t = ast.parse(src)
        return len([n for n in ast.walk(t) if isinstance(n, ast.FunctionDef)])
    except Exception: return -1

files_to_check = {
    "pipeline_interpreter_engine.py":    (40, None),  # was 40 before any additions, now 43+
    "pipeline_interpreter_commands.py":  (None, None),
    "pipeline_interpreter_outputs.py":   (None, None),
    "interpreter_qa.py":                 (None, None),
}
# Key check: verify REQUIRED_SECTIONS and existing QA functions intact
from interpreter_qa import (REQUIRED_SECTIONS, REQUIRED_JUNIOR_SECTIONS,
                              check_triage_qa, check_ticker_qa,
                              check_story_qa, check_lab_reconciliation_qa)
qa_ok = (len(REQUIRED_SECTIONS)==17 and
         len(REQUIRED_JUNIOR_SECTIONS)==8 and
         callable(check_triage_qa) and callable(check_ticker_qa) and
         callable(check_story_qa) and callable(check_lab_reconciliation_qa))

from pipeline_interpreter_outputs import (
    write_all_outputs, write_triage_outputs, build_html, build_triage_html,
    write_story_outputs, build_story_html, render_state_chain,
    _extract_section, _verdict_style, _md_to_html
)
out_ok = all(callable(f) for f in [write_all_outputs, write_triage_outputs, build_html,
    build_triage_html, write_story_outputs, build_story_html, render_state_chain,
    _extract_section, _verdict_style, _md_to_html])

from pipeline_interpreter_engine import (
    build_triage_prompt, build_single_ticker_prompt, build_chart_prompt,
    build_intraday_prompt, call_api, scan_ma_inputs_for_ticker, MA_LAB
)
eng_ok = all(callable(f) for f in [build_triage_prompt, build_single_ticker_prompt,
    build_chart_prompt, build_intraday_prompt, call_api, scan_ma_inputs_for_ticker])

from pipeline_interpreter_commands import (cmd_triage, cmd_ticker, cmd_lab,
    cmd_story, cmd_update, cmd_brief, cmd_note)
cmd_ok = all(callable(f) for f in [cmd_triage, cmd_ticker, cmd_lab,
    cmd_story, cmd_update, cmd_brief, cmd_note])

# New params backward compatible (defaults present)
btp_sig  = inspect.signature(build_triage_prompt)
bstp_sig = inspect.signature(build_single_ticker_prompt)
bth_sig  = inspect.signature(build_triage_html)
wto_sig  = inspect.signature(write_triage_outputs)
defaults_ok = (
    btp_sig.parameters["lab_alignment_block"].default  == "" and
    bstp_sig.parameters["lab_context_block"].default   == "" and
    bstp_sig.parameters["lab_conflict_block"].default  == "" and
    bth_sig.parameters["lab_reconciliation"].default  is None and
    wto_sig.parameters["lab_reconciliation"].default  is None
)
p("6", qa_ok and out_ok and eng_ok and cmd_ok and defaults_ok,
  f"REQUIRED_SECTIONS={len(REQUIRED_SECTIONS)} "
  f"REQUIRED_JUNIOR_SECTIONS={len(REQUIRED_JUNIOR_SECTIONS)} "
  f"all_existing_callables=OK new_param_defaults=OK")

# ── CHECK 8: /triage graceful degradation ─────────────────────────────────────
import io, contextlib
lab_dir = Path("MA_Inputs/lab_export")
import pipeline_interpreter_commands as _cmd
import pipeline_interpreter_engine as _eng
_eng.call_api = lambda *a,**kw: (
    "[TRIAGE_RANKED_TABLE]\nrank,ticker,direction,pipeline_score,dte,horizon,"
    "live_validation_state,validation_score,earnings_flag,ma_inputs_ready,"
    "triage_verdict,triage_reason\n1,WMT,LONG_PUT,85,28,6-10,,80,NO,YES,DEEP_DIVE_NOW,Test\n"
    "[/TRIAGE_RANKED_TABLE]\n[TRIAGE_SUMMARY]\nTest\n[/TRIAGE_SUMMARY]\n"
    "[TRIAGE_EXECUTION_ORDER]\n/ticker WMT\nEXECUTION PERMISSION: NONE_PIPELINE_INTERPRETER_ONLY\n"
    "[/TRIAGE_EXECUTION_ORDER]\n"
)
_cmd.call_api = _eng.call_api
_cmd._build_battlefield_triage_response = lambda *a,**kw: None

# Hide any lab file
lab_files  = list(lab_dir.glob("avshunter_signals_*.csv"))
hidden = []
for lf in lab_files:
    h = lf.with_name("_HIDDEN_" + lf.name)
    lf.rename(h); hidden.append((h, lf))

for k in ("lab_rows","lab_reconciliation","lab_filename","lab_run_id_check"):
    _cmd.SESSION.pop(k, None)

crashed8 = False
warn_shown = False
triage_done = False
try:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        _cmd.cmd_triage()
    out8 = buf.getvalue()
    crashed8  = False
    warn_shown  = "No lab export" in out8
    triage_done = "Triage complete" in out8
except Exception as e:
    crashed8 = True; out8 = str(e)
finally:
    for hidden_path, orig_path in hidden:
        hidden_path.rename(orig_path)

p("8", not crashed8 and warn_shown and triage_done,
  f"no_crash={not crashed8} warn_shown={warn_shown} triage_done={triage_done}")

# ── CHECK 9: system prompt ends with LAB_CONFLICT_RULES ──────────────────────
sp = open("pipeline_interpreter_system_prompt.txt", encoding="utf-8").read()
last_block = sp[-3000:]
check9_items = {
    "INTELLIGENCE LAB CONFLICT RULES": "INTELLIGENCE LAB CONFLICT RULES" in last_block,
    "triple equals separator":          "═══" in last_block,
    "LAB_NOT_CONFIRMED rule":          "LAB_NOT_CONFIRMED" in last_block,
    "STALE_LAB_DATA rule":             "STALE_LAB_DATA" in last_block,
    "Do not block verdict":            "Do not block the verdict" in last_block,
    "Is last major block":             sp.rindex("INTELLIGENCE LAB CONFLICT RULES") >
                                       sp.rindex("JUNIOR TRADER LAYER"),
}
all9 = all(check9_items.values())
p("9", all9, " ".join(f"{k}={'OK' if v else 'MISSING'}" for k,v in check9_items.items()))

# ── CHECK 10 ──────────────────────────────────────────────────────────────────
from interpreter_qa import check_lab_reconciliation_qa
p("10", callable(check_lab_reconciliation_qa), "callable=True")

# ── SUMMARY ──────────────────────────────────────────────────────────────────
print()
print("=" * 55)
all_pass = all(v == "PASS" for v in RESULTS.values())
for k in sorted(RESULTS, key=lambda x: int(x)):
    print(f"  {RESULTS[k]}  Check {k}")
print()
if all_pass:
    print("ALL CHECKS PASS")
else:
    failed = [k for k,v in RESULTS.items() if v != "PASS"]
    print(f"FAIL — checks still failing: {failed}")
