# AVS-OPS-001 — Root tidy and baseline commit

**Issued:** 2026-09-04
**Agent:** Claude Code — **this prompt grants write access** to the repository for the specific operations below and nothing else. It is an operations prompt, not an audit prompt.
**Repository:** `C:\Users\ACKVerissimo\AVSHUNTER-Intelligence`
**Interpreter:** `C:\Python314\python.exe`
**Output root for reports:** `audit\ops\AVS-OPS-001\`
**Goal:** three clean commits on a tagged baseline — (1) the tree as it stands, (2) dead material moved to `_attic\`, (3) `.gitignore` so it stops coming back — with proof that the production entry points and the full test matrix are unchanged by commit 2.

---

## 1. Hard constraints

- **Never execute the pipeline.** No `--evening`, `--morning`, `--auto`, no `morning_gate.py`, no stage scripts, no Lab server, no provider calls. The only orchestrator invocation permitted is `python intelligent_orchestrator.py --evening --cds-startup-self-test`, which is a self-test and was used as such in the Phase 6 closure.
- **Move, never delete** — with one exception (`.env.txt`, §4 Tier A). Every other file leaves the root via `git mv` into `_attic\<original relative path>` so history and path are preserved and any mistake is one `git mv` back.
- **Only files with zero inbound references.** A file moves only when *both* hold: no inbound edge in `audit\usage_graph.json` (AVS-INV-001) **and** zero hits from `git grep -n "<module stem>"` across `*.py *.ps1 *.bat *.json *.toml *.cfg *.ini *.md` excluding the file itself, `_attic\`, `backups\`, `audit\` and `Archive\`. If either check finds a reference, the file stays and is listed in `deferred.csv` with the referrer.
- **Do not touch:** `data\`, `backups\`, `audit\`, `config\`, `contracts\`, `canonical_data\`, `market_structure\`, `vanguard\`, `orchestrator\`, `pipeline_interpreter\`, `intelligence-lab\`, `scripts\`, `tests\`, `tools\`, `src\`, `templates\`, `.git\`, `.claude\`, `venv\`. This is a **root-level** tidy. Subsystem quarantine (`news_terminal`, `ma_cockpit`, `zero_dte`, `short_swing`, `bridge`, `ml_confidence_layer`, `legacy`, `orchestrator\` v1) is out of scope — AVS-INV-001 defers it until two accepted cycles exist.
- **Do not rename, reformat or edit any surviving `.py` file.** Not even whitespace. Commit 2 must be *only* moves plus the one deletion.
- **No flag is set, no `.env` value is read aloud or written anywhere.**
- If `git status` shows a merge in progress, a detached HEAD, or a rebase, **stop and report**.

---

## 2. Step 0 — Snapshot before anything

1. `git rev-parse HEAD`, `git status --porcelain` (count and full list), `git stash list` → `audit\ops\AVS-OPS-001\00_pre_state.txt`.
2. Full recursive listing of the repository root (path, size, mtime, sha256 for files < 50 MB) → `00_tree_before.csv`.
3. Confirm `audit\usage_graph.json` exists and record its node/edge counts and its baseline SHA. If it is missing or its baseline is older than `5d886f0`, regenerate the reachability graph from the four entry points (`intelligent_orchestrator.py`, `morning_gate.py`, `intelligence-lab\intelligence_lab.py`, `pipeline_interpreter\`) using static import analysis only, and save it as `usage_graph_20260904.json`. Do not import the modules to discover their imports — parse them.
4. Run the **pre-tidy verification matrix** (§6) and save every XML under `01_pre\`. If anything in the matrix fails *before* you move a file, record it as `PRE_EXISTING` — the tidy is not allowed to fix it and must not be blamed for it.

## 3. Commit 1 — baseline as-is

```
git add -A
git commit -m "AVS-OPS-001 baseline: working tree as of 2026-09-04 before root tidy (post AVS-SD-002 Phase 0-8, post run 20260904_004338)"
git tag -a pre-tidy-20260904 -m "Tree state before AVS-OPS-001 root tidy; last run 20260904_004338"
```

Before `git add -A`, confirm that `.env` is in `.gitignore` and is **not** staged. If it would be staged, stop. Confirm no file > 100 MB is being added (`data\` and `backups\` should already be ignored; if they are not, add them to `.gitignore` *first* and note it — this is the one `.gitignore` edit permitted before commit 3).

Record the commit SHA in `02_commit1.txt`.

## 4. Commit 2 — move dead material to `_attic\`

Work through the tiers in order. For each candidate, run the two reference checks from §1, record the result in `03_candidates.csv` (`path, tier, graph_inbound, grep_hits, decision, referrer`), and only then `git mv`.

### Tier A — scratch, backups and debris (no import risk by construction)

Root-level only:

- `*.bak`, `*.bak_*`, `*.rr_cap.bak`, `*old0908.py`, `*.pre_macro_redesign.bak`, `*.b1_fix.bak`, `*.b1b2b3.bak`, `*.phantom75.bak`, `*.mcmillan_fix.bak`, `*.fix_gates.bak`, `*.regime_watch.bak`, `*.polygon_migration.bak`, `*.missing_tokens.bak` and any other file whose name carries `.bak`, `bak_`, `old`, `dnu` as a suffix or token
- `tmp*\` directories; `pip-build-tracker-*\`, `pip-ephem-wheel-cache-*\`, `pip-install-*\`, `pip-metadata-*\`, `pip-target-*\`, `pip-unpack-*\`
- `avs_macro_check_*\` directories
- `.codex_py312_testenv\`, `.codex_python313_runtime\`, `.codex_test_runtime\`, `.codex_test_temp\`, `.codex_test_tmp\`, `.pytest_cache\`, `pytest-of-ACKVerissimo\`, `__pycache__\`
- `datadnuold2404\`
- `cmd_lines_debug.txt`, `menu_debug.txt`, `docx_extracted.txt`, `comp9_spec.txt`, `hash_diag_20260421.json`, `hash_diag_fixed.json`, `build_packages_from_discovery.txt`
- `requirements..txt` (double dot) — but first diff it against `requirements.txt`; `requirements.txt` is 0 bytes, so if `requirements..txt` has content, **rename** it to `requirements.txt` via `git mv` instead of archiving it, and note this
- `dropbox - Shortcut.lnk`, `dropbox - Shortcut (2).lnk`, `pipeline_interpreter - Shortcut.lnk`
- `Audit_AVSHUNTER_CompleteFixList_20260521.ps1`, `stability_run_template.ps1`, `stability_run_template0.ps1`, `setup_config.ps1`, `check_pipeline.ps1` — archive unless referenced
- `run_evening.bat`, `run_premarket.bat`, `run_shadow_automation.bat`, `run_daily_orchestration.sh` — retired per AVS-INV-001; archive **only if** the grep check is clean (the release baseline or self-tests may still reference the launcher names — if so, defer)
- The nested directory `AVSHUNTER-Intelligence\` inside the repo root: list its contents first. If it is an accidental copy of the repo, move it whole to `_attic\nested_repo_copy\`. If it contains anything unique (a file whose sha256 appears nowhere else in the tree), stop and report before moving.
- **Delete, do not archive:** `.env.txt`. It is a plaintext copy of API keys (AVS-INV-001 R-05). `git rm` it, confirm it never appeared in a prior commit (`git log --all -- .env.txt`); if it did, report that the keys in it must be rotated regardless of this tidy. Do not print its contents.

### Tier B — retired root modules (move only if both reference checks are clean)

From the AVS-INV-001 dead list and the Aug–Sep audits:

- `morning_validation.py`, `morning_validation_engine.py` (retired pair)
- `kelly_sizer.py`, `position_sizing_engine.py` *(check carefully — `execution_intelligence_runner` was found importing PSE in the past; if referenced, defer)*
- `catastrophe_gate.py` (stub; orchestrator runs a "catastrophe no-op" — confirm the no-op does not import it)
- `execution_decision_engine.py` (retired EDE)
- `premarket_intelligence_ULTIMATE.py`
- `step4_test.py`, `step5_graceful_test.py`, `step6_test.py`, `step6_test_v2.py`, `step6_test_v3.py`, `step7_test.py`, `step7_test_v2.py`, `step8_test.py`, `step9_verify.py`, `step10_test.py`, `section11_tests.py`, `section11_tests_v2.py`, `final_verify_c9.py`, `check7_prompt.py`, `lab_recon_selftest.py`, `macro_sector_propagation_test.py`, `md_api_diagnostic.py`, `polygon_options_validation.py`
- `actuarial_hash_diagnostic.py`, `add_state_hash.py`, `scenario_builder.py`, `refresh_daily_data.py`, `run.py`, `resume_after_vanguard.py`, `audit_latest_run.py`, `uat_audit_report.py` *(uat_audit_report is named in AVS-SD-003 W1-10 — if it is the live UAT generator, it stays; check the orchestrator)*
- `WyckoffEngine_3101_v2.py`, `wyckoff_crabel_precor_logic_v2.py`, `wyckoff_phase_validator.py` *(AVS-REV-002 reviewed "both Wyckoff engines" as core — expect these to be referenced; defer if so)*
- `avshunter_options_intelligence.py` at root (1,018 bytes — a shim; the real module is `scripts\avshunter_options_intelligence.py`). Check what imports the root shim before moving.
- `avshunter_monetisation_policy.py` at root — AVS-INV-001 found it duplicated in `scripts\` with **both reachable**. **Do not move.** List it in `deferred.csv` as `DUPLICATE_BOTH_REACHABLE` for the post-MVP dedupe.

### Tier C — not in scope, list only

Every other root-level `.py` that the graph marks unreachable from all four entry points but which is not in Tier A or B: list in `04_tier_c_candidates.csv` with its graph status. Do not move. These are for the post-MVP quarantine under AVS-INV-001.

### Commit

```
git add -A
git commit -m "AVS-OPS-001 tidy: move unreferenced root backups, scratch and retired modules to _attic/ (no code edits); remove plaintext .env.txt"
```

Record the SHA, the count of files moved per tier, and the count deferred in `05_commit2.txt`.

## 5. Commit 3 — `.gitignore`

Append (only if absent):

```
__pycache__/
.pytest_cache/
pytest-of-*/
tmp*/
pip-*/
avs_macro_check_*/
.codex_*/
*.bak
*.bak_*
*.rr_cap.bak
*old0908.py
.env
.env.txt
*.lnk
```

Do **not** add `_attic/` — it must stay tracked so the moves are reversible and visible.

```
git add .gitignore
git commit -m "AVS-OPS-001: ignore scratch, cache and backup patterns"
git tag -a post-tidy-20260904 -m "Root tidy complete; verified by AVS-OPS-001 matrix"
```

## 6. Verification matrix — run after Step 0 and again after commit 2, compare

Every test file in its own process (the Phase 2 closure records that single-process collection is invalid because of the `vanguard/scripts` shadowing). Save each XML under `01_pre\` and `06_post\` respectively.

1. **Compile check:** `python -m compileall -q .` excluding `_attic`, `backups`, `venv`, `.codex_*`. Zero errors required. (Note: AVS-INV-001 recorded a pre-existing f-string parse error in `scripts\run_vanguard_from_packages.py`; if it still exists, it is `PRE_EXISTING`, not a tidy failure.)
2. **Entry-point import smoke:** for each of `intelligent_orchestrator`, `morning_gate`, `intelligence-lab/intelligence_lab.py`, `pipeline_interpreter` — `python -c "import importlib, sys; ..."` with `AVSHUNTER_*` unset, in a subprocess, asserting the import succeeds without network. If a module performs I/O at import time and fails for that reason, record it, do not fix it.
3. **CDS self-test:** `python intelligent_orchestrator.py --evening --cds-startup-self-test` → must report PASS as it did in the Phase 6 closure.
4. **Dynamic-session pack:** `tests\test_dynamic_session_phase0.py` … `phase8.py`, `test_morning_handoff_finalizer.py`, `test_lab_governed_handoff.py`, `test_pipeline_interpreter_lab_authority.py`, `test_morning_gate_authority.py`, `test_direction_governance_contract.py`, `test_governed_states.py` — expected 165 passed / 0 failed, matching `dynamic_phase8_results_20260903.xml`.
5. **Full top-level production matrix:** every `tests\test_*.py` at top level, isolated — expected 877 top-level passed, 1 skipped, matching `dynamic_phase8_full_regression_20260903.xml`. Plus `tests\qa\` and `tests\rca\` — expected 23 passed.
6. **Reachability diff:** regenerate the static import graph after the move and diff against the pre-move graph. **The set of modules reachable from the four entry points must be identical.** Any difference is a failure — revert the offending move.

**Pass condition for the whole tidy:** identical pass/fail/skip counts pre and post on items 1–5 (including identical `PRE_EXISTING` failures — no new ones, no fewer), and an empty diff on item 6.

If the post-tidy matrix differs from the pre-tidy matrix in any way, do **not** try to patch it. `git revert` commit 2, re-run the matrix to confirm the revert restores the pre-state, and report which move caused it.

## 7. Deliverables

```
audit\ops\AVS-OPS-001\
  00_pre_state.txt
  00_tree_before.csv
  01_pre\                    (verification XMLs before any move)
  02_commit1.txt
  03_candidates.csv          (every candidate, both checks, decision, referrer)
  04_tier_c_candidates.csv
  05_commit2.txt
  06_post\                   (verification XMLs after the move)
  07_reachability_diff.txt   (must be empty)
  08_tree_after.csv
  deferred.csv               (everything that stayed, with the reason)
  AVS-OPS-001_REPORT.md      (summary: three SHAs, two tags, counts per tier, matrix pre/post table, anything PRE_EXISTING, anything that needs ACK's decision)
```

Finish by printing the three commit SHAs, the two tag names, the number of files moved, the number deferred, and a one-line statement of whether the post-tidy matrix is identical to the pre-tidy matrix.

**Do not proceed to any AVS-SD-003 cycle 1 work in this session.** That starts from the `post-tidy-20260904` tag in a separate session.
