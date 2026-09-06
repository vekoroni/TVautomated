# AVS-IMP-FIX-001 — implementation claim sheet

**Date:** 2026-09-06 · **Branch:** `avs-fix-001` · **Baseline tag:** `avs-baseline-20260906`
**Register of record:** `audit/pipeline_map/AVS-FIX-001_PRODUCTION_READINESS_FIX_REGISTER_20260906.md`
**Implementer:** Claude Code. **This session does not self-certify.** Nothing here is
`CLOSED`; that is the tester's assignment after a run artefact shows the item firing.

## Status vocabulary (§0 rule 10)

`IMPLEMENTED — OFFLINE VERIFIED` · `IMPLEMENTED — AWAITING RUN` · `BLOCKED` · `DEFERRED`

---

## 0. Summary

| | |
|---|---|
| Items in this claim sheet | **21** |
| `IMPLEMENTED — OFFLINE VERIFIED` | 9 (W0.1, W0.2, W0.3, W0.4, W0.6+W0.7, Part D, W3.1, W3.6, W4.2) |
| `IMPLEMENTED — AWAITING RUN` | 10 (W1.1–W1.6, W3.3, W3.4, W3.5, W3.9) |
| `BLOCKED` | 1 (W4.1 — one further credential probe needs ACK's authorisation) |
| `DEFERRED` | 1 (W0.5 — ACK's, interpreter pinning) |
| Commits on the branch | 20 (2 baseline + 18 item commits; W0.4 took two — see its row) |
| Tests added | **182** = 175 in new files (159 across 11 here + 16 in the Worker 3 package) + 7 into existing files (3 run-meta, 3 phase0, 1 msi one-minute-cadence) |
| Existing tests edited | 5 files, all classified; **0 `PROTECTION_WEAKENED`** |
| Backups | 20 pre-change + 3 retroactive/reconstructed (2 self-reported deviations, §7) |

**The two headline measurements:**
* **DEC-2** — widening the bands recovers **128** candidates (71 CALL / 57 PUT), of which
  **128 pass economics** and **127 clear the monetisability floor**. Not 195.
* **Early lane (W3.6)** — **not supported.** Median monetisable row buys IV **−1.9%**
  against its three-session-earlier level; only 12.2% are ≥ +20% above.

---

## 1. Part A — credential verification (W4.1)

| | |
|---|---|
| **Status** | **BLOCKED** |
| Files | `audit/ops/verify_anthropic_key.py` (new), `.env` (one line removed) |
| Backup | `backups/avs_fix_001_PartA_dotenv_prechange_20260906_143528/` |
| Commit | in the W0.1 baseline commit `dcbb73d`; the probe-ledger fix in `1c8429a` |

**Local facts — all pass.** User scope present (length 108, `sk-ant-api03-` prefix, no
whitespace, no CRLF, no quotes); Machine scope absent; process equals user;
`.env` line removed so the credential is single-sourced; `.env.txt` absent.

**`GET /v1/models` returned HTTP 400 `invalid_request_error`.** The script exits 1, so the
Part A pass condition is **not met**.

This is not a 401. A rejected credential returns `401 authentication_error`; a 400
`invalid_request_error` describes a malformed request or an account-level condition —
"credit balance too low" is returned in exactly this shape. The prompt's escalation rule
covers 401 ("stop and report — the environment, not the code, is wrong") and not this.

**Why it is BLOCKED rather than diagnosed:** the script as specified discarded
`error.message`, so the one permitted request produced a status with no explanation.
That defect is fixed — the message is now captured — but §0 rule 1 allows **exactly one**
`GET /v1/models` in Part A and it has been spent. A probe ledger
(`audit/ops/verify_anthropic_key_probe_ledger.json`) now records the spend and refuses a
second probe without `--authorised-reprobe`.

**Decision needed from ACK:** authorise one further probe (`--authorised-reprobe`), which
will return the provider's own explanation. **This gates Monday's macro build**, which
reads the same variable via `build_macro_json.py:559`.

`python build_macro_json.py --dry-run` — **exit 0**, 23 input files loaded, date
consistency confirmed at 2026-09-04, no API call, no files written.

---

## 2. Workstream 0

### W0.1 — baseline commit, tag, `git_describe`

| | |
|---|---|
| **Status** | **IMPLEMENTED — OFFLINE VERIFIED** |
| Commits | `dcbb73d` (baseline a), `5e68aca` (baseline b, `domain/`), `f6b6ab4` (git_describe) |
| Files | `.gitignore`, `intelligent_orchestrator.py`, `tests/test_msi_orchestrator_run_meta.py` |
| Backup | `backups/avs_fix_001_W0.1_prechange_20260906_134210/` |
| Tests | 3 added, 5 passed |
| run_artefact_evidence | **AWAITING RUN** — `check_run_gates` reports `DDD-RUN-META-GIT-DESCRIBE ABSENT` on `20260905_151448`, which is the pre-fix state. Monday's run supplies it. |

Two commits as the register preferred: the 4–6 Sep build, then the `domain/` refactor
separately. `git status --porcelain` is **empty**; tag `avs-baseline-20260906` points at
runtime profile `054a76be…`, matching the release manifest.

`git add -A` initially aborted on `audit/ddd_closure_testdeps/py.py`: thirteen
pytest-basetemp and vendored-testdep trees under `audit/` carry Windows ACLs git cannot
read. Each was added to `.gitignore`, anchored, and **verified to match 0 tracked paths**;
the 9 tracked XMLs inside `AVS-TST-SD-002-001/tmp/codex_remediation/` are preserved by
excluding only that directory's subdirectories.

`_git_baseline_identity()` was extracted so the property is testable without executing the
pipeline; a missing git still degrades to `"UNAVAILABLE"` rather than aborting a run.

### W0.2 — flag-default test integrity (QT-D01)

| | |
|---|---|
| **Status** | **IMPLEMENTED — OFFLINE VERIFIED** |
| Commit | `5465790` · Backup `backups/avs_fix_001_W0.2_prechange_20260906_134733/` |
| Existing test edited | `tests/test_dynamic_session_phase0.py` — **`OBSOLETE_ASSERTION_CORRECTED`** |
| Tests | 16 passed (1 renamed, 3 added) |

`test_all_new_features_are_disabled_by_default` called `from_environment({})` — the
explicit-mapping branch that hard-codes every flag False — and presented the result as the
production default. Production calls `from_environment()` and loads the governed profile,
where 8 of 9 are on.

The original assertion is preserved **verbatim** under a name describing what it actually
proves. Three added: the controlled-live-cycle set pinned **by name** with AUTO withheld;
`AVSHUNTER_DYNAMIC_RELEASE_DISABLE_ALL=1` returning every flag off; and the runtime
profile's SHA-256 pinned against the DDD release manifest — the guard that makes a silent
profile change impossible. The two profile tests run under an emptied environment so a
stray shell override cannot make the profile look like something it is not.

### W0.3 — `tests/msi/` into the matrix (QT-001 D-04)

| | |
|---|---|
| **Status** | **IMPLEMENTED — OFFLINE VERIFIED** |
| Commit | `1c8429a` · Backups `W0.3_…135228`, `W0.3b_…135630`, `W0.3c_…140250` |
| Existing tests edited | `tests/msi/test_computation.py` (`OBSOLETE_ASSERTION_CORRECTED` + `FIXTURE_CORRECTED`), `test_flow.py` / `test_functionality.py` (`FIXTURE_CORRECTED`) |
| Filed | `audit/pipeline_map/AVS-IMP-FIX-001/W0.3_msi_matrix_defects.md` |

Five files that had never run in acceptance. **34 failures → 24**, all 24 filed with root
cause in three classes. Nothing was made to pass by weakening an assertion.

**c07 arbitrated in favour of the code.** All six volume-allocation assertions passed; only
the cadence label failed, because the shared fixture's bars are +0/+5/+31 minutes — a
16-minute median, not one-minute data. Against AVS-SD-002 §9.1 the code satisfies both
halves (uniform allocation **and** disclosed basis), so the assertion was the defect. A new
test supplies twenty genuine one-minute bars so `ONE_MINUTE_ESTIMATED` keeps its coverage.

**Six tests died in setup on "2026-08-30 is not an XNYS session" — a Sunday.** Two
expressions of one defect: the `date()` constructors, and five fixture payloads timestamped
`1788120000` (that same Sunday at 20:00Z) which the chain resolver's 80% quote/session rule
then rejected. The deliberately-Sunday CLOSED-state instant is untouched — a blanket
replace corrupted it on the first attempt and was reverted.

**`test_logic.py` ran to completion** (95 tests, 7m17s); it was budget-blocked in QT-001.

**One failure this session caused and fixed:** L12 greps the tree for the literal
`BUDGET_EXHAUSTED`, and Part A's `verify_anthropic_key.py` was the only match in the
repository. Renamed. The pre-existing `test_logic` failure count is therefore **5, not 6**.

### W0.4 — documentation truth (QT-D08/D09/D10)

| | |
|---|---|
| **Status** | **IMPLEMENTED — OFFLINE VERIFIED** |
| Commits | `6757893`, `0498df7` (two: the second is the `.gitignore` negation that made the register trackable — the blanket `*.csv` rule was swallowing it) |
| Backups | `W0.4_…152201`, `QT-D10_retroactive_pre-tidy-20260904_…152146` |

Claim 5 corrected: the per-profile gate was **0.95 before and after**; the 0.90 is a **new
stage-level** `min_usable_ratio` over tickers — a different quantity, a stricter posture.
The stated 77/78 rationale was wrong (98.7% coverage fails on `last_region`, not coverage;
the real fix was the exclusive-`to` change).

All 17 test files classified in `test_edits_register.csv`: **12 UNRELATED** (pure
additions, 0 deletions), **4 OBSOLETE_ASSERTION_CORRECTED**, **1 FIXTURE_CORRECTED**,
**0 PROTECTION_WEAKENED**. QT-D05's alleged "one weakening" is examined, not dismissed:
`phase6` retired a test asserting the profile stage was *coupled* to the thesis flag, which
Rev 1.1 decoupled by design. **Residual for the tester:** its replacement asserts the stage
**defaults to enabled** when unset. Covered three ways (profile sets it, W0.2 pins the
profile hash, the kill switch still works) — but ACK should confirm the default is intended.

QT-D10 retroactive manifests reconstructed from `pre-tidy-20260904`; both files did change.
Labelled `retroactive: true` and **not** a pre-change backup. **QT-D10 is mitigated, not
closed.**

`AVS-AR-003_P0_RECERTIFICATION_v2_20260906.md` re-issued: `CLOSED OFFLINE` retired, a
`run_artefact_evidence` column on every P0. **Nothing upgraded; two downgraded** — P0-02
(protection holds, but a run with zero usable profiles cannot evidence a profile-stage
contract) and P0-05 (invalidation protection 294/294, but four provenance fields
incomplete, one at 0/294). **P0-08 stays OPEN.** Promotion decision unchanged.

### W0.5 — pin the venv base interpreter

**DEFERRED — operator.** ACK's, per the prompt.

### W0.6 / W0.7 — CLI hygiene and QT-D05 arbitration

| | |
|---|---|
| **Status** | **IMPLEMENTED — OFFLINE VERIFIED** |
| Commit | `38232a8` · Backup `backups/avs_fix_001_W0.6_prechange_20260906_140537/` |
| Tests | `tests/test_avs_fix_001_cli_hygiene.py`, 7 added, 7 passed |

`--data-mode` now emits a WARNING naming the flag and why it cannot apply on the dynamic
path. It fires only for a non-AUTO value, so the plan-only dispatch (which passes none)
correctly logged nothing.

`FINALISE` and `BUILD_THESIS` no longer share a callback object.
`assert_finalise_preconditions()` refuses unless the provider reports the session finalised
**and** the plan carries a run identity other than the accepted thesis's. **That second
check is not redundant:** `resolve_dispatch_plan` mints a fresh run id for FINALISE only
when the operator supplied none, so `--finalise --run-id <accepted run>` would have had the
evening workflow write into the accepted thesis's own directory. The guard can only refuse.

**QT-D05 closed as NOT_A_DEFECT** (`QT-D05_arbitration.md`). `test_c06` — now in the matrix
and executed, not merely cited — pins the disputed tie-break: equal adjacent counts expand
to the **higher** bin. The independent implementation used a strict `>`. No code change.
A documentation follow-up is filed: AVS-SD-002 §10.1 states neither tie-break convention.

---

## 3. Workstream 1

### W1.1 — `structural_target` null, never zero (QT-D04)

| | |
|---|---|
| **Status** | **IMPLEMENTED — AWAITING RUN** |
| Commit | `4a774e7` · Backup `backups/avs_fix_001_W1.1_prechange_20260906_141101/` |
| Files | `eod_candidate_engine.py`, `contracts/lab_control.py`, `handoff_contract_audit.py` |
| Tests | 14 + 17 subtests |
| run_artefact_evidence | **The new audit rule fires on the unremediated artefact.** `_semantic_contract_audit` over `20260905_151448`'s Lab book: `PRICE_FIELD_ZERO_AS_MISSING`, severity FAIL, **19 rows**, sample tickers `AEE,AVA,BEPC,CPRI,CWEN,EXK,G,GIII,LZB,MASS,MD,NI`. The *producer* fix awaits a run. |

The Options producer was already honest (NaN). The zero was manufactured twice downstream:
`eod_candidate_engine`'s `target_price` ladder ended in `default=0.0`, and `lab_control`'s
`first()` treats the string `"0.0"` as present. Both fixed; `first_price()` is the second
line of defence. `target_spot` was also added to both fallback chains — it carried a real
value on all 19 rows and simply was not consulted.

The audit rule was generalised from `MISSING_PROFILE_LEVEL_PUBLISHED_AS_ZERO` to
`PRICE_FIELD_ZERO_AS_MISSING` over six fields and five stages, with the one legitimate zero
(a 0.0 bid with `contract_bid_size == 0`) encoded as an exception that applies to the bid
only.

### W1.2 — retired EIL telemetry (QT-D06)

| | |
|---|---|
| **Status** | **IMPLEMENTED — AWAITING RUN** |
| Commit | `c72f312` · Backup `backups/avs_fix_001_W1.2_prechange_20260906_141601/` |
| Tests | 12 added |
| run_artefact_evidence | **Demonstrated on the unremediated artefact:** applying the suppression to `20260905_151448`'s `eil_enriched` (1,461 rows) takes contradictions **187 → 0**; 1,121 BLOCKED rows preserved; 153 legitimate EXECUTE rows untouched; TTEK suppressed with both reasons. A stage re-run awaits Monday. |

187 rows (127 CALL, 60 PUT, 0 OTHER) carried `EXECUTE*` beside a governed `STAND_DOWN`.
Suppressed to `NOT_EVALUATED` at `_ensure_eil_audit_contract`, the single chokepoint for
all three write paths. BLOCKED/WATCHLIST preserved — they agree with the stand-down and
explain it. No permission field is touched.

### W1.3 — `monetisability_authority` on every row (QT-D07)

| | |
|---|---|
| **Status** | **IMPLEMENTED — AWAITING RUN** |
| Commit | `a062ef0` · Backup `backups/avs_fix_001_W1.3_prechange_20260906_141949/` |
| Tests | 7 + 11 subtests |
| run_artefact_evidence | `check_run_gates` `AG-12/13:monetisability_authority` = **0/294 FAIL** on `20260905_151448`. Target 294/294 on Monday's run. |

Two independent causes: the F29 shape (allow-listed, never assigned) and five EOD
early-return paths whose shared `base` carried neither field — the 27 nulls.

**DEVIATION:** the register asks for `ADVISORY_ONLY`; the value stays
**`ADVISORY_SCENARIO_ONLY`**, the member AVS-SD-002 Phase 2 pinned. The two mean the same
thing, but `ADVISORY_ONLY` is not the vocabulary in use and §0 rule 9 forbids a second name
for one state. Now a shared constant rather than a literal in one producer.

### W1.4 — profile-stage guard semantics (QT-D03)

| | |
|---|---|
| **Status** | **IMPLEMENTED — AWAITING RUN** |
| Commit | `ab52833` · Backup `backups/avs_fix_001_W1.4_prechange_20260906_142207/` |
| Tests | 7 added; `tests/test_dynamic_session_phase4.py` 14 passed unchanged |
| run_artefact_evidence | `check_run_gates` reports `DDD-PROFILE-USABLE-RATIO` and `DDD-PROFILE-GUARD` as `NOT_EVALUATED — pre-W1.4 summary` on `20260905_151448`: the fields did not exist. Monday's run publishes them. |

`usable_ratio` divided by the **whole input**, so a session with many non-trading tickers
looked like a coverage failure; `failure_ratio` counted only transport failures, so ATR and
other data defects never reached the guard. Now four disjoint buckets with the identity
`input = processed + excluded + deferred + exceptions` asserted,
`usable_ratio = processed / (input − deferred)`, `failure_ratio = exceptions / input`, and
one named `guard_decision`.

`PARTIAL_SESSION` moved from `deferred` to a new `excluded` bucket — taking it out of the
coverage denominator would let a run where every ticker returned half a session report a
healthy ratio with zero profiles. Provider `no_data` is `TICKER_INACTIVE`, not
`INSUFFICIENT_BARS`, which describes a data defect.

All three shapes the prompt specifies are tested, including 12% deferral with a healthy
remainder, which the old denominator failed.

### W1.5 — `contract_dte` in the Lab book

| | |
|---|---|
| **Status** | **IMPLEMENTED — AWAITING RUN** |
| Commit | `d52461e` · Backup `backups/avs_fix_001_W1.5_prechange_20260906_142752/` |
| Tests | 14 + 5 subtests |
| run_artefact_evidence | Column absent from `20260905_151448` (it did not exist). `check_run_gates` carries a `FIX-W1.5:contract_dte` row for Monday. |

`xnys_sessions_between()` added to `session_clock`. From Friday 4 Sep, Labor Day Monday
7 Sep is three calendar days away and **zero sessions** away — the case a calendar DTE gets
wrong. Derived from the selected contract's own OCC expiry, so it can never describe a
different contract; an absent contract is null with
`NOT_APPLICABLE_NO_SELECTED_CONTRACT`, never 0.

### W1.6 — one spread authority (RCA3-D07, DEC-3)

| | |
|---|---|
| **Status** | **IMPLEMENTED — AWAITING RUN** |
| Commit | `800c03b` · Backup `backups/avs_fix_001_W1.6_prechange_20260906_143206/` |
| Tests | 15 + 41 subtests |
| run_artefact_evidence | **Leak measured on `20260905_151448`** (filter: `spread_pct` present, ≤ the flat 25%, > the row's own horizon band, all `1_5d`): Lab book **36 rows**, 24 `EXECUTABLE_QUOTE`, 23 also `MONETISABLE`; Options **151 rows**, 118 non-`STAND_DOWN` (97 ARMED, 21 EXECUTE). Baseline `20260904_004338`: 28 rows, 0 `EXECUTABLE_QUOTE`. |

The per-horizon band is now the authority at all three sites, clamped by the flat ceiling:
`min(band, flat)`. That clamp also binds `11_20d`, whose 35% band previously *exceeded* the
flat ceiling. An unrecognised horizon falls back to the tightest band.
`domain/long_option_execution.py` is untouched, asserted by a test.

**DISCREPANCY for the tester:** the prompt describes "the 3 rows QT-001/RCA-003 found
leaking". **Three does not reproduce** on `20260905_151448` under any filter constructed
here. The counts above are what the artefacts hold. The fix is the same either way, but the
number should be arbitrated.

---

## 4. Part D — the checkers ACK runs

| | |
|---|---|
| **Status** | **IMPLEMENTED — OFFLINE VERIFIED** |
| Commit | `a3f06b1` · New files, no backup required |

**`audit/ops/check_run_gates.py <run_id>`** — reproduces all **20 rows** of
`AVS-TST-QT-001/B_20260905_151448.csv` exactly, including the three-direction splits
(AG-10 191 CALL=133/PUT=58; RG-07 0 over STRANGLE=129/UNRESOLVED=40; RG-02 294
CALL=190/PUT=104). On `20260904_004338` it shows the baseline failures (AG-01 1068,
AG-02 1551, AG-05 43, AG-08 23, AG-08b 24, AG-09 36, AG-07 13, 17 genuine audit findings).
Exit 1 on both.

Read-only is **enforced**: `handoff_contract_audit.audit_run` writes beside the run by
default, so the call redirects `output_dir` to a discarded temporary directory. Verified —
the run's `diagnostics/` is untouched.

The eleven AG/RG numbers B never defined are reported `NOT_DEFINED_IN_B` rather than
invented, so the coverage gap stays visible.

**`audit/ops/check_warm_rerun.py <cold> <warm>`** — W2.3, from the control plane opened
read-only. Smoke-tested on `20260904_004338` vs `20260905_151448`, which are **not** a warm
pair (different sessions, 1,292 chain fetches), so the blocking check correctly fails. That
is the discrimination test, not a W2.3 pass.

---

## 5. Workstream 3

### W3.1 — DEC-2 shadow replay

| | |
|---|---|
| **Status** | **IMPLEMENTED — OFFLINE VERIFIED** (a measurement; it is its own evidence) |
| Commit | `c12ce01` · Backup `backups/avs_fix_001_W3.1_prechange_20260906_145506/` |
| Artefact | `w31_shadow_replay_20260905_151448.json` |

774 `BLOCK_SPREAD` rows (494 CALL / 280 PUT / 0 OTHER), all with a stored chain.
**128 recovered** (71/57) with the spread gate unchanged; **128 pass economics**;
**127 clear the floor** (125 MONETISABLE, 2 LIMITED, 1 NOT). +43% monetisable candidates on
a 294-row book. The 646 that recover nothing are blocked by genuine illiquidity.

The concern recorded against DEC-2 — that recovered candidates would be *available* but not
*good* — is not borne out. RCA-003 S2b projected 121 against the flat gate; this measures
128 against the **tighter** per-horizon band. **AVS-IMP-FIX-001 anticipated ~195, which
does not reproduce; 128 is recorded rather than parameter-fitted.**

### W3.3 — per-contract rejection taxonomy

| | |
|---|---|
| **Status** | **IMPLEMENTED — AWAITING RUN** |
| Commit | `1177a2b` · Backup `backups/avs_fix_001_W3.3_prechange_20260906_150028/` |
| Tests | 24 + 9 subtests |
| run_artefact_evidence | **AWAITING RUN** — the sidecar `options/contracts_tested_<run_id>.jsonl` is written by the Options stage, which this session may not execute. |

`contracts/contract_rejection.py` classifies every contract against the same gates. A
contract is attributed to the **first** gate it fails, so counts form a funnel that sums to
the chain and never double-counts. Wired as a **separate pass**, not an edit to
`_score_leg`, so an instrumentation error can never change which contract is selected.

### W3.4 — `monetisability_state_timevalue` (DEC-1, RCA3-D05)

| | |
|---|---|
| **Status** | **IMPLEMENTED — AWAITING RUN** |
| Commit | `a547692` · Backup `backups/avs_fix_001_W3.4_prechange_20260906_145617/` |
| Tests | 19 + 18 subtests |

PNW CALL (strike 100, ask 0.85, target 100.82, IV 18.7%, 8 DTE) → intrinsic
`NOT_MONETISABLE`, time-value `MONETISABLE` at **+84.3%**; deep-ITM → both; PUT mirror
identical. The lower-bound property (time value ≥ intrinsic) is asserted across eight
fixtures **and enforced in the code**, not assumed of the pricer.

**ADVISORY_ONLY.** It returns only `*_timevalue*` fields, so it structurally cannot
overwrite the intrinsic record — asserted by a test. Five authority tests.

One real bug caught while testing: an `or` chain read a legitimate hold of 0 sessions and a
DTE of 0 as missing, because both are falsy.

### W3.5 — derived tier (THS-001 §4)

| | |
|---|---|
| **Status** | **IMPLEMENTED — AWAITING RUN** |
| Commit | `58da85c` · Backup `backups/avs_fix_001_W3.5_prechange_20260906_150448/` |
| Tests | 26 + 69 subtests |
| run_artefact_evidence | Derived over `20260905_151448`'s 294 rows: **TIER_1 0, TIER_3 149, ARMED 3, WATCH 1, BLOCK 141**. `final_action` identical across every tier. |

**A measurement forced a design change.** The first implementation returned **115 TIER_1**
rows against THS-001's own expectation of "tens, not hundreds", because `trigger_state`,
`contract_dte` and `monetisability_state_timevalue` are all absent from that pre-fix book —
those checks silently could not fire, and their absence read as strength. That is the same
class of defect as W1.1's fabricated zero. **An unevaluable criterion is now itself a named
weakness** (`UNEVALUABLE_*`), never silence. Tier 1 is now correctly **empty** on a book
that predates the fields Tier 1 requires.

**It grants nothing.** Six authority tests assert `final_action` is unchanged across every
tier and every action value. ARMED requires a **named** promoter; without one the row is
WATCH.

### W3.6 — IV at selection

| | |
|---|---|
| **Status** | **IMPLEMENTED — OFFLINE VERIFIED** (a measurement) |
| Commit | `fc6521b` · Backup `W3.6_prechange_RECONSTRUCTED_…153417` (see §7) |

Five sessions back **could not be evaluated** — only four stored chain sessions precede the
run. Three sessions back (2026-08-31), 148 of 232 rows matched: **median −1.9%**, p25 −8.7%,
p75 +3.7%, **12.2%** at or above +20%. The mean (+3,296%) is reported, flagged
outlier-sensitive, and discarded; the rule uses the median as fixed in advance.

**Recommendation: do not build the early lane.** A shorter lookback biases *toward* finding
a rise, so failing to find one over three sessions is stronger evidence against than a
five-session window would need to be. Re-run when five sessions exist.

### W3.9 — outcome maturation runs nightly

| | |
|---|---|
| **Status** | **IMPLEMENTED — AWAITING RUN** |
| Commit | `f8a0528` · Backup `W3.9_prechange_RECONSTRUCTED_…153417` (see §7) |
| Tests | 14 + 2 subtests |

**Correction to the item as written:** maturation was *already* invoked in the Evening path,
so "make it run nightly" was largely already true. Two real gaps remained. It was nested
inside the decision-ledger **append** block, so a failure appending *this* run's candidates
also skipped maturation of every candidate from every previous run — work that does not
depend on the append. And it skipped **in silence** when the price database was absent.

Now its own stage publishing `diagnostics/outcome_maturation_<run_id>.json` on every path
with a named status (COMPLETE / SKIPPED / DEFERRED / FAILED), so a stage that ran and found
nothing is distinguishable from one that never ran. NON-CRITICAL, OBSERVATION_ONLY.

### W3.2, W3.7, W3.8, W3.10

**Not in this prompt.** W3.2 is sized by W3.1's result (**128**, not 195) and needs
AVS-SD-004 first.

---

## 6. Part F — Worker 3 (W4.2)

| | |
|---|---|
| **Status** | **IMPLEMENTED — OFFLINE VERIFIED** |
| Commit | `5683028` · Backup `backups/avs_fix_001_W4.2_prechange_20260906_151501/` |
| Package | `Documents/Codex/2026-07-24/a/worker3_foundation` (not a git repository) |
| Tests | **263 before → 279 after** (16 added), 188 subtests. **No live call.** |
| Existing test edited | `tests/test_live_semantic.py` — **`OBSOLETE_ASSERTION_CORRECTED`**, citing RCA3-D02 |

D01 — `error.type` and `error.message` on the receipt (capped 500 chars, ≤8 KiB read);
headers still never recorded, asserted by a test that puts a fake key in a response header.
D02 — budget consumed only on a 2xx whose body decoded into model output; a 200 with an
undecodable body does not spend it; the budget still binds.
D03 — `credential_source` and `sha256(key)[:8]`, recorded on failed calls too.

The edited test's *property* — that a redirect or error is never followed — is unchanged and
still asserted; only the incidental `calls == 1` (the retired policy) is inverted.

Because the package is unversioned, the commit carries the changed adapter, the new test
file, a unified diff of both changed files, and their SHA-256s.

---

## 7. Self-reported deviations

Recorded because a claim sheet that only lists successes is not evidence.

1. **Two backups were not taken before their item** (§0 rule 4): **W3.6** and **W3.9**.
   Reconstructed afterwards as `*_prechange_RECONSTRUCTED_*` from `git show <commit>^:<path>`.
   The content is **byte-exact** — the file was committed unchanged immediately before and
   after each item, so no intermediate edit can have been lost. Reversibility is intact;
   the process step was skipped, not the guarantee.
2. **`.env` was backed up redacted, not in plaintext.** §0 rule 2 ("never write any secret")
   outranks rule 4. The manifest carries the pre-change SHA-256 and a key-redacted copy;
   the value's source of record is the User environment scope.
3. **W1.3 keeps `ADVISORY_SCENARIO_ONLY`** where the register asks for `ADVISORY_ONLY`
   (§2 above).
4. **Part A is BLOCKED on a 400**, not passed (§1).
5. **W1.6's "3 leaking rows" does not reproduce** (§3).
6. **W3.1 measured 128, not the anticipated ~195** (§5).
7. **`.gitignore` was edited twice** — once in W0.1 to make `git add -A` possible at all,
   once in W0.4 so the test-edits register could be tracked. Both are anchored, scoped, and
   verified against tracked paths.
8. **One failure this session introduced** (W0.3 L12) was found and fixed; it is why the
   pre-existing `test_logic` count is 5 and not 6.

---

## 8. Verification

* **`git diff --check`** — clean on every source file (`*.py`, `*.json`, `*.md`,
  `.gitignore`, `*.csv`). The only hits are generated evidence: pytest JUnit XMLs and a
  captured unified diff, which legitimately contain trailing whitespace from test output.
* **`py_compile`** — all **36** changed Python modules compile.
* **Plan-only dispatch** — `--evening --plan-only --as-of-utc 2026-09-06T15:26:47Z`, exit 0,
  plan hash `df651c1698ad…`, resolved BUILD_THESIS, ceiling EOD_PREPARED, session
  2026-09-04, estimated physical requests 0. **Snapshot over 52,754 files** across
  `data/output/runs`, `data/output/run_plans`, `data/canonical`, `dropbox` and `logs`:
  0 added, 0 removed, **1 modified — `logs/orchestrator.log`**, the logger's own file. No
  run directory, no persisted plan record, no canonical database, no dropbox artefact.
  Evidence: `plan_only_snapshot_diff.txt`, `plan_only_dispatch.log`.
* **`build_macro_json.py --dry-run`** — exit 0, no API call, no files written.
* **Replay of the Lab/EOD stages over `151448`'s pinned inputs: NOT POSSIBLE.** No replay
  harness exists. `tools/cds2_replay_lifecycle_shadow.py` reconciles stage *membership*
  through the lifecycle and `pipeline_interpreter/automation_v2/replay.py` is request
  *serialisation*; neither re-executes a stage. The orchestrator's own REPLAY action raises
  `"REPLAY is research-only and must use the offline replay runner"`, and that runner is not
  in the tree. **This is why W1.1–W1.6, W3.3, W3.4, W3.5 and W3.9 are `AWAITING RUN`.**
  Where a fix could be demonstrated against the stored artefact without executing a stage
  (W1.1's audit rule firing on 19 rows; W1.2's 187 → 0; W1.6's leak counts; W3.5's tier
  distribution), that is recorded above as partial evidence and labelled as such.
* **Full matrix** — see §9.

---

## 9. Full acceptance matrix

Run with `--skip-orchestrator`: §0 rule 1 forbids this session from invoking `--evening` in
any form, self-test flag included. **The tester runs it without that flag**; matrix item 3
(the CDS startup self-test) is unverified by this session and marked so in the summary JSON.

**159 files, one isolated process each** (`tests/`, `tests/qa/`, `tests/rca/` and — for
the first time, per W0.3 — `tests/msi/`). Artefacts under
`audit/pipeline_map/AVS-IMP-FIX-001/matrix_20260906/`, per-file XMLs under its
`pytest_xml/`.

| | |
|---|---|
| tests | **1,762** |
| passed | **1,733** |
| failures | **25** |
| errors | **0** |
| skipped | 4 |

**Every one of the 25 is accounted for. Zero unexplained failures.**

| File | Failures | Explanation |
|---|---|---|
| `msi__test_regression` | 13 | filed, class C (schema/materializer field-name drift) |
| `msi__test_logic` | 5 | filed, classes A and B |
| `msi__test_functionality` | 4 | filed, classes A and B |
| `msi__test_flow` | 2 | filed, class A (stale absence assertions) |
| `test_cds2_historical_prices` | 1 | pre-existing, environment (`NO_SOURCE_ALLOWED`) |

The 24 `tests/msi/` failures are the ones W0.3 filed with root cause in
`W0.3_msi_matrix_defects.md`; none is a regression, and the reason they were invisible
until now is that the pack was outside the matrix. **Entry-point imports:** all four OK
(`intelligent_orchestrator`, `morning_gate`, `intelligence_lab`, `pipeline_interpreter`).

**`compileall` reports 4 error lines, none of them a source defect:** two
`PermissionError` pairs on `audit/ddd_closure_testdeps/py.py` and
`audit/ddd_readiness_tmp/pydeps/py.py` — the same ACL-locked vendored-testdep trees that
made `git add -A` abort in W0.1 and are now gitignored. Every one of the 36 changed
modules compiles (§8).

**Known pre-existing failure:** `tests/test_cds2_historical_prices.py::test_backfill_direct_script_launch_can_import_canonical_data`
fails with `NO_SOURCE_ALLOWED` — no permitted price source in this offline environment.
Proved pre-existing by running the file at the `avs-baseline-20260906` tag in a detached
worktree: **2 failures at baseline, 1 on this branch.** Not investigated further; no credit
is claimed for the one that now passes.

---

## 10. What ACK runs next

```
# 1. Authorise the second credential probe (BLOCKED item W4.1) — needed before the macro build
python audit/ops/verify_anthropic_key.py --authorised-reprobe

# 2. Monday evening, the Evening run on committed code (W2.1)
python intelligent_orchestrator.py --evening

# 3. Then, on that run
python audit/ops/check_run_gates.py <run_id>

# 4. Tuesday morning (W2.2), then again
python intelligent_orchestrator.py --morning
python audit/ops/check_run_gates.py <run_id>

# 5. Tuesday/Wednesday warm rerun (W2.3)
python audit/ops/check_warm_rerun.py <cold_run_id> <warm_run_id>
```

`avs-fix-001` is **not merged**. That happens after the tester's pass and Monday's run.
