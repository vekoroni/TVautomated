# AVS-TST-QT-001 — Findings

**Tester:** independent quantitative tester. **Date:** 2026-09-06.
**Repository state tested:** working tree at `HEAD = 6e834b8` (uncommitted).
**Method:** build archaeology → system model → 54 pre-registered expectations → logic tests → run-artefact reconciliation. No pipeline execution; no flag set; all writes confined to this directory.

---

## 1. Built vs claimed

### 1.1 The structural fact that conditions everything

**Nothing from 4–6 September is committed.** `git rev-list --count pre-tidy-20260904..HEAD` = **2**, and both commits are Friday morning's root tidy. The entire week's work — AVS-SD-003 cycle 1, the adapter fix, five blockers, integration repair, DDD production integration and DDD closure — exists as **63 modified tracked files and 33 untracked paths in a dirty working tree**.

Three consequences no claim sheet states:
- Runs `20260904_122358` and `20260905_151448` both record `baseline_commit_hash: 6e834b8` while being produced by materially different code. **A run artefact cannot identify the code that produced it** — a P0-01 regression (**QT-D02**).
- There is no rollback point. `git revert`/`checkout` cannot reach any intermediate state; recovery depends entirely on `backups/`.
- The gap fixes and an unauthorised architectural refactor (§1.3) cannot be reverted independently, because neither is committed.

The one identity mechanism that does work is `run_meta.json.ddd_runtime_profile.sha256`, and it is how I established which run ran which code.

### 1.2 Undocumented changes

**20 production changes appear in no claim sheet** (`00_built_vs_claimed.csv`), of which the material set is:

- **An entire new `domain/` package — 10 modules** — plus `canonical_data/outcome_maturation.py`, `canonical_data/run_plan_store.py`, `orchestrator/session_authority_adapter.py`. AVS-SD-003 authorises bounded changes to named modules to close eleven gaps; a domain-driven-design layer is a structural change of a different order (**QT-D11**).
- `scripts/macro_quant_packet.py`, `canonical_data/request_ledger.py`, `contracts/dynamic_session_authority_v1.json`.
- **16 of 17 test-file edits.** `AVS-IMP-SD-003-004` admits one fixture edit; seventeen existing test files changed (**QT-D09**).

### 1.3 Unsupported claims

| Claim | Verdict |
|---|---|
| ddd_closure "coverage gate 95 % → 90 %" | **CONTRADICTED** — the per-profile gate is `>= 0.95` before *and* after; `0.90` is a *new, stage-level* `min_usable_ratio`, a different quantity and a stricter posture. The stated rationale is also wrong (§2.1). **QT-D08** |
| IMP-004 "one test fixture edited" | **CONTRADICTED** — 17 modified |
| Every ddd_closure capability claim | **VERIFIED_OFFLINE at best** — no run exists under the closure code (**QT-D14**) |
| Worker 3 "built against AVS-W3-SD-001" | **BLOCKED** — that design does not exist as a file in either tree |

### 1.4 Changes without a backup, and pinned-hash drift

- **9 modified files with no pre-change backup** — 7 tests and **2 production**, both one-line additions (`dynamic_session_authority_v1.json`, `request_ledger.py`). Real but minor (**QT-D10**). The 25 *new* files without backups are not violations — a new file has no pre-image.
- **Closure manifest: 13 of 13 pinned hashes match live.** Integration manifest: 2 of 9 mismatch, both superseded by the closure. **Not drift — stale documentation.**
- **Runtime-profile hash resolved:** live is **`054a76be…` v1.0.1** (closure). `2b416bbe…` is the superseded v1.0.0 and appears nowhere but the integration manifest.

---

## 2. Pre-registered expectations: where the code disagreed, and where I was wrong

**54 registered; 33 executed; the code disagreed with 4.** In **3 of those 4 I was wrong**, and in 1 I was right.

### 2.1 Where I was right — and it refutes a claim

**`PROF-COV-04`.** I predicted that a 77/78 frame fails under **both** a 0.95 and a 0.90 coverage gate, because `last_region` is a hard `and` in the usability expression. Confirmed: coverage 0.987179, `usable=False`, `last_region=False` under either threshold.

The DDD closure lowered a gate to rescue 77/78 frames. **No coverage threshold could have rescued them** — at 98.7 % they were far above both. The binding constraint was the missing 15:55 bar, and the real fix was the exclusive-`to` `+1 interval` shipped in the same release.

**Confirmed on real data:** all 1,491 persisted `INTRADAY_BAR` payloads from run `20260905_151448` run **09:30 → 15:50** (AAPL: exactly 77 bars, 300 s step) — the 15:55 bar is absent, exactly as the off-by-one predicts.

### 2.2 Where I was wrong

| ID | My expectation | Reality |
|---|---|---|
| `GEO-06` | a CALL with a stop above entry is silently accepted | **Protection exists** at `avshunter_options_intelligence.py:4265-4270` — sets `invalidation_state = DATA_DEFECT_WRONG_SIDE` and leaves `invalidation=None`. My test called `compute_trade_economics` directly, below that boundary. |
| `L2-03` | the `ALIGNED` uplift delta is exactly 25 | It is **22**, because the score saturates at `min(100.0, score)` (`edge_detector.py:598`). My expectation ignored the cap. |
| `PROF-COV-05` | 75/78 with interior gaps is unusable | **Usable** — interior gaps are tolerated above the coverage gate when both edges are present. Correct design. |

`QT-D05` (my independent TPO implementation disagreeing with production by one bin) was **arbitrated against me**: the repository's own excluded test `test_c06_value_area_expands_from_poc_to_next_higher_adjacent_count` passes, confirming production's tie-break. Recorded at P3 for completeness, not asserted as a production defect.

### 2.3 The most valuable thing a pre-registered expectation caught

**`GEO-03` — the CALL null-target branch that no production run has ever exercised.** AVS-RCA-002 established that `compute_trade_economics` carried identical exposure on both branches and that the CALL side was spared only by chance. I tested CALL and PUT × `None`/`NaN`/`inf`/`0.0`/negative — **all ten combinations return the governed `NOT_EVALUATED` / `STRUCTURAL_TARGET_UNRESOLVED` record.** The guard sits before the direction branch, as specified. This is now verified rather than assumed.

### 2.4 The threshold question, answered with evidence

AVS-SD-003 and AVS-PRE-001 specified 95 %; the closure claimed 90 %. Truncation error measured on **60 real tickers** from the run's own persisted bars, in ATR units:

| bars | coverage | dPOC p50 | dPOC p95 | dPOC max | dVAH p95 |
|---|---|---|---|---|---|
| 76 | 0.974 | 0.000 | **0.000** | 0.487 | 0.132 |
| 74 | 0.949 | 0.000 | **0.000** | 0.487 | 0.159 |
| 73 | 0.936 | 0.000 | 0.094 | 0.406 | 0.180 |
| 72 | 0.923 | 0.000 | **0.260** | 1.422 | 0.325 |
| 70 | 0.897 | 0.000 | **0.382** | 1.422 | 0.325 |

There is a clear knee between **74 and 72 bars** — between ~94.9 % and ~92.3 % coverage. Above 94.9 % the 95th-percentile POC error is **exactly zero**. At 89.7 % (a 90 % gate) **1 ticker in 6 has a POC error above 0.10 ATR and the worst case is 1.42 ATR**.

**Recommendation: keep the per-profile gate at 0.95.** It is where the data says the profile stops being exact, and — decisively — **90 % was never needed**, because the frames that motivated it failed on `last_region`, not coverage. Retain `min_usable_ratio = 0.90` as the *stage-level* gate; it is a genuine addition and would have caught the zero-usable-profile run.

"Both session edges" is consistently defined: `expected[0]` = 09:30 and `expected[-1]` = 15:55, matching AVS-PRE-001's 78 open-stamped RTH bars.

---

## 3. Gate table — latest run `20260905_151448`

Full tables in `B_20260904_122358.csv` and `B_20260905_151448.csv`.

| Gate | Assertion | Count | Required | Verdict | Three-direction |
|---|---|---|---|---|---|
| AG-01 | `INSUFFICIENT_DATA` and `ALIGNED` | **0** | 0 | **PASS** | was 1,068 (547C/319P/202O) |
| AG-02 | POC as `0.0` | **0** | 0 | **PASS** | was 1,551 |
| AG-03 | `ready_to_trade` with null POC | **0** | 0 | **PASS** | was 1,068 |
| AG-04a | governed branch executed (`timeframe=GOVERNED`) | 1,537 | 1,537 | **PASS** | — |
| AG-05 | `ARMED` with `invalidation_state=MISSING` | **0** | 0 | **PASS** | was 43 CALL |
| AG-07 | `EOD_CANDIDATE_ONLY` without invalidation | **0** | 0 | **PASS** | was 13 CALL |
| AG-08 | Lab `EXECUTABLE` without invalidation | **0** | 0 | **PASS** | was 23 |
| AG-08b | Lab rows blank `invalidation_price` | **0** | 0 | **PASS** | was 24 CALL |
| AG-09 | raw interpreter text | **0** | 0 | **PASS** | was 36 PUT |
| AG-10 | governed `STRUCTURAL_TARGET_UNRESOLVED` | 191 | 191 | **PASS** | 133 CALL / 58 PUT |
| AG-11 | Lab quote lineage | 275/294 + named absence | 294 | **PASS** | 19 absent are `NOT_APPLICABLE_NO_SELECTED_CONTRACT` |
| AG-11 | `execution_viability_state` | **294/294** | 294 | **PASS** | was 0/256 |
| AG-12 | macro lineage identity | 294/294 | 294 | **PASS** | was 0/256 |
| AG-13 | `monetisability_authority` | **0/294** | 294 | **FAIL** | **QT-D07** |
| AG-16 | audit fails on the unremediated run | **16**, 0 spurious | ≥6 | **PASS** | IMP-003 claim reproduced |
| RG-02 | Lab direction population | 294 | 294 | **PASS** | 190 CALL / 104 PUT |
| RG-05 | Lab population reconciles | 294 | 294 | **PASS** | — |
| RG-07 | OTHER direction `NOT_APPLICABLE` | **0** violations | 0 | **PASS** | 129 STRANGLE / 40 UNRESOLVED |

**Sixteen of eighteen gates pass on real output.** The two exceptions are `monetisability_authority` (advisory; §4 explicitly ignores it) and the audit's own `fail_count = 2`.

**Reconciliations demanded by the brief:**
- **IMP-004's 271/270/MRP claim — exact.** 271 Lab rows, 1 blank `invalidation_price`, ticker **MRP**, direction CALL, permission `NOT_EXECUTABLE`.
- **DDD-closure "100 % selected-handoff coverage, zero missing invalidations, while the profile stage failed" — both halves confirmed.** Lab book 294 rows, 0 blank invalidations, invalidation on the correct side **294/294 in both directions**; profile stage `completed = 0` of 1,587.

**What that book looks like to a trader:** 294 rows, 190 CALL / 104 PUT, every row with a governed direction hash matching Options, a real stop on the correct side, and a median underlying R:R of 3.0 — **ranked with no auction or profile input at all**, because every profile was unusable. 135 rows show `EXECUTABLE_QUOTE`, 84 `BLOCKED_WIDE_SPREAD`, 30 `ZERO_BID_REVIEW`, 27 `DATA_MISSING`, 18 `MANUAL_LIQUIDITY_REVIEW`. No row carries `BUY_NOW`/`BUY_SMALL` — correct for an Evening book.

### 3.1 The two remaining audit failures

`fail_count = 2`, both `DIRECTIONAL_TRADE_PROMOTED_WITHOUT_GOVERNED_INVALIDATION`, both **ticker TTEK**, 1 of 1,461 rows at `eil_enriched` and again at `execution`. TTEK carries `invalidation_state=MISSING` and `options_verdict=STAND_DOWN`, yet `eil_v3_verdict=EXECUTE_WITH_CAUTION`. **TTEK does not reach the Lab book**, and both stages carry no capital authority. Real failure, no trader-facing exposure (**QT-D06**).

---

## 4. Deviation register summary

Nine entries in `C_DEVIATIONS.md`. Confirmed: D-01 dispatcher is the production path; D-04 `tests/msi/` excluded **and hiding a live failure**; D-05 test edits (16 undocumented, one weakening); D-06 `CLOSED OFFLINE` (12 gates have since acquired run artefacts; the closure's have not); D-07 Worker 3 unlocatable design but genuinely isolated; D-09 unauthorised `domain/` layer. **Refuted:** D-02 as described, D-03, D-08 as described.

### The single most serious finding

**QT-D01 — `tests/test_dynamic_session_phase0.py::test_all_new_features_are_disabled_by_default` still passes, and still bears that name, while production enables 8 of 9 flags.** It passes because it calls `from_environment({})`, the explicit-mapping branch that hard-codes all-`False`; production calls `from_environment()` with no argument and loads the runtime profile. The only edit this week was `8` → `9`.

This is the **third** instance this week of a test certifying a property that is false in production — after the Phase 3 adapter tests against mocks and the Phase 4 Vanguard test with `required=True`. It is the most consequential because the property is the MVP trust boundary itself.

The *code* is defensible: a hash-pinned single-file runtime profile with a one-variable rollback is better than nine loose environment variables. The defect is that a green count containing this test is cited as evidence that flags are off.

---

## 5. MVP verdict

> ## INTACT WITH CONDITIONS

Full reasoning in `D_MVP_READINESS.md`. Every §4 field is present, populated and produced by the authority AR-003 assigns; invalidation geometry is correct on **294/294 rows in both directions**; kill criteria 1–4 are all clear. Conditions:

1. **Run Evening + Morning on the current code first.** The newest run predates the closure; the closure's changes have never executed (**QT-D14**).
2. **§4 cannot be completed from an Evening book** — `final_action` is `MANUAL_REVIEW`/`CONTRACT_REPAIR` on all 294 rows; the contract-and-quote clauses need Tuesday's Morning run.
3. **Kill criterion 6 currently fires** (`fail_count = 2`). Clear TTEK or record the exception consciously first.

Also: treat any `structural_target` of `0.00` as missing (13 rows, **QT-D04**), and keep `AVSHUNTER_DYNAMIC_RELEASE_DISABLE_ALL=1` to hand as the rollback.

**What went right, and it is substantial:** ten of the eleven AVS-SD-003 cycle-1 gaps are closed **and verified by run artefact** — not offline. The fail-open that produced 1,068 fabricated `ALIGNED` rows is gone; POC is null rather than `0.0`; 43 `ARMED`-without-stop rows are gone; 36 raw `TypeError` strings are gone; the Lab lineage that was 0/256 is now complete or explicitly absent. The audit that could not fail now returns 16 genuine failures on the known-bad run and 2 on the current one.

---

## 6. What I could not verify, and why

| Item | Status | Reason |
|---|---|---|
| Every DDD-closure capability | **VERIFIED_OFFLINE** | no run exists under the closure code (QT-D14) |
| Morning-path behaviour, validation events 1:1 with actionable rows | **BLOCKED** | no Morning run exists under any DDD code state |
| Single `pipeline_run_id` across stages; immutable build receipt; `DATA_REPAIR_REQUIRED` | **VERIFIED_OFFLINE** | present in source; never executed |
| `tests/msi/test_logic.py`, `test_flow.py`, `test_functionality.py`, `test_regression.py` | **BLOCKED — budget** | exceeded time budget; `test_computation.py` ran and failed 2 |
| Classification of 8 of 17 test edits | **BLOCKED — budget** | the 9 material ones are classified in C_DEVIATIONS D-05 |
| `A7` full dispatcher `as_of_utc` matrix; plan-hash determinism; DDD-closure plan hash `06a1c5c8…` | **BLOCKED — budget** | `DISP-01` verified in source; the matrix and hash reproduction not run |
| `A5` execution-viability one-quote-one-state cross-module probe | **BLOCKED — budget** | partially covered by AG-11 on run artefacts (294/294) |
| `W3-03` displacement boundary at exactly 25 % | **NOT_ACHIEVED** | my staircase construction saturates displacement at 1.0; a test-construction limit, not a code finding |
| Worker 3 v2 validator (`W3-08/09/10`) | **BLOCKED — budget** | the v2 module was not exercised; its 263-test suite passes |
| `AVS-W3-SD-001` design | **BLOCKED** | does not exist as a file in either tree |
| Whether my independent TPO differs from production correctly | **UNRESOLVED → arbitrated** | the repository's own excluded `test_c06` passes, favouring production; QT-D05 held at P3 |

**One limitation in my own prior work, disclosed:** `audit/preflight/AVS-PRE-001_20260904_075820/01_responses.jsonl` records parsed summaries but **not the raw OHLC arrays**, so the real SPY frame that report was built on cannot be re-derived from it. I used the run's 1,491 persisted `INTRADAY_BAR` payloads instead, which are better evidence. And my own AVS-OPS-001 matrix excluded `tests/msi/` — the same gap I file here as D-04.

---

## 7. Defects filed

14 in `AVS-TST-QT-001_DEFECTS.csv`, all `OPEN`, none fixed.

| Severity | IDs |
|---|---|
| **P0** | QT-D01 (test integrity: "disabled by default" passes while 8 of 9 are enabled) |
| **P1** | QT-D02 (nothing committed; runs cannot identify their code), QT-D03 (profile stage reports `systemic_failure=false` on 0 usable of 1,587), QT-D14 (no run under the current code) |
| **P2** | QT-D04 (`structural_target = 0.0` × 13), QT-D06 (TTEK), QT-D07 (`monetisability_authority` 0/294), QT-D08 (closure misdescribes its own change), QT-D09 (16 undocumented test edits), QT-D11 (unauthorised `domain/` layer), QT-D12 (`--data-mode` silently ignored) |
| **P3** | QT-D05 (my TPO disagreement, arbitrated against me), QT-D10 (2 files without backup), QT-D13 (`FINALISE`/`BUILD_THESIS` share a callback) |
