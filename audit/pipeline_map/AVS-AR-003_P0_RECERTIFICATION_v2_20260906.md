# AVS-AR-003 P0 recertification — v2

**Date:** 2026-09-06 · **Supersedes:** `AVS-AR-003_P0_RECERTIFICATION_20260903.md`
**Issued under:** AVS-FIX-001 W0.4 (QT-D06 status vocabulary, QT-D08 documentation truth)
**Scope:** AVS-SD-002 Rev 1.1 implementation, with run-artefact evidence

---

## Why v2 exists

The 3 September recertification recorded seven P0s as **`CLOSED OFFLINE`**.
AVS-TST-QT-001 D-06 established that this is not a status the register can
carry beside `CLOSED`: `CLOSED` requires a run-artefact count, `CLOSED OFFLINE`
asserts only that code and tests agree, and putting them in one column invites
the reader to treat them as the same thing. AVS-FIX-001 §0 rule 10 and the
register's §7 retire it.

v2 says the same things about the same seven P0s, in a vocabulary that cannot
mislead, and adds the column that was missing: **`run_artefact_evidence`** — the
artefact, filter and count that supports each disposition, or an explicit
`AWAITING RUN` where none exists.

**Nothing here is upgraded. Two dispositions are downgraded** where the run
artefact contradicts or fails to support the offline claim (P0-02, P0-05).

## Status vocabulary

| Status | Meaning |
|---|---|
| `IMPLEMENTED — RUN EVIDENCED` | code contract holds AND a run artefact shows it, with a filter and a count |
| `IMPLEMENTED — OFFLINE VERIFIED` | code contract holds and tests prove it; no run artefact yet exercises it |
| `IMPLEMENTED — AWAITING RUN` | implemented, and the run that would evidence it has not happened |
| `OPEN` | not satisfied |

`CLOSED` appears nowhere in this document. It is the tester's assignment after
a run artefact shows the item firing.

---

## Result

**P0-08 remains OPEN**, unchanged and for the same reason: it expressly requires
accepted live completed-session, premarket, RTH and after-hours evidence, none
of which exists. G01 therefore remains `NOT_RUN` and is not inferred from unit
or replay tests.

Run-artefact citations are rows of `audit/pipeline_map/AVS-TST-QT-001/B_20260905_151448.csv`,
reproduced independently by `audit/ops/check_run_gates.py 20260905_151448` on
2026-09-06 (all twenty rows matched exactly).

| P0 | v1 said | v2 disposition | run_artefact_evidence |
|---|---|---|---|
| **P0-01** reproducible release | CLOSED OFFLINE | `IMPLEMENTED — AWAITING RUN` | **None.** `run_meta.json` on `20260905_151448` carries no `git_describe` and no plan-bound build receipt — `check_run_gates` reports `DDD-RUN-META-GIT-DESCRIBE ABSENT` and `DDD-BUILD-RECEIPT RECEIPT_MISSING`, both P0 failures. AVS-FIX-001 W0.1 adds `git_describe`; the receipt binding is evidenced on Monday's run. The run was also produced from an uncommitted tree, so no run to date is reproducible from a commit. |
| **P0-02** Market Profile fail-open | CLOSED OFFLINE | `IMPLEMENTED — OFFLINE VERIFIED` **(downgraded)** | AG-01 `profile_type==INSUFFICIENT_DATA & auction_state==ALIGNED` = **0** and AG-02 `poc==0.0` = **0** on `20260905_151448` — the protection holds. But the stage produced **zero usable profiles** on that run, so the fail-open path is what was exercised and the fail-*closed* path was not: `completed_profile_summary` carries neither `usable_ratio` nor `guard_decision` (pre-W1.4 format). AVS-FIX-001 W1.4 supplies both. **Awaiting a run where profiles actually exist.** |
| **P0-03** macro authority | CLOSED OFFLINE | `IMPLEMENTED — RUN EVIDENCED` | AG-12/13 `non-blank macro_as_of_utc` = **294/294** and `macro_packet_sha256` = **294/294** on the Lab book. Macro is stamped as lineage on every row and appears in no permission field. |
| **P0-04** economics authority | CLOSED OFFLINE | `IMPLEMENTED — RUN EVIDENCED` | AG-11 `non-blank execution_viability_state` = **294/294**, distinct from the monetisability columns; RG-02 Lab direction population **294/294** (CALL=190, PUT=104) with `final_action` written only by the Execution Gate. AVS-FIX-001 W3.4 and W3.5 add two further advisory columns, both asserted by authority tests to leave `final_action` unchanged. |
| **P0-05** Lab fail-open | CLOSED OFFLINE | `IMPLEMENTED — OFFLINE VERIFIED` **(downgraded)** | AG-08 `blank invalidation_price & permission==EXECUTABLE_SUBJECT_TO_GATES` = **0** and AG-08b `blank invalidation_price` = **0**: the protection holds. But three lineage fields were **275/294**, not 294/294 (AG-11 `contract_bid_size`, `contract_ask_size`, `selected_quote_timestamp_utc`), and `monetisability_authority` was **0/294** — the Lab published rows whose provenance was incomplete rather than presenting them as non-actionable. AVS-FIX-001 W1.3 fixes the authority column; the three lineage gaps are **filed, not fixed** (see `W0.3_msi_matrix_defects.md` class C, which may share their root cause). |
| **P0-06** restart collisions | CLOSED OFFLINE | `IMPLEMENTED — RUN EVIDENCED` | `check_run_gates` `DDD-RUN-IDENTITY` = **1** distinct run id and `DDD-COMPLETED-SESSION` = **1** distinct session (`2026-09-04`) across Discovery, Options, EIL, execution and the Lab book; RG-05 `nunique(trade_idea_id)==len` = **294/294**. Identity is stable and unduplicated across the run. The *restart* half is offline-only: no run has been restarted. |
| **P0-07** thesis geometry | CLOSED OFFLINE | `IMPLEMENTED — RUN EVIDENCED` | RG-07 `direction in (STRANGLE,UNRESOLVED) & invalidation_state!=NOT_APPLICABLE` = **0**, over STRANGLE=129 and UNRESOLVED=40 — the protected positive holds on real data. AG-10 `economics_reason==STRUCTURAL_TARGET_UNRESOLVED` = **191** (CALL=133, PUT=58): missing geometry defers explicitly rather than being guessed. AG-05 ARMED-with-missing-invalidation = **0**. **Caveat:** the same run published `structural_target == 0.0` on 19 Lab rows (13 CALL, 6 PUT) — a fabricated price, not a defer. That is QT-D04, fixed by AVS-FIX-001 W1.1, and the new `PRICE_FIELD_ZERO_AS_MISSING` audit rule fires on the unremediated artefact. |
| **P0-08** live lifecycle evidence | OPEN | **OPEN** | **AWAITING RUN.** Requires G18A–G18D live evidence across completed-session, premarket, RTH and after-hours, plus G19 measured operating budget. No Morning run exists on any stored run; `20260905_151448` has no `morning_validation` artefact. Unchanged from v1. |

---

## What changed the dispositions

Neither downgrade reflects a code regression. Both reflect the difference
between "a test proves the contract holds" and "a run artefact shows it
holding in production":

* **P0-02** — the protection is real and fires, but a run that produced zero
  usable profiles cannot evidence a profile-stage contract. The stage guard
  itself had no published decision until AVS-FIX-001 W1.4.
* **P0-05** — the Lab's *invalidation* protection is fully evidenced at
  294/294. Its *provenance* obligation is not: four fields were incomplete on
  the published book, one of them at 0/294.

## Regression evidence

The v1 figures stand and are not restated; they were measured on a different
code state. Evidence for the current state (branch `avs-fix-001`,
tag `avs-baseline-20260906`) is the AVS-FIX-001 claim sheet and the matrix
under `audit/pipeline_map/AVS-IMP-FIX-001/`.

## Promotion decision

**Unchanged from v1: do not enable dynamic production flags yet**, and note
that v1's own promotion decision was already the correct one — v2 changes the
vocabulary and the evidence column, not the recommendation.

The next acceptance phase remains observational: execute the controlled
four-state live cycle, preserve its immutable evidence, measure its resource
use, and then reassess G01/G18/G19. Two P0s (P0-01, P0-02) now have a named,
specific artefact that Monday's Evening run will either supply or fail to
supply, which is the point of the added column.
