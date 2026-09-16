# AVS-TD-001 root-cause and remediation analysis

**Assessment date:** 2026-09-13  
**Production branch:** `avs-fix-001`  
**Production commit assessed:** `cc509cbe7fa60a3fb2f7a37a164a66f27588251d`  
**Mode:** read-only. The paused pipeline was not resumed. No provider was called, no test was rerun, and no production source, configuration, database or runtime artifact was changed.

## 1. Executive decision

The AVS-TD-001 defects do not all represent current production failures, but an implementation is not considered resolved merely because its component code exists. If its production handoff can fail, silently fall back, commute a different meaning or publish an apparently complete row without the required evidence, that integration failure is part of the production root cause.

The corrected root-cause disposition is:

| Disposition | Consolidated items | Meaning |
|---|---:|---|
| Active production or integration root causes | 12 | Current source or an unclosed production handoff can produce an incorrect, contradictory, semantically incomplete or falsely complete result. |
| Evidence-only acceptance dependencies | 2 | Source and integration paths exist and no conflicting fallback was identified, but a normal governed cycle is still needed to prove production operation. |
| Resolved component mechanisms | 8 examples | Current source contains the required component behavior, but each mechanism remains governed by its end-to-end integration root cause where applicable. |
| Test/specification defects | 9 groups | Tests assert that functionality is absent, use invalid calendar fixtures, inspect source text instead of behavior, or target out-of-scope STRANGLE handling. |
| Research/evidence gaps | 3 | More normal-session outcomes are required; these are not deterministic pipeline defects. |

The most important active causes are not missing algorithms. They are incomplete migrations and handoffs between old and new bounded contexts:

1. canonical values are created but legacy aliases still guess units;
2. thesis validity is conflated with current quote executability;
3. contract-family generation deletes evidence before the v2 economics domain can classify it;
4. legacy and v2 formulas share fields or compete as parallel truths;
5. the Lab invents favourable-looking defaults for missing evidence; and
6. release tests contain historical negative assertions that were never retired after implementation.

### 1.1 What “genuine data” means in this assessment

The pipeline produces genuine data only when all three conditions hold:

1. **Evidence truth:** the value comes from the identified provider, canonical store or deterministic calculation with its real timestamp, session, unit and dataset identity.
2. **Semantic truth:** the consumer interprets the value in the same unit and business meaning emitted by the producer.
3. **Integration truth:** the required value reaches the intended bounded context without silent substitution, legacy fallback, premature exclusion or favourable defaulting.

Therefore:

- a correct GARCH value that never reaches DOI is not genuine DOI valuation evidence;
- a valid thesis paired with an old quote may remain a genuine thesis, but it is not genuine current execution evidence;
- a legacy monetisability answer substituted when v2 is unavailable is not a genuine v2 answer;
- a missing outcome event does not corrupt today's thesis, but it makes any claim that the learning loop is operating untrue; and
- an advisory macro failure does not invalidate a trade, but the Lab must disclose `ADVISORY_DATA_UNAVAILABLE` rather than present a neutral interpretation as observed fact.

No integration failure may silently convert `UNAVAILABLE`, `NOT_EVALUATED` or `DATA_EXCEPTION` into a favourable or complete-looking state.

The pipeline should not be signed off from the current AVS-TD-001 suite result. It also should not be subjected to another broad rewrite. The right action is a bounded repair of the active integration defects, followed by correction of the stale tests and a controlled completed-session acceptance cycle.

## 2. Root-cause method

Each issue was traced across five boundaries:

1. **Symptom** — what the tester or trader observes.
2. **Producer** — where the value or state originates.
3. **Commutation** — how it changes name, unit, timestamp or meaning between stages.
4. **Consumer/authority** — which calculation or UI decision uses it.
5. **Verification** — whether current code, current tests and current run evidence agree.

An issue is classified as resolved only when the current mechanism is absent or replaced. A component existing in source is not enough to prove end-to-end acceptance; that requires a current governed artifact.

## 3. Active production defects

### RCA-01 — Spread units remain ambiguous after the canonical adapter

**Severity:** P0 for candidate suppression and execution classification.  
**Status:** ACTIVE.

**Observed symptom**

The same economic spread can be represented as `0.20` or `20.0`. The Lab or tier logic can therefore treat 20% as 2,000%, or apply different thresholds to equivalent quotes. The historical reconstruction found hundreds of CALL and PUT rows capable of being blocked solely by this mismatch.

**Root cause**

`domain/quote_units.py` is correctly strict, but it is not the only path into production. Legacy consumers still combine percentage-point and fractional aliases:

- `contracts/lab_control.py:2004-2007` reads mixed aliases and guesses the unit with `spread <= 1`;
- `contracts/lab_control.py:2639` republishes the unresolved value as `spread_pct`;
- `contracts/opportunity_tier.py:83-98` assumes a bare `spread_pct` is `FRACTION_OF_MID`;
- `morning_gate.py:2723-2724` and `morning_gate.py:2958` guess the unit again; and
- `contracts/selected_contract_economics.py:463` names a percentage-point output `live_contract_spread_pct`, while other paths use that name for a fraction.

This is an incomplete schema migration: a correct value object was introduced, but shared Lab and Morning paths were not converted.

**Required fix**

1. Make `spread_fraction_mid` the only computational field.
2. Make `spread_pct_of_mid` the only percentage-point display field.
3. Require `spread_unit` at every legacy ingress adapter.
4. Delete all magnitude-based conversion logic.
5. Deprecate ambiguous aliases at the final-book boundary; retain them only in lineage payloads if historical replay requires them.
6. Reject impossible fractions and crossed/invalid quotes before tiering.

**Acceptance evidence**

- property tests showing `0.20 FRACTION_OF_MID` equals `20.0 PERCENT_OF_MID`;
- CALL and PUT threshold-boundary tests;
- one stored-chain replay with zero implicit-unit conversions; and
- final-book diagnostics reconciling source-unit counts to candidate population.

### RCA-02 — A valid multi-day thesis is being used to excuse an old execution quote

**Severity:** P0 at the human execution boundary.  
**Status:** ACTIVE.

**Observed symptom**

A 1-20-session thesis may correctly remain active, while its option quote is minutes or hours old. Current code can still label that contract `FRESH` or permit an executable state without a provider-authoritative timestamp.

**Root cause**

An earlier business correction—“do not invalidate a swing thesis merely because the quote aged”—was applied in the wrong bounded context:

- `morning_gate.py` no longer fabricates the provider timestamp from `_utc_now()`, which is correct;
- but `_morning_liquidity_lifecycle()` still falls back to `live_options_fetched_at` when calculating age;
- it then writes `quote_freshness = "FRESH"` unconditionally;
- `domain/option_contract_liquidity.py` applies TTL only when age is present, so missing age can reach `EXECUTABLE_NOW`;
- `pipeline_interpreter/evidence_resolver.py:182-232` deliberately ignores `STALE` exact-option and underlying quotes; and
- `contracts/quote_change_evidence.py` uses fetch time as a timestamp fallback and computes freshness with a hard-coded 60-second TTL, but never makes stale a comparison state.

The thesis lifecycle and execution-observation lifecycle are two different aggregates. Preserving the thesis must not assert that its old quote is executable.

**Required fix**

1. Keep `thesis_state` active until target, invalidation, time stop or governed evidence changes it.
2. Require a provider quote timestamp for `EXECUTABLE_NOW`.
3. Preserve provider timestamp and fetch timestamp as separate fields; never substitute one for the other.
4. Move quote TTL to governed configuration. Use the approved execution-observation window, not the current hard-coded 60 seconds.
5. Map old/missing execution evidence to `REQUOTE_REQUIRED` or `CURRENT_QUOTE_UNAVAILABLE` without deleting the ticker, changing direction or invalidating the thesis.
6. Let post-open Morning contract refresh own provider acquisition. The Interpreter should detect and request refresh, not independently fetch market data.

**Acceptance evidence**

- a state-matrix test proving `THESIS_ACTIVE + QUOTE_STALE` is valid but not executable;
- no `EXECUTABLE_NOW` row with null provider timestamp;
- no fetch timestamp copied into a provider timestamp field;
- governed TTL boundary tests; and
- a post-open replay proving the thesis population is unchanged while execution states refresh.

### RCA-03 — Horizon-limited contracts are removed before they can be classified

**Severity:** P1.  
**Status:** ACTIVE.

**Observed symptom**

Contracts expiring inside or near the planned hold disappear from the family. The v2 economics model contains a correct `HORIZON_LIMITED` state, but production users never see it for contracts already removed upstream.

**Root cause**

`canonical_data/dynamic_options_family.py:285,347-348` calculates required sessions as planned hold plus buffer and structurally excludes contracts with insufficient runway. `domain/contract_economics_v2.py:94-97` can classify such a contract as `HORIZON_LIMITED`, but it is downstream of the exclusion.

The focused Stage 2-5 test proved the domain calculator, not the full generator-to-valuation path. The claim “horizon-limited contracts are retained” therefore exceeded its evidence.

**Required fix**

1. Exclude only expired, malformed or thesis-side-incompatible contracts from the structural family.
2. Retain inside-hold contracts with `HORIZON_LIMITED` applicability and exact remaining-session evidence.
3. Prevent them from becoming preferred while they cannot cover the governed hold.
4. Preserve them in alternatives and lifecycle monitoring so improving liquidity or a changed remaining hold can be observed.

**Acceptance evidence**

An integration test must start with a mixed-expiry chain, pass through family generation, valuation, ranking and Lab projection, and reconcile every input contract as excluded-for-valid-structural-reason, ranked, unranked or horizon-limited.

### RCA-04 — One ranking field mixes legacy and v2 score scales

**Severity:** P1.  
**Status:** ACTIVE.

**Observed symptom**

Contracts with complete v2 economics can compete with contracts scored by the legacy formula under the same `ranking_score_uncalibrated` field. Preferred selection and hysteresis can therefore compare unlike values.

**Root cause**

`canonical_data/dynamic_options_valuation.py:438-442` writes v2 utility when available and silently falls back to v1 utility otherwise. Metadata at line 424 calls both `DETERMINISTIC_UTILITY`. `canonical_data/dynamic_options_ranking.py:290` consumes the common field without score provenance.

The compatibility fallback was allowed to enter the decision comparison domain. A fallback may support disclosure, but it cannot participate in the same rank ordering unless it is transformed and validated onto the same scale.

**Required fix**

1. Publish `ranking_score_v2` and `ranking_score_legacy_v1` separately.
2. Rank only records with the selected governed score kind and version.
3. Retain v2-incomplete contracts as `UNRANKED_DATA_INCOMPLETE`; do not delete them.
4. Persist the compared score kind/version on every preferred and supersession decision.
5. Apply hysteresis only between comparable scores.

### RCA-05 — Legacy and v2 monetisability are parallel, conflicting truths

**Severity:** P1.  
**Status:** ACTIVE.

**Observed symptom**

The same contract can be `MONETISABLE` in the legacy target-at-expiry engine and `NOT_MONETISABLE` or `INDETERMINATE` in the reachable-scenario, friction-aware v2 engine.

**Root cause**

`contracts/selected_contract_economics.py` intentionally retains the legacy `monetisability_state` for existing consumers, using a 20% threshold and different payoff assumptions. `domain/contract_economics_v2.py` uses reachable target, scenario volatility, friction and the governed 25% floor. `domain/lab_signal_book_v4.py` prefers DOI but falls back to legacy state.

The v2 implementation was added alongside the existing conclusion instead of replacing the presentation contract. This preserved backward compatibility at the cost of semantic authority.

**Required fix**

1. Define one trader-facing `contract_monetisability_state` derived from v2 whenever v2 is applicable.
2. Rename legacy output to `structural_payoff_disclosure_v1`; it must never masquerade as the current presentation state.
3. If v2 evidence is missing, show `NOT_EVALUATED_DATA_MISSING`, not a legacy answer presented as equivalent.
4. Keep all ticker theses; monetisability governs contract quality and re-ranking, not opportunity deletion.
5. Recompute atomically when the exact contract, underlying spot or quote changes.

### RCA-06 — Lab v4 converts missing evidence into plausible positive states

**Severity:** P1.  
**Status:** ACTIVE.

**Observed symptom**

The Lab can show a reassuring summary even when evidence is absent, and legacy `BLOCK`, `GO`, `BUY_SMALL` or `EXECUTE` fields can coexist with the newer presentation state.

**Root cause**

`domain/lab_signal_book_v4.py` defaults missing execution to `EXECUTION_REVIEWABLE`, structure to `DEVELOPING` and ranking kind to `DETERMINISTIC_UTILITY`. `domain/presentation.py` recognises only two invalid tokens and otherwise embeds `THESIS_ACTIVE` in its reason. The projector is a small happy-path mapping rather than an exhaustive state transition table.

This violates the system principle that missing evidence must remain missing. It is particularly damaging because the Lab is the user's single operational surface.

**Required fix**

1. Centralise canonical thesis, contract, execution and presentation vocabularies.
2. Use `NOT_EVALUATED`, `MISSING` or `UNKNOWN` defaults, never favourable inferred states.
3. Build an exhaustive thesis × contract × execution transition table.
4. Show the four independent truths explicitly: thesis, preferred-contract quality, present execution observation, advisory macro.
5. Move legacy verdicts to lineage/detail and prevent them from being rendered as co-authoritative summaries.

### RCA-07 — Probability-shaped fields can escape without calibration provenance

**Severity:** P1 if displayed/authoritative; P2 if retained only in audit payloads.  
**Status:** ACTIVE CONTRACT RISK; visible severity requires UI verification.

**Observed symptom**

Fields such as `win_prob_predicted`, `ev3_p_target` and adjusted target-hit probabilities exist in production contracts even though the learning gate reports insufficient outcomes.

**Root cause**

Legacy actuarial and EV fields were copied into the final book without one common calibration gate. The v4 read model exposes ranking kind, but does not require complete calibration metadata for every probability-shaped value.

**Required fix**

1. Null all `p_*`, `probability` and `win_prob*` fields unless calibration state is accepted.
2. Require model ID, training cutoff, effective sample, calibration version and held-out metrics.
3. Rename deterministic or scenario quantities as scores/assumptions, never probabilities.
4. Keep raw legacy values only in governed audit lineage if required for research.

### RCA-08 — Macro is joined twice using different routing semantics

**Severity:** P2 because macro is advisory; P1 if any consumer uses it as a gate.  
**Status:** ACTIVE.

**Observed symptom**

Populated sector data can still produce `SECTOR_UNMAPPED`, neutral routing or unresolved scenarios. Worker 3 and the trader may receive a weaker or contradictory money-flow narrative.

**Root cause**

`contracts/interpreter_macro_context.py` and `domain/macro_advisory_context.py` both project US Money Index context. One emits `usmi_alignment_priority` as the advisory priority; the other writes the routing key into the same field. `usmi_routing_key` is not consistently present. One join can occur before sector backfill; the later join can overwrite fields with a different vocabulary.

**Required fix**

1. Make one post-classification macro-context service the sole producer.
2. Emit separate `usmi_routing_key`, `usmi_alignment`, `usmi_priority` and `usmi_reason` fields.
3. Evaluate only structured scenario predicates with observed value, timestamp and source.
4. Prove by property test that macro changes cannot alter direction, ticker population, preferred contract, thesis validity or execution permission.

### RCA-09 — Deactivated capital allocation remains reachable upstream

**Severity:** P1 architecture and authority-boundary violation.  
**Status:** ACTIVE UNTIL ALL PRODUCTION REACHABILITY IS REMOVED OR HARD-DEACTIVATED.

**Observed symptom**

The final Lab correctly displays `HUMAN DETERMINED`, but upstream modules still calculate allocation, risk budgets and suggested contract counts. Even if later overwritten, those calculations must not be part of the AVSHUNTER production decision graph.

**Root cause**

Retirement was implemented as a final display override rather than removal from the production dependency graph. `trade_book_builder.py`, `execution_intelligence_runner.py` and `intelligent_orchestrator.py` still contain production-reachable account/risk inputs. This is not an incomplete feature awaiting future activation. Capital allocation is outside the pipeline's bounded context and authority.

**Required fix**

1. Keep all capital-allocation and position-sizing features deactivated.
2. Remove account size, affordability, risk-budget, Kelly sizing and suggested-contract inputs from monetisability, ranking, filtering, pipeline membership and execution-state computation.
3. Remove or hard-disable production orchestrator calls into allocation logic. A configuration flag must default to false, reject unrecognised values and never be enabled by AUTO or a standard run profile.
4. Do not publish contract quantity, capital permission, affordable/not-affordable or percentage allocation as governed pipeline conclusions.
5. Permit only the display statement `HUMAN DETERMINED`, plus option premium and contract economics needed by the human to make an independent decision.
6. If allocation code is retained for historical compatibility, isolate it outside the production decision graph with no authority to write Lab, thesis, contract-ranking, execution or ledger-decision states.
7. Add dependency and mutation tests proving that changing account size, risk budget or sizing-related environment variables cannot change any pipeline output other than an explicitly isolated, non-production research artifact.

**Acceptance evidence**

- no standard, forced, replay, evening, Morning or Interpreter path invokes capital-allocation logic;
- no active release configuration can enable it;
- the final Lab and Worker 3 contracts contain no computed position quantity or allocation recommendation;
- `HUMAN DETERMINED` is the only capital-related trader-facing state; and
- identical market evidence produces byte-equivalent governed decision outputs under different account-size/risk-budget environment values.

### RCA-10 — Tracked source contains provider credential fallbacks

**Severity:** P0 security.  
**Status:** ACTIVE.

**Observed symptom**

Two tracked modules contain provider-key-shaped literal fallbacks in environment lookups.

**Root cause**

Legacy convenience defaults survived repository cleanup, while prior secret checks focused on changed files rather than the whole tracked tree and history.

**Required fix**

1. Remove literal fallbacks from `avshunter_db_update.py` and `bond_macro_intelligence.py`.
2. Require environment or an approved local secret store and fail with a non-secret diagnostic.
3. Rotate the affected provider credentials.
4. Scan the tracked tree and Git history; never print secret values in reports or logs.

## 4. Integration root causes and acceptance dependencies

### RCA-11 — DOI forecast-volatility bridge

**Prior finding:** DOI could not value otherwise valid families because its input CSV lacked the canonical annual forecast-volatility field.  
**Current status:** COMPONENT IMPLEMENTED; PRODUCTION INTEGRATION REMAINS ACTIVE UNTIL RECONCILED.

`intelligent_orchestrator.py:5650-5659` now runs GARCH, invokes `merge_garch_into_enriched()`, and only then runs DOI. The merge now writes `l3_*` fields into the Options Intelligence CSV—the boundary read by `run_completed_session_doi()`. `canonical_data/dynamic_options_production.py:311-314` consumes `l3_forward_realised_vol`. This corrects the missing component path.

The integration is not yet closed because:

- `merge_garch_into_enriched()` treats merge exceptions as non-critical and returns success;
- DOI itself is advisory and can fail while the pipeline continues; and
- the Lab falls back from `doi_monetisability_state` to legacy `monetisability_state`.

The result can therefore look populated while the governed v2 input or assessment is absent. That is not genuine DOI data; it is a different legacy conclusion occupying the same user journey.

**Why the audit still reported failure:** its stored artifacts and replay describe the earlier schema, before this bridge was added. The historical component finding is fixed, but the production handoff and failure semantics remain unaccepted.

**Required integration fix:** do not rebuild the bridge. Add a production-boundary reconciliation result containing input rows, GARCH matches, Options rows updated, DOI families assessed, exceptions and final Lab projections. If the bridge or DOI fails, preserve the ticker but publish `DOI_NOT_EVALUATED_DATA_UNAVAILABLE`; never substitute the legacy state as if it were v2. A current run must demonstrate full accounting before this RCA closes.

### RCA-12 — Quote-change comparison and size propagation

**Current status:** COMPONENTS RESOLVED; INTEGRATION IS PART OF ACTIVE RCA-01 AND RCA-02.

Current source now:

- propagates option and underlying bid/ask sizes;
- computes quote-change evidence;
- detects a zero baseline;
- detects coarse market-profile cadence;
- classifies an exact-contract change; and
- calls the canonical freshness evaluator.

Several AVS-TD tests explicitly asserted that those functions did not exist. Their failures are evidence of implementation, not regression. However, the handoff is not genuine end to end while snapshot builders can use fetch time as quote time, carry ambiguous spread units or omit the trader-facing freshness state.

Remaining real defects are RCA-01, RCA-02 and the missing trader-facing `Quote Freshness` label in the active Lab HTML.

### RCA-13 — Outcome capture and learning

**Current status:** ACTIVE LEARNING-INTEGRATION GAP; DOES NOT INVALIDATE TODAY'S DETERMINISTIC TRADE DATA.

Stage 6 now captures all-presented candidate events and attempts to carry completed session, reference price, target, invalidation and planned hold. Maturation emits named data exceptions and deferred observations instead of inventing outcomes. Model activation remains correctly disabled.

The old ledger cannot prove this because its records predate the fields. No historical test run should be backfilled and treated as normal evidence. In the current orchestrator, ledger-observation failure is logged as a warning and the pipeline continues. That is acceptable for trade production only if the run manifest explicitly says learning capture is incomplete. It is not acceptable to describe the pipeline as learning from every presented trade when the candidate events did not persist.

**Required integration fix:** add a Stage 6 reconciliation artifact and manifest state such as `LEARNING_CAPTURE_COMPLETE`, `LEARNING_CAPTURE_PARTIAL` or `LEARNING_CAPTURE_FAILED`. A normal completed-session run must show:

- every presented directed candidate has a completed session, reference, target, invalidation and integer hold;
- every candidate × horizon reconciles to completed, deferred or named data exception;
- decisions and fills remain separate; and
- model activation remains off until sample and held-out gates pass.

This blocks the reinforced-learning business claim, but it is not a reason to discard present-day opportunities or invalidate otherwise genuine deterministic thesis/contract evidence.

### RCA-14 — Provider finality, run truth and macro packet identity

**Current status:** EVIDENCE-ONLY ACCEPTANCE DEPENDENCY, PROVIDED NO BYPASS/FALLBACK IS OBSERVED.

Current source contains provider-finality services, central run planning, distinct run conditions, baseline eligibility, provider/fetch timestamp separation and immutable macro packet archiving. The forced intra-session reference runs predate those changes.

**Remaining action:** validate them in one `NORMAL_COMPLETED_SESSION` run. The run must reconcile every provider request and dataset to the declared evidence cutoff and completed session. Any bypass, ambiguous session, mutable “latest” packet or false production label would promote this immediately to an active integration defect. Do not reopen the component design solely because the only available stored runs were forced tests.

## 5. Test and specification root causes

The full suite's **44 failed elements are not 44 product defects**. They consolidate as follows.

### T-01 — Historical negative assertions were left active after the feature landed

Affected examples:

- W01 expects no size propagation;
- F08 expects no underlying NBBO-size producer;
- F10 expects zero freshness callers;
- L01 expects no quote comparison;
- L02 expects no baseline-zero derivation;
- L07 expects no cadence detection; and
- L09 expects no contract-change classification.

**Fix:** replace each with a positive behavioral assertion against the current canonical contract. Never preserve a test whose PASS condition is absence of an approved feature.

### T-02 — Tests inspect implementation strings instead of behavior

The EV3 order test searches for an exact one-line source substring even though the call is now multiline/keyword-based. R06 similarly expects field names to appear directly in one materializer instead of validating its helper-produced bundle and overlay schema.

**Fix:** use an instrumented execution-order test and contract-level output assertions. Source-text greps are acceptable inventory tools, not release acceptance tests.

### T-03 — Quote-change tests confuse canonical bundle keys with Lab overlay keys

The canonical comparison bundle uses keys such as `current_bid`; `quote_change_overlay_fields()` maps them to `current_contract_bid` for the Lab. W07 expects the overlay names inside the canonical bundle.

**Fix:** assert the canonical schema, run the mapper, then assert the Lab schema and value equality across the boundary.

### T-04 — Calendar fixtures use “yesterday” instead of the previous exchange session

Three historical-price tests use `date.today() - 1 day`. On a weekend or holiday this creates an invalid completed-session expectation and makes correct production finality fail the test.

**Fix:** derive the previous XNYS completed session through the same calendar domain contract used by production. Do not weaken production finality to satisfy a wall-clock fixture.

### T-05 — Minimal Lab fixtures no longer satisfy the governed-book contract

Cache and STRANGLE tests construct partial rows without the identities, state records and reconciliation evidence required by the current Lab. The row is correctly excluded, after which the test raises `IndexError` or `KeyError` before exercising cache or direction behavior.

**Fix:** either construct a valid governed book fixture or test the isolated cache-signature/direction function directly. Assert fixture admission before the subject assertion.

### T-06 — STRANGLE tests are misaligned with the current business scope

The governed product trades single-leg long CALLs and PUTs. Most failing STRANGLE tests are not acceptance criteria for current monetisability. One protection remains important: a non-directional record must never be silently coerced into CALL or PUT.

**Fix:** retire STRANGLE execution/policy tests from the release gate, retain one non-coercion/data-preservation test, and keep the underlying PUT regression.

### T-07 — Vocabulary disagreements are being reported as behavioral failures

`OBSERVED_POSITIVE` versus `OBSERVED`, and `quote_quality=INVALID` plus a crossed-quote reason versus literal `CROSSED`, are safe behavioral outcomes with inconsistent terminology.

**Fix:** centralise the enum. Recommended semantics are:

- size quality: `OBSERVED_POSITIVE`, `OBSERVED_ZERO`, `MISSING`, `INVALID_SIZE`;
- quote validity: `VALID`, `INVALID`, `MISSING`;
- quote defect reason: `CROSSED_QUOTE`, `ZERO_BID`, `NEGATIVE_VALUE`, etc.

Update the requirement glossary and tests together. Do not change safe invalidation behavior merely to match an obsolete literal.

### T-08 — Final-book completeness test still expects deliberately retired R:R fields

`write_final_opportunity_book()` explicitly removes `rr_*` fields and its CSV field list excludes them. The old test asserts that every member of the historical `FINAL_BOOK_FIELDS`, including retired R:R fields, remains in the returned row.

**Fix:** define `ACTIVE_FINAL_BOOK_FIELDS` or remove retired R:R fields from the active schema constant. Test exact active-schema completeness and separately verify that prohibited R:R fields are absent.

### T-09 — R07 duplicates downstream failures rather than adding independent evidence

The R07 meta-suite reruns named groups and records their failures again. Its own failure count must not be added to the underlying defect count.

**Fix:** retain it as a reconciliation report, but mark its status derived from child suites and exclude it from unique-defect totals.

## 6. Lab UI defect requiring a small direct repair

The current HTML contains trader-facing liquidity information but lacks the literal inline `Quote Freshness` field required by the liquidity design. This is not the same as the stale-quote algorithmic defect, but it prevents the human from seeing the result.

**Fix:** display the canonical freshness state and provider timestamp alongside current bid/ask. It must show `FRESH`, `REQUOTE_REQUIRED`, `UNAVAILABLE` or `INVALID`, and must never infer freshness from row age or the 1-20-day thesis horizon.

## 7. Corrected disposition of the principal AVS-TD findings

| Original finding family | Current disposition | Correct next action |
|---|---|---|
| Spread ambiguity | Active P0 | Repair canonical units end to end. |
| Stale executable quote | Active P0 | Separate thesis and quote lifecycle; provider timestamp required. |
| DOI forecast vol missing | Component resolved; integration active | Reconcile GARCH → Options → DOI → Lab and prohibit silent legacy substitution. |
| Horizon-limited deletion | Active P1 | Retain and classify before ranking. |
| Mixed v1/v2 rank | Active P1 | Split score fields and comparison sets. |
| Two monetisability truths | Active P1 | One v2 presentation state; legacy disclosure only. |
| Contradictory Lab states | Active P1 | Exhaustive canonical presentation model. |
| Uncalibrated probability names | Active contract risk | Gate/null or rename; verify visible UI. |
| Macro mapping | Active advisory defect | One post-classification join and explicit route field. |
| Capital allocation | Active deactivation-boundary defect | Keep deactivated and remove/hard-isolate every upstream production path; final display remains `HUMAN DETERMINED`. |
| Outcome learning absent | Active learning-integration gap | Publish capture completeness and prove population/maturation in a normal cycle. |
| Provider finality/run truth | Evidence-only acceptance dependency | Prove in a normal completed-session cycle and promote to active if any bypass appears. |
| Size propagation | Resolved | Replace stale negative tests. |
| Quote comparison | Resolved core | Replace stale tests; repair timestamps/units/UI. |
| Baseline zero/cadence/contract change | Resolved | Replace stale negative tests. |
| 44 test failures | Mixed | Resolve product defects and rewrite invalid tests; do not count raw failures as defects. |
| Credential fallback | Active P0 security | Remove, rotate and scan history. |

## 8. Recommended build sequence

This sequence minimises regression risk and follows DDD ownership.

### Slice 1 — Canonical market-observation truth

1. Repair spread units and aliases.
2. Repair provider/fetch timestamps and governed quote TTL.
3. Correct current executability without changing thesis validity.
4. Add the Lab freshness display.
5. Remove and rotate credential literals.

**Gate:** no row is executable with missing/stale provider evidence; no magnitude guessing exists; CALL and PUT behavior is symmetric.

### Slice 2 — Contract-family and economics truth

1. Retain horizon-limited contracts.
2. Separate v1 and v2 rank fields.
3. Establish v2 as the single monetisability presentation contract.
4. Preserve unranked/developing alternatives and exact supersession lineage.

**Gate:** every source-chain contract reconciles, all ranked comparisons use one score kind, and no ticker is deleted due solely to present timing, spread or monetisability.

### Slice 3 — Trader-facing read model

1. Centralise state vocabulary.
2. Replace positive defaults with explicit missing states.
3. Remove legacy verdicts from the authoritative surface.
4. Gate probability-shaped fields.
5. Consolidate macro projection and permanently deactivate/remove capital reachability.

**Gate:** the Lab cannot present contradictory authoritative states and macro remains advisory under mutation/property tests.

### Slice 4 — Test and release repair

1. Rewrite stale negative assertions as positive governed tests.
2. Replace source-string tests with behavioral tests.
3. Fix exchange-calendar and governed-fixture construction.
4. Retire out-of-scope STRANGLE release tests while keeping non-coercion protection.
5. Split active versus retired final-book schemas.
6. Run focused tests, then the complete governed suite.

**Gate:** zero undisclosed failures. Any accepted exception must identify owner, reason, scope and expiry.

### Slice 5 — Acceptance evidence

1. Run one clean `NORMAL_COMPLETED_SESSION` cycle.
2. Reconcile candidate population, provider finality, spread units, forecast-vol coverage, contract-family states, v2 assessments, ranks, Lab states, macro advisory and ledger events.
3. Run the next valid post-open thesis/contract validation phase.
4. Mature outcomes as sessions become available.

**Gate:** the release manifest, artifacts and database events all identify the same code/configuration, input sessions and evidence cutoffs.

## 8.1 Integration completeness gates

Each integration must close with an explicit population equation. A stage log saying “complete” is insufficient.

| Handoff | Required equation or invariant | Failure representation |
|---|---|---|
| Provider → canonical store | requested = persisted + no-data + named exception | No substitution of an earlier session as current. |
| GARCH → Options boundary | Options directed rows = forecast joined + named forecast-unavailable | No silent numeric zero. |
| Options → DOI | retained families = assessed + named unassessed | No legacy state represented as v2. |
| DOI → Lab | Lab ticker population unchanged; every row has v2 state or explicit DOI unavailable | No candidate deletion. |
| Morning → execution observation | thesis rows unchanged except governed thesis transitions; executable rows all have valid provider timestamps | Stale/missing quote changes execution state only. |
| Macro → Lab/Worker 3 | requested tickers = exact + sector-only + unmapped + invalid | Unavailable macro remains advisory unavailable. |
| Lab → decision ledger | presented rows = appended + idempotent-existing + named persistence failure | Manifest discloses partial/failed learning capture. |
| Ledger → outcomes | candidates × horizons = completed + deferred + data exception + already observed | No invented fill or outcome. |

An integration is resolved only when its equation reconciles for a governed run and the failure branch produces an explicit non-favourable state.

## 9. First-principles production conclusion

The underlying business model remains sound:

- Discovery/Vanguard owns the ticker thesis and direction.
- Options Intelligence owns the evolving contract family and current monetisability evidence.
- Morning/post-open validation decides whether the thesis survived and refreshes entry evidence.
- The Lab explains all independent states to the human.
- The ledger learns from every presented opportunity without pretending a trade was filled.

The current failures arise where those boundaries are crossed, not because long CALL/PUT dynamics are inherently unmodellable. The pipeline will become materially more reliable by enforcing one unit, one timestamp meaning, one score kind per comparison, one monetisability presentation contract and one explicit state per bounded context.

The immediate release blockers are RCA-01, RCA-02, RCA-03, RCA-04, RCA-05, RCA-06, RCA-09 and RCA-10. RCA-11 is also a release blocker until DOI failure cannot silently fall back to a legacy answer. RCA-07 and RCA-08 must close before claiming the full Intelligence Lab/Worker 3 narrative is production-complete. RCA-09 closes only when capital allocation is demonstrably unreachable or hard-isolated and remains deactivated in every governed run mode. RCA-13 blocks the learning claim, although it does not invalidate today's deterministic trade evidence. RCA-14 requires governed-run proof and becomes an active defect if that run exposes a bypass or fallback.
