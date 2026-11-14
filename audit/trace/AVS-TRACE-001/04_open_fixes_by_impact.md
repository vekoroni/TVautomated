# AVS-TRACE-001 · 04 · Open fixes, by monetisation impact

Open items only, most important first, grouped under the 13 Nov flaws. Detail and sources for every trace ID are in `01_traceability_matrix.csv`.
Acceptance is always two-level: **code evidence** (commit on the integration line, tests named) and **run evidence** (a run ID or a dated Lane B artefact that shows it working).

Nothing here is built by this review. Pipeline items need an approved root cause and design first (CLAUDE.md).

## Before anything else

| Trace | Item | Owner | Smallest next step | Acceptance |
|---|---|---|---|---|
| TR-006 | **Morning refuses to price outside 09:35–09:45 ET** (uncommitted, on no branch, live in the working tree) | ACK decides; Codex | ACK confirms "refuse" or changes it to "flag and price"; Codex commits it on a named branch either way | Code: a commit holding `domain\morning_pricing_window.py` and its config. Run: one Morning inside the window and one deliberately late, each with the outcome ACK chose |
| (branches) | The working tree is the code that runs and matches no branch | ACK; Codex; Claude Code | Step 0 of `03_branch_review.md` section 7: name the integration line; each owner commits its uncommitted work | `git status` shows no modified tracked files before a run; the run's `run_meta.json` cites a commit |

## Flaw 1 · Thesis clock too slow for 1 to 20 sessions

| Trace | Item | Owner | Smallest next step | Acceptance |
|---|---|---|---|---|
| TR-001 | Trading-window flag in the pipeline (`trade_window_state`, basis N_Q50 or PROXY_Q50) | Codex | Design note for brief item W3; bounds in config | Code: field in the Lab manifest `card_fields`. Run: counts by state on one normal cycle against Lane B's 591 in / 1,499 out |
| TR-FL-A2, TR-FL-A9 | Planned hold is q80 converted from bars; three clocks on one row | Codex | Say in writing whether `da9a922` closes them; if so, merge and run | Run: hold, q50 and q80 in sessions on ten rows checked by hand |
| TR-E2 (in TR-001) | ETF arrival times from stock-style structure (15 of 62 within 20 sessions) | Codex | ETF package item E2, after GARCH D1 has run | Run: share of ETF rows with q50 ≤ 20 against the 24% baseline |

## Flaw 2 · Runway is a penalty; selection in SHADOW

| Trace | Item | Owner | Smallest next step | Acceptance |
|---|---|---|---|---|
| TR-009 | Monetisation clock published (A12) | Codex | Merge `fix/ac-reliability-20261112` then `feat/a12-monetisation-clock-20261112`; publish on the next run | Code: `b709669` on the line. Run: `monetisation_state` other than NOT_PUBLISHED; share of rows with an n (saved-data check gave 39 of 2,800 at +20%) |
| TR-002 | `contract_covers_n` and the shadow pick from n | Codex | Design note for brief item W2. Blocked by TR-009, and by its thin coverage: say what the proxy is when n is blank | Run: count of rows with `contract_covers_n = YES` beside 1,005 / 481 expiring early; selected `contract_symbol` unchanged |
| TR-003 | SHADOW to ACTIVE; rank by return per premium dollar | ACK | Decide after three sessions of shadow picks; CLAUDE.md rule 5 gates apply | Decision recorded in `config\governed_constants_v1.json` with its evidence |
| TR-011 | Two or three alternatives on the card | Codex | Commit the uncommitted projection fields; publish `contract_alternative*` | Run: Lane B `check_triage.py` raises no WARN when triage uses a published alternative |
| TR-FL-A3, TR-FL-A4, TR-FL-A5 | Hold does not count down; repair state contradicts itself; Morning keeps names blocked | Codex | Map each to a commit or mark open | Run: the three behaviours on named rows |

## Flaw 3 · Illiquid contracts kept; one liquidity standard

| Trace | Item | Owner | Smallest next step | Acceptance |
|---|---|---|---|---|
| TR-004 | The 11 Nov tiers owned once, in config, used by pipeline and Lane B | Codex (pipeline), Claude Code (Lane B reader) | ACK confirms the 11 Nov tiers replace all six limits in section 3 of `02_fix_log_review.md`; thresholds move to `governed_constants_v1.json` | Code: one definition, no literals. Run: tier counts equal Lane B's 99 A / 248 B / 1,697 C on the same publication |
| TR-E11 | Tier on an in-session quote; post-close quotes labelled | Codex / Claude Code | Add the quote time beside every tier | Run: no tier without a quote time |
| TR-013 | X17 test and old-layout scripts still on 25% | ACK decides; Claude Code | Retire or rewrite | `tests\test_x17_check_triage_spread_gate.py` passes or is removed with a logged decision |
| TR-014 | Premium cap as a pipeline flag; account-based cap | Codex (flag), ACK (cap) | Brief item W4 | Run: `premium_cap_state` on every row; over-cap lane visible (848 rows on 12 Nov) |

## Flaw 4 · Stale quotes

| Trace | Item | Owner | Smallest next step | Acceptance |
|---|---|---|---|---|
| TR-005 | Delayed feed (900 s) against a 900 s freshness limit | ACK (data plan), Codex | Decide: real-time entitlement, or label every quote DELAYED and widen nothing | Run: verifier rule R19 passes on a Morning that starts on time |
| TR-006 | Morning window | as above | as above | as above |
| TR-007 | Tastytrade re-quote at entry | ACK | Decide; it conflicts with "options data from MarketData only" unless scoped to the live check triage already does | Decision recorded |
| TR-041 | Option closes captured at 16:20 ET widen; no 15:50 ET snapshot | ACK (monitor prompt), Claude Code | Paste the capture rules (register X17-01, `lessons\monitor_task_changes_20261017.md` section 1) | Artefact: `monitor\option_closes.csv` rows carry a session-close flag |

## Flaw 5 · Specified fixes not shipped

| Trace | Item | Owner | Smallest next step | Acceptance |
|---|---|---|---|---|
| TR-008 | GARCH D1 | Codex | Merge `fff3a3e` (4 files, no overlap). Then check the consumers UAT-D44 lists, including `domain\pretrade_focus.py:248-253` | Code: commit on the line. Run: 5, 10 and 20-session expected moves rise with the horizon on every row; ratios no longer 0.414 / 0.586 |
| TR-010 | Outcome ledger for every card | Claude Code | Start AVS-LEDGER-001 item L1 (score the six unscored ledgers), no new provider calls | Artefact: every `decision_ledger_*.csv` has `_outcomes.csv`; card count equals cards on disk |
| TR-020 | PUT base rates (`ev_engine_v2.py:92-94`) | Codex | Root cause and design note for ACK | Run: PUT and CALL base rates differ where history differs |
| TR-021 | Dropped match dimensions (`actuarial_query.py:653, 667, 1002-1016`) | Codex | Root cause and design note | Run: matched dimensions listed per row |

## Other, high impact

| Trace | Item | Owner | Smallest next step | Acceptance |
|---|---|---|---|---|
| TR-012 | Lane B on the Lab hand-off: built, not live | ACK, Claude Code | ACK pastes the triage block and runs `avs_day.ps1 status -LabHandoff` before the next Evening | Artefact: `handoff\lab_<session>` built from a new publication; `checktriage` report |
| TR-015 | Station quarantine | Codex | Merge `58a4904` first (cut from the current tip) | Run: an Evening that completes with a quarantined ticker listed in the drop-off audit |
| TR-030 | Resting exits never placed (OI held since 13 Oct; 45 reports) | ACK | Decide whether exit tickets are read; place or close the position | Order record |
| TR-031 | Criteria met, no order (18 reports) | ACK, Claude Code | First Lab-first cycle with B10 decision records | Artefact: no `CARD_BUILT_DECISION_MISSING` at the close |
| TR-036 | Hand-off inside the trigger session | Codex / Claude Code | Measure the lag on the first Lab-first cycle | Run: trigger date against hand-off date per row |
| TR-017 | A/C reliability | Codex | Merge `da9a922`; list the fix-list items it closes | Run: Lab republished with the corrected clocks |
| TR-E5, TR-E12, TR-E16 | ETF decisions | ACK | See `06_ETF_fix_package_for_Codex.md` section 8 | Decisions recorded in the repo |
| TR-I-B-contract_choice, -exit_rules, -ranking, -quote_freshness, -liquidity, -hold_window; TR-I-A-* | 42 unregistered inbox candidates on contract choice, exits, ranking, quotes, liquidity and hold | Not assigned | Triage each into the register (`evidence\trace_sources.csv` lists them) | Register rows with owners |

## Other, medium and low impact (open, not urgent)

| Trace | Item | Owner |
|---|---|---|
| TR-028, TR-029 | `today_context` did not roll on 13 Nov; scheduled tasks without the folder, monitors late | Claude Code; ACK |
| TR-032 | Earnings date null in the hand-off (regression of a Built fix); re-check on the Lab hand-off | Claude Code |
| TR-033, TR-034, TR-040 | Correlation and beta from the store; sector and money-tag map; 52-week flag | Claude Code; Codex |
| TR-035 | NO_DIRECTION rows handed over as CONFIRMED | Codex |
| TR-037 | G5-REST pricing bundle approved for 24 Oct: no trace that it was done | Claude Code |
| TR-016 | Production eligibility: merge last | Codex |
| TR-018, TR-019 | PHANTOM branches; 12 Nov backfill deferred (40 entry chains, 20 path quotes) | Codex |
| TR-022, TR-023 | Change log and register lapsed | all agents; ACK names an owner |
| TR-024 to TR-027 | Macro branches | Codex |
| TR-038, TR-039 | Kill-switch acceptance rule; 145 macro defects with no closure | ACK; macro chat |
| TR-E1, E3, E6, E14, E17 to E23 | ETF package | Codex |

## Document-defined requirements (not re-verified)

641 further rows (`TR-D*`) are open by their own documents' account: 432 proposed and 209 approved, of which 355 are tagged high impact. The largest sets are AVS-REQ-FIX-002 (REQ, NFR, ALG), the AVS-TD-001 defects (UAT-D01 to D59, verdict REJECT) and the MON-003 and INT-001 registers from September. Most of what they ask for is already carried by the headline rows above (GARCH, quote freshness, spread units, outcome ledger, monetisability). I did not check each against today's code; before any of them is scheduled it should be checked against the headline row it belongs to.
