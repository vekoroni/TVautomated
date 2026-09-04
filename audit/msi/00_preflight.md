# MSI v1.1 Independent Test — Preflight

**Date:** 2026-08-30 | **Design:** AVS-SD-MSI-001 v1.1 (`audit/solution_design/MARKET_STRUCTURE_INTERPRETER_DATA_ENHANCEMENT_SOLUTION_DESIGN_20260830.md`, read in full)
**Role:** independent test engineer. Implementer: Codex. Production code is read-only for this engagement.

## Commit / working-tree state

- Current HEAD: `5d886f07c1d290f25600e2e7e62ae77aad85476a`
- MSI-0 baseline commit recorded by the implementer (`audit/msi_implementation/MSI_IMPLEMENTATION_RECORD_20260830.md`): `5d886f07c1d290f25600e2e7e62ae77aad85476a` — **matches HEAD exactly.**
- Working tree: **not clean** (216 tracked-path status lines from `git status --short`, plus numerous permission-denied warnings on `.codex_test_temp/*`, `tests/.codex_tmp_*` scratch directories left by the implementer's own test runs). This matches the implementation record's own statement: "Working tree: pre-existing user/remediation changes preserved; implementation must not reset or discard them." The dirty tree is expected — this repository has carried uncommitted work across every prior audit pack in this engagement (OLM, OLM-fix, OLM-fix retest) and MSI is built on top of that same uncommitted baseline, not a clean commit.
- Pre-change backup: `backups/msi_v11_prechange_20260830_110913/` with `MANIFEST.md` — 21 files backed up by SHA-256 hash (orchestrator, Morning Gate, Morning handoff finalizer, Lab control/UI, handoff contract, selected-contract economics, canonical_data core files, Options Intelligence, Interpreter command/engine/macro/direction files, the design doc itself). **Verified present and readable.**

## §22 Module map — existence check

Existing-owner files were spot-checked for presence (all pre-date MSI and were already covered by prior audit packs in this repo); new modules were checked directly.

| Component | Existing owner | Exists? | New module | Exists? | MSI-0-recorded entry-point function |
|---|---|---|---|---|---|
| Discovery/worklist | `avshunter_discovery_ULTIMATE.py`, `canonical_data/discovery_publisher.py`, `canonical_data/worklist_gate.py` | Yes (all three) | none | n/a | **Not recorded** |
| CDS request/registry | `canonical_data/gateway.py`, `registry.py`, `contracts.py`, `request_ledger.py`, `storage.py` | Yes | `canonical_data/market_observation_service.py` | **MISSING** — this exact filename does not exist. The equivalent responsibility appears to be split across `canonical_data/market_observation_resolver.py`, `marketdata_response.py`, `intraday_bars.py`, `stage_publisher.py` (all present) — a different module layout than the design names. This is a finding, not a pass: the design's named new module was not built under its named path. | **Not recorded** |
| Session clock | duplicated consumer logic | n/a | `canonical_data/session_clock.py` | Yes | **Not recorded** |
| OCC identity | `contracts/selected_contract_economics.py`, `canonical_data/contract_reference.py` | Yes (both) | `canonical_data/option_identity.py` | Yes | **Not recorded** |
| Options Intelligence | `scripts/avshunter_options_intelligence.py`, `canonical_data/option_chain_store.py` | Yes | none | n/a | **Not recorded** |
| Selected-contract economics | `contracts/selected_contract_economics.py` | Yes | none | n/a | **Not recorded** |
| OLM | `contracts/options_liquidity_lifecycle.py`, `canonical_data/option_liquidity_lifecycle.py`, `contracts/options_liquidity_execution_guard.py` | Yes (all three) | none | n/a | **Not recorded** |
| Market Structure | none | n/a | `market_structure/contracts.py`, `params.py`, `profile.py`, `service.py` | **`contracts.py` MISSING**; `params.py`, `profile.py`, `service.py` all present. | **Not recorded** |
| Morning Gate | `morning_gate.py` | Yes | none | n/a | **Not recorded** |
| Handoff finalisation | `morning_handoff_finalizer.py`, `contracts/handoff_contract.py` | Yes (both) | `contracts/interpreter_handoff.py`, `tools/msi_reconcile.py` | Yes (both) | **Not recorded** |
| Lab materialisation | `contracts/lab_control.py`, `intelligence-lab/intelligence_lab.py` | Yes (both) | `contracts/lab_evidence_overlay.py` | Yes | **Not recorded** |
| Lab UI | `intelligence-lab/static/index.html` | Yes | none | n/a | **Not recorded** |
| Interpreter resolver | `pipeline_interpreter/pipeline_interpreter_commands.py`, `pipeline_interpreter_engine.py` | Yes (both) | `pipeline_interpreter/evidence_resolver.py` | Yes | **Not recorded** |
| Interpreter output | active prompt/engine modules | Yes | `pipeline_interpreter/assessment_contract.py` | Yes | **Not recorded** |
| Interpreter macro | `pipeline_interpreter/news_macro_readers.py`, `direction_conflict_resolver.py`, system prompt | Yes (all three) | `pipeline_interpreter/macro_context.py` | Yes | **Not recorded** |
| Structured automation evidence | `pipeline_interpreter/automation_v2/` | not independently re-checked this pass (out of MSI's own new-module set; existing dir from prior work) | extend existing manifest contracts | n/a | **Not recorded** |
| Screenshot adapter | existing chart/screenshot commands, `pipeline_interpreter/capture_v1/` | Yes (`capture_v1/` present) | `pipeline_interpreter/screenshot_adapter.py` | Yes (but `MSI_SCREEN_ADAPTER` flag is OFF — see below) | **Not recorded** |
| Orchestration | `intelligent_orchestrator.py` | Yes | none | n/a | **Not recorded** |

**Also noted:** the implementation record cites two modules not named anywhere in the §22 table at all — `canonical_data/marketdata_response.py` and `intelligence_lab/backend.py` / `intelligence_lab/index.html` (note the underscore, not hyphen — the design's Lab UI row names `intelligence-lab/static/index.html` with a hyphen; a module named `intelligence_lab/backend.py` with an underscore is a **different path** and was not found to exist as such — see the functionality-agent's task to confirm whether this is a typo in the implementation record referring to the real `intelligence-lab/` directory, or a genuinely new, unlisted module). This is flagged for the Flow/Regression agents to resolve with a direct file check, not assumed here.

**Finding against MSI-0:** the design's own MSI-0 exit criterion (§19 MSI-0: "record the current production baseline commit/hash and every intended modified file... publish the module map, ID rules, enums and provider fixtures defined in this document") required recording, for every module-map row, the exact active entry-point function before edits began. No such per-row entry-point record exists anywhere in the repository — only a file-hash-only backup manifest (`backups/msi_v11_prechange_20260830_110913/MANIFEST.md`) and a prose implementation record with no function-level citations. **This MSI-0 deliverable is UNVALIDATED/absent.** It does not by itself block testing (the actual code can be read directly), but per the task's own gating instruction this is recorded as a finding against MSI-0, and every test card below that needs a specific function must independently locate and cite it, since no authoritative MSI-0 record exists to check against.

## §26 Feature switches

Single configuration source confirmed: `config/msi_runtime.json`, read by `msi_runtime.py` (both present, matching the design's "read from one configuration module" requirement — **PASS** on that specific structural requirement). Current recorded state (`deployment_state: "CONTROLLED_PRODUCTION_CYCLE_1"`):

| Design flag name | Config key | State |
|---|---|---|
| `MSI_V2_CAPTURE` | `v2_capture` | **true** |
| `MSI_CDS_RESOLVER` | `cds_resolver` | **true** |
| `MSI_MINUTE_BARS` | `minute_bars` | **true** |
| `MSI_STRUCTURE` | `structure` | **true** |
| `MSI_LAB_V3_VIEW` | `lab_v3_view` | **true** |
| `MSI_MACRO_ADVISORY` | `macro_advisory` | **true** |
| `MSI_INTERPRETER_RESOLVER` | `interpreter_resolver` | **true** |
| `MSI_SCREEN_ADAPTER` | `screen_adapter` | **false** |

Seven of eight switches are ON. This means most functionality/logic/computation/flow tests below are **not** gated to NOT_IMPLEMENTED purely by a disabled switch — code paths should be live and testable against fixtures. The one exception: **W-17 (screenshot lane) and any MSI-7b-specific behaviour must be marked NOT_ACTIVATED**, not tested as if live, since `MSI_SCREEN_ADAPTER` is off. This directly matches the design's own phased sequencing (§19: "MSI-7b may activate later and does not block structured Interpreter production").

Note per the design (§19 MSI-8, §28 step 6): "never activate all switches at once without phase evidence." Seven switches being simultaneously true, with **zero completed production cycles** (see below), is itself worth flagging in `20_design_inconsistencies.md` as a process deviation from the design's own stated sequencing discipline — reported, not resolved, per instructions.

## §16.1 Provider fixtures

Fixture directory: `tests/fixtures/marketdata/` (not `tests/fixtures/msi/` — the implementer placed fixtures under a pre-existing, non-MSI-namespaced path). Five files exist:

- `option_chain_list_sizes.json`
- `option_quote_crossed.json`
- `option_quote_negative_size.json`
- `option_quote_no_data.json`
- `option_quote_scalar_ok.json`

The design (§16.1 final paragraph) requires fixtures for: **ok, no_data, error, scalar, parallel-array, missing-field**. Mapping by filename alone (content not yet verified — this is a preflight inventory, not a content audit):

- **ok** — no file literally named `*_ok*` except `option_quote_scalar_ok.json`, which conflates ok+scalar. Whether a pure "ok" (non-scalar, non-error) case is covered needs content verification by the functionality-test agent.
- **no_data** — `option_quote_no_data.json` present.
- **error** — **no file matches.** No fixture named or evidently containing a provider-error-response shape was found by filename. **Flagged as likely MISSING pending content verification.**
- **scalar** — `option_quote_scalar_ok.json` present (conflated with ok, as above).
- **parallel-array** — `option_chain_list_sizes.json` is the most likely candidate (chain responses are the parallel-array case per §8.1) but this needs content verification.
- **missing-field** — **no file matches.** **Flagged as likely MISSING pending content verification.**

Two extra fixtures exist beyond the required set (`crossed`, `negative_size`) — useful for F-04/F-05 but not part of the required six.

**Preliminary finding against MSI-0:** at minimum two of the six required fixture categories (**error**, **missing-field**) have no obviously-matching file. This gates F-03 (provider adapter fixture handling) for those two categories specifically — the functionality-test agent must open each of the five files, confirm exactly which of the six required categories each one actually represents by content, and mark any category with no matching fixture as **BLOCKED — MSI-0 fixture missing**, per the task's explicit instruction ("If those fixtures do not exist, record that as a finding against MSI-0 and mark dependent tests BLOCKED").

## `run_meta.json` / run-history (§13)

- `msi_runtime.py` and the implementation record both claim "run-meta-v2 identity, MSI configuration hash/flags, in-progress/completion status and production-acceptance fields" were added to run metadata.
- **No run directory under `data/output/runs/` currently contains a run_meta.json matching this schema.** The newest run, `data/output/runs/20260830_071747/` (created 2026-08-30, macro `pinned_at_utc: 2026-08-30T06:17:52Z`), has a `run_meta.json` that is the **pre-existing macro-pinning schema** (`canonical_run_id`, `discovery_run_id`, `macro_source_path`, `macro_freshness_status`, etc.) — it contains **none** of the §13-required fields (`run_kind`, `run_status`, `pipeline_mode`, baseline commit hash, configuration hash, producer versions). This run's top-level contents (`canonical/`, `catalysts/`, `diagnostics/`, `discovery/`, `packages/`, `regime_screener/`, `vanguard/`) show it never reached Options Intelligence, Morning Gate, Market Structure, Lab or Interpreter stages — it predates the MSI code (MSI files have mtimes from 13:xx–14:xx on 2026-08-30; this run's macro pin is from 06:17). **This run is not an MSI-active run and is not evidence for Section 7.**
- No run directory anywhere under `data/output/runs/` (or `data/archive/`) contains the §26-specified run-scoped artefact layout (`canonical/` in the new sense, `market_structure/`, `intelligence_lab/`, `interpreter/bundles/`, `interpreter/assessments.jsonl`, `interpreter/handoff_manifest.json`, `screens/`, `diagnostics/msi_reconciliation.json`).
- **Conclusion: `run_meta.json` per §13 is not yet being written by any run that has actually executed** (the code to write it may exist per the implementation record's claim, but no executed run demonstrates it). This is UNVALIDATED, not FAILED — the capability may exist in code but has no run-artefact evidence. The functionality/regression agents should check the code path directly (does `intelligent_orchestrator.py` call a run-meta-v2 writer function on the code path) versus rely on a run artefact, and label accordingly.

## Latest run directories

Most recent five (by mtime): `20260830_071747` (pre-MSI, see above), `20260829_221022`, `20260829_213124`, `TEST_OLM_REGRESSION_20260829` (a prior test artefact from the OLM pack, not production), `20260824_100301`. **None qualify as an MSI-active production run.** Section 7 (run-artefact verification) is therefore **entirely BLOCKED — no run produced under the MSI switches exists.** Per the task's explicit instruction ("Only if data/output/runs/ contains a run produced under the MSI switches"), Section 7 is not performed as a positive test; `07_run_artefacts.md` will record this precondition failure and mark every §20 criterion in that section BLOCKED pending a fresh MSI-active run — the same live evening→morning cycle already known from the prior OLM-fix pack to require explicit user authorisation and real provider cost.

## `tools/msi_reconcile.py`

**Exists** (`tools/msi_reconcile.py`, 4,459 bytes, modified 2026-08-30 13:29). Content/behavioural verification (does it actually return non-zero on mismatch, is it actually invoked by the finalizer) is deferred to the Flow-test agent (W-13).

## Test runtime

The implementation record specifies `.codex_python313_runtime/python.exe` with `venv/Lib/site-packages` as the test runtime used for its own self-reported regression counts, **not** the `venv/Scripts/python.exe` used throughout every prior OLM audit pack in this repository. Both interpreters exist on disk. **All MSI test agents in this pack must use `.codex_python313_runtime/python.exe` for MSI-related test execution**, to match the environment the implementation was actually built and tested against, and must record which interpreter was used for every executed test as part of its evidence.

## Gating summary for downstream test agents

| Precondition | Status | Downstream impact |
|---|---|---|
| MSI-0 baseline commit recorded and matches HEAD | CONFIRMED | No gating |
| MSI-0 module-map entry-point functions recorded | **NOT RECORDED** | Every test must independently cite file:function:line; no authoritative cross-check exists |
| `canonical_data/market_observation_service.py` (named new module) | **MISSING** (responsibility apparently relocated) | Any test written strictly against this filename is BLOCKED; agents must locate the actual responsible module themselves and note the naming deviation |
| `market_structure/contracts.py` (named new module) | **MISSING** | Same as above for Market Structure data-contract definitions — agents must check whether contracts live in `service.py`/`profile.py` instead |
| Feature switches | 7/8 ON, `MSI_SCREEN_ADAPTER` OFF | Screenshot-lane tests (W-17) → NOT_ACTIVATED; all others proceed |
| §16.1 provider fixtures | 5 files present; **error** and **missing-field** categories not obviously matched by filename | F-03 (and any dependent test) for those two categories is BLOCKED pending content verification; functionality agent must open every fixture file and confirm |
| `run_meta.json` §13 schema | Not demonstrated by any executed run | UNVALIDATED (code may exist, no run evidence) — regression/flow agents check code path directly, do not claim VERIFIED from absence of contrary evidence |
| MSI-active run for Section 7 | **None exists** | Section 7 entirely BLOCKED |
| `tools/msi_reconcile.py` | EXISTS | Behavioural test proceeds (W-13) |
| Test runtime | `.codex_python313_runtime/python.exe` confirmed present | All agents must use this interpreter |
