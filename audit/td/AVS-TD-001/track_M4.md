# Track M4 — cheapest convexity (discovery §4.5, RESEARCH_ONLY)
No NORMAL_COMPLETED_SESSION run exists; every result below is on TEST-condition runs and cannot be CLOSED.

**Data source.** Contract family: `db_copies/phantom_history.db` `options_greeks_history` (read-only copy). Outcomes: `probes/p32_labels.csv` (retrospective triple-barrier labels, MFE and terminal return from daily OHLC in `historical_prices.sqlite`; vol-budget target; presented-not-taken; no fills). Selected contract: `intelligence_lab/final_opportunity_book_<run>.csv` (usecols `ticker, governed_direction/direction, contract_symbol, contract_delta, contract_dte`), used for geometry only (Rule 10). Stored DOI families in `control_plane.sqlite` copy, structure only.
**Runs whose books were read:** 20260804_114554, 20260831_010309, 20260901_082437, 20260902_232526 (the only runs whose decision sessions have a chain snapshot; see below).
**Dependency.** C7 is unmet at launch. Per comprehension item 10, the stored `convexity_score` is a 0–8 condition count, 2.0 on the stored run. Everything here is derived independently from historical chains.
**Probes.** `probes/p24_M4_convexity_surface.py` (91 s) → `p24_M4_family_surface.csv`, `p24_M4_selected_vs_peak.csv`, `p24_M4_candidate_counts.csv`, `p24_M4_family_contracts.csv`, `p24_M4_breakeven_outcomes.csv`, `p24_M4_breakeven_bins.csv`, `p24_M4_summary.json`, `p24_M4_stdout.txt`. `probes/p24_M4_supplement.py` → `p24_M4_surface_within_thesis.csv`, `p24_M4_h2h_delta.csv`, `p24_M4_h2h_tenor.csv`, `p24_M4_selected_geometry_by_run.csv`, `p24_M4_selected_in_family_summary.csv`, `p24_M4_breakeven_summary.csv`, `p24_M4_doi_family_candidate_counts.csv`, `p24_M4_supplement_stdout.txt`. Also `p24_M4_snapshot_dates.csv`.

**Method (stated assumptions).**
- **Theses.** `p32_labels.csv` is deduplicated to unique (ticker, direction, decision_session), keeping the first run: 8,417 theses, all with decision_session ≤ 2026-09-04.
- **Chain match.** A thesis matches if its ticker has a snapshot on the decision session, or on the nearest prior snapshot within 2 XNYS sessions.
  - The chain holds only 5 snapshot dates in the book era: 07-10, 07-17, 07-31, 08-28 and 09-04 (1,294–1,636 tickers each).
  - Only 4 decision sessions therefore match: 08-03 (snapshot 07-31, lag 1), 08-28 (lag 0), 08-31 (lag 1) and 09-01 (lag 2).
  - That gives **929 matched theses (11.0% of 8,417)**: CALL h10 497, CALL h5 216, PUT h5 127, PUT h10 83, CALL h20 5, PUT h20 1.
- **Sample.** Candidate counts use all 929. The surface uses a stratified proportional sample of **601** (`random.seed(20260912)`, direction × hold strata), capped near 600 to bound runtime. 574 of the 601 have ≥ 1 family contract.
- **Hold.** h is the p32 bucket upper bound (5 / 10 / 20).
- **Session→calendar.** time_stop = advance_sessions(decision_session, h) on the XNYS calendar (`canonical_data/session_clock.is_xnys_session`, cross-checked against a local holiday list with 0 mismatches for Jun–Dec 2026). cal_h = time_stop − snapshot_date in calendar days.
- **Family.** Side matches direction; bid > 0 and ask > bid; |delta| 0.10–0.85; chain `dte` (calendar days from snapshot) in [cal_h+5, cal_h+45]. All 19,767 family rows have quality_status OK.
- **Valuation.**
  - T_rem = (expiration_date − time_stop)/365. Premium = ask. S = chain `underlying_price`.
  - Pricing is BSM with **r = 0.039** (book-era 3m T-bill, `macro_snapshot.json` `extras.rates.t3m` 3.86–3.92% on runs 20260809…20260906) and q = 0. IV is held flat at the contract's stored IV.
  - The Annex A reachable-scenario theoretical value is reproduced at 4.036.
- **Target.** Reachable target = thesis spot × (1 ± 1.5·σ_h), with σ_h = σ_a·√(h/252) and σ_a from p32.
- **Per-contract metrics.**
  - payoff_per_dollar = V(reachable target, T_rem)/ask. This is gross, so 1.0 means the premium is recovered.
  - A net variant applies the `friction_model_v1` exit haircut: net_return_reach_friction.
  - convexity_per_dollar = gamma·S²/(2·ask); vega_per_dollar = vega/ask (vega per vol point); theta_per_dollar_day = theta/ask (theta per day); leverage_efficiency = |delta|·S/ask. Greeks are the stored chain greeks.
  - breakeven_move is the underlying level at time_stop where V = ask + (ask−bid)/2, solved by bisection. It is expressed as a favourable fraction of thesis spot, divided by σ_h.
- **Bands.** |delta| bands: D010_025, D025_040, D040_060, D060_085. DTE bands, as offset from cal_h: H+05_15, H+15_30, H+30_45.
- **OTHER.** p32 holds CALL/PUT only, so OTHER is "no directed side, not measured" in every row.

## Findings table
| Finding ID | CALL | PUT | OTHER | data source | evidence (artefact, field, value) | N | magnitude |
|---|---|---|---|---|---|---|---|
| DISC-F-M4-1 candidate count vs delta band | median 2 → 3 → 5 → 6; zero 136 → 54 → 38 → 31 | median 3 → 5 → 8 → 10; zero 33 → 20 → 10 → 8 | not measured (no side) | phantom chain | `p24_M4_candidate_counts.csv` W040_060…W010_085 | CALL 718 · PUT 211 theses | expressible share (≥ 1 candidate), all theses: 81.8% → 92.0% → 94.8% → 95.8% |
| DISC-F-M4-2 where payoff_per_dollar peaks (within thesis) | argmax |delta| median 0.36 (h5), 0.34 (h10); D060_085 beats D040_060 in 13.8% (h5) and 9.9% (h10) of theses; D025_040 beats D040_060 in 65.6% (h10) | argmax |delta| median 0.18 (h5, INSUFFICIENT_POWER n=81); D010_025 beats D040_060 in 91.0% (h5, INSUFFICIENT_POWER n=67) | not measured | phantom chain + BSM | `p24_M4_h2h_delta.csv`, `p24_M4_supplement_stdout.txt` argmax marginals | CALL h5 137 / h10 303; PUT h5 81 / h10 49 | D025_040 over D040_060 payoff ratio median 1.062 (CALL h10, n=212); D060_085 over D040_060 0.892 (h5, n=109) / 0.861 (h10, n=213) |
| DISC-F-M4-3 tenor axis | H+05_15 beats H+30_45 in 81.4% of CALL h5 theses (ratio 1.248) | 98.7% (PUT h5, INSUFFICIENT_POWER n=75) | not measured | phantom chain | `p24_M4_h2h_tenor.csv` | CALL h5 118 | CALL h10 tenor comparisons all INSUFFICIENT_POWER (n 66–71) |
| DISC-F-M4-4 selected contract vs thesis best | in-family n=146: selected/best payoff median 0.879; band vs thesis best: higher |delta| 92, same 48, lower 6; ≥ 90% of best 62 (42.5%) | in-family n=86 (INSUFFICIENT_POWER): 0.666; higher 68, same 15, lower 3; ≥ 90% 19 (22.1%) | not measured | books (geometry) + chain | `p24_M4_selected_vs_peak.csv`, `p24_M4_selected_in_family_summary.csv` | CALL 146 · PUT 86 | CALL h5 (n=107): in own best cell 36 (33.6%), in bucket raw-peak cell 1; offset is toward higher |delta| (median +1 band CALL, +2 PUT h5) |
| DISC-F-M4-5 selected geometry on 20260804_114554 | CALL h10: 105 of 285 selected symbols on the opposite side; book `contract_delta` = 0 on 259/321; DTE offset < 5 on 212 (median offset 4 calendar days); 5 expire ≤ time stop | PUT h10: 11 of 50 opposite side; delta 0 on 43/54; offset < 5 on 26 | not measured | books (geometry) + chain | `p24_M4_selected_geometry_by_run.csv` | 321 CALL + 54 PUT rows (h10) | runs 20260831/0901/0902: 0 side mismatch, 0 zero deltas (226 rows) |
| DISC-F-M4-6 breakeven/σ_h distribution | family-median per thesis p10/p50/p90 0.239/0.751/1.724; cheapest contract median 0.444; selected median 0.517 (n=146) | 0.174/0.620/1.401; cheapest 0.305; selected 0.331 (INSUFFICIENT_POWER n=85) | not measured | chain + BSM + p32 σ_a | `p24_M4_breakeven_summary.csv` | CALL 440 · PUT 130 | — |
| DISC-F-M4-7 breakeven vs realised outcome | side_correct 62.3% (low-breakeven half, n=220) vs 47.7% (high half, n=220); TARGET_FIRST 15.9% vs 10.5%; Mann–Whitney p = 0.00019 (BH over 6 tests: 0.0011); Spearman breakeven vs MFE/σ_h −0.112 (p = 0.018); MFE ≥ family-median breakeven 44.8%; terminal ≥ it 24.8% | 46.2% vs 47.7% (halves n=65, INSUFFICIENT_POWER); p = 0.99; MFE ≥ median breakeven 38.5%; terminal 15.4% | not measured | p32 OHLC outcomes + chain | `p24_M4_breakeven_summary.csv`, `p24_M4_breakeven_bins.csv` | CALL 440 · PUT 130 | CALL side-correct but MFE < median breakeven: 75 (17.0%); PUT 27 (20.8%) |
| DISC-F-M4-8 structural vs reachable payoff | struct/reach payoff_per_dollar median 0.563 | 0.857 (INSUFFICIENT_POWER n=81) | not measured | chain + BSM + book targets | `p24_M4_summary.json` premise | 235 theses (8,456 contracts) | argmax cell differs on 46.4% of theses |

Each finding does NOT establish:
- **1:** the population behind the "median one, 305 none" claim. The denominator here is 929 chain-matched theses from 4 decision sessions, not a run book.
- **2 and 3:** expected value. payoff_per_dollar is conditional on the underlying reaching the 1.5σ_h target at the time stop with IV flat; it carries no probability of reaching it.
- **4:** that the thesis-best contract would have monetised. It is a model ranking on one scenario.
- **5:** the pipeline's intended hold for that run. h = 10 is the p32 bucket bound; the legacy `6_10d` DTE window is 21–35 days.
- **6:** calibration of σ_a. breakeven/σ_h falls as σ_a rises relative to option IV.
- **7:** causality. Low breakeven/σ_h co-varies with high σ_a/IV, so the relationship may be a vol-regime effect, not a contract effect. The data is TEST-era and presented-not-taken.
- **8:** which target is right. It measures only divergence.
- **All findings:** RESEARCH_ONLY; nothing authorises a trade.

TRACE lines:
- DISC-F-M4-1: `TRACE: REQ-NONE | ALG-UNMAPPED | WP-2 | STAGE-NONE | TRACK-M4 | EVIDENCE-p24_M4_candidate_counts.csv | N=929`
- DISC-F-M4-2/3: `TRACE: REQ-NONE | ALG-04 | WP-2 | STAGE-NONE | TRACK-M4 | EVIDENCE-p24_M4_h2h_delta.csv,p24_M4_h2h_tenor.csv | N=574`
- DISC-F-M4-4: `TRACE: REQ-NONE | ALG-04 | WP-2 | STAGE-NONE | TRACK-M4 | EVIDENCE-p24_M4_selected_vs_peak.csv | N=232`
- DISC-F-M4-5: `TRACE: REQ-UNMAPPED | ALG-03 | WP-2 | STAGE-NONE | TRACK-M4 | EVIDENCE-p24_M4_selected_geometry_by_run.csv | N=601`
- DISC-F-M4-6/7: `TRACE: REQ-NONE | ALG-02,ALG-04,ALG-08 | WP-2 | STAGE-NONE | TRACK-M4 | EVIDENCE-p24_M4_breakeven_summary.csv | N=570`
- DISC-F-M4-8: `TRACE: REQ-NONE | ALG-02,ALG-04 | WP-2 | STAGE-NONE | TRACK-M4 | EVIDENCE-p24_M4_summary.json | N=235`

## Surface tables (payoff_per_dollar, median across contracts; n_theses in brackets; cells with n_theses < 100 are INSUFFICIENT_POWER)
Raw medians mix tickers. The within-thesis table (each cell's best contract divided by that thesis's best contract, median) is the cleaner read.

**CALL h5** (raw)
| |H+05_15|H+15_30|H+30_45|
|---|---|---|---|
|D010_025|2.829 (90)|2.071 (46)|1.896 (92)|
|D025_040|2.804 (90)|2.255 (47)|1.887 (93)|
|D040_060|2.458 (109)|2.152 (48)|1.764 (114)|
|D060_085|1.908 (121)|1.743 (48)|1.546 (105)|
Within-thesis: D010_025 0.963/0.771/0.711; D025_040 0.982/0.798/0.696; D040_060 0.868/0.720/0.705; D060_085 0.764/0.623/0.656.
Peaks: raw peak D010_025/H+05_15 (INSUFFICIENT_POWER); best powered cell D040_060/H+05_15. Per-thesis argmax: dband {D025_040 41, D010_025 39, D040_060 32, D060_085 25}; tband H+05_15 120/137.

**CALL h10** (raw)
| |H+05_15|H+15_30|H+30_45|
|---|---|---|---|
|D010_025|2.998 (60)|2.985 (46)|2.257 (195)|
|D025_040|3.511 (62)|3.070 (57)|2.334 (246)|
|D040_060|2.990 (68)|2.823 (59)|2.119 (251)|
|D060_085|2.289 (61)|2.345 (52)|1.826 (257)|
Within-thesis: D010_025 0.987/0.783/0.895; D025_040 0.914/0.802/0.959; D040_060 0.866/0.737/0.920; D060_085 0.714/0.608/0.782.
Peaks: raw peak D025_040/H+05_15 (INSUFFICIENT_POWER); best powered cell D025_040/H+30_45 (0.959, n=246). Per-thesis argmax: dband {D025_040 111, D040_060 81, D010_025 78, D060_085 33}; tband H+30_45 251/303. The tenor axis here is confounded: the stored chain stops at DTE 49 and many tickers list only a monthly expiry, so H+30_45 (offset 30–32) is the only tenor most theses have.

**PUT h5** (raw; every cell INSUFFICIENT_POWER, n 45–72)
| |H+05_15|H+15_30|H+30_45|
|---|---|---|---|
|D010_025|4.280 (62)|2.863 (47)|2.527 (66)|
|D025_040|3.613 (66)|2.665 (47)|2.328 (70)|
|D040_060|2.877 (69)|2.269 (47)|1.984 (71)|
|D060_085|2.126 (72)|1.799 (45)|1.554 (66)|
Within-thesis: D010_025 1.000/0.700/0.551; D025_040 0.835/0.560/0.481; D040_060 0.661/0.456/0.427; D060_085 0.497/0.372/0.360.

**PUT h10** (raw; every cell INSUFFICIENT_POWER, n 8–41)
| |H+05_15|H+15_30|H+30_45|
|---|---|---|---|
|D010_025|1.870 (13)|1.694 (12)|1.910 (39)|
|D025_040|2.068 (14)|1.907 (12)|1.982 (37)|
|D040_060|2.014 (14)|1.915 (12)|1.736 (41)|
|D060_085|1.578 (12)|1.544 (8)|1.455 (41)|

h20 (CALL 3, PUT 1 theses): INSUFFICIENT_POWER, not tabled (`p24_M4_family_surface.csv`).

The other metrics per cell (convexity_per_dollar, vega_per_dollar, theta_per_dollar_day, leverage_efficiency, net_return_reach_friction, breakeven) are in `p24_M4_family_surface.csv`. Example, CALL h5: convexity_per_dollar runs from 94.3 (D010_025/H+05_15) to 7.6 (D060_085/H+30_45); theta_per_dollar_day from −0.061 to −0.005; leverage_efficiency from 14.1 to 5.7. With friction the reachable net return stays positive in every cell of every table (CALL h5 lowest 0.441).

## Candidate-count table (full matched set; family filters except the delta band)
| delta band | ALL median / zero (n=929) | CALL median / zero (n=718) | PUT median / zero (n=211) | CALL h10 median / zero (n=497) | CALL h5 (n=216) | PUT h5 (n=127) | PUT h10 (n=83) | per-ticker max, median / zero (785 tickers) |
|---|---|---|---|---|---|---|---|---|
| 0.40–0.60 | 2 / 169 (18.2%) | 2 / 136 | 3 / 33 | 1 / 104 | 3 / 31 | 7 / 14 | 1 / 19 | 2 / 146 |
| 0.30–0.70 | 3 / 74 (8.0%) | 3 / 54 | 5 / 20 | 3 / 43 | 6 / 10 | 16 / 8 | 2 / 12 | 3 / 61 |
| 0.20–0.80 | 5 / 48 (5.2%) | 5 / 38 | 8 / 10 | 4 / 28 | 8 / 10 | 26 / 3 | 4 / 7 | 5 / 39 |
| 0.10–0.85 | 7 / 39 (4.2%) | 6 / 31 | 10 / 8 | 5 / 26 | 10 / 5 | 37 / 2 | 5 / 6 | 6 / 31 |

Median two-sided contracts in the DTE window at any delta: 10. Median chain max DTE: 49.

**Claim test.** "0.40–0.60 leaves the median ticker one candidate, 305 with none."
- On this historical family the per-thesis median is 2 (CALL h10 alone: 1), with 169 of 929 theses at zero; the per-ticker figure is 146 of 785 at zero.
- The count 305 cannot be reproduced because its population is not stated anywhere I found; only the two prompt files contain it.
- The stored DOI families (`doi_contract_families`, policy `doi-thesis-conditioned-family-v1`, no delta band) carry a median of 59 candidates and **0** zero-candidate families on both runs that have them: 20260910_150045 (1,241 families) and 20260911_115904 (1,218).
- The legacy selector's band is `1_5d` 0.40–0.60 / DTE 7–21, `6_10d` 0.35–0.55 / DTE 21–35, `11_20d` 0.30–0.50 / DTE 35–60 (`scripts/avshunter_options_intelligence.py:1216-1218`), with a 0.15–0.35 fallback when no dte_config is passed (`:4558-4559`, `:5223-5224`).

## Selected contract located on the surface (sample 601)
| direction h | n | IN_FAMILY | in chain, outside family | not in chain snapshot | no selected symbol | in bucket raw-peak cell | in own best cell | selected/best payoff median | higher / same / lower |delta| band than best |
|---|---|---|---|---|---|---|---|---|---|
| CALL h5 | 140 | 107 | 16 | 16 | 1 | 1 | 36 | 0.893 | 62 / 40 / 5 |
| CALL h10 | 321 | 39 | 245 | 1 | 36 | 7 | 7 | 0.849 | 30 / 8 / 1 (INSUFFICIENT_POWER) |
| PUT h5 | 82 | 71 | 8 | 3 | 0 | 3 | 11 | 0.636 | 59 / 11 / 1 (INSUFFICIENT_POWER) |
| PUT h10 | 54 | 14 | 36 | 0 | 4 | 0 | 2 | 0.855 | 9 / 3 / 2 (INSUFFICIENT_POWER) |
| h20 | 4 | 1 | 2 | 0 | 1 | 1 | 1 | — | INSUFFICIENT_POWER |

Band location of every located selected contract, including those outside the family:
- CALL h5: D040_060 89 of 139, DTE band H+05_15 137.
- PUT h5: D040_060 57 of 82.
- CALL h10: D040_060 128, D025_040 110; DTE band OUT_LOW (offset < 5) 212 of 285.

Reasons a chain-present selection falls outside the family (n=307):
- dte_window alone: 148
- side + dte_window: 75
- side alone: 32
- one-sided quote, alone or combined: 47
- delta, alone or combined: 19

Offset direction from the thesis best: higher |delta|, and for h5 the same DTE band. For h10 the selection is shorter-dated than the family window.

## Breakeven table (breakeven_move / σ_h; outcomes from historical OHLC, `p32_labels.csv`)
| slice | n | family-median breakeven p10 / p50 / p90 | cheapest-contract breakeven p50 | selected breakeven p50 (n) | MFE/σ_h p50 | MFE ≥ cheapest breakeven | MFE ≥ family-median breakeven | terminal ≥ family-median breakeven | side_correct | TARGET_FIRST (label_V) | side_correct low / high breakeven half (n) | TARGET_FIRST low / high half | Mann–Whitney p (breakeven by side_correct) | power |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| CALL | 440 | 0.239 / 0.751 / 1.724 | 0.444 | 0.517 (146) | 0.621 | 61.6% | 44.8% | 24.8% | 55.0% | 13.2% | 62.3% / 47.7% (220/220) | 15.9% / 10.5% | 0.00019 | n≥100 |
| CALL h5 | 137 | 0.367 / 0.896 / 2.530 | 0.472 | 0.664 (107) | 0.502 | 45.3% | 30.7% | 15.3% | 44.5% | 7.3% | 51.5% / 37.7% (68/69, halves INSUFFICIENT_POWER) | 10.3% / 4.3% | 0.036 | n≥100 |
| CALL h10 | 303 | 0.194 / 0.706 / 1.486 | 0.423 | 0.303 (39) | 0.679 | 69.0% | 51.2% | 29.0% | 59.7% | 15.8% | 65.6% / 53.9% (151/152) | 17.2% / 14.5% | 0.013 | n≥100 |
| PUT | 130 | 0.174 / 0.620 / 1.401 | 0.305 | 0.331 (85) | 0.359 | 60.8% | 38.5% | 15.4% | 46.9% | 5.4% | 46.2% / 47.7% (65/65, halves INSUFFICIENT_POWER) | 3.1% / 7.7% | 0.99 | n≥100 |
| PUT h5 | 81 | 0.115 / 0.527 / 1.396 | 0.225 | 0.319 (71) | 0.354 | 69.1% | 45.7% | 19.8% | 48.1% | 3.7% | 40.0% / 56.1% | 2.5% / 4.9% | 0.50 | INSUFFICIENT_POWER |
| PUT h10 | 49 | 0.357 / 0.890 / 1.477 | 0.494 | 0.678 (14) | 0.363 | 46.9% | 26.5% | 8.2% | 44.9% | 8.2% | 54.2% / 36.0% | 12.5% / 4.0% | 0.51 | INSUFFICIENT_POWER |
| OTHER | 0 | not measured | | | | | | | | | | | | |

- MFE ≥ selected-contract breakeven: CALL 45.9% (n=146), PUT 60.0% (n=85, INSUFFICIENT_POWER).
- Median family breakeven for side-correct vs side-wrong theses: CALL 0.647 vs 0.861; PUT 0.653 vs 0.610.
- Spearman of family-median breakeven against MFE/σ_h: CALL −0.112 (p = 0.018); PUT −0.026 (p = 0.77).
- Fixed breakeven bins (`p24_M4_breakeven_bins.csv`): every bin is INSUFFICIENT_POWER except CALL h10 0.5–1.0 (n=115: side_correct 63.5%, TARGET_FIRST 16.5%, MFE ≥ breakeven 45.2%).
- **Trial count.** 54 surface cells, 16 delta and 12 tenor head-to-heads, 23 breakeven bins, 6 halves tests, 2 Spearman: 113 splits examined in this track.
- **BH adjustment** over the 6 Mann–Whitney tests: CALL pooled 0.0011, CALL h10 0.039, CALL h5 0.072. At full 113-split Bonferroni only CALL pooled remains below 0.05 (0.021). The implied haircut is about 113×: treat it as one surviving association, not an effect size.
- The MFE comparison is not a monetisation test. MFE is the intraperiod favourable excursion on daily highs/lows, while breakeven is valued at the time stop; an earlier exit carries more time value but no observed bid.

## Per-check notes
1. **Chain match.** `p24_M4_stdout.txt` "match by decision_session". Re-check: distinct `snapshot_date` per p32 ticker between 2026-07-01 and 2026-09-04 (`p24_M4_snapshot_dates.csv`).
2. **Candidate counts.** `p24_M4_candidate_counts.csv`: one row per matched thesis with counts per band.
3. **Surface.** `p24_M4_family_surface.csv` (raw medians, per-thesis argmax counts); `p24_M4_surface_within_thesis.csv` (normalised); `p24_M4_h2h_delta.csv` and `p24_M4_h2h_tenor.csv` (within-thesis pairwise).
4. **Selected vs peak.** `p24_M4_selected_vs_peak.csv`: symbol parsed from the OCC tail; DTE from symbol expiry − snapshot; located in the family, else in the chain with a reason, else by book delta; band steps versus the bucket raw-peak cell and versus the thesis-best cell. Summaries in `p24_M4_selected_in_family_summary.csv` and `p24_M4_selected_geometry_by_run.csv`.
5. **Breakeven.** `p24_M4_breakeven_outcomes.csv` holds per-thesis values; `p24_M4_breakeven_summary.csv` holds the table above.

## Deviations (observations, no severity)
- **Chain history sparsity.** `options_greeks_history` holds 5 snapshot dates between 2026-07-01 and 2026-09-04: 07-10, 07-17, 07-31, 08-28, 09-04. Of 13 p32 decision sessions only 4 have a snapshot on or ≤ 2 sessions before them, so 929 of 8,417 theses (11.0%) are measurable.
- **Chain DTE cap.** The stored chain has max DTE 49 (median chain max 49 across matched theses). For h10 (cal_h 17 from the 07-31 snapshot) the hold+45 upper bound of 62 days is truncated to 49, so H+30_45 means offset 30–32 only.
- **Chain rate.** `risk_free_rate` = 0.045 constant on sampled rows (AAPL 2026-08-28, 571 rows), so stored greeks and IV use 4.5%. The book-era t3m is 3.86–3.92%; this track values with 0.039 using the stored IV and greeks.
- **20260804_114554 book, selected-contract geometry** (`p24_M4_selected_geometry_by_run.csv`):
  - The selected symbol is on the opposite side to the thesis direction on 121 of 373 rows with a symbol (CALL h10 105/285, CALL h5 4/28, CALL h20 1/2, PUT h10 11/50).
  - `contract_delta` = 0.0 on 308 of 415 rows.
  - The symbol expiry falls < 5 calendar days after the h = 10 time stop on 241 rows; on 8 rows it falls at or before the time stop.
  - The later books (20260831_010309, 20260901_082437, 20260902_232526; 226 sampled rows) show 0 side mismatches and 0 zero deltas.
- **Two candidate-count regimes coexist.** The legacy selector bands (0.40–0.60 / 0.35–0.55 / 0.30–0.50 by hold label, `scripts/avshunter_options_intelligence.py:1216-1218`, fallback 0.15–0.35 at `:4558-4559` and `:5223-5224`) sit alongside DOI families with no delta band (median 59 candidates, 0 empty on 2,459 stored families, `control_plane.sqlite` `doi_contract_families`). The "305 having none" figure appears only in `dropbox/macro/coaching/desk_gate/AVS-TD-001_claude_code_prompt.md:281` and `AVS-DISC-002_claude_code_prompt.md:232`; its source artefact was not located.
- **Field-name mapping.** The Annex field `payoff_reachable_net_return_fraction` has no counterpart in the historical chain. This track's payoff_per_dollar is a gross ratio, with `net_return_reach_friction` (the friction_model_v1 exit haircut) reported beside it.

## Premise notes (spec / measured / gap; no severity, no recommendation)
- **Structural vs reachable monetisability.**
  - *Spec:* Engine A (`contracts/selected_contract_economics.py`, read by Morning Gate/EOD) prices the selected contract at the structural target.
  - *Measured:* on 235 historical theses with a valid structural target, structural payoff_per_dollar is a median 0.68× the reachable-target payoff (CALL 0.563×, n=154; PUT 0.857×, INSUFFICIENT_POWER n=81). The payoff-maximising cell differs between the two targets on 46.4% of theses: the structural argmax leans to D060_085 (68 of 235), the reachable argmax to D010_025 (104 of 235). In σ_a-based units the structural distance is a median 0.74 σ_h for CALL (92.2% inside 1.5 σ_h) and 1.64 σ_h for PUT.
  - *Gap:* the ranking differs on 46.4% of theses and the payoff level by 32% at the median.
- **Selection band vs payoff geometry.**
  - *Spec:* the legacy `1_5d` delta window is 0.40–0.60, and the selected contracts sit there (CALL h5 89/139, PUT h5 57/82).
  - *Measured:* per-thesis reachable payoff_per_dollar ranks D025_040 above D040_060 in 65.6% of CALL h10 theses (n=212), and D060_085 below D040_060 in 86–90% of CALL theses (n=109, 213). The per-thesis argmax |delta| median is 0.34–0.36 for CALL.
  - *Gap:* in-family selected contracts deliver a median 0.879× the thesis-best payoff for CALL (n=146) and 0.666× for PUT (INSUFFICIENT_POWER n=86).
- **breakeven/σ_h as the single number.**
  - *Spec (§4.5):* breakeven/σ_h is the cleanest single number.
  - *Measured:* its association with side-correctness exists for CALL (62.3% vs 47.7%, n=440) and not for PUT (n=130). σ_h is built from σ_a (GARCH) while breakeven is driven by option IV, so the ratio mixes forecast-vs-implied vol with contract choice.
  - *Gap:* the size of that mixing is not separated on this sample.
- **convexity_score (C7 context).**
  - *Spec:* the stored `convexity_score` is a 0–8 condition count (comprehension item 10).
  - *Measured:* convexity_per_dollar varies 12× across CALL h5 cells (94.3 → 7.6) and falls monotonically with |delta| in every bucket, while reachable payoff_per_dollar does not (CALL h10 within-thesis peak at D025_040, and D010_025 beats D025_040 in only 40.9% of theses, n=176).
  - *Gap:* gamma-per-dollar and reachable payoff-per-dollar rank low-delta contracts differently. The stored count measures neither.

## Not tested / data unavailable
- **6–10 and 11–20 hold outside 08-03.** DATA_UNAVAILABLE: no chain snapshot within 2 sessions before the other 9 decision sessions (07-22, 07-30, 08-07, 08-13, 08-14, 08-17, 08-19, 08-20, 08-21). Needed: daily chain snapshots.
- **h20.** 6 theses. INSUFFICIENT_POWER throughout.
- **PUT surface and PUT selected-vs-peak.** Every cell is n < 100, so INSUFFICIENT_POWER; values are reported, not presented as results.
- **OTHER.** p32 contains no non-directional theses, so it is not measured.
- **"305 having none".** The population could not be identified, so the count is not reproducible.
- **IV stress.** Not run (IV held flat per brief).
- **Surface coverage.** The 328 matched theses outside the 601-thesis sample are not on the surface; they are in the candidate-count table.

## Expectation vs actual (expectations.md M4 row)
| item | E | A | gap |
|---|---|---|---|
| Median candidates, 0.40–0.60 → 0.10–0.85 | 1 → ≥ 5 | per-thesis 2 → 7 (CALL 2 → 6; PUT 3 → 10; CALL h10 1 → 5) | start one higher; end within E |
| Zero-candidate count | 305 → < 100 | 169 → 39 of 929 theses (18.2% → 4.2%); stored DOI families 0 empty | population differs, so 305 is not comparable; direction and ending level match E |
| payoff_per_dollar peak | |delta| 0.25–0.40, DTE hold+15 to hold+30 | CALL argmax |delta| median 0.34–0.36; PUT h5 0.18 (INSUFFICIENT_POWER). DTE: H+05_15 wins for CALL h5 (81.4% vs H+30_45, n=118); H+15_30 is the argmax for 1–2 theses per bucket | delta matches E for CALL; tenor contradicts E for h5 and is untestable for h10 (chain cap, expiry cadence) |
| Selected within the peak region | < 50% | own best cell: CALL h5 33.6% (n=107); ≥ 90% of best: CALL 42.5% (n=146), PUT 22.1% (INSUFFICIENT_POWER); bucket raw-peak cell: 1/107 | consistent with E |
| breakeven_move median | 0.8–1.2 σ_h | family-median 0.751 CALL / 0.620 PUT; cheapest 0.444 / 0.305; selected 0.517 / 0.331 | below E |

## State log lines
```
4.5-M4-chain-match,PARTIAL,929,10s,"5 snapshot dates in book era (07-10,07-17,07-31,08-28,09-04); 929 of 8417 p32 theses matched within 2 sessions (decision sessions 08-03,08-28,08-31,09-01)"
4.5-M4-candidate-counts,MEASURED,929,69s,"0.40-0.60 median 2 zero 169; 0.30-0.70 3/74; 0.20-0.80 5/48; 0.10-0.85 7/39; CALL 718 PUT 211; DOI stored families median 59 zero 0"
4.5-M4-surface,PARTIAL,601,91s,"stratified sample seed 20260912; 574 theses 12085 contracts; r=0.039 q=0 IV flat; CALL argmax |delta| med 0.34-0.36; PUT cells INSUFFICIENT_POWER; chain max DTE 49 truncates h10 window"
4.5-M4-selected-vs-peak,PARTIAL,601,5s,"in-family CALL 146 sel/best 0.879 higher-delta 92; PUT 86 0.666 INSUFFICIENT_POWER; 20260804 book side mismatch 121/373 delta0 308/415 expiry<time_stop+5 241"
4.5-M4-breakeven,MEASURED,570,5s,"family-median breakeven/sigma_h CALL p50 0.751 PUT 0.620; CALL side_correct low/high half 62.3/47.7 MW p=0.00019; PUT p=0.99 halves INSUFFICIENT_POWER; 113 splits"
4.5-M4-premise-struct-vs-reach,MEASURED,235,2s,"structural/reachable payoff_per_dollar median 0.68 (CALL 0.563 PUT 0.857); argmax cell differs 46.4%"
```
