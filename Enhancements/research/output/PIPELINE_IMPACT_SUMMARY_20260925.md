# Pipeline impact summary — merged Model 5 + 7 + 8 harness, extended tests

**Date:** 2026-09-25 · **State:** EXPLORATORY_NO_AUTHORITY · read-only against completed runs · pipeline untouched
**Harness:** `Enhancements/research/harness/merged_5_7_8_scenario_harness.py` v0.1 (self-test passes the ALG-04 worked example). Convention for every run below: horizon-bucket hold, r = 0.04, bias 1.0 unless stated.
**Tests run:** (1) the full 1,532-row 24 September book; (2) twelve completed books from 9 to 24 September; (3) vol-budget bias sensitivity 0.70–1.15. **Not yet run:** database-backed tests for models 3 and 6; they wait for the evening orchestrator (run `20260925_061649`, still in progress at the time of writing) to exit.

---

## 1. What the tests say about the pipeline, in five findings

### Finding 1 — Under a consistent net-of-friction valuation, the actionable book is net negative and the GO tier is not the best tier

| Lab verdict (24 Sep) | Rows | Valued | Grid EV > 0 | Median grid EV | Median FLAT | Median REACHABLE | Median spread |
|---|---|---|---|---|---|---|---|
| GO | 169 | 169 | 9 | −16.1% | −28.3% | +65.9% | 4.6% |
| GO_LIMIT | 232 | 232 | 22 | −20.0% | −28.4% | +48.3% | 13.4% |
| MANUAL_REVIEW | 592 | 253 | 22 | −32.1% | −42.0% | +21.8% | 19.2% |
| BLOCKED | 492 | 60 | 13 | −13.7% | −21.9% | +60.3% | 15.3% |
| CONTRACT_REPAIR | 47 | 0 | — | — | — | — | — |

Impact: the Lab verdict orders rows by gate outcome, not by value. Only 5% of GO rows and 9% of GO_LIMIT rows have a positive probability-free expectancy after friction and time decay, and the 60 valuable BLOCKED rows sit at a better median than GO. This is the "rank, don't gate" rule (R11) measured on the pipeline's own numbers. The GO tier does have the tightest spreads (4.6% of mid), so the liquidity gates are doing their job; the value gates are not.

### Finding 2 — The pipeline cannot value 53% of its own book, for four reasons that are all upstream defects, not market absence

| Reason the harness could not value a row | Rows | What it is in pipeline terms |
|---|---|---|
| Spread outside the friction model domain (> 30% of mid) | 383 | Contract selection is publishing quotes ALG-04 says must be INDETERMINATE. 339 of them are MANUAL_REVIEW rows |
| Target and invalidation both missing | 184 | The Thesis context did not publish geometry; matches the 185 handoff defects in the manifest (fix item F5) |
| No contract at all (strike, DTE, IV, quote, direction all missing) | 190 | The 127 + 63 rows with no expression; mostly BLOCKED |
| Target missing only | 41 | Partial geometry |
| Other (one-sided quote, hold beyond expiry) | 10 | Quote validity (ALG-12) |

Impact: 818 of 1,532 rows are unvaluable, and 435 of those are missing fields the spec says an upstream owner must publish or explicitly mark. Any ranking built on top of today's book would be ranking the 714 rows that happen to be complete, which is a selection the pipeline does not control or record.

### Finding 3 — The set of positive rows does not persist from one session to the next

| Run | GO+GO_LIMIT | Grid EV > 0 | Median EV | Median spread | Positive-set overlap with previous positive set |
|---|---|---|---|---|---|
| 20260911_115904 | 19 | 3 | −20.3% | 12.0% | — |
| 20260916_223756 | 20 | 7 | −10.1% | 12.9% | — |
| 20260918_112522 | 515 | 80 | −18.3% | 8.9% | — |
| 20260920_203115 | 206 | 3 | −23.5% | 12.6% | — |
| 20260922_000106 | 249 | 2 | −23.9% | 12.1% | 0.00 |
| 20260922_223221 | 359 | 44 | −18.1% | 9.0% | 0.00 |
| 20260924_085940 | 401 | 31 | −17.7% | 9.5% | 0.13 |

Runs on 10, 13, 17 and 19 September produced zero GO rows and are omitted; the dirty run of 14 September is excluded per the backtest report; the 9 September run had four rows.

Impact: two things are unstable at once. The actionable count swings from 0 to 515 between adjacent sessions, which is a gate-configuration signature rather than a market one. And the positive set has essentially no memory: of the rows that were positive on 22 September evening, none were positive the next morning, and only 13% of the 24 September positives were positive in the previous book. A book that changes this much cannot be the basis of a prospective record (F7) until the cause is known. The median EV, by contrast, is stable at −18% to −24% across every populated run, which says the negative expectancy is structural, not a one-day artefact.

### Finding 4 — The whole positive set is a function of the unvalidated vol forecast

| Vol-budget multiplier (sensitivity, not validated) | Grid EV > 0 rows (of 401) | Median grid EV | Median REACHABLE payoff | Median ALG-07-shape utility |
|---|---|---|---|---|
| 0.70 | 13 | −23.3% | +27.7% | −19.0% |
| 0.85 | 18 | −20.8% | +41.0% | −13.6% |
| 1.00 | 31 | −17.7% | +56.2% | −8.6% |
| 1.15 | 53 | −14.9% | +72.4% | −4.0% |

Impact: a 15% error in the forecast moves the number of positive rows by roughly a factor of two in either direction, and the 24 September book has forecast volatility above the contract IV on 46% of actionable rows. Until ALG-10 (fix item F4.3) reports the realised-to-forecast ratio out of sample, no positive row is evidence of cheap convexity, and the governed `bias_multiplier_approved = false` is the correct state. The probability of a positive net exit (30%) does not move with the multiplier because it is dominated by friction and theta, which the multiplier does not touch.

### Finding 5 — What the book already carries for models 3 and 6, before any database test

- **Model 3 (state):** `hidden_state_label` is populated on every row from six rule-based labels; none of the 401 actionable rows shows the default-50 signature on compression or force, so the Invariant B defect in `physics_state_engine._num` is latent on this book, not active. Macro regime is a single constant (`TRANSITIONAL_BULLISH`) on all 1,532 rows, so it carries no cross-sectional information for anything.
- **Model 6 (dealer positioning):** `gamma_flip` is present on 347 of 401 actionable rows; `gamma_flip_state` is blank on 193 rows of the book instead of `GEX_UNAVAILABLE`. The observation exists, its availability state does not.

---

## 2. Net impact statement

If the merged valuation replaced the current verdict ordering tomorrow, and nothing else changed:

1. The actionable list would shrink from 401 rows to roughly 30, and about a third of those would come from rows the Lab currently marks BLOCKED or MANUAL_REVIEW.
2. That list would be different the next day, with near-zero overlap.
3. The list would double or halve with a 15% change in the vol forecast that has not been validated.
4. More than half the book could not be placed on the list at all, because its geometry, contract or quote is missing or out of domain.

None of that is a reason to switch. It is the reason the fix review sequenced the work as it did: geometry and quote provenance (F5, F2.4) so the book is complete, ALG-10 (F4.3) so the vol budget is trusted, then outcome labels and calibration (F1) so a probability replaces the coin-flip, and only then a rank test against the desk gate. The harness gives each of those steps a before-and-after number on the same book.

## 3. Pending: database-backed tests for models 3 and 6

These open `historical_prices.sqlite` and the chain-snapshot store read-only and will run only after the evening orchestrator exits (a background wait is armed). Planned:

- Model 3: refit-free check of `hidden_state_label` stability, per ticker, across the last 20 sessions of stored bars, and how often the label changes without a change in the underlying inputs.
- Model 6: for the 347 actionable rows with a gamma flip, whether the flip level lies inside the vol-budget reachable range and whether `gamma_island_on_path` agrees with the recomputed profile.

Outputs will be added under `Enhancements/research/output/20260924_085940/`.

## 3a. Correction to Finding 3 and the evening book of 25 September (added after the evening run exited)

**Correction.** The runs with zero GO rows (10, 13, 17, 19 September) are all `pipeline_mode = EOD`; GO and GO_LIMIT verdicts exist only after morning validation. The "0 to 515 swing" is therefore evening books beside morning books, not a gate-configuration signature. Among morning-mode runs the actionable count ranges 206 to 515 (18 Sep 515, 20 Sep 206, 22 Sep 249 and 359, 24 Sep 401). The positive-set overlap figures (0%, 0%, 13%) were measured between morning-mode books and stand.

**Tonight's evening book (`20260925_061649`).** 1,549 rows, 1,368 MANUAL_REVIEW, 175 BLOCKED, 0 actionable by design; manifest DEGRADED with 175 missing `invalidation_spot`. Valued read-only with the harness: 846 rows in domain (418 missing geometry or contract, 285 outside the friction domain). Median grid EV −28% on end-of-day quotes with a median spread of 16.7%, so evening quotes are not comparable with morning ones.

| Rule applied to the whole evening book | Rows |
|---|---|
| Spread ≤ 15% and reachable ≥ 2 × |FLAT| | 83 (42 PUT, 41 CALL) |
| … and break-even p\* ≤ 0.40 | **26** (18 CALL, 8 PUT) |

All 26 are MANUAL_REVIEW with `REQUOTE_REQUIRED`; 10 carry an EIL verdict of BLOCKED, 15 EXECUTE or EXECUTE_WITH_CAUTION. This is the list the morning validation would be confirming under the proposed rules, and the evening-to-morning requote is the right place to test it.

## 4. Files

- Full-book run: `Enhancements/research/output/20260924_085940/merged_5_7_8_hold-horizon_bias-1.0_*.csv` (latest)
- Bias sweep: `merged_5_7_8_hold-horizon_bias-{0.7,0.85,1.15}_*.csv` and their `_summary.json`
- Cross-run table: computed in-session from the twelve books listed above; re-runnable with the harness `--run-id` per book
