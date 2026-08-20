import sys
sys.path.insert(0, ".")
from interpreter_qa import (
    check_lab_reconciliation_qa,
    check_ticker_qa, check_triage_qa,        # existing — must still work
    REQUIRED_SECTIONS,                        # existing — must be 17
    REQUIRED_JUNIOR_SECTIONS,                 # story — must be 8
)

errors = []

# ── Existing functions and constants untouched ────────────────────────────────
assert len(REQUIRED_SECTIONS)       == 17, "REQUIRED_SECTIONS altered"
assert len(REQUIRED_JUNIOR_SECTIONS) == 8, "REQUIRED_JUNIOR_SECTIONS altered"
assert callable(check_ticker_qa),          "check_ticker_qa removed"
assert callable(check_triage_qa),          "check_triage_qa removed"
print("Existing QA untouched:              PASS  (REQUIRED_SECTIONS=17, both callables present)")

# ── Test 1: empty lab (no file loaded) ───────────────────────────────────────
r1 = check_lab_reconciliation_qa([], "", {}, None)
assert r1["mode"] == "LAB_RECONCILIATION"
assert r1["checks"]["lab_file_loaded"]["status"]   == "WARN"
assert r1["checks"]["lab_file_loaded"]["filename"] == "NOT_FOUND"
assert r1["checks"]["lab_file_loaded"]["rows"]     == 0
assert "run_id_alignment"  not in r1["checks"]   # no run_id_check passed
assert "reconciliation"    not in r1["checks"]   # no reconciliation passed
print("Test 1 — empty lab (WARN):          PASS")

# ── Test 2: lab loaded, run_id matches, all confirmed ────────────────────────
lab_rows     = [{"Ticker": "WFC"}, {"Ticker": "SPY"}]
reconcile    = {"confirmed_count":2, "lab_only_count":0, "interp_only_count":0}
run_id_ok    = {"match": True, "lab_run_id": "20260521_212948", "pipeline_run_id": "20260521_212948"}
r2 = check_lab_reconciliation_qa(lab_rows, "avshunter_signals_test.csv", reconcile, run_id_ok)
assert r2["checks"]["lab_file_loaded"]["status"]  == "PASS"
assert r2["checks"]["lab_file_loaded"]["rows"]    == 2
assert r2["checks"]["run_id_alignment"]["status"] == "PASS"
assert r2["checks"]["run_id_alignment"]["note"]   == ""
assert r2["checks"]["reconciliation"]["status"]   == "PASS"
assert r2["checks"]["reconciliation"]["interp_only"] == 0
print("Test 2 — all PASS (matched run_id, all confirmed): PASS")

# ── Test 3: run_id mismatch → WARN ───────────────────────────────────────────
run_id_bad = {"match": False, "lab_run_id": "20260521_212948", "pipeline_run_id": "20260522_095636"}
r3 = check_lab_reconciliation_qa(lab_rows, "test.csv", reconcile, run_id_bad)
assert r3["checks"]["run_id_alignment"]["status"] == "WARN"
assert "STALE_LAB_DATA" in r3["checks"]["run_id_alignment"]["note"]
print("Test 3 — run_id mismatch WARN:      PASS")

# ── Test 4: interp_only tickers → WARN with note ─────────────────────────────
reconcile_bad = {"confirmed_count":1, "lab_only_count":0, "interp_only_count":3,
                 "interp_only":["MET","GS","JPM"]}
r4 = check_lab_reconciliation_qa(lab_rows, "test.csv", reconcile_bad, run_id_ok)
assert r4["checks"]["reconciliation"]["status"]      == "WARN"
assert r4["checks"]["reconciliation"]["interp_only"] == 3
assert "3 tickers require manual review" in r4["checks"]["reconciliation"]["note"]
print("Test 4 — interp_only WARN:          PASS")

# ── Test 5: function signature matches spec exactly ──────────────────────────
import inspect
sig = inspect.signature(check_lab_reconciliation_qa)
params = list(sig.parameters.keys())
assert params == ["lab_rows","lab_filename","reconciliation","run_id_check"], \
    f"Signature wrong: {params}"
print("Test 5 — signature matches spec:    PASS")

# ── Test 6: return structure has required keys ────────────────────────────────
assert "mode"      in r2
assert "timestamp" in r2
assert "checks"    in r2
print("Test 6 — return structure correct:  PASS")

print()
print("=" * 60)
print("ALL STEP 10 TESTS PASS")
print()
print("Spec verification commands:")
print("  from interpreter_qa import check_lab_reconciliation_qa  -> OK")
print("  from interpreter_qa import check_ticker_qa, check_triage_qa -> OK")
