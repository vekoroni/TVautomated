# AVS-TD-001 — Premise notes (§4A)

**Largest premise note by magnitude: PN-01.** ALG-04 specifies the headline REACHABLE:LATE:BASE EV as a scenario boundary. M7 measured that with zero drift, EV stays positive under probability weighting on only 22 of 1,049 EV-positive contracts on the reachable barrier (123 on the structural barrier). The sign of EV is therefore set by the thesis-drift assumption on 97.9% of positive rows (88.3% structural).

A premise note records where a document is internally consistent but measurement suggests it solves for a different quantity. Premise notes are not defects. They carry no severity and no recommendation. All run data is TEST condition; see each note for its data and caveats. RESEARCH_ONLY.

**Magnitude rule.** The gap is expressed as a share of the measured rows on which the specified and measured quantities diverge (percent of n), or as a percentage-point difference between two rates. Ties are broken by n.
- **Largest first** holds notes with such a gap measured on n ≥ 100 units, sorted descending.
- **Remainder** holds, in order: (a) the same kind of gap on n < 100 units; (b) gaps fixed by construction or by absent data (empty tables, unreachable values, missing preconditions); (c) gaps stated as a multiple; (d) gaps in return, ratio, coefficient or correlation units, or not quantified.

Under a plain share-of-rows rule with no split into (b), PN-22 (100% of 4,931) would rank first.

**Merges.** Two pairs of notes had the same spec clause and the same measurement from two tracks, so each pair became one note: PN-29 (Track E gate stratum population with M8 E6 strata) and PN-34 (Track A evidence-cutoff scalar with Track D D5 refresh vs cutoff).

## Index

| PN | source | spec reference | magnitude (comparable) | n |
|---|---|---|---|---|
| PN-01 | M7 | ALG-04 headline EV cell | 97.9% of positive rows reverse sign at zero drift | 1,049 contracts |
| PN-02 | M7 | DOI EV design (forecast over IV) | 95.9% of positive rows keep sign without the forecast gap | 1,049 |
| PN-03 | N | NFR-05 | 92.8% of pairs get a new id without a new observation | 973 pairs |
| PN-04 | M3 | §4.3 directional quantity | 85.6% of side-correct theses miss the thesis amount | 3,071 |
| PN-05 | D | D4 activity vs executability | 75.9% of selected contracts activity-thin | 1,218 |
| PN-06 | M3 | structural target (PUT) | 65.7% beyond 1.5σ_h | 300 |
| PN-07 | F | REQ-WP5-01 routing coverage | 60.9% of rows without a route | 1,444 |
| PN-08 | M7 | friction proxy | 52.6% of capped-positive out-of-domain rows removed | 527 |
| PN-09 | C | v2 re-rank | 50.3% of families ρ < 0.7 | 153 families |
| PN-10 | M4 | Engine A structural pricing | 46.4% of theses change argmax | 235 |
| PN-11 | C | monetisability drivers | 37.6% of contracts decided by friction domain | 2,385 |
| PN-12 | A | REQ-WP0-08 | 16% of nodes | 177 modules |
| PN-13 | M5 | §4.6 waiting inequality | 14 pp | 378 pairs |
| PN-14 | B | REQ-WP1-03 | 11% of values | 2,027 values in (1,2] |
| PN-15 | M1 | ALG-14 route grain | 6.3% of observations unmappable (21% four-label) | 332 |
| PN-16 | A | ALG-12 | 100% past F at manifest | 69 |
| PN-17 | A | ALG-15 | 100 pp | 2 runs |
| PN-18 | M8 | §4.10 outcome | 70.8% of survivors side_correct | 48 |
| PN-19 | E | ALG-08 labels | 66.7% of rows no structural label | 30 |
| PN-20 | F | structure vs GO | 42.1% of GO rows | 19 |
| PN-21 | M8 | §4.10 conditions | 31 pp between-session range | 13 sessions |
| PN-22 | H | REQ-WP7-02 | 100% of population | 4,931 events |
| PN-23 | B | ALG-01 oracle | 100% of rows constant | 2,868 |
| PN-24 | C | e_h forecast input | 100% of offline numbers conditional | 2,385 |
| PN-25 | D | D6 hysteresis | 100% of switches without incumbent | 79 |
| PN-26 | F | scenario timing | 100% of scenarios | 3 |
| PN-27 | I | TST-04 | 100% of runs | 2 runs |
| PN-28 | G | REQ-WP6-04 | 100% of cycles missing | 0 of 2 |
| PN-29 | E + M8 | ≥100 per direction × hold | 94% short (PUT 11–20) | 6–7 |
| PN-30 | F | alignment values | 40% of values unreachable | 5 |
| PN-31 | H | attribution vocabulary | 28.6% of categories unreachable | 7 |
| PN-32 | G | REQ-WP6-02 | 160× (480 → 3) | 480 combinations |
| PN-33 | E | 70/15/15 split | 6.1× (26.8× on ledger) | 22 run books / 5 sessions |
| PN-34 | A + D | REQ-WP0-01 evidence cutoff | 1,220× | 1,220 cutoffs |
| PN-35 | M6 | breadth | ~106× | 1,444 rows |
| PN-36 | M8 | Rule 12 floor | 20.5× | 6 strata |
| PN-37 | M4 | convexity_score | 12× | CALL h5 cells |
| PN-38 | M5 | early-lane median | ~10× | 148–693 |
| PN-39 | M3 | invalidation distance | 4.8× | 2,626 |
| PN-40 | M3 | ALG-08 thesis amount | 3.4× | 8,417 |
| PN-41 | M5 | waiting cost framing | ~3.3× | 769 |
| PN-42 | M4 | legacy delta band | 1.14× (0.879) | 146 |
| PN-43 | C | ALG-05/06 scenario switch | 138.6 pp net return (PUT) | 1,093 |
| PN-44 | M3 | profit floor 0.25 | +42% to +92% recovery | 1,250 |
| PN-45 | C | European valuation | ≤ 10.35 pp | real PUT |
| PN-46 | M2 | M2(c) question | b_F −60% | 2,389–4,848 |
| PN-47 | M2 | "20–40% above IV" | 8–25% measured | 1,893–14,279 |
| PN-48 | M2 | ALG-01 √-time | 15% relative | 17,275 / 5,172 |
| PN-49 | M1 | sector bridge | ratio 0.86 | 670 sessions |
| PN-50 | M2 | ALG-10 multiplier | 0.08 below band floor | 4,891 |
| PN-51 | M7 | ranking | ρ −0.76 | 1,093 |
| PN-52 | M6 | TC target | ρ 0.68 vs ≤ 0.13 | 1,444 |
| PN-53 | M1 | ALG-14 RS states | autocorr ≈ 0 | 675 sessions |
| PN-54 | M6 | ALG-08 barrier | σ SMD −1.41 to +0.55 | 20,000+ |
| PN-55 | M4 | breakeven/σ_h | not separated | 570 |
| PN-56 | M5 | delta_p resolution | within ~3.8 SE | ~400 per cell |
| PN-57 | G | REQ-WP6-03 | not measurable on markdown | 19 |

---

## Largest first — measured divergence, share of rows (n ≥ 100)

**PN-01** · M7 · 97.9% of EV-positive contracts (reachable barrier); 88.3% (structural) · n = 1,049 contracts (PUT 66 families `INSUFFICIENT_POWER` at family level)
> ALG-04 (`contract_economics_v2.py:139`) specifies the REACHABLE:LATE:BASE EV as a scenario boundary. M7 measured the sign of that EV after probability weighting with a double-barrier Monte Carlo at zero drift. On the structural barrier, EV > 0 falls from 689 to 115 (CALL) and from 360 to 8 (PUT); on the reachable barrier to 15 and 7. Offline DOI assessments of one TEST snapshot with the forecast as a tester substitution. Gap: the sign of EV is set by the thesis-drift assumption rather than by volatility on 1,027 of 1,049 positive rows. Recorded for ACK, no recommendation.

**PN-02** · M7 · 95.9% of EV-positive rows keep sign with σ_forecast := σ_IV · n = 1,049
> The DOI EV design specifies rewarding a forecast of more vol than is priced. M7 measured the median forecast-over-IV share of EV_net at −0.01 (CALL, n=731) and 0.17 (PUT, n=362). EV-positive rows stay positive with σ_forecast := σ_IV on 94.9% (CALL) and 97.8% (PUT). Same offline snapshot. Gap: the forecast gap explains at most about one-sixth of EV_net; what carries EV is delta times an assumed 1.5σ move (drift_component median 0.50 / 0.84 against EV 0.33 / 0.87). Recorded for ACK, no recommendation.

**PN-03** · Track N · 92.8% of same-thesis cross-run pairs · n = 973
> NFR-05 specifies "a new OCC symbol or new quote observation produces a new `assessment_id`". Track N measured the stored identity key as (thesis, run, symbol, quote_as_of): an unchanged provider quote carried into a later run gets a new id and different greeks on 903 of 973 same-thesis cross-run pairs. Gap: "new observation" is operationally "new run" on 92.8% of pairs. Recorded for ACK, no recommendation.

**PN-04** · M3 · 85.6% of UNGOVERNED CALL side-correct theses (≈ 40 pp between definitions) · n = 3,071
> §4.3 specifies the directional quantity as "did the underlying move the thesis way, by the thesis amount, within the hold". M3 measured terminal side against thesis-amount-first on p32 labels (TEST books, presented-not-taken): the definitions diverge on 2,628 of 3,071 UNGOVERNED CALL side-correct theses. Gap: a 45–55% side-correct rate coexists with a 3–7% thesis-amount rate. Recorded for ACK, no recommendation.

**PN-05** · Track D · 75.9% of selected contracts · n = 1,218
> The DOI spec treats OI and volume as activity-only. Track D (D4) measured 924 of 1,218 selected contracts as thin (OI < 100 or volume = 0), 288 of them `EXECUTABLE_NOW` on spread and quote; at candidate level 74.6% are low-OI and 81.5% zero-volume. Gap: the activity machine would label about three-quarters of rows `ACTIVITY_THIN`. Recorded for ACK, no recommendation.

**PN-06** · M3 · 65.7% · n = 300 (UNGOVERNED PUT side-correct theses with a valid contract)
> The structural target is specified as the thesis target. M3 measured the structural target lying more than 1.5σ_h away on 65.7% of these theses; structural TARGET_FIRST_S for PUT 6–10 is 1.4% (n=1,180). Gap: two-thirds of these PUT targets sit beyond 1.5σ_h. Recorded for ACK, no recommendation.

**PN-07** · Track F · 60.9% of book rows · n = 1,444
> REQ-WP5-01 specifies SECTOR_UNMAPPED ≤ tickers lacking GICS. Track F measured that with a perfect `map_routing` join the stored packet still has no route for CALL 486/798, PUT 205/458 and OTHER 188/188. Gap: the coverage metric can be met at 0 SECTOR_UNMAPPED while 879 of 1,444 rows carry no route. Recorded for ACK, no recommendation.

**PN-08** · M7 · 52.6% of capped-positive rows outside the friction domain · n = 527
> The friction spec is a capped current-spread proxy (cap 0.15 within a 0.30 domain). M7 measured the cap inert inside the domain (capped = full on 1,093/1,093). Outside it (s > 0.30; 40% of CALL and 33% of PUT quoted book rows), full half-spread removes 188 of 336 CALL and 89 of 191 PUT capped-positive rows. Gap: the cap binds nowhere, and full half-spread removes about half of the rows the domain excludes. Recorded for ACK, no recommendation.

**PN-09** · Track C · 50.3% of families · n = 153 families
> The v2 utility spec anticipates re-ranking relative to v1 (ρ < 0.7). Track C measured within-family median ρ 0.679, 50.3% of families below 0.7, same top contract in 103 of 159; across contracts ρ is 0.147. Gap: most cross-contract decorrelation is between-family scale; within-family ordering changes for about half of families. Recorded for ACK, no recommendation.

**PN-10** · M4 · 46.4% of theses change payoff-maximising cell (level −32% at median) · n = 235 (PUT n=81 `INSUFFICIENT_POWER`)
> Engine A (`contracts/selected_contract_economics.py`) specifies pricing at the structural target. M4 measured structural payoff_per_dollar at a median 0.68× the reachable-target payoff (CALL 0.563×, n=154) on historical chains; the argmax cell differs on 46.4% of theses (structural leans to D060_085, reachable to D010_025). Gap: ranking differs on 46.4% of theses and level by 32% at the median. Recorded for ACK, no recommendation.

**PN-11** · Track C · 37.6% of valued contracts · n = 2,385
> The monetisability spec has reachability and the profit floor drive the state. Track C measured 896 of 2,385 valued contracts INDETERMINATE at the 0.30 friction-domain limit before any payoff is computed; 730 of 1,093 contracts with a grid are SCENARIO_MONETISABLE at floor 0.25, and 25 of 26 legacy state changes come via friction. Gap: at floor 0.25 the spread domain, not reachability, decides the state. Recorded for ACK, no recommendation.

**PN-12** · Track A · 16% of nodes · n = 177 modules
> REQ-WP0-08 specifies enumerating the production import graph. Track A measured two static walkers on the same entry points giving 152 vs 177 modules. Gap: 25 modules depend on the walker's resolver. Recorded for ACK, no recommendation.

**PN-13** · M5 · 14 pp (6–14 pp) · n = 378 pairs (d1 CALL); d2 PUT `INSUFFICIENT_POWER (n=41)`
> §4.6 specifies waiting is paid for iff delta_p·payoff(t+d) > −delta_premium_total + friction. M5 measured that delta_premium_total is negative when premium falls, so as written a cheaper later entry raises the bar for waiting. The satisfied share differs by 6–14 pp between the as-written and reversed sign on the same pairs (12.0% vs 18.0% d1 CALL; 9.0% vs 24.0% d1 PUT, n=128; 17.0% vs 24.5% d2 CALL, n=108). Pairs carry book-to-book contamination; not reported as a result. Gap: up to 14 pp between sign conventions. Recorded for ACK, no recommendation.

**PN-14** · Track B · 11% of `contract_spread_pct` values (2.9% of `spread_pct`) · n = 2,027 and 369 values
> REQ-WP1-03 specifies `spread_fraction_mid` in [0, 2] as the validator band. Track B measured 369 primary `spread_pct` values and 2,027 `contract_spread_pct` values in (1, 2], where fraction and percent overlap. Gap: on 2.9% and 11% of values a range check cannot distinguish fraction from percent. Recorded for ACK, no recommendation.

**PN-15** · M1 · 6.3% of distinct label observations unmappable (21% of four-label) · n = 332 (four-label n=19 `INSUFFICIENT_POWER`)
> §4.1 and ALG-14 express the route at sector grain. M1 measured packet routes at theme grain: 21 of 332 distinct observations (4 of 19 four-label: IWM_SMALL_CAPS_PUT, SPY_QQQ_PUT, BROAD_INDEX_CALL) map to no GICS sector, and routes such as AIRLINES_PUT or DEFENCE_CALL are proxied by whole-sector composites. Gap: the measured quantity (GICS sector return) is broader than the labelled quantity (theme return) for every mapped non-whole-sector route. Recorded for ACK, no recommendation.

## Remainder

### (a) Measured divergence on n < 100 units

**PN-16** · Track A · 100% past F at manifest (78% at book write) · n = 69
> ALG-12 specifies age = refresh_instant − provider ts with F = 15 min. Track A measured gate ages of 3.2–6.9 min; at the Lab book write 54 of 69 EXECUTABLE_NOW rows are past F; at the manifest EXECUTION_READY, 69 of 69. Gap: 4 min gate→book, 94 min gate→manifest; the spec has no age-at-publication or expiry quantity. Recorded for ACK, no recommendation.

**PN-17** · Track A · 100 pp · n = 2 runs
> ALG-15 prohibits "latest timestamp ≥ 16:00 ET" as session completion. Track A measured the naive rule scoring 0.54 and 1.00 on runs whose true session-date close coverage is 0.0; stored registry labels still use the naive notion. Recorded for ACK, no recommendation.

**PN-18** · M8 · 70.8% of surviving tests · n = 48 survivors (8,413 theses)
> §4.10 specifies outcome as P(TARGET_FIRST) and P(side_correct). M8 measured 34 of 48 survivors on side_correct, concentrated in sector, with opposite CALL/PUT signs for compression. Gap: on overlapping windows of one market path, side_correct mostly measures sector and market drift; surviving TARGET_FIRST differences are 2–14 points. Recorded for ACK, no recommendation.

**PN-19** · Track E · 66.7% of sampled rows · n = 30 (E1 sample)
> ALG-08 specifies labels against the vol-budget target; production labels against the structural target. Track E measured the structural target unusable on 20 of 30 sampled rows (CALL 13/15, PUT 7/15); where both exist the labels agree on 9 of 10. Recorded for ACK, no recommendation.

**PN-20** · Track F · 42.1% of GO_LIMIT rows · n = 19
> The spec treats structure evidence as context only. Track F measured 8 of 19 GO_LIMIT rows deriving NO_EDGE (LOW_ENERGY); OPPOSED is unreachable with the stored trigger vocabulary. Recorded for ACK, no recommendation.

**PN-21** · M8 · 31 pp between-session range (CALL 6–10 side_correct 0.34–0.65) · n = 13 sessions
> §4.10 specifies finding where outcomes differ from the stratum base rate. M8 measured between-session base-rate variation exceeding most within-session conditional differences; every regime label is session-constant. Gap: with 13 decision sessions and 4 regime labels, a session-level condition has ≤ 5 sessions per level; the thesis count is not the binding sample. Recorded for ACK, no recommendation.

### (b) Gap fixed by construction or by absent data

**PN-22** · Track H · 100% of population · n = 4,931 candidate events
> REQ-WP7-02 specifies option MFE/MAE "where canonical observations exist" and DOI labels joined by `preferred_assessment_id`. Track H measured `doi_contract_assessments` and `doi_outcome_labels` at 0 rows and `preferred_assessment_id` absent from all 4,931 candidate payloads. Gap: every outcome would be UNDERLYING_ONLY and TARGET_FIRST attribution UNCLASSIFIED_UNCERTAINTY. Recorded for ACK, no recommendation.

**PN-23** · Track B · 100% of rows · n = 2,868
> The ALG-01 oracle specifies `10d/5d ∈ [1.407, 1.421]` on every row. Track B measured that one annualised forecast scaled by √(h/252) makes the ratio identically 1.41421 regardless of the forecast. Gap: the oracle distinguishes cumulative from differenced fields, not a correct forecast from a wrong one. Recorded for ACK, no recommendation.

**PN-24** · Track C · 100% of offline economics numbers · n = 2,385 contracts
> The spec takes e_h from the governed forecast vol. Track C measured that the production DOI input carries none; every offline economics number uses the tester substitution `garch_forecast_vol`, which is unvalidated (see PN-47). Gap: all reachable-payoff sizes are conditional on a substituted input. Recorded for ACK, no recommendation.

**PN-25** · Track D · 100% of switches · n = 79
> D6 specifies hysteresis on utility margin. Track D measured a 6.6% day-over-day contract change rate: 40 of 79 changes are a single strike increment, 22 expiry-only, and the EOD selector recorded no incumbent on 10 Sep. Gap: 79 switches with no utility comparison. Recorded for ACK, no recommendation.

**PN-26** · Track F · 100% of scenarios · n = 3
> The spec evaluates USMI scenarios at the Morning Gate. Track F measured that all 3 scenarios need `cpi_core_mom_pct`; the packet is pre-CPI (CPI 12:30Z, cutoff 11:59Z) and all 20 USMI metrics are `UNVERIFIED_SOURCE`. Gap: 3 of 3 scenarios resolve UNRESOLVED at this evaluation point by construction. Recorded for ACK, no recommendation.

**PN-27** · Track I · 100% of stored runs · n = 2 runs
> TST-04 specifies building the replay harness on the stored test runs until two normal runs exist. Track I measured both runs as produced by 00baa2b, before every remediation commit. Gap: a replay at cc509cb can show only the full remediation delta, not per-change declared differences. Recorded for ACK, no recommendation.

**PN-28** · Track G · 100% of required normal cycles missing · n = 0 of 2
> REQ-WP6-04 specifies parity "until two stored runs and two normal cycles". Track G measured one stored run with overlay outputs and zero normal cycles; the precondition cannot be met before a NORMAL_COMPLETED_SESSION run. Recorded for ACK, no recommendation.

**PN-29** · Track E + M8 · 94% short on PUT 11–20 (CALL 11–20 49–65% short) · n = 6–7 (PUT), 35–51 (CALL)
> The calibration gate (ALG-09) specifies ≥ 100 fit outcomes per direction × hold stratum. Track E measured census full-window rows CALL 11–20 51, PUT 11–20 7, PUT 1–5 361 before any baseline filter (0 eligible; all runs TEST); M8 measured unique labelled theses 35 and 6 in the 11–20 strata, with 86% in 6–10. Gap: 2 of 6 strata unusable at any split. Recorded for ACK, no recommendation.

**PN-30** · Track F · 40% of output values unreachable · n = 5 values
> The alignment spec defines five values, SUPPORTIVE/OPPOSED set by direction against the route's preferred side. Track F measured route keys that already encode the side (…_CALL / …_PUT) and carry 4 priority/watch labels; OPPOSED arises on 0 rows offline and stored. Recorded for ACK, no recommendation.

**PN-31** · Track H · 28.6% of categories unreachable · n = 7 categories
> The `attribute_outcome` vocabulary lists EXECUTION and VOLATILITY. Track H measured no code path assigning either (`domain/outcome_learning.py:140-154`). Recorded for ACK, no recommendation.

**PN-32** · Track G · 160× (480 combinations → 3 outcomes) · n = 480
> REQ-WP6-02 specifies an exhaustive state-combination test over (thesis, contract, execution, macro). Track G measured `summary_state` depending on 2 inputs only; monetisability and macro never change it. Gap: a passing exhaustive test would not distinguish a projector that ignores contract and macro. Recorded for ACK, no recommendation.

**PN-33** · Track E · 6.1× (134 sessions required vs 22 run books; 26.8× vs 5 ledger sessions)
> The calibration spec specifies a 70/15/15 date split with a 20-session embargo. Track E measured that validation and test are non-empty only when N ≥ 134 decision sessions; the ledger spans 5 and the run books 22. Gap: ≥ 112 further sessions before a partition can be READY. Recorded for ACK, no recommendation.

### (c) Gap stated as a multiple

**PN-34** · Track A + Track D · 1,220 distinct cutoffs vs 1 recorded; evidence acquired 260–306 min after cutoff · n = 1,220
> REQ-WP0-01 specifies one run-level `evidence_cutoff_utc`. Track A measured 11 Sep requests spanning 4 h 20 min after the plan cutoff, with 1,220 distinct per-request cutoffs in the ledger; Track D measured refreshed quotes 301–306 min after the run's cutoff, so a completed-session cutoff and a post-open refresh cannot share one field. Recorded for ACK, no recommendation.

**PN-35** · M6 · ~106× (row count vs effective breadth) · n = 1,444 rows (22 runs)
> Gate design counts rows (1,444 presented, 19 GO). M6 measured N_eff 11–15 for every population of ≥ 179 rows (ρ̄ ≈ 0.07). Gap: about 100 rows per unit of effective breadth. Recorded for ACK, no recommendation.

**PN-36** · M8 · 20.5× the floor for side_correct (3.2–5.7× for TARGET_FIRST) · n = 6 strata
> Rule 12 specifies n < 100 as INSUFFICIENT_POWER. M8 measured that at family-wise α (m = 248) a 5-point TARGET_FIRST difference needs 322–568 per cell and side_correct about 2,050. Gap: formally eligible cells are underpowered for 5 points. Recorded for ACK, no recommendation.

**PN-37** · M4 · 12× variation in gamma-per-dollar against a stored count · n = CALL h5 surface cells (137 theses)
> The stored `convexity_score` is a 0–8 condition count (2.0 on every primary-run row). M4 measured convexity_per_dollar varying 12× across CALL h5 cells and falling monotonically with |delta|, while reachable payoff_per_dollar peaks at D025_040. Gap: the stored count measures neither quantity. Recorded for ACK, no recommendation.

**PN-38** · M5 · ~10× (p10–p90 spread vs |median|) · n = 148–693 per population
> The early-lane decision is specified as one median of % IV change. M5 measured row-level IQR 9–15 pp and p10–p90 spread about 30–40 pp against |median| ≤ 4 pp; the median's sign flips with the lookback date. Recorded for ACK, no recommendation.

**PN-39** · M3 · 4.8× (target distance vs stop distance) · n = 2,626 touched CALL theses
> ALG-08 places the invalidation as the row's own stop against a σ_h-scaled target. M3 measured median stop distance 3.0% against median vol-budget distance 14.4%; 71.8% of side-wrong CALL theses touch the stop. Recorded for ACK, no recommendation.

**PN-40** · M3 · 3.4× (target vs median favourable excursion) · n = 8,417
> ALG-08 specifies the vol-budget target 1.5·σ_a·√(h/252), median 13.8–14.9% for 6–10. M3 measured median MFE within the hold at 4.1–4.6%, target reached at any time on 3.9–8.3% of theses. Recorded for ACK, no recommendation.

**PN-41** · M5 · ~3.3× (theta up to −26% vs IV component ≤ +8%) · n = 769 clean pairs
> §4.6 frames the waiting question as the IV bought. M5 measured that at d ≥ 2 the held contract's premium path is dominated by theta (−6 to −26%) and the underlying move (±7 to ±28%), while the IV component is −0.2 to +8%. Recorded for ACK, no recommendation.

**PN-42** · M4 · selected at 0.879× thesis-best payoff · n = 146 (PUT n=86 `INSUFFICIENT_POWER`)
> The legacy `1_5d` delta window is 0.40–0.60. M4 measured D025_040 ranking above D040_060 in 65.6% of CALL h10 theses and per-thesis argmax |delta| median 0.34–0.36. Gap: in-family selected CALL contracts deliver a median 0.879× the thesis-best payoff. Recorded for ACK, no recommendation.

### (d) Return, ratio, coefficient or correlation units; or not quantified

**PN-43** · Track C · 138.6 pp net return (PUT); −3.4 pp (CALL) · n = 1,093 contracts with a grid
> ALG-05/06 specify moving headline and utility from the structural to the reachable scenario because targets are 3–4× the budget. Track C measured (offline, GARCH_SUB, rate 0.0395, floor 0.25) CALL median reachable net +32.7% vs structural +29.4% (reach ratio 1.38) and PUT +87.2% vs +229.3% (reach ratio 3.22). Gap: the switch reduces headline magnitude only for PUT; for CALL the reachable spot lies beyond the structural target on the median row. Recorded for ACK, no recommendation.

**PN-44** · M3 · +42% to +92% of move-free value to recover before the floor · n = 1,250 priced theses
> The governed profit floor is 0.25 (bid ≥ 1.25 × ask). M3 measured median flat-scenario decay −17% to −35% over the hold and median best bid / entry ask 0.32–0.81. Gap: the floor is set against entry ask while decay and spread (median 12–17%) are charged against it. Recorded for ACK, no recommendation.

**PN-45** · Track C · up to 10.35 pp scenario net return (2.04% theoretical) · n = real PUT rows
> The spec's European valuation has no intrinsic floor. Track C measured the intrinsic floor adding up to 10.35 pp to net return on deep-ITM PUT structural scenarios. Recorded for ACK, no recommendation.

**PN-46** · M2 · b_F −60% (0.192 → 0.076) · n = 2,389 / 4,848
> M2(c) asks whether the forecast carries information beyond IV. M2 measured that the available IV is weekly and coarse in tenor; at h=5 b_F falls from 0.192 to 0.076 when IV error is reduced by averaging sources. Gap: the test partly measures IV staleness. Recorded for ACK, no recommendation.

**PN-47** · M2 · 8–25% above IV measured vs 20–40% specified · n = 1,893–14,279 per IV source
> The design reads the forecast's 20–40% gap above IV as edge. M2 measured median σ_f/IV 1.08–1.25; the forecast sits 25–43% above realised and IV 43–87% above mean |r|. Gap: the gap above IV is 8–25%, and it coexists with a forecast that runs high against realised. Recorded for ACK, no recommendation.

**PN-48** · M2 · 15% relative (median RV/σ_f 0.697 at h=5 vs 0.800 at h=20) · n = 17,275 / 5,172
> ALG-01 specifies scaling one annual forecast by √(h/252) for every h. M2 measured horizon-dependent bias that √-time scaling of one number cannot represent. Recorded for ACK, no recommendation.

**PN-49** · M1 · within-sector/universe median std ratio 0.86 (range 0.47–1.19) · n = 670 sessions
> The design uses sector routing as the macro→ticker bridge. M1 measured within-sector 5-session std p50 at 47–119% of the universe std. Gap: most cross-sectional spread remains inside sectors. Recorded for ACK, no recommendation.

**PN-50** · M2 · 0.08 (h=5) and 0.05 (h=10) below the band floor; per-session ratio sd 0.19 · n = 4,891 / 4,320 test rows
> ALG-10 specifies a static bias multiplier with pass band median [0.90, 1.10] on the time-ordered test. M2 measured median σ_f/RV drifting 1.13 → 1.75 over 13 sessions; a multiplier trained on 6 sessions leaves the test median at 0.818 (h=5) and 0.851 (h=10). Recorded for ACK, no recommendation.

**PN-51** · M7 · Spearman EV rank vs |delta| −0.76 (CALL) / −0.62 (PUT) · n = 1,093
> The ranking is specified to favour the strongest expression. M7 measured EV rank falling with |delta| and premium (ρ −0.61 / −0.39); |delta| ≥ 0.60 contracts hold 4–5% of the top quintile. Gap: rank tracks leverage per unit premium. Recorded for ACK, no recommendation.

**PN-52** · M6 · TC 0.68 vs ≤ 0.13 depending on target · n = 1,444 rows
> §4.8 frames TC against "the unconstrained score". M6 measured no single unconstrained score in the book: rank is verdict order then `priority_score`, and `composite_score` and `ev3_ev_lower_bound_return` have |ρ| ≤ 0.13 with every inclusion indicator. Recorded for ACK, no recommendation.

**PN-53** · M1 · sector RS autocorrelation ≈ 0 at lags 5/10/20 · n = 675 sessions × 11 sectors
> ALG-14 phrases routes as relative-strength states. M1 measured 5-session sector RS autocorrelation −0.041 / −0.002 / 0.012 (non-overlapping lag 5 −0.092). Gap: a prior-week sector RS state carries near-zero linear information about the next 5–20 sessions. Recorded for ACK, no recommendation.

**PN-54** · M6 · σ SMD between arms −1.41 to +0.55 · n = gate cells ≥ 100 per arm
> ALG-08 specifies a σ-scaled barrier. M6 measured that every gate removing lower- or higher-σ rows is compared on that barrier, so hit-rate differences mix gate selection with barrier distance. Not separated. Recorded for ACK, no recommendation.

**PN-55** · M4 · not separated (CALL association 14.6 pp; PUT none) · n = 570
> §4.5 specifies breakeven/σ_h as the cleanest single number. M4 measured its association with side-correctness for CALL (62.3% vs 47.7%) and not for PUT; σ_h comes from the GARCH forecast while breakeven is driven by option IV, so the ratio mixes forecast-vs-implied vol with contract choice. Recorded for ACK, no recommendation.

**PN-56** · M5 · |delta_p| ≤ 4.2 pp against binomial SE 1.1–1.2 pp · n ≈ 400 per cell
> §4.6 specifies delta_p by hidden_state × confirmation state. M5 measured TARGET_FIRST base rates of 2–7%; the SE at available cell sizes is the same order as every measured |delta_p|. Gap: the measurement cannot resolve delta_p at available sizes. Recorded for ACK, no recommendation.

**PN-57** · Track G · not quantified · n = 19
> REQ-WP6-03 specifies that every coaching value equals the Lab value exactly. Track G measured the dossier as rendered markdown with formatted numbers; exact equality is measurable only on the machine-readable desk-gate CSV (19/19). Recorded for ACK, no recommendation.

---

## Source mapping

Track A: PN-12, 16, 17, 34 · Track B: PN-14, 23 · Track C: PN-09, 11, 24, 43, 45 · Track D: PN-05, 25, 34 · Track E: PN-19, 29, 33 · Track F: PN-07, 20, 26, 30 · Track G: PN-28, 32, 57 · Track H: PN-22, 31 · Track I: PN-27 · Track N: PN-03 · M1: PN-15, 49, 53 · M2: PN-46, 47, 48, 50 · M3: PN-04, 06, 39, 40, 44 · M4: PN-10, 37, 42, 55 · M5: PN-13, 38, 41, 56 · M6: PN-35, 52, 54 · M7: PN-01, 02, 08, 51 · M8: PN-18, 21, 29, 36 · M9: none.

Recommendation or verdict wording removed from source notes: Track A "supports the spec"; Track C defect reference UAT-D-C1; Track D "separating it from executability matters"; Track F "the acceptance metric passes"; Track G "the acceptance test needs a machine-readable dossier"; M5 proposed consistent form of the inequality (kept only as a measured sign comparison); M7 comparison with the pre-registered expectation.
