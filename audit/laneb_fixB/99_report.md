# Lane B Fix B: report (Lab-first hand-off)

Written 12 Nov 2026 by Claude Code for ACK. Branch `laneb/lab-first-handoff` (from `f4968c7`). Not merged, not pushed, nothing scheduled, triage task not edited.

## 1. Result

All seven items are built, tested and committed. Every acceptance check passed on run `20261111_231951`, Lab revision `f70092078e3f4a548955a08cbec131f6`.

| Item | Result | Evidence |
|---|---|---|
| B1 | PASS | 25 rows (20 random + HSBC, CPNG, PH, AZZ, NXST), 3,725 comparisons against the Lab API, 0 differ |
| B2 | PASS | One target set and one contract set in `handoff.csv`; `legacy_compare.csv` reproduces CPNG |
| B3 | PASS | Order rebuilt from `lab_verdict` and `lab_rank` alone equals `lb_order`; counts and batch 1 below |
| B4 | PASS | WARN on CPNG contract and first profit; matching rows pass; no 25% rule left |
| B6 | PASS | HSBC and CPNG `lab_card.json` equal the Lab API (145 fields, 4 families); batches 1 and 3 in one session folder |
| B7 | PASS | After `packs -Batch 1` then `-Batch 3`: batch 1 still ready, `packs_ready_batches` = 1, 3, one folder |
| B10 | PASS | Lists HSBC (card, no decision file) and CPNG (has one). On ACK's go-ahead (12 Nov, 23:05Z) the HSBC record was created; CPNG's file is byte-for-byte unchanged |

**The live daily flow is still on the old hand-off.** I saved `handoff_source = LEGACY` in `day_settings.json` after testing, because the triage scheduled task still expects the old columns. Section 6 has the one line that switches it on.

## 2. Commits

| Commit | Item | Change |
|---|---|---|
| `1e43e6b` | B0 | Baseline: the 18–20 Oct uncommitted edits to `avs_day.ps1`, `check_triage.py`, `collect_decisions.py`; first commit of `tools\ticker_pack.py`; the plan |
| `7f604d1` | B1, B2, B3 | `build_lab_handoff.py`, `lab_reader.py`, tests |
| `572a904` | B6 | `tools\ticker_pack.py`, tests, `B6_lab_card_check.md` |
| `60d0511` | B4 | `check_triage.py`, tests, `triage_interface.md`, `B4_check_triage_output.md` |
| `99ee568` | B10 | `collect_decisions.py`, tests, `B10_dry_run_output.txt` |
| `26c6f3e` | B2, B7 | `avs_day.ps1`; two small fixes to `build_lab_handoff.py` |
| (this commit) | — | `needs_codex.md`, `99_report.md` |

One departure from "commit per item": B1, B2 and B3 share one script, so its first commit carries all three. `B1_spotcheck.csv` is on disk but not committed (the repo ignores `.csv`).

Tests: 48 new, all pass, one file per process.

| File | Tests |
|---|---|
| `data\scratch\workaround\test_laneb_lab_handoff.py` | 26 |
| `data\scratch\workaround\test_laneb_check_triage.py` | 9 |
| `data\scratch\workaround\test_laneb_collect_decisions.py` | 7 |
| `data\scratch\workaround\test_laneb_ticker_pack.py` | 6 |

**One older test now fails:** `tests\test_x17_check_triage_spread_gate.py`, 4 of 5. It pins the 25% rule that B4 removes. It is outside my files, so I left it. See `needs_codex.md` section 3.

## 3. Per item

### B1. Hand-off from the Lab's publication
- New `build_lab_handoff.py` and `lab_reader.py` (one read-only reader used by the hand-off, the packs and the tests).
- Refuses, with the reason, when the manifest is missing, not `COMPLETE`, the database is missing or its sha256 is not the manifest's.
- Output `data\scratch\workaround\handoff\lab_2026-11-12\`: `handoff.csv` (145 Lab fields + `lb_` columns), `handoff_evidence.jsonl` (73 MB), `handoff.md`, `receipt.json`, `legacy_compare.csv`, `pack_commands\`.
- Session = first XNYS session after the Lab's bar date (2026-11-11 → 2026-11-12). The Lab's own timing reference date agrees.
- Acceptance: `audit\laneb_fixB\B1_spotcheck.csv`, 3,725 comparisons, 0 differ. Seed 20261112.

### B2. One target, one contract
- Target `anticipated_level`, first profit `anticipated_level_q50`, contract `contract_symbol`. No half target, no cap, no own pick.
- `legacy_compare.csv` for CPNG: old half target 13.4579 against Lab first profit 10.9258; old contracts `CPNG270219P00015000` (hand-off), `CPNG270219P00018000` (options tool), `CPNG270319P00018000` (triage) against Lab `CPNG270219P00017000`. `differs = True`.
- Across the 165 old names that are in the Lab hand-off: first profit differs on 165, contract on 124, target on 11.
- `avs_day.ps1 evening` calls `build_lab_handoff.py`. `-LegacyHandoff` runs the old chain; `-LabHandoff` switches back. The choice is saved in `day_settings.json`.
- The decision ledger is still built in Lab mode as the outcome record (no credits). The options tool is not run.

### B3. Flags, order, groups, batches
Counts on the 2,132 hand-off rows:

| Flag | Counts |
|---|---|
| `lab_verdict` | MANUAL_REVIEW 2,129, GO_LIMIT 3 (PH, MCK, NXST) |
| `lb_window_flag` | IN_WINDOW 591, OUTSIDE_WINDOW 1,499, NOT_ASSESSED 42 |
| `lb_window_basis` | PROXY_Q50 2,132 |
| `monetisation_state` | NOT_PUBLISHED 2,132 |
| `lb_time_fit` | CONTRACT_EXPIRES_BEFORE_MEDIAN_TIME 1,005, CONTRACT_OUTLASTS_Q80 558, CONTRACT_EXPIRES_BEFORE_Q80 481, blank 88 |
| `lb_over_cap` | WITHIN_CAP 1,196, OVER_CAP 848, NO_QUOTE 88 |
| `lb_saved_gate` | A 99, B 248, C 1,697, NO_CONTRACT 88 |
| `lb_stock_tier` | A 1,139, B 334, C 659 |
| `lb_repair_conflict` | True 455, False 1,677 |
| `lb_runway_note` | Trigger age over q50: 219 |
| `lb_group_role` | PRIMARY 79, ALTERNATE 2,053 |

Tier C on the saved quote: 1,045 on open interest (under 100 or not recorded), 616 on spread over 20%, 36 with no bid or ask.

**Only 35 of 2,132 rows are clear on all four flags** (in window, within cap, gate A or B, stock A or B). No row is dropped for it; the flags are information.

72 batches of 30. Batch 1, in order:

PH, MCK, NXST, TWST, NOK, MET, GWW, LHX, HSBC, BAC, VLO, BR, USB, SE, UHS, BKNG, EWBC, PGNY, SNA, PNC, AMGN, VCTR, QCRH, EXPD, WTS, CPNG, FITB, CBRL, ISRG, GRAB

Batch 1 flags: 8 in window, 9 within cap, gate A 2 / B 7 / C 21, stock A 28 / B 1 / C 1, 26 contracts expire before q80, 15 repair conflicts.

Two readings of the tier rule that I applied; correct me if wrong:
- "Premium under 1.50" is the mid of the quote.
- A quote with spread ≤10% that fails the 0.10 width is B; one that fails the OI test is C.

### B4. `check_triage.py`
- 25% rule removed. Liquidity tiers A, B, C on the triage's live quote (B and C are WARN).
- `trade_contract` must be the Lab `contract_symbol`; target must equal `anticipated_level`; first profit must equal `anticipated_level_q50`. Otherwise WARN.
- `--batch N`, `--all`, `--triage-folder`. Reads the Lab layout or the old one.
- Run on today's batch 1–3 files against the Lab hand-off (`audit\laneb_fixB\B4_check_triage_output.md`), 90 names, verdict PASS WITH WARNINGS:

| Line | Rows |
|---|---|
| Contract is not the Lab contract | 26 |
| First profit is not the Lab's | 88 |
| Target is not the Lab's | 6 |
| Live tier B | 15 |
| Live tier C | 11 |
| No contract named | 50 |

- CPNG: WARN on contract (`CPNG270319P00018000` against Lab `CPNG270219P00017000`) and on first profit (13.4579 against 10.9258). Its target matches, so no target line.
- Rows that match pass: HSBC raises no contract line; VALE raises no line at all.
- Today's files were built from the old hand-off, so batch membership is a note, not a FAIL. A file with a `lab_revision` column is checked strictly.
- One rule relaxed: ranks may continue across batches (batch 2 = 31–60). Gaps and duplicates still FAIL.
- `audit\laneb_fixB\triage_interface.md` lists the fields for the triage prompt.

### B6. Packs
- `lab_card.json` is the first file in every pack: card values by name, four evidence families, Lab revision, database sha256.
- Output `data\scratch\ticker_packs\<session>\`; `packs_index.json` lists the tickers and the revision.
- Refused when the Lab is not `COMPLETE` or was published before the Morning run finished.
- A ticker the Lab does not publish still gets a pack, marked `TICKER_ABSENT_FROM_LAB`.
- `lab_revision` in each `manifest.json`. All existing pack files kept.
- Repair in passing: tickers `NAN` and `NA` were read as missing values in run files; fixed.
- Acceptance: `audit\laneb_fixB\B6_lab_card_check.md`.

### B7. `today_context`
New or changed keys: `handoff`, `handoff_source`, `handoff_lab_revision`, `handoff_matches_lab`, `lab_book` (the manifest path), `lab_revision`, `lab_publication_state`, `packs_folder` (session folder), `packs_ready_batches`. `split_handoff`, `packs_ready` and `packs_missing` are kept for existing prompts.

After `packs -Batch 1` then `packs -Batch 3`:

```
packs_folder         data\scratch\ticker_packs\2026-11-12
packs_ready          True
packs_ready_batches  1, 3
packs_missing
```

### B10. Decision records
- Scans for `*_deep_dive_*.html`; the newest card is the one with the latest date in its name.
- A card with no `decisions\<TICKER>.json` gets one with `state = CARD_BUILT_DECISION_MISSING`. An existing record is never touched.
- Reports "decided, not placed". Works without a triage CSV. `--dry-run`.
- The ticket sheet's spread rule is now the 11 Nov tiers.
- Dry run on `split_2026-11-12_cap5`: HSBC would get a record (no artifact link in its HTML); CPNG has one; decided, not placed: CPNG (`final_action` TRADE_NOW, no order recorded).

## 4. Counts

| | |
|---|---|
| Lab rows in | 2,800 |
| Hand-off rows | 2,132 |
| Excluded by verdict | BLOCKED 512, CONTRACT_REPAIR 156 |
| Excluded by window filter | 0 (flag mode) |
| Batches | 72 |

## 5. Overlap with the old 171-name hand-off

| | Count | Examples |
|---|---|---|
| Kept | 165 | HG (now order 118, batch 4), NTGR (220, batch 8), INGR (105, batch 4) |
| Added | 1,967 | NXST (GO_LIMIT, order 3), TWST (Lab rank 1), NOK (Lab rank 2) |
| Dropped | 6 | LAW (CONTRACT_REPAIR), VALE (BLOCKED), WULF (BLOCKED); also IWM, OPK, KIDS |

- Of the Lab's first 60 in order, 20 were in the old hand-off.
- The old batch 1 now sits at orders 9 to 701; four of its names are in the new batch 1 (HSBC, UHS, PGNY, CPNG).
- Daily setups with q50 ≤ 20 and a contract: 570 in the Lab hand-off; 101 were in the old one.

## 6. The lines ACK runs each day under the new flow

Switch on, once (after the triage prompt is updated from `triage_interface.md`):

`& C:\Users\ACKVerissimo\AVSHUNTER-Intelligence\data\scratch\workaround\avs_day.ps1 status -LabHandoff`

Each day:

| When | Line |
|---|---|
| After the Evening run and Lab publication | `& C:\Users\ACKVerissimo\AVSHUNTER-Intelligence\data\scratch\workaround\avs_day.ps1 evening` |
| After the Morning run and Lab republication | `& C:\Users\ACKVerissimo\AVSHUNTER-Intelligence\data\scratch\workaround\avs_day.ps1 evening -Refresh` |
| Packs, batch 1 | `& C:\Users\ACKVerissimo\AVSHUNTER-Intelligence\data\scratch\workaround\avs_day.ps1 packs -Batch 1` |
| Packs, another batch | `& C:\Users\ACKVerissimo\AVSHUNTER-Intelligence\data\scratch\workaround\avs_day.ps1 packs -Batch 2` |
| Packs, named tickers | `& C:\Users\ACKVerissimo\AVSHUNTER-Intelligence\data\scratch\workaround\avs_day.ps1 packs -Tickers HSBC CPNG` |
| After the triage | `& C:\Users\ACKVerissimo\AVSHUNTER-Intelligence\data\scratch\workaround\avs_day.ps1 checktriage` |
| Pre-close | `& C:\Users\ACKVerissimo\AVSHUNTER-Intelligence\data\scratch\workaround\avs_day.ps1 preclose` |
| End of day | `& C:\Users\ACKVerissimo\AVSHUNTER-Intelligence\data\scratch\workaround\avs_day.ps1 eod` |

Direct lines, from the repo root:

- `venv\Scripts\python.exe data\scratch\workaround\build_lab_handoff.py --run 20261111_231951`
- `venv\Scripts\python.exe data\scratch\workaround\build_lab_handoff.py --run 20261111_231951 --refresh`
- `venv\Scripts\python.exe data\scratch\workaround\build_lab_handoff.py --run 20261111_231951 --spotcheck audit\laneb_fixB\B1_spotcheck.csv` (about 5 minutes; the Lab app must be running)
- `venv\Scripts\python.exe tools\ticker_pack.py HSBC CPNG --run 20261111_231951 --session 2026-11-12`
- `venv\Scripts\python.exe data\scratch\workaround\check_triage.py --folder data\scratch\workaround\handoff\lab_2026-11-12 --triage-folder data\scratch\workaround\handoff\split_2026-11-12_cap5 --session 2026-11-12 --all`
- `venv\Scripts\python.exe data\scratch\workaround\collect_decisions.py --folder data\scratch\workaround\handoff\split_2026-11-12_cap5 --dry-run`

Back to the old chain at any time: `& C:\Users\ACKVerissimo\AVSHUNTER-Intelligence\data\scratch\workaround\avs_day.ps1 status -LegacyHandoff`

Settings: `data\scratch\workaround\lab_handoff_settings.json` (optional; defaults are in `build_lab_handoff.py`). The premium cap stays in `day_settings.json` (`-Cap`).

## 7. Deferred, and decisions for ACK

| # | Item | State |
|---|---|---|
| 1 | Switch the live flow to the Lab hand-off | Left on LEGACY. One line in section 6, after the triage prompt is updated |
| 2 | Create `decisions\HSBC.json` in `split_2026-11-12_cap5` | Done on ACK's go-ahead. State `CARD_BUILT_DECISION_MISSING`, no artifact link (none in the HTML). The decision itself (TRADE / WATCH / PASS) is still to be written. The same run wrote `cards_2026-11-12.csv` and `order_tickets_2026-11-12.md` there (neither existed before) |
| 3 | `tests\test_x17_check_triage_spread_gate.py` | Fails (pins the removed 25% rule). Retire or rewrite; outside my files |
| 4 | Strategy layer, hand-off comparison, pre-close scan, S6 replay | Still read the old layout. Not run on a Lab hand-off. Adapt or retire |
| 5 | Evening or Morning publication | The evening step builds from whatever `COMPLETE` publication exists and labels its stage. After the Morning republish it refuses until `-Refresh`. Confirm this is the flow you want |
| 6 | 72 batches | Batch size is a setting (30). How many batches are triaged per day is B5, ACK's chat |
| 7 | Disk | `lab_2026-11-12` is 161 MB (two test refreshes kept in `_rev_` subfolders); the session pack folder is 153 MB for 60 tickers |
| 8 | Fields the Lab lacks | `needs_codex.md` section 1: monetisation n, contract alternatives, one repair state, session date, publication stage, cluster |

## 8. What was written outside the repo's tracked files

All under Lane B's own folders; nothing in `data\output\runs\`.

- `data\scratch\workaround\handoff\lab_2026-11-12\` (new)
- `data\scratch\ticker_packs\2026-11-12\` (new, 60 packs)
- `data\scratch\workaround\day_settings.json` (new: cap 5, hand-off source LEGACY)
- `data\scratch\workaround\today_context.json` and `.md` (rewritten by `avs_day.ps1 status`, as every step does)
- `data\scratch\workaround\mining\guard_rerun_2026-11-11.csv` (rewritten by the evening step's trade guard, same inputs)
- `split_2026-11-12_cap5`: three files added on ACK's go-ahead (`decisions\HSBC.json`, `cards_2026-11-12.csv`, `order_tickets_2026-11-12.md`). Nothing in it was overwritten.
