# AVS-RCA-002 Part B — The pipeline as it actually executed

**Run:** `20260904_004338` (EVENING, session 2026-09-03)
**Command:** legacy `python intelligent_orchestrator.py --evening` (inferred: `AVSHUNTER_DYNAMIC_PLAN_ENABLED` was off, so `intelligent_orchestrator.py:6346` was never entered)
**Companion:** `B_flag_topology.csv`
**Prerequisite:** every count cited here is `CONFIRMED` in `A_counts.csv`.

---

## B1. The executed stage graph

### B1.1 What ran

Reconstructed from `logs/orchestrator.log` (run window `00:16:45` → `04:47:22`) and `run_meta.json`. `▶`/`✅` markers are the orchestrator's own stage delimiters; row counts come from the drop-off checkpoints and the stage CSVs.

| # | Stage | Start → End | Duration | In → Out | Flag consulted |
|---|---|---|---|---|---|
| 0 | Preflight / scripts check | 00:16:45 | 1s | — | `cfg.COMPLETED_PROFILE_ENABLED` at `:973` → **False**, so `BUILD_COMPLETED_PROFILES` was **not** added to `required` |
| 1 | Macro normaliser + bond sidecar | 00:16:45 → 00:16:46 | 1s | — | none |
| 2 | Actuarial cache (4.6) | → 00:18:48 | 2m 02s | 3,816,857 rows → 508 states / 454 valid | none |
| 3 | Actuarial transition matrix (4.7) | 00:18:48 → 00:20:08 | 1m 20s | — | none |
| 4 | **Discovery ULTIMATE** | 00:20:08 → 00:43:40 | **23m 32s** | universe → **1,601** selected / 1,719 excluded | none |
| 5 | External Intel review lane | 00:43:40 → 00:43:42 | 2s | 1,601 | none |
| 6 | Macro enrichment → Discovery | 00:43:42 → 00:43:44 | 2s | 1,601 | none |
| 7 | Quality validation + regression check | 00:43:44 | <1s | 1,601 | none |
| 8 | Position tracker | 00:43:44 → 00:43:47 | 3s | — | none |
| 9 | Pin run directory (4.5) | 00:43:47 → 00:43:48 | 1s | drop-off 3,320 | none |
| 10 | Build packages from Discovery | 00:50:46 → 00:56:42 | 5m 56s | 1,601 → 1,601 packages | none |
| 11 | Inject macro into packages | 00:56:45 → 01:01:13 | 4m 28s | 1,601 | none |
| 12 | Backfill timeseries (EOD) | 01:01:13 → 01:13:29 | 12m 16s | 1,601 | none |
| **13** | **Completed Market Profile (Phase 4)** | **01:13:29** | **SKIPPED — 0s** | **—** | **`cfg.COMPLETED_PROFILE_ENABLED` at `:2417` → False; `else` at `:2429` logged "built but not yet promoted"** |
| 14 | Trap-to-Launch (5.5) | 01:13:29 → 01:24:49 | 11m 20s | 1,601 | none |
| 15 | **VANGUARD** | 01:24:49 → 02:36:17 | **71m 28s** | 1,601 → **1,551** (50 dropped) | `market_profile_contract_required` **False on all 1,601 packages** → `auction_synthesizer.py:66-144` legacy branch |
| 16 | **Options Intelligence (8b)** | 02:36:28 → 03:47:25 | **70m 57s** | 1,551 → **1,454** (97 dropped) | none. 1,264 physical MarketData chain fetches |
| 17 | Horizon Router (1B) | 03:47:30 → 03:47:35 | 5s | 1,454 → 1_5d 912 / 6_10d 352 / blocked 190 | none |
| 18 | EV-1.5 Production Evidence | 03:47:42 → 03:50:18 | 2m 36s | 299 evaluated (24.7% coverage) | `AVSHUNTER_EV3_SHADOW_ENABLED` (default **on**) |
| 19 | EV-3 Advisory Overlay | 03:50:18 → 03:50:27 | 9s | advisory only | `AVSHUNTER_EV3_AUTHORITY_ENABLED` off → `ev3_production_authority: false` |
| 20 | Actuarial enrichment (8.5) | 03:50:27 → 04:02:42 | 12m 15s | 1,601 patched (exact 1,145 / fallback 400 / no_match 6) | none |
| 21 | Phantom scoring (7.5) | 04:02:42 → 04:12:09 | 9m 27s | — | none |
| 22 | Core Intel exporter (8c) | 04:12:09 → 04:12:16 | 7s | — | none |
| 23 | Trigger layer (8.6) | 04:12:17 → 04:34:14 | 21m 58s | 1,601 patched | none |
| 24 | SuperBrain passthrough (8d) | 04:34:14 → 04:34:18 | 4s | 1,454 | none |
| 25 | Catastrophe gate | 04:34:25 | 0s | **removed Sprint 2 — no-op** | none |
| 26 | Wall Break scorer (8e) | 04:34:25 → 04:34:34 | 9s | — | none |
| 27 | Actuarial CSV injection + WS2 trigger spine | 04:34:34 → 04:37:19 | 2m 45s | 1,454 (fill 100%) | none |
| 28 | EIL (Phase 9) | 04:37:19 → 04:39:54 | 2m 35s | 1,454 → block rate 79.7%; A 14 / B 91 / C 103 | `eil_eod_mode = EOD_SYNTHETIC` |
| 29 | Q-Omega GARCH (10a) + merge (10b) | 04:41:24 → 04:44:16 | 2m 52s | patched retroactively into EIL | none |
| 30 | EOD Candidate Engine (10) | 04:44:16 → 04:45:58 | 1m 42s | 1,454 → **256** candidates + 0-row shadow book + 78-row regime watch | none |
| 31 | Integrity + handoff + UAT reports | 04:46:00 → 04:46:24 | 24s | `technical=PASS`, `semantic=DEGRADED`, handoff `FAIL` | none |
| 32 | Intelligence Lab book | 04:46:24 → 04:47:22 | 58s | 256 → **256** (`final_opportunity_book`) | `AVSHUNTER_LAB_DYNAMIC_VIEW_ENABLED` off → **no `lab_signal_book_v3`** |
| 33 | Interpreter prep + finalisation | 04:47:22 | <1s | — | `pipeline_interpreter_prep_enabled: true` |

Population chain, reconciled at every boundary: **3,320 universe → 1,601 discovery → 1,551 Vanguard → 1,454 Options → 256 candidates → 256 Lab.** No unexplained loss; the drop-off audit accounts for all 3,320.

### B1.2 Against AR-003 §5.1 (as-is) and §5.2 (target)

The executed graph is **§5.1 exactly**, including every ordering defect §5.1 complains about:

- *"Horizon runs after Options even though downstream economics and evidence are meant to use the governed hold"* — confirmed: Options at #16, Horizon Router at #17.
- *"GARCH runs after EIL and is patched back into an already-created file"* — confirmed: EIL at #28, GARCH at #29 with an explicit `10b: GARCH → SUPERBRAIN MERGE`.
- *"Several compatibility layers copy or patch fields after the producer has completed"* — confirmed at #20, #23, #24, #27, #29.

Not one element of the §5.2 target sequence was reached. The measure of that is stark:

| §5.2 target element | Status in this run |
|---|---|
| Run + invocation identity | partial — `run_meta.json` has `canonical_run_id`, but no dispatch plan record |
| Canonical daily observations | partial — Discovery still calls Polygon directly (§B4) |
| Discovery and frozen Direction Governance decision | **achieved** — 1,454 governed direction records, 256/256 hash match (A7-09) |
| Authorised survivor worklist | partial — `stage_worklist` populated, but not gating |
| **Governed horizon and thesis geometry** *before* options | **not achieved** — Horizon runs after Options |
| **Canonical completed-session intraday observations** | **not achieved** — stage skipped |
| **Completed Market Profile evidence** | **not achieved** — stage skipped |
| **Vanguard using typed evidence packets** | **not achieved** — legacy fabrication branch |
| Options selection using the governed thesis/horizon | partial — uses direction, not governed horizon |
| Advisory EV/volatility evidence | achieved — EV3 advisory, `ev3_production_authority: false` |
| **EOD opportunity book with complete lineage** | **not achieved** — G-06, G-11 |
| Morning validation → exact quote refresh → RTH profile | not run (EOD-only) |
| Execution Gate | not reached |
| Governed Lab surface | partial — `final_opportunity_book` only, no v3 book |
| Read-only Interpreter | prep only |
| Append-only decisions and outcomes | **not achieved** — ledger flag off |

**Six of sixteen target elements are unreachable while `AVSHUNTER_DYNAMIC_PLAN_ENABLED` and `AVSHUNTER_DYNAMIC_THESIS_ENABLED` are off.** Only one — direction governance — was fully achieved, and it was achieved on the *legacy* path, which is the proof that legacy-path correctness is possible without the dynamic tree.

### B1.3 Stages that exist in code but were skipped

| Stage / capability | Skipped because | Evidence |
|---|---|---|
| `scripts\build_completed_market_profiles.py` | `AVSHUNTER_DYNAMIC_THESIS_ENABLED` off | `intelligent_orchestrator.py:2417` / log 01:13:29 |
| `_governed_profile_verdict` + `_not_evaluated` | `market_profile_contract_required` False (downstream of the above) | `auction_synthesizer.py:59`; `timeframe='intraday'` ×1,551 |
| `orchestrator\dynamic_dispatcher` (whole tree) | `AVSHUNTER_DYNAMIC_PLAN_ENABLED` off | `:6346` never entered |
| `orchestrator\dynamic_validation.validate_thesis` + P0-07 explicit defer | `AVSHUNTER_DYNAMIC_VALIDATION_ENABLED` off | `:6394`; `PHASE5_CLAIM_20260903.json:8` |
| `lab_signal_book_v3` / frozen-thesis + current-validation axes | `AVSHUNTER_LAB_DYNAMIC_VIEW_ENABLED` off | `morning_handoff_finalizer.py:373`; no v3 file in the run |
| `canonical_data\decision_outcome_ledger` | `AVSHUNTER_DECISION_LEDGER_ENABLED` off | `morning_handoff_finalizer.py:463`; no `decision_outcome_ledger.sqlite` |
| AUTO dispatch | `AVSHUNTER_DYNAMIC_AUTO_ENABLED` off | `:6390` |
| Catastrophe gate | **removed in Sprint 2**, not flagged | log 04:34:25 |
| Enhancement layer 9B / trade book 9C | disabled pending confirmation | `pipeline_integrity` `action_items` |

---

## B2. Why each offline-closed P0 reappeared

The recertification (`AVS-AR-003_P0_RECERTIFICATION_20260903.md`) closed P0-01…P0-07 "at the offline/code-contract level" on 165 + 76 + 900 passing tests. Every one of those tests is, as far as I can determine, correct. The failure is not in the tests. **It is that the two-level closure standard was applied at one level only.**

Using the prompt's taxonomy — (a) correct for the path it tested, but that path is not the production path; (b) tested a contract without testing the writer that populates it; (c) simply wrong — none of the four is (c).

### P0-02 — Market Profile fail-open → **(a)**

The recertification's evidence reads: *"Typed completed/developing profile packets; unavailable profiles remain null/`NOT_EVALUATED`; no profile-derived readiness."* Every clause is true of `_governed_profile_verdict` and `_not_evaluated` (`auction_synthesizer.py:147-227`), and the Phase 4 acceptance pack (10/10) proved it. But those functions are reached only when `market_profile_contract_required` is `True`, whose sole producer runs only when `AVSHUNTER_DYNAMIC_THESIS_ENABLED=1`, and whose value defaults to `False` at five independent points (§A1.2b). **The tests exercised a branch that production cannot enter.** Production took the branch at `:66-144` and emitted 1,551 fabricated profiles and 1,068 daily-only `ALIGNED` — the exact condition AR-003 line 673 forbids. Closure documents: `AVS-SD-002_PHASE4_CLOSURE_20260903.md`, `AVS-AR-003_P0_RECERTIFICATION_20260903.md:13`.

The Phase 4 closure contains a second, compounding defect. Its "Rollout control" section reads: *"`AVSHUNTER_COMPLETED_PROFILE_ENABLED` remains disabled by default."* **That environment variable does not exist** (A1-07). The real gate is `AVSHUNTER_DYNAMIC_THESIS_ENABLED`, six lines above the integration point in the same file the closure describes. This single sentence is the origin of the operator's uncertainty and of the prompt's §7 Option 2. A closure document that names the wrong flag cannot be used to reason about production state, and it is why C2 must decide the flag policy from the code rather than from any closure.

### P0-04 — economics authority → **(b)**

The recertification reads: *"Quote viability is separated from scenario EV/R:R; final capital authority remains Execution Gate."* Both halves are true and both are irrelevant to what happened. `contracts\long_option_policy.py:177-234` computes a full, correct `execution_viability_state` vocabulary; the Morning candidate file carries it 256/256; Phase 2 closure states *"The final Execution Gate consumes the execution-viability state and verifies its exact contract identity."* — and `execution_gate.py:187` does exactly that.

**But the Lab never receives it: 0/256** (A3-03). `execution_viability_state` is declared in the `contracts\lab_control.py` allow-list at `:256-265` and has **no `first(sig, ...)` assignment in the row builder**. The contract was tested; the writer that populates it was not. A test asserting "the allow-list contains `execution_viability_state`" and a test asserting "Execution Gate reads `execution_viability_state`" both pass while the column is empty on every row of the delivered book.

The same taxonomy covers the second half of P0-04. `compute_trade_economics` (`avshunter_options_intelligence.py:5428`) has no `None` guard on `structural_target`, and 36 rows died inside it. No economics-authority test asserts that the function *terminates* for a thesis with no target. Closure documents: `AVS-SD-002_PHASE2_CLOSURE_20260903.md`, `AVS-AR-003_P0_RECERTIFICATION_20260903.md:15`.

### P0-07 — thesis geometry → **(a)**, with an aggravating factor

The recertification reads: *"Frozen direction/horizon/entry/target/invalidation contract plus symmetric geometry tests and explicit defer on missing decision-critical data."* The frozen contract is genuinely delivered and is the run's strongest positive (A7-09: 256/256 governed direction hash match). The symmetric geometry tests are real. **The explicit defer is behind `AVSHUNTER_DYNAMIC_VALIDATION_ENABLED`** (`PHASE5_CLAIM_20260903.json:8`), so on the `--evening` path there is no defer at all.

The aggravating factor is what filled the vacuum. With no defer, 173 directional rows proceeded with `invalidation_state = MISSING`, and **43 of them were `ARMED`** (A2-02) — 15 reaching the Lab as `EXECUTABLE_SUBJECT_TO_GATES`. On the PUT side the vacuum was filled by an unhandled `TypeError`, which stood 36 rows down. So the run's *only* operative protection against arming a thesis with no invalidation was an exception that fires on one direction and not the other. That is not a defer; it is an accident that happened to be safe.

I record one disagreement with the recertification's own framing here. "Symmetric geometry tests" passed while `compute_trade_economics` is *asymmetrically survivable*: the CALL branch carries the identical unguarded subtraction (`:5464`) and was saved only because its 12 exposed rows failed unrelated contract-quality gates first (A2-07). Symmetry was asserted about the geometry formulae, not about the failure behaviour of the code that consumes them.

### Lineage loss (P1-03 / P1-04 family) → **(b)**, and it is a *recurrence* of a defect this build explicitly fixed

This is the most instructive of the four. The Phase 5 closure states:

> *"Corrected the Morning handoff defect where calculated `ms_*` evidence was written only to `live_map` and never copied into the result rows consumed by the Lab."*

That is fix F29, and it was applied correctly — to `ms_*`. **The identical shape was left in place for three other field families**, all of which failed in this run:

| Family | Same shape? | Result |
|---|---|---|
| `ms_*` | fixed in Phase 5 | works |
| `execution_viability_*` | not fixed | 256 → **0** at the Lab boundary |
| `contract_bid_size` / `contract_ask_size` / `contract_quote_quality` | not fixed | 241 → **0**, column absent from the Morning projection |
| `macro_*` (19 of 24 columns) | not fixed | declared in the Lab schema, produced by nobody |

And `eod_candidate_engine.py:879` computes `"selected_quote_timestamp_utc": quote_timestamp` into a dict that is never projected into the candidate CSV — the *original* F29 shape, still live, in a different module.

The build treated F29 as a bug in one field family. It is a **structural property of the handoff**: any field can be allow-listed at the consumer without being projected at the producer, and nothing in the system detects the resulting column of nulls. Until the handoff is contract-tested field-by-field with a populated-count assertion (C5), this class will keep recurring.

### B2.1 The finding of the review

**Every P0 in this run was closed without a run artefact showing the fix firing, and the closure standard permitted that.**

The evidence column of the recertification table cites test packs, contracts and manifests. Not one entry cites a row of production output. The Phase 4 closure's cache claim — *"Exact-cache test: second completed-profile execution issued 0 physical provider requests"* — is a unit-test observation offered where a ledger reconciliation was required; the run's actual ledger shows 1,264 physical requests and, correctly, zero reuse (§A5.2).

The recertification's own final paragraph is right and was not followed to its conclusion: *"Do not enable dynamic production flags yet. The next acceptance phase is observational."* The gap is that "do not enable yet" was applied to *protections* as well as capabilities. An observational phase that observes the legacy path observes none of the fixes.

Named closure documents that assert closure without a run artefact: `AVS-SD-002_PHASE2_CLOSURE_20260903.md`, `AVS-SD-002_PHASE4_CLOSURE_20260903.md`, `AVS-SD-002_PHASE5_CLOSURE_20260903.md`, `AVS-SD-002_PHASE7_CLOSURE_20260903.md`, `AVS-AR-003_P0_RECERTIFICATION_20260903.md`.

---

## B3. Flag topology

Full table in `B_flag_topology.csv`. The structural findings:

**All eight flags default `False` and all eight were off.** `_as_bool` (`contracts\dynamic_session_contract.py:89-97`) returns `False` for unset, empty *and unrecognised* values, so a typo cannot accidentally enable anything — this is genuinely safe, and `AVS-TST-SD-002-001\AVS-TST-SD-002-001_FINDINGS.md:16` reached the same conclusion.

**Two flags gate a fail-closed protection rather than a new capability. These are the design's mistake.**

| Flag | Capability it gates | **Protection it also gates** |
|---|---|---|
| `AVSHUNTER_DYNAMIC_THESIS_ENABLED` | completed-profile acquisition; `BUILD_THESIS` dispatch | **Vanguard fail-closed** (`_governed_profile_verdict` / `_not_evaluated`) — the whole of P0-02 |
| `AVSHUNTER_DYNAMIC_VALIDATION_ENABLED` | dynamic `validate_thesis` service | **Explicit defer on missing decision-critical data** — the operative half of P0-07 |

A protection that is off by default is not a protection; it is an unexercised capability. Worse, in the profile case the coupling is *transitive and invisible*: nothing in `auction_synthesizer.py` mentions a flag. A reader auditing the fail-open fix sees a clean fail-closed branch and no gate. The gate is five files away, expressed as five separate `False` defaults on a boolean.

**One flag is a name trap.** `AVSHUNTER_PROFILE_LIFECYCLE_ENABLED` is the only profile-named flag and it does **nothing** on `--evening`; its sole read is `:6399`, inside the dynamic-plan block. Both the operator's assessment and the prompt's §7 Option 2 reach for a profile-named flag; neither existing one does the job under that name.

**Two flags are undocumented in the closures**, and the one that matters most is documented *wrongly*: the Phase 4 closure names `AVSHUNTER_COMPLETED_PROFILE_ENABLED`, which does not exist. This is a P1 documentation defect with P0 consequences, since it is the only place an operator would look before an Evening run.

**One pattern is done right and should be copied.** `AVSHUNTER_LAB_DYNAMIC_VIEW_ENABLED` and `AVSHUNTER_INTERPRETER_DYNAMIC_RESOLVER_ENABLED` must activate together or `morning_handoff_finalizer.py:367` raises. Paired activation with a loud failure is exactly the right shape for coupled capabilities, and the profile/protection pair should have used it — or, better, should not have been a pair at all.

**Promotion staging is coherent** (`orchestrator\dynamic_release.py:218-237`): `PLAN_ONLY` → `EXPLICIT_COMMANDS` → `DYNAMIC_VIEWS` → `AUTO`, with `AUTO` last. Nothing in C2 need disturb it. What C2 must change is *what is inside* stage 2 — the protections should not be there at all.

---

## B4. Residual legacy paths

Provider calls, default substitutions and post-stage patches that executed on this run and that AR-003 §6.2 / §7 said must not be on the production path.

### B4.1 Provider calls that remained stage-local

| Stage | AR-003 §6.2 required target | What actually ran | Ledgered? |
|---|---|---|---|
| Discovery | *"Resolve canonical daily history first; fetch only missing tail"* | Direct Polygon: `Polygon API initialized (UNLIMITED)` at 00:20:12; `--universe polygon_liquid_universe.csv` | **No** |
| Package backfill | *"Preserve canonical full frames; no session collapse"* | Backfill timeseries, 12m 16s over 1,601 packages | **No** |
| Options | *"Canonical option/quote resolver owns acquisition"* | MarketData chain via the canonical resolver | **Yes** — 2,528 rows, 1,264 physical |
| Morning / Interpreter | canonical resolver only | not exercised (EOD-only run) | n/a |

**`api_request_ledger` contains 2,528 rows for this run and every one is `stage = OPTIONS`, `dataset_type = OPTION_CHAIN`** (B4-02). Options is the only stage commuted through the gateway. Discovery's Polygon calls and the backfill's session-bar calls are entirely invisible to the control plane.

This has a direct consequence for the design. The reconciliation C3/G-08 asks for — *physical = ledger `PROVIDER_FETCH` rows* — **is already true, and only true, of option chains** (1,264 = 1,264). Stated over the whole run it is unverifiable, because two of the three acquiring stages report nothing. G-08's gate must either be scoped to `OPTION_CHAIN` or preceded by ledger coverage for Discovery and backfill (**G-13**).

### B4.2 Default substitution on the production path

> `2026-09-04 00:43:44 — 39 tickers (1.2%) used stale cached bar data (Polygon fetch failed — prices may not be EOD)`

AR-003 §6.3 states the required states explicitly and forbids *"a stale value relabelled with the current run date"*. Thirty-nine tickers received exactly that: a substitution, a warning in a log nobody gates on, and no row-level state. Under §6.3 these rows should carry `APPROVED_FALLBACK` — *"explicitly approved substitute with reduced quality and no hidden authority"* — and be countable. Nothing downstream can currently tell a stale-bar ticker from a fresh one (B4-01, **G-13**).

Two further §6.3 prohibitions were breached in the same run:

- *"a fabricated zero"* — POC/VAH/VAL published as `0.0` on 1,551 rows (A1-03).
- *"a neutral score that looks observed"* — `auction_state = ALIGNED` and `ready_to_trade = True` on 1,068 unusable profiles, carrying +25 into Layer 2 (A1-05, A1-13).

Conversely, §6.3 already supplies the vocabulary G-05 needs: `UNRESOLVED_EXCEPTION` — *"required evidence could not be obtained or calculated"* — is the correct state for the 36 stood-down PUT rows, in place of a stringified `TypeError`.

### B4.3 Post-stage patches still active

AR-003 §5.1: *"Several compatibility layers copy or patch fields after the producer has completed. This creates silent schema drift and makes failure attribution difficult."* All still present:

| Patch | Time | Evidence |
|---|---|---|
| Actuarial enrichment patches 1,601 packages after Options | 04:02:42 | `exact=1145 fallback=400 no_match=6 no_vanguard=50` |
| Trigger layer patches 1,601 package JSONs after Core Intel | 04:34:14 | log |
| SuperBrain "passthrough" re-writes 1,454 rows | 04:34:18 | log |
| `FIX-ACTUARIAL-SEQ` patches 1,454 rows into superbrain *before* EIL | 04:37:00 | log |
| WS2 trigger spine commuted before EIL, re-verified after | 04:37:19 / 04:44:16 | `mismatches=0` |
| **GARCH patched retroactively into EIL output** | 04:43:53 → 04:44:16 | Phase 10b |

Note the `fallback=400` on actuarial enrichment: 400 of 1,601 packages (25%) matched on a fallback rather than an exact state, and `pipeline_integrity` reports `actuarial_fill_rate: 1.0`. A 100% fill rate that is 25% fallback is precisely the "neutral score that looks observed" §6.3 prohibits — the fill metric cannot distinguish them.

### B4.4 What the build removed, and what it did not

Comparing `20260904_004338` against `20260902_232526`:

| | 20260902_232526 | 20260904_004338 | Change |
|---|---|---|---|
| Vanguard `INSUFFICIENT_DATA` | 1,449 / 1,449 | 1,551 / 1,551 | **none** |
| Daily-only `ALIGNED` | 995 | 1,068 | **none** (scales with population) |
| POC as `0.0` | 1,449 | 1,551 | **none** |
| `layer1__profile__timeframe` | `intraday` | `intraday` | **none** |
| Option-chain ledger `request_fingerprint` | `LEGACY:<uuid>` ×2,172 | real SHA-256 ×1,264 | **improved** |
| Ledger rows per request | 1 | 2 (resolution + fetch) | **improved** |
| Polygon option-chain fallbacks | 0 | 0 | unchanged |
| Run size | 2.648 GB / 1,569 files | 2.846 GB / 1,675 files | +7.5%, all in `packages\` |

**The build removed exactly one thing on the production path: the legacy request-fingerprint scheme.** The 20260902 ledger carries `LEGACY:<uuid>` fingerprints — non-deterministic, so identity matching was impossible by construction. The 20260904 ledger carries real content-derived SHA-256 fingerprints and splits each request into a resolution row and a fetch row. That is a genuine, load-bearing improvement and it is the foundation G-08 builds on.

Everything else the build delivered is behind a flag.

---

## B5. Conclusion of Part B

The executed path was AR-003 §5.1 in full, including all three of its named ordering defects. None of the §5.2 target sequence was reached, and six of its sixteen elements are structurally unreachable while two flags are off.

The four reappearing P0s divide cleanly: **P0-02 and P0-07 are type (a)** — correct code on a path production cannot enter; **P0-04 and the lineage family are type (b)** — a contract tested without its writer. None is type (c). No implemented behaviour needs redesign.

The single sentence that carries this review: **the closure standard accepted test evidence where run evidence was required, and applied "do not enable yet" to protections as well as to capabilities.** Correcting the second half of that sentence is C2's first decision, and correcting the first half is C8's definition of done.
