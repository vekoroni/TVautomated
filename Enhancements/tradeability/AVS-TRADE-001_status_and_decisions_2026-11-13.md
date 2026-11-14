# AVS-TRADE-001 · Tradeability track: where it stands and what ACK decides

Written 13 Nov 2026 by Claude Code for ACK. Read-only review: no pipeline code, run or hand-off was changed.

## 1. Purpose

Turn the pipeline's ideas into trades that can be placed and exited at a profit. No ticker is dropped and no thesis changes. The track changes which contract is picked, when the price is taken, and what is published beside it.

## 2. The three documents this track already has

| Document | Date | What it holds |
|---|---|---|
| `data\scratch\workaround\lessons\fix_inbox\2026-11-12_lab_first_fix_list.md` | 12 Nov | The master list: A1–A11 (Lab output, Codex), B1–B10 (Lane B, Claude Code), C1–C6 (macro), decisions D1 and D2 |
| `data\scratch\workaround\lessons\fix_inbox\2026-11-12_fix_A12_monetisation_clock.md` | 12 Nov | A12: the missing clock n (sessions until the option first shows +30%), with ACK's decision that the planned hold stays |
| The ten-item plan ACK pasted on 13 Nov | 13 Nov | A resequencing of the same work, with three new decisions |

A fourth brief would repeat these. This sheet maps them onto one status and lists what blocks them.

## 3. Status of each piece

"In the working tree" means the code is edited but uncommitted and has not been seen on a completed run.

| Item | What it fixes | State on 13 Nov | Evidence |
|---|---|---|---|
| B1–B4, B6, B7, B10 | Hand-off, packs and triage check built from the Lab | **Built and tested, not switched on** | `audit\laneb_fixB\99_report.md`; 48 tests; `handoff_source = LEGACY` |
| B5, B8, B9 | Every batch triaged; deep dive starts from the Lab card; fallback contract from the Lab | Not started | Fix list |
| A1 | Contract outlasts the hold, counted in exact XNYS sessions | **Measurement in the working tree**: `expiry_session_check_state` (`domain\option_contract_liquidity.py`, `domain\trade_timing.py`, edited 12 Nov). Selection by it: not seen | `git diff` |
| A3 | Hold counts down from the trigger | **In the working tree**: `remaining_hold_sessions`, state `EXHAUSTED` (`morning_gate.py`, edited 13 Nov) | `git diff` |
| A8 | Contract alternatives published | **Partly in the working tree**: card fields `contract_value_alternatives`, `doi_alternatives_json` (`contracts\lab_review_projection.py`) | `git diff` |
| A12 | Monetisation clock n, and contract chosen from n | **Not started**: no `monetisation_n_*` or `contract_covers_n` in pipeline code | search of `domain`, `contracts`, `scripts`, `vanguard`, `canonical_data` |
| A2 | Planned hold rule (decision D1) | Waits for D1 | Fix list |
| A4, A5, A6, A7, A9, A10, A11 | Repair state, Morning unlock, scenario feed, blanks shown as 0, clocks labelled, evidence status, projection flag | Not checked today | — |
| C2 | US Money Index routing | **In the working tree** (`contracts\us_money_index_contract.py`, 181 lines changed) | `git diff` |
| C1, C3–C6 | Macro inputs, sector returns, thesis, kill-switch rule | Not checked today | — |
| GARCH D1 | Expected-move fields built from differences | **Open**, confirmed today at `layer3_forward_variance.py:690-692` | Model audit, item 4c |
| PUT base rates; dropped dimensions | Win rates long-side only; a partial match reported as exact | **Open**, confirmed today (`ev_engine_v2.py:92-94`; `actuarial_query.py:653, 667, 1002-1016`) | Model audit, items 4a and 4b |
| Outcome ledger | One scored row per decision | **Built in the research package**: every decision since 12 Oct, scored nightly on stock and exact contract (85.3% contract coverage). Missing: a 20-session horizon, MFE/MAE, the exit | `dropbox\macro\coaching\model\reports\step0_report_2026-11-13.md` |

**Operating state.** The last completed run is `20261111_231951`. The folder for `20261112_230902` was last written at 23:09 on 12 Nov, and the 13 Nov post-close monitor reports the run still "running" and no hand-off for 13 Nov. Nothing in this track can be accepted until a normal Evening and Morning cycle completes on committed code.

## 4. What the 11 Nov run shows (Lane B report, 2,132 hand-off rows)

| Measure | Rows |
|---|---|
| Clear on all four flags (in window, within cap, tier A or B contract, tier A or B stock) | 35 |
| Contract expires before the median arrival time | 1,005 |
| Contract expires before q80 | 481 |
| Saved quote is tier C | 1,697 |
| Monetisation state published | 0 |
| In the 1–20 session window (on q50, a proxy) | 591 |

## 5. Decisions for ACK

Each has my recommendation. Items 1 to 3 block the build; 4 to 9 correct the pasted plan before any of it goes to Codex.

**ACK accepted the recommendations on 1, 2 and 3 on 13 Nov 2026** ("Yes, accept all three"). The Codex brief written from them is `AVS-TRADE-001_codex_brief_2026-11-13.md` in this folder. Items 4 to 9 are still open; the brief keeps everything they touch out of scope.

| # | Decision | Recommendation | Why |
|---|---|---|---|
| 1 | **Which rule picks the contract's expiry?** The pasted plan says cover q80 plus a buffer and make shorter contracts ineligible. Your A12 decision of 12 Nov says the hold stays as the thesis runway and the contract is chosen from n; a contract may be shorter than the hold. | Keep A12. Publish both checks (`anticipated_time_fit` and `contract_covers_n`). | The two rules contradict. Covering q80 is what makes contracts long and expensive (A12, "Why this should already exist"). The pasted plan's test "expires before q80 falls to 0" would then be the wrong test. |
| 2 | **Trading window (D1).** | 1–20 sessions on n once A12 publishes it, on q50 until then, as a flag. Nothing dropped; out-of-window rows stay as WATCH. | Lane B already carries the flag (`PROXY_Q50`). |
| 3 | **Premium cap or an over-cap lane (D2).** | Keep the cap as a flag and show over-cap rows in a labelled lane. | 848 of 2,132 rows are over the cap; a flag keeps them visible. |
| 4 | Switch `value_selection_mode` from SHADOW to ACTIVE after 3 sessions | Not on 3 sessions. Close or re-version `Enhancements\research\cohorts\cohort_1_preregistration.json` first and state the gate evidence. | It gives logic decision authority (CLAUDE.md rule 5) and changes a pre-registered rule under test. |
| 5 | Rank contracts by return per premium dollar | Fix PUT base rates and dropped dimensions first, or use a ranking that does not read them. | Puts would be ranked on long-side odds. |
| 6 | Stop the Morning job pricing when it starts late | Flag the late start and re-quote. | Your rule: flag quote age, never gate on it (9 Oct). |
| 7 | Tastytrade live quotes on cards | Your call. If yes, label the source and time on the card and keep MarketData as the record. | Your rule is MarketData only for option quotes. |
| 8 | Rank in-window names first inside the Lab | Feed the window flag into `domain\opportunity_rank.py` as a readiness input. | One rank owner (8 Oct). |
| 9 | Success tests: "TRADE cards beat 50% after 30 cards" and "at least 10 rows a day" | Average return per card at ask in, bid out, with its interval; and restate the 10-row target, which 35 rows already meets. | Expectancy, not hit rate (7 Oct); 30 cards carries about ±18 points. |

## 6. Order of work once decisions 1 to 3 are answered

| Order | Work | Owner | Depends on |
|---|---|---|---|
| 1 | Complete a normal Evening and Morning run; commit or shelve the working-tree edits so the run is on known code | ACK runs; Codex owns the edits | — |
| 2 | Switch Lane B to the Lab hand-off: update the triage prompt from `audit\laneb_fixB\triage_interface.md`, then `avs_day.ps1 status -LabHandoff` | ACK and Claude Code | 1 |
| 3 | A12 monetisation clock, proxy first (`PROXY_LEVEL`), then the option-based n | Codex | Decision 1 |
| 4 | Contract chosen from n with the 11 Nov tiers applied at selection; alternatives published (A1, A8) | Codex, in shadow beside today's pick | 3 |
| 5 | GARCH D1: move consumers to the cumulative fields | Codex, with ACK's approval of root cause and design | — |
| 6 | PUT base rates and dropped dimensions | Codex, same approval | — |
| 7 | Outcome ledger: add the 20-session horizon, MFE/MAE and the exit to the nightly scorer | Claude Code (research package) | — |
| 8 | Old-layout scripts and the X17 test: adapt or retire | ACK decides, Claude Code does it | 2 |

Item 7 is the only one in my files. I have not started it: it waits for your go-ahead, like every step of the model package.

## 7. What I did not verify

- Whether Codex's working-tree edits pass their tests or produce the intended fields on a run. I read the diffs only.
- The state of A4–A7, A9–A11 and C1, C3–C6 since the 11 Nov run.
- Why the 12 Nov run did not complete.

## Update 14 Nov 2026: decisions recorded and status changes

Recorded by Claude Code from ACK's words on 14 Nov. Where this section differs from the text above, this section is current.

### ACK's decisions of 14 Nov

| # | Decision | ACK's words |
|---|---|---|
| D-14.1 | The Morning gate runs at any time during market hours. 09:35-09:45 ET is a preferred window that labels the run; only a start outside market hours stops. Closes open decision 6 above. | "The morning gate should have the flexibility to run anytime during market hours." |
| D-14.2 | Macro decides which ETFs are looked at first. It does not set direction and does not gate. A wider role needs a test on held data first. | "i agree with all your recommendations" (recommendation 1 on Codex's ETF response) |
| D-14.3 | Index ETFs: show both the over-cap near-the-money contract and the in-cap out-of-the-money one, labelled, with no automatic switch. | same (recommendation 2) |
| D-14.4 | An ETF review view that keeps the Lab's rank, ordered by macro context. No rank change. | same (recommendation 3) |
| D-14.5 | Leveraged, inverse and volatility products: research-only, visible and labelled, until a product-specific rule exists. | same (recommendation 4) |
| D-14.6 | Freshness and monetisation parameters: no invented figures; a row with thin evidence says "needs evidence". Thresholds are set after the first runs publish the clock. | same (recommendation 5) |
| D-14.7 | Claude Code builds contract selection from the clock; Codex reviews before commit. One writer per file. | "agreed, write the design note" |
| D-14.8 | Trading principle: macro identifies the opportunity, expressed in ETFs and in pipeline names, so the ETF fixes must work. Improve the pipeline through a fixed set of criteria per trade, filled only from data held. | "our new trading principles is based on the macro identify opportunities in the etf and the pipeline" |

D-14.2 and D-14.8 sit beside CLAUDE.md rule 6 (macro never influences a gate, score or rank). D-14.2 keeps macro to visibility, which is inside the rule. Any step beyond that needs rule 6 amended in writing by ACK.

### Status changes since 13 Nov

| Item | 13 Nov | 14 Nov |
|---|---|---|
| GARCH D1 | Open at `layer3_forward_variance.py:690-692` | Committed on the line (`3bd7ecf`); not yet run |
| Station quarantine, exact session clocks, PHANTOM changes, Lab card sections, macro delivery | Uncommitted working tree | Committed (`ff694d7`, `ffcdbbe`, `79c5983`, `c213a92`, `ca060b7`); not yet run |
| Monetisation clock (A12) | Branch only | Merged (`cc07ff1`). It measures the exact contract's own quote history, is not called by a run, and uses different field names from ACK's 12 Nov brief |
| Contract from the clock | Assigned to Codex in the brief of 13 Nov | Assigned to Claude Code. Design note: `AVS-TRADE-001_design_contract_from_clock_2026-11-14.md`, awaiting ACK's approval |
| ETF fixes | Draft | Package with Codex; Codex's response in `audit\trace\AVS-TRACE-001\ETF_codex_response.md`: 15 accepted, 4 challenged, 4 for ACK (now decided above), 1 interface only. Nothing built |
| Stock outcomes | Three ledgers scored to two sessions | Nine ledgers scored to 12 Nov: direction right 52.5% at 10 sessions; with the money tag 64%, against it 42% (one month, exploratory) |

The Codex brief of 13 Nov (`AVS-TRADE-001_codex_brief_2026-11-13.md`) is superseded for items W1 and W2 by the design note; W3 and W4 stand.

### ACK's approval to build the crossing scenario (14 Nov, later)

| # | Decision | ACK's words |
|---|---|---|
| D-14.9 | ETF identity work validated and committed by Claude Code (`4010d4d`). | "option 1, validate and commit the etf identity work" |
| D-14.10 | Build design note v4 (`AVS-TRADE-001_design_contract_from_clock_2026-11-14.md`) now. Taken, as stated to ACK before the answer, as: approval of the ten proposed decisions in its section 15; confirmation of the shared-file handoff with Claude Code as the one writer until it is committed; building before Codex's fourth design review, with Codex reviewing the code before commit. | "Yes, build v4 now" |

Shadow and display only. No selection, rank, gate or Lane B window-flag change. The Evening run follows the build.
