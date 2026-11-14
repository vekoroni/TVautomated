# AVS-TRACE-001 · 00 · Comprehension gate

Written 14 Nov 2026 by Claude Code, before the review. Branch checked out: `laneb/lab-first-handoff` at `016b301`.

## What I understand (10 lines)

1. **Daily product.** AVSHUNTER scans about 3,000 US tickers and publishes a ranked book of long-option ideas (ticker, side, level, hold, contract) for ACK to trade by hand; the pipeline is a signal engine, not an executor (`CLAUDE.md`; run `20261111_231951` published 2,800 book rows, `audit\verify\20261111_231951\evening\verify_report.md`).
2. **Lane A** is the Evening and Morning pipeline (`intelligent_orchestrator.py --evening` / `--morning`): Discovery, Vanguard, options selection, Morning gate, and the Intelligence Lab, which publishes the cards. It is repo code, built mainly by Codex.
3. **Lane B** is the desk workflow on top of Lane A's output: the hand-off (`data\scratch\workaround\build_lab_handoff.py`), ticker packs, the scheduled triage, deep-dive cards, monitors and decision records (`avs_day.ps1`). It lives in `data\scratch\workaround\` and in claude.ai scheduled tasks.
4. **Fix inbox** (`lessons\fix_inbox\*.md`): every chat, monitor and deep dive drops what it found there. It is raw candidates, not decisions.
5. **Fix register** (`lessons\fix_register.csv`): the one list of fixes, each with an ID, status, owner and closure evidence. Inbox files are meant to be merged into it and moved to `fix_inbox\processed\`.
6. **Change log** (`lessons\change_log.md`): one entry per change by any chat or agent, read before building, because chats share no memory (ACK's rule of 17 Oct, `change_log.md:3-8`).
7. **Two-level closure** (ACK, 4 Sep 2026): CLOSED needs code evidence **and** a run artefact showing the fix working. Code plus tests only is CLOSED OFFLINE and is never counted as closed.
8. Missing evidence is never a pass: where I cannot find it I write `NOT FOUND` and where I looked.
9. I am a reviewer here: read only. I write under `audit\trace\AVS-TRACE-001\` and one change-log entry at the end.
10. I do not run the pipeline, the Lab, or anything that calls MarketData, Polygon, Tastytrade or the Claude API.

## Branches found

Source: `git branch -a -vv`, `git cherry HEAD <branch>`, `git diff --name-only HEAD...<branch>` on 14 Nov 2026. Raw output: `evidence\branch_commits.txt`, `evidence\branch_files\`, `evidence\branch_vs_worktree.txt`.

**The brief names 7 unmerged branches. I found 12 with commits that are not in the checked-out branch, carrying 12 distinct commits.** `master` (`8c15f51`, 6 Sep 2026) is 267 commits behind the checked-out branch; nothing has been merged into it since. `origin/main` (`b7f2993`, Feb 2025) shares no history with the working line.

| Branch | Tip | Date (UTC) | Unmerged commits | Files | What it touches |
|---|---|---|---|---|---|
| `laneb/lab-first-handoff` (checked out) | `016b301` | 12 Nov 23:05 | 8 ahead of `high-convexity-watchlist` | 8 commits | Lane B: `data\scratch\workaround\` hand-off, packs, triage check, decisions; `audit\laneb_fixB\` |
| `fix/station-quarantine-20261113` | `58a4904` | 13 Nov 07:29 | 1 | 9 | `domain\station_inspection.py`, `intelligent_orchestrator.py`, `morning_gate.py`, `avshunter_discovery_ULTIMATE.py`, `dropoff_audit.py`, `config\governed_constants_v1.json` |
| `fix/garch-d1-cumulative-windows-20261113` (**not in the brief**) | `fff3a3e` | 13 Nov 22:06 | 1 | 4 | `layer3_forward_variance.py`, `domain\volatility_budget.py`, one test, one guard |
| `fix/phantom-path-completeness-safeguards-20261113` | `f845857` | 13 Nov 21:19 | 2 (includes `1332983`) | 22 | PHANTOM backfill guards under `Enhancements\phase0\`; also carries copies of Lane B and model-package files |
| `feat/a12-monetisation-clock-20261112` | `b709669` | 12 Nov 23:07 | 2 (includes `da9a922`) | 22 | `avshunter\c12_outcome\monetisation.py`, `contracts\monetisation_clock.py`, `config\monetisation_clock_v1.json`, Lab contracts, publish and verify scripts |
| `fix/ac-reliability-20261112` | `da9a922` | 12 Nov 22:14 | 1 | 14 | `domain\trade_timing.py`, `contracts\handoff_reliability.py`, Lab contracts, `domain\anticipated_move.py`, `scripts\exit_rules_engine.py` |
| `fix/production-eligibility-20261112` | `eb50549` | 12 Nov 12:18 | 1 | 8 | `orchestrator\production_eligibility.py`, `intelligent_orchestrator.py`, `orchestrator\dynamic_dispatcher.py`, `avshunter\c0_run\canonical_manifest.py` |
| `phantom-scoring-iv-hold-fixes-20261111` | `1332983` | 11 Nov 11:15 | 1 | 6 | `scripts\phantom_database.py`, `phantom_engine.py`, `phantom_maintenance.py`, `intelligent_orchestrator.py` |
| `macro-board-event-timestamp-sort-20261110` (not in the brief) | `66d0501` | 10 Nov 22:46 | 1 | 2 | `macro_board\build_board.py` |
| `macro-delivery-publication-guards-20261110` (not in the brief) | `4601ce5` | 10 Nov 21:59 | 1 | 32 | `Run-MacroInputs.ps1`, `build_macro_json.py`, `contracts\macro_*`, `contracts\us_money_index_contract.py`, three config files |
| `market-mentality-redesign` (not in the brief) | `a4f0ecc` | 19 Oct | 2 (includes `0724adf`) | 23 | Lab macro desk, `contracts\lab_market_mentality.py`, `intelligent_orchestrator.py` |
| `macroboard-lab-worker3-decommission` (not in the brief) | `0724adf` | 18 Oct | 1 | 19 | Lab macro desk, Worker 3 retirement |
| `macro-null-usmi-fixes` (not in the brief) | `4d47a85` | 17 Oct | 1 | 4 | `contracts\us_money_index_contract.py`, Colab macro module |

Already contained in the checked-out branch (same patch under another hash, `git cherry` shows `-`): `claude/dexuseu-h10-release` (`d6caa69`), `phantom-maintenance-provenance` (`808f9c3`). Fully merged ancestors: `avs-fix-001`, `high-convexity-watchlist`, `avs-p04-capture`, `claude/ivs-001-iv-surface`, `ila-stage-ladder-investigation`, `wp1-expression-tradeability`, four `worktree-agent-*`. Five `claude/*` branches sit on `origin/main` with no work.

**The working tree is not any branch.** It has 64 modified and 171 untracked paths (`evidence\git_status_before.txt`), which include uncommitted copies of most of the branches above. Measured file by file (`evidence\branch_vs_worktree.txt`):

| Branch | Its files present in the working tree as on the branch | Not present | Differ from both |
|---|---|---|---|
| GARCH D1 | 4 of 4 | 0 | 0 |
| Station quarantine | 6 of 9 | 0 | 3 |
| PHANTOM path completeness | 17 of 22 | 3 | 2 |
| A/C reliability | 9 of 14 | 1 | 4 |
| A12 monetisation clock | 8 of 22 | **9 (all the monetisation files)** | 5 |
| Production eligibility | 0 of 8 | **7** | 1 |
| Macro delivery guards | 21 of 32 | 2 | 9 |

So a pipeline run from this folder today would run GARCH D1 and station quarantine, and would **not** run the monetisation clock or the production-eligibility check. "Differ from both" files are those two or more branches change (`intelligent_orchestrator.py` is changed by seven branches).
