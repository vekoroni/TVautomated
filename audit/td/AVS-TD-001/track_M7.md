# Track M7 — What EV is made of (discovery, RESEARCH_ONLY)
No NORMAL_COMPLETED_SESSION run exists; every result below is on TEST-condition runs and cannot be CLOSED.
Runs used: `20260911_115904` (primary, TEST); `20260910_150045` (spread-unit check only).
Data sources: offline DOI assessments of run 20260911_115904 produced by Track C through the production DOI service (`probes/p12_C_offline_assessments_all_contracts.csv`, pass GARCH_SUB, 2,385 contracts / 200 families; family picks from `probes/p12_C_offline_assessments.csv`; OI and provider delta from `probes/_scratch_c6/control_plane_scratch_garch_sub.sqlite`, opened mode=ro); `intelligence_lab/final_opportunity_book_<run>.csv` for bid/ask/delta/OI (structure only). Forecast vol is Track C's tester substitution (`garch_forecast_vol` from the governed book); as wired, production reads no forecast column and values nothing (`p12_C_offline_sample.out.json` as_wired: 298/298 NOT_EVALUATED_DATA_MISSING). No historical outcome data is used. Everything here describes model arithmetic on one TEST-run snapshot. Nothing is a market edge, hit rate or realised EV (Rule 10). All values are RESEARCH_ONLY.

STATUS: COMPLETE. Probes: `p27_M7_decomposition.py` → `p27_M7_decomposition.csv`, `.out.json`, `p27_M7_crosstab.csv`; `p27_M7_reachability.py` → `p27_M7_reachability.csv`, `_ev.csv`, `_summary.csv`, `.out.json`; `p27_M7_friction.py` → `p27_M7_friction.csv`, `.out.json`. Runtime about 13 s + 12 s + 10 s.

Definitions used throughout:
- **EV_net** is `net_return_fraction` of the REACHABLE:LATE:BASE cell, the headline cell at `domain/contract_economics_v2.py:139`. `deterministic_utility_v2` is reported beside it.
- **Reproduction.** `evaluate_contract_economics_v2` was re-called with production wiring (`canonical_data/dynamic_options_valuation.py:369-395`). It reproduces all 1,093 APPLICABLE rows: state mismatch 0, max abs diff EV 8.9e-16, utility 4.4e-16.
- **OTHER.** The DOI path raises on non-CALL/PUT (`contract_economics_v2.py:74-75`), so every OTHER cell is n=0.

## Findings
| Finding ID | CALL | PUT | OTHER | data source | evidence (artefact, field, value) | N | magnitude |
|---|---|---|---|---|---|---|---|
| DISC-F-M7-1 forecast-over-IV share of EV | median vol_component/EV_net −0.012 (p25 −1.82, p75 0.26) | median 0.172 (p25 0.01, p75 0.30) | n=0 | offline DOI assessments (GARCH_SUB) | `p27_M7_decomposition.out.json` all_contracts.vol_share_of_ev | 731 / 362 / 0 | forecast > IV on 44.6% CALL, 74.9% PUT contracts; family picks 0.197 / 0.234 are INSUFFICIENT_POWER (n = 70 / 54) |
| DISC-F-M7-2 EV > 0 kept when the budget uses σ = σ_IV | 654 of 689 (94.9%); 5 not evaluable at σ_IV | 352 of 360 (97.8%) | n=0 | same | `.out.json` ev_pos, ev_pos_retained_at_sigma_iv | 689 / 360 / 0 | utility > 0 kept: 276/332 (83.1%) CALL, 138/193 (71.5%) PUT; EV ≥ 0.25 floor kept 399/407, 311/323 |
| DISC-F-M7-3 EV rank against abs(delta) and premium | Spearman EV vs abs(delta) −0.76; vs ask −0.61 | −0.62; −0.39 | n=0 | same | `p27_M7_crosstab.csv` | 731 / 362 / 0 | abs(delta) ≥ 0.60 median EV-rank pct 0.32 (CALL) / 0.24 (PUT); low-premium tercile top-quintile share 45.7% / 30.3% vs high tercile 0.4% / 12.4% |
| DISC-F-M7-4 EV sign, (1) pipeline → (3) double-barrier MC, structural barrier | thesis drift: 295 of 731 flip (40.4%); zero drift: 574 (78.5%) | thesis 270 of 362 (74.6%); zero 352 (97.2%); 66 families → INSUFFICIENT_POWER | n=0 | same + MC seed 20260912 | `p27_M7_reachability_summary.csv` sign_flips | contracts 731 / 362; families 101 / 66 | every flip is positive → non-positive; reachable-barrier variant: thesis 222 / 22, zero 674 / 353 |
| DISC-F-M7-5 p_target (3) against single-barrier (2) | structural barrier: median relative diff −19.0% (thesis), −32.1% (zero) | −2.0% / −2.8% (INSUFFICIENT_POWER, 66 families) | n=0 | same | `p27_M7_reachability_summary.csv` median_rel_diff_p3T_vs_p2 | 101 / 66 / 0 families | closed form vs single-barrier MC max abs diff ≤ 0.011 (correctness check) |
| DISC-F-M7-6 EV > 0 survivors under friction variants | configured 689; cap 0.15 with the 0.30 domain lifted 1,025; full half-spread 837 | 360; 551; 462 | n=0 | same | `.out.json` friction_survivors | 1,427 / 958 contracts | inside the domain (s ≤ 0.30) capped = full, identical; the cap binds only on rows the domain already excludes |
| DISC-F-M7-7 quoted spread by abs(delta) / OI | 11 Sep book median s 0.204; abs(delta) ≥ 0.60 0.351; OI 0 → 0.478, OI 100–999 → 0.143 | 0.157; abs(delta) 0.40–0.60 0.139; OI 10–99 0.159, OI 100–999 0.131 | n=0 quoted | 11 Sep book (structure) + offline sample | `p27_M7_friction.csv` | 772 / 446 / 0 | 40.2% CALL, 32.5% PUT quoted book rows have s > 0.30 |
| DISC-F-M7-8 fills / effective half-spread multiplier | unestimable, 0 fills | unestimable | unestimable | Track H ledger copy | `FILL_RECORDED` = 0 | 0 | 1.0 is the only supportable assumption (MEASURED) |

What each finding does NOT establish:
- **F-1** does not say the forecast is right or wrong, or that forecast-over-IV earns anything. It is the sensitivity of one scenario cell to the forecast, and the GARCH forecast is a tester substitution.
- **F-2** does not show that positive EV is robust. At σ = σ_IV the reachable target still assumes a 1.5σ move is reached.
- **F-3** is a cross-section on one snapshot. It does not show low-delta/low-premium contracts perform better, and the association is partly mechanical (return per unit premium).
- **F-4 / F-5** assume driftless or thesis-drift geometric BM at the forecast σ, no jumps, and LATE-cell payoffs applied at barrier time. They are not calibrated probabilities (ALG-09 is absent). PUT family cells are INSUFFICIENT_POWER, and contracts in one family share one probability triple.
- **F-6** does not measure realised friction; no fills exist.
- **F-7** is one intraday TEST snapshot; spreads at other times are unknown.
- **F-8** does not mean friction is 1.0× — only that nothing narrower is supportable.

TRACE lines:
- F-1: `TRACE: NONE | ALG-04 | WP-2 | STAGE-3 | TRACK-M7 | EVIDENCE-p27_M7_decomposition.out.json | N=1093`
- F-2: `TRACE: NONE | ALG-01, ALG-04 | WP-2 | STAGE-3 | TRACK-M7 | EVIDENCE-p27_M7_decomposition.out.json | N=1049`
- F-3: `TRACE: NONE | ALG-06 | WP-2 | STAGE-3 | TRACK-M7 | EVIDENCE-p27_M7_crosstab.csv | N=1093`
- F-4: `TRACE: NONE | ALG-02, ALG-04 | WP-2 | STAGE-3 | TRACK-M7 | EVIDENCE-p27_M7_reachability_summary.csv | N=1093`
- F-5: `TRACE: NONE | ALG-02 | WP-2 | STAGE-3 | TRACK-M7 | EVIDENCE-p27_M7_reachability.csv | N=167`
- F-6: `TRACE: NONE | ALG-04 | WP-2 | STAGE-3 | TRACK-M7 | EVIDENCE-p27_M7_decomposition.out.json | N=2385`
- F-7: `TRACE: NONE | ALG-12 | WP-1 | STAGE-2 | TRACK-M7 | EVIDENCE-p27_M7_friction.csv | N=3642`
- F-8: `TRACE: NONE | UNMAPPED | WP-7 | NONE | TRACK-M7 | EVIDENCE-track_H.md | N=0`

## Decomposition table (all APPLICABLE contracts; medians, p10–p90 in brackets; return fractions of the ask)
Component definitions:
- **vol_component**: central finite difference of EV_net with respect to σ_forecast through the vol budget, times (σ_forecast − σ_IV). ε = min(0.005, σ/2).
- **vol_exact**: EV(σ_f) − EV(σ_f := σ_IV).
- **pricing vega × gap**: the literal BS-vega formula (entry vega / ask × gap). It does not enter EV_net because the engine prices at IV.
- **drift_component**: BS entry delta × (reachable − S₀) / ask; thesis_drift × horizon is the reachable move.
- **friction_component**: −theo(REACHABLE, LATE, BASE) × min(s/2, 0.15) / ask.
- **residual**: EV_net − vol − drift − friction, which carries theta, gamma and the overlap between the vol and drift terms.

| dir | n | EV_net | utility_v2 | vol_component | vol_exact | pricing vega×gap | drift | friction | residual |
|---|---|---|---|---|---|---|---|---|---|
| CALL | 731 | 0.327 [0.035–1.495] | −0.038 [−0.421–0.656] | −0.051 [−0.458–0.410] | −0.048 | −0.007 | 0.501 [0.168–1.404] | −0.106 [−0.231 to −0.038] | 0.113 [−0.256–0.406] |
| PUT | 362 | 0.872 [0.228–1.936] | 0.039 [−0.471–0.990] | 0.150 [−0.101–0.664] | 0.150 | 0.069 | 0.839 [0.393–1.413] | −0.120 [−0.252 to −0.051] | 0.024 [−0.197–0.237] |
| OTHER | 0 | n=0 | | | | | | | |
| CALL family picks | 70 | INSUFFICIENT_POWER (1.345) | (0.494) | (0.239) | | (0.137) | (1.286) | (−0.162) | (0.009) |
| PUT family picks | 54 | INSUFFICIENT_POWER (1.486) | (0.489) | (0.366) | | (0.167) | (1.201) | (−0.145) | (0.081) |

Checks: finite-difference vs exact vol component, median abs diff 0.001 in both directions. 35 contracts have IV < 0.01 (flag `iv_below_fd_step`).

## Counterfactual table (vol budget re-priced with σ_forecast := σ_IV, production function)
| dir | EV>0 now | EV>0 at σ_IV | kept | EV≥0.25 now → kept | utility>0 now → kept | not evaluable at σ_IV |
|---|---|---|---|---|---|---|
| CALL | 689 | 654 | 94.9% | 407 → 399 | 332 → 276 (83.1%) | 5 (6 incl. EV ≤ 0) |
| PUT | 360 | 352 | 97.8% | 323 → 311 | 193 → 138 (71.5%) | 0 |
| OTHER | 0 | 0 | n=0 | | | |

## Cross-tab (EV rank percentile within direction) — `p27_M7_crosstab.csv`
| dir | cell | n | median EV-rank pct | median EV_net | top-quintile share |
|---|---|---|---|---|---|
| CALL | abs(delta) < 0.25 / 0.25–0.40 | 14 / 55 | INSUFFICIENT_POWER | | |
| CALL | abs(delta) 0.40–0.60 | 195 | 0.748 | 1.010 | 39.5% |
| CALL | abs(delta) ≥ 0.60 | 467 | 0.323 | 0.152 | 4.7% |
| CALL | premium T1 (ask 0.47–8.50) / T2 / T3 (23.60–227.40) | 245 / 243 / 243 | 0.773 / 0.464 / 0.313 | 1.075 / 0.263 / 0.148 | 45.7 / 14.0 / 0.4% |
| PUT | abs(delta) < 0.25 / 0.25–0.40 | 12 / 53 | INSUFFICIENT_POWER | | |
| PUT | abs(delta) 0.40–0.60 | 151 | 0.619 | 1.089 | 25.2% |
| PUT | abs(delta) ≥ 0.60 | 146 | 0.240 | 0.501 | 4.1% |
| PUT | premium T1 (0.08–3.30) / T2 / T3 (9.00–40.20) | 122 / 119 / 121 | 0.673 / 0.459 / 0.334 | 1.206 / 0.809 / 0.627 | 30.3 / 17.6 / 12.4% |
| OTHER | — | 0 | n=0 | | |

Joint abs(delta) × premium cells are in the CSV; most are n < 100 (INSUFFICIENT_POWER).

## Reachability comparison table — `p27_M7_reachability_summary.csv`
Setup:
- **Estimator (1)**: the pipeline's `reach_ratio` and reachable target. It is not a probability; the headline EV implicitly treats the reachable target as reached at LATE (p = 1).
- **Estimator (2)**: closed-form single-barrier first passage.
- **Estimator (3)**: double-barrier daily-step MC with a Brownian-bridge crossing correction. 20,000 paths per row per variant, seed 20260912, max abs(p_T + p_I + p_O − 1) = 1.1e-16.
- **Model parameters**: σ = row forecast; T = hold/252. Zero drift is log-drift 0; thesis drift ν = ln(R/S₀)/T.
- **Same-step double touch**: when both barriers are touched inside one step, the order is drawn 50/50. This happened on 471,839 path-steps across the double runs (about 3.5% of 13.36 M paths).
- **Families**: 167 of 200 have structural target, invalidation and forecast (CALL 101 / PUT 66).

| barrier | drift | dir | families | median reach_ratio (1) | median p (2) | median p_T (3) | median p_I (3) | median p_O (3) | median rel diff (3) vs (2) | EV>0 (1) → EV>0 (3) | sign flips (contracts) | flips on family picks |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| STRUCTURAL | THESIS | CALL | 101 | 1.31 | 0.699 | 0.491 | 0.251 | 0.151 | −19.0% | 689 → 394 | 295 / 731 | 13 / 70 (INSUFFICIENT_POWER) |
| STRUCTURAL | ZERO | CALL | 101 | 1.31 | 0.227 | 0.185 | 0.582 | 0.192 | −32.1% | 689 → 115 | 574 / 731 | 45 / 70 (IP) |
| STRUCTURAL | THESIS | PUT | 66 IP | 3.12 | 0.020 | 0.019 | 0.025 | 0.948 | −2.0% | 360 → 90 | 270 / 362 | 39 / 54 (IP) |
| STRUCTURAL | ZERO | PUT | 66 IP | 3.12 | 0.0001 | 0.0002 | 0.291 | 0.701 | −2.8% | 360 → 8 | 352 / 362 | 51 / 54 (IP) |
| REACHABLE | THESIS | CALL | 101 | — | 0.628 | 0.561 | 0.251 | 0.189 | −10.7% | 689 → 467 | 222 / 731 | 13 / 70 (IP) |
| REACHABLE | ZERO | CALL | 101 | — | 0.158 | 0.141 | 0.639 | 0.222 | −11.6% | 689 → 15 | 674 / 731 | 67 / 70 (IP) |
| REACHABLE | THESIS | PUT | 66 IP | — | 0.613 | 0.610 | 0.024 | 0.364 | −0.5% | 360 → 338 | 22 / 362 | 0 / 54 (IP) |
| REACHABLE | ZERO | PUT | 66 IP | — | 0.103 | 0.102 | 0.289 | 0.615 | −0.2% | 360 → 7 | 353 / 362 | 51 / 54 (IP) |
| any | any | OTHER | 0 | n=0 | | | | | | | | |

Zero-drift minus thesis-drift gap, structural barrier: CALL median p_T 0.185 vs 0.491; PUT 0.0002 vs 0.019. EV>0 contracts: CALL 115 vs 394, PUT 8 vs 90.

## Friction table (quoted spread s = (ask − bid)/mid, from bid/ask) — `p27_M7_friction.py` → `p27_M7_friction.csv`
Units resolved by this track, since B3 did not fully resolve them:
- 11 Sep book bare `spread_pct` = 100·s on 1,218/1,218 quoted rows (PERCENT).
- 10 Sep book `spread_pct` = s on 1,241/1,241 (FRACTION).
- Every number below is recomputed from bid/ask, not read from `spread_pct`.
- bid = 0 with ask > 0 gives s = 2.0 and is kept.

| source | dir | cell | n | median s | share s > 0.30 | note |
|---|---|---|---|---|---|---|
| BOOK_11SEP | CALL | all quoted | 772 | 0.204 | 40.2% | 37 book rows bid = 0, both directions |
| BOOK_11SEP | CALL | abs(delta) 0.40–0.60 / ≥ 0.60 | 545 / 161 | 0.162 / 0.351 | 31.0 / 57.1% | abs(delta) < 0.25, 0.25–0.40: n = 6 / 60 INSUFFICIENT_POWER |
| BOOK_11SEP | CALL | OI 0 / 1–9 / 10–99 / 100–999 | 125 / 144 / 264 / 189 | 0.478 / 0.372 / 0.202 / 0.143 | 62.4 / 53.5 / 40.5 / 21.2% | OI ≥ 1000 n=50 INSUFFICIENT_POWER |
| BOOK_11SEP | PUT | all quoted | 446 | 0.157 | 32.5% | |
| BOOK_11SEP | PUT | abs(delta) 0.40–0.60 | 342 | 0.139 | 25.4% | other bands n = 2 / 36 / 66 INSUFFICIENT_POWER |
| BOOK_11SEP | PUT | OI 10–99 / 100–999 | 155 / 125 | 0.159 / 0.131 | 29.7 / 18.4% | OI 0, 1–9, ≥1000: n = 51 / 81 / 34 INSUFFICIENT_POWER |
| BOOK_11SEP | OTHER | — | 0 | n=0 (188 OTHER rows carry no contract quote) | | |
| OFFLINE_SAMPLE | CALL | all quoted | 1,424 | 0.205 | 38.2% | family candidate sets, wider strike range than book |
| OFFLINE_SAMPLE | CALL | abs(delta) < 0.25 / 0.25–0.40 / 0.40–0.60 / ≥ 0.60 | 305 / 135 / 312 / 672 | 2.000 / 0.301 / 0.167 / 0.137 | 95.4 / 50.4 / 29.2 / 14.0% | 76% of < 0.25 rows bid = 0 |
| OFFLINE_SAMPLE | CALL | OI 0 / 1–9 / 10–99 / 100–999 | 550 / 289 / 303 / 235 | 0.186 / 0.248 / 0.235 / 0.194 | 31.6 / 44.3 / 44.9 / 37.0% | OI ≥ 1000 n=47 INSUFFICIENT_POWER |
| OFFLINE_SAMPLE | PUT | all quoted | 950 | 0.347 | 52.5% | |
| OFFLINE_SAMPLE | PUT | abs(delta) < 0.25 / 0.25–0.40 / 0.40–0.60 / ≥ 0.60 | 400 / 100 / 226 / 224 | 2.000 / 0.201 / 0.123 / 0.170 | 96.8 / 33.0 / 17.7 / 17.4% | |
| OFFLINE_SAMPLE | PUT | OI 0 / 1–9 / 10–99 / 100–999 | 315 / 163 / 259 / 168 | 2.000 / 0.375 / 0.270 / 0.135 | 71.4 / 56.4 / 45.9 / 29.8% | OI ≥ 1000 n=45 INSUFFICIENT_POWER |
| OFFLINE_SAMPLE | OTHER | — | 0 | n=0 | | |

Fills: 0 `FILL_RECORDED` (Track H). The effective half-spread multiplier is unestimable; 1.0 is the only supportable assumption — MEASURED.

Surviving-row count (EV_net > 0) under each friction variant:

| dir | contracts | configured (cap 0.15, domain 0.30) | cap 0.15, domain lifted | full half-spread (multiplier 1.0, no cap) | rows with s > 0.30: EV>0 capped → full | utility>0: configured / capped-lifted / full |
|---|---|---|---|---|---|---|
| CALL | 1,427 | 689 (731 applicable; 476 FRICTION_OUT_OF_RANGE) | 1,025 (of 1,207) | 837 | 336 → 148 (of 544) | 332 / 405 / 369 |
| PUT | 958 | 360 (362; 420 out of range) | 551 (of 782) | 462 | 191 → 102 (of 499) | 193 / 232 / 212 |
| OTHER | 0 | n=0 | | | | |

## Deviations (observations, no severity)
- **Headline EV is not a probability-weighted value.** The Annex (ALG-04) presents REACHABLE:LATE:BASE as a scenario boundary. The monetisability policy (`contract_economics_v2.py:139-147`) treats it as the value to compare with the floor. Under (3) at thesis drift, 40.4% of CALL and 74.6% of PUT positive rows turn non-positive (structural barrier).
- **The forecast does not enter option pricing.** It enters only the reachable, 1σ and 2σ spots (`dynamic_options_valuation.py:369-390`); contracts are priced at IV × stress. The §4.7 formula "vega × (σ_forecast − σ_IV)" therefore measures a channel absent from EV_net (literal-formula median −0.007 CALL / 0.069 PUT). The budget-channel equivalent is the one reported as vol_component.
- **The drift term is not independent of the vol term.** The reachable move is k·σ_forecast·√(h/252), so the specified drift term (thesis drift = reachable move) contains the forecast. Components overlap, and the residual absorbs the overlap plus theta/gamma.
- **As wired, no forecast reaches the DOI path.** Every number here depends on Track C's GARCH substitution (`p12_C_offline_sample.py` pass GARCH_SUB).
- **Cap and domain.** The friction cap 0.15 never binds inside the 0.30 model domain (s/2 ≤ 0.15 there). Capped and full half-spread are identical on all 1,093 applicable rows. The domain, not the cap, removes 896 contracts, 527 of which are EV-positive under capped arithmetic.
- **σ_IV counterfactual not evaluable on 6 contracts.** Five were EV-positive and 1 was not; this is the "5 not evaluable" in the counterfactual table.
- **Near-zero IV.** 35 applicable contracts have IV < 0.01 (provider IV near zero) and are still valued.
- **Spread units.** The bare `spread_pct` unit flips between the 11 Sep (percent) and 10 Sep (fraction) books, confirming Track B.

## Premise notes (spec / measured / gap; no recommendation)
- **Spec**: DOI EV is designed to reward forecasting more vol than is priced. **Measured**: median forecast-over-IV share of EV_net is −0.01 (CALL) and 0.17 (PUT); 95–98% of positive rows stay positive with σ_forecast := σ_IV. **Gap**: the forecast gap explains at most about one-sixth of EV, against the pre-registered > 60%. What carries EV is delta × a 1.5σ move assumed to occur (drift_component median 0.50 CALL / 0.84 PUT vs EV 0.33 / 0.87).
- **Spec**: the reachable target is a scenario boundary. **Measured**: at zero drift, EV>0 after probability weighting falls from 689 to 115 (CALL) and 360 to 8 (PUT) on the structural barrier, and to 15 / 7 on the reachable barrier. **Gap**: the sign of EV is set by the thesis-drift assumption, not by volatility.
- **Spec**: the ranking favours the strongest expression. **Measured**: EV rank falls with abs(delta) (ρ −0.76 CALL / −0.62 PUT) and premium (ρ −0.61 / −0.39). abs(delta) ≥ 0.60 contracts hold 4–5% of the top quintile. **Gap**: rank tracks leverage per unit premium.
- **Spec**: friction is a capped current-spread proxy. **Measured**: the cap is inert inside the domain. Outside it (s > 0.30, 40% CALL / 33% PUT of quoted book rows), full half-spread removes 56% (CALL) and 47% (PUT) of the capped-positive rows.

## Not tested / limits
- PUT family-level reachability cells are INSUFFICIENT_POWER (66 families).
- Contract-level reachability counts are clustered: one probability triple per family.
- Monte Carlo uses the LATE-cell payoff at barrier time, not the payoff at the hit instant.
- Uncertainty in the MC probabilities (standard error ≤ 0.0035 at 20,000 paths) is not propagated.
- Realised spread and fill slippage: DATA_UNAVAILABLE (no fills; would need `FILL_RECORDED` events with a decision-time mid).
- Nothing outcome-linked was measured (Rule 10).

## Expectation vs actual (expectations.md M7 row)
| item | E | A | gap |
|---|---|---|---|
| vol_component / EV_net median | > 0.6 | CALL −0.012, PUT 0.172 | far below E, both directions |
| EV>0 kept at σ = σ_IV | < 40% | CALL 94.9%, PUT 97.8% | far above E |
| p_T (3) below single-barrier (2) | 15–35% lower | structural: CALL −19% (thesis) / −32% (zero); PUT −2 / −3% (INSUFFICIENT_POWER) | CALL inside E; PUT far below E (target rarely reached; invalidation rarely competes) |
| EV sign flips (1)→(3) | 20–40% | structural thesis CALL 40.4%, PUT 74.6%; zero drift 78.5% / 97.2%; reachable thesis 30.4% / 6.1% | CALL at E's upper edge; PUT and zero drift well above |
| half-spread multiplier | unestimable, 1.0 | unestimable, 1.0 (0 fills) | none |

## State log lines
```
step,state,n,duration,note
M7-friction,MEASURED,3642,~10s,s from bid/ask; 11Sep book spread_pct=100*s (1218/1218), 10Sep=s (1241/1241); 0 fills -> multiplier unestimable, 1.0
M7-decomposition,MEASURED,1093,~13s,production fn reproduces 1093/1093 (max diff 8.9e-16); vol/EV median CALL -0.012 PUT 0.172; OTHER n=0
M7-counterfactual-sigmaIV,MEASURED,1049,~13s,EV>0 kept CALL 654/689 PUT 352/360; utility>0 kept 276/332, 138/193
M7-crosstab,MEASURED,1093,~1s,Spearman EV vs abs(delta) CALL -0.76 PUT -0.62; vs ask -0.61 / -0.39; delta<0.40 cells INSUFFICIENT_POWER
M7-reachability,PARTIAL,167,~12s,167/200 families with target+invalidation+forecast; MC 20000 paths seed 20260912; PUT families 66 INSUFFICIENT_POWER; structural thesis flips CALL 295/731 PUT 270/362
M7-friction-survivors,MEASURED,2385,~13s,EV>0 configured 689/360; cap-domain lifted 1025/551; full half-spread 837/462; cap inert inside domain
```
