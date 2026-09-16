# Track M5 — cost of waiting and value of confirmation (§4.6) — DISCOVERY, RESEARCH_ONLY
No NORMAL_COMPLETED_SESSION run exists; every result below is on TEST-condition runs and cannot be CLOSED.

Status: complete (all sections written).

**Data sources (historical, Rule 10).**
- Stored option chains: `data/canonical/market_observations/option_chain/<session>/<ticker>/*.json`, indexed through `db_copies/control_plane.sqlite` `dataset_registry` (`OPTION_CHAIN`). Sessions stored: 2026-08-28, 08-31, 09-02, 09-03, 09-04, 09-08, 09-10. **09-01 and 09-09 are absent.**
- `db_copies/phantom_history.db` `options_greeks_history`: weekly Friday snapshots. The only dates in the thesis window are 2026-07-17, 07-31, 08-28 and 09-04 (checked on 10 tickers).
- `db_copies/control_plane.sqlite` `option_contract_observations`, and the EXACT_OPTION_QUOTE JSON for session 2026-09-11.
- The 22 `final_opportunity_book_<run>.csv`, read via usecols for structure fields only (`probes/p25_M5_books_panel.csv`, 17,116 rows). This covers contract symbol, quote and greeks as stored, and states.
- `probes/p31_presented_candidates.csv` (hidden_state, verdict, decision_session; positionally aligned with the panel, checked).
- `probes/p32_labels.csv` (`label_V`; favourable = `TARGET_FIRST`), 9,893 rows.

Books were read for structure only. Every premium path is taken from stored quotes of the same OCC contract. Outcome rates are retrospective barrier labels on presented-not-taken rows, not fills.

**Runs used:** all 22 book runs (2026-07-23 → 2026-09-11). The early-lane population is 20260905_151448; the staleness population is 20260911_115904, with the 20260910_150045 observations.

**Dependency D4:** it ran in parallel, and `probes/p13_D_d4_lifecycle.*` exists, but `state_log.csv` had no D4 line when I read it. M5 does not use D4's result: `liquidity_state` per row and retention across runs are taken directly from the books. The dependency is noted as unmet at run time.

## 1. Findings table

| Finding ID | CALL | PUT | OTHER | data source | evidence | N | magnitude |
|---|---|---|---|---|---|---|---|
| DISC-F-M5-1 early-lane reproduction | median −1.99%, n 94 (`INSUFFICIENT_POWER`) | median −0.93%, n 54 (`INSUFFICIENT_POWER`) | 0 rows | 20260905 book + options_intelligence; stored chain 2026-08-31 | p25_M5_earlylane.py → p25_M5_earlylane_summary.csv | 148 matched of 232 | median −1.908% (W3.6 figure reproduced exactly); IQR 12.4 pp (p25 −8.9 / p75 +3.5); p10 −18.4 / p90 +21.4; in IV points: median −0.88, p10 −8.3, p90 +8.6 |
| DISC-F-M5-2 "three sessions" is four trading sessions | — | — | — | chain session list + NYSE calendar | dataset_registry OPTION_CHAIN sessions | 148 | 08-31 is 4 trading sessions before 09-04 (09-01 chain not stored). A true 3-session lookback (09-01) is DATA_UNAVAILABLE for that run |
| DISC-F-M5-3 early lane on the 10 Sep books | 3 back: +5.2% (n 388) / +3.9% (n 355) | 3 back: +2.1% (n 292) / +2.1% (n 294) | 0 rows | books 20260910_150045 / 20260911_115904 MONETISABLE; chain 2026-09-04 | p25_M5_earlylane_summary.csv | 680 / 649 | median +3.7% / +3.2%; IQR 13.6 / 12.8 pp; p10 −12.1 / −13.1, p90 +20.0 / +18.0; share ≥ +20%: 10.2% / 9.2%. 2 back (09-08): −1.9% / −2.2% |
| DISC-F-M5-4 staleness, direct | 255 stale rows, 0 re-quoted | 198 stale rows, 0 re-quoted | 0 | book 20260911 + option_contract_observations + EXACT_OPTION_QUOTE 2026-09-11 | p25_M5_staleness.py → p25_M5_staleness.csv | 453 | DATA_UNAVAILABLE: none of the 453 contracts has a stored quote after 2026-09-10T17Z. `morning_contract_mid` = `contract_mid` on 453/453; `contract_mid_change_pct` null on 453/453 |
| DISC-F-M5-5 staleness, proxy cohort (PARTIAL) | abs Δmid median 12.1% (p10 1.8 / p90 46.9), n 316 | abs Δmid median 10.5% (p10 1.8 / p90 35.5), n 139 | 0 | same-book non-stale contracts, quoted 10 Sep ~17Z and again 11 Sep ~17Z | p25_M5_staleness_proxy.csv | 455 | over a median 23.6 h: abs Δmid median 11.8% (IQR 5.0–25.0; p10 1.7 / p90 43.3); signed median +1.0%; 11 Sep ask vs 10 Sep mid: median +30.2%; ΔIV median −1.25 pts; share with abs Δmid > 10 Sep half-spread: 25.3% |
| DISC-F-M5-6 thesis identity unstable | — | — | — | panel thesis_id | p25_M5_repeats.py stdout | 3,639 rows with thesis_id | 2,887 distinct ids; 752 seen in more than one session; 87% of ids embed their own session date. Repeats use the ticker+direction cohort, marked PARTIAL |
| DISC-F-M5-7 repeat pairs and repricing coverage | pairs d1/2/3/5: 3,840 / 2,722 / 1,575 / 2,032 | 887 / 465 / 311 / 260 | excluded (no direction) | panel + chains + phantom | p25_M5_repeats.csv | 12,092 pairs; 2,560 repriced | same-contract repricing from stored chains at both ends: 780 pairs. Book-to-book repricing before 20260831: zero Δpremium on 44.0% of 645 pairs (stored contract fields repeated) |

## 2. Early-lane table (IV of the same OCC contract at selection vs earlier stored session)

Percent change = (IV_sel − IV_then)/IV_then. Quantiles use pandas linear interpolation. W3.6 used index quantiles, reproduced as w36_p25 −8.728 / w36_p75 +3.738. "Back" counts trading sessions; the 2026-09-07 holiday is excluded.

| population (selection session) | lookback (session) | source | rows | matched n | median % | p10 | p25 | p75 | p90 | IQR pp | share ≥ +20% | median IV pts |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| W3.6 options_intelligence 20260905 (09-04) | "3 stored-chain back" = 08-31 (4 trading) | chain | 232 | 148 | **−1.908** | −18.40 | −8.89 | +3.49 | +21.43 | 12.38 | 12.16% | −0.88 |
| book 20260905 MONETISABLE (09-04) | 1 back 09-03 | chain | 232 | 210 | −1.12 | −15.62 | −6.50 | +2.79 | +12.65 | 9.29 | 5.7% | −0.51 |
| same | 2 back 09-02 | chain | 232 | 179 | −2.00 | −16.49 | −8.34 | +3.33 | +13.66 | 11.67 | 7.3% | −0.81 |
| same | 3 back 09-01 | — | 232 | 0 | DATA_UNAVAILABLE (no chain stored) | | | | | | | |
| same | 5 back 08-28 | chain | 232 | 142 | −1.19 | −18.87 | −6.89 | +3.47 | +16.43 | 10.36 | 9.2% | −0.53 |
| same | 5 back 08-28 | phantom | 232 | 195 | +0.07 | −14.34 | −5.66 | +6.03 | +17.75 | 11.69 | 8.7% | +0.03 |
| book 20260910_150045 MONETISABLE (09-10) | 2 back 09-08 | chain | 809 | 693 | −1.90 | −13.94 | −7.39 | +3.71 | +13.78 | 11.10 | 6.2% | −0.75 |
| same | 3 back 09-04 | chain | 809 | 680 | +3.68 | −12.13 | −2.75 | +10.85 | +20.03 | 13.60 | 10.2% | +1.54 |
| same | 4 back 09-03 | chain | 809 | 651 | +3.11 | −14.55 | −3.37 | +10.21 | +20.36 | 13.58 | 10.3% | +1.27 |
| same | 5 back 09-02 | chain | 809 | 566 | +2.98 | −14.98 | −3.66 | +8.84 | +16.95 | 12.50 | 8.0% | +1.15 |
| book 20260911_115904 MONETISABLE (09-10) | 2 back 09-08 | chain | 757 | 661 | −2.22 | −15.31 | −7.99 | +3.63 | +15.10 | 11.63 | 6.8% | −1.02 |
| same | 3 back 09-04 | chain | 757 | 649 | +3.20 | −13.14 | −3.36 | +9.41 | +17.97 | 12.77 | 9.2% | +1.29 |
| same | 4 back 09-03 | chain | 757 | 617 | +2.80 | −15.00 | −4.38 | +10.10 | +18.69 | 14.48 | 8.9% | +1.08 |
| same | 5 back 09-02 | chain | 757 | 538 | +1.75 | −18.30 | −5.40 | +7.94 | +15.20 | 13.35 | 6.9% | +0.71 |

1-back for the 09-10 books is DATA_UNAVAILABLE because no 09-09 chain is stored. Per-direction splits are in `p25_M5_earlylane_summary.csv`. In the W3.6 population, CALL (n 94) and PUT (n 54) are each `INSUFFICIENT_POWER`. On the 09-10 books, CALL is +5.2%/+3.9% and PUT +2.1%/+2.1% at 3 back, all n ≥ 100. The W3.6 population and the 20260905 book MONETISABLE rows are the same 232 contracts (the per-row numbers are identical). The mean (+3,296%) is driven by one contract whose earlier IV sits at the 0.0001 floor (`iv_then_floor_n = 1`).

## 3. Staleness table (11 Sep primary run, 453 `QUOTE_STALE` rows)

| measure | ALL | CALL | PUT | OTHER |
|---|---|---|---|---|
| stale rows | 453 | 255 | 198 | 0 |
| stale quote_as_of | 2026-09-10T16Z (36), T17Z (417) | | | |
| book mid = 10 Sep observation mid, same symbol | 411 / 453 | | | |
| `morning_contract_mid` = `contract_mid` | 453 / 453 | | | |
| `contract_mid_change_pct` populated | 0 / 453 | | | |
| stale contracts with a stored quote after 10 Sep 17Z (observations: 540 fresh rows; exact quotes: 765 fresh) | **0** — DATA_UNAVAILABLE | 0 | 0 | 0 |
| **Proxy (PARTIAL):** non-stale contracts in the same book, 10 Sep quote → 11 Sep quote, n | 455 | 316 | 139 | 0 |
| window hours, median (p10/p90) | 23.6 (23.3/24.0) | 23.6 | 23.7 | |
| abs Δmid %, median (p25/p75; p10/p90) | 11.8 (5.0/25.0; 1.7/43.3) | 12.1 (4.9/25.8; 1.8/46.9) | 10.5 (5.8/22.7; 1.8/35.5) | |
| signed Δmid %, median (p10/p90) | +1.0 (−26.8/+33.1) | +2.6 (−27.1/+33.0) | −1.5 (−25.0/+33.1) | |
| 11 Sep ask vs 10 Sep mid %, median | +30.2 | +33.3 | +21.7 | |
| ΔIV pts, median (p10/p90) | −1.25 (−11.1/+5.8) | −1.35 | −1.03 | |
| share with abs Δmid > 10 Sep half-spread | 25.3% | 25.9% | 23.7% | |

The proxy cohort differs from the stale set. Its mix is LIQUIDITY_PENDING 296, EXECUTABLE_NOW 55, REVIEWABLE_SPREAD 41, others 63, and its 10 Sep mid median is 2.10 against 3.28 for the stale set. Cheaper contracts move more in percentage terms, so the proxy is not the stale contracts' own move.

## 4. Decomposition curves (repeat pairs, same ticker+direction at t and t+d; same OCC contract held from t) — PARTIAL (cohort, not thesis identity)

Definitions, all in percent of premium(t) (mid):
- delta_premium_total = mid(t+d) − mid(t).
- theta_component = BS(S_t, K, T_t − calendar days/365, IV_t) − BS(S_t, K, T_t, IV_t), with r = 0.045. It is within 4% of the linear theta×days, ratio median 0.96.
- IV_component = vega_t × ΔIV in points. Chain vega is per vol point; the median ratio to BS vega is 1.00 (n 1,877).
- move_component = delta_t × ΔS.
- The residual carries gamma and cross terms: absolute median 7.1% of premium across all repriced pairs.

**Clean subset (both ends priced from the stored chain, 769 pairs after the IV-floor exclusion).** This is the only subset where repricing is not partly the book's own stored contract fields. Source: `probes/p25_M5_repeats_chainonly.csv`.

| d | dir | n | t-sessions | total | theta | IV | move | residual | p10 / p90 total | IQR pp | power |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | CALL | 146 | 4 | 0.00 | −3.53 | +0.42 | +4.73 | +0.64 | −25.8 / +42.2 | 30.0 | OK |
| 1 | PUT | 86 | 3 | +1.10 | −2.81 | +1.34 | +1.75 | +1.34 | −33.4 / +31.9 | 33.6 | INSUFFICIENT_POWER |
| 2 | CALL | 65 | 4 | −15.32 | −6.25 | −0.52 | −7.16 | +2.92 | −53.4 / +45.9 | 44.0 | INSUFFICIENT_POWER |
| 2 | PUT | 56 | 3 | −0.18 | −4.74 | −0.23 | +4.22 | +2.94 | −46.0 / +45.1 | 37.4 | INSUFFICIENT_POWER |
| 3 | CALL | 160 | 4 | −33.90 | −18.77 | +7.98 | −28.20 | +3.32 | −73.6 / +17.0 | 40.2 | OK |
| 3 | PUT | 100 | 3 | +17.41 | −14.95 | +5.04 | +22.39 | +3.20 | −38.4 / +105.5 | 65.1 | OK |
| 5 | CALL | 93 | 3 | see csv | | | | | | | INSUFFICIENT_POWER |
| 5 | PUT | 63 | 2 | see csv | | | | | | | INSUFFICIENT_POWER |

These clean curves start from only 2–4 distinct sessions (08-28 … 09-08), so each cell is dominated by one or two market days. The d=3 CALL −33.9% and PUT +17.4% have opposite signs and are driven by the move component, which points to a common underlying move over those days rather than decay alone.

- **Per hidden_state (clean subset):** 48 cells, largest n 71. All are `INSUFFICIENT_POWER`.
- **Per confirmation state (clean subset):** 22 cells. Only d=3 MANUAL_REVIEW CALL reaches n ≥ 100 (n 149): total −35.0, theta −21.4, IV +8.3, move −30.5. All other cells are `INSUFFICIENT_POWER`, largest n 91.
- **Per liquidity_state (clean subset):** 52 cells, largest n 79. All are `INSUFFICIENT_POWER`.

**All repriced pairs (2,543, including book-sourced ends; lower quality).** Per d × dir3, per hidden_state, per verdict and per era, with n per cell, in `probes/p25_M5_repeats_summary.csv`. Headline cells with n ≥ 100:

| d | dir | n | total | theta | IV | move |
|---|---|---|---|---|---|---|
| 1 | CALL | 997 | 0.00 | −2.30 | −0.11 | 0.00 |
| 1 | PUT | 476 | 0.00 | −1.89 | −0.24 | +1.33 |
| 2 | CALL | 264 | −4.31 | −8.11 | +1.80 | −3.03 |
| 2 | PUT | 147 | 0.00 | −5.54 | +0.82 | +1.44 |
| 3 | CALL | 251 | −27.48 | −14.92 | +7.96 | −17.83 |
| 3 | PUT | 146 | +10.09 | −11.29 | +4.30 | +14.67 |
| 5 | CALL | 168 | −24.08 | −25.78 | +5.64 | −5.41 |

d=5 PUT has n 94 (`INSUFFICIENT_POWER`). Hidden-state cells with n ≥ 100:
- COMPRESSED_BALANCED: d1 CALL 441, d1 PUT 189, d2 CALL 110.
- LOW_ENERGY_NO_EDGE: d1 CALL 315, d1 PUT 136, d2 CALL 101.
- COMPRESSED_BEARISH_FORCE: d1 CALL 152.

All other hidden-state cells (41 cells, 1,099 rows) are `INSUFFICIENT_POWER`.

Medians of 0.00 reflect book-to-book pairs whose stored contract fields did not change: 44.0% zero Δpremium on 645 pre-20260831 pairs, against 3.3% on chain-to-chain pairs (`p25_M5_repeats_srccheck.csv`).

The theta curve is monotone in d in every powered cell: about −2%, −6 to −8%, −15 to −19%, and −26% of premium at d = 1, 2, 3, 5.

## 5. delta_p and the waiting inequality

- **State cell** = hidden_state × confirmation state, where confirmation state is the row verdict (`lab_verdict`; `MORNING_VALIDATION_REQUIRED` on pre-20260831 books). P(favourable) is the `label_V = TARGET_FIRST` rate per cell (`p25_M5_state_cells.csv`).
- **Powered cells:** only 4 of 23 have n ≥ 100:

| cell | n | P(TARGET_FIRST) |
|---|---|---|
| COMPRESSED_BALANCED × BLOCKED | 389 | 0.023 |
| COMPRESSED_BALANCED × MVR | 2,763 | 0.055 |
| LOW_ENERGY_NO_EDGE × BLOCKED | 450 | 0.029 |
| LOW_ENERGY_NO_EDGE × MVR | 6,025 | 0.065 |

  MANUAL_REVIEW, the dominant verdict from 20260831 on, has n ≤ 88 in every hidden state, so every thesis-era state cell is `INSUFFICIENT_POWER`.
- **delta_p on pairs with both cells powered:** n per d is 3,611 / 2,729 / 1,458 / 1,910. Median 0.000 at every d; mean −0.007 / −0.009 / −0.002 / −0.012; range −0.042 to +0.036. States change between t and t+d on 15.8% of pairs (hidden_state) and 27.2% (verdict).
- **Overlap problem:** on the clean chain-to-chain subset, only 3 pairs have a powered delta_p. The two sides of the inequality are measured on almost disjoint populations. Premium is measurable after 20260831; P(favourable | state) is powered only before it.
- **Inequality per cell:**
  - Payoff(t+d) = intrinsic at the vol-budget target S_{t+d}(1 ± 1.5·IV_{t+d}·√(10/252)) − mid(t+d).
  - Friction = half-spread at t+d.
  - Share satisfied, on all repriced pairs with a powered delta_p, with the §4.6 sign convention: 12.0% (d1 CALL, n 378), 9.0% (d1 PUT, n 128), 17.0% (d2 CALL, n 108), 25.6% (d2 PUT, n 41, `INSUFFICIENT_POWER`).
  - With the sign convention in Premise note 1: 18.0%, 24.0%, 24.5%, 33.3%.
  - These pairs inherit the book-to-book zero-change contamination, so neither version is reported as a result.

## 6. Findings (DISC-F-M5-n) — RESEARCH_ONLY

**DISC-F-M5-1 — The early-lane median is reproduced (−1.908%), with wide dispersion.**
- Measured: the same-contract IV change for the 232 MONETISABLE rows of 20260905_151448 against the 2026-08-31 stored chain. 148 matched: median −1.908%, IQR 12.4 pp, p10/p90 −18.4/+21.4. CALL n 94 and PUT n 54 are each `INSUFFICIENT_POWER`.
- Does NOT establish: that the IV bought is above or below any fair level; anything about outcomes or P&L; stability across runs (see F-M5-3); a 3-trading-session change (see F-M5-2). The match rate is 64%, and unmatched contracts may differ systematically.
- TRACE: REQ-UNMAPPED | ALG-NONE | WP-NONE | STAGE-NONE | TRACK-M5 | EVIDENCE-p25_M5_earlylane_summary.csv | N=148

**DISC-F-M5-2 — The W3.6 "three sessions earlier" is four trading sessions.**
- Measured: the W3.6 script counts stored-chain sessions (`earlier[-back]`). 2026-09-01 has no chain, so 08-31 is 4 trading sessions back. The true 1- and 2-back changes on the same rows are −1.12% (n 210) and −2.00% (n 179).
- Does NOT establish: that the conclusion changes. Every lookback from 1 to 5 on this run has a median between −2.0% and +0.1%.
- TRACE: REQ-UNMAPPED | ALG-NONE | WP-NONE | STAGE-NONE | TRACK-M5 | EVIDENCE-dataset_registry OPTION_CHAIN; audit/pipeline_map/AVS-IMP-FIX-001/w36_iv_at_selection.py | N=148

**DISC-F-M5-3 — On the 10 Sep selection, the median IV change against 3 sessions earlier is positive (+3.7% / +3.2%).**
- Measured: n 680 / 649, IQR about 13 pp, share ≥ +20% about 10%. Against 09-08 (2 back) it is −1.9% / −2.2%. CALL +5.2/+3.9 and PUT +2.1/+2.1, all n ≥ 100.
- Does NOT establish: a systematic effect. It is one selection date, the sign flips with the lookback date, and every median is far below the +20% threshold. Rows share one market day and are not independent.
- TRACE: REQ-UNMAPPED | ALG-NONE | WP-NONE | STAGE-NONE | TRACK-M5 | EVIDENCE-p25_M5_earlylane_summary.csv | N=1329

**DISC-F-M5-4 — The stale window's price move cannot be measured for the 453 stale contracts themselves.**
- Measured: 0 of 453 have any stored quote after 2026-09-10T17Z. The book's morning mid is a copy of the stale mid on 453/453 rows.
- Does NOT establish: that the stale contracts did not move; why they were not re-quoted.
- TRACE: REQ-UNMAPPED | ALG-NONE | WP-NONE | STAGE-NONE | TRACK-M5 | EVIDENCE-p25_M5_staleness.csv | N=453

**DISC-F-M5-5 — Proxy: over one session (about 23.6 h), same-book contracts moved a median 11.8% in absolute mid (PARTIAL).**
- Measured: n 455 (CALL 316, PUT 139). p90 43.3%. 25% moved more than the prior half-spread. The next-day ask was a median 30.2% above the prior mid.
- Does NOT establish: the stale contracts' own move (different liquidity mix, cheaper premiums); a direction of cost, since the signed median is +1.0%; that a fill would have occurred at that ask.
- TRACE: REQ-UNMAPPED | ALG-NONE | WP-NONE | STAGE-NONE | TRACK-M5 | EVIDENCE-p25_M5_staleness_proxy.csv | N=455

**DISC-F-M5-6 — Thesis identity is not stable across sessions.**
- Measured: 87% of thesis_ids embed their own session date; 752 of 2,887 recur. Repeats are therefore a ticker+direction cohort (PARTIAL).
- Does NOT establish: that a cohort repeat is the same economic thesis. The contract changed on 30% / 47% / 36% / 71% of pairs at d = 1 / 2 / 3 / 5.
- TRACE: REQ-UNMAPPED | ALG-NONE | WP-NONE | STAGE-NONE | TRACK-M5 | EVIDENCE-p25_M5_repeats.csv | N=3639

**DISC-F-M5-7 — Holding the same contract, time decay is the steadiest component of the premium path.**
- Measured: about −2 / −7 / −17 / −26% of premium at d = 1/2/3/5 in powered cells. The IV component is −0.2 to +8%. The move component dominates the total at d=3, with CALL and PUT of opposite sign. Clean-subset totals: d1 CALL 0.0% (n 146); d3 CALL −33.9% (n 160); d3 PUT +17.4% (n 100).
- Does NOT establish: a general cost of waiting. The clean subset starts on only 2–4 sessions; waiting was never executed; payoff is not included.
- TRACE: REQ-UNMAPPED | ALG-NONE | WP-NONE | STAGE-NONE | TRACK-M5 | EVIDENCE-p25_M5_repeats_chainonly.csv | N=769

**DISC-F-M5-8 — delta_p ("what confirmation buys") is powered only on pre-20260831 state cells, and is about 0 there.**
- Measured: median 0.000 and |mean| ≤ 0.012 at every d. Only 4 of 23 cells have n ≥ 100. Only 3 clean-repriced pairs carry a powered delta_p.
- Does NOT establish: that confirmation is worthless. Base rates of 2–7% leave little room to detect change; thesis-era verdict cells are `INSUFFICIENT_POWER`; labels are barrier reconstructions, not fills.
- TRACE: REQ-UNMAPPED | ALG-NONE | WP-NONE | STAGE-NONE | TRACK-M5 | EVIDENCE-p25_M5_state_cells.csv; p25_M5_repeats.csv | N=9693

## Deviations (observations only, no severity)

1. Claimed (commit fc6521b / DECISIONS_FOR_ACK): "three sessions back (2026-08-31)". Found: 4 trading sessions, because the lookback counts stored-chain sessions. Evidence: `w36_iv_at_selection.py` (`earlier[-back]`); chain session list.
2. Claimed (W3.6): "232 MONETISABLE rows". Found: the script builds a set of monetisable *tickers* and joins options rows by ticker. The counts coincide here (232 = 232 = 232), so the equality depends on one row per ticker.
3. Claimed (brief): phantom `options_greeks_history` supports re-pricing at t and t+d. Found: weekly Friday snapshots, with 08-28 and 09-04 the only dates in the thesis window. It cannot price d = 1/2/3 pairs.
4. Stored chains are absent for 2026-09-01 and 2026-09-09, both trading sessions.
5. On 20260911_115904, `morning_contract_mid` equals `contract_mid` and `contract_mid_change_pct` is null on all 453 QUOTE_STALE rows.
6. Pre-20260831 books repeat identical contract bid/ask/mid across sessions on 44% of same-contract book-to-book pairs.

## Premise notes

1. **Sign in the §4.6 waiting inequality.**
   - Spec: waiting is paid for iff delta_p·payoff(t+d) > −delta_premium_total + friction.
   - Measured: delta_premium_total is negative when premium falls while waiting, which is a saving to the waiter. Written as specified, a cheaper later entry raises the bar for waiting.
   - Consistent form: delta_p·payoff > delta_premium_total + friction. Shares differ by 6–14 pp between the two forms on the same pairs (§5).
2. **Early-lane quantity.**
   - Spec: the early-lane decision is one median of % IV change.
   - Measured: row-level dispersion (IQR 9–15 pp; p10 to p90 about 30–40 pp) dwarfs the median (|median| ≤ 4 pp on every population and lookback), and the median's sign flips with the lookback date.
   - Gap: about 10× between the p10–p90 spread and the median's size.
3. **Where the waiting cost sits.**
   - Spec: the question is framed as the IV bought.
   - Measured: at d ≥ 2 the held contract's premium path is dominated by theta (−6 to −26%) and the underlying move (±7 to ±28%); the IV component is −0.2 to +8%.
4. **What delta_p can resolve.**
   - Spec: delta_p by hidden_state × confirmation state.
   - Measured: with TARGET_FIRST base rates of 2–7%, a cell of n ≈ 400 has a binomial SE of about 1.1–1.2 pp, the same order as every measured |delta_p| (≤ 4.2 pp).
   - Gap: the specified measurement cannot resolve delta_p at available cell sizes.

## Not tested / data unavailable

- Staleness move of the 453 stale contracts themselves: DATA_UNAVAILABLE (no later quote stored; would need an 11 Sep re-quote of those symbols).
- Early-lane true 3-trading-session lookback for 20260905 (needs the 09-01 chain) and 1-back for the 09-10 books (needs the 09-09 chain): DATA_UNAVAILABLE.
- No chains before 2026-08-28, and phantom is weekly. Pre-20260831 repeats can be priced only from book fields (contaminated), and d=5 clean pairs are `INSUFFICIENT_POWER`.
- Per-hidden_state and per-liquidity_state curves on the clean subset: all cells `INSUFFICIENT_POWER`.
- Thesis-era delta_p: `INSUFFICIENT_POWER`, because label windows for ≥ 20260831 rows are mostly not elapsed and MANUAL_REVIEW cells have n ≤ 88.
- Monetised outcome (option P&L at exit): DATA_UNAVAILABLE (no fills).

## Expectation vs actual (expectations.md M5 row)

| expectation | actual | gap |
|---|---|---|
| 1.9% IV figure reproducible ± 1pp | −1.908% reproduced exactly | 0.00 pp |
| IQR > 5pp | 12.4 pp (index quartiles 12.5 pp) | about 7 pp above the floor |
| n 100–400 rows | 148 (W3.6 population); 649–693 on the 10 Sep books | in range for W3.6; above for later books |
| staleness median abs Δmid 5–15% | own contracts: not measurable (0/453); proxy 11.8% | inside the band on the proxy only (PARTIAL) |

## State log lines
```
M5-earlylane-reproduce,MEASURED,148,60s,"20260905 MONETISABLE vs 2026-08-31 chain: median -1.908% (exact), IQR 12.4pp, p10 -18.4 p90 +21.4; lookback is 4 trading sessions (09-01 chain absent)"
M5-earlylane-extend,MEASURED,1329,120s,"books 20260910/20260911 MONETISABLE vs 09-04 chain (3 back): median +3.7%/+3.2%, IQR ~13pp; vs 09-08: -1.9%/-2.2%"
M5-staleness-direct,DATA_UNAVAILABLE,453,60s,"0 of 453 QUOTE_STALE contracts have any stored quote after 2026-09-10T17Z; morning_contract_mid==contract_mid 453/453"
M5-staleness-proxy,PARTIAL,455,60s,"same-book non-stale contracts 10Sep->11Sep (23.6h): median abs dmid 11.8% (CALL 12.1 n316, PUT 10.5 n139), p90 43.3%"
M5-thesis-identity,PARTIAL,3639,10s,"87% of thesis_ids embed session date; 752/2887 recur; repeats degraded to ticker+direction cohort"
M5-repeats-decomposition,PARTIAL,769,300s,"12092 pairs, 2560 repriced, 769 clean chain>chain; powered clean cells d1 CALL, d3 CALL, d3 PUT; theta ~-2/-7/-17/-26% at d1/2/3/5; hidden_state and liquidity_state cells all INSUFFICIENT_POWER"
M5-delta-p,INSUFFICIENT_POWER,9693,30s,"4 of 23 hidden_state x verdict cells n>=100 (all pre-0831); powered delta_p median 0 at every d; 3 clean-repriced pairs carry powered delta_p"
M5-waiting-inequality,PARTIAL,655,10s,"evaluated on book-contaminated pairs only; §4.6 sign convention looks inverted (premise note 1); not reported as a result"
```
