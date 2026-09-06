# AVS-PRR-001 — Production readiness review

**Date:** 2026-09-06 (Sunday)
**Evidence base:** `audit\pipeline_map\AVS-TST-QT-001\` (independent quant test, 6 Sep), `AVS-RCA-002`, the IMP-SD-003 and DDD claim sheets, runs `20260904_004338`, `20260904_122358`, `20260905_151448`
**Purpose:** state the current condition of the pipeline, what has been fixed and proven, what has been fixed but not proven, and exactly what must be true before two distinct sign-offs: (A) MVP trading on Tue 8 / Wed 9 Sep, and (B) production-ready as defined by AR-003 §12 and Rev 1.1 §19.
**Decision owner:** ACK

---

## 1. Current state in one paragraph

The pipeline today is materially more honest than it was on Thursday. Ten of the eleven AVS-SD-003 cycle-1 gaps are closed **and proven on a real run**: no `ALIGNED` on fabricated profiles, no POC published as zero, no armed row without a stop, no raw exception text, invalidation on the correct side of entry on every one of 294 Lab rows in both directions, viability and quote lineage reaching the Lab, and an audit that now fails 16 times on the known-bad run instead of twice for the wrong reason. The production path is no longer the legacy `--evening` branch: normal commands dispatch through the dynamic engine under a checked-in, hash-pinned runtime profile (v1.0.1, `054a76be…`) with 8 of 9 capabilities on and AUTO off. Against that, three things condition everything: **nothing from the last three days is committed** (63 modified, 33 untracked files sit in the working tree, so a run artefact cannot identify its code); **no run has yet executed under the current code** — the DDD closure's boundary fix, usable-ratio guard, single run-id and build receipt are all unexercised; and the completed-profile capability has produced **zero usable profiles** in production so far, for a reason now fixed but not yet demonstrated.

---

## 2. What has been fixed and proven (run `20260905_151448` vs baseline `20260904_004338`)

| Property | Thursday baseline | Latest run | Status |
|---|---|---|---|
| `auction_state=ALIGNED` on unusable profile | 1,068 | **0** | VERIFIED |
| POC/VAH/VAL published as `0.0` | 1,551 | **0** (null) | VERIFIED |
| `ready_to_trade=True` with no profile | 1,068 | **0** | VERIFIED |
| `ARMED` with `invalidation_state=MISSING` | 43 | **0** | VERIFIED |
| Raw `TypeError` text in trader-facing fields | 36 | **0** | VERIFIED |
| Governed `STRUCTURAL_TARGET_UNRESOLVED` records | 0 | **191** (133 CALL / 58 PUT) | VERIFIED |
| Lab rows with blank `invalidation_price` | 24 | **0** | VERIFIED |
| `EOD_CANDIDATE_ONLY` without invalidation | 13 | **0** | VERIFIED |
| Invalidation on correct side of entry | not checked | **294/294** (190 CALL / 104 PUT) | VERIFIED |
| `execution_viability_state` in Lab | 0/256 | **294/294** | VERIFIED |
| Bid/ask size, quote timestamp in Lab | 0/256 | 275/294 + named absence | VERIFIED |
| Direction lineage hash Options↔Lab | 256/256 | **294/294** | VERIFIED (protected positive) |
| OTHER direction stays `NOT_APPLICABLE`, never in Lab | correct | correct (129 STRANGLE / 40 UNRESOLVED) | VERIFIED |
| Semantic audit on the known-bad run | 2 spurious | **16 genuine, 0 spurious** | VERIFIED |
| CALL null-target branch (never hit by any run) | untested | all 10 direction×value cases governed | VERIFIED_OFFLINE |
| MarketData adapter: Eastern wall-clock window, 404 handled, segment derived | defective | fixed | VERIFIED_OFFLINE (no run yet) |

**Fixed but not proven on any run (DDD closure, 5 Sep evening):** exclusive-`to` +1 interval (the reason for 1,491 partial profiles), stage-level `min_usable_ratio=0.90`, `DATA_REPAIR_REQUIRED` before EOD, one `pipeline_run_id` across stages, plan-hash-bound build receipt, telemetry split. These are `VERIFIED_OFFLINE` at best (QT-D14).

**Not fixed:** `monetisability_authority` stamp, 0/294 on every run since it was filed (QT-D07).

---

## 3. The pipeline as it executes today

`python intelligent_orchestrator.py --evening` → `DynamicSessionFeatureFlags.from_environment()` loads `contracts\dynamic_session_runtime_v1.json` → `plan_engine=True` so the dispatcher is entered at `:6632` (the legacy branch at `:6733` is unreachable) → `RunPlan` resolved at `as_of_utc`, action `BUILD_THESIS`, plan hash persisted → Discovery (frozen direction governance, survivor worklist, stale-bar fallback stamped) → **completed Market Profile stage** (MarketData 5-min candles via the corrected adapter, coverage ≥ 0.95 per profile with both session edges, stage fails closed below 0.90 usable ratio) → Vanguard (governed verdict only; `NOT_EVALUATED`/null/zero-uplift when no usable evidence) → Options Intelligence (invalidation precondition at arming; null-target guard both directions; MarketData chains) → Horizon → EV3/GARCH/trigger/EIL advisory layers → EOD candidate engine (`DATA_REPAIR_REQUIRED` without governed invalidation; no capital permission without a stop) → Execution Gate (final action; viability from current quote; monetisability advisory) → governed Lab book with lineage → semantic audit + UAT → immutable build receipt → Decision/Outcome Ledger (append-only). `--morning` → `VALIDATE` over the accepted thesis → Morning Gate → validation events (1:1 with actionable rows) → Execution Gate → Lab/Interpreter parity. Rollback: `AVSHUNTER_DYNAMIC_RELEASE_DISABLE_ALL=1` returns to the legacy path (verified in source, never exercised live).

Authority as implemented matches AR-003 §8 on every row the tester checked: direction governance, horizon router, Vanguard geometry, Options selection, long-option policy, Execution Gate — each the sole writer of its field, with the profile, macro, EV3 and monetisability layers advisory.

---

## 4. Sign-off A — MVP trading (Tue 8 / Wed 9 Sep)

**Tester verdict:** `INTACT WITH CONDITIONS`. All twelve AVS-MVP-001 §4 filter fields are present, populated and produced by the assigned authority; kill criteria 1–4 (the ones that would indicate the RCA-002 defects had returned) are clear.

**Required before the first trade — in order:**

| # | Item | Why | Owner | Evidence of done |
|---|---|---|---|---|
| A1 | **Commit the working tree and tag it** (`avs-sd-003-cycle1+ddd-closure-20260906` or similar); record the tag in `run_meta.json` for every run from now on | QT-D02: two runs already share a baseline hash while running different code. A trade taken on a run whose code cannot be identified is untraceable. | ACK / Codex | `git rev-parse HEAD` ≠ `6e834b8`; `git status --porcelain` empty; tag exists |
| A2 | **Fix the test-integrity defect** (QT-D01): rename/rewrite `test_all_new_features_are_disabled_by_default` to assert what production actually does (runtime profile loads 8/9 on, AUTO off, kill switch works), and add a test that fails if the profile hash changes without a manifest update | The green count currently certifies a false property — the MVP trust boundary itself | Codex | New test names; run XML |
| A3 | **Run Evening on Monday night on the committed code** (Friday 4 Sep is the completed session; Monday is Labor Day) | QT-D14: nothing has run under the closure. Apply the §4 filter to *this* book, not to `151448` | ACK | `run_meta.json` shows the new tag and profile `054a76be…`; build receipt present |
| A4 | On that run, **confirm the profile stage worked**: 78-bar frames, `usable_ratio ≥ 0.90`, `completed_profile_count > 0`; or, if it did not, that `min_usable_ratio` **stopped the stage** and Vanguard fell to `NOT_EVALUATED` | QT-D03: the old failure-ratio guard cannot fire on a 100%-unusable outcome; the new guard has never run | ACK + tester | `completed_profile_summary_*.json` |
| A5 | On that run, **re-run the corrected audit and kill criteria 1–4**; resolve or consciously waive criterion 6 (currently `fail_count=2`, both TTEK, retired EIL telemetry, not in Lab — QT-D06) | AVS-MVP-001 §6 | ACK | audit JSON; a one-line waiver in the MVP decision log if TTEK-class failures are accepted |
| A6 | **Run Morning on Tuesday** over the accepted Monday run; apply §4 clauses on contract/quote/`final_action` to the Morning book; confirm validation events 1:1 with actionable rows, Execution Gate↔Lab parity, finaliser pass | §4 cannot be completed from an Evening book — no row carries `BUY_NOW`/`BUY_SMALL` until Morning | ACK | Morning artefacts; kill criterion 5 clear |
| A7 | Trader applies §4 **with the side check on `structural_target`** and treats any `0.00` as missing | QT-D04: 13 CALL rows carry a fabricated zero target (all already `NOT_EXECUTABLE`) | ACK | manual |
| A8 | Add `contract_dte` to the Lab book (or evaluate DTE from the OCC symbol manually) | §4 clause "DTE ≥ 2 × planned hold" is not evaluable from the book as written | Codex (small) / ACK (manual) | column present or manual note |

A1 and A2 are code/process and can be done today. A3–A6 are the live cycle. A7–A8 are trader discipline. **First trade: Tuesday only if A1–A6 are clean; realistically Wednesday.** Probe size, max 3 positions, hard exit at invalidation, journal same day, per AVS-MVP-001 §5.

---

## 5. Sign-off B — production-ready (shippable product)

Everything in §4, plus:

| # | Item | Defect / gate | Severity |
|---|---|---|---|
| B1 | Separate the DDD `domain/` refactor (10 new modules + 3) from the gap fixes so they are independently revertable; give it a design record | QT-D11 — unauthorised architectural layer bundled into the same uncommitted tree | P2 |
| B2 | `structural_target` null-not-zero at the producer; extend `PROFILE_ZERO_AS_PRICE` audit rule to `structural_target` | QT-D04 | P2 |
| B3 | Suppress or map retired EIL telemetry (`EXECUTE_WITH_CAUTION` on a stood-down row) so no execution-shaped language appears beside a governed stand-down | QT-D06 | P2 |
| B4 | Write `monetisability_authority=ADVISORY_ONLY` on every row incl. `FAILED` | QT-D07 | P2 |
| B5 | Bring `tests\msi\` into the acceptance matrix; fix or file `test_c07_one_minute_volume_uniformly_allocated_and_labelled` (a genuine Market Profile volume-allocation failure); retire the stale `*_NOT_IMPLEMENTED` absence test | D-04 — the Market Profile arithmetic has been outside every green count this week | P1 |
| B6 | Correct the DDD closure claim sheet (claim 5 misdescribes the gate change); document the 16 undocumented test edits with classification; record backups for the 2 files changed without one | QT-D08, QT-D09, QT-D10 | P2 (documentation) |
| B7 | Same-session warm rerun: option-chain physical requests = 0, ledger reconciles | AVS-SD-003 AG-20 / Rev 1.1 G19 | gate |
| B8 | Premarket, RTH (developing profile) and after-hours finalisation live cycles | Rev 1.1 G18B–D | gate |
| B9 | `--data-mode` silently ignored on the dynamic path (warn or remove); `FINALISE` and `BUILD_THESIS` share a callback | QT-D12, QT-D13 | P3 |
| B10 | Arbitrate QT-D05 (independent TPO vs production POC/VAH by one bin) — `tests\msi` `test_c06` suggests production is right; close with a written note | QT-D05 | P3 |
| B11 | Replace the Windows Store base interpreter behind `venv/` with a pinned install; record in the release manifest | D-08 / P0-01 | P3 |
| B12 | Decide Worker 3's integration boundary before any live-AI slice touches the Interpreter surface (AR-003 §7.14) | D-07 | design decision |
| B13 | Exercise `AVSHUNTER_DYNAMIC_RELEASE_DISABLE_ALL=1` once in a controlled run so the rollback is proven, not read | D-01 | gate |
| B14 | Re-issue the P0 recertification with a run-artefact column; retire `CLOSED OFFLINE` from claim sheets | AVS-SD-003 §C8 | process |

**Production-ready is declared when:** the tree is committed and tagged; B1–B6 are closed with run evidence; G18A–D and G19 have passed on one code state; `tests\msi\` is green in the matrix; and the release assessor records hash-bound artefacts for all of it. Earliest realistic date: the week of 14 September, assuming Monday's run is clean and one more RCA loop is not needed.

---

## 6. What the tester got wrong, and what I got wrong

Recorded because it is how the closure standard earns trust.

- The tester pre-registered 54 expectations, ran 33, and the code disagreed with 4; it was wrong in 3 (wrong-side stop *is* rejected; the alignment uplift saturates at 100 rather than adding 25; interior gaps do not fail the coverage gate). Its one correct disagreement refuted a claim sheet.
- I told you on Sunday morning the coverage gate had been lowered from 95% to 90%. It had not; the claim sheet said so and I repeated it. The per-profile gate is unchanged; 0.90 is a new stage-level guard. I also listed the runtime-profile hash as "drift"; it is supersession, and the run artefacts identify their profile correctly.
- The tester's own Friday tidy matrix excluded `tests\msi\`; it reported that gap against itself.

---

## 7. Decision log

| Decision needed | Options | Recommendation |
|---|---|---|
| Commit strategy | one commit of everything / two commits (gap fixes, then DDD refactor) | Two if Codex can separate them in under an hour; otherwise one commit now and the separation as B1 |
| TTEK-class audit failures | clear before trading / waive with a written exception | Waive *only* for failures at stages with no capital authority on tickers absent from the Lab; anything in the book blocks |
| Tuesday trade | yes if A1–A6 clean / Wednesday regardless | Wednesday, unless Tuesday's Morning artefacts are clean on first inspection |
| `structural_target=0.0` rows | fix before trading / manual side-check | Manual side-check for the MVP window; fix as B2 |
