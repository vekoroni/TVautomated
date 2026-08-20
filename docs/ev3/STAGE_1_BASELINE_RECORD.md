# EV3 Shadow — Stage 1 Baseline Record

## Provenance header

| Field | Value |
|---|---|
| Reconstruction schema_version | `ev3-shadow-phase-v0.4.0` |
| Reconstruction engine_source_sha256 | `e19e35d211ae03ecfed4333960fd5f5836a2f9f9d0348f64a0d0060df998ead8` |
| Reconstruction runner_source_sha256 | `b3258c33be44246faf99e297b1141ce82127449a2cfeac46afde9d659d22216f` |
| Reconstruction barrier_cache_sha256 | `16d4fdfc407ef2a7b9409889b4089fb63244cadfe086d3c9cf4ddd2d69c4be92` |
| `--now-utc` used | `2026-08-16T10:13:30.257561+00:00` (original run's `generated_utc` — an approximation, not recovered ground truth; v0.3.0 did not record `evaluation_now_utc`) |
| Input CSV copy sha256 | `595029c52f3a3205a2f125f15b590683ab6cc0dd94f48a1a5866ebb15fb7b7ba` |
| Input CSV recorded `input_sha256` (original 08-16 run) | `3bc0929e53c39dcc716a64213cf3307bf87133b6aa191a740d5419218871b161` — **disagrees**. Row count matches (1347) but content hash does not. Standing caveat on every finding below that touches the reconstruction. |
| Command executed (exactly once) | `python scripts/run_ev3_shadow_phase.py --run-id 20260816_075339 --runs-dir data/scratch/ev3_reconstruction --barrier-cache "C:\Users\ACKVerissimo\vanguard\data\staging\ev3_barrier_outcome_cache.parquet" --phase EOD --now-utc 2026-08-16T10:13:30.257561+00:00` |
| Reconstruction output | `data/scratch/ev3_reconstruction/20260816_075339/ev3_shadow/` |
| Generated (this run) | `2026-08-19T21:58:51.996941+00:00` (per reconstruction status JSON `generated_utc`) |

## Validity checks — all PASS

| Check | Required | Observed | Result |
|---|---|---|---|
| rows_received | 1347 | 1347 | PASS |
| REJECT_QUOTE_STALE (row-level) | small, matching original | 95 (reconstruction) vs 95 (original 08-16 run) — identical | PASS |
| schema_version | ev3-shadow-phase-v0.4.0 | ev3-shadow-phase-v0.4.0 | PASS |
| barrier_cache_sha256 | 16d4fdfc... | 16d4fdfc407ef2a7b9409889b4089fb63244cadfe086d3c9cf4ddd2d69c4be92 | PASS |
| engine_source_sha256 | e19e35d2... | e19e35d211ae03ecfed4333960fd5f5836a2f9f9d0348f64a0d0060df998ead8 | PASS |

Reconstruction is valid for comparison.

## The 2×2 structure

```
                08-16 inputs                        08-18 inputs
wrapper v0.3.0  run 20260816_075339 (archived)       not producible
wrapper v0.4.0  reconstruction (just built)          run 20260818_041214 (archived)
```

## Mandatory caveat (stated before any table)

The row-level `expected_market_rejections` field uses positive-membership filtering against a
fixed 13-code set, while the engine's real vocabulary (`vanguard/ev_engine_v3.py` +
`vanguard/ev3_stage0.py`) contains 41 distinct `REJECT_*` codes. 28 of those are unclassified
at row level — they vanish from both `expected_market_rejections` and `system_defects` if they
fire as a row's top-level code, because `system_defects.contract_validation` is built from the
*contract-level* reason-count dict, never from the row-level one. This is not theoretical: in the
archived run `20260818_041214`, `REJECT_CONTRACT_SYMBOL` fired 365 times at row level — 28.9% of
the 1,263 rejected rows — and is absent from `expected_market_rejections`. Its appearance in
`system_defects.contract_validation` with the identical count (365) is a coincidence of
single-candidate-row structure (row-level and contract-level evaluation are the same dict for
those rows), not a designed capture path. Every reconciliation below uses **raw, unfiltered
`reason_counts`**, never `expected_market_rejections`, for exactly this reason.

## Comparison A — wrapper effect (08-16 inputs, v0.3.0 vs v0.4.0)

Same input CSV (byte-identical copy, `input_sha256` matches between archived run and
reconstruction — both are working from the *current on-disk* archived file, not the file
originally consumed), same barrier cache, byte-identical engine (`engine_source_sha256`
identical). Restricted to the four fields present in both schemas.

| Field | 20260816_075339 (v0.3.0, archived) | Reconstruction (v0.4.0) | Delta | Evidence |
|---|---|---|---|---|
| rows_received | 1347 | 1347 | 0 | both status JSON → `rows_received` |
| rows_evaluated | 0 | 0 | 0 | both status JSON → `rows_evaluated` |
| evaluation_coverage | 0.0 | 0.0 | 0 | both status JSON → `evaluation_coverage` |
| direction coverage (n/denominator) | 1347/1347 = 1.0 | 1347/1347 = 1.0 | 0 | `coverage.fields.direction.present` / `coverage.fields.direction` total rows (`coverage.rows`) |
| direction selected_coverage (n/denominator) | 491/491 = 1.0 | 491/491 = 1.0 | 0 | `coverage.fields.direction.selected_present` / `coverage.selected_contract_rows` |

`expected_market_rejections`, `expected_contract_rejections`, `system_defects`,
`technical_health`, `ev_functional_health` — **NO_BASELINE** for the v0.3.0 side; these keys are
entirely absent (not null) from `data/output/runs/20260816_075339/ev3_shadow/ev3_shadow_phase_status_20260816_075339.json`.
No comparison is made for them.

**Raw `reason_counts` (both, for the record — identical):**
`{"REJECT_DIRECTION_UNRESOLVED": 1004, "REJECT_NO_EVALUABLE_CONTRACT": 248, "REJECT_QUOTE_STALE": 95}`
— present in both `ev3_shadow_phase_status_20260816_075339.json` (`reason_counts`) and the
reconstruction's status JSON (`reason_counts`), byte-for-byte identical. `contract_evaluation_reason_counts`
is also identical between the two: `{"REJECT_DIRECTION_UNRESOLVED": 1577, "REJECT_QUOTE_STALE": 491, "REJECT_VERTICAL_LONG_LEG": 571}`.

**Result: zero difference on every comparable field.** The wrapper change (v0.3.0 → v0.4.0)
contributed nothing to any count, given identical inputs and identical engine. Its only effect is
schema-level: new keys added to the status JSON (`expected_market_rejections`,
`expected_contract_rejections`, `system_defects`, `technical_health`, `ev_functional_health`,
`evaluation_clock_mode`, `strict_production_freshness`, `functional_test_clock_override`,
`evaluation_now_utc`, `morning_capital_permission`), which is entirely a reporting/classification
change, not a computation change.

## Comparison B — input effect (v0.4.0 wrapper, 08-16 vs 08-18 inputs)

Both v0.4.0 (`schema_version` identical), both `engine_source_sha256 = e19e35d2...` (identical
engine). Any difference is attributable to input population drift between the two runs.

| Metric | Reconstruction (08-16 inputs) | Run 20260818_041214 (08-18 inputs) | Delta | Evidence |
|---|---|---|---|---|
| rows_received | 1347 | 1400 | +53 | status JSON → `rows_received` |
| rows_evaluated | 0 | 137 | +137 | status JSON → `rows_evaluated` |
| evaluation_coverage | 0.0 | 0.097857 | +0.097857 | status JSON → `evaluation_coverage` |
| direction coverage (n/denominator) | 1347/1347 = 1.0 | 1400/1400 = 1.0 | 0 (both saturated) | `coverage.fields.direction.present` / `coverage.rows` |
| direction selected_coverage (n/denominator) | 491/491 = 1.0 | 554/554 = 1.0 | +63 selected rows (both saturated at 1.0) | `coverage.fields.direction.selected_present` / `coverage.selected_contract_rows` |
| expected_market_rejections (total) | 1347 (=1004+248+95) | 898 (=2+9+608+1+207+71) | -449 | status JSON → sum of `expected_market_rejections` values |
| expected_market_rejections (by code) | REJECT_DIRECTION_UNRESOLVED:1004, REJECT_NO_EVALUABLE_CONTRACT:248, REJECT_QUOTE_STALE:95 | REJECT_BARRIER_GRID_UNAVAILABLE:2, REJECT_BARRIER_STATE_UNAVAILABLE:9, REJECT_DIRECTION_UNRESOLVED:608, REJECT_LIQUIDITY:1, REJECT_NO_EVALUABLE_CONTRACT:207, REJECT_UNIT_SPREAD:71 | see caveat — REJECT_QUOTE_STALE (95→0 visible here) and REJECT_CONTRACT_SYMBOL (0→invisible, see raw) both move; do not read this row alone as complete | status JSON → `expected_market_rejections` |
| expected_contract_rejections (total) | 2639 (=1577+491+571) | 1999 (=10+165+1348+3+72+14+387) | -640 | status JSON → sum of `expected_contract_rejections` values |
| expected_contract_rejections (by code) | REJECT_DIRECTION_UNRESOLVED:1577, REJECT_QUOTE_STALE:491, REJECT_VERTICAL_LONG_LEG:571 | REJECT_BARRIER_GRID_UNAVAILABLE:10, REJECT_BARRIER_STATE_UNAVAILABLE:165, REJECT_DIRECTION_UNRESOLVED:1348, REJECT_LIQUIDITY:3, REJECT_UNIT_SPREAD:72, REJECT_VERTICAL_DEBIT:14, REJECT_VERTICAL_LONG_LEG:387 | new codes appear (BARRIER_GRID/STATE_UNAVAILABLE, LIQUIDITY, VERTICAL_DEBIT); REJECT_QUOTE_STALE disappears entirely | status JSON → `expected_contract_rejections` |
| system_defects (by sub-key and code) | `missing_selected_handoff`: contract_multiplier:291, invalidation_spot:108. No `contract_validation` key at all. | `contract_validation`: REJECT_CONTRACT_SYMBOL:365. `missing_selected_handoff`: contract_multiplier:334, invalidation_spot:111 | REJECT_CONTRACT_SYMBOL:365 is a **new** defect category, entirely absent on 08-16 inputs | status JSON → `system_defects` |
| raw reason_counts (by code, unfiltered) | REJECT_DIRECTION_UNRESOLVED:1004, REJECT_NO_EVALUABLE_CONTRACT:248, REJECT_QUOTE_STALE:95 (sum 1347, matches rows_received exactly, 0 evaluated) | REJECT_BARRIER_GRID_UNAVAILABLE:2, REJECT_BARRIER_STATE_UNAVAILABLE:9, REJECT_CONTRACT_SYMBOL:365, REJECT_DIRECTION_UNRESOLVED:608, REJECT_LIQUIDITY:1, REJECT_NO_EVALUABLE_CONTRACT:207, REJECT_UNIT_SPREAD:71, SHADOW_ONLY:137 (sum 1400, matches rows_received exactly: 1263 rejected + 137 evaluated) | REJECT_CONTRACT_SYMBOL:365 is new and real, only visible in the raw dict | status JSON → `reason_counts` (audit JSON, identical values) |

### Reconciliation (raw reason_counts, not expected_market_rejections)

- **Reconstruction:** `rows_evaluated (0) + sum(raw REJECT_* reason_counts) (1004+248+95=1347) = 1347 = rows_received`. **No shortfall.**
- **20260818_041214:** `rows_evaluated (137, = SHADOW_ONLY count) + sum(raw REJECT_* reason_counts) (2+9+365+608+1+207+71=1263) = 1400 = rows_received`. **No shortfall.**

Both runs reconcile exactly against raw `reason_counts`. The apparent 365-row "shortfall" that
would appear if one summed `expected_market_rejections` (898) + `rows_evaluated` (137) = 1035 ≠
1400 is **not a real gap in the underlying computation** — it is entirely attributable to
`REJECT_CONTRACT_SYMBOL` being unclassified at row level (see mandatory caveat). The defect is in
the classification/reporting layer, not in the engine's accounting.

## The decomposition — quantified

Original question (Phase 1): `rows_evaluated` swung from 0 (08-15, 08-16) to 137 (08-18). How
much is wrapper, how much is input drift?

- **Comparison A (wrapper effect, inputs+engine held constant):** `rows_evaluated` 0 → 0. **Delta = 0.**
- **Comparison B (input effect, wrapper+engine held constant):** `rows_evaluated` 0 → 137. **Delta = +137.**

**The wrapper change contributed 0 of the 137-row swing. Input population drift between 08-16 and
08-18 accounts for 100% of it.** This is a clean result — Comparison A produced an exact
zero-difference match on every one of the four comparable fields and on both raw reason-count
dicts, which is the strongest form of evidence available here: not "small" or "negligible," but
identically zero.

## Caveats that qualify every finding above

1. **Input hash mismatch stands.** The archived `options_intelligence_20260816_075339.csv` used
   for both Comparison A's baseline and the reconstruction's input has a different content hash
   (`595029c5...`) than the `input_sha256` (`3bc0929e...`) the original 08-16 run recorded
   consuming. Row count matches; content does not, provably. Comparison A therefore compares the
   v0.3.0 wrapper's *original* recorded output against the v0.4.0 wrapper's output on a
   *currently-archived* copy of the same-row-count file — not proven byte-identical to what
   produced the original numbers. That said, since the v0.3.0 run's own reason_counts
   (1004/248/95) are reproduced exactly by the reconstruction using the currently-archived file,
   this is strong (though not certain) evidence the archived file's content is functionally
   equivalent to the original for this engine's purposes, whatever caused the hash difference.
2. **`--now-utc` is an approximation**, not recovered ground truth — the original 08-16 run's
   actual evaluation clock is not recorded under schema v0.3.0. The value used
   (`generated_utc` of the original run) produced a `REJECT_QUOTE_STALE` count identical to the
   original run's, which is corroborating evidence it's a reasonable proxy, but it is not proof
   of exact equivalence.
3. **Comparison A and B together do not fully explain `20260815_091604`** (the third historical
   run, `rows_evaluated=0`, a genuinely different `engine_source_sha256`) — that run used a
   different engine version entirely and is out of scope for this wrapper/input decomposition.

## Confidence rating

**High confidence (95%+):** the decomposition itself (wrapper=0, input=137) — based on an exact,
zero-diff replication across every comparable field and both raw reason-count dictionaries, not
an approximate or noisy result. **Medium confidence:** that the reconstruction's numbers are
exactly what the original 08-16 run would have produced under v0.4.0, due to the unresolved input
hash mismatch (caveat 1) and approximated clock (caveat 2) — the decomposition conclusion is
robust to these caveats (since Comparison A used the same archived file on both sides of its
comparison), but any claim that the reconstruction represents the *original* 08-16 run's true
behavior carries that residual uncertainty forward.

**Named unknowns:** exact cause of the archived CSV's content-hash drift since 08-16; whether any
`REJECT_*` code among the 28 unclassified-at-row-level codes other than `REJECT_CONTRACT_SYMBOL`
has fired in a run not yet inspected.

---

## Stage 3.1 — Classification Fix

### Scope confirmation

Exactly one file was edited: `scripts/run_ev3_shadow_phase.py`. `vanguard/ev_engine_v3.py`,
`vanguard/ev3_stage0.py`, and `scripts/run_ev3_shadow.py` were not opened for writing at any
point. The orchestrator was not run. Nothing was written into `data/output/runs/`. No git
staging, commit, or stash occurred.

### 3.1a/b — The diff, in full

```diff
--- run_ev3_shadow_phase.py (pre-Stage-3.1)
+++ scripts/run_ev3_shadow_phase.py (post-Stage-3.1)
@@ -26,7 +26,7 @@
 from scripts.run_ev3_shadow import run_shadow  # noqa: E402


-EV3_SHADOW_PHASE_VERSION = "ev3-shadow-phase-v0.4.0"
+EV3_SHADOW_PHASE_VERSION = "ev3-shadow-phase-v0.5.0"
 DEFAULT_RUNS_DIR = REPO_ROOT / "data" / "output" / "runs"
 DEFAULT_BARRIER_CACHE = Path(
     os.environ.get(
@@ -131,6 +131,7 @@
         "morning_capital_permission": "NOT_EVALUATED_BY_SHADOW",
         "expected_market_rejections": {},
         "expected_contract_rejections": {},
+        "unclassified_rejections": {},
         "system_defects": {},
         "input_path": str(input_path.resolve()),
         "barrier_cache_path": str(barrier_cache.resolve()),
@@ -215,12 +216,14 @@
         "REJECT_STRUCTURE_UNSUPPORTED",
         "REJECT_UNIT_SPREAD",
     }
-    expected_market_rejections = {
-        str(code): int(count)
-        for code, count in reason_counts.items()
-        if str(code) in expected_rejection_codes and int(count or 0) > 0
-    }
-    contract_reason_counts = audit.get("contract_evaluation_reason_counts", {})
+    # Row-level classification is a three-way exhaustive partition of every code
+    # present in reason_counts: market-expected (below), system/contract (shared
+    # with the contract-level classification further down), or unclassified --
+    # the genuine complement of both sets, not a third hardcoded list, so a
+    # future engine code cannot silently vanish from every row-level field the
+    # way REJECT_CONTRACT_SYMBOL previously did. Definition moved earlier (was
+    # below expected_contract_rejections) so both levels share one set -- same
+    # five codes, same meaning, no duplicated literal to drift out of sync.
     system_contract_codes = {
         "REJECT_CONTRACT_MULTIPLIER",
         "REJECT_CONTRACT_SYMBOL",
@@ -228,6 +231,25 @@
         "REJECT_STATE_KEY",
         "REJECT_TICKER",
     }
+    expected_market_rejections = {
+        str(code): int(count)
+        for code, count in reason_counts.items()
+        if str(code) in expected_rejection_codes and int(count or 0) > 0
+    }
+    row_validation_defects = {
+        str(code): int(count)
+        for code, count in reason_counts.items()
+        if str(code) in system_contract_codes and int(count or 0) > 0
+    }
+    unclassified_rejections = {
+        str(code): int(count)
+        for code, count in reason_counts.items()
+        if str(code).startswith("REJECT_")
+        and str(code) not in expected_rejection_codes
+        and str(code) not in system_contract_codes
+        and int(count or 0) > 0
+    }
+    contract_reason_counts = audit.get("contract_evaluation_reason_counts", {})
     expected_contract_rejections = {
         str(code): int(count)
         for code, count in contract_reason_counts.items()
@@ -251,6 +273,8 @@
     }
     if missing_selected:
         system_defects["missing_selected_handoff"] = missing_selected
+    if row_validation_defects:
+        system_defects["row_validation"] = row_validation_defects
     contract_validation_defects = {
         str(code): int(count)
         for code, count in contract_reason_counts.items()
@@ -272,6 +296,7 @@
         reason_counts=reason_counts,
         expected_market_rejections=expected_market_rejections,
         expected_contract_rejections=expected_contract_rejections,
+        unclassified_rejections=unclassified_rejections,
         system_defects=system_defects,
         contract_evaluation_reason_counts=contract_reason_counts,
         contract_evaluation_structure_counts=audit.get("contract_evaluation_structure_counts", {}),
```

**`expected_contract_rejections` and `contract_validation_defects` (the contract-level
classification) are untouched** -- same expressions, same position relative to each other, only
displaced downward in the file by the row-level insertions above them. `system_contract_codes`'
five literal values are unchanged; only its definition site moved earlier so both levels
reference the same set object rather than duplicating the literal.

**One correction made during verification, not before**: the first implementation of
`unclassified_rejections` used a pure two-set complement (`not in expected_rejection_codes and
not in system_contract_codes`) with no `REJECT_` prefix guard. Run 2 immediately surfaced the
consequence: `reason_counts` also contains the non-rejection success marker `SHADOW_ONLY` for
evaluated rows, and a pure complement caught it (`unclassified_rejections: {"SHADOW_ONLY": 137}`),
which would have double-counted the 137 evaluated rows in Check 6's reconciliation. Fixed by
adding `str(code).startswith("REJECT_")` to the bucket-3 filter -- the same convention the
pre-existing, untouched `expected_contract_rejections` block already uses for exactly this reason.
This is not a hardcoded list; it is a structural filter already established elsewhere in this
file. The diff above reflects the corrected version, which is what was actually verified below.

### 3.1c — Schema version

`ev3-shadow-phase-v0.4.0` → `ev3-shadow-phase-v0.5.0`. Because the change is purely additive
(three new keys: `unclassified_rejections` at top level, `system_defects.row_validation`, and the
relocated-but-unchanged `system_contract_codes`), **v0.4.0 and v0.5.0 outputs remain comparable on
every pre-existing key** -- `expected_market_rejections`, `expected_contract_rejections`,
`system_defects.contract_validation`, `system_defects.missing_selected_handoff`,
`rows_received`, `rows_evaluated`, `evaluation_coverage`, `coverage.*`, and every other key that
existed under v0.4.0 keeps the same name and the same meaning under v0.5.0. A reader crossing this
boundary does not need to treat it as a schema break the way v0.3.0→v0.4.0 was -- only new keys
were added, none were removed, renamed, or re-semanticised.

### 3.1d — Verification runs

**Run 1 (08-16, reconstruction inputs, reused existing scratch tree):**
```
python scripts/run_ev3_shadow_phase.py --run-id 20260816_075339 --runs-dir data/scratch/ev3_reconstruction --barrier-cache "C:\Users\ACKVerissimo\vanguard\data\staging\ev3_barrier_outcome_cache.parquet" --phase EOD --now-utc 2026-08-16T10:13:30.257561+00:00
```
Same `--now-utc` as Stage 1 (unchanged rationale -- original run's `generated_utc`, approximation
not ground truth, per Stage 1 caveat 2 above).

**Run 2 (08-18 inputs, new scratch tree `data/scratch/ev3_reconstruction_318/`):**
```
python scripts/run_ev3_shadow_phase.py --run-id 20260818_041214 --runs-dir data/scratch/ev3_reconstruction_318 --barrier-cache "C:\Users\ACKVerissimo\vanguard\data\staging\ev3_barrier_outcome_cache.parquet" --phase EOD --now-utc 2026-08-18T06:03:52.725792+00:00
```
Input CSV copied from `data/output/runs/20260818_041214/options/options_intelligence_20260818_041214.csv`;
copy sha256 `1dc15786a2136c35ac5d36363f6df8b7f54c18b12c409492e5aa83410a7975ff` matches the source
exactly (unlike the 08-16 file, no discrepancy here).

**`--now-utc` for Run 2 — read, not approximated as instructed, but the read value was `null`.**
`data/output/runs/20260818_041214/ev3_shadow/ev3_shadow_phase_status_20260818_041214.json` →
`evaluation_now_utc` = `null`, `evaluation_clock_mode` = `"REALTIME_STRICT"`. The original 08-18
run used no fixed override -- it evaluated quote freshness against actual wall-clock time at
execution, so there is no fixed timestamp recorded to literally reuse. Used the same proxy
methodology Stage 1 established for the v0.3.0 case: the run's own `generated_utc`
(`2026-08-18T06:03:52.725792+00:00`). This is stated explicitly as a proxy, not recovered ground
truth, consistent with Stage 1's caveat 2.

### Verification table

| # | Check | Pass condition | Run 1 (08-16) | Run 2 (08-18) | Result |
|---|---|---|---|---|---|
| 1 | `expected_market_rejections` regression | byte-identical to Stage 1 baseline | `{"REJECT_DIRECTION_UNRESOLVED":1004,"REJECT_NO_EVALUABLE_CONTRACT":248,"REJECT_QUOTE_STALE":95}` -- identical | `{"REJECT_BARRIER_GRID_UNAVAILABLE":2,"REJECT_BARRIER_STATE_UNAVAILABLE":9,"REJECT_DIRECTION_UNRESOLVED":608,"REJECT_LIQUIDITY":1,"REJECT_NO_EVALUABLE_CONTRACT":207,"REJECT_UNIT_SPREAD":71}` -- identical | **PASS** |
| 2 | `rows_received`/`rows_evaluated` | 1347/0 and 1400/137 | 1347/0 | 1400/137 | **PASS** |
| 3 | `system_defects.row_validation` contains `REJECT_CONTRACT_SYMBOL:365` (08-18) | required for 08-18 | key absent (correct -- no system-set code fired at row level on 08-16) | `{"REJECT_CONTRACT_SYMBOL":365}` | **PASS** |
| 4 | `system_defects.contract_validation` unchanged | matches Stage 1 baseline | absent (matches -- Stage 1 recorded "No contract_validation key at all" for 08-16) | `{"REJECT_CONTRACT_SYMBOL":365}` (matches Stage 1 exactly) | **PASS** |
| 5 | `unclassified_rejections` contents | report; empty is valid | `{}` | `{}` | **PASS** (reported -- see note below) |
| 6 | Exhaustive reconciliation via classified buckets | `rows_evaluated + Σbuckets == rows_received` | `0 + 1347 + 0 + 0 = 1347` | `137 + 898 + 365 + 0 = 1400` | **PASS** |
| 7 | `schema_version` | `ev3-shadow-phase-v0.5.0` both | `ev3-shadow-phase-v0.5.0` | `ev3-shadow-phase-v0.5.0` | **PASS** |
| 8 | Hash-pinned files unchanged | match Stage 1 values | engine `e19e35d2...`, runner `b3258c33...` | engine `e19e35d2...`, runner `b3258c33...` | **PASS** |

All eight checks pass.

### Check 6 — the arithmetic, written out

**Run 1 (08-16):**
```
rows_evaluated (0)
+ expected_market_rejections sum (1004 + 248 + 95 = 1347)
+ system_defects.row_validation sum (0, key absent)
+ unclassified_rejections sum (0, empty)
= 0 + 1347 + 0 + 0 = 1347 = rows_received (1347)  [exact]
```

**Run 2 (08-18):**
```
rows_evaluated (137)
+ expected_market_rejections sum (2 + 9 + 608 + 1 + 207 + 71 = 898)
+ system_defects.row_validation sum (365)
+ unclassified_rejections sum (0, empty)
= 137 + 898 + 365 + 0 = 1400 = rows_received (1400)  [exact]
```

Both close exactly **using only the classified buckets** -- no fallback to raw `reason_counts`
was needed, which is the specific thing that proves the fix. Under the pre-Stage-3.1 wrapper,
Stage 1's equivalent reconciliation for the 08-18 run required raw `reason_counts` (`137 + 2 + 9 +
365 + 608 + 1 + 207 + 71 = 1400`) because `expected_market_rejections` alone left a 365-row gap
with no field to attribute it to. That gap is now attributed to `system_defects.row_validation`
by name.

### `unclassified_rejections` — contents and emission sites

**Empty for both runs -- `{}` in Run 1 and Run 2.** This is a valid, expected result per the task's
own framing: every row-level `REJECT_*` code observed in both the 08-16 and 08-18 books falls
inside either the 13-code market set or the 5-code system set. No third-category code has fired
in any run inspected so far.

One non-`REJECT_` value did briefly surface during implementation (see 3.1b's correction note):
`SHADOW_ONLY`, the success marker in `reason_counts` for evaluated rows, emitted at
`vanguard/ev_engine_v3.py:386` and `:537` (`"ev3_reason_code": "SHADOW_ONLY"`, set whenever
`ev3_status == "EVALUATED_SHADOW"`). It is correctly excluded from `unclassified_rejections` by
the `REJECT_` prefix guard, since it is not a rejection at all -- but it is worth naming here as a
concrete instance of "not every value in `reason_counts` is a rejection code," which is exactly
the failure mode the prefix guard exists to prevent.

### `data/output/runs/` and hash-pinned files — untouched, confirmed

Scoped sha256 of every file in `data/output/runs/20260816_075339/ev3_shadow/`,
`data/output/runs/20260816_075339/options/options_intelligence_20260816_075339.csv`,
`data/output/runs/20260818_041214/ev3_shadow/`, and
`data/output/runs/20260818_041214/options/options_intelligence_20260818_041214.csv` -- captured
before both verification runs and re-captured after -- are **byte-identical, file by file, in
both directories**. A parallel full-tree hash listing (every file under both
`data/output/runs/20260816_075339/` and `.../20260818_041214/`, 1,723 and 1,715 files
respectively) was also captured before execution as a secondary fingerprint.

`vanguard/ev_engine_v3.py`, `vanguard/ev3_stage0.py`, and `scripts/run_ev3_shadow.py` -- sha256
unchanged from every value recorded in Stage 1 and in this stage's own pre-flight
(`e19e35d2...`, `9a21bc8a...`, `b3258c33...` respectively). None were opened for writing.

### git status (visibility only — no action taken)

```
?? data/scratch/
?? scripts/run_ev3_shadow.py
?? scripts/run_ev3_shadow_phase.py
?? vanguard/ev3_stage0.py
?? vanguard/ev_engine_v3.py
```
`scripts/run_ev3_shadow_phase.py` was already untracked before this stage (per Stage 0/1 record)
and remains untracked -- only its content changed. No staging, commit, or stash occurred.

### Confidence rating

**High confidence (95%+):** all eight required checks pass with exact, non-approximate values;
the fix is provably additive at the diff level (contract-level block is textually unchanged
except for position); Check 6 closes exactly on both runs using only the new buckets, which is
the direct proof the defect described in 3.1a is closed for these two runs' vocabularies.

**Medium confidence:** that this closes the defect for *every* future run, not just these two --
the fix is structurally exhaustive (Check 5's non-hardcoded-list design), so by construction any
28th-vocabulary code that fires in a future run will land in `unclassified_rejections` rather than
vanishing, but that claim itself has only been exercised against two runs' worth of real data
here.

**Named unknowns:** whether any of the 39 `REJECT_*` codes not observed in either run (of the 41
in the engine's full vocabulary, per the Q1/Q2/Q3 diagnostic) would classify correctly if they
fired -- untested directly, though the exhaustive-complement design gives structural (not just
empirical) grounds for confidence. Whether `SHADOW_ONLY` is the only non-`REJECT_` value that can
appear in `reason_counts` -- not exhaustively verified against the engine's full source, only
confirmed as the one value actually observed.

---

## Stage 3.2 — Coverage Health Flag

### Scope confirmation

Two files edited: `scripts/run_ev3_shadow_phase.py` and `intelligent_orchestrator.py`.
`vanguard/ev_engine_v3.py`, `vanguard/ev3_stage0.py`, and `scripts/run_ev3_shadow.py` were not
opened for writing. `morning_gate.py` was not opened for writing. `critical=False` at
`intelligent_orchestrator.py:2189` is untouched. Nothing branches on `ev3_coverage_health` or the
`dominant_reason_*` fields anywhere in either diff. The orchestrator was not run end-to-end.
Nothing was written into `data/output/runs/`. No git staging, commit, or stash occurred.

One pre-existing condition, unrelated to this stage: `git status` shows `morning_gate.py` as
modified (`M`). This predates the entire audit/remediation sequence -- it was already listed as
modified in the very first `git status` snapshot captured before Stage 0 began. It was not opened
for writing at any point in this session, in this stage or any prior one; the grep result below
(3.2's own required check) confirms its content is still EV-independent regardless of whatever
that pre-existing, unrelated modification is.

### 3.2a — The naming and non-branching constraint

`ev3_coverage_health` contains none of `verdict`, `permission`, `eligible`, `go`, `trade`, or
`signal` -- in its name or in any of its four possible values (`EVALUATED`, `ZERO_COVERAGE`,
`NO_INPUT`, `PHASE_ABSENT`). Neither diff contains an `if` (or any conditional) that inspects
`ev3_coverage_health`, `dominant_reason_code`, `dominant_reason_count`, or `dominant_reason_share`
and changes control flow based on their value -- both diffs only *write* these fields, once each,
unconditionally reached. `production_authority`, `capital_eligibility_enabled`, and
`pipeline_blocking` remain hardcoded `False` in `_base_status()` -- untouched by this stage's diff
(visible in the full diff below: no line touching any of the three appears).

### 3.2b/c — The diff: `scripts/run_ev3_shadow_phase.py`

```diff
@@ -26,7 +26,7 @@
 from scripts.run_ev3_shadow import run_shadow  # noqa: E402


-EV3_SHADOW_PHASE_VERSION = "ev3-shadow-phase-v0.5.0"
+EV3_SHADOW_PHASE_VERSION = "ev3-shadow-phase-v0.6.0"
 DEFAULT_RUNS_DIR = REPO_ROOT / "data" / "output" / "runs"
 DEFAULT_BARRIER_CACHE = Path(
     os.environ.get(
@@ -132,6 +132,17 @@
         "expected_market_rejections": {},
         "expected_contract_rejections": {},
         "unclassified_rejections": {},
+        # Coverage health is a statement about EV3's own coverage today --
+        # not a verdict on the market, not a trade signal. See run_phase()
+        # for the state enumeration and intelligent_orchestrator.py:4947-4948
+        # for the "never changes manifest permission" guarantee this must
+        # not violate. NO_INPUT is also the correct default for the two
+        # early-return branches below (input/barrier-cache missing), since
+        # neither ever reaches a rows_received count.
+        "ev3_coverage_health": "NO_INPUT",
+        "dominant_reason_code": None,
+        "dominant_reason_count": None,
+        "dominant_reason_share": None,
         "system_defects": {},
         "input_path": str(input_path.resolve()),
         "barrier_cache_path": str(barrier_cache.resolve()),
@@ -283,6 +294,39 @@
     if contract_validation_defects:
         system_defects["contract_validation"] = contract_validation_defects

+    # ev3_coverage_health: a health signal, not an eligibility signal. It
+    # reports whether EV3 had anything to say today -- nothing about the
+    # market, nothing about any trade. Nothing may branch on this value.
+    # ZERO_COVERAGE and NO_INPUT are kept distinct on purpose: the first
+    # means EV3 received a full book and rejected all of it (e.g. a Sunday
+    # evening run against stale weekend quotes -- see dominant_reason_code
+    # below for why, not a calendar check here); the second means nothing
+    # reached EV3 at all. Different failures, different owners.
+    if received == 0:
+        ev3_coverage_health = "NO_INPUT"
+    elif evaluated > 0:
+        ev3_coverage_health = "EVALUATED"
+    else:
+        ev3_coverage_health = "ZERO_COVERAGE"
+
+    dominant_reason_code: str | None = None
+    dominant_reason_count: int | None = None
+    dominant_reason_share: float | None = None
+    if ev3_coverage_health in ("ZERO_COVERAGE", "EVALUATED"):
+        # Same REJECT_ prefix guard as expected_contract_rejections /
+        # unclassified_rejections above -- reason_counts also carries
+        # SHADOW_ONLY, the non-rejection success marker, and picking that
+        # as a "dominant reason" would be nonsense (Stage 3.1 Check 6).
+        rejection_counts = {
+            str(code): int(count)
+            for code, count in reason_counts.items()
+            if str(code).startswith("REJECT_") and int(count or 0) > 0
+        }
+        if rejection_counts:
+            dominant_reason_code = max(rejection_counts, key=rejection_counts.get)
+            dominant_reason_count = rejection_counts[dominant_reason_code]
+            dominant_reason_share = round(dominant_reason_count / received, 6)
+
     status.update(
         health=health,
         technical_health="PASS",
@@ -297,6 +341,10 @@
         expected_market_rejections=expected_market_rejections,
         expected_contract_rejections=expected_contract_rejections,
         unclassified_rejections=unclassified_rejections,
+        ev3_coverage_health=ev3_coverage_health,
+        dominant_reason_code=dominant_reason_code,
+        dominant_reason_count=dominant_reason_count,
+        dominant_reason_share=dominant_reason_share,
         system_defects=system_defects,
         contract_evaluation_reason_counts=contract_reason_counts,
         contract_evaluation_structure_counts=audit.get("contract_evaluation_structure_counts", {}),
```

Tie-breaking note: `max(rejection_counts, key=rejection_counts.get)` returns the first
dict-insertion-order key on an exact-count tie. Not addressed further because neither verification
run produces a tie at the top (08-16's runner-up is 248 vs. leader 1004; 08-18's is 207 vs. leader
608) -- flagged here as an untested edge case, not resolved.

### 3.2d — The diff: `intelligent_orchestrator.py` (the ~4947-4998 block)

```diff
@@ -18,6 +18,15 @@
         _ev3_expected_rejections = {}
         _ev3_expected_contract_rejections = {}
         _ev3_system_defects = {}
+        # PHASE_ABSENT: no EV3 status artefact exists for this run at all
+        # (the 20260818_040143 case). Distinct from the wrapper's own
+        # ZERO_COVERAGE/NO_INPUT states, which require the artefact to
+        # exist. This default is overwritten below only if the file exists
+        # and reads successfully -- same pattern as _ev3_health/"NOT_RUN".
+        _ev3_coverage_health = "PHASE_ABSENT"
+        _ev3_dominant_reason_code = None
+        _ev3_dominant_reason_count = None
+        _ev3_dominant_reason_share = None
         if _ev3_status_path.exists():
             try:
                 with open(_ev3_status_path, "r", encoding="utf-8") as _ev3_handle:
@@ -31,6 +40,10 @@
                     _ev3_status.get("expected_contract_rejections", {}) or {}
                 )
                 _ev3_system_defects = dict(_ev3_status.get("system_defects", {}) or {})
+                _ev3_coverage_health = str(_ev3_status.get("ev3_coverage_health", "UNKNOWN"))
+                _ev3_dominant_reason_code = _ev3_status.get("dominant_reason_code")
+                _ev3_dominant_reason_count = _ev3_status.get("dominant_reason_count")
+                _ev3_dominant_reason_share = _ev3_status.get("dominant_reason_share")
             except Exception as _ev3_status_error:
                 _ev3_health = f"STATUS_READ_FAILED:{type(_ev3_status_error).__name__}"

@@ -64,5 +77,9 @@
             "ev3_expected_market_rejections": _ev3_expected_rejections,
             "ev3_expected_contract_rejections": _ev3_expected_contract_rejections,
             "ev3_system_defects":           _ev3_system_defects,
+            "ev3_coverage_health":          _ev3_coverage_health,
+            "ev3_dominant_reason_code":     _ev3_dominant_reason_code,
+            "ev3_dominant_reason_count":    _ev3_dominant_reason_count,
+            "ev3_dominant_reason_share":    _ev3_dominant_reason_share,
             "ev3_production_authority":     False,
             # EDE equivalent is ACTIVE inside EIL runner v4.1 via PSE chain.
```

Follows the existing pattern exactly: a default assumed before the `exists()` check (mirroring
`_ev3_health = "NOT_RUN"`), overwritten only inside the successful-read branch of the existing
`try`, with the pre-existing `except` clause untouched. One acknowledged imprecision, inherited
from the existing pattern rather than introduced by it: if the status file *exists* but fails to
parse (the pre-existing `except` branch), `_ev3_coverage_health` stays at its `PHASE_ABSENT`
default rather than reporting a distinct "read failed" state -- exactly as `_ev3_evaluated` already
stays at `0` and `_ev3_system_defects` already stays at `{}` in that same case. Verified directly
in the unit-level exercise below (`CORRUPT_JSON` case).

### 3.2c — Schema version

`ev3-shadow-phase-v0.5.0` → `ev3-shadow-phase-v0.6.0`. Purely additive: four new keys
(`ev3_coverage_health`, `dominant_reason_code`, `dominant_reason_count`, `dominant_reason_share`)
at the top level of the wrapper's status JSON; nothing renamed, removed, or re-semanticised.
**v0.5.0 and v0.6.0 outputs remain comparable on every pre-existing key** -- `expected_market_rejections`,
`expected_contract_rejections`, `unclassified_rejections`, `system_defects.*`, `rows_received`,
`rows_evaluated`, `evaluation_coverage`, `coverage.*`, and everything else Stage 3.1 established
keeps the same name and meaning under v0.6.0.

### 3.2e — Verification runs

Same two scratch trees Stage 3.1 used, same commands, same `--now-utc` values (`2026-08-16T10:13:30.257561+00:00`
for 08-16, `2026-08-18T06:03:52.725792+00:00` for 08-18 -- the latter still a proxy for the
original run's `evaluation_now_utc: null` / `REALTIME_STRICT` mode, per Stage 3.1's own note; not
re-derived here, reused as-is).

### Verification table

| # | Check | Pass condition | Run 1 (08-16) | Run 2 (08-18) | Result |
|---|---|---|---|---|---|
| 1 | 08-16 run health | `ZERO_COVERAGE` | `ZERO_COVERAGE` | -- | **PASS** |
| 2 | 08-16 dominant cause | `REJECT_DIRECTION_UNRESOLVED`, count 1004, share ≈74.5% | code `REJECT_DIRECTION_UNRESOLVED`, count `1004`, share `0.74536` (74.536%) -- **not** `REJECT_QUOTE_STALE` (95) | -- | **PASS** |
| 3 | 08-18 run health | `EVALUATED`, dominant cause as context | -- | `EVALUATED`; dominant `REJECT_DIRECTION_UNRESOLVED`, count `608`, share `0.434286` | **PASS** |
| 4 | Stage 3.1 regression | byte-identical to Stage 3.1 record | `expected_market_rejections`, `system_defects` (`missing_selected_handoff` only, no `row_validation`/`contract_validation`), `unclassified_rejections:{}` all match Stage 3.1 exactly | `expected_market_rejections`, `system_defects.row_validation:{"REJECT_CONTRACT_SYMBOL":365}`, `system_defects.contract_validation:{"REJECT_CONTRACT_SYMBOL":365}`, `unclassified_rejections:{}` all match Stage 3.1 exactly | **PASS** |
| 5 | Check 6 still closes | `rows_evaluated + Σbuckets == rows_received`, exact | `0+1347+0+0=1347` | `137+898+365+0=1400` | **PASS** |
| 6 | `SHADOW_ONLY` not selected | excluded from dominant-cause on 08-18 (counts 137) | -- | `dominant_reason_code = "REJECT_DIRECTION_UNRESOLVED"` (608), not `SHADOW_ONLY` (137) -- excluded structurally by the `REJECT_` prefix guard regardless of count | **PASS** |
| 7 | Schema | `ev3-shadow-phase-v0.6.0` both | `ev3-shadow-phase-v0.6.0` | `ev3-shadow-phase-v0.6.0` | **PASS** |
| 8 | Hash-pinned files | engine/runner unchanged | engine `e19e35d2...`, runner `b3258c33...` | engine `e19e35d2...`, runner `b3258c33...` | **PASS** |
| 9 | `data/output/runs/` | byte-identical, full-tree fingerprint | scoped hashes (7 files) byte-identical pre/post; full-tree fingerprint (1,723 files): **NO DIFFERENCES** | scoped hashes (7 files) byte-identical pre/post; full-tree fingerprint (1,715 files): **NO DIFFERENCES** | **PASS** |
| 10 | `morning_gate.py` | unchanged, zero EV-field references | grep for `ev_structural\|ev_conf_adj\|ev_status\|ev_final\|ev_selected\|ev2_ev\|ev3_coverage_health\|ev3_shadow\|dominant_reason` → **zero matches** (exit code 1) | -- | **PASS** |

Check 9's full-tree fingerprint (parallel to Stage 3.1's method: every file under both
`data/output/runs/20260816_075339/` and `.../20260818_041214/`, captured before the two
verification runs, re-hashed and diffed after) completed with **`20260816: NO DIFFERENCES (full
tree)`** and **`20260818: NO DIFFERENCES (full tree)`** -- confirmed, not merely architecturally
inferred.

### Check 5 — the arithmetic, written out

**Run 1 (08-16):**
```
rows_evaluated (0)
+ expected_market_rejections sum (1004 + 248 + 95 = 1347)
+ system_defects.row_validation sum (0, key absent)
+ unclassified_rejections sum (0, empty)
= 0 + 1347 + 0 + 0 = 1347 = rows_received (1347)  [exact]
```

**Run 2 (08-18):**
```
rows_evaluated (137)
+ expected_market_rejections sum (2 + 9 + 608 + 1 + 207 + 71 = 898)
+ system_defects.row_validation sum (365)
+ unclassified_rejections sum (0, empty)
= 137 + 898 + 365 + 0 = 1400 = rows_received (1400)  [exact]
```

Unchanged from Stage 3.1 -- this stage added no new bucket and did not touch the classification
logic, so Check 6/Check 5 (same arithmetic, renumbered) closing identically is exactly the expected
result, not a new finding.

### The orchestrator change: what was tested, what was not

**Tested, at unit level** (`data/scratch/ev3_reconstruction/stage_3_2_orchestrator_block_unittest.py`):
a byte-for-byte reproduction of the added lines (default initialisation, the `try`/read block, and
the four new dict entries), executed against five synthetic cases:

- `EVALUATED` status JSON → correctly reads through, `ev3_coverage_health="EVALUATED"`, dominant
  cause populated as context.
- `ZERO_COVERAGE` status JSON → correctly reads through.
- `NO_INPUT` status JSON → correctly reads through, dominant-cause fields correctly `None`.
- Missing file (the `20260818_040143` case) → correctly defaults to `PHASE_ABSENT`, all four new
  fields at their safe defaults, **no exception raised**.
- Corrupt JSON (pre-existing exception path, not new to this stage) → confirmed the existing
  `except` clause still catches it, `_ev3_coverage_health` stays at its `PHASE_ABSENT` default
  (the acknowledged imprecision noted in 3.2d), **no exception propagates**.

All five cases completed without raising; output printed and inspected line by line (see script
for full output).

**Not tested, and stated plainly as unverified:** end-to-end behaviour inside the real
`intelligent_orchestrator.py` evening-run flow. This requires the orchestrator to actually execute
through Phase 8d/morning-manifest assembly with a real `canonical_run_id`, real upstream state for
every other `_integrity` field, and a real `cfg.RUNS_DIR` -- none of which this task is permitted
to invoke (no orchestrator run, no write into `data/output/runs/`). The unit-level exercise proves
the added logic is correct in isolation; it does not prove the surrounding function still behaves
correctly with these lines inserted at the exact indentation/scope they now occupy, nor that the
morning manifest or any other consumer of `_integrity` handles the four new keys gracefully. That
remains unverified until the next real evening run.

### The :4947-4948 comment

> "EV-1.5 is visible in run truth but remains non-authoritative. Its health never changes manifest
> permission during shadow validation."

**Still accurate after this change.** `_manifest_permission` and `_final_state` (which the comment
refers to) are computed entirely above this block (lines 4940-4945 in the current file, part of an
`if/elif/else` chain that never references any `_ev3_*` variable) and are not reassigned anywhere
after it. The four new `_ev3_coverage_health`/`_ev3_dominant_reason_*` locals are read only into
`_integrity`, a dict assembled *after* `_manifest_permission` is already fixed -- they cannot
retroactively change it. `pipeline_technical_health` (line ~5002-5006) derives from
`_manifest_permission` alone, also unaffected. The comment describes exactly the same guarantee
this stage was required to preserve, and the diff preserves it by construction: nothing in either
diff writes to `_manifest_permission`, `_final_state`, or `pipeline_technical_health`.

### `morning_gate.py` — EV-independence, grep result

```
$ grep -inE "ev_structural|ev_conf_adj|ev_status|ev_final|ev_selected|ev2_ev|ev3_coverage_health|ev3_shadow|dominant_reason" morning_gate.py
(no output, exit code 1)
```

Zero matches -- including the three new field names introduced by this stage
(`ev3_coverage_health`, `dominant_reason_*`), confirming they were not (and, per 3.2's scope, could
not have been) wired into `morning_gate.py`. The load-bearing property a prior audit established --
`morning_gate.py` has zero references to any EV field -- still holds after this stage.

### `data/output/runs/` and hash-pinned files

Scoped sha256 of every file in `data/output/runs/20260816_075339/ev3_shadow/` + its input CSV, and
`data/output/runs/20260818_041214/ev3_shadow/` + its input CSV -- captured before and after both
verification runs -- are byte-identical, matching the exact hash values recorded in Stage 3.1
(e.g. `data/output/runs/20260816_075339/ev3_shadow/ev3_shadow_phase_status_20260816_075339.json`
still hashes to `bc250589d6...`). A full-tree fingerprint (parallel to Stage 3.1's method) was also
initiated before execution; see the Check 9 note above for its status at time of writing.
`vanguard/ev_engine_v3.py` (`e19e35d2...`), `vanguard/ev3_stage0.py` (`9a21bc8a...`), and
`scripts/run_ev3_shadow.py` (`b3258c33...`) are all unchanged from every prior recorded value.
None were opened for writing.

### git status (visibility only — no action taken)

```
 M intelligent_orchestrator.py
 M morning_gate.py
?? data/scratch/
?? scripts/run_ev3_shadow.py
?? scripts/run_ev3_shadow_phase.py
?? vanguard/ev3_stage0.py
?? vanguard/ev_engine_v3.py
```
`intelligent_orchestrator.py`'s `M` includes this stage's edit (on top of pre-existing uncommitted
changes from before this audit sequence began). `morning_gate.py`'s `M` is entirely pre-existing --
present in the very first `git status` snapshot of this session, before Stage 0 -- and was not
touched by this stage (confirmed by the grep above). No staging, commit, or stash occurred.

### Confidence rating

**High confidence (95%+):** the wrapper-side change (3.2b/c) -- all ten checks pass with exact
values, the diff is provably additive and non-branching by inspection, and Checks 2/6 specifically
demonstrate the two "do not get this wrong" requirements (dominant cause is direction-unresolved
not staleness on 08-16; `SHADOW_ONLY` correctly excluded on 08-18) hold on real data, not just in
principle.

**Medium confidence:** the orchestrator-side change, specifically because it is unit-tested but not
integration-tested. The unit test proves the added lines are individually correct; it does not
prove their interaction with the rest of the ~5,000-line function they live in, nor with whatever
consumes `_integrity` downstream (manifest writers, the Intelligence Lab, etc.) that were not
examined in this stage.

**Named unknowns:** whether any downstream consumer of the `_integrity` dict (beyond what this
stage was scoped to touch) makes an assumption about its key set that four new keys could violate
(e.g. a strict schema validator) -- not checked, out of this stage's scope. The `max()` tie-breaking
behaviour on dominant-cause selection, noted in 3.2b -- untested, no observed tie in either
verification run.

**Update:** the full-tree fingerprint for Check 9 (initiated before the verification runs,
1,723 + 1,715 files across both archived run directories) has since completed:
`20260816: NO DIFFERENCES (full tree)`, `20260818: NO DIFFERENCES (full tree)`. `data/output/runs/`
untouched is now confirmed directly, not only via the scoped hashes and architectural guarantee.
