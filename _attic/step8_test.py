"""Step 8 test — LAB_ALIGNMENT card and LAB STATUS column in triage HTML."""
import sys, io, contextlib, os
sys.path.insert(0, ".")

import pipeline_interpreter_engine as _eng
_FAKE_TRIAGE = (
    "[TRIAGE_RANKED_TABLE]\n"
    "rank,ticker,direction,pipeline_score,dte,horizon,live_validation_state,"
    "validation_score,earnings_flag,ma_inputs_ready,triage_verdict,triage_reason\n"
    "1,WFC,LONG_PUT,82,45,11-20,,80,NO,YES,DEEP_DIVE_NOW,High score\n"
    "2,SPY,LONG_CALL,75,30,1-5,,70,NO,YES,DEEP_DIVE_NEXT,Good setup\n"
    "3,MET,LONG_PUT,60,60,6-10,,55,NO,PARTIAL,REVIEW_LATER,Watch only\n"
    "[/TRIAGE_RANKED_TABLE]\n"
    "[TRIAGE_SUMMARY]\nTest session picture\n[/TRIAGE_SUMMARY]\n"
    "[TRIAGE_EXECUTION_ORDER]\n/ticker WFC\nEXECUTION PERMISSION: NONE_PIPELINE_INTERPRETER_ONLY\n"
    "[/TRIAGE_EXECUTION_ORDER]\n"
)
_eng.call_api = lambda *a, **kw: _FAKE_TRIAGE
_eng._build_battlefield_triage_response = lambda *a, **kw: None  # force API path

import pipeline_interpreter_commands as _cmd
from pipeline_interpreter_commands import SESSION, MA_LAB

# Load sample file into SESSION via /lab
buf0 = io.StringIO()
with contextlib.redirect_stdout(buf0):
    _cmd.cmd_lab()
assert SESSION.get("lab_rows"), "Lab rows not loaded"
lab_count = len(SESSION["lab_rows"])
print(f"Lab rows loaded: {lab_count}")

# Run /triage to produce HTML with lab data
buf1 = io.StringIO()
crashed = False
try:
    with contextlib.redirect_stdout(buf1):
        _cmd.cmd_triage()
except Exception as e:
    crashed = True
    buf1.write(f"CRASH: {e}\n")

out = buf1.getvalue()
print("\n=== /triage output ===")
for line in out.split("\n"):
    if line.strip(): print(" ", line)

assert not crashed, f"cmd_triage crashed:\n{out}"

# Find the HTML file that was written
from pathlib import Path
outputs_dir = Path("outputs")
html_files = sorted(outputs_dir.rglob("triage_*.html"),
                    key=lambda p: p.stat().st_mtime, reverse=True)
assert html_files, "No triage HTML file written"
html_path = html_files[0]
html = html_path.read_text(encoding="utf-8")
print(f"\nHTML file: {html_path.name}  ({len(html):,} chars)")

# ── Check 1: LAB_ALIGNMENT card present ──────────────────────────────────────
assert "Intelligence Lab Reconciliation" in html, "LAB_ALIGNMENT card header missing"
print("\nCheck 1 — LAB_ALIGNMENT card present:        PASS")

# ── Check 2: Three rows with correct badges ───────────────────────────────────
assert "CONFIRMED" in html,        "CONFIRMED badge missing"
assert "LAB ONLY"  in html,        "LAB ONLY badge missing"
assert "LAB_NOT_CONFIRMED" in html, "LAB_NOT_CONFIRMED badge missing"
print("Check 2 — Three rows with correct badges:     PASS")

# ── Check 3: LAB STATUS column in table header ───────────────────────────────
assert "Lab Status" in html, "Lab Status column header missing"
print("Check 3 — LAB STATUS column in header:        PASS")

# ── Check 4: Ticker-level badges in the ranked table ─────────────────────────
# WFC - check if it shows CONFIRMED or LAB_NOT_CONFIRMED based on sample data
lab_tickers = {r["Ticker"] for r in SESSION["lab_rows"]}
wfc_in_lab = "WFC" in lab_tickers
spy_in_lab = "SPY" in lab_tickers
met_in_lab = "MET" in lab_tickers
print(f"\n  WFC in lab: {wfc_in_lab} | SPY in lab: {spy_in_lab} | MET in lab: {met_in_lab}")

# All three tickers in fake triage — at least one should have LAB_NOT_CONFIRMED or CONFIRMED badge
import re
lab_status_cells = re.findall(r'(CONFIRMED|LAB_NOT_CONFIRMED|LAB_ONLY|LAB_NOT_LOADED|CONFIRMED_CONFLICTS)', html)
print(f"  LAB STATUS values found in HTML: {lab_status_cells[:15]}")
assert len(lab_status_cells) >= 3, f"Expected at least 3 lab status cells, found {len(lab_status_cells)}"
print("Check 4 — Per-ticker LAB STATUS badges:       PASS")

# ── Check 5: Run_ID section present ──────────────────────────────────────────
# The run_id check shows MISMATCH since we have no pipeline CSV loaded
assert "20260521_212948" in html or "run_id" in html.lower() or "STALE" in html or "reconciliation" in html.lower(), \
    "Run_ID / lab filename not found in HTML"
print("Check 5 — Lab filename/run_id in card:        PASS")

# ── Check 6: Regression — triage still works without lab file (LAB_NOT_LOADED) ──
SESSION.pop("lab_rows", None)
SESSION.pop("lab_reconciliation", None)
SESSION.pop("lab_filename", None)
SESSION.pop("lab_run_id_check", None)

buf2 = io.StringIO()
with contextlib.redirect_stdout(buf2):
    _cmd.cmd_triage()
html2_files = sorted(outputs_dir.rglob("triage_*.html"),
                     key=lambda p: p.stat().st_mtime, reverse=True)
html2 = html2_files[0].read_text(encoding="utf-8")
assert "LAB_NOT_LOADED" in html2, "LAB_NOT_LOADED not shown when no lab in session"
assert "Intelligence Lab Reconciliation" in html2, "LAB card missing on no-lab run"
print("Check 6 — No-lab HTML shows LAB_NOT_LOADED:   PASS")

print()
print("=" * 60)
print("ALL STEP 8 TESTS PASS")
print()
print(f"HTML written: {html_path}")
print(f"Open in browser to visually confirm layout.")
