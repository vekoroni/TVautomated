# AVS-TEV-001: pre-option structural cohort audit (27 September 2026)

Scope: offline, read-only inspection of six completed run packages. No pipeline
run, broker request, database write, model fit, production switch, or trade
authority was performed. The cohort builder is additive research code only.

## Cohort rule tested

A numeric first-passage label requires an option-neutral Discovery row with
`DISCOVERY_GOVERNED` direction, a `WYCKOFF` structural target, a
`WYCKOFF_VALIDATION` governed invalidation, valid side-correct geometry, and
completed-session non-stale price evidence. `PENDING_OI`, option-stage `TARGET_3R`,
an unsourced stop, a stale bar, or a bar from another session cannot be treated
as a frozen pre-option forecast. Rows with incomplete geometry remain visible
as descriptive starts, not silently transformed into training labels.

| Run | WYCKOFF target rows | Governed, sourced, side-correct target/stop | Of these, stale prior-session bars | Eligible before price-version parity |
|---|---:|---:|---:|---:|
| 20260824_100301 | 150 | 0 | 0 | 0 |
| 20260901_082437 | 76 | 0 | 0 | 0 |
| 20260905_151448 | 70 | 42 | 1 | 41 |
| 20260910_150045 | 83 | 50 | 1 | 49 |
| 20260916_223756 | 69 | 36 | 1 | 35 |
| 20260926_173730 | 134 | 71 | 1 | 70 |
| **Total** | **582** | **199** | **4** | **195** |

The August run lacks populated governed direction/stop; 1 September has
`DISCOVERY_PRELIMINARY_ONLY` direction and no governed stop. The four later
runs have four distinct evidence sessions (4, 10, 16, 25 September), not 195
independent date blocks. The 20th future XNYS session for those starts is
5, 8, 14, and 23 October respectively. **As of 27 September, zero of these
195 starts has a matured 20-session path.** The provisional design floor of
30 independent 20-session blocks therefore fails decisively in this sampled
cohort; no C4 numeric baseline or 20-session probability is claimed.

This is a **six-run sample**, not a census of every repository run. Counts are
based on the run-scoped Discovery CSV and final manifest. The 195 count is
*before* point-in-time price-version parity, de-duplication across same
ticker/session starts, outcome-path completeness, or option quote checks.
Even a complete underlying first-passage label is not an executable
ask-to-bid option return. The completed-session evidence date was derived
from each final manifest's UTC publication timestamp using the XNYS calendar.

## Next safe acceptance steps

1. Reconcile each eligible Discovery reference price and source timestamp to
   the canonical as-of bar/version at its original decision cut. Exclude or
   explain discrepancies before labeling.
2. Audit all completed runs, deduplicate ticker–session–geometry starts, and
   report 1/5/10/20-session target-first, stop-first, unresolved, missing,
   and same-bar ambiguity separately. Do not turn the descriptive cohort into
   a numeric forecast by lowering support floors after looking at outcomes.
3. Keep C4 `NOT_ESTIMABLE` at unsupported horizons; continue collecting
   independently dated, fully governed starts. Test the contract-expression
   path separately against exact option identity and quote economics.

Regression: `tests/test_avs_tev001_structural_cohort.py` checks sourced
geometry, pending option targets, wrong-side stops, unsourced stop markers,
and stale/wrong-session bars. The cohort code is
`audit/avs_tev001_structural_cohort.py`. Neither is called by production.
