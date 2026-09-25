# Change register — every enhancement identified on 25 September 2026, with impact and defence

**State:** research register for ACK decision. No change below has been made. Every number comes from read-only tests on completed runs (24 Sep morning book, 25 Sep evening and morning books, eleven earlier books) documented in `Enhancements/research/`.
**Reading guide:** *Improves / eliminates* is measured on the books tested. *Pros* and *cons* are the defence. *Verdict* is my recommendation on timing.

---

## A. Data and provenance

### A1 — Geometry or an explicit gap (fix items F5 / P3, morning finding M3)

**Change.** The Thesis context publishes a target and an invalidation, or `GEOMETRY_UNAVAILABLE` with a reason. A target or invalidation within 1% of spot is `GEOMETRY_DEGENERATE`, not a level. The Wyckoff structural invalidation level, present on all 375 rows lacking an invalidation, becomes a governed fallback source with its provenance stamped. The manifest reports the gap count and downgrades `run_tradeable_label` when it is non-zero.

**Evidence.** 24 Sep: 375 rows without invalidation, 312 also without target; manifest EXECUTION_READY beside 185 handoff defects. 25 Sep morning: 175 missing again; TSM, MS and RIO reached GO or GO_LIMIT with a level within 1% of spot; 9 of 86 evening candidates and 8 of 22 morning Tier A rows were degenerate.

**Improves / eliminates.** Eliminates the largest silent death (375 rows) and the false EXECUTION_READY label. Up to 375 rows regain an invalidation; 312 stay dead for a valid, counted reason. Removes degenerate rows from GO.

**Pros.** Invariant B compliance. The gap becomes an owned, visible defect instead of a BLOCKED verdict. The fallback level already exists in the row. Trades stop being valued against a stop that is 0.3% away.

**Cons.** The Wyckoff level is a different owner's number; approving it as a fallback needs an ACK decision and a provenance label so it is never confused with a Thesis-owned level. Downgrading the tradeable label will make more runs read DEGRADED until the producer is fixed, which is honest but uncomfortable.

**Verdict.** Saturday. Small, contained, and a prerequisite for everything valued.

### A2 — Timestamp label corrected, not "fixed" (P2, revised)

**Change.** Rows with no quote at all are labelled `NO_EXECUTABLE_EXPRESSION`, not `PROVIDER_TIMESTAMP_MISSING`.

**Evidence.** All 191 rows carrying the timestamp reason have no bid or ask of any kind.

**Improves / eliminates.** Eliminates a misleading death reason. Revives zero rows.

**Pros.** A trader reads a true reason. **Cons.** None material; it is a relabel. The rows only come back through A/B expressions (B3).

**Verdict.** Saturday, inside D1.

### A3 — Multi-session quote provenance, coverage test, canary, then capture (F6)

**Change.** Every new quote row carries provider timestamp, session, capture instant, contract identity and writer version. Measure 5/10/20-session exact-contract coverage on the store. Run the production-scale writer in isolation for one session against the governed completeness thresholds. Only then activate routine capture. Never backfill gaps.

**Evidence.** Provenance assessment: 37/40 one-session paths verified, 0/40 five-session paths complete.

**Improves / eliminates.** Creates the only dataset on which walk-forward evaluation and the prospective record can be scored at ask-to-bid over a real hold.

**Pros.** Without it nothing beyond one session can ever be validated. **Cons.** Calendar-bound: 20-plus sessions after the canary before a 20-session horizon can be evaluated. Storage and provider-credit cost. It produces no trade improvement by itself.

**Verdict.** Start the provenance and coverage steps Saturday; canary on the first clean session; capture after.

---

## B. Contract and expression

### B1 — Revive the approved shadow value selection (P4, first step)

**Change.** The value-based contract selection ACK approved on 18 Sep (`value_selection_mode = SHADOW`, measure `emp_path_r_central`) has returned `VALUE_INPUTS_UNAVAILABLE` on every row since. Find which of forecast vol, target or invalidation is arriving empty at selection time and feed it, so the shadow produces evidence.

**Evidence.** 25 Sep options output: 1,332 of 1,332 contract rows `SCORE_FALLBACK_VALUE_UNAVAILABLE`; the Lab book carries the fields as None.

**Improves / eliminates.** Eliminates a dead shadow that has silently blocked ACK's own switch to ACTIVE. Produces the comparison ACK asked for on 18 Sep without changing selection authority.

**Pros.** Smallest change with the largest information gain; already approved; shadow only, zero risk to the book. **Cons.** The shadow's shortlist is drawn from the delta-filtered set, so it cannot see the contracts in B2; and its measure is a path Monte Carlo rather than ALG-04, so the two valuations need reconciling before either gets authority.

**Verdict.** Saturday, first. It is the P4 root cause.

### B2 — Retire the delta band and the R gate as pre-selection (P4)

**Change.** Generate the bounded expression set (spec §10) without the 0.30–0.60 preferred band and the 0.20–0.75 mandate band as filters, and without `ESTIMATED_R_LT_1`. Valuation orders the set; the legacy choice is written beside the new one.

**Evidence.** Re-selection test on 367 actionable rows: the contract changes on 89%; median spread 10.1% → 5.3%; median expectancy −10.8% → −4.7%; 242 of the 327 better contracts were excluded by `REJECT_DELTA_BAND`. Half the better contracts have |delta| above 0.89. All 527 tickers with an R rejection still ended with a contract, so the R gate shapes routes, not deaths.

**Improves / eliminates.** Roughly 5 to 6 points of expectancy per row from expression cost alone. Removes a rule the spec explicitly forbids ("no delta bands may be used to pre-select contracts"). Does **not** increase the number of positive-expectancy rows (24 → 19).

**Pros.** The largest measured lever on asymmetry. Same DTE, same thesis, better contract. **Cons.** Half the better contracts are deep in the money and stock-like: the test is really saying the money is closer to the stock than to the OTM option, so B3 must ship with it or the book fills with synthetic stock. The tested-chain record is truncated on 102 tickers, so the gain is a floor but the candidate set is incomplete. Route logic that depended on the R flag needs a replacement key.

**Verdict.** Tonight's evening run, after B1, as the single change under test, with the legacy contract recorded beside it.

### B3 — Shares and short-dated contracts as expression candidates (P6, H5)

**Change.** Expression generation adds one long- or short-shares expression per thesis and the short-dated contract at or above the anticipated-move floor, each with its own immutable last exit session, valued on the same paths.

**Evidence.** DTE comparison: the short contract lost 4 points at the median and was worse on 7 rows in 10, but won on 97 of 305, identifiable in advance by spread and IV level. 190 rows died with `NO_LIQUID_OTM_CONTRACT` and 191 with no quote; only shares reach them. B2's best contracts are stock-like on half the rows.

**Improves / eliminates.** Answers the spec's central question, "is the money in the option or the ticker", on every thesis. Reaches about 380 rows that today have no expression. Captures the 97 short-contract wins without a DTE rule.

**Pros.** Spec §10 already prescribes it; no new model; borrow data is the only gap for short shares and it has a defined state. **Cons.** More expressions to value and display; the trader's list grows unless ranking is disciplined. Short-shares need borrow availability that is not captured yet (`BORROW_DATA_UNAVAILABLE`).

**Verdict.** Saturday after B2, long shares first, short-dated contracts second, short shares when borrow data exists.

### B4 — Keep the window DTE floor; retire the duplicate hold band (H4, F4.1)

**Change.** No anticipated-move DTE rule. Remove `HORIZON_PLANNED_HOLD_SESSIONS` from `governed_dte_config` so one hold definition remains.

**Evidence.** The anticipated-move rule cost 4 points at the median, two-thirds of its contracts failed the 15% spread cap; 0 of 401 rows needed a different contract at any horizon under the window floor.

**Improves / eliminates.** Eliminates a second hold owner in the same module. Avoids a rule that would have pushed selection into contracts the execution model refuses.

**Pros.** Confirms an ACK decision with numbers. Trivial code. **Cons.** None found.

**Verdict.** Saturday, inside B2.

---

## C. Valuation and probability

### C1 — Scenario valuation published on every row; legacy R relabelled (F2)

**Change.** ALG-04 net-of-friction payoffs (FLAT / 1σ / 2σ / REACHABLE / STRUCTURAL / INVALIDATION) on every row; `rr_predicted` renamed to a structural-intrinsic scenario with a version and basis; the Lab projection carries the fields.

**Evidence.** `rr_predicted` is intrinsic at the structural target; absent as a key from the whole 24 Sep book. Median gap between structural and reachable scenarios: 63 to 135 points.

**Improves / eliminates.** Eliminates the headline number that overstates the reachable payoff by roughly 2×. Gives the trader the three numbers that actually decide a long option.

**Pros.** Already the approved design; harness reproduces the worked example. **Cons.** Rates and dividends are defaulted (r = 0.04, q = 0) until captured; the reachable payoff depends on the unvalidated vol forecast (C3).

**Verdict.** Saturday.

### C2 — Asymmetry as the selection rule and p\* on every row (P5)

**Change.** Governed constants: spread cap 0.15, reachable / |FLAT| ≥ 2, break-even p\* ≤ 0.40. Every row shows p\*, "what you must believe", beside whatever probability the pipeline has.

**Evidence.** 24 Sep actionable rows: median p\* 0.52; 173 rows pass spread and asymmetry, 61 with p\* ≤ 0.40. 25 Sep morning: 22 Tier A of which 8 agree with the pipeline's GO.

**Improves / eliminates.** Turns the actionable list from 401 gate survivors into an ordered set of about 20 to 60 asymmetric rows. Makes the only value-based death "you would have to believe more than X".

**Pros.** Transparent; no model; a trader can argue with a number. **Cons.** The constants are provisional and will be tuned, which is exactly the overfitting risk F7 warns about; they must be governed and frozen per cohort. The rule favours cheap far-from-the-money convexity when the forecast is high (C3).

**Verdict.** Saturday as governed configuration with initial values; frozen when the cohort starts.

### C3 — Validate the volatility forecast before any "cheap convexity" language (F4.3, P9)

**Change.** Run ALG-10: realised-to-forecast ratio by horizon and state bucket out of sample, coverage at 1σ, QLIKE on variance, bias. Approve a bias multiplier only with a validation report id.

**Evidence.** Positive-row count moves 13 → 31 → 53 as the multiplier goes 0.70 → 1.00 → 1.15. Forecast sits above contract IV on 46% of actionable rows. The top harness row had forecast 42 points above IV and a legacy probability of 0.04.

**Improves / eliminates.** Eliminates the largest single source of false positives in every valuation above. Either validates the forecast or shortens the list honestly.

**Pros.** The tool exists (`tools/validate_forecast_vol.py`); stored data suffices. **Cons.** A failing result removes most of the cheap-convexity story and the list shrinks; that is a feature, but it will feel like a loss.

**Verdict.** Saturday, run and report; ACK approves the multiplier or not.

### C4 — Outcome labels and calibrated probability from geometry, not the state label (F1, P7, H2)

**Change.** Label every historical decision row TARGET_FIRST / INVALIDATION_FIRST / TIMEOUT with the touch session; publish the first-passage curve per candidate geometry; calibrate on time-separated partitions with the 20-session purge; report Brier skill, ECE, AUC, lift, coverage; activate only past the ALG-09 gate. Demote `hidden_state_label` to display and remove its default-50.

**Evidence.** Legacy probability sits at 0.50–0.51 on most rows. The state label changed on 19.8% of ticker-pairs between books, 242 times with inputs moving under 5 points, and stayed put 745 times with inputs moving 25 or more. Under the legacy probability the ALG-07 utility flips sign with the hold convention.

**Improves / eliminates.** Replaces the coin-flip with a probability that can be compared with p\*. Eliminates an unstable calibration key. Makes the horizon a forecast (exit policy with the best value) instead of a Discovery tier label.

**Pros.** The only path to the 30–50 with a right to be called probable. **Cons.** Longest build in the register (8–10 days); result may show no stratum beats base rate, in which case the honest output is a rank driven by contract cost alone and the register's promise shrinks to "cheaper expressions, same coin".

**Verdict.** Start Saturday with the label writer; calibration the following week.

### C5 — Exit-policy valuation on a fixed contract (H3)

**Change.** Value each expression under the base policy plus Day-5 / Day-10 / Day-20 time-stops on the same contract; the strongest expression is a (contract, exit policy) pair. Stop using the Discovery bucket as a timing input.

**Evidence.** 0 of 401 rows needed a different contract at any horizon; choosing the best policy over the assigned bucket gained a median 14 utility points, but with a horizon-blind probability Day 20 wins 343 times mechanically.

**Improves / eliminates.** Eliminates the "1_5d" label being read as a hold when it is a signal-quality tier. Lets a trade move horizon without moving contract.

**Pros.** Spec §9/§10 already prescribe it; no contract churn. **Cons.** Meaningless until C4 supplies a session-indexed probability; before that it will always prefer the longest policy.

**Verdict.** Build with C4; do not activate before it.

---

## D. Verdicts, routing and deaths

### D1 — Four death reasons; every other verdict becomes display (P1, M2)

**Change.** A row leaves the actionable set only for `NO_EXECUTABLE_EXPRESSION`, `GEOMETRY_UNAVAILABLE`, `ASYMMETRY_INSUFFICIENT` or `NO_POSITIVE_EDGE`. EIL, physics, campaign, direction-conflict, convexity, macro and trigger verdicts are displayed fields with no routing power.

**Evidence.** 24 Sep: 114 rows sent to review for a Wyckoff-versus-actuarial disagreement; 25 Sep morning: SNY and SMCI BLOCKED by `STAND_DOWN_DIRECTION` with an executable quote and Tier A economics. The row-by-row check found the direction-conflict path revives only about 8 rows, so the value of D1 is in what it stops, not what it revives.

**Improves / eliminates.** Eliminates verdict-driven deaths that no trader would accept as a market reason. Reduces the verdict surface a trader must read from eight verdicts to one reason.

**Pros.** Directly the ACK requirement: a trade dies for a valid reason. Removes the complexity that makes the book unpredictable. **Cons.** Some of those verdicts encode real caution (the EIL spread review is right on 371 rows); moving them to display relies on the asymmetry and executability rules to carry the same protection. Revives few rows; if expectations are "more trades", this will disappoint. Every consumer of the old routes needs a characterisation test first.

**Verdict.** Saturday, after B2, as the second change.

### D2 — Manifest tells the truth about tradeability (F5.4, M4)

**Change.** `run_tradeable_label` is downgraded when semantic defects touch actionable rows; both invalidation counts are reported with denominators.

**Evidence.** Two consecutive manifests read EXECUTION_READY beside DEGRADED and 175–185 defects.

**Improves / eliminates.** Eliminates a run label that contradicts its own health field. **Pros.** Trivial. **Cons.** More runs will read not-ready until A1 lands. **Verdict.** Saturday with A1.

### D3 — Book stability as a run-health metric (P10)

**Change.** Each morning manifest reports the overlap of the asymmetric set with the previous morning book, and the actionable count, compared like for like (morning to morning).

**Evidence.** Positive-set overlap 0%, 0%, 13% across the last three morning books; 13 of 26 evening Tier A rows dropped by the morning, mostly on spread; 9 new appeared. The earlier "0 to 515 swing" was evening beside morning and was withdrawn.

**Improves / eliminates.** Makes a 0% overlap a health failure to investigate instead of a market event. **Pros.** Cheap, and it is the metric the prospective record needs. **Cons.** Low overlap has legitimate causes (the open re-prices spreads); the metric must be split by cause (spread, geometry, asymmetry) or it will be misread.

**Verdict.** Saturday.

---

## E. Presentation

### E1 — Remove defective observations from the trader's view (P8, F4.2)

**Change.** Until each passes validation: hide the convexity score (a re-encoding of the campaign verdict, source blank on all rows), the gamma flip and island fields (flip on the adverse side on 55% of actionable rows, island true on 96%), and the macro regime label (one constant on all rows). Repair convexity at its source with the real GEX dashboard.

**Improves / eliminates.** Eliminates three fields that imply a signal that is not one. **Pros.** Invariant B; the trader reads less and trusts more. **Cons.** Removing familiar fields will be felt as a loss; the GEX engine recompute (deferred, needs the chain store) may rehabilitate the flip, in which case it returns with a source stamp.

**Verdict.** Saturday for the view; the GEX recompute when the store is readable.

### E2 — Macro as a per-row overlay, never a gate (models 1–4, spec §14)

**Change.** Show ALIGNED / NEUTRAL / AGAINST with the packet's rule text per row, including sector-ETF and broad-index handling. No consensus-surprise engine, no local projections, no macro HMM, no sector momentum model. Capture the earnings calendar point-in-time for the event-variance split (note 04 §4) only.

**Evidence.** The morning short list: only FANG C and IBIT P cleared valuation, pipeline and macro together; the four tech puts and two avoid-sector calls were AGAINST. The macro regime field in the book is a constant.

**Improves / eliminates.** Gives the reviewer the macro read the spec allows without building models the spec forbids from ranking. **Pros.** Already built in the plan harness; zero pipeline risk. **Cons.** Macro can only ever inform; if ACK later wants it to rank, that is a business decision, not a research finding.

**Verdict.** Adopt in presentation; no model work.

---

## F. Validation and process

### F1 — Freeze the rule and start the prospective cohort (F7)

**Change.** Write down the selection rule, contract selector, exit rule and thresholds with a hash before the next session; log selected and rejected every session at decision time with the quote; score at ask-to-bid; compare against the desk gate and a matched sector-ETF alternative; count every historical variant tried; any rule change starts a new cohort.

**Evidence.** The +10.9% figure was a hindsight oracle over five sessions. Today's harness constants have already been chosen after looking at the books, which is the risk.

**Improves / eliminates.** The only route from research numbers to a tradeable claim. **Pros.** Cheap to build. **Cons.** Evidence arrives at one session a day; 40–60 sessions before it carries weight. Freezing before B2 and D1 land means the first cohort measures the old pipeline; freezing after means waiting. Recommendation: freeze the *measurement* now (what is logged and how scored) and start cohort 1 on the first evening run with B2 live.

**Verdict.** Measurement spec today; cohort 1 from tonight's evening run.

### F2 — Broker-side quote check for the short list (M5)

**Change.** Use the existing read-only Tastytrade capture script (or the read-only connector) to record broker quotes for the morning short list inside an explicit window, as advisory evidence beside the MarketData.app requote.

**Evidence.** The interpreter and the morning validation quote from MarketData.app; Tastytrade is used only for outcome marks and an optional cohort capture.

**Improves / eliminates.** Gives the prospective record the quote that would actually be traded against. **Pros.** Script exists; read-only; no pipeline change. **Cons.** Needs broker OAuth in the process; adds an operator step each morning.

**Verdict.** Optional, from Monday.

### F3 — Sizing stays out (F3)

**Change.** None. Capital, Kelly and percent-of-capital remain outside AVSHUNTER; `wbs_size_guidance` labelled as relative guidance.

**Defence.** Every row already reads HUMAN DETERMINED and capital grant false. The packet's 0.63 / 0.56 / 0.49 modifiers stay advisory text. **Cons.** None. **Verdict.** No work.

---

## G. Expected impact on the funnel, and what does not change

| Stage (24 Sep morning book) | Today | After A–E | Change comes from |
|---|---|---|---|
| Rows in the book | 1,532 | 1,532 | — |
| Rows with a valuable expression | 714 | ~1,100 | B3 (shares reach the no-option rows), A2 relabel |
| Complete, non-degenerate geometry | ~530 | ~900 | A1 (Wyckoff fallback; degenerate flagged) |
| Executable at the requote | 401 actionable | similar | The open decides; unchanged |
| Asymmetric at the governed cap | 173 | 200–280 | B2 (better contracts: 261 → 284 in the like-for-like test) |
| p\* below ceiling | 61 | 50–80 | C1, C2 |
| Probable, once validated | unknown | 30–50 target | C3, C4 |
| Median expectancy of the actionable row | −10.8% | −4.7% | B2 |
| Verdict-driven deaths | 8 verdicts route | 4 reasons | D1 |

**What none of this changes.** The executable ceiling is set by the market and by upstream publication. The sign of the median row stays negative until C4 supplies a probability that clears p\*. The book's day-to-day memory is a fault still to be found (D3 measures it; nothing here fixes it). The vol forecast may fail validation and shorten every list above.

## H. Order and timing

| When | Items | Why this order |
|---|---|---|
| Today, before tonight's evening run | F1 measurement spec; characterisation tests for selection and routing; B1 root cause | Rules of the repo; the evening run is the safest live test of the week |
| Tonight's evening run | B1 + B2 (+ B4) only, legacy contract recorded beside the new one | One cause under test; weekend to review; Sunday re-run as rollback |
| Saturday | A1, A2, D1, D2, D3, C1, C2 (as config), E1, C3 run | Contained changes with characterisation tests; C3 is a report, not code |
| Sunday | Full regression, rollback rehearsal | Monday morning validates a clean book |
| Next week | B3 long shares, C4 label writer, A3 provenance and coverage, E1 GEX recompute | Larger builds; C4 is the critical path to "probable" |
| Following weeks | C4 calibration, C5 exit policies, A3 canary and capture, F2 | Data-bound |

## I. Decisions needed from ACK

1. A1: approve the Wyckoff structural invalidation as a labelled fallback source, and `GEOMETRY_DEGENERATE` at 1% of spot.
2. B2: approve retiring the delta bands and `ESTIMATED_R_LT_1` as pre-selection; confirm the legacy choice is recorded beside the new one for tonight's run.
3. B3: approve long shares and short-dated contracts in the expression set.
4. C2: approve 0.15 / 2 / 0.40 as governed initial constants.
5. D1: approve the four death reasons and the demotion of every other verdict to display.
6. E1: confirm removal of the convexity score, gamma fields and macro regime from the trader view until validated.
7. F1: confirm cohort 1 starts on the first evening run with B2 live.
