# AVS-OPS-002 — 03. Commit plan (awaiting ACK sign-off)

**Branch:** `avs-fix-001` · **From:** `00baa2b` · **Remote:** exists, nothing will be pushed
**Nothing has been staged or committed.** This document is the proposal only.

---

## Headline numbers

| | Count |
|---|---|
| Paths in `git status --porcelain=v1 -uall` | 4071 |
| **Files to commit** | **494** (297 added/modified + 197 deletions) |
| Files excluded | 3579 |
| — vendored / run artefacts | 3577 |
| — `UNKNOWN`, needs your decision | 2 |
| Commits proposed | 21 |
| Secret-risk findings | 0 confirmed, 2 items for your awareness (§ Secrets) |
| Test tree | 1726 tests collect cleanly, 0 collection errors |

---

## Secrets scan result

Rule 4 scan run over all 297 candidate add/modify paths, for `sk-` prefixes,
`ANTHROPIC_API_KEY` / `MARKETDATA_API_KEY` / `POLYGON_API_KEY` literals,
`*_key|token|secret|password|credential = "<20+ chars>"` assignments, and 40+
character base64 blobs.

**No credential value was found.** Every provider key is read through
`os.environ.get(...)` at call time. Two items are reported for awareness, not as
blockers, and no value is reproduced here or in any commit message:

1. `worker3/adapters/anthropic_http.py` records a `credential_fingerprint` — the
   first 8 hex characters of the SHA-256 of the key. It is deliberately
   non-reversible and was added by AVS-FIX-001 W4.2 to diagnose the 6 Sep
   two-credential incident. The same 8-character fingerprint appears in the
   Worker 3 canary evidence JSONs in group `G20`. **Your call** whether an
   8-character digest prefix belongs in the repository; I recommend yes.
2. `config/anthropic_runtime.json` holds one field, `workspace_id`. Its own
   companion document `config/ANTHROPIC_RUNTIME.md` states this is the
   installation's **non-secret** workspace ID. It is an account identifier, not
   a credential. **Your call**; I recommend committing it.

The long base64-shaped strings flagged in the DOI phase manifests are SHA-256
content hashes, not secrets.

---

## Two things you should decide before I execute

### 1. Attribution lines — the prompt and this session disagree

Section 7 of the prompt requires these exact two lines on every commit:

```
Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01DyN6iHjTxkW7cvHyBmGwnU
```

This session is **Claude Opus 5, not Fable 5.1**, and its own attribution
configuration specifies `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`.
The session URL in the prompt belongs to a different session than this one.

Stamping `Fable 5.1` would put a false model attribution into permanent history
on 21 commits. I have not chosen for you. Reply with one of:

- **`attrib: prompt`** — use the two lines exactly as written in the prompt.
- **`attrib: opus`** — use `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`
  and drop the `Claude-Session` line (I cannot verify this session's URL).
- **`attrib: opus+session <url>`** — Opus 5 line plus a session URL you supply.

Default if you just say `go`: **`attrib: opus`**, because an accurate
attribution is the safer thing to make permanent.

### 2. The two `UNKNOWN` modules

Section 2 of the prompt says an untracked module that nothing imports and has no
test is an `UNKNOWN` candidate and must not enter a code commit without saying
so. Two qualify:

| Path | Size | Evidence |
|---|---|---|
| `worker3/adapters/claude_refresh.py` | 3.6 KB | Referenced by no `.py`, `.js`, `.html` or `.md` in the tree. No test. Docstring: "Refresh adapter with actual prior evidence. Inherits the offline transport port." |
| `worker3/integration/provider_runner.py` | 3.4 KB | Referenced by nothing. No test. Docstring: "Explicit one-job provider runner guarded by a disabled release contract." — reads like a manual CLI entry point, which would explain having no importer. |

Both sit inside the otherwise coherent new `worker3/` package. **I recommend
including them in `G15` and naming them in that commit's body**, because an
uncommitted file is unrecoverable and a committed dead module is not. They are
currently marked `include=N` in `02_inventory.csv`. Reply `unknown: include` or
`unknown: exclude`.

---

## Exclusions (3577 artefact files)

| Prefix | Files | Bytes | Reason |
|---|---|---|---|
| `audit/outcome_comparison/20260909_071646/node_modules/` | 3315 | ~48 MB | Vendored JavaScript dependency tree (`.ts`, `.js`, `.map`, `.wasm`, `.bcmap`, `.pfb`, font binaries). Rule 5 excludes `node_modules`. |
| `audit/doi/AVS-TST-DOI-001/scratch/` | 253 | ~2.4 MB | Run-output JSON from the DOI tester engagement. Regenerable scratch. |
| `audit/outcome_comparison/20260909_071646/` (rest) | 9 | ~1.1 MB | `.artifact_build/` preview PNGs, one `.xlsx`, one `.ndjson`. Rule 5 excludes `*.xlsx` under output paths. |

No tracked artefact, database, cache or backup file is modified, so nothing has
to be left deliberately unstaged under rule 5. No `.bak` file exists in the tree
at all, contrary to the prompt's "around 95 `.bak` copies" hint.

---

## The commits, in order

Order rationale: `.gitignore` first (Section 3); then the standalone cleanup;
then code groups in dependency order, because several groups call into code
introduced by an earlier one (`G09` calls `configured_workspace_id()` from
`G08`; `G11` imports `G10`; `G13` wires `G11`; `G14` renders both `G13` and
`G15`); audit documents last, as they carry no code risk.

---

### G01 · `chore(git): ignore vendored node_modules and audit run scratch`

**Files (1):** `.gitignore`

The only file this operation modifies. Section 3 of the prompt explicitly
permits a `.gitignore` commit. Three rules appended in the file's existing
annotated house style, each verified to match 0 tracked paths:

```
node_modules/
/audit/outcome_comparison/
/audit/doi/AVS-TST-DOI-001/scratch/
```

**Body:** names the three gaps found in §1.7 of `01_state.md`, the file counts
they suppress (3315 / 9 / 253), and records that each pattern was checked
against `git ls-files` before being added.

**If you would rather I not touch `.gitignore` at all, say `skip G01`.** The
other 20 commits do not depend on it; I never use `git add -A` or `git add .`,
so the artefacts cannot be swept in either way. The cost of skipping is that
`git status` keeps showing 3577 untracked files.

---

### G02 · `chore(repo): drop archived, attic and backup source snapshots`

**Files (197, all deletions).** Every one is dead-storage material already
removed from the working tree; none is live source:

| Tree | Files |
|---|---|
| `_cleanup_holding/` | 154 |
| `_attic/` | 23 |
| `backups/database_remediation_20260803_phase0/` | 6 |
| `vanguard/execution/strategies/Archive/` | 5 |
| `pipeline_interpreter/` (Archive + two `old2505` copies) | 5 |
| `Archive/` | 3 |
| `decommissioned/morning_validator_legacy_20260526/` | 1 |

**Body:** states that every path is archive, attic or backup material; that the
content stays retrievable at `00baa2b` and at tag `avs-baseline-20260906`; and
that no live module was removed.

**Flag:** this is the one group that records removals rather than additions.
Rule 1 forbids *me* deleting source; these deletions already existed in the
working tree when I arrived, and recording them loses nothing, since git keeps
the blobs. **Say `skip G02` if you would rather leave them uncommitted.**

---

### G03 · `fix(msi): quote age is evidence metadata, not thesis authority`

**Files (7):**
`contracts/quote_change_evidence.py`, `contracts/lab_evidence_overlay.py`,
`contracts/interpreter_handoff_materializer.py`, `tools/msi_production_readiness.py`,
`tests/test_msi_quote_and_size_lineage.py`, `tests/test_msi_interpreter_handoff.py`,
`tests/test_msi_handoff_materializer.py`

Market Structure Interpreter work. Contract comparability and quote recency were
one conflated fact; an aged quote could mark a swing thesis stale and demand a
refresh. The diff separates them: a new `quote_age_affects_thesis` overlay field,
`execution_quote_status` as metadata (`PRIOR_SESSION_EVIDENCE`,
`QUOTE_EVIDENCE_METADATA_ONLY`), and a `VALIDATION_QUOTE_UNAVAILABLE` warning
instead of a failure.

**Mixed-file flag:** `contracts/interpreter_handoff_materializer.py` also adds
seven `doi_*` advisory placeholder columns that belong to `G13`. The two
concerns interleave in the same hunks and cannot be split without hand surgery
on the diff, which rule 1 forbids. The commit body will say so.

Implements: `AVS-SD-MSI-001`.

---

### G04 · `fix(eil): EIL is advisory telemetry and never a governing gate`

**Files (6):**
`contracts/handoff_contract.py`, `trade_book_builder.py`, `position_sizing_engine.py`,
`tests/test_handoff_contract.py`, `tests/test_big_bang_phase_6_7.py`,
`tests/test_eil_advisory_authority.py` *(new)*

Completes the EIL demotion begun in `c72f312` (W1.2). `EIL_BLOCKED` stops being
a sovereign gate and becomes an `EIL_ADVISORY_BLOCKED` warning retained for human
review; `trade_book_builder` now fails a missing `eil_advisory_only` disclosure
**to** advisory rather than re-arming EIL as a gate; the retired position sizing
engine's EIL hook returns a fixed neutral 1.0 so a replayed historical verdict
cannot re-acquire capital authority.

Implements: `AVS-IMP-FIX-001` W1.2 follow-through, `MVP-001` kill criterion 6.

---

### G05 · `fix(identity): selected contract strike, expiry and DTE are atomic`

**Files (6):**
`canonical_data/session_clock.py`, `contracts/selected_contract_economics.py`,
`morning_gate.py`, `tests/test_selected_contract_economics.py`,
`tests/test_morning_gate_contract_repair.py`,
`tests/test_avs_fix_001_w34_timevalue_monetisability.py`

Adds `advance_xnys_sessions()` to the session clock and makes contract identity
one indivisible object, so a repaired OCC symbol can never be combined with the
strike, expiry or DTE left over from a prior contract. `morning_gate` re-derives
strike, expiry and DTE from the repaired symbol and rebuilds `trade_idea_id`
from them.

Implements: `AVS-MVP-001` §4, continuing `d52461e` (W1.5).

---

### G06 · `feat(dte): governed DTE from per-horizon planned hold sessions`

**Files (2):** `scripts/avshunter_options_intelligence.py`,
`tests/test_governed_dte_policy_alignment.py` *(new)*

Introduces `HORIZON_PLANNED_HOLD_SESSIONS` (`1_5d`→5, `6_10d`→10, `11_20d`→20)
and `DTE_SELECTION_POLICY_VERSION = "governed-dte-alignment-v1"`, so DTE
selection is derived from the governed horizon instead of an independent rule.

---

### G07 · `feat(macro): macro bounded context with local dealer-gamma exposure`

**Files (9):**
`macro_domain/__init__.py` *(new)*, `macro_domain/gamma_exposure.py` *(new)*,
`canonical_data/gamma_exposure_store.py` *(new)*, `canonical_data/contracts.py`,
`contracts/macro_file_contract.py` *(new)*, `scripts/build_local_gex.py` *(new)*,
`scripts/refresh_macro_context.py` *(new)*, `docs/MACRO_DOMAIN.md` *(new)*,
`tests/test_macro_domain_enhancements.py` *(new)*

A new `macro_domain` package holding deterministic dealer-gamma calculations over
completed option sessions, its infrastructure adapter in `canonical_data`, a
shared macro file contract, a `GAMMA_EXPOSURE` canonical dataset registration,
and two CLI entry points.

Implements: `docs/MACRO_DOMAIN.md` (committed in the same group).

---

### G08 · `feat(runtime): pin the Anthropic workspace for unattended runs`

**Files (4):**
`anthropic_runtime_config.py` *(new)*, `config/anthropic_runtime.json` *(new)*,
`config/ANTHROPIC_RUNTIME.md` *(new)*, `tests/test_anthropic_runtime_config.py` *(new)*

Persists the installation's non-secret workspace ID so the macro builder and the
Worker 3 clients resolve one workspace without an interactive prompt. Ordered
before `G09` because `build_macro_json.py` calls `configured_workspace_id()` from
this module.

See §Secrets item 2 — `config/anthropic_runtime.json` contains the workspace ID
and nothing else.

---

### G09 · `feat(mi): advisory US Money Index sidecar through the macro packet`

**Files (12):**
`build_macro_json.py`, `macro_domain/us_money_index.py` *(new)*,
`contracts/us_money_index_contract.py` *(new)*,
`scripts/validate_us_money_index.py` *(new)*, `contracts/interpreter_macro_context.py`,
`canonical_data/decision_outcome_ledger.py`, `scripts/macro_quant_packet.py`,
`scripts/inject_macro_into_packages.py`,
`pipeline_interpreter/prepare_interpreter_session.py`,
`tests/test_interpreter_macro_advisory_handoff.py`,
`tests/test_build_macro_json_anthropic_workspace.py` *(new)*,
`tests/test_build_macro_json_response_repair.py` *(new)*

The advisory US Money Index sidecar end to end: contract and normaliser, a
validation CLI, propagation through the macro quant packet and interpreter macro
context, and seven `usmi_*` columns on the decision outcome ledger.

**Mixed-file flag:** `build_macro_json.py` is a three-way mix — 37 added lines
are USMI, 18 are provider response repair, 12 are the `G08` workspace call. Its
two new tests ride with it for that reason. The commit body will say that the
response-repair change is a distinct concern that could not be separated.

Implements: `AVS-SD-MI-001` (`audit/pipeline_map/AVS-SD-MI-001_US_MONEY_INDEX_SIDECAR_20260906.md`, committed in `G19`).

---

### G-DDD · `test(ddd): completed-profile exclusions survive the receipt adapter`

**Files (1):** `tests/test_dynamic_session_phase6.py`

One added regression: excluded partial sessions must survive the legacy-to-DDD
receipt adapter. Its own commit because it is the only file in the tree carrying
dynamic-session-dispatcher work, and folding it into a DOI commit would mislabel
it.

---

### G10 · `feat(doi-1..10): pure Dynamic Options Intelligence domain layer`

**Files (12):**
`domain/__init__.py`, `domain/dynamic_options_intelligence.py` *(new)*,
`domain/contract_family_generation.py` *(new)*,
`domain/deterministic_option_valuation.py` *(new)*,
`domain/dynamic_options_lifecycle.py` *(new)*, `domain/dynamic_options_outcomes.py` *(new)*,
`domain/dynamic_options_probability.py` *(new)*, `domain/dynamic_options_projection.py` *(new)*,
`domain/dynamic_options_ranking.py` *(new)*, `contracts/dynamic_options_policy.py` *(new)*,
`config/doi_runtime.json` *(new)*, `docs/AVS-SD-DOI-001_DYNAMIC_OPTIONS_INTELLIGENCE.md` *(new)*

The IO-free DOI domain: contract-entry state vocabulary, append-only
`ContractFamily` generation, deterministic valuation, lifecycle and hysteresis
rules, outcome labelling, probability-model contracts, the trader-facing
projection contract, and ranking policy — plus the governed authority policy and
the design document they implement.

This is the `domain/` package flagged as unauthorised under QT-D11. It is now
documented and committed rather than left in the working tree.

Implements: `AVS-SD-DOI-001`, phases DOI-1 through DOI-10.

---

### G11 · `feat(doi): canonical DOI application services and persistence`

**Files (9, all new):** `canonical_data/dynamic_options_bridge.py`,
`dynamic_options_family.py`, `dynamic_options_lifecycle.py`,
`dynamic_options_outcomes.py`, `dynamic_options_probability.py`,
`dynamic_options_production.py`, `dynamic_options_projection.py`,
`dynamic_options_ranking.py`, `dynamic_options_valuation.py`

The application services over the `G10` domain: the governed canonical/Phantom
observation bridge (DOI-3), thesis-conditioned family generation (DOI-4),
deterministic scenarios (DOI-5), lifecycle re-ranking (DOI-6), point-in-time
outcome labels (DOI-7), chronological probability modelling (DOI-8), append-only
ranking persistence (DOI-9), read-only projection (DOI-10) and production
integration (DOI-11).

---

### G12 · `test(doi): DOI regression pack and phase-11 readiness assessor`

**Files (13, all new):** 12 files matching `tests/test_dynamic_options_*.py`,
`tests/test_doi10_projection_integration.py`,
`tests/test_doi11_production_integration.py`,
`tests/test_doi_phase_quality_assurance.py`, and
`tools/doi11_production_readiness.py`

The DOI regression pack, including the non-discard policy test and an AST-level
phase quality-assurance check, plus the read-only DOI-11 production acceptance
assessor.

---

### G13 · `feat(doi-11): wire DOI into the evening orchestrator and EOD book`

**Files (9):**
`intelligent_orchestrator.py`, `eod_candidate_engine.py`,
`execution_intelligence_runner.py`, `contracts/lab_control.py`,
`contracts/interpreter_handoff.py`, `canonical_data/__init__.py`,
`canonical_data/option_liquidity_lifecycle.py`,
`pipeline_interpreter/pipeline_interpreter_commands.py`,
`tests/test_eod_options_research_handoff.py`

DOI wired into production after horizon propagation: orchestrator stage,
EOD candidate handoff, execution runner, Lab control surface, interpreter
handoff columns, and the `CONTRACT_FAMILY` / DOI schema extensions on the option
lifecycle store (1320 changed lines, the largest single file in this operation).

**Mixed-file flag:** `intelligent_orchestrator.py` carries 17 DOI lines and 3
dynamic-session-dispatcher receipt lines; the latter belong with `G-DDD`.

---

### G15 · `feat(w3): isolated Worker 3 provider foundation, offline by default`

**Files (39, all new**, or 41 if you answer `unknown: include`**):**
36 modules under `worker3/`, `contracts/worker3_integration_v1.json`,
`contracts/worker3_provider_release_v1.json`, `docs/AVS-W3-SD-001.md`,
`docs/AVS-W3-SD-002.md`, `docs/AVS-W3-SD-003.md`

**The prompt's workstream list has no entry for this.** Worker 3 is an entire
untracked package: pure domain and assessment contracts, an opt-in bounded HTTPS
transport with no retries or credential logging, SQLite durable job state,
offline-tested Claude adapters, a v2 bound-output grammar, deterministic
narrative and semantic lint, and a read-only AVSHUNTER integration boundary.
None of it imports the pipeline; none installs a network transport
automatically.

Partly committed already — `5683028` (W4.2) touched the transport receipts —
which is why the package is a mix of tracked and untracked files.

**Decision point:** `worker3/adapters/claude_refresh.py` and
`worker3/integration/provider_runner.py` are the two `UNKNOWN` modules above.
They are excluded as the plan stands; I recommend including them and naming them
in this commit's body.

Implements: `AVS-W3-SD-001`, `-002`, `-003` (committed in this group).

---

### G16 · `test(w3): Worker 3 regression pack`

**Files (10, all new):** `tests/test_worker3_activation.py`,
`test_worker3_avshunter_source_bridge.py`, `test_worker3_bound_output.py`,
`test_worker3_browser_launch.py`, `test_worker3_coordinator.py`,
`test_worker3_current_canary.py`, `test_worker3_detailed_reports.py`,
`test_worker3_evidence_coverage.py`, `test_worker3_response_guidance.py`,
`test_worker3_timeout_recovery.py`

Every one is offline: none waits on or calls a provider.

---

### G14 · `feat(lab): DOI projection, Worker 3 controls and USMI panel`

**Files (3):** `intelligence-lab/intelligence_lab.py`,
`intelligence-lab/static/index.html`,
`intelligence-lab/static/worker3-controls.js` *(new)*

Placed after `G13` and `G15` because it renders both.

**This is the one commit that genuinely breaks "one workstream per commit", and
I want you to see it before I run it.** The two Lab files interleave three
workstreams in the same hunks:

| File | US Money Index | Worker 3 | DOI |
|---|---|---|---|
| `intelligence_lab.py` | 14 added lines | 8 | 3 |
| `static/index.html` | — | 6 | 35 |

Splitting them would require hand-editing hunks, which rule 1 forbids. The
alternatives are one honest mixed commit or three commits each containing a
partial file, which git cannot do without `add -p`. **I propose the single
commit, with a body that names all three workstreams and says why they are
together.** Reply `G14: split` if you would rather I stop and ask you to
separate the change yourself.

---

### G17 · `feat(evidence): full-book resolved opportunity evidence`

**Files (1):** `pipeline_interpreter/evidence_resolver.py`

Adds `ResolvedOpportunityEvidence`, a frozen non-executable full-book evidence
record for review and trajectory analysis, and a dual import path so the module
works both as a package member and as a direct script.

---

### G18 · `fix(discovery): resolve os from module scope in main()`

**Files (2):** `avshunter_discovery_ULTIMATE.py`,
`tests/test_discovery_scope_and_macro_timestamp.py` *(new)*

Removes a shadowing `import os` inside `main()` that made the module-level
import unreachable from that scope. The new test asserts the resolution using
`symtable`, so the shadow cannot come back.

---

### G19 · `docs(audit): DOI phase records, tester engagement and AVS-OPS-002`

**Files (76):** `audit/doi/` (64, excluding `scratch/`),
`audit/ops/AVS-OPS-002/` (this operation's own outputs),
`audit/macro_domain_smoke_20260906/` (4),
`audit/pipeline_map/AVS-SD-MI-001_*.md` and `AVS-THS-002_*.md`,
`audit/post_run_20260907/AVSHUNTER_POST_RUN_AUDIT_20260907.md`,
`audit/repository_cleanup/REPOSITORY_CLEANUP_MANIFEST_20260910.md`,
`audit/worker3_assessment_20260907/WORKER3_BUILD_ASSESSMENT_20260907.md`

545 KB. DOI phase implementation records and release manifests for phases 1–11,
the `AVS-TST-DOI-001` tester engagement (comprehension, expectations, inventory,
defects, claims, verdict, and the T1–T12 test notes with their 17 probe
scripts), and the loose audit documents above.

Includes this operation's own `01_state.md`, `02_inventory.csv`,
`03_commit_plan.md`, `_build_inventory.py`, and the `04`/`05`/`06` outputs
produced in Sections 4 and 5.

---

### G20 · `docs(audit): Worker 3 current-state canary evidence`

**Files (76):** everything under `audit/worker3_current_state_canary/`

**3.9 MB — the largest group, and its own commit so you can drop it alone.**
63 JSON evidence files and 13 markdown reports from seven canary attempts
against the live provider, including two ~870 KB offline structured-output
captures and four ~230 KB preservation snapshots.

**Judgment call I am flagging rather than making silently:** the prompt's
workstream list says `AUDIT` is "anything under `audit\`", which would include
this. Rule 5 says do not commit run artefacts. These files are both — provider
run output kept as audit evidence. They carry the 8-character credential
fingerprint described in §Secrets item 1. I lean towards committing them,
because they are the only record of how Worker 3 behaved against the real
provider, and `G20` is separable if you disagree. Reply `skip G20` to exclude.

---

## After the commits (Section 4, not yet executed)

1. `git status --porcelain` re-run; everything remaining written to
   `05_exclusions.md` with a category.
2. Annotated tag `avs-committed-20260911` on the final commit, message listing
   the workstreams: `CLEANUP`, `MSI-QUOTE`, `EIL`, `IDENTITY`, `DTE`,
   `MACRO-GEX`, `ANTHROPIC-RT`, `MI`, `DDD`, `DOI` (domain, canonical, tests,
   wiring), `W3`, `LAB-UI`, `EVIDENCE`, `HYGIENE`, `AUDIT`.
3. **No push.** The remote exists, but Section 4 requires your explicit
   instruction and I do not have it.

---

## Confidence in the workstream classifications

| Workstream | Confidence | Basis |
|---|---|---|
| `DOI-domain`, `DOI-canonical`, `DOI-tests` | High | Every module's docstring names its DOI phase number |
| `W3` | High | Self-contained package, every module docstring is explicit |
| `CLEANUP` (G02) | High | All 197 paths are under archive/attic/backup roots |
| `EIL`, `IDENTITY`, `MSI-QUOTE` | High | Read from the diffs, including the added comments |
| `MI`, `MACRO-GEX`, `ANTHROPIC-RT` | High | Docstrings plus `usmi_*` / `gamma_exposure` symbol evidence |
| `DTE`, `EVIDENCE`, `HYGIENE`, `DDD` | Medium | Single-purpose diffs, but each is one or two files with no corroborating design document in the tree |
| `DOI-wiring` (G13) | Medium | Correct as a group, but `intelligent_orchestrator.py` provably mixes in DDD work |
| `LAB-UI` (G14) | **Guess** | Three workstreams in two files; the grouping is a packaging decision, not a classification I can defend |
| `AUDIT`, `AUDIT-W3-EVIDENCE` | High | Location-based |

---

## What I need from you

Reply `go` to run the plan with the defaults (`attrib: opus`, `unknown:
exclude`, all groups including `G01`, `G02`, `G14` as one commit, and `G20`), or
amend with any of: `attrib: prompt` · `attrib: opus+session <url>` ·
`unknown: include` · `skip G01` · `skip G02` · `skip G20` · `G14: split`.
