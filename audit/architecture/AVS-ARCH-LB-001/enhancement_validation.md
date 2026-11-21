# AVS-ARCH-LB-001-VAL: validation of the 20-21 Nov fixes and enhancements

21 Nov 2026. Read-only. Nothing was run, no provider was called, no existing file was changed. Detail per item is in `enhancement_validation.csv`; proposed register rows are in `register_entries_proposal.csv`.

## The most important finding

**Seven item IDs in this list already exist in `fix_register.csv` with a different meaning: D1, G1, G2, G3, G4, G6 (register lines 23, 115, 116, 117, 111, 128), and E1 is also a triage class on the board and the end-of-day prompt named in register row R14-14.** A merge under these IDs would overwrite or confuse open rows. The proposal file uses the prefix `LB-` (for example `LB-G1`). ACK to confirm the naming before any merge.

Second: none of the 37 items is in the register, the inbox or the change log under its own ID. The fix list is the only record, and it does not record the six LIVE board features as built items.

## Counts

| Status given | Items |
|---|---|
| LIVE | 6 |
| ACCEPTED | 11 |
| PROPOSED | 14 |
| DECISION | 4 |
| NOT_CHOSEN | 1 |
| Evidence to verify (D1c) | 1 |
| **Total** | **37** |

| Built state | Items | Which |
|---|---|---|
| LIVE_VERIFIED | 5 | V-01, V-02, V-03, V-04, V-06 |
| LIVE_UNVERIFIED | 5 | V-05, G4, G7c, CF-05, CF-06 |
| NOT_BUILT | 27 | all others |

Classification: 25 ENHANCEMENT, 12 DEFECT_FIX (V-03, G1, G4, G5, G7c, D1c, CF-01 to CF-06).

"LIVE_VERIFIED" here means the code is present in `board_page_v19.html` (1,491 lines, exported 21 Nov 10:12). It is a static read. The page was not opened, the board database is not in the repo, and the page carries no version string, so "v17", "v18", "v19" cannot be matched to code. The export folder is untracked in git.

## Not recorded

| Item | What is missing |
|---|---|
| R-02 | The localhost option and the reason it was not chosen are written nowhere |
| V-01, V-02, V-03 | Not recorded as items; the fix list only says "board v17 to v19" are missing from the change log |
| V-04, V-05, V-06 | Referred to in the fix list (supersedes, Triage pipeline, the bands) but not recorded as built |
| W-03 | The chain steps are in the fix list (H1); the rule "run the chain only after the enhancements" is not |

## Challenges and contradictions

| Item | Note |
|---|---|
| V-05, R-01, L-01, L-02 | The board's loops stop when the page is not visible (`:1456`, `:1039`). Pricing, the relay and both logs work only while the desktop board is open in front. The design must say so, and gaps must be logged as gaps |
| V-06 | CLOSED says "nothing to dive" and has no copy-prompt button (`:962`, `:1008`), against "every name still gets a deep dive". A card over 5 sessions old and still in its window is neither DONE nor VALIDATE (`:963-964`) |
| G2 | The settings file holds 124 focus names; 114 reach the hand-off |
| G7c | The blanks for cards, order tickets and triage check are true: those files were never produced for 20 Nov. The new refresh filled prompts and triage files |
| G7a | A VIX "Fear" and breadth read already exists on the board (`:1357-1367`) |
| W-01 | OI is already read in three places; only the card-row tier ignores it |
| F1 | A copy of the page is now in the repo folder, untracked and unversioned |
| D1c | 24 cards found, not 21; seven of nine counts differ (table below) |
| CF-01 | 126 unmerged inbox files to 20 Nov, not 116 |
| CF-03 | The test file has 4 tests, not 5; by reading, all 4 would fail. Register row X17-02 still cites it as closure |
| CF-04 | The change log has five entries after 14 Nov (four on 15 Nov, one on 18 Nov). The named changes and today's commit 1323f35 are still unlogged |
| CF-05 | Register N2 is not an execution row. None of the three named themes is built; two neighbouring flags are |

## LIVE items that failed verification

- **V-05**: the section, the 60-second loop and the eight calls are in the code. The "158 rows in the board database" cannot be seen from the repo. The local merged triage file has 158 rows, which is consistent but is not the board.
- **V-06**: verified, with the two rule differences above.

## Built on 21 Nov, not yet run on a session (commit 1323f35)

| Item | Built | Not built |
|---|---|---|
| G4 | `collect_board_rows.py`: one file, one shape | Row validator; any write or sync to the board |
| G7c | `refresh_context` in `ticket_ready.py`, called by `collect_decisions.py` | The files the blank keys point to |
| CF-05 | Flags for a fill with no resting exit and for a quantity mismatch | Fired stop not executed; fill on a contract not on the card; resting sell below target |
| CF-06 | Stale macro state flagged in `check_triage.py` and `ticket_ready.py` | Anything that rewrites `macro_state.json` (still dated 16 Nov) |

## Counts re-made from the files

| Count | Prompt | Found |
|---|---|---|
| Hand-off rows, all MANUAL_REVIEW | all | 2,593 of 2,593 |
| Monetisation fields blank | all | 2,593 |
| Expire before median time | 1,109 | 1,109 |
| No contract | 561 | 561 |
| CONTRACT_REPAIR (excluded) | 152 | 152 |
| Focus tickers | 114 | 124 listed, 114 placed |
| Ledger outcome files 16-20 Nov | none | none; last written 14 Nov for the 11 and 12 Nov ledgers |
| Open register rows | 86 | 86 |
| Built, never verified | 51 | 50 Built; 51 rows marked "Verify existing" |
| Unmerged inbox files | 116 | 126 |

## D1c card scan (keyword based, low confidence)

Cards: unversioned `*_deep_dive_<date>.html`, 8 in `lab_2026-11-18` and 16 in `lab_2026-11-20`.

| Check | Keyword (case-insensitive) | Missing, found | Prompt |
|---|---|---|---|
| Thesis part | `so (this\|the) … (option\|call\|put) should` | 12 of 24 | 11 of 21 |
| Notes switch | `notesw`, `notes-toggle`, `hideNotes`, `id="nt"` in the HTML | 8 | 8 |
| GTC ladder | `GTC` | 7 | 7 |
| Lifecycle | `lifecycle`, `life cycle`, `7-stage` | 7 | 4 |
| Players | `market player`, `player read`, `who is buying/selling` | 7 | 2 |
| Max pay | `max pay`, `most you may pay`, `never above` | 4 | 2 |
| Two-sided | `both sides`, `two-sided`, `other side` | 6 | 2 |
| Lab rank | `lab rank`, `lab_rank` | 23 | 20 |
| Board-row link | `board row`, `board_row`, `Card Watch Board` | 17 | 15 |

A keyword can miss wording. The drift is real; the exact numbers are not settled.

## Overlaps with existing register rows

| Item | Register rows |
|---|---|
| CF-06, G7c | N17-01 (same problem, Proposed), F14-07, M16-01 |
| CF-05 | N7, R14-14, N17-16, W16-04 |
| CF-03 | X17-02, W16-02, A16-01 |
| CF-04, CF-01 | X17-05, D8 |
| G5, L-01, A-01 | W4, A16-03, W16-12, N8, G8, N7, W16-10, X17-01, N1 |
| G1 | D1 (register), A16-04, N17-07, N17-11 |
| W-01 | N17-07, A16-01 |
| D1, D1a | N6, A16-07, N17-15, R14-14 |

CF-06 is left out of the proposal file because N17-01 already holds it. D1c is left out because it is evidence for D1, not a fix.

## Not determined

- What is in the board database (triage row count, October rows, whether AWK, ES and GILD rows arrived).
- What the saved `avshunter-board-row` skill says (file not found on disk).
- Why the outcome steps were not run after 14 Nov.
- Whether the Lab branch of `avs_day.ps1` reaches the strategy call.
- Whether the export equals the page now live in the artifact.

## Decisions for ACK

- **G2**: keep the focus names first, or move to a flag column in Lab order; and if kept, the cap and the drop rule (the list is 124 names today).
- **G5**: whether ledger scoring of every Lab row continues beside the board logs or is retired.
- **A-01**: the measures and the target number for each, and over how many sessions they are judged.
- **CF-02**: restore the strategy layer S1-S6 on the Lab hand-off, or retire it and remove its steps.
- **CF-03**: retire the X17 spread-gate test, or rewrite it to pin the 11 Nov liquidity tiers (and correct register row X17-02 either way).
