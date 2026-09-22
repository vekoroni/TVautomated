# AVS-TDD-MON-004 — Test-driven path-aware decision research

**Date:** 22 September 2026
**Status:** research test contract; no production authority
**Companion:** `AVS-SD-MON-003_PATH_AWARE_MONETISATION_AND_EXPRESSION.md`
**Scope:** shares, long calls and long puts; 1–20 sessions; human execution; capital-agnostic.

## 1. Decision to be tested

Can a point-in-time, path-aware Evening ranking surface more *realistically monetisable* opportunities than the current deterministic baseline at the same top-20 and top-50 human-review capacity, without hiding valid theses, materially increasing severe losses, or relying on later information? Morning Gate tests the frozen Evening thesis against new evidence; it does not retroactively create the Evening signal.

This is **not** a claim that HARC or any other model is already profitable. A high quoted maximum is an opportunity ceiling, not an executed return. The research must establish whether a rule knowable at decision time captures that ceiling.

## 2. Read-only characterisation tests run before solution design

Sources: `data/output/runs/20260922_000106/` and `Enhancements/backtest/signal_ticket_backtest_rows.csv`. Commands were read-only; no pipeline stage, broker operation or database update was run.

| Probe | Observed result | Test-design consequence |
|---|---:|---|
| Latest Morning handoff population | 1,543 rows | Preserve all rows and reconcile every state transition. |
| Latest Evening states | 685 repair-at-open; 440 trigger-ready; 330 data-insufficient; 66 watchlist-monetisable; 22 thesis-ready | Do not equate a monitoring/repair state with thesis invalidity or option profitability. |
| Directed rows missing authoritative invalidation | 159 | Test geometry and provenance; all 159 currently have `capital_permission=NO`. A handoff audit `FAIL` is not evidence that unsafe permission was granted. |
| Latest option outcome learning | 17,557 complete outcomes, all `UNDERLYING_ONLY`; zero option labels available | A fitted option-path model is not presently supportable from this learning snapshot. |
| Historical option-ticket panel | 8,950 rows across 9 session dates: 5,729 CALL, 3,221 PUT | Useful for failure localisation and label-factory tests, not a representative market-wide sample. |
| Entry quotes / exit marks | 8,950 entry bid/ask; 2,992 recorded exit bids; 325 marked unavailable; 5,633 open | Missing future quote is neither zero return nor a loss. Exit-label coverage is only 33.4%. |
| Closed-panel outcome | 320/2,992 positive and 67/2,992 at least +100%; 19 tickets among closed, 1 positive | These are outcomes under the *existing recorded stopping rule*, not an unbiased estimate of a new exit rule. |
| Latest historical cohort | 1,166 rows on 16 September; zero closed | Cannot validate a full 20-session policy from this cohort on 22 September. |

The existing MON-003 document's as-is claims about planned-hold and observation identity were written before subsequent repairs. Re-measure those claims against the release being tested; do not import them as current defects.

### Test-definition manipulation actually performed

I ran two alternative denominators on the *same* stored panel before fixing the outcome contract. If open/unavailable outcomes are incorrectly filled with zero, the apparent positive rate falls from **8.3% to 3.5% for CALL** (200 positives; 2,403 closed of 5,729) and from **20.4% to 3.7% for PUT** (120 positives; 589 closed of 3,221). Neither version is an unbiased trading hit rate: the first conditions on the old stopping rule and observed exits; the second invents losses for unobserved outcomes. This adversarial manipulation makes T03/T05 prerequisite tests, not optional reporting. No performance threshold was selected from these numbers.

## 3. Failing tests to write first (red contract)

Each test is initially an executable specification. A test may fail because data is absent; that must produce `UNMEASURABLE`, not a manufactured positive or negative result.

| ID | Red test / expected invariant | Minimum fixture or evidence | Green criterion |
|---|---|---|---|
| T01 Point-in-time | Moving a future quote, IV, OI, macro packet or thesis revision into the input set changes nothing at an earlier decision cutoff. | Frozen ticker-session with one deliberately future-dated field. | Future field rejected; decision hash unchanged; violation logged. |
| T02 Exact identity | A quote for a different expiry, strike, right or symbol cannot mark the selected contract. | Same ticker with adjacent contract. | Exact contract identity, provider observation time and source ID match. |
| T03 Label accounting | Every monitored expression and horizon has one of `OBSERVED`, `RIGHT_CENSORED_DATA_EDGE`, `QUOTE_UNAVAILABLE`, `NOT_ELIGIBLE`, `INTEGRITY_EXCEPTION`; no null-to-zero conversion. | Open, closed, expired and missing-quote examples. | Counts reconcile to the frozen input population on replay. |
| T04 Competing event order | Target, invalidation, time stop, expiry and quote loss are ordered by observed session; target after invalidation is not a win. | Synthetic CALL, PUT and share paths with reversed event order. | First event and reason are deterministic and symmetric for CALL/PUT. |
| T05 Horizon truth | A 20-session non-hit is a negative only after 20 observable sessions or a defined terminal event; a not-yet-mature cohort is censored. | 16 September cohort and synthetic mature cohort. | No full-horizon label assigned prematurely. |
| T06 Executable economics | Entry ask and exit bid, fees and explicitly stated fill assumptions govern the primary option outcome; mid-to-mid and maximum bid are secondary diagnostics. | Wide-spread and zero-bid paths. | Primary result never uses hindsight best fill or mid as if executable. |
| T07 Baseline parity | Current deterministic DOI/C12 result replays unchanged before any challenger is evaluated. | Hash-bound stored run and immutable config. | Same row count, direction, thesis, expression and authority fields. |
| T08 Opportunity retention | Weak current option quote or no current option expression cannot erase a valid share thesis. | Valid thesis with wide/absent option quote. | Thesis retained; expression marked monitoring/unavailable; no false execution permission. |
| T09 Counterfactual policy | Fixed, predeclared exit and delay policies run on the same candidate population, with abstentions and missing marks counted. | Shares/CALL/PUT, immediate vs 1/2-session wait; hold to 1/3/5/10/20 or first event. | Comparable paired denominators and complete reason codes. |
| T10 Model calibration | Predicted target-first, invalidation-first, liquidity-development and positive ask-to-bid probabilities sum/reconcile appropriately by horizon and are calibrated separately. | Mature holdout with sufficient labels. | Brier/calibration and confidence intervals reported; insufficient strata remain inactive. |
| T11 Human review capacity | At fixed top-20 and top-50, challenger is compared with current ordering on identical session populations. | Contemporaneous session books, no hindsight filtering. | Paired gains, severe losses, missed right tails and coverage all reported. |
| T12 Production boundary | Research output cannot change thesis direction, execution authority, capital allocation, live Lab verdict or selected contract while disabled. | Contract tests at orchestrator/Lab/Execution Gate. | Byte/field parity in production outputs; explicit research-only manifest. |

## 4. Registered experimental branches (exploration, not acceptance tuning)

The user authorises creative alternatives. We will explore them on development periods, version each branch, and retain failed attempts. We will **not** alter the untouched later-session holdout or acceptance thresholds after seeing its result.

1. **B0 deterministic baseline:** current DOI scenario economics and C12 labels; no new model.
2. **B1 transparent event ranking:** thesis quality + distance/time to target and invalidation + option spread/IV/DTE + observed liquidity trajectory. Fit a calibrated, interpretable discrete-time competing-event model only where labels exist.
3. **B2 HARC challenger:** hazard-adjusted right-tail capture with *separate* activation probability, target-before-invalidation probability, gain distribution, nonactivation loss, costs and uncertainty. No extrapolated extreme-value tail is production-eligible on a handful of events.
4. **B3 expression/timing alternatives:** shares versus exact-contract CALL/PUT; immediate entry versus 1/2-session conditional wait; fixed hold versus predeclared first-event exits. Never select the historical best exit per row as a tradable result.
5. **B4 interaction/confluence:** structure, market profile, macro advisory, catalyst, activity, IV and thesis geometry enter only if an incremental ablation improves an untouched comparison. PCR/OI are positioning context, not signed flow or directional authority.

The ranking objective is the **unconditional** distribution of executable outcomes, not `P(activation) × upside conditional on activation` alone. Otherwise a low-probability lottery with large upside can outrank a more reliable opportunity while its nonactivation losses disappear.

## 5. Research protocol and stress tests

- Freeze candidate event time, provider observation time, source ID, run ID, thesis version, selected expression and alternatives. Retain the whole candidate population, including rejected and no-option rows.
- Use session-ordered train, calibration and untouched test partitions; embargo overlapping 20-session labels. Cluster uncertainty by ticker and session. Historical H/H+ cohorts diagnose mechanisms; the forward N cohort is necessary for promotion.
- Report CALL and PUT separately; shares separately; 1/3/5/10/20-session horizons separately. A bucket without mature labels is `UNMEASURABLE`.
- Stress spreads +25%/+50%, quote dropout 10%/25%, delayed OI, IV crush/expansion, gap continuation/reversal, sector leave-out, removal of top 1% outcomes, event/no-event, and low-OI maturation.
- Primary scorecard at fixed top-20/top-50: mean and median ask-to-bid return, positive-return rate, severe-loss rate, +100/+200/+500% recall, calibration, quote/outcome coverage, missingness, abstentions, and comparison with shares. Do not optimise solely for spectacular tails.
- Record all variants and test iterations in the scenario register. A revised definition gets a new ID/version and re-run of B0. No silent overwrites or selection of a favourable test after viewing holdout outcomes.

## 6. Decision gates after tests

**Gate A, implementable data:** T01–T08 pass; exact-contract path coverage by session/direction/horizon is published. If not, build label capture and coverage repair first, not HARC.

**Gate B, research merit:** B1/B2/B3 are evaluated on the same mature, held-out population with B0. Require improvement in *executable* top-capacity outcomes without unacceptable severe-loss deterioration, and disclose confidence intervals and all trials. If B2 adds no robust value over B1, keep B1 or B0.

**Gate C, production:** existing MON-003 §11.4 gates plus forward shadow parity and human sign-off. The quantitative thresholds there are governance proposals, not a statistical guarantee. No model grants capital permission or hides candidates.

## 7. Reproducibility and immediate next test

First implement T01–T06 as a read-only label-factory test harness against frozen copies of `signal_ticket_backtest_rows.csv`, canonical chain snapshots and underlying prices. Reconcile the historical panel's 8,950 rows, 2,992 exits, 325 unavailable marks and 5,633 open rows before evaluating any ranking. Then run B0 and B1 on the *same* eligible rows. This yields an implementable baseline even if HARC lacks fit-eligible labels.

No trading-performance conclusion or production change is authorised by this document.
