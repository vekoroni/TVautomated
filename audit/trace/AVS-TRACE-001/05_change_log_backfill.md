# AVS-TRACE-001 · 05 · Change-log backfill, 19 Oct to 13 Nov 2026

**For ACK to approve. Nothing here has been appended to `data\scratch\workaround\lessons\change_log.md`.**
The last entry in the log is dated 20 Oct 2026 (`change_log.md:30`). The file was last saved on 20 Oct 10:44.

Built from: `git log` on every branch (`evidence\branch_commits.txt`), run folders under `data\output\runs\`, `logs\orchestrator.log`, verifier reports under `audit\verify\`, Lane B's report (`audit\laneb_fixB\99_report.md`) and Codex's evidence records in `C:\Users\ACKVerissimo\Documents\Codex\2026-07-24\a\` (outside the repo; named below as `Codex:` plus the file name).

Format: the log's own (WHAT, WHERE, REGISTER, STATE, COMMITTED) plus the AVS-CHANGELOG-001 fields (BRANCH, COMMIT, FIX_ID, RUN_EVIDENCE, RECEIPT, MERGED). "MERGED: line" means the commit is on the checked-out line `laneb/lab-first-handoff`; nothing has been merged into `master` since 6 Sep 2026. Entries are newest first, as in the log.

What I could not rebuild: changes made only in claude.ai chats or scheduled-task prompts between 20 Oct and 13 Nov (triage prompt, monitor prompts, skills). They leave no trace in git. Where an inbox file reports one, it is listed under "Not recoverable from the repo" at the end.

---

## Entries to append

```
### 2026-11-14 - Claude Code session (AVS-TRACE-001 review)
- WHAT: Read-only traceability review of fix logs, design documents and branches; ETF fix package written for Codex. No code, config, prompt or data changed.
- WHERE: audit\trace\AVS-TRACE-001\ (00 to 06, 99, evidence\)
- REGISTER: none built or closed; matrix maps register rows, inbox candidates and document IDs to trace IDs
- STATE: needs ACK action (decisions in 99_report.md; approve this backfill); COMMITTED: not committed
- BRANCH: laneb/lab-first-handoff (working tree); COMMIT: none; FIX_ID: AVS-TRACE-001; RUN_EVIDENCE: n/a (review); RECEIPT: audit\trace\AVS-TRACE-001\99_report.md; MERGED: no

### 2026-11-13 - Claude Code session (AVS-MODEL-001 steps 2 and 3; tradeability documents)
- WHAT: Model research package: pre-registration signed by ACK, development dataset, baselines scored (every baseline worse than the plain rate). Tradeability status sheet and Codex brief written. Triage prompt block and run sheet for switching Lane B to the Lab hand-off.
- WHERE: dropbox\macro\coaching\model\ (spec, scripts, datasets, reports); Enhancements\tradeability\AVS-TRADE-001_status_and_decisions_2026-11-13.md, AVS-TRADE-001_codex_brief_2026-11-13.md; audit\laneb_fixB\triage_prompt_update_2026-11-13.md
- REGISTER: none (research only; W0-W4 in the Codex brief are proposed)
- STATE: model step 4 not started; hand-off still LEGACY; needs ACK action (paste the triage block, run `avs_day.ps1 status -LabHandoff`); COMMITTED: not committed
- BRANCH: laneb/lab-first-handoff (working tree); COMMIT: none; FIX_ID: AVS-MODEL-001, AVS-TRADE-001; RUN_EVIDENCE: n/a; RECEIPT: dropbox\macro\coaching\model\reports\step3_report_2026-11-13.md; MERGED: no

### 2026-11-13T22:06Z - Codex (GARCH D1)
- WHAT: Layer 3 publishes cumulative trading-session expected moves instead of differences between windows.
- WHERE: layer3_forward_variance.py, domain\volatility_budget.py, tests\test_garch_d1_cumulative_windows.py, Enhancements\garch_d1\offline_guard.py
- REGISTER: 13 Nov fix 4; AVS-FIX-002 D1 (GARCH)
- STATE: built, not run; the same four files are in the working tree uncommitted; COMMITTED: fff3a3e
- BRANCH: fix/garch-d1-cumulative-windows-20261113; COMMIT: fff3a3e; FIX_ID: GARCH-D1; TESTS: 116 pass, 1 skipped (Codex: GARCH_D1_RELEASE_20261113.json); RUN_EVIDENCE: AWAITING_RUN; RECEIPT: none under audit\fix_receipts\ (Codex: GARCH_D1_RELEASE_20261113.json); MERGED: no

### 2026-11-13 (after 22:06Z) - Codex (Morning pricing window) - NOT COMMITTED, ON NO BRANCH
- WHAT: A Morning run that starts outside 09:35-09:45 ET is refused before pricing (outside_window_action STOP_BEFORE_PRICING).
- WHERE: domain\morning_pricing_window.py, config\morning_pricing_policy_v1.json, tests\test_morning_pricing_window.py (untracked); intelligent_orchestrator.py:7971-7980; morning_gate.py:3486, 3664, 4701
- REGISTER: 13 Nov fix 2; register D3
- STATE: live in the working tree now; the tradeability sheet of 13 Nov lists the Morning late-start decision as open; needs ACK action (confirm or switch to a flag); COMMITTED: not committed
- BRANCH: none; COMMIT: none; FIX_ID: MORNING-WINDOW; RUN_EVIDENCE: AWAITING_RUN; RECEIPT: none; MERGED: no

### 2026-11-13T21:19Z - Codex (PHANTOM path completeness)
- WHAT: "Path complete" now needs a usable entry quote and ten usable later quotes; guarded historical backfill runner; named-contract and path supplements.
- WHERE: Enhancements\phase0\guarded_phantom_backfill.py, phantom_named_contract_supplement_20261113.py, phantom_path_supplement_20261113.py, backfill_runbook.py; five test files. The commit also carries copies of Lane B files (build_lab_handoff.py, lab_reader.py, collect_decisions.py) and three AVS-MODEL-001 scripts.
- REGISTER: UAT-04, UAT-05 (PHANTOM workstream)
- STATE: built, not run in a pipeline; COMMITTED: f845857
- BRANCH: fix/phantom-path-completeness-safeguards-20261113 (stacked on 1332983); COMMIT: f845857; FIX_ID: PHANTOM-PATH; TESTS: 33 pass before the resume (Codex: PHANTOM_RESUME_FAILURE_20261113.json); RUN_EVIDENCE: AWAITING_RUN; RECEIPT: none; MERGED: no

### 2026-11-13 15:58Z to 19:10Z - Codex (data action: PHANTOM backfills, MarketData credits)
- WHAT: Historical option chains backfilled for sessions 20 Oct and 9 Nov, then 44 named-contract quotes and 508 path quotes (13 Oct to 5 Nov); research outcomes re-scored. Totals: 466,193 rows; 6,205 credits consumed, 7,187 reserved of a 30,000 cap. The first pass stopped at 15:58Z (Windows "Access denied" on BUDGET.json; 3,768 credits consumed at the stop) and was resumed. 4,895 rows have no Greeks. SPX and SPXW excluded (identity not verified). 12 Nov deferred: 40 entry chains and 20 path quotes.
- WHERE: PHANTOM store (data\phantom); dropbox\macro\coaching\model\outcomes\decision_events.sqlite (named-contract coverage 175 to 187 of 272)
- REGISTER: none
- STATE: complete with exclusions; 12 Nov still missing; COMMITTED: n/a (data)
- BRANCH: n/a; COMMIT: n/a; FIX_ID: PHANTOM-BACKFILL-20261113; RUN_EVIDENCE: Codex: PHANTOM_BACKFILL_FINAL_20261113.json, RESEARCH_RESCORE_FINAL_20261113.json, OPTION_PATH_GAP_AUDIT_AFTER_20261113.json; RECEIPT: same; MERGED: n/a

### 2026-11-13T07:29Z - Codex (station quarantine)
- WHAT: One bad row at a station is set aside with a receipt instead of stopping the run; sub-cent prices are kept, not rounded to zero. Systemic faults still stop the run. Limits: 5 tickers or 1% per station, 5 per run.
- WHERE: domain\station_inspection.py, intelligent_orchestrator.py, morning_gate.py, avshunter_discovery_ULTIMATE.py, dropoff_audit.py, config\governed_constants_v1.json, tests\test_station_quarantine.py
- REGISTER: none (new; cause of the 12 Nov stop)
- STATE: built, not run; mostly present in the working tree uncommitted; COMMITTED: 58a4904
- BRANCH: fix/station-quarantine-20261113; COMMIT: 58a4904; FIX_ID: STATION-QUARANTINE; TESTS: count not recorded; saved replay of 20261112_230902 PASS, 2,952 of 2,953 rows kept (Codex: STATION_QUARANTINE_SAVED_VERIFICATION_20261113_v2.json); RUN_EVIDENCE: AWAITING_RUN; RECEIPT: Enhancements\maintenance_repairs\STATION_QUARANTINE_20261113.json (on the branch); MERGED: no

### 2026-11-13T01:09Z - Pipeline run 20261112_230902 (Evening)
- WHAT: STOPPED at the Discovery station. One row failed the positive-price check: RBOT entry_price not positive (saved close 0.0001 rounded to 0). Enforcement was on. No options stage, no book, no Lab publication, no Morning.
- WHERE: data\output\runs\20261112_230902\diagnostics\station_discovery_20261112_230902.json; logs\orchestrator.log (2026-11-13 01:09:57 CRITICAL)
- REGISTER: fixed by STATION-QUARANTINE (not yet run)
- STATE: no Lab book for the session of 13 Nov; latest pointer still 20261111_231951; COMMITTED: n/a
- BRANCH: working tree on laneb/lab-first-handoff, uncommitted; FIX_ID: n/a; RUN_EVIDENCE: 20261112_230902 (STOPPED at Discovery); RECEIPT: n/a; MERGED: n/a

### 2026-11-12T23:07Z - Codex (A12 monetisation clock)
- WHAT: Sessions until the exact contract first showed +20% and +30% (ask to bid, net of fees), measured on saved quotes; descriptive only. Publish and verify tools; Lab and hand-off disclosures. No change to expiry selection or Lane B.
- WHERE: avshunter\c12_outcome\monetisation.py, adapters\monetisation_history.py, contracts\monetisation_clock.py, config\monetisation_clock_v1.json, scripts\publish_monetisation_clock.py, scripts\verify_monetisation_publication.py, Lab contracts, tests\test_a12_monetisation_clock.py
- REGISTER: fix list A12; 13 Nov fix 7; register D1 (14 Oct)
- STATE: built, not deployed; the monetisation files are NOT in the working tree; on saved run 20261111_231951, 39 of 2,800 rows get an n at +20% and 21 at +30%; COMMITTED: b709669
- BRANCH: feat/a12-monetisation-clock-20261112 (stacked on da9a922); COMMIT: b709669; FIX_ID: A12; TESTS: 84 pass (Codex: A12_IMPLEMENTATION_RESULT_20261112.json); RUN_EVIDENCE: AWAITING_RUN; RECEIPT: Enhancements\maintenance_repairs\A12_MONETISATION_CLOCK_20261112.json (on the branch); MERGED: no

### 2026-11-12T21:12Z to 23:05Z - Claude Code session (Lane B Fix B, B0 to B10)
- WHAT: Lane B hand-off built from the Lab's publication: reader, hand-off with flags (window, time fit, saved liquidity tier, cap, stock tier), packs with the Lab card, triage check on the 11 Nov tiers, a decision record for every card. Live flow left on LEGACY.
- WHERE: data\scratch\workaround\lab_reader.py, build_lab_handoff.py, check_triage.py, collect_decisions.py, avs_day.ps1, pack scripts; audit\laneb_fixB\
- REGISTER: fix list B1, B2, B3, B4, B6, B7, B10 built; B5, B8, B9 not built; 13 Nov fix 1
- STATE: built on stored run 20261111_231951 (handoff\lab_2026-11-12, 2,132 rows); needs ACK action (`avs_day.ps1 status -LabHandoff`, paste the triage block); tests\test_x17_check_triage_spread_gate.py now fails by design; COMMITTED: 1e43e6b, 7f604d1, 572a904, 60d0511, 99ee568, 26c6f3e, 163e933, 016b301
- BRANCH: laneb/lab-first-handoff; COMMIT: 016b301 (tip); FIX_ID: FIX-B (B0-B10); TESTS: 48 pass (13 Nov); RUN_EVIDENCE: AWAITING_RUN (first Lab-first cycle); RECEIPT: audit\laneb_fixB\99_report.md; MERGED: line

### 2026-11-12T22:14Z - Codex (A/C reliability)
- WHAT: Exact XNYS session counting for holds and expiry; hand-off reliability contract; exit engine and Lab projection corrections; evidence hand-off export for Claude.
- WHERE: domain\trade_timing.py, contracts\handoff_reliability.py, contracts\lab_control.py, lab_review_projection.py, lab_review_sources.py, domain\anticipated_move.py, domain\option_valuation.py, scripts\exit_rules_engine.py, scripts\export_claude_evidence_handoff.py, macro_domain\us_money_index.py
- REGISTER: fix list A and C items (see the matrix)
- STATE: built, not published live; 9 of 14 files are in the working tree uncommitted; COMMITTED: da9a922
- BRANCH: fix/ac-reliability-20261112; COMMIT: da9a922; FIX_ID: AC-RELIABILITY; TESTS: 465 pass (Codex: AC_RELIABILITY_VERIFICATION_20261112.json); RUN_EVIDENCE: AWAITING_RUN; RECEIPT: none in the repo; MERGED: no

### 2026-11-12T15:42Z - Pipeline run 20261111_231951 (Morning)
- WHAT: COMPLETE. Morning ran at about 10:42 ET, an hour after the planned time. Verifier verdict DO_NOT_TRADE: all 4 tradeable rows were on quotes 53 to 58 minutes old.
- WHERE: data\output\runs\20261111_231951\final_run_manifest.json; audit\verify\20261111_231951\morning\verify_report.md
- REGISTER: 13 Nov flaw 4
- STATE: this is the last completed run and the current Lab book (2,800 rows, 4 actionable); run_condition TEST, baseline_eligible false; COMMITTED: n/a
- BRANCH: working tree, uncommitted; RUN_EVIDENCE: 20261111_231951 (COMPLETE); MERGED: n/a

### 2026-11-12T12:18Z - Codex (production eligibility)
- WHAT: A standard production Evening run refuses to start when the code is uncommitted or its Git identity is unavailable; run metadata carries a provisional and a final eligibility label.
- WHERE: orchestrator\production_eligibility.py, intelligent_orchestrator.py, orchestrator\dynamic_dispatcher.py, avshunter\c0_run\canonical_manifest.py, three test files
- REGISTER: none
- STATE: built, not active; not in the working tree. Once active, a run from a tree with uncommitted changes is refused; COMMITTED: eb50549
- BRANCH: fix/production-eligibility-20261112; COMMIT: eb50549; FIX_ID: PRODUCTION-ELIGIBILITY; TESTS: count not recorded; saved check PASS (Codex: PRODUCTION_ELIGIBILITY_SAVED_ACCEPTANCE_20261112.json); RUN_EVIDENCE: AWAITING_RUN; RECEIPT: Enhancements\production_eligibility_release_20261112.md (on the branch); MERGED: no

### 2026-11-11T23:19Z to 2026-11-12T10:23Z - Pipeline run 20261111_231951 (Evening)
- WHAT: COMPLETE after about 11 hours (Discovery 01:42Z, options 08:47Z, book 10:23Z). A first start at 23:10Z (20261111_231010) failed the macro publication preflight (news advisory hash changed) and was restarted. Verifier verdict on the Evening book: DO_NOT_TRADE (pipeline's own self-report; manifest row count mismatch).
- WHERE: data\output\runs\20261111_231951; logs\orchestrator.log; audit\verify\20261111_231951\evening\verify_report.md
- REGISTER: none
- STATE: complete; the 09:58 UK triage of 12 Nov found no hand-off and was forced (fix_inbox\2026-11-12_triage.md); COMMITTED: n/a
- BRANCH: working tree, uncommitted; RUN_EVIDENCE: 20261111_231951 (COMPLETE); MERGED: n/a

### 2026-11-11T11:15Z - Codex (PHANTOM scoring, IV and hold lineage)
- WHAT: Faster PHANTOM scoring through a covering index; IV work acknowledged only after both stores commit; measured contract holding periods preserved, no invented defaults.
- WHERE: scripts\phantom_database.py, phantom_engine.py, phantom_maintenance.py, finalize_phantom_weekly_snapshot.py, intelligent_orchestrator.py, tests\test_evening_saved_repairs.py
- REGISTER: UAT-04, UAT-05 (PHANTOM workstream)
- STATE: built; an uncommitted copy was in the working tree for run 20261111_231951; COMMITTED: 1332983
- BRANCH: phantom-scoring-iv-hold-fixes-20261111; COMMIT: 1332983; FIX_ID: PHANTOM-SCORING; TESTS: 69 pass (commit message); RUN_EVIDENCE: 20261111_231951 ran with it; no artefact found that shows the fix itself; RECEIPT: Enhancements\maintenance_repairs\20261111_evening\repair_receipt.json; MERGED: no

### 2026-11-10T23:16Z to 2026-11-11T15:54Z - Pipeline run 20261110_231648 (Evening and Morning)
- WHAT: COMPLETE. First completed run since 21 Oct. A first start at 23:03Z (20261110_230344) failed the macro publication preflight (macro files missing or changed) and was restarted. Evening verdict DO_NOT_TRADE; Morning verdict TRUST_WITH_CAVEATS, 4 of 5 tradeable rows clean.
- WHERE: data\output\runs\20261110_231648; audit\verify\20261110_231648\
- REGISTER: N17-01 (stale session) reported in every monitor file 26 Oct to 10 Nov
- STATE: complete; run_condition TEST, baseline_eligible false; COMMITTED: n/a
- BRANCH: working tree, uncommitted; RUN_EVIDENCE: 20261110_231648 (COMPLETE); MERGED: n/a

### 2026-11-10T22:46Z - Codex (macro board event order)
- WHAT: Board events sorted by their own source timestamps before the display limit.
- WHERE: macro_board\build_board.py, macro_board\tests\test_event_timestamp_sorting.py
- REGISTER: none
- STATE: built; board rebuilt and checked by Codex on 10 Nov; COMMITTED: 66d0501
- BRANCH: macro-board-event-timestamp-sort-20261110; COMMIT: 66d0501; FIX_ID: MACRO-EVENT-SORT; RUN_EVIDENCE: board rebuild (Codex: ETF_BOARD_EVENT_SORT_VERIFIED_20261110.json); no pipeline run; RECEIPT: none in the repo; MERGED: no

### 2026-11-10T21:59Z - Codex (macro delivery and publication guards)
- WHAT: Exact-byte intake of the three advisory macro files; FULL publication guarded; a busy delivery writer is deferred, not failed.
- WHERE: Run-MacroInputs.ps1, build_macro_json.py, contracts\macro_*.py, contracts\us_money_index_contract.py, config\macro_delivery_v1.json, fred_publication_v1.json, source_recovery_v1.json, 13 test files
- REGISTER: N17-13 (scheduled tasks without the folder) is related, not closed
- STATE: built; most files in the working tree uncommitted; COMMITTED: 4601ce5
- BRANCH: macro-delivery-publication-guards-20261110; COMMIT: 4601ce5; FIX_ID: MACRO-DELIVERY; RUN_EVIDENCE: board rebuild of 10 Nov (Codex: MACRO_FULL_REBUILD_VERIFICATION_20261110.json); RECEIPT: Enhancements\macro_delivery_publication_guards.md (on the branch); MERGED: no

### 2026-10-22 to 2026-11-10 - Pipeline (no runs)
- WHAT: No Evening or Morning run completed between 20261021_222556 and 20261110_231648 (12 sessions). The price store stopped at 21 Oct; the newest hand-off stayed split_2026-10-22_cap5; today_context stayed on 22 Oct. No macro thesis from 27 Oct to 10 Nov. Monitors reported it in every file.
- WHERE: logs\orchestrator.log (no session IDs between the two runs); fix_inbox\2026-10-26_monitor_OPEN.md to 2026-11-10_monitor_POSTCLOSE.md; fix_inbox\2026-10-22_triage.md (appended notes)
- REGISTER: N17-01, N17-13 (both still Proposed)
- STATE: ended 10 Nov; cause not recorded in the repo; COMMITTED: n/a
- RUN_EVIDENCE: none (absence)

### 2026-10-21T22:25Z to 2026-10-22T17:43Z - Pipeline run 20261021_222556 (Evening and Morning)
- WHAT: COMPLETE. Morning final hand-off written at 17:42Z (13:42 ET): 2,783 rows, 7 Lab actionable. Evening verdict DO_NOT_TRADE; Morning TRUST_WITH_CAVEATS, 7 of 7 tradeable rows clean.
- WHERE: logs\orchestrator.log; audit\verify\20261021_222556\ (the run folder itself is no longer under data\output\runs)
- STATE: complete; COMMITTED: n/a
- RUN_EVIDENCE: 20261021_222556 (COMPLETE)

### 2026-10-20T19:24Z - Codex (high-convexity watchlist)
- WHAT: Saved-data high-convexity watchlist added to the Lab.
- WHERE: contracts\lab_convexity_watchlist.py, intelligence-lab\static\convexity-watchlist.*
- REGISTER: none
- STATE: live from the next Lab build; later uncommitted edits to the same files are in the working tree; COMMITTED: f4968c7
- BRANCH: high-convexity-watchlist; COMMIT: f4968c7; FIX_ID: none; RUN_EVIDENCE: NOT FOUND (looked in audit\verify\20261021_222556 and the Lab manifest of 20261110_231648); RECEIPT: none; MERGED: line

### 2026-10-19T21:25Z to 2026-10-20 - Pipeline run 20261019_222539 (Evening and Morning)
- WHAT: COMPLETE. Evening verdict DO_NOT_TRADE; Morning TRUST_WITH_CAVEATS, 7 of 13 tradeable rows clean.
- WHERE: audit\verify\20261019_222539\
- RUN_EVIDENCE: 20261019_222539 (COMPLETE)

### 2026-10-19T13:01Z - Claude Code session (macro inputs)
- WHAT: A Polygon rate limit no longer wipes out market intelligence; bonds run after the producers.
- WHERE: Run-MacroInputs.ps1 and macro input scripts
- STATE: live; COMMITTED: 878cdd8
- BRANCH: avs-fix-001; COMMIT: 878cdd8; FIX_ID: none; RUN_EVIDENCE: NOT FOUND; RECEIPT: none; MERGED: line

### 2026-10-19T09:29Z - Claude Code and Codex (macro inputs; Lab macro desk)
- WHAT: GEX, bonds and rotation flag run by default, -Now with readiness, board input fixes (1789870). Market Mentality macro desk in the Lab; Worker 3 decommissioned and kept (bb65704).
- WHERE: Run-MacroInputs.ps1, macro_board\, contracts\lab_macro_desk.py, intelligence-lab\
- STATE: live; two older branches of the same Lab work (0724adf, a4f0ecc) remain unmerged and differ from this commit in 6 and 12 files; COMMITTED: 1789870, bb65704
- BRANCH: avs-fix-001; FIX_ID: none; RUN_EVIDENCE: NOT FOUND; RECEIPT: docs\LAB_MACRO_DESK_AND_WORKER3_RETIREMENT.md; MERGED: line
```

## Not recoverable from the repo

These changes are reported in inbox files but were made in chats or task prompts, so I cannot give a time, an author or the exact change. They should be confirmed by whoever made them and logged by hand.

| Reported in | What |
|---|---|
| `fix_inbox\2026-11-11_triage.md`, `2026-11-11_UHS.md` | The 11 Nov liquidity tiers (spread 20%, OI 100, $20M a day) adopted in the triage; the 25% rule of 16 Oct superseded |
| `fix_inbox\2026-11-12_lab_first_fix_list.md`, `2026-11-12_fix_A12_monetisation_clock.md`, `2026-11-12_claude_code_brief_fix_B.md` | The Lab-first fix list (A1–A12, B1–B10, C1–C6, D1, D2) and ACK's A12 decision of 12 Nov |
| `fix_inbox\2026-10-22_triage.md` (appended notes to 10 Nov) | Forced triage runs during the outage |
| `fix_inbox\2026-10-23_qqq_exclusion.md` | QQQ exclusion finding |
| `Enhancements\tradeability\AVS-TRADE-001_status_and_decisions_2026-11-13.md` | ACK's decisions of 13 Nov ("accept all three": A12 stands, 1–20 window as a flag, premium cap as a flag) |
| Scheduled tasks | 24 Oct options-fixes reminder (G5-REST): no entry or commit shows it ran |
