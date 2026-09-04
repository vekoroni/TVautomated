# AVS-TST-CYC2-001 — Cycle 2 Closure Report

**Role:** independent tester and closure gatekeeper. I did not implement, I fixed nothing, and I executed no pipeline stage.
**Mode:** production code and run data READ-ONLY. Source read `utf-8-sig`; SQLite opened `mode=ro`. All writes under `audit/pipeline_map/AVS-TST-CYC2-001/`.
**References:** `AVS-SD-001_solution_design.md` v0.2 · AVS-E2E-CODE-001 atlas · frozen baseline `data/output/runs/20260831_010309/` + `data/canonical/control_plane.sqlite`.

---

## Intake

| Item | Value |
|---|---|
| git HEAD | `5d886f07c1d290f25600e2e7e62ae77aad85476a` (master — *"Pre-remediation snapshot"*) |
| Working tree | **DIRTY**: 134 untracked, 73 modified, 32 deleted |
| Cycle-2 tag | **none** (tags present are all pre-existing baselines) |
| Code delta since Cycle 1 | **16 files**, incl. new `contracts/governed_states.py`, new `tests/test_cycle2_governance.py`, new `tests/test_governed_states.py` |
| Evening run supplied | **NONE** — newest run is the frozen baseline |
| Morning run supplied | **NONE** |
| Claim sheet | **NOT SUPPLIED** |

**Substantive implementation has landed since Cycle 1.** Five of the seven fixes now verify PASS. Two fail, and the release-evidence stage has nothing to evaluate.

---

## Stage 1 — Are the seven fixes implemented? **FAIL (5 PASS / 2 FAIL)**

| # | Fix | Expected | Actual | Verdict |
|---|---|---|---|---|
| **F1** | Invalidation-side invariant | rejects an invalidation on the thesis side of entry, symmetric to the target check | **PRESENT.** `contracts/options_liquidity_lifecycle.py:426-430`: `invalidation_geometry = direction * (origin - invalidation)`; raises when `<= 0`. Sits immediately before `invalidated` is computed and mirrors the target check at `:433`. | **PASS** |
| **F2** | Hold restricted to {5,10,20} | domain assert + routed hold at the call site | **PRESENT.** `:109-110` raises *"remaining_hold_sessions must be a governed routed hold in {5, 10, 20}"*. Call site derives `planned_hold_sessions` 5/10/20/None from the horizon endpoint (`options_intelligence:4124-4130`) and stamps `planned_hold_source = HORIZON_BUCKET_ENDPOINT_V1 | UNROUTED` (`:4163-4164`). **Zero** legacy-alias feeds remain. | **PASS** |
| **F3** | Named non-directional state | `NOT_EVALUATED_NON_DIRECTIONAL`, never INVALIDATED | **PRESENT** at five production call sites: `options_intelligence:4581,:4588`, `exit_rules_engine:87`, `morning_gate:1461`, `eod_candidate_engine:1461`. | **PASS** |
| **F4** | Fabricated stop removed | no `entry × 0.97`; stopless rows carry `MISSING_AUTHORITATIVE_STOP` | **PRESENT.** Zero `entry*0.97` matches remain. `MISSING_AUTHORITATIVE_STOP` now emitted from the enum at `options_intelligence:4029,:4108` and `morning_gate:1472`. | **PASS** |
| **F5** | Canonical state vocabulary | one enum, one module, no redefinitions | **SPLIT.** The enum exists and is correct — `contracts/governed_states.py` carries all eight `GovernedDataState` values plus four `LifecycleEvaluationState` values. **But 10 bare `"CONTRACT_REPAIR_REQUIRED"` literals persist outside it** (`options_intelligence:6373,:6427,:6745,:7814`; `eod_candidate_engine:560,:566,:1108,:1388,:1492,:1505`). The gate says *each redefinition is a FAIL*. The other seven states show zero redefinitions. | **FAIL** |
| **F6** | Supersession persistence | four columns + superseded status; corrections insert | **PRESENT.** All four columns (`calculation_version`, `supersedes_event_id`, `correction_reason`, `corrected_by_run_id`) on all three lifecycle tables; writer declares them at `canonical_data/option_liquidity_lifecycle.py:118-120,:161-163,:182-184,:272-274`; `SUPERSEDED_DATA_DEFECT` in the enum. *(How the migration was applied is a Stage 3 failure — see CYC2-DEF-001.)* | **PASS** |
| **F7** | Corrected regression tests | CALL, PUT and non-directional variants for every geometry/lifecycle test | **FAIL.** `tests/test_cycle2_governance.py` (4 tests, read in full) is **CALL ×3, STRANGLE ×2, PUT ×0**. Two of its four tests are CALL-only on business-critical geometry. | **FAIL** |

**Stage 1 fails on F5 and F7.** Per the sequencing rule, Stages 2–6 are **BLOCKED-BY-STAGE-1**.

### The F7 finding, stated precisely

This is a **coverage** failure, not a correctness failure — and the distinction matters. My own fixtures supply the missing PUT variant and it **passes**:

```
CYC2.F1.wrong_sided_raises [PUT] raised=True
  ValueError: invalidation_spot must be beyond thesis_spot opposite the option direction
```

So the fix is correct on both sides. What is missing is the *test that would notice if it stopped being correct* — on the exact direction that produced 437 of the 442 production false invalidations. A PUT regression in this code would ship green.

---

## Stage 2 — Offline testing **BLOCKED-BY-STAGE-1** (evidence gathered)

| Item | Expected | Actual | Verdict |
|---|---|---|---|
| Focused Cycle-2 fixtures | zero failures | **17/17 PASS**, full three-direction matrix — `fixtures/t_cyc2_fixtures.py` | PASS |
| Existing regression suite | zero new failures | **6/6 pass** (`test_cycle2_governance` 4/4, `test_governed_states` 2/2). **`pytest` is not installed**, so I executed the modules directly; no full-suite baseline diff was possible | PASS (partial) |
| Three-direction coverage by count | all business-critical tests | see F7 — **FAIL** | FAIL |
| DB migration / replay / rollback **on a copy** | schema matches, 442 replay → 0, rollback byte-identical | **BLOCKED.** The migration has already been applied **to the production/frozen database**, and **no backup exists** — there is no pre-migration state to roll back to or byte-compare against | BLOCKED |
| Replay of the 442 | originals preserved as superseded | **BLOCKED.** `supersedes_event_id IS NOT NULL` → **0 rows**; `correction_reason IS NOT NULL` → **0 rows** | BLOCKED |

Integrity guard: I hashed `control_plane.sqlite` before and after every fixture and test execution. Hash `a2a68a95…` **unchanged throughout** — my testing mutated nothing.

---

## Stage 3 — Release evidence **FAIL**

| Item | Expected | Actual | Verdict |
|---|---|---|---|
| Claim sheet mapping F1–F7 → file:line + proving tests | present, spot-verified | **NOT SUPPLIED** | FAIL |
| Production-file manifest with SHA-256 | present, all match | **NOT SUPPLIED** | FAIL |
| Lifecycle DB backup, hashed, restorable | present | **NO BACKUP EXISTS** — only the live DB and its WAL sidecars | FAIL |
| Controlled git baseline, only approved changes | release tag/commit | **No cycle-2 tag; HEAD is still the pre-remediation snapshot; 239 dirty entries** | FAIL |

### CYC2-DEF-001 — the frozen baseline was modified

`data/canonical/control_plane.sqlite` is designated frozen and *never modified*. It has been migrated in place:

| Measurement | Cycles 0–1 | Now |
|---|---|---|
| mtime | 2026-08-31 **02:31:17** | 2026-08-31 **22:59:22** |
| supersession columns | **0 of 4** | **4 of 4**, all three tables |
| `calculation_version` | absent | backfilled `option_liquidity_lifecycle_v1` × 1507 |
| row counts | 1507 / 1021 / 1021 | **1507 / 1021 / 1021 — unchanged** |

No data was lost, and the schema change is the one F6 requires. But the *pre-fix reference* is gone and **no backup was taken**, so Stage 2's rollback test and Stage 3's restorability check have no known-good state to verify against.

---

## Stages 4, 5, 6 — **AWAITING** (and BLOCKED-BY-STAGE-1)

All artefact-level acceptance is unmeasurable: **no candidate Evening run exists.** The seven fixes are verified statically and behaviourally but have **never been observed producing a pipeline artefact**.

Runs I need the operator to execute (I will not execute them):

1. **An Evening run** against the current tree → unblocks Stage 4 in full.
2. **A Morning Gate run over that Evening run** → unblocks Stage 5. I will hash every EOD column set and the run manifest immediately before it, and compare after.
3. Stage 6 follows from 1 and 2 with no further run.

---

## Discrepancies recorded (design wins)

1. **Line drift.** The prompt cites `:4546` (hold) and `:3801-3808` (fabricated stop). Both regions have been edited and renumbered. Not a defect — evidence of work — but line-anchored gates will produce false ABSENTs and must be re-anchored.
2. **F3 form.** Design §3.5 asks for a named state. The contract itself still *raises* for non-directional sides (`:86`), while the named state is applied at the five call sites. Behaviour satisfies "never INVALIDATED"; the form differs from the gate wording. Recorded, not silently passed.
3. **Tester instrument.** Two bounded greps returned false negatives this cycle (`NOT_EVALUATED_NON_DIRECTIONAL`, `entry*0.97`), both silently empty. F3 was corrected **from ABSENT to PASS** on re-verification. Any ABSENT from a bounded grep in this suite is now re-checked on a narrower path set before filing (CYC2-DEF-008).

---

## Defects

`CYC2_defects.csv` — 8 rows: **5 × P1**, 3 × P2. Open P0/P1 count: **5**.

| ID | Sev | Summary |
|---|---|---|
| CYC2-DEF-001 | P1 | Frozen baseline DB migrated in place; no backup |
| CYC2-DEF-002 | P1 | F7 — zero PUT variants in the Cycle-2 governance tests |
| CYC2-DEF-003 | P1 | F5 — 10 bare `CONTRACT_REPAIR_REQUIRED` literals outside the enum |
| CYC2-DEF-004 | P1 | No claim sheet, manifest, backup record or release tag |
| CYC2-DEF-005 | P1 | No candidate Evening run; Stages 4–6 unmeasurable |
| CYC2-DEF-006 | P2 | The 442 false invalidations not yet superseded |
| CYC2-DEF-007 | P2 | `pytest` unavailable; no full-suite baseline diff |
| CYC2-DEF-008 | P2 | Tester's own grep produced two false negatives |

---

## Closure decision

Stage 1 contains FAILs (F5, F7), so the cycle cannot be **IMPLEMENTED — AWAITING LIVE-CYCLE ACCEPTANCE**, which requires Stages 1–3 fully PASS. Stage 3 additionally has four FAILs and Stages 4–6 are unrun.

The engineering is close: **F1, F2, F3, F4 and F6 all verify PASS on independent measurement**, and the core geometry behaves correctly on CALL, PUT and all four non-directional variants. What blocks closure is two narrow code items, absent release evidence, and a mutated baseline.

CYCLE 2 STATUS: FAILED — REMEDIATION REQUIRED. Evening run: NONE. Morning run: NONE. Open P0/P1 defects: 5.
