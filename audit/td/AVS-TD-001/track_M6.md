# Track M6 — What are the gates selecting on? (discovery, §4.8) — RESEARCH_ONLY
No NORMAL_COMPLETED_SESSION run exists; every result below is on TEST-condition runs and cannot be CLOSED.

**Data source (Rule 10).** Gate membership and scores: per-run artefacts of the 22 runs that wrote `intelligence_lab/final_opportunity_book_<run>.csv` (2026-07-23 → 2026-09-11): `diagnostics/dropoff_audit_<run>.csv`, `discovery/discovery_lifecycle_<run>.csv`, `options/contract_rejection_log_<run>.csv`, `morning_validation/eod_dropoff_audit_<run>.csv` (20260831+), `qomega/garch_forecasts_<run>.csv`; dropoff audits of 25 stub runs for counts only. **Outcomes:** retrospective labels only, rebuilt from `db_copies/historical_prices.sqlite` `ohlcv_daily` (daily bars up to 2026-09-10), and cross-checked against `probes/p32_labels.csv`. H4 (`track_H.md`) found **no counterfactual outcome record** (0 counterfactual `OUTCOME` events), so no ledger outcome is used. None of these outcomes is a fill. Books are used for labels, scores and ranks, never as evidence of edge.

Runs used: 22 book runs; outcome-resolvable subset is 15 runs (20260723_072618 → 20260902_232526; 38,478 ticker-rows resolvable).
Probes (all in `probes/`): `p26_M6_removal_counts.py` → `p26_M6_removal_counts.csv`; `p26_M6_outcomes.py` → `p26_M6_outcomes.csv`; `p26_M6_gate_table.py` → `p26_M6_gate_table.csv` (+ compact `p26_M6_gate_pooled.txt`); `p26_M6_tc.py` → `p26_M6_tc.csv`; `p26_M6_ic.py` → `p26_M6_ic.csv`, `p26_M6_breadth.csv`.

## Method (stated assumptions)
- **Reference and barrier.** S0 is the close on the run's `decision_session` (from `p31_presented_candidates`). Hold h comes from `eod_horizon_bucket`, else the Discovery lifecycle `horizon_bucket` (1_5d→5, 6_10d→10, 11_20d→20), else 10. The barrier is a **symmetric** vol-budget barrier S0·(1 ± 1.5·σ·√(h/252)). It is symmetric because removed rows carry no invalidation level; this differs from p32 `label_V`, which uses the row's own invalidation. Agreement with p32 on the 9,895 shared rows is 98.97% for TARGET_FIRST and 98.66% for side_correct.
- **σ source.** σ = `l3_forward_realised_vol` from `qomega/garch_forecasts_<run>.csv` where the ticker is present (27,254 rows). Otherwise σ is the trailing 20-session realised volatility from `ohlcv_daily` (`sigma_src = RV20_FALLBACK`, 20,204 rows, almost all of them Discovery-removed OTHER rows).
- **Outcome metrics.** For CALL/PUT, hit = TARGET_FIRST (`hit_sym`); `side_correct` (terminal close in the thesis direction) is also reported. OTHER rows have no direction, so their metric is `touch_any` (either barrier touched), a movement measure, not a directional hit.
- **Direction.** Book `governed_direction`/`direction`, else `eod_direction`, else `discovery_direction`. Discovery-removed rows have no direction and are OTHER by construction.
- **Resolvability.** Rows whose window has not elapsed (27,604), with no price series (5,460), no bar on the decision session (1,517) or no σ (21) are excluded. All runs are TEST condition; the condition column is `TEST|sym_vol_budget_K1.5|h=row_or_10`.
- **Intervals and power.** Differences (survivor − removed) carry a Newcombe/Wilson 95% interval; pooled cells also carry a ticker-cluster Poisson bootstrap (500 reps). Any arm with n < 100 is `INSUFFICIENT_POWER`. Pooled rows repeat tickers across runs, and the cluster bootstrap is the interval that allows for that.

## Finding table
| Finding ID | CALL | PUT | OTHER | data source | evidence | N | magnitude |
|---|---|---|---|---|---|---|---|
| DISC-F-M6-1 | removed 3,082 hit 11.4% vs survivors 8.1% | 235 vs 2,452: 3.0% vs 3.8% (interval spans 0) | removed 158 touch 13.3% vs 7.0% | dropoff_audit + ohlcv | `p26_M6_gate_table.csv` gate OPTIONS_INTEL_SCOPE, POOLED | 20,012 resolved | CALL diff −0.033 [−0.045, −0.021]; boot [−0.048, −0.016] |
| DISC-F-M6-2 | removed 3,720 hit 9.0% vs 7.7%; side 50.0% vs 45.1% | removed 463 hit 6.3% vs 3.2%; side 59.2% vs 53.5% | removed 1,476 vs 28 surv (INSUFFICIENT_POWER) | dropoff_audit + ohlcv | gate EIL_EXECUTION_STAGE_prebook, POOLED | 16,774 resolved | CALL −0.013 [−0.024, −0.003]; PUT −0.031 [−0.058, −0.010] |
| DISC-F-M6-3 | spread-rejected 353 hit 3.7% vs 8.2% | spread-rejected 213 hit 8.9% vs 3.3%; side 65.7% vs 53.6% | 766 vs 738, 7.2% vs 6.8% | contract_rejection_log + ohlcv | gate SPREAD_contract_log_GT_25PCT, POOLED | 18,278 resolved | CALL +0.045 [0.019, 0.061]; PUT −0.057 [−0.103, −0.024] (opposite signs) |
| DISC-F-M6-4 | STAND_DOWN 10,263 hit 6.9% vs 11.1% | STAND_DOWN 1,664 side 56.6% vs 50.5% (hit interval spans 0) | 7.0% vs 7.3% | dropoff_audit oi_verdict + ohlcv | gate OI_VERDICT_STAND_DOWN, POOLED | 17,978 resolved | CALL +0.042 [0.031, 0.053]; PUT side −0.061 [−0.103, −0.018] |
| DISC-F-M6-5 | lab BLOCKED 890 hit 3.7% vs 8.1% | BLOCKED 275 hit 1.8% vs 3.4% (interval spans 0) | INSUFFICIENT_POWER (28) | final book + ohlcv | gate LAB_VERDICT_BLOCKED, POOLED | 12,591 resolved | CALL +0.044 [0.028, 0.056] |
| DISC-F-M6-6 | GO/GO_LIMIT inclusion vs scores: median Spearman −0.03…+0.16 across runs | same | GO set 0 rows OTHER | final books | `p26_M6_tc.csv` UNGATED_BOOK lab_GO_or_GO_LIMIT | 22 runs (3–4 defined) | primary: \|ρ\| ≤ 0.12 for all 6 scores |
| DISC-F-M6-7 | book rank vs priority_score ρ 0.94 (median); vs composite 0.03, ev3 lower bound 0.01, eil_composite −0.04 | same | — | final books; `contracts/lab_control.py:3033-3041` | `p26_M6_tc.csv` GATED_lab_not_BLOCKED | 9–21 runs | rank = verdict order, then −priority_score |
| DISC-F-M6-8 | N_eff 11–15 at every gate stage | — | — | ohlcv 60-session returns | `p26_M6_breadth.csv` | 22 runs | ρ̄ 0.061–0.090; 1,572 rows → N_eff 13.7 (primary) |
| DISC-F-M6-9 | IC in book (pooled): vanguard_probability_edge +0.083, trigger_score −0.090 | priority_score −0.32, options_score −0.25 (n 171, 123 tickers) | — | book + ohlcv | `p26_M6_ic.csv` step 3_in_book | 10,604 CALL / 171–1,987 PUT | \|IC\| ≤ 0.09 on CALL for every score |
| DISC-F-M6-10 | 0 | 0 | 0 | final books | `p26_M6_removal_counts.csv` BOOK_usmi_sector_alignment | 1,444 (primary) | macro route differentiates no row: NEUTRAL 1,444/1,444 (UNAVAILABLE 264/264 on 20260906) |
| DISC-F-M6-11 | Discovery-removed rows have no direction | — | removed 16,701 touch 22.3% vs survivors 7.6% | dropoff_audit + ohlcv | gate DISCOVERY_SCOPE, POOLED | 18,363 | −0.147 [−0.160, −0.132]; σ source differs by arm (see finding) |

## Per-gate table (pooled over resolvable runs; hit = TARGET_FIRST on the symmetric barrier; OTHER = touch_any)
Full per-run cells (704) are in `p26_M6_gate_table.csv`. Of those, 51 have both arms at n ≥ 100.

| gate (what it selects on) | dir | population | removed | resolved surv / rem | surv rate | rem rate | diff [Newcombe] | ticker-boot | side_correct surv / rem | power |
|---|---|---|---|---|---|---|---|---|---|---|
| Discovery scope: liquidity/price/tier-4/no-horizon, 7 causes under one code | CALL | 24,153 | 0 (no direction on removed) | 17,428 / 0 | 0.087 | — | — | — | 0.466 / — | INSUFFICIENT_POWER |
| | PUT | 6,473 | 0 | 2,687 / 0 | 0.037 | — | — | — | 0.547 / — | INSUFFICIENT_POWER |
| | OTHER | 42,454 | 37,647 | 1,662 / 16,701 | 0.076 | 0.223 | −0.147 [−0.160, −0.132] | [−0.166, −0.130] | abs move σ 0.42 / 0.50 | n≥100 |
| Vanguard reject: DATA_FAILURE_NO_OHLCV | CALL | 24,153 | 618 | 17,425 / 3 | 0.087 | 0.000 | — | — | — | INSUFFICIENT_POWER |
| | PUT / OTHER | 6,473 / 4,807 | 111 / 251 | — / 0 | — | — | — | — | — | INSUFFICIENT_POWER (removed rows lack price bars) |
| Options Intelligence scope: tier ∉ {0,1,2} or WAIT without Vanguard support; merge | CALL | 23,535 | 3,137 | 14,343 / 3,082 | 0.081 | 0.114 | −0.033 [−0.045, −0.021] | [−0.048, −0.016] | 0.464 / 0.479 | n≥100 |
| | PUT | 6,362 | 326 | 2,452 / 235 | 0.038 | 0.030 | +0.008 [−0.023, 0.025] | [−0.019, 0.031] | 0.546 / 0.549 | n≥100 |
| | OTHER | 4,556 | 1,040 | 1,504 / 158 | 0.070 | 0.133 | −0.063 [−0.126, −0.017] | [−0.136, −0.002] | — | n≥100 |
| EIL / EOD manifest stage before book (runs ≤ 20260902) | CALL | 20,379 | 7,159 | 10,604 / 3,720 | 0.077 | 0.090 | −0.013 [−0.024, −0.003] | [−0.027, 0.000] | 0.451 / 0.500 | n≥100 |
| | PUT | 6,034 | 2,543 | 1,987 / 463 | 0.032 | 0.063 | −0.031 [−0.058, −0.010] | [−0.060, −0.007] | 0.535 / 0.592 | n≥100 |
| | OTHER | 3,516 | 3,111 | 28 / 1,476 | 0.214 | 0.067 | — | — | — | INSUFFICIENT_POWER (28) |
| OI verdict STAND_DOWN (row kept) | CALL | 20,379 | 14,919 | 4,061 / 10,263 | 0.111 | 0.069 | +0.042 [0.031, 0.053] | [0.027, 0.057] | 0.515 / 0.443 | n≥100 |
| | PUT | 6,034 | 4,179 | 786 / 1,664 | 0.033 | 0.040 | −0.007 [−0.021, 0.011] | [−0.025, 0.011] | 0.505 / 0.566 | n≥100 |
| | OTHER | 3,516 | 3,165 | 177 / 1,327 | 0.073 | 0.069 | +0.004 [−0.029, 0.054] | — | — | n≥100 |
| Spread: ticker has a SPREAD_GT_25PCT contract rejection | CALL | 20,379 | 4,038 | 13,971 / 353 | 0.082 | 0.037 | +0.045 [0.019, 0.061] | [0.023, 0.065] | 0.465 / 0.414 | n≥100 |
| | PUT | 6,034 | 2,250 | 2,237 / 213 | 0.033 | 0.089 | −0.057 [−0.103, −0.024] | [−0.102, −0.018] | 0.536 / 0.657 | n≥100 |
| | OTHER | 3,516 | 1,104 | 738 / 766 | 0.068 | 0.072 | −0.004 [−0.030, 0.022] | [−0.035, 0.027] | — | n≥100 |
| Open interest: audit flag LOW_OI | CALL | 20,379 | 4,102 | 12,917 / 1,407 | 0.081 | 0.080 | 0.000 [−0.016, 0.014] | [−0.018, 0.019] | 0.459 / 0.507 | n≥100 |
| | PUT | 6,034 | 1,907 | 2,258 / 192 | 0.035 | 0.068 | −0.033 [−0.078, −0.004] | [−0.076, 0.002] | 0.539 / 0.625 | n≥100 |
| | OTHER | 3,516 | 826 | 1,022 / 482 | 0.071 | 0.066 | +0.005 [−0.024, 0.031] | — | — | n≥100 |
| EOD manifest mask (proxy: eod_dropoff_reason ≠ PRESERVED_TO_MORNING_VALIDATION; 20260831+) | CALL | 13,220 | 11,640 | 1,028 / 9,576 | 0.109 | 0.074 | +0.035 [0.017, 0.056] | [0.011, 0.064] | 0.472 / 0.449 | n≥100 |
| | PUT | 3,491 | 2,204 | 664 / 1,323 | 0.030 | 0.033 | −0.002 [−0.018, 0.016] | [−0.021, 0.016] | 0.500 / 0.553 | n≥100 |
| | OTHER | 405 | 399 | 6 / 22 | — | — | — | — | — | INSUFFICIENT_POWER |
| EIL signal not EXECUTE* (BLOCKED/WATCHLIST/NOT_EVALUATED) | CALL | 13,220 | 1,837 | 10,356 / 248 | 0.077 | 0.109 | −0.032 [−0.077, 0.001] | [−0.080, 0.011] | 0.452 / 0.387 | n≥100 |
| | PUT | 3,491 | 916 | 1,904 / 83 | — | — | — | — | — | INSUFFICIENT_POWER (83) |
| | OTHER | 405 | 371 | 28 / 0 | — | — | — | — | — | INSUFFICIENT_POWER |
| lab_verdict BLOCKED | CALL | 13,220 | 1,609 | 9,714 / 890 | 0.081 | 0.037 | +0.044 [0.028, 0.056] | [0.028, 0.060] | 0.454 / 0.422 | n≥100 |
| | PUT | 3,491 | 672 | 1,712 / 275 | 0.034 | 0.018 | +0.016 [−0.009, 0.030] | [−0.003, 0.032] | 0.532 / 0.560 | n≥100 |
| | OTHER | 405 | 201 | 16 / 12 | — | — | — | — | — | INSUFFICIENT_POWER |
| lab_verdict not GO/GO_LIMIT | CALL / PUT / OTHER | 13,220 / 3,491 / 405 | 13,190 / 3,462 / 403 | 15 / 20 / 2 survivors resolved | — | — | — | — | — | INSUFFICIENT_POWER |
| Morning Gate not GO_LIMIT/GO/CONTRACT_REPAIR | CALL / PUT / OTHER | 1,830 / 771 / 203 | 1,782 / 736 / 200 | 30 / 22 / 3 survivors | — | — | — | — | — | INSUFFICIENT_POWER |
| opportunity_tier BLOCK (20260904+) | CALL / PUT / OTHER | 1,910 / 1,087 / 370 | 1,451 / 809 / 370 | 0 / 0 resolved (window not elapsed) | — | — | — | — | — | INSUFFICIENT_POWER (n=0) |
| quote_freshness not FRESH/SESSION_ALIGNED | CALL / PUT / OTHER | 2,325 / 1,410 / 35 | 203 / 154 / 8 | 154/18 · 102/58 · 22/6 | — | — | — | — | — | INSUFFICIENT_POWER |
| liquidity_state ≠ EXECUTABLE_NOW | CALL / PUT / OTHER | 2,695 / 1,658 / 223 | 2,002 / 1,189 / 217 | 58/129 · 15/156 · 4/24 | — | — | — | — | — | INSUFFICIENT_POWER |
| macro route: usmi_sector_alignment headwind/conflict | CALL / PUT / OTHER | 1,910 / 1,087 / 370 | 0 / 0 / 0 | — | — | — | — | — | — | INSUFFICIENT_POWER (nothing removed) |
| final_action BLOCK | CALL / PUT / OTHER | 2,695 / 1,659 / 405 | 721 / 518 / 201 | 174/13 · 48/123 · 16/12 | — | — | — | — | — | INSUFFICIENT_POWER |

**Rows removed per run.** On the primary run 20260911_115904, 3,320 inputs split as follows: Discovery 1,748 (OTHER); Vanguard reject 50 (18/13/19); Options Intelligence scope 78 (3/7/68); EIL pre-book 0. The book holds 1,444 rows, and label gates flag within them: OI STAND_DOWN 990; spread-rejected tickers 463; LOW_OI 640; EOD reason ≠ preserved 1,126; opportunity_tier BLOCK 1,443; lab BLOCKED 450; Morning Gate not GO 1,423; quote_freshness NA 451; usmi 0. Pooled over the 22 book runs: Discovery 37,464; OI scope 4,503; EIL/EXECUTION pre-book 9,725 + 2,136 + 952 shadow; Vanguard reject 980. The EIL pre-book stage is present on every run up to 20260909 and absent on 20260910 and 20260911, where the book equals the OI population. Per run × direction counts are in `p26_M6_removal_counts.csv`.

**What each gate selects on.** Standardised mean difference, survivor − removed, pooled; `p26_M6_gate_pooled.txt` lines 53–103:
- **Options Intelligence scope:** survivors carry higher `vanguard_probability_edge` (CALL +0.37, PUT +0.72) and higher σ (+0.32 / +0.55). `discovery_composite_score` goes opposite ways by direction (CALL +0.63, PUT −0.59).
- **EIL pre-book:** survivors have much lower `oi_options_score` (CALL −0.95, OTHER −0.86). The gate keeps rows the options layer scored low, consistent with the book carrying repair and stand-down rows.
- **OI STAND_DOWN:** removal is `oi_options_score`/`priority_score` driven (SMD +1.4 to +1.9 on both directions). Survivors also have higher σ (+0.40).
- **Spread and LOW_OI:** both select on `oi_options_score` (spread −0.75 CALL, −2.05 OTHER). LOW_OI shows `eil_composite_eod` SMD +6.05 CALL / +4.92 PUT, which indicates `eil_composite_eod` is near-constant with a shift between arms, not a broad distribution.
- **lab BLOCKED:** `options_score` +0.74 and `priority_score` +0.69 (CALL). `composite_score` −0.05 and `ev3_ev_lower_bound_return` +0.14.
- **EIL signal:** selects on `eil_composite_eod` (+1.53 / +1.76) and on **lower σ** (−1.25 / −1.41).
- **opportunity_tier:** `priority_score` +1.28 / +1.22, `options_score` +0.73 / +0.82.

**Gates whose removed rows show a higher rate than their survivors** (noted, not characterised; pooled interval excludes zero):
- Options Intelligence scope: CALL hit; OTHER touch.
- EIL pre-book: CALL hit and side_correct; PUT hit and side_correct.
- Spread: PUT hit and side_correct.
- LOW_OI: PUT hit (Newcombe only; bootstrap spans 0) and side_correct.
- OI STAND_DOWN: PUT side_correct.
- EOD manifest proxy: PUT side_correct.
- Discovery scope: OTHER touch (movement, not direction).

Per run, among cells with both arms n ≥ 100: OI scope CALL has removed > survivor in 9 of 12 runs (6 with interval excluding 0); EIL pre-book CALL in 8 of 12 (0 excluding 0); LOW_OI CALL in 4 of 8.

## TC table (no outcomes; `p26_M6_tc.csv`)
Spearman / Pearson (point-biserial for inclusion). Cross-run values are medians over runs where the correlation is defined. Many runs are undefined because inclusion is constant: lab GO inclusion is constant on 18 of 22 runs.

| population | inclusion or weight | score | primary run ALL ρ_s / ρ_p (n, included) | CALL ρ_s | PUT ρ_s | cross-run median ρ_s [min, max] (runs) |
|---|---|---|---|---|---|---|
| UNGATED Discovery survivors | reached book | discovery_composite_score | −0.095 / −0.098 (1,572; 1,444) | −0.113 | −0.084 | 0.086 [−0.095, 0.287] (22) |
| | reached book | vanguard_probability_edge | 0.033 / 0.060 (1,522) | −0.029 | 0.052 | 0.024 [−0.009, 0.069] (22) |
| | reached book | oi_options_score | undefined (every scored row is in the book) | — | — | −0.436 [−0.708, 0.190] (20) |
| UNGATED book | lab GO/GO_LIMIT | composite / priority / options / trigger / eil_composite / ev3_lb | −0.072 / 0.073 / 0.080 / −0.036 / −0.078 / −0.123 (1,444; 19) | −0.07 / 0.07 / 0.06 / −0.07 / −0.03 / −0.16 | −0.10 / 0.02 / 0.08 / 0.00 / −0.12 / undef | −0.027 / 0.132 / 0.079 / 0.064 / −0.015 / 0.161 (3–4) |
| | lab not BLOCKED | composite / priority / options / trigger / eil_composite / ev3_lb | −0.026 / **0.679** / **0.676** / 0.017 / −0.251 / −0.032 (1,444; 994) | −0.08 / 0.52 / 0.55 / 0.09 / −0.10 / −0.06 | −0.15 / 0.51 / 0.52 / −0.16 / −0.10 / undef | −0.021 / 0.143 / 0.109 / 0.064 / 0.015 / 0.123 (3–16) |
| | eil EXECUTE* | composite / priority / options / trigger / eil_composite / ev3_lb | −0.007 / 0.458 / 0.289 / 0.005 / **0.427** / 0.194 (1,444; 215) | eil_composite 0.45 | eil_composite 0.57 | eil_composite 0.298 [−0.033, 0.441] (19) |
| | opportunity_tier not BLOCK | all six | \|ρ\| ≤ 0.04 (1,444; 1) | ≤ 0.06 | undefined (0 included) | priority 0.370 [−0.087, 0.839] (4) |
| | Morning GO | all six | \|ρ\| ≤ 0.12 (1,444; 21) | ≤ 0.16 | ≤ 0.10 | ≤ 0.16 (3–4) |
| UNGATED book | −lab_rank | priority / options / composite / eil_composite / ev3_lb | −0.155 / −0.358 / 0.076 / 0.213 / 0.011 (1,444) | — | — | 0.940 / 0.633 / 0.028 / −0.046 / −0.036 (8–22) |
| GATED lab not BLOCKED | −lab_rank | priority / options / composite / trigger / eil_composite / ev3_lb | — (994) | — | — | **0.945** / 0.659 / 0.027 / 0.006 / −0.035 / 0.008 (7–21) |
| GATED lab GO/GO_LIMIT | −lab_rank | priority / options / composite / ev3_lb | 1.000 / 0.497 / −0.186 / −0.900 (19; ev3 n=5) | — | — | INSUFFICIENT_POWER (n 5–19 per run) |

`lab_rank` and `priority_rank` are the same integer (`contracts/lab_control.py:2432-2433`). The book is sorted by the lab_verdict order and then by −`priority_score` (`:3033-3041`). A within-verdict rank–priority correlation near 1 is therefore mechanical, not a measured transfer. On the primary ungated book the rank correlates *negatively* with `priority_score` (−0.155), because the verdict order dominates.

## IC / breadth table
**IC** is pooled over resolvable runs: Spearman of each score against the directional return in σ units (`dir_ret_sig`) and against `hit_sym`. There are 160 cells, 99 with n ≥ 100. No multiple-testing adjustment was applied, so treat single p-values as descriptive.

| stage | dir | score | n (tickers) | IC dir_ret_sig | p | IC hit |
|---|---|---|---|---|---|---|
| Discovery survivors | CALL | discovery_composite_score | 17,428 (1,775) | −0.024 | 0.002 | −0.080 |
| | CALL | vanguard_probability_edge | 17,406 (1,773) | +0.092 | <0.001 | +0.077 |
| | CALL | oi_options_score | 14,324 (1,733) | +0.036 | <0.001 | +0.005 |
| | PUT | discovery_composite_score | 2,687 (947) | +0.006 | 0.76 | −0.057 |
| | PUT | vanguard_probability_edge | 2,685 (946) | −0.043 | 0.026 | −0.025 |
| after OI scope | CALL | vanguard_probability_edge | 14,324 | +0.088 | <0.001 | +0.074 |
| in book | CALL | trigger_score | 10,604 (1,659) | −0.090 | <0.001 | −0.018 |
| | CALL | eil_composite_eod | 10,604 | +0.004 | 0.67 | −0.012 |
| | CALL | composite / priority / options | 187 (143) | +0.085 / +0.063 / +0.068 | 0.25 / 0.39 / 0.35 | — |
| | PUT | priority_score | 171 (123) | −0.320 | <0.001 | −0.089 |
| | PUT | options_score | 171 (123) | −0.254 | <0.001 | −0.129 |
| | PUT | trigger / eil_composite | 1,987 (747) | +0.004 / −0.034 | 0.85 / 0.14 | — |
| eil EXECUTE* | CALL | vanguard_probability_edge / trigger | 10,356 | +0.086 / −0.094 | <0.001 | — |
| lab not BLOCKED | CALL | trigger_score | 9,714 | −0.106 | <0.001 | −0.027 |
| lab GO/GO_LIMIT | CALL / PUT | all | 15 / 20 | — | — | INSUFFICIENT_POWER |
| opportunity_tier not BLOCK | CALL / PUT | all | 0 / 0 | — | — | INSUFFICIENT_POWER (n=0) |

**Effective breadth** (`p26_M6_breadth.csv`, direction ALL): N_eff = n / (1 + (n−1)·ρ̄), where ρ̄ is the mean pairwise correlation of the survivors' daily returns over the 60 sessions before the decision session.

| run | Discovery survivors n / N_eff | after OI scope | in book | eil EXECUTE* | lab not BLOCKED | lab GO/GO_LIMIT | opp. tier not BLOCK |
|---|---|---|---|---|---|---|---|
| 20260723_072618 | 1,695 / 12.7 | 1,379 / 13.2 | 1,068 / 13.0 | 1,011 / 12.5 | 1,056 / 13.1 | 0 | 0 |
| 20260824_100301 | 1,630 / 13.5 | 1,307 / 13.7 | 934 / 13.6 | 932 / 13.6 | 35 / 5.2 | 25 / 4.7 | 0 |
| 20260901_082437 | 1,518 / 13.5 | 1,283 / 13.3 | 191 / 13.3 | 179 / 13.5 | 65 / 11.8 | 13 / 7.4 | 0 |
| 20260906_213931 | 1,587 / 14.1 | 1,461 / 13.9 | 264 / 10.7 | 84 / 6.7 | 264 / 10.7 | 0 | 124 / 6.9 |
| 20260909_071646 | 1,585 / 14.8 | 1,448 / 14.6 | 235 / 12.6 | 73 / 8.2 | 231 / 12.8 | 4 / 2.0 | 1 |
| 20260910_150045 | 1,544 / 14.4 | 1,424 / 14.2 | 1,424 / 14.2 | 220 / 13.6 | 941 / 13.3 | 0 | 611 / 13.7 |
| 20260911_115904 | 1,572 / 13.7 | 1,444 / 13.6 | 1,444 / 13.6 | 215 / 14.5 | 994 / 13.1 | 19 / 7.8 | 1 |

Across all 22 runs, ρ̄ lies between 0.061 and 0.090 for every population of 179 rows or more. N_eff is 10.7–15.2 whether the population holds 1,695 rows or 179.

## Findings

**DISC-F-M6-1 — Options Intelligence scope (tier/WAIT/merge) removes CALL rows whose barrier-hit rate exceeds the survivors'.**
- Pooled CALL: removed 11.4% (n 3,082) vs survivors 8.1% (n 14,343); diff −0.033 [−0.045, −0.021], ticker-bootstrap [−0.048, −0.016].
- CALL per run: removed > survivor in 9 of 12 runs with both arms ≥ 100.
- OTHER: touch 13.3% vs 7.0%.
- PUT: no difference (interval spans 0).
- The gate selects on `vanguard_probability_edge` and σ, which are higher among survivors. The removed rows have lower σ, and a lower-σ barrier is closer, which may by itself raise TARGET_FIRST frequency.

Does NOT establish: that the removed rows were monetisable, that the gate costs P&L, or that the gap survives a σ-matched comparison (the barrier scales with σ, and σ differs between arms). Retrospective labels on TEST runs; not a fill.
TRACE: UNMAPPED | ALG-08 | NONE | NONE | TRACK-M6 | EVIDENCE-p26_M6_gate_table.csv | N=20012

**DISC-F-M6-2 — The pre-book EIL/EOD manifest stage (runs ≤ 20260909) removed CALL and PUT rows with higher hit and side-correct rates than the rows it kept.**
- CALL: hit 9.0% vs 7.7%, diff −0.013 [−0.024, −0.003]; side_correct 50.0% vs 45.1%.
- PUT: hit 6.3% vs 3.2%, diff −0.031 [−0.058, −0.010]; side_correct 59.2% vs 53.5%.
- Survivors have a much lower `oi_options_score` (SMD −0.95 CALL).

Does NOT establish: that the removed rows were expressible in options (many had no usable contract), any P&L, or a causal effect. Per run, 0 of 12 CALL cells exclude zero individually. The PUT interval upper bound (−0.006 side_correct) is close to zero.
TRACE: UNMAPPED | ALG-08 | NONE | NONE | TRACK-M6 | EVIDENCE-p26_M6_gate_table.csv | N=16774

**DISC-F-M6-3 — The spread gate splits by direction.**
- CALL tickers with a SPREAD_GT_25PCT rejection: hit 3.7% vs 8.2%, diff +0.045 [0.019, 0.061].
- PUT: hit 8.9% vs 3.3%, diff −0.057 [−0.103, −0.024]; side_correct 65.7% vs 53.6%.
- OTHER: no difference.

Does NOT establish: whether the spread would have consumed the move (no option P&L computed), or that the PUT pattern holds per run (PUT per-run cells are INSUFFICIENT_POWER). The measure is ticker-level: a ticker is flagged if any tested contract was rejected for spread.
TRACE: UNMAPPED | ALG-08 | NONE | NONE | TRACK-M6 | EVIDENCE-contract_rejection_log_<run>.csv;p26_M6_gate_table.csv | N=18278

**DISC-F-M6-4 — OI STAND_DOWN keeps CALL survivors with a higher hit rate (11.1% vs 6.9%, +0.042 [0.031, 0.053]); PUT rows it stands down are side-correct more often (56.6% vs 50.5%).**
- The label selects on `oi_options_score`/`priority_score` (SMD ≈ +1.4 to +1.9) and on σ (+0.40).
- CALL per run: the interval excludes 0 in 4 of 12 runs.

Does NOT establish: that the options score carries directional information independent of σ. A higher σ changes barrier distance.
TRACE: UNMAPPED | ALG-08 | NONE | NONE | TRACK-M6 | EVIDENCE-dropoff_audit_<run>.csv oi_verdict | N=17978

**DISC-F-M6-5 — lab_verdict BLOCKED flags CALL rows with a lower hit rate (3.7% vs 8.1%, +0.044 [0.028, 0.056]).**
- PUT: interval spans 0.
- The flag selects on `options_score` (+0.74) and `priority_score` (+0.69), not on `composite_score` (−0.05).
- The downstream GO/GO_LIMIT, Morning Gate, opportunity_tier, quote_freshness and liquidity gates have ≤ 58 resolved survivors each: INSUFFICIENT_POWER.

Does NOT establish: anything about GO rows, or anything on runs after 20260902. Most BLOCKED rows with outcomes come from 20260824 (899 BLOCKED that run).
TRACE: UNMAPPED | ALG-08 | NONE | NONE | TRACK-M6 | EVIDENCE-final_opportunity_book_<run>.csv lab_verdict | N=12591

**DISC-F-M6-6 — Inclusion in the GO set is nearly uncorrelated with every unconstrained score.**
- Primary run: \|ρ_s\| ≤ 0.12 for composite, priority, options, trigger, eil_composite_eod and the ev3 lower bound. Cross-run medians range from −0.03 to +0.16.
- The non-BLOCKED set correlates with `priority_score`/`options_score` at 0.68 on the primary run, but only 0.14/0.11 as a cross-run median.
- The EIL EXECUTE* set correlates with `eil_composite_eod` at 0.43, i.e. its own score.
- `composite_score` and `ev3_ev_lower_bound_return` have \|ρ\| ≤ 0.13 against every inclusion indicator on the primary run.

Does NOT establish: that any score should drive inclusion. TC here uses scores the pipeline did not claim to allocate on. Correlations with a 19-row inclusion set are unstable.
TRACE: UNMAPPED | NONE | NONE | NONE | TRACK-M6 | EVIDENCE-p26_M6_tc.csv | N=1444

**DISC-F-M6-7 — Book rank encodes verdict order and then `priority_score`.**
- Within gated sets, rank vs `priority_score` has median ρ 0.945. Against `composite_score` it is 0.03, against `ev3_ev_lower_bound_return` 0.01, and against `eil_composite_eod` −0.04.
- No position size exists to serve as a weight: the book writes `position_size_display = "HUMAN DETERMINED"` (`contracts/lab_control.py:3013`) and `eod_sizing_policy` is PSE_IGNORED_MANUAL_SIZING.

Does NOT establish: which score the rank should use. The value is mechanical by construction.
TRACE: UNMAPPED | NONE | NONE | NONE | TRACK-M6 | EVIDENCE-contracts/lab_control.py:3033-3041;p26_M6_tc.csv | N=22 runs

**DISC-F-M6-8 — Effective breadth is set by cross-sectional correlation, not by the number of rows any gate leaves.**
- ρ̄ is 0.061–0.090, so N_eff ≈ 11–15 for every population from 179 to 1,695 rows.
- The primary run's 1,572 Discovery survivors and its 994 non-BLOCKED rows both give N_eff ≈ 13–14. The 19 GO rows give 7.8.

Does NOT establish: forward correlation during the hold, or correlation of option returns. It uses 60 trailing sessions of underlying returns, equal-weighted.
TRACE: UNMAPPED | NONE | NONE | NONE | TRACK-M6 | EVIDENCE-p26_M6_breadth.csv | N=22 runs

**DISC-F-M6-9 — On resolved rows the ICs are small.**
- CALL, in book: \|IC\| ≤ 0.09 for every score. `vanguard_probability_edge` is +0.08 to +0.09 at every stage; `trigger_score` is −0.09 to −0.11.
- PUT, in book: `priority_score` −0.32 and `options_score` −0.25 on 171 rows (123 tickers, runs 20260831–0902, 1–5 day holds only).
- 99 cells were examined with n ≥ 100, with no multiple-testing adjustment.

Does NOT establish: a stable relationship. The PUT cell comes from 3 runs and one hold bucket, and would need BH adjustment across the 99 cells before any reading.
TRACE: UNMAPPED | ALG-08 | NONE | NONE | TRACK-M6 | EVIDENCE-p26_M6_ic.csv | N=10604/1987

**DISC-F-M6-10 — The macro route removes nothing.**
- `usmi_sector_alignment` is NEUTRAL on 1,444 of 1,444 rows (20260911) and UNAVAILABLE on 264 of 264 (20260906).
- `discovery_macro_caution` is NONE on 1,572 of 1,572.
- No row is differentiated, so there is no removed-vs-survivor comparison.

Does NOT establish: how the route would behave with a populated packet.
TRACE: UNMAPPED | NONE | NONE | NONE | TRACK-M6 | EVIDENCE-p26_M6_removal_counts.csv BOOK_usmi_sector_alignment | N=1444

**DISC-F-M6-11 — Discovery-removed tickers moved more, in σ units, than Discovery survivors.**
- Touch-either-barrier: 22.3% (16,701) vs 7.6% (1,662); median \|move\|/σ_h 0.50 vs 0.42.
- The σ source differs by arm: removed rows mostly use RV20_FALLBACK, survivors GARCH. The difference may partly be a σ-estimator artefact.
- No direction exists for removed rows, so CALL/PUT hit rates cannot be reconstructed.

Does NOT establish: directional value, or anything about the seven collapsed Discovery causes individually (`comprehension.md` item 11).
TRACE: UNMAPPED | ALG-08 | NONE | NONE | TRACK-M6 | EVIDENCE-dropoff_audit_<run>.csv;ohlcv_daily | N=18363

## What was reconstructable
- **Fully:** Options Intelligence scope, EIL pre-book, OI STAND_DOWN, spread, LOW_OI and lab BLOCKED, on runs 20260723–20260902. The EOD manifest proxy is resolvable only on the 1–5 day rows of 20260831–0902.
- **Discovery scope:** movement measure only; no direction.
- **Vanguard reject:** 3 resolvable rows; the rejected tickers lack OHLCV.
- **opportunity_tier (20260904+):** 0 resolvable rows; no window has elapsed.
- **Morning Gate, quote_freshness, liquidity_state:** INSUFFICIENT_POWER (≤ 58 resolved survivors).
- **Macro route:** nothing removed.

## Deviations (observations, no severity)
- **EOD manifest mask column.** `eod_candidate_engine.py:2867` writes `phase10_manifest_include` and `:2882-2887` writes `phase10_manifest_exclusion_reason` to `full_out_df`. Neither column appears in `eod_dropoff_audit_<run>.csv` (141 columns, 20260831 and 20260911). The artefact carries only `eod_dropoff_reason`, which M6 used as a proxy.
- **quote_freshness vocabulary.** The value set changes between runs: `SESSION_ALIGNED / SYNTHETIC_NOT_EXECUTABLE / UNAVAILABLE` on 20260831–0906, `FRESH / NA` on 20260911 (993 / 451).
- **Discovery lifecycle reason code.** `discovery_lifecycle` reports `NO_SIGNAL_AT_ANY_HORIZON` for 1,720 of the 1,748 primary drops. The dropoff audit's `vanguard_expected_options_scope` reconstructs the OI-scope exclusions heuristically, labelling 1,748 rows `EXCLUDED_BY_SCOPE_RULES` although they never reached Vanguard.
- **σ coverage.** `qomega/garch_forecasts_<run>.csv` covers some non-book tickers on older runs (5,659 non-book rows had a GARCH σ), so it is not strictly book-scoped.
- **Duplicate rank columns.** `lab_rank` and `priority_rank` are always identical (`contracts/lab_control.py:2432-2433`).
- **Pre-book EIL stage.** Present on runs up to 20260909 (e.g. 20260906: 835 `EIL` dropoffs); absent on 20260910 and 20260911, where book = Options Intelligence population. This agrees with D4's 3,320 = 1,444 + 1,876 identity.
- **Direction in the audit.** Direction for Discovery-removed tickers is absent in the dropoff audit (all `discovery_direction` NaN), so the three-direction split cannot be applied to that removal point.

## Premise notes
- **Transfer target.** The spec (§4.8) frames TC against "the unconstrained score". The book has no single unconstrained score: rank is verdict order and then `priority_score`, and `composite_score` and `ev3_ev_lower_bound_return` have \|ρ\| ≤ 0.13 with every inclusion indicator on the primary run. Measured TC is 0.68 against priority_score (non-BLOCKED set, primary) and ≤ 0.13 against the EV lower bound. The gap between those two figures depends on which score is taken as the target.
- **Breadth.** Gate design counts rows (1,444 presented, 19 GO). Measured N_eff is 11–15 for any population of 179 rows or more (ρ̄ ≈ 0.07). The ratio of row count to effective breadth is about 100:1 at the book stage.
- **Barrier distance.** Every gate that removes lower-σ rows is compared on a σ-scaled barrier (ALG-08 form), so hit-rate differences mix gate selection with barrier distance. SMD of σ between arms ranges from −1.41 (EIL signal) to +0.55 (OI scope PUT).

## Not tested / insufficient
- **Morning Gate states, opportunity_tier, quote freshness, liquidity_state, lab GO:** INSUFFICIENT_POWER. The outcome window has not elapsed on the runs that carry these fields (populated 20260831+/20260904+).
- **Option-level P&L of removed rows:** not computed. There are no fills and no contract for most removed rows.
- **Multiple-testing adjustment:** not applied to the 51 pooled gate cells or the 99 IC cells. Values are descriptive.
- **σ-matched comparison:** not run. It would separate barrier-distance effects from gate selection.

## Expectation vs actual (`expectations.md` M6 row: "TC (inclusion vs unconstrained score) < 0.3; hit-rate halves INSUFFICIENT_POWER")
- **TC.** For GO inclusion, actual \|ρ\| ≤ 0.16 (median) against every score, in line with the expectation. For the non-BLOCKED set on the primary run, TC against `priority_score`/`options_score` is 0.68, above the expected < 0.3. TC against `composite_score`/EV3 is ≤ 0.13.
- **Hit-rate halves.** Expected all INSUFFICIENT_POWER; actual 23 pooled gate × direction cells reach n ≥ 100 in both arms. These are the pre-book gates, OI STAND_DOWN, spread, LOW_OI, lab BLOCKED and the EOD proxy, because older runs' removed rows are reconstructable from the price store. Every gate added on 20260831 or later remains INSUFFICIENT_POWER. The gap is that more of the question is answerable than expected, but only for the older gates.
- **Unexpected.** Breadth is saturated by correlation (N_eff ≈ 13 regardless of gate), and several gates show removed rows with higher rates than survivors.

## State log lines
```
M6-1-removal-counts,MEASURED,1330,58s,"47 runs with dropoff audit; 22 with book; primary: Discovery 1748, Vanguard reject 50, OI scope 78, opportunity_tier BLOCK 1443/1444, usmi NEUTRAL 1444/1444"
M6-2-outcomes,MEASURED,38478,97s,"symmetric vol-budget barrier K=1.5 on 22 book runs; resolvable 38478 (15 runs); window not elapsed 27604; no price 5460; agreement with p32 label_V 98.97%"
M6-3-gate-table,MEASURED,704,120s,"17 gates x 3 dirs pooled + per run; 23 pooled cells n>=100 both arms; removed>survivor with interval excluding 0: OI scope CALL, EIL prebook CALL/PUT, spread PUT; post-20260831 gates INSUFFICIENT_POWER"
M6-4-tc,MEASURED,22,90s,"GO inclusion |rho|<=0.16 all scores; non-BLOCKED vs priority_score 0.68 primary; rank vs priority 0.945 mechanical (lab_control.py:3033-3041)"
M6-5-ic-breadth,MEASURED,160,51s,"IC cells 160 (99 n>=100) |IC|<=0.09 CALL; PUT priority -0.32 n=171; N_eff 10.7-15.2 all populations>=179 rows, rho_bar 0.061-0.090"
```
