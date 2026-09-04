"""Step 7 tests v2 — handles file-present and file-absent scenarios."""
import sys, io, contextlib, shutil
sys.path.insert(0, ".")

import pipeline_interpreter_commands as _cmd
from pipeline_interpreter_commands import SESSION, MA_LAB
from pathlib import Path

def _run_lab(args=""):
    buf = io.StringIO()
    crashed = False
    try:
        with contextlib.redirect_stdout(buf):
            _cmd.cmd_lab(args)
    except Exception as e:
        crashed = True
        buf.write(f"CRASH: {type(e).__name__}: {e}\n")
    return buf.getvalue(), crashed

# ══ TEST 1: graceful degradation — temporarily hide sample file ════════════════
sample = MA_LAB / "avshunter_signals_20260521_212948_2026-05-22_1213.csv"
tmp_hide = MA_LAB / "_HIDDEN_avshunter_signals_test.csv"
had_file = sample.exists()

if had_file:
    sample.rename(tmp_hide)

try:
    SESSION.pop("lab_rows", None)
    out1, crash1 = _run_lab()
    print("=== TEST 1: no lab file (graceful degradation) ===")
    for line in out1.split("\n"):
        if line.strip(): print(" ", line)
    assert not crash1,                        "TEST 1: CRASHED"
    assert "No lab export found" in out1,     "TEST 1: WARN message missing"
    assert "avshunter_signals" in out1,       "TEST 1: expected file hint missing"
    print("TEST 1 — No lab file (graceful):   PASS\n")
finally:
    if had_file:
        tmp_hide.rename(sample)     # always restore

# ══ TEST 2: /lab in MENU ════════════════════════════════════════════════════
from pipeline_interpreter_commands import MENU
assert "/lab" in MENU, "TEST 2: /lab not in MENU"
print("TEST 2 — /lab in MENU:             PASS")

# ══ TEST 3: /lab in route_command ════════════════════════════════════════════
import inspect
from pipeline_interpreter_commands import route_command
src = inspect.getsource(route_command)
assert 'cmd_lab' in src and '/lab' in src, "TEST 3: /lab not in route_command"
print("TEST 3 — /lab in route_command:    PASS")

# ══ TEST 4: 101-ticker sample file load ══════════════════════════════════════
assert sample.exists(), f"TEST 4: sample file not found at {sample}"
SESSION.pop("lab_rows", None)
SESSION.pop("lab_reconciliation", None)
SESSION.pop("lab_filename", None)

out4, crash4 = _run_lab()
print("\n=== TEST 4: sample file (101 tickers) ===")
for line in out4.split("\n"):
    if line.strip(): print(" ", line)

assert not crash4,                                 "TEST 4: CRASHED"
assert SESSION.get("lab_rows"),                    "TEST 4: SESSION['lab_rows'] not populated"
lab_count = len(SESSION["lab_rows"])
assert lab_count == 101, f"TEST 4: expected 101 tickers, got {lab_count}"
assert SESSION.get("lab_filename") == sample.name, "TEST 4: filename not stored in SESSION"
assert "LAB_ALIGNMENT" in out4,                    "TEST 4: LAB_ALIGNMENT block missing"
assert "confirmed" in out4.lower(),                "TEST 4: confirmed count missing"
assert "20260521_212948" in out4,                  "TEST 4: Run_ID missing from output"

rec = SESSION.get("lab_reconciliation", {})
assert "confirmed_count"   in rec, "TEST 4: reconciliation.confirmed_count missing"
assert "lab_only_count"    in rec, "TEST 4: reconciliation.lab_only_count missing"
assert "interp_only_count" in rec, "TEST 4: reconciliation.interp_only_count missing"

print(f"\nTEST 4 — Sample file loaded:       PASS")
print(f"  Tickers loaded:                  {lab_count} (expected 101)")
print(f"  SESSION['lab_filename']:         {SESSION['lab_filename']}")
print(f"  confirmed:                       {rec['confirmed_count']}")
print(f"  lab_only:                        {rec['lab_only_count']}")
print(f"  interp_only:                     {rec['interp_only_count']}")

# ══ TEST 5: individual ticker lookups work on the loaded data ════════════════
from lab_reconciliation import get_lab_row
first_ticker = SESSION["lab_rows"][0]["Ticker"]
found_row = get_lab_row(SESSION["lab_rows"], first_ticker)
assert found_row is not None,                  f"TEST 5: get_lab_row failed for {first_ticker}"
assert found_row["Ticker"] == first_ticker,    "TEST 5: Ticker not uppercase"
print(f"\nTEST 5 — get_lab_row works:        PASS (first ticker: {first_ticker})")

print()
print("=" * 60)
print("ALL STEP 7 TESTS PASS")
print()
print("Test summary:")
print("  1. /lab no file (graceful):    PASS — WARN printed, no crash")
print("  2. /lab in MENU:               PASS")
print("  3. /lab in route_command:      PASS")
print(f" 4. 101 tickers loaded:         PASS — SESSION populated")
print(f" 5. get_lab_row on loaded data: PASS — ticker lookup works")
