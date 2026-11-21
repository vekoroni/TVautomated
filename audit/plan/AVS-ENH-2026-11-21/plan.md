# AVS-ENH-2026-11-21 — Wave 0 build plan

21 November 2026. **For ACK's go-ahead. Nothing is built.** Evidence for every item is in `verification.md`.

Target: in place before Monday 23 November, 15:40 ET. All changes are in Lane B (`data\scratch\workaround`), owned by Claude Code. None touches a file Codex has open.

Standing rules kept: advisory only (ACK places every order), flags and labels and no hard gates, nothing invented, tests first, commands given as full PowerShell lines.

## What the verification changes about the brief

- **Five of the eight items are regressions of fixes already marked Built** (W16-04, W16-05, M16-01, M16-04, M16-05, F14-07). The pattern is the same each time: the fix was a rule written into a prompt or a ticket line, and nothing in code checks it.
- **Three root causes cover seven of the eight items:**
  1. The ticket and context steps only run when `avs_day.ps1` is run by hand, and they did not produce output on 16 to 20 November.
  2. `collect_decisions.py` reads one hand-off folder, so cards from earlier sessions that are still live drop out.
  3. `macro_state.json` and the board are written only by chats, with no file-side check or collector.
- **F-04 is smaller than stated:** the order for 2 was cancelled and the fill was 1.

## Build items, in order

Each item starts with a failing test in `data\scratch\workaround\test_laneb_*.py`. Effort: S under 2 hours, M half a day.

| # | Item | Change | Files | Test and proof | Effort |
|---|---|---|---|---|---|
| 1 | **F-10** context kept current | A small Python context refresher that `collect_decisions.py` calls after every decisions write, and that `avs_day.ps1` uses in place of its own `Write-Context` logic for the same fields. `cards`, `order_tickets`, `split_triage_files`, `deep_dive_prompts`, `macro_context*` and `triage_check` are filled from what is on disk at that moment. | `collect_decisions.py`, `avs_day.ps1`, new `refresh_context.py` | Test: files that land after the first context write appear after a refresh. Proof: Monday's `today_context.json` shows cards and tickets after the first deep dive. | M |
| 2 | **F-01** ticket ready list | `collect_decisions.py` reads every hand-off folder that still has a live card, not one folder. A new output `ticket_ready_<session>.md`: only criteria-met tickets, one exact order string each. A reason code column proposed for `execution_review.csv` (PLACED, NOT_PLACED with reason, VETOED_SPREAD, VETOED_MACRO, PRICED_OUT). | `collect_decisions.py`, `avs_day.ps1` (`preclose`) | Test: a live card from an earlier folder is on the list; a priced-out card is not. Proof: Monday's list names the same contracts the monitor marks criteria-met. | M |
| 3 | **F-02, F-03** exit travels with the entry | Each ticket carries its exit as a second order string beside the entry (target GTC, and the stop or guard exit), built from `one_contract_exit` and `branches[].gtc`. Decision files gain `resting_exit` (price, placed time, order id as typed by ACK or the monitor, state). A card with a fill and no resting exit is listed first, flagged. | `collect_decisions.py`, decisions schema (`STANDARD_FIELDS :46`) | Test: a filled card with no resting exit is flagged; a card with one is not. Proof: GRAB and SMCI would both have been flagged on 20 Nov (replayed from the saved files). | M |
| 4 | **F-04** quantity | `size` read as an integer whatever its form. The order string carries the quantity. A fill whose quantity differs from the card size is flagged unless the card has a scaling note. A quantity column proposed for `execution_review.csv`. | `collect_decisions.py` | Test: the two free-text sizes parse to 1; a fill of 2 against size 1 is flagged. | S |
| 5 | **F-05** macro kill on the ticket | For each card, compare its `macro_dependency.kill_switch` with the fired switches in `macro_state.json` and write `macro_kill` (FIRED, CLEAR, NOT_ASSESSED with the reason) into the ticket's first line and the cards file. A card with no `macro_dependency` is NOT_ASSESSED, never CLEAR. | `collect_decisions.py` | Test: a fired switch the card depends on gives FIRED; a missing dependency gives NOT_ASSESSED. Proof: replay on 20 Nov files shows 16 of 16 NOT_ASSESSED (no kill switch on any card), which is the true state. | S |
| 6 | **F-09** stale macro state is visible | `check_triage.py` flags (WARN, never blocks) when `macro_state.session` is not today. `collect_decisions.py` labels fired switches read from a stale file with its date. `avs_day.ps1 status` shows the age. | `check_triage.py`, `collect_decisions.py`, `avs_day.ps1` | Test: a state file dated five days back gives the warning and the label. Proof: Monday's check shows the age if the triage has not rewritten it. | S |
| 7 | **F-29** board rows collected | A new `collect_board_rows.py`: reads every `board_row*.json` in the hand-off folders, accepts the shapes found (payload under `data`, `row`, `rows[]` or top level), writes one `board_rows_<session>.json` in a single shape, and lists rejected files with the reason. The write to the board stays a chat step, now from one file. | new `collect_board_rows.py`, `avs_day.ps1` | Test: the 23 files of 20 Nov normalise to one shape with a count that reconciles; a malformed file is listed, not dropped. | M |

Items 1 to 6 change `collect_decisions.py`, so they are built one after another in that order. Item 7 is independent.

## What I need from ACK before building

1. **F-01:** a push-only "ticket ready" list (my assumption, since the pipeline is advisory), or pre-staged orders?
2. **F-02, F-03:** does your Tastytrade order flow support a buy with an attached sell, or a target and stop that cancel each other, on single-leg options? If yes, the ticket shows one linked order. If no, it shows two strings and the flag in item 3 covers the gap.
3. **Who runs `preclose`.** The ticket step produced nothing on 16 to 20 November. Either it is added to a scheduled command, or the context refresher in item 1 also builds the ticket list whenever a decisions file changes. I recommend the second, so the list does not depend on a manual step.
4. **F-09:** flag the stale state (this plan), or also have a repo step rewrite `macro_state.json` from the newest thesis? The second needs the thesis file format to be fixed first.

## What stays with the chats (not buildable here)

- The 15:40 push, and the monitor writing reason codes and quantity into `execution_review.csv`.
- The monitor reading working orders and pushing on a cancelled exit.
- The triage prompt rewriting `macro_state.json` each session.
- The card template making `macro_dependency` (with a kill switch) and an integer `size` mandatory, and one board-row shape.
- The write to the Card Watch Board.

I will give you the exact text for each prompt change with the build, for you to paste.

## Acceptance and rollback

- **Offline:** each item's test, plus a replay on the saved 16, 18 and 20 November hand-off folders written to a scratch folder.
- **Real session:** Monday 23 November. The ticket ready list, the context and the board rows file are checked against the monitor's own record for that day.
- **Rollback:** every change is in Lane B scripts and adds output files. Reverting the commit restores the previous behaviour; no ledger, card or decision file is rewritten.

## Risks

- `today_context.json`, the decisions files and `execution_review.csv` are shared with the chats and the monitors. New fields are added, none renamed, so existing readers keep working.
- Codex is editing pipeline files in the same working tree. Lane B commits are staged by file name.
- A flag that fires on every card is noise. Item 5 will show NOT_ASSESSED on all cards until the card template carries the kill switch, so the template change should land the same day.

## Not in this plan

The rest of the brief: Part A items outside Wave 0, Part B and Part C. They are not verified yet. Waves 1 to 4 follow after Wave 0 is accepted.
