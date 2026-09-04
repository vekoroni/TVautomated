import sys
sys.path.insert(0, ".")
from lab_reconciliation import (
    reconcile_universes, load_lab_export, validate_lab_field_alignment,
    build_lab_alignment_block, build_lab_context_block, build_field_conflict_block,
    get_lab_row, check_run_id_alignment,
    FIELD_MAP, FIELD_SEVERITY, IVP_TOLERANCE, PREMIUM_TOLERANCE,
)
from pathlib import Path

errors = []

# 1. Constants
assert IVP_TOLERANCE == 5.0,      "IVP_TOLERANCE wrong"
assert PREMIUM_TOLERANCE == 0.10, "PREMIUM_TOLERANCE wrong"
assert "Direction" in FIELD_MAP,  "FIELD_MAP missing Direction"
assert FIELD_SEVERITY["Direction"] == "FLAG",  "Direction must be FLAG"
assert FIELD_SEVERITY["IVP"]       == "WARN",  "IVP must be WARN"
print("1. Constants:                PASS")

# 2. reconcile_universes — three-way split
lab   = [{"Ticker":"WFC"},{"Ticker":"SPY"},{"Ticker":"AAPL"}]
interp= ["WFC","MET","SPY"]
r     = reconcile_universes(lab, interp)
assert r["confirmed"]   == ["SPY","WFC"],  f"confirmed wrong: {r['confirmed']}"
assert r["lab_only"]    == ["AAPL"],       f"lab_only wrong: {r['lab_only']}"
assert r["interp_only"] == ["MET"],        f"interp_only wrong: {r['interp_only']}"
assert r["confirmed_count"]   == 2
assert r["lab_only_count"]    == 1
assert r["interp_only_count"] == 1
print("2. reconcile_universes:      PASS")

# 3. get_lab_row
row = get_lab_row(lab, "wfc")   # lowercase input
assert row is not None,          "get_lab_row returned None for WFC"
assert row["Ticker"] == "WFC",   "Ticker should be uppercase"
assert get_lab_row(lab,"XYZ") is None, "Unknown ticker should be None"
print("3. get_lab_row:              PASS")

# 4. check_run_id_alignment
lab2 = [{"Run_ID":"20260521_212948","Ticker":"WFC"}]
ck   = check_run_id_alignment(lab2, "20260521_212948")
assert ck["match"] is True,                     "matching IDs should match"
ck2  = check_run_id_alignment(lab2, "20260522_000000")
assert ck2["match"] is False,                   "different IDs should not match"
assert ck2["lab_run_id"] == "20260521_212948"
ck3  = check_run_id_alignment([], "X")
assert ck3["match"] is False and ck3["lab_run_id"] == "UNKNOWN"
print("4. check_run_id_alignment:   PASS")

# 5. validate_lab_field_alignment — direction normalisation
lab_row  = {"Direction":"LONG_PUT","Verdict":"ARMED","IVP":"45"}
pipe_row = {"direction":"PUT",     "eil_v3_verdict":"ARMED","ivp":"47"}
conflicts = validate_lab_field_alignment(lab_row, pipe_row, "WFC")
# LONG_PUT vs PUT => no conflict (same direction after normalise)
dir_conflicts = [c for c in conflicts if c["field"]=="Direction"]
assert len(dir_conflicts) == 0, f"LONG_PUT vs PUT should not conflict: {dir_conflicts}"
# IVP 45 vs 47 => within ±5 tolerance, no conflict
ivp_conflicts = [c for c in conflicts if c["field"]=="IVP"]
assert len(ivp_conflicts) == 0, f"IVP 45 vs 47 within tolerance should not conflict"
print("5a. Direction normalisation: PASS")
print("5b. IVP tolerance:           PASS")

# 5c. Direction conflict — genuinely different
lab_row2  = {"Direction":"LONG_CALL","Verdict":"ARMED"}
pipe_row2 = {"direction":"LONG_PUT", "eil_v3_verdict":"ARMED"}
c2        = validate_lab_field_alignment(lab_row2, pipe_row2, "WFC")
dir_c2    = [c for c in c2 if c["field"]=="Direction"]
assert len(dir_c2) == 1,                 "CALL vs PUT should be a FLAG conflict"
assert dir_c2[0]["severity"] == "FLAG",  "Direction conflict must be FLAG"
print("5c. Direction FLAG conflict: PASS")

# 5d. Premium tolerance ±10%
lab_row3  = {"Premium_Mid":"1.00"}
pipe_row3 = {"premium":"1.05"}          # 5% diff → within 10%
c3        = validate_lab_field_alignment(lab_row3, pipe_row3, "WFC")
prem_c3   = [c for c in c3 if c["field"]=="Premium_Mid"]
assert len(prem_c3) == 0, "1.00 vs 1.05 within 10% should not conflict"
lab_row4  = {"Premium_Mid":"1.00"}
pipe_row4 = {"premium":"1.50"}          # 50% diff → outside 10%
c4        = validate_lab_field_alignment(lab_row4, pipe_row4, "WFC")
prem_c4   = [c for c in c4 if c["field"]=="Premium_Mid"]
assert len(prem_c4) == 1, "1.00 vs 1.50 outside 10% should conflict"
print("5d. Premium tolerance:       PASS")

# 6. build_lab_alignment_block
recon = {"confirmed_count":3,"lab_only_count":1,"interp_only_count":2,
         "interp_only":["MET","GS"]}
run_check = {"match":True,"lab_run_id":"20260521_212948","pipeline_run_id":"20260521_212948"}
block = build_lab_alignment_block(recon, "avshunter_signals_test.csv", run_check)
assert "LAB_ALIGNMENT" in block
assert "MATCH"         in block
assert "confirmed:    3" in block
assert "MET" in block and "GS" in block
print("6. build_lab_alignment_block:PASS")

# 7. build_lab_context_block
lab_full = {"Ticker":"WFC","Verdict":"ARMED","Direction":"LONG_PUT","IVP":"45","Run_ID":"20260521_212948"}
ctx = build_lab_context_block(lab_full, "WFC")
assert "LAB_CONTEXT_WFC" in ctx
assert "ARMED"           in ctx
assert "NOT_IN_LAB" not in ctx
# No lab row
ctx_absent = build_lab_context_block(None, "XYZ")
assert "LAB_NOT_CONFIRMED" in ctx_absent
print("7. build_lab_context_block:  PASS")

# 8. build_field_conflict_block
conflicts_in = [
    {"field":"Direction","lab_value":"LONG_CALL","pipeline_value":"LONG_PUT","severity":"FLAG"},
    {"field":"IVP",      "lab_value":"30",       "pipeline_value":"50",      "severity":"WARN"},
]
blk = build_field_conflict_block(conflicts_in, "WFC")
assert "LAB_FIELD_CONFLICTS_WFC" in blk
assert "2 conflicts"             in blk
assert "FLAG"                    in blk
assert "1 FLAG-level"            in blk
# No conflicts
blk_none = build_field_conflict_block([], "WFC")
assert "NONE" in blk_none
print("8. build_field_conflict_block:PASS")

# 9. load_lab_export — empty dir
from pathlib import Path
import tempfile, os
with tempfile.TemporaryDirectory() as td:
    rows, fname = load_lab_export(Path(td))
    assert rows == [] and fname == "", "Empty dir should return ([], '')"
print("9. load_lab_export (empty):  PASS")

# 10. Hard constraint — no forbidden imports
import ast
src = open("lab_reconciliation.py", encoding="utf-8").read()
tree = ast.parse(src)
forbidden = {"pipeline_interpreter_engine","pipeline_interpreter_commands",
             "pipeline_interpreter_outputs","interpreter_qa","thesis_registry"}
for node in ast.walk(tree):
    if isinstance(node, (ast.Import, ast.ImportFrom)):
        names = [a.name for a in getattr(node,"names",[])]
        mod   = getattr(node, "module", "") or ""
        for name in names + [mod]:
            for bad in forbidden:
                assert bad not in name, f"Forbidden import found: {name}"
print("10. Zero forbidden imports:  PASS")

print()
print("All self-tests PASS")
