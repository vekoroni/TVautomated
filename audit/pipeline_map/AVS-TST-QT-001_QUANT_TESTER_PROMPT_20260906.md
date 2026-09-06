# AVS-TST-QT-001 — Quant tester: comprehend, then test, the 4–6 September build

**Issued:** 2026-09-06 (Sunday)
**Tester:** Claude Code, acting as an independent quantitative tester — not a checklist runner
**Repository:** `C:\Users\ACKVerissimo\AVSHUNTER-Intelligence` (production; **read-only**)
**Staging package:** `C:\Users\ACKVerissimo\Documents\Codex\2026-07-24\a\worker3_foundation\` (Worker 3; **read-only**)
**Interpreter:** `C:\Python314\python.exe`; run every test file in its own pytest/unittest process
**Output root:** `audit\pipeline_map\AVS-TST-QT-001\` — the only place you write
**Trading context:** the operator intends to resume real-capital trading on Tuesday 8 / Wednesday 9 September on the MVP boundary in `AVS-MVP-001`. Your verdict informs that decision. It does not make it.

---

## 0. What kind of tester you are

A quant tester does three things a regression runner does not. First, they **understand the business outcome** the code is meant to produce — here, an honest long single-leg CALL/PUT book where every executable row has governed direction, a real stop, a live quote, and no authority derived from fabricated evidence. Second, they **understand the algorithm** well enough to say, before running anything, what a correct implementation must output for a given input and what a plausible-looking wrong implementation would output instead. Third, they **test the logic, not the test suite** — a suite that passes while the defect is live has happened twice this week (the Phase 3 adapter tests against mocks; the Phase 4 Vanguard test with `required=True`), so "N passed" is a claim you verify, never evidence you cite.

You therefore work in this order: establish what was built (§0A) → comprehend (§1) → pre-register expectations → test logic → reconcile against run artefacts → report. Do not run a single test before §0A and §1 are written.

---

## 0A. Build archaeology — establish what was actually built, independent of the documents

Before reading any claim sheet, reconstruct the last three days of change from evidence that does not depend on anyone's write-up. The documents in §1 describe what the implementers *say* they built; this track establishes what is *in the tree*. The difference between the two lists is one of your primary findings.

**Reference points.** Tag `pre-tidy-20260904` (Friday ~09:30, before any AVS-SD-003 work) and `post-tidy-20260904` (after the root tidy). The Phase 0 backup `backups\avs_sd_002_rev1_1_phase0_prechange_20260903_133546\` holds the tree as of Thursday 13:35 with a SHA-256 manifest. Baseline commit SHA per the claim sheets: `6e834b8`.

Produce `00_BUILD_ARCHAEOLOGY.md` and `00_changed_files.csv` from all of the following:

1. **Git.** `git log --oneline --stat pre-tidy-20260904..HEAD`; `git diff --stat pre-tidy-20260904..HEAD`; `git status --porcelain` (the dirty working tree is part of the build — the DDD manifest itself says `PRE_EXISTING_DIRTY_WORKTREE`); `git tag -l --sort=creatordate` with dates; `git stash list`. Record every commit SHA, author, timestamp and message. Record every uncommitted modified/untracked path.
2. **File-level change list.** For every tracked and untracked file (excluding `_attic\`, `backups\`, `venv\`, `data\`, `__pycache__`, `.pytest_cache`, `audit\**\tmp*`): current SHA-256, SHA-256 at `pre-tidy-20260904`, SHA-256 in the Phase 0 backup manifest if present, mtime, and a change class: `ADDED`, `MODIFIED`, `DELETED`, `MOVED_TO_ATTIC`, `UNCHANGED`. Sort by mtime. This is `00_changed_files.csv`.
3. **Backup manifests as a change ledger.** Every `backups\*prechange_2026090[4-6]*\MANIFEST.json` lists the files that change touched, with pre-change hashes. Enumerate them in time order (`avs_sd_003_phase0_…093119`, `…blockers_…111946`, `…integration_…161255`, `ddd_production_integration_…120000`, `ddd_closure_prechange_20260905`, and any others). For each file in each manifest: confirm the pre-change hash matches the tree state immediately before that change (i.e. the chain is consistent), and flag any file that changed **without** appearing in any manifest — that is a change made without a backup, which AVS-SD-002 §16 and the IMP-001 working rules forbid.
4. **Release manifests as drift detectors.** `AVS-DDD-PRODUCTION-INTEGRATION-20260905\RELEASE_MANIFEST.json` and `ddd_closure_20260905\AVS_DDD_CLOSURE_RELEASE_MANIFEST_20260905.json` pin production-file hashes. Compare every pinned hash to HEAD. A mismatch means the file changed *after* the release it belongs to was declared — list them. Resolve the runtime-profile hash question here (`2b416bbe…` vs `054a76be…` vs live).
5. **Function-level diff of the decision-bearing modules.** For `intelligent_orchestrator.py`, `orchestrator\dynamic_dispatcher.py`, `orchestrator\dynamic_thesis.py`, `orchestrator\dynamic_validation.py`, `orchestrator\dynamic_release.py`, `vanguard\layer1_auction\auction_synthesizer.py`, `vanguard\layer2_statistical\edge_detector.py`, `scripts\avshunter_options_intelligence.py`, `scripts\build_completed_market_profiles.py`, `canonical_data\marketdata_stock_candles.py`, `canonical_data\intraday_bars.py`, `eod_candidate_engine.py`, `execution_gate.py`, `morning_gate.py`, `morning_handoff_finalizer.py`, `contracts\lab_control.py`, `contracts\dynamic_session_contract.py`, `handoff_contract_audit.py`, `avshunter_discovery_ULTIMATE.py`: produce `git diff pre-tidy-20260904..HEAD -- <file>` and list, per file, the functions/classes added, removed or modified, with a one-line statement of what each change does **as read from the code**, not from any note. Flag any change that alters a decision-critical field's writer or adds a reader that could override one.
6. **Test-tree diff.** Every file under `tests\` added, modified or deleted since the tag, with the same hash columns. Count modified existing tests — this feeds Track C item 5.
7. **New runtime surfaces.** Any new CLI switch, environment variable, config/JSON file under `contracts\` or `config\`, database table or column (diff the SQLite schemas of `data\canonical\control_plane.sqlite` and any new ledger DB against the Phase 0 backup copies — read-only), and any new scheduled or launcher script.
8. **Run artefacts as a timeline.** `data\output\runs\` entries created since 4 Sep 00:00 with `run_meta.json`'s recorded git head, flag states and runtime profile hash — this tells you which code state produced which run.
9. **Worker 3.** Same mtime/hash sweep over `Documents\Codex\2026-07-24\a\worker3_foundation\`; confirm from imports that nothing there references the repository, and that nothing in the repository references it.

**Then reconcile.** Build `00_built_vs_claimed.csv`: one row per changed production file or new surface, with the claim sheet(s) that mention it (or `UNDOCUMENTED`), and one row per claim-sheet item with the file evidence that supports it (or `NO_CODE_EVIDENCE`). Every `UNDOCUMENTED` change and every `NO_CODE_EVIDENCE` claim is carried into `C_DEVIATIONS.md`.

Finish 0A by printing: commits since the tag, files changed by class, files changed without a backup manifest, pinned-hash mismatches, undocumented production changes, and the run-to-code-state table. Only then open §1.

---

## 1. Comprehension gate — write `01_SYSTEM_MODEL.md` before any test

Build the model from what 0A found in the tree, using the documents to explain intent — not the other way round.

Read the documents below **in this order** and write a model of the system as it stands at HEAD today. The model is graded on whether it would let a second tester predict outputs; it is not a summary.

### 1.1 Business outcome and authority (read first)

- `audit\pipeline_map\AVS-MVP-001_MINIMUM_VIABLE_PIPELINE_20260904.md` — the trust boundary the operator will trade on, the manual filter (§4), the kill criteria (§6)
- `audit\pipeline_map\AVS-AR-003_AS_IS_PIPELINE_SHIPPABILITY_REVIEW_20260903.md` §§1, 6.3, 8, 12 — the product objective ("one observation contract, one authority per decision, one derivation per field, one presentation surface, one append-only record"), the six required field states, the authority matrix, the twenty acceptance gates
- `audit\pipeline_map\AVS-SD-002_DATA_INTELLIGENCE_AND_MARKET_PROFILE_LIFECYCLE_20260903.md` §§3, 5–9, 14, 21 — goals/non-goals, the Market Profile algorithm (§9.1–9.5: bin width, TPO, POC, 70% value area, coverage, gap/POC/value-mid in ATR units, robust-z shock, five-component uncertainty), acceptance tests
- `audit\pipeline_map\AVS-SD-002_REV1_1_DYNAMIC_SESSION_ORCHESTRATION_20260903.md` §§5–11, 19 — session/evidence/thesis state model, identity model, dispatcher decision table, authority ceilings, twenty gates

### 1.2 What was found wrong and what was designed to fix it

- `audit\pipeline_map\AVS-RCA-002\A_run_validation.md` and `B_executed_path_review.md` — run `20260904_004338`: the fail-open mechanism (five `False` defaults), the 43 `ARMED`-without-stop, the null-target ladder (`:4138-4158`, `:5462-5468`), the lineage boundary map, the audit that could not fail
- `audit\pipeline_map\AVS-SD-003_GAP_ELIMINATION_20260904.md` (current version; note it was revised after issue) — D1–D3, gap register C1, per-gap specs C3, gates AG-01…AG-20 and RG-01…RG-09, test additions C5
- `audit\preflight\AVS-PRE-001_20260904_075820\AVS-PRE-001_RESULT.md` — the adapter defects D1–D5 with the 30-bar vs 78-bar evidence; `01_responses.jsonl` are real provider bodies

### 1.3 What was then built (claims under test)

Read every one of these as a **claim sheet**, and while reading, write into `02_CLAIMS_INVENTORY.csv` one row per claim: `source_doc, claim, implementer_status, files_named, tests_named, run_artefact_named (Y/N)`.

- `audit\pipeline_map\AVS-IMP-SD-003-001_CYCLE1_AND_ADAPTER_FIX_20260904.md` — the instruction Codex was given (binding decisions D1–D5 in its §1)
- `audit\pipeline_map\AVS-IMP-SD-003-002_20260904\` — cycle 1 + adapter; claims 933 passed
- `audit\pipeline_map\AVS-IMP-SD-003-003_20260904\` — five blockers; audit replay on `20260904_004338` = 16 FAIL
- `audit\pipeline_map\AVS-IMP-SD-003-004_20260904\` — integration repair after **real Evening run `20260904_122358`**; 271→270 candidates, MRP the one true missing stop; one test fixture edited
- `audit\ops\AVS-OPS-001\AVS-OPS-001_REPORT.md` — root tidy; three commits; pre/post matrix
- `audit\pipeline_map\AVS-DDD-PRODUCTION-INTEGRATION-20260905\` — **normal `--evening`/`--morning` now dispatch through the dynamic dispatcher**; runtime profile `contracts\dynamic_session_runtime_v1.json` enables the "controlled DDD capability set"; Morning adapter serialises Morning Gate results into validation events; 1,063 passed
- `audit\ddd_closure_20260905\` — after **real Evening run `20260905_151448`** produced 1,491 partial / 0 usable profiles: exclusive `to` boundary (+1 interval), **coverage gate 95% → 90%**, `DATA_REPAIR_REQUIRED` before EOD, single `pipeline_run_id`, immutable build receipt, telemetry split, runtime profile `AVS-DDD-CLOSURE-20260905`
- `audit\pipeline_map\AVS-TST-SD-002-001\` — the prior independent tester's outputs (cite, don't repeat)
- The Worker 3 staging package: `README.md`, `TEST_REPORT.md`, `SLICE2…SLICE13_*.md` under `Documents\Codex\2026-07-24\a\worker3_foundation\` — an isolated Claude-analyst package built 5–6 Sep against "AVS-W3-SD-001" (a design that lives in a Codex task response; if you cannot find it as a file, say so). Note the other dated folders under `Documents\Codex\` are session transcripts from May–August; read only `.md` files dated on or after 4 September.

### 1.4 What `01_SYSTEM_MODEL.md` must contain

1. **The executed path at HEAD.** Trace `python intelligent_orchestrator.py --evening` from the CLI to the final book, *as the code is now*, naming the branch taken at each flag/profile/config read. The DDD integration claims the legacy path is no longer what runs; establish whether that is true, what `contracts\dynamic_session_runtime_v1.json` actually enables, its current SHA-256 (two manifests record different hashes — `2b416bbe…` and `054a76be…`; resolve which is live), and what `AVSHUNTER_DYNAMIC_RELEASE_DISABLE_ALL=1` would do.
2. **The authority matrix as implemented** — for each of direction, hold, invalidation, contract, viability, monetisability, profile, macro, final action: the sole writer (file:function), every reader that could override it, and whether the override path is reachable. Compare with AR-003 §8.
3. **The algorithms changed this week, each as a specification**: inputs, formula or rule, outputs, and — critically — *the wrong answer a subtle bug would give*. Minimum set:
   - Vanguard fail-closed verdict and the Layer-2 score (`_calculate_right_side_score`, the `auction_conf × 0.40` term)
   - Completed-profile coverage: `expected_bars` from the calendar, `coverage_ratio`, the 90% gate, "both session edges", exclusive-`to` boundary
   - Market Profile calculation in `market_structure\profile.py` (bin width, TPO count, POC selection, 70% value-area expansion, cadence)
   - Structural-target ladder and the null-target guard, both directions
   - Invalidation precondition at arming, EOD, Lab; `DATA_REPAIR_REQUIRED`
   - Execution viability (spread denominator, thresholds, quote age) vs scenario monetisability
   - Handoff/semantic audit rules (the nine categories) and `EMPTY_BY_DESIGN` corroboration
   - Dynamic dispatcher decision table and `RunPlan` hash; validation event identity
   - Worker 3 behavioural engine v1 rules (control proxy 3×4-session windows with 25% displacement; contraction ≤70%; effort/reward ≥120% volume with ≤50% move; exhaustion; failed follow-through; campaign origin) and its v2 bound-slot assessment validator
4. **Pre-registered expectations** — for each algorithm, at least three concrete input→output cases you commit to *before* running code: a nominal case, a boundary case, and a mirror (CALL↔PUT or buyer↔seller) case. These go in `03_PREREGISTERED_EXPECTATIONS.csv` with columns `algorithm, case, input, expected_output, rationale, design_ref`. You will be scored on how many of these the code disagrees with and whether you were right.

Deliver §1 outputs, then stop and print a five-line summary of the executed path before continuing. (This is a checkpoint for the operator, not a permission request; continue unless told otherwise.)

---

## 2. Hard constraints

- **Never execute the pipeline.** No `--evening`, `--morning`, `--auto`, `--finalise`, `--replay`; no stage scripts, Lab server, Interpreter commands, provider calls. The single exception is `python intelligent_orchestrator.py --evening --plan-only --as-of-utc <now>`, which two implementers have run as side-effect-free — you may run it **once**, with a full recursive filesystem snapshot (path, size, mtime) of the repository and `data\` before and after, and the diff must be empty except under your output root.
- **Never set a feature flag or edit the runtime profile.** Flag-on behaviour only via monkeypatched unit tests in isolated processes.
- **Production code, run data, backups and the Worker 3 package are read-only.** New tests you write live under your output root and import production modules; they never modify them.
- **Defects are filed, never fixed.**
- **Worker 3 live transport:** do not attempt any Anthropic API call. The last attempt returned 401; that is a credentials matter for the operator, not a test.
- **Three-direction discipline** on every direction-bearing rule: CALL / PUT / OTHER (STRANGLE, UNRESOLVED, null). A CALL-only pass is not a pass.
- **Evidence standard:** every finding cites file:line for source claims and artefact path + filter + count for run claims. Test counts from claim sheets are never evidence.

---

## 3. Track A — Logic tests against pre-registered expectations

For each algorithm in §1.4(3), write tests under `A_logic_tests\` that encode your `03_PREREGISTERED_EXPECTATIONS.csv` cases, run them, and record `expected / actual / agrees (Y/N)` in `A_results.csv`. Where the code disagrees with your expectation, decide which is wrong — cite the design clause — and file it either as a defect (code wrong) or a correction (your expectation wrong, with the reason). Specific probes the claim sheets do not cover:

**A1 Profile coverage and the 90% gate.** Build synthetic 5-minute frames: 78/78, 77/78 (last bar missing — the exact pre-closure symptom), 75/78, 71/78, 70/78, 69/78, and a 78-bar frame missing the 09:30 bar (first edge absent). Assert which are `COMPLETED_SESSION` and which `PARTIAL_SESSION`; assert none below the gate can set `MarketProfileEvidence.usable=True`. Then answer the design question the closure did not: **is 90% the right threshold?** AVS-SD-003 and AVS-PRE-001 specified 95%; the closure lowered it to 90% after a run produced 77/78 (98.7%) frames — which would have passed 95% once the exclusive-`to` fix landed. Establish whether 90% was necessary for any legitimate case, what a 70–78-bar profile does to POC/VAH/VAL error versus the full session (compute it on the real R2/SPY frame from `01_responses.jsonl` by dropping bars), and recommend a threshold with evidence. Note AVS-PRE-001's 78 RTH bars are 09:30–15:55 open-stamped; make sure "both session edges" is defined consistently with that.

**A2 Market Profile arithmetic.** On the real 78-bar SPY frame: compute POC, VAH, VAL independently (your own TPO implementation, 70% expansion around POC) and compare with `market_structure\profile.py`. Assert `VAL ≤ POC ≤ VAH`, value-area TPO share ∈ [0.70, 0.70 + one bin's share], determinism under row shuffling, and null (not `0.0`) for a 12-bar input. Check the bin-width formula `round_to_tick(max(tick, ATR14 / divisor))` — what happens when ATR14 is null or zero?

**A3 Vanguard scoring.** With profile evidence absent, assert every row's `right_side_score` alignment component is exactly 0 and `auction_conf` is 0.0 for CALL, PUT and OTHER inputs; with a usable packet, assert `PROFILE_CONTEXT_ONLY` grants no readiness. Then the question the design deferred: with the whole auction component zeroed, **what remains in the Layer-2 score, and does the ranking still discriminate?** Compute the score decomposition on the latest run's Vanguard rows and report the share of total score that the auction component contributed before the fix — this is the operator's real exposure in the AG-18 book.

**A4 Invalidation and target geometry.** Mirror pairs: CALL entry 100 / stop 95 / target 110 and PUT entry 100 / stop 105 / target 90 must yield identical `stop_dist`, `target_3r`, R:R and transitions. `stop=None` must yield a governed `UNRESOLVED_EXCEPTION` in **both** branches (the CALL branch at `:5464` was never exercised by any run). Wrong-side stop (CALL stop above entry) must be rejected, not silently used. OTHER direction must remain `NOT_APPLICABLE` end-to-end (RG-07).

**A5 Execution viability.** One quote, one state: assert `execution_gate.py`, Options, Morning and Lab produce the same liquidity state for the same bid/ask/size; assert the denominator is mid everywhere; assert a `quote_age_seconds` of literally `0.0` cannot be produced from a real timestamp pair; assert a synthetic/reconstructed mark cannot reach `execution_viability_eligible=True`.

**A6 Audit rules.** Run the corrected semantic audit read-only against the artefacts of `20260904_004338` and assert `fail_count ≥ 6` with **zero** shadow-book contribution (the implementer reports 16; reproduce the number and list the sixteen). Then construct a minimal fixture that is *just* healthy and assert `fail_count = 0` — an audit that fails everything is as useless as one that passes everything. Assert the empty-shadow-book rule requires corroboration from the dropoff audit.

**A7 Dispatcher and identity.** Fixed `as_of_utc` matrix (closed / premarket / regular / after-hours / weekend / Labor Day): assert the resolved action and plan hash are deterministic and match Rev 1.1 §8.3; assert `--evening` resolves to `BUILD_THESIS` and never to `VALIDATE` or `FINALISE`; assert a changed cutoff mints a new `invocation_id` with a link; assert the build receipt is bound to the plan hash. Reproduce the DDD-closure plan hash `06a1c5c8…` if the inputs are recoverable; if not, say what is missing.

**A8 Worker 3 behavioural engine.** Under `A_worker3\`, import the staging package and test its rules against synthetic daily bars you construct: a clean 12-bar rising structure with ≥25% displacement → `BUYER_CONTROL_PROXY`; its exact price reflection → `SELLER_CONTROL_PROXY`; displacement at exactly 25% and 24.9%; contraction at 70.0% and 70.1%; effort/reward at the 120%/50% boundaries; 11 bars → `INSUFFICIENT_DATA` (not a neutral score); a gapped session sequence → rejection. Then the v2 validator: a response with an unbound numeric literal → rejected; a valid citation → accepted; a response asserting "Phase C accumulation" → blocked by the semantic lint. Confirm from the code (not the notes) that nothing in the package imports production modules, touches production paths, or can publish. Record its 263-test result yourself.

---

## 4. Track B — Run-artefact reconciliation

There are now three real runs under different code states. Reconcile each; do not average across them.

| Run | Code state (establish from `run_meta.json`, git, manifests) | What it can prove |
|---|---|---|
| `20260904_004338` | pre-build baseline | the defects (already done in RCA-002; reuse) |
| `20260904_122358` | after IMP-002 (cycle 1 + adapter), before IMP-003/004 | AG-01…AG-10 on the **legacy** path; the 271/270/MRP claim |
| `20260905_151448` | after DDD integration, before DDD closure | the dynamic path's first real output; 1,491 partial profiles; the exclusive-`to` symptom |
| any run dated after `20260905` 22:00 | after DDD closure | the current code — **if it exists, it is the primary evidence**; if not, say so |

For each run, produce `B_<run_id>.csv` with every AG-01…AG-17 and RG-01…RG-09 gate: filter, count, three-direction split, PASS/FAIL, and the code state it was produced under. Add the DDD-specific checks: one `pipeline_run_id` across Discovery/profile/Vanguard/Options/book; one completed session date across stages; build receipt present and plan-hash-bound; `run_meta.json` records all nine flags and the runtime profile hash; completed-profile `usable_ratio` and `systemic_failure`; validation events (Morning runs only) 1:1 with actionable rows.

Then the reconciliation that matters most: **the IMP-004 claim that run `20260904_122358` had 271 candidates, 270 with valid invalidation, and MRP as the single true missing stop.** Recompute from the artefacts. And the DDD-closure claim that `20260905_151448`'s *selected handoff* is at 100% semantic coverage with zero missing invalidations while its profile stage failed — confirm both halves, and state plainly what that book would have looked like to a trader (how many rows, ranked on what, with what profile evidence).

---

## 5. Track C — Deviation register

`C_DEVIATIONS.md`: every place where the implemented state departs from an accepted design or from a binding instruction, with the evidence and the risk. Do not soften. Known candidates to confirm or refute:

1. **The production path is now the dynamic dispatcher**, not the legacy `--evening` path that AVS-SD-003 §C2 and AVS-MVP-001 §2 assumed would carry the MVP with all dynamic flags off. Establish exactly which capabilities the runtime profile enables, whether any of them writes to a decision-critical field, and whether the MVP filter fields in AVS-MVP-001 §4 are still produced with the same names and semantics.
2. **Coverage gate 95% → 90%** (DDD closure claim 5) — a threshold change made in the same commit as the boundary fix that removed the need for it. Design reference: AVS-SD-003 §C3 W2-0 and AVS-PRE-001 §5.
3. **Runtime profile hash drift** between the DDD integration manifest and the DDD closure manifest; is the live file either of them?
4. **`tests\msi\` excluded from every acceptance count** since Phase 8 — legitimate historical pack, or a way to keep a green number? List what it asserts.
5. **Test edits.** Count every test file whose content hash changed between the `pre-tidy-20260904` tag and HEAD; classify each edit as in AVS-TST-SD-002-001 §T2 (`OBSOLETE_ASSERTION_CORRECTED` / `FIXTURE_CORRECTED` / `PROTECTION_WEAKENED` / `UNRELATED`). IMP-004 admits one fixture edit; find the rest.
6. **"CLOSED OFFLINE" used as a status** in IMP-002/003 despite AVS-SD-003 §C8 and the 4 Sep policy that `CLOSED` requires a run-artefact count. Which claims have since acquired a run artefact, and which are still offline-only?
7. **Worker 3** is built against a design (AVS-W3-SD-001) that is not in the repository and is not in AVS-SD-001's CT3 roles as approved; it is isolated and unintegrated — confirm it has no production reach today, and note whether its README's "next slice" plan would cross the Interpreter authority boundary in AR-003 §7.14.
8. **`.venv` points to a removed interpreter** (DDD integration note) — a release-reproducibility regression against P0-01.

---

## 6. Track D — MVP readiness verdict

`D_MVP_READINESS.md`. Against AVS-MVP-001 §4 (the trader's manual filter) and §6 (kill criteria), using the most recent run artefact:

- For each filter field, is it present in the Lab book under the expected name, populated, and produced by the authority AR-003 assigns? Table: field, present, populated N/256-style, producer, authority match.
- Which kill criteria would fire on the most recent run *today*?
- The three things a trader would most plausibly be misled by in the current book, with the row-level evidence.
- Your verdict on whether the MVP boundary is intact under the dynamic dispatcher, stated as one of: `INTACT — trade on the §4 filter`, `INTACT WITH CONDITIONS — <conditions>`, `NOT INTACT — <what breaks it>`. This is advice; the operator decides.

---

## 7. Deliverables and reporting

```
audit\pipeline_map\AVS-TST-QT-001\
  environment.json                 (interpreter, every command run, every XML + sha256, plan-only fs diff)
  00_BUILD_ARCHAEOLOGY.md
  00_changed_files.csv
  00_built_vs_claimed.csv
  01_SYSTEM_MODEL.md
  02_CLAIMS_INVENTORY.csv
  03_PREREGISTERED_EXPECTATIONS.csv
  A_logic_tests\   A_worker3\   A_results.csv
  B_20260904_122358.csv  B_20260905_151448.csv  B_<latest>.csv
  C_DEVIATIONS.md
  D_MVP_READINESS.md
  AVS-TST-QT-001_FINDINGS.md
  AVS-TST-QT-001_DEFECTS.csv       (id, severity, file:line, design_ref, repro test, status OPEN)
```

`FINDINGS.md` opens with: the built-vs-claimed reconciliation (undocumented changes, unsupported claims, changes without backups, pinned-hash drift); how many pre-registered expectations the code disagreed with, and in how many of those you were wrong; the gate table for the latest run; the deviation register summary; the MVP verdict; and what you could not verify and why. Statuses are `VERIFIED`, `VERIFIED_OFFLINE`, `SOURCE_ONLY`, `CONTRADICTED`, `BLOCKED` — never "closed". If you run out of budget, finish the track you are on and deliver with the rest marked `BLOCKED — budget`.

Begin with §0A. Do not run a test until `00_BUILD_ARCHAEOLOGY.md`, `01_SYSTEM_MODEL.md` and `03_PREREGISTERED_EXPECTATIONS.csv` exist.
