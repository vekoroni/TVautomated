# AVS-VERIFY-001 v1.2: run verification agent

The verifier has two layers. Both are read-only and advisory; neither blocks the Lab.

1. **`avs_verify.py`** is a deterministic checker. It uses only the standard library and takes about 10 s on a 200 MB book. The same book always gets the same verdict.
2. **The `avs-verifier` Claude Code agent** (`.claude\agents\avs-verifier.md`) runs the checker and then challenges it. It checks the column map, confirms each P0 against raw rows, checks that Morning didn't re-derive the Evening thesis, and gives a confidence rating on every finding.

The rules were calibrated on 28 Sep 2026 against run `20260927_205123`.

## Run it after every Evening and Morning run (from the repo root)
```powershell
C:\Python314\python.exe tools\avs_verify\avs_verify.py --run-id <RUN_ID> --phase evening
C:\Python314\python.exe tools\avs_verify\avs_verify.py --run-id <RUN_ID> --phase morning
```
For the full review, tell Claude Code: `use the avs-verifier agent on run <RUN_ID> morning`

Output goes to `audit\verify\<run_id>\<phase>\`: `verify_report.md`, `verify_report.json` and `row_flags.csv`. The CSV has one line per tradeable row, with `clean` set to True or False.

| Exit | Verdict | Meaning |
|---|---|---|
| 0 | TRUST | Every rule passed. |
| 1 | TRUST_WITH_CAVEATS | No book-level P0. Trade only rows with `clean=True`, and read the caveats. |
| 2 | DO_NOT_TRADE | At least one book-level P0. |
| 3 | UNVERIFIED | A critical column is missing, or a P0 check had no evidence (`UNCERTAIN`). Missing evidence is never a pass. |

## What it checks
Book-level checks cover the whole book. Row-level checks cover only tradeable rows: `final_action` BUY_* for the Lab book, `morning_gate_verdict` GO for Morning.

**Book-level P0**
- R00: the pipeline's own manifest says not tradeable (`run_tradeable`, capital or execution permission, technical health, `fatal_flags`)
- R01: Evening run inside the trading session
- R02: duplicate headers with conflicting values
- R03: critical columns missing, or >2% null on tradeable rows
- R16: spread unit missing or implausible
- R20: two authorities disagree on ≥50% of tradeable rows (e.g. `final_action` BUY vs `lab_verdict` BLOCKED)
- R24: manifest row count ≠ book row count
- R19: quotes stale by both the independent age and the pipeline's own age

- R15_HOLD_DERIVED: the hold must be an analysis output per trade (intraday to 20+ sessions, no cap). One value on every row, or a config-constant source such as `THESIS_WINDOW_D2`, fails. It is registered as a known defect until the hold wiring is fixed

**Row-level P0**
- R10: direction not CALL/PUT
- R11: missing spot, target or stop
- R12: level on the wrong side, or live price already through the stop
- R13: bid > ask
- R14: OCC contract type or delta sign contradicts direction
- R15: DTE < hold
- R21: probability outside 0–1

**P1 caveats**
- R19: quotes >15 min old at the time the verdict was stamped
- R18: target >3× the expected move over the hold
- R16: spread ≥10% or ≥25% of mid
- R01: Morning run outside 09:35–09:45 ET
- duplicate identical headers
- degraded health flags
- known defects

## Known defects
Rules listed under `known_defects` in `avs_verify_rules.json` still report, but as a P1 instead of a P0, so a known, unfixed defect doesn't turn every night into DO_NOT_TRADE. Remove an entry once the fix is CLOSED with a run artefact.

## Keep it honest
When a new error reaches you that the verifier missed, add a rule for it. That is how the same error gets caught before it can reach you a second time.
