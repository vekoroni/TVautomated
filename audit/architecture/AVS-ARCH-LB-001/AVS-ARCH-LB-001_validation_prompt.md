# AVS-ARCH-LB-001-VAL: validate every fix proposed in the 20-21 Nov chat

Paste into Claude Code from the repo root. Read-only except the output files named below.

---

You are validating the fixes and enhancements proposed in ACK's Claude chat of 20-21 Nov 2026 (Card Watch Board, Lane B, discovery and architecture). Your job is NOT to build or redesign anything. For each item below, establish:

1. **Recorded**: is it written down where the team will find it? Check `audit\architecture\AVS-ARCH-LB-001\AVS-ARCH-LB-001_fix_list.md` (v1.1), `data\scratch\workaround\lessons\fix_register.csv`, `lessons\fix_inbox\`, `lessons\change_log.md`. Name the file and section or row ID, or say NOT_RECORDED.
2. **Reviewed against the code**: does the code or data confirm the problem or need as described? Give `path:line` or artefact evidence. If the evidence contradicts the item, say so plainly.
3. **Already done?**: is any part already implemented (for example the board items built on 20 Nov)? Verify against `audit\architecture\AVS-ARCH-LB-001\board_page_v19.html` or the code. States: LIVE_VERIFIED, LIVE_UNVERIFIED, NOT_BUILT.
4. **Classification**: ENHANCEMENT (new capability) or DEFECT_FIX (something not working as intended). Most items here are enhancements; say which and why.
5. **Acceptance status**: use the status given below (it is ACK's position as of 21 Nov). Do not change it. If the code shows an item cannot work as accepted, add a CHALLENGE note with evidence.
6. **Conflicts and overlaps**: does it duplicate, contradict or depend on an existing register row (give IDs) or another item in this list?

Rules:
- Read-only. Do not edit any existing file. Do not run the pipeline, `avs_day.ps1`, the weekend chain, the orchestrator or any writing script. No Bigdata.com, MarketData or Anthropic calls.
- Missing evidence is UNKNOWN, never a pass.
- The phase is discovery and architecture: nothing here is approved to build except where the status says LIVE (already built).
- Repo root `C:\Users\ACKVerissimo\AVSHUNTER-Intelligence`; Lane B `data\scratch\workaround`; hand-off folders `data\scratch\workaround\handoff\lab_<session>`.

Status key: **LIVE** = built and running on the board (verify). **ACCEPTED** = ACK agreed the direction, design not yet built. **PROPOSED** = put to ACK, no decision yet. **DECISION** = waiting on an ACK choice. **NOT_CHOSEN** = option considered and not taken (record it so it is not re-proposed).

## Items

### Board features built on 20 Nov (status LIVE: verify in board_page_v19.html)
| ID | Item | Status |
|---|---|---|
| V-01 | Updated card from the board without a full build (v17): baselines and updates collections, mini/check/full verdict, downloads via the downloads capability | LIVE |
| V-02 | Review queue for older cards (v18): window passed or group "review"; up to 5 sessions = Validate, older = Fresh card; copy-prompt and Retire buttons; older cards kept, not hidden | LIVE |
| V-03 | Stop and target checks on expired rows in the updated-card judge (v18 fix) | LIVE |
| V-04 | Card lineage (v18.1): `supersedes` field, auto-retire the older card unless held | LIVE |
| V-05 | Triage pipeline section (v19): 158 triage rows in the board database, priced every 60 s, calls NOW, NEXT, LATER, DONE, VALIDATE, HELD, CLOSED, WAIT | LIVE |
| V-06 | Deep-dive timing rule: NOW = no current card and (fired but short of half target, or within 1.5% of trigger, or class E1); NEXT = within 4% or E2/E3 with no level; LATER = further, beyond half target, or E6; DONE = card up to 5 sessions; VALIDATE = older card; CLOSED = invalidation crossed. Order only; every name still gets a deep dive | LIVE (bands 1.5% and 4% uncalibrated) |
| V-07 | Board-row skill changes proposed (fields `built`, `supersedes`, `outcome`, `review` group) | PROPOSED (ACK has not confirmed saving the skill) |

### Weekend list (20 Nov) and gap register (21 Nov)
| ID | Item | Status |
|---|---|---|
| G1 | Lab passes thesis but not a usable contract or timing: all rows MANUAL_REVIEW, monetisation fields unpublished, 1,109 contracts expire before median time to target, 561 no contract, 152 CONTRACT_REPAIR. Owner Codex | PROPOSED (Codex brief) |
| G2 | Hand-off order anchored on 114 carried-forward focus tickers ahead of Lab rank. Option: flag column, cap about 30, drop after 3 sessions without a card | DECISION |
| G3 | Triage as a script (A6): `triage_from_lab.py`; trigger, stop, half target, invalidation, contract and tier as numbers; chat adds narrative, market players, lifecycle | PROPOSED |
| G4 | Cards don't reliably reach the board (AWK, ES, GILD 20 Nov rows missing); row validator and sync | ACCEPTED (absorbed into D1 card record and the feed) |
| G5 | Outcome loop stopped (no ledger outcomes 16-20 Nov); scoring v3 for options and triage calls | ACCEPTED in revised form: logging moves to the board (see L-01, L-02); ledger scoring role is a DECISION |
| G6 | Lifecycle stage (1-7) and market-player read as data fields in triage, card and board row | PROPOSED |
| G7a | Market regime banner on the board (VIX, breadth) | PROPOSED |
| G7b | Retire the October rows on the board | PROPOSED |
| G7c | `today_context.md` blanks for triage_check, prompts, cards, tickets | PROPOSED (defect fix) |
| W-01 | Open interest check on board contracts | PROPOSED |
| W-02 | Live stock dollar volume for the liquidity tier on the board | PROPOSED |
| W-03 | Run the weekend chain only after the enhancements; chain to gain triage script, feed refresh and scoring steps | ACCEPTED (sequence); steps PROPOSED |

### Architecture decisions and designs (21 Nov)
| ID | Item | Status |
|---|---|---|
| D1 | The card becomes one data record (JSON); the HTML card is rendered from it by one fixed template; the board row, decision file, ledger columns and order tickets are produced from the same record | ACCEPTED |
| D1a | Card checker that rejects a record with missing required fields | ACCEPTED (part of D1) |
| D1b | Versioning with a field-level diff so an updated card cannot silently drop data (ACK's merge rule) | ACCEPTED (part of D1) |
| D1c | Card format drift evidence: 21 cards scanned; thesis "so this option should" part missing in 11, notes switch in 8, GTC ladder in 7, lifecycle in 4, players in 2, max pay in 2, two-sided ticket in 2, Lab rank in 20, board-row link in 15; at least three tab markups | Evidence to VERIFY (keyword scan) |
| E1 | Local read-only feed (MCP over stdio) on the PC so the board picks up card records and triage without a chat; import rules: insert missing only, never overwrite board edits, remember imported IDs, start date | PROPOSED (design) |
| R-01 | Chrome view of the board via a quote relay: the desktop board saves quotes, positions, orders and tape to the board database about every 60 s; Chrome reads the snapshot and shows its age | ACCEPTED |
| R-02 | Local board hosted on the PC (localhost) | NOT_CHOSEN |
| L-01 | Board card log: per card, traded or not, first time in entry zone, trigger fired, option bid high and low after trigger, stop or half target first, window expiry, every state change with time | ACCEPTED (learning comes from the board) |
| L-02 | Board triage call log: NOW/NEXT/LATER per triaged name at fixed times, to score calls and calibrate the bands | ACCEPTED |
| L-03 | CSV export of the logs and a reader for scoring | ACCEPTED |
| F1 | Board page source kept in the repo with versions (today it exists only in the artifact) | PROPOSED |
| A-01 | Accuracy measures for "accurate intelligence mining" (trigger hit rate by call, option return at half target, win rate at least 75% with losers not eating profit, results by lifecycle stage, tier and side) | DECISION (ACK sets targets) |

### Carried forward and housekeeping (21 Nov)
| ID | Item | Status |
|---|---|---|
| CF-01 | Reconcile all earlier open fixes: 86 open register rows, 51 built-not-verified, 116 unmerged inbox files (about 900 lines), 12 Nov Lab-first list A1-A11, 12 Nov `needs_codex.md` | ACCEPTED (section 7 of the fix list) |
| CF-02 | Strategy layer S1-S6 not run since the Lab hand-off (`strategy_layer.py` reads the old layout) | DECISION (restore or retire) |
| CF-03 | `tests\test_x17_check_triage_spread_gate.py` fails 4 of 5 since the 25% rule was removed | DECISION (retire or rewrite) |
| CF-04 | Change log has no entries after 14 Nov (board v17-v19, `check_triage.py` v5, triage import missing) | PROPOSED (defect fix) |
| CF-05 | Execution discipline themes from the monitors: fired stops not executed, fills on contracts not on the card, resting sells below card target | PROPOSED (verify against register N2, N7, R14-14, N17-16) |
| CF-06 | Stale `today_context` and `macro_state` across sessions | PROPOSED (verify against N17-01) |

## Output

Write to `audit\architecture\AVS-ARCH-LB-001\`:
- `enhancement_validation.csv`: one row per ID above: id, title, status_given, recorded_in, evidence, built_state (LIVE_VERIFIED / LIVE_UNVERIFIED / NOT_BUILT), classification (ENHANCEMENT / DEFECT_FIX), overlaps (register IDs, other IDs), challenge (blank or the note), confidence (HIGH / MEDIUM / LOW).
- `enhancement_validation.md`: a one-page summary: counts by status and built_state; every NOT_RECORDED item; every CHALLENGE; every LIVE item that failed verification; items that overlap existing register rows.
- `register_entries_proposal.csv`: rows in the `fix_register.csv` column layout for every item not yet in the register, with `status` copied from the status above (LIVE items as Built, ACCEPTED as Approved, PROPOSED as Proposed, DECISION as Decision, NOT_CHOSEN as Closed with the reason). Do not edit `fix_register.csv` itself: ACK approves the merge.

Finish with one line per DECISION item stating exactly what ACK has to choose.
