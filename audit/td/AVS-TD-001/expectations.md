# AVS-TD-001 — Pre-registered expectations

Written 2026-09-12 (local evening) BEFORE opening run artefacts in detail. Basis for expectations: the governed documents (SD v1.2, REQ v1.2, Annex A v1.2), the four stage claim sheets under `audit/avs_fix_002/`, the run-directory file listings (names and sizes only), and the two `run_meta.json` files. No CSV/JSON row content had been read at the time of writing, except the file trees.

Primary run: `20260911_115904` (TEST, forced intra-session). Comparison: `20260910_150045` (TEST). No `NORMAL_COMPLETED_SESSION` run is expected to exist because the last stored run predates the Stage 1 commits (all of 12 Sep).

**Overall expected shape:** "Not yet implemented at run level, source present offline." The stored runs were produced by pre-remediation code, and the claim sheets say every stage after Stage 0 is offline-only awaiting a controlled cycle. So most REQs are expected to land as `CLOSED OFFLINE` (source + tests) or `NOT IMPLEMENTED` at run level, with the stored artefacts reproducing the defect figures quoted in the requirements. Acceptance verdict expected: `BASELINE — NOT YET IMPLEMENTED` with a handful of P0s from what *is* live.

Column legend: E = expected (pre-registered), A = actual (filled in after the track ran), Δ = gap note.

## Acceptance tracks

| Check | Expected (E) | Actual (A) | Δ |
|---|---|---|---|
| A1 run_condition | `run_meta.json` on both stored runs lacks `run_condition`/`baseline_eligible` (pre-Stage-1). Artefact evidence (evidence cutoff vs session hours) shows intra-session on both. Verdict: NOT IMPLEMENTED at run level; source CLOSED OFFLINE. | Fields absent on 27/27 runs; runs labelled PRODUCTION; 13/13 ledgered runs fetched after own cutoff (11 Sep cutoff PRE_OPEN 07:59 ET). NOT IMPLEMENTED run level; source CLOSED OFFLINE | **GAP** worse than expected: unanticipated P0 (cutoff contradicted on every ledgered run) + P1 mislabelling |
| A2 provider completeness | `provider_completeness_evidence` absent from stored run_meta. My own computation from control_plane chain observations: fraction of tickers with max provider ts ≥ 16:00 ET on 11 Sep expected < 0.5 (forced intra-session at ~11:59 local). | Naive max-ts fraction 0.5438; session-date close coverage 0.0 on both runs (0/993, 0/1,020); evidence field absent; registry says COMPLETE | **GAP** direction reversed on E's metric (0.54, +0.04 over 0.5); correct metric 0.0, worse than expected |
| A3 pre-open run | No PREOPEN run exists → NOT TESTED. On 11 Sep morning artefacts `physical_fetch_count` > 0 and EXECUTABLE_NOW-type rows > 0. | NOT TESTED (no PREOPEN run); DOI `physical_fetch_count` 0 vs ledger 1,218 physical; EXECUTABLE_NOW 69 (CALL 47 / PUT 22) | worse than expected: report says 0 fetches while ledger shows 1,218 (lineage defect, P2) |
| A4 quote timestamps | On 11 Sep: count(quote_fetch == provider ts to the second) > 0 (old `_utc_now()` fallback); same-session hydrated fraction < 0.95; ~453 rows on prior-session quotes; 391/409 FLAG rows QUOTE_STALE. | fetch==provider ts 226 (CALL 26 / PUT 12 / OTHER 188); same-session 0.628; prior-session 453 (CALL 255 / PUT 198); FLAG QUOTE_STALE 391/409; FRESH label on the 453 stale | as expected (453 and 391/409 exact); extra FRESH-label finding |
| A5 `_utc_now` grep | 0 hits on quote-timestamp assignment paths after Stage 1 (CLOSED OFFLINE). | 0 hits at cc509cb; 11 near-misses on fetch/validation fields; 1 borderline cutoff fallback. CLOSED OFFLINE | as expected |
| A6 packet archive | Archive module exists (Stage 1 claim). Stored run does not record `packet_id`+hash (pre-Stage-1) → run-level NOT IMPLEMENTED. Resolving the 10 Sep packet by ID: expect the archive to contain packets only from 12 Sep onward → resolution of 10 Sep FAILS by ID (only "latest"-style file in dropbox/macro). | Module exists; packet_id+hash not recorded; resolve 10 Sep by ID FAILS (FileNotFoundError); `data/macro/archive` never created; 2 conflicting 11 Sep packet ids | worse than expected: archive empty, not populated from 12 Sep (P0) |
| A7 import graph | 0 untracked (Stage 0 claims 138 modules / 356 edges). `git ls-files --error-unmatch` on USMI/macro_domain/worker3 = 0 (already observed: exit 0). | 0 untracked, `--error-unmatch` exit 0 on 179 modules; graph 132/335 (4 roots), 177/479 (6 roots), gate 152/382 at HEAD; 25 reachable modules outside gate. OPEN P1 | untracked part as expected; gate under-enumeration not anticipated |
| B1 10d/5d ratio | v2 fields `expected_move_10d_fraction` absent from stored Layer 3 output → NOT IMPLEMENTED at run level. Legacy `garch_expected_move_6_10d / _1_5d` = 0.4142 on ~100% of rows (differenced). Source `domain/volatility_budget.py` exists → CLOSED OFFLINE. | v2 fields absent 82/82 CSVs; legacy ratio 0.4142 on 100% (2,868 rows); offline ratio 1.41421 on all rows; fixtures exact. NOT IMPLEMENTED run level / CLOSED OFFLINE | as expected |
| B2 legacy deprecated | Legacy names exist; "deprecated" marker present in producer; ≥1 legacy consumer still reads them (trigger_layer). | Names and deprecated markers present; trigger_layer adapts; 4 further unadapted consumers; ev3_stage0 reads never-emitted names. OPEN P2 | worse than expected: 4+ unadapted readers vs >= 1 |
| B3 spread units | `spread_fraction_mid` absent from every stored CSV; legacy `spread_pct` present in mixed units (some ≤ 1, some > 1). Adapter fixture 0.12/12.0: labelled unit if adapter exists (Stage 2–5 claim) → CLOSED OFFLINE. | `spread_fraction_mid` absent 82/82; `spread_pct` 2,149 <= 1 / 369 in (1,2] / 10,093 > 2, unit flips between runs; adapter labels 0.12/12.0; lab_control still guesses. OPEN P1 | adapter as expected; writers and one consumer worse than expected |
| B4 tier BLOCK | Stored run: BLOCK rows whose only trigger is spread ≤ 0.25 > 0 (old defect: "BLOCK on every row"). Expect > 500 such rows. | 584 spread-only BLOCK with spread <= 25% (CALL 349 / PUT 235) on 20260911; 0 on 20260910; current code clears 0. OPEN P1 | as expected on count (+84 over 500); fix ineffective offline was not expected |
| B5 silent defaults | `audit/silent_defaults_inventory.md` exists; 5 random sites verifiable ≥ 4/5; `silent_zero_violations` absent from stored run summary → NOT TESTED at run level. | Inventory exists; 5/5 sites verified; 1 row cites absent module; 3 named sites uninventoried; counter absent. OPEN P2 | better on sample (5/5), worse on inventory completeness |
| C1 rate | Stored DOI report: `FAMILY_NOT_VALUED_RATE_UNAVAILABLE` = 1,218 of 1,218 (known). No replay artefact under audit/ showing 0 → run-level NOT IMPLEMENTED; source CLOSED OFFLINE. | RATE_UNAVAILABLE 1,218/1,218; offline rate lineage on 2,385/2,385. NOT IMPLEMENTED run level / CLOSED OFFLINE | as expected; forecast-vol gap remains (UAT-D-C1) |
| C2 reachability | Fields absent from stored runs → NOT IMPLEMENTED at run level. If I compute reach_ratio myself on Friday GO rows from cumulative moves: median ≈ 4.1, 13/19 > 3. | NOT IMPLEMENTED run level; ALG-02 GO median 3.48, 11/19 > 3 | worse than expected numerically: median -0.6, 2 fewer rows > 3 (E reproduced only with the differenced legacy sum) |
| C3 geometry | Wrong-side target/invalidation rows in stored run: > 0 and NOT named exceptions (expect 1–5% of directed rows). | 0 wrong-sided rows; missing values named (202 invalidation, 233 target). OPEN for population | **GAP** direction reversed: 0% wrong-side vs 1-5% expected; the problem is missing geometry |
| C4 BSM oracle | Production function reproduces Annex worked example within 0.5% (flat −32.3%, reachable +115.3%, invalidation −67.5%) → CLOSED OFFLINE. No stored assessment carries scenario grid → run-level NOT TESTED. | Annex example within 0.05pp; real CALL exact; real PUT fails 15/54 scenarios (up to 2.04%, intrinsic floor). Run NOT TESTED; OPEN offline for PUT | worse than expected for PUT (+1.5pp over tolerance) |
| C5 dte_inside_hold | Field absent from stored runs → NOT IMPLEMENTED at run level; source fixture exists. | Fixture passes; chain excludes all 7,981 inside-hold contracts before valuation; 1,094 mislabelled. NOT IMPLEMENTED run / OPEN offline | **GAP** worse than expected: retention unreachable in production |
| C6 monetisability policy | Stored run monetisability states are legacy vocabulary (not SCENARIO_*) → NOT IMPLEMENTED at run level. | Legacy vocabulary at run level; offline recompute 1,093/1,093 equal (CALL SM 407 / SL 282 / NCM 42 / IND 476; PUT 323 / 37 / 2 / 420). NOT IMPLEMENTED run level | as expected |
| C7 convexity | Stored run: `convexity_score` = 2.0 on ≥ 99% of rows, distinct values ≤ 3. | 100% of directed rows = 2.0, 2 distinct values; offline v2 1,012 distinct, 0 = 2.0 | as expected |
| C8 rr_ consumers | ≥ 1 consumer of `rr_*` remains on Lab required schema or morning gate path → OPEN (P2). | 10-15 `rr_*` columns on books; Morning Gate and lab_control readers. OPEN P2 | as expected |
| C9 vol validation | No validation report → `validation_state` absent from run; bias_multiplier absent. NOT IMPLEMENTED at run level. If a report exists offline, median ratio expected 0.7–0.85 (forecast runs high). | No report; offline 100% UNVALIDATED_INPUT, multiplier 1.0; economics rows carry no validation state (0/1,093). NOT IMPLEMENTED | as expected; ratio not measurable (no report; M2 gives RV/sigma_f 0.70-0.80) |
| C10 utility v2 | Absent from stored runs; Spearman(v1,v2) not computable on stored runs → NOT TESTED at run level; expect < 0.7 if computable from replay. | NOT TESTED run level; offline rho(v1,v2) 0.147 (CALL 0.025 / PUT 0.342); within-family median 0.679 | as expected (< 0.7); within-family borderline |
| D1 reconciliation | Does NOT hold on stored run: discovery candidates ≈ 2,000–3,000; Lab 1,444; dropoff audit accounts for part; unexplained gap > 0 → P0 candidate but on TEST run. | Identity holds on both runs (gap 0; 3,320 input reconciles); named-exception quality P2 | **GAP** better than expected: expected P0 not found |
| D2 doi_projection_state | `DOI_TABLES_NOT_ACTIVATED` = 1,381/1,444; `GOVERNED_CONTRACT_IDENTITY_MISMATCH` = 63 (as quoted in REQ). | 1,381 / 63 exactly (CALL 761/37, PUT 432/26, OTHER 188/0). OPEN P1 | as expected |
| D3 thesis_id | Lab triage has thesis_id on 1,444/1,444; DOI input CSV missing thesis_id on > 0 rows (unverified path) — expect > 0. | Book 1,444/1,444; DOI input missing 226 (CALL 26 / PUT 12 / OTHER 188); 38 book ids legacy run-scoped. OPEN P1 | as expected |
| D4 lifecycle | Stored run: contracts with OI < 100 / vol 0 removed > 0 (contract_rejection_log) → OPEN at run level; retained-in-LIQUIDITY_* > 0 also. | 0 OI/volume removals; 924 thin retained; three state machines NOT IMPLEMENTED | **GAP** direction reversed: removals 0 vs > 0 (non-removal holds) |
| D5 EXECUTABLE_NOW | No post-open run → NOT TESTED. | Post-open NOT TESTED; 453 (primary) + 458 (comparison) stale/non-refresh EXECUTABLE_NOW; 69 Lab rows pass. P0 candidate | **GAP** worse than expected: P0 candidate where NOT TESTED expected |
| D6 hysteresis | Flip rate between 10 Sep and 11 Sep preferred contracts: 40–70%; no margin fields → NOT IMPLEMENTED at run level. | Flip rate 6.6% (79/1,191; CALL 7.5% / PUT 5.1%); no margin fields. NOT IMPLEMENTED run level | **GAP** better than expected: 6-10x lower than 40-70% |
| D7 assessment_id | Absent from stored runs; source per ALG-16 exists (Stage 2–5 claim) → CLOSED OFFLINE if hash matches recomputation. | Absent from runs (0 rows); hash matches production formula 5/5, ALG-16 0/5. OPEN P1 | **GAP** worse than expected: OPEN, not CLOSED OFFLINE |
| D8 p_* fields | Lab book v3 contains ≥ 1 non-null `p_*`/probability column from EV3 shadow while `calibration_state` is absent → P0 candidate on a TEST run (uncalibrated number shown as probability). | `win_prob_predicted` 1,444, `ev3_p_*` 223, layer2 prob 1,444 non-null without calibration_state; `doi_p_*` null. P0 candidate | as expected; exposure wider than EV3 shadow |
| E1 labels | If `domain/outcome_learning.py` exists: 30/30 agreement with my ALG-08 recomputation, except tie handling (Annex says AMBIGUOUS, prompt says same-session tie → INVALIDATION_FIRST: expect a deviation note). | 30/30 3-way on budget labels (CALL 15 / PUT 15); 10/10 structural; 0 ties; production labels against structural target (UAT-D-E1 P1). CLOSED OFFLINE | as expected on function; production-target defect not anticipated |
| E2 point-in-time | 10/10 if archived run artefacts hold budget/invalidation; else NOT TESTED. | Retrospective 10/10 from archives; production records lack budget/hold/session 10/10. OPEN | worse than expected: production half fails |
| E3/E4 calibration report | No report exists → NOT TESTED; Stage 6 readiness = INSUFFICIENT_OUTCOMES. | No report, script absent (E3 NOT IMPLEMENTED); E4 NOT TESTED; readiness INSUFFICIENT_OUTCOMES; gate/partition logic CLOSED OFFLINE | as expected |
| E5 backoff | Functions exist offline; 10 keys from a synthetic table → CLOSED OFFLINE. | Chain order exists; 4 of 5 lineage fields, kappa-shrinkage, kappa/n_min config absent on 10/10 keys. NOT IMPLEMENTED P1 | **GAP** worse than expected: NOT IMPLEMENTED vs CLOSED OFFLINE |
| E6 p_T vs base rate | No calibrated p_T exists; disclosure: "no stratum can be reported; n resolved < 100 everywhere". | No calibrated p_T; n resolved = 0 in all 6 direction x hold strata; uncalibrated `win_prob_predicted` 1,444/1,444 (UAT-D-E4 P0) | as expected on disclosure (0, stricter than < 100); extra P0 |
| F1 SECTOR_UNMAPPED | Stored run: SECTOR_UNMAPPED on 19/19 GO rows; `macro_ticker_context_available` 0/1,444; rows lacking GICS in canonical store < 5% → former > latter → OPEN. | SECTOR_UNMAPPED 19/19 GO and 1,444/1,444; available 0/1,444; lacking GICS 0%. OPEN P1 | as expected; cause wider (vocabulary mismatch) |
| F2 routing | `usmi_routing_key` absent from stored run → NOT IMPLEMENTED at run level; 20/20 if evaluated through the offline function. | `usmi_routing_key` absent. NOT IMPLEMENTED; offline Join 2 exact 5/20; routed 533/565 (CALL 288/312, PUT 245/253); 0 OPPOSED | **GAP** worse than expected: 5/20 vs 20/20 offline |
| F3 scenario | `usmi_scenario` absent from stored run → NOT IMPLEMENTED; offline evaluator exists. | `usmi_scenario` present, UNRESOLVED 1,444, no failed_clause; offline evaluators cannot parse real packet. OPEN P1 | **GAP** E wrong on presence: OPEN, not NOT IMPLEMENTED |
| F4 macro immutability | grep: no macro input in producers of direction/population/preferred symbol; `contracts_at_budget` producer retired → CLOSED OFFLINE. | Grep clean (CLOSED OFFLINE); property test and consumer table NOT IMPLEMENTED P1 | worse than expected: missing property test |
| F5 capacity | Legacy `contracts_at_budget` present in stored run; recomputation matches floor(budget/(ask×100)) on ≥ 95% of rows; field retired from config (ALG-13). | `contracts_at_budget` absent from every stored CSV; recompute NOT TESTED; capacity calculators on production paths; `position_size_display` legacy 1,444. OPEN P1 | **GAP** E wrong on field presence; recompute not measurable (field absent) |
| F6 structure_evidence_state | Absent from stored run → NOT IMPLEMENTED at run level. | Absent run level. NOT IMPLEMENTED; offline CLOSED OFFLINE (LOW_ENERGY 327 -> NO_EDGE; GO 8 -> NO_EDGE) | as expected |
| G1 lineage 10 rows | < 10/10 resolvable on v3 book (no per-field dataset IDs); expect 0/10 fully resolvable. | 0/10 on v3 (CALL 0/5 / PUT 0/5) and 0/10 on final book; 18 numbers/row dataset-only, 0 versioned | as expected |
| G2 projector | BLOCK beside GO occurrences > 0 in stored run; summary says executable while execution_state ≠ EXECUTABLE_NOW on > 0 rows. | BLOCK beside GO 19 canonical (CALL 10 / PUT 9) / 100 any pair; no SD execution_state column; v3 `quote_freshness=STALE` on 19/19 GO rows (P0); offline 432/480 reason contradictions. OPEN | as expected plus unregistered P0 (stale quote shown executable) |
| G3 coaching parity | 20 sampled values: ≥ 18/20 equal (dossiers are derived from the same book); mismatches expected in derived/rounded fields. | 15/20 equal (CALL 5/9, PUT 10/11); 5 rounding mismatches; desk-gate csv 19/19. OPEN | worse than expected by 3 (15 vs >= 18); mechanism as expected |
| G4 overlay parity | No parity report → NOT IMPLEMENTED. | NOT IMPLEMENTED; mini parity 1,444/1,444 on population/contract/direction | as expected |
| H1 ledger | CANDIDATE_DECISION > 1,000; EXECUTION_DECISION > 100; HumanDecisionRecorded = 0; FillRecorded = 0; OUTCOME events < 100. No position episodes at all. | CANDIDATE_DECISION 4,931; EXECUTION_DECISION 1,679; decision/fill record types 0; OUTCOME 1 (QA test row); no episodes. OPEN | as expected; naming deviation only |
| H2 manual fills | None entered → NOT TESTED (nothing to verify). | NOT TESTED; 14 journal closed_trades are not fills | as expected |
| H3 price-store health | `outcome_maturation` diagnostic present; `outcomes_deferred` count present; price DB present now (1 GB), so deferred reason is horizon-not-elapsed rather than absent store. | Diagnostic present, `deferred_horizons=0`; store covers 1,444/1,444; 3,252/3,252 ineligible for missing `completed_session`. OPEN P1 | **GAP** root cause differs: missing completed_session, not horizon |
| H4 counterfactuals | No OutcomeRecord per candidate on runs ≥ 5 sessions old → NOT IMPLEMENTED at run level. | 0 counterfactual OUTCOME events (20260904 0/256, 20260831 0/201). NOT IMPLEMENTED | as expected |
| I1 replay | Replay harness produces no book diff for stored runs; only Stage 1 provider-finality replay JSON → NOT TESTED (partial). | No book replay harness; only provider-finality replay (not runnable read-only). NOT IMPLEMENTED | worse than expected: NOT IMPLEMENTED, not NOT TESTED |
| I2 os.environ | > 10 hits in production modules; ≥ 1 gating a feature without release-profile documentation → OPEN. | 154 env reads (73 on import graph); 20 gating/threshold vars undocumented. OPEN P1 | as expected in direction; magnitude 15x the > 10 floor |
| I3 governed constants | `config/governed_constants_v1.json` exists with most Annex keys; ≥ 2 Annex keys missing; literal values also present in ≥ 1 non-loader module → OPEN (P2). | 20/29 Annex keys present, 9 missing; 13 literal hits in 7 files. OPEN P1 | worse than expected: 9 missing vs >= 2; P1 not P2 |
| I4 release evidence | Manifests exist for stage 0/1/2_5/6; migration record and rollback instructions: partial. | 5 manifests (0/1/2_5/6/policy; 2_5 no hashes); 0 migrations, record consistent; backup hashes 3/3; rollback rehearsal absent. OPEN | as expected |
| N NFR-01..10 | NFR-02, -05, -06, -09 fail or NOT TESTED at run level; NFR-03, -04, -08 partially met offline. | 0 of 10 pass: -01 OPEN, -02 NOT TESTED, -03..-09 OPEN (7), -10 NOT IMPLEMENTED | worse than expected: -01, -08 OPEN (not partially met); -05 measured, not NOT TESTED |

## Discovery tracks

| Track | Expected (E) | Actual (A) | Δ |
|---|---|---|---|
| Outcome census | Decisions in ledger: 2,000–6,000 CANDIDATE_DECISION rows across ~20 runs; resolved outcomes (target/invalidation/timeout): < 200; buckets with n ≥ 100: 0; modal bucket n < 20. Reconstruction from OHLC feasible for > 80% of decisions (price store covers the universe). | CANDIDATE_DECISION 4,931 over 5 ledgered runs (ledger starts 5 Sep); resolved ledger outcomes 0; 5-key buckets with full window 66, n >= 100: 10; modal 3,077 (LOW_ENERGY/LOW/CALL/6-10); OHLC-reconstructable 9,926 of 16,711 directed (59%; CALL 8,177 / PUT 1,749) | **GAP** modal bucket ~150x E's < 20; 10 buckets >= 100 vs 0; reconstruction 59% vs > 80%; 5 ledgered runs not ~20 |
| M9 field census | lab_signal_book_v3: 502 fields; fill rate < 50% on ≥ 30% of fields; constants (1 distinct) ≥ 15%; UNREAD ≥ 40%; AMBIGUOUS_UNIT ≥ 20 fields. Minimum set for current decisions ≤ 40 fields. | 502 fields; fill < 50% on 15.9%; constants 39.8%; UNREAD 3.8% (run-wide 40.3%); AMBIGUOUS_UNIT 15 (11 genuine); minimum set tier A 34, tier B 231 | **GAP** UNREAD -36 pts; constants +25 pts; fill -14 pts; tier B ~6x the <= 40 set |
| M2 forecast vs IV | (a) forecast/realised median ratio 1.2–1.4 (forecast high). (b) IV explains realised better than forecast (higher R²). (c) forecast coefficient NOT significant (|t| < 2) once IV_matched present, n ≈ 5,000–20,000 rows if IV history is joinable; else PARTIAL (a) only. Fraction `_6_10d < _1_5d`: ≈ 100% (differenced fields). | (a) sigma_f/RV median 1.434 / 1.390 / 1.250 at h 5/10/20; (b) mixed by IV source; (c) pooled abs t 3.76 / 6.21 / 4.72 on surface IV (PUT < 1); n 2,389-2,935 for (c), 17,275 for (a); frac 6_10d < 1_5d 100.000% | **GAP** (c) direction reversed on primary proxy; (a) as expected; n below range |
| M7 EV decomposition | vol_component/EV_net median > 0.6; rows retaining EV > 0 at σ = σ_IV: < 40% of currently positive rows. Reachability (2) single-barrier vs (3) double-barrier: p_target(3) lower by 15–35%; EV sign flips (1)→(3): 20–40% of rows. Friction: no fills → half-spread multiplier unestimable (1.0). | vol/EV_net median CALL -0.012 / PUT 0.172; EV>0 kept at sigma_IV CALL 94.9% / PUT 97.8%; p_T(3) vs (2) CALL -19% / PUT -2%; sign flips CALL 40.4% / PUT 74.6%; multiplier 1.0 (0 fills) | **GAP** vol share 0.6+ below E; EV kept +55 pts above; PUT flips +35 pts |
| M4 convexity surface | Widening delta band 0.40–0.60 → 0.10–0.85 raises median candidates from 1 to ≥ 5 and reduces zero-candidate tickers from 305 to < 100. payoff_per_dollar peaks at delta 0.25–0.40, DTE hold+15 to hold+30. Selected contract within the peak region on < 50% of rows. breakeven_move median 0.8–1.2 σ_h. | Median candidates 2 -> 7 (CALL 2 -> 6, PUT 3 -> 10); zero 169 -> 39 of 929; CALL peak abs delta 0.34-0.36, DTE H+05_15 wins h5; selected in peak 33.6-42.5%; breakeven 0.751 CALL / 0.620 PUT sigma_h | as expected on candidates and delta; tenor contradicts E; breakeven below E by 0.05-0.18 |
| M1 dispersion/routing | Cross-sectional 5d return std per session: 4–7%; sector RS autocorrelation at lag 1: 0.1–0.3, at 20: ≈ 0. USMI label hit rates 45–55%, INSUFFICIENT_POWER for most labels (n < 100 sessions). Join requires external sector reconstruction. | 5d std p50 6.78% (p10 5.51 / p90 8.69); RS5 lag1 0.793 (mechanical), RS1 -0.000; lag20 0.012; four-label hit rates DATA_UNAVAILABLE, proxies 0.35-0.67 all INSUFFICIENT_POWER (max n 51); external sector join done | as expected on dispersion and lag20; lag1 outside range both ways; label power worse than expected |
| M3 two probabilities | DATA_UNAVAILABLE for monetised outcomes (no fills, no option outcome history); directional outcome reconstructable; side-correct rate 45–55% by direction. | Monetised PARTIAL: 1,250/8,417 theses priced (14.9%), no fills; directional reconstructable 8,417; side-correct CALL 45.4% / PUT 53.5% (GOVERNED CALL 37.2%, n 172) | better than expected on availability (PARTIAL vs DATA_UNAVAILABLE); side-correct as expected |
| M5 cost of waiting | 1.9% IV figure reproducible ± 1pp with IQR > 5pp; n 100–400 rows; quote staleness: median |Δ option mid| over the stale window 5–15%. | -1.908% reproduced exactly; IQR 12.4pp; n 148 (649-693 on later books); own-contract staleness DATA_UNAVAILABLE (0/453), proxy median abs dmid 11.8% | as expected (0.00pp); staleness PARTIAL, proxy only |
| M6 gates / TC | Transfer coefficient (inclusion vs unconstrained score) < 0.3; hit-rate halves INSUFFICIENT_POWER. | GO inclusion abs rho <= 0.16; non-BLOCKED TC vs priority_score 0.68; 23 pooled gate x direction cells powered (post-0831 gates INSUFFICIENT_POWER); N_eff ~13 | **GAP** TC +0.38 above < 0.3 on non-BLOCKED set; more hit-rate halves powered than expected |
| M8 conditional outcomes | 0 cells with n ≥ 100; splits examined ≈ 11 conditions × ~5 levels ≈ 60 cells; nothing survives. | 248 eligible tests with n >= 100 (CALL 166 / PUT 82); 14 partitions, 485 cells, 970 tests; 80 pooled BH survivors, 48 after session-stratified BH (CALL 41 / PUT 7), 26 session-confounded | **GAP** 248 vs 0 powered; 48 survivors vs none; +425 cells (survivors largely sector/session structure) |

## Question and split count

Distinct acceptance checks pre-registered: 62 (A1–A7, B1–B5, C1–C10, D1–D8, E1–E6, F1–F6, G1–G4, H1–H4, I1–I4, N×10).
Distinct discovery measurements pre-registered: 9 tracks + census = ~28 measurements.
Splits pre-registered for M8: 11 conditioning variables (to be counted exactly in track_M8.md and added here as actual).

**Actual (filled after the tracks ran; the pre-registered lines above are left unchanged).**

Acceptance checks run: 64 distinct. The pre-registered list names 54 lettered checks plus 10 NFRs, which is 64; the "62" above was a miscount. Each check gets one headline status, the worst run-level state. Sub-parts closed offline are noted in the A column.

| Status | Count | Checks |
|---|---|---|
| OPEN | 35 | A1, A4, A7, B2, B3, B4, B5, C3, C7, C8, D2, D3, D5, D7, D8, E2, E6, F1, F3, F5, G2, G3, H1, H3, I2, I3, I4, NFR-01, -03, -04, -05, -06, -07, -08, -09 |
| NOT IMPLEMENTED | 19 | A2, A6, B1, C1, C2, C5, C6, C9, D4, D6, E3, E5, F2, F6, G1, G4, H4, I1, NFR-10 |
| NOT TESTED | 6 | A3, C4, C10, E4, H2, NFR-02 |
| CLOSED OFFLINE | 3 | A5, E1, F4 |
| Holds on a TEST run (cannot be closed) | 1 | D1 |

Ten more checks were run that were not pre-registered: REQ-WP0-05, REQ-WP0-07, ALG-12 EXECUTABLE_NOW rule, ALG-15, REQ-WP1-05, REQ-WP3-05, REQ-WP6-01 v4 coverage, REQ-WP7-03, Rule 7 test edits, DEV-03 failure reconciliation.

Discovery measurements made: 69 state-log lines across the census and M1–M9, against about 28 pre-registered. Counts come from each track's state log; COMPLETE and DONE are counted as MEASURED.

| Track | Lines | MEASURED | PARTIAL | DATA_UNAVAILABLE | INSUFFICIENT_POWER |
|---|---|---|---|---|---|
| Outcome census | 3 | 3 | 0 | 0 | 0 |
| M1 | 9 | 5 | 0 | 1 | 3 |
| M2 | 11 | 7 | 4 | 0 | 0 |
| M3 | 5 | 3 | 2 | 0 | 0 |
| M4 | 6 | 3 | 3 | 0 | 0 |
| M5 | 8 | 2 | 4 | 1 | 1 |
| M6 | 5 | 5 | 0 | 0 | 0 |
| M7 | 6 | 5 | 1 | 0 | 0 |
| M8 | 5 | 5 | 0 | 0 | 0 |
| M9 | 11 | 11 | 0 | 0 | 0 |
| **Total** | **69** | **49** | **14** | **2** | **4** |

Splits and tests examined (actual):

| Source | Count |
|---|---|
| M8 | splits examined: 14 (pre-registered 11 conditioning variables; 485 cells; 970 tests; BH family 248 pooled / 222 session-stratified) |
| M4 | 113 splits (54 surface cells, 16 delta + 12 tenor head-to-heads, 23 breakeven bins, 6 halves tests, 2 Spearman) |
| M6 | 51 pooled gate × direction cells (17 gates × 3 directions; 704 per-run cells) + 160 IC cells (99 with n >= 100); no multiple-testing adjustment |
| M5 | 23 hidden_state × verdict cells for delta_p (4 with n >= 100) |
| Outcome census (descriptive, not tests) | 66 five-key buckets with a full window (139 over all directed rows) |
| **Total tests/splits (M8 970 + M4 113 + M6 51 + 160 + M5 23)** | **1,317** (not counting M6's 704 per-run cells or the 66 descriptive census buckets) |

The M8 plan pre-registered about 60 cells. The discovery tracks examined about 22 times as many comparisons, so read any single surviving association against that count.

## Largest pre-registration misses

| # | Check | Expected (E) | Actual (A) | Track that shows why |
|---|---|---|---|---|
| 1 | M7 EV decomposition | vol_component/EV_net median > 0.6; EV > 0 kept at σ_IV < 40% | CALL −0.012 / PUT 0.172; kept CALL 94.9% / PUT 97.8% | `track_M7.md` |
| 2 | Outcome census | modal bucket n < 20; 0 buckets n >= 100; reconstruction > 80% | modal 3,077; 10 buckets n >= 100; 9,926/16,711 (59%); ledger resolved outcomes 0 | `outcome_census.md` |
| 3 | M8 conditional outcomes | 0 cells n >= 100; nothing survives | 248 eligible tests; 48 survivors after session-stratified BH (mostly sector/session structure) | `track_M8.md` |
| 4 | D6 hysteresis | flip rate 40–70% | 6.6% (CALL 7.5% / PUT 5.1%) | `track_D.md` |
| 5 | M9 field census | UNREAD >= 40% of Lab-book fields | 3.8% (19/502); run-wide 40.3% | `track_M9.md` |
| 6 | D1 / D5 reconciliation and EXECUTABLE_NOW | D1 unexplained gap > 0 (P0); D5 NOT TESTED | D1 gap 0 on both runs; D5 P0 candidate (453 + 458 stale EXECUTABLE_NOW) | `track_D.md` |
| 7 | F2 routing | 20/20 offline | Join 2 exact 5/20 | `track_F.md` |
| 8 | M2(c) forecast given IV | abs t < 2 | pooled abs t 3.76 / 6.21 / 4.72 on surface IV (h 5/10/20) | `track_M2.md` |