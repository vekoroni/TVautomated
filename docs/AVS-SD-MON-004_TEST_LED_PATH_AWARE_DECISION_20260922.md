# AVS-SD-MON-004 — Test-led path-aware decision extension

**Date:** 22 September 2026
**Status:** proposed research-to-production design; model authority disabled
**Prerequisite test contract:** `AVS-TDD-MON-004_PATH_AWARE_DECISION_RESEARCH_20260922.md`
**Extends, does not supersede:** `AVS-SD-MON-003_PATH_AWARE_MONETISATION_AND_EXPRESSION.md`.

## 1. Thesis and choice

The latest pipeline can form and retain ticker theses, but it does not yet have mature exact-option-path labels to show that a new path-ranking model improves monetisable trading decisions. Build the **outcome measurement and transparent competing-event benchmark first**, then challenge it with HARC. Do not replace the retired cautious-return veto with another opaque hard gate. Keep shares, long calls and long puts visible, preserve the Evening thesis, and let the human judge execution. The Morning run updates the thesis with new evidence and refreshes expression observations; it does not need to manufacture the Evening opportunity.

This choice follows TDD probes rather than narrative preference: latest run `20260922_000106` has zero option labels available to the outcome learner; the historical ticket panel has only 2,992 recorded exits from 8,950 entries. A fitted HARC score from those records today would confuse missingness and the old stopping rule with true option-path performance.

## 2. Domain boundaries and non-negotiable authority

| Bounded context | Existing seam to reuse | Owns / must not own |
|---|---|---|
| Market evidence | canonical provider-finality, historical prices, Phantom `chain_snapshots` | Owns exact timestamped source observations; no thesis or recommendation. |
| Opportunity thesis | Discovery/Vanguard and governed Evening handoff | Owns direction, target, invalidation, horizon and validity; no option quote veto. |
| Expression evidence | `canonical_data/option_liquidity_lifecycle.py`, `canonical_data/dynamic_options_valuation.py`, `domain/contract_economics_v2.py` | Owns family geometry, deterministic economics and quote quality; no ticker-direction reversal. |
| Outcome capture | `canonical_data/dynamic_options_outcomes.py`, `canonical_data/outcome_maturation.py`, Decision/Outcome Ledger | Owns append-only path and event labels; no production recommendation. |
| Research forecast | new versioned local research service behind MON-003 interfaces | Owns calibrated probabilities and uncertainty; disabled in live authority until accepted. |
| Presentation/human decision | Intelligence Lab, Morning Gate, Execution Gate | Shows thesis, expression, alternatives and reasons; human execution, no capital allocation from this extension. |

An advisory macro or Worker 3 narrative may explain a result but never repair missing quotes, set direction, create option fills or grant trading authority.

## 3. Data contracts and flow

### 3.1 Freeze point-in-time opportunity

At completed-session publication, persist an immutable `OpportunitySnapshot` with run/ticker/thesis IDs, direction, thesis version, target, invalidation, horizon (1–20 sessions), provider observation cutoff, source dataset IDs/hashes, macro packet ID, and candidate state. A non-directional or missing-invalidation state remains visible but cannot masquerade as a directed executable thesis.

### 3.2 Capture all candidate expressions

For each snapshot, record a share expression and the eligible long CALL/PUT family as applicable, including selected and unselected monitored contracts. Store exact option symbol/right/strike/expiry, observed bid/ask, sizes, spread, IV/Greeks, volume, OI, quote observation time, source dataset ID and a quality state. An absent or wide option quote changes the expression state, not the underlying thesis. Low OI is evidence of current positioning and possible liquidity maturation, not an automatic discard.

### 3.3 Mature path labels without hindsight leakage

Use existing `capture_family()` and append-only `doi_outcome_labels` persistence rather than inventing a second database. Add governed scheduling from live outcome maturation so eligible frozen families are revisited after each completed session. Record each exact-contract bid/ask path and underlying path through the first of target, invalidation, time stop, expiry or data edge. Calculate MFE/MAE and threshold passage separately from any hypothetical fixed policy return. Distinguish `QUOTE_UNAVAILABLE` from `RIGHT_CENSORED_DATA_EDGE` and a matured non-hit. Do not overwrite provider Greeks or historical labels; supersede by new calculation version if a correction is required.

### 3.4 Forecast and comparison

The deterministic baseline remains live. Research first estimates cause-specific, discrete-session probabilities of: thesis target first; invalidation first; executable quote development; and option gain threshold before the governed time stop. A probability of target at session 20 is not a probability of *first passage before invalidation*. Candidate expression comparisons must include nonactivation loss, spread/fees, theta/IV risk and uncertainty. Share returns and option premium returns are reported in their own units; do not rank raw percentage returns as if they have equal risk or capital usage.

HARC is a challenger, not the default: use its tail model only after the transparent benchmark passes calibration and the tail sample is adequate. An extreme-value fit to a tiny >500% sample is research-only. No candidate disappears because the chosen expression currently looks weak; show alternatives and monitoring conditions.

### 3.5 Evening-to-Morning handoff

Evening emits `THESIS_READY`, `TRIGGER_READY`, `MONITOR_CONDITION`, `EXPRESSION_REPAIR`, or `DATA_REVIEW` with plain-language reason and frozen source IDs. These are presentation classes mapped from governed states, not a parallel execution vocabulary. Pre-open Morning checks the Evening thesis against new price/gap/event evidence; post-open refreshes quote and expression suitability. It may validate, develop, defer or invalidate with reason and source. It cannot silently flip CALL↔PUT or erase the Evening record. The Lab displays both snapshots and the change.

## 4. Build order dictated by red tests

1. **Baseline and characterisation (T01, T02, T07, T12).** Hash frozen run `20260922_000106`, source code/config, panel and schemas. Reproduce current deterministic DOI/C12 and state counts. Confirm all research flags disabled. No production change until this passes.
2. **Label accounting and event order (T03–T06).** Write synthetic CALL/PUT/share fixtures before implementation. Wire existing `capture_family()` into outcome maturation for frozen candidate families. Publish an exact reconciliation receipt. Reuse canonical stores and append-only identities.
3. **Counterfactual policy harness (T08, T09).** Compare immediate/conditional delayed entry and registered exit policies on paired rows, including shares and no-option cases. Treat missing quotes as unavailable/censored, not failures. Report quote coverage and attrition at every step.
4. **Transparent benchmark (T10, T11).** Fit only on mature training windows, calibrate separately, test on untouched time-separated cohorts. Rank at fixed top-20/top-50. Produce executable ask-to-bid economics and downside/tail scorecards.
5. **HARC and interaction challengers.** Test the attached papers' ideas, confluence, market profile, macro and activity features as pre-registered incremental branches. Ablate each feature family. Retain null results and all variant IDs. HARC proceeds only if it beats the simpler model in paired holdout/stress evidence.
6. **Shadow integration and Lab contract.** Write versioned advisory forecasts to a separate projection; do not alter governed thesis, selected contract or execution gate. Show expected path, uncertainties, alternative expression and why an opportunity is monitor-only. Replay stored Evening→Morning handoff and run full regression.
7. **Forward acceptance.** Accumulate mature N outcomes over independent completed sessions; perform MON-003 §11.4 stress and promotion gates. Require explicit release sign-off for any ranking change. Human execution remains the only trading action.

Each slice is reviewable and reversible; a failure leaves the deterministic baseline in place. Repository cleanup must not delete frozen source artefacts, database rows or audit evidence needed for this comparison.

## 5. Acceptance and rejection rules

- **Data readiness:** exact-contract identities and provider times reconcile; every candidate/horizon is accounted for; zero future evidence at decision cutoff; mature option-label coverage and missingness are published by session and direction. Until sufficient mature paths exist, the research can explain historical defects but cannot claim a production-winning model.
- **Economic merit:** compare like-for-like candidate populations and top-20/top-50 capacity. Report ask-to-bid outcomes, severe losses, missed right tails, calibration, uncertainty and sensitivity to spread widening and quote dropout. Quoted max return is not the primary success metric.
- **Robustness:** CALL and PUT separately, 1/3/5/10/20-session horizons, regime/event strata, leave-one-session/sector-out, removal of top 1%, and all registered alternatives. A result driven by one session or a few extreme options is rejected or held as hypothesis.
- **No silent authority change:** model outputs remain advisory until production acceptance. No new capital budgeting, automatic order, thesis-direction switch or new hard discard based on entry/exit timing.
- **Honest null outcome:** if B1, HARC and timing alternatives do not beat B0 robustly, keep the current deterministic flow and improve data/quote capture. Do not move thresholds until a favourable backtest appears.

## 6. Research basis and limitations

Listed-option transaction-cost research shows that bid/ask costs can eliminate apparent abnormal returns, motivating ask-to-bid primary economics: [Phillips and Smith, *Journal of Financial Economics*](https://www.sciencedirect.com/science/article/pii/0304405X80900161). Competing-event predictions need event-specific calibration and censoring-aware evaluation: [Blanche et al., competing-risk prediction evaluation](https://arxiv.org/abs/1707.03971). Repeatedly trying variants creates selection bias, so all attempts and holdout access must be logged: [López de Prado, multiple-testing in financial research](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3177057).

These papers motivate tests; they do not demonstrate that AVSHUNTER has a profitable signal. The user's three HARC/volatility/cautious-return documents are hypotheses to challenge under this protocol, not evidence of production fit.

**Implementation authorised by this document:** none. The next development action is Slice 1 with tests written first, followed by the label-factory integration only if its red tests identify and localise a genuine gap.
