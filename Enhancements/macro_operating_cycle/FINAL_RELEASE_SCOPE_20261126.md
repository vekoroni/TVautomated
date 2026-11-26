# Final macro release pre-commit checkpoint — 26 November 2026

Status: ADAPTER_TESTS_PASS_ACK_APPROVED_MACRO_ONLY_RELEASE. ACK approved the exact 14-file commit, annotated tag and branch/tag-only push after reviewing acceptance. No main merge, deployment or task enablement is authorized. Earlier precommit checkpoints below are retained as history; the final Git identity is carried by this document's commit and annotated tag.

Prepared local branch: `feat/macro-final-governance-20261126`.
Published macro-only base: `a2c50838dfbc19b96d6d1a93c186d5beffd9a54f` (`feat/macro-operating-cycle-integration-20261126`).
ACK-approved annotated tag: `macro-final-governance-20261126`.
Live checkout remains on `laneb/lab-first-handoff`; its index and working files were not altered by this release-preparation task.

## Exact proposed increment: 14 files

Modified (7):

1. `config/macro_narrative_v1.schema.json`
2. `config/macro_operating_cycle_v1.json`
3. `intelligence-lab/static/macro-cycle.js`
4. `macro_board/cycle_narrative.py`
5. `macro_board/cycle_scoring.py`
6. `macro_board/operating_cycle.py`
7. `tests/js/macro_cycle_harness.cjs`

New (7):

8. `config/macro_research_input_v2.schema.json`
9. `macro_board/cycle_governance.py`
10. `tests/test_macro_cycle_governance.py`
11. `tools/verify_final_macro_saved_replay.py`
12. `Enhancements/macro_operating_cycle/FINAL_GOVERNANCE_HANDOFF_20261126.md`
13. `Enhancements/macro_operating_cycle/FINAL_RELEASE_SCOPE_20261126.md`
14. `macro_board/cycle_option_compat.py`

The saved replay helper is versioned here so the release can actually test its OWN imports, rather than using the original evidence helper's hardcoded working-checkout ROOT. Defaults read existing saved artifacts only; output is a separate evidence folder. No live runtime, .env or database bindings are added.

Important correction to the proposed scope rule: `build_board.py` and `measured_sheet.py` were integration edits in the previously published base. They are unchanged in THIS increment. The final contracts necessarily modify the seven existing macro-only files above, including the shared macro narrative renderer. It would be inaccurate to claim these two builder files are the only existing files changed in the final release. ACK review of this exact scope is pending.

Excluded: all `data/` files, raw drafts, saved responses, generated board/Lab output, audit receipts, live databases, backups, Lane B, ticker scoring, shared option-valuer code, orchestrator, scheduler scripts/configuration, budget files and credential files. No whole dirty-working-checkout files were copied for board/triage consumers. FULL and PostClose timing remain inherited unchanged.

## Initial isolated test output — retained history, superseded by adapter acceptance below

Command 1:

`Set-Location "C:\Users\ACKVerissimo\Documents\Codex\2026-07-24\a\macro_final_governance_release_20261126"; & "C:\Users\ACKVerissimo\AVSHUNTER-Intelligence\venv\Scripts\python.exe" -B -m pytest "C:\Users\ACKVerissimo\Documents\Codex\2026-07-24\a\macro_final_governance_release_20261126\tests\test_macro_cycle_governance.py" -q -p no:cacheprovider --basetemp="C:\Users\ACKVerissimo\Documents\Codex\2026-07-24\a\mcgrelease"`

```text
FAILED test_correct_relative_call_is_not_put_profit_and_delay_iv_can_lose
FAILED test_world_payoffs_and_authored_stress_comparisons_do_not_inherit_win_marks
ImportError: cannot import name 'net_return_on_premium_raw' from 'domain.option_valuation'
2 failed, 26 passed in 15.53s
```

The isolated published base has an older shared option-valuer interface than the dirty live checkout. That dependency was not visible in the earlier 155 live-checkout passes. No test was weakened or skipped, and no unrelated valuation runtime was imported into this branch to hide the failure. Evidence: `C:\Users\ACKVerissimo\Documents\Codex\2026-07-24\a\MACRO_FINAL_RELEASE_GOVERNANCE_TESTS_20261126.xml`.

Command 2:

`Set-Location "C:\Users\ACKVerissimo\Documents\Codex\2026-07-24\a\macro_final_governance_release_20261126"; & "C:\Users\ACKVerissimo\AVSHUNTER-Intelligence\venv\Scripts\python.exe" -B "C:\Users\ACKVerissimo\Documents\Codex\2026-07-24\a\macro_final_governance_release_20261126\tools\verify_final_macro_saved_replay.py"`

```text
status: PASS
content_status: RESEARCH_DRAFT
board_http: 200
lab_http: 200
same_narrative_hash: true
all_three_feeds: true
unchanged_etf_rows: 115
older_narrative_unchanged: true
draft_installed_as_live_input: false
live_publication_modified: false
provider_calls: 0; paid_builds: 0; pipeline_runs: 0
```

Output: `C:\Users\ACKVerissimo\Documents\Codex\2026-07-24\a\MACRO_FINAL_GOVERNANCE_ISOLATED_20261126`.
Saved publication ID: `9f73f99aa303134f5dd0f722f62b3806b4683ebf5799b8c4925d4a668c8f77fb`.

This replay has no exact option contracts in the draft envelope and correctly reports option payoffs unassessed. Its PASS cannot substitute for the two failed option-valuing tests.

## Approval gates before commit

1. ACK/independent reviewer checks the actual output above.
2. ACK approved the macro-only compatibility adapter; it is implemented and tested below. No shared valuation dependency was imported or changed.
3. Both commands now pass against the isolated branch. ACK/independent reviewer must check the output and final 14-file list before commit/tag/push.
4. After authorization: create macro-only commit and annotated tag, push only that branch and tag. No merge to main before a clean controlled live board run. Operational acceptance remains AWAITING_RUN and schedules remain disabled.

## Shared release change-log line (no data-folder mutation)

The repository's usual shared change log is under `data/`. ACK explicitly said leave data untouched; therefore this release checkpoint records its line here instead. It is not a claim that a commit was made.

| when_utc | agent | branch | commit | action | acceptance |
|---|---|---|---|---|---|
| 2026-11-26 | Codex | feat/macro-final-governance-20261126 | NOT_COMMITTED | Isolated final macro scope and saved replay; no providers/paid/pipeline/live publication/schedule changes | 26 pass, 2 option-interface failures; saved E2E PASS; awaiting correction and independent review |
| 2026-11-26 | Codex | feat/macro-final-governance-20261126 | NOT_COMMITTED | ACK-approved macro-only compatibility adapter; shared pricing/fees/data/ticker/Lane B untouched | 42 tests PASS; saved E2E PASS; awaiting ACK precommit review |

## Current adapter acceptance — supersedes the earlier release blocker

`cycle_option_compat.py` imports only the published shared valuer's stable entry-cost and exit-proceeds helpers. It returns an unrounded premium return and applies only the extra/reduced spread haircut BEFORE the shared closing-fee/zero-floor calculation. Original ask/bid and the shared price, fee and configuration owners are unchanged. Governance imports this macro-local adapter instead of requiring the newer shared `net_return_on_premium_raw` interface. Missing/invalid evidence stays unassessed; invalid stress assumptions raise an explicit error.

Fourteen new parameterised cases check zero/base/double spread, worthless-option loss floor, agreement with the shared base return after its published rounding, invalid/missing inputs and invalid stress assumptions. Test-first run failed as expected before the adapter existed; current final run:

```text
..........................................                               [100%]
42 passed in 5.26s
```

Both commands use the isolated worktree as their working directory and its own code imports. The interpreter is the existing venv; no live runtime/data/.env bindings were added. The Python launcher emitted its existing `Failed to find real location of C:\Python314\python.exe` warning, but both commands completed with exit code 0.

Final first-command receipt: `C:\Users\ACKVerissimo\Documents\Codex\2026-07-24\a\MACRO_FINAL_ADAPTER_TESTS_20261126.xml`. It uses the same pytest command above with fresh `--basetemp=...\mcgad_green` and the JUnit receipt option; no test skips or expectation weakening.

Final second command adds an explicit isolated output path:

`Set-Location "C:\Users\ACKVerissimo\Documents\Codex\2026-07-24\a\macro_final_governance_release_20261126"; & "C:\Users\ACKVerissimo\AVSHUNTER-Intelligence\venv\Scripts\python.exe" -B "C:\Users\ACKVerissimo\Documents\Codex\2026-07-24\a\macro_final_governance_release_20261126\tools\verify_final_macro_saved_replay.py" --output "C:\Users\ACKVerissimo\Documents\Codex\2026-07-24\a\MACRO_FINAL_ADAPTER_REPLAY_20261126"`

```text
status: PASS
content_status: RESEARCH_DRAFT
board_http: 200; lab_http: 200
same_narrative_hash: true; all_three_feeds: true
unchanged_etf_rows: 115; older_narrative_unchanged: true
draft_installed_as_live_input: false; live_publication_modified: false
provider_calls: 0; paid_builds: 0; pipeline_runs: 0
```

Saved publication: `2b93dc0c0e5b078f38867342cced040f812866970af2e22c7570e22011197a1d`; narrative: `macro_2026-11-25_66b9421573307b4f7be3cf0c`. Replay `publication.status=COMMITTED` means only the isolated saved-artifact commit pointer, NOT a Git commit or live deployment. Revision 1 remains RESEARCH_DRAFT, approval time null.

Scope checks: no diff to `data/`, shared `domain/option_valuation.py`, `vanguard/`, governed fee constants, orchestrator, `Run-MacroInputs.ps1`, delivery configuration, `build_board.py` or `measured_sheet.py`. All three MacroInputs scheduled tasks independently observed Disabled. `git diff --check` clean. No Git staging, commit, tag, push or merge performed.

## ACK release approval and follow-up register

ACK approved the 14 listed files, dedicated branch and annotated tag only. Pushing is not house-view approval or live deployment. Revision 1 remains RESEARCH_DRAFT; schedules remain disabled; real controlled-run acceptance remains AWAITING_RUN. No merge to main before clean controlled live board evidence.

### MACRO-COMPAT-01 — retire or equivalence-test the adapter

Owner: Codex/shared valuation maintainer. Status: OPEN; follow-up only, not part of this release implementation.

Trigger: the approved macro release lineage gains the shared `domain.option_valuation.net_return_on_premium_raw` API. Correction to the initial dependency description: that API is ALREADY committed in the live `laneb/lab-first-handoff` history (`fc5faee`, AVS-TRADE-001). The older published macro base used here lacks it. Do not import unrelated live-branch history merely to obtain the function.

Acceptance: compare the macro adapter and shared API on identical captured quote/model inputs, zero/base/widened spreads, governed fees, worthless-option floor, threshold-adjacent unrounded returns and malformed/missing evidence. Confirm no input mutation and no option WIN/LOSE or threshold crossing differences caused by rounding. Reconcile any deliberate difference (the macro adapter requires a known bid) explicitly rather than weakening missing-evidence safeguards. If equivalent, switch macro governance to the approved shared API and retire `cycle_option_compat.py` in a separately reviewed macro change. Otherwise document and test the remaining compatibility boundary. Repeat the saved board/Lab replay and preserve narrative lineage. No Lane B or ticker change is implied by this follow-up.

### Separate live-checkout review inventory — not included in this commit

Read-only inventory of `domain/` and `avshunter/shared/` on `laneb/lab-first-handoff`, HEAD `82ef06e92f289cc2d6fb3e4153be055cc2bda86f`:

| Status | Absolute file path |
|---|---|
| Modified | `C:\Users\ACKVerissimo\AVSHUNTER-Intelligence\domain\lab_convexity.py` |
| Modified | `C:\Users\ACKVerissimo\AVSHUNTER-Intelligence\domain\macro_input_governance.py` |
| Untracked | `C:\Users\ACKVerissimo\AVSHUNTER-Intelligence\domain\evening_assessment.py` |
| Untracked | `C:\Users\ACKVerissimo\AVSHUNTER-Intelligence\domain\evening_target_roles.py` |

No uncommitted changes were reported in `avshunter/shared/`. The shared option valuer, deterministic/path valuers, crossing-scenario module, governed fee constants, EV3 engine and one-valuation-engine tests are tracked and clean in that live checkout; they must not be described as uncommitted merely because their committed versions differ from this macro base. This is a scoped shared-domain inventory, not an assertion that the entire live checkout is clean. Nothing there was staged, reverted, copied into this release or otherwise modified.

| when_utc | agent | branch | commit | action | acceptance |
|---|---|---|---|---|---|
| 2026-11-26 | Codex | feat/macro-final-governance-20261126 | SELF | ACK-approved macro-only 14-file commit and annotated tag `macro-final-governance-20261126`; branch/tag-only push; follow-up MACRO-COMPAT-01 logged | 42 tests PASS and saved E2E PASS; research draft, disabled schedules, AWAITING_RUN; no main merge |
