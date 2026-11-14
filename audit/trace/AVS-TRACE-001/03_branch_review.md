# AVS-TRACE-001 · 03 · Branch review

Reviewed 14 Nov 2026, read only. Nothing was merged, checked out or changed.
Evidence files are in `audit\trace\AVS-TRACE-001\evidence\`: `branch_commits.txt` (commits and file stats), `branch_files\` (file list per branch), `branch_vs_worktree.txt` (each branch file against the working tree), `branch_overlap_hunks.txt` (hunk headers for every file changed on two or more branches), `worktree_modified_on_no_branch.txt`, `worktree_untracked_on_no_branch.txt`.

## 1. The state in five facts

1. **There is no integration branch.** `master` is at `8c15f51` (6 Sep 2026) and is 267 commits behind the checked-out branch. `origin/main` (`b7f2993`, Feb 2025) shares no history with the working line. Every status of "merged" in this review therefore means "on the checked-out line `laneb/lab-first-handoff`", not "in `master`".
2. **12 branches hold 12 commits that are not on the checked-out line** (the brief names 7). Five extra: `fix/garch-d1-cumulative-windows-20261113`, `macro-delivery-publication-guards-20261110`, `macro-board-event-timestamp-sort-20261110`, `market-mentality-redesign` / `macroboard-lab-worker3-decommission`, `macro-null-usmi-fixes`.
3. **None of the 12 commits has run evidence.** The last completed run, `20261111_231951`, started 11 Nov 23:19 UTC. Eleven of the commits are dated after it, or were made in separate release folders. Codex's own records say so: "NOT_LIVE_DEPLOYED" (A12), "NOT_LIVE_PUBLISHED" (A/C), `pipeline_run: false` (all).
4. **The working tree is the code that runs, and it matches no branch.** 64 tracked files are modified and 171 paths are untracked. It holds uncommitted copies of most branch changes (section 3) plus **32 modified and 133 untracked paths that are on no branch at all** (section 4).
5. **`intelligent_orchestrator.py` is changed by 7 of the 12 branches** and again by uncommitted edits. It is the main merge risk.

## 2. Each unmerged branch

Tests: "recorded" means a count written in the commit message or in Codex's evidence folder `C:\Users\ACKVerissimo\Documents\Codex\2026-07-24\a\` (outside the repo). I did not rerun any branch's tests. No branch has a receipt under `audit\fix_receipts\`; that folder does not exist.

| # | Branch | Commit, date (UTC) | Purpose | Files | Tests recorded | Receipt | Run evidence | Closes (trace_id) |
|---|---|---|---|---|---|---|---|---|
| 1 | `laneb/lab-first-handoff` (checked out; unmerged against `master`) | 8 commits `1e43e6b`..`016b301`, 12 Nov 22:07–23:05 | Lane B hand-off built from the Lab's publication (B0–B10) | Lane B scripts in `data\scratch\workaround\`, `audit\laneb_fixB\` | 48 pass on the 13 Nov working tree (`audit\laneb_fixB\triage_prompt_update_2026-11-13.md` section 4) | `audit\laneb_fixB\99_report.md` | Built on stored run `20261111_231951` only (`handoff\lab_2026-11-12`); live flow still `LEGACY` | TR-012 → CLOSED_OFFLINE |
| 2 | `fix/station-quarantine-20261113` | `58a4904`, 13 Nov 07:29 | A single bad row is set aside instead of stopping the run (RBOT price 0.0001 rounded to 0) | 9 | Count not recorded in the repo | `Enhancements\maintenance_repairs\STATION_QUARANTINE_20261113.json` (on the branch) | None. Saved replay of `20261112_230902`: PASS, 2,952 of 2,953 rows kept (`STATION_QUARANTINE_SAVED_VERIFICATION_20261113_v2.json`) | TR-015 → BUILT_UNMERGED |
| 3 | `fix/garch-d1-cumulative-windows-20261113` | `fff3a3e`, 13 Nov 22:06 | Expected moves published for cumulative trading-session windows (the D1 fix) | 4 | 116 pass, 1 skipped (`GARCH_D1_RELEASE_20261113.json`) | That JSON, outside the repo | None | TR-008 → BUILT_UNMERGED |
| 4 | `phantom-scoring-iv-hold-fixes-20261111` | `1332983`, 11 Nov 11:15 | PHANTOM scoring speed, IV acknowledgement, hold-period lineage | 6 | "69 isolated tests passed" (commit message) | `Enhancements\maintenance_repairs\20261111_evening\repair_receipt.json` (working tree) | Uncommitted copy was in the working tree for run `20261111_231951`; no artefact found that shows the fix itself working | TR-018 → BUILT_UNMERGED |
| 5 | `fix/phantom-path-completeness-safeguards-20261113` (stacked on 4) | `f845857`, 13 Nov 21:19 | "Path complete" needs usable quotes; guarded historical backfill | 16 (+6 from branch 4) | 33 pass before the resume (`PHANTOM_RESUME_FAILURE_20261113.json`) | None in the repo | Data action, not a run: backfills of 13 Nov (section 6) | TR-019 → BUILT_UNMERGED |
| 6 | `fix/ac-reliability-20261112` | `da9a922`, 12 Nov 22:14 | Exact XNYS session clocks, hand-off reliability contract, exit-engine and Lab projection fixes (fix-list A and C items) | 14 | 465 pass, by file (`AC_RELIABILITY_VERIFICATION_20261112.json`) | That JSON, outside the repo | None: "SAVED_DATA_VERIFIED_NOT_LIVE_PUBLISHED" | TR-017 → BUILT_UNMERGED |
| 7 | `feat/a12-monetisation-clock-20261112` (stacked on 6) | `b709669`, 12 Nov 23:07 | Monetisation clock measured on saved quotes (+20% / +30%), descriptive only | 13 (+14 from branch 6) | 84 pass (`A12_IMPLEMENTATION_RESULT_20261112.json`) | `Enhancements\maintenance_repairs\A12_MONETISATION_CLOCK_20261112.json` (on the branch) | None: "NOT_LIVE_DEPLOYED". On saved run `20261111_231951`: 39 of 2,800 rows get an n at +20%, 21 at +30% | TR-009 → BUILT_UNMERGED |
| 8 | `fix/production-eligibility-20261112` | `eb50549`, 12 Nov 12:18 | A standard production run refuses to start on uncommitted code | 8 | Count not recorded | `Enhancements\production_eligibility_release_20261112.md` (on the branch) | None. Saved check: the 11 Nov run would have been refused, "CODE_UNCOMMITTED" (`PRODUCTION_ELIGIBILITY_SAVED_ACCEPTANCE_20261112.json`) | TR-016 → BUILT_UNMERGED |
| 9 | `macro-delivery-publication-guards-20261110` | `4601ce5`, 10 Nov 21:59 | Macro file delivery, FULL publication guard, busy-writer deferral | 32 | Count not recorded | `Enhancements\macro_delivery_publication_guards.md` (on the branch) | Board rebuild of 10 Nov verified by Codex (`MACRO_FULL_REBUILD_VERIFICATION_20261110.json`); not a pipeline run | TR-024 → BUILT_UNMERGED |
| 10 | `macro-board-event-timestamp-sort-20261110` | `66d0501`, 10 Nov 22:46 | Board events sorted by their own timestamps | 2 | Count not recorded | None in the repo | Board rebuild verified (`ETF_BOARD_EVENT_SORT_VERIFIED_20261110.json`) | TR-025 → BUILT_UNMERGED |
| 11 | `macro-null-usmi-fixes` | `4d47a85`, 17 Oct | Absent gamma flips handled; one explicit US Money Index text flag accepted | 4 | Not recorded | None | NOT FOUND | TR-026 → BUILT_UNMERGED |
| 12 | `macroboard-lab-worker3-decommission` and `market-mentality-redesign` (stacked) | `0724adf` 18 Oct, `a4f0ecc` 19 Oct | Lab macro desk, Worker 3 retired, Market Mentality page | 19 and 12 | Not recorded | `docs\LAB_MACRO_DESK_AND_WORKER3_RETIREMENT.md` | NOT FOUND | TR-027 → see note |

Note on 12: the checked-out line already has `bb65704` (19 Oct, "Market Mentality macro desk; Worker 3 decommissioned and retained"). Against the checked-out tip, `market-mentality-redesign` differs in 6 files (106 lines added, 66 removed) and `macroboard-lab-worker3-decommission` in 12. These branches look like an earlier cut of work that was then committed differently. They should be compared and closed, not merged as they stand.

Not unmerged: `claude/dexuseu-h10-release` (`d6caa69`) and `phantom-maintenance-provenance` (`808f9c3`) are already on the checked-out line under other hashes.

## 3. How much of each branch is already in the working tree

A pipeline run from `C:\Users\ACKVerissimo\AVSHUNTER-Intelligence` runs the working tree. Counted per file (`branch_vs_worktree.txt`):

| Branch | Files identical to the branch | Files absent | Files that differ from branch and from the last commit |
|---|---|---|---|
| GARCH D1 | 4 of 4 | 0 | 0 |
| PHANTOM scoring | 5 of 6 | 0 | 1 (`intelligent_orchestrator.py`) |
| PHANTOM path | 17 of 22 | 3 | 2 |
| Station quarantine | 6 of 9 | 0 | 3 (`intelligent_orchestrator.py`, `morning_gate.py`, `avshunter_discovery_ULTIMATE.py`) |
| A/C reliability | 9 of 14 | 1 | 4 |
| A12 monetisation clock | 8 of 22 | **9: every monetisation file** | 5 |
| Production eligibility | 0 of 8 | **7** | 1 |
| Macro delivery | 21 of 32 | 2 | 9 |
| Macro event sort | 0 of 2 | 0 | 2 |

What this means for the next Evening run from this folder:

- **GARCH D1 runs** (uncommitted). The old 13 Nov statement "lines 691–692 still differences" is true of the last commit and no longer true of the working tree.
- **Station quarantine runs** (uncommitted, with further edits on top).
- **The monetisation clock does not run.** `avshunter\c12_outcome\monetisation.py`, `contracts\monetisation_clock.py`, `config\monetisation_clock_v1.json` and the publish script are not in the working tree. The Lab will still show `monetisation_state = NOT_PUBLISHED`.
- **The production-eligibility check does not run.** If it did, it would refuse the run, because the tree is not clean.

## 4. Work in the working tree that is on no branch

32 modified tracked files and 133 untracked paths belong to no branch. The ones that change pipeline behaviour:

| What | Files | Why it matters |
|---|---|---|
| **Morning pricing window guard** | `domain\morning_pricing_window.py`, `config\morning_pricing_policy_v1.json`, `tests\test_morning_pricing_window.py` (untracked); wired at `intelligent_orchestrator.py:7971-7980` and `morning_gate.py:3486-3487, 3664, 4701` | A Morning run that starts outside **09:35–09:45 ET is refused** (`outside_window_action = STOP_BEFORE_PRICING`; the workflow logs "Morning start refused" and returns). The config names ACK as owner, effective 13 Nov. The tradeability status sheet of 13 Nov lists "Morning late-start handling" as **still open**. Codex's GARCH record confirms it was "implemented separately in working checkout, not in this release commit". See 99_report, decision 1. |
| Exact session runway on the contract | `domain\option_contract_liquidity.py` (+23), `scripts\avshunter_options_intelligence.py` (+13), `scripts\options_candidate_lane.py` (+9) | Adds `expiry_sessions_remaining` and `expiry_session_check_state`; passes the evidence date into the runway floor. Touches the contract-selection owner. |
| Lab display | `contracts\lab_contract_display.py`, `intelligence-lab\static\contract-details.js`, `short-horizons.js`, `trade-timing.js`, `review-app.css` | New Lab card sections, uncommitted. |
| Macro board and inputs | `macro_board\session_plan.py`, `sources.py`, `measured_sheet.py`, `board_template.html`, `Run-MacroBoard.ps1`, `scripts\refresh_completed_gex.py`, `scripts\refresh_futures_snapshot.py`, four Colab producers | Board and macro-input changes, uncommitted. |
| Verifier | `tools\avs_verify\avs_verify.py` (+28) | The run verifier itself is edited and uncommitted. |
| Rules file | `CLAUDE.md` | Modified, uncommitted. |

Full lists: `evidence\worktree_modified_on_no_branch.txt`, `evidence\worktree_untracked_on_no_branch.txt`.

## 5. File overlaps (merge risk)

Same file changed on two branches. Hunk headers for all of them are in `evidence\branch_overlap_hunks.txt`; the ones that can collide are below.

| File | Branches | Hunks | Risk |
|---|---|---|---|
| `intelligent_orchestrator.py` | production eligibility | `@@ -2367`, `-2392`, `-2955`, `-3085`, `-3129` (all `pin_run_directory` or provider completeness), `-3670`, `-3678`, `-5696`, `-6248`, `-8448`, `-8457` | **High.** `-3129,7` sits 25 lines above the macro-desk hunk `-3154,6`, in the same function. |
| | station quarantine | `@@ -3333`, `-3478`, `-3491`, `-3503`, `-7698` | Medium: `-7698,6` meets the macro-desk rewrite `-7689,37` in `evening_workflow`. **These two overlap directly.** |
| | PHANTOM scoring and PHANTOM path (same four hunks) | `@@ -4154`, `-4176`, `-4231`, `-4248` (`patch_horizon_fields_into_csv`) | Low: identical on both, no other branch touches them. |
| | macro desk / Market Mentality | `@@ -3154`, `-7584`, `-7689,37` | See above. |
| | working tree only | `@@ -7878`, `-7887`, `-7945` (`premarket_workflow`, the Morning guard) | On no branch. |
| `scripts\phantom_database.py` | PHANTOM scoring, PHANTOM path: `@@ -11`, `-359,40` (identical) | Low. Stacked. |
| `scripts\phantom_maintenance.py`, `scripts\finalize_phantom_weekly_snapshot.py` | PHANTOM scoring and path: identical hunks | Low. |
| `contracts\lab_review_sources.py` | A/C `@@ -135`; A12 `-135`, `-189`, `-198`; macro desk `-261` (appended) | Low to medium: different regions. |
| `intelligence-lab\static\review-app.js` | A/C `@@ -14`, `-31,6`; A12 `-14`, `-31,8`; Market Mentality `-40` | **Medium:** minified lines; A12's `-31,8` and Market Mentality's `-40,6` are nine lines apart in one-line-per-function code. |
| `contracts\us_money_index_contract.py` | macro null `@@ -204,6`, `-212,6`; macro delivery `-204,14`, `-223,6` and 16 more | **High:** both rewrite lines 204–230. Macro delivery does not contain the macro-null commit. |
| `macro_board\build_board.py` | event sort `@@ -896`, `-932`; macro desk `-446` | Low. |
| `Run-MacroInputs.ps1` | macro delivery only (the other branch is already merged) | None. |
| `data\scratch\workaround\collect_decisions.py` | PHANTOM path (+18 lines against the 20 Oct base); the checked-out line changed it in `99ee568` (B10) | **Medium:** a pipeline branch carries a Lane B file. Keep the checked-out version unless the 18 lines are wanted. |
| `data\scratch\workaround\build_lab_handoff.py`, `lab_reader.py` | PHANTOM path adds them; identical to the checked-out line | None (same content). |
| `dropbox\macro\coaching\model\scripts\*.py` (3 files) | PHANTOM path adds them | **Scope breach to note:** these are AVS-MODEL-001 research scripts, which the model brief says are never committed with pipeline code. They entered a pipeline commit. |

Stacked pairs (the later branch contains the earlier commit, so its file list repeats it): A12 on A/C reliability; PHANTOM path on PHANTOM scoring; Market Mentality on macro desk.

## 6. Data actions that are not in git

| When (UTC) | What | Counts | Evidence |
|---|---|---|---|
| 13 Nov 15:58 | PHANTOM backfill stopped: Windows "Access denied" replacing `BUDGET.json` | 3,768 credits consumed, 4,408 reserved at the stop | `PHANTOM_RESUME_FAILURE_20261113.json` |
| 13 Nov 17:04 | PHANTOM backfill finished, sessions 20 Oct and 9 Nov | 465,641 rows, 5,654 ticker-days; 5,653 credits consumed, 6,635 reserved; 4,895 rows without Greeks; SPX and SPXW excluded | `PHANTOM_BACKFILL_FINAL_20261113.json` |
| 13 Nov 17:20–19:10 | Named-contract and path supplements; research re-score | 44 named-contract quotes and 508 path quotes; totals 466,193 rows, **6,205 credits consumed, 7,187 reserved** of a 30,000 cap; named-contract coverage 175 → 187 of 272 | `RESEARCH_RESCORE_FINAL_20261113.json`, `OPTION_PATH_GAP_AUDIT_AFTER_20261113.json` |
| Deferred | 12 Nov session | 40 entry chains and 20 path quotes not fetched | same files |

The brief's figures (466,193 rows, 6,205 credits, 7,187 reserved) are confirmed as the totals after the supplements.

## 7. Recommended merge order

Do not merge anything before step 0. I have merged nothing.

| Step | What | Why |
|---|---|---|
| 0 | **Name the integration line and save the working tree.** ACK chooses the line (I recommend continuing from `016b301`, since `master` is 267 commits behind). Then each owner commits the uncommitted work in section 4 as its own named commit: the Morning pricing guard (after ACK's decision on it), the session-runway edits, Lab display, macro board. | Git refuses a merge that would overwrite uncommitted changes, and 64 files are modified. Until this is done no merge is safe, and no run is on known code. |
| 1 | `fix/station-quarantine-20261113` | Cut from the current tip, so it applies cleanly. It fixes the fault that stopped run `20261112_230902`. Saved replay passed. |
| 2 | `fix/garch-d1-cumulative-windows-20261113` | 4 files, no overlap with any branch, already identical in the working tree. Highest monetisation value for least risk. |
| 3 | `phantom-scoring-iv-hold-fixes-20261111`, then `fix/phantom-path-completeness-safeguards-20261113` | Stacked. Before the second: drop the three model-package scripts from it and keep the checked-out `collect_decisions.py`. |
| 4 | `fix/ac-reliability-20261112`, then `feat/a12-monetisation-clock-20261112` | Stacked; the same 14 files. A12 is what publishes the monetisation fields that Lane B's window flag and the Codex brief (W1) are waiting for. |
| 5 | `macro-null-usmi-fixes`, then `macro-delivery-publication-guards-20261110`, then `macro-board-event-timestamp-sort-20261110` | The first two rewrite the same 30 lines of `contracts\us_money_index_contract.py`; the smaller one first makes the conflict small and visible. |
| 6 | `macroboard-lab-worker3-decommission`, `market-mentality-redesign` | Compare with `bb65704` and the working tree; port what is missing or close the branches. Do not merge as they stand. |
| 7 | `fix/production-eligibility-20261112` **last** | Once merged, a standard production Evening run refuses to start on uncommitted code. Merging it before the tree is clean would block the run. It also has the hunks most likely to collide in `intelligent_orchestrator.py`, so it is best rebased on the result of steps 1–6. |

After each step: the branch's own tests, then one run, then the run ID goes into the change log as the run evidence. A branch is CLOSED only then.

**For the Evening run due by Sunday 15 Nov:** if no merging is done first, the run is on the working tree as it stands today. That is workable, but the run record must say so: uncommitted code, GARCH D1 and station quarantine in, monetisation clock and production eligibility out, Morning refused outside 09:35–09:45 ET.
