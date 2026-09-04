# AVS-TST-SD-001 — Cycle 1

**Role:** independent tester. I did not write the code under test, I fixed nothing, and I executed no pipeline stage.
**Mode:** production code and all run data READ-ONLY. Source read `utf-8-sig`; SQLite opened `mode=ro`. All writes under `audit/pipeline_map/AVS-TST-SD-001/`.
**Specification under test:** `audit/pipeline_map/AVS-SD-001_solution_design.md` — **now present** (32,530 bytes, written 20:18). Its workstream exit gates are the acceptance contract.

---

## 1. Cycle intake

| Input | Status |
|---|---|
| **Specification** | **PRESENT.** AVS-SD-001. Note its own status line: *"DRAFT v0.2 **for review**"*, and §12 lists **D1, D2, D3, D4 as "Decision points for you (blocking)"** — all four unresolved. |
| **Claim sheet** (WS0–WS9 asserted complete + Level-1 numbers) | **NOT SUPPLIED.** No workstream is formally claimed, so there are no Level-1 numbers to agree with. |
| **Candidate run ID(s)** | **NONE.** Newest run under `data/output/runs/` is the frozen baseline `20260831_010309` itself. |
| **git identity** | `HEAD = 5d886f07c1d290f25600e2e7e62ae77aad85476a` (master — the *"Pre-remediation snapshot"* commit). |
| **git status** | **DIRTY:** 130 untracked entries (70 `.py`), 72 modified, 32 deleted. |
| Code delta since cycle 0 | **Zero.** No `.py` modified after 2026-08-31 20:55; the code under test is byte-identical to cycle 0. |

**Per the prompt's own rule — *"confirm `git status` clean; a dirty tree = cycle BLOCKED"* — this cycle is BLOCKED at intake.** Every result below is therefore attributable only to an *uncommitted working tree*, not to a reproducible SHA. I nonetheless completed the full Part A fix-verification, because that is the maximum verifiable work available and it answers the question the missing claim sheet leaves open: **what is actually implemented?**

Because no candidate run exists, **all Part B artefact-level regression measurement is BLOCKED — AWAITING MANUAL RUN.**

---

## 2. Headline: WS1 is *partially* implemented, and no other workstream is

With no claim sheet, I verified all ten workstreams mechanically. Result:
**5 PRESENT · 33 ABSENT · 9 BLOCKED**, with WS1 the only workstream showing real change.

### 2.1 WS1 — changes 1 and 2 landed; 3, 4, 5, 6 have not

Two of my automated verdicts were **false readings by my own regex**, which I caught and corrected by direct read. Recording both, because a tester's own false PASS is the failure mode this suite exists to prevent:

| Design change | Verdict | Evidence |
|---|---|---|
| §3.1 lifecycle consumes the **published governed invalidation**, not raw `ctx["stop"]` | **PRESENT** | `scripts/avshunter_options_intelligence.py:4583-4584`: `"invalidation_spot": _repair_alt_float(governed_handoff.get("invalidation_spot")…)`. Line drifted from the design's `:4549` → `:4583` (code was edited). |
| §3.2 lifecycle consumes the **routed planned hold** | **PRESENT** | `:4575` `"remaining_hold_sessions"`, `:4638` `"planned_hold_sessions"`. Drifted from `:4546` → `:4575`. |
| §3.3 `classify_remaining_runway` raises on a wrong-sided invalidation | **ABSENT** | Fixture-proven — see §2.2. |
| §3.4 `calculate_dte_requirement` domain-asserts hold ∈ {5,10,20} | **ABSENT** | Fixture-proven — see §2.2. |
| §3.5 third arm → `NOT_EVALUATED_NON_DIRECTIONAL` | **ABSENT as specified** (see discrepancy §4) | Token appears **nowhere** in the repo (exhaustive grep). |
| §3.6 kill the fabricated stop `entry × 0.97` | **PARTIAL** | The **named state exists and is tested**: `MISSING_AUTHORITATIVE_STOP` at `scripts/avshunter_options_intelligence.py:4094`, asserted by `tests/test_ev3_options_handoff.py:394`. But the **fabrication itself survives** at `:3809`: `stop = float(_raw_stop) if _stop_authoritative else entry*0.97`. Drifted from `:3801-3808` → `:3809`. |

> **Correction to my own instrument.** My repo-wide `0.97` grep reported six
> candidate sites; on inspection only **one** is a fabricated stop (`:3809`).
> The others are legitimate ATM strike windows — `spot*0.97, spot*1.03` at
> `:1904` and `:1973`, and `spot*0.92, spot*0.97` at `:3397`. The static
> check over-reported; the true count is one. Recorded so the number in
> `TST_static_fixverify.csv` is not read as six defects.

### 2.2 Fixture proof — the 437-PUT mechanism reproduced on demand

`fixtures/t_ws1_invariants.py` imports `contracts/options_liquidity_lifecycle.py` read-only and calls the pure functions on synthetic geometry. **Three-direction matrix, 15 tests, 9 PASS / 6 FAIL:**

| Test | Direction | Expected | Actual | Verdict |
|---|---|---|---|---|
| wrong-sided invalidation raises | **CALL** (stop 103 above entry 100) | raises | **no raise; returns `remaining_runway_state: THESIS_INVALIDATED`** | **FAIL** |
| wrong-sided invalidation raises | **PUT** (stop 97 below entry 100) | raises | **no raise; returns `THESIS_INVALIDATED`** | **FAIL** |
| correct geometry accepted | CALL / PUT | no raise, `THESIS_ACTIVE` | `THESIS_ACTIVE` | PASS ×2 |
| routed hold accepted | 5 / 10 / 20 | no raise | no raise | PASS ×3 |
| domain assert raises | 7 / 15 / 0 / 100 | raises | **no raise — all four accepted** | **FAIL ×4** |
| non-directional named outcome | STRANGLE / UNRESOLVED / blank / NONE | never INVALIDATED | `ValueError: unsupported long-option side` | PASS ×4 |

Two findings of substance:

1. **The wrong-sided-stop defect is symmetric, not PUT-specific.** CALL and PUT fail identically. The 437-PUT / 5-CALL production split therefore came from *which rows carried wrong-sided stops*, not from asymmetric code — so any fix must be verified on both sides, and a CALL-only test would have shown nothing.
2. **The non-directional third arm is already fail-closed**, though not in the form the design specifies: `_normalise_side` raises `ValueError` at `contracts/options_liquidity_lifecycle.py:85` for every OTHER value. It satisfies the gate's *"never INVALIDATED"* but not its *"named state"* wording. Recorded as a discrepancy, not a pass.

### 2.3 A safety result worth stating plainly

WS1 being *partially* done raised an obvious risk: with the consumer fixed (§3.1) but the fabricator alive (§3.6), does a fabricated `entry × 0.97` stop now launder through the *governed* path and acquire false authority?

**It does not.** Traced and confirmed:

- `:3809` fabricates the stop when `stop_loss` is missing or ≤ 0;
- `:4018` stamps `'stop_authoritative': False`;
- `:4019` stamps `'stop_source': 'LEGACY_DEFAULT_NOT_EV_ELIGIBLE'`;
- `:4095` the publisher gates on `bool(ctx.get('stop_authoritative'))` before computing any invalidation.

So a fabricated stop yields **no** governed invalidation, and the lifecycle — now reading `governed_handoff["invalidation_spot"]` — receives `None` rather than a fabricated number. The partial implementation is safe on this axis. **The residual exposure is the non-lifecycle consumers of `ctx['stop']`** that the design names in §3.6 (`exit_invalidation_price` in the morning plan, `scripts/exit_rules_engine.py:34`), which remain unaddressed.

### 2.4 WS7 scaffolding is in the source but not in the database

`scripts/avshunter_options_intelligence.py:4542-4547` now emits `supersedes_calculation_version`, `thesis_calculation_version`, `evidence_session_date` and `evidence_session_source` — WS7 §9.2 vocabulary. But `PRAGMA table_info` (mode=ro) on all three lifecycle tables shows **none** of `calculation_version`, `supersedes_event_id`, `correction_reason`, `corrected_by_run_id`. The protocol is being written into row payloads before the schema exists to persist it.

---

## 3. Per-gate verdict table

| WS | Design exit gate | Expected | Actual | Verdict |
|---|---|---|---|---|
| **WS0** | `git status` clean | clean | 130 untracked (70 `.py`), 72 M, 32 D | **FAIL** |
| WS0 | tag `baseline-20260831` | present | absent | **FAIL** |
| WS0 | 42 BOMs normalised | 0 | 42 | **FAIL** |
| WS0 | deterministic `scenario_builder` binding | 1 module | 3 copies (2 byte-identical) | **FAIL** |
| WS0 | morning baseline run captured | present | none exists | **BLOCKED** |
| **WS1** | false invalidations 442 → 0 | 0 | no candidate run | **BLOCKED** |
| WS1 | two new invariants demonstrably raise | both raise | **neither raises** (6 fixture FAILs) | **FAIL** |
| WS1 | no code path manufactures a stop | none | `:3809` `entry*0.97` alive | **FAIL** |
| WS1 | CALL/PUT/STRANGLE geometry variants pass | all pass | CALL FAIL, PUT FAIL, OTHER pass | **FAIL** |
| **WS2** | trigger populated 201/201 in book, = EIL | — | trigger pass 2 still at `:4770` **after** EIL `:4690`; Lab fallback alive at `intelligence_lab.py:653,:1860`; `execution_schema.py` has 0 trigger fields | **FAIL (static)** + BLOCKED (artefact) |
| **WS3** | Options→Horizon reconciles exactly | 0 unaccounted | worklist gate not at that boundary; `_DTE_SCAFFOLD` alive (`:2229`,`:2238`); stale comment alive (`:4139`); D2 unresolved | **FAIL (static)** + BLOCKED |
| **WS4** | zero two-branch direction conditionals | 0 | **all six coercion sites intact** (`trigger_confirmation_engine.py:290`, `exit_rules_engine.py:56`, `zero_dte_contract.py:368`, `short_swing_contract.py:318`, `short_swing_monitor.py:314`, `trap_engine.py:273`) | **FAIL** |
| **WS5** | macro absent from Discovery scoring | absent | 17 macro references remain; `MACRO_DIRECTION_SIZING` alive at 5 sites; D3 unresolved | **FAIL** |
| **WS6** | EOD book zero blank monetisability | 0 blank | call site **exists** (`eod_candidate_engine.py:873`); baseline artefact blank 201/201 but is **pre-change** — unverifiable | **BLOCKED** |
| **WS7** | supersession protocol present | 4 columns | **0 of 4** on any lifecycle table; 7 `write_final_run_manifest` call sites (design says reduce to 1); 104 `date.today()` sites; 2 session-clock importers | **FAIL** |
| **WS8** | zero type-bridging fallbacks; 8 states in one enum | lint green | `PENDING_MORNING_REFRESH` appears in **0** modules — the state enum does not exist; no `DATA_DEFECT` in the validator | **FAIL** |
| **WS9** | guard at emission; no fork twins | enforced | `action_is_within_guard` **0** call sites in `execution_gate.py`; both fork twins still present | **FAIL** |

---

## 4. Prompt-vs-design discrepancies (design wins; recorded)

1. **WS1 line numbers.** Prompt and design both cite `:4546`/`:4549`/`:4801-3808`. The code has drifted to `:4575`/`:4583`/`:3809`. Not a defect — evidence that editing occurred — but line-number gates must be re-anchored or they will produce false ABSENTs.
2. **WS1 §3.5 third arm.** Design specifies a *named state* `NOT_EVALUATED_NON_DIRECTIONAL`. The code instead **raises** `ValueError` for every non-directional side (`:85`). Fail-closed and arguably stronger, but not what the gate says. Adjudication needed.
3. **WS1 DTE gate wording.** Design §3 says `≤ 32 with zero unrouted rows`, then immediately qualifies it as `≤ 32 + unrouted, unrouted count reported` until WS3 lands. The prompt uses the qualified form. No conflict, but the gate has two readings and should be stated once.

---

## 5. Runs I need the operator to produce (I will not execute them)

| Run needed | Unblocks |
|---|---|
| **A post-fix evening run** against the current tree | All Part B regression; WS1/WS2/WS3/WS4/WS5/WS6 artefact gates |
| **A morning run over that evening run** | WS6 EOD byte-identity; WS7 manifest/immutability checks (I will hash the EOD columns and manifest before, compare after) |
| **A second evening run on the same completed session** | WS7 thesis-identity convergence |
| **Three evening runs — macro present / absent / stale** | WS5 macro-invariance gate |

---

## 6. Defects filed

`TST_defects_cycle1.csv` — TST-DEF-010 … TST-DEF-021. Severities: 1 × TEST_BLOCKED (intake), 9 × GATE_FAIL, 1 × UNTRACKED_CHANGE, 1 × spec discrepancy.

---

**Candidate run(s): NONE. Fix verification: 16 pass / 40 fail / 12 blocked. Regression: AWAITING RUN. Gates closed: [none]. Gates failed: [WS0, WS1, WS2, WS3, WS4, WS5, WS7, WS8, WS9]. Gates blocked: [WS0 morning-baseline, WS1 artefact replay, WS2 artefact, WS3 artefact, WS6, CT1 n/a].**
