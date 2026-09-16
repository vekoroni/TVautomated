# Track M3 — When we were right, what were we right about? (discovery, §4.3)
No NORMAL_COMPLETED_SESSION run exists; every result below is on TEST-condition runs and cannot be CLOSED.
RESEARCH_ONLY. Discovery track (Rules 9–13): no verdict vocabulary, no severities. Nothing here authorises, sizes or clears a position.

**Data source (Rule 10):** historical reconstruction only.
- Directional outcomes: `probes/p32_labels.csv` (coordinator probe p32). These are retrospective ALG-08 labels built from `db_copies/historical_prices.sqlite` daily OHLC on presented-not-taken candidates from 15 run books (decision sessions 2026-07-22 → 2026-09-01). The vol-budget target is S·(1 ± 1.5·σ_a·√(h/252)), and h is the routed bucket's upper bound.
- Selected contract and entry quote: each run's `intelligence_lab/final_opportunity_book_<run>.csv`, read for geometry and quote only.
- Option paths: `db_copies/phantom_history.db` `options_greeks_history`, queried per ticker and date range. `chain_snapshots` was the fallback and added 0 rows.
- No fills and no ledger outcomes exist (ledger resolved outcomes = 0, outcome_census §1).

**Dependency:** E1 (label correctness) is running in parallel. The labels used here come from the coordinator's probe p32 and have not yet been verified by E1.
**Runs:** UNGOVERNED_PRE = books 20260723_072618 … 20260824_100301 (12 runs). GOVERNED = 20260831_010309, 20260901_082437, 20260902_232526. All runs are TEST condition.
**Probes:** `probes/p23_M3_thesis_outcomes.py` → `p23_M3_thesis_outcomes.csv`, `p23_M3_thesis_tables.txt`, `p23_M3_thesis_table_T1.csv`. `probes/p23_M3_monetisation.py` → `p23_M3_monetisation.csv`, `p23_M3_option_snapshots.csv`, `p23_M3_monetisation_stdout.txt`, `p23_M3_monetisation_tables.txt`. `probes/p23_M3_coverage_addendum.py` → `p23_M3_coverage_addendum.txt`.

**Measurement states:**
- Directional outcome: MEASURED (8,417 unique theses).
- Monetisation: PARTIAL. Option history has no daily bars. Across all 40 sampled tickers the only snapshot dates are 2026-07-10, 07-17, 07-31, 08-28 and 09-04, so "best daily bid over the window" became "best bid over the snapshots that fall inside the window". The median is 1 snapshot per priced window. 1,250 of 8,417 unique theses are priced; the rest are excluded for the reasons in the coverage table.
- OTHER: p32 carries CALL and PUT only. The 405 OTHER presented rows, all on governed books, have no full window, so OTHER n = 0 everywhere → INSUFFICIENT_POWER (n=0).

## Findings table
| Finding ID | CALL | PUT | OTHER | data source | evidence (artefact, field, value) | N | magnitude |
|---|---|---|---|---|---|---|---|
| DISC-F-M3-1 | side_correct 45.4%; TARGET_FIRST_V 6.6%; median MFE 4.1% vs median vb_dist 13.8% | side_correct 53.5%; TARGET_FIRST_V 3.4%; median MFE 4.4% vs vb_dist 14.2% | INSUFFICIENT_POWER (n=0) | p32 labels (OHLC) | p23_M3_thesis_outcomes.csv: side_correct, label_V, mfe, vb_dist | CALL 6,900 · PUT 1,517 unique theses | the side is right on about half of theses, but the thesis amount is reached first on 3–7% |
| DISC-F-M3-2 | priced theses: side-wrong/not-mon 53.3% · side-correct/not-mon 37.1% · side-correct/mon 9.0% · side-wrong/mon 0.6% | 46.3% · 39.1% · 14.2% · 0.4% | INSUFFICIENT_POWER (n=0) | p32 + books + phantom_history | p23_M3_monetisation.csv: side_correct × monetised_125, coverage_state=PRICED | CALL 792 · PUT 458 | among side-correct priced theses, 80.5% (CALL 294/365) and 73.4% (PUT 179/244) did not reach bid ≥ 1.25 × entry ask |
| DISC-F-M3-3 | UNGOVERNED first-binding: MFE<strike dist 26.5% · flat decay 25.3% · none identified 20.9% · IV down ≥10% 17.3% · spread>15% 10.0% · reach 0% | UNGOVERNED: MFE<strike 30.5% · decay 27.7% · reach>1.5 14.2% · IV 13.5% · spread 7.1% · none 7.1% | INSUFFICIENT_POWER (n=0) | same | first_binding, cause_* columns | CALL 249 · PUT 141 (GOVERNED 45 / 38 → INSUFFICIENT_POWER) | multi-cause incidence: flat decay 72% (CALL) / 66% (PUT); reach>1.5 on 70% of PUT; mean causes 1.68 / 2.18 |
| DISC-F-M3-4 | UNGOVERNED side-wrong: invalidation touched 71.8%, timeout-negative 28.2%; touched: median terminal loss/stop 1.24, loss > stop on 62.0% | touched 63.7%; median loss/stop 1.15; loss > stop on 57.0% | INSUFFICIENT_POWER (n=0) | p32 labels (OHLC) | p23_M3_thesis_outcomes.csv: side_wrong_class, loss_over_stop, mae_over_stop | CALL 3,657 · PUT 647 (GOVERNED all cells < 100 → INSUFFICIENT_POWER) | holding past a touched invalidation ends beyond the stop distance on more than half of touched theses |
| DISC-F-M3-5 | contract usable (VALID) on 17.0% of UNGOVERNED CALL theses (1,141/6,728); 99.4% GOVERNED | usable 41.1% UNGOVERNED (575/1,400); 99.1% GOVERNED | INSUFFICIENT_POWER (n=0) | books + phantom_history | coverage_state: NO_SYMBOL 3,356 · NO_ENTRY_ASK 1,811 · SIDE_MISMATCH 1,247 · NO_SNAPSHOT 725 · SYMBOL_ABSENT 28 · PRICED 1,250 | 8,417 unique theses | 14.9% of unique theses priced; the priced set is concentrated on 3 snapshot dates |
| DISC-F-M3-6 | monetised_125: GOVERNED 1-5 10.9% (n=156); UNGOVERNED 6-10 11.0% (n=498), 1-5 3.0% (n=135) | GOVERNED 1-5 11.3% (n=106); UNGOVERNED 6-10 16.8% (n=304); 1-5 INSUFFICIENT_POWER (n=45) | INSUFFICIENT_POWER (n=0) | same | monetised_125, monetised_entry, best_bid_over_ask | 1,250 priced | median best bid / entry ask: GOVERNED 0.42 / 0.51; UNGOVERNED 6-10 0.32 / 0.60 |
| DISC-F-M3-7 | entry geometry GOVERNED: strike dist +0.6%, spread 16.5%, cal DTE 18, flat decay −24%; UNGOVERNED: +3.6%, 12.9%, 29, −35% | GOVERNED −1.1%, 14.1%, 21, −17%; UNGOVERNED +3.3%, 12.1%, 30, −32% | INSUFFICIENT_POWER (n=0) | books (geometry only) | strike_dist, entry_spread_frac, cal_dte, flat_decay_frac (VALID contracts, unique) | GOV 171 / 116 · UNGOV 1,141 / 575 | governed contracts sit closer to ATM with shorter DTE and wider spreads |

Each finding's "does NOT establish" statement is in the Findings section below.

## Table 1 — Directional outcome per unique thesis by condition × direction × horizon
Unique thesis = (ticker, direction, decision_session); the first row in run order is kept. 8,417 theses from 9,896 presented rows; no thesis appears in both conditions.

| condition | dir | horizon | n | side_correct | reached vb target (MFE, any time) | TARGET_FIRST_V | INVALIDATION_FIRST_V | TIMEOUT_V | median terminal | median vb_dist | median MFE | valid structural n | TARGET_FIRST_S |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| UNGOVERNED_PRE | CALL | 1-5 | 672 | 50.7% | 8.3% | 7.3% | 42.0% | 50.6% | +0.1% | 10.1% | 3.4% | 434 | 35.3% |
| UNGOVERNED_PRE | CALL | 6-10 | 6,021 | 45.1% | 7.8% | 6.6% | 50.3% | 43.0% | −0.7% | 14.4% | 4.2% | 705 | 40.9% |
| UNGOVERNED_PRE | CALL | 11-20 | 35 | INSUFFICIENT_POWER (n=35) | | | | | | | | | |
| UNGOVERNED_PRE | PUT | 1-5 | 214 | 49.1% | 3.7% | 3.3% | 23.8% | 72.9% | −0.1% | 12.2% | 3.6% | 214 | 7.9% |
| UNGOVERNED_PRE | PUT | 6-10 | 1,180 | 54.6% | 3.9% | 3.4% | 36.3% | 60.3% | +0.9% | 14.9% | 4.6% | 1,180 | 1.4% |
| UNGOVERNED_PRE | PUT | 11-20 | 6 | INSUFFICIENT_POWER (n=6) | | | | | | | | | |
| GOVERNED | CALL | 1-5 | 172 | 37.2% | 4.7% | 2.3% | 46.5% | 51.2% | −1.0% | 8.6% | 2.1% | 171 | 14.0% |
| GOVERNED | PUT | 1-5 | 117 | 49.6% | 4.3% | 3.4% | 17.1% | 79.5% | −0.0% | 12.4% | 3.9% | 117 | 7.7% |
| any | OTHER | any | 0 | INSUFFICIENT_POWER (n=0) | | | | | | | | | |

GOVERNED books have no 6-10 or 11-20 theses with a full window: the store ends 2026-09-10. Unique-thesis side_correct × TARGET_FIRST_V: UNGOVERNED CALL side-correct 3,071 of which TARGET_FIRST 443; PUT 753 / 48. TARGET_FIRST with side wrong: CALL 7, PUT 0.

## Table 2 — Option-history coverage (unique theses)
| condition | dir | NO_SYMBOL | NO_ENTRY_ASK | SIDE_MISMATCH | NO_SNAPSHOT_DATE_IN_WINDOW | SYMBOL_ABSENT_FROM_HISTORY | PRICED | total |
|---|---|---|---|---|---|---|---|---|
| UNGOVERNED_PRE | CALL | 2,873 | 1,543 | 1,171 | 502 | 3 | 636 (9.5%) | 6,728 |
| UNGOVERNED_PRE | PUT | 481 | 268 | 76 | 223 | 0 | 352 (25.1%) | 1,400 |
| GOVERNED | CALL | 1 | 0 | 0 | 0 | 15 | 156 (90.7%) | 172 |
| GOVERNED | PUT | 1 | 0 | 0 | 0 | 10 | 106 (90.6%) | 117 |

- **Best-bid date of priced theses:** 07-31 358 (all UNGOVERNED) · 08-28 613 (all UNGOVERNED) · 09-04 279 (all 262 GOVERNED + 17).
- **Priced runs:** 20260723, 20260731, 20260815, 20260816, 20260818, 20260820, 20260821, 20260824 and the 3 governed runs. The runs 20260804, 20260808, 20260809 and 20260814 have 0 priced theses because no snapshot falls in their windows.
- **Snapshot position** (days from decision to snapshot ÷ window calendar span), median: UNGOVERNED 0.64; GOVERNED CALL 0.50, PUT 1.00.
- **Entry check:** entry ask in the book equals the phantom_history ask on the decision session where both exist (median ratio 1.000, n=114). Median DB iv / book contract_iv on priced rows = 0.985, which indicates the same units.
- **Selection check:** side_correct rate on priced vs all theses: UNGOVERNED CALL 48.0% vs 45.6%; PUT 55.1% vs 53.8%; GOVERNED CALL 38.5% vs 37.2%; PUT 47.2% vs 49.6%.

## Table 3 — Four-cell side_correct × monetised (PRICED unique theses)
monetised_125 = best in-window snapshot bid ≥ 1.25 × entry ask; monetised_entry = best bid ≥ entry ask.

| condition | dir | n | side-wrong / not mon | side-wrong / mon | side-correct / not mon | side-correct / mon | (≥ entry) SC/not · SC/mon · SW/mon |
|---|---|---|---|---|---|---|---|
| UNGOVERNED_PRE | CALL | 636 | 328 | 3 | 249 | 56 | 218 · 87 · 7 |
| UNGOVERNED_PRE | PUT | 352 | 156 | 2 | 141 | 53 | 114 · 80 · 8 |
| GOVERNED | CALL | 156 | 94 | 2 | 45 | 15 | 37 · 23 · 6 |
| GOVERNED | PUT | 106 | 56 | 0 | 38 | 12 | 36 · 14 · 0 |
| any | OTHER | 0 | INSUFFICIENT_POWER (n=0) | | | | |

- The condition × direction totals are all ≥ 100.
- Rates computed on sub-cells with n < 100 are INSUFFICIENT_POWER, so the GOVERNED side-correct subsets (60 and 50) are not reported as rates.
- **TARGET_FIRST_V × monetised_125:** UNGOVERNED CALL TARGET_FIRST 57 (31 monetised) → INSUFFICIENT_POWER (n=57); PUT 10 → INSUFFICIENT_POWER; GOVERNED 4 / 4 → INSUFFICIENT_POWER. Among not-TARGET_FIRST: UNGOVERNED CALL 28/579 monetised, PUT 46/342.
- **Monetised rates by horizon (PRICED unique):**

| condition | dir | horizon | n | mon ≥1.25× | mon ≥ entry | median bid/ask |
|---|---|---|---|---|---|---|
| GOVERNED | CALL | 1-5 | 156 | 10.9% | 18.6% | 0.42 |
| GOVERNED | PUT | 1-5 | 106 | 11.3% | 13.2% | 0.51 |
| UNGOVERNED | CALL | 1-5 | 135 | 3.0% | 15.6% | 0.81 |
| UNGOVERNED | CALL | 6-10 | 498 | 11.0% | 14.7% | 0.32 |
| UNGOVERNED | PUT | 6-10 | 304 | 16.8% | 25.0% | 0.60 |
| UNGOVERNED | PUT | 1-5 | 45 | INSUFFICIENT_POWER (n=45) | | |
| UNGOVERNED | CALL/PUT | 11-20 | 3 / 3 | INSUFFICIENT_POWER | | |

## Table 4 — Attribution for side-correct-not-monetised (PRICED unique theses, monetised_125 = false)
**Causes, in the order used for first-binding:**
1. MFE_LT_STRIKE_DIST: MFE < signed spot→strike distance.
2. IV_DOWN_10PCT: last in-window snapshot iv ÷ entry contract_iv − 1 ≤ −0.10. This reads the coordinator's "IV change > −10% relative" as a fall of more than 10%; the reading is stated, not confirmed.
3. SPREAD_GT_15PCT: entry (ask−bid)/mid > 0.15.
4. FLAT_DECAY_GE_25PCT: BS value at flat spot after hold×7/5 calendar days ÷ entry value − 1 ≤ −0.25, with r = 0.045, q = 0 and entry iv. The 25% threshold is defined in this probe.
5. DTE_LT_HOLD: calendar DTE < hold×7/5.
6. REACH_RATIO_GT_1_5: structural target distance ÷ (σ_a·√(h/252)) > 1.5, on valid structural targets only.

| first-binding | UNGOV CALL (n=249) | UNGOV PUT (n=141) | GOV CALL (n=45) | GOV PUT (n=38) |
|---|---|---|---|---|
| MFE_LT_STRIKE_DIST | 66 | 43 | 8 | 0 |
| IV_DOWN_10PCT | 43 | 19 | 16 | 6 |
| SPREAD_GT_15PCT | 25 | 10 | 11 | 19 |
| FLAT_DECAY_GE_25PCT | 63 | 39 | 4 | 2 |
| DTE_LT_HOLD | 0 | 0 | 0 | 0 |
| REACH_RATIO_GT_1_5 | 0 | 20 | 0 | 4 |
| NO_CAUSE_IDENTIFIED | 52 | 10 | 6 | 7 |
| power | | | INSUFFICIENT_POWER (n=45) | INSUFFICIENT_POWER (n=38) |

**Multi-cause incidence** (a row can carry several causes):

| | MFE<strike | IV down | spread | flat decay | DTE<hold | reach>1.5 | mean n_causes |
|---|---|---|---|---|---|---|---|
| UNGOV CALL (249) | 26.5% | 30.1% | 38.2% | 72.3% | 0% | 1.2% | 1.68 |
| UNGOV PUT (141) | 30.5% | 19.9% | 31.2% | 66.0% | 0% | 70.2% | 2.18 |

- n_causes distribution: UNGOV CALL 0:52, 1:75, 2:50, 3:44, 4:28. PUT 0:10, 1:36, 2:43, 3:32, 4:11, 5:9.
- **History-free causes on all side-correct theses with a VALID contract** (these do not depend on option coverage): UNGOV CALL (n=534): MFE<strike 28.5%, spread 40.3%, flat decay 77.5%, DTE<hold 4.1%, reach 3.4%. UNGOV PUT (n=300): 28.7%, 37.3%, 67.7%, 4.3%, 65.7%. GOVERNED CALL 64 and PUT 57 → INSUFFICIENT_POWER.
- DTE_LT_HOLD = 0 on priced rows is partly by construction. The pricing window is capped at expiry and requires a snapshot before expiry, so contracts that expire early drop into NO_SNAPSHOT_DATE_IN_WINDOW.

## Table 5 — Side-wrong: invalidation touched vs timeout-negative; realised loss ÷ modelled stop distance
stop_dist = signed spot→invalidation distance. "Touched" means MAE ≥ stop_dist at any time in the window. Loss = −terminal_return.

| condition | dir | class | n | loss/stop q10 · q25 · q50 · q75 · q90 | MAE/stop q50 · q90 | terminal loss > stop | median stop_dist |
|---|---|---|---|---|---|---|---|
| UNGOVERNED_PRE | CALL | INVALIDATION_TOUCHED | 2,626 | 0.35 · 0.75 · 1.24 · 2.07 · 3.54 | 1.89 · 4.61 | 62.0% | 3.0% |
| UNGOVERNED_PRE | CALL | TIMEOUT_NEGATIVE_NO_TOUCH | 1,031 | 0.05 · 0.15 · 0.34 · 0.53 · 0.72 | 0.71 · 0.95 | 0% | 6.0% |
| UNGOVERNED_PRE | PUT | INVALIDATION_TOUCHED | 412 | 0.30 · 0.67 · 1.15 · 1.68 · 2.72 | 1.64 · 3.41 | 57.0% | 6.1% |
| UNGOVERNED_PRE | PUT | TIMEOUT_NEGATIVE_NO_TOUCH | 235 | 0.06 · 0.14 · 0.28 · 0.45 · 0.63 | 0.68 · 0.93 | 0% | 6.9% |
| GOVERNED | CALL | touched / timeout | 60 / 48 | INSUFFICIENT_POWER (n=60, n=48) | | | |
| GOVERNED | PUT | touched / timeout | 18 / 41 | INSUFFICIENT_POWER (n=18, n=41) | | | |
| any | OTHER | — | 0 | INSUFFICIENT_POWER (n=0) | | | |

Touched share of side-wrong: UNGOVERNED CALL 71.8%, PUT 63.7%. The median stop distance of touched CALL theses (3.0%) is half that of timeout-negative CALL theses (6.0%).

## Findings
- **DISC-F-M3-1 — direction versus thesis amount.**
  - Measured: terminal side is correct on 45.4% of CALL and 53.5% of PUT theses. The vol-budget thesis amount is reached before invalidation on 6.6% and 3.4%. Median MFE (4.1% / 4.4%) is about 30% of the median vol-budget distance (13.8% / 14.2%).
  - Does NOT establish: that the vol-budget target is the right thesis amount; that E1 labels are correct (E1 pending); anything about taken trades (all presented-not-taken); any edge versus a base rate (M8's question).
  - TRACE: REQ-NONE | ALG-08 | WP-NONE | STAGE-NONE | TRACK-M3 | EVIDENCE-p23_M3_thesis_outcomes.csv | N=8417
- **DISC-F-M3-2 — four-cell mass.**
  - Measured: on 1,250 priced theses, 50.7% are side-wrong/not-monetised, 37.8% side-correct/not-monetised, 10.9% side-correct/monetised and 0.6% side-wrong/monetised. Among side-correct theses, 77.7% did not reach the 1.25× floor at the observed snapshot.
  - Does NOT establish: that these theses never reached 1.25× between snapshots. The "best bid" is at 1 snapshot (median), so monetisation is a lower bound. It does not establish the rate on the 85% of theses that are unpriced, and does not establish fill feasibility.
  - TRACE: REQ-UNMAPPED | ALG-NONE | WP-NONE | STAGE-NONE | TRACK-M3 | EVIDENCE-p23_M3_monetisation.csv | N=1250
- **DISC-F-M3-3 — what stopped side-correct theses monetising.**
  - Measured: in UNGOVERNED books the most frequent first-binding causes are a move smaller than the strike distance (CALL 26.5%, PUT 30.5%) and flat-scenario decay ≥ 25% (25.3%, 27.7%). Flat decay is present on 72% and 66% of these theses as one of several causes. For PUT, a structural target beyond 1.5σ_h is present on 70.2%. No cause is identified for 20.9% of CALL theses.
  - Does NOT establish: causality (the causes co-occur and the order is imposed); the IV-crush rate on a daily path (1 snapshot); the right decay threshold (25% is defined here); GOVERNED attribution (INSUFFICIENT_POWER).
  - TRACE: REQ-UNMAPPED | ALG-NONE | WP-NONE | STAGE-NONE | TRACK-M3 | EVIDENCE-p23_M3_monetisation.csv | N=390
- **DISC-F-M3-4 — side-wrong theses.**
  - Measured: invalidation is touched on 71.8% (CALL) and 63.7% (PUT) of side-wrong theses. On touched theses the terminal loss ends beyond the stop distance on 62.0% and 57.0%, with median terminal loss/stop 1.24 and 1.15.
  - Does NOT establish: the fill at the stop. Daily bars cannot see gaps through the invalidation or intraday order; gap-through was not measured. It also does not establish the option P&L of stopping out, or anything GOVERNED (INSUFFICIENT_POWER).
  - TRACE: REQ-NONE | ALG-08 | WP-NONE | STAGE-NONE | TRACK-M3 | EVIDENCE-p23_M3_thesis_outcomes.csv | N=4304
- **DISC-F-M3-5 — contract usability and option-history coverage.**
  - Measured: on UNGOVERNED books the selected contract is unusable (no symbol, no ask, or wrong side) on 78.9% of theses (6,412/8,128) — no symbol 3,354 of the 3,356 total (2 are GOVERNED), no entry ask 1,811, symbol side opposite to direction 1,247. Option history has 3 snapshot dates across the priced windows, and 14.9% of all theses are priced.
  - Does NOT establish: whether a valid contract existed in the chain for those theses (M4's question); why the book fields are empty (implementation observation, see Deviations).
  - TRACE: REQ-UNMAPPED | ALG-NONE | WP-NONE | STAGE-NONE | TRACK-M3 | EVIDENCE-p23_M3_monetisation.csv | N=8417
- **DISC-F-M3-6 — monetisation rate by condition.**
  - Measured: GOVERNED 1-5 theses reach ≥1.25× at the 09-04 snapshot on 10.9% (CALL) and 11.3% (PUT). UNGOVERNED 6-10 reach it on 11.0% and 16.8%, and UNGOVERNED CALL 1-5 on 3.0%. Median best bid / entry ask is below 1 in every measured cell (0.32–0.81).
  - Does NOT establish: a governed-versus-ungoverned difference. The horizons differ (1-5 vs 6-10), the snapshot dates differ (09-04 vs 07-31/08-28), market regimes differ, and there is no significance test. It also does not establish performance, since these are TEST-condition presented candidates.
  - TRACE: REQ-UNMAPPED | ALG-NONE | WP-NONE | STAGE-NONE | TRACK-M3 | EVIDENCE-p23_M3_monetisation.csv | N=1250
- **DISC-F-M3-7 — entry geometry (structure only).**
  - Measured: GOVERNED selected contracts are near ATM (median strike distance +0.6% CALL, −1.1% PUT; delta ±0.50), with 18–21 calendar DTE and median spread 14–17%. UNGOVERNED contracts are 3–4% OTM, 29–30 DTE, spread 12–13%. Median flat-scenario decay over the hold is −24% / −17% GOVERNED and −35% / −32% UNGOVERNED.
  - Does NOT establish: that one geometry monetises better. The flat-decay values are model values (BS, entry iv), not observed.
  - TRACE: REQ-UNMAPPED | ALG-NONE | WP-NONE | STAGE-NONE | TRACK-M3 | EVIDENCE-p23_M3_monetisation.csv | N=2003

## Deviations (observations, no severity)
- **Contract geometry fields on pre-20260831 books.**
  - Claimed/expected: books carry the selected contract's strike, expiry, bid and spread.
  - Found: `strike` = 0.0 on 64–84% of rows per run; `expiry` and `contract_bid` populated on 16–36%; `spread_pct` 0% populated on 11 of 12 runs (25% on 20260824); `contract_ask` = 0.0 wherever the bid is missing. `contract_symbol` is populated on 89–96% of rows up to 20260814 and 25–35% from 20260815.
  - Governed books populate all of these fields on 92–95% of rows.
  - Evidence: `p23_M3_monetisation_stdout.txt` lines 1–15.
- **Put symbol on CALL rows (and the reverse).**
  - Found: 1,396 labelled CALL rows and 88 PUT rows on UNGOVERNED books carry an OCC symbol of the opposite side. In `final_opportunity_book_20260814_114553.csv`, 227 of 1,025 CALL rows carry a `P` symbol, e.g. `AA` CALL → `AA260918P00050000`, strike 0.0.
  - Governed books: 0.
  - Evidence: `p23_M3_coverage_addendum.txt` (per-run counts), `p23_M3_monetisation.csv` contract_state=SIDE_MISMATCH.
- **Option history granularity.**
  - Brief assumption: a best daily bid over the window.
  - Found: `options_greeks_history` and `chain_snapshots` carry the same sparse dates (2026-07-10, 07-17, 07-31, 08-28, 09-04 on all 40 sampled tickers). No daily snapshot exists between 07-31 and 08-28. `chain_snapshots` added 0 symbols beyond `options_greeks_history`.
  - Evidence: ticker-sample query in this track's session; `p23_M3_option_snapshots.csv` (1,935 rows, 3 dates).
- **Governed symbols missing from history.** 25 GOVERNED theses have a snapshot for the ticker on 09-04, but their selected symbol is absent.
- **Governed direction fields.** Governed books carry both `governed_direction` and `direction`, and they disagree on some rows (e.g. 20260901_082437 ALNY `governed_direction` = STRANGLE, `direction` = CALL with a call symbol). p31 takes `governed_direction` first, so these rows are OTHER and have no full window.
- **Spot vs price-store path.** 8 theses have MFE or MAE < −20% (the whole window sits more than 20% away from the book spot). They are kept, not excluded.
- **Unique-thesis count.** 8,417 here vs 8,414 in outcome_census; the 3 extra theses have no σ_a (label_V = NO_SIGMA).

## Premise notes (spec / measured / gap; no severity, no recommendation)
- **Thesis amount.**
  - Spec: the ALG-08 vol-budget target is 1.5·σ_a·√(h/252), median 13.8–14.9% for 6-10.
  - Measured: median MFE within the hold is 4.1–4.6%, and the target is reached at any time on 3.9–8.3% of theses.
  - Gap: the median target is about 3.4× the median favourable excursion.
- **Profit floor versus flat decay.**
  - Spec: governed profit floor 0.25 (bid ≥ 1.25 × ask).
  - Measured: median model flat-scenario decay over the hold is −17% to −35%, so the premium to recover before the floor is +42% to +92% of the move-free value. Median observed best bid / entry ask is 0.32–0.81.
  - Gap: the floor is set against entry ask, while decay and spread (median 12–17%) are already charged against it.
- **"Side correct" as the directional quantity.**
  - Spec (§4.3): "did the underlying move the thesis way, by the thesis amount, within the hold".
  - Measured: terminal side and thesis-amount-first diverge on 2,628 of 3,071 UNGOVERNED CALL side-correct theses. A 45–55% side-correct rate is compatible with a 3–7% thesis-amount rate.
  - Gap: the two definitions differ by roughly 40 percentage points.
- **Structural target reach (PUT).** On 65.7% of UNGOVERNED PUT side-correct theses with a valid contract, the structural target is more than 1.5 σ_h away. The structural-target TARGET_FIRST_S rate for PUT 6-10 is 1.4% (n=1,180).
- **Invalidation distance.** Touched CALL theses have median stop distance 3.0% against median σ_h-scaled vb_dist 14.4%. The stop sits much closer to spot than the target, and 71.8% of side-wrong CALL theses touch it.

## Not tested / partial
- **Best daily bid:** PARTIAL. Daily option history is absent (3 snapshot dates). Measured at in-window snapshots only. Would need daily `options_greeks_history` rows for 2026-07-22 → 2026-09-10 for the selected symbols.
- **Monetisation for 7,167 unpriced theses:** DATA_UNAVAILABLE (contract fields empty or wrong-side on the book, or no snapshot in the window).
- **Gap-through at invalidation / loss at stop fill:** not measured; needs intraday or open-vs-invalidation logic on the touch session.
- **IV-crush attribution on a path:** PARTIAL (1 snapshot iv).
- **OTHER:** n = 0 in the full-window labelled set.
- **E1 cross-check of p32 labels:** pending (parallel track).
- **Significance tests between conditions:** not run. The conditions are confounded by horizon and snapshot date.

## Expectation vs actual (expectations.md, M3 row)
- **Monetised outcomes.** Expected: DATA_UNAVAILABLE (no fills, no option outcome history). Actual: PARTIAL. Option snapshot history exists at 3 dates inside the windows, and 1,250 of 8,417 unique theses (14.9%) could be priced. There are still no fills.
  - Gap: better than expected on availability; coverage is thin and point-in-time.
- **Directional outcome reconstructable.** Expected: yes. Actual: yes, 8,417 unique theses. Gap: none.
- **Side-correct rate.** Expected: 45–55% by direction. Actual: CALL 45.4%, PUT 53.5%; GOVERNED CALL 37.2% (n=172), below the band.
- **Not pre-registered:** thesis-amount-first rate (3.4–6.6%); 78.9% of UNGOVERNED theses without a usable selected contract; side-correct-not-monetised at 78% of priced side-correct theses.

## State log lines
```
M3-thesis-outcomes,MEASURED,8417,15s,"unique theses; side_correct CALL 45.4% PUT 53.5%; TARGET_FIRST_V CALL 6.6% PUT 3.4%; GOVERNED 289 (1-5 only); OTHER n=0"
M3-contract-coverage,MEASURED,8417,60s,"PRICED 1250 (14.9%); NO_SYMBOL 3356 NO_ENTRY_ASK 1811 SIDE_MISMATCH 1247 NO_SNAPSHOT 725 SYMBOL_ABSENT 28; option history 3 snapshot dates in windows"
M3-four-cell,PARTIAL,1250,60s,"priced only; SW/notmon 634 SC/notmon 473 SC/mon 136 SW/mon 7; best bid at snapshot (median 1 per window), not daily"
M3-attribution-SC-not-monetised,PARTIAL,473,5s,"UNGOV CALL 249 PUT 141 measured; GOV 45/38 INSUFFICIENT_POWER; top first-binding MFE<strike and flat decay; decay incidence 66-72%"
M3-side-wrong,MEASURED,4471,5s,"UNGOV touched CALL 71.8% PUT 63.7%; touched terminal loss>stop 62.0%/57.0%; GOV cells INSUFFICIENT_POWER; gap-through not measured"
```
