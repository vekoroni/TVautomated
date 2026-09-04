# AVS-TST-SD-002-001 — Independent test prompt for the AVS-SD-002 Rev 1.1 dynamic-session build

**Issued:** 2026-09-03
**Tester:** Claude Code (independent, read-only on production code and run data)
**Implementer under test:** the AVS-SD-002 Rev 1.1 Phase 0–8 build closed on 2026-09-03
**Repository:** `C:\Users\ACKVerissimo\AVSHUNTER-Intelligence`
**Output root:** `audit\pipeline_map\AVS-TST-SD-002-001\` (create it; write nothing outside it except the scratch paths named in §3)

---

## 1. Mandate

You are the independent tester for the dynamic-session orchestration and Market Profile lifecycle build (AVS-SD-002 v1.0 + Rev 1.1, executed against AVS-AR-003). The implementer has published eight phase closure reports, claim sheets, a release evidence register and a release assessment. Every one of those is a **claim**, not a fact. Your job is to establish, per claim, whether the code and the evidence on disk actually support it, and to find what the claims omit.

**Scope: the fixes implemented today, tested offline.** Pipeline execution is out of scope. You are not running the Evening, Morning or dynamic paths, not producing run artefacts, and not assessing the live gates (G01, G18A–D, G19, P0-08). Those are a separate, later activity. Everything you do is static reading, isolated unit/contract tests, fixture-driven tests of the new modules, and diffing against the pre-change backup.

You are testing three things, in this priority order:

1. **Safety of the current production path.** Eight new feature flags are claimed to default to disabled and the legacy `--evening` / `--morning` paths are claimed to be unchanged apart from the unflagged Phase 2 authority corrections. If that is false, nothing else matters.
2. **Each fix in the fix register (§5A) actually fixes the defect it claims to.** Gates G02–G17 and G20 are marked PASS and P0-01 to P0-07 are marked CLOSED OFFLINE. Verify each against source and executed evidence, not against the closure prose.
3. **Legitimacy of the test reconciliation.** 25 previously failing tests were edited so the full suite passes (`dynamic_phase8_open_regressions_20260903.xml` → `dynamic_phase8_reconciled_regressions_20260903.xml`). Each edit either corrected an obsolete assertion or weakened a protection. Decide which, per test.

You are **not** re-reviewing the design. AVS-SD-002, Rev 1.1 and AVS-AR-003 are the accepted specification. Where the code disagrees with them, the code is wrong unless the closure report explicitly records a deviation and the reason.

---

## 2. Hard constraints — read before doing anything

- **Never execute the pipeline.** No `intelligent_orchestrator.py` with any switch (including `--plan-only`), no `morning_gate.py`, no `run_*` stage scripts, no Intelligence Lab server, no Interpreter commands, no scripts that call a market-data provider. Pipeline execution is out of scope for this prompt without exception.
- **Existing run artefacts are read-only reference data.** You may read `20260902_232526` (latest EOD) and `20260901_082437` (latest accepted Morning) to build fixtures or confirm a defect's pre-fix shape. Nothing in them will show today's fixes firing, because no run has been produced since the fixes — do not treat their absence as a finding, and do not mark anything `UNVALIDATED — requires run` as if that were in scope. Where a fix can only be proven by a future run, say so once in the findings and move on.
- **Production code and run data are read-only.** Do not edit any `.py`, `.json`, `.html`, `.sqlite`, `.csv` outside your output root. Do not modify, delete or re-run anything under `backups\`.
- **Defects are filed, never fixed.** No patches, no "quick corrections", no suggested diffs applied.
- **Never set a feature flag.** Do not export or set any `AVSHUNTER_*_ENABLED` variable in a shell that could touch production paths. Flag-on behaviour is exercised only through the unit-test harness with monkeypatched environment, in isolated pytest processes.
- **Provider entitlement is untested by design** (AVS-SD-002 §15.3). Do not call MarketData, Polygon or FRED. Any test that needs a live response is out of scope; say so.
- **Three-direction discipline is mandatory.** Every direction-bearing check is exercised for CALL, PUT and OTHER (STRANGLE / UNRESOLVED / null). A CALL-only pass is not a pass.
- **Interpreter:** `C:\Python314\python.exe` is the runtime the implementer used (Phase 0 closure). Use the same one. Record `sys.version`, `sys.executable` and `pandas.__version__` in `environment.json`. Run every test file in its **own** pytest process — the Phase 2 closure records that single-process collection is invalid because tests mutate `sys.path` and `vanguard/scripts` shadows the repository `scripts` package. Do not attempt to fix that collision.

---

## 3. Inputs

Read all of these before writing any test. Quote them by section ID in every finding.

**Specification (accepted, normative)**
- `audit\pipeline_map\AVS-SD-002_DATA_INTELLIGENCE_AND_MARKET_PROFILE_LIFECYCLE_20260903.md` — v1.0, §§5–14, §16, §20
- `audit\pipeline_map\AVS-SD-002_REV1_1_DYNAMIC_SESSION_ORCHESTRATION_20260903.md` — Rev 1.1, §§6–12, §§15–19, §22
- `audit\pipeline_map\AVS-AR-003_AS_IS_PIPELINE_SHIPPABILITY_REVIEW_20260903.md` — §§7–12
- `audit\pipeline_map\AVS-AR-003_GAP_REGISTER_20260903.csv` — P0-01…P2-03
- `audit\pipeline_map\AVS-SD-002_REV1_1_VALIDATION_MATRIX_20260903.csv` — DSO-001…DSO-024

**Implementer claims (under test)**
- `AVS-SD-002_PHASE0_CLOSURE_20260903.md` + `PHASE0_CLAIM.json`
- `AVS-SD-002_PHASE1_CLOSURE_20260903.md` + `PHASE1_PLAN_PROBE.json`
- `AVS-SD-002_PHASE2_CLOSURE_20260903.md` + `PHASE2_CLAIM.json`
- `AVS-SD-002_PHASE3_CLOSURE_20260903.md` + `PHASE3_CLAIM.json`
- `AVS-SD-002_PHASE4_CLOSURE_20260903.md` + `PHASE4_CLAIM.json`
- `AVS-SD-002_PHASE5_CLOSURE_20260903.md` + `PHASE5_CLAIM.json`
- `AVS-SD-002_PHASE6_CLOSURE_20260903.md` + `PHASE6_CLAIM.json`
- `AVS-SD-002_PHASE7_CLOSURE_20260903.md` + `PHASE7_CLAIM.json`
- `AVS-SD-002_PHASE8_CLOSURE_20260903.md`, `PHASE8_EVIDENCE.json`, `PHASE8_ASSESSMENT.json`
- `AVS-AR-003_P0_RECERTIFICATION_20260903.md`

**Evidence artefacts (hash-bound in PHASE8_EVIDENCE.json)**
- `dynamic_phase8_results_20260903.xml` (168 testcases, claimed sha256 `1bf91e6f…4251`)
- `dynamic_phase8_full_regression_20260903.xml` (900 testcases, claimed sha256 `b48960ed…9328`)
- `dynamic_phase8_qa_rca_regression_20260903.xml` (44 testcases, claimed sha256 `d9559762…72da`)
- `dynamic_phase8_open_regressions_20260903.xml` (76 run, 25 failed — the pre-reconciliation state)
- `dynamic_phase8_reconciled_regressions_20260903.xml` (76 run, 0 failed — post-reconciliation)
- `dynamic_phase8_recursive_diagnostic_20260903.xml` (1,113 pass / 33 fail — MSI characterisation pack, excluded from acceptance by the implementer)
- `design_validation_results.xml` (61 pass) and `as_is_validation_results_20260903.xml` (239 pass / 2 env fail) — the pre-build baselines
- `backups\avs_sd_002_rev1_1_phase0_prechange_20260903_133546\` — contains `phase0_release_manifest.json`, `restore_verification.json`, `release_file_manifest.json`, `environment.json` and the **pre-change source and test tree** — this is your diff baseline
- `backups\avs_sd_002_rev1_1_phase{2,3,4,5,6,7}_prechange_20260903_*` — per-phase backups

**Scratch paths you may write to:** your output root, and a temp directory under `audit\pipeline_map\AVS-TST-SD-002-001\tmp\` for restore drills and fixture databases. Nothing else.

---

## 4. Closure standard

Every item in your register gets exactly one status:

| Status | Meaning |
|---|---|
| `VERIFIED` | Source evidence **and** an executed test or artefact on disk both support the claim. |
| `SOURCE_ONLY` | Code reads correctly but no executed evidence exists or the evidence does not exercise the claim. |
| `CONTRADICTED` | Source or evidence disagrees with the claim. File a defect. |
| `VERIFIED_OFFLINE` | As `VERIFIED`, but the fix's run-level effect is deferred to the live cycle (note it in T6). |
| `BLOCKED` | You could not check it: state exactly what you needed. |

A closure report saying "PASS" is never itself evidence. A test count in a claim sheet is never itself evidence — the XML is. A test passing is only evidence for a claim if you have read the test and confirmed it asserts the claimed property rather than a weaker proxy.

---

## 5A. Fix register — what was implemented today and must be tested

This is the list of defects the documentation says were fixed today, with the phase that fixed each, where the fix lives, and the test that must prove it. Each row must appear in `T1_claim_register.csv` with a status. If you find a fix in the closures that is not on this list, add it. If you find a row here that no closure actually claims, mark it `CONTRADICTED — not implemented` rather than assuming it was.

| Fix | Defect it addresses (source) | Implemented in | Where to look | What proves it |
|---|---|---|---|---|
| F01 Reproducible release baseline + verified restore | P0-01; AR-003 §2, Wave 0 | Phase 0 | `scripts/release_baseline.py`, `backups/…phase0_prechange…/` manifests | Independent restore drill into tmp; manifest rebuilds the tested tree |
| F02 Frozen contracts and eight independently reversible flags, all default off | AVS-SD-002 §16.2; Rev 1.1 §22 | Phase 0 | `contracts/dynamic_session_contract.py`, `contracts/dynamic_session_authority_v1.json` | Flag inventory; every reader treats unset as disabled; one capital owner = `execution_gate` |
| F03 Deterministic hashed `RunPlan`, plan-only resolution, append-only plan store | Rev 1.1 §8, DSO-004/005 | Phase 1 | planner module under `orchestrator/` (locate) | Reproduce `PHASE1_PLAN_PROBE.json` hash exactly; material-input change → new hash; ticker order → same hash |
| F04 Invocation identity separate from run/thesis; idempotent retry; linked changed-scope retry | P0-06; Rev 1.1 §7, §15.3; DSO-012 | Phase 1 | identity module; `canonical_data` `DatasetRequest`; control-plane ledger v2 | Same inputs → same `invocation_id`; changed cutoff → new id with `supersedes_/retry_of_`; v1 ledger rows survive migration |
| F05 Session-aware planning on the shared XNYS clock, provider-finalisation distinction | Rev 1.1 §6, §8.3; DSO-001/011 | Phase 1, 6 | planner; `canonical_data/session_clock.py` | CLOSED/PREMARKET/REGULAR/AFTER_HOURS/weekend decision table; after-hours stays VALIDATE until finalised=true |
| F06 Discovery macro-invariant (tiers, priors, sector lift) | P0-03; AR-003 §7.2 | Phase 2 (unflagged) | `avshunter_discovery_ULTIMATE.py` | Extreme vs absent macro → bitwise-equal tier/prior/lift outputs, CALL/PUT/OTHER |
| F07 Vanguard L2 macro-invariant; core-regime compatibility payload | P0-03; AR-003 §7.5 | Phase 2 (unflagged) | `vanguard/layer2_statistical/edge_detector.py`, `state_calculator.py` | Same as F06 at L2 score level |
| F08 Horizon routes with macro absent; macro cannot block/resize/choose | P0-03; AR-003 §7.8 | Phase 2 (unflagged) | `macro_horizon_router.py` | No bias object → valid route, never BLOCK; 38 embedded checks re-run |
| F09 Legacy R:R/EV removed from Options verdict and EOD tier authority | P0-04; AR-003 §7.7, §8 | Phase 2 (unflagged) | `scripts/avshunter_options_intelligence.py` `derive_verdict`; `eod_candidate_engine.py` | Negative `rr_options` on viable contract → no demotion anywhere |
| F10 One long-option quote policy: single spread denominator, thresholds, quote age | P1-05, P1-06; AR-003 §7.12 | Phase 2 (unflagged) | new policy module (locate); `execution_gate.py`; Morning; Lab | Grep every spread expression; one denominator; no literal `quote_age_seconds=0.0` |
| F11 Execution viability (hard, current quote) separated from scenario monetisability (advisory) | P0-04; AR-003 §7.10 | Phase 2 (unflagged) | `contracts/selected_contract_economics.py`, `execution_gate.py`, `morning_gate.py` | `NOT_MONETISABLE` + viable quote → not blocked on monetisability; viability fail → blocked; `ADVISORY_SCENARIO_ONLY` label present |
| F12 Morning recomputes viability from current bid/ask, never reuses EOD label | AR-003 §7.11 | Phase 2 (unflagged) | `morning_gate.py` | EOD `MONETISABLE` row with dead current quote → not viable |
| F13 Frozen-thesis guard at Morning handoff (annotation allowed, mutation rejected) | P0-07; Rev 1.1 §5.2 | Phase 2 | handoff boundary (locate) | Mutating direction/target/invalidation → rejected; adding annotation → accepted |
| F14 Lab fails closed without governed book | P0-05; AR-003 §7.13 | Phase 2 (unflagged) | `contracts/lab_control.py`, `intelligence-lab/` | No governed book → zero actionable rows; `LEGACY_IN_MEMORY_ASSEMBLY` non-actionable |
| F15 Interpreter production path manifest-only; retired acquisition/alt-selection unreachable | P1-08; AR-003 §7.14 | Phase 2, 7 | `pipeline_interpreter/` | Import graph has no provider client; retired commands not dispatchable |
| F16 Frame-preserving MarketData candle adapter (no session collapse) | P1-02; AVS-SD-002 §5.1 | Phase 3 | new adapter under `canonical_data/` or `market_data/` | 78 candles in → 78 out; mismatched arrays → fail closed |
| F17 Interval-aware canonical intraday resolver (1/5/15/30) with calendar-derived expectations | AVS-SD-002 §5.2, §8.1; DSO-013 | Phase 3 | `canonical_data/intraday_bars.py` | Distinct scope/schema per interval; early-close count from calendar; duplicates/gaps/out-of-scope diagnosed |
| F18 Exact-cache zero calls; partial fetch missing ranges only; cutoff defers future bars | AVS-SD-002 §14.1.4–5; Rev 1.1 §11.1 | Phase 3 | resolver | Mock callback counts: 0 on hit; only coalesced missing ranges on partial; 0 for post-cutoff |
| F19 Inactive/non-worklisted ticker makes zero provider calls; per-ticker isolation | AVS-SD-002 §14.1.6–7 | Phase 3, 4, 5 | resolver batch; completed-profile stage; validation batch | Callback never invoked for dropped ticker; one failure doesn't stop others; systemic threshold reported |
| F20 Cadence classification corrected (15-min → `FIFTEEN_MINUTE_TPO`) | AVS-SD-002 §5.7 | Phase 4 | `market_structure/profile.py` | 5/15/30-min frames → correct cadence enum |
| F21 `MarketProfileEvidence` typed packet; nulls not zeros; no direction/action/capital fields | AVS-SD-002 §5.5, §5.6, §8.2 | Phase 4 | contract module; `vanguard/schemas/input_schema.py` | Short/daily frame → `None` levels; packet schema has no authority fields |
| F22 Vanguard fail-open removed: unusable profile → `NOT_EVALUATED`, `ready_to_trade=False`, uplift 0 | **P0-02** (the headline defect: 1,449 zero-level rows, 995 ALIGNED) | Phase 4 (flag `AVSHUNTER_COMPLETED_PROFILE_ENABLED`) | `vanguard/layer1_auction/auction_synthesizer.py`, `orchestrator_adapter.py` | One daily bar → never ALIGNED; usable packet → consumed without recalculation and without granting readiness; **also state what the flag-off (current production) path does** |
| F23 Completed-profile stage after Discovery, before Vanguard; persisted; cache-reused | AVS-SD-002 §5.4, §13 Phase 3 | Phase 4 | stage module; `intelligent_orchestrator.py` insertion point | Second execution → 0 physical requests; stage order fixed in `build_thesis` |
| F24 `build_thesis(plan)` fixed order, EOD_PREPARED ceiling, immutable restart receipt, population identity | Rev 1.1 §9, §8.4; AVS-SD-002 §12 | Phase 4 | `orchestrator/dynamic_thesis.py` | Non-BUILD plan rejected; `input ≠ processed+excluded+deferred+exceptions` rejected |
| F25 `validate_thesis(plan, thesis)`: underlying-first, survivor-only option refresh, stop-on-invalidation | Rev 1.1 §10.2; AR-003 §7.11; DSO-009 | Phase 5 (flag `AVSHUNTER_DYNAMIC_VALIDATION_ENABLED`) | validation service module | Invalidated ticker → zero later option/bar callbacks |
| F26 Symmetric CALL/PUT geometry (invalidation, target, trigger, max-entry) | Rev 1.1 §10.3; P0-07 | Phase 5 | validation service | Mirror pairs give identical transitions; UNRESOLVED → no transition |
| F27 Profile lifecycle states: premarket `PENDING_MARKET_OPEN`, RTH `DEVELOPING_SESSION`, after-hours `PARTIAL_SESSION`; EOD profile immutable | AVS-SD-002 §6.2–6.3, §14.2.6–8 | Phase 5 | validation service; profile lifecycle module | Premarket → 0 bar-resolver calls; EOD packet hash unchanged through validation |
| F28 Morning Market Structure provider swapped: Polygon 1-min callback → governed MarketData 5-min | AVS-SD-002 §5.3 | Phase 5 | `morning_gate.py` structure capture | No Polygon minute callback reachable from Morning structure path |
| F29 Morning handoff defect: `ms_*` evidence now copied into Lab result rows, not only `live_map` | discovered during Phase 5 | Phase 5 | Morning handoff / finaliser | Fixture Morning result row carries `ms_*` fields |
| F30 Validation event immutable identity, atomic file persistence | Rev 1.1 §7, §15.3 | Phase 5, 7 | validation persistence | Re-persist same event → same id, same bytes; changed content → new id |
| F31 Dynamic dispatcher: governed `latest.json` pointer (never newest-folder), reuse current thesis, compatibility mapping of `--evening`/`--morning`, plan persisted before callback, finalisation mints new run id | Rev 1.1 §8.3, §12; DSO-004 | Phase 6 (flags `AVSHUNTER_DYNAMIC_PLAN_ENABLED`, `AVSHUNTER_DYNAMIC_AUTO_ENABLED`) | `orchestrator/dynamic_dispatcher.py`; CLI in `intelligent_orchestrator.py` | Unit tests only — no CLI invocation; trace CLI branch statically |
| F32 Append-only Decision and Outcome Ledger with UPDATE/DELETE-rejecting triggers; accepted + rejected candidates; idempotent | P1-09; AVS-SD-002 §10 | Phase 7 (flag `AVSHUNTER_DECISION_LEDGER_ENABLED`) | ledger module | Raw sqlite UPDATE/DELETE fail; double append → one row; rejected rows captured |
| F33 v3 Lab/Interpreter materializer: `frozen_thesis` + `current_validation` axes, `validation_event_id`-bound bundle, fail-closed matching | Rev 1.1 §12, §13; DSO-018/019 | Phase 7 (flags `AVSHUNTER_LAB_DYNAMIC_VIEW_ENABLED`, `AVSHUNTER_INTERPRETER_DYNAMIC_RESOLVER_ENABLED`) | `contracts/interpreter_handoff_materializer.py`, `pipeline_interpreter/evidence_resolver.py`, `intelligence-lab/static/index.html` | Mismatched event/ticker/direction/contract → fail closed; bundle id changes with event |
| F34 Lab cache signature includes v3 handoff/bundle files | Rev 1.1 §12 | Phase 7 | Lab cache signature | New bundle file → signature changes |
| F35 Release assessor: hash-bound evidence, `NOT_READY`/`READY_FOR_LIVE_CYCLE`/`READY_FOR_CONTROLLED_PROMOTION`, refuses promotion settings early | Rev 1.1 §19, §22 | Phase 8 | `orchestrator/dynamic_release.py`, `scripts/validate_dynamic_session_release.py` | Changed/missing artefact → fail closed; any G18/G19 NOT_RUN → no promotion settings (unit tests only; do not run the script against `audit\pipeline_map\`) |
| F36 `release_baseline.py --verify-only` false `KeyError` fixed | Phase 8 closure | Phase 8 | `scripts/release_baseline.py` | Verify-only against a tmp restore returns success cleanly |
| F37 25 test reconciliations | Phase 8 closure "Reconciled regression groups" | Phase 8 | the 25 test files | T2 audit |

## 5. Test tracks

Execute in order. T0 and T1 are prerequisites; do not start T2+ until T0 has established that the evidence files are what the claim sheets say they are.

### T0 — Evidence integrity and production-safety preflight

1. **Hashes.** Compute sha256 of every artefact listed in `PHASE8_EVIDENCE.json` and `PHASE8_ASSESSMENT.json`. Compare to the recorded values. Any mismatch is a P0 finding — the release assessor is claimed to fail closed on changed artefacts (Phase 8 `test_missing_or_changed_release_artifact_fails_closed`), so a mismatch means either the artefact was rewritten after assessment or the assessor does not do what the test says.
2. **XML-to-claim reconciliation.** Parse each JUnit XML and reconcile testcase counts, failure counts, skipped counts and subtest counts against every number in every closure report and claim sheet. Known points to resolve:
   - Phase 8 closure claims "165 passed, 3 subtests passed, 0 failed" for the integrated pack; `dynamic_phase8_results_20260903.xml` carries 165 `<testcase>` elements and a suite `tests="168"` attribute. Confirm 168 = 165 + 3 subtests and that no subtest failed.
   - Phase 8 closure claims "900 passed, 1 skipped, 43 subtests passed, 0 failed — 877 top-level plus 23 active QA/RCA". The XMLs do not obviously support that arithmetic: `dynamic_phase8_full_regression` has 878 `<testcase>` elements and `tests="900"` (878 + 22 subtests); `qa_rca` has 23 `<testcase>` elements and `tests="44"` (23 + 21 subtests). So the "900" appears to be the full-regression file alone, the "877 + 23" appears to be a different decomposition, and 22 + 21 = 43 subtests spans both files. Reconcile exactly which tests are in which file, whether any QA/RCA test is also inside the 878, and restate the true totals. This is a reporting-accuracy finding, not necessarily a code defect — but the G17 gate detail repeats the arithmetic, so it must be corrected in the evidence register.
   - Phase 4 claims "190 collected; command exited 0" with no pass count. Locate the XML or log for that run. If none exists, the Phase 4 combined pack is `SOURCE_ONLY` at best.
   - Phase 5 claims "58 passed / 0 failed" for the compatibility pack **and** in the same report records two red tests in `test_morning_gate_contract_repair.py`. Establish whether those two were inside or outside the 58.
   - Phase 6 records "284 passed, 30 failed" for the wider pack; Phase 8 later records 25 failures reconciled. Account for the other 5.
3. **Git state.** Record `git rev-parse HEAD`, `git status --porcelain | wc -l`, and whether HEAD is still `5d886f07c1d290f25600e2e7e62ae77aad85476a` (the source_head in every claim). P0-01 is marked CLOSED OFFLINE on the strength of a release manifest, not a commit. State plainly whether a person could rebuild the tested tree from `phase0_release_manifest.json` + `release_file_manifest.json` alone, and whether any file changed after Phase 0 is absent from a later per-phase backup (the Phase 2 closure admits `vanguard/layer2_statistical/state_calculator.py` and `contracts/lab_control.py` were edited without a Phase 2 backup).
4. **Flag inventory.** From `contracts/dynamic_session_contract.py` and `contracts/dynamic_session_authority_v1.json`, list every dynamic feature flag by exact environment-variable name, its default, and the module(s) that read it. Phase 0 says eight; the closures name seven (`AVSHUNTER_COMPLETED_PROFILE_ENABLED`, `AVSHUNTER_DYNAMIC_VALIDATION_ENABLED`, `AVSHUNTER_DYNAMIC_PLAN_ENABLED`, `AVSHUNTER_DYNAMIC_AUTO_ENABLED`, `AVSHUNTER_LAB_DYNAMIC_VIEW_ENABLED`, `AVSHUNTER_INTERPRETER_DYNAMIC_RESOLVER_ENABLED`, `AVSHUNTER_DECISION_LEDGER_ENABLED`). Identify the eighth. For each flag, grep the entire live tree for reads of it and confirm every read treats absent/unset as disabled. A flag read anywhere with a truthy default is a P0.
5. **Legacy path diff.** Using the Phase 0 backup as baseline, produce a unified diff of every production module the closures list as changed (Phase 4 file list, Phase 5 `morning_gate.py`, Phase 6 `intelligent_orchestrator.py` CLI, Phase 7 `intelligence-lab/`, `contracts/`, `pipeline_interpreter/`). For each hunk, classify: (a) reachable only behind a disabled flag, (b) reachable on the legacy `--evening`/`--morning` path, (c) unconditional. Every (b) and (c) hunk must be individually justified from a closure report; list the ones that are not. **Pay particular attention to the Phase 2 authority changes** — Discovery macro invariance, Options verdict R:R removal, EOD tier R:R removal, single spread denominator, Morning viability recompute, Lab fail-closed — these are explicitly *not* behind flags and therefore already change production behaviour. The claim sheet says `production_behavior_changed: false` for Phase 0 only; check whether any later closure makes the same claim for a phase that changed unflagged code.

Deliver `T0_evidence_integrity.md` and `T0_flag_inventory.csv` before proceeding.

### T1 — Phase-by-phase claim verification

For each phase, take every bullet under "Implemented" in the closure and every key in the claim JSON and give it a status. Run the phase's own test file in an isolated process and save the XML under your output root. Then **read each test** and record whether it asserts the claimed property or a proxy. Specific probes:

**Phase 0.** Run `tests.test_dynamic_session_phase0`. Independently re-execute the restore drill into your tmp directory (do not touch the backup): restore the three SQLite files, compute hashes, run `PRAGMA integrity_check`, count tables and rows, compare to `restore_verification.json`. Confirm the 15.8 GB Phantom store is genuinely excluded and that no later phase changed its writer (grep for the Phantom writer module in each per-phase backup diff).

**Phase 1.** Run `tests.test_dynamic_session_phase1`. Reproduce `PHASE1_PLAN_PROBE.json` by calling the planner in-process with the same inputs (`as_of_utc=2026-09-03T13:00:00Z`, `AUTO`, run `20260902_232526`); the `plan_hash` must match `52ce811d…b214c` exactly. Then vary one input at a time (cutoff +1s, worklist order, ticker added) and confirm the hash changes for material inputs and does **not** change for ticker order. Confirm `DatasetRequest` and the control-plane ledger v2 carry `invocation_id`, `evidence_cutoff_utc`, `exchange_calendar`, `evidence_state` (Rev 1.1 §7, §11). Confirm no provider module is importable from the planner's import graph.

**Phase 2.** Run `tests.test_dynamic_session_phase2`. This is the highest-risk phase because it is unflagged. For each of the following, find the exact line(s) and confirm the removal is complete, not partial:
- Discovery: no macro payload field reaches tier thresholds, state priors or sector lift (AR-003 §7.2, P0-03). Grep `avshunter_discovery_ULTIMATE.py` for every macro-derived name and show where each is consumed.
- Vanguard L2: `edge_detector.py` and `state_calculator.py` — regime EV/win-rate floors and score boosts are macro-invariant (AR-003 §7.5).
- Horizon Router: routes with macro entirely absent; no `BLOCK` when bias object missing (AR-003 §7.8).
- Options: `derive_verdict` no longer demotes EXECUTE→ARMED on `rr_options` (AR-003 §7.7).
- Spread: exactly one denominator across `execution_gate.py`, Options, Morning, Lab (P1-05). Grep every `(ask` and `/ ask`, `/ mid`, `/mid` expression in the live tree and list them.
- Morning: `quote_age_seconds` is never a literal `0.0` (P1-06). Grep for it.
- Lab: with no governed book, no row is actionable (P0-05). Read `contracts/lab_control.py` and the UI path; confirm `LEGACY_IN_MEMORY_ASSEMBLY` cannot reach an actionable state.
- Interpreter: `live_market_reader.py` and `alternative_contract_selector.py` unreachable from production commands (P1-08).
Run each of these for CALL, PUT and OTHER inputs.

**Phase 3.** Run `tests.test_dynamic_session_phase3`. Add your own fixtures under your output root for: a 78-bar full session, a 26-bar early-close session (calendar-derived, not hard-coded), a session with one duplicate timestamp, one out-of-order, one 15-minute gap, and one with a bar timestamped after `evidence_cutoff_utc`. Confirm `completeness_status`, coverage ratio, max gap and deferral behave per AVS-SD-002 §8.1 and §14.1. Confirm exact-cache reuse causes zero provider-callback invocations (count with a mock) and partial coverage requests only the missing coalesced ranges. Confirm a ticker absent from the authorised worklist never reaches the callback.

**Phase 4.** Run `tests.test_dynamic_session_phase4`. Then:
- Feed one daily bar to the governed auction path and confirm the result is `NOT_EVALUATED`, `ready_to_trade=False`, uplift 0, POC/VAH/VAL `None` — **not** `0.0` (AVS-SD-002 §5.6, §14.3). Repeat with 12 bars (below the 13-bar floor). Repeat for CALL, PUT and UNRESOLVED direction inputs.
- Feed a valid 15-minute frame and confirm cadence is `FIFTEEN_MINUTE_TPO`, not `ONE_MINUTE_ESTIMATED` (§5.7).
- Confirm `MarketProfileEvidence` carries no direction, action or capital field (§8.2).
- Confirm the legacy `vanguard/layer1_auction/market_profile.py` is reachable **only** when `AVSHUNTER_COMPLETED_PROFILE_ENABLED` is off, and confirm which path the current production run would take.
- Confirm `build_thesis(plan)` refuses a non-BUILD plan and refuses population inflation (input ≠ processed + excluded + deferred + exceptions).

**Phase 5.** Run `tests.test_dynamic_session_phase5`. Then:
- Geometry symmetry: construct a CALL and its mirror PUT with identical distances to target/invalidation/max-entry and confirm identical transition outcomes (`THESIS_CONFIRMED`, `ENTRY_RUNWAY_EXHAUSTED`, `THESIS_INVALIDATED`). The shipped test parametrises three PUT cases and one CALL case — add the missing CALL mirrors.
- Confirm an invalidated underlying stops **all** later acquisition for that ticker (no option quote, no bar request) via callback counting.
- Confirm PREMARKET publishes `PENDING_MARKET_OPEN` and makes zero bar-resolver calls; REGULAR produces `DEVELOPING_SESSION` only when closed RTH bars exist; AFTER_HOURS without provider finalisation stays `PARTIAL_SESSION`.
- Confirm the EOD completed profile object is byte-identical before and after validation (hash it).
- Verify the fix for `ms_*` evidence being written only to `live_map` (F29): read the Morning handoff code and confirm the result rows consumed by the Lab now carry `ms_*` fields, and build a fixture Morning result through that code path to show them populated. You may read run `20260901_082437` to confirm the pre-fix shape (rows without `ms_*`) for the fixture; do not expect it to show the fix.
- The two red tests in `test_morning_gate_contract_repair.py` (`test_blank_primary_contract_promotes_live_repair_alternative`, `test_composite_repair_is_hydrated_but_not_promoted_to_production`) were later edited in Phase 8. Handle them under T2.

**Phase 6.** Run `tests.test_dynamic_session_phase6`. Confirm:
- `--evening` maps to exactly `BUILD_THESIS` and `--morning` to exactly `VALIDATE`, with no behavioural change while `AVSHUNTER_DYNAMIC_PLAN_ENABLED` is off (trace the CLI branch in `intelligent_orchestrator.py`).
- Accepted-run resolution uses `latest.json` and accepted metadata, never directory mtime ordering. Grep for `sorted(` / `os.listdir` / `glob` in the resolver.
- Finalisation mints a new `pipeline_run_id` and cannot write into the accepted thesis run directory.
- Plan persistence precedes callback execution and is idempotent on identical plan hash.
- `--data-mode LATEST` remains research-only and cannot produce an accepted pointer.

**Phase 7.** Run `tests.test_dynamic_session_phase7`. Then, against a fixture ledger in your tmp directory:
- Attempt `UPDATE` and `DELETE` on every ledger table via raw sqlite3 and confirm the triggers reject them.
- Append the same decision event twice and confirm one row.
- Confirm rejected and deferred candidates are captured, not only accepted ones (AVS-SD-002 §10.2).
- Confirm the v3 materializer fails closed when `validation_event_id` in the bundle differs from the ledger's latest for that thesis, and when ticker/direction/contract mismatch.
- Confirm the Interpreter resolver's import graph contains no provider client, `requests`, `httpx`, `urllib` request path, or the retired `live_market_reader` (AVS-SD-002 §14.4.6).
- Confirm the Lab cache signature includes the v3 handoff/bundle files.

**Phase 8.** Run `tests.test_dynamic_session_phase8`. Exercise `orchestrator/dynamic_release.py` in-process against a copy of `PHASE8_EVIDENCE.json` in your tmp directory: confirm it reports `NOT_READY` with exactly the six gates listed in `PHASE8_ASSESSMENT.json` as failed; tamper one byte of a copied artefact and confirm it fails closed; mark all gates PASS in the copy and confirm it still refuses promotion settings until the live gates carry artefacts. Do not run `scripts/validate_dynamic_session_release.py` against the real `audit\pipeline_map\`. Confirm the weekend case creates no phantom session and the replay case has zero provider requirements.

Deliver `T1_claim_register.csv` (columns: phase, claim, design_ref, status, evidence_path, test_name, notes).

### T2 — Test-edit audit (the 25 reconciled tests)

For each of the 25 tests that failed in `dynamic_phase8_open_regressions_20260903.xml` and pass in `dynamic_phase8_reconciled_regressions_20260903.xml`, produce a diff of the test file against its copy in the Phase 0 backup and classify the change as one of:

- `OBSOLETE_ASSERTION_CORRECTED` — the old assertion encoded a policy AVS-AR-003 explicitly retired (e.g. R:R capital authority, intrinsic-only monetisability blocking, legacy strangle presentation), and the new assertion tests the approved contract at equal or greater strength.
- `FIXTURE_CORRECTED` — only fixture data changed (e.g. the Sunday 30 Aug 2026 session), and the assertion is unchanged.
- `PROTECTION_WEAKENED` — the assertion was loosened, removed, skipped, or replaced with a proxy that would still pass if the original defect returned.
- `UNRELATED_CHANGE` — the diff touches something other than the failing assertion.

Groups to work through, as listed by the implementer: 4 monetisability tests + 1 OLM test; 3 Lab cache/journal fixtures; 9 Lab strangle fixtures; 2 Morning contract-repair tests; 1 canonical resolver Sunday fixture; 5 options-research hard-block tests. Any `PROTECTION_WEAKENED` is a P1 defect minimum. For the monetisability and options-research groups specifically, write one adversarial test each under your output root that reintroduces the retired behaviour (e.g. a `NOT_MONETISABLE` row reaching `BUY_NOW`; a 20%-of-mid spread reaching GO) and confirm the **current** production code still blocks it through the approved authority (execution viability / Execution Gate) rather than through the retired one.

Deliver `T2_test_edit_audit.csv` and `T2_adversarial_tests\`.

### T3 — Authority invariant adversarial pack

Write new tests (under your output root only, importing production modules read-only) that attempt to violate each row of the AVS-SD-002 §7 authority matrix and AR-003 §8 alignment table. Minimum set:

1. Market Profile packet with injected `direction`, `action` or `capital` keys → must be rejected or ignored, never propagated.
2. Macro snapshot with extreme regime values → Discovery tier, Vanguard L2 score, Horizon route and Execution Gate action unchanged versus macro absent (bitwise-equal outputs).
3. Developing profile at RTH with `CONTRADICTING` relationship → direction, action and capital unchanged.
4. Current price gapped through invalidation for a CALL → `THESIS_INVALIDATED`; mirror for PUT; UNRESOLVED direction → no transition and no acquisition.
5. Lab bundle hand-edited to upgrade `final_action` → Lab/Interpreter materializer fails closed.
6. Validation event whose `thesis_id` matches but `contract_episode_id` differs → fail closed.
7. Legacy `rr_options` negative on an otherwise viable contract → no demotion anywhere on the path.
8. Scenario monetisability `NOT_MONETISABLE` with viable current quote → Execution Gate does not block on it; viability failure with `MONETISABLE` → Execution Gate does block.
9. Same plan hash submitted twice → one persisted plan, one execution; changed cutoff → new `invocation_id` linked via `supersedes_invocation_id` or `retry_of_invocation_id`.
10. Interpreter asked to "switch to the PUT" or "pick a different strike" → structured refusal or refresh request, no substitution.

Every test runs CALL / PUT / OTHER. Deliver `T3_authority_pack\` with XML results and `T3_authority_matrix.csv` (matrix row → test → status).

### T4 — Design conformance traceability

Build a traceability table from every "must / cannot / never / only" sentence in AVS-SD-002 §§5–12, Rev 1.1 §§5–15 and AR-003 §12 to the file:line that implements it and the test that proves it. Rows with no implementing line are `CONTRADICTED` (design requirement unimplemented but phase closed) unless the closure explicitly defers them to a later phase — in which case cite the deferral. Known items to trace carefully:

- §8.4 resolution origin enum (`CACHE_HIT`, `COMPUTED_FROM_CANONICAL`, `PROVIDER_FETCH`, `APPROVED_FALLBACK`, `UNRESOLVED_EXCEPTION`) actually stamped on resolved fields, not just defined.
- §12 stage identity `input_count = processed + excluded + deferred + exception_count` enforced at every new stage boundary (completed profile, validation batch, ledger capture).
- §9.4 robust-z shock states and §9.5 five-component uncertainty vector — are they implemented, or deferred? The closures do not mention them.
- Rev 1.1 §10.3 current-price semantics: gap-toward-target making the option unattractive without reversing direction — is there a state for it?
- Rev 1.1 §12 Lab banners — which of the seven listed banner strings exist in `intelligence-lab/static/index.html`?
- AR-003 §7.10 `EXPIRY_INTRINSIC_FLOOR` label retained for the old monetisability.
- AR-003 §7.11 Morning publishes actual quote source timestamp, acquired-at and age.
- P0-07: recertified CLOSED OFFLINE on the strength of a contract that defers missing geometry. The latest run still reports 127 missing invalidations. State explicitly that closure is contract-level, and what a fresh run must show for it to be data-level.

Deliver `T4_traceability.csv`.

### T5 — Regression harness validity

The implementer excluded the 1,113/33 recursive MSI characterisation pack from acceptance. Read the 33 failing tests and classify each as (a) intentionally asserts absent/obsolete behaviour, (b) Sunday/invalid fixture, or (c) a genuine failure the implementer mislabelled. Any (c) is a defect. Separately, confirm that no test file was renamed, moved, deleted or given a skip marker between the Phase 0 backup and the current tree without being mentioned in a closure. List every `@pytest.mark.skip`, `pytest.skip(`, `unittest.skip` and `xfail` added since baseline.

Deliver `T5_harness_validity.md`.

### T6 — Fixes that cannot be proven offline

Some fixes change what a *run* produces (F22 flag-on path, F23, F25, F27, F28, F29, F31). For each, you can and must prove the code and the fixture-level behaviour. What you cannot prove is that a real run shows them firing, because no run has been produced since the fixes and pipeline execution is outside this prompt. Write `T6_deferred_run_evidence.md` listing, per such fix: what you verified offline, and the single artefact/field a future run would need to show for the fix to be considered CLOSED at run level. Keep it to one line per fix. Do not attempt to produce that evidence.

### T7 — Defect register and verdict

Deliver `AVS-TST-SD-002-001_FINDINGS.md` with:

1. **Production-safety verdict** (one paragraph): is the legacy `--evening`/`--morning` path behaviourally unchanged apart from the explicitly unflagged Phase 2 authority corrections? List every unflagged change.
2. **Fix table**: F01–F37 with your status and the evidence path, one row per fix. This is the primary deliverable.
3. **Gate and P0 tables**: G02–G17, G20 and P0-01…P0-07 with your status, the implementer's status, and the evidence path. G01, G18A–D, G19 and P0-08 are listed as `OUT_OF_SCOPE — live cycle` and nothing more.
4. **Defect register** `AVS-TST-SD-002-001_DEFECTS.csv`: id, severity (P0/P1/P2), phase, file:line, design_ref, description, reproduction (test path), implementer_claim_contradicted (yes/no), status OPEN. Do not fix anything.
5. **Test-edit verdict**: count of `OBSOLETE_ASSERTION_CORRECTED` / `FIXTURE_CORRECTED` / `PROTECTION_WEAKENED` / `UNRELATED_CHANGE`.
6. **Claims you could not verify** and exactly what would let you.
7. **Your recommendation**: whether the offline build is sound enough that ACK may proceed to the controlled live cycle, or which fixes must be reworked first. Do not recommend enabling any flag.

---

## 6. Output layout

```
audit\pipeline_map\AVS-TST-SD-002-001\
  environment.json
  T0_evidence_integrity.md
  T0_flag_inventory.csv
  T0_legacy_path_diff\            (one .diff per changed production module, with hunk classification)
  T1_claim_register.csv
  T1_xml\                         (one JUnit XML per isolated pytest process)
  T2_test_edit_audit.csv
  T2_adversarial_tests\
  T3_authority_pack\
  T3_authority_matrix.csv
  T4_traceability.csv
  T5_harness_validity.md
  T6_deferred_run_evidence.md
  AVS-TST-SD-002-001_FINDINGS.md
  AVS-TST-SD-002-001_DEFECTS.csv
  tmp\                            (restore drills, fixture DBs — delete on completion)
```

Every pytest invocation you run must be recorded as the exact command line in `environment.json` alongside its XML path and sha256.

---

## 7. Reporting discipline

- Quote file paths and line numbers for every source claim. Quote the test name for every executed claim.
- Never write "verified" for anything you did not execute or read yourself.
- When you disagree with an implementer classification (e.g. "pre-existing test-contract drift"), say so and give the evidence; do not soften it.
- If you run out of budget, finish the track you are on, mark the remaining tracks `BLOCKED — budget`, and deliver what exists. A partial register with honest statuses is worth more than a complete one with inferred ones.
- The user's operating standard applies: nothing is closed until an artefact shows it firing. Offline evidence closes offline gates only.

Begin with T0.
