# AVS-TST-QT-001 Track D — MVP readiness verdict

**Assessed against:** `AVS-MVP-001` §4 (the trader's manual filter) and §6 (kill criteria).
**Evidence run:** `20260905_151448` — the most recent real run, 294 Lab rows, produced under DDD runtime profile **v1.0.0 `2b416bbe…`**, *not* the current closure code.
**Decision context:** the operator intends to resume real-capital trading Tue 8 / Wed 9 September. This is advice; the operator decides.

---

## 1. Verdict

> ## INTACT WITH CONDITIONS

The MVP trust boundary holds under the dynamic dispatcher. Every §4 field is present, populated and produced by the authority AR-003 assigns, and the geometry the filter depends on is sound in both directions. But three conditions must be met before capital is committed, and one of them is not optional.

**Condition 1 — run the Evening + Morning cycle on the current code first.** The newest run predates the DDD closure (QT-D14). The exclusive-`to` boundary fix, `min_usable_ratio`, `DATA_REPAIR_REQUIRED`, the single `pipeline_run_id` and the immutable build receipt have **never executed in production**. Trading on Tuesday means trading on a code state whose first live output will be Monday night's run. The §4 filter should be applied to *that* book, not to `20260905_151448`.

**Condition 2 — §4 cannot be completed from an Evening book.** `final_action` is `MANUAL_REVIEW` on 275 rows and `CONTRACT_REPAIR` on 19; **zero rows carry `BUY_NOW` or `BUY_SMALL`**. That is correct — Execution Gate grants at the Morning boundary — but it means the four contract-and-quote clauses of §4 are unevaluable until Tuesday's Morning run completes. The Evening book can only pre-qualify on identity, direction and geometry.

**Condition 3 — one kill criterion currently fires.** §6 item 6 reads *"Audit `fail_count` > 0 for a genuine rule"*. The corrected audit returns **`fail_count = 2`** on the latest run. Both are the same ticker (TTEK) at `eil_enriched` and `execution`, both `DIRECTIONAL_TRADE_PROMOTED_WITHOUT_GOVERNED_INVALIDATION`. **TTEK does not reach the Lab book**, and both stages carry no capital authority, so there is no trader-facing exposure — but the criterion as written fires, and the operator should either clear TTEK or consciously record the exception before trading.

---

## 2. §4 filter fields — presence, population, authority

Run `20260905_151448`, 294 Lab rows (190 CALL / 104 PUT).

| §4 field | Present | Populated | Producer | Authority match (AR-003 §8) |
|---|---|---|---|---|
| `governed_direction_record_sha256` | yes | **294/294** | `contracts/direction_governance.py` | ✔ and **294/294 match Options↔Lab** |
| `final_direction` | yes | 294/294 | direction governance | ✔ CALL 190 / PUT 104, **zero OTHER** |
| `hold_period` | yes | 294/294 | `macro_horizon_router` | ✔ `1_5d` 203 / `6_10d` 91, no `11_20d` |
| `invalidation_price` | yes | **294/294** | Vanguard geometry | ✔ |
| `structural_target` | yes | 294/294 | thesis geometry | ⚠ 13 rows carry **`0.0`** (QT-D04) |
| `contract_symbol` (OCC) | yes | 275/294 | Options selection | ✔ the 19 absent are `NOT_APPLICABLE_NO_SELECTED_CONTRACT` |
| `execution_viability_state` | yes | **294/294** | `contracts/long_option_policy.py` | ✔ — **fixed since RCA-002 (was 0/256)** |
| `execution_viability_bid/_ask/_spread_pct` | yes | 267/294 | long_option_policy | ✔ absent where no contract |
| `contract_bid_size` / `_ask_size` | yes | 275/294 | Options quote | ✔ — **fixed since RCA-002 (was 0/256)** |
| `selected_quote_timestamp_utc` | yes | 275/294 | Options quote | ✔ — **fixed since RCA-002 (was 0/256)** |
| `final_action` | yes | 294/294 | `execution_gate.py` | ✔ but see Condition 2 |
| `contract_dte` | **ABSENT** | — | — | ⚠ §4 requires "DTE ≥ 2 × planned hold"; the column is not in the Lab book under that name |

**Geometry, computed three ways:**

| Check | Result | CALL | PUT |
|---|---|---|---|
| `invalidation_price` on the correct side of `underlying_price` | **294/294** | 190/190 | 104/104 |
| `structural_target` on the correct side | 281/294 | 177/190 | 104/104 |
| underlying R:R ≥ 1.5 | 289/294 (median **3.00**) | — | — |
| **§4 geometry subset eligible** | **276/294** | 173 | 103 |
| …and with a selected contract | **270/294** | — | — |

**Invalidation geometry is perfect in both directions** — the headline AVS-SD-003 G-03/G-04 fix is verified on real output. The 13 failures on the target side are all the `structural_target = 0.0` rows, and all 13 are already `NOT_EXECUTABLE`.

---

## 3. Kill criteria — what fires today

| § | Criterion | Count | Fires? |
|---|---|---|---|
| 1 | Lab row `EXECUTABLE_SUBJECT_TO_GATES` or `BUY_*` with blank `invalidation_price` | **0** | clear |
| 2 | `governed_direction_record_sha256` mismatch | **0** of 294 | clear |
| 3 | STRANGLE / UNRESOLVED in the Lab book | **0** | clear |
| 4 | `unsupported operand` / `Traceback` / `Unhandled exception` in a trader-facing field | **0** | clear |
| 5 | Morning handoff finaliser failure or Lab/Execution disagreement | not run (EOD-only) | **unevaluable** |
| 6 | Audit `fail_count` > 0 for a genuine rule | **2** | **FIRES** |
| 7 | Two consecutive invalidation exits | n/a | n/a |

Criteria 1–4 are the ones that would indicate the RCA-002 defects had returned. **All four are clear.** That is the substantive result.

---

## 4. The three things a trader would most plausibly be misled by

**1. A `structural_target` of `0.0` read without the side check (13 rows).** `AEE`, `AVA`, `BEPC`, `CPRI`, `GIII`, `LZB`, `MD`, `NI`, `NSSC`, `OGE`, `TSSI`, `VNT`, `XRAY` — all CALL, all with a real `underlying_price` (8.42–106.47) and a real `invalidation_price`, and a target of exactly zero. A trader scanning the target column would read "0.00" as a missing value if lucky and as a price if not. AR-003 §6.3 forbids the fabricated zero explicitly, and this is the same defect class as the POC-as-zero that *was* fixed. All 13 are `NOT_EXECUTABLE`, so the filter catches them — but only if the trader applies the side check rather than reading the column. **QT-D04.**

**2. `eil_v3_verdict = EXECUTE_WITH_CAUTION` on a row that is stood down.** TTEK carries `invalidation_state=MISSING` and `options_verdict=STAND_DOWN`, yet the EIL verdict column says `EXECUTE_WITH_CAUTION`. The run's own integrity report calls the Final Decision fields *"RETIRED TELEMETRY — no candidate or capital authority"*, and TTEK never reaches the Lab. But a retired-telemetry column that still emits execution-shaped language next to a governed stand-down is a presentation trap. **QT-D06.**

**3. Profile and auction columns that are uniformly `NOT_EVALUATED`.** All 1,537 Vanguard rows carry `auction_state=NOT_EVALUATED`, `ready_to_trade=False`, `poc=None`. §4 explicitly says to ignore these — and that instruction is correct — but the Lab surfaces them, and a trader who has previously seen `ALIGNED` on 1,068 rows may read the uniform `NOT_EVALUATED` as a data outage rather than as the protection working as designed. **It is the protection working.** The zero usable profiles are a real capability gap (QT-D03), not a correctness gap.

---

## 5. What improved, verified on run artefacts

Against AVS-RCA-002's baseline (`20260904_004338`), and this is the part that should give the operator confidence:

| Property | Before | Now | Gate |
|---|---|---|---|
| `auction_state = ALIGNED` on unusable profiles | 1,068 | **0** | AG-01 PASS |
| POC published as `0.0` | 1,551 | **0** (all null) | AG-02 PASS |
| `ready_to_trade = True` with no profile | 1,068 | **0** | AG-03 PASS |
| `ARMED` with `invalidation_state = MISSING` | 43 | **0** | AG-05 PASS |
| Raw interpreter text in `stand_down_reason` | 36 | **0** | AG-09 PASS |
| Governed `STRUCTURAL_TARGET_UNRESOLVED` records | 0 | **191** (133 CALL / 58 PUT) | AG-10 PASS |
| Lab rows blank `invalidation_price` | 24 | **0** | AG-08b PASS |
| `EOD_CANDIDATE_ONLY` without invalidation | 13 | **0** | AG-07 PASS |
| Lab `execution_viability_state` | 0/256 | **294/294** | AG-11 PASS |
| Lab `contract_bid_size` / `_ask_size` | 0/256 | 275/294 + named absence | AG-11 PASS |
| Audit `fail_count` on the unremediated run | 2 (both spurious) | **16 genuine, 0 spurious** | AG-16 PASS |
| OTHER-direction handling | correct | correct | RG-07 PASS |

**Ten of the eleven AVS-SD-003 cycle-1 gaps are closed and verified by run artefact.** The exception is `monetisability_authority`, still 0/294 (QT-D07), which §4 lists as advisory and explicitly ignores for eligibility.

---

## 6. Recommendation

Trade on the §4 filter, subject to the three conditions in §1. Concretely:

1. **Run Evening on Monday night and Morning on Tuesday under the current code**, and apply §4 to Tuesday's Morning book. Do not carry `20260905_151448` forward — it was produced by superseded code.
2. **Before committing capital, confirm on the new run:** `fail_count` on the corrected audit, and specifically that criteria 1–4 remain at zero. If `fail_count > 0`, read the rows: a failure at `eil_enriched`/`execution` on a ticker absent from the Lab book is not the same risk as one in the book.
3. **Apply the correct-side check to `structural_target` manually**, and treat any `0.00` as missing until QT-D04 is fixed.
4. **Keep `AVSHUNTER_DYNAMIC_RELEASE_DISABLE_ALL=1` to hand.** It is a one-variable rollback to the legacy path the MVP was originally scoped against, verified in source at `contracts/dynamic_session_contract.py:135-143`.

**What would change the verdict to NOT INTACT:** a Monday run in which any of kill criteria 1–4 fires, or in which the profile stage again yields zero usable profiles *and* `min_usable_ratio` fails to stop the run — because that would mean the closure's new stage gate does not work either, and the operator would be trading a book whose ranking has no auction input and no guard that says so.
