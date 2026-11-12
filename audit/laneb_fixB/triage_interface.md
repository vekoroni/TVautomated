# Triage interface: what the triage reads and writes under the Lab-first hand-off

Written 12 Nov 2026 by Claude Code (Fix B4). For ACK's chat, which updates the triage scheduled-task prompt. Claude Code has not edited the task.

Rule: the triage reads Lab fields as they are. It adds live checks, skills and a rank. It never writes its own target, half target or contract pick. A disagreement is a flag in `main_challenge`, not a replacement.

## 1. Where to read

All paths come from `data\scratch\workaround\today_context.json`.

| Key | Meaning |
|---|---|
| `handoff` | Hand-off folder, `data\scratch\workaround\handoff\lab_<session>` |
| `handoff_source` | `LAB` (this interface) or `LEGACY` (old columns) |
| `lab_book` | The Lab review projection `manifest.json` |
| `lab_revision` | Revision the Lab publishes now |
| `handoff_lab_revision` | Revision the hand-off was built from |
| `handoff_matches_lab` | `false` means the Lab republished: run `avs_day.ps1 evening -Refresh` first |
| `packs_folder` | `data\scratch\ticker_packs\<session>` |
| `packs_ready_batches` | Batches whose every name has a pack |
| `packs_ready` | Batch 1 ready (true/false) |

Files in the hand-off folder:

| File | Use |
|---|---|
| `handoff.csv` | One row per Lab row. Every Lab card field under its Lab name, then `lb_` columns |
| `handoff_evidence.jsonl` | Per row: `card`, `card_missing_fields`, `card_extra`, `evidence` (structure, option_risk, context, morning) |
| `handoff.md` | Counts, flags, batch 1 |
| `receipt.json` | Run, revision, settings, counts |
| `pack_commands\ticker_pack_command_<batch>.txt` | Pack line for the batch |

Read the CSV with no default NA handling. `NAN` is a real ticker. Blank means not available; `0` is a real zero.

## 2. Lab fields the triage reads (names as in `handoff.csv`)

| Purpose | Field |
|---|---|
| Batch and order | `lb_batch`, `lb_order` |
| Key | `lb_ledger_id` (`<session>_<TICKER>_<CALL or PUT>`), `lb_row_key` |
| Identity | `ticker`, `direction`, `sector`, `sector_etf` |
| Lab rank and verdict | `lab_rank`, `lab_verdict`, `final_action`, `rank_expected_multiple`, `rank_basis` |
| Setup | `trade_lane_setup` (timeframe, setup, state) |
| Thesis state | `thesis__readiness`, `thesis__event_status`, `thesis__trigger_age_sessions` |
| Trigger | `thesis_trigger_level` |
| Kill | `invalidation_price`, `early_warning_invalidation_level` |
| **Target** | `anticipated_level` with `anticipated_level_basis` |
| **First profit** | `anticipated_level_q50` |
| Timing | `anticipated_sessions_q50`, `anticipated_sessions_q80`, `planned_hold_sessions`, `planned_hold_source`, `anticipated_time_fit` |
| Evidence status | `anticipated_evidence_status`, `anticipated_evidence_n` |
| **Contract** | `contract_symbol`, `expiry`, `contract_dte` |
| Saved quote | `contract_bid`, `contract_ask`, `contract_oi`, `contract_iv`, `contract_delta`, `selected_quote_timestamp_utc` |
| Payoffs | `scenario_target_return_on_premium`, `scenario_stall_return_on_premium`, `scenario_invalidation_return_on_premium`, `scenario_exit_sessions` |
| Earnings | `earnings_state`, `earnings_date`, `earnings_report_time`, `earnings_date_confirmation`, `earnings_sessions_to_event`, `earnings_inside_hold`, `earnings_disclosure` |
| Macro (evidence, `context` family) | `macro_*`, `usmi_*` |
| Morning (evidence, `morning` family) | `morning_*`, `execution_viability_*` |

Lane B flags (information, never a reason to change a Lab field):

| Flag | Values |
|---|---|
| `lb_window_flag`, `lb_window_reason`, `lb_window_basis` | IN_WINDOW, OUTSIDE_WINDOW, NOT_ASSESSED. Basis `PROXY_Q50` until the Lab publishes the monetisation clock |
| `monetisation_n_q50`, `monetisation_n_q80`, `monetisation_threshold`, `monetisation_state` | Blank and `NOT_PUBLISHED` today |
| `lb_time_fit` | Copy of `anticipated_time_fit` |
| `lb_over_cap` | WITHIN_CAP, OVER_CAP, NO_QUOTE |
| `lb_saved_gate`, `lb_saved_gate_reason`, `lb_saved_spread_pct`, `lb_saved_gate_basis` | A, B, C, NO_CONTRACT on the Lab's saved quote. The triage re-checks live |
| `lb_trigger_age`, `lb_runway_note` | Trigger age; note when it exceeds q50 |
| `lb_repair_status`, `lb_repair_action`, `lb_repair_conflict` | From `option_risk` evidence |
| `lb_stock_tier`, `lb_dollar_volume_20d_usd` | A, B, C (C not tradeable), NO_PRICE_HISTORY |
| `lb_group`, `lb_group_role` | `sector_etf` + direction; PRIMARY or ALTERNATE. The triage may override with a narrative cluster |
| `lb_lab_missing_fields` | Lab fields not recorded for the row |

## 3. Columns the triage writes (`batch<N>_triage_<session>.csv`, in the hand-off folder)

`check_triage.py` treats a file with a `lab_revision` column as built from the Lab hand-off and checks it strictly.

| Column | Content | Checked |
|---|---|---|
| `deep_mine_rank` | Whole number first; consecutive, no gaps. Batch 1 starts at 1 | FAIL |
| `ticker` | As in the hand-off; every name of the batch, once | FAIL |
| `ledger_id` | Copy of `lb_ledger_id` | FAIL |
| `side` | Copy of `direction` | WARN if the contract is the other side |
| `lab_revision` | Copy of `handoff_lab_revision` | Required |
| `target` | Copy of `anticipated_level` | WARN if not equal |
| `first_profit` | Copy of `anticipated_level_q50` | WARN if not equal |
| `trigger_state` | Live: beyond trigger on a close, at trigger, not yet | Required |
| `chase_state` | Live: in range, extended, chased | Required |
| `trade_contract` | `contract_symbol`, or a named Lab alternative when the Lab publishes them, or `none` with the reason | WARN if not the Lab's |
| `contract_bid`, `contract_ask`, `contract_oi` | Live quote on that contract, numbers only | Tier B and C are WARN |
| `contract_quote_time_utc` | When the live quote was read | — |
| `live_gate` | A, B or C from the 11 Nov tiers on the live quote | — |
| `earnings_tastytrade` | Date from Tastytrade | WARN if over 1 day from the Lab's |
| `cluster`, `cluster_role` | Narrative cluster, if it overrides `lb_group` | — |
| `main_challenge`, `rank_reason` | Text | Required |
| `decision`, `decision_reason`, `contract_taken`, `entry_type`, `entry_premium` | Present and empty | WARN if filled |

No longer written: `half_target`, `level`, `pays_at_half_target`, `handoff_best_contract`, `contract_spread_pct`, any own contract pick, any 25% spread test.

## 4. The 11 Nov liquidity tiers (live quote)

| Tier | Rule | Triage action |
|---|---|---|
| A | Spread ≤10% of mid, OI ≥100, and under a 1.50 premium the spread is ≤0.10 wide | Tradeable |
| B | Spread 10–20% of mid (or A except for the 0.10 width) | Tradeable with care; say so |
| C | Spread over 20%, no bid, or OI under 100 | Not tradeable at this quote. A Lab alternative, or `none` |

"Premium" is read as the mid of the quote. One owner in code: `liquidity_tier` in `data\scratch\workaround\build_lab_handoff.py`.

## 5. Check

`venv\Scripts\python.exe data\scratch\workaround\check_triage.py --all`

or `& C:\Users\ACKVerissimo\AVSHUNTER-Intelligence\data\scratch\workaround\avs_day.ps1 checktriage`

Prompts files: batch 1 `deep_dive_prompts_<session>.md`; batch N `deep_dive_prompts_<session>_b<N>.md`. Each section names the session and the hand-off folder.

## 6. Open, waiting on Codex

- Contract alternatives (A8): until published, any contract other than `contract_symbol` is a WARN.
- Monetisation clock n: until published, the window uses `PROXY_Q50`.
