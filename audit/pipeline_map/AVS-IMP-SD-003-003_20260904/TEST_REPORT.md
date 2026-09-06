# AVS-IMP-SD-003-003 — Test report

## Focused acceptance

Command scope:

- `tests/test_avs_sd003_blocker_closure.py`
- `tests/test_eod_options_research_handoff.py`
- `tests/test_handoff_contract_audit.py`
- `tests/test_macro_quant_packet.py`
- `tests/test_lab_governed_handoff.py`

Result: **40 passed, 0 failed**.

Covered behavior includes named stale-bar fallback states, stale source/as-of/age transport, deterministic advisory macro identity, EOD quote depth/quality/timestamp transport, Lab preservation, nine explicit semantic failure categories, and corroborated empty-shadow classification.

## Full regression

Command scope: `tests --ignore=tests/msi -q`

Result: **938 passed, 1 skipped, 43 subtests passed, 0 failed** in 474.72 seconds.

## Static validation

- `py_compile`: PASS.
- `git diff --check`: PASS, with line-ending notices only.

## Historical artefact replay

The corrected semantic audit was invoked read-only against run `20260904_004338`. It loaded Vanguard, Options Intelligence, EIL-enriched, Execution, EOD, Lab and shadow-book artefacts and returned 16 FAIL records. This is expected because the stored run predates the blocker fixes. It proves that the new audit detects the known bad handoff rather than granting it acceptance.

## Verdict

**OFFLINE BLOCKERS CLOSED. CONTROLLED LIVE CYCLE REQUIRED.**
