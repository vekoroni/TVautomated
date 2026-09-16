# AVS-TD-001 independent pipeline impact validation

**Assessment date:** 2026-09-13  
**Production code assessed:** branch `avs-fix-001`, commit `cc509cbe7fa60a3fb2f7a37a164a66f27588251d`  
**Audit folder:** `audit/td/AVS-TD-001`  
**Assessment mode:** read-only. No pipeline stage, provider call, test, database write, configuration change, or production-code change was performed.

## 1. Executive verdict

The AVS-TD-001 folder contains substantial, reproducible evidence and has identified several genuine production-impacting defects. It must not, however, be read as 64 independent production failures or as proof that every historical defect remains present in the current release.

The correct conclusion is:

1. **The pack has found current-code defects that can materially distort which long CALL and PUT opportunities are shown as monetisable or executable.** The most important are spread-unit ambiguity, stale/missing quote authority, incomplete DOI valuation wiring, mixed ranking scales, exclusion of contracts that expire inside the governed hold, conflicting monetisability engines, and contradictory Lab presentation states.
2. **Several severe-looking findings are valid historical evidence but not yet evidence of failure at the current commit.** The stored runs were forced, dirty-tree, intra-session runs produced by commit `00baa2b`, before the 12 September remediation. Provider finality, run-condition governance, quote timestamp separation and macro archiving now exist in source, but no normal completed-session run has demonstrated them.
3. **The outcome-learning business objective is not operating yet.** The ledger contains candidate, validation and execution-decision events but no usable population of fills or matured counterfactual outcomes. Stored candidate decisions lack the completed-session and hold values needed by maturation. Current source has fields for them, but a new governed run is needed to prove population and maturation.
4. **The discovery analyses are useful model-risk evidence, not production-performance evidence.** They use TEST-condition books, reconstructed underlying outcomes and no executed option fills. They can identify algorithms that deserve correction or controlled experiments, but they cannot establish win rate, realised profitability or trading edge.
5. **The current release is not ready for production acceptance.** It may be exercised as a controlled integration candidate after the current-code blockers below are corrected and the failing tests are dispositioned. A clean `NORMAL_COMPLETED_SESSION` run and the subsequent post-open validation remain necessary for final acceptance.

## 2. What is in the folder

The folder is an independent test workspace rather than a single final report. It contains:

- the tester briefing, comprehension gate, pre-registered expectations, deviation register and run inventory;
- acceptance Tracks A-I and N;
- research-only discovery Tracks M1-M9;
- read-only copies of the production databases;
- stored-run probes and their outputs;
- a full governed pytest result;
- a state log; and
- an outcome census.

The acceptance tracks record **64 unique UAT IDs** before root-cause consolidation:

| Track | Subject | UAT findings |
|---|---|---:|
| A | run truth, finality, timestamps, macro identity | 10 |
| B | volatility and spread units, defaults, adapters | 6 |
| C | DOI valuation, reachability and ranking | 6 |
| D | lifecycle and contract identity | 9 |
| E | outcome labels and calibration | 4 |
| F | macro advisory, structure, capital boundary | 7 |
| G | Intelligence Lab and coaching presentation | 7 |
| H | ledger and outcome capture | 3 |
| I | replay, configuration, release governance | 9 |
| N | cross-cutting DDD invariants | 3 |

These are not independent. For example, the stale-executable condition appears as A7, D3, G4 and I4; the uncalibrated-probability condition appears as D8 and E4; spread ambiguity appears as B2, B3 and multiple discovery observations. Raw severity totals therefore overstate the number of separate faults.

## 3. Evidence quality and limitations

### 3.1 Strong evidence

The following evidence is strong and directly comparable to the current production tree:

- the audit briefing is pinned to `cc509cb`;
- the source citations for current modules resolve at that commit;
- focused probes have saved inputs and outputs;
- database analysis was performed against read-only copies;
- the full test suite completed with **1,881 passed, 44 failed and 4 skipped**;
- the tester separated CALL, PUT and OTHER in most acceptance measurements; and
- findings normally state the requirement, exposure, reproduction and closure condition.

### 3.2 Material limitations

The largest limitation is explicit in the pack: **no `NORMAL_COMPLETED_SESSION` run exists.** The two main runs were:

- `20260911_115904`: forced intra-session, dirty tree, Morning Validation, built on pre-remediation commit `00baa2b`;
- `20260910_150045`: forced intra-session, dirty tree, EOD mode, also pre-remediation.

They are valid for proving what the old artifacts contained, testing schema and lineage, and recreating historical failure mechanisms. They are not valid for proving that `cc509cb` currently fails or passes end to end.

The pack also has an internal progress-state inconsistency. `pytest/finished_utc.txt` and `pytest/full_run.txt` prove that the full suite finished, while `state_log.csv` still contains a `RUNNING` entry for that pytest step. The folder therefore appears paused in coordination/synthesis, not paused inside the completed full pytest execution. There is no consolidated, signed acceptance report that resolves all track findings into independent root causes.

The repository has no tracked production modifications at the assessed commit, but it has numerous untracked audit and temporary directories, including this test pack. That does not invalidate the source comparison, but a release manifest that ignores untracked runtime dependencies would be insufficient.

## 4. Confirmed current-code production impacts

### 4.1 Spread units can wrongly block otherwise reviewable contracts

**Audit references:** UAT-D-B2, B3 and the M7 spread reconstruction.  
**Validation:** confirmed in current source.

The Lab still reads `live_contract_spread_pct`, `contract_spread_pct` and `spread_pct` through one alias chain. Those upstream fields are not in one unit: some producers supply percentage points while others supply a fraction of mid. `contracts/lab_control.py` guesses the unit using `spread <= 1`, and writes the unresolved value back to `spread_pct`. `contracts/opportunity_tier.py` then treats bare `spread_pct` as `FRACTION_OF_MID`.

The primary stored book demonstrates the consequence: its spread values are percentage points, while the comparison book's values are fractions. The audit found 993 spread-only BLOCK rows in the primary book and reconstructed 584 of them as having a true spread at or below 25%: 349 CALL and 235 PUT.

**Business impact:** high and direct. A unit error can suppress monetisable contracts, distort manual-liquidity review, produce absurd quote-change values and materially reduce the displayed opportunity set. This is a current source defect, not merely an old-run artifact.

**Required outcome:** one canonical `spread_fraction_mid` field, one separately named `spread_pct_of_mid` display field, explicit unit metadata at every adapter, range validation, and no threshold code that guesses a unit from magnitude.

### 4.2 Current quote evidence can be labelled FRESH or EXECUTABLE without sufficient timestamp authority

**Audit references:** UAT-D-A4, A7, D3, G4 and I4.  
**Validation:** the historical exposure is proven; the enabling mechanism remains in current source.

The previous `_utc_now()` provider-timestamp fallback has been removed from the Morning quote base record, which is a real remediation. However:

- `morning_gate.py` still writes `quote_freshness = "FRESH"` unconditionally after the lifecycle assessment;
- `classify_current_executability()` only applies the age limit when `quote_age_seconds` is non-null;
- the transition to `EXECUTABLE_NOW` is driven by liquidity state, while the explicit post-open guard shown in Morning only handles a missing provider timestamp when `morning_execution_mode == POSTOPEN_CONTRACT_REFRESH`; and
- the historical Lab artifacts retained executable labels long after the quote exceeded the configured live TTL.

**Business impact:** critical at the execution-advisory boundary. The user's governing requirement is that Morning validates the thesis and provides current entry positioning without discarding a valid multi-day thesis. That does not permit an old or untimestamped quote to be described as executable now. Thesis validity and quote executability must remain separate.

**Required outcome:** thesis state may remain active for 1-20 days, but `EXECUTABLE_NOW` must require a same-session provider timestamp, a governed refresh mode and a freshness calculation at publication time. Old quotes must become `REQUOTE_REQUIRED` or `CURRENT_QUOTE_UNAVAILABLE` without invalidating or deleting the ticker thesis.

### 4.3 DOI v2 economics is not receiving the forecast-volatility input used elsewhere

**Audit reference:** UAT-D-C1.  
**Validation:** confirmed in current source.

The Options Intelligence lifecycle code can derive a forecast from `garch_forecast_vol`, `l3_vol_forecast`, HV, ATM IV and contract IV. The DOI production bridge is different: `canonical_data/dynamic_options_production.py` reads only `l3_forward_realised_vol`, `forecast_vol_annual_fraction` or `forward_realised_vol` from the Options Intelligence row. The assessed stored Options Intelligence schema carries none of those three fields.

The audit's current-code offline replay therefore produced 298/298 `NOT_EVALUATED_DATA_MISSING` contract assessments when wired as production, even after substituting a valid rate.

**Business impact:** high. The new reachable-target, friction-aware economics can exist in code while producing no usable assessments in the pipeline. That leaves the Lab dependent on legacy monetisability and ranking data.

**Required outcome:** the DOI bridge must consume one canonical annual forecast-volatility field with unit, calculation version, dataset identity and evidence cutoff. A replay must produce scenario grids and reachable targets for every otherwise complete directed family.

### 4.4 Contracts expiring inside the hold are discarded before they can be disclosed as horizon-limited

**Audit references:** UAT-D-C2 and C5.  
**Validation:** confirmed in current source and current tests.

`dynamic_options_family.py` requires remaining sessions to be at least the planned hold plus an eight-session buffer and structurally excludes contracts below that threshold. The v2 economics function can correctly return `HORIZON_LIMITED`, but the production family generator removes those contracts first. The audit measured 7,981 inside-hold contracts removed in the sample, split 4,118 CALL and 3,863 PUT.

**Business impact:** high relative to the agreed business rule. The pipeline is intended to retain valid ticker opportunities and let the human decide execution. An inside-hold contract may be unsuitable as the preferred expression, but it remains useful disclosure and may become active as the thesis evolves. Removing it prevents comparison and lifecycle monitoring.

**Required outcome:** retain it in the family as `HORIZON_LIMITED`, unranked and non-executable, with DTE and spread reasons disclosed separately. It must not be selected as preferred while it cannot survive the governed hold.

### 4.5 One ranking field mixes two materially different scoring formulas

**Audit reference:** UAT-D-C6.  
**Validation:** confirmed in current source.

`canonical_data/dynamic_options_valuation.py` writes v2 deterministic utility when it exists, otherwise falls back to the legacy v1 score in the same `ranking_score_uncalibrated` field while labelling both `DETERMINISTIC_UTILITY`. The required `ranking_score_uncalibrated_v1` disclosure field is absent. The audit measured a whole-sample rank correlation of only 0.147 between the formulas.

**Business impact:** high. A contract with complete v2 economics and a contract with missing or out-of-domain v2 economics can compete inside the same family on different scales. Preferred-contract selection and hysteresis can therefore be unstable or economically incoherent.

**Required outcome:** rank a family on one score kind only. Publish v1 under its own legacy disclosure field, make v2-null contracts explicitly unranked, and persist the score kind/version used for every comparison and switch.

### 4.6 The pipeline has two monetisability truths

**Audit reference:** DEV-10, Track C and the comprehension gate.  
**Validation:** confirmed in current source.

The EOD and Morning paths call `contracts/selected_contract_economics.py`. It prices against the structural target, uses an intrinsic floor plus a separate Black-Scholes disclosure, applies no governed friction and uses a 20% threshold. The DOI path calls `domain/contract_economics_v2.py`. It prices a reachable target and scenario grid, applies a spread-based friction model and uses the approved 25% floor.

The first engine continues to supply `monetisability_state`, which existing Lab and tier consumers read. DOI publishes a separate `doi_monetisability_state` that was not active in the reference runs.

**Business impact:** high. The same contract can be called monetisable by one engine and not currently monetisable by the other, for defensible but different reasons. Without one authoritative presentation contract, a user cannot know which answer governs the Lab.

**Required outcome:** preserve both structural payoff and reachable-scenario payoff as named disclosures, but derive one presentation state from the governed v2 scenario contract. Neither state should delete the ticker; it should describe current contract quality and support dynamic re-ranking.

### 4.7 Lab summary states can contradict thesis and execution evidence

**Audit references:** UAT-D-G2, G3 and G7.  
**Validation:** confirmed in current source; old-run contradictions are also demonstrated.

The Lab carries many legacy verdict columns alongside the newer presentation state, permitting `BLOCK` beside `GO`, `EXECUTE` or `BUY_SMALL`. The v4 projector defaults missing execution evidence to `EXECUTION_REVIEWABLE`, missing structure evidence to `DEVELOPING`, and missing ranking kind to `DETERMINISTIC_UTILITY`. Its presentation function recognises only two invalid tokens but hardcodes `THESIS_ACTIVE` into reasons for many other thesis states.

**Business impact:** high for human use even when execution authority remains deterministic. The Intelligence Lab is the user's single operational surface; contradictory or invented-positive defaults make correct manual interpretation unnecessarily difficult.

**Required outcome:** project one authoritative summary from explicit thesis, contract and execution states; preserve legacy fields only in lineage/detail; represent missing as missing; exhaustively test every allowed thesis × contract × execution combination.

### 4.8 Uncalibrated quantities remain probability-shaped in production contracts

**Audit references:** UAT-D-D8 and E4.  
**Validation:** genuine contract risk; current visible-UI severity is not fully proven.

The current Lab materializer still carries `win_prob_predicted`, `layer2__adjusted_prob_target_hit` and `ev3_p_target` fields. The v4 projector exposes a ranking kind but not a complete probability disclosure. The historical book populated probability-named values while outcome-learning state was `INSUFFICIENT_OUTCOMES`.

The active HTML clearly labels liquidity maturation values as monitoring estimates rather than probabilities, which is good. It does not establish that every legacy probability-named field is visibly rendered. The raw P0 label in the pack should therefore be read as:

- **P0 if an uncalibrated value is shown to the trader or used as a probability in an authority calculation;**
- **P1 data-contract defect if it remains in artifacts but is neither displayed nor authoritative.**

**Required outcome:** any `p_*`, `probability` or `win_prob` output must be null unless its calibration state, model ID, training cutoff and effective sample size are present and accepted. Deterministic scores must be named scores, not probabilities.

### 4.9 Macro routing and scenarios are currently unreliable, but macro remains advisory

**Audit references:** UAT-D-F1, F2, F3 and F4.  
**Validation:** current code contains the two-join and vocabulary mismatch mechanisms.

Macro advisory data is joined twice. The first join can run before sector backfill; the second join uses a different routing map and overwrites fields. `usmi_routing_key` is not emitted; `usmi_alignment_priority` is used instead. The scenario evaluator expects structured scenarios, while the input packet can contain free-text `conditions_all` or an empty scenario structure. In the stored run, all 1,444 rows were `SECTOR_UNMAPPED`/neutral and scenarios were unresolved despite populated GICS sectors.

**Business impact:** medium. It damages trader context, Worker 3 narrative quality and sector/ticker money-flow interpretation. It should not change direction, delete a ticker, select a contract or grant execution, so it is not by itself a capital-authority blocker. If any old coaching code places macro in a pass/fail `CORE` set, that consumer violates the advisory-only boundary and becomes a high-priority presentation defect.

**Required outcome:** one post-classification macro join, one routing vocabulary, structured predicates with observed values and timestamps, and property tests proving changes to macro cannot change direction, population, preferred contract or execution permission.

### 4.10 Capital-allocation remnants still exist upstream

**Audit reference:** UAT-D-F5 and I7.  
**Validation:** confirmed, with mitigation in the final Lab writer.

The final Lab materializer now overwrites `position_size_display` with `HUMAN DETERMINED`, which matches the capital-agnostic requirement. However, account size, risk budget and suggested contract count remain in production-reachable modules and configuration.

**Business impact:** medium today if those fields are hidden and non-authoritative; high if any ranking, filtering or coaching consumer reads them. They also create unnecessary future regression risk.

**Required outcome:** remove capital and affordability inputs from the production decision graph, keep the Lab human-determined display, and enforce the boundary with a dependency/property test rather than a late display override alone.

### 4.11 Outcome capture cannot yet deliver pipeline learning

**Audit references:** UAT-D-E1-E4 and H1-H3; `outcome_census.md`.  
**Validation:** proven for stored data; current writer improvements require a new run.

The copied ledger contains 4,931 candidate decisions, 1,679 validations and 1,679 execution decisions, but zero useful fills, zero outcome observations and only one QA outcome. All 4,931 stored candidate records have null `planned_hold_sessions`; the 3,252 EOD records examined also have null completed sessions. Consequently, the maturation job marked all 3,252 candidates ineligible.

Current source now attempts to populate `completed_session` and `planned_hold_sessions`, but this depends on upstream row population. No current-run artifact proves it.

**Business impact:** high for the strategic business outcome, not necessarily for today's deterministic trade presentation. Until this is corrected and observed, the pipeline cannot learn systematically from presented-but-not-taken trades, calibrate probabilities, or distinguish a bad thesis from a bad contract or bad entry timing.

**Required outcome:** every directed candidate decision records completed session, integer hold, origin, target/invalidation, forecast budget and exact selected family. Maturation must emit a named reason for every ineligible/deferred row and append counterfactual outcomes without inventing fills.

### 4.12 Release evidence and regression status are not acceptable yet

**Audit reference:** Track I and `pytest/failures_list.txt`.  
**Validation:** confirmed.

The full governed suite exited non-zero: 1,881 pass, 44 fail, 4 skip. Those 44 failure elements correspond to 33 listed cases; some are intentionally old negative assertions and some are likely fixture/contract drift, so they are not automatically 33 product defects. However, 14 failing cases were not disclosed in the baseline defect register or claim sheets, including Lab cache refresh, Lab STRANGLE/direction behavior, EV3 order and opportunity-book/learning feedback.

There is no full stored-run replay that rebuilds a governed book and compares hashes under an expected-difference manifest. Governed constants are incomplete and duplicated in code; runtime environment switches can still alter production behavior outside one immutable release profile. Release manifests and rollback evidence are incomplete.

**Business impact:** high release risk. Even correct algorithms can be integrated incorrectly, and a failed suite means the current commit cannot be signed off solely from offline evidence.

**Required outcome:** triage every failure as product defect, obsolete assertion or invalid fixture; correct the former and replace the latter with a positive governed assertion. The complete governed suite must pass or contain an approved, explicit baseline exception. Add a true pinned-input replay and expected-difference contract.

### 4.13 Credential hygiene finding is genuine

**Audit reference:** UAT-D-I9.  
**Validation:** confirmed without reproducing any secret value in this report.

Two tracked modules contain provider-key-shaped fallback literals in environment lookups. A release-diff-only scan did not cover the whole repository.

**Business impact:** security and provider-account exposure, independent of trading calculations.

**Required outcome:** remove and rotate exposed credentials, require environment/secret-store injection with no literal fallback, and run a whole-tree plus history-aware secret scan.

## 5. Findings that are historical or awaiting current-run proof

The following findings are genuine descriptions of the reference runs, but should not be presented as current production failures without a new run:

| Finding | Historical evidence | Current-source assessment | Remaining proof |
|---|---|---|---|
| Evidence cutoff earlier than provider requests | proven across stored runs | run-condition and provider-finality integration now exists | normal run with zero governed post-cutoff requests, or a separately identified refresh cutoff |
| Intra-session chains registered as completed | proven | provider-finality domain/canonical modules exist | completed-session run with denominator and timestamp-distribution evidence |
| Provider timestamp fabricated from current time | proven for 226 rows | direct `_utc_now()` quote fallback removed | post-open run with distinct provider and fetch timestamps |
| TEST run labelled PRODUCTION/EXECUTION_READY | proven | current run-planning code writes condition and baseline eligibility | forced/dirty test proving it cannot receive a production label |
| Macro latest file not recoverable by packet ID | proven for old runs | builder and orchestrator now archive packet ID/hash | current run with one consistent, loadable archived packet identity |
| DOI stopped at rate unavailable | proven for all 1,218 old families | rate observation integration exists | current DOI run with rate lineage and valued families; forecast-vol gap must also be fixed |
| Lab position size not human determined | proven in old run | final materializer now writes `HUMAN DETERMINED` | current book and source-graph test showing no upstream allocation affects decisions |
| Stored ledger decisions cannot mature | proven | current ledger writer has the fields but relies on upstream values | current run showing complete eligible decision rows and later maturation |

## 6. Research-only findings and their genuine value

The M-series tracks are correctly labelled `RESEARCH_ONLY`. Their findings should inform design and data collection but must not be promoted into live policy yet.

### 6.1 Forecast-volatility bias

Historical reconstruction suggests forecast volatility is generally above realised volatility and often above IV. The size varies materially by session, IV source, direction and horizon. The forecast adds information for some pooled/CALL regressions, but the result is fragile to IV measurement and rests on very few independent forecast sessions.

**Genuine impact:** model-risk evidence. Keep `bias_multiplier_applied = false` until a dated validation report passes. Do not conclude that the forecast is useless; conclude that a static correction is not yet justified.

### 6.2 Monetisability currently assumes a scenario is reached rather than estimating its probability

Track M7 shows that the positive headline is largely driven by pricing a 1.5-sigma reachable spot as if it is achieved. Under the research Monte Carlo, many positive CALL and PUT rows become non-positive after target-before-invalidation probabilities are introduced. Exact percentages are not production evidence because inputs came from a TEST snapshot and forecast vol was substituted.

**Genuine impact:** important model-premise risk. The deterministic scenario payoff is useful, but it is not expected value. The Lab should call it scenario monetisability until calibrated transition/outcome probabilities exist.

### 6.3 Filters may remove useful candidates

Track M6 retrospectively finds some removed groups moved more or hit barriers more often than survivors, including Options scope and pre-book EIL filters. These comparisons use reconstructed underlying outcomes, overlapping windows and old TEST-run populations.

**Genuine impact:** a strong reason to retain candidates with named monitoring states and measure counterfactual outcomes. It is not sufficient evidence to reverse a gate or claim higher profitability.

### 6.4 CALL concentration and weak state diversity

The reconstructable history is 82% CALL and is dominated by two hidden states and the 6-10-day horizon. Most fine-grained calibration cells are too small, and 11-20-day evidence is nearly absent.

**Genuine impact:** the current data cannot support a richly segmented ML model or confident CALL/PUT comparison. The ledger must accumulate clean, governed decisions across more sessions before activation.

### 6.5 Data bloat and ambiguous contracts

The primary 19-row Lab signal book contains 502 fields, including 200 constant fields, 62 all-null fields, 58 duplicate fields and 15 ambiguous-unit fields. The wider pipeline has thousands of produced-but-unread or duplicated fields.

**Genuine impact:** maintainability, lineage and integration risk. It does not prove the pipeline's core logic is wrong, but it explains why incompatible aliases and silent defaults recur. Schema reduction should follow authority and contract correction, not precede it.

## 7. Findings whose severity should be qualified

1. **The raw P0 count is inflated by duplicate filing.** Stale-executable behavior is one root cause represented in at least four tracks; uncalibrated probability is one root cause represented in two tracks.
2. **Old forced-run artifacts cannot close or reopen a current-code claim by themselves.** They prove the historical mechanism and provide replay fixtures.
3. **Macro defects are advisory unless a downstream consumer turns macro into a pass/fail gate.** The coaching dossier currently appears to do so and should be corrected, but the deterministic execution gate does not appear to consume macro.
4. **The European BSM intrinsic-floor difference is a specification/model-choice conflict, not automatically a pricing bug.** It must be resolved by choosing and naming the model; silently claiming pure European BSM while flooring the output is the defect.
5. **The absence of three separate contract state machines is a design non-compliance, but the business impact comes from conflation, not the number of enums.** One well-defined state object could be acceptable if it independently represents identity, present executability and developing activity.
6. **The 44 failing tests are not 44 current production defects.** They still prevent clean release evidence until each is explicitly dispositioned.
7. **Retrospective underlying hit rates are not option P&L.** No fill data exists, so the research tracks cannot validate monetisation profitability.

## 8. Root-cause view

The daily defects are not random. They concentrate in six architectural causes:

1. **One concept has multiple names and units.** Examples: spread fraction vs percentage, expected-move cumulative vs differenced, route key vs alignment priority.
2. **Multiple contexts calculate the same business conclusion.** Examples: legacy and DOI monetisability, two macro joins, legacy and v2 utility in one rank field.
3. **Missing data is converted into a positive/default state.** Examples: FRESH, EXECUTION_REVIEWABLE, DEVELOPING and DETERMINISTIC_UTILITY defaults.
4. **Current-state execution evidence is conflated with multi-day thesis validity.** A valid 1-20-day thesis can coexist with a stale or unavailable execution quote; the pipeline must show both truths independently.
5. **Offline feature completeness is being mistaken for production integration.** Provider finality, DOI, lifecycle, macro archive and learning components exist, but no current normal run proves the entire handoff.
6. **Release governance does not yet bind the whole runtime.** Untracked dependencies, environment switches, incomplete manifests, missing replay and unresolved tests make behavior difficult to reproduce.

## 9. Recommended closure order

This order maximises business value and prevents one fix from being masked by another:

### Gate 1 — protect the trader-facing decision surface

1. Canonicalise spread units end to end and remove magnitude guessing.
2. Separate thesis validity from current quote executability; remove unconditional FRESH and require provider timestamp/run condition for EXECUTABLE_NOW.
3. Correct Lab v4 defaults and presentation vocabulary so missing evidence cannot appear positive and BLOCK/GO cannot coexist in the authoritative summary.
4. Suppress or explicitly label every uncalibrated probability-shaped field.

### Gate 2 — make contract monetisability internally coherent

5. Wire canonical forecast volatility into DOI.
6. Retain inside-hold contracts as horizon-limited evidence rather than deleting them.
7. Eliminate mixed v1/v2 family ranking; publish score kinds separately.
8. Make v2 reachable-scenario monetisability the single presentation contract, retaining structural payoff only as disclosure.
9. Recompute economics atomically whenever the exact contract or quote changes and persist supersession lineage.

### Gate 3 — restore advisory and DDD boundaries

10. Replace the two macro joins with one post-classification join and keep macro advisory-only in the Lab and coaching outputs.
11. Remove production-reachable account/risk-budget/capacity calculations.
12. Centralise thesis-owned fields and prevent downstream writers from fabricating or overwriting target, invalidation and hold.
13. Remove credential literals and add whole-tree secret scanning.

### Gate 4 — make learning operable

14. Populate completed session, planned hold, volatility budget and exact contract-family identity on every candidate decision.
15. Record presentation decisions and fills separately; never infer a fill from an execution decision.
16. Mature counterfactual candidate outcomes with named deferral/ineligibility reasons.
17. Keep calibration/model activation gated until dated held-out evidence and minimum samples exist.

### Gate 5 — prove the release

18. Add focused CALL/PUT/horizon contract tests for every corrected boundary.
19. Triage and resolve all 33 currently failing test cases; do not merely delete contradictory assertions.
20. Run the complete governed regression suite with zero undisclosed failures.
21. Produce a hash-bound release manifest, governed constants profile, expected-difference manifest and rollback rehearsal.
22. Run a clean `NORMAL_COMPLETED_SESSION` cycle.
23. Run the next valid `PREOPEN_THESIS_CHECK` and `POSTOPEN_CONTRACT_REFRESH` phases.
24. Reconcile population, quote timestamps, monetisability, ranking, macro advisory, Lab presentation and ledger eligibility before production sign-off.

## 10. Acceptance decision

**Decision: the AVS-TD-001 findings have genuine impact, but the pack is not itself a production verdict.**

- **Do not sign off the current commit as production-ready from the stored runs.**
- **Do not discard the pack because the runs are old.** Its current-source analyses have exposed real integration defects.
- **Do not treat research hit rates or simulated EV as trading proof.** They are hypotheses and model-risk diagnostics.
- **Do use the pack as the defect and acceptance basis after consolidating duplicate UAT IDs into the root causes above.**

The business outcome remains achievable. The pipeline already has the essential assets—governed thesis generation, canonical option evidence, lifecycle persistence, deterministic execution authority, an Intelligence Lab, macro advisory data and an append-only ledger. The immediate problem is not lack of data or lack of models. It is inconsistent contracts between these components. Correcting the canonical units, state boundaries, single monetisability truth and release evidence will have more production value than adding another scoring layer.

## 11. Principal evidence reviewed

- `_tester_briefing.md`
- `comprehension.md`
- `expectations.md`
- `deviations.md`
- `outcome_census.md`
- `run_inventory.csv`
- `state_log.csv`
- `track_A.md` through `track_I.md`, `track_N.md`
- `track_M1.md` through `track_M9.md`
- `pytest/full_run.txt`, `pytest/failures_list.txt`, `pytest/junit_full.xml`
- saved probes and read-only database copies under this audit folder
- current production source at commit `cc509cb`, especially `morning_gate.py`, `contracts/lab_control.py`, `contracts/opportunity_tier.py`, `domain/option_contract_liquidity.py`, `canonical_data/dynamic_options_production.py`, `canonical_data/dynamic_options_family.py`, `canonical_data/dynamic_options_valuation.py`, `contracts/selected_contract_economics.py`, `domain/contract_economics_v2.py`, `domain/presentation.py`, `domain/lab_signal_book_v4.py`, macro advisory modules and decision/outcome ledger modules.
