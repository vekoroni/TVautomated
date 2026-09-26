# D2 — The manifest reads EXECUTION_READY beside DEGRADED semantic health: root cause and design

**Date:** 2026-09-25 · **Owner of the change:** `contracts/lab_control.build_final_run_manifest`, existing owner of the run manifest · **Authority:** none changed; `run_tradeable` and every permission field unchanged (step 1: routing preserved) · **Requested by:** ACK ("carry on with D2"); reviewer amendment: "a grain-correct D2"

## 1. Symptom

Two consecutive manifests read `run_tradeable_label = EXECUTION_READY` beside `pipeline_semantic_health = DEGRADED` and 175–185 rows missing an invalidation. The one defect count carries no denominator, does not say how many rows lack a target, and does not say whether any actionable row is affected. The register's own figure for geometry recovery was wrong because of that missing grain (amendment A1).

## 2. Root cause (confirmed)

| Fact | Evidence |
|---|---|
| `missing_selected_handoff` holds a single count, `invalidation_spot`, over the morning-candidate rows with a CALL/PUT direction; the population is not written | `lab_control.py:2046-2072` |
| Missing targets are not counted anywhere in the manifest | same block |
| `run_tradeable` is decided by fatal flags, phase status and EIL row count only; semantic health never enters, so the label cannot express "ready, but rows have no geometry" | `lab_control.py:2100-2131` |
| The actionable grain (rows routed GO / GO_LIMIT) is available in the same CSV via `morning_execution_route` and is never used | 24 Sep book: route GO_LIMIT ↔ Lab GO 169 + GO_LIMIT 232 = 401 exactly |
| Consumers of the label only display it (`intelligence_lab.py:2773`); consumers of `run_tradeable` are the orchestrator log and `qa_live_uat_readiness` | grep |

## 3. Design (additive; the boolean and permissions untouched)

New manifest block `thesis_geometry_completeness`, computed over the same population the semantic score already uses:

```
population                    rows with a CALL/PUT direction
missing_target                target absent or non-positive
missing_invalidation          invalidation absent, non-positive, or state in the missing set (as today)
missing_both
complete
actionable_population         rows with morning_execution_route in {GO, GO_LIMIT}
actionable_missing_target
actionable_missing_invalidation
actionable_missing_both
```

Every count sits beside its denominator; nothing is a percentage without one.

`missing_selected_handoff.invalidation_spot` stays exactly as today (its consumers take the max over the dict's values, so a denominator cannot be added there).

`run_tradeable_label` *(25 Sep design, superseded by §7 on 26 Sep)*: when `run_tradeable` is true and any actionable row lacks a target or an invalidation, the label reads `EXECUTION_READY_ACTIONABLE_GEOMETRY_DEFECTS`; otherwise unchanged. The label is display; `run_tradeable`, `run_execution_permission`, `run_prep_permission` and `next_action` are not touched. A new `stale_flags` entry `ACTIONABLE_GEOMETRY_DEFECTS:<n>` accompanies it (which lowers `run_health_score` by 3, the same weight as every other stale flag).

**Invariants.** Labels say what was measured; units and denominators explicit (R3, R6). Nothing revived, nothing killed.

## 4. Tests (written first), `tests/test_d2_manifest_geometry_grain.py`

- Characterisation: with complete geometry the label, permissions and `missing_selected_handoff` are exactly as today.
- Counts by grain: rows missing target only, invalidation only, both; actionable subset counted separately; denominators present.
- Label downgrades only when an actionable row is affected; a non-actionable defect leaves `EXECUTION_READY` and still reports the count. *(Superseded by §7: the test now expects `REVIEW_REQUIRED_SEMANTIC_HANDOFF_DEFECTS` for a selected-handoff gap and `REVIEW_REQUIRED_ACTIONABLE_GEOMETRY_DEFECTS` for actionable geometry.)*
- `run_tradeable` and the permission fields are identical with and without defects.

## 5. Result (implemented 25 Sep 2026, uncommitted pending ACK)

| Item | Outcome |
|---|---|
| Change | `contracts/lab_control.py` +80 lines: `_thesis_geometry_completeness(candidate_rows, validated_rows)`, the block in the manifest, the `ACTIONABLE_GEOMETRY_DEFECTS:<n>` stale flag, the label qualifier. Geometry is read from the candidate rows (which carry `target_price` / `invalidation_spot` and no route); the route from the validated-trades rows by ticker |
| Finding during the build | The candidates file has no `morning_execution_route` and neither morning file has `structural_target`; the target field at this grain is `target_price`. The test fixture was reshaped to production's two-file layout before the change was made |
| Tests written first | `tests/test_d2_manifest_geometry_grain.py`: 1 characterisation, 5 business rules; all pass |
| Regression | big-bang phases 6–7 3/3, Lab ranking export 2/2, morning gate authority 20/20, options liquidity morning Lab 7/7, ILA golden 7/7, book integrity 24/24, A2 9/9 |
| Preview on this morning's real run (in memory, not written) | population 1,355 · missing target 224 · missing invalidation 175 · both 175 · complete 1,131 · actionable 273 with 0 missing · label unchanged `EXECUTION_READY` · legacy `missing_selected_handoff` unchanged at 175 |

The preview corrects one more register figure: 224 rows lack a target, and every row lacking an invalidation also lacks a target (175 both). Supplying a fallback invalidation alone would complete 0 rows on this book, not 63.

## 6. Acceptance *(superseded by §7)*

Monday's morning manifest shows the block with `population ≈ 1,500`, `missing_target` and `missing_invalidation` separately, `actionable_missing_* = 0` (today no GO row lacks geometry) and therefore `EXECUTION_READY` unchanged, with the defect counts visible beside it. If a degenerate or missing level ever reaches GO, the label says so.

## 7. Superseding INT-001 correction (26 Sep 2026)

The acceptance sentence above was superseded by stored-run scenario testing. A selected-handoff semantic gap is incompatible with a run-level `EXECUTION_READY` label even when no GO/GO_LIMIT row is affected. `build_final_run_manifest` now reports `REVIEW_REQUIRED_SEMANTIC_HANDOFF_DEFECTS` for that case and `REVIEW_REQUIRED_ACTIONABLE_GEOMETRY_DEFECTS` when actionable geometry is missing. The distinct counts and per-row execution routes remain intact; `run_tradeable` and the permission fields are not changed by this label correction. The old `EXECUTION_READY_ACTIONABLE_GEOMETRY_DEFECTS` label is retired; the geometry basis in `_thesis_geometry_completeness` moved to the shared `cumulative_expected_move_pct` resolver (INT-001 finding H2) so the manifest and the Evening thesis read one budget. The scenario replay for the stored TEST run (`tests/test_avs_int001_scenario_stored_run_replay.py`, r7–r9) showed the review-required label without rewriting its original artefacts; the D2 grain tests and `tests/test_a1_geometry_labels.py` were updated to the new labels (regression 526 passed on 26 Sep, receipt `Enhancements/assessment/AVS-INT-001_SCENARIO_TEST_RECEIPT_20260926.md`). Committed 26 Sep 2026 at ACK's instruction. A normal operator-started completed-session cycle (live proving) remains the acceptance gate.
