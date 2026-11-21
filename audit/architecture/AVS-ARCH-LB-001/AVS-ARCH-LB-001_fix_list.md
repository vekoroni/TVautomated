# AVS-ARCH-LB-001: Lane B to accurate intelligence mining. Fix list for code analysis

Version 1.1, 21 Nov 2026 (1.1 adds section 7: fixes carried forward from earlier registers). Author: Claude (chat), from the discovery session with ACK.
Status: DISCOVERY AND ARCHITECTURE. Nothing is to be built from this document yet.

## 0. What Claude Code is asked to do

Analyse every fix below against the existing code and data, and return the evidence needed to plan the build.

Rules:
- Read-only. Do not edit, move or delete any file. Do not run the pipeline, the orchestrator, `avs_day.ps1`, the weekend chain or any script that writes. Read code, read data, run read-only probes on copies if needed.
- No credits: no Bigdata.com, MarketData or Anthropic calls.
- Every claim carries evidence: `path:line` for code, file name plus row count or field name for data. Missing evidence is reported as UNKNOWN, never assumed.
- Do not redesign what ACK has decided (section 2). Challenge it only where the code shows it cannot work, and say why.
- Repo root: `C:\Users\ACKVerissimo\AVSHUNTER-Intelligence`. Lane B lives in `data\scratch\workaround`. Hand-off folders: `data\scratch\workaround\handoff\lab_<session>`.
- Write all output under `audit\architecture\AVS-ARCH-LB-001\`.

For each fix, return:
1. Current behaviour (what the code does today, with `path:line`).
2. Root cause.
3. Every file and function that would change, and every consumer that reads what changes.
4. Options (at least two where they exist), with a recommendation.
5. Effort (S under 2 h, M half a day, L a day, XL more), and risk of breaking something else.
6. Dependencies on other fixes (IDs).
7. How the fix would be proved: the test, and the run artefact that shows it firing.

Then return one build plan: waves in dependency order, what can run in parallel, who should build each part (Claude Code, Codex, or Claude chat for skills and the board page), and the open questions for ACK.

## 1. The target chain

```
Intelligence Lab (governed book)            owner: Codex (A fixes)
  -> Lab hand-off (build_lab_handoff.py)    owner: Lane B
  -> Triage script (new, A6)                numeric levels from Lab + live quote
     + chat judgement                       narrative, market players, lifecycle
  -> Deep dive (chat, skills, plugins)      writes ONE card record (JSON)
  -> Card record checker                    rejects a record with missing fields
  -> Renderer                               card HTML from one fixed template
  -> Feed (local, read-only)                card records to the board
  -> Card Watch Board                       live states, review queue, triage pipeline
  -> Board logs                             card log + triage call log (learning source)
  -> Scoring                                accuracy of cards and calls, by stage
```

The principle: the chat does the judgement, and the scripts handle format, levels and transport. One record per card is the single source of truth. The HTML card, the board row, the decision file and the ledger columns are all produced from it.

## 2. Decisions already taken by ACK (do not reopen)

- D1. The card becomes a data record; the HTML card is generated from it (21 Nov).
- D2. Learning comes from the board: the identified trades on the board test the logic and accuracy, and what the board sees must be logged (21 Nov).
- D3. The board must be viewable in Chrome, like the trade cards. Chosen design: a quote relay (the desktop board saves snapshots; Chrome reads them) (21 Nov).
- D4. Every triaged name still gets a deep dive; the rank and the board's NOW/NEXT call set order only.
- D5. No step is a hard gate until confidence is earned; flags, not filters.
- D6. Card standard (unchanged): status strip; tabs 1 Trade card, 2 Evidence and challenge, 3 Ticker news; thesis sentence ("Because [macro], [sector] is [X], and [ticker] is [Y], so this option should [move] by [date], unless [invalidation]"); both sides where feasible; 7-stage lifecycle; market-player read; Soul of the Chart; all timeframes in one story; "For the trade" notes with an on/off switch; 52-week check; liquidity tier; dark text on white.
- D7. Updated cards merge the prior card; nothing may be dropped.
- D8. Commands for ACK are full PowerShell lines.
- D9. Codex owns the Lab and macro fixes; Lane B fixes go through Claude Code from a written brief.

## 3. Evidence found on 21 Nov (starting point, verify it)

- 20 Nov hand-off (`handoff\lab_2026-11-20\handoff.md`): 2,746 Lab rows in, 2,593 on the hand-off, all MANUAL_REVIEW (no GO_LIMIT); BLOCKED 1 and CONTRACT_REPAIR 152 excluded; `monetisation_state` NOT_PUBLISHED on every row; Lab fields `monetisation_n_q50`, `monetisation_n_q80`, `monetisation_threshold` not published; `lb_time_fit` CONTRACT_EXPIRES_BEFORE_MEDIAN_TIME 1,109; NO_CONTRACT 561; OVER_CAP 759; window OUTSIDE_WINDOW 1,475 on PROXY_Q50 basis.
- `lab_handoff_settings.json` places 114 focus tickers first. Top names carry Lab ranks 1413 (TTEK), 2192 (HSBC), 2355 (CNR), while BAC is 4 and USB is 8. Ten focus names are not on the hand-off but were still triaged (ANDE, APO, CTVA, DOLE, DOW, EXK, KMB, MTH, SPB, TWI).
- Batch triage CSVs have about 90 columns. `half_target`, `level`, `invalidation` are numbers; `trigger` and `kill` are sentences. The board had to parse triggers from text (155 of 158 parsed, 15 uncertain).
- Board-row files exist in at least six shapes: `{doc_id, collection, data}`, the same plus `call_leg_row`, `{rows:[{doc_id,data}]}`, `{rows:{id:data}}`, `{doc_id, collection, row}`, and a flat row. Some carry `"limit": "mid"` (text in a number field). File names vary (`board_row_<date>_<T>_<SIDE>.json`, `board_row_<date>_<T>.json`, `board_row_<T>.json`, `board_rows_<T>_<date>.json`).
- Five 20 Nov rows were never put on the board: AWK_CALL, ES_CALL, ES_PUT, GILD_CALL, GILD_PUT.
- Card scan of 21 cards (18 and 20 Nov), keyword based, so verify: thesis "so this option should" part missing in 11; notes on/off switch missing in 8; GTC ladder missing in 7; lifecycle missing in 4 (18 Nov, before the rule); market players missing in 2; max pay missing in 2; two-sided ticket missing in 2; Lab rank missing in 20; link to the board row missing in 15. At least three tab markups. Text length 33k to 81k characters.
- Decision ledgers 16, 18, 19 and 20 Nov have no `_outcomes.csv`; the last outcome run was 13 Nov. `track_outcomes.py` (v2, 12 Oct) scores stock levels only.
- `today_context.md` for 20 Nov shows triage_check, deep_dive_prompts, cards and order_tickets blank although they exist.
- The board page exists only inside the artifact (1,491 lines, one file). There is no copy in the repo and no version history outside the artifact.

## 4. Fix list

### A. Lab input (scope for Codex; Claude Code analyses, does not design the Lab)

| ID | Problem | Questions for the analysis |
|---|---|---|
| A1 | Every hand-off row is MANUAL_REVIEW; no GO_LIMIT. | Where is `lab_verdict` set? Is MANUAL_REVIEW by design for the evening publication, or a fallback? What would let the Lab separate ready rows from review rows? |
| A2 | Monetisation fields not published (`monetisation_state`, `_n_q50`, `_n_q80`, `_threshold`). | Which producer should write them? Do they exist anywhere in the run folder? |
| A3 | 1,109 contracts expire before the median time to target. | How does contract selection choose the expiry? Is the time-to-target (q50/q80) available to the selector? Which DTE rule wins? |
| A4 | 561 rows with no contract, 152 CONTRACT_REPAIR. | Breakdown by reason (spread, OI, no chain, premium). Which are recoverable with a wider delta or DTE band (see RCA-003 / DEC-2)? |
| A5 | Window flag OUTSIDE_WINDOW on 1,475 rows, basis PROXY_Q50. | Is the proxy right? Does it penalise weekly and monthly setups wrongly? |
| A6 | UNRESOLVED direction rows reach the hand-off with no target or contract (CNR, DNOW, BKNG, VCTR in batch 1). | Should they be triaged as two-sided, or flagged? Where does direction stay UNRESOLVED? |

### B. Lab hand-off

| ID | Problem | Questions |
|---|---|---|
| B1 | 114 focus tickers override the Lab order. | Who writes `focus_tickers` and when? Design options: a carry-forward flag column instead of reordering; a cap; a drop rule after N sessions with no card. Effect on batch membership. |
| B2 | Excluded names are still triaged. | Where do the extra names come from (merged weekly triage, previous ledger)? Should they carry an explicit `carried_from` field? |
| B3 | `today_context.md` blanks. | Which step should fill each field, and why didn't it on 20 Nov? |
| B4 | Hand-off columns needed by the new triage script. | List the Lab fields the triage script needs (trigger level, trigger kind, stop, invalidation, q50/q80, contract, OI, spread) and whether each is already on `handoff.csv`. |

### C. Triage (A6: triage as a script plus chat judgement)

| ID | Problem | Questions |
|---|---|---|
| C1 | Triage is built in chat, so it is slow and varies. | Design `triage_from_lab.py`: which of the about 90 columns can be filled by code from the hand-off, the price store and a live quote, and which need judgement. Give the split column by column. |
| C2 | Trigger and stop exist only as sentences. | Define numeric columns: `trig_kind` (above, below, zone, fired, pre), `trig_v`, `trig_lo`, `trig_hi`, `stop_dir`, `stop_v`, `half_v`, `inval_v`. Where does each value come from? |
| C3 | No schema or version for the triage CSV. | Propose `triage_v1` with required columns, types and a version column. What reads it today (`check_triage.py`, prompts builder, merged weekly file, board import)? |
| C4 | Deep-dive prompts are written by the chat triage. | Can the prompts be generated from the triage CSV by a template? What must stay in the prompt (pack path, Lab fields, macro context, rules)? |
| C5 | Merged weekly triage file is assembled by hand. | Can the script build `merged_triage_week_<from>_to_<to>.csv` from the batch files and the board's states? |
| C6 | Lifecycle stage, market-player read and narrative are not columns. | Add `lifecycle_stage` (1 to 7), `player_read`, `narrative_catalyst` as judgement columns. Which consumers need them? |
| C7 | `check_triage.py` v5 checks the old layout. | What changes for the new numeric columns and `triage_v1`? |

### D. Card record (decision D1; absorbs the board-row problem)

| ID | Problem | Questions |
|---|---|---|
| D1 | Cards are free-form HTML; format drifts and data is dropped. | Draft `card_record_v1` JSON schema covering every part of the card standard (D6) and everything the board, the decision files, the ledger and the order tickets read today. Mark each field required or optional, with type. Inventory the fields the board page reads (see F section) so nothing is lost. |
| D2 | No fixed template. | Design the renderer (`render_card.py`): one template producing the status strip, the three tabs, the notes switch, dark text on white, the thesis sentence assembled from its parts. Which existing card is the best visual base? |
| D3 | Nothing checks a card. | Design `check_card.py`: required fields, numbers where numbers are expected, OCC format and underlying, expiry after card day, dates ISO, both sides present or a reason, thesis parts present, lifecycle 1 to 7, sources listed. Error vs warning list. |
| D4 | Updated cards are rewritten whole, and data is lost in the merge. | Design versioning: `card_<date>_<T>_v<N>.json`, `supersedes`, a field-level diff between versions, and a rule that a later version cannot silently drop a field the earlier one had. How do the current `_v1`, `_v2`, `_base` HTML files map onto this? |
| D5 | Board rows exist in six shapes and are typed separately from the card. | Derive the board row from the record. Map every board field (`rungs`, `stop`, `cancel`, `gtcSteps`, `gates`, `manual`, `review`, `built`, `exit`, `until`, `from`, `at1550`, `spreadMaxPct`, `stockDvM`, `supersedes`, `outcome`, `group`) to a record field. List the shapes found and how old files would be read. |
| D6 | Decision files and ledger columns are filled separately. | Can `decisions\<TICKER>.json`, the ledger decision columns and the order tickets (`collect_decisions.py`) be produced from the record? What changes in `collect_decisions.py`? |
| D7 | Skills tell the chat to write HTML. | List the skill instructions that must change (avshunter-ticker-mining, avshunter-card-notes, avshunter-card-notes-retrofit, avshunter-board-row, avshunter-trade-guard, avshunter-52w-resistance-check) so the chat writes the record. Claude chat will write the skill edits; Claude Code lists what each must say. |
| D8 | Existing cards. | Is back-conversion of the 18 and 20 Nov cards to records feasible (parse the HTML), or should records start from the next session? Estimate per approach. |
| D9 | Card links. | Cards are also published as claude.ai artifact links. How does the rendered HTML get published, and does the link go into the record? |
| D10 | Speed (ACK's rule: cards must be fast). | Estimate whether writing a record plus rendering is faster or slower than writing HTML. What can be pre-filled from the triage row so the chat writes less? |

### E. Card feed to the board

| ID | Problem | Questions |
|---|---|---|
| E1 | The board cannot read PC files; rows are copied by hand and some never arrive. | Design a local read-only feed server (MCP over stdio, like the Tastytrade server) exposing the card records and board rows. Language (Python with no dependencies, or Node using the SDK already in `C:\Users\ACKVerissimo\tastytrade-mcp\node_modules`). How is it registered in the Claude desktop app? |
| E2 | Import rules. | Insert missing rows only; never overwrite a row edited on the board; remember imported IDs so a retired or deleted row is not re-imported; a start date so old folders are not swept in. Edge cases: a newer card version for a row already on the board. |
| E3 | Triage to the board. | Can the same feed publish the triage rows (`triage_v1`) so the board's Triage pipeline no longer needs a chat import? |

### F. Card Watch Board (the board page; Claude chat edits it, Claude Code analyses the code)

Claude Code cannot open the artifact. Claude chat will export the current page to `audit\architecture\AVS-ARCH-LB-001\board_page_v19.html` for this analysis.

| ID | Problem | Questions |
|---|---|---|
| F1 | The board page exists only in the artifact. | Propose keeping the source in the repo (`board\card_watch_board.html`) with a version line in the change log. |
| F2 | Chrome view (D3). | Design the relay: which state the desktop board saves (quotes, positions, orders, tape, triage quotes), how often, document size and split, how Chrome shows its age, and how only one engine writes. |
| F3 | Card log (D2). | Per card, traded or not: time first in entry zone, trigger fired, option bid high and low after the trigger, stop or half target first, window expiry, every state change with time. Storage layout and size per day. |
| F4 | Triage call log (D2). | NOW, NEXT, LATER call per triaged name at fixed times (for example 09:45, 12:00, 15:45 ET). Storage and size. |
| F5 | Reading the logs back. | CSV download from the board, and a reader script for scoring. |
| F6 | Row checks on the board. | Mirror the card checker on import; show rejected rows instead of hiding them. |
| F7 | Smaller board items. | Open interest check on contracts; live dollar volume for the stock tier; regime banner (VIX, breadth); lifecycle stage and player read shown on the row; retiring the October rows. |
| F8 | Page size and safety. | 1,491 lines in one file. Which parts should be split into sections that can be checked separately? |

### G. Outcomes and scoring (accuracy)

| ID | Problem | Questions |
|---|---|---|
| G1 | Ledger outcomes stopped on 13 Nov. | Confirm. Decide with ACK whether ledger scoring continues beside the board logs (all ledger rows, no selection bias) or is retired. |
| G2 | `track_outcomes.py` v2 scores stock levels only. | Design v3: card option outcomes (entry fill or would-have-filled, best bid after entry, return at the half target, stop first or target first), using `capture_option_closes.py` and the board logs. |
| G3 | Triage calls are never scored. | Score NOW vs NEXT vs LATER on later moves, to set the 1.5% and 4% bands from data. |
| G4 | Accuracy targets are not defined. | Propose the measures ACK will judge "accurate intelligence mining" by, for example: trigger hit rate by call; option return at the half target; win rate (ACK's bar: at least 75% wins, with losers not eating the profit); results by lifecycle stage, liquidity tier and side. ACK sets the targets. |
| G5 | Missed trades. | Score cards not taken alongside cards taken (ACK wants both). |

### H. Runbook and operations

| ID | Problem | Questions |
|---|---|---|
| H1 | `Run-WeekendChain.ps1` ends at packs. | Which new steps join the chain (triage script, prompts, feed refresh, scoring) and in what order? |
| H2 | `avs_day.ps1` steps. | New steps or flags needed; the full PowerShell line for each. |
| H3 | Shared change log. | Confirm where it lives and that every build step writes one line. |
| H4 | Tests. | Existing `test_laneb_*` files: which need updating; new tests needed for the triage script, the checker, the renderer, the feed and scoring. |

## 5. Output files

Under `audit\architecture\AVS-ARCH-LB-001\`:
- `analysis.md`: one section per fix ID with points 1 to 7 from section 0.
- `card_record_v1_draft.json`: the draft schema (D1), with a field map to every current consumer.
- `triage_v1_columns.csv`: column, type, source (code or judgement), current location, consumer.
- `board_fields.csv`: every field the board page reads, and where it would come from in the record.
- `build_plan.md`: waves, dependencies, parallel work, owner per item, effort, risks, and open questions for ACK. It covers the new fixes in section 4 and every carried-forward item in section 7 that is still open.
- `carried_forward.csv`: the reconciliation in section 7.

## 7. Fixes carried forward from earlier registers (reconcile all of them)

Section 4 came from the 21 Nov discovery only. Earlier fixes that were raised and never implemented, or built and never verified, must go into the same plan. The sources, as found on 21 Nov:

| Source | What it holds | State found |
|---|---|---|
| `data\scratch\workaround\lessons\fix_register.csv` | 137 rows (last full merge 17 Oct; V18 rows added 18 Nov) | 86 open: 83 Proposed, 1 Approved, 2 Decision. 50 Built, of which 51 rows carry the disposition "Verify existing" (built, closure never verified on a run). 1 Closed. V18-01 to V18-10 (vol and Vanguard review, 18 Nov) show release references and replays while their status still says Proposed |
| `data\scratch\workaround\lessons\fix_inbox\` (not `processed\`) | 116 files from 18 Oct to 20 Nov that were never merged into the register | About 900 FIX CANDIDATE lines. Many repeat daily (monitor OPEN, PRECLOSE and POSTCLOSE files), e.g. fired stops never executed (OI 22-23 Oct), fills on a contract not on the card (VALE), resting sells not at the card target, `macro_state.json` and `today_context.json` not refreshed, post-close quotes overstating spreads, monitor runs missed |
| `lessons\fix_inbox\2026-11-12_lab_first_fix_list.md` | A1 to A11 (Lab, Codex), the B items (Lane B), C items (macro into the Lab and triage) | A12 (monetisation clock) merged 14 Nov per the change log. A1 to A11 status unknown; the 20 Nov hand-off still shows A1 (contract expires before hold), A4 (repair contradiction), A6 and A7 symptoms |
| `audit\laneb_fixB\99_report.md` and `needs_codex.md` (12 Nov) | Fix B results and what Codex must supply | Six Lab fields Lane B depends on (monetisation n, contract alternatives, one repair state, cluster field, and others). `tests\test_x17_check_triage_spread_gate.py` fails 4 of 5 since the 25% rule was removed and needs retiring or rewriting. Lane B scripts still on the old hand-off layout: `strategy_layer.py` (S1 to S6 is not run in Lab mode, so cards carry no strategy row), `compare_split_handoffs.py`, `preclose_trigger_scan.py` (uses the ledger half target, not the Lab's), `track_outcomes.py`, `quickkill.py`, `capture_score.py` (25% rule) |
| `lessons\fix_inbox\2026-11-18_vol_vanguard_review.md` | Vol and Vanguard findings | Mapped to V18 rows; verify |
| `lessons\change_log.md` | What was changed | Last entry 14 Nov. Changes after that (board v17 to v19, `check_triage.py` v5 macro check of 20 Nov, the triage import to the board) are not logged |

What to do:
1. Read every open register row, every unmerged inbox file and the open items of the 12 Nov documents. De-duplicate the inbox lines (same problem on different days = one item, with first and last date seen and the count).
2. For each item, check the code and data now and give it one state:
   - `DONE_VERIFIED`: the fix is in the code and a run artefact shows it firing (name both).
   - `BUILT_NOT_VERIFIED`: in the code, no run evidence yet (say what run would prove it).
   - `OPEN`: not done.
   - `SUPERSEDED_BY <id>`: covered by a section 4 fix (give the ID), or by a later decision.
   - `OBSOLETE`: no longer applies (say why, for example the step was retired).
   - `DECISION_FOR_ACK`: cannot move without ACK.
3. Write `carried_forward.csv` with: source, source_id, first_seen, last_seen, times_seen, lane, summary, state, evidence (`path:line` or artefact), maps_to (section 4 ID or new ID `CF-nn`), owner suggestion, effort.
4. Every item left `OPEN` or `BUILT_NOT_VERIFIED` goes into `build_plan.md` beside the section 4 fixes, in the same waves.
5. Do not edit `fix_register.csv`, do not move inbox files to `processed\`, and do not write to `change_log.md`. The monitoring chat owns the register. Propose the register update as a separate file, `register_update_proposal.csv`, for ACK to approve.

Themes already visible, to make sure they are not lost:
- Execution discipline: fired stops not executed; fills on contracts not on the card; resting sells not at the card target; decided but not placed (N2, N7, R14-14, N17-16).
- Context freshness: `today_context` and `macro_state` stale across sessions (N17-01, plus inbox lines from 23 Oct onward).
- Outcome capture and scoring: W4, W16-12, A16-03, G8, and the monitor's option closes (overlaps G1 to G5 in section 4).
- Contract and hold timing: A1 to A3 of 12 Nov, A16-04, N17-07, N17-11 (overlaps section 4 A3).
- Vol inputs: V18-01 to V18-10.
- Strategy layer S1 to S6 switched off by the Lab hand-off (needs_codex section 4).
- Industry and ETF mapping: W2, A16-02, R14-04.

## 6. Open questions for ACK (for the plan, not for Claude Code to answer)

1. The measurable targets for "accurate intelligence mining" (G4).
2. Whether ledger scoring of every Lab row continues beside the board logs (G1).
3. Whether existing cards are back-converted to records (D8).
4. The carry-forward rule for focus tickers (B1).
5. Who builds each wave (Claude Code, Codex, Claude chat).
6. Whether the strategy layer (S1 to S6) is brought back on the Lab hand-off or retired.
7. What happens to the failing X17 spread-gate test.
