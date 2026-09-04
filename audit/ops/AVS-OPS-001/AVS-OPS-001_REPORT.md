# AVS-OPS-001 — Root tidy and baseline commit: report

**Executed:** 2026-09-04
**Repository:** `C:\Users\ACKVerissimo\AVSHUNTER-Intelligence`, branch `master`
**Starting HEAD:** `5d886f07c1d290f25600e2e7e62ae77aad85476a` (2026-08-20, "Pre-remediation snapshot: full working tree")
**Test runtime:** `venv\Scripts\python.exe` 3.13.14, pytest 9.1.1 (pytest is not installed under `C:\Python314`; analysis scripts used `C:\Python314\python.exe` as specified)
**Result:** all three commits made; **post-tidy verification matrix is identical to the pre-tidy matrix**; no revert required.

---

## 1. Headline

| | |
|---|---|
| Commit 1 (baseline as-is) | **`e183d60a1e843bf369a8a4fd81b38a0459e78c7f`** |
| Commit 2 (moves to `_attic/`) | **`4c33c1cac2e97924dc9956faf7172127deeb037e`** |
| Commit 3 (`.gitignore` + deliverables) | tagged **`post-tidy-20260904`**; SHA in `05_commit3.txt` (a commit cannot contain its own hash, so it is recorded immediately after the commit) |
| Tag before | **`pre-tidy-20260904`** → commit 1 |
| Tag after | **`post-tidy-20260904`** → commit 3 |
| Files moved | **34** (13 Tier A + 21 Tier B; 23 `.py`, 11 non-`.py`) |
| Files deleted | **1** (`.env.txt` — the single permitted deletion) |
| Files deferred | **184 rows** in `deferred.csv` (96 Tier A, 17 Tier B, 71 Tier C) |
| Commit 2 diff | **34 files changed, 0 insertions(+), 0 deletions(-)** — 34 `R100` renames, nothing else |
| Matrix pre vs post | **IDENTICAL** — 964 tests, 958 passed, 5 failed, 1 skipped, both runs |
| Reachability diff (item 6) | **EMPTY** — 200 reachable modules before and after |

Root-level tracked files fell **169 → 136**; root-level tracked `.py` fell **107 → 84**, exactly the 23 `.py` files among the 34 movers.

---

## 2. Verification matrix — pre vs post

Both runs executed every test file in its own process (130 files: 125 `tests\test_*.py`, 4 `tests\qa\`, 1 `tests\rca\`), per the Phase 2 closure note that single-process collection is invalid because of `vanguard`/`scripts` shadowing. XMLs: `01_pre\pytest_xml\` and `06_post\pytest_xml\`.

| # | Item | Pre-tidy | Post-tidy | Verdict |
|---|---|---|---|---|
| 1 | `compileall` (excl. `_attic`, `backups`, `venv`, `.codex_*`) | rc=0, **0 error lines** | rc=0, **0 error lines** | **MATCH** |
| 2 | Entry-point import smoke, `AVSHUNTER_*` unset, subprocess | 4/4 OK | 4/4 OK | **MATCH** |
| 3 | `--evening --cds-startup-self-test` | **PASS** | **PASS** | **MATCH** |
| 4/5 | pytest, 130 files isolated | 964 tests / 958 passed / **5 failed** / 0 errors / 1 skipped | 964 / 958 / **5** / 0 / 1 | **MATCH** |
| — | per-file records differing | — | **0 of 130** | **MATCH** |
| — | failing files | `test_olm_execution_authority`: 5 | `test_olm_execution_authority`: 5 | **MATCH** |
| 6 | Reachability diff from the 4 entry points | 200 reachable | 200 reachable | **EMPTY DIFF — PASS** |

The comparison was made per test file on `(tests, passed, failures, errors, skipped)`, not only on totals: **0 of 130 records differ**, and the file sets are equal. Machine record: `06_post\matrix_comparison.txt`.

**Pass condition met.** Identical pass/fail/skip counts including identical `PRE_EXISTING` failures — no new ones, no fewer — and an empty item-6 diff.

### 2.1 `PRE_EXISTING` failure

`tests\test_olm_execution_authority.py` — 27 tests, 22 passed, **5 failures**, present in the pre-tidy run before any file was moved:

```
test_full_morning_transition_matrix[EXECUTABLE_NOW-BUY_NOW]
test_full_morning_transition_matrix[GAP_CONFIRMATION_WITH_RUNWAY-BUY_NOW]
test_corrected_v2_lifecycle_contract_is_supported_by_execution_guard
test_existing_valid_action_and_advisory_monetisability_remain_compatible
test_direct_legacy_caller_remains_compatible_but_production_batch_requires_olm
```

All five are the same assertion: `AssertionError: assert 'CONTRACT_REPAIR' == 'BUY_NOW'`. This is a behavioural expectation about the morning execution action; it is unrelated to file location and reproduced identically after the move.

**One thing needs ACK's attention (§6.1): these five are NOT in the recorded 09-03 baseline.** `audit\pipeline_map\dynamic_phase8_full_regression_20260903.xml` records **900 tests, 0 failures, 1 skipped**, with all 27 `olm_execution_authority` cases passing. So they regressed between 2026-09-03 and now. The tidy did not cause them — they were present before the first `git mv` — and per §2.4 of the prompt the tidy is not allowed to fix them.

### 2.2 Deviation from the prompt's expected counts

§6 item 5 expected "877 top-level passed, 1 skipped" and item 4 expected "165 passed / 0 failed". Measured: **964 tests / 958 passed / 5 failed / 1 skipped** across 130 files. The difference is a mix of test-count growth since 09-03 and the five regressions above. Because the pass condition is *pre equals post*, not *post equals the 09-03 XML*, this does not block the tidy — but the 09-03 baseline is stale and should be re-recorded.

### 2.3 A pre-existing failure that did NOT reproduce

AVS-INV-001 recorded an f-string parse error in `scripts\run_vanguard_from_packages.py`. It does **not** occur here: `compileall` is clean and the static parser reported 0 parse errors across 680 files. The original error was a Python-version artefact (PEP 701 changed f-string parsing); under 3.13.14/3.14 the file parses. Nothing was edited to achieve this.

---

## 3. What moved

All 34 moved by `git mv` into `_attic\<original relative path>`, so history is preserved and each is reversible with a single `git mv` back. Every one passed **both** §1 reference checks: zero inbound edges in the reachability graph **and** zero `git grep` hits outside itself, `_attic\`, `backups\`, `audit\` and `Archive\`.

**Tier A — 13** (scratch, debris, retired launchers)

`check_pipeline.ps1`, `cmd_lines_debug.txt`, `comp9_spec.txt`, `docx_extracted.txt`, `hash_diag_20260421.json`, `hash_diag_fixed.json`, `menu_debug.txt`, `run_daily_orchestration.sh`, `setup_config.ps1`, `stability_run_template.ps1`, `stability_run_template0.ps1`, `bond_macro_intelligenceold0908.py`, `build_macro_jsonold0908.py`

**Tier B — 21** (retired root modules and step/section self-test scripts)

`step4_test.py`, `step5_graceful_test.py`, `step6_test.py`, `step6_test_v2.py`, `step6_test_v3.py`, `step7_test.py`, `step7_test_v2.py`, `step8_test.py`, `step9_verify.py`, `step10_test.py`, `section11_tests.py`, `section11_tests_v2.py`, `final_verify_c9.py`, `check7_prompt.py`, `lab_recon_selftest.py`, `macro_sector_propagation_test.py`, `polygon_options_validation.py`, `actuarial_hash_diagnostic.py`, `add_state_hash.py`, `resume_after_vanguard.py`, `audit_latest_run.py`

**Deleted — 1**

`.env.txt`. `git log --all -- .env.txt` returns **0 commits**, so the plaintext keys never entered git history and **no rotation is required on that ground**. Its contents were never read or printed. It was untracked and gitignored (`.gitignore:43 *.env.txt`), so `git rm` did not apply and it was unlinked; the deletion therefore does not appear in commit 2's diff. Independently confirmed by the tree snapshots: of 35 removals, 34 match an identical-`sha256` addition elsewhere (proving they were moves) and **exactly one — `.env.txt` — has no content match anywhere**, i.e. is a genuine deletion.

---

## 4. What did not move, and why

`deferred.csv` — 184 rows. The five classes that matter:

| Class | Count | Why |
|---|---|---|
| `UNTRACKED_GITIGNORED_NOT_A_GIT_OBJECT` | **46** | Already excluded by `.gitignore` (`*.bak` :35, `*.bak_*` :36, `*.lnk` :57, and `md_api_diagnostic.py` :139 on the secret-bearing list). They are **not git objects**, so `git mv` is impossible. See §6.2. |
| `PERMISSION_DENIED_UNREADABLE` | **37** | `tmp*/`, `pip-*/`, `avs_macro_check_*/` at root raise `PermissionError` on `listdir` for this account. Git cannot enumerate or move them either. Commit 3 hides them from `git status`. |
| `TIER_C_*` | **71** | Out of scope by §4 Tier C — list only, in `04_tier_c_candidates.csv`. 39 reachable/keep, 19 unreachable with no inbound, 13 unreachable but referenced. |
| `REFERENCED_*` | **20** | A real inbound graph edge or a real filename reference. |
| `ACK_DECISION_DEFER` / `GITIGNORED_BY_ACK_DECISION` / `DUPLICATE_BOTH_REACHABLE` / `EMPTY_DIR` | **10** | See §5. |

### 4.1 Deferrals the prompt specifically anticipated — all confirmed live

| File | Evidence | Prompt's warning |
|---|---|---|
| `position_sizing_engine.py` | 3 graph inbound (`execution_intelligence_runner.py`, `avshunter_ticker_probe.py`, `tests\test_pse_retired_authority.py`); 6 filename refs incl. `final_decision_engine.py` | *"execution_intelligence_runner was found importing PSE in the past; if referenced, defer"* — **it is** |
| `uat_audit_report.py` | 3 graph inbound: `intelligent_orchestrator.py`, `scripts\go_live_uat_audit_watch.py`, `scripts\qa_uat_regression_backstop.py` | *"if it is the live UAT generator, it stays"* — **it is**, and it is named in AVS-SD-003 W1-10 |
| `WyckoffEngine_3101_v2.py` | 5 graph inbound incl. `avshunter_discovery_ULTIMATE.py`, `orchestrator\wyckoff_engine.py` | *"expect these to be referenced; defer if so"* — **confirmed** |
| `wyckoff_crabel_precor_logic_v2.py` | 4 graph inbound | as above |
| `wyckoff_phase_validator.py` | 2 graph inbound incl. `tests\test_wyckoff_phase_validator.py` | as above |
| `catastrophe_gate.py` | 1 filename ref from `avshunter_trade_journal.py` | *"confirm the no-op does not import it"* — the orchestrator no-op does not, but the journal references it, so deferred |
| `execution_decision_engine.py` | 1 graph inbound: `intelligent_orchestrator.py` (7 filename refs) | retired EDE, but still referenced |
| `premarket_intelligence_ULTIMATE.py` | 1 graph inbound: `intelligent_orchestrator.py` | still wired |
| `kelly_sizer.py` | 2 graph inbound (`enhancement_integration.py`, `test_pipeline_regression.py`) | *"check carefully"* — referenced |
| `avshunter_options_intelligence.py` (root shim) | **12** graph inbound incl. `intelligent_orchestrator.py`, `scripts\diag_options.py` | *"check what imports the root shim"* — heavily imported, deferred |
| `avshunter_monetisation_policy.py` | 5 filename refs; duplicated in `scripts\` with both reachable | prompt says **do not move** — recorded `DUPLICATE_BOTH_REACHABLE` |
| `morning_validation.py` / `_engine.py` | 8 and 2 real filename refs incl. `eod_candidate_engine.py`, `convergence_engine.py` | "retired pair" — but still referenced |
| `run_shadow_automation.bat` | `watch_lab_exports.ps1:13` builds its path | *"the release baseline or self-tests may still reference the launcher names — if so, defer"* |

### 4.2 Substring artefacts — deferred anyway

The §1 check greps the bare module stem, which produces false positives. Four deferrals are artefacts of that (`grep_hits > 0` but `grep_hits_strict == 0`, where "strict" matches the filename *with* extension):

| File | Loose hits | Strict | The artefact |
|---|---|---|---|
| `run.py` | 2,191 | 0 | stem `run` matches every occurrence of "run" in the repo |
| `run_evening.bat` | 3 | 0 | `run_evening_workflow()` in `run_daily_orchestration.sh` |
| `run_premarket.bat` | 4 | 0 | `run_premarket_intelligence()` in `intelligent_orchestrator.py` |
| `Audit_AVSHUNTER_CompleteFixList_20260521.ps1` | 1 | 1 | genuine reference, not an artefact |

These were **left in place**: §1 says "If either check finds a reference, the file stays", and erring toward not moving is the safe direction. `03_candidates.csv` carries a `substring_artefact` column so ACK can clear them in a follow-up.

---

## 5. Decisions taken in session

Four points required a judgement that the prompt did not fully determine. Two were put to ACK.

**D1 — `requirements..txt` (ACK decision: leave both).** The double-dot file holds 6 real lines (`anthropic`, `python-dotenv`, `reportlab`, `Pillow`, `pandas`, `watchdog`); `requirements.txt` is 0 bytes; both are tracked. §4 Tier A says rename it. It was **not** renamed: the list is a partial set that cannot build the pipeline (no numpy, scipy, pyarrow, requests), so promoting it to `requirements.txt` would make the repository state a dependency set that does not work. Both are in `deferred.csv`.

**D2 — nested `AVSHUNTER-Intelligence\` (ACK decision: leave).** It contains exactly one file, `reports\vanguard_contract_audit.jsonl`, 143.5 MB, dated 2026-04-16, whose content is **unique** in the tree (the only other copy, `.\reports\vanguard_contract_audit.jsonl`, is 0 bytes). §4 requires a stop-and-report on a unique file, which was done. It is untracked and gitignored via the `reports/` rule, so `git mv` is impossible and any move would be invisible to commit 2 and not undone by `git revert`. Left in place.

**D3 — `.codex_*\` (ACK decision: gitignore, do not commit).** `.codex_python313_runtime` is a vendored CPython 3.13 runtime: 5,849 files, 103.6 MB, of which 2,532 would have been staged. §4 Tier A says move it to `_attic\`, but `_attic\` stays tracked, so that route puts ~40 MB of DLLs into permanent history and makes commit 3's `.codex_*/` rule inert. Instead `.codex_*/` was added to `.gitignore` before commit 1. The five directories remain on disk, invisible to git, recorded in `deferred.csv`. **This is a deliberate deviation from Tier A.**

**D4 — pre-commit-1 `.gitignore` edit (prompt-authorised, §3).** `backups\` and `data\` were **not** ignored. Verified before commit 1:

| Path | Scale | Action |
|---|---|---|
| `backups/` | 14,518 files, **35.0 GB**, 5 files >100 MB (up to 16.1 GB) | added |
| `data/canonical/` | 6,261 stageable files, **463 MB** of canonical dataset payloads | added |
| `.codex_*/` | 5,849 files, 103.6 MB | added (D3) |

`data/` was **not** excluded wholesale: that would defeat the existing `!data/universe/polygon_liquid_universe.csv` negation (git cannot re-include a file inside an excluded directory) and would misrepresent the 5 files already tracked under `data/`. Verified after the edit: the universe file is still not ignored, and `git add -An backups` stages 0. Commit 1 consequently staged **710 paths / 17.0 MB with zero files over 100 MB and no `.env`**.

---

## 6. Findings for ACK

### 6.1 Five test failures regressed between 2026-09-03 and now

Detailed in §2.1. Present before any move, identical after, so `PRE_EXISTING` for this tidy — but **not** present in `dynamic_phase8_full_regression_20260903.xml` (900 tests, 0 failures). Something changed the morning execution action from `BUY_NOW` to `CONTRACT_REPAIR` after the 09-03 regression was recorded. Worth a separate look; it is adjacent to the `CONTRACT_REPAIR_REQUIRED` behaviour that AVS-RCA-002 found on 162 of 256 Lab rows in run `20260904_004338`.

### 6.2 The bulk of Tier A cannot be tidied by `git mv` at all

46 root files — ~47 `.bak`/`.bak_*` backups of `intelligent_orchestrator.py`, `morning_thesis_validator.py`, `eod_candidate_engine.py` and others, 3 `.lnk` shortcuts, and `md_api_diagnostic.py` — are already excluded by `.gitignore` and are therefore not git objects. They are invisible to git today, so the *git-facing* tidy is already complete for them, but they still clutter the working directory. Moving them needs a plain filesystem `mv`, which would not appear in commit 2 and would not be undone by `git revert`. **Left in place, pending your instruction.** This is the same reasoning you applied to D2.

### 6.3 The prompt's `.gitignore` patterns would have over-matched

§5 lists `tmp*/` and `*old0908.py` unanchored. Applied literally they would have matched:

- `audit/olm_fix_test/tmp_runs/` and `audit/pipeline_map/AVS-TST-SD-002-001/tmp/` — which hold **tracked** test evidence XMLs and run manifests;
- `_attic/bond_macro_intelligenceold0908.py` and `_attic/build_macro_jsonold0908.py` — which must stay tracked for the moves to remain visible and reversible.

They were anchored to the repository root instead (`/tmp*/`, `/pip-*/`, `/avs_macro_check_*/`, `/*old0908.py`). Verified: each anchored pattern matches **0 tracked paths**, and `_attic/` is not ignored.

### 6.4 `.git` was almost empty before this

Despite the 2026-08-20 commit titled "Pre-remediation snapshot: full working tree", `.git` was **5 MB** and only 9 files under `backups/` and 5 under `data/` were tracked. Commit 1 is the first real baseline. `git diff` reported 590 additions among the 710 paths.

### 6.5 `audit/usage_graph.json` did not exist

§2.3 expects it. The nearest artefact is `audit\AVS-INV-001_usage_graph.json` (2026-09-01), which predates the AVS-SD-002 Phase 0–8 build of 09-03 and so does not describe the tree being tidied. A fresh graph was generated by **static parsing only** — `ast.parse` plus `.py` string-literal references to catch subprocess invocation; no target module is ever imported — and saved as `usage_graph_20260904.json` (680 nodes, 1,474 edges, 200 reachable, 31 entry points, 0 parse errors). The post-move graph is `usage_graph_after_20260904.json` (665 nodes, 200 reachable).

---

## 7. Reversibility

- Commit 2 is **34 `R100` renames and nothing else** — 0 insertions, 0 deletions. `git revert 4c33c1c` restores every path.
- `_attic/` is deliberately **not** in `.gitignore`, so every move stays visible and each is one `git mv` from being undone.
- `pre-tidy-20260904` marks the exact tree before the first move.
- `.gitignore` was backed up to `_gitignore_before_commit1.bak` before the first edit.
- The one irreversible act is the `.env.txt` unlink, which the prompt explicitly directs and which git never held.

---

## 8. Deliverables

```
audit\ops\AVS-OPS-001\
  00_pre_state.txt                 HEAD, branch/merge/rebase state, stashes, full porcelain status
  00_tree_before.csv               14,617 files, path/size/mtime/sha256
  01_pre\                          pre-tidy matrix: console, matrix_summary.json, 130 pytest XMLs,
                                   compileall, 4 import probes, CDS self-test output
  02_commit1.txt                   commit 1 SHA, tag, stat, status breakdown
  03_candidates.csv                every candidate: both reference checks, strict/loose grep,
                                   substring_artefact flag, decision, referrer
  04_tier_c_candidates.csv         71 Tier C, list only
  05_commit2.txt                   commit 2 SHA, per-tier move counts, deferral counts
  06_post\                         post-tidy matrix + matrix_comparison.txt
  07_reachability_diff.txt         EMPTY — item 6 PASS
  08_tree_after.csv                14,893 files
  deferred.csv                     184 rows, every deferral with its class and referrer
  usage_graph_20260904.json        static reachability graph, before
  usage_graph_after_20260904.json  static reachability graph, after
  scripts\                         the read-only analysis scripts written for this operation
  AVS-OPS-001_REPORT.md            this file
```

---

## 9. Constraint compliance

| Constraint | Status |
|---|---|
| Never execute the pipeline | Kept. The only orchestrator invocation was `--evening --cds-startup-self-test`, twice (once per matrix run). |
| Move, never delete (exception `.env.txt`) | Kept. 34 `git mv`; exactly one deletion, independently confirmed by sha256 matching of the tree snapshots. |
| Move only with both checks clean | Kept. 34 movers all had 0 graph inbound edges and 0 grep hits; 59 candidates deferred on a failed check. |
| Do not touch `data\`, `backups\`, `audit\`, `config\`, `contracts\`, `canonical_data\`, `market_structure\`, `vanguard\`, `orchestrator\`, `pipeline_interpreter\`, `intelligence-lab\`, `scripts\`, `tests\`, `tools\`, `src\`, `templates\`, `.git\`, `.claude\`, `venv\` | Kept. Every move was root-level → `_attic\`. Writes under `audit\ops\AVS-OPS-001\` are this operation's own deliverables. |
| Do not rename, reformat or edit any surviving `.py` | Kept. Commit 2 is 0 insertions / 0 deletions. The tree diff shows 5 content-changed files: `.gitignore` and 4 of this operation's own analysis scripts/outputs. **No production file changed content.** |
| No flag set, no `.env` value read or written | Kept. No `AVSHUNTER_*` was set; the matrix strips `AVSHUNTER_*` from the subprocess environment. `.env` and `.env.txt` were never opened or printed. |
| Stop on merge / rebase / detached HEAD | Checked and clean: `master`, no `MERGE_HEAD`, no rebase dir, no cherry-pick/revert/bisect, no stashes. |
| Do not start AVS-SD-003 cycle 1 work | Kept. No production code was touched. Cycle 1 starts from `post-tidy-20260904` in a separate session. |
