# Phase 0 characterisation report: run 20261006_060401

**Date:** 7 Oct 2026. **Design:** `Enhancements/decision_map/DISCOVERY_VANGUARD_REDESIGN_20261007.md` §12, phase 0. **Status:** complete, for ACK to read; reading it is the phase's acceptance step.

**Scope:**
- Read-only on the frozen run.
- **One approved data change**: the daily-history backfill (§9), approved by ACK on 7 Oct.
- No pipeline code changed, no pipeline run, no provider call.

**How every number is reproduced:**
- [p0_characterise.py](p0_characterise.py) extracts the run once into `tests/fixtures/phase0/`, then measures from that extract only.
- Results: [p0_characterisation.json](p0_characterisation.json).
- Recall losses: [P0_DISCOVERY_RECALL_LOSSES.md](P0_DISCOVERY_RECALL_LOSSES.md), [p0_recall_losses.py](p0_recall_losses.py).
- Duplicate output keys: [p0_duplicate_keys.py](p0_duplicate_keys.py).

**Pinned by tests (11 pass, each file run on its own):**
- `tests/test_phase0_characterisation.py` (9)
- `tests/test_phase0_duplicate_output_keys.py` (2)

These tests describe **today's defects**. Each later phase changes one of these numbers and must update the matching assertion in the same change, stating why.

---

## 1. Summary

| # | Finding | Size on the frozen run | Fixed in |
|---|---|---|---|
| F1 | **The card assembles its story from different sources** | Setup ≠ thesis on 646 of 1,052 (32 of 51 GO); target from the legacy `PRIOR_RANGE_EXTREME` on all rows; trigger from Wall-Break on all 1,039; thesis candidate's own contract found for only 244 | Phases 1, 2, 5 |
| F2 | **Five compression definitions** that rarely agree | All four comparable producers agree on 172 of 768 tickers (22%) | Phase 1 |
| F3 | **Direction producers point opposite ways** | The legacy resolver is opposite to the thesis on 608 of 1,006; precor intent on 626 of 903 | Phase 2 |
| F4 | **Five target producers** | Discovery's `structural_target` differs from the thesis candidate's target on 990 of 1,041 (median gap 6.4%) | Phases 1, 5 |
| F5 | **The trigger layer reads trend state, not events**; VWAP and TRAP never fire | VWAP 0, TRAP 0, no trigger on 814 of 1,636; 822 "GO-eligible" with no level checked | Phase 3 |
| F6 | **Silent overwrites in output records** | Discovery publishes precor's `crabel_score` after its own score set the tier; the EOD engine overwrites the contract quote timestamp | Phase 1 |
| F7 | **Recall loss from short daily history** | 1,221 tickers dropped (918 "intraday only untested" + 303 "no live setup"), all seeded with about 92 bars | **Data fixed 7 Oct** (§9); labels in phase 1 |
| F8 | **Vetoes before the human** | 1,814 → 51 GO; 16,500 of 18,500 candidates deferred by a resource cap | Phases 2, 5 |
| F9 | **Vanguard side evidence fails on every row** | `SIDE_BLOCK_ERROR:TypeError` on 1,702 of 1,702 (timezone seam, RC01) | Phase 4 |
| F10 | **Stale and unservable universe symbols** | 278 symbols returned "No data"; 110 survivors are stale and unflagged; 28 unservable; 7 crashes on mixed date formats | Later phase (universe hygiene) |
| F11 | **Two daily-history stores with different coverage** | The canonical store held about 92 bars for ~1,270 tickers while actuarial v7 held full history for the same tickers | Fact ownership register (design §14) |

## 2. Ticker funnel and vetoes

| Stage | Tickers |
|---|---|
| Universe (`polygon_liquid_universe.csv` 3,320 + 5 scanner tickers) | 3,325 |
| Discovery survivors | 1,814 (side: 743 BEAR, 426 BULL, **645 UNASSIGNED**) |
| Vanguard pass / reject | 1,702 / 112 (all `DATA_FAILURE_NO_OHLCV`; history-policy issue, RC04) |
| Options, Morning and Lab | 1,636 (66 excluded by the WAIT scope rule) |
| **Lab GO / GO_LIMIT** | **51** (24 / 27) |

**Lab verdicts:** BLOCKED 834, MANUAL_REVIEW 732, CONTRACT_REPAIR 19.

**Top reasons for not GO:**

| Reason | Rows |
|---|---|
| Direction not executable (unresolved side) | 584 |
| Option liquidity still pending | 440 |
| Campaign verdict missing | 243 |
| Thesis under pressure (an unrecognised state) | 127 |
| Target or invalidation on the wrong side of the signal price | 111 |
| Wait for pullback | 42 |

## 3. Candidate-level dispositions (not only tickers)

| Stage | Count |
|---|---|
| Engine candidate records | 29,009 over 3,007 tickers: DETECTED 16,401; MONITOR (undirected) 6,904; OUTCOME_REACHED 3,100; ACTIVATED 2,099; FAILED 505 |
| Expression lane (directed, live) | 18,500 |
| Expression status | **DEFERRED_RESOURCE 16,500** (cap of 2,000); CONTRACT_FOUND 1,048 (613 tickers); NOT_ROUTED 949 (479 outside options scope, 470 chain not authorised); NO_CONTRACT_FIT 3 |

**The governing thesis candidate is usually not the one that gets a contract.** Its median handoff rank is 4,194, against a cap of 2,000. Of the 1,052 directed thesis candidates that reach the Lab, 808 are deferred.

## 4. F1: the story on the card

All 1,052 directed thesis candidates in the Lab, compared by candidate ID with a strict tolerance (relative 1e-4):

| Part | Result |
|---|---|
| Setup shown (`trade_lane_setup`) vs the thesis candidate | Differs on **646** (32 of the 51 GO rows) |
| Target | Source is `PRIOR_RANGE_EXTREME` on all 964 rows that have one. It differs from the candidate's own `Outcome_Level` on **907 of 951** |
| Trigger | Source is `WBS_PHASE_C_CONFIRMED_BREAK` on all 1,039. It differs from the candidate's `Trigger_Level` on **1,038 of 1,039** |
| Invalidation | Differs on only 8. Already carried correctly from the candidate |
| Contract | The thesis candidate's own contract was found for 244. Options vs Morning contract differs on 144; Morning repaired 60; expression vs final Lab contract differs on 55 |

**What already works:** the card's `anticipated_level` equals the thesis outcome level on 707 of 998 rows (§7). The side never flips anywhere.

These counts differ slightly from the first, ad hoc trace (for example 1,038 vs 1,009 trigger mismatches) because of the strict tolerance. The values here are the reproducible ones and are pinned by tests.

## 5. F2: compression

| Producer | Compressed | Not | Not measured |
|---|---|---|---|
| Discovery `crabel_compression` (ATR7/ATR20 + NR7) | 339 | 1,475 | 0 |
| Precor `crabel_state` (NR7/NR4/ATR percentile/inside bars) | 727 | 141 | 946 |
| Engine `compression.py`, daily reading (box, location, contracting side) | 439 | 1,219 | 156 |
| Trigger-layer T1 (`VOL_COMPRESSION*`) | 626 | 1,010 | 178 |

- A fifth definition, `detect_early_position` (ATR vs its 60-day average), feeds the early-position tier.
- `crabel_bucket` mixes precor's score with Discovery's pattern.

**Pairwise agreement:**

| Pair | Agree | Out of |
|---|---|---|
| Discovery vs engine | 1,251 | 1,658 |
| Precor vs engine | 361 | 819 |
| Trigger layer vs precor | 753 | 816 (the trigger layer mostly copies precor) |
| **All four agree** | **172** | **768 (22%)** |

**Also:**
- Discovery's percentile defaults to **50 ("neutral") when history is thin**, and precor's ATR percentile defaults to 0.5. Both break the "missing is never neutral" rule (R1).
- Discovery's compression score feeds the **tier, the composite score and a "win probability"**.

## 6. F3: direction

The comparison uses the side where both producers give one:

| Producer vs the thesis side | Both directed | Same | Opposite |
|---|---|---|---|
| Legacy resolver (`legacy_direction`) | 1,006 | 398 | **608** |
| Precor intent | 903 | 277 | **626** |
| Precor intent (raw) | 1,017 | 253 | **764** |
| Fusion direction | 36 | 13 | 23 |
| Dominant trend | 713 | 669 | 44 |

The legacy and precor producers still feed displayed fields, scores and the trigger layer's own direction fallback (`trigger_layer._direction`). That makes five direction owners.

## 7. F4: targets

Each producer is compared with the thesis candidate's `thesis_outcome_level`:

| Producer | Comparable | Differs | Median gap |
|---|---|---|---|
| `structural_target` (Discovery, legacy geometry) | 1,041 | **990** | 6.4% |
| `target_price` (downstream) | 942 | 899 | 6.2% |
| `legacy_structural_target` | 303 | 303 | 20.8% |
| `asymmetry_target1` | 36 | 36 | 45.7% |
| `anticipated_level` (card) | 998 | 291 | ~0% (matches on the rest) |

## 8. F5: trigger layer

| `trigger_primary` | Rows |
|---|---|
| NONE | 814 |
| VOL_COMPRESSION | 271 |
| VOL_COMPRESSION_IV_UNVERIFIED | 189 |
| VOL_COMPRESSION_IV_RICH | 166 |
| RANGE_BREAK_EARLY | 161 |
| RANGE_BREAK | 35 |

- Codes containing **VWAP_RECLAIM: 0, VWAP_LOSS: 0, TRAP: 0.**
- GO-eligible 822, not 814.

**Causes, from the code:**
- RANGE_BREAK is a trend-state test (markup + EMA aligned + ADX ≥ 25). No boundary is checked.
- VWAP events need Vanguard's controller, which is NEUTRAL on every row (RC02).
- TRAP is disabled.

## 9. F7: recall losses, root cause and the data fix (executed)

**Root cause** (detail in [P0_DISCOVERY_RECALL_LOSSES.md](P0_DISCOVERY_RECALL_LOSSES.md)):
1. On 22 Aug the canonical price store was seeded from Discovery's 90-day CSV cache, and nothing ever fetched older history.
2. About 1,270 tickers held about 92 bars starting 26 May 2026.
3. The engine needs 120 daily, 60 weekly and 36 monthly bars before it reads a chart, so these tickers were never read.
4. They were labelled "intraday only untested" or "no live setup" and dropped (`trade_lane.py:164–176`, `avshunter_discovery_ULTIMATE.py:2732`).

**Replay before the fix:** 30 healthy survivors cut to 92 bars went from 29 with a setup to 0.

| Reason (3,325-ticker lifecycle) | Tickers | Verdict |
|---|---|---|
| INTRADAY_ONLY_UNTESTED | 1,036 | 918 short history (**defect**); 47 stale or dead symbols; 71 genuine |
| NO_LIVE_SETUP | 331 | 303 short history (**defect**); 23 stale or dead; 5 genuine |
| ELIG_INSUFFICIENT_BARS | 109 | Correct rule. 104 are stale symbols the provider no longer serves |
| NO_PRICE_DATA | 28 | Unservable universe symbols (SPX, SPXW, class shares, delisted) |
| SCAN_EXCEPTION_ValueError | 7 | Delisted names; a mixed-date-format crash in the stale-CSV fallback (latent robustness defect) |

**Data fix, executed 7 Oct 2026 with ACK's approval:**
- **Script:** [p0_backfill_daily_history.py](p0_backfill_daily_history.py).
- **Source:** Polygon grouped-daily bars already on disk. No provider calls.
- **Rules:**
  - insert-only, before each ticker's first stored date;
  - only the contiguous history that joins the existing data;
  - a join check on the overlapping days.
- **Result:**
  - **1,342,130 bars inserted for 1,241 tickers**; 0 revised, 0 unchanged, 0 rejected;
  - **1,229 tickers now have ≥ 260 bars**;
  - the join matched to the cent on every backfilled ticker.
- **Backup:** `data/canonical/backups/historical_prices.pre_history_backfill_20261007T221941Z.sqlite`.
- **Receipt:** [backfill_receipts/daily_history_backfill_execute_20261007T221941Z.json](backfill_receipts/daily_history_backfill_execute_20261007T221941Z.json).
- **Skipped, with reasons (58):** 29 too few overlapping days; 17 no earlier history on disk; 8 split mismatch at the join (these need a split-aware fetch); 4 gap at the join.

**Verification:** 20 sampled former "intraday only untested" tickers. Before: 0 of 20 read on the daily chart. After: **19 of 20 read, all 19 with a live directed daily, weekly or monthly setup.**

**Actuarial v7:** already covers all 1,241 backfilled tickers (median 1,204 rows from Dec 2021), so no change is needed. The gap was confined to the canonical store (F11).

**Expected effect:** roughly 1,000 or more extra tickers in Discovery on the next Evening run. That's an estimate; ACK's run will measure it.

**Still open:** the labels. "Insufficient daily history" must become its own disposition rather than "intraday only untested" (phase 1).

## 10. F6: duplicate keys in output records (static scan of decision-path modules)

| Location | Keys written twice | Effect |
|---|---|---|
| `avshunter_discovery_ULTIMATE.py:2231` (signal record) | `crabel_score`; `bar_data_asof`, `bar_data_days_old`, `data_source`, `is_stale` | **`crabel_score`**: the published value (precor's, line 2335) is not the value that set the tier (Discovery's, line 2249). The freshness keys repeat identical values, so they are harmless |
| `eod_candidate_engine.py:2391` (candidate record) | `quote_as_of`, `option_chain_dataset_id`, `remaining_runway_state`, `signal_type`, `momentum_tier` | **`quote_as_of`**: the contract quote timestamp (line 2498) is overwritten by the generic field (line 2534), which affects quote-age disclosure. The others repeat the same expression |
| `scripts/core_intel_exporter.py:114` | `l1__confidence`, `l2__edge_status`, `pm_action` | Display exporter; review in phase 5 |

## 11. Defect register handed to the later phases

| ID | Defect | Owner module | Phase | First failing test (business rule) |
|---|---|---|---|---|
| P0-01 | The story is mixed (F1) | Discovery 1685–2090; `options_candidate_lane.py`; `eod_candidate_engine.py:2777`; `lab_control.py:4549` | 1, 2, 5 | One `thesis_id` has the same side, trigger, target, invalidation and contract at every stage |
| P0-02 | Five compression producers (F2) | `compression.py` (owner) | 1 | Compression fields are written only by the engine; a thin history gives NOT_MEASURED |
| P0-03 | Five direction producers (F3) | Discovery thesis step (owner) | 2 | Only the thesis step writes side |
| P0-04 | Five target producers (F4) | Candidate `Outcome_Level` (owner) | 1 | A thesis target equals the candidate's `Outcome_Level` |
| P0-05 | State-based trigger layer (F5) | `trigger_layer.py` | 3 | A close beyond `box_high` with acceptance gives BREAK_ACCEPTED_UP at that bar; VWAP events come from bars |
| P0-06 | Silent overwrites (F6) | Discovery 2231; EOD 2391 | 1 | No decision-path record writes a field twice |
| P0-07 | Wrong disposition label for short history (F7) | `trade_lane.py:164–176`; Discovery 2732 | 1 | Insufficient daily history is reported as INSUFFICIENT_DAILY_HISTORY, never as INTRADAY_ONLY_UNTESTED |
| P0-08 | Vetoes and the resource cap (F8) | `handoff_packet._rank_key`; `options_candidate_lane.py:50`; Options WAIT scope `:10274`; Lab gates | 2, 5 | No candidate disappears without a recorded disposition |
| P0-09 | Side-evidence timezone seam (F9 / RC01) | `actuarial_query.py:169` | 4 | The same session cut gives the same result whether stored as a date or a UTC timestamp |
| P0-10 | Stale and unservable universe; stale survivors unflagged; mixed-date crash (F10) | Universe file; Discovery load and fallback; `WyckoffEngine_3101_v2.py:1534` | Hygiene step | A stale ticker carries a freshness flag; a dead symbol has a recorded universe disposition |
| P0-11 | Two history stores (F11) | Canonical store (owner) | Register | The actuarial builder and Discovery read the same daily history |

Defects already registered in the 7 Oct Codex audit (RC02–RC08, RC10, RC12–RC18) stay in the design's phase plan; Phase 0 did not re-measure them.

## 12. Effect on the overnight universe test

The candidate scan started before the backfill, so tickers it had already processed saw short histories. After the scan, the backfilled tickers will be re-scanned so the panel reflects the corrected store. This is recorded as a data-state note in the test's deviation log; the rules are unchanged.

## 13. Proposed next step: phase 1 (needs ACK's go-ahead)

Phase 1, as in design §12:
- **CandidateRecord and compression episode:** the engine becomes the single candidate and compression source.
- **Corrected labels:** P0-07.
- **Removal of the duplicate-key overwrites:** P0-06.
- **Characterisation first:** each step starts with its failing business-rule test, and the matching Phase 0 assertion changes in the same commit.
