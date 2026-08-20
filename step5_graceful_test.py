"""
Graceful-degradation test for Step 5.
Tests the lab reconciliation gate in cmd_triage() without making a live API call.
Patches call_api and _build_battlefield_triage_response to avoid network/file deps.
"""
import sys, io, contextlib, types
sys.path.insert(0, ".")

# ── Patch call_api before importing commands ──────────────────────────────────
import pipeline_interpreter_engine as _eng
_eng.call_api = lambda *a, **kw: "[TRIAGE_RANKED_TABLE]\nrank,ticker\n1,WFC\n[/TRIAGE_RANKED_TABLE]\n[TRIAGE_SUMMARY]\nTest summary\n[/TRIAGE_SUMMARY]\n[TRIAGE_EXECUTION_ORDER]\n/ticker WFC\nEXECUTION PERMISSION: NONE_PIPELINE_INTERPRETER_ONLY\n[/TRIAGE_EXECUTION_ORDER]"

import pipeline_interpreter_commands as _cmd

# Patch battlefield builder so it returns nothing (forces API path)
_cmd._build_battlefield_triage_response = lambda *a, **kw: None

# Confirm lab_export folder is empty
from pathlib import Path
lab_dir = Path("MA_Inputs/lab_export")
lab_files = list(lab_dir.glob("avshunter_signals_*.csv"))
assert len(lab_files) == 0, f"Expected empty lab_export, found: {lab_files}"

# ── Capture all output from cmd_triage ───────────────────────────────────────
buf = io.StringIO()
crashed = False
try:
    with contextlib.redirect_stdout(buf):
        _cmd.cmd_triage()
except SystemExit:
    pass  # acceptable
except Exception as e:
    crashed = True
    print(f"CRASH: {type(e).__name__}: {e}")

output = buf.getvalue()

# ── Assertions ────────────────────────────────────────────────────────────────
print("=== cmd_triage() output (no lab file) ===")
for line in output.split("\n"):
    if line.strip():
        print(" ", line)
print()

# 1. Did NOT crash
assert not crashed, "cmd_triage() raised an exception — FAIL"
print("1. No crash:                      PASS")

# 2. WARN message printed
assert "No lab export" in output, f"Expected WARN message not found in output:\n{output}"
print("2. WARN message printed:          PASS")

# 3. lab_block set to warn string (no LAB_ALIGNMENT data injected)
assert "[LAB] No lab export" in output, "Expected [LAB] prefix in warn message"
print("3. [LAB] prefix in message:       PASS")

# 4. SESSION keys initialised safely
from pipeline_interpreter_commands import SESSION
assert SESSION.get("lab_rows")           == [],  "lab_rows should be [] when no file"
assert SESSION.get("lab_reconciliation") == {},  "lab_reconciliation should be {} when no file"
assert SESSION.get("lab_filename")       == "",  "lab_filename should be '' when no file"
print("4. SESSION keys safe (empty):     PASS")

# 5. Triage still completed (response was produced)
assert "TRIAGE" in output or "triage" in output.lower(), "Triage output missing from stdout"
print("5. Triage output produced:        PASS")

print()
print("GRACEFUL DEGRADATION TEST: PASS — /triage completes normally with no lab file")
