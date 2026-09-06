# AVS-IMP-SD-003-002 — Test report

## Acceptance result

**OFFLINE IMPLEMENTATION ACCEPTED; LIVE CAPABILITY ACTIVATION PENDING**

### Focused authority regression

Command scope:

- `tests/test_execution_monetisability_gate.py`
- `tests/test_olm_execution_authority.py`
- `tests/test_avs_sd003_authority_boundaries.py`

Result: **42 passed, 0 failed**.

This includes explicit adversarial cases for:

- a directional execution row with no governed invalidation;
- a legacy numeric stop attempting to substitute for governed state;
- a wrong-sided CALL invalidation;
- an EOD row with a numeric invalidation but no `AVAILABLE` state;
- preservation of OLM lifecycle, quote viability, contract identity and advisory monetisability behavior.

### Complete production regression

Scope: `tests/`, excluding the historical read-only defect-assertion directory `tests/msi/`.

Result: **933 passed, 1 skipped, 43 subtests passed, 0 failed** in 491.48 seconds.

### Static and recovery checks

| Check | Result |
|---|---|
| `py_compile`, changed production Python modules | PASS |
| `git diff --check` | PASS |
| Rollback SQLite `PRAGMA quick_check` | `ok` |
| Capability default | completed-profile stage OFF |

### Remaining tests

Live provider acquisition, cold-cache, warm-cache and Morning Gate continuity checks are release activation tests. They are not replaceable with mocks and have not been represented as completed.

