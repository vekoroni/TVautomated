# AVS-ENH-2026-11-21 — Wave 0 verification

21 November 2026. Read-only. Scope: the eight Wave 0 items of `data\scratch\workaround\lessons\fix_inbox\2026-11-21_claude_code_brief_enhancements.md` (F-01 to F-05, F-09, F-10, F-29). The other items of the brief are not verified yet.

No file was changed, no script was run, and no broker or provider was called. Every order, fill and cancel below comes from the monitor-written `execution_review.csv` or the fix inbox; none was confirmed with the broker.

`W` = `data\scratch\workaround`.

## Facts that apply to several items

- **Where decisions live:** `W\handoff\<folder>\decisions\<TICKER>.json`. Files: 9 in `lab_2026-11-16`, 8 in `lab_2026-11-18`, 16 in `lab_2026-11-20`, none in `lab_2026-11-19`. The repo-root `decisions\` holds only `NVDA.json`.
- **Order tickets** are written by `W\collect_decisions.py:247, 289` and only when `avs_day.ps1` runs `preclose` (`:417`) or `eod` (`:426`). The newest ticket file is from 12 November. No `lab_*` folder has one, so those two steps did not produce output on 16 to 20 November. Whether they were run and failed, or were not run, is not established: there is no log.
- **`collect_decisions.py` reads one hand-off folder** (`:198-214`). A card written on 16 or 18 November that is still live never reaches a 20 November ticket sheet.
- **`W\monitor\execution_review.csv`** exists: 304 rows, 15 October to 20 November. No repo code writes it. The claude.ai monitor task does.
- **Nothing in the repo can read working orders.** `bridge\tastytrade_readonly_mcp.py:66` allows quotes and market metrics only. `tools\journal_real_fill.py` takes hand-typed fills.
- **Register:** five of the eight items map to rows already marked Built (W16-04, W16-05, M16-01, M16-04, M16-05, F14-07). The symptoms have recurred, so those rows are built but not holding.

## Verdicts

| ID | Verdict | Evidence | Where the gap is | Register / inbox |
|---|---|---|---|---|
| F-01 | **CONFIRMED.** The record exists; the ticket does not. | `execution_review.csv`, session 19 Nov: 19 entry rows, all `order_placed=no`. Criteria met with no order: QQQ 570P, HSBC 85P, BAC 49P, NVDA 140P, and BAC 49C "MISSED". 18 Nov has four more (BAC, UPS, QQQ, EL). Only fill: SMCI 25C at 2.26. Correction to the brief: SMCI 24P was priced out (mid 2.375 over the 2.00 cap), not criteria-met. The brief's P&L percentages were not re-derived. | No script produces a 15:40 ticket. The reason is free text in `window_state` / `reason`; there is no reason-code column. Ticket step not producing output (see above). | W16-04 Built (16 Oct, "15:45 ET close-entry tickets"). Mentioned in 35 inbox files, 22 Oct to 20 Nov. |
| F-02 | **CONFIRMED** from monitor records. | 19 Nov SMCI row: GTC sell 2.94 working, guards fired, action "EXIT at the mid (~1.89)". 20 Nov row: "no sell working (2.94 GTC cancelled 20:14Z)". The 2.03 / 1.89 / 1.45 sequence is in `fix_inbox\2026-11-20_monitor_OPEN.md`. | The exit plan is on the card (`one_contract_exit{target_stock, target_option_price, stop, time_stop}`, 16 of 16 on 20 Nov; `branches[].gtc` on 4 of 16). No decision file has an order id or a resting-order field. | W16-05 Built; N17-15 Proposed ("add hold state and resting-exit fields"). 69 inbox files. |
| F-03 | **CONFIRMED** from monitor records. | 20 Nov GRAB: filled 0.15 at 20:30:42Z, action "Rest GTC STC 1 at 0.25 now". 18 Nov SMCI: "NO resting GTC sell at 2.95". 18 Nov OI: "7 sessions without a resting sell". Also: `GRAB.json` still shows `order_placed=""` and `fill=null` after the fill. | The resting-exit rule is text only (`collect_decisions.py:59`, ticket line `:267`). No paired entry-and-exit ticket exists. | As F-02. |
| F-04 | **PARTLY.** An order for 2 was entered and cancelled; the fill was 1. | `GRAB.json` `size: 1`. 20 Nov GRAB row: "x2 at 0.14/0.15 cancelled 20:20:54Z, x1 at 0.15 Day received 20:21:49Z". | No quantity check anywhere. `size` is an integer in 31 files and free text in two. `execution_review.csv` has no quantity column. | Not in the register. One inbox file. |
| F-05 | **CONFIRMED.** | `macro_kill` is in 0 of 33 decision files and in no code. 20 Nov GRAB row: "FILLED; MACRO BROKEN after the fill". The nearest field, `macro_dependency.kill_switch`, is on 7 of 9 files (16 Nov), 2 of 8 (18 Nov) and 0 of 16 (20 Nov). | The ticket prints `macro_dependency` and static text (`collect_decisions.py:163, 268`). `macro_line()` (`:173-185`) reads fired switches from `macro_state.json`, which is stale (F-09). | M16-04, M16-05 Built. 37 inbox files. |
| F-09 | **CONFIRMED.** | `W\macro_state.json`: modified 16 Nov 10:51Z, `session` 2026-11-16, `written_by` "B3 triage batch 1, FORCED rerun". Eight kill switches, two fired. `dropbox\macro\thesis\` has 18 and 19 Nov theses and no 20 Nov file. | Written only by a triage chat. Read in code only by `collect_decisions.py:173-185, 268`. `check_triage.py` never reads it; `avs_day.ps1` does not mention it. | M16-01 Built. 93 inbox files. |
| F-10 | **CONFIRMED.** | `today_context.json` written 20 Nov 13:56 and never rewritten. Null or empty: `cards`, `order_tickets`, `split_triage_files`, `deep_dive_prompts`, `macro_context*`, `triage_check`, `strategy_layer`, `comparison`, `preclose_*`. Five of these were only stale: the files landed between 14:07 and 14:43, after the context was written. | The only writer is `Write-Context` (`avs_day.ps1:213-217`), which runs when an `avs_day` step runs. `collect_decisions.py` reads the context (`:196`) and never writes it. | N17-01 Proposed (15 Oct, same symptom); F14-07 Built. 96 inbox files. |
| F-29 | **CONFIRMED.** | Board row files: 7 in 3 shapes (16 Nov), 7 in 6 shapes (18 Nov), 0 (19 Nov), 23 in 14 shapes (20 Nov). Payload sits under `data`, `row`, `rows[]` or at top level. File names vary. | No collector: `board_row` appears in no `.py` or `.ps1` file. | Not in the register. 10 inbox files. |

## What cannot be fixed by editing repo files

| Item | Part outside the repo | Owner |
|---|---|---|
| F-01 | The 15:40 push itself; the monitor's write to `execution_review.csv`; placing the order | ACK chat (scheduled task), ACK |
| F-02, F-03 | Reading working orders and cancels; the "REPLACE order" push; whether the broker supports linked orders | ACK chat (monitor), ACK |
| F-04 | A guard at order time | Monitor check after the order appears, or the ticket text |
| F-05 | Tagging MACRO AT RISK during the session | Monitor prompt |
| F-09 | Rewriting `macro_state.json` from the newest thesis | Triage prompt, or a new repo step |
| F-10 | Monitor fall-back to the decisions folder | Monitor prompt |
| F-29 | The write to the Card Watch Board | A chat with access to the board |

## Not determined

- Broker truth for any order, fill, cancel or quantity.
- Whether Tastytrade supports a buy with an attached sell, or a target and stop that cancel each other, on single-leg options.
- The text of the scheduled-task prompts and the board's row schema. Neither is in the repo.
- Whether `avs_day.ps1 preclose` and `eod` were run and failed on 18 to 20 November, or were not run.
