# AVS-TRACE-001 · Report · 14 Nov 2026

Independent, read-only review by Claude Code for ACK. No code, config, prompt, scheduled task or data was changed; no pipeline, Lab or provider was run.

## Result

**Nothing is proven closed.** Across 944 traced requirements and fixes, not one has both code evidence and a run that shows it working. The work exists: it is built, mostly tested, and sitting uncommitted or on 12 unmerged branches. The pipeline that runs is the working tree, which matches no branch.

## Counts by status

| Status | Rows | Of which verified in this review |
|---|---|---|
| CLOSED (code and run) | **0** | 0 |
| CLOSED_OFFLINE (code and tests) | 35 | 4 |
| MERGED (on the checked-out line, no test or run cited) | 7 | 7 |
| BUILT_UNMERGED | 11 | 11 |
| APPROVED, not built | 216 | 7 |
| DECISION_PENDING | 23 | 7 |
| PROPOSED | 523 | 67 |
| NOT_FOUND (claimed; evidence not in the repo) | 128 | 28 |
| REJECTED | 1 | 0 |

- Sources covered: 127 of 127 register rows, 855 of 855 inbox candidates (96 files), 1,775 of 1,775 document IDs (114 files).
- 131 rows were verified against code, git and runs. The other 813 carry the source document's own claim or are grouped supporting records; they are labelled as such.
- 33 rows are marked `CLAIM_NOT_SUPPORTED`: 20 of the register's 50 "Built" rows were reported broken again afterwards.

## The five most important gaps

1. **The code that runs is uncommitted and on no single branch.** 64 modified and 171 untracked paths. It includes GARCH D1 and station quarantine; it excludes the monetisation clock and the production-eligibility check. `master` is 267 commits behind; there is no integration branch. (`03_branch_review.md`)
2. **A Morning run that starts outside 09:35–09:45 ET is now refused**, by an uncommitted guard on no branch. The tradeability sheet of 13 Nov lists that decision as still open, and it conflicts with "flag quote age, never gate on it". The last two Mornings ran at 10:42 ET and 13:42 ET. (TR-006)
3. **The logs stopped.** The register was last written on 17 Oct and the change log on 20 Oct. Since then 855 candidates were filed and never triaged, 21 commits went unlogged, and a 12-session pipeline outage (22 Oct to 10 Nov) is recorded only in monitor notes. (`02_fix_log_review.md`)
4. **The contract fixes that matter for money are decided or built but not running.** Monetisation clock: built, not merged, and it gives an n for only 39 of 2,800 rows. Contract from n, one liquidity standard, the window flag, alternatives: decided, not built. On the last run 1,005 of 2,132 contracts expire before the median arrival and 1,697 quote at tier C. (TR-001, 002, 004, 009, 011)
5. **Execution leaks the logs keep reporting.** Resting exits never placed (45 reports; one position held past its stop, time stop and target), criteria met with no order (18), and no outcome ledger to show what any card made. The outcome ledger has been asked for under more than 20 IDs since 10 Sep. (TR-030, 031, 010)

Two corrections to the 13 Nov picture: there are 12 unmerged branches, not 7; and GARCH D1 is no longer "not shipped" (`fff3a3e`, 13 Nov 22:06 UTC, in the working tree, not yet run).

## Decisions needed from ACK

| # | Decision | Recommendation |
|---|---|---|
| 1 | Morning late start: refuse the run, or flag and price | Flag and price, with the start time on every row. It matches your rule on quote age, and a refused Morning leaves no book. If you keep "refuse", it should be committed and written into the tradeability sheet |
| 2 | Name the integration branch and have the working tree committed by its owners | Continue from `016b301`; do this before any merge |
| 3 | Approve the change-log backfill (`05_change_log_backfill.md`) | Approve; I append it on your word |
| 4 | Who owns inbox to register, and the change-log line per commit | One scheduled task for the register; the log line in the same commit for Codex and Claude Code |
| 5 | Confirm the 11 Nov tiers replace the six spread limits now in force | Confirm; one definition in governed constants |
| 6 | ETF package: macro direction for ETFs (the 12 Nov QQQ exception is not written down anywhere), ETF priority, leveraged and inverse products, index ETFs and the cap | `06_ETF_fix_package_for_Codex.md` section 8 |
| 7 | Still open from 13 Nov: SHADOW to ACTIVE, Tastytrade quotes, window order in the rank, success tests, X17 test, triage on Evening or Morning | `02_fix_log_review.md` section 5 |
| 8 | Are exit tickets read at all (OI position held since 13 Oct) | Yours |

## Merge order (nothing merged)

0. Name the line; commit the working tree by owner.
1. `fix/station-quarantine-20261113` (fixes the fault that stopped the 12 Nov run).
2. `fix/garch-d1-cumulative-windows-20261113` (4 files, no overlap).
3. `phantom-scoring-iv-hold-fixes-20261111`, then `fix/phantom-path-completeness-safeguards-20261113` (drop the three model-package scripts it carries).
4. `fix/ac-reliability-20261112`, then `feat/a12-monetisation-clock-20261112`.
5. `macro-null-usmi-fixes`, `macro-delivery-publication-guards-20261110`, `macro-board-event-timestamp-sort-20261110`.
6. `macroboard-lab-worker3-decommission`, `market-mentality-redesign`: compare and close, do not merge as they stand.
7. `fix/production-eligibility-20261112` last: once in, it refuses a run on uncommitted code.

One run after each step, with the run ID written to the change log. `intelligent_orchestrator.py` is changed by seven branches and is where conflicts will be.

**For the Evening run due by Sunday 15 Nov:** if none of this is done first, the run is on the working tree as it stands. Record that with the run, and start Monday's Morning inside 09:35–09:45 ET or it will not price.

## Acceptance

| # | Check | Result |
|---|---|---|
| T1 | Every register row and inbox candidate is in the matrix | 127 = 127; 855 = 855 (`evidence\matrix_summary.json`) |
| T2 | Every unmerged branch is in the branch review with its overlaps | 12 branches, plus the checked-out branch; overlaps in section 5 and `evidence\branch_overlap_hunks.txt` |
| T3 | Every status other than PROPOSED cites evidence; every CLOSED cites a run | 0 rows without evidence; 0 CLOSED rows |
| T4 | 13 Nov flaws 1–5 and fixes 1–10 map to trace IDs | All mapped; fix 3 is NEW (`01_traceability_matrix.md` section 4) |
| T5 | The ETF package confirms or corrects every evidence line | E1–E15: 11 confirmed (two with a corrected range or scope), 2 corrected, 1 partly, 1 not found; the "Why" paragraph corrected on three of four figures; 9 missed items added |
| T6 | No file outside `audit\trace\AVS-TRACE-001\` changed | `git status` before and after are identical outside `audit\trace\` (235 lines each; `evidence\git_status_before.txt`, `git_status_after.txt`). The one exception is the change-log entry required by the brief, in `lessons\change_log.md`, which git does not track |

## Limits of this review

- 689 document-defined rows carry the document's claim; I did not check each against today's code.
- Inbox candidates were extracted by three reader agents and attached to trace rows by register match and keyword; 146 are grouped by lane and topic rather than judged one by one.
- Codex's test counts and replay results are quoted from its evidence folder outside the repo; I did not rerun any branch's tests.
- Changes made only in claude.ai chats or scheduled-task prompts leave no trace here and are listed as not recoverable in the backfill.

## Files

`00_comprehension.md` · `01_traceability_matrix.csv` and `.md` · `02_fix_log_review.md` · `03_branch_review.md` · `04_open_fixes_by_impact.md` · `05_change_log_backfill.md` · `06_ETF_fix_package_for_Codex.md` · `evidence\`
