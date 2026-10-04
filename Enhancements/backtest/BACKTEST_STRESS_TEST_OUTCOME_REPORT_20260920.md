# AVSHUNTER Backtest and Stress-Test Outcome Report

**Report date:** 2026-09-20  
**State:** `EXPLORATORY_NO_AUTHORITY`  
**Production impact:** None. No production ranking, filter, direction, execution authority, database or configuration was changed.

## 1. Executive outcome

The tournament did not validate a static monetisation rule. It did identify a narrower, testable solution thesis.

1. Option-chain activity contains real relative-ranking information.
2. Static contract selection and fixed one-, three- or five-session exits remain negative after executable quote friction.
3. Changing only the contract selector cannot solve the problem: even a hindsight best-contract oracle is negative at each fixed horizon.
4. A hindsight oracle that may jointly select the contract and exit horizon across days 1/3/5 becomes positive in the highest S-ACT priority bands.
5. Therefore the missing capability is a **thesis-conditioned, path-aware contract-and-exit model**, not another blended PCR rule.

The strongest feasibility ceiling was the five-percent priority band:

- +10.9% mean ask-to-bid return;
- +4.6% with spreads widened by 50%;
- 25.2% achieved at least +25%;
- 254 candidate families across five temporally valid test sessions.

This is not a deployable result because it uses future outcomes to choose the contract and exit day. It proves that a learnable solution may exist and defines what the next model must predict.

## 2. Research governance

The tests followed these controls:

- Recorded ticker thesis and CALL/PUT direction were preserved.
- A ticker was never invalidated because its current option contract was unattractive.
- No capital allocation was modelled.
- PCR was treated as unsigned positioning/activity evidence, never buyer/seller flow.
- Entry-time models could not use next-session OI.
- Primary learned tests used purged walk-forward training: every training outcome ended before the test session began.
- Dirty/test run `20260914_214012` was excluded.
- Marketable results used entry at ask and exit at bid.
- Midpoint and partial-spread entries were disclosed as conditional-on-fill diagnostics only.
- Every scenario remained advisory research with zero production authority.

The historical sessions had already been inspected by earlier Round-4 research. This is adaptive mechanism discovery, not an untouched final holdout. Replication on later completed sessions remains mandatory.

## 3. Data population

The S-ACT population contained:

- 7,808 candidate identities;
- 19,989 candidate/horizon rows;
- eight eligible source sessions;
- 7,259 recorded contracts found in the entry-session chain;
- 6,871 prior-session premium residuals;
- 7,198 next-session OI changes, retained only as deferred diagnostics.

Temporal evidence shrank with horizon after purging overlapping outcomes:

- one-session tests: five valid walk-forward sessions;
- three-session tests: three valid walk-forward sessions;
- five-session tests: one valid walk-forward session, therefore inconclusive.

## 4. Test families executed

### 4.1 S-ACT activity tournament

Tested:

- total-chain OI PCR;
- delta-weighted OI PCR;
- printed-volume PCR;
- OI/volume agreement and disagreement;
- selected-expiry activity;
- near-money and selected-delta-region activity;
- premium residual, IV change and selected-contract OI change;
- combined nonlinear feature set;
- denominator floors of 1, 10 and 50;
- contemporaneous versus prior-session OI;
- 10% and 25% volume-evidence dropout;
- 25% and 50% spread widening;
- 10% and 25% quote-outcome dropout;
- regime subdivisions;
- LOSO comparison and purged walk-forward primary validation.

### 4.2 CEX contract and execution tournament

Tested while keeping ticker direction fixed:

- recorded contract control;
- minimum-spread current contract;
- $0.25, $0.50 and $1.00 premium floors;
- deterministic spread/IV/DTE/moneyness utility;
- logistic contract selection;
- random-forest contract selection;
- 0.05 and 0.10 switching hysteresis;
- delayed liquidity-maturation contract;
- ask entry, 25%-spread-capture limit, midpoint entry and wider-spread stress.

### 4.3 Cross-layer combinations

The frozen purged S-ACT-9 priority score was combined with independent CEX contract selectors at priority bands of 1%, 2%, 5%, 10%, 20% and 30%. Lower-priority candidates remained monitoring opportunities.

### 4.4 Feasibility bounds

Tested:

- random-contract controls;
- hindsight best contract at each fixed horizon;
- hindsight best contract and best exit horizon across days 1/3/5.

Oracle tests explicitly use future outcomes and cannot become production rules.

## 5. Results

### 5.1 Activity evidence is informative but insufficient

The best one-session combined activity model (`S-ACT-9`, denominator floor 50) produced:

- walk-forward AUC 0.740;
- top-quintile mean −21.3% versus −41.2% baseline;
- +25% hit rate 9.1% versus 3.9% baseline;
- positive relative improvement in all five temporally valid test sessions.

The result remained negative and therefore was classified `RELATIVE_IMPROVEMENT_ONLY`, not monetisable.

Evidence ranking:

1. printed-volume activity and local expiry/moneyness structure were strongest;
2. combined evidence was stronger than either source alone;
3. total OI had some relative information;
4. delta-weighted OI alone was weakest and frequently indistinguishable from noise at longer horizons;
5. prior-session OI performed similarly to contemporaneous OI, confirming that OI is positioning context rather than immediate flow.

### 5.2 Friction is a major—but not sole—cause

For the strongest one-session S-ACT-9 priority band:

- mid-to-mid mean: +1.9%;
- executable ask-to-bid mean: −21.3%;
- mean quote-friction gap: 23.2%;
- median entry spread: 20.2%;
- 21.6% gained at mid but lost ask-to-bid;
- ticker direction was favourable only 49.9% of the time.

At three sessions:

- mid-to-mid mean: −8.3%;
- ask-to-bid mean: −32.8%;
- directional underlying success: 42.0%.

Thus one-session losses are heavily affected by execution friction; longer-horizon losses also reflect weak thesis/path timing.

### 5.3 Static contract selection did not monetise

Across the full eligible population:

- recorded H1 contract: −41.2%;
- minimum-spread H1 contract: −34.0%;
- $1 premium-floor/minimum-spread H1: −32.9%;
- hypothetical midpoint entry for that scenario: −24.7%;
- 50%-wider-spread result: −41.7%.

All 33 static/learned CEX scenarios were rejected or inconclusive.

Delayed maturation improved coverage but not returns. Logistic and random-forest selectors did not outperform simple minimum-spread selection. This is evidence against adding model complexity before defining the correct temporal target.

### 5.4 Cross-layer selection improved but remained negative

Best executable cross-layer result:

`S-ACT-9 top 5% + minimum spread + $1 premium floor, H1`

- n = 241;
- five test sessions;
- ask-to-bid mean −9.1%;
- 25%-spread-capture conditional mean −7.4%;
- midpoint-entry/exit-bid conditional mean −5.5%;
- 50%-wider-spread mean −13.4%;
- +25% hit rate 8.3%;
- improved against recorded contract in all five sessions.

It is a stable relative improvement but not monetisable.

Narrower one- and two-percent bands did not improve the result. This rejects the idea that repeatedly shrinking the population will manufacture a robust solution.

### 5.5 Fixed-horizon oracle rejected the available family

Even after using future returns to choose the best available current contract, average executable returns remained negative at each fixed horizon.

Best fixed-horizon oracle observation:

- H1, top 5% band: −5.1%;
- 50%-wider-spread oracle: −9.9%;
- random-contract median: −12.9%.

This proves the static contract family at a fixed exit horizon is structurally insufficient.

### 5.6 Joint contract-and-exit path contains positive upside

When the diagnostic oracle may choose both contract and exit horizon from day 1, 3 or 5:

| Priority band | n | Ask-to-bid oracle | Spread +50% oracle | Hit ≥25% |
|---|---:|---:|---:|---:|
| 1% | 52 | +9.9% | +1.7% | 25.0% |
| 2% | 103 | +2.8% | −3.8% | 19.4% |
| 5% | 254 | +10.9% | +4.6% | 25.2% |
| 10% | 506 | +7.4% | +0.9% | 24.9% |
| 20% | 1,010 | +4.3% | −2.8% | 22.7% |

The positive ceiling survives severe spread stress in the 1%, 5% and 10% bands. The non-monotonic 1/2/5% pattern also warns that very narrow ranks are noisy; the 5% band currently has the strongest combination of sample size and feasibility.

## 6. Harness defects found and corrected

The backtest itself exposed three implementation defects:

1. missing historical spread values caused deterministic selection to fail;
   - corrected to retain the ticker as monitored with no selected contract;
2. a valid empty purged fold caused the summary layer to fail;
   - corrected to emit zero coverage and complete monitoring diagnostics;
3. the initial learned CEX run filtered to evaluation sessions before training;
   - rejected, corrected and rerun using all eligible prior sessions while retaining purged evaluation.

Permanent tests were added for each boundary. The corrected CEX harness has seven passing tests; S-ACT has seven; the combination harness has two.

## 7. Lessons learned

### Confirmed

- PCR should remain advisory and multidimensional.
- Printed volume is more useful than delta-weighted OI alone.
- Whole-chain aggregates lose important local strike/expiry information.
- Contract spread matters materially, but a tighter contract alone is insufficient.
- Static fixed-horizon classification is the wrong optimisation target.
- The system must learn a joint path: which contract, when it becomes executable, and when monetisation is likely before thesis expiry.

### Rejected

- replacing OI with a single put/call ratio;
- treating PCR as directional order flow;
- selecting only the lowest-spread contract;
- imposing a premium floor as the solution;
- assuming midpoint entry repairs economics;
- adding a more complex classifier to the same static target;
- repeatedly reducing the candidate population until a positive historical subset appears;
- invalidating the ticker thesis because its current option contract is unattractive.

## 8. New solution thesis

The next model should not predict “best contract” at one fixed exit. It should estimate a distribution over contract and path states:

1. `P(executable within 1/2/3 sessions)`;
2. `P(+25% before invalidation or time stop)`;
3. expected maximum favourable excursion and maximum adverse excursion;
4. expected time to monetisation;
5. probability that an alternative contract dominates the current contract;
6. probability that waiting improves entry economics without invalidating the ticker thesis.

The decision object should expose:

- ticker thesis: retained unless thesis evidence invalidates it;
- preferred contract now;
- monitored alternative contracts;
- liquidity-maturation probability;
- entry-condition state;
- expected monetisation window;
- uncertainty and data-quality state;
- human execution narrative.

This is a competing-risks/path-prediction problem, not a static binary filter.

## 9. Next backtest phase

The next phase should build research labels only—no production code:

1. Generate daily paths for every monitored contract, not only selected contracts.
2. Extend horizons from 1/3/5 toward the governed 1–20 day holding period where data coverage permits.
3. Label:
   - first executable session;
   - first +10%, +25%, +50% monetisation session;
   - MFE and MAE;
   - target, invalidation and time-stop ordering;
   - spread tightening and volume/OI development;
   - best alternative contract and switch time.
4. Train interpretable survival/logistic benchmarks before nonlinear models.
5. Use nested purged walk-forward validation with embargo for overlapping holdings.
6. Preserve later sessions as a genuinely untouched holdout.
7. Stress wider spreads, missing volume, stale OI, quote dropout, delayed entry and regime changes.
8. Require positive ask-to-bid and 50%-wider-spread returns across multiple sessions before proposing production integration.

## 10. Decision

Do not implement the tested static selectors in production.

Proceed to the path-aware outcome-label and survival-model backtest phase. The evidence supports this direction because the joint contract-and-exit oracle is positive while every static selector and fixed-horizon oracle is negative.

The objective is now precise: learn enough of the positive oracle ceiling without future leakage, while retaining every ticker thesis for human review and separating `MONITOR_CONTRACT` from thesis invalidation.
