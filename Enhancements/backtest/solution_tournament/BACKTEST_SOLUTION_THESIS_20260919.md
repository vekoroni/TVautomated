# AVSHUNTER backtest solution thesis — 19 September 2026

**Decision state:** `RESEARCH_CONTINUES — NO PRODUCTION CHANGE AUTHORISED`  
**Business outcome:** surface accurate, monetisable long-call/long-put opportunities while preserving the ticker thesis when the current contract is not yet executable.

## Executive conclusion

AVSHUNTER does not have one defect that can be repaired with one threshold. The evidence supports a layered failure:

1. The candidate population contains movement/magnitude information, but the current direction and timing do not show a stable positive edge in the available H sample.
2. Options are usually priced above subsequently delivered movement; compression is often already reflected in IV.
3. The historical selector frequently chose contracts with severe quoted friction. That choice is economically dominated by cleaner contracts on the same ticker and side.
4. A hard near-money or tight-spread selector improves the average but loses much of the convex right tail.
5. Only two H sessions meet the current certified normal-completed-run standard. Historical rows can localise failure but cannot promote a production model.

The intelligent fix is therefore **not** “discard more trades.” It is to separate:

- ticker opportunity and direction;
- option price versus expected movement;
- core executable expression;
- convex alternative expression;
- current execution state;
- subsequent lifecycle and outcome learning.

## What this backtest executed

### Round 1 — failure localisation

- 8,950 frozen candidate rows across 9 sessions and 1,556 tickers.
- Exact 1/3/5-session underlying closes and exact selected-contract future chain marks.
- Direction alternatives: recorded, 5-day momentum, 20-day momentum, 5-day mean reversion, and 5/20 consensus.
- Pricing alternatives: spread limits, volatility cheapness, near-money geometry, and combined price-aware states.
- Ranking alternatives: recorded valuation ranks, IV cheapness, spread, and a fixed exploratory composite.
- Ask-to-bid and mid-to-mid marks with session-block bootstrap intervals.

Result:

| Horizon | Recorded direction | Selected option ask→bid | Selected option mid→mid | Mean quote drag |
|---:|---:|---:|---:|---:|
| 1 | +0.01% | −40.63% | −1.30% | +36.99 pts |
| 3 | −0.24% | −43.66% | −5.33% | +36.21 pts |
| 5 | −0.42% | −48.50% | −10.10% | +36.07 pts |

Interpretation: spread/quote friction is the largest measured avoidable loss, but it is not the only cause. Even midpoint performance weakens with time, and recorded direction is negative at 3/5 sessions.

### Round 2 — full contract-family alternatives

For every frozen ticker and direction, the replay loaded the exact entry-session chain and tested pre-registered alternative contracts. No OI or volume hard gate was used. No-quote contracts were ineligible as executable expressions while the ticker thesis remained present.

Paired improvement against the recorded contract, excluding the explicit test/dirty run:

| Alternative | 1 session | 3 sessions | 5 sessions | Better than recorded |
|---|---:|---:|---:|---:|
| Tightest executable spread | +16.01 pts | +15.05 pts | +16.02 pts | 71–73% |
| Near-money | +8.73 pts | +8.98 pts | +12.01 pts | 68–73% |
| Delta 0.35–0.55 core | +9.98 pts | +9.35 pts | +12.11 pts | 69–72% |
| Price/value composite | +12.98 pts | +12.44 pts | +14.96 pts | 73–76% |

This confirms a real contract-expression defect. It also rejects the idea that a cleaner contract alone makes the historical book profitable: the alternatives remain negative after executable quote costs.

### Round 3 — sealed direction holdout

The direction protocol was frozen before opening 2026. Models trained through November 2024; 2025 was calibration/report-only; 2026 was the sealed holdout. Results were scored independently of option pricing.

- Five-day mean reversion produced +0.170% at one session, but did not persist at three or five sessions.
- Gradient boosting produced +0.758% at five sessions (90% session-block interval +0.240% to +1.259%) but only +0.092% and +0.360% at one/three sessions, with near-random AUC at the shorter horizons.
- Logistic regression was inconsistent and had AUC below 0.50 at one/three sessions.
- On H, recent regime and model results changed sign relative to the wider universe, demonstrating regime confounding rather than a stable replacement signal.

**Decision:** no direction model passed the pre-registered consistency bar. The current H direction was approximately flat at one session and negative at three/five sessions; it is not validated, but neither is any tested replacement.

### Round 4 — integrated expression and stress tournament

The next phase joined direction, real CALL/PUT contract families, core/value/convex selection, dynamic option/share/no-trade expression, two-session liquidity maturation, and exact future option quotes. It generated 311,822 scenario rows and tested base performance, 25%/50% spread widening, 10%/25% quote dropout, removal of the best 1%, and SPY bull/bear plus high/low-volatility regimes.

No scenario passed the reliability gate in any governed population. The strongest route was five-day mean-reversion direction with dynamic expression:

| Horizon | Participation | Mean | Spread +50% | Top 1% removed |
|---:|---:|---:|---:|---:|
| 1 | 70.58% | -1.00% | -1.84% | -1.56% |
| 3 | 70.08% | -0.83% | -1.72% | -1.82% |
| 5 | 67.59% | -2.38% | -3.18% | -3.49% |

This materially dominates the recorded-contract losses but remains negative and regime-sensitive. Delayed liquidity recovered contracts for roughly 19–21% of initially missing core families, yet measured recovered contracts averaged -21.58% at three sessions and -24.61% at five. Liquidity maturation is therefore real, but it is not proof of monetisability.

The run also confirmed that core and convex lanes find complementary extreme winners. The next convex test must use the complete contract family as the oracle denominator; a union denominator defined only by the two selected lanes is descriptive and cannot prove full-family recall.

## Root-cause hierarchy

### RC1 — Run evidence is not yet sufficient for promotion

H has nine sessions, one explicitly TEST/dirty run, six legacy runs without modern run-condition truth, and only two certified normal-completed sessions. Thousands of ticker rows are correlated within those sessions and are not independent trials.

**Impact:** confidence intervals based on row count would be false precision; apparent parameter winners can be regime artefacts.

### RC2 — Ranking magnitude is being mistaken for directional alpha

The broader intelligence audit found magnitude information but no stable market-adjusted directional information in the tested bar features. Round 1 likewise did not find a robust directional replacement in the small H sample.

**Impact:** the pipeline can identify names likely to move but still buy the wrong side. Better contract selection cannot repair wrong direction.

### RC3 — Options are generally rich relative to delivered movement

The weekly-chain study covers 94 Fridays and approximately 337,000 observations. Overall variance delivery was roughly 0.61–0.65 of IV; the cheapest volatility fifth approached fair value, while rich-volatility groups were materially overpriced. Compression itself was not an underpricing signal.

**Impact:** a correct ticker thesis can still lose in the option because the expected move was already priced.

### RC4 — Contract execution friction is excessive

Round 1 measured roughly 36–37 return points of ask-to-bid versus mid-to-mid drag. Round 2 shows alternative contracts beat the recorded contract in most paired cases.

**Impact:** historical contract selection converted a weak opportunity into a much worse executable trade.

### RC5 — Mean optimization conflicts with convex-tail capture

Near-money, delta-core, and value rules improve average outcomes but recall only a minority of families containing a +100% contract. The recorded contract had higher tail recall in some horizons despite a much worse average.

**Impact:** replacing the selector with one hard “best contract” can remove precisely the asymmetric outcomes long options are meant to capture.

### RC6 — The short-horizon convex hypothesis is not testable in H

Every recorded `hold` in H is 12–20 sessions. The pre-registered convex satellite requires a genuine 1–5-session thesis and therefore selected zero contracts by design.

**Impact:** zero activation is a data-contract limitation, not evidence that the satellite fails.

### RC7 — Simple direction replacement is not robust out of sample

The sealed 2026 test produced horizon-specific pockets of performance, not one stable rule. The nonlinear model's strongest five-session result did not reproduce at one/three sessions; H-only regime signals reversed in the broader universe.

**Impact:** deploying a new direction model now would be selection on noise. The next direction study must condition on thesis horizon and market state, retain abstention, and add more independent sessions.

## Solution candidates: accepted, rejected, and still open

### Accepted for the next research round

1. **Two-lane contract presentation**
   - Core: executable near-money/delta-core contract.
   - Convex alternative: separately ranked; never hidden merely because its current liquidity is developing.
   - Human sees both lanes and their evidence; neither changes the ticker thesis.

2. **Dynamic expression choice**
   - Cheap/fair option: long call or long put may express the thesis.
   - Rich option with bullish thesis: compare long shares.
   - Rich option with bearish thesis: option or no trade; short shares remain outside scope.
   - No quote: exact contract is non-executable, but the family remains monitored and re-ranked.

3. **Separate models for separate probabilities**
   - probability the ticker moves in the governed direction;
   - probability and magnitude of movement;
   - probability a contract becomes executable;
   - probability the contract monetises conditional on the thesis path.

4. **Tail-aware evaluation**
   - Mean and hit rate alone are insufficient.
   - Every candidate rule must report +50/+100/+200/+500% recall and contribution.

### Rejected as complete fixes

- Spread-only hard filtering.
- OI or volume as a deletion gate.
- One universal “best contract” score.
- Treating compression as automatic cheap convexity.
- Using cautious/central/upside valuation rank as proof of directional alpha.
- Replacing missing data with zero.
- Invalidating a ticker thesis because the current option quote is absent or temporarily unattractive.

### Still open

- A profitable direction/timing policy.
- A validated short-horizon convex satellite.
- Calibrated probability models; current outcomes are insufficient for activation.
- Intraday entry timing and liquidity maturation, which need point-in-time observations rather than completed-session snapshots alone.

## Remaining backtest sequence

### Batch A — Direction and timing tournament — completed, no model advanced

The larger underlying history was used with frozen train/calibration/holdout periods. Deterministic momentum, mean reversion, SPY regime, logistic regression, and histogram gradient boosting were compared. No route was consistently positive across 1/3/5 sessions.

**Gate remains closed:** no option-expression authority should assume a new direction model until a horizon-conditioned route shows held-out benefit over the current signal and unconditional base rate on more independent sessions.

### Batch B — Instrument-choice tournament

On the weekly-chain year and daily post-backfill chains, compare option versus allowed share expression using point-in-time IV/realised-volatility cheapness. Report CALL and PUT separately, because bearish opportunities do not have the permitted share substitute.

**Gate:** the chooser must improve outcomes without manufacturing performance from no-trade zeros or midpoint fills.

**Round 4 status:** completed for the initial deterministic chooser. It improved outcomes substantially but failed every reliability gate. The next version must use thesis-conditioned required-move economics rather than IV cheapness percentile alone.

### Batch C — Convex-tail forensics

For every family containing a +100/+200/+500% contract, measure whether the winning contract was knowable at entry from moneyness, DTE, IV price, spread, activity trajectory, catalyst proximity, and underlying state. Use case-control sampling and leave-session-out validation.

**Gate:** the convex lane must increase tail recall beyond the core lane without making the combined candidate set operationally unbounded.

### Batch D — Liquidity maturation

Build labels from Phantom trajectories: executable within 1/2/3 sessions, minimum spread, first meaningful volume, and OI change between completed sessions. Compare calibrated logistic and survival models with simple deterministic baselines.

**Gate:** no model activation until sufficient labelled events, calibration, and held-out performance exist.

**Round 4 status:** deterministic two-session maturation was tested. It recovered availability but produced negative measured economics. Future work must predict liquidity development and payoff separately.

### Batch E — Thesis-conditioned entry and path stress

For each ticker/contract family, calculate the required underlying move after quoted spread, IV, theta, DTE, and thesis horizon. Test immediate entry, one/two-session deferral, `MONITOR_OPTION`, allowed CALL-share substitution, and no-current-expression for PUTs. Measure executable-bid MFE/MAE across sessions 1–5 and stress gap continuation/reversal, IV crush/expansion, spread widening, quote loss, regime shifts, and removal of extreme winners.

**Gate:** a frozen route must remain positive after costs and stress on held-out completed sessions, without future-data dependency and with useful participation.

## Build decision

Do **not** change production selection or authority from these results. The backtest has produced actionable research findings—core contract quality, two-lane presentation, dynamic expression, and liquidity monitoring—but has proved that none is yet a complete monetisation solution. Execute Batch E and full-family tail forensics, then use the fix register to promote only changes supported by independent, point-in-time evidence.

## Reproducible artefacts

- `round1_solution_tournament.py`
- `round1_results.json`
- `ROUND1_VALIDATION_REPORT_20260919.md`
- `ROUND2_PROTOCOL_20260919.md`
- `round2_contract_family.py`
- `round2_contract_family_results.json`
- `ROUND2_VALIDATION_REPORT_20260919.md`
- `ROUND3_DIRECTION_PROTOCOL_20260919.md`
- `round3_direction_results.json`
- `ROUND3_DIRECTION_REPORT_20260919.md`
- `ROUND4_END_TO_END_STRESS_PROTOCOL_20260919.md`
- `round4_end_to_end_stress_results.json`
- `ROUND4_END_TO_END_STRESS_REPORT_20260919.md`
- `ROUND4_DIAGNOSTIC_FINDINGS_20260919.md`
- `test_round1_solution_tournament.py` — 14 tests passing
