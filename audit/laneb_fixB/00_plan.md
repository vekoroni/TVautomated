# Lane B Fix B: plan (Lab-first hand-off)

Written 12 Nov 2026 by Claude Code for ACK. Status: **PLAN ONLY. No code changed.** Waiting for ACK's go-ahead.

- Brief: `data\scratch\workaround\lessons\fix_inbox\2026-11-12_claude_code_brief_fix_B.md`
- Branch: `laneb/lab-first-handoff`, created from `f4968c7` (was `high-convexity-watchlist`). Nothing committed.
- Test run: `20261111_231951`, read-only.
- Items in scope: B1, B2, B3, B4 (`check_triage.py` only), B6, B7, B10.

---

## 1. What I checked before planning

| Check | Result |
|---|---|
| Lab publication | `publication_state = COMPLETE`, revision `f70092078e3f4a548955a08cbec131f6`, database `review-f70092078e3f4a548955a08cbec131f6.sqlite`, created `2026-11-12T20:19:00Z`, 2,800 rows |
| `card_fields` | 145 names, aligned to `card_json.values` |
| SQLite layout | `rows`, `evidence`, `publication` as the brief describes. Evidence is zlib JSON with `fields`. Five families, 2,800 rows each |
| One row per ticker | Yes. No ticker has two rows |
| Lab API | `localhost:5002` answers (HTTP 200) |
| Price store | `data\canonical\historical_prices.sqlite`, table `ohlcv_daily` (close, volume, `bar_status`), last SPY bar 2026-11-11 |
| CPNG | Lab target 10.9258, contract `CPNG270219P00017000` (Feb 17P): matches the brief |
| B10 inputs | `split_2026-11-12_cap5` holds `HSBC_deep_dive_2026-11-12_clean.html` and two CPNG cards; `decisions\` holds only `CPNG.json`: matches the brief |

## 2. Where the evidence differs from the brief (ground rule 10)

None of these block the plan. Each needs ACK to see it.

1. **The Lab was republished after the brief was written.** The brief quotes database `review-5ea68db1…` and 4 GO_LIMIT / 2,128 MANUAL_REVIEW. The current revision `f7009207…` has **3 GO_LIMIT (PH, NXST and one more) / 2,129 MANUAL_REVIEW**. AZZ is now `MANUAL_REVIEW` (its `final_action` is still `BUY_SMALL`). The hand-off population is 2,132 either way. Five revisions exist in the folder for this run.
2. **D1.** Section 4 of the brief on disk still says "ACK has not decided". I follow ACK's message of 12 Nov instead: the planned hold stays as the thesis runway (never capped), the monetisation clock n is carried, and `PROXY_Q50` is the labelled stand-in until the Lab publishes n.
3. **Repair fields are not card fields.** `contract_repair_status` and `contract_repair_action` live in the `option_risk` evidence family. I read them from there.
4. **The decision ledger has other users.** `build_thesis_ledger.py` also feeds the session date in `avs_day.ps1`, `track_outcomes.py`, `preclose_trigger_scan.py`, `strategy_layer.py` and `compare_split_handoffs.py`. Removing it from the evening step breaks those steps. See question Q2.
5. **Uncommitted edits already sit in three of my files.** `avs_day.ps1`, `check_triage.py` and `collect_decisions.py` carry the 18–20 Oct strategy-layer and trade-guard edits, never committed. `tools\ticker_pack.py` has never been committed at all. See question Q1.
6. **The hand-off grows from 171 names to about 2,132, so 72 batches of 30** (6 today). The order is the Lab's, so batch 1 is still the top of the book. How many batches are triaged per day is ACK's call (B5).

## 3. Lab fields I will read (checked against manifest `card_fields`)

All present in `card_fields` unless marked.

| Group | Fields | State |
|---|---|---|
| Identity, rank | `ticker`, `sector`, `sector_etf`, `direction`, `thesis_id`, `trade_lane_candidate_id`, `lab_rank`, `rank_basis`, `rank_expected_multiple`, `lab_verdict`, `final_action`, `trade_lane_setup` | Present |
| Thesis | `thesis__readiness`, `thesis__event_status`, `thesis__trigger_age_sessions`, `thesis_trigger_level`, `invalidation_price`, `early_warning_invalidation_level` | Present |
| Target | `anticipated_level`, `anticipated_level_basis`, `anticipated_level_q50` | Present |
| Timing | `anticipated_sessions_q50`, `anticipated_sessions_q80`, `planned_hold_sessions`, `planned_hold_source`, `anticipated_time_fit`, `anticipated_evidence_status`, `anticipated_evidence_n`, `remaining_runway_state` | Present |
| Contract | `contract_symbol`, `expiry`, `contract_dte`, `contract_bid`, `contract_ask`, `contract_oi`, `contract_iv`, `contract_delta`, `contract_volume`, `selected_quote_timestamp_utc`, `quote_freshness` | Present |
| Payoffs | `scenario_target_return_on_premium`, `scenario_stall_return_on_premium`, `scenario_invalidation_return_on_premium`, `scenario_exit_sessions` | Present |
| Earnings | `earnings_state`, `earnings_date`, `earnings_report_time`, `earnings_date_confirmation`, `earnings_source`, `earnings_sessions_to_event`, `earnings_inside_hold`, `earnings_inside_contract`, `earnings_unknown_reason`, `earnings_disclosure` | Present |
| Repair | `contract_repair_status`, `contract_repair_action` | **Not card fields.** In `option_risk` evidence |
| Monetisation clock | `monetisation_n_q50`, `monetisation_n_q80`, `monetisation_threshold` | **Not published** anywhere (card or evidence). The audit family has `monetisability_*`, which is a different thing and is not used |
| Contract alternatives (A8) | none on the card | **Not published** as a Lab-ordered list |
| Cluster | none | **Not published** (brief already says so) |

The hand-off copies **all 145 card fields** under their Lab names, not only the ones above. A field missing from a later manifest is written blank and listed in the receipt and in `needs_codex.md`; the build does not fail.

Evidence families copied to `handoff_evidence.jsonl` and `lab_card.json`: `structure`, `option_risk`, `context`, `morning` (the four the brief names). `audit` (644 fields) is left out and that is stated in the receipt.

Value rules: copied as stored. Blank and null both mean "not available" and are written blank in the CSV; `0` stays `0`. The JSONL keeps the exact stored value. No pandas default NA handling anywhere, so ticker `NAN` survives.

---

## 4. Plan per item

### B1. Build the hand-off from the Lab's publication

**Create**
- `data\scratch\workaround\build_lab_handoff.py`
- `data\scratch\workaround\lab_reader.py`: one shared read-only reader (manifest, SQLite opened `?mode=ro`, card values by name, evidence decode, database sha256 check). Used by B1, B4, B6 so the Lab is read one way.
- `data\scratch\workaround\test_laneb_lab_handoff.py`: tests on a small synthetic SQLite built in a temp folder (no live data, no network).

**Behaviour**
- `--run` (default: newest run whose manifest says `COMPLETE`). Refuses, with the reason, when the manifest is missing, not `COMPLETE`, the database file is missing, or its sha256 differs from the manifest.
- Population `lab_verdict` in {GO_LIMIT, MANUAL_REVIEW}. Excluded verdict counts go in the receipt.
- Output `data\scratch\workaround\handoff\lab_<session>\`: `handoff.csv`, `handoff_evidence.jsonl`, `handoff.md`, `receipt.json` (run id, revision, database sha256, created times, settings, counts in and out by reason, fields missing).
- Lane B columns are prefixed `lb_`. No Lab field is recomputed, capped or replaced.
- `lb_ledger_id` = `<session>_<TICKER>_<CALL|PUT>` so decisions and triage files keep their existing key. `lb_row_key` carries the Lab row key.

**Acceptance**
- `audit\laneb_fixB\B1_spotcheck.csv`: 20 random rows (seed written in the receipt) plus HSBC, CPNG, PH, AZZ, NXST. For each, every copied field is compared with `GET /api/lab/<run>/rows/<row_key>`. One line per row and field that differs; PASS means zero lines. The API revision is checked against the manifest first; if they differ the check stops and says so.
- Needs the Lab app running on 5002 (it is now).

**Needs Codex:** nothing to build. Requests listed in section 6.

### B2. One target and one contract per name

**Change**
- `build_lab_handoff.py` (same file): no half target, no cap, no own contract. Target = `anticipated_level` with `anticipated_level_basis`; first profit = `anticipated_level_q50`; contract = `contract_symbol`.
- Writes `legacy_compare.csv` (ticker, legacy target, legacy half target, legacy contract, Lab target, Lab contract, `differs`) **only when** a legacy `split_<session>_cap*` folder exists for the session. It reads that folder; it never writes to it. No legacy folder: the receipt says `LEGACY_NOT_BUILT`.
- `data\scratch\workaround\avs_day.ps1`: evening step calls `build_lab_handoff.py`. New switch `-LegacyHandoff` runs the old chain exactly as today. `build_thesis_ledger.py`, `avshunter_options_standalone.py`, `build_mining_handoff.py` are not edited or deleted.

**Acceptance**
- `handoff.csv` header has exactly one target set and one contract set (asserted by a test and shown in the report).
- `legacy_compare.csv` row for CPNG shows legacy half target 13.46 and Mar 18P against Lab 10.93 and Feb 17P, `differs = True`.

**Needs Codex:** no.

### B3. Flags, order, groups, batches

**Change:** `build_lab_handoff.py`. Settings defaults live in the script; overrides in `data\scratch\workaround\lab_handoff_settings.json`. The premium cap is read from the existing `day_settings.json` (one owner).

| Column | Rule | Source |
|---|---|---|
| `lb_window_flag`, `lb_window_reason`, `lb_window_basis` | IN_WINDOW when timeframe (first part of `trade_lane_setup`) is in `window_timeframes` and the clock ≤ `window_max_q50_sessions`. Clock = `monetisation_n_q50` when published, else `anticipated_sessions_q50` with basis `PROXY_Q50`. Weekly and monthly are flagged, never dropped (`window_mode = flag`) | Lab |
| `monetisation_n_q50`, `monetisation_n_q80`, `monetisation_threshold`, `monetisation_state` | Copied if the Lab has them, else blank and `NOT_PUBLISHED`. Never computed here | Lab |
| `lb_time_fit` | Copy of `anticipated_time_fit` | Lab |
| `lb_over_cap` | OVER_CAP when `contract_ask` > `premium_cap` (5.0). Flag only | Lab quote |
| `lb_saved_gate`, `lb_saved_spread_pct`, `lb_saved_gate_basis` | 11 Nov tiers on the Lab's saved bid, ask, OI. A: spread ≤10% of mid, OI ≥100, and if premium <1.50 the spread ≤0.10 wide. B: 10–20%. C: over 20%, no bid, or OI <100. NO_CONTRACT when the Lab has none. Basis `SAVED_QUOTE` with the quote time | Lab quote |
| `lb_trigger_age`, `lb_runway_note` | Trigger age copied; note `TRIGGER_AGE_EXCEEDS_Q50` when age > q50 (CPNG: 115 vs 42) | Lab |
| `lb_repair_conflict` | True when `contract_repair_status` and `contract_repair_action` disagree | `option_risk` evidence |
| `lb_stock_tier`, `lb_dollar_volume_20d_usd` | Mean of close × volume over the last 20 COMPLETE bars. A ≥$50M, B $20–50M, C <$20M (flagged not tradeable). `NO_PRICE_HISTORY` when fewer than 20 bars | Price store, read-only |
| `lb_order` | GO_LIMIT first, then `lab_rank` ascending. No weights | Lab |
| `lb_group`, `lb_group_role` | `sector_etf` + direction; first row in order is PRIMARY, the rest ALTERNATE | Lab |
| `lb_batch` | 30 per batch in `lb_order` | — |

Also writes `ticker_pack_command_<batch>.txt` per batch (full PowerShell line).

Two readings I will state in the output, for ACK to correct if wrong:
- "premium" in the tier-A rule = the mid of the saved quote.
- A contract with spread ≤10% that fails the OI or the 0.10-wide test falls to B or C by the same rules, never stays A.

**Acceptance**
- A test rebuilds the order from `lab_verdict` and `lab_rank` alone and compares it with `lb_order`.
- Report for run `20261111_231951`: counts by each flag, and the batch-1 list.

**Needs Codex:** monetisation n; one repair state (A4); a cluster field if ACK wants groups from the Lab.

### B4 (part). `check_triage.py`

**Change:** `data\scratch\workaround\check_triage.py` only. **Create** `audit\laneb_fixB\triage_interface.md` (the field names triage should read and write).

- The 25% rule is removed. The spread check uses the 11 Nov tiers on the triage's live quote: A passes, B is WARN, C is WARN "not tradeable at this quote".
- New: `trade_contract` must equal the hand-off's `contract_symbol`. Any other contract is WARN "not the Lab contract". When the Lab publishes alternatives (A8) a named alternative passes; until then the line says alternatives are not published.
- New: the triage target must equal `anticipated_level`; a triage half target must equal `anticipated_level_q50`. Otherwise WARN with both values.
- Reads either layout: `lab_<session>` (new) or `split_*` (legacy, old checks unchanged).
- Any batch: `--batch N` or `--all` (default: every `batch*_triage_<session>.csv` found). New `--triage-folder` so triage files in one folder can be checked against a hand-off in another.
- Triage files built from the old hand-off have batches that do not match the Lab's. For those the batch-membership check becomes a note, not a FAIL; the row checks still run.

**Acceptance**
- PowerShell line: `venv\Scripts\python.exe data\scratch\workaround\check_triage.py --folder data\scratch\workaround\handoff\lab_2026-11-12 --triage-folder data\scratch\workaround\handoff\split_2026-11-12_cap5 --session 2026-11-12 --all`
- Must WARN on CPNG (target and contract) and pass rows that match. The output is copied into the report.

**Needs Codex:** A8 alternatives, before the "named Lab alternative" pass can work.

### B6. Packs from the Lab, one folder per session

**Change:** `tools\ticker_pack.py`. **Create** `data\scratch\workaround\test_laneb_ticker_pack.py`.

- New first file per ticker `lab_card.json`: card values by name, the four evidence families, `lab_revision`, `database_sha256`, `row_key`. Written first into the zip. A ticker not in the Lab still gets a pack, with `lab_card` status `TICKER_ABSENT_FROM_LAB` in the manifest.
- Output folder `data\scratch\ticker_packs\<session>\`. `--session` (default: the session of the newest Lab hand-off receipt). A re-run adds or replaces tickers in that folder.
- Refuses, with the reason, when the publication is not `COMPLETE` or is older than the run's Morning completion. Morning completion = the time `morning_validation\morning_validated_trades_<run>.csv` was written (15:41Z for this run). A run with no Morning files is allowed and labelled `EVENING_PUBLICATION`.
- Per-ticker `manifest.json` gains `lab_revision`, `lab_database_sha256`, `lab_publication_created_at_utc`.
- Every existing pack file stays. One small repair in passing: the CSV filter reads with default NA handling, which turns ticker `NAN` into a missing value; I will fix that in this file.

**Acceptance**
- Packs for HSBC and CPNG: `lab_card.json` compared field by field with the Lab API (same comparer as B1).
- Batch 1 then batch 2: both land in `data\scratch\ticker_packs\2026-11-12\`; no second folder.

**Needs Codex:** an explicit Morning-completed time in the Lab manifest would replace my file-time reading (section 6).

### B7. `today_context` points at the right inputs

**Change:** `data\scratch\workaround\avs_day.ps1` (Get-Context, Write-Context, `packs`, `checktriage`, `preclose`, `eod` to read the new keys).

| Key | New value |
|---|---|
| `handoff` | `data\scratch\workaround\handoff\lab_<session>` |
| `handoff_source` | `LAB` or `LEGACY` |
| `split_handoff` | Kept, same folder as `handoff`, so existing chat prompts and scripts keep working |
| `lab_book` | Path of the review projection `manifest.json` |
| `lab_revision`, `lab_publication_state` | From that manifest |
| `packs_folder` | `data\scratch\ticker_packs\<session>` (fixed per session) |
| `packs_ready_batches` | List of batches whose every name has a pack |
| `packs_ready` | Kept: true when batch 1 is ready (the scheduled triage reads it) |
| `packs_missing` | Kept, for batch 1 |

- `packs -Batch N` reads `ticker_pack_command_<N>.txt`.
- Session date in Lab mode comes from the hand-off receipt, not from the ledger files.

**Acceptance:** `avs_day.ps1 packs -Batch 1`, then `-Batch 3`; `today_context.json` shows batch 1 still ready, `packs_ready_batches` = 1, 3, and one session folder. The JSON goes in the report.

**Needs Codex:** no.

### B10. A decision record for every card

**Change:** `data\scratch\workaround\collect_decisions.py`. **Create** `data\scratch\workaround\test_laneb_collect_decisions.py`.

- Scans the hand-off folder for `*_deep_dive_*.html` (skips Office lock files `~$…`). Ticker = the text before `_deep_dive_`. Several cards for one ticker: the newest is the card path, all are listed.
- No `decisions\<TICKER>.json`: creates one with `state = CARD_BUILT_DECISION_MISSING`, `ticker`, `card_path`, `card_files`, `artifact_url` (any claude.ai artifact link found in the HTML, else blank), `created_utc`. An existing decision file is never touched.
- Works without a triage CSV (today it stops).
- New report section "decided, not placed": decision `TRADE*` or `ENTER` with no recorded order.
- `--dry-run` lists what it would create and writes nothing.

**Acceptance**
- `venv\Scripts\python.exe data\scratch\workaround\collect_decisions.py --folder data\scratch\workaround\handoff\split_2026-11-12_cap5 --dry-run` lists HSBC (card, no decision file) and CPNG (has one).
- Creating `decisions\HSBC.json` in that existing folder adds a file to a legacy folder. I will run only the dry run until ACK says to create it.

**Needs Codex:** no.

---

## 5. Questions for ACK before I start

| # | Question | My recommendation |
|---|---|---|
| Q1 | Three of my files carry older uncommitted edits (18–20 Oct), and `ticker_pack.py` was never committed. May I commit them first as `B0: baseline` so each B commit shows only its own change? | Yes. Files staged by name only |
| Q2 | The decision ledger also drives outcome tracking, the pre-close scan, the strategy layer and the comparison. In Lab mode, keep building the ledger as an outcome record (it costs no credits and is no longer a hand-off source), or stop it and let those steps report "not available in Lab mode"? | Keep building it. The options tool (which costs credits) stops. Adapting those four scripts to the Lab layout is a follow-up, not in this brief |
| Q3 | The Lab republishes during the day (five revisions on 12 Nov). When `lab_<session>` exists and the revision has changed: refuse, or refresh? | Refresh only with `--refresh`: the previous `handoff.*` set is first copied to `lab_<session>\_rev_<old revision>\`, triage files and cards stay where they are, the receipt keeps the revision history. Without `--refresh` it refuses and says why |
| Q4 | `collect_decisions.py` prints the 16 Oct execution rule "no order when the spread is over 25% of the mid" on every ticket sheet. Replace it with the 11 Nov tiers while I am in that file? | Yes, same wording as `check_triage.py` |
| Q5 | 72 batch command files in the hand-off folder root, or in a `pack_commands\` subfolder? | Subfolder. The brief says root; I follow the brief unless told |
| Q6 | This checkout is now on `laneb/lab-first-handoff`. Any other session committing in this same folder would land on this branch. The Codex worktrees I can see are in separate folders. Is anything else committing here? | Tell me if so and I will move to a worktree |

## 6. For Codex (will go to `audit\laneb_fixB\needs_codex.md` at the build)

Nothing here blocks Fix B. Each has a labelled fallback.

| Need | Today | Lane B fallback |
|---|---|---|
| `monetisation_n_q50`, `monetisation_n_q80`, `monetisation_threshold` | Not published | Blank, `monetisation_state = NOT_PUBLISHED`, window on `PROXY_Q50` |
| Contract alternatives in Lab order (A8) | Not on the card or the API | Any non-Lab contract is WARN |
| One repair state per row (A4) | Status and action can disagree; both sit in `option_risk` evidence | `lb_repair_conflict` |
| Decision session date | Manifest has only the bar date (`macro_context.session_date` = 2026-11-11) | Session = date of the first XNYS session after the bar date, cross-checked with `timing_details.expiry_reference_date` |
| Publication stage and Morning-completed time | Not in the manifest | Read from the run's `morning_validation` file times |
| Cluster field | Not published | `sector_etf` + direction |
| Value types (A7) | Same field is a number on some rows and text on others (`planned_hold_sessions` "52.0", `anticipated_sessions_q50` 22); blank and null both occur | Copied as stored |
| Projection issue | `NAN:MATCHING_VALIDATION_EVENT_NOT_FOUND` in the source receipt (A11) | Carried into the receipt |

## 7. Rules I will keep

- Changes only under `data\scratch\workaround\` and `tools\ticker_pack.py`. Audit files under `audit\laneb_fixB\`.
- Read-only on run folders, the Lab projection, the price store and macro outputs.
- No pipeline run. Tests against stored run `20261111_231951` and synthetic fixtures.
- Every change starts with a failing test that states the rule. Tests run one file per process with `venv\Scripts\python.exe -m pytest`.
- Commit per item (`B1: …`), files staged by name, no merge, no push.
- New outputs in new folders. No `split_*` folder overwritten.
- No key values printed or written.

## 8. Build order after the go-ahead

1. B0 baseline commit (if Q1 is yes).
2. `lab_reader.py` and B1, then the spot check.
3. B3 flags and order, then B2 legacy compare and the `avs_day.ps1` switch.
4. B6 packs, then B7 context.
5. B4 `check_triage.py` and `triage_interface.md`.
6. B10 `collect_decisions.py`.
7. `needs_codex.md` and `99_report.md`. Stop.
