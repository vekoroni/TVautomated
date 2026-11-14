# AVS-TRADE-001 · Codex brief: the contract is chosen from the monetisation clock

Owner: ACK (decides, runs pipelines, commits). Builder: Codex. Tester: Claude Code.
Written 13 Nov 2026 by Claude Code from ACK's decisions of 12 and 13 Nov. Status sheet: `Enhancements\tradeability\AVS-TRADE-001_status_and_decisions_2026-11-13.md`.

## Objective

Each row with a contract says how many sessions the option needs to become sellable at a profit (n), whether the contract lasts that long, and which contract would be picked on that basis. No ticker is dropped, no thesis changes, and the contract the pipeline selects today does not change in this brief.

## Decisions this brief rests on

| Decision | By | Date |
|---|---|---|
| The planned hold (q80 arrival) stays as the thesis runway. It is not capped or replaced. | ACK | 12 Nov |
| Add the monetisation clock n and choose the contract from it. A contract may fit n and be shorter than the hold. | ACK | 12 Nov, confirmed 13 Nov |
| Trading window is 1–20 sessions, as a flag: on n once published, on q50 until then. Out-of-window rows stay, as WATCH. | ACK | 13 Nov |
| The premium cap is a flag. Over-cap rows are shown in a labelled lane. | ACK | 13 Nov |

## Read first

1. `CLAUDE.md` (working rules; rule 5 on decision authority).
2. `data\scratch\workaround\lessons\fix_inbox\2026-11-12_fix_A12_monetisation_clock.md`. It defines n, the method, the fields and the "do not" list. This brief does not restate it.
3. `data\scratch\workaround\lessons\fix_inbox\2026-11-12_lab_first_fix_list.md` (A1, A8).
4. `audit\laneb_fixB\99_report.md` and `needs_codex.md` (what Lane B already reads and its fallbacks).

## State of the code on 13 Nov

- Uncommitted edits from 12–13 Nov are in the working tree: exact XNYS session counting and `expiry_session_check_state` (`domain\trade_timing.py`, `domain\option_contract_liquidity.py`), the hold counting down (`morning_gate.py`), card fields `contract_value_alternatives` and `doi_alternatives_json` (`contracts\lab_review_projection.py`), US Money Index routing, station quarantine.
- No pipeline code publishes `monetisation_n_*` or `contract_covers_n`.
- The selection owner is `select_best_contract` (`scripts\avshunter_options_intelligence.py:5615`), governed by `long_option_contract_selection` in `config\governed_constants_v1.json` (`value_selection_mode` SHADOW, `value_selection_eligibility` COVERS_PLANNED_HOLD).
- The last completed run is `20261111_231951`.

## Work, in order

**W0. Known code and a completed run.** With ACK, commit or shelve the working-tree edits so a run is on known code. ACK then completes one normal Evening and Morning cycle. Nothing below is accepted on an incomplete run.

**W1. Monetisation clock (A12).**
- Build as the A12 brief defines, proxy first (`monetisation_basis = PROXY_LEVEL`), then the option-based n.
- Fields: `monetisation_n_q50`, `monetisation_n_q80`, `monetisation_hit_rate`, `monetisation_evidence_n`, `monetisation_evidence_status`, `monetisation_threshold_pct`, `monetisation_basis`, `monetisation_state`.
- Threshold (+30%, floor +20%) and the minimum sample live in `governed_constants_v1.json`.
- Too little evidence: blank with the reason, never 0.
- Field name to settle: the A12 brief says `monetisation_threshold_pct`; Lane B reads `monetisation_threshold` today (`data\scratch\workaround\build_lab_handoff.py:66`). Publish the A12 name; Claude Code aligns Lane B's reader when the field appears.
- Reality check, not a fit: the research package records the first session each of 232 named contracts reached +20% and +30% at mid (`dropbox\macro\coaching\model\outcomes\decision_events.sqlite`, table `option_entry`, open read-only). Report published n against those observed sessions.

**W2. Contract covers n, and the shadow pick.**
- Publish `contract_covers_n` (YES / NO / NOT_ASSESSED) beside `anticipated_time_fit`: the contract is still valid at `monetisation_n_q80` plus the existing 3 monitoring and 5 exit sessions, counted on XNYS, and still shows the threshold there with decay included.
- Add a second eligibility, covers n, computed beside COVERS_PLANNED_HOLD. `value_selection_mode` stays SHADOW.
- Apply the 11 Nov liquidity tiers on the selection quote: A spread ≤10% of mid and OI ≥100, and under a 1.50 premium no more than 0.10 wide; B 10–20%; C over 20%, no bid, or OI under 100. One owner: move the thresholds into `governed_constants_v1.json`. Lane B's `liquidity_tier` (`data\scratch\workaround\build_lab_handoff.py:172`) is the oracle.
- Publish the shadow pick beside the selected contract: its symbol, tier, `contract_covers_n`, sessions to expiry, premium, and the reason it differs.
- Publish 2 or 3 alternatives in Lab order with quote, OI, spread, sessions to expiry, time fit and `contract_covers_n` (A8). Lane B picks up any column whose name starts `contract_alternative`.

**W3. Window flag.** Publish `trade_window_state` (IN_WINDOW / OUTSIDE_WINDOW / NOT_ASSESSED) and `trade_window_basis` (N_Q50 once n is published, PROXY_Q50 until then). The 1–20 bounds live in config. No row is dropped or reordered by it in this brief.

**W4. Premium cap flag.** Publish `premium_cap_state` (WITHIN_CAP / OVER_CAP / NO_QUOTE) with the cap from config. Flag only.

## Out of scope (each needs its own decision from ACK)

- Switching `value_selection_mode` to ACTIVE, or changing how contracts are ranked.
- Ordering rows by the window flag. If wanted later it enters `domain\opportunity_rank.py` as a readiness input, with ACK's approval of the design.
- Stopping the Morning job from pricing when it starts late; Tastytrade quotes on cards.
- GARCH D1 (`layer3_forward_variance.py:690-692`), PUT base rates (`ev_engine_v2.py:92-94`) and dropped match dimensions (`actuarial_query.py:653, 667, 1002-1016`). All three are confirmed open and each needs an approved root cause and design.
- Any change to `planned_hold_sessions` values.

## Rules

- Return a short design note per work item for ACK's approval before code. No pipeline code changes without an approved root cause and design.
- Test first: a failing test that states the business rule, and a characterisation test pinning the behaviour being changed.
- Thresholds in versioned configuration, never as literals in domain code.
- Flags and labels only. Nothing here gates, blocks or drops a row. Missing is never neutral: blank with a reason.
- Never present n as a probability of profit or as validated.
- No code edits while ACK is running a pipeline. ACK commits and pushes.

## Acceptance, on one normal Evening and Morning cycle

1. The W1 fields are in the Lab manifest `card_fields` and on the card, with evidence status visible. Rows with a contract carry n or a blank with its reason.
2. Distribution of `monetisation_n_q50` and `n_q80` by timeframe (1d / 1w / 1mo) against q50 and q80 arrival.
3. Ten rows checked by hand, including HSBC, PH and CPNG: threshold level, first-hit session on two historical cases each, reported n.
4. Count of GO_LIMIT and MANUAL_REVIEW rows with `contract_covers_n = YES`, beside the current time-fit counts (11 Nov: 1,005 expire before the median arrival, 481 before q80).
5. Shadow pick against today's pick on three sessions: tier of each, `contract_covers_n`, premium. No tier C shadow pick where a tier A or B candidate exists.
6. Rows clear on all four Lane B flags under the shadow pick, against 35 of 2,132 on 11 Nov.
7. `planned_hold_sessions` and the selected `contract_symbol` are unchanged on every row.
8. Lane B's `check_triage.py` raises no WARN when triage uses a published alternative.
