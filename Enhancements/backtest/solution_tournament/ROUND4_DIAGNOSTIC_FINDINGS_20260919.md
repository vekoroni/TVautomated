# AVSHUNTER Round 4 — diagnostic findings and next testable solution

**State:** `RESEARCH CONTINUES — NO PRODUCTION CHANGE AUTHORISED`  
**Evidence:** 311,822 end-to-end scenario rows; 279,846 rows after excluding explicit test/dirty runs; 8 sessions in the primary population.  
**Execution convention:** option entry at ask and exit at bid; missing quotes and no-trade states remain null.

## Decision

No tested end-to-end solution is reliable enough to implement. Zero reliability gates passed in the full historical population, the test/dirty-excluded population, or the two-session certified population.

The experiment nevertheless localised the monetisation problem more sharply:

1. Contract selection is materially improvable, but contract selection alone cannot create positive expectancy.
2. Replacing rich CALL options with shares removes most option friction, but the tested direction/timing rules remain too weak for a reliable positive result.
3. Waiting for liquidity recovers additional contracts, but recovered liquidity is not the same as recovered economics.
4. A convex lane is complementary to a core lane for extreme outcomes, but its mean return and coverage are presently insufficient.

## Primary results

The least-negative route at every horizon was the five-day mean-reversion direction rule with dynamic option/share/no-trade expression:

| Horizon | Participation | Mean | 90% session CI | Spread widened 50% | Best 1% removed | Bull | Bear |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 session | 70.58% | -1.00% | -2.09% to +0.02% | -1.84% | -1.56% | -3.89% | -0.63% |
| 3 sessions | 70.08% | -0.83% | -2.59% to +0.87% | -1.72% | -1.82% | -2.22% | -0.61% |
| 5 sessions | 67.59% | -2.38% | -3.47% to -1.33% | -3.18% | -3.49% | -1.39% | -2.58% |

This is a large improvement over the recorded contracts, which returned -40.74%, -43.14%, and -47.82% at the same horizons. It is not a passing solution: the base means remain negative, lower confidence bounds are negative, spread stress is negative, tail removal is negative, and both market regimes are not positive.

## Failure attribution

### Direction and instrument expression

For the best dynamic rule, the CALL-share component returned +0.11% at one session, then -0.45% and -1.32% at three and five sessions. Its option component returned -6.80%, -2.83%, and -8.29%.

This shows two separate problems:

- the option leg still carries adverse pricing and execution economics;
- the underlying direction/timing edge is too small and too short-lived to absorb option friction.

Therefore the next solution must condition contract admission on the required underlying move and expected holding path, not merely select the cleanest available contract.

### Liquidity maturation

When no core contract existed initially, a two-session search recovered:

| Horizon | Initially absent | Contract recovered | Measured exit | Mean recovered return |
|---:|---:|---:|---:|---:|
| 1 | 5,495 | 1,064 | 0 | not measurable before the horizon |
| 3 | 4,689 | 968 | 819 | -21.58% |
| 5 | 4,005 | 843 | 802 | -24.61% |

Roughly 19–21% of initially absent core contracts became selectable, confirming that liquidity is dynamic. Their negative measured returns prove that “became liquid” must not be treated as “became monetisable.” The lifecycle model needs separate probabilities for executable liquidity and profitable thesis-conditioned payoff.

### Core and convex lanes

The convex lane had only about 7–8% participation and negative mean returns in every tested direction/horizon. However, within the limited two-lane comparison it found some +100% and +200% outcomes missed by the core lane, while the core lane found others missed by convex.

The present union-recall statistic is descriptive only: its denominator is defined by winners found in either of those two lanes, so a 100% union is tautological. The next tail test must use the complete governed contract family as the oracle denominator and ask whether the winning contract was identifiable from entry-time evidence.

## Research-harness assurance

During review, the dynamic chooser was found to consult later exit-quote availability when deciding option versus shares. That look-ahead path was removed. A permanent regression now proves that a missing future quote cannot alter an entry-time instrument choice. The clean recomputation changed participation slightly but did not change the economic conclusion. Fourteen adversarial tests pass.

## Reliable next solution to test — not yet to build

The evidence supports a **thesis-conditioned entry and path tournament**, not another static selector:

1. Preserve the ticker thesis and both contract lanes.
2. At each completed-session observation, calculate the option's required underlying move after quoted spread, IV, theta, and remaining DTE.
3. Admit an option only when the governed expected move distribution clears that requirement with a pre-registered margin; otherwise show it as `MONITOR_OPTION`, use shares for permitted bullish expression, or show `NO_CURRENT_EXPRESSION` for bearish cases.
4. Test deterministic entry deferral for one and two sessions when spread/IV conditions improve while the thesis remains valid.
5. Measure maximum favourable and adverse option excursions across sessions 1–5, not only fixed endpoint returns, using executable bid marks.
6. Stress delayed entry, missed moves, spread widening, quote loss, IV crush/expansion, gap continuation/reversal, bull/bear regimes, and removal of extreme winners.
7. Run full-family convex forensics with a non-tautological oracle denominator.

Promotion requires a frozen rule to remain positive after costs and stress on held-out completed sessions, with useful participation and no future-data dependency. Until that happens, AVSHUNTER should present opportunities and monitoring states to the human trader but should not claim that the tested options selector has positive expectancy.

