import sys, inspect
sys.path.insert(0, ".")
from pipeline_interpreter_engine import build_triage_prompt, build_single_ticker_prompt

errors = []

# ── 1. New parameters present in signatures ───────────────────────────────────
tp_sig  = inspect.signature(build_triage_prompt)
stp_sig = inspect.signature(build_single_ticker_prompt)

assert "lab_alignment_block"  in tp_sig.parameters,  "build_triage_prompt missing lab_alignment_block"
assert "lab_context_block"    in stp_sig.parameters, "build_single_ticker_prompt missing lab_context_block"
assert "lab_conflict_block"   in stp_sig.parameters, "build_single_ticker_prompt missing lab_conflict_block"
print("1. New parameters in signatures:   PASS")

# ── 2. New params default to empty string ─────────────────────────────────────
assert tp_sig.parameters["lab_alignment_block"].default  == "", "lab_alignment_block default must be ''"
assert stp_sig.parameters["lab_context_block"].default   == "", "lab_context_block default must be ''"
assert stp_sig.parameters["lab_conflict_block"].default  == "", "lab_conflict_block default must be ''"
print("2. Default empty string:           PASS")

# ── 3. Existing params still present and in same order ────────────────────────
tp_params  = list(tp_sig.parameters.keys())
stp_params = list(stp_sig.parameters.keys())
assert tp_params[:3]  == ["pipeline_rows","ma_inputs_summary","session_mode"], \
    f"build_triage_prompt param order broken: {tp_params[:3]}"
assert stp_params[:5] == ["ticker","pipeline_row","options_data","context","ticker_note"], \
    f"build_single_ticker_prompt param order broken: {stp_params[:5]}"
print("3. Existing param order unchanged:  PASS")

# ── 4. build_single_ticker_prompt — lab empty → prompt unchanged for callers ──
# Call with NO lab args; just check it runs and doesn't inject empty blocks
fake_row = {"ticker":"WFC","direction":"LONG_PUT","kill_switch_level":"77.50"}
# build_single_ticker_prompt calls news_macro_readers which may print — capture that
import io, contextlib
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    prompt_no_lab = build_single_ticker_prompt("WFC", fake_row)
assert "LAB_CONTEXT"     not in prompt_no_lab, "Lab block leaked into no-lab prompt"
assert "LAB_FIELD"       not in prompt_no_lab, "Conflict block leaked into no-lab prompt"
assert "PIPELINE ROW"    in prompt_no_lab,     "PIPELINE ROW missing from prompt"
assert "MACRO + ENRICHMENT" in prompt_no_lab,  "MACRO section missing from prompt"
print("4. No-lab call unchanged:          PASS")

# ── 5. build_single_ticker_prompt — lab blocks injected when provided ─────────
with contextlib.redirect_stdout(buf):
    prompt_with_lab = build_single_ticker_prompt(
        "WFC", fake_row,
        lab_context_block="LAB_CONTEXT_WFC: Verdict=ARMED",
        lab_conflict_block="LAB_FIELD_CONFLICTS_WFC: NONE — fully aligned",
    )
assert "LAB_CONTEXT_WFC"        in prompt_with_lab, "Lab context not injected"
assert "LAB_FIELD_CONFLICTS_WFC" in prompt_with_lab, "Lab conflict not injected"
# Confirm injection position: lab block appears AFTER options, BEFORE macro
options_pos = prompt_with_lab.find("OPTIONS DATA")
lab_pos     = prompt_with_lab.find("LAB_CONTEXT_WFC")
macro_pos   = prompt_with_lab.find("MACRO + ENRICHMENT")
assert options_pos < lab_pos < macro_pos, \
    f"Injection order wrong: options={options_pos} lab={lab_pos} macro={macro_pos}"
print("5. Lab blocks injected in order:   PASS")

# ── 6. build_triage_prompt — lab_alignment_block injected after macro ─────────
fake_rows = [{"ticker":"WFC","direction":"LONG_PUT","pipeline_score":"85"}]
with contextlib.redirect_stdout(buf):
    tp_with_lab = build_triage_prompt(
        fake_rows,
        lab_alignment_block="LAB_ALIGNMENT (test.csv):\n  confirmed: 1",
    )
assert "LAB_ALIGNMENT" in tp_with_lab, "Lab alignment not injected into triage prompt"
macro_pos2 = tp_with_lab.find("MACRO + ENRICHMENT")
lab_pos2   = tp_with_lab.find("LAB_ALIGNMENT")
output_pos = tp_with_lab.find("OUTPUT EXACTLY THREE")
assert macro_pos2 < lab_pos2 < output_pos, \
    f"Triage injection order wrong: macro={macro_pos2} lab={lab_pos2} output={output_pos}"
print("6. Triage lab injection in order:  PASS")

# ── 7. build_triage_prompt — no lab = no lab block in prompt ─────────────────
with contextlib.redirect_stdout(buf):
    tp_no_lab = build_triage_prompt(fake_rows)
assert "LAB_ALIGNMENT" not in tp_no_lab, "Lab block leaked into no-lab triage prompt"
print("7. No-lab triage unchanged:        PASS")

print()
print("All Step 4 tests PASS")
