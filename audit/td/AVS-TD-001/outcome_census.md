# Outcome census (§4.4)

No NORMAL_COMPLETED_SESSION run exists; every stored run is TEST condition. This census counts what exists; it reports no verdict.

**Data sources.** Decision/outcome ledger copy (`db_copies/decision_outcome_ledger.sqlite`, table `ledger_events`, 8,290 rows); the `final_opportunity_book_<run>.csv` of every one of the 22 runs that wrote one (2026-07-23 → 2026-09-11); `historical_prices.sqlite` copy (`ohlcv_daily`, split-adjusted daily OHLC to 2026-09-10); `qomega/garch_forecasts_<run>.csv` on the same 22 runs (annualised forecast per ticker per run, needed for the ALG-08 point-in-time budget). Probe: `probes/p31_outcome_census.py`; outputs `p31_ledger_events_by_run.csv`, `p31_presented_candidates.csv`, `p31_bucket_population*.csv`.

## 1. Decisions in the ledger versus outcomes

| Item | Count |
|---|---|
| `CANDIDATE_DECISION` events | 4,931 (3,478 unique run × ticker × direction) |
| … by direction | CALL 3,023 · PUT 1,720 · STRANGLE 138 · UNRESOLVED 50 |
| … by run | 20260905_151448 294 · 20260906_213931 264 · 20260909_071646 940 · 20260910_150045 1,241 · 20260911_115904 (5,550 events of all types) |
| `EXECUTION_DECISION` | 1,679 |
| `VALIDATION` | 1,679 |
| `HumanDecisionRecorded` | 0 (event type does not exist in the ledger) |
| `FillRecorded` | 0 (event type does not exist) |
| `OUTCOME` | 1 — a `QA_CLOSE` test row in `run_001` (2026-09-05), `outcome_class = PROCESS_WIN`, no MFE/MAE, no horizon |
| `OUTCOME_OBSERVATION` | 0 |
| Decisions with a resolved target / invalidation / timeout outcome | **0** |
| Decisions with `planned_hold_sessions` populated | 0 of 4,931 (field present, always null) |
| Decisions with target and invalidation populated | 4,931 of 4,931 |

The ledger only begins on 2026-09-05. Every candidate presented by the 17 earlier runs (2026-07-23 → 2026-09-04) was never written to the ledger; those rows exist only in the run artefacts. The maturation stage on the primary run found 3,252 candidate events, 0 eligible, 3,252 ineligible, 0 deferred (`diagnostics/outcome_maturation_<run>.json`) — Track H explains the eligibility rule.

## 2. Presented candidates in run artefacts and retrospective reconstructability

| Item | Count |
|---|---|
| Presented rows across 22 run books | 17,116 |
| Directed rows (CALL / PUT) | 16,711 (CALL 13,220 · PUT 3,491) · OTHER 405 |
| Directed rows with target, invalidation and spot present | 97.2% / 96.9% / 100% |
| Directed rows with a hold label | 14,082 (`6_10d` 10,968 · `1_5d` 2,965 · `11_20d` 149); `unrouted` 2,629 |
| Rows whose full hold window is inside the price store (as of 2026-09-10) | **9,926** (CALL 8,177 · PUT 1,749) |
| Rows with a partial window (hold not yet elapsed) | 2,537 |
| Rows whose window has not started (11 Sep run) | 1,023 |
| Rows with missing geometry (no target or invalidation) | 596 |
| Not directed / no hold | 3,034 |
| Unique (ticker, direction, decision session) among directed rows | 14,312; with full window 8,421 |
| Tickers in the directed set with daily bars in the price store since July | 1,771 of 1,771 (100%) |

Triple-barrier outcomes (TARGET_FIRST / INVALIDATION_FIRST / TIMEOUT / AMBIGUOUS_TOUCH_ORDER) can therefore be reconstructed retrospectively from daily OHLC for 9,926 presented rows (8,421 unique theses) using the row's own structural target and invalidation, and for the ALG-08 vol-budget target for the subset where a point-in-time annualised forecast exists (`garch_forecast_vol` is on the final book only from 20260831 onward, 26% of directed rows; the `qomega/garch_forecasts_<run>.csv` file exists on all 22 runs and supplies σ_a for the rest — Track M3 uses it). Daily bars cannot order a same-session dual touch; those cases are AMBIGUOUS by construction.

Note on direction fields: runs before 20260831 carry `direction` only (pre-governance); runs from 20260831 carry `governed_direction`. Both were used as the directed label; the census does not assert they are equivalent.

**Geometry validity of the stored targets (probe `p32_labels.py`, 9,896 labelled rows).** The invalidation level is on the correct side of spot on 100% of rows in both directions. The structural target is on the correct side on 18.4% of CALL rows and 100% of PUT rows — because on every book before 20260831 the `structural_target` column holds **0.0** on 76–92% of CALL rows per run and on the majority of PUT rows (target-distance fraction exactly −1.0 for CALL and +1.0 for PUT): the zero-as-missing defect that AVS-FIX-001 W1.1 removed on 6 Sep. Books from 20260831 onward carry a non-zero target on 98–100% of rows. Consequently:

| Outcome set | Rows | Unique theses |
|---|---|---|
| Vol-budget barrier labels (ALG-08 target = S_d(1 ± 1.5·σ_a·√(h/252)), invalidation = row's own) — σ_a available | 9,893 | 8,414 |
| Structural barrier labels (row's own target, target > 0 and correct side, invalidation correct side) | 3,243 (CALL 1,501 · PUT 1,742) | ~2,760 |

Every later track states which set it uses. Labels, MFE/MAE, terminal return and sessions-to-hit are in `probes/p32_labels.csv` (columns `label_V`, `label_S`, `t_hit_*`, `s_hit_*`, `terminal_return`, `mfe`, `mae`, `side_correct`). Hold h is the routed bucket's upper bound (1_5d → 5, 6_10d → 10, 11_20d → 20), a stated assumption because the books do not carry an integer hold and the ledger's `planned_hold_sessions` is null.

Headline counts from the vol-budget set, unique theses (RESEARCH_ONLY, TEST-condition books, presented-not-taken, no fills): CALL 6–10: INVALIDATION_FIRST 3,030 · TARGET_FIRST 396 · TIMEOUT 2,592; PUT 6–10: 428 · 40 · 712; CALL 1–5: 362 · 53 · 428; PUT 1–5: 71 · 11 · 249. Side-correct (terminal close in the thesis direction): CALL 44.3%, PUT 52.8%.

## 3. Bucket population — hidden_state × phase × compression × direction × horizon

`compression` is bucketed by terciles of `compression_energy` across all presented rows (LOW / MID / HIGH). `phase` is absent from every run before 20260831 (12 of 22 runs), so for those rows the phase key is NaN — the buckets below are coarser than the ALG-09 key assumes. Horizon = the routed hold label.

**Full-window reconstructable rows (9,926):** 66 populated buckets; n ≥ 200: **9**; n ≥ 100: **10**; n ≥ 50: 16; median bucket n = 4; modal bucket n = 3,077.

| hidden_state | phase | compression | direction | horizon | n |
|---|---|---|---|---|---|
| LOW_ENERGY_NO_EDGE | (absent) | LOW | CALL | 6-10 | 3,077 |
| LOW_ENERGY_NO_EDGE | (absent) | MID | CALL | 6-10 | 1,854 |
| COMPRESSED_BALANCED | (absent) | HIGH | CALL | 6-10 | 1,659 |
| LOW_ENERGY_NO_EDGE | (absent) | LOW | PUT | 6-10 | 637 |
| COMPRESSED_BALANCED | (absent) | MID | CALL | 6-10 | 590 |
| LOW_ENERGY_NO_EDGE | (absent) | MID | PUT | 6-10 | 357 |
| COMPRESSED_BALANCED | (absent) | HIGH | CALL | 1-5 | 296 |
| COMPRESSED_BALANCED | (absent) | HIGH | PUT | 6-10 | 290 |
| LOW_ENERGY_NO_EDGE | (absent) | LOW | CALL | 1-5 | 230 |
| LOW_ENERGY_NO_EDGE | (absent) | MID | CALL | 1-5 | 165 |
| COMPRESSED_BALANCED | (absent) | MID | PUT | 6-10 | 97 |
| COMPRESSED_BALANCED | (absent) | HIGH | PUT | 1-5 | 87 |

**Unique theses with full window (8,421):** 66 buckets; n ≥ 200: 8; n ≥ 100: 10; n ≥ 50: 15; modal 2,518.

**Coarser keys (full window):**

| direction × horizon | n | | hidden_state × direction | n |
|---|---|---|---|---|
| CALL 1-5 | 946 | | LOW_ENERGY_NO_EDGE CALL | 5,380 |
| CALL 6-10 | 7,180 | | COMPRESSED_BALANCED CALL | 2,715 |
| CALL 11-20 | 51 | | LOW_ENERGY_NO_EDGE PUT | 1,147 |
| PUT 1-5 | 361 | | COMPRESSED_BALANCED PUT | 562 |
| PUT 6-10 | 1,381 | | COMPRESSED_BEARISH_FORCE CALL/PUT | 58 / 20 |
| PUT 11-20 | 7 | | all TRENDING_* and COMPRESSED_BULLISH_FORCE | ≤ 9 each |

**All presented directed rows (16,711), for comparison:** 139 buckets; n ≥ 200: 18; n ≥ 100: 26; n ≥ 50: 47; median 19.

## 4. Headline for the later tracks

The modal bucket is not small: it is one cell, LOW_ENERGY_NO_EDGE / LOW compression / CALL / 6–10 sessions, holding 31% of every reconstructable row. The population is dominated by two hidden states (LOW_ENERGY_NO_EDGE 66%, COMPRESSED_BALANCED 33%), one horizon (6–10: 86%) and one direction (CALL 82%). Every hidden state other than those two has fewer than 60 rows in total. The 11–20 horizon has 58 rows. At the full five-key granularity only 10 cells reach n ≥ 100, and none of them carries a `phase` value, because the phase field did not exist before 20260831. Any calibration keyed as ALG-09 specifies is therefore feasible today only at the granularity direction × horizon (5 cells ≥ 100) or hidden_state × direction (4 cells ≥ 100), and only for theses whose 6–10 session hold has elapsed. The ledger contributes no resolved outcome to any of this; every outcome used downstream is a retrospective reconstruction from daily OHLC on presented-but-not-taken candidates, none of which is a fill.

Every later discovery track reads this table and sizes itself to it: M3 and M8 use the 9,926 / 8,421 reconstructable set; M5 uses run-to-run repeats within it; M6 uses the removed-versus-survivor split within it.

## State log lines

```
4.4-outcome-census-ledger,MEASURED,4931,60s,"CANDIDATE_DECISION 4931 (5 runs from 20260905); resolved outcomes 0; FillRecorded/HumanDecisionRecorded event types absent; planned_hold_sessions null on all"
4.4-outcome-census-presented,MEASURED,17116,240s,"22 run books; directed 16711 (CALL 13220 PUT 3491); full-window reconstructable 9926 (unique 8421); partial 2537; not started 1023; missing geometry 596"
4.4-outcome-census-buckets,MEASURED,66,10s,"5-key buckets with full window: 66; n>=200: 9; n>=100: 10; n>=50: 16; modal 3077 (LOW_ENERGY_NO_EDGE/LOW/CALL/6-10); phase absent on 12 of 22 runs"
```

## Addendum after the artefact inventory (§2.2 step 7)

The inventory flagged two artefacts no track had opened that bear on items reported here as assumptions or gaps. Both were opened.

- **Hold length.** `options/options_candidates_ranked.csv` and `options/options_intelligence_latest.csv` carry `planned_hold_sessions` on all 1,444 rows of the primary run (5 on 972, 10 on 472), and the column is fully filled in 17 of the 22 runs that have the file. That matches the census assumption that the routed bucket `1_5d` means 5 sessions and `6_10d` means 10. The ledger's `planned_hold_sessions` is still null on all 4,931 decisions (DEV-14, UAT-D for H1), so the hold is recoverable from run artefacts but not from the decision record. The same file's hold disagrees with `options_intelligence_<run>.csv`, `superbrain_enriched` and `pre_ev3_authority` on 739 of 1,444 tickers, which leave 188 null; no track assumed those three files' hold, so no label changes.
- **Completed session.** `completed_thesis_receipt_inv_*.json` records `completed_session = 2026-09-10` at run level for the primary run, which supplies the value the ledger decision payloads lack for that run.

Neither item changes any count in this census.
