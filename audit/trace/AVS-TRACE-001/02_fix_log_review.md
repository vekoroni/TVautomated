# AVS-TRACE-001 · 02 · Fix-log review

Reviewed 14 Nov 2026, read only. Logs are in `data\scratch\workaround\lessons\`.

## 1. The flow, and where it broke

The intended flow (`change_log.md:3-16`, `fix_inbox\README.md`): a chat or monitor writes candidates to the **inbox** → they are merged into the **register** with an ID, owner and status → each change is written to the **change log** → a fix is closed with **closure evidence**.

| Step | Rule | What happened | Broke on |
|---|---|---|---|
| Inbox | Every chat, monitor and deep dive files what it found | **Working.** 96 files from 18 Oct to 13 Nov, 855 candidates. The monitors kept filing through the 12-session pipeline outage. | Not broken |
| Inbox → register | Candidates merged into the register; files moved to `fix_inbox\processed\` | Done **once**, on 17 Oct (40 files, 14 to 17 Oct). Nothing since. `fix_register.csv` was last saved 17 Oct 17:59. | **17 Oct** |
| Change log | One entry per change, before the chat finishes | 13 entries, 16 to 20 Oct. Last saved 20 Oct 10:44. Since then: 9 commits on the line, 12 on branches, three pipeline runs, one failed run, 6,205 credits of backfill, and the uncommitted Morning guard. None logged. | **20 Oct** |
| Closure | Two-level: code evidence and a run artefact | The register has 50 Built and 1 Closed. **None cites a pipeline run ID.** The one Closed row (N17-17) cites a monitor note. | Never worked |
| Read before building | Read the last 7 days of the log and the open register rows | Cannot work when the log is 25 days stale. Result: the same problems re-raised under new IDs (section 3). | 20 Oct |

Why it broke, as far as the files show: the 17 Oct merge was a one-off script run by one Claude Code session (`lessons\merge_register_20261017.py`). No task or agent owns the inbox-to-register step. The change-log rule depends on each chat remembering a closing line; Codex's work from 10 Nov on is recorded in its own evidence folder outside the repo instead.

## 2. Register rows marked Built or Closed: what the evidence proves

51 rows (50 Built, 1 Closed). Full table: `evidence\built_rows_table.md`. Summary:

| What the evidence proves | Rows | Meaning |
|---|---|---|
| CLOSED (code and a run artefact) | 0 | |
| CLOSED_OFFLINE (commit and tests cited) | 4 | G5-MIN, G9-GUARD, UAT-06/07, and N17-17 (process rule, monitor note only) |
| MERGED (commit or script on the line; no test or run cited) | 11 | For example G4 (`666f09c`), X17-04 (`245e87c`), W16-10 (`75eb443`), F14-04 |
| NOT_FOUND (the change is a task prompt, skill or rule not stored in the repo) | 30 | All M16-01 to M16-08, most F14 rows, W16-01, W16-04 to W16-07 |
| Open again (the row's trace item is now proposed, approved or awaiting a decision) | 6 | F14-07, W16-02, W16-03, X17-02, X17-05, D8: the built thing lapsed, was replaced, or rests on a known-wrong input |

**20 of the 50 Built rows were reported again in the inbox after they were marked Built.** These are `CLAIM_NOT_SUPPORTED` in the matrix. The worst:

| Register ID | Marked Built | Later reports | What the reports say |
|---|---|---|---|
| W16-05 resting exit within 5 minutes of a fill | 16 Oct | 45 | OI Dec18 5P: stop 22 Oct, time stop 27 Oct, target 29 Oct; no resting exit to 13 Nov |
| W16-02 25% spread gate | 16 Oct | 19 | 34 of 60 shortlist contracts over the gate on 19 Oct; the rule itself replaced on 11 Nov |
| W16-04 order outcome recorded | 16 Oct | 18 | Criteria met, no order: ADTN, AAL, ATEN, UHS, CPNG |
| F14-01 / W1 earnings date in the hand-off | 14 Oct | 16 | 57 of 60 names null on 19 Oct |
| F14-07 `today_context` board time | 14 Oct | 14 | Stale on 19, 20, 22 Oct; never rolled past 22 Oct |
| G5-MIN American pricing in both lanes | 17 Oct | 11 (matched to G5-REST) | Triage and strategy layer still European, no dividend |
| M16-01 sector AGREE/CONFLICT step | 16 Oct | 9 | Board and Money Index sector conflicts in every macro file |
| W16-01 mid first, one lift | 16 Oct | 8 | |
| M16-04 monitors re-quote kill switches | 16 Oct | 8 | 10Y and credit legs "not checkable live" from 26 Oct |
| X17-02 spread-gate check | 17 Oct | 4 | Its closure evidence, `tests\test_x17_check_triage_spread_gate.py`, now fails by design |
| X17-05 / D8 one register and a change log | 17 Oct | n/a | Both lapsed within three days |

For the other 30 Built rows no later report was found, and no run evidence either: "shown working on a run since" is `NOT FOUND` (looked in `audit\verify\*`, `data\output\runs\20261110_231648`, `20261111_231951`, and the inbox).

Has any run since shown a Built row working? Only three runs completed after 17 Oct (`20261019_222539`, `20261021_222556`, then `20261110_231648` and `20261111_231951` after the outage). The verifier reports for those runs check book rules (R00 to R24), not register fixes, so they do not close any register row.

## 3. Duplicates, contradictions and superseded rules

### Rules that contradict each other

| Topic | The rules in force | Source |
|---|---|---|
| **Spread limit** | 25% of mid, hard gate (W16-02, 16 Oct) | `fix_register.csv:65` |
| | Tiers: A ≤10%, B 10–20%, C >20%, OI ≥100 (11 Nov) | `fix_inbox\2026-11-11_triage.md`; `Enhancements\tradeability\AVS-TRADE-001_codex_brief_2026-11-13.md:48` |
| | 0.18 executable, 0.25 reviewable, 0.08 full size, 0.15 research; "single policy a later decision" | `config\governed_constants_v1.json:177-185` |
| | 0.10 entry spread | `docs\AVS-INT-001_WEEKEND_POLICY_RECEIPT_20260926.md:15` |
| | 15% hard stop, 10–15% repair band (desk gate H4) | `dropbox\macro\coaching\desk_gate\AVS-DESK-GATE-001_weekend_fix_register.md` |
| | Card gate 20%, monitor gate 25%, on the same day | `fix_inbox\2026-11-13_monitor_PRECLOSE.md` |
| | Still 25% in `quickkill.py`, `capture_score.py`; triage notes of 12 Nov still propose 25% | `audit\laneb_fixB\needs_codex.md`; `fix_inbox\2026-11-12_triage*.md` |
| **Spread or OI as a gate vs "rank, don't gate"** | W16-02 and A16-01 drop a contract; CLAUDE.md R11, DOI and the Codex brief say flags only | `CLAUDE.md:9`; `docs\AVS-SD-DOI-001_DYNAMIC_OPTIONS_INTELLIGENCE.md:25`; brief `:69` |
| **Minimum DTE** | "14 DTE default" (L3); "weekly to 90 days" (R6) | `Enhancements\phase8\LESSONS_AND_REQUIREMENTS_REGISTER_20261012.md:25`, `:18` |
| | 14 days left at the q80 exit (F14-03); at q50 and q80 (N17-07) | `lessons\fix_review_2026-10-14.md:11`; `fix_register.csv:100` |
| | Model spec picks DTE 14–45; BUYABLE zone 5–20 conflicts by design | `dropbox\macro\coaching\model\spec\preregistration.md`; `audit\AVS-REV-002_PIPELINE_FUNCTIONAL_REFERENCE_20260901.md:230` |
| | Lab TIER_3 wants DTE ≥ 2 × q80 | `fix_inbox\2026-10-19_CPNG.md`, `2026-10-19_D.md` |
| | "Ignored in mining": **NOT FOUND** in any source read | looked in `lessons\`, `fix_inbox\`, `docs\`, `Enhancements\tradeability\`, `Enhancements\phase8\` |
| **Contract runway** | "The horizon informs contract choice, it never gates it" (ACK 18 Sep) | `config\governed_constants_v1.json:120` |
| | Same block: `value_selection_eligibility` COVERS_PLANNED_HOLD | `:135` |
| | DOI hard-excludes a DTE that cannot outlive hold plus buffer; MON-003 M4 wants zero shorter contracts | `docs\AVS-SD-DOI-001…md:306`; `docs\AVS-SD-MON-003_PATH_AWARE_MONETISATION_AND_EXPRESSION.md:598` |
| | Fix list A1: zero rows expiring before q80. ACK 12 Nov (A12): contract from n, may be shorter than the hold | `fix_inbox\2026-11-12_lab_first_fix_list.md`; `fix_inbox\2026-11-12_fix_A12_monetisation_clock.md` |
| **Macro advisory-only vs exceptions** | Display-only, never a gate, score or rank | `CLAUDE.md:12`; `config\governed_constants_v1.json:222` |
| | Triage ranks by money tag (W16-03, Built); "money side wins ties" (L5); AGAINST cards at half premium (P3) | `fix_register.csv:66`; `phase8\LESSONS…md:27`; `lessons\lessons_learnt_week_2026-10-12.md:29` |
| | The QQQ exception (ACK, 12 Nov): **NOT FOUND in the repo** | see `06_ETF_fix_package_for_Codex.md` E5 |
| **Quote age** | Flag, never gate (ACK) | `Enhancements\tradeability\AVS-TRADE-001_status_and_decisions_2026-11-13.md:65` |
| | `freshness_max_seconds` 900; Morning refused outside 09:35–09:45 ET (uncommitted) | `config\governed_constants_v1.json:110`; `config\morning_pricing_policy_v1.json` |
| **Premium cap** | $5 stays, account-based cap open (W16-08); about $1.50 from the account (P9); "a daily parameter" (L3); a flag only (ACK 13 Nov) | `fix_register.csv:71`; `lessons_learnt_week_2026-10-12.md:52`; `phase8:25`; status sheet `:62` |
| **Close entry vs resting order** | Close entry is one option, not the rule; winners lost for lack of a resting limit; a resting option limit fills at the wrong stock level | `fix_inbox\2026-10-18_thesis_book.md`; `2026-10-23_monitor_*.md`; `2026-10-19_NNE.md` |

### Superseded

| Superseded | By | Recorded where |
|---|---|---|
| 25% spread rule (W16-02, X17-02) | 11 Nov tiers | Only in `fix_inbox\2026-11-12_lab_first_fix_list.md` (B4); the register still says Built |
| "Contract must cover q80" (fix list A1; 13 Nov fix 5) | ACK's A12 decision, 12 and 13 Nov | `Enhancements\tradeability\…status…md:56`; not in the register |
| Desk-gate F1.3 (reachable-target monetisability as governed), F2.3, F2.5, C2 | AVS-SD-FIX-002 v1.2 sections 2 and 21 | `docs\AVS-SD-FIX-002_MONETISABLE_PIPELINE_REMEDIATION.md` |
| ALG-13 sizing | Retired in v1.2; UAT step F5 still tests it | `docs\requirements\AVS-REQ-FIX-002_Annex_A_algorithms_and_models.md` |
| `focus_v3` drop of QQQ/SPY | Lab-first hand-off (not yet live) | `audit\laneb_fixB\99_report.md` |

### Same problem, several IDs (merged in the matrix)

| Problem | IDs | Trace row |
|---|---|---|
| GARCH differenced horizon | Desk D1, F1.1, WP1, REQ-WP1-01/02, ALG-01, UAT-D44, DISC-F12, Approved Item 4, INT C3, "GARCH D1", 13 Nov fix 4 | TR-008 |
| Outcome ledger | Desk NEW-2, F3.5, QA R2, WP7/7A/7B, REQ-WP7-01/02, UAT-D33, RCA-13, Approved Items 6 and 7, DOI-7, phase8 R3 and L7, W4, N8, T1, A16-03, W16-12, G8, AVS-LEDGER-001, 13 Nov fix 9 | TR-010 |
| Stale quote treated as executable | Desk D18, F0.2, QA R8, REQ-WP0-04, ALG-12, UAT-D02, UAT-D06, RCA-02, 13 Nov flaw 4 | TR-005 |
| Spread units and tiers | Desk D9 and D15, F1.5, F1.6, REQ-WP1-03, UAT-D10, RCA-01, DEC-3, W5, W6, W16-02, A16-01 | TR-004 |
| Sector and money-tag map | W2, R14-04, A16-02, phase8 R4, ETF E4 | TR-034 |
| Hand-off after the trigger closed | D5, R14-12, A16-05, phase8 R1 | TR-036 |
| Earnings date in the hand-off | W1, F14-01, N17-04, phase8 R5 | TR-032 |

### Claims that later evidence does not support

| Claim | Where | Contradicted by |
|---|---|---|
| Cumulative GARCH horizon "implemented and offline-tested" (26 Sep); "PASS" in the Stages 2–5 claim sheet | `docs\AVS-INT-001_HORIZON_UNIT_REPAIR_20260926.md:3`; `audit\avs_fix_002\stage2_5\STAGES2_5_CLAIM_SHEET.md:5` | Differences still at `layer3_forward_variance.py:690-692` on the last commit; fixed only by `fff3a3e` on 13 Nov |
| "STAGE 1 COMPLETE" | `audit\avs_fix_002\stage1\` claim sheet | AVS-TD-001 verdict REJECT: 0 closed, 36 open, 4 P0 (`audit\td\AVS-TD-001\verdict.md:5`) |
| Stage 6 "OFFLINE COMPLETE" | Stage 6 closure report | Calibration script, report and table absent (UAT-D23); 0 of 3,252 candidates eligible for maturation (UAT-D33) |
| Lane B report: all seven items PASS | `audit\laneb_fixB\99_report.md` | True on stored run `20261111_231951` only; live flow LEGACY; B5, B8, B9 not built |

## 4. Inbox candidates never triaged into the register

- **96 files, 855 candidates** (706 fixes, 117 rules, 21 decisions for ACK, 11 research items), dated 18 Oct to 13 Nov. None has been moved to `processed\`.
- 453 match an existing register row (the same problem, still open or wrongly marked Built). The most repeated: N17-01 stale session (61), W16-05 resting exits (45), N17-03 Tastytrade metric traps (31), W16-02 spread gate (19), W16-04 no order placed (18), N17-13 scheduled tasks (17), F14-01 earnings date (16).
- **402 have no register row.** By source: ticker deep dives and other notes 152, monitors 110, macro checks 101, triage 39.
- The full list, one line per candidate with file and line: `evidence\inbox_candidates_A.jsonl`, `evidence\inbox_candidates_B.jsonl`, and the trace row for each in `evidence\trace_sources.csv`.

The three largest unregistered groups: macro thesis and board defects repeated build after build (145, `TR-039`); the kill-switch acceptance rule (24, `TR-038`); the 52-week flag missing from triage (20, `TR-040`).

## 5. Decisions waiting on ACK

| # | Decision | Raised by | Trace |
|---|---|---|---|
| 1 | **Morning late start: refuse the run (as now built, uncommitted) or flag it** | `config\morning_pricing_policy_v1.json`; status sheet `:65` | TR-006 |
| 2 | Switch `value_selection_mode` to ACTIVE; rank by return per premium dollar | status sheet `:63-64`; `config\governed_constants_v1.json:136` | TR-003 |
| 3 | Tastytrade live quotes on cards and at entry | status sheet `:66` | TR-007 |
| 4 | Rank in-window names first inside the Lab | status sheet `:67` | TR-D (decision 8) |
| 5 | Success tests (TRADE cards over 50% after 30 cards; 10 rows a day) | status sheet `:68` | TR-D (decision 9) |
| 6 | Retire or rewrite the X17 test and the old-layout scripts | `audit\laneb_fixB\triage_prompt_update_2026-11-13.md` section 3 | TR-013 |
| 7 | Triage on the Evening or the Morning publication | same file, section 5 | TR-012 |
| 8 | May the macro board set ETF direction (QQQ exception)? Record it or withdraw it | `06_ETF_fix_package_for_Codex.md` | TR-E5 |
| 9 | ETFs first: a lane or the rank; leveraged and inverse products | same | TR-E12, TR-E16 |
| 10 | Kill-switch acceptance rule: two closes or a band | 8 inbox files, 3–12 Nov; fix list C6 | TR-038 |
| 11 | Account-based premium cap and open-premium budget | `fix_register.csv:71` (W16-08) | TR-014 |
| 12 | Parallel-run retirement criteria (N1); define or retire ARMED (D6); Bigdata credits (D7) | `fix_register.csv:3`, `:28`, `:29` | TR-R002, TR-R011, TR-R012 |
| 13 | Are exit tickets read at all (OI position)? | `fix_inbox\2026-11-05_monitor_PRECLOSE.md` | TR-030 |
| 14 | Paste the monitor and triage prompt changes (X17-01, N17-13, the 13 Nov triage block) | `lessons\monitor_task_changes_20261017.md`; `triage_prompt_update_2026-11-13.md` | TR-041, TR-029, TR-012 |
| 15 | Approve the change-log backfill; name the integration branch | `05_change_log_backfill.md`; `03_branch_review.md` section 7 | TR-022 |
| 16 | Older, still open: contract-selection bands (DEC-2), Discovery liquidity pre-filter, fee schedule, model activation, PI-LAB decisions | `audit\rca\AVS-RCA-003\DECISIONS_FOR_ACK.md:19`, `:43`; `config\governed_constants_v1.json:285`, `:69`; `docs\AVS-SD-PI-LAB-001…md:135-140` | TR-D0248, TR-D0249, TR-D0524, TR-D0504, TR-D0717 |

## 6. What would make the logs work

Not built; for ACK to decide.

1. **One owner for inbox to register**, on a schedule (for example the post-close monitor or a weekly Claude Code task), with the count of untriaged files shown in `avs_day.ps1 status`.
2. **The change-log line written in the same commit** (AVS-CHANGELOG-001 rule 1) for both Codex and Claude Code, and Codex's evidence records copied into `audit\fix_receipts\` in the repo.
3. **A `run_evidence` column in the register**, filled only with a run ID or a dated Lane B artefact. "Built" then means CLOSED_OFFLINE and nothing more.
4. **One ID scheme from now on**, or at least the scheme prefix written with every ID (section 5 of the matrix summary lists the collisions).
