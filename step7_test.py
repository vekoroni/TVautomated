"""Step 7 tests — cmd_lab() with and without lab file."""
import sys, io, contextlib
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

# ══ TEST 1: graceful degradation — empty lab_export folder ════════════════════
lab_files = list(MA_LAB.glob("avshunter_signals_*.csv"))
assert len(lab_files) == 0, f"Expected empty folder, found: {lab_files}"

SESSION.pop("lab_rows", None)
out1, crash1 = _run_lab()
print("=== TEST 1: no lab file ===")
for line in out1.split("\n"):
    if line.strip(): print(" ", line)

assert not crash1,                        "TEST 1 crashed"
assert "No lab export found" in out1,     "TEST 1: WARN message missing"
assert "avshunter_signals" in out1,       "TEST 1: expected file pattern in message"
assert SESSION.get("lab_rows") is None or SESSION.get("lab_rows") == [], \
    "TEST 1: SESSION not clean"
print("TEST 1 — No lab file (graceful):   PASS")
print()

# ══ TEST 2: check /lab appears in MENU ═══════════════════════════════════════
from pipeline_interpreter_commands import MENU
assert "/lab" in MENU,              "TEST 2: /lab not in MENU"
print("TEST 2 — /lab in MENU:             PASS")
print()

# ══ TEST 3: /lab registered in route_command ═════════════════════════════════
import inspect
from pipeline_interpreter_commands import route_command
src = inspect.getsource(route_command)
assert 'cmd_lab' in src and '/lab' in src, "TEST 3: /lab not registered in route_command"
print("TEST 3 — /lab in route_command:    PASS")
print()

# ══ TEST 4: with sample file (conditional) ═══════════════════════════════════
sample = MA_LAB / "avshunter_signals_20260521_212948_2026-05-22_1213.csv"
if sample.exists():
    SESSION.pop("lab_rows", None)
    SESSION.pop("lab_reconciliation", None)
    out4, crash4 = _run_lab()
    print("=== TEST 4: with sample file ===")
    for line in out4.split("\n"):
        if line.strip(): print(" ", line)
    assert not crash4,                         "TEST 4 crashed"
    assert SESSION.get("lab_rows"),            "TEST 4: SESSION['lab_rows'] not populated"
    assert len(SESSION["lab_rows"]) > 0,       "TEST 4: lab_rows empty"
    lab_count = len(SESSION["lab_rows"])
    print(f"\nTEST 4 — Sample file loaded ({lab_count} tickers): PASS")
    print(f"  SESSION['lab_rows'] length: {lab_count}")
    print(f"  SESSION['lab_filename']:    {SESSION.get('lab_filename')}")
else:
    print(f"TEST 4 — Sample file not yet placed in {MA_LAB}")
    print(f"  Expected: avshunter_signals_20260521_212948_2026-05-22_1213.csv")
    print(f"  Place file and re-run for full validation.")

print()
print("=" * 60)
print("STEP 7 CORE TESTS PASSED")
